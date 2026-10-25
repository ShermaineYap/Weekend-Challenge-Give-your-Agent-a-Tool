"""Before/after eval on real Bedrock: does the agent take ownership of "later"?

Runs each prompt against the BEFORE agent and the AFTER agent with wake-ups in
dry-run (nothing is actually scheduled) and an empty bucket (so nothing can be
finished right now). Scores:

  deferred   — AFTER: called schedule_wakeup with a sensible interval
  punted     — reply asks the human to come back / check again later
  premature  — called schedule_wakeup for a task that does NOT need waiting (control prompts)

    python scripts/eval_before_after.py
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PATIENCE_DRY_RUN"] = "1"

from patience import base_tools, wakeup  # noqa: E402
from patience.agent import run_task  # noqa: E402


class EmptyS3:
    def list_objects_v2(self, **kw):
        return {"Contents": []}


base_tools._s3 = lambda: EmptyS3()

NEEDS_WAITING = [
    "When q3_sales.csv shows up in the bucket, email me revenue by region.",
    "Finance will upload q3_sales.csv sometime this afternoon. Let me know the top region once it's in.",
    "Keep an eye on the bucket and tell me as soon as any new CSV arrives.",
    "Remind me tomorrow morning to review the Q3 numbers, with a summary of whatever is in the bucket by then.",
    "Check the bucket every 30 minutes for the next 2 hours and email me if q3_sales.csv appears.",
]
CONTROL = [
    "What files are in the bucket right now?",
    "What can you help me with?",
]
PUNT = re.compile(r"(check back|come back|try again later|ask (me )?again|let me know when|once it('s| is) (uploaded|available).*(ask|let me know)|re-?run)", re.I)


def run(prompt, with_wakeup):
    wakeup.DRY_RUN_LOG.clear()
    reply = str(run_task(prompt, with_wakeup=with_wakeup, callback_handler=None))
    return bool(wakeup.DRY_RUN_LOG), bool(PUNT.search(reply)), reply


def main():
    rows = []
    for p in NEEDS_WAITING:
        for mode in (False, True):
            sched, punt, reply = run(p, mode)
            rows.append(("wait", "AFTER" if mode else "BEFORE", p, sched, punt, reply))
    for p in CONTROL:
        sched, punt, reply = run(p, True)
        rows.append(("control", "AFTER", p, sched, punt, reply))

    print("\n| kind | agent | prompt | scheduled itself | told human to come back |\n|---|---|---|---|---|")
    for kind, mode, p, s, pu, _ in rows:
        print(f"| {kind} | {mode} | {p[:60]} | {'✅' if s else '—'} | {'⚠️' if pu else '—'} |")

    wait_after = [r for r in rows if r[0] == "wait" and r[1] == "AFTER"]
    wait_before = [r for r in rows if r[0] == "wait" and r[1] == "BEFORE"]
    ctrl = [r for r in rows if r[0] == "control"]
    print(f"\nBEFORE: handled 'later' itself {sum(r[3] for r in wait_before)}/{len(wait_before)}, "
          f"punted to human {sum(r[4] for r in wait_before)}/{len(wait_before)}")
    print(f"AFTER : handled 'later' itself {sum(r[3] for r in wait_after)}/{len(wait_after)}, "
          f"punted to human {sum(r[4] for r in wait_after)}/{len(wait_after)}")
    print(f"AFTER : unnecessary wake-ups on control prompts {sum(r[3] for r in ctrl)}/{len(ctrl)}")


if __name__ == "__main__":
    main()
