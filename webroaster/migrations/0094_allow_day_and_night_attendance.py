from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("webroaster", "0093_advance_request_received_notification"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE attendance "
                "DROP CONSTRAINT IF EXISTS webroaster_attendance_employee_id_date_847b5788_uniq"
            ),
            reverse_sql=(
                "ALTER TABLE attendance "
                "ADD CONSTRAINT webroaster_attendance_employee_id_date_847b5788_uniq "
                "UNIQUE (employee_id, date)"
            ),
        ),
    ]
