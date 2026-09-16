from decimal import Decimal

from django import template

register = template.Library()


def format_with_thousands(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, Decimal):
        places = max(-value.as_tuple().exponent, 0)
        return f"{value:,.{places}f}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return value


@register.filter(name="thousands")
def thousands(value):
    return format_with_thousands(value)

