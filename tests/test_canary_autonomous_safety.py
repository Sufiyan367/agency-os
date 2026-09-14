import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from app.core.config import settings, get_today_window_start
from app.database.models import OutreachStatus, OutreachMessage
from app.outreach.auto_approval import DeterministicAutoApprovalEngine, AutoApprovalResult


def test_today_window_start_without_canary(monkeypatch):
    monkeypatch.setattr(settings, "CANARY_START_TIME", None)
    start = get_today_window_start()
    now_utc = datetime.utcnow()
    expected = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    assert start.date() == expected.date()
    assert start.hour == 0
    assert start.minute == 0


def test_today_window_start_with_canary_timestamp(monkeypatch):
    now_utc = datetime.utcnow()
    one_hr_ago = now_utc - timedelta(hours=1)
    iso_str = one_hr_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
    monkeypatch.setattr(settings, "CANARY_START_TIME", iso_str)
    start = get_today_window_start()
    assert start.year == one_hr_ago.year
    assert start.hour == one_hr_ago.hour
    assert start.minute == one_hr_ago.minute


def test_today_window_start_canary_cannot_be_in_future(monkeypatch):
    now_utc = datetime.utcnow()
    in_future = now_utc + timedelta(hours=2)
    iso_str = in_future.strftime("%Y-%m-%dT%H:%M:%SZ")
    monkeypatch.setattr(settings, "CANARY_START_TIME", iso_str)
    start = get_today_window_start()
    expected_midnight = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    assert start.hour == 0
    assert start.minute == 0


@pytest.mark.asyncio
async def test_auto_approval_engine_scan_and_auto_approve():
    engine = DeterministicAutoApprovalEngine()
    mock_session = AsyncMock()

    mock_msg1 = MagicMock(id=1, status=OutreachStatus.PENDING_APPROVAL.value, recipient_email="a@example.com")
    mock_msg2 = MagicMock(id=2, status=OutreachStatus.PENDING_APPROVAL.value, recipient_email="b@example.com")

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_msg1, mock_msg2]
    mock_session.execute.return_value = mock_result

    eval_res_ok = AutoApprovalResult(1, True, [], [])
    eval_res_blocked = AutoApprovalResult(2, False, [], ["Prohibited claim"])

    with patch.object(engine, "auto_approve_if_eligible", new_callable=AsyncMock) as mock_approve:
        mock_approve.side_effect = [
            (True, MagicMock(status=OutreachStatus.APPROVED.value), eval_res_ok),
            (False, MagicMock(status=OutreachStatus.PENDING_APPROVAL.value), eval_res_blocked)
        ]

        res = await engine.scan_and_auto_approve_pending(mock_session)
        assert res["total_pending_scanned"] == 2
        assert res["auto_approved_count"] == 1
        assert res["blocked_count"] == 1
