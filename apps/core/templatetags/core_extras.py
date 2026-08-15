from django import template

register = template.Library()


@register.filter
def money(value, symbol="₦"):
    try:
        return f"{symbol}{float(value):,.2f}"
    except (TypeError, ValueError):
        return f"{symbol}0.00"


@register.filter
def num(value):
    try:
        v = float(value)
        return str(int(v)) if v == int(v) else f"{v:g}"
    except (TypeError, ValueError):
        return value
