from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html_join
from zoneinfo import ZoneInfo

try:
    from unfold.admin import ModelAdmin, TabularInline
except ModuleNotFoundError:
    ModelAdmin = admin.ModelAdmin
    TabularInline = admin.TabularInline

from .access import (
    MODEL_PERMISSION_NAMES,
    ROLE_GROUPS,
    change_group_permissions,
    change_user_access,
    employee_for_user,
    user_allowed_models,
    user_allowed_views,
)
from .models import (
    # Operations Department
    AccessChangeLog, AuditLog, Notification, WorkflowAction, ClientUserAccess, Client, Contract, ContractDeliverable, Region, Site, SitePost, SiteRiskAssessment, Shift, Asset, AssetAssignment, Incident, IncidentNotification, Patrol_Log, PatrolRoute, PatrolCheckpoint, PatrolSession, PatrolCheckpointVisit, Deployment, DeploymentArea, Roster, RosterAssignment, SupervisorVisit, GuardPresenceVerification,
    # Human Resources Department
    Role, Position, Employee, Guard, Supervisor, Training, Attendance, Leave, 
    Disciplinary_Action, DisciplinaryNotification, Performance_Evaluation, Document, EmployeeComplianceRecord, ExitClearance, LeaveNotification,
    # Finance Department
    Salary, PayrollDeduction, PayrollPeriod, PayrollRun, Advance, AdvanceRecovery, Invoice, InvoiceBillableItem, InvoiceBillableItemPrice, Paymee, Payment, Supplier, ProcurementRequisition, ProcurementApproval, SupplierProformaInvoice, SupplierProformaItemPrice, SupplierProformaInvoiceItem, PurchaseOrder, GoodsReceivedNote, SupplierInvoice, SupplierPayment, ProcurementNotification, Budget, Expense, ExpenseNotification, BudgetNotification,
    WebsiteAdvertisement, CompanyEvent, WebsiteResource, AssociatedLink, JobPosting, JobApplication, JobApplicationNotification
)


# ==================== GOVERNANCE AND AUDIT ====================

ROLE_GROUP_BY_EMPLOYEE_ROLE = {
    "supervisor": "Supervisor",
    "manager": "Operations Manager",
    "operations_officer": "Operations Manager",
    "hr_officer": "Human Resources",
    "finance_officer": "Finance Officer",
    "administrator": "Head of Finance",
}


def permission_module_label(permission):
    model_name = permission.content_type.model
    for role_name, label in (
        ("Finance Officer", "Finance"),
        ("Human Resources", "Human Resources"),
        ("Operations Manager", "Operations"),
        ("Supervisor", "Operations"),
    ):
        model_names = {
            MODEL_PERMISSION_NAMES[slug]
            for slug in ROLE_GROUPS[role_name]["models"]
            if slug in MODEL_PERMISSION_NAMES
        }
        if model_name in model_names:
            return label
    return permission.content_type.app_label.title()


