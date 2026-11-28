from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password

from .access import ROLE_GROUPS, provision_user, role_group_permission_queryset, sync_role_groups
from .models import Employee


class PasswordExpiredChangeForm(forms.Form):
    current_password = forms.CharField(
        label="Current password",
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "current-password"}),
    )
    new_password = forms.CharField(
        label="New password",
        min_length=8,
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
    )
    confirm_password = forms.CharField(
        label="Confirm password",
        min_length=8,
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        password = self.cleaned_data["current_password"]
        if self.user and not self.user.check_password(password):
            raise forms.ValidationError("Current password is not correct.")
        return password

    def clean_new_password(self):
        password = self.cleaned_data["new_password"]
        validate_password(password, self.user)
        return password

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")
        if new_password and confirm_password and new_password != confirm_password:
            raise forms.ValidationError("The two password fields did not match.")
        return cleaned_data


class ForgotPasswordRequestForm(forms.Form):
    username = forms.CharField(label="Username", max_length=150)
    email = forms.EmailField(label="Account email")


class AdminUserCreationForm(forms.Form):
    employee = forms.ModelChoiceField(
        label="Employee",
        queryset=Employee.objects.filter(status="active").order_by("employee_number", "first_name", "last_name"),
        empty_label="Select employee",
        help_text="The employee number becomes the login username.",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    groups = forms.ModelChoiceField(
        label="Role group",
        queryset=Group.objects.none(),
        required=False,
        empty_label="Select a role group",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    permissions = forms.ModelMultipleChoiceField(
        label="Additional permissions",
        queryset=Permission.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-control permission-select", "size": "5"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_model = get_user_model()
        sync_role_groups()
        self.fields["groups"].queryset = Group.objects.filter(name__in=ROLE_GROUPS).order_by("name")
        self.fields["employee"].label_from_instance = self.employee_label
        self.fields["permissions"].label_from_instance = self.permission_label
        group = self.selected_group()
        if group:
            self.fields["permissions"].queryset = role_group_permission_queryset(group).select_related("content_type").order_by("content_type__model", "codename")

    def selected_group(self):
        group_id = None
        if self.is_bound:
            group_id = self.data.get(self.add_prefix("groups"))
        else:
            group_id = self.initial.get("groups")
        if not group_id:
            return None
        return self.fields["groups"].queryset.filter(pk=group_id).first()

    @staticmethod
    def employee_label(employee):
        name = f"{employee.first_name} {employee.last_name}".strip()
        number = employee.employee_number or f"Employee #{employee.pk}"
        department = employee.get_department_display() if hasattr(employee, "get_department_display") else employee.department
        return f"{number} - {name} ({department})"

    @staticmethod
    def permission_label(permission):
        return permission.name

    def clean_employee(self):
        employee = self.cleaned_data["employee"]
        username = (employee.employee_number or "").strip()
        if not username:
            raise forms.ValidationError("Selected employee does not have an employee number yet.")
        if self.user_model.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A system user already exists for this employee number.")
        email = (employee.email or "").strip()
        if not email:
            raise forms.ValidationError("The employee needs an email address before an account can be invited.")
        if email and self.user_model.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A system user already exists for this employee email.")
        return employee

    def save(self, actor):
        employee = self.cleaned_data["employee"]
        return provision_user(
            actor,
            username=employee.employee_number.strip(),
            first_name=employee.first_name,
            last_name=employee.last_name,
            email=employee.email.strip(),
            group=self.cleaned_data.get("groups"),
            permissions=self.cleaned_data.get("permissions"),
        )

