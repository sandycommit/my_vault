from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .forms import EditItemForm, FileUploadForm, TextItemForm
from .models import VaultItem
from .search import search_items
from .services import (
    create_text_item,
    delete_physical_file_if_orphaned,
    get_storage_report,
    save_uploaded_file,
    update_text_item,
)

# Mime types it is safe to render inline (img/video/audio/iframe). Everything
# else — including SVG, which can carry <script> — is attachment-only via
# item_download_view, never served inline.
_INLINE_SAFE_MIME_PREFIXES = (
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp", "image/tiff",
    "audio/", "video/", "application/pdf",
)


def _is_ajax(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _owned_item_or_404(request, pk, **extra_filters):
    """Ownership is always enforced at the query level, and a mismatch looks
    identical to a missing row — a 404, never a 403 — so a user can't probe
    for other people's item IDs."""
    return get_object_or_404(VaultItem, pk=pk, user=request.user, **extra_filters)


def _safe_next(request, fallback):
    candidate = request.POST.get("next") or request.META.get("HTTP_REFERER")
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return fallback


def _paginate(request, queryset, page_size=None):
    paginator = Paginator(queryset, page_size or settings.PAGE_SIZE)
    return paginator.get_page(request.GET.get("page") or 1)


# ---------------------------------------------------------------------------
# Chat (main screen) + infinite scroll
# ---------------------------------------------------------------------------

@login_required
def chat_view(request):
    base_qs = VaultItem.objects.filter(user=request.user, is_deleted=False)
    items = list(base_qs.order_by("-created_at")[: settings.PAGE_SIZE])
    items.reverse()  # oldest-of-page at top, newest at the bottom, like a chat feed

    has_more = bool(items) and base_qs.filter(created_at__lt=items[0].created_at).exists()

    context = {
        "items": items,
        "has_more": has_more,
        "oldest_id": items[0].id if items else None,
        "text_form": TextItemForm(),
        "upload_form": FileUploadForm(),
    }
    return render(request, "vault/chat.html", context)


@login_required
@require_GET
def load_more_view(request):
    """Returns an HTML partial (not JSON) of the next page of older items,
    for the composer's vanilla-JS scroll-up-to-load-older behaviour."""
    qs = VaultItem.objects.filter(user=request.user, is_deleted=False)

    before_id = request.GET.get("before")
    if before_id and before_id.isdigit():
        anchor = _owned_item_or_404(request, before_id)
        qs = qs.filter(created_at__lt=anchor.created_at)

    older = list(qs.order_by("-created_at")[: settings.PAGE_SIZE])
    older.reverse()

    has_more = bool(older) and VaultItem.objects.filter(
        user=request.user, is_deleted=False, created_at__lt=older[0].created_at
    ).exists()

    response = render(request, "vault/partials/item_feed.html", {"items": older})
    response["X-Has-More"] = "true" if has_more else "false"
    response["X-Oldest-Id"] = str(older[0].id) if older else ""
    return response


@login_required
@require_POST
def save_text_view(request):
    form = TextItemForm(request.POST)
    if not form.is_valid():
        if _is_ajax(request):
            return HttpResponseBadRequest(form.errors.as_text())
        messages.error(request, "Write something before saving.")
        return redirect("vault:chat")

    item = create_text_item(request.user, form.cleaned_data["text"])

    if _is_ajax(request):
        return render(request, "vault/components/item_card.html", {"item": item})

    messages.success(request, "Saved to your vault.")
    return redirect("vault:chat")


@login_required
@require_POST
def upload_file_view(request):
    form = FileUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        error_text = form.errors.as_text()
        if _is_ajax(request):
            return HttpResponseBadRequest(error_text)
        messages.error(request, error_text)
        return redirect("vault:chat")

    item = save_uploaded_file(request.user, form.cleaned_data["file"])

    if _is_ajax(request):
        return render(request, "vault/components/item_card.html", {"item": item})

    messages.success(request, "Uploaded to your vault.")
    return redirect("vault:chat")


# ---------------------------------------------------------------------------
# Item detail / edit / actions
# ---------------------------------------------------------------------------

@login_required
def item_detail_view(request, pk):
    item = _owned_item_or_404(request, pk)
    return render(request, "vault/item_detail.html", {"item": item})


@login_required
def item_edit_view(request, pk):
    item = _owned_item_or_404(request, pk, is_deleted=False)
    if not item.is_editable:
        raise Http404

    if request.method == "POST":
        form = EditItemForm(request.POST)
        if form.is_valid():
            update_text_item(item, form.cleaned_data["text"])
            messages.success(request, "Updated.")
            return redirect("vault:item_detail", pk=item.pk)
    else:
        initial_text = item.content
        if item.item_type == VaultItem.ItemType.CODE:
            initial_text = f"```{item.language}\n{item.content}\n```"
        form = EditItemForm(initial={"text": initial_text})

    return render(request, "vault/item_edit.html", {"item": item, "form": form})


@login_required
@require_POST
def item_favorite_view(request, pk):
    item = _owned_item_or_404(request, pk)
    item.is_favorite = not item.is_favorite
    item.save(update_fields=["is_favorite", "updated_at"])

    if _is_ajax(request):
        return render(request, "vault/partials/favorite_button.html", {"item": item})
    return redirect(_safe_next(request, reverse("vault:chat")))


@login_required
@require_POST
def item_delete_view(request, pk):
    item = _owned_item_or_404(request, pk, is_deleted=False)
    item.soft_delete()

    if _is_ajax(request):
        return HttpResponse(status=204)
    messages.success(request, "Moved to Trash.")
    return redirect(_safe_next(request, reverse("vault:chat")))


@login_required
@require_POST
def item_restore_view(request, pk):
    item = _owned_item_or_404(request, pk, is_deleted=True)
    item.restore()

    if _is_ajax(request):
        return HttpResponse(status=204)
    messages.success(request, "Restored.")
    return redirect(_safe_next(request, reverse("vault:trash")))


@login_required
@require_POST
def item_permanent_delete_view(request, pk):
    item = _owned_item_or_404(request, pk, is_deleted=True)
    with transaction.atomic():
        delete_physical_file_if_orphaned(item)
        item.delete()

    if _is_ajax(request):
        return HttpResponse(status=204)
    messages.success(request, "Permanently deleted.")
    return redirect(_safe_next(request, reverse("vault:trash")))


@login_required
@require_POST
def empty_trash_view(request):
    trashed_items = list(VaultItem.objects.filter(user=request.user, is_deleted=True))
    with transaction.atomic():
        # Deleted one at a time (not a bulk queryset .delete()) so the orphan
        # check for each item sees the up-to-date state of its siblings.
        for item in trashed_items:
            delete_physical_file_if_orphaned(item)
            item.delete()
    messages.success(request, "Trash emptied.")
    return redirect("vault:trash")


@login_required
@require_GET
def item_download_view(request, pk):
    item = _owned_item_or_404(request, pk, is_deleted=False)
    if not item.file:
        raise Http404
    return FileResponse(
        item.file.open("rb"),
        as_attachment=True,
        filename=item.original_filename or "download",
        content_type=item.mime_type or None,
    )


@login_required
@require_GET
def item_raw_view(request, pk):
    item = _owned_item_or_404(request, pk, is_deleted=False)
    mime_type = item.mime_type or ""
    if not item.file or not mime_type.startswith(_INLINE_SAFE_MIME_PREFIXES):
        raise Http404
    response = FileResponse(item.file.open("rb"), content_type=mime_type)
    response["Content-Disposition"] = "inline"
    response["X-Content-Type-Options"] = "nosniff"
    return response


# ---------------------------------------------------------------------------
# Favorites / Trash / Search / Settings
# ---------------------------------------------------------------------------

@login_required
def favorites_view(request):
    qs = VaultItem.objects.filter(
        user=request.user, is_deleted=False, is_favorite=True
    ).order_by("-created_at")
    page = _paginate(request, qs)
    return render(request, "vault/favorites.html", {"page_obj": page, "items": page.object_list})


@login_required
def trash_view(request):
    qs = VaultItem.objects.filter(user=request.user, is_deleted=True).order_by("-deleted_at")
    page = _paginate(request, qs)
    return render(request, "vault/trash.html", {"page_obj": page, "items": page.object_list})


@login_required
def search_view(request):
    query = request.GET.get("q", "").strip()
    page = None
    if query:
        page = _paginate(request, search_items(request.user, query))

    return render(
        request,
        "vault/search.html",
        {
            "query": query,
            "page_obj": page,
            "items": page.object_list if page else [],
        },
    )


@login_required
def settings_view(request):
    return render(request, "vault/settings.html", {"report": get_storage_report(request.user)})


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

def error_400(request, exception=None):
    return render(request, "errors/400.html", status=400)


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)
