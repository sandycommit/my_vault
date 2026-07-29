import hashlib
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from vault.models import VaultItem

User = get_user_model()


class MediaIsolatedTestCase(TestCase):
    """Uploads write real bytes to disk — point MEDIA_ROOT at a throwaway
    temp directory so tests never touch the project's actual media/ folder."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix="vault_test_media_")
        cls._override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()


class FileUploadTests(MediaIsolatedTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pw")
        self.other = User.objects.create_user(username="intruder", password="pw")
        self.client.force_login(self.user)

    def test_upload_creates_item_with_metadata(self):
        content = b"hello vault"
        upload = SimpleUploadedFile("notes.txt", content, content_type="text/plain")
        response = self.client.post(reverse("vault:upload_file"), {"file": upload})
        self.assertRedirects(response, reverse("vault:chat"))

        item = VaultItem.objects.get(user=self.user)
        self.assertEqual(item.original_filename, "notes.txt")
        self.assertEqual(item.file_size, len(content))
        self.assertEqual(item.file_hash, hashlib.sha256(content).hexdigest())

    def test_empty_file_is_rejected(self):
        upload = SimpleUploadedFile("empty.txt", b"", content_type="text/plain")
        self.client.post(reverse("vault:upload_file"), {"file": upload})
        self.assertEqual(VaultItem.objects.count(), 0)

    def test_blocked_extension_is_rejected(self):
        upload = SimpleUploadedFile(
            "installer.exe", b"MZ-fake-binary", content_type="application/octet-stream"
        )
        self.client.post(reverse("vault:upload_file"), {"file": upload})
        self.assertEqual(VaultItem.objects.count(), 0)

    @override_settings(MAX_UPLOAD_SIZE_BYTES=10)
    def test_oversized_file_is_rejected(self):
        upload = SimpleUploadedFile("big.txt", b"x" * 100, content_type="text/plain")
        self.client.post(reverse("vault:upload_file"), {"file": upload})
        self.assertEqual(VaultItem.objects.count(), 0)

    def test_duplicate_upload_reuses_physical_storage(self):
        content = b"identical bytes for both uploads"
        self.client.post(
            reverse("vault:upload_file"),
            {"file": SimpleUploadedFile("first.txt", content, content_type="text/plain")},
        )
        self.client.post(
            reverse("vault:upload_file"),
            {"file": SimpleUploadedFile("second.txt", content, content_type="text/plain")},
        )

        items = list(VaultItem.objects.filter(user=self.user).order_by("created_at"))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].file.name, items[1].file.name)
        self.assertEqual(items[0].file_hash, items[1].file_hash)
        # Only one physical file should exist on disk despite two vault entries.
        self.assertEqual(
            VaultItem.objects.filter(file_hash=items[0].file_hash).count(), 2
        )

    def test_download_requires_ownership(self):
        item = VaultItem.objects.create(
            user=self.other,
            item_type=VaultItem.ItemType.OTHER,
            original_filename="secret.txt",
        )
        response = self.client.get(reverse("vault:item_download", args=[item.pk]))
        self.assertEqual(response.status_code, 404)

    def test_download_owned_file(self):
        upload = SimpleUploadedFile("report.txt", b"contents", content_type="text/plain")
        self.client.post(reverse("vault:upload_file"), {"file": upload})
        item = VaultItem.objects.get(user=self.user)

        response = self.client.get(reverse("vault:item_download", args=[item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_svg_upload_is_never_served_inline(self):
        upload = SimpleUploadedFile(
            "icon.svg", b"<svg onload='alert(1)'></svg>", content_type="image/svg+xml"
        )
        self.client.post(reverse("vault:upload_file"), {"file": upload})
        item = VaultItem.objects.get(user=self.user)

        self.assertNotEqual(item.item_type, VaultItem.ItemType.IMAGE)
        response = self.client.get(reverse("vault:item_raw", args=[item.pk]))
        self.assertEqual(response.status_code, 404)
