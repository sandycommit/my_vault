from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from vault.models import VaultItem, vault_upload_path

User = get_user_model()


class SecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pw")
        self.other = User.objects.create_user(username="intruder", password="pw")

    def test_csrf_is_required_for_post_requests(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(reverse("vault:save_text"), {"text": "no csrf token"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(VaultItem.objects.count(), 0)

    def test_other_users_item_looks_like_a_404_not_403(self):
        item = VaultItem.objects.create(
            user=self.other, item_type=VaultItem.ItemType.TEXT, content="private"
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("vault:item_detail", args=[item.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_delete_another_users_item(self):
        item = VaultItem.objects.create(
            user=self.other, item_type=VaultItem.ItemType.TEXT, content="private"
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("vault:item_delete", args=[item.pk]))
        self.assertEqual(response.status_code, 404)
        item.refresh_from_db()
        self.assertFalse(item.is_deleted)

    def test_note_content_is_html_escaped(self):
        self.client.force_login(self.user)
        payload = "<script>alert(1)</script>"
        self.client.post(reverse("vault:save_text"), {"text": payload})

        response = self.client.get(reverse("vault:chat"))
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_link_only_accepts_http_and_https(self):
        self.client.force_login(self.user)
        self.client.post(reverse("vault:save_text"), {"text": "javascript:alert(1)"})
        item = VaultItem.objects.get(user=self.user)
        # Doesn't match the http(s)-only URL pattern, so it's stored as plain text,
        # never rendered as a clickable javascript: link.
        self.assertEqual(item.item_type, VaultItem.ItemType.TEXT)

    def test_storage_path_ignores_directory_traversal_in_filename(self):
        path = vault_upload_path(None, "../../../etc/passwd")
        self.assertNotIn("..", path)
        self.assertTrue(path.startswith("uploads/"))

    def test_anonymous_user_redirected_for_every_private_view(self):
        protected_urls = [
            reverse("vault:chat"),
            reverse("vault:favorites"),
            reverse("vault:trash"),
            reverse("vault:search"),
            reverse("vault:settings"),
        ]
        for url in protected_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("login"), response.url)
