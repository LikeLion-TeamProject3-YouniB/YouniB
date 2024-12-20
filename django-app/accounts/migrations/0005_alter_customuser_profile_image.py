# Generated by Django 5.1.4 on 2024-12-12 04:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_alter_customuser_profile_image'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='profile_image',
            field=models.ImageField(blank=True, default='profile_images/default_profile.png', null=True, upload_to='profile_images/', verbose_name='Profile Image'),
        ),
    ]