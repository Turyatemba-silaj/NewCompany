from django.db import migrations


def repair_asset_state_only_columns(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    statements = [
        """
        ALTER TABLE assets
        ADD COLUMN IF NOT EXISTS asset_name varchar(255) NOT NULL DEFAULT ''
        """,
        """
        ALTER TABLE assets
        ADD COLUMN IF NOT EXISTS condition varchar(20) NOT NULL DEFAULT ''
        """,
    ]

    with schema_editor.connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0097_repair_skipped_state_only_columns"),
    ]

    operations = [
        migrations.RunPython(repair_asset_state_only_columns, migrations.RunPython.noop),
    ]
