"""Use MySQL UPDATE JOIN syntax when refreshing receivables."""
from importlib import import_module

from django.db import migrations

original = import_module("NewCompany.sqlite_migrations.0049_refresh_paymee_receivables")


def refresh_paymee_receivables(apps, schema_editor):
    # The shared migration checks for legacy columns before issuing this update.
    def mysql_sql(execute, sql, params, many, context):
        if "WITH payment_totals AS" in sql:
            sql = """
                UPDATE paymees
                JOIN invoices ON paymees.invoice_id = invoices.invoice_id
                LEFT JOIN (
                    SELECT invoice_id, COALESCE(SUM(amount), 0) AS amount_paid,
                           MAX(payment_date) AS last_payment_date
                    FROM payments GROUP BY invoice_id
                ) payment_totals ON payment_totals.invoice_id = invoices.invoice_id
                SET paymees.client_id = invoices.client_id,
                    paymees.total_amount = COALESCE(invoices.total_amount, 0),
                    paymees.amount_paid = COALESCE(payment_totals.amount_paid, 0),
                    paymees.due_date = invoices.due_date,
                    paymees.last_payment_date = payment_totals.last_payment_date,
                    paymees.status = CASE
                        WHEN invoices.status = 'cancelled' THEN 'cancelled'
                        WHEN COALESCE(invoices.total_amount, 0) <= 0 THEN 'pending'
                        WHEN COALESCE(payment_totals.amount_paid, 0) > invoices.total_amount THEN 'overpaid'
                        WHEN COALESCE(payment_totals.amount_paid, 0) >= invoices.total_amount THEN 'paid'
                        WHEN COALESCE(payment_totals.amount_paid, 0) > 0 THEN 'partial'
                        WHEN invoices.due_date < CURRENT_DATE THEN 'overdue'
                        ELSE 'pending'
                    END,
                    paymees.updated_at = CURRENT_TIMESTAMP
            """
        return execute(sql, params, many, context)

    with schema_editor.connection.execute_wrapper(mysql_sql):
        original.refresh_paymee_receivables(apps, schema_editor)


class Migration(original.Migration):
    operations = [migrations.RunPython(refresh_paymee_receivables, migrations.RunPython.noop, atomic=False)]
