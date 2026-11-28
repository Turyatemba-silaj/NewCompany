from django import template

from webroaster.advance_routing import can_open_queue

register = template.Library()
register.simple_tag(can_open_queue, name="can_open_advance_queue")
