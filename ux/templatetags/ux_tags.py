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
def plain(value):
    """Decimal/matn -> ortiqcha nolsiz matn: 300000.00 -> '300000', 1.5 -> '1.5', '' -> ''."""
    if value in (None, ''):
        return ''
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    return str(int(d)) if d == d.to_integral() else str(d.normalize())


@register.filter
def phone(value):
    """901234567 / +998 90 123 45 67 -> '90 123 45 67' (aniq 9 raqam bo'lsa)."""
    d = ''.join(ch for ch in str(value or '') if ch.isdigit())
    if d.startswith('998') and len(d) == 12:
        d = d[3:]
    if len(d) == 9:
        return f'{d[:2]} {d[2:5]} {d[5:7]} {d[7:]}'
    return value or ''


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
