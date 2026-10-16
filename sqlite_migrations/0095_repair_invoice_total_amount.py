from NewCompany.migration_compat import column_names
from django.db import migrations


def repair_invoice_total_amount(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        column_rows = [(name,) for name in column_names(schema_editor, 'invoices') if name == 'total_amount']
        if not (column_rows[0] if column_rows else None):
            schema_editor.execute(
                "ALTER TABLE invoices ADD COLUMN total_amount numeric(12, 2) NOT NULL DEFAULT 0"
            )


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0094_allow_day_and_night_attendance"),
    ]

    operations = [
        migrations.RunPython(repair_invoice_total_amount, migrations.RunPython.noop, atomic=False),
    ]
