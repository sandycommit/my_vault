from django.conf import settings
from django.core.management.base import BaseCommand

from vault.models import VaultItem
from vault.services import database_size_mb, directory_size_bytes, find_orphaned_media_files


class Command(BaseCommand):
    help = "Report vault storage usage and optionally remove orphaned media files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete-orphans",
            action="store_true",
            help="Delete orphaned files found under MEDIA_ROOT. Without this flag, only reports them.",
        )

    def handle(self, *args, **options):
        total_items = VaultItem.objects.count()
        trashed = VaultItem.objects.filter(is_deleted=True).count()
        media_bytes = directory_size_bytes(settings.MEDIA_ROOT)

        self.stdout.write("Vault storage report")
        self.stdout.write("--------------------")
        self.stdout.write(f"Database items:  {total_items}")
        self.stdout.write(f"Items in trash:  {trashed}")
        self.stdout.write(f"Media on disk:   {media_bytes / (1024 * 1024):.2f} MB")
        try:
            self.stdout.write(f"Database size:   {database_size_mb():.2f} MB")
        except Exception as exc:  # pragma: no cover - depends on live DB connection
            self.stdout.write(self.style.WARNING(f"Could not read database size: {exc}"))

        orphans = find_orphaned_media_files()
        if not orphans:
            self.stdout.write(self.style.SUCCESS("No orphaned media files found."))
            return

        orphan_bytes = 0
        self.stdout.write(self.style.WARNING(f"Found {len(orphans)} orphaned file(s):"))
        for path in orphans:
            size = path.stat().st_size
            orphan_bytes += size
            self.stdout.write(f"  {path} ({size / 1024:.1f} KB)")
        self.stdout.write(f"Total orphaned size: {orphan_bytes / (1024 * 1024):.2f} MB")

        if options["delete_orphans"]:
            for path in orphans:
                path.unlink(missing_ok=True)
            self.stdout.write(self.style.SUCCESS(f"Deleted {len(orphans)} orphaned file(s)."))
        else:
            self.stdout.write("Run again with --delete-orphans to remove these files.")
