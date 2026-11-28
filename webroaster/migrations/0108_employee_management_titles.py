from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("webroaster", "0107_advance_routing")]

    operations = [
        migrations.AlterField(
            model_name="employee",
            name="role",
            field=models.CharField(
                choices=[('guard', 'Guard'),
                 ('supervisor', 'Supervisor'),
                 ('manager', 'Manager'),
                 ('operations_officer', 'Operations Officer'),
                 ('hr_officer', 'HR Officer'),
                 ('finance_officer', 'Finance Officer'),
                 ('administrator', 'Administrator'),
                 ('general_manager', 'General Manager'),
                 ('head_of_finance', 'Head of Finance')],
                default="guard",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="employee",
            name="position",
            field=models.CharField(
                choices=[('security_guard', 'Security Guard'),
                 ('site_supervisor', 'Site Supervisor'),
                 ('regional_supervisor', 'Regional Supervisor'),
                 ('operations_officer', 'Operations Officer'),
                 ('hr_officer', 'HR Officer'),
                 ('finance_officer', 'Finance Officer'),
                 ('administrator', 'Administrator'),
                 ('general_manager', 'General Manager'),
                 ('head_of_finance', 'Head of Finance')],
                default="security_guard",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="employee",
            name="department",
            field=models.CharField(
                choices=[('operations', 'Operations'),
                 ('hr', 'Human Resources'),
                 ('finance', 'Finance'),
                 ('admin', 'Administration'),
                 ('management', 'Management')],
                default="operations",
                max_length=50,
            ),
        ),
    ]
