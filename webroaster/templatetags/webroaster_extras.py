from decimal import Decimal

from django import template


register = template.Library()


@register.filter
def field_value(instance, field_name):
    value = getattr(instance, field_name, "")
    if callable(value):
        value = value()
    if isinstance(value, Decimal):
        return f"{value:,.2f}"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


@register.filter
def field_label(form, field_name):
    field = form.fields.get(field_name)
    return field.label if field else field_name.replace("_", " ").title()

