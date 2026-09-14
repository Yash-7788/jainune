import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import HTTPException

from app.routers.admin import reinstate_user
from app.services.dignity_engine import _evaluate_auto_action, AUTO_SUSPEND_THRESHOLD


class TestReinstateHardening:
    """Unit tests for FINDING-12: manual reinstatement resolving pending reports and preventing re-suspension."""

    @pytest.mark.asyncio
    async def test_01_reinstate_user_bulk_resolves_unresolved_reports(self):
        """Verify reinstate_user sets resolved=TRUE on all unresolved reports in same transaction."""
        user_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        admin = {"user_id": admin_id, "admin_role": "superadmin"}

        mock_conn = AsyncMock()
        async def fake_execute(query, *args):
            if "UPDATE reports" in query:
                return "UPDATE 5"
            return "UPDATE 1"
        mock_conn.execute = AsyncMock(side_effect=fake_execute)

        # Mock transaction context manager
        tx_mock = AsyncMock()
        tx_mock.__aenter__.return_value = None
        tx_mock.__aexit__.return_value = None
        mock_conn.transaction = MagicMock(return_value=tx_mock)

        mock_pool = MagicMock()
        acquire_cm = AsyncMock()
        acquire_cm.__aenter__.return_value = mock_conn
        acquire_cm.__aexit__.return_value = None
        mock_pool.acquire.return_value = acquire_cm

        mock_conn.fetchrow = AsyncMock(return_value={
            "is_photo_verified": True,
            "created_at": None,
            "has_voice": 0,
            "confirmed_reports": 0,
            "pending_reports": 0,
            "badge_count": 0,
        })
        mock_conn.fetchval = AsyncMock(return_value=None)

        res = await reinstate_user(
            user_id=user_id,
            admin=admin,
            pool=mock_pool,
            request=None,
        )

        assert res["reinstated"] is True
        assert res["user_id"] == user_id
        assert res["dismissed_reports"] == 5

        # Verify UPDATE reports was executed with resolved = TRUE and action_taken = 'dismissed'
        exec_calls = mock_conn.execute.call_args_list
        assert len(exec_calls) >= 3

        # First call is UPDATE users SET account_status = 'active'
        users_sql = exec_calls[0][0][0]
        assert "account_status = 'active'" in users_sql

        # Second call is UPDATE reports SET resolved = TRUE
        reports_sql = exec_calls[1][0][0]
        assert "UPDATE reports" in reports_sql
        assert "resolved         = TRUE" in reports_sql
        assert "action_taken     = 'dismissed'" in reports_sql
        assert exec_calls[1][0][1] == admin_id
        assert exec_calls[1][0][2] == user_id

        # Third call is audit log
        audit_sql = exec_calls[2][0][0]
        assert "INSERT INTO admin_audit_log" in audit_sql
        assert "dismissed 5 unresolved report(s)" in exec_calls[2][0][3]

    @pytest.mark.asyncio
    async def test_02_reinstate_user_raises_404_when_user_missing(self):
        """Verify reinstate_user raises 404 if user does not exist."""
        user_id = uuid.uuid4()
        admin = {"user_id": uuid.uuid4(), "admin_role": "superadmin"}

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 0")
        tx_mock = AsyncMock()
        tx_mock.__aenter__.return_value = None
        tx_mock.__aexit__.return_value = None
        mock_conn.transaction = MagicMock(return_value=tx_mock)

        mock_pool = MagicMock()
        acquire_cm = AsyncMock()
        acquire_cm.__aenter__.return_value = mock_conn
        acquire_cm.__aexit__.return_value = None
        mock_pool.acquire.return_value = acquire_cm

        with pytest.raises(HTTPException) as exc_info:
            await reinstate_user(user_id=user_id, admin=admin, pool=mock_pool)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_03_resolved_reports_prevent_immediate_resuspension(self):
        """Verify _evaluate_auto_action excludes resolved reports and does not re-suspend."""
        user_id = uuid.uuid4()
        mock_conn = AsyncMock()

        # Reports have been resolved, so valid_reporters_count returns 0 (below threshold)
        mock_conn.fetchval = AsyncMock(return_value=0)

        actioned = await _evaluate_auto_action(user_id=user_id, conn=mock_conn, is_underage=False)
        assert actioned is False

        # Verify SQL checks resolved = FALSE
        query_executed = mock_conn.fetchval.call_args[0][0]
        assert "r.resolved = FALSE" in query_executed
