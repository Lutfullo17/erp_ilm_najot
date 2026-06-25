from django import template
from bot.services import money as money_formatter

register = template.Library()

@register.filter(name='money')
def money(value):
    return money_formatter(value)

@register.filter(name='get_item')
def get_item(dictionary, key):
    return dictionary.get(str(key)) or dictionary.get(int(key))

@register.filter(name='subtract')
def subtract(value, arg):
    try:
        return value - arg
    except:
        return 0
