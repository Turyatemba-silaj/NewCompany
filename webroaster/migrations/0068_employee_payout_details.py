from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webroaster', '0067_employee_is_reliever'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='payout_method',
            field=models.CharField(choices=[('bank_transfer', 'Bank Transfer'), ('mobile_money', 'Mobile Money')], default='mobile_money', max_length=30),
        ),
        migrations.AddField(
            model_name='employee',
            name='bank_name',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='employee',
            name='bank_account_name',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='employee',
            name='bank_account_number',
            field=models.CharField(blank=True, default='', max_length=80),
        ),
        migrations.AddField(
            model_name='employee',
            name='mobile_money_provider',
            field=models.CharField(blank=True, default='', max_length=80),
        ),
        migrations.AddField(
            model_name='employee',
            name='mobile_money_number',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
    ]

