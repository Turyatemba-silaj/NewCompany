from django.db import migrations


def update_supervisor_employee_numbers(apps, schema_editor):
    Employee = apps.get_model("webroaster", "Employee")
    supervisors = list(Employee.objects.filter(role="supervisor").order_by("employee_id"))

    for employee in supervisors:
        employee.employee_number = f"__SUP_TMP_{employee.employee_id}"
        employee.save(update_fields=["employee_number"])

    for index, employee in enumerate(supervisors, start=1):
        employee.employee_number = f"SUP {index:03d}"
        employee.save(update_fields=["employee_number"])


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0046_performance_evaluation_areas_for_improvement_and_more"),
    ]

    operations = [
        migrations.RunPython(update_supervisor_employee_numbers, migrations.RunPython.noop),
    ]

