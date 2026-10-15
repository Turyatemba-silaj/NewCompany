from django.db import migrations


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute('ALTER TABLE deployments ALTER COLUMN guard_id DROP NOT NULL;')


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0087_site_site_code"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
