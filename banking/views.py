import csv, io, hashlib
from datetime import date
from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, IntegrityError
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from .models import Account, Statement, Entry, Audit
from webroaster import models as erp

ROLES = {'Cashier','Finance Officer','Finance Manager','Head of Finance','Administrator'}
def allowed(user, *roles):
    return user.is_active and user.is_authenticated and bool(set(user.groups.values_list('name', flat=True)) & set(roles))
def check(user, *roles):
    if not allowed(user, *roles): raise PermissionDenied

def audit(s,u,action,detail=''):
    Audit.objects.create(statement=s,actor=u,actor_name=u.get_username(),action=action,detail=detail)

def candidates(e):
    if e.account.currency != 'UGX': return []
    a=abs(e.amount); r=e.reference
    if e.amount>0:
        specs=[('client_payment',erp.Payment.objects.filter(transaction_ref=r,amount=a,payment_date=e.date,payment_method='bank_transfer'))]
    else:
        specs=[('advance',erp.Advance.objects.filter(payment_reference=r,amount_requested=a,disbursement_date=e.date,status__in=['disbursed','recovered'])),('supplier',erp.SupplierPayment.objects.filter(transaction_ref=r,amount=a,payment_date=e.date,payment_status='paid',payment_method='bank_transfer')),('expense',erp.Expense.objects.filter(receipt_reference=r,amount=a,expense_date=e.date,status='approved',payment_method='bank_transfer'))]
    return [(k,f'{k}:{pk}') for k,q in specs for pk in q.values_list('pk',flat=True)[:2]]

@login_required
def index(request):
    if not request.user.is_superuser: check(request.user,*ROLES)
    return render(request,'banking/index.html',{'accounts':Account.objects.all(),'statements':Statement.objects.select_related('account').order_by('-pk')[:100], 'upload':allowed(request.user,'Cashier'), 'manage':allowed(request.user,'Head of Finance')})

@login_required
@require_POST
def account(request):
    check(request.user,'Head of Finance')
    name=request.POST.get('name','').strip(); number=request.POST.get('number','').strip()
    if not name or not number or len(name)>120 or len(number)>80: raise ValidationError('Invalid account')
    Account.objects.get_or_create(number=number,defaults={'name':name})
    return redirect('banking:index')

@login_required
@require_POST
def upload(request):
    check(request.user,'Cashier')
    acc=get_object_or_404(Account,pk=request.POST.get('account'))
    f=request.FILES.get('file')
    try:
        if not f or f.size>5*1024*1024 or not f.name.lower().endswith('.csv'): raise ValueError('Upload CSV up to 5 MB.')
        raw=f.read(); reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if not {'date','reference','description','amount'}.issubset(reader.fieldnames or []): raise ValueError('Required columns: date,reference,description,amount')
        with transaction.atomic():
            s=Statement.objects.create(account=acc,digest=hashlib.sha256(raw).hexdigest(),filename=f.name,uploaded_by=request.user)
            count=0
            for row in reader:
                count+=1
                if count>10000: raise ValueError('Maximum 10,000 rows')
                r=row['reference'].strip(); d=row['description']; a=Decimal(row['amount'])
                if not r or len(r)>100 or len(d)>500 or not a.is_finite() or not a or abs(a)>=10**12 or a!=a.quantize(Decimal('.01')): raise ValueError(f'Invalid row {count}')
                Entry.objects.create(statement=s,account=acc,date=date.fromisoformat(row['date']),reference=r,description=d,amount=a)
            if not count: raise ValueError('Empty statement')
            audit(s,request.user,'import',str(count))
        return redirect('banking:detail',pk=s.pk)
    except (ValueError, InvalidOperation, IntegrityError, UnicodeError, TypeError, AttributeError) as exc:
        messages.error(request,'Import rejected: duplicate reference/file or invalid CSV. No rows imported.')
        return redirect('banking:index')

@login_required
def detail(request,pk):
    if not request.user.is_superuser: check(request.user,*ROLES)
    s=get_object_or_404(Statement,pk=pk)
    return render(request,'banking/detail.html',{'s':s,'entries':s.entries.order_by('date','pk'),'events':s.events.order_by('created'),'review':allowed(request.user,'Finance Officer'),'verify':allowed(request.user,'Finance Manager'),'approve':allowed(request.user,'Head of Finance')})

@login_required
@require_POST
@transaction.atomic
def action(request,pk):
    s=get_object_or_404(Statement.objects.select_for_update(),pk=pk)
    op=request.POST.get('action'); u=request.user
    if op in ('auto','classify','review'):
        check(u,'Finance Officer')
        if s.state!='imported' or s.uploaded_by_id==u.pk: raise PermissionDenied
        if op=='auto':
            for e in s.entries.filter(kind='').select_for_update():
                matches=candidates(e)
                if len(matches)==1 and not Entry.objects.filter(target=matches[0][1]).exists():
                    try:
                        with transaction.atomic():
                            e.kind,e.target=matches[0]; e.save(update_fields=['kind','target']); audit(s,u,'match',f'{e.pk}: {e.target}')
                    except IntegrityError: continue
        elif op=='classify':
            e=get_object_or_404(s.entries.select_for_update(),pk=request.POST.get('entry')); k=request.POST.get('kind'); note=request.POST.get('note','').strip()
            if e.kind or k not in ('bank_charge','statutory','payroll','other') or not note or len(note)>2000: raise PermissionDenied
            if k!='other' and e.amount>0: raise PermissionDenied
            e.kind=k; e.note=note; e.save(update_fields=['kind','note']); audit(s,u,'classify',f'{e.pk}: {k}: {note}')
        else:
            if s.entries.filter(kind='').exists(): messages.error(request,'Resolve all unmatched entries first.'); return redirect('banking:detail',pk=pk)
            s.state='reviewed'; s.save(update_fields=['state']); audit(s,u,'review')
    elif op in ('verify','approve'):
        check(u,'Finance Manager' if op=='verify' else 'Head of Finance')
        if s.state!=('reviewed' if op=='verify' else 'verified') or s.events.filter(actor=u,action__in=['import','review','verify']).exists(): raise PermissionDenied
        for e in s.entries.exclude(target=None):
            if candidates(e)!=[(e.kind,e.target)]: messages.error(request,'ERP match changed; do not approve. Contact administrator.'); return redirect('banking:detail',pk=pk)
        s.state='verified' if op=='verify' else 'closed'; s.save(update_fields=['state']); audit(s,u,op)
    else: raise PermissionDenied
    return redirect('banking:detail',pk=pk)