@admin.register(AccessChangeLog)
class AccessChangeLogAdmin(admin.ModelAdmin):
    list_display = ("action", "actor", "affected_user", "affected_group", "created_at_eat")
    list_filter = ("action", "created_at")
    search_fields = ("actor__username", "affected_user__username", "affected_group__name", "action")
    readonly_fields = (
        "actor",
        "affected_user",
        "affected_group",
        "action",
        "previous_values",
        "new_values",
        "created_at_eat",
    )
    ordering = ("-created_at", "-id")

    @admin.display(description="Timestamp (EAT)", ordering="created_at")
    def created_at_eat(self, obj):
        return timezone.localtime(obj.created_at, ZoneInfo("Africa/Kampala"))

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.has_perm("webroaster.view_accesschangelog")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class AccessManagedUserAdmin(DjangoUserAdmin):
    list_display = (
        "username",
        "email",
        "linked_employee",
        "group_names",
        "is_active",
        "last_login",
    )
    list_filter = ("is_active", "groups")
    search_fields = ("username", "email", "first_name", "last_name", "groups__name")
    ordering = ("username",)
    filter_horizontal = ("groups",)
    readonly_fields = ("password", "last_login", "date_joined")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("Access", {"fields": ("is_active", "groups")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    change_list_template = "admin/auth/user/access_change_list.html"

    @admin.display(description="Linked employee")
    def linked_employee(self, user):
        employee = employee_for_user(user)
        return str(employee) if employee else "No linked employee"

    @admin.display(description="Groups")
    def group_names(self, user):
        return ", ".join(user.groups.values_list("name", flat=True)) or "No role group"

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term:
            employees = Employee.objects.filter(employee_number__iexact=search_term)
            employee_numbers = employees.values_list("employee_number", flat=True)
            employee_emails = employees.exclude(email="").values_list("email", flat=True)
            queryset |= self.model.objects.filter(
                Q(username__in=employee_numbers) | Q(email__in=employee_emails)
            )
        return queryset, use_distinct

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if change:
            change_user_access(
                request.user,
                obj,
                groups=form.cleaned_data["groups"],
                is_active=form.cleaned_data["is_active"],
                action="update_user_access",
            )
        super().save_model(request, obj, form, change)

    def get_urls(self):
        return [
            path(
                "access-report/",
                self.admin_site.admin_view(self.access_report_view),
                name="auth_user_access_report",
            ),
        ] + super().get_urls()

    def access_report_view(self, request):
        if not (
            request.user.is_superuser
            or (
                request.user.has_perm("auth.view_user")
                and request.user.has_perm("auth.view_group")
            )
        ):
            raise PermissionDenied("You are not authorized to view the access report.")

        User = get_user_model()
        users = User.objects.filter(is_staff=True).prefetch_related(
            "groups",
            "user_permissions__content_type",
        ).order_by("username")
        access_rows = []
        missing_employee_links = []
        conflicting_assignments = []
        unassigned_role_users = []
        for user in users:
            employee = employee_for_user(user)
            groups = sorted(user.groups.values_list("name", flat=True))
            recognized_groups = sorted(set(groups).intersection(ROLE_GROUPS))
            direct_permissions = sorted(
                f"{permission.content_type.app_label}.{permission.codename}"
                for permission in user.user_permissions.all()
            )
            allowed_models = user_allowed_models(user)
            allowed_views = user_allowed_views(user)
            access_rows.append(
                {
                    "user": user,
                    "employee": employee,
                    "groups": groups,
                    "allowed_models": (
                        ["All modules (superuser)"]
                        if allowed_models is None
                        else sorted(allowed_models)
                    ),
                    "allowed_views": (
                        ["All views (superuser)"]
                        if allowed_views is None
                        else sorted(allowed_views)
                    ),
                    "direct_permissions": direct_permissions,
                }
            )
            if user.is_active and not employee:
                missing_employee_links.append(user)
            if not user.is_superuser and not recognized_groups:
                unassigned_role_users.append(user)
            expected_group = ROLE_GROUP_BY_EMPLOYEE_ROLE.get(
                getattr(employee, "role", "")
            )
            if len(recognized_groups) > 1 or (
                expected_group and expected_group not in recognized_groups
            ):
                conflicting_assignments.append(
                    {
                        "user": user,
                        "employee": employee,
                        "groups": groups,
                        "expected_group": expected_group,
                    }
                )

        vacant_roles = []
        for role_name in ROLE_GROUPS:
            role_group = Group.objects.filter(name=role_name).first()
            if not role_group or not role_group.user_set.filter(is_active=True).exists():
                vacant_roles.append(role_name)

        context = {
            **self.admin_site.each_context(request),
            "title": "User access report",
            "access_rows": access_rows,
            "missing_employee_links": missing_employee_links,
            "unassigned_role_users": unassigned_role_users,
            "vacant_roles": vacant_roles,
            "conflicting_assignments": conflicting_assignments,
        }
        return TemplateResponse(request, "admin/webroaster/access_report.html", context)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["access_report_url"] = reverse("admin:auth_user_access_report")
        return super().changelist_view(request, extra_context=extra_context)


admin.site.unregister(Group)


@admin.register(Group)
class AccessManagedGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "member_list", "active_member_count", "permissions_by_module")
    search_fields = ("name", "permissions__name", "permissions__codename")
    filter_horizontal = ("permissions",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            active_member_total=Count(
                "user",
                filter=Q(user__is_active=True),
                distinct=True,
            )
        )

    @admin.display(description="Members")
    def member_list(self, group):
        names = group.user_set.order_by("username").values_list("username", flat=True)
        return ", ".join(names) or "No members"

    @admin.display(description="Active members", ordering="active_member_total")
    def active_member_count(self, group):
        return group.active_member_total

    @admin.display(description="Permissions by module")
    def permissions_by_module(self, group):
        grouped = {}
        for permission in group.permissions.select_related("content_type").order_by(
            "content_type__app_label",
            "content_type__model",
            "codename",
        ):
            module = permission_module_label(permission)
            grouped.setdefault(module, []).append(permission.name)
        return format_html_join(
            "<br>",
            "<strong>{}</strong>: {}",
            (
                (module, ", ".join(names))
                for module, names in grouped.items()
            ),
        ) or "No permissions"

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        formfield = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == "permissions" and formfield:
            grouped = {}
            for permission in formfield.queryset.select_related("content_type").order_by(
                "content_type__app_label",
                "content_type__model",
                "codename",
            ):
                module = permission_module_label(permission)
                grouped.setdefault(module, []).append(
                    (str(permission.pk), str(permission))
                )
            formfield.choices = [
                (module, choices) for module, choices in grouped.items()
            ]
        return formfield

    def save_related(self, request, form, formsets, change):
        change_group_permissions(
            request.user,
            form.instance,
            form.cleaned_data["permissions"],
            adding=not change,
        )
        super().save_related(request, form, formsets, change)


admin.site.unregister(get_user_model())
admin.site.register(get_user_model(), AccessManagedUserAdmin)

@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    list_display = ('audit_id', 'created_at', 'username', 'action', 'method', 'status_code', 'path', 'ip_address')
    list_filter = ('action', 'method', 'status_code', 'created_at')
    search_fields = ('username', 'path', 'ip_address', 'user_agent')
    readonly_fields = ('user', 'username', 'action', 'path', 'method', 'status_code', 'ip_address', 'user_agent', 'created_at')
    ordering = ('-created_at', '-audit_id')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

# ==================== OPERATIONS DEPARTMENT ====================

class SiteInline(TabularInline):
    model = Site
    extra = 1


class ContractInline(TabularInline):
    model = Contract
    extra = 1


@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ('client_id', 'client_name', 'contact_person', 'phone_number')
    list_filter = ('created_at',)
    search_fields = ('client_name', 'contact_person', 'email')
    inlines = [SiteInline, ContractInline]


class ContractDeliverableInline(TabularInline):
    model = ContractDeliverable
    extra = 1
    readonly_fields = ('amount',)

@admin.register(Contract)
class ContractAdmin(ModelAdmin):
    list_display = ('contract_id', 'contract_number', 'client', 'day_shift_guards', 'night_shift_guards', 'number_of_guards', 'remaining_guards', 'rate_per_guard', 'contract_value', 'contract_display_status')
    list_filter = ('contract_status', 'contract_start_date', 'contract_end_date', 'client')
    search_fields = ('contract_number', 'client__client_name', 'client__contact_person', 'client__email')
    readonly_fields = ('contract_number', 'number_of_guards', 'site_required_guards', 'assigned_guards_count', 'remaining_guards', 'contract_value')
    inlines = [ContractDeliverableInline]



@admin.register(ContractDeliverable)
class ContractDeliverableAdmin(ModelAdmin):
    list_display = ('deliverable_id', 'contract', 'item_name', 'quantity', 'unit_price', 'amount')
    list_filter = ('contract', 'created_at')
    search_fields = ('item_name', 'contract__client__client_name')
    readonly_fields = ('amount',)


@admin.register(Region)
class RegionAdmin(ModelAdmin):
    list_display = ('region_id', 'region_name', 'description')
    search_fields = ('region_name', 'description')
@admin.register(Site)
class SiteAdmin(ModelAdmin):
    list_display = ('site_id', 'site_code', 'region', 'site_name', 'site_address', 'day_shift_guards', 'night_shift_guards', 'number_of_guards', 'assigned_guards')
    list_filter = ('region', 'client', 'contract', 'created_at')
    search_fields = ('site_code', 'site_name', 'site_address', 'region__region_name', 'guards__first_name', 'guards__last_name', 'guards__employee_number')
    readonly_fields = ('site_code',)
    filter_horizontal = ('guards',)


class DeploymentInline(TabularInline):
    model = Deployment
    extra = 1


@admin.register(Shift)
class ShiftAdmin(ModelAdmin):
    list_display = ('shift_id', 'shift_type', 'start_time', 'end_time', 'hours_per_shift')
    list_filter = ('shift_type',)
    inlines = [DeploymentInline]


@admin.register(Asset)
class AssetAdmin(ModelAdmin):
    list_display = ('asset_id', 'asset_type', 'asset_name', 'make', 'model', 'asset_number', 'police_number', 'color', 'size', 'condition', 'quantity')
    list_filter = ('asset_type', 'condition', 'created_at')
    search_fields = ('asset_name', 'make', 'model', 'asset_number', 'police_number', 'color', 'size')


@admin.register(AssetAssignment)
class AssetAssignmentAdmin(ModelAdmin):
    list_display = ('assignment_id', 'asset', 'quantity', 'assigned_to', 'issued_by', 'received_by', 'assigned_date', 'status', 'accountability_status')
    list_filter = ('status', 'accountability_status', 'condition_issued', 'condition_returned', 'asset__asset_type', 'site', 'assigned_date')
    search_fields = ('asset__asset_name', 'asset__asset_number', 'guard__first_name', 'guard__last_name', 'driver__first_name', 'driver__last_name', 'issued_by__first_name', 'issued_by__last_name', 'received_by__first_name', 'received_by__last_name', 'site__site_name')


@admin.register(Incident)
class IncidentAdmin(ModelAdmin):
    list_display = ('incident_id', 'incident_type', 'site', 'severity_level', 'status', 'date_time', 'reported_by')
    list_filter = ('incident_type', 'severity_level', 'status', 'date_time', 'site')
    search_fields = ('site__site_name', 'reported_by', 'reported_to', 'description', 'occurrence_summary', 'conclusion')

@admin.register(IncidentNotification)
class IncidentNotificationAdmin(ModelAdmin):
    list_display = ('notification_id', 'incident', 'recipient', 'authority_group', 'status', 'notified_at')
    list_filter = ('authority_group', 'status', 'notified_at')
    search_fields = ('incident__site__site_name', 'recipient__first_name', 'recipient__last_name', 'recipient__email')

@admin.register(Patrol_Log)
class Patrol_LogAdmin(ModelAdmin):
    list_display = ('patrol_id', 'site', 'patrol_date', 'patrol_route', 'duration')
    list_filter = ('patrol_date', 'site')
    search_fields = ('patrol_route', 'site__site_name')


@admin.register(Deployment)
class DeploymentAdmin(ModelAdmin):
    list_display = ('deployment_id', 'client', 'site', 'shift_summary', 'day_guards_summary', 'night_guards_summary', 'start_date', 'end_date', 'status')
    list_filter = ('status', 'shift_coverage', 'client', 'start_date', 'site')
    search_fields = ('client__client_name', 'site__site_name', 'day_guards__first_name', 'day_guards__last_name', 'night_guards__first_name', 'night_guards__last_name')
    filter_horizontal = ('day_guards', 'night_guards')

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.sync_operational_plan()



@admin.register(DeploymentArea)
class DeploymentAreaAdmin(ModelAdmin):
    list_display = ('deployment_area_id', 'employee', 'region', 'start_date', 'end_date', 'status', 'transferred_by_hr_manager')
    list_filter = ('status', 'region', 'start_date')
    search_fields = ('employee__first_name', 'employee__last_name', 'region__region_name', 'transferred_by_hr_manager__first_name', 'transferred_by_hr_manager__last_name')
# ==================== HUMAN RESOURCES DEPARTMENT ====================

@admin.register(Role)
class RoleAdmin(ModelAdmin):
    list_display = ('role_id', 'role_name', 'department')
    list_filter = ('department',)
    search_fields = ('role_name',)


@admin.register(Position)
class PositionAdmin(ModelAdmin):
    list_display = ('position_id', 'position_title', 'department', 'grade_level')
    list_filter = ('department', 'grade_level')
    search_fields = ('position_title',)


class GuardInline(TabularInline):
    model = Guard
    extra = 0


class SupervisorInline(TabularInline):
    model = Supervisor
    extra = 0


@admin.register(Employee)
class EmployeeAdmin(ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if not request.user.is_superuser:
            return (*fields, "advance_supervisor", "is_department_head")
        return fields

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "advance_supervisor":
            kwargs["queryset"] = Employee.objects.filter(status="active").order_by("employee_number")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    list_display = ('employee_id', 'employee_number', 'first_name', 'last_name', 'role', 'position', 'department', 'daily_rate', 'email', 'nssf_number', 'status', 'hire_date')
    list_filter = ('status', 'role', 'position', 'department', 'hire_date', 'gender')
    search_fields = ('employee_number', 'first_name', 'last_name', 'email', 'national_id', 'nssf_number')
    readonly_fields = ('employee_number', 'salary_scale', 'daily_rate', 'created_at', 'updated_at')
    ordering = ('employee_id',)

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term:
            queryset |= self.model.objects.filter(employee_number__iexact=search_term)
        return queryset, use_distinct

@admin.register(Guard)
class GuardAdmin(ModelAdmin):
    list_display = ('employee', 'qualification', 'armed_status')
    list_filter = ('qualification', 'armed_status')
    search_fields = ('employee__first_name', 'employee__last_name')


@admin.register(Supervisor)
class SupervisorAdmin(ModelAdmin):
    list_display = ('supervisor_id', 'employee', 'authority_level')
    list_filter = ('authority_level',)
    search_fields = ('employee__first_name', 'employee__last_name')


@admin.register(Training)
class TrainingAdmin(ModelAdmin):
    list_display = ('training_id', 'training_type', 'trainee', 'training_name', 'provider', 'start_date', 'end_date')
    list_filter = ('training_type', 'start_date', 'end_date')
    search_fields = ('employee__first_name', 'employee__last_name', 'recruit', 'training_name', 'provider')
    exclude = ('certificate_no',)


@admin.register(Attendance)
class AttendanceAdmin(ModelAdmin):
    list_display = ('attendance_id', 'site', 'shift', 'scheduled_guard', 'present', 'attended_guard', 'recorded_by', 'date')
    list_filter = ('date', 'site', 'shift', 'present')
    search_fields = ('employee__first_name', 'employee__last_name', 'scheduled_guard__first_name', 'scheduled_guard__last_name', 'attended_guard__first_name', 'attended_guard__last_name')

    def save_model(self, request, obj, form, change):
        obj.recorded_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Leave)
class LeaveAdmin(ModelAdmin):
    list_display = ('leave_id', 'employee', 'leave_type', 'start_date', 'end_date', 'application_status', 'operations_verification_status', 'approval_status', 'supervisor', 'hod')
    list_filter = ('leave_type', 'application_status', 'operations_verification_status', 'approval_status', 'start_date')
    search_fields = ('employee__first_name', 'employee__last_name', 'address_while_away', 'emergency_contact')


@admin.register(LeaveNotification)
class LeaveNotificationAdmin(ModelAdmin):
    list_display = ('notification_id', 'leave', 'recipient', 'recipient_group', 'notification_type', 'status', 'decision', 'notified_at')
    list_filter = ('recipient_group', 'notification_type', 'status', 'decision', 'notified_at')
    search_fields = ('leave__employee__first_name', 'leave__employee__last_name', 'recipient__first_name', 'recipient__last_name', 'message')


@admin.register(Disciplinary_Action)
class Disciplinary_ActionAdmin(ModelAdmin):
    list_display = ('action_id', 'employee', 'offence_committed', 'offence_date', 'status', 'outcome', 'approval_status')
    list_filter = ('status', 'outcome', 'approval_status', 'offence_date')
    search_fields = ('employee__first_name', 'employee__last_name', 'offence_committed', 'description', 'steps_taken', 'conclusion')



@admin.register(DisciplinaryNotification)
class DisciplinaryNotificationAdmin(ModelAdmin):
    list_display = ('notification_id', 'disciplinary_action', 'recipient', 'status', 'notified_at')
    list_filter = ('status', 'notified_at')
    search_fields = ('disciplinary_action__offence_committed', 'recipient__first_name', 'recipient__last_name', 'recipient__email', 'message')

@admin.register(Performance_Evaluation)
class Performance_EvaluationAdmin(ModelAdmin):
    list_display = ('eval_id', 'employee', 'review_period_start', 'review_period_end', 'overall_score', 'rating', 'status', 'evaluated_by')
    list_filter = ('rating', 'status', 'review_period_start', 'review_period_end')
    search_fields = ('employee__first_name', 'employee__last_name', 'strengths', 'areas_for_improvement', 'goals')


@admin.register(Document)
class DocumentAdmin(ModelAdmin):
    list_display = ('doc_id', 'employee', 'doc_type', 'expiry_date')
    list_filter = ('doc_type', 'expiry_date')
    search_fields = ('employee__first_name', 'employee__last_name')


# ==================== FINANCE DEPARTMENT ====================

@admin.register(Salary)
class SalaryAdmin(ModelAdmin):
    list_display = ('salary_id', 'employee', 'shifts_worked', 'daily_rate', 'basic_salary', 'loan_deduction', 'medical_deduction', 'total_deductions', 'total_salary', 'pay_period')
    list_filter = ('pay_period',)
    search_fields = ('employee__first_name', 'employee__last_name')
    readonly_fields = ('shifts_worked', 'daily_rate', 'basic_salary', 'overtime_pay', 'gross_pay', 'loan_deduction', 'medical_deduction', 'other_payroll_deductions', 'ledger_installment_amount', 'total_deductions', 'total_salary', 'created_at', 'updated_at')


@admin.register(PayrollDeduction)
class PayrollDeductionAdmin(ModelAdmin):
    list_display = ('deduction_id', 'employee', 'category', 'amount', 'start_date', 'end_date', 'status')
    list_filter = ('category', 'status', 'start_date', 'end_date')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__employee_number', 'description')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Advance)
class AdvanceAdmin(ModelAdmin):
    readonly_fields = (
        "installment_amount", "approval_status", "approved_by", "decision_at",
        "verification_status", "verified_by", "verified_at", "status", "disbursement_date",
        "routing_path", "payment_authorized_by", "payment_authorized_at", "paid_by", "paid_at",
    )

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if not obj:
            return fields
        fields = (*fields, "employee")
        if obj.verification_status != "pending" or obj.status != "pending":
            fields = (*fields, "amount_requested")
        return fields

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            obj.notify_submission()

    list_display = ('advance_id', 'employee', 'amount_requested', 'installment_amount', 'balance', 'approval_status', 'status')
    list_filter = ('approval_status', 'status', 'created_at')
    search_fields = ('employee__first_name', 'employee__last_name', 'strengths', 'areas_for_improvement', 'goals')


@admin.register(AdvanceRecovery)
class AdvanceRecoveryAdmin(ModelAdmin):
    list_display = ('recovery_id', 'employee', 'advance', 'salary', 'amount', 'installment_amount', 'balance', 'period_start_date', 'period_end_date')
    list_filter = ('period_start_date', 'period_end_date', 'created_at')
    search_fields = ('employee__first_name', 'employee__last_name', 'strengths', 'areas_for_improvement', 'goals')
    readonly_fields = ('created_at',)


@admin.register(InvoiceBillableItemPrice)
class InvoiceBillableItemPriceAdmin(ModelAdmin):
    list_display = ('item_name', 'unit_price', 'taxable', 'active', 'updated_at')
    list_filter = ('active', 'taxable')
    search_fields = ('item_name',)

class PaymentInline(TabularInline):
    model = Payment
    extra = 1


class InvoiceBillableItemInline(TabularInline):
    model = InvoiceBillableItem
    extra = 3
    readonly_fields = ('amount',)

@admin.register(Invoice)
class InvoiceAdmin(ModelAdmin):
    list_display = ('invoice_number', 'contract', 'client', 'invoice_date', 'due_date', 'deployed_guards', 'contract_amount', 'tax_amount', 'total_amount', 'status')
    list_filter = ('status', 'invoice_date', 'client', 'contract')
    search_fields = ('invoice_number', 'client__client_name', 'contract__contract_number')
    readonly_fields = ('invoice_number', 'deployed_guards', 'rate_per_guard', 'contract_amount', 'tax_amount', 'total_amount')
    inlines = [InvoiceBillableItemInline, PaymentInline]


@admin.register(Paymee)
class PaymeeAdmin(ModelAdmin):
    readonly_fields = ('client', 'total_amount', 'amount_paid', 'balance_amount', 'overpaid_amount', 'due_date', 'last_payment_date', 'aging_days', 'status')
    list_display = ('invoice', 'client', 'total_amount', 'amount_paid', 'balance_amount', 'due_date', 'aging_days', 'status')
    list_filter = ('status', 'due_date', 'currency')
    search_fields = ('invoice__client__client_name', 'invoice__contract__contract_number')


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = ('payment_id', 'invoice', 'amount', 'payment_date', 'payment_method')
    list_filter = ('payment_method', 'payment_date')
    search_fields = ('invoice__client__client_name', 'transaction_ref')


@admin.register(Supplier)
class SupplierAdmin(ModelAdmin):
    list_display = ('supplier_code', 'supplier_name', 'contact_person', 'phone_number', 'email', 'status')
    list_filter = ('status', 'created_at')
    search_fields = ('supplier_code', 'supplier_name', 'contact_person', 'phone_number', 'email', 'tax_identification_number')
    readonly_fields = ('supplier_code', 'created_at', 'updated_at')


@admin.register(ProcurementRequisition)
class ProcurementRequisitionAdmin(ModelAdmin):
    list_display = ('requisition_number', 'title', 'department', 'budget', 'required_date', 'estimated_amount', 'requested_by', 'status')
    list_filter = ('department', 'category', 'status', 'required_date')
    search_fields = ('requisition_number', 'title', 'description', 'requested_by__first_name', 'requested_by__last_name')
    readonly_fields = ('requisition_number', 'approved_amount', 'created_at', 'updated_at')


@admin.register(ProcurementApproval)
class ProcurementApprovalAdmin(ModelAdmin):
    list_display = ('approval_id', 'requisition', 'approved_by', 'decision', 'approved_amount', 'decided_at')
    list_filter = ('decision', 'decided_at')
    search_fields = ('requisition__requisition_number', 'requisition__title', 'approved_by__first_name', 'approved_by__last_name')
    readonly_fields = ('decided_at', 'created_at', 'updated_at')


@admin.register(SupplierProformaItemPrice)
class SupplierProformaItemPriceAdmin(ModelAdmin):
    list_display = ('item_name', 'unit_price', 'tax_rate', 'discount_allowed', 'max_discount_rate', 'active', 'updated_at')
    list_filter = ('active', 'discount_allowed')
    search_fields = ('item_name',)


class SupplierProformaInvoiceItemInline(TabularInline):
    model = SupplierProformaInvoiceItem
    extra = 3
    readonly_fields = ('description', 'unit_price', 'tax_rate', 'line_total', 'tax_amount', 'total_amount')


@admin.register(SupplierProformaInvoice)
class SupplierProformaInvoiceAdmin(ModelAdmin):
    list_display = ('proforma_number', 'supplier_reference', 'requisition', 'supplier', 'proforma_date', 'total_amount', 'status', 'purchase_order')
    list_filter = ('status', 'proforma_date', 'supplier')
    search_fields = ('proforma_number', 'supplier_reference', 'supplier__supplier_name', 'requisition__requisition_number')
    readonly_fields = ('proforma_number', 'subtotal_amount', 'tax_amount', 'total_amount', 'purchase_order', 'created_at', 'updated_at')
    inlines = [SupplierProformaInvoiceItemInline]


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(ModelAdmin):
    list_display = ('po_number', 'requisition', 'supplier', 'order_date', 'expected_delivery_date', 'total_amount', 'status')
    list_filter = ('status', 'order_date', 'expected_delivery_date', 'supplier')
    search_fields = ('po_number', 'requisition__requisition_number', 'supplier__supplier_name')
    readonly_fields = ('po_number', 'total_amount', 'created_at', 'updated_at')


@admin.register(GoodsReceivedNote)
class GoodsReceivedNoteAdmin(ModelAdmin):
    list_display = ('grn_number', 'purchase_order', 'received_date', 'received_by', 'quantity_summary', 'status')
    list_filter = ('status', 'received_date')
    search_fields = ('grn_number', 'purchase_order__po_number', 'delivery_note_number', 'quantity_summary')
    readonly_fields = ('grn_number', 'created_at', 'updated_at')


@admin.register(SupplierInvoice)
class SupplierInvoiceAdmin(ModelAdmin):
    list_display = ('invoice_number', 'supplier', 'purchase_order', 'due_date', 'total_amount', 'amount_paid', 'balance_amount', 'status')
    list_filter = ('status', 'invoice_date', 'due_date', 'supplier')
    search_fields = ('invoice_number', 'supplier__supplier_name', 'purchase_order__po_number')
    readonly_fields = ('total_amount', 'amount_paid', 'balance_amount', 'created_at', 'updated_at')


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(ModelAdmin):
    list_display = ('supplier_payment_id', 'supplier_invoice', 'payment_date', 'amount', 'payment_method', 'approval_status', 'payment_status', 'paid_by')
    list_filter = ('payment_method', 'approval_status', 'payment_status', 'payment_date')
    search_fields = ('supplier_invoice__invoice_number', 'supplier_invoice__supplier__supplier_name', 'transaction_ref')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Budget)
