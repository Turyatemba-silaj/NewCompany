from django.db import migrations


def repair_incident_reported_by(apps, schema_editor):
    schema_editor.execute("ALTER TABLE incidents ADD COLUMN IF NOT EXISTS reported_by varchar(255) NOT NULL DEFAULT ''")
    schema_editor.execute(
        """
        UPDATE incidents
        SET reported_by = COALESCE(NULLIF(reported_by, ''), reported_by_id::text, '')
        WHERE reported_by = '' AND reported_by_id IS NOT NULL
        """
    )


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0081_repair_legacy_schema_gaps"),
    ]

    operations = [
        migrations.RunPython(repair_incident_reported_by, migrations.RunPython.noop),
    ]
