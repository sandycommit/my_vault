from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from vault.models import VaultItem

User = get_user_model()


class SearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="pw")
        self.other = User.objects.create_user(username="intruder", password="pw")
        self.client.force_login(self.user)

    def _create(self, owner=None, **kwargs):
        item = VaultItem.objects.create(user=owner or self.user, **kwargs)
        item.update_search_vector()
        return item

    def test_search_matches_note_content(self):
        match = self._create(
            item_type=VaultItem.ItemType.TEXT,
            content="Use session authentication for the Django project.",
        )
        self._create(item_type=VaultItem.ItemType.TEXT, content="Unrelated grocery list.")

        response = self.client.get(reverse("vault:search"), {"q": "django authentication"})
        results = list(response.context["items"])
        self.assertIn(match, results)
        self.assertEqual(len(results), 1)

    def test_search_matches_filename(self):
        match = self._create(
            item_type=VaultItem.ItemType.PDF, original_filename="django-deployment-guide.pdf"
        )
        response = self.client.get(reverse("vault:search"), {"q": "deployment"})
        self.assertIn(match, list(response.context["items"]))

    def test_search_excludes_deleted_items(self):
        item = self._create(item_type=VaultItem.ItemType.TEXT, content="hidden secret plan")
        item.soft_delete()

        response = self.client.get(reverse("vault:search"), {"q": "secret"})
        self.assertEqual(len(response.context["items"]), 0)

    def test_search_only_returns_the_requesting_users_items(self):
        self._create(
            owner=self.other, item_type=VaultItem.ItemType.TEXT, content="topsecret plan"
        )
        response = self.client.get(reverse("vault:search"), {"q": "topsecret"})
        self.assertEqual(len(response.context["items"]), 0)

    def test_search_ranks_stronger_matches_first(self):
        strong = self._create(
            item_type=VaultItem.ItemType.TEXT, content="django django django deployment"
        )
        self._create(
            item_type=VaultItem.ItemType.TEXT, content="a single passing mention of django"
        )

        response = self.client.get(reverse("vault:search"), {"q": "django"})
        results = list(response.context["items"])
        self.assertEqual(results[0], strong)

    def test_blank_query_returns_no_results(self):
        self._create(item_type=VaultItem.ItemType.TEXT, content="anything")
        response = self.client.get(reverse("vault:search"), {"q": ""})
        self.assertEqual(list(response.context["items"]), [])
