"""
schedule_wakeup — the one tool that gives a Strands agent a sense of time.

The agent calls it to book a one-time Amazon EventBridge Scheduler entry that
re-invokes *itself* later with an instruction it wrote for its future self.
When the schedule fires, the payload is delivered to the wake target
(an AWS Lambda function, or an SQS queue drained by a local worker) and the
agent picks the task back up.

Drop-in usage:

    from patience.wakeup import schedule_wakeup, WakeupGuard
    agent = Agent(tools=[...your tools..., schedule_wakeup], hooks=[WakeupGuard()])

Configuration (env vars):
    PATIENCE_TARGET_ARN      Lambda or SQS ARN the schedule delivers to   (required unless DRY_RUN)
    PATIENCE_SCHEDULER_ROLE  IAM role ARN EventBridge Scheduler assumes   (required unless DRY_RUN)
    PATIENCE_GROUP           Schedule group name                          (default "patience")
    PATIENCE_MAX_MINUTES     Furthest the agent may schedule ahead        (default 10080 = 7 days)
    PATIENCE_MAX_DEPTH       Max chained wake-ups per task                (default 6)
    PATIENCE_DEMO_CAP_MINUTES  Demo/time-compression mode: clamp every wake-up to at most N minutes
    PATIENCE_DRY_RUN=1       Record schedules locally instead of calling AWS (tests / evals)
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from strands import ToolContext, tool
from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

TOOL_NAME = "schedule_wakeup"

# Schedules recorded when PATIENCE_DRY_RUN=1 (inspected by tests and the eval).
DRY_RUN_LOG: list[dict[str, Any]] = []

_scheduler_client = None


def _cfg(name: str, default: str | None = None) -> str | None:
    return os.environ.get(f"PATIENCE_{name}", default)


def _scheduler():
    global _scheduler_client
    if _scheduler_client is None:
        _scheduler_client = boto3.client("scheduler")
    return _scheduler_client


def set_scheduler_client(client) -> None:
    """Inject a client (tests, custom sessions, other regions)."""
    global _scheduler_client
    _scheduler_client = client


def _schedule_name(chain_id: str, depth: int) -> str:
    # Deterministic per (chain, depth): a retried tool call can't create duplicates.
    safe = re.sub(r"[^0-9A-Za-z_.-]", "-", chain_id)[:40]
    return f"patience-{safe}-d{depth}"


def _error(msg: str) -> dict:
    return {"status": "error", "content": [{"text": msg}]}


@tool(context=True)
def schedule_wakeup(
    minutes_from_now: int,
    instruction: str,
    note_to_self: str,
    tool_context: ToolContext,
) -> dict:
    """Schedule yourself to wake up later and continue this task.

    Use this whenever the task cannot be finished right now because something
    has not happened YET (a file has not arrived, a value has not changed, a
    deadline is in the future, the user asked for a follow-up later).
    Do NOT tell the user to "check back later" — schedule the check yourself.
    Do NOT use it for work you can finish now.

    Args:
        minutes_from_now: How many minutes from now to wake up (1 to the configured maximum).
            Pick the shortest sensible interval for the situation.
        instruction: Exactly what your future self should do on waking, written as a
            direct command, including what "done" looks like and what to do if it still isn't done.
        note_to_self: Everything your future self needs to know, because it will NOT remember
            this conversation: the user's goal, what you already checked and found, names/keys/IDs.
    """
    state = tool_context.invocation_state or {}
    depth = int(state.get("wake_depth", 0)) + 1
    chain_id = state.get("chain_id") or uuid.uuid4().hex[:12]
    original_task = state.get("original_task") or instruction

    max_minutes = int(_cfg("MAX_MINUTES", "10080"))
    max_depth = int(_cfg("MAX_DEPTH", "6"))

    if minutes_from_now < 1 or minutes_from_now > max_minutes:
        return _error(f"minutes_from_now must be between 1 and {max_minutes}.")
    if state.get("_scheduled_this_turn"):
        return _error(
            f"You already scheduled a wake-up this turn ({state['_scheduled_this_turn']}). "
            "Do not schedule another; tell the user when you'll check back."
        )
    if depth > max_depth:
        return _error(
            f"Wake-up limit reached ({max_depth} chained wake-ups for this task). "
            "Stop rescheduling and tell the user what you found and what is still pending."
        )

    requested = minutes_from_now
    cap = _cfg("DEMO_CAP_MINUTES")
    if cap:
        minutes_from_now = min(minutes_from_now, int(cap))

    now = datetime.now(timezone.utc)
    run_at = (now + timedelta(minutes=minutes_from_now)).replace(microsecond=0)
    payload = {
        "patience": 1,
        "chain_id": chain_id,
        "wake_depth": depth,
        "scheduled_at": now.isoformat(),
        "run_at": run_at.isoformat(),
        "original_task": original_task,
        "instruction": instruction,
        "note_to_self": note_to_self,
        "user": state.get("user"),
    }
    name = _schedule_name(chain_id, depth)

    if _cfg("DRY_RUN") == "1":
        DRY_RUN_LOG.append({"name": name, **payload})
    else:
        target_arn, role_arn = _cfg("TARGET_ARN"), _cfg("SCHEDULER_ROLE")
        if not target_arn or not role_arn:
            return _error("Wake-ups are not configured (PATIENCE_TARGET_ARN / PATIENCE_SCHEDULER_ROLE).")
        try:
            _scheduler().create_schedule(
                Name=name,
                GroupName=_cfg("GROUP", "patience"),
                ScheduleExpression=f"at({run_at.strftime('%Y-%m-%dT%H:%M:%S')})",
                ScheduleExpressionTimezone="UTC",
                FlexibleTimeWindow={"Mode": "OFF"},
                ActionAfterCompletion="DELETE",  # one-shot: cleans itself up after firing
                Description=instruction[:512],
                Target={
                    "Arn": target_arn,
                    "RoleArn": role_arn,
                    "Input": json.dumps(payload),
                    "RetryPolicy": {"MaximumRetryAttempts": 2, "MaximumEventAgeInSeconds": 3600},
                },
            )
        except _scheduler().exceptions.ConflictException:
            pass  # same chain+depth already booked: idempotent success
        except Exception as e:  # surface AWS errors to the model so it can tell the user
            return _error(f"Could not schedule wake-up: {e}")

    state["_scheduled_this_turn"] = f"wake #{depth} at {run_at.isoformat()}"
    result = {
        "scheduled": True,
        "schedule_name": name,
        "wakes_at_utc": run_at.isoformat(),
        "wake_number": depth,
        "remaining_wakeups": max_depth - depth,
    }
    if requested != minutes_from_now:
        result["demo_mode"] = f"requested {requested} min, compressed to {minutes_from_now} min for the demo"
    return {"status": "success", "content": [{"json": result}]}


class WakeupGuard(HookProvider):
    """Policy layer around schedule_wakeup, using Strands hooks.

    - Blocks schedule_wakeup until the model has checked the world with another tool this turn
      (no sleeping blind, and no lazy "wake, sleep, wake" loop that never re-checks).
    - Optionally requires human approval (Strands interrupts) before booking.
    """

    def __init__(self, require_approval: bool | None = None):
        if require_approval is None:
            require_approval = _cfg("REQUIRE_APPROVAL") == "1"
        self.require_approval = require_approval

    def register_hooks(self, registry: HookRegistry, **_: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self._before_tool)

    def _before_tool(self, event: BeforeToolCallEvent) -> None:
        if event.tool_use.get("name") != TOOL_NAME:
            return

        state = event.invocation_state or {}
        used = _tools_used_this_turn(event.agent)
        if not (used - {TOOL_NAME}):
            woke = state.get("wake_depth", 0) > 0
            event.cancel_tool = (
                ("You just woke up. " if woke else "")
                + "Check the current situation with your other tools BEFORE scheduling a wake-up "
                "(it may already be possible to finish now)."
            )
            return

        if self.require_approval:
            mins = event.tool_use.get("input", {}).get("minutes_from_now")
            answer = event.interrupt(
                "patience-approval",
                reason=f"Agent wants to wake itself in {mins} min to: "
                f"{event.tool_use.get('input', {}).get('instruction', '')}",
            )
            if str(answer).strip().lower() not in {"y", "yes", "approve", "ok"}:
                event.cancel_tool = "The user declined the follow-up. Do not schedule it."


def _tools_used_this_turn(agent) -> set[str]:
    """Names of tools the agent has called since the latest user message."""
    names: set[str] = set()
    for msg in reversed(agent.messages):
        content = msg.get("content", [])
        if msg.get("role") == "user" and not any("toolResult" in c for c in content):
            break
        for c in content:
            if "toolUse" in c:
                names.add(c["toolUse"]["name"])
    return names
