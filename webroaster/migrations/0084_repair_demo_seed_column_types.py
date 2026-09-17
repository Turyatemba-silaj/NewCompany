from django.db import migrations


def repair_demo_seed_column_types(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'guards' AND column_name = 'armed_status'
            """
        )
        row = cursor.fetchone()
        if row and row[0] == "boolean":
            schema_editor.execute(
                """
                ALTER TABLE guards
                ALTER COLUMN armed_status DROP DEFAULT,
                ALTER COLUMN armed_status TYPE varchar(20)
                USING CASE WHEN armed_status THEN 'armed' ELSE 'unarmed' END,
                ALTER COLUMN armed_status SET DEFAULT 'unarmed'
                """
            )

        cursor.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'patrol_logs' AND column_name = 'duration'
            """
        )
        row = cursor.fetchone()
        if row and row[0] == "interval":
            schema_editor.execute(
                """
                ALTER TABLE patrol_logs
                ALTER COLUMN duration TYPE numeric(5, 2)
                USING ROUND((EXTRACT(EPOCH FROM duration) / 3600.0)::numeric, 2)
                """
            )


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0083_relax_legacy_only_columns"),
    ]

    operations = [
        migrations.RunPython(repair_demo_seed_column_types, migrations.RunPython.noop),
    ]
