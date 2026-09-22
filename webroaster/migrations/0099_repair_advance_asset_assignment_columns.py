from django.db import migrations


def repair_advance_asset_assignment_columns(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    statements = [
        "ALTER TABLE advances ADD COLUMN IF NOT EXISTS verification_status varchar(20) NOT NULL DEFAULT 'pending'",
        "ALTER TABLE advances ADD COLUMN IF NOT EXISTS verified_at timestamp with time zone NULL",
        "ALTER TABLE advances ADD COLUMN IF NOT EXISTS verified_by_id bigint NULL",
        "CREATE INDEX IF NOT EXISTS advances_verified_by_id_idx ON advances (verified_by_id)",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'advances_verified_by_id_fk'
            ) THEN
                ALTER TABLE advances
                ADD CONSTRAINT advances_verified_by_id_fk
                FOREIGN KEY (verified_by_id)
                REFERENCES employees(employee_id)
                DEFERRABLE INITIALLY DEFERRED;
            END IF;
        END $$;
        """,
        "ALTER TABLE asset_assignments ADD COLUMN IF NOT EXISTS accountability_notes text NOT NULL DEFAULT ''",
        "ALTER TABLE asset_assignments ADD COLUMN IF NOT EXISTS accountability_status varchar(30) NOT NULL DEFAULT 'pending_acknowledgement'",
        "ALTER TABLE asset_assignments ADD COLUMN IF NOT EXISTS acknowledged_at timestamp with time zone NULL",
        "ALTER TABLE asset_assignments ADD COLUMN IF NOT EXISTS condition_issued varchar(20) NOT NULL DEFAULT 'good'",
        "ALTER TABLE asset_assignments ADD COLUMN IF NOT EXISTS condition_returned varchar(20) NOT NULL DEFAULT ''",
        "ALTER TABLE asset_assignments ADD COLUMN IF NOT EXISTS issued_by_id bigint NULL",
        "ALTER TABLE asset_assignments ADD COLUMN IF NOT EXISTS received_by_id bigint NULL",
        "CREATE INDEX IF NOT EXISTS asset_assignments_issued_by_id_idx ON asset_assignments (issued_by_id)",
        "CREATE INDEX IF NOT EXISTS asset_assignments_received_by_id_idx ON asset_assignments (received_by_id)",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'asset_assignments_issued_by_id_fk'
            ) THEN
                ALTER TABLE asset_assignments
                ADD CONSTRAINT asset_assignments_issued_by_id_fk
                FOREIGN KEY (issued_by_id)
                REFERENCES employees(employee_id)
                DEFERRABLE INITIALLY DEFERRED;
            END IF;
        END $$;
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'asset_assignments_received_by_id_fk'
            ) THEN
                ALTER TABLE asset_assignments
                ADD CONSTRAINT asset_assignments_received_by_id_fk
                FOREIGN KEY (received_by_id)
                REFERENCES employees(employee_id)
                DEFERRABLE INITIALLY DEFERRED;
            END IF;
        END $$;
        """,
    ]
    for statement in statements:
        schema_editor.execute(statement)


class Migration(migrations.Migration):
    dependencies = [
        ("webroaster", "0098_repair_asset_state_only_columns"),
    ]

    operations = [
        migrations.RunPython(repair_advance_asset_assignment_columns, migrations.RunPython.noop),
    ]
