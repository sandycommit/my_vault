from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from vault.models import VaultItem

User = get_user_model()


class FavoriteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pw")
        self.other = User.objects.create_user(username="intruder", password="pw")
        self.client.force_login(self.user)

    def test_toggle_favorite_on_and_off(self):
        item = VaultItem.objects.create(
            user=self.user, item_type=VaultItem.ItemType.TEXT, content="x"
        )

        self.client.post(reverse("vault:item_favorite", args=[item.pk]))
        item.refresh_from_db()
        self.assertTrue(item.is_favorite)

        self.client.post(reverse("vault:item_favorite", args=[item.pk]))
        item.refresh_from_db()
        self.assertFalse(item.is_favorite)

    def test_favorites_page_lists_only_favorited_items(self):
        favorited = VaultItem.objects.create(
            user=self.user, item_type=VaultItem.ItemType.TEXT, content="fav", is_favorite=True
        )
        VaultItem.objects.create(
            user=self.user, item_type=VaultItem.ItemType.TEXT, content="not fav"
        )

        response = self.client.get(reverse("vault:favorites"))
        self.assertEqual(list(response.context["items"]), [favorited])

    def test_favorites_page_excludes_trashed_items(self):
        item = VaultItem.objects.create(
            user=self.user,
            item_type=VaultItem.ItemType.TEXT,
            content="fav but trashed",
            is_favorite=True,
        )
        item.soft_delete()

        response = self.client.get(reverse("vault:favorites"))
        self.assertEqual(list(response.context["items"]), [])

    def test_cannot_favorite_another_users_item(self):
        item = VaultItem.objects.create(
            user=self.other, item_type=VaultItem.ItemType.TEXT, content="private"
        )
        response = self.client.post(reverse("vault:item_favorite", args=[item.pk]))
        self.assertEqual(response.status_code, 404)
        item.refresh_from_db()
        self.assertFalse(item.is_favorite)
