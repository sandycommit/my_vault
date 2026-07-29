from datetime import timedelta

from django import template
from django.utils import timezone

register = template.Library()

_TYPE_ICONS = {
    "text": "📝",
    "image": "🖼️",
    "video": "🎬",
    "audio": "🎵",
    "pdf": "📕",
    "document": "📄",
    "archive": "📦",
    "code": "💻",
    "link": "🔗",
    "other": "📁",
}


@register.filter
def day_label(value):
    """'Today' / 'Yesterday' / 'Month D, YYYY' — used with {% ifchanged %} to
    draw date separators in a chronological feed without a platform-specific
    strftime flag (Windows has no %-d)."""
    if not value:
        return ""
    item_date = timezone.localtime(value).date()
    today = timezone.localdate()
    if item_date == today:
        return "Today"
    if item_date == today - timedelta(days=1):
        return "Yesterday"
    return f"{item_date.strftime('%B')} {item_date.day}, {item_date.year}"


@register.filter
def item_icon(item_type):
    return _TYPE_ICONS.get(item_type, "📁")
