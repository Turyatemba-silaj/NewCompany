"""Edit an existing account's role memberships and direct permission grants."""

import json

from django import forms
from django.contrib import messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from .access import ROLE_GROUPS
from .views import render_page


class UserAccessForm(forms.Form):
    groups = forms.ModelMultipleChoiceField(
        label="Role groups", queryset=Group.objects.order_by("name"), required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    permissions = forms.ModelMultipleChoiceField(
        label="Individual permissions",
        queryset=Permission.objects.select_related("content_type").order_by(
            "content_type__app_label", "content_type__model", "name", "pk",
        ),
        required=False, widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, target, **kwargs):
        super().__init__(*args, **kwargs)
        self.target = target
        self.fields["permissions"].label_from_instance = lambda permission: (
            f"{permission.content_type.app_label}.{permission.content_type.model} — {permission.name}"
        )

    def clean_groups(self):
        groups = self.cleaned_data["groups"]
        if self.target.is_staff and not any(group.name in ROLE_GROUPS for group in groups):
            raise forms.ValidationError(
                "Select a NewCompany staff role. Use Block on Access Control to suspend access."
            )
        return groups


def access_snapshot(groups, permissions):
    return {
        "groups": sorted(group.name for group in groups),
        "permissions": sorted(
            f"{permission.content_type.app_label}.{permission.codename}" for permission in permissions
        ),
    }


@require_http_methods(["GET", "POST"])
def edit_user_access(request, user_id):
    if not (request.user.is_active and request.user.is_staff and request.user.is_superuser):
        raise PermissionDenied
    users = get_user_model().objects
    with transaction.atomic():
        target = get_object_or_404(users.select_for_update() if request.method == "POST" else users, pk=user_id)
        if target.is_superuser:
            raise PermissionDenied("Use administrator account management for superuser accounts.")
        direct_permissions = target.user_permissions.select_related("content_type")
        form = UserAccessForm(
            request.POST if request.method == "POST" else None,
            target=target,
            initial={"groups": target.groups.all(), "permissions": direct_permissions},
        )
        if request.method == "POST" and form.is_valid():
            groups = form.cleaned_data["groups"]
            permissions = form.cleaned_data["permissions"]
            before = access_snapshot(target.groups.all(), direct_permissions)
            after = access_snapshot(groups, permissions)
            if before != after:
                target.groups.set(groups)
                target.user_permissions.set(permissions)
                LogEntry.objects.create(
                    user=request.user,
                    content_type=ContentType.objects.get_for_model(target),
                    object_id=str(target.pk),
                    object_repr=target.get_username()[:200],
                    action_flag=CHANGE,
                    change_message="Access updated " + json.dumps({"before": before, "after": after}),
                )
                messages.success(request, f"Access updated for {target.get_username()}.")
            else:
                messages.info(request, "Access is already set to these values.")
            return redirect("webroaster:password_management")

    inherited = Permission.objects.filter(group__user=target).select_related(
        "content_type",
    ).distinct().order_by("content_type__app_label", "content_type__model", "name", "pk")
    return render_page(request, "webroaster/edit_user_access.html", {
        "title": "Edit User Access", "target": target, "form": form, "inherited": inherited,
    }, "password-management")
