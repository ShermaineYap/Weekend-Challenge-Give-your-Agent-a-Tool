"""Patience: give a Strands agent the ability to wait (EventBridge Scheduler wake-ups)."""

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Tiny .env loader (written by scripts/configure.py) so no extra dependency is needed."""
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()
