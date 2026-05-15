from django.db import migrations


class Migration(migrations.Migration):
    """Drop the legacy `Player` model; recreated next migration with NHL ID PK."""

    dependencies = [
        ("players", "0002_alter_player_nhl_api_id"),
    ]

    operations = [
        migrations.DeleteModel(name="Player"),
    ]