class BudgetAdmin(ModelAdmin):
    list_display = ('budget_code', 'budget_title', 'department', 'fiscal_year', 'requested_amount', 'allocated_amount', 'spent_amount', 'remaining_amount', 'approval_status')
    list_filter = ('department', 'budget_category', 'fiscal_year', 'approval_status')
    search_fields = ('budget_code', 'budget_title', 'department', 'requisition_reason')
    readonly_fields = ('budget_code', 'spent_amount', 'approved_at', 'created_at', 'updated_at')


@admin.register(Expense)
class ExpenseAdmin(ModelAdmin):
    list_display = ('expense_code', 'requisition_title', 'budget', 'requested_amount', 'amount', 'variance_amount', 'expense_date', 'approval_status', 'accountability_status')
    list_filter = ('category', 'verification_status', 'approval_status', 'accountability_status', 'status', 'expense_date')
    search_fields = ('expense_code', 'requisition_title', 'category', 'description', 'receipt_reference', 'requested_by__first_name', 'requested_by__last_name', 'spent_by__first_name', 'spent_by__last_name')
    readonly_fields = ('expense_code', 'accountability_status', 'approved_at', 'accounted_at', 'recorded_at', 'created_at', 'updated_at')












































@admin.register(ProcurementNotification)
class ProcurementNotificationAdmin(ModelAdmin):
    list_display = ('notification_id', 'recipient', 'recipient_group', 'notification_type', 'status', 'notified_at')
    list_filter = ('recipient_group', 'notification_type', 'status', 'notified_at')
    search_fields = ('recipient__first_name', 'recipient__last_name', 'message', 'related_model')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BudgetNotification)
