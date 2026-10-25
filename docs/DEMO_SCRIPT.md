# Demo video script (target 2:40, hard limit 3:00)

Record with OBS or Loom at 1080p. Use a big terminal font (18pt+) and a split screen:
**left = terminal 2 (you talking to the agent), right = terminal 1 (the worker / "alarm clock")**.
Put your email inbox in a third window for the ending.

Before you record: `python scripts/drop_file.py --remove`, then start `python -m patience.worker` in terminal 1.

---

### 0:00–0:15 · Hook (on camera or over a title card)
> "Every AI agent has the same blind spot: it can't wait. If the answer depends on something that hasn't happened yet, it hands the problem back to you. This weekend I gave my agent one tool that fixes that."

Title card: **Patience: give your agent the ability to wait** · Strands Agents + Amazon Bedrock + EventBridge Scheduler

### 0:15–0:45 · BEFORE
> "This is Kopi, a Strands agent on Bedrock. It can read our S3 bucket, summarise CSVs and email me."

Run:
```
python -m patience.cli --before "Finance is uploading q3_sales.csv this afternoon. When it lands, email me revenue by region."
```
Point at the reply ("please ask me again once it's uploaded").
> "It has every tool it needs to do the work. What it doesn't have is time. Now I'm the one who has to remember."

### 0:45–1:15 · The one tool
Show `patience/wakeup.py` in the editor for about 10 seconds. Highlight the `@tool` signature and the `create_schedule(... at(...), ActionAfterCompletion="DELETE")` call.
> "One new tool: schedule_wakeup. The agent picks *when* to come back and writes a note to its future self. EventBridge Scheduler books a one-shot schedule that wakes the agent up with that note."

Flash the 3-line reuse snippet from the README.

### 1:15–2:20 · AFTER (the payoff, keep it real-time and cut the dead air)
```
python -m patience.cli "Finance is uploading q3_sales.csv this afternoon. When it lands, email me revenue by region."
```
- Agent lists bucket → calls `schedule_wakeup(2, ...)` → "I'll check back at 15:04."
- *(jump cut)* Right terminal: **⏰ Wake-up #1**, list_bucket, still missing, reschedules.
  > "Nobody prompted it. It woke itself up, checked, and went back to sleep."
- Upload the file live: `python scripts/drop_file.py`
- *(jump cut)* **⏰ Wake-up #2**, finds the file, summarise_csv, notify_user.
- Switch to the inbox: the email arrives with revenue by region. **Hold this shot for 2 s.**

Optionally flash the EventBridge Scheduler console showing the schedule, then show it auto-deleted.

### 2:20–2:45 · Why it matters
Show the eval table (BEFORE vs AFTER) and the safety-rail list for about 5 seconds.
> "It has guardrails: a max number of wake-ups, a hook that won't let it sleep again without re-checking, idempotent schedules, and an optional human approval interrupt. It's one tool, one hook and one Lambda, so any Strands agent can use it to follow up, poll a deploy or remind you tomorrow."

### 2:45–2:55 · Close
> "Before, the agent made me wait. Now it waits for me. Code's on GitHub."
End card: repo URL.

---

**Tips**
- Use `minutes_from_now` 1–2 for the recording. Scheduler fires within about a minute of the target.
- Speed up the waiting with cuts and a visible clock/timestamp so it doesn't feel faked.
- Upload to YouTube as **Public** or **Unlisted** (public is safest per the rules) and paste the link in the "demo" field.
