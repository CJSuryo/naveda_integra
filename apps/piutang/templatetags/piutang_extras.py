from django import template

register = template.Library()


@register.filter
def get_item(obj, key):
    try:
        return obj[key]
    except (KeyError, TypeError):
        return ''
