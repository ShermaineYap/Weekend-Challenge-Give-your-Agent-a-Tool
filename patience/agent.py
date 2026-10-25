"""Building the agent, running a task, and resuming a task when a wake-up fires."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from strands import Agent
from strands.models import BedrockModel

from .base_tools import BASE_TOOLS
from .wakeup import WakeupGuard, schedule_wakeup

MODEL_ID = os.environ.get("PATIENCE_MODEL_ID", "us.amazon.nova-pro-v1:0")
REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"

BASE_PROMPT = """You are Kopi, a data assistant for a small Malaysian F&B company.
You can look at the team's S3 data bucket, summarise CSV files, and email the user.
Be concise. When you finish a piece of work for the user, email them the result with notify_user.
Current time (UTC): {now}"""

WAKEUP_PROMPT = """
You can now act over time. If a task depends on something that hasn't happened yet,
do not ask the user to come back later and do not promise to "check again" yourself:
first check the current situation with your tools, then call schedule_wakeup (once) and handle it yourself.
Your future self remembers NOTHING except the instruction and note_to_self you write, so make them complete.
When a task is finally done, send the result and do not schedule further wake-ups."""


def build_agent(with_wakeup: bool = True, model=None, callback_handler=..., **kwargs) -> Agent:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    prompt = BASE_PROMPT.format(now=now) + (WAKEUP_PROMPT if with_wakeup else "")
    tools = BASE_TOOLS + ([schedule_wakeup] if with_wakeup else [])
    extra = {} if callback_handler is ... else {"callback_handler": callback_handler}
    return Agent(
        model=model or BedrockModel(model_id=MODEL_ID, region_name=REGION, temperature=0.2),
        system_prompt=prompt,
        tools=tools,
        hooks=[WakeupGuard()] if with_wakeup else [],
        **extra,
        **kwargs,
    )


def run_task(prompt: str, with_wakeup: bool = True, user: str | None = None, **agent_kwargs):
    """A fresh request from a human."""
    agent = build_agent(with_wakeup=with_wakeup, **agent_kwargs)
    return agent(
        prompt,
        invocation_state={
            "wake_depth": 0,
            "chain_id": uuid.uuid4().hex[:12],
            "original_task": prompt,
            "user": user,
        },
    )


def handle_wakeup(payload: dict, **agent_kwargs):
    """A scheduled wake-up fired. Rebuild the agent and resume from the payload."""
    scheduled = datetime.fromisoformat(payload["scheduled_at"])
    mins_ago = int((datetime.now(timezone.utc) - scheduled).total_seconds() // 60)
    wake_prompt = (
        f"⏰ WAKE-UP #{payload['wake_depth']} — you scheduled this yourself {mins_ago} min ago.\n"
        f"Original user request: {payload['original_task']}\n"
        f"Your note to self: {payload['note_to_self']}\n"
        f"Instruction: {payload['instruction']}\n"
        "Re-check the current situation with your tools now, then either finish the task "
        "(and notify the user) or, if it still isn't ready, schedule another wake-up."
    )
    agent = build_agent(with_wakeup=True, **agent_kwargs)
    return agent(
        wake_prompt,
        invocation_state={
            "wake_depth": payload["wake_depth"],
            "chain_id": payload["chain_id"],
            "original_task": payload["original_task"],
            "user": payload.get("user"),
        },
    )
