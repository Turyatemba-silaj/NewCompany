from django.db import migrations


def repair_invoice_total_amount(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'invoices' AND column_name = 'total_amount'
            """
        )
        if not cursor.fetchone():
            schema_editor.execute(
                "ALTER TABLE invoices ADD COLUMN total_amount numeric(12, 2) NOT NULL DEFAULT 0"
            )


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0094_allow_day_and_night_attendance"),
    ]

    operations = [
        migrations.RunPython(repair_invoice_total_amount, migrations.RunPython.noop),
    ]
