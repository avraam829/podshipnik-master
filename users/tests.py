from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=["testserver"])
class UserFlowTests(TestCase):
    def test_registration_rejects_duplicate_email_and_keeps_safe_redirects(self):
        User = get_user_model()
        User.objects.create_user(username="existing", email="same@example.com", password="test-only-pass")
        response = self.client.post("/users/register/?next=https://example.invalid/", {
            "username": "new-user", "email": "same@example.com",
            "password1": "another-test-pass", "password2": "another-test-pass",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Этот email уже используется.")

        response = self.client.post("/users/register/?next=/cart/checkout/", {
            "username": "new-user", "email": "new@example.com",
            "password1": "another-test-pass", "password2": "another-test-pass",
        })
        self.assertRedirects(response, "/cart/checkout/", fetch_redirect_response=False)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_shows_generic_error_for_wrong_password(self):
        User = get_user_model()
        User.objects.create_user(username="buyer", email="buyer@example.com", password="test-only-pass")
        response = self.client.post("/users/login/", {"username": "buyer", "password": "wrong-password"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Пожалуйста, введите правильные имя пользователя и пароль")