class BudgetNotificationAdmin(ModelAdmin):
    list_display = ('notification_id', 'budget', 'recipient', 'recipient_group', 'notification_type', 'status', 'notified_at')
    list_filter = ('recipient_group', 'notification_type', 'status', 'notified_at')
    search_fields = ('budget__budget_code', 'budget__budget_title', 'recipient__first_name', 'recipient__last_name', 'message')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(ExpenseNotification)
class ExpenseNotificationAdmin(ModelAdmin):
    list_display = ('notification_id', 'expense', 'recipient', 'recipient_group', 'notification_type', 'status', 'notified_at')
    list_filter = ('recipient_group', 'notification_type', 'status', 'notified_at')
    search_fields = ('expense__expense_code', 'expense__requisition_title', 'recipient__first_name', 'recipient__last_name', 'message')
    readonly_fields = ('created_at', 'updated_at')


# ==================== PUBLIC WEBSITE ====================

@admin.register(WebsiteAdvertisement)
class WebsiteAdvertisementAdmin(ModelAdmin):
    list_display = ('title', 'placement', 'starts_on', 'ends_on', 'is_active')
    list_filter = ('placement', 'is_active', 'starts_on')
    search_fields = ('title', 'message')


@admin.register(CompanyEvent)
class CompanyEventAdmin(ModelAdmin):
    list_display = ('title', 'event_date', 'location', 'is_public')
    list_filter = ('is_public', 'event_date')
    search_fields = ('title', 'location', 'summary')


