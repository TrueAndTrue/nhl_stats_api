# Generated by Django 4.2.7 on 2023-11-10 04:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("players", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="player",
            name="nhl_api_id",
            field=models.IntegerField(unique=True),
        ),
    ]