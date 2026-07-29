from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string

# Small allowance for multipart boundaries/headers on top of the actual file bytes.
_REQUEST_OVERHEAD_BYTES = 1024 * 1024


class MaxUploadSizeMiddleware:
    """Reject oversized uploads early using Content-Length, before the body is read."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        content_length = request.META.get("CONTENT_LENGTH")
        if content_length:
            try:
                length = int(content_length)
            except (TypeError, ValueError):
                length = None
            if length is not None and length > settings.MAX_UPLOAD_SIZE_BYTES + _REQUEST_OVERHEAD_BYTES:
                html = render_to_string(
                    "errors/413.html",
                    {"max_upload_size_mb": settings.MAX_UPLOAD_SIZE_MB},
                    request=request,
                )
                return HttpResponse(html, status=413)
        return self.get_response(request)
