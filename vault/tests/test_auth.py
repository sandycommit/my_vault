from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class AuthTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="s3cret-pass!")

    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(reverse("vault:chat"))
        self.assertRedirects(
            response, f"{reverse('login')}?next={reverse('vault:chat')}"
        )

    def test_login_works(self):
        response = self.client.post(
            reverse("login"), {"username": "owner", "password": "s3cret-pass!"}
        )
        self.assertRedirects(response, reverse("vault:chat"))

    def test_login_fails_with_wrong_password(self):
        response = self.client.post(
            reverse("login"), {"username": "owner", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["user"].is_authenticated)

    def test_logout_works(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))

        response = self.client.get(reverse("vault:chat"))
        self.assertEqual(response.status_code, 302)
