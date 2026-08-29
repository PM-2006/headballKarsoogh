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

    def test_staff_bots_are_not_listed_as_public(self):
        from .models import SavedStrategy
        staff = User.objects.create_user(
            username="staffer", password="pass123456user", is_staff=True
        )
        staff_bot = SavedStrategy.objects.create(
            user=staff,
            name="Staff Practice Bot",
            strategy_data=self.sample_strategy,
        )
        # Older saves forced is_public=True on staff bots; those rows
        # must still stay out of the public gallery.
        SavedStrategy.objects.filter(pk=staff_bot.pk).update(is_public=True)
        SavedStrategy.objects.create(
            user=self.admin,
            name="Official Boss Bot",
            strategy_data=self.sample_strategy,
        )

        self.client.login(username="student1", password="pass123456user")
        data = self.client.get(reverse("game:api_strategies")).json()
        public_names = {b["name"] for b in data["public_strategies"]}
        self.assertNotIn("Staff Practice Bot", public_names)
        self.assertIn("Official Boss Bot", public_names)

        self.client.logout()
        self.client.login(username="staffer", password="pass123456user")
        staff_data = self.client.get(reverse("game:api_strategies")).json()
        my_names = {b["name"] for b in staff_data["my_strategies"]}
        staff_public = {b["name"] for b in staff_data["public_strategies"]}
        self.assertIn("Staff Practice Bot", my_names)
        self.assertNotIn("Staff Practice Bot", staff_public)

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






