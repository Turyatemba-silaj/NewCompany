import logging
from smtplib import SMTPException

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .access import (
    change_user_access,
    deactivate_for_termination,
    role_group_permission_queryset,
    sync_role_groups,
)
from .forms_accounts import AdminUserCreationForm, ForgotPasswordRequestForm, PasswordExpiredChangeForm
from .models import Employee, UserPasswordProfile
from .views import render_page

logger = logging.getLogger(__name__)


class AccountEmailDeliveryError(Exception):
    pass


def _employee_account_maps():
    employees = Employee.objects.only("employee_id", "employee_number", "first_name", "last_name", "email", "status")
    by_email = {}
    by_employee_number = {}
    for employee in employees:
        if employee.email:
            by_email[employee.email.strip().lower()] = employee
        if employee.employee_number:
            by_employee_number[employee.employee_number.strip().lower()] = employee
    return by_email, by_employee_number


def _matched_employee_for_user(user, by_email, by_employee_number):
    email_key = (user.email or "").strip().lower()
    username_key = (user.username or "").strip().lower()
    if email_key and email_key in by_email:
        return by_email[email_key]
    if username_key and username_key in by_employee_number:
        return by_employee_number[username_key]
    return None


def password_profile_for(user):
    profile, _created = UserPasswordProfile.objects.get_or_create(user=user)
    return profile


def password_status_for(user):
    profile = password_profile_for(user)
    if profile.force_password_change:
        return "Reset required"
    if profile.is_expired:
        return "Expired"
    if profile.days_until_expiry <= 14:
        return "Expiring soon"
    return "Current"

def _password_management_rows():
    User = get_user_model()
    by_email, by_employee_number = _employee_account_maps()
    rows = []
    users = User.objects.prefetch_related("groups__permissions", "user_permissions").order_by("username", "id")
    for user in users:
        employee = _matched_employee_for_user(user, by_email, by_employee_number)
        groups = ", ".join(group.name for group in user.groups.all()) or "No role group"
        permission_names = sorted({
            permission.name
            for group in user.groups.all()
            for permission in group.permissions.all()
        } | {permission.name for permission in user.user_permissions.all()})
        permissions = f"{len(permission_names)} permission{'s' if len(permission_names) != 1 else ''}" if permission_names else "No permission assigned"
        profile = password_profile_for(user)
        rows.append(
            {
                "user": user,
                "groups": groups,
                "permissions": permissions,
                "employee": employee,
                "employee_status": employee.get_status_display() if employee else "No linked employee",
                "is_terminated_staff": bool(employee and employee.status == "terminated"),
                "password_profile": profile,
                "password_status": password_status_for(user),
                "password_changed_at": profile.password_changed_at,
                "password_expires_at": profile.expires_at,
                "password_days_left": profile.days_until_expiry,
            }
        )
    return rows


def _deactivate_terminated_staff_accounts():
    User = get_user_model()
    by_email, by_employee_number = _employee_account_maps()
    users = User.objects.filter(is_active=True)
    changed = []
    for user in users:
        employee = _matched_employee_for_user(user, by_email, by_employee_number)
        if employee and employee.status == "terminated":
            if deactivate_for_termination(user):
                changed.append(user.username)
    return changed


def send_account_password_link(request, user, *, invitation=False):
    if not settings.EMAIL_HOST:
        logger.error(
            "Account email delivery is unavailable because EMAIL_HOST is unset (user_id=%s).",
            user.pk,
        )
        raise AccountEmailDeliveryError("Outbound email is not configured.")
    if "console.EmailBackend" in settings.EMAIL_BACKEND:
        logger.error(
            "Account email delivery cannot use the console backend (user_id=%s).",
            user.pk,
        )
        raise AccountEmailDeliveryError("A secure outbound email backend is required.")

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = request.build_absolute_uri(
        reverse(
            "webroaster:invitation_set_password",
            kwargs={"uidb64": uid, "token": token},
        )
    )
    message = render_to_string(
        "webroaster/account_invitation_email.txt",
        {
            "user": user,
            "link": link,
            "company_name": getattr(settings, "COMPANY_NAME", "NewCompany"),
            "invitation": invitation,
        },
    )
    subject = (
        f"{getattr(settings, 'COMPANY_NAME', 'NewCompany')} account invitation"
        if invitation
        else f"{getattr(settings, 'COMPANY_NAME', 'NewCompany')} password reset"
    )
    try:
        sent = send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except (OSError, SMTPException, ValueError) as exc:
        logger.exception("Account email delivery failed (user_id=%s).", user.pk)
        raise AccountEmailDeliveryError("Outbound email delivery failed.") from exc
    if sent != 1:
        logger.error("Account email was not accepted by the backend (user_id=%s).", user.pk)
        raise AccountEmailDeliveryError("Outbound email delivery failed.")
    return sent


