from django.db import migrations


class Migration(migrations.Migration):
    """Drop the legacy `Games` model; replaced by a redesigned `Game`."""

    dependencies = [
        ("games", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(name="Games"),
    ]
