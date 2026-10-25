"""Offline tests for schedule_wakeup + WakeupGuard (no AWS, no Bedrock).

    PATIENCE_DRY_RUN=1 pytest -q
"""

import json
import os

import pytest

os.environ["PATIENCE_DRY_RUN"] = "1"
os.environ["PATIENCE_MAX_DEPTH"] = "3"

from patience import base_tools, wakeup  # noqa: E402
from patience.agent import build_agent, handle_wakeup, run_task  # noqa: E402

from .scripted_model import ScriptedModel  # noqa: E402

FILES: list[dict] = []


@pytest.fixture(autouse=True)
def fake_aws(monkeypatch):
    wakeup.DRY_RUN_LOG.clear()
    base_tools.NOTIFICATIONS.clear()
    FILES.clear()

    class FakeS3:
        def list_objects_v2(self, **kw):
            return {"Contents": [dict(f) for f in FILES]}

        def get_object(self, **kw):
            import io
            return {"Body": io.BytesIO(open("data/q3_sales.csv", "rb").read())}

    monkeypatch.setattr(base_tools, "_s3", lambda: FakeS3())


def _schedule(minutes=1):
    return {"tool": "schedule_wakeup", "input": {
        "minutes_from_now": minutes,
        "instruction": "Check the bucket for q3_sales.csv; if present summarise by region and email the user.",
        "note_to_self": "User wants Q3 sales summary by region. At first check the file was missing.",
    }}


LIST = {"tool": "list_bucket", "input": {}}


def test_before_agent_has_no_wakeup_tool():
    agent = build_agent(with_wakeup=False, model=ScriptedModel([]), callback_handler=None)
    assert "schedule_wakeup" not in agent.tool_names


def test_after_agent_schedules_itself_with_full_payload():
    model = ScriptedModel([[LIST], [_schedule(1)], [{"text": "I'll check back in 1 minute."}]])
    run_task("Email me the Q3 summary when q3_sales.csv lands", model=model, callback_handler=None)

    assert len(wakeup.DRY_RUN_LOG) == 1
    s = wakeup.DRY_RUN_LOG[0]
    assert s["wake_depth"] == 1
    assert s["original_task"].startswith("Email me the Q3 summary")
    assert s["name"].startswith("patience-") and s["name"].endswith("-d1")
    json.dumps(s)  # payload must be JSON-serialisable for EventBridge


def test_full_loop_missing_then_present():
    # 1) human request, file missing -> schedules
    run_task("Email me the Q3 summary when q3_sales.csv lands",
             model=ScriptedModel([[LIST], [_schedule(1)], [{"text": "Will check back."}]]), callback_handler=None)
    first = wakeup.DRY_RUN_LOG[-1]

    # 2) wake #1, still missing -> reschedules (chain id carried over, depth increments)
    handle_wakeup(first, model=ScriptedModel([[LIST], [_schedule(2)], [{"text": "Still waiting."}]]), callback_handler=None)
    second = wakeup.DRY_RUN_LOG[-1]
    assert second["chain_id"] == first["chain_id"] and second["wake_depth"] == 2

    # 3) file arrives, wake #2 -> summarises + notifies, no new schedule
    FILES.append({"Key": "q3_sales.csv", "Size": 5000, "LastModified": __import__("datetime").datetime.now()})
    handle_wakeup(second, model=ScriptedModel([
        [LIST],
        [{"tool": "summarise_csv", "input": {"key": "q3_sales.csv", "group_by": "region", "value_column": "revenue_myr"}}],
        [{"tool": "notify_user", "input": {"subject": "Q3 sales summary", "message": "Klang Valley led."}}],
        [{"text": "Sent."}],
    ]), callback_handler=None)
    assert len(wakeup.DRY_RUN_LOG) == 2
    assert base_tools.NOTIFICATIONS[-1]["subject"] == "Q3 sales summary"


def test_guard_blocks_sleeping_again_without_checking():
    payload = {"chain_id": "abc", "wake_depth": 1, "scheduled_at": "2026-10-25T00:00:00+00:00",
               "original_task": "x", "instruction": "y", "note_to_self": "z"}
    handle_wakeup(payload, model=ScriptedModel([[_schedule(5)], [{"text": "ok"}]]), callback_handler=None)
    assert wakeup.DRY_RUN_LOG == []  # cancelled by WakeupGuard: must re-check first


def test_depth_limit_stops_infinite_loops():
    payload = {"chain_id": "abc", "wake_depth": 3, "scheduled_at": "2026-10-25T00:00:00+00:00",
               "original_task": "x", "instruction": "y", "note_to_self": "z"}
    handle_wakeup(payload, model=ScriptedModel([[LIST], [_schedule(5)], [{"text": "ok"}]]), callback_handler=None)
    assert wakeup.DRY_RUN_LOG == []  # depth 4 > max 3


def test_rejects_out_of_range_horizon():
    run_task("x", model=ScriptedModel([[LIST], [_schedule(999999)], [{"text": "ok"}]]), callback_handler=None)
    assert wakeup.DRY_RUN_LOG == []


def test_real_scheduler_call_shape(monkeypatch):
    calls = []

    class FakeScheduler:
        class exceptions:
            class ConflictException(Exception):
                pass

        def create_schedule(self, **kw):
            calls.append(kw)

    monkeypatch.setenv("PATIENCE_DRY_RUN", "0")
    monkeypatch.setenv("PATIENCE_TARGET_ARN", "arn:aws:sqs:us-east-1:123:patience-wake")
    monkeypatch.setenv("PATIENCE_SCHEDULER_ROLE", "arn:aws:iam::123:role/sched")
    wakeup.set_scheduler_client(FakeScheduler())
    run_task("x", model=ScriptedModel([[LIST], [_schedule(10)], [{"text": "ok"}]]), callback_handler=None)

    kw = calls[0]
    assert kw["ScheduleExpression"].startswith("at(") and kw["ActionAfterCompletion"] == "DELETE"
    assert kw["FlexibleTimeWindow"] == {"Mode": "OFF"}
    assert json.loads(kw["Target"]["Input"])["wake_depth"] == 1


def test_guard_blocks_scheduling_before_checking_on_first_turn():
    run_task("x", model=ScriptedModel([[_schedule(5)], [{"text": "ok"}]]), callback_handler=None)
    assert wakeup.DRY_RUN_LOG == []


def test_only_one_wakeup_per_turn():
    run_task("x", model=ScriptedModel([[LIST], [_schedule(1)], [_schedule(60)], [{"text": "ok"}]]),
             callback_handler=None)
    assert len(wakeup.DRY_RUN_LOG) == 1


def test_demo_cap_compresses_time(monkeypatch):
    monkeypatch.setenv("PATIENCE_DEMO_CAP_MINUTES", "1")
    from datetime import datetime
    run_task("x", model=ScriptedModel([[LIST], [_schedule(60)], [{"text": "ok"}]]), callback_handler=None)
    s = wakeup.DRY_RUN_LOG[0]
    delta = datetime.fromisoformat(s["run_at"]) - datetime.fromisoformat(s["scheduled_at"])
    assert delta.total_seconds() <= 61
