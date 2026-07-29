from django.contrib import admin

from .models import VaultItem


@admin.register(VaultItem)
class VaultItemAdmin(admin.ModelAdmin):
    # Content/notes are intentionally left out of the list view — metadata only.
    list_display = (
        "id", "user", "item_type", "original_filename", "file_size",
        "is_favorite", "is_deleted", "created_at",
    )
    list_filter = ("item_type", "is_favorite", "is_deleted", "created_at")
    search_fields = ("original_filename", "content", "tags", "mime_type")
    date_hierarchy = "created_at"
    list_select_related = ("user",)
    readonly_fields = ("file_hash", "search_vector", "created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("user", "item_type")}),
        ("Content", {"fields": ("content", "language", "tags")}),
        (
            "File metadata",
            {"fields": ("original_filename", "file", "thumbnail", "mime_type", "file_size", "file_hash")},
        ),
        ("State", {"fields": ("is_favorite", "is_deleted", "deleted_at")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
        ("Search", {"fields": ("search_vector",)}),
    )
