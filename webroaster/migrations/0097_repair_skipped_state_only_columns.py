from django.db import migrations


def add_column_if_missing(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    statements = [
        """
        ALTER TABLE expenses
        ADD COLUMN IF NOT EXISTS approved_by_id bigint NULL
        """,
        """
        ALTER TABLE disciplinary_actions
        ADD COLUMN IF NOT EXISTS status varchar(30) NOT NULL DEFAULT 'reported'
        """,
        """
        CREATE INDEX IF NOT EXISTS expenses_approved_by_id_idx
        ON expenses (approved_by_id)
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'expenses_approved_by_id_fk'
            ) THEN
                ALTER TABLE expenses
                ADD CONSTRAINT expenses_approved_by_id_fk
                FOREIGN KEY (approved_by_id)
                REFERENCES employees (employee_id)
                DEFERRABLE INITIALLY DEFERRED;
            END IF;
        END
        $$
        """,
    ]

    with schema_editor.connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0096_performance_indexes"),
    ]

    operations = [
        migrations.RunPython(add_column_if_missing, migrations.RunPython.noop),
    ]