class SingleSessionTests(TestCase):
    """Only the most recent login for a user stays valid."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.password = "pass123456user"
        self.user = User.objects.create_user(username="oneuser", password=self.password)

    def test_second_login_kills_the_first_session(self):
        from django.test import Client
        from .models import UserSession

        first = Client()
        first.login(username="oneuser", password=self.password)
        first_key = first.session.session_key
        self.assertEqual(first.get(reverse("game:index")).status_code, 200)

        second = Client()
        second.login(username="oneuser", password=self.password)
        second_key = second.session.session_key
        self.assertNotEqual(first_key, second_key)

        # The first browser is bounced to the login page on its next request.
        self.assertEqual(first.get(reverse("game:index")).status_code, 302)
        self.assertEqual(second.get(reverse("game:index")).status_code, 200)

        mapping = UserSession.objects.get(user=self.user)
        self.assertEqual(mapping.session_id, second_key)
        self.assertEqual(UserSession.objects.filter(user=self.user).count(), 1)

    def test_other_users_sessions_are_untouched(self):
        from django.test import Client

        other = User.objects.create_user(username="otheruser", password=self.password)
        other_client = Client()
        other_client.login(username="otheruser", password=self.password)

        mine = Client()
        mine.login(username="oneuser", password=self.password)

        self.assertEqual(other_client.get(reverse("game:index")).status_code, 200)
        self.assertEqual(int(other_client.session["_auth_user_id"]), other.pk)

    def test_logout_clears_the_mapping(self):
        from django.test import Client
        from .models import UserSession

        client = Client()
        client.login(username="oneuser", password=self.password)
        self.assertTrue(UserSession.objects.filter(user=self.user).exists())

        client.logout()
        self.assertFalse(UserSession.objects.filter(user=self.user).exists())

    def test_staff_may_hold_several_sessions(self):
        from django.test import Client
        from .models import UserSession

        staff = User.objects.create_user(
            username="staffuser", password=self.password, is_staff=True
        )

        first = Client()
        first.login(username="staffuser", password=self.password)
        second = Client()
        second.login(username="staffuser", password=self.password)

        # Neither admin session is kicked, but both are still tracked.
        self.assertEqual(first.get(reverse("game:index")).status_code, 200)
        self.assertEqual(second.get(reverse("game:index")).status_code, 200)
        self.assertEqual(UserSession.objects.filter(user=staff).count(), 2)

    def test_demoting_staff_makes_their_old_sessions_reachable(self):
        """Staff sessions are tracked, so losing the flag brings them under the rule."""
        from django.test import Client
        from .models import UserSession

        user = User.objects.create_user(
            username="demoted", password=self.password, is_staff=True
        )
        stale = Client()
        stale.login(username="demoted", password=self.password)

        user.is_staff = False
        user.save(update_fields=["is_staff"])

        fresh = Client()
        fresh.login(username="demoted", password=self.password)

        # The admin-era session is now gone, and only the new one is left mapped.
        self.assertEqual(stale.get(reverse("game:index")).status_code, 302)
        self.assertEqual(fresh.get(reverse("game:index")).status_code, 200)
        self.assertEqual(UserSession.objects.filter(user=user).count(), 1)

class SessionLimitTests(TestCase):
    """The admin-configurable ceiling on concurrent sessions per user."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.password = "pass123456user"
        self.user = User.objects.create_user(username="player", password=self.password)
        self.admin = User.objects.create_superuser("boss", password="pw12345678")

    def _login(self):
        from django.test import Client

        client = Client()
        client.login(username="player", password=self.password)
        return client

    def _set_limit(self, value):
        from .gameconfig import set_session_limit

        return set_session_limit(value, user=self.admin)

    def test_default_limit_is_one(self):
        from .gameconfig import get_session_limit

        self.assertEqual(get_session_limit(), 1)

    def test_limit_of_three_keeps_three_sessions(self):
        from .models import UserSession

        self._set_limit(3)
        clients = [self._login() for _ in range(3)]

        for client in clients:
            self.assertEqual(client.get(reverse("game:index")).status_code, 200)
        self.assertEqual(UserSession.objects.filter(user=self.user).count(), 3)

    def test_oldest_session_is_evicted_past_the_limit(self):
        from .models import UserSession

        self._set_limit(2)
        oldest, middle = self._login(), self._login()
        newest = self._login()

        self.assertEqual(oldest.get(reverse("game:index")).status_code, 302)
        self.assertEqual(middle.get(reverse("game:index")).status_code, 200)
        self.assertEqual(newest.get(reverse("game:index")).status_code, 200)
        self.assertEqual(UserSession.objects.filter(user=self.user).count(), 2)

    def test_lowering_the_limit_is_enforced_on_the_next_login(self):
        from .models import UserSession

        self._set_limit(3)
        first, second = self._login(), self._login()
        self.assertEqual(UserSession.objects.filter(user=self.user).count(), 2)

        # Nobody is kicked at the moment the limit drops...
        self._set_limit(1)
        self.assertEqual(first.get(reverse("game:index")).status_code, 200)
        self.assertEqual(second.get(reverse("game:index")).status_code, 200)

        # ...but the next login prunes back down to the new ceiling.
        third = self._login()
        self.assertEqual(first.get(reverse("game:index")).status_code, 302)
        self.assertEqual(second.get(reverse("game:index")).status_code, 302)
        self.assertEqual(third.get(reverse("game:index")).status_code, 200)
        self.assertEqual(UserSession.objects.filter(user=self.user).count(), 1)

    def test_staff_stay_exempt_from_the_limit(self):
        from django.test import Client
        from .models import UserSession

        self._set_limit(1)
        staff = User.objects.create_user(
            username="staffuser", password=self.password, is_staff=True
        )
        clients = []
        for _ in range(3):
            client = Client()
            client.login(username="staffuser", password=self.password)
            clients.append(client)

        for client in clients:
            self.assertEqual(client.get(reverse("game:index")).status_code, 200)
        self.assertEqual(UserSession.objects.filter(user=staff).count(), 3)

    def test_other_users_are_untouched_by_a_prune(self):
        from django.test import Client

        self._set_limit(1)
        other = User.objects.create_user(username="bystander", password=self.password)
        other_client = Client()
        other_client.login(username="bystander", password=self.password)

        self._login()
        self._login()

        self.assertEqual(other_client.get(reverse("game:index")).status_code, 200)
        self.assertEqual(int(other_client.session["_auth_user_id"]), other.pk)

    def test_limit_is_clamped_to_the_allowed_range(self):
        from .gameconfig import MAX_SESSION_LIMIT

        self.assertEqual(self._set_limit(0), 1)
        self.assertEqual(self._set_limit(-5), 1)
        self.assertEqual(self._set_limit(9999), MAX_SESSION_LIMIT)
        self.assertEqual(self._set_limit("junk"), 1)

    def test_endpoint_is_superuser_only(self):
        from .gameconfig import get_session_limit

        self.client.login(username="player", password=self.password)
        self.assertEqual(self.client.get("/api/session-limit/").status_code, 403)
        resp = self.client.post(
            "/api/session-limit/",
            data=json.dumps({"limit": 5}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(get_session_limit(), 1)

    def test_superuser_reads_and_writes_the_limit(self):
        from .gameconfig import get_session_limit

        self.client.login(username="boss", password="pw12345678")
        read = self.client.get("/api/session-limit/")
        self.assertEqual(read.status_code, 200)
        self.assertEqual(json.loads(read.content)["limit"], 1)

        write = self.client.post(
            "/api/session-limit/",
            data=json.dumps({"limit": 4}),
            content_type="application/json",
        )
        self.assertEqual(write.status_code, 200)
        self.assertEqual(json.loads(write.content)["limit"], 4)
        self.assertEqual(get_session_limit(), 4)

    def test_missing_limit_is_rejected(self):
        self.client.login(username="boss", password="pw12345678")
        resp = self.client.post(
            "/api/session-limit/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


class GameActivationTests(TestCase):
    """The admin kill switch that closes the whole site to non-admins."""

    def setUp(self):
        from django.core.cache import cache

        # The flag is cached outside the database, so it does not get rolled
        # back with the test transaction. Without this the suite is
        # order-dependent: a test that closes the game leaks that state.
        cache.clear()
        User = get_user_model()
        self.student = User.objects.create_user("student", password="pw12345678")
        self.admin = User.objects.create_superuser("boss", password="pw12345678")

    def _set_enabled(self, value):
        from .gameconfig import set_game_enabled

        set_game_enabled(value, user=self.admin)

    def test_enabled_by_default(self):
        from .gameconfig import is_game_enabled

        self.assertTrue(is_game_enabled())

    def test_student_locked_out_when_disabled(self):
        self._set_enabled(False)
        self.client.login(username="student", password="pw12345678")

        api = self.client.get("/api/vocabulary/")
        self.assertEqual(api.status_code, 403)
        self.assertIn("application/json", api.headers["Content-Type"])
        self.assertIn("error", json.loads(api.content))

        page = self.client.get("/")
        self.assertEqual(page.status_code, 403)
        self.assertIn(b"text/html", page.headers["Content-Type"].encode())

    def test_admin_bypasses_the_lock(self):
        self._set_enabled(False)
        self.client.login(username="boss", password="pw12345678")
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/api/vocabulary/").status_code, 200)

    def test_login_and_healthz_stay_reachable_when_disabled(self):
        # Locking these would strand the admin outside and make the container
        # healthcheck fail the moment the game is switched off.
        self._set_enabled(False)
        self.assertEqual(self.client.get("/healthz/").status_code, 200)
        self.assertEqual(self.client.get("/accounts/login/").status_code, 200)

    def test_students_work_again_once_re_enabled(self):
        self._set_enabled(False)
        self.client.login(username="student", password="pw12345678")
        self.assertEqual(self.client.get("/api/vocabulary/").status_code, 403)
        self._set_enabled(True)
        self.assertEqual(self.client.get("/api/vocabulary/").status_code, 200)

    def test_toggle_endpoint_is_superuser_only(self):
        self.client.login(username="student", password="pw12345678")
        resp = self.client.post(
            "/api/game-active/",
            data=json.dumps({"active": False}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

        from .gameconfig import is_game_enabled

        self.assertTrue(is_game_enabled(), "a student must not be able to close the game")

    def test_superuser_can_toggle_through_the_api(self):
        from .gameconfig import is_game_enabled

        self.client.login(username="boss", password="pw12345678")
        off = self.client.post(
            "/api/game-active/",
            data=json.dumps({"active": False}),
            content_type="application/json",
        )
        self.assertEqual(off.status_code, 200)
        self.assertFalse(json.loads(off.content)["active"])
        self.assertFalse(is_game_enabled())

        on = self.client.post(
            "/api/game-active/",
            data=json.dumps({"active": True}),
            content_type="application/json",
        )
        self.assertEqual(on.status_code, 200)
        self.assertTrue(json.loads(on.content)["active"])
        self.assertTrue(is_game_enabled())
