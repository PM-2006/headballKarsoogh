import json
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .engine import batch_matches, get_game_config, simulate_match
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
        self.assertEqual(result["duration"], get_game_config().match_time)
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
        config = get_game_config()
        self.assertEqual(data["config"]["width"], config.width)
        self.assertEqual(data["config"]["ball_radius"], config.ball_radius)

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


class UniqueBotNameTests(TestCase):
    """Bot names identify a bot everywhere in the UI, so they must be unique."""

    def setUp(self):
        self.user1 = User.objects.create_user(username="namer1", password="pass123456user")
        self.user2 = User.objects.create_user(username="namer2", password="pass123456user")
        self.strategy = {
            "label": "Bot",
            "rules": [
                {
                    "priority": 1,
                    "conditions": [{"left": "can_kick", "operator": "==", "rightType": "value", "right": True}],
                    "action": "KICK_LOW",
                }
            ],
            "default_action": "IDLE",
        }

    def _create(self, name):
        return self.client.post(
            reverse("game:api_strategies"),
            data=json.dumps({"name": name, "strategy": self.strategy}),
            content_type="application/json",
        )

    def test_same_user_cannot_save_one_name_twice(self):
        self.client.login(username="namer1", password="pass123456user")
        self.assertEqual(self._create("شاهین").status_code, 201)
        response = self._create("شاهین")
        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertTrue(body["name_taken"])
        self.assertEqual(body["suggestion"], "شاهین (2)")

    def test_other_user_cannot_reuse_a_taken_name(self):
        self.client.login(username="namer1", password="pass123456user")
        self.assertEqual(self._create("Falcon").status_code, 201)
        self.client.login(username="namer2", password="pass123456user")
        # Case and padding must not open a loophole.
        self.assertEqual(self._create("  falcon  ").status_code, 409)

    def test_rename_to_a_taken_name_is_rejected_but_self_rename_is_fine(self):
        from .models import SavedStrategy

        self.client.login(username="namer1", password="pass123456user")
        self._create("اول")
        second = self._create("دوم").json()["strategy"]
        clash = self.client.post(
            reverse("game:api_strategy_detail", args=[second["id"]]),
            data=json.dumps({"name": "اول"}),
            content_type="application/json",
        )
        self.assertEqual(clash.status_code, 409)

        same = self.client.post(
            reverse("game:api_strategy_detail", args=[second["id"]]),
            data=json.dumps({"name": "دوم"}),
            content_type="application/json",
        )
        self.assertEqual(same.status_code, 200)
        self.assertEqual(SavedStrategy.objects.get(pk=second["id"]).name, "دوم")

    def test_model_level_uniqueness(self):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from .models import SavedStrategy

        SavedStrategy.objects.create(user=self.user1, name="Unique", strategy_data=self.strategy)
        with self.assertRaises(DjangoValidationError):
            SavedStrategy.objects.create(user=self.user2, name="unique", strategy_data=self.strategy)


