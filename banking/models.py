from django.db import models
from django.conf import settings

class Account(models.Model):
    name = models.CharField(max_length=120)
    number = models.CharField(max_length=80, unique=True)
    currency = models.CharField(max_length=3, default='UGX')
    def __str__(self): return f'{self.name} ({self.number[-4:]})'

class Statement(models.Model):
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    digest = models.CharField(max_length=64)
    filename = models.CharField(max_length=255)
    state = models.CharField(max_length=20, default='imported')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['account','digest'], name='bank_statement_unique')]

class Entry(models.Model):
    statement = models.ForeignKey(Statement, on_delete=models.PROTECT, related_name='entries')
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    date = models.DateField()
    reference = models.CharField(max_length=100)
    description = models.CharField(max_length=500, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    kind = models.CharField(max_length=30, blank=True)
    target = models.CharField(max_length=80, null=True, blank=True, unique=True)
    note = models.TextField(blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['account','reference'], name='bank_entry_reference_unique')]

class Audit(models.Model):
    statement = models.ForeignKey(Statement, on_delete=models.PROTECT, related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    actor_name = models.CharField(max_length=150)
    action = models.CharField(max_length=40)
    detail = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
