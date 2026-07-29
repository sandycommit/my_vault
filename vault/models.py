import uuid
from pathlib import PurePosixPath

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models
from django.utils import timezone


def _safe_extension(filename):
    """Return a short, filesystem-safe extension derived from filename, never the filename itself."""
    ext = PurePosixPath(filename or "").suffix.lower()
    ext = "".join(ch for ch in ext if ch.isalnum() or ch == ".")
    return ext[:16]


def _dated_storage_path(subdir, filename):
    """Generate a random, collision-proof storage path. Never derived from user input,
    so path traversal via a crafted original filename is not possible."""
    today = timezone.now()
    safe_name = f"{uuid.uuid4().hex}{_safe_extension(filename)}"
    return f"{subdir}/{today:%Y}/{today:%m}/{today:%d}/{safe_name}"


def vault_upload_path(instance, filename):
    return _dated_storage_path(settings.VAULT_UPLOAD_SUBDIR, filename)


def vault_thumbnail_path(instance, filename):
    return _dated_storage_path(settings.VAULT_THUMBNAIL_SUBDIR, filename)


class VaultItem(models.Model):
    """A single chronological entry in the vault: either free text/code/a link,
    or metadata describing a file stored on disk under MEDIA_ROOT."""

    class ItemType(models.TextChoices):
        TEXT = "text", "Text"
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        AUDIO = "audio", "Audio"
        PDF = "pdf", "PDF"
        DOCUMENT = "document", "Document"
        ARCHIVE = "archive", "Archive"
        CODE = "code", "Code"
        LINK = "link", "Link"
        OTHER = "other", "Other"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vault_items",
    )
    item_type = models.CharField(
        max_length=12, choices=ItemType.choices, default=ItemType.TEXT
    )

    # Text-like content: note body, code body, or a saved link URL.
    content = models.TextField(blank=True)
    language = models.CharField(max_length=32, blank=True)
    tags = models.CharField(max_length=255, blank=True)

    # File-backed items only. Binary bytes always live on the filesystem,
    # never in PostgreSQL — these fields store metadata/pointers only.
    file = models.FileField(upload_to=vault_upload_path, blank=True, null=True)
    thumbnail = models.ImageField(upload_to=vault_thumbnail_path, blank=True, null=True)
    original_filename = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=127, blank=True)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    file_hash = models.CharField(max_length=64, blank=True)  # sha256 hex digest

    is_favorite = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    search_vector = SearchVectorField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "is_deleted", "created_at"],
                name="vault_user_del_created_idx",
            ),
            models.Index(
                fields=["user", "is_favorite", "created_at"],
                name="vault_user_fav_created_idx",
            ),
            models.Index(
                fields=["user", "file_hash"],
                name="vault_user_filehash_idx",
            ),
            GinIndex(fields=["search_vector"], name="vault_search_vector_gin"),
        ]

    def __str__(self):
        return self.display_title

    @property
    def display_title(self):
        if self.original_filename:
            return self.original_filename
        stripped = self.content.strip()
        if stripped:
            return stripped.splitlines()[0][:80]
        return f"Item {self.pk}"

    @property
    def tag_list(self):
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]

    @property
    def is_file_item(self):
        return bool(self.file)

    @property
    def is_editable(self):
        return self.item_type in {self.ItemType.TEXT, self.ItemType.CODE, self.ItemType.LINK} and not self.file

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def update_search_vector(self):
        """Recompute the search vector via an UPDATE ... expression (no DB trigger needed).
        Called only when content/filename/tags actually change, not on every save."""
        VaultItem.objects.filter(pk=self.pk).update(
            search_vector=(
                SearchVector("content", weight="A", config="english")
                + SearchVector("original_filename", weight="B", config="english")
                + SearchVector("tags", weight="C", config="english")
                + SearchVector("mime_type", weight="D", config="english")
            )
        )