class BrainVisibilityTests(TestCase):
    """Anyone may read the rules of a bot that is listed for them."""

    def setUp(self):
        self.student = User.objects.create_user(username="viewer", password="pass123456user")
        self.admin = User.objects.create_superuser(username="viewadmin", password="admin123456pass")
        self.strategy = {
            "label": "Boss",
            "rules": [
                {
                    "priority": 1,
                    "conditions": [{"left": "can_kick", "operator": "==", "rightType": "value", "right": True}],
                    "action": "KICK_HIGH",
                }
            ],
            "default_action": "IDLE",
        }

    def test_student_can_read_an_official_bot_brain(self):
        from .models import SavedStrategy

        bot = SavedStrategy.objects.create(user=self.admin, name="Official Brain", strategy_data=self.strategy)
        self.client.login(username="viewer", password="pass123456user")

        listed = self.client.get(reverse("game:api_strategies")).json()
        public = listed["public_strategies"][0]
        self.assertEqual(public["strategy"]["rules"][0]["action"], "KICK_HIGH")
        self.assertFalse(public["is_owner"])

        detail = self.client.get(reverse("game:api_strategy_detail", args=[bot.id]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["strategy"]["strategy"]["rules"][0]["action"], "KICK_HIGH")


class OwnGoalTests(TestCase):
    """A bot must never drive the ball into the goal it is defending."""

    def test_touch_in_own_box_is_turned_into_a_clearance(self):
        from .engine import _own_goal_guard, get_game_config

        config = get_game_config()
        ball_x = config.goal_depth + 60.0          # deep inside team 0's own box

        # Team 0 defends the left goal: a leftwards push must be turned around.
        dvx, dvy = _own_goal_guard(0, ball_x, -400.0, 0.0, config)
        self.assertGreater(dvx, 0.0)
        self.assertLess(dvy, 0.0)                  # and lifted away from the line

        # A push up-field is left untouched.
        self.assertEqual(_own_goal_guard(0, ball_x, 400.0, 0.0, config), (400.0, 0.0))

        # Team 1 defends the right goal, so the mirror case must hold there.
        far_x = config.width - config.goal_depth - 60.0
        dvx, _unused = _own_goal_guard(1, far_x, 400.0, 0.0, config)
        self.assertLess(dvx, 0.0)

        # In the opponent's half nothing is changed for either team: a backwards
        # touch there is a normal pass, not a threat to your own net.
        self.assertEqual(
            _own_goal_guard(0, config.width - 300.0, -400.0, 0.0, config), (-400.0, 0.0)
        )
        self.assertEqual(_own_goal_guard(1, 300.0, 400.0, 0.0, config), (400.0, 0.0))

    def test_defender_does_not_walk_through_the_ball_towards_its_own_goal(self):
        from .engine import _resolve_intent, get_game_config

        config = get_game_config()
        ball_x = config.goal_depth + 250.0
        # Team 0 defends the left goal. Standing right on top of a ball that is
        # between it and that goal, it must back off (+1) instead of shoving the
        # ball over its own line (-1).
        state = {"my_x": ball_x + 10.0, "ball_x": ball_x}
        self.assertEqual(_resolve_intent("MOVE_TO_GOAL", state, 0, config).move_dir, 1)

        # Coming from up-field it still runs home, but only as far as the ball.
        stop_x = ball_x + config.ball_radius + config.player_width / 2.0 + 6.0
        self.assertEqual(
            _resolve_intent("MOVE_TO_GOAL", {"my_x": stop_x, "ball_x": ball_x}, 0, config).move_dir,
            0,
        )
        self.assertEqual(
            _resolve_intent("MOVE_TO_GOAL", {"my_x": stop_x + 300.0, "ball_x": ball_x}, 0, config).move_dir,
            -1,
        )

        # With the ball at the other end it runs home normally.
        state = {"my_x": config.width / 2, "ball_x": config.width - 300.0}
        self.assertEqual(_resolve_intent("MOVE_TO_GOAL", state, 0, config).move_dir, -1)

    def test_preset_matches_do_not_flood_with_own_goals(self):
        """A bot must almost never turn the ball towards its own goal and score.

        Counted strictly: the ball was not already flying at that goal, the
        conceding team's own touch turned it around, and the goal followed.
        """
        from . import engine
        from .engine import Ball, _attack_direction, _best_player_ball_contact

        own_goals = total = 0
        turned_by = {"team": None}

        def touch_tracker(world, config, run):
            before = world.ball.vx
            touching = [
                index
                for index, player in enumerate(world.players)
                if _best_player_ball_contact(
                    player, Ball(world.ball.x, world.ball.y, world.ball.vx, world.ball.vy), config
                )
                is not None
            ]
            result = run()
            after = world.ball.vx
            for index in touching:
                attack = _attack_direction(index)
                if before * attack > -60.0 and after * attack < -60.0:
                    turned_by["team"] = index
                elif after * attack > 60.0 and turned_by["team"] == index:
                    turned_by["team"] = None
            return result

        original_contacts = engine._resolve_player_ball_contacts
        original_kicks = engine._apply_kicks
        original_detect = engine._detect_goal

        def contacts(world, config):
            return touch_tracker(world, config, lambda: original_contacts(world, config))

        def kicks(world, intents, config):
            return touch_tracker(world, config, lambda: original_kicks(world, intents, config))

        def detect(world, previous_x, config):
            nonlocal own_goals, total
            scorer = original_detect(world, previous_x, config)
            if scorer is not None:
                total += 1
                if turned_by["team"] is not None and turned_by["team"] != scorer:
                    own_goals += 1
                turned_by["team"] = None
            return scorer

        engine._resolve_player_ball_contacts = contacts
        engine._apply_kicks = kicks
        engine._detect_goal = detect
        try:
            for blue, red in (("goalie", "adaptive"), ("defensive", "aggressive"), ("goalie", "counter")):
                for seed in (1, 2, 3):
                    turned_by["team"] = None
                    simulate_match(get_preset(blue), get_preset(red), seed=seed, record_frames=False)
        finally:
            engine._resolve_player_ball_contacts = original_contacts
            engine._apply_kicks = original_kicks
            engine._detect_goal = original_detect

        self.assertGreater(total, 0)
        self.assertLess(own_goals / total, 0.10)
