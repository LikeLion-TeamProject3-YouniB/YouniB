# Generated by Django 5.1.4 on 2024-12-11 13:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_remove_customuser_first_name_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='major',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Major'),
        ),
        migrations.AddField(
            model_name='customuser',
            name='school',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='School'),
        ),
    ]