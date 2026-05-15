from django.db import migrations


class Migration(migrations.Migration):
    """Drop the per-event-type tables; we're consolidating to one Event model."""

    dependencies = [
        ("events", "0007_alter_blockedshot_event_id_alter_faceoff_event_id_and_more"),
    ]

    operations = [
        migrations.DeleteModel(name="BlockedShot"),
        migrations.DeleteModel(name="Faceoff"),
        migrations.DeleteModel(name="Giveaway"),
        migrations.DeleteModel(name="Goal"),
        migrations.DeleteModel(name="Hit"),
        migrations.DeleteModel(name="MissedShot"),
        migrations.DeleteModel(name="Penalty"),
        migrations.DeleteModel(name="Shot"),
    ]
