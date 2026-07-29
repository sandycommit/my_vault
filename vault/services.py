"""Business logic for creating, deduplicating, and cleaning up vault items.

Kept separate from views.py so the request/response plumbing stays thin and
this logic is easy to unit test directly.
"""
import hashlib
import mimetypes
import re
import uuid
from io import BytesIO
from pathlib import PurePosixPath

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connection
from django.db.models import Sum

from .models import VaultItem

# Extensions we refuse to store even for a trusted single-user vault, because
# they are directly executable if this deployment's media is ever misconfigured
# to serve with execute permissions.
BLOCKED_UPLOAD_EXTENSIONS = {
    ".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".ps1", ".vbs", ".jar", ".apk", ".dll",
}

# SVG is deliberately excluded: it can embed <script>, and is never safe to
# render inline (see item_raw_view's mime allowlist in views.py). SVG uploads
# fall through to ItemType.OTHER and are only ever offered as a download.
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".tiff"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}
_ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2"}
_ARCHIVE_MIMES = {
    "application/zip", "application/x-rar-compressed", "application/vnd.rar",
    "application/x-7z-compressed", "application/x-tar", "application/gzip",
}
_DOCUMENT_EXTS = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp", ".txt", ".rtf"}

_FENCE_RE = re.compile(r"\A```([a-zA-Z0-9_+-]*)\n(.*)\n```\Z", re.DOTALL)
_URL_RE = re.compile(r"\Ahttps?://\S+\Z")


def compute_sha256(uploaded_file):
    """Stream the file in chunks so we never load a large upload fully into memory."""
    hasher = hashlib.sha256()
    uploaded_file.seek(0)
    for chunk in uploaded_file.chunks():
        hasher.update(chunk)
    uploaded_file.seek(0)
    return hasher.hexdigest()


def resolve_mime_type(filename, declared_content_type=""):
    """Prefer extension-based detection over a client-declared Content-Type header,
    which cannot be trusted on its own."""
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed
    if declared_content_type:
        return declared_content_type[:127]
    return "application/octet-stream"


def detect_item_type(mime_type, extension):
    extension = (extension or "").lower()
    mime_type = mime_type or ""

    # SVG can embed <script> and is never treated as a previewable image (see
    # the inline-serving mime allowlist in views.py) — it always falls through
    # to OTHER, regardless of what its mimetype "starts with".
    if extension == ".svg" or mime_type == "image/svg+xml":
        return VaultItem.ItemType.OTHER
    if extension == ".pdf" or mime_type == "application/pdf":
        return VaultItem.ItemType.PDF
    if extension in _IMAGE_EXTS or mime_type.startswith("image/"):
        return VaultItem.ItemType.IMAGE
    if extension in _VIDEO_EXTS or mime_type.startswith("video/"):
        return VaultItem.ItemType.VIDEO
    if extension in _AUDIO_EXTS or mime_type.startswith("audio/"):
        return VaultItem.ItemType.AUDIO
    if extension in _ARCHIVE_EXTS or mime_type in _ARCHIVE_MIMES:
        return VaultItem.ItemType.ARCHIVE
    if extension in _DOCUMENT_EXTS or "word" in mime_type or "officedocument" in mime_type:
        return VaultItem.ItemType.DOCUMENT
    return VaultItem.ItemType.OTHER


def parse_composer_text(raw_text):
    """Detect a fenced code block or a bare URL so the composer can behave like a
    single smart input, the same way Telegram/WhatsApp self-chat renders content."""
    text = raw_text.strip()
    fence_match = _FENCE_RE.match(text)
    if fence_match:
        language = fence_match.group(1).strip().lower()
        body = fence_match.group(2)
        return VaultItem.ItemType.CODE, body, language
    if _URL_RE.match(text):
        return VaultItem.ItemType.LINK, text, ""
    return VaultItem.ItemType.TEXT, text, ""


def create_text_item(user, raw_text):
    item_type, content, language = parse_composer_text(raw_text)
    item = VaultItem.objects.create(
        user=user, item_type=item_type, content=content, language=language,
    )
    item.update_search_vector()
    return item


def update_text_item(item, raw_text):
    item_type, content, language = parse_composer_text(raw_text)
    item.item_type = item_type
    item.content = content
    item.language = language
    item.save(update_fields=["item_type", "content", "language", "updated_at"])
    item.update_search_vector()
    return item


