from django.db import migrations


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute('ALTER TABLE attendance DROP CONSTRAINT IF EXISTS webroaster_attendance_employee_id_date_847b5788_uniq')


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute('ALTER TABLE attendance ADD CONSTRAINT webroaster_attendance_employee_id_date_847b5788_uniq UNIQUE (employee_id, date)')


class Migration(migrations.Migration):
    dependencies = [
        ("webroaster", "0093_advance_request_received_notification"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
