"""Tests for the in-app inbox.

Weighted heavily towards the audience rules: everything else here is
recoverable, but a message that reaches the wrong people is not.
"""
from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .messaging import (
    EmptyAudienceError,
    audience_count,
    excerpt,
    recipients_for,
    send_message,
)
from .models import Message, Notification

User = get_user_model()


def make_user(username, **kwargs):
    # No password: every test signs in with force_login, and hashing one for
    # each of these would dominate the runtime of the whole module.
    return User.objects.create_user(username=username, **kwargs)


class AudienceRuleTests(TestCase):
    """Section 2 of the spec: who a message reaches, and who it must not."""

    def setUp(self):
        self.admin = make_user("admin", is_staff=True)
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.carol = make_user("carol")
        self.ghost = make_user("ghost", is_active=False)

    def _message(self, **kwargs):
        kwargs.setdefault("sender", self.admin)
        kwargs.setdefault("title", "اعلان")
        return Message.objects.create(**kwargs)

    def test_everyone_reaches_all_active_users_except_the_sender(self):
        message = self._message(to_everyone=True)
        names = set(recipients_for(message).values_list("username", flat=True))
        self.assertEqual(names, {"alice", "bob", "carol"})

    def test_everyone_skips_inactive_accounts(self):
        message = self._message(to_everyone=True)
        self.assertNotIn(self.ghost, recipients_for(message))

    def test_everyone_beats_a_named_selection(self):
        message = self._message(to_everyone=True)
        message.users.set([self.alice])
        names = set(recipients_for(message).values_list("username", flat=True))
        self.assertEqual(names, {"alice", "bob", "carol"})

    def test_named_users_reach_exactly_those_users(self):
        message = self._message()
        message.users.set([self.alice, self.carol])
        names = set(recipients_for(message).values_list("username", flat=True))
        self.assertEqual(names, {"alice", "carol"})

    def test_named_selection_still_excludes_the_sender(self):
        message = self._message()
        message.users.set([self.alice, self.admin])
        names = set(recipients_for(message).values_list("username", flat=True))
        self.assertEqual(names, {"alice"})

    def test_named_selection_still_skips_inactive_accounts(self):
        message = self._message()
        message.users.set([self.alice, self.ghost])
        names = set(recipients_for(message).values_list("username", flat=True))
        self.assertEqual(names, {"alice"})

    def test_nothing_selected_reaches_nobody(self):
        """The trap: an empty audience must match nothing, not everything."""
        message = self._message()
        self.assertEqual(recipients_for(message).count(), 0)

    def test_preview_count_matches_what_a_send_delivers(self):
        preview = audience_count(to_everyone=True, exclude_user_id=self.admin.pk)
        message = self._message(to_everyone=True)
        self.assertEqual(preview, send_message(message))

    def test_send_refuses_an_empty_audience(self):
        message = self._message()
        with self.assertRaises(EmptyAudienceError):
            send_message(message)
        message.refresh_from_db()
        self.assertEqual(message.status, Message.Status.DRAFT)
        self.assertIsNone(message.sent_at)

    def test_a_user_created_after_the_send_is_not_reached(self):
        """The reason the audience is frozen into rows at send time."""
        message = self._message(to_everyone=True)
        send_message(message)
        latecomer = make_user("latecomer")
        self.assertFalse(Notification.objects.filter(user=latecomer).exists())

    def test_a_draft_has_no_notification_rows(self):
        message = self._message(to_everyone=True)
        self.assertEqual(Notification.objects.count(), 0)
        send_message(message)
        self.assertEqual(Notification.objects.count(), 3)


class ExcerptTests(TestCase):
    def test_short_body_is_returned_whole(self):
        self.assertEqual(excerpt("سلام"), "سلام")

    def test_whitespace_is_collapsed(self):
        self.assertEqual(excerpt("یک\n\n  دو\tسه"), "یک دو سه")

    def test_long_body_is_cut_with_an_ellipsis(self):
        text = excerpt("x" * 400)
        self.assertEqual(len(text), 141)
        self.assertTrue(text.endswith("…"))


class InboxApiTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin", is_staff=True)
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.message = Message.objects.create(
            sender=self.admin, sender_label="admin", title="عنوان", body="متن پیام"
        )
        self.message.to_everyone = True
        self.message.save(update_fields=["to_everyone"])
        send_message(self.message)
        self.alice_note = Notification.objects.get(user=self.alice)
        self.bob_note = Notification.objects.get(user=self.bob)

    def get_json(self, name, *args):
        response = self.client.get(reverse(name, args=args))
        return response, json.loads(response.content)

    def post_json(self, name, payload=None, *args):
        response = self.client.post(
            reverse(name, args=args),
            data=json.dumps(payload or {}),
            content_type="application/json",
        )
        return response, json.loads(response.content)

    def test_inbox_requires_a_session(self):
        response = self.client.get(reverse("game:api_notifications"))
        self.assertEqual(response.status_code, 401)

    def test_inbox_returns_the_list_and_the_count_together(self):
        self.client.force_login(self.alice)
        response, data = self.get_json("game:api_notifications")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["unread"], 1)
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["results"]), 1)
        row = data["results"][0]
        self.assertEqual(row["title"], "عنوان")
        self.assertEqual(row["body"], "متن پیام")
        self.assertEqual(row["excerpt"], "متن پیام")
        self.assertFalse(row["is_read"])

    def test_sender_does_not_receive_their_own_message(self):
        self.client.force_login(self.admin)
        _response, data = self.get_json("game:api_notifications")
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["unread"], 0)

    def test_detail_does_not_mark_the_message_read(self):
        self.client.force_login(self.alice)
        response, data = self.get_json(
            "game:api_notification_detail", self.alice_note.pk
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(data["notification"]["is_read"])
        self.alice_note.refresh_from_db()
        self.assertIsNone(self.alice_note.read_at)

    def test_a_user_cannot_read_another_users_notification(self):
        self.client.force_login(self.alice)
        response, _data = self.get_json(
            "game:api_notification_detail", self.bob_note.pk
        )
        self.assertEqual(response.status_code, 404)

    def test_marking_read_decrements_the_badge(self):
        self.client.force_login(self.alice)
        response, data = self.post_json(
            "game:api_notifications_read", {"ids": [self.alice_note.pk]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["marked"], 1)
        self.assertEqual(data["unread"], 0)
        self.alice_note.refresh_from_db()
        self.assertIsNotNone(self.alice_note.read_at)

    def test_marking_read_is_idempotent(self):
        self.client.force_login(self.alice)
        self.post_json("game:api_notifications_read", {"ids": [self.alice_note.pk]})
        _response, data = self.post_json(
            "game:api_notifications_read", {"ids": [self.alice_note.pk]}
        )
        self.assertEqual(data["marked"], 0)
        self.assertEqual(data["unread"], 0)

    def test_marking_read_ignores_foreign_and_stale_ids(self):
        """One bad id in a batch must not cost the user the good ones."""
        self.client.force_login(self.alice)
        response, data = self.post_json(
            "game:api_notifications_read",
            {"ids": [self.alice_note.pk, self.bob_note.pk, 999999]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["marked"], 1)
        self.bob_note.refresh_from_db()
        self.assertIsNone(self.bob_note.read_at)

    def test_read_all_clears_the_badge(self):
        self.client.force_login(self.alice)
        _response, data = self.post_json("game:api_notifications_read_all")
        self.assertEqual(data["unread"], 0)
        self.bob_note.refresh_from_db()
        self.assertIsNone(self.bob_note.read_at)


class ComposerPermissionTests(TestCase):
    """A non-admin gets 403 from every ``messages/`` endpoint."""

    def setUp(self):
        self.admin = make_user("admin", is_staff=True)
        self.alice = make_user("alice")
        self.sent = Message.objects.create(
            sender=self.admin, title="اعلان", to_everyone=True
        )
        send_message(self.sent)

    def test_every_messages_endpoint_refuses_an_ordinary_user(self):
        self.client.force_login(self.alice)
        calls = [
            ("get", reverse("game:api_messages")),
            ("post", reverse("game:api_messages")),
            ("get", reverse("game:api_message_detail", args=[self.sent.pk])),
            ("patch", reverse("game:api_message_detail", args=[self.sent.pk])),
            ("delete", reverse("game:api_message_detail", args=[self.sent.pk])),
            ("post", reverse("game:api_message_send", args=[self.sent.pk])),
            ("get", reverse("game:api_message_recipients", args=[self.sent.pk])),
            ("get", reverse("game:api_message_audience")),
            ("post", reverse("game:api_message_audience_preview")),
        ]
        for method, url in calls:
            with self.subTest(method=method, url=url):
                if method == "get":
                    response = self.client.get(url)
                else:
                    response = getattr(self.client, method)(
                        url, data="{}", content_type="application/json"
                    )
                self.assertEqual(response.status_code, 403)

    def test_a_superuser_without_the_staff_flag_still_counts_as_admin(self):
        boss = make_user("boss", is_staff=False, is_superuser=True)
        self.client.force_login(boss)
        response = self.client.get(reverse("game:api_messages"))
        self.assertEqual(response.status_code, 200)


class ComposerApiTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin", is_staff=True)
        self.other_admin = make_user("other_admin", is_staff=True)
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.carol = make_user("carol")
        self.client.force_login(self.admin)

    def create(self, **payload):
        response = self.client.post(
            reverse("game:api_messages"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        return response, json.loads(response.content)

    def patch(self, pk, **payload):
        response = self.client.patch(
            reverse("game:api_message_detail", args=[pk]),
            data=json.dumps(payload),
            content_type="application/json",
        )
        return response, json.loads(response.content)

    def test_draft_round_trip_save_reopen_edit_send(self):
        response, data = self.create(title="پیش‌نویس", body="متن اول")
        self.assertEqual(response.status_code, 201)
        pk = data["result"]["id"]
        self.assertEqual(data["result"]["status"], "draft")

        response = self.client.get(reverse("game:api_message_detail", args=[pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["result"]["body"], "متن اول")

        response, data = self.patch(pk, body="متن دوم", users=[self.alice.pk])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["result"]["body"], "متن دوم")
        self.assertEqual(data["result"]["users"], [self.alice.pk])

        response = self.client.post(reverse("game:api_message_send", args=[pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["delivered"], 1)
        self.assertTrue(Notification.objects.filter(user=self.alice).exists())

    def test_create_and_send_in_one_call(self):
        response, data = self.create(
            title="سلام", body="خوش آمدید", to_everyone=True, send=True
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(data["result"]["status"], "sent")
        self.assertEqual(data["delivered"], 4)
        self.assertEqual(Notification.objects.count(), 4)
        self.assertIsNotNone(data["result"]["sent_at"])

    def test_sending_to_three_named_users_reaches_exactly_those_three(self):
        response, data = self.create(
            title="گروهی",
            users=[self.alice.pk, self.bob.pk, self.carol.pk],
            send=True,
        )
        self.assertEqual(data["delivered"], 3)
        reached = set(
            Notification.objects.values_list("user__username", flat=True)
        )
        self.assertEqual(reached, {"alice", "bob", "carol"})

    def test_sending_with_nothing_selected_is_refused_with_409(self):
        response, data = self.create(title="بی‌گیرنده", send=True)
        self.assertEqual(response.status_code, 409)
        self.assertIn("گیرنده", data["error"])
        # Nothing half-made is left behind by the refusal.
        self.assertEqual(Message.objects.count(), 0)

    def test_an_empty_audience_is_legal_on_a_draft(self):
        response, data = self.create(title="بعداً تصمیم می‌گیرم")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(data["result"]["status"], "draft")

    def test_a_title_is_required(self):
        response, _data = self.create(title="   ", body="متن")
        self.assertEqual(response.status_code, 400)

    def test_editing_a_sent_message_is_refused_with_409(self):
        _response, data = self.create(title="نهایی", to_everyone=True, send=True)
        pk = data["result"]["id"]
        response, _data = self.patch(pk, title="ویرایش‌شده")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Message.objects.get(pk=pk).title, "نهایی")

    def test_deleting_a_sent_message_is_refused_with_409(self):
        _response, data = self.create(title="نهایی", to_everyone=True, send=True)
        pk = data["result"]["id"]
        response = self.client.delete(reverse("game:api_message_detail", args=[pk]))
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Message.objects.filter(pk=pk).exists())

    def test_deleting_a_draft_works(self):
        _response, data = self.create(title="دورریختنی")
        pk = data["result"]["id"]
        response = self.client.delete(reverse("game:api_message_detail", args=[pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Message.objects.filter(pk=pk).exists())

    def test_sending_twice_does_not_duplicate_deliveries(self):
        _response, data = self.create(title="یک‌بار", to_everyone=True)
        pk = data["result"]["id"]
        first = self.client.post(reverse("game:api_message_send", args=[pk]))
        self.assertEqual(first.status_code, 200)
        second = self.client.post(reverse("game:api_message_send", args=[pk]))
        self.assertEqual(second.status_code, 409)
        self.assertEqual(Notification.objects.filter(message_id=pk).count(), 4)

    def test_drafts_are_private_to_their_author(self):
        _response, data = self.create(title="خصوصی")
        pk = data["result"]["id"]

        self.client.force_login(self.other_admin)
        listed = self.client.get(reverse("game:api_messages"), {"status": "draft"})
        self.assertEqual(json.loads(listed.content)["results"], [])
        detail = self.client.get(reverse("game:api_message_detail", args=[pk]))
        self.assertEqual(detail.status_code, 404)

    def test_sent_messages_are_visible_to_every_admin(self):
        _response, data = self.create(title="عمومی", to_everyone=True, send=True)
        pk = data["result"]["id"]

        self.client.force_login(self.other_admin)
        listed = self.client.get(reverse("game:api_messages"), {"status": "sent"})
        ids = [row["id"] for row in json.loads(listed.content)["results"]]
        self.assertIn(pk, ids)

    def test_sent_list_carries_the_read_figure(self):
        _response, data = self.create(title="آمار", to_everyone=True, send=True)
        pk = data["result"]["id"]
        note = Notification.objects.filter(message_id=pk, user=self.alice).get()
        self.client.force_login(self.alice)
        self.client.post(
            reverse("game:api_notifications_read"),
            data=json.dumps({"ids": [note.pk]}),
            content_type="application/json",
        )

        self.client.force_login(self.admin)
        listed = self.client.get(reverse("game:api_messages"), {"status": "sent"})
        row = json.loads(listed.content)["results"][0]
        self.assertEqual(row["delivered"], 4)
        self.assertEqual(row["read"], 1)
        self.assertEqual(row["unread"], 3)

    def test_audience_preview_excludes_the_caller(self):
        response = self.client.post(
            reverse("game:api_message_audience_preview"),
            data=json.dumps({"to_everyone": True}),
            content_type="application/json",
        )
        # admin, other_admin, alice, bob, carol -- minus the caller.
        self.assertEqual(json.loads(response.content)["count"], 4)

    def test_audience_preview_of_an_empty_selection_is_zero(self):
        response = self.client.post(
            reverse("game:api_message_audience_preview"),
            data=json.dumps({"to_everyone": False, "users": []}),
            content_type="application/json",
        )
        self.assertEqual(json.loads(response.content)["count"], 0)

    def test_audience_list_excludes_the_caller(self):
        response = self.client.get(reverse("game:api_message_audience"))
        names = [row["username"] for row in json.loads(response.content)["users"]]
        self.assertNotIn("admin", names)
        self.assertIn("alice", names)


class ReadReceiptTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin", is_staff=True)
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.carol = make_user("carol")
        self.message = Message.objects.create(
            sender=self.admin, title="گزارش", to_everyone=True
        )
        send_message(self.message)
        note = Notification.objects.get(user=self.carol)
        self.client.force_login(self.carol)
        self.client.post(
            reverse("game:api_notifications_read"),
            data=json.dumps({"ids": [note.pk]}),
            content_type="application/json",
        )
        self.client.force_login(self.admin)

    def test_receipts_list_unread_recipients_first(self):
        response = self.client.get(
            reverse("game:api_message_recipients", args=[self.message.pk])
        )
        data = json.loads(response.content)
        self.assertEqual(data["delivered"], 3)
        self.assertEqual(data["read"], 1)
        self.assertEqual(data["unread"], 2)
        self.assertEqual(
            [row["username"] for row in data["recipients"]],
            ["alice", "bob", "carol"],
        )
        self.assertFalse(data["recipients"][0]["is_read"])
        self.assertTrue(data["recipients"][-1]["is_read"])

    def test_receipts_for_a_draft_are_refused_with_409(self):
        draft = Message.objects.create(sender=self.admin, title="پیش‌نویس")
        response = self.client.get(
            reverse("game:api_message_recipients", args=[draft.pk])
        )
        self.assertEqual(response.status_code, 409)
