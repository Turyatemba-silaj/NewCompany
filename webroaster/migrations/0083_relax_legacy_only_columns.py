from django.db import migrations


LEGACY_ONLY_COLUMNS = {
    "employees": ["role_name", "position_title", "deployment_area"],
    "guards": ["uniform_size", "training_level", "badge_number"],
    "supervisors": ["assigned_zone", "experience_years"],
    "training": ["status"],
    "leaves": ["days"],
    "disciplinary_actions": ["action_type", "penalty"],
    "performance_evaluations": ["eval_date"],
    "sites": ["city"],
    "shifts": ["shift_name"],
    "assets": ["serial_number"],
    "incidents": ["incident_date", "deployment_id", "reported_by_id", "guard_id"],
    "patrol_logs": ["patrol_time", "observations", "guard_id"],
    "deployments": ["supervisor_id"],
    "attendance": ["status"],
    "salaries": ["pay_period_start", "pay_period_end", "net_salary", "payment_method", "status"],
    "advances": ["request_date", "purpose", "repayment_status"],
    "invoices": ["paid_amount", "balance_amount"],
    "budgets": ["category", "remaining_amount"],
    "expenses": ["receipt_no", "remarks"],
}


def relax_legacy_only_columns(apps, schema_editor):
    quote_name = schema_editor.quote_name
    with schema_editor.connection.cursor() as cursor:
        for table_name, column_names in LEGACY_ONLY_COLUMNS.items():
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s
                """,
                [table_name],
            )
            existing_columns = {row[0] for row in cursor.fetchall()}
            for column_name in column_names:
                if column_name in existing_columns:
                    schema_editor.execute(
                        f"ALTER TABLE {quote_name(table_name)} ALTER COLUMN {quote_name(column_name)} DROP NOT NULL"
                    )


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0082_repair_incident_reported_by"),
    ]

    operations = [
        migrations.RunPython(relax_legacy_only_columns, migrations.RunPython.noop),
    ]
