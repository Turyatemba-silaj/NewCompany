from django.db import migrations


def refresh_paymee_receivables(apps, schema_editor):
    schema_editor.execute(
        """
        WITH payment_totals AS (
            SELECT invoice_id, COALESCE(SUM(amount), 0) AS amount_paid, MAX(payment_date) AS last_payment_date
            FROM payments
            GROUP BY invoice_id
        )
        UPDATE paymees
        SET
            client_id = invoices.client_id,
            total_amount = COALESCE(invoices.total_amount, 0),
            amount_paid = COALESCE(payment_totals.amount_paid, 0),
            due_date = invoices.due_date,
            last_payment_date = payment_totals.last_payment_date,
            status = CASE
                WHEN invoices.status = 'cancelled' THEN 'cancelled'
                WHEN COALESCE(invoices.total_amount, 0) <= 0 THEN 'pending'
                WHEN COALESCE(payment_totals.amount_paid, 0) > COALESCE(invoices.total_amount, 0) THEN 'overpaid'
                WHEN COALESCE(payment_totals.amount_paid, 0) >= COALESCE(invoices.total_amount, 0) THEN 'paid'
                WHEN COALESCE(payment_totals.amount_paid, 0) > 0 THEN 'partial'
                WHEN invoices.due_date IS NOT NULL AND invoices.due_date < CURRENT_DATE THEN 'overdue'
                ELSE 'pending'
            END,
            updated_at = CURRENT_TIMESTAMP
        FROM invoices
        LEFT JOIN payment_totals ON payment_totals.invoice_id = invoices.invoice_id
        WHERE paymees.invoice_id = invoices.invoice_id
        """
    )


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0048_alter_paymee_options_paymee_client_paymee_currency_and_more"),
    ]

    operations = [
        migrations.RunPython(refresh_paymee_receivables, migrations.RunPython.noop),
    ]
