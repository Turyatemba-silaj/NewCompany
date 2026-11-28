from django import template
from banking.views import allowed, ROLES
register=template.Library()
@register.simple_tag
def banking_visible(user):
    return user.is_superuser or allowed(user,*ROLES)
