from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from vault.models import VaultItem

User = get_user_model()


class TextItemTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pw")
        self.client.force_login(self.user)

    def test_create_text_item(self):
        response = self.client.post(
            reverse("vault:save_text"), {"text": "Remember to deploy the Django app."}
        )
        self.assertRedirects(response, reverse("vault:chat"))
        item = VaultItem.objects.get(user=self.user)
        self.assertEqual(item.content, "Remember to deploy the Django app.")
        self.assertEqual(item.item_type, VaultItem.ItemType.TEXT)

    def test_empty_text_is_rejected(self):
        self.client.post(reverse("vault:save_text"), {"text": "   "})
        self.assertEqual(VaultItem.objects.count(), 0)

    def test_code_fence_is_detected_as_code(self):
        raw = "```python\nprint('hi')\n```"
        self.client.post(reverse("vault:save_text"), {"text": raw})
        item = VaultItem.objects.get(user=self.user)
        self.assertEqual(item.item_type, VaultItem.ItemType.CODE)
        self.assertEqual(item.language, "python")
        self.assertEqual(item.content, "print('hi')")

    def test_bare_url_is_detected_as_link(self):
        self.client.post(reverse("vault:save_text"), {"text": "https://example.com/path"})
        item = VaultItem.objects.get(user=self.user)
        self.assertEqual(item.item_type, VaultItem.ItemType.LINK)

    def test_item_detail_shows_owned_item(self):
        item = VaultItem.objects.create(
            user=self.user, item_type=VaultItem.ItemType.TEXT, content="hello world"
        )
        response = self.client.get(reverse("vault:item_detail", args=[item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "hello world")

    def test_edit_text_item(self):
        item = VaultItem.objects.create(
            user=self.user, item_type=VaultItem.ItemType.TEXT, content="old"
        )
        response = self.client.post(
            reverse("vault:item_edit", args=[item.pk]), {"text": "new content"}
        )
        self.assertRedirects(response, reverse("vault:item_detail", args=[item.pk]))
        item.refresh_from_db()
        self.assertEqual(item.content, "new content")

    def test_file_items_are_not_editable(self):
        item = VaultItem.objects.create(
            user=self.user,
            item_type=VaultItem.ItemType.OTHER,
            original_filename="report.pdf",
            file="uploads/2026/01/01/fake.pdf",
        )
        response = self.client.get(reverse("vault:item_edit", args=[item.pk]))
        self.assertEqual(response.status_code, 404)

    def test_delete_restore_and_permanent_delete(self):
        item = VaultItem.objects.create(
            user=self.user, item_type=VaultItem.ItemType.TEXT, content="x"
        )

        self.client.post(reverse("vault:item_delete", args=[item.pk]))
        item.refresh_from_db()
        self.assertTrue(item.is_deleted)
        self.assertIsNotNone(item.deleted_at)

        self.client.post(reverse("vault:item_restore", args=[item.pk]))
        item.refresh_from_db()
        self.assertFalse(item.is_deleted)
        self.assertIsNone(item.deleted_at)

        self.client.post(reverse("vault:item_delete", args=[item.pk]))
        self.client.post(reverse("vault:item_permanent_delete", args=[item.pk]))
        self.assertFalse(VaultItem.objects.filter(pk=item.pk).exists())

    def test_permanent_delete_requires_item_to_be_in_trash_first(self):
        item = VaultItem.objects.create(
            user=self.user, item_type=VaultItem.ItemType.TEXT, content="still active"
        )
        response = self.client.post(reverse("vault:item_permanent_delete", args=[item.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(VaultItem.objects.filter(pk=item.pk).exists())
