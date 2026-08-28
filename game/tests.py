import json
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


class ConfigTests(TestCase):
    def test_vocabulary_includes_config(self):
        user = User.objects.create_user(username="cfguser", password="securepassword123")
        self.client.login(username="cfguser", password="securepassword123")
        response = self.client.get(reverse("game:api_vocabulary"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("config", data)
        self.assertEqual(data["config"]["width"], 1280.0)
        self.assertEqual(data["config"]["ball_radius"], 22.0)

    def test_env_variable_overrides(self):
        import os
        from .engine import get_game_config
        os.environ["GAME_PLAYGROUND_WIDTH"] = "1920.0"
        os.environ["GAME_GRAVITY"] = "2200.0"
        os.environ["GAME_BALL_RADIUS"] = "30.0"
        os.environ["GAME_FLOOR_FRICTION"] = "0.95"
        try:
            cfg = get_game_config()
            self.assertEqual(cfg.width, 1920.0)
            self.assertEqual(cfg.gravity, 2200.0)
            self.assertEqual(cfg.ball_radius, 30.0)
            self.assertEqual(cfg.floor_friction, 0.95)
        finally:
            del os.environ["GAME_PLAYGROUND_WIDTH"]
            del os.environ["GAME_GRAVITY"]
            del os.environ["GAME_BALL_RADIUS"]
            del os.environ["GAME_FLOOR_FRICTION"]


class AICompilerSchemaTests(TestCase):
    def test_condition_schema_normalization(self):
        from .prompts.strategy_compiler import ConditionSchema
        # Legacy sensor / value input
        cond1 = ConditionSchema.model_validate({
            "sensor": "can_kick",
            "operator": "==",
            "value": True
        })
        self.assertEqual(cond1.left, "can_kick")
        self.assertEqual(cond1.rightType, "value")
        self.assertEqual(cond1.right, True)

        # Sensor comparison
        cond2 = ConditionSchema.model_validate({
            "left": "opponent_distance_to_ball",
            "operator": "<",
            "right": "distance_to_ball"
        })
        self.assertEqual(cond2.rightType, "sensor")
        self.assertEqual(cond2.right, "distance_to_ball")

    def test_strategy_compiler_response_pydantic_validation(self):
        from .prompts.strategy_compiler import StrategyCompilerResponse
        # Valid response validation
        data = {
            "valid": True,
            "feedback": ["خوب است"],
            "strategy": {
                "label": "My Bot",
                "rules": [
                    {
                        "priority": 1,
                        "conditions": [
                            {"left": "can_kick", "operator": "==", "rightType": "value", "right": True}
                        ],
                        "action": "KICK_LOW"
                    }
                ],
                "default_action": "IDLE"
            }
        }
        res = StrategyCompilerResponse.model_validate(data)
        self.assertTrue(res.valid)
        self.assertEqual(len(res.strategy.rules), 1)
        self.assertEqual(res.strategy.rules[0].action, "KICK_LOW")

    def test_feedback_string_normalization(self):
        from .prompts.strategy_compiler import StrategyCompilerResponse
        # If AI sends feedback as a plain string instead of array
        res = StrategyCompilerResponse.model_validate({
            "valid": False,
            "feedback": "استراتژی مبهم است.",
            "strategy": None
        })
        self.assertFalse(res.valid)
        self.assertEqual(res.feedback, ["استراتژی مبهم است."])

    def test_empty_text_raises_validation_error(self):
        from .services.llm import compile_persian_strategy
        with self.assertRaises(StrategyValidationError):
            compile_persian_strategy("   ")


class SavedStrategyTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="student1", password="pass123456user")
        self.user2 = User.objects.create_user(username="student2", password="pass123456user")
        self.admin = User.objects.create_superuser(username="superadmin", password="admin123456pass")
        self.sample_strategy = {
            "label": "Eagle Bot",
            "rules": [
                {
                    "priority": 1,
                    "conditions": [{"left": "can_kick", "operator": "==", "rightType": "value", "right": True}],
                    "action": "KICK_LOW",
                }
            ],
            "default_action": "MOVE_TO_BALL",
        }

    def test_create_and_list_strategy(self):
        self.client.login(username="student1", password="pass123456user")
        response = self.client.post(
            reverse("game:api_strategies"),
            data=json.dumps({"name": "عقاب زاگرس", "strategy": self.sample_strategy, "ai_prompt": "تست پرامپت"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["strategy"]["name"], "عقاب زاگرس")

        # List strategies
        list_res = self.client.get(reverse("game:api_strategies"))
        self.assertEqual(list_res.status_code, 200)
        list_data = list_res.json()
        self.assertEqual(len(list_data["my_strategies"]), 1)
        self.assertEqual(list_data["my_strategies"][0]["name"], "عقاب زاگرس")

    def test_admin_strategy_visible_to_all(self):
        from .models import SavedStrategy
        # Admin creates public strategy
        SavedStrategy.objects.create(
            user=self.admin,
            name="Official Boss Bot",
            strategy_data=self.sample_strategy,
            is_public=True,
        )

        # Student 1 lists strategies
        self.client.login(username="student1", password="pass123456user")
        res = self.client.get(reverse("game:api_strategies"))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data["public_strategies"]), 1)
        self.assertEqual(data["public_strategies"][0]["name"], "Official Boss Bot")

    def test_permissions_user_cannot_edit_or_delete_others_strategy(self):
        from .models import SavedStrategy
        strat = SavedStrategy.objects.create(
            user=self.user1,
            name="Private Bot",
            strategy_data=self.sample_strategy,
        )

        # User 2 tries to update User 1's strategy
        self.client.login(username="student2", password="pass123456user")
        res_update = self.client.post(
            reverse("game:api_strategy_detail", kwargs={"pk": strat.pk}),
            data=json.dumps({"name": "Hacked"}),
            content_type="application/json",
        )
        self.assertEqual(res_update.status_code, 403)

        # User 2 tries to delete User 1's strategy
        res_delete = self.client.delete(reverse("game:api_strategy_detail", kwargs={"pk": strat.pk}))
        self.assertEqual(res_delete.status_code, 403)

    def test_simulation_with_saved_strategy_id(self):
        from .models import SavedStrategy
        strat = SavedStrategy.objects.create(
            user=self.user1,
            name="User1 Bot",
            strategy_data=self.sample_strategy,
        )

        self.client.login(username="student1", password="pass123456user")
        sim_res = self.client.post(
            reverse("game:api_simulate"),
            data=json.dumps({
                "blue": {"strategy_id": strat.id},
                "red": {"preset": "adaptive"},
                "seed": 1,
            }),
            content_type="application/json",
        )
        self.assertEqual(sim_res.status_code, 200)
        self.assertIn("frames", sim_res.json())

    def _create(self, name):
        return self.client.post(
            reverse("game:api_strategies"),
            data=json.dumps({"name": name, "strategy": self.sample_strategy}),
            content_type="application/json",
        )

    def test_bot_name_unique_across_users_but_reusable_by_owner(self):
        # student1 registers "Falcon"
        self.client.login(username="student1", password="pass123456user")
        self.assertEqual(self._create("Falcon").status_code, 201)
        # same user may reuse their own name as many times as they like
        self.assertEqual(self._create("Falcon").status_code, 201)
        self.assertEqual(self._create("  Falcon  ").status_code, 201)

        # a different user cannot take that name (case-insensitive)
        self.client.logout()
        self.client.login(username="student2", password="pass123456user")
        res = self._create("falcon")
        self.assertEqual(res.status_code, 409)
        self.assertIn("error", res.json())
        # but a fresh name works
        self.assertEqual(self._create("Hawk").status_code, 201)

    def test_rename_cannot_steal_another_users_name(self):
        from .models import SavedStrategy
        self.client.login(username="student1", password="pass123456user")
        self._create("Falcon")
        mine = SavedStrategy.objects.create(
            user=self.user2, name="Sparrow", strategy_data=self.sample_strategy,
        )
        self.client.logout()
        self.client.login(username="student2", password="pass123456user")
        res = self.client.post(
            reverse("game:api_strategy_detail", kwargs={"pk": mine.pk}),
            data=json.dumps({"name": "Falcon"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 409)

    def test_public_bot_brain_is_viewable_read_only(self):
        from .models import SavedStrategy
        boss = SavedStrategy.objects.create(
            user=self.admin, name="Boss Bot",
            strategy_data=self.sample_strategy, ai_prompt="secret sauce",
            is_public=True,
        )
        self.client.login(username="student1", password="pass123456user")

        # A student may READ an official bot's brain (for the view-only popup)...
        detail = self.client.get(
            reverse("game:api_strategy_detail", kwargs={"pk": boss.pk})
        ).json()["strategy"]
        self.assertFalse(detail["is_owner"])
        self.assertEqual(detail["rules_count"], 1)
        self.assertEqual(detail["strategy"]["rules"][0]["action"], "KICK_LOW")

        # ...but may NOT edit it.
        res = self.client.post(
            reverse("game:api_strategy_detail", kwargs={"pk": boss.pk}),
            data=json.dumps({"name": "Hijacked"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)

    def test_admin_can_line_up_every_users_bot(self):
        from .models import SavedStrategy
        SavedStrategy.objects.create(
            user=self.user1, name="Student1 Bot", strategy_data=self.sample_strategy,
        )
        SavedStrategy.objects.create(
            user=self.user2, name="Student2 Bot", strategy_data=self.sample_strategy,
        )
        # Admin: gets is_admin + all_strategies covering every user's bot.
        self.client.login(username="superadmin", password="admin123456pass")
        data = self.client.get(reverse("game:api_strategies")).json()
        self.assertTrue(data["is_admin"])
        names = {b["name"] for b in data["all_strategies"]}
        self.assertIn("Student1 Bot", names)
        self.assertIn("Student2 Bot", names)

        # Student: no admin pool, and is_admin is false.
        self.client.logout()
        self.client.login(username="student1", password="pass123456user")
        sdata = self.client.get(reverse("game:api_strategies")).json()
        self.assertFalse(sdata["is_admin"])
        self.assertNotIn("all_strategies", sdata)

    def test_owner_still_sees_own_brain(self):
        from .models import SavedStrategy
        strat = SavedStrategy.objects.create(
            user=self.user1, name="Mine", strategy_data=self.sample_strategy,
        )
        self.client.login(username="student1", password="pass123456user")
        detail = self.client.get(
            reverse("game:api_strategy_detail", kwargs={"pk": strat.pk})
        ).json()["strategy"]
        self.assertIn("strategy", detail)
        self.assertEqual(detail["strategy"]["rules"][0]["action"], "KICK_LOW")


class KitTests(TestCase):
    def test_sanitize_kit_enforces_distinct_hues(self):
        from .kits import sanitize_kit, colors_too_close, PALETTE
        # three near-hue oranges collapse to three hue-distinct colours
        result = sanitize_kit(["#F58231", "#FF8C00", "#FFB300"])
        self.assertEqual(len(result), 3)
        for c in result:
            self.assertIn(c, PALETTE)
        for i in range(3):
            for j in range(i + 1, 3):
                self.assertFalse(colors_too_close(result[i], result[j]))

    def test_sanitize_kit_default_survives(self):
        from .kits import sanitize_kit, DEFAULT_KIT
        self.assertEqual(sanitize_kit(DEFAULT_KIT), DEFAULT_KIT)

    def test_api_kit_rejects_similar_colors(self):
        user = User.objects.create_user(username="kituser", password="pass123456user")
        self.client.login(username="kituser", password="pass123456user")
        res = self.client.post(
            reverse("game:api_kit"),
            data=json.dumps({"colors": ["#F58231", "#FF8C00", "#FFB300"]}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        from .kits import colors_too_close
        colors = res.json()["colors"]
        for i in range(3):
            for j in range(i + 1, 3):
                self.assertFalse(colors_too_close(colors[i], colors[j]))




