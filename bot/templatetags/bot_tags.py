from django import template
from bot.services import money as money_formatter
import datetime

register = template.Library()

@register.filter(name='money')
def money(value):
    return money_formatter(value)

@register.filter(name='money_uz')
def money_uz(value):
    try:
        val = int(float(value))
        return "{:,}".format(val).replace(',', ' ') + " so'm"
    except (ValueError, TypeError):
        return value

@register.filter(name='date_format_uz')
def date_format_uz(value):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            # Try ISO format first
            value = datetime.date.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime('%d.%m.%Y')
    return value

@register.filter(name='get_item')
def get_item(dictionary, key):
    return dictionary.get(str(key)) or dictionary.get(int(key))

@register.filter(name='subtract')
def subtract(value, arg):
    try:
        return value - arg
    except:
        return 0

@register.filter(name='split')
def split(value, delimiter=','):
    if not value:
        return []
    return [item.strip() for item in str(value).split(delimiter) if item.strip()]
