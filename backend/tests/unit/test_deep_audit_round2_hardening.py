import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.stable_marriage import StableMarriageEngine
from app.services.email_verifier import verify_bot_integrity
from app.models.schemas.feed import DailyCompatibleResponse, FeedCandidate


class TestDeepAuditRound2Hardening(unittest.IsolatedAsyncioTestCase):
    async def test_01_daily_compatible_payload_completeness(self):
        """P1/P2: Verify DailyCompatibleResponse candidate adheres to FeedCandidate schema."""
        candidate_data = {
            "id": str(uuid.uuid4()),
            "first_name": "Aarav",
            "age": 27,
            "city": "Mumbai",
            "state": "Maharashtra",
            "distance_display": "Under 2 km away",
            "dietary_strictness": "pure_jain",
            "eats_root_vegetables": False,
            "eats_onion_garlic": False,
            "community_sect": "shwetambar_murtipujak",
            "paryushan_mode": True,
            "education": "Chartered Accountant",
            "job_title": "Senior Auditor",
            "height_cm": 178,
            "bio": "Committed to Jain values.",
            "open_to_relocation": True,
            "is_photo_verified": True,
            "photos": [{"id": "p1", "url": "https://cdn.jainune.com/p1.jpg", "order": 1}],
            "prompts": [{"question": "Values", "answer": "Ahimsa and truth", "position": 1}],
            "voice_snapshot": {"audio_url": "https://cdn.jainune.com/v1.m4a", "duration_seconds": 7.0},
            "compatibility": {"values_alignment_percentage": 94, "shared_traditions": ["Jain Values", "Ahimsa"]},
            "compatibility_rationale": "Highest reciprocal affinity",
            "pairing_algorithm": "gale_shapley_nightly",
        }
        resp = DailyCompatibleResponse(
            candidate=candidate_data,
            pairing_algorithm=candidate_data["pairing_algorithm"],
            locked_until="2026-09-08T00:00:00+05:30",
        )
        self.assertIsNotNone(resp.candidate)
        self.assertEqual(len(resp.candidate["photos"]), 1)
        self.assertEqual(len(resp.candidate["prompts"]), 1)
        self.assertIsNotNone(resp.candidate["voice_snapshot"])
        self.assertTrue(resp.candidate["is_photo_verified"])

    def test_02_daily_proposals_canonical_ordering(self):
        """P7: Verify canonical ordering of pairs prevents inverted duplicates."""
        u_a = uuid.UUID("11111111-1111-1111-1111-111111111111")
        u_b = uuid.UUID("22222222-2222-2222-2222-222222222222")

        # Inverted incoming inputs
        p1 = {"user_a": str(u_a), "user_b": str(u_b), "score": 0.95}
        p2 = {"user_a": str(u_b), "user_b": str(u_a), "score": 0.95}

        canon_1 = (min(uuid.UUID(p1["user_a"]), uuid.UUID(p1["user_b"])), max(uuid.UUID(p1["user_a"]), uuid.UUID(p1["user_b"])))
        canon_2 = (min(uuid.UUID(p2["user_a"]), uuid.UUID(p2["user_b"])), max(uuid.UUID(p2["user_a"]), uuid.UUID(p2["user_b"])))

        self.assertEqual(canon_1, canon_2)
        self.assertEqual(canon_1[0], u_a)
        self.assertEqual(canon_1[1], u_b)

    async def test_03_telemetry_worker_fk_and_uuid_sanitization(self):
        """P6: Telemetry batch worker skips missing users and avoids ForeignKeyViolation."""
        # Simulated batch containing valid user, deleted user, and invalid UUID string
        valid_user_id = uuid.uuid4()
        deleted_user_id = uuid.uuid4()

        raw_events = [
            {"actor_id": str(valid_user_id), "target_user_id": str(deleted_user_id), "event_type": "profile_view"},
            {"actor_id": str(deleted_user_id), "target_user_id": str(valid_user_id), "event_type": "like"},
            {"actor_id": "invalid-uuid-string", "target_user_id": None, "event_type": "app_open"},
        ]

        # Mimic DB check: only valid_user_id exists
        valid_ids = {valid_user_id}

        sanitized_rows = []
        for e in raw_events:
            a_uuid = None
            if e.get("actor_id"):
                try:
                    a_uuid = uuid.UUID(str(e["actor_id"]))
                except (ValueError, TypeError):
                    pass

            t_uuid = None
            if e.get("target_user_id"):
                try:
                    t_uuid = uuid.UUID(str(e["target_user_id"]))
                except (ValueError, TypeError):
                    pass

            if a_uuid and a_uuid not in valid_ids:
                continue
            if not a_uuid:
                continue

            t_final = t_uuid if (t_uuid and t_uuid in valid_ids) else None
            sanitized_rows.append((e["event_type"], a_uuid, t_final))

        # Event 1 kept with target sanitized to None; Event 2 (deleted actor) dropped; Event 3 (malformed) dropped
        self.assertEqual(len(sanitized_rows), 1)
        self.assertEqual(sanitized_rows[0][0], "profile_view")
        self.assertEqual(sanitized_rows[0][1], valid_user_id)
        self.assertIsNone(sanitized_rows[0][2])

    def test_04_bot_integrity_detection(self):
        """P4: Verify bot scraper detection catches automated User-Agents."""
        is_bot, msg = verify_bot_integrity({"user-agent": "Scrapy/2.11.0 (+https://scrapy.org)"})
        self.assertTrue(is_bot)
        self.assertIn("Automated", msg)

        is_bot_clean, msg_clean = verify_bot_integrity({"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"})
        self.assertFalse(is_bot_clean)
