"""
Unit tests for Chat Safety Moderation Service — Roblox-style filter & anti-circumvention:
- Social media handles & app names
- Competitor dating apps
- Phone numbers & multi-digit contact sequences
- Addresses, street names, PIN codes & GPS coordinates
- Single-letter / single-digit stealth tracking (allowed 1st & 2nd, blocked on 3rd)
- Subscription & user approval gate
"""

from __future__ import annotations

import unittest
import uuid
from typing import Dict

from app.services.chat_safety_filter import filter_chat_content


class MockRedis:
    """In-memory Redis mock for unit testing counters and expiration."""

    def __init__(self):
        self.data: Dict[str, int] = {}
        self.ttls: Dict[str, int] = {}

    async def incr(self, key: str) -> int:
        val = self.data.get(key, 0) + 1
        self.data[key] = val
        return val

    async def expire(self, key: str, ttl: int) -> bool:
        self.ttls[key] = ttl
        return True


class TestChatSafetyFilter(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = MockRedis()
        self.chat_id = uuid.uuid4()
        self.user_id = uuid.uuid4()

    async def test_01_single_character_stealth_sequence(self):
        """
        1st single char: allowed.
        2nd single char: allowed.
        3rd single char: blocked and replaced with '#'.
        Interspersed normal messages do not reset the count.
        """
        # Msg 1: single char 'y' -> allowed
        res1 = await filter_chat_content("y", self.chat_id, self.user_id, self.redis)
        self.assertEqual(res1.content, "y")
        self.assertFalse(res1.is_moderated)

        # Msg 2: normal message -> allowed
        res_norm = await filter_chat_content("Hello how are you?", self.chat_id, self.user_id, self.redis)
        self.assertEqual(res_norm.content, "Hello how are you?")
        self.assertFalse(res_norm.is_moderated)

        # Msg 3: single char 'a' -> 2nd single char -> allowed
        res2 = await filter_chat_content("a", self.chat_id, self.user_id, self.redis)
        self.assertEqual(res2.content, "a")
        self.assertFalse(res2.is_moderated)

        # Msg 4: normal message -> allowed
        res_norm2 = await filter_chat_content("Nice weather today", self.chat_id, self.user_id, self.redis)
        self.assertFalse(res_norm2.is_moderated)

        # Msg 5: single char 's' -> 3rd single char -> BLOCKED and replaced with '#'
        res3 = await filter_chat_content("s", self.chat_id, self.user_id, self.redis)
        self.assertEqual(res3.content, "#")
        self.assertTrue(res3.is_moderated)
        self.assertEqual(res3.moderation_type, "SINGLE_CHAR_SEQUENCE")

        # Msg 6: single char 'h' -> 4th single char -> BLOCKED
        res4 = await filter_chat_content("h", self.chat_id, self.user_id, self.redis)
        self.assertEqual(res4.content, "#")
        self.assertTrue(res4.is_moderated)

    async def test_02_single_digit_sequence_tracking(self):
        """Single digits 9 (allowed), 8 (allowed), 7 (blocked with #)."""
        u2 = uuid.uuid4()
        r1 = await filter_chat_content("9", self.chat_id, u2, self.redis)
        self.assertEqual(r1.content, "9")
        self.assertFalse(r1.is_moderated)

        r2 = await filter_chat_content("8", self.chat_id, u2, self.redis)
        self.assertEqual(r2.content, "8")
        self.assertFalse(r2.is_moderated)

        r3 = await filter_chat_content("7", self.chat_id, u2, self.redis)
        self.assertEqual(r3.content, "#")
        self.assertTrue(r3.is_moderated)

    async def test_03_social_media_handles_masked(self):
        """Social media app names and handles masked to '#'."""
        # Snapchat
        r = await filter_chat_content("add me on snapchat please", self.chat_id, self.user_id, self.redis)
        self.assertTrue(r.is_moderated)
        self.assertEqual(r.moderation_type, "SOCIAL_ID")
        self.assertNotIn("snapchat", r.content.lower())
        self.assertIn("########", r.content)

        # Instagram
        r2 = await filter_chat_content("my insta is rahul_jain", self.chat_id, self.user_id, self.redis)
        self.assertTrue(r2.is_moderated)
        self.assertNotIn("insta", r2.content.lower())

        # WhatsApp
        r3 = await filter_chat_content("msg me on whatsapp", self.chat_id, self.user_id, self.redis)
        self.assertTrue(r3.is_moderated)
        self.assertNotIn("whatsapp", r3.content.lower())

        # Telegram
        r4 = await filter_chat_content("reach me on telegram", self.chat_id, self.user_id, self.redis)
        self.assertTrue(r4.is_moderated)
        self.assertNotIn("telegram", r4.content.lower())

    async def test_04_competitor_dating_apps_masked(self):
        """Competitor dating app references masked to '#'."""
        r1 = await filter_chat_content("are you active on bumble?", self.chat_id, self.user_id, self.redis)
        self.assertTrue(r1.is_moderated)
        self.assertEqual(r1.moderation_type, "DATING_APP")
        self.assertNotIn("bumble", r1.content.lower())

        r2 = await filter_chat_content("lets talk on tinder or hinge", self.chat_id, self.user_id, self.redis)
        self.assertTrue(r2.is_moderated)
        self.assertNotIn("tinder", r2.content.lower())
        self.assertNotIn("hinge", r2.content.lower())

    async def test_05_phone_numbers_masked(self):
        """10-digit phone numbers and spaced numbers masked to '#'."""
        # Standard mobile number
        r1 = await filter_chat_content("my number is 9876543210", self.chat_id, self.user_id, self.redis)
        self.assertTrue(r1.is_moderated)
        self.assertEqual(r1.moderation_type, "NUMBERS")
        self.assertNotIn("9876543210", r1.content)
        self.assertIn("##########", r1.content)

        # Spaced mobile number
        r2 = await filter_chat_content("call 98765 43210", self.chat_id, self.user_id, self.redis)
        self.assertTrue(r2.is_moderated)
        self.assertNotIn("98765", r2.content)

    async def test_06_addresses_street_pincode_gps_masked(self):
        """Address, street names, flat number, PIN code, and GPS coordinates masked to '#'."""
        # PIN code
        r1 = await filter_chat_content("I live in 400001", self.chat_id, self.user_id, self.redis)
        self.assertTrue(r1.is_moderated)
        self.assertEqual(r1.moderation_type, "ADDRESS")
        self.assertNotIn("400001", r1.content)

        # GPS lat/long
        r2 = await filter_chat_content("coordinates are 19.0760, 72.8777", self.chat_id, self.user_id, self.redis)
        self.assertTrue(r2.is_moderated)
        self.assertEqual(r2.moderation_type, "ADDRESS")
        self.assertNotIn("19.0760", r2.content)

        # Flat and Road
        r3 = await filter_chat_content("meet at flat no 402 mg road", self.chat_id, self.user_id, self.redis)
        self.assertTrue(r3.is_moderated)
        self.assertNotIn("flat no 402", r3.content.lower())
        self.assertNotIn("mg road", r3.content.lower())

    async def test_07_subscription_and_approval_allows_unmasked(self):
        """
        If user is subscribed AND approved disclaimer: allowed unmasked.
        If user is NOT subscribed: strictly masked regardless of approval.
        """
        # Subscribed and approved
        r_sub = await filter_chat_content(
            "add me on snap 9876543210",
            self.chat_id,
            self.user_id,
            self.redis,
            is_subscribed=True,
            user_disclaimer_approved=True,
        )
        self.assertFalse(r_sub.is_moderated)
        self.assertEqual(r_sub.content, "add me on snap 9876543210")

        # Unsubscribed but approved -> STILL MASKED
        r_unsub = await filter_chat_content(
            "add me on snap 9876543210",
            self.chat_id,
            self.user_id,
            self.redis,
            is_subscribed=False,
            user_disclaimer_approved=True,
        )
        self.assertTrue(r_unsub.is_moderated)
        self.assertNotIn("snap", r_unsub.content)
        self.assertNotIn("9876543210", r_unsub.content)
        self.assertTrue(r_unsub.requires_subscription)


if __name__ == "__main__":
    unittest.main()