def password_management(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Only system administrators can manage staff account access.")

    sync_role_groups()
    create_user_form = AdminUserCreationForm()

    if request.method == "POST" and request.POST.get("action") == "deactivate_terminated":
        changed = _deactivate_terminated_staff_accounts()
        if changed:
            messages.success(request, f"Deactivated {len(changed)} terminated staff account(s): {', '.join(changed[:8])}.")
        else:
            messages.info(request, "No active Django user accounts matched terminated staff records.")
        return redirect("webroaster:password_management")

    if request.method == "POST" and request.POST.get("action") == "create_user":
        create_user_form = AdminUserCreationForm(request.POST)
        if create_user_form.is_valid():
            new_user = create_user_form.save(request.user)
            try:
                send_account_password_link(request, new_user, invitation=True)
            except AccountEmailDeliveryError:
                messages.error(
                    request,
                    f"Account {new_user.username} was created, but its invitation could not be emailed. Check SMTP configuration and send a password reset link.",
                )
            else:
                messages.success(request, f"Invitation sent to {new_user.email} for {new_user.username}.")
            return redirect("webroaster:password_management")
        messages.error(request, "User account was not created. Review the highlighted fields.")

    role_permission_options = {}
    for group in create_user_form.fields["groups"].queryset:
        permissions = role_group_permission_queryset(group).select_related("content_type").order_by("content_type__model", "codename")
        role_permission_options[str(group.pk)] = [
            {"value": str(permission.pk), "label": create_user_form.permission_label(permission)}
            for permission in permissions
        ]

    rows = _password_management_rows()
    context = {
        "rows": rows,
        "create_user_form": create_user_form,
        "role_permission_options": role_permission_options,
        "total_users": len(rows),
        "active_users": sum(1 for row in rows if row["user"].is_active),
        "blocked_users": sum(1 for row in rows if not row["user"].is_active),
        "terminated_staff_accounts": sum(1 for row in rows if row["is_terminated_staff"]),
    }
    return render_page(request, "webroaster/password_management.html", context, "password-management")

def password_management_action(request, user_id):
    if not request.user.is_superuser:
        raise PermissionDenied("Only system administrators can manage staff account access.")
    if request.method != "POST":
        return redirect("webroaster:password_management")

    User = get_user_model()
    managed_user = get_object_or_404(User, pk=user_id)
    action = request.POST.get("action")
    by_email, by_employee_number = _employee_account_maps()
    employee = _matched_employee_for_user(managed_user, by_email, by_employee_number)

    if action == "activate":
        if employee and employee.status == "terminated":
            messages.error(request, f"{managed_user.username} is linked to a terminated employee record. Reactivate the employee first if this account should be restored.")
        else:
            change_user_access(
                request.user,
                managed_user,
                is_active=True,
                action="activate_user",
            )
            messages.success(request, f"Activated {managed_user.username}.")
    elif action == "block":
        if managed_user.pk == request.user.pk:
            messages.error(request, "You cannot block your own active administrator account.")
        else:
            change_user_access(
                request.user,
                managed_user,
                is_active=False,
                action="deactivate_user",
            )
            messages.success(request, f"Blocked {managed_user.username}.")
    elif action == "reset_password":
        if not managed_user.is_active or not managed_user.email:
            messages.error(request, f"A reset link cannot be sent for inactive account {managed_user.username} or an account without email.")
        else:
            try:
                send_account_password_link(request, managed_user)
            except AccountEmailDeliveryError:
                messages.error(
                    request,
                    f"The password reset link for {managed_user.username} could not be emailed. Check SMTP configuration and retry.",
                )
            else:
                messages.success(request, f"A password reset link was sent to {managed_user.email}.")
    else:
        messages.error(request, "Unknown account management action.")

    return redirect("webroaster:password_management")

def password_expired(request):
    if not request.user.is_authenticated:
        return redirect("webroaster:login")
    profile = password_profile_for(request.user)
    form = PasswordExpiredChangeForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        request.user.set_password(form.cleaned_data["new_password"])
        request.user.save(update_fields=["password"])
        profile.mark_changed(force_change=False)
        update_session_auth_hash(request, request.user)
        messages.success(request, "Your password has been updated.")
        return redirect("webroaster:home")
    context = {
        "form": form,
        "profile": profile,
        "title": "Password Reset Required",
    }
    return render(request, "webroaster/password_expired.html", context)


def forgot_password(request):
    User = get_user_model()
    form = ForgotPasswordRequestForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            matched_user = User.objects.filter(
                username=form.cleaned_data["username"].strip(),
                email__iexact=form.cleaned_data["email"].strip(),
                is_active=True,
            ).first()
            if matched_user:
                try:
                    send_account_password_link(request, matched_user)
                except AccountEmailDeliveryError:
                    logger.info("Self-service reset email was not delivered.")
            messages.info(
                request,
                "If the account details matched, a reset email was requested. Delivery is not confirmed; contact your system administrator if it does not arrive.",
            )
            return redirect("webroaster:forgot_password")
    return render(request, "webroaster/forgot_password.html", {"form": form, "title": "Forgot Password"})


def invitation_set_password(request, uidb64, token):
    User = get_user_model()
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = User._default_manager.get(pk=user_id, is_active=True)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is None or not default_token_generator.check_token(user, token):
        return render(
            request,
            "webroaster/invitation_invalid.html",
            {"title": "Invalid password link"},
            status=400,
        )

    form = SetPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        password_profile_for(user).mark_changed(force_change=False)
        messages.success(request, "Your password has been set. You can now sign in.")
        return redirect("webroaster:login")
    return render(
        request,
        "webroaster/invitation_set_password.html",
        {"form": form, "title": "Set your password"},
    )

