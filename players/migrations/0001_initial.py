# Generated by Django 4.2.7 on 2023-11-10 03:24

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Player",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("nhl_api_id", models.IntegerField()),
                ("first_name", models.CharField(max_length=255)),
                ("last_name", models.CharField(max_length=255)),
                ("is_active", models.BooleanField()),
                ("jersey_number", models.IntegerField()),
                ("primary_position", models.CharField(max_length=255)),
                ("headshot", models.CharField(max_length=255)),
                ("hero_image", models.CharField(max_length=255)),
                ("birth_date", models.DateField()),
                ("height_in_cm", models.IntegerField()),
                ("weight_in_lbs", models.IntegerField()),
            ],
        ),
    ]
