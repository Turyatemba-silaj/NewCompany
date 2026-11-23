from django import template

register = template.Library()


@register.simple_tag
def can_open_hr_reports(user):
    return user.is_authenticated and user.is_staff and (
        user.is_superuser or user.groups.filter(name="Human Resources").exists()
    )
