from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def som(value):
    """1450000 -> '1 450 000'."""
    try:
        v = Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return value
    if v == v.to_integral():
        return f"{int(v):,}".replace(',', ' ')
    return f"{v:,.2f}".replace(',', ' ').rstrip('0').rstrip('.')


@register.filter
def hm(value):
    return value.strftime('%H:%M') if value else ''


@register.filter
def initials(student):
    first = (getattr(student, 'first_name', '') or ' ')[0]
    last = (getattr(student, 'last_name', '') or ' ')[0]
    return (first + last).upper()


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None
