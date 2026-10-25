"""Before/after eval on real Bedrock: does the agent take ownership of "later"?

Runs each prompt against the BEFORE agent and the AFTER agent with wake-ups in
dry-run (nothing is actually scheduled) and an empty bucket (so nothing can be
finished right now). Scores:

  booked        — the agent actually booked a follow-up (schedule_wakeup)
  empty promise — the agent SAID it would check again / let you know, but booked nothing
  punted        — the agent asked the human to come back / ask again later
  premature     — booked a wake-up for a task that does NOT need waiting (control prompts)

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
PROMISE = re.compile(r"(i('| wi)ll (check|monitor|keep|let you know|notify|email|follow)|check again|keep an eye|will be notified)", re.I)
PUNT = re.compile(r"(check back|come back|try again later|ask (me )?again|let me know when|once it('s| is) (uploaded|available).*(ask|let me know)|re-?run)", re.I)


def run(prompt, with_wakeup):
    wakeup.DRY_RUN_LOG.clear()
    reply = str(run_task(prompt, with_wakeup=with_wakeup, callback_handler=None))
    booked = bool(wakeup.DRY_RUN_LOG)
    empty_promise = (not booked) and bool(PROMISE.search(reply))
    return booked, empty_promise, bool(PUNT.search(reply)), reply


def main():
    rows = []
    for p in NEEDS_WAITING:
        for mode in (False, True):
            rows.append(("wait", "AFTER" if mode else "BEFORE", p, *run(p, mode)))
    for p in CONTROL:
        rows.append(("control", "AFTER", p, *run(p, True)))

    print("\n| kind | agent | prompt | booked follow-up | empty promise | asked human to come back |")
    print("|---|---|---|---|---|---|")
    for kind, mode, p, b, e, pu, _ in rows:
        print(f"| {kind} | {mode} | {p[:55]} | {'✅' if b else '—'} | {'❌' if e else '—'} | {'⚠️' if pu else '—'} |")

    def tally(sel):
        n = len(sel)
        return (f"booked {sum(r[3] for r in sel)}/{n}, empty promises {sum(r[4] for r in sel)}/{n}, "
                f"asked human {sum(r[5] for r in sel)}/{n}")

    print("\nBEFORE:", tally([r for r in rows if r[0] == "wait" and r[1] == "BEFORE"]))
    print("AFTER :", tally([r for r in rows if r[0] == "wait" and r[1] == "AFTER"]))
    ctrl = [r for r in rows if r[0] == "control"]
    print(f"AFTER control prompts: unnecessary wake-ups {sum(r[3] for r in ctrl)}/{len(ctrl)}")


if __name__ == "__main__":
    main()
