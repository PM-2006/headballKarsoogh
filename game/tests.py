from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .engine import batch_matches, simulate_match
from .strategy import get_preset
from .validators import StrategyValidationError, validate_strategy

User = get_user_model()

class StrategyTests(TestCase):
    def test_preset_is_valid(self):
        validate_strategy(get_preset("adaptive"))

    def test_invalid_action_is_rejected(self):
        strategy = get_preset("aggressive")
        strategy["rules"][0]["action"] = "SUPER_KICK"
        with self.assertRaises(StrategyValidationError):
            validate_strategy(strategy)

class EngineTests(TestCase):
    def test_match_finishes(self):
        result = simulate_match(get_preset("aggressive"), get_preset("defensive"), seed=42, record_frames=False)
        self.assertEqual(result["duration"], 60.0)
        self.assertEqual(len(result["score"]), 2)
        self.assertTrue(all(goal >= 0 for goal in result["score"]))

    def test_batch_count(self):
        result = batch_matches(get_preset("predictive"), get_preset("adaptive"), matches=8, seed=5)
        self.assertEqual(result["blue_wins"] + result["red_wins"] + result["draws"], 8)

class AuthAndSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testplayer", password="securepassword123")

    def test_unauthenticated_access_redirects_to_login(self):
        response = self.client.get(reverse("game:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_login_success(self):
        response = self.client.post(
            reverse("login"),
            data={"username": "testplayer", "password": "securepassword123"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "testplayer")

    def test_login_failure(self):
        response = self.client.post(
            reverse("login"),
            data={"username": "testplayer", "password": "wrongpassword"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "نام کاربری یا گذرواژه وارد شده نادرست است")

    def test_logout(self):
        self.client.login(username="testplayer", password="securepassword123")
        response = self.client.post(reverse("logout"), follow=True)
        self.assertEqual(response.status_code, 200)
        # Should now be redirected to login
        index_response = self.client.get(reverse("game:index"))
        self.assertEqual(index_response.status_code, 302)

class ApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="apiuser", password="securepassword123")
        self.client.login(username="apiuser", password="securepassword123")

    def test_vocabulary_endpoint(self):
        response = self.client.get(reverse("game:api_vocabulary"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("sensors", response.json())

    def test_simulate_endpoint(self):
        response = self.client.post(
            reverse("game:api_simulate"),
            data={"blue": {"preset": "aggressive"}, "red": {"preset": "adaptive"}, "seed": 4},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("frames", response.json())

    def test_batch_endpoint(self):
        response = self.client.post(
            reverse("game:api_batch"),
            data={"blue": {"preset": "aggressive"}, "red": {"preset": "adaptive"}, "seed": 4, "matches": 5},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["matches"], 5)

