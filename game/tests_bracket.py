"""Tests for the knockout bracket -- the derivation and the cascade above all."""
from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .bracket import (
    BracketError,
    apply_result,
    apply_team,
    champion,
    participants,
    rounds_for,
    third_participants,
    third_place,
)
from .models import KnockoutBracket

User = get_user_model()


def draw(size):
    return [f"T{i}" for i in range(size)]


class DerivationTests(TestCase):
    def test_rounds(self):
        self.assertEqual([rounds_for(n) for n in (2, 4, 8, 16, 32, 64)], [1, 2, 3, 4, 5, 6])

    def test_first_round_participants_come_from_the_draw(self):
        teams = draw(8)
        self.assertEqual(participants(8, teams, {}, 0, 3), ("T6", "T7"))

    def test_empty_slot_is_unknown(self):
        teams = draw(4)
        teams[1] = ""
        self.assertEqual(participants(4, teams, {}, 0, 0), ("T0", None))

    def test_later_rounds_follow_winners(self):
        teams, results = draw(8), {}
        apply_result(8, teams, results, "0-0", 1, [0, 2])  # T1 beats T0
        apply_result(8, teams, results, "0-1", 0, None)    # T2 beats T3
        self.assertEqual(participants(8, teams, results, 1, 0), ("T1", "T2"))
        self.assertEqual(participants(8, teams, results, 1, 1), (None, None))

    def test_champion_and_third_place(self):
        teams, results = draw(4), {}
        apply_result(4, teams, results, "0-0", 0, None)  # T0 beats T1
        apply_result(4, teams, results, "0-1", 1, None)  # T3 beats T2
        self.assertEqual(third_participants(4, teams, results), ("T1", "T2"))
        apply_result(4, teams, results, "1-0", 1, [1, 3])
        apply_result(4, teams, results, "third", 0, None)
        self.assertEqual(champion(4, teams, results), "T3")
        self.assertEqual(third_place(4, teams, results), "T1")


class CascadeTests(TestCase):
    def test_a_result_needs_both_sides_known(self):
        with self.assertRaises(BracketError):
            apply_result(8, draw(8), {}, "1-0", 0, None)

    def test_changing_a_winner_voids_the_path_to_the_final(self):
        teams, results = draw(8), {}
        for i in range(4):
            apply_result(8, teams, results, f"0-{i}", 0, None)
        apply_result(8, teams, results, "1-0", 0, None)
        apply_result(8, teams, results, "1-1", 0, None)
        apply_result(8, teams, results, "2-0", 0, None)
        self.assertEqual(champion(8, teams, results), "T0")

        apply_result(8, teams, results, "0-0", 1, None)  # T1 now beats T0
        self.assertNotIn("1-0", results)
        self.assertNotIn("2-0", results)
        self.assertIn("1-1", results, "the other half of the draw is untouched")
        self.assertIsNone(champion(8, teams, results))

    def test_same_winner_with_a_new_score_keeps_the_path(self):
        teams, results = draw(4), {}
        apply_result(4, teams, results, "0-0", 0, [1, 0])
        apply_result(4, teams, results, "0-1", 0, None)
        apply_result(4, teams, results, "1-0", 0, None)
        apply_result(4, teams, results, "0-0", 0, [3, 0])
        self.assertIn("1-0", results)

    def test_changing_a_semi_voids_the_third_place_match(self):
        teams, results = draw(4), {}
        apply_result(4, teams, results, "0-0", 0, None)
        apply_result(4, teams, results, "0-1", 0, None)
        apply_result(4, teams, results, "third", 0, None)
        apply_result(4, teams, results, "0-1", 1, None)
        self.assertNotIn("third", results)

    def test_emptying_a_slot_voids_its_decided_match(self):
        teams, results = draw(4), {}
        apply_result(4, teams, results, "0-0", 0, None)
        apply_result(4, teams, results, "0-1", 0, None)
        apply_result(4, teams, results, "1-0", 0, None)
        apply_team(4, teams, results, 0, "")
        self.assertNotIn("0-0", results)
        self.assertNotIn("1-0", results)

    def test_renaming_a_slot_flows_through(self):
        teams, results = draw(4), {}
        apply_result(4, teams, results, "0-0", 0, None)
        apply_team(4, teams, results, 0, "Eagles")
        self.assertEqual(participants(4, teams, results, 1, 0), ("Eagles", None))

    def test_scores_are_validated(self):
        teams = draw(2)
        with self.assertRaises(BracketError):
            apply_result(2, teams, {}, "0-0", 0, [1])
        with self.assertRaises(BracketError):
            apply_result(2, teams, {}, "0-0", 0, [-1, 0])
        with self.assertRaises(BracketError):
            apply_result(2, teams, {}, "0-0", 2, None)

    def test_third_place_needs_at_least_four_teams(self):
        with self.assertRaises(BracketError):
            apply_result(2, draw(2), {}, "third", 0, None)


class BracketApiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", is_staff=True)
        self.user = User.objects.create_user(username="user")
        self.url = reverse("game:api_bracket")

    def patch(self, **payload):
        response = self.client.patch(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        return response, json.loads(response.content)

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_unpublished_bracket_is_hidden_from_users(self):
        self.client.force_login(self.user)
        data = json.loads(self.client.get(self.url).content)
        self.assertFalse(data["published"])
        self.assertNotIn("teams", data)

    def test_admin_sees_an_unpublished_bracket_with_suggestions(self):
        self.client.force_login(self.admin)
        data = json.loads(self.client.get(self.url).content)
        self.assertTrue(data["can_edit"])
        self.assertEqual(len(data["teams"]), 16)
        self.assertIn("user", data["suggestions"])

    def test_users_cannot_edit(self):
        self.client.force_login(self.user)
        response, _ = self.patch(title="x")
        self.assertEqual(response.status_code, 403)

    def test_users_see_a_published_bracket_without_suggestions(self):
        self.client.force_login(self.admin)
        self.patch(published=True, teams={"0": "Lions"})
        self.client.force_login(self.user)
        data = json.loads(self.client.get(self.url).content)
        self.assertTrue(data["published"])
        self.assertEqual(data["teams"][0], "Lions")
        self.assertFalse(data["can_edit"])
        self.assertNotIn("suggestions", data)

    def test_full_edit_flow(self):
        self.client.force_login(self.admin)
        _, data = self.patch(size=4, teams={"0": "A", "1": "B", "2": "C", "3": "D"})
        self.assertEqual(data["size"], 4)
        _, data = self.patch(results={"0-0": {"winner": 0, "score": [2, 1]}, "0-1": {"winner": 1, "score": None}})
        self.assertEqual(data["third_participants"], ["B", "C"])
        _, data = self.patch(results={"1-0": {"winner": 1, "score": [0, 1]}})
        self.assertEqual(data["champion"], "D")
        self.assertEqual(data["updated_by"], "admin")

    def test_invalid_size_and_unknown_match_are_400(self):
        self.client.force_login(self.admin)
        response, _ = self.patch(size=12)
        self.assertEqual(response.status_code, 400)
        response, _ = self.patch(results={"9-9": {"winner": 0}})
        self.assertEqual(response.status_code, 400)
        response, _ = self.patch(results={"1-0": {"winner": 0}})
        self.assertEqual(response.status_code, 400, "both sides still unknown")

    def test_changing_size_clears_results_and_keeps_names(self):
        self.client.force_login(self.admin)
        self.patch(size=4, teams={"0": "A", "1": "B", "2": "C", "3": "D"})
        self.patch(results={"0-0": {"winner": 0}})
        _, data = self.patch(size=8)
        self.assertEqual(data["results"], {})
        self.assertEqual(data["teams"][:4], ["A", "B", "C", "D"])
        self.assertEqual(len(data["teams"]), 8)

    def test_rejected_patch_changes_nothing(self):
        self.client.force_login(self.admin)
        self.patch(size=4, teams={"0": "A", "1": "B"})
        response, _ = self.patch(teams={"2": "C"}, results={"1-0": {"winner": 0}})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(KnockoutBracket.load().teams[2], "")


class DivisionTests(TestCase):
    """The boys' and girls' draws are two rows that never touch each other."""

    def setUp(self):
        self.admin = User.objects.create_user(username="admin", is_staff=True)
        self.user = User.objects.create_user(username="user")
        self.url = reverse("game:api_bracket")

    def patch(self, division, **payload):
        response = self.client.patch(
            self.url + "?division=" + division,
            data=json.dumps(payload),
            content_type="application/json",
        )
        return response, json.loads(response.content)

    def get(self, division=None):
        url = self.url if division is None else self.url + "?division=" + division
        return json.loads(self.client.get(url).content)

    def test_each_division_has_its_own_bracket(self):
        self.client.force_login(self.admin)
        self.patch("boys", size=4, teams={"0": "A", "1": "B", "2": "C", "3": "D"})
        self.patch("girls", size=8, teams={"0": "X"})

        boys, girls = self.get("boys"), self.get("girls")
        self.assertEqual((boys["division"], boys["size"], boys["teams"][0]), ("boys", 4, "A"))
        self.assertEqual((girls["division"], girls["size"], girls["teams"][0]), ("girls", 8, "X"))
        self.assertEqual(KnockoutBracket.objects.count(), 2)

    def test_results_do_not_leak_between_divisions(self):
        self.client.force_login(self.admin)
        for division in ("boys", "girls"):
            self.patch(division, size=2, teams={"0": "A", "1": "B"})
        self.patch("boys", results={"0-0": {"winner": 0, "score": [3, 1]}})
        self.assertEqual(self.get("boys")["champion"], "A")
        self.assertIsNone(self.get("girls")["champion"])

    def test_publishing_one_division_does_not_publish_the_other(self):
        self.client.force_login(self.admin)
        self.patch("boys", published=True, teams={"0": "Lions"})
        self.client.force_login(self.user)
        self.assertTrue(self.get("boys")["published"])
        girls = self.get("girls")
        self.assertFalse(girls["published"])
        self.assertNotIn("teams", girls)

    def test_each_division_starts_with_its_own_title(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.get("boys")["title"], KnockoutBracket.DEFAULT_TITLES["boys"])
        self.assertEqual(self.get("girls")["title"], KnockoutBracket.DEFAULT_TITLES["girls"])

    def test_missing_division_means_the_boys_draw(self):
        self.client.force_login(self.admin)
        self.patch("boys", teams={"0": "A"})
        self.assertEqual(self.get()["division"], "boys")
        self.assertEqual(self.get()["teams"][0], "A")

    def test_unknown_division_is_400(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url + "?division=nope").status_code, 400)
        response, _ = self.patch("nope", title="x")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(KnockoutBracket.objects.filter(division="nope").count(), 0)

    def test_division_may_travel_in_the_body(self):
        self.client.force_login(self.admin)
        response = self.client.patch(
            self.url,
            data=json.dumps({"division": "girls", "teams": {"0": "Falcons"}}),
            content_type="application/json",
        )
        self.assertEqual(json.loads(response.content)["division"], "girls")
        self.assertEqual(KnockoutBracket.load("girls").teams[0], "Falcons")
        self.assertEqual(KnockoutBracket.load("boys").teams, [])

    def test_load_refuses_an_unknown_division(self):
        with self.assertRaises(ValueError):
            KnockoutBracket.load("teachers")
