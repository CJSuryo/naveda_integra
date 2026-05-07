from django import template

register = template.Library()


@register.filter
def has_ni_perm(user, perm_code):
    return user.has_ni_perm(perm_code)
