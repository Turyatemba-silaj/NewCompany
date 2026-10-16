"""Use MySQL casts and JOIN syntax for the employee backfill."""
from importlib import import_module

from django.db import migrations

original = import_module("NewCompany.sqlite_migrations.0022_employee_armed_status_employee_authority_level_and_more")


def backfill_employee_roles(apps, schema_editor):
    # Keep the data mapping shared with SQLite without duplicating the CASE rules.
    def mysql_sql(execute, sql, params, many, context):
        sql = sql.replace(" AS text)", " AS CHAR)")
        if "UPDATE salaries" in sql:
            sql = """
                UPDATE salaries
                JOIN employees ON salaries.employee_id = employees.employee_id
                SET salaries.basic_salary = employees.salary_scale
                WHERE employees.salary_scale IS NOT NULL
            """
        return execute(sql, params, many, context)

    with schema_editor.connection.execute_wrapper(mysql_sql):
        original.backfill_employee_roles(apps, schema_editor)


class Migration(original.Migration):
    operations = [
        migrations.RunPython(backfill_employee_roles, migrations.RunPython.noop)
        if isinstance(operation, migrations.RunPython) and operation.code is original.backfill_employee_roles
        else operation
        for operation in original.Migration.operations
    ]