def save_uploaded_file(user, uploaded_file):
    """Create a VaultItem for an uploaded file, reusing existing storage when the
    same user has already uploaded identical bytes (matched by SHA-256)."""
    file_hash = compute_sha256(uploaded_file)
    extension = PurePosixPath(uploaded_file.name).suffix.lower()
    mime_type = resolve_mime_type(uploaded_file.name, getattr(uploaded_file, "content_type", ""))
    item_type = detect_item_type(mime_type, extension)

    existing = (
        VaultItem.objects.filter(user=user, file_hash=file_hash)
        .exclude(file="")
        .order_by("-created_at")
        .first()
    )

    item = VaultItem(
        user=user,
        item_type=item_type,
        original_filename=uploaded_file.name[:255],
        mime_type=mime_type,
        file_size=uploaded_file.size,
        file_hash=file_hash,
    )

    if existing:
        # Reuse the physical file already on disk — no duplicate bytes written.
        item.file.name = existing.file.name
        if existing.thumbnail:
            item.thumbnail.name = existing.thumbnail.name
        item.save()
    else:
        item.file = uploaded_file
        item.save()
        maybe_create_thumbnail(item)

    item.update_search_vector()
    return item


def maybe_create_thumbnail(item):
    if item.item_type != VaultItem.ItemType.IMAGE or not settings.THUMBNAILS_ENABLED or not item.file:
        return

    max_source_bytes = settings.THUMBNAIL_MAX_SOURCE_MB * 1024 * 1024
    if item.file_size and item.file_size > max_source_bytes:
        return

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        return

    buffer = BytesIO()
    try:
        item.file.open("rb")
        with Image.open(item.file) as image:
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            image.thumbnail((settings.THUMBNAIL_MAX_DIMENSION, settings.THUMBNAIL_MAX_DIMENSION))
            image.save(buffer, format="JPEG", quality=82)
    except (UnidentifiedImageError, OSError):
        return
    finally:
        item.file.close()

    buffer.seek(0)
    item.thumbnail.save(f"{uuid.uuid4().hex}.jpg", ContentFile(buffer.read()), save=True)


def delete_physical_file_if_orphaned(item):
    """Only remove bytes from disk if no other VaultItem row still points at them —
    duplicate uploads share a single physical copy."""
    if item.file:
        file_name = item.file.name
        if not VaultItem.objects.filter(file=file_name).exclude(pk=item.pk).exists():
            item.file.storage.delete(file_name)
    if item.thumbnail:
        thumb_name = item.thumbnail.name
        if not VaultItem.objects.filter(thumbnail=thumb_name).exclude(pk=item.pk).exists():
            item.thumbnail.storage.delete(thumb_name)


def find_orphaned_media_files():
    """Files on disk under MEDIA_ROOT that no VaultItem row references any more —
    e.g. left behind by a crashed request. Used by `manage.py cleanup_vault`."""
    referenced = set(VaultItem.objects.exclude(file="").values_list("file", flat=True))
    referenced |= set(VaultItem.objects.exclude(thumbnail="").values_list("thumbnail", flat=True))

    orphans = []
    for subdir in (settings.VAULT_UPLOAD_SUBDIR, settings.VAULT_THUMBNAIL_SUBDIR):
        root = settings.MEDIA_ROOT / subdir
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(settings.MEDIA_ROOT).as_posix()
            if relative not in referenced:
                orphans.append(path)
    return orphans


def directory_size_bytes(path):
    if not path.exists():
        return 0
    return sum(entry.stat().st_size for entry in path.rglob("*") if entry.is_file())


def database_size_mb():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_database_size(current_database())")
        (size_bytes,) = cursor.fetchone()
    return round(size_bytes / (1024 * 1024), 2)


def get_storage_report(user):
    """Computed on demand only (settings page view), never on every request."""
    base_qs = VaultItem.objects.filter(user=user)
    active_qs = base_qs.filter(is_deleted=False)
    trash_qs = base_qs.filter(is_deleted=True)

    return {
        "total_items": base_qs.count(),
        "text_items": active_qs.filter(file="").count(),
        "file_items": active_qs.exclude(file="").count(),
        "image_items": active_qs.filter(item_type=VaultItem.ItemType.IMAGE).count(),
        "favorite_items": active_qs.filter(is_favorite=True).count(),
        "trash_items": trash_qs.count(),
        "trash_bytes": trash_qs.aggregate(total=Sum("file_size"))["total"] or 0,
        "media_bytes": directory_size_bytes(settings.MEDIA_ROOT),
        "database_mb": database_size_mb(),
        "database_budget_mb": settings.DB_STORAGE_BUDGET_MB,
        "database_warning_mb": settings.DB_STORAGE_WARNING_MB,
    }