@admin.register(WebsiteResource)
class WebsiteResourceAdmin(ModelAdmin):
    list_display = ('title', 'resource_type', 'is_public')
    list_filter = ('resource_type', 'is_public')
    search_fields = ('title', 'summary')


@admin.register(AssociatedLink)
class AssociatedLinkAdmin(ModelAdmin):
    list_display = ('title', 'category', 'url', 'is_public')
    list_filter = ('category', 'is_public')
    search_fields = ('title', 'description', 'url')


@admin.register(JobPosting)
class JobPostingAdmin(ModelAdmin):
    list_display = ('title', 'department', 'location', 'employment_type', 'deadline', 'is_online', 'is_active')
    list_filter = ('department', 'employment_type', 'is_online', 'is_active')
    search_fields = ('title', 'summary', 'requirements')


@admin.register(JobApplication)
class JobApplicationAdmin(ModelAdmin):
    list_display = ('applicant_name', 'job', 'application_mode', 'phone_number', 'status', 'submitted_at')
    list_filter = ('application_mode', 'status', 'job')
    search_fields = ('applicant_name', 'phone_number', 'email', 'job__title')


@admin.register(JobApplicationNotification)
class JobApplicationNotificationAdmin(ModelAdmin):
    list_display = ('notification_id', 'application', 'recipient', 'recipient_group', 'status', 'notified_at')
    list_filter = ('recipient_group', 'notification_type', 'status', 'notified_at')
    search_fields = ('application__applicant_name', 'application__job__title', 'recipient__first_name', 'recipient__last_name', 'recipient__email', 'message')
    readonly_fields = ('created_at', 'updated_at')


class PhaseModelAdmin(ModelAdmin):
    list_per_page = 50


for model in (
    WorkflowAction,
    Notification,
    ClientUserAccess,
    SitePost,
    SiteRiskAssessment,
    PatrolRoute,
    PatrolCheckpoint,
    PatrolSession,
    PatrolCheckpointVisit,
    Roster,
    RosterAssignment,
    SupervisorVisit,
    GuardPresenceVerification,
    EmployeeComplianceRecord,
    ExitClearance,
    PayrollPeriod,
    PayrollRun,
):
    try:
        admin.site.register(model, PhaseModelAdmin)
    except admin.sites.AlreadyRegistered:
        pass






