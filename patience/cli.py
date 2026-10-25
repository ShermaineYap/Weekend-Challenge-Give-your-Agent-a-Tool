"""Talk to the agent.

    python -m patience.cli "Watch the bucket for q3_sales.csv and email me a summary when it lands"
    python -m patience.cli --before "..."     # same agent, WITHOUT schedule_wakeup
"""

import argparse

from .agent import run_task


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--before", action="store_true", help="run the original agent (no schedule_wakeup)")
    args = ap.parse_args()
    label = "BEFORE (no schedule_wakeup)" if args.before else "AFTER (with schedule_wakeup)"
    print(f"\n=== Kopi agent — {label} ===\n")
    run_task(args.prompt, with_wakeup=not args.before)
    print()


if __name__ == "__main__":
    main()
