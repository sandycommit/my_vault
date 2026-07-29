from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from vault.models import VaultItem

User = get_user_model()


class QueryCountTests(TestCase):
    """A page whose query count grows with the number of items has an N+1
    somewhere in its template. These compare a small vault against a larger
    one and require the count to stay flat."""

    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pw")
        self.client.force_login(self.user)

    def _query_count(self, url, item_count, **item_kwargs):
        VaultItem.objects.filter(user=self.user).delete()
        for i in range(item_count):
            VaultItem.objects.create(
                user=self.user,
                item_type=VaultItem.ItemType.TEXT,
                content=f"item {i}",
                **item_kwargs,
            )
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_chat_view_query_count_does_not_grow_with_item_count(self):
        small = self._query_count(reverse("vault:chat"), 3)
        large = self._query_count(reverse("vault:chat"), 30)
        self.assertEqual(small, large)

    def test_favorites_view_query_count_does_not_grow_with_item_count(self):
        url = reverse("vault:favorites")
        small = self._query_count(url, 3, is_favorite=True)
        large = self._query_count(url, 30, is_favorite=True)
        self.assertEqual(small, large)

    def test_trash_view_query_count_does_not_grow_with_item_count(self):
        url = reverse("vault:trash")
        small = self._query_count(url, 3, is_deleted=True)
        large = self._query_count(url, 30, is_deleted=True)
        self.assertEqual(small, large)
