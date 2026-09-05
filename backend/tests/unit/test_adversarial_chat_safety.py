"""
Adversarial Human-like Stress & Evasion Tests for Chat Safety Moderation.
Simulates real attacker evasion vectors:
- Separated / spaced / dotted keywords (s.n.a.p, i n s t a, 9 8 7 6 5 4 3 2 1 0)
- Full app names in ANY casing combo (InStAgRaM, snapCHAT, FaceBook, WHATSAPP, TeleGram, BUMBLE)
- Zero-width character and homoglyph injections
- Sequential single-character/digit stealth tricks interspersed with dialogue
- Word numbers (long series blocked; casual conversational numbers allowed)
- Generalized intent & idiom preservation (cooking grams, road trips, street food, two-way street)
"""

from __future__ import annotations

import unittest
import uuid
from typing import Dict

from app.services.chat_safety_filter import filter_chat_content


class MockRedis:
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


class TestAdversarialChatSafety(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = MockRedis()
        self.chat_id = uuid.uuid4()
        self.user_id = uuid.uuid4()

    async def test_01_word_numbers_casual_vs_series(self):
        """Casual conversational numbers must be allowed; series of word numbers must be masked."""
        # Casual conversation: 1 or 2 number words -> MUST PASS
        c1 = await filter_chat_content("I have two brothers and one sister", self.chat_id, self.user_id, self.redis)
        self.assertFalse(c1.is_moderated, "False positive on casual word numbers")
        self.assertEqual(c1.content, "I have two brothers and one sister")

        c2 = await filter_chat_content("Let us meet at four pm for dinner", self.chat_id, self.user_id, self.redis)
        self.assertFalse(c2.is_moderated, "False positive on time meeting")

        c3 = await filter_chat_content("Book a table for three please", self.chat_id, self.user_id, self.redis)
        self.assertFalse(c3.is_moderated, "False positive on table reservation")

        # Evasion: series of 4+ word numbers -> MUST BE BLOCKED
        ev1 = await filter_chat_content("nine eight seven six five four three two one zero", self.chat_id, self.user_id, self.redis)
        self.assertTrue(ev1.is_moderated, "Failed to catch full 10-digit word number")
        self.assertEqual(ev1.moderation_type, "NUMBERS")
        self.assertIn("#", ev1.content)

        ev2 = await filter_chat_content("call me at nine eight seven six", self.chat_id, self.user_id, self.redis)
        self.assertTrue(ev2.is_moderated, "Failed to catch call prefix + word numbers")
        self.assertEqual(ev2.moderation_type, "NUMBERS")

    async def test_02_spaced_and_dotted_social_apps(self):
        """Attackers using separators (s.n.a.p, i n s t a, w-h-a-t-s-a-p-p) must be caught."""
        evasions = [
            "my s.n.a.p is jain99",
            "add me on s n a p",
            "check my i n s t a",
            "message on w.h.a.t.s.a.p.p",
            "ping on t.e.l.e.g.r.a.m",
            "find me on b.u.m.b.l.e",
            "lets move to t-i-n-d-e-r",
            "my sc is rahulj",
            "dm me on ig",
        ]
        for msg in evasions:
            res = await filter_chat_content(msg, self.chat_id, self.user_id, self.redis)
            self.assertTrue(res.is_moderated, f"Failed to catch evasion: '{msg}'")
            self.assertIn("#", res.content)

    async def test_03_zero_width_and_homoglyph_injections(self):
        """Invisible chars (\\u200b) and Cyrillic homoglyphs must be normalized and caught."""
        # Zero-width space inside 'snap'
        zw_msg = "my s\u200bn\u200ba\u200bp id"
        r1 = await filter_chat_content(zw_msg, self.chat_id, self.user_id, self.redis)
        self.assertTrue(r1.is_moderated, "Failed to catch zero-width space evasion")

        # Cyrillic 'а' (U+0430) in 'insta'
        cyrillic_msg = "find me on inst\u0430"
        r2 = await filter_chat_content(cyrillic_msg, self.chat_id, self.user_id, self.redis)
        self.assertTrue(r2.is_moderated, "Failed to catch Cyrillic homoglyph evasion")

    async def test_04_phone_formatting_evasions(self):
        """Phone numbers with varied delimiters and formatting must be caught."""
        phones = [
            "call 9 8 7 6 5 4 3 2 1 0",
            "call 9.8.7.6.5.4.3.2.1.0",
            "call 9-8-7-6-5-4-3-2-1-0",
            "phone +91-98765-43210",
            "mobile (987) 654-3210",
            "dial 9876543210 now",
        ]
        for p in phones:
            res = await filter_chat_content(p, self.chat_id, self.user_id, self.redis)
            self.assertTrue(res.is_moderated, f"Failed to catch phone format: '{p}'")
            self.assertEqual(res.moderation_type, "NUMBERS")

    async def test_05_address_and_coordinates_evasions(self):
        """Addresses, PIN codes, and GPS coords must be caught."""
        addresses = [
            "my pincode is 400 001",
            "pincode 560001",
            "I live at flat no 502",
            "meet at 12th main road",
            "reach brigade road near church street",
            "coords: 12.9716, 77.5946",
        ]
        for a in addresses:
            res = await filter_chat_content(a, self.chat_id, self.user_id, self.redis)
            self.assertTrue(res.is_moderated, f"Failed to catch address: '{a}'")
            self.assertEqual(res.moderation_type, "ADDRESS")

    async def test_06_conversational_false_positive_resistance(self):
        """Normal English phrases containing substrings must NOT be moderated."""
        safe_phrases = [
            "I wrote a computer program yesterday",
            "My grandmother makes amazing thepla",
            "The road was completely clear today",
            "She had an instant reaction to the joke",
            "We took a photograph together",
            "I am in a diagram meeting right now",
            "Life is an endless road of learning",
        ]
        for s in safe_phrases:
            res = await filter_chat_content(s, self.chat_id, self.user_id, self.redis)
            self.assertFalse(res.is_moderated, f"False positive triggered on safe phrase: '{s}'")
            self.assertEqual(res.content, s)

    async def test_07_dialogue_interspersed_stealth_character_leak(self):
        """
        Simulate an attacker trying to spell out handle 'yash98' across a conversation:
        - Msg 1: 'y' (1st single char) -> allowed
        - Msg 2: normal message -> allowed
        - Msg 3: 'a' (2nd single char) -> allowed
        - Msg 4: normal message -> allowed
        - Msg 5: 's' (3rd single char) -> BLOCKED -> '#'
        - Msg 6: 'h' (4th single char) -> BLOCKED -> '#'
        - Msg 7: '9' (5th single char) -> BLOCKED -> '#'
        - Msg 8: '8' (6th single char) -> BLOCKED -> '#'
        """
        dialogue = [
            ("y", False, "y"),
            ("Hey, how is your day going?", False, "Hey, how is your day going?"),
            ("a", False, "a"),
            ("Did you have lunch yet?", False, "Did you have lunch yet?"),
            ("s", True, "#"),
            ("h", True, "#"),
            ("9", True, "#"),
            ("8", True, "#"),
        ]

        for text, expected_mod, expected_content in dialogue:
            res = await filter_chat_content(text, self.chat_id, self.user_id, self.redis)
            self.assertEqual(res.is_moderated, expected_mod, f"Failed on dialogue turn: '{text}'")
            self.assertEqual(res.content, expected_content, f"Content mismatch on turn: '{text}'")

    async def test_08_casing_variations_full_app_names(self):
        """Full app names in ANY casing combo must be caught and masked."""
        cases = [
            ("Add me on InStAgRaM right now", "INSTAGRAM"),
            ("My snapCHAT id is rahul_j99", "SNAPCHAT"),
            ("Ping me on WHATSAPP or TeleGram", "WHATSAPP/TELEGRAM"),
            ("Are you on FaceBook or TwItTeR?", "FACEBOOK/TWITTER"),
            ("Lets switch to BUMBLE or TiNdEr", "BUMBLE/TINDER"),
            ("Check my profile on sHaAdI", "SHAADI"),
            ("Are you on HiNgE?", "HINGE"),
        ]
        for msg, label in cases:
            res = await filter_chat_content(msg, self.chat_id, self.user_id, self.redis)
            self.assertTrue(res.is_moderated, f"Failed on casing combo: '{msg}' ({label})")
            self.assertIn("#", res.content)

    async def test_09_generalized_intent_and_idiom_preservation(self):
        """Smart intent preserves benign cooking, idioms, and travel phrases."""
        safe_conversations = [
            "I need 500 grams of flour for the recipe",
            "I love cooking with 200 grams of paneer",
            "She sent a snapshot of the temple",
            "It was a snap decision to travel",
            "Street food in Bangalore is delicious",
            "The road was under construction",
            "Life is a two-way street",
            "We went on a road trip last weekend",
            "I love street art in Berlin",
            "There were street dogs outside the park",
            "The road ahead is very clear",
        ]
        for msg in safe_conversations:
            res = await filter_chat_content(msg, self.chat_id, self.user_id, self.redis)
            self.assertFalse(res.is_moderated, f"False positive on benign message: '{msg}'")
            self.assertEqual(res.content, msg)


if __name__ == "__main__":
    unittest.main()
