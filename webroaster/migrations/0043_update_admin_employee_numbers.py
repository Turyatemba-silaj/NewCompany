from django.db import migrations


def update_admin_employee_numbers(apps, schema_editor):
    Employee = apps.get_model("webroaster", "Employee")
    admin_employees = list(
        Employee.objects.exclude(role__in=("guard", "supervisor")).order_by("employee_id")
    )

    for employee in admin_employees:
        employee.employee_number = f"__ADM_TMP_{employee.employee_id}"
        employee.save(update_fields=["employee_number"])

    for index, employee in enumerate(admin_employees, start=1):
        employee.employee_number = f"ADM {index:03d}"
        employee.save(update_fields=["employee_number"])


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0042_leave_feedback_leave_hr_decided_at_and_more"),
    ]

    operations = [
        migrations.RunPython(update_admin_employee_numbers, migrations.RunPython.noop),
    ]

