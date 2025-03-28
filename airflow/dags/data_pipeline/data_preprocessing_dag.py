from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials
from airflow.providers.postgres.hooks.postgres import PostgresHook
import os
import subprocess
import json
import logging

# Google Drive API 인증 설정
SERVICE_ACCOUNT_FILE = '/opt/airflow/google-drive-apikey.json'
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

# 경로 설정
DOWNLOAD_DIR = "/opt/airflow/data"
OUTPUT_DIR = "/opt/airflow/output"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 로그 설정
logger = logging.getLogger("airflow.task")
logger.setLevel(logging.INFO)

# PostgreSQL 테이블에서 pending 파일 가져오기
def fetch_pending_files():
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    conn = pg_hook.get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT file_id, file_name, folder_name
        FROM public.file_metadata
        WHERE status = 'pending';
    """)
    files = cursor.fetchall()

    cursor.close()
    conn.close()

    return files

# Google Drive에서 파일 다운로드
def download_file_from_gdrive(file_id, destination_path):
    request = drive_service.files().get_media(fileId=file_id)
    with open(destination_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            logger.info(f"Download progress: {int(status.progress() * 100)}%")

# MinerU로 파일 처리
def run_mineru_and_save_output(file_id, file_name):
    pdf_path = os.path.join(DOWNLOAD_DIR, file_name)
    download_file_from_gdrive(file_id, pdf_path)

    mineru_command = [
        "magic-pdf",
        "-p", pdf_path,
        "-o", OUTPUT_DIR,
        "--method", "auto"
    ]

    try:
        subprocess.run(mineru_command, check=True)
        logger.info(f"MinerU processing completed for: {pdf_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error during MinerU processing for {pdf_path}: {e}")
        raise RuntimeError("MinerU processing failed.")

    content_json_path = find_content_json(OUTPUT_DIR)
    return content_json_path

# 처리된 JSON 파일 찾기
def find_content_json(output_dir):
    for root, dirs, files in os.walk(output_dir):
        for file in files:
            if file.endswith("_content_list.json"):
                return os.path.join(root, file)
    raise FileNotFoundError("No _content_list.json file found in the output directory.")

# 데이터 저장: processed_data_queue에 저장
def save_to_processed_data_queue(file_id, processed_data):
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    conn = pg_hook.get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO processed_data_queue (file_id, processed_data, status)
            VALUES (%s, %s, 'pending_for_review');
        """, (file_id, json.dumps(processed_data)))
        conn.commit()
        logger.info(f"Data saved to processed_data_queue for file_id: {file_id}")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error saving to processed_data_queue for file_id {file_id}: {e}")
    finally:
        cursor.close()
        conn.close()

# PostgreSQL 상태 업데이트
def update_file_status(file_id, status):
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    conn = pg_hook.get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE file_metadata
            SET status = %s
            WHERE file_id = %s;
        """, (status, file_id))
        conn.commit()
        logger.info(f"Updated status to '{status}' for file_id: {file_id}")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error updating status for file_id {file_id}: {e}")
    finally:
        cursor.close()
        conn.close()

# 에러 발생 시 상태 업데이트
def update_file_status_failed(file_id):
    update_file_status(file_id, "failed")

# Airflow 작업 정의
def process_pending_files(**kwargs):
    files = fetch_pending_files()

    if not files:
        logger.info("No pending files to process.")
        return

    for file_id, file_name, folder_name in files:
        logger.info(f"Processing file: {file_name} in folder: {folder_name}")

        try:
            # MinerU로 처리
            content_json_path = run_mineru_and_save_output(file_id, file_name)

            # 처리 결과 저장
            processed_data = {"file_name": file_name, "folder_name": folder_name, "content_path": content_json_path}
            save_to_processed_data_queue(file_id, processed_data)

            # 상태 업데이트
            update_file_status(file_id, "processed")
        except Exception as e:
            logger.error(f"Error processing file {file_name}: {e}")
            update_file_status_failed(file_id)

# Airflow DAG 정의
with DAG(
    dag_id="integrated_data_processing_pipeline",
    start_date=datetime(2023, 1, 1),
    schedule_interval=None,
    catchup=False,
) as dag:

    detect_and_process_files = PythonOperator(
        task_id="detect_and_process_files",
        python_callable=process_pending_files,
        provide_context=True,
    )

    detect_and_process_files
