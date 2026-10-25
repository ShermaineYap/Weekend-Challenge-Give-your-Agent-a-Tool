# Submission write-up (paste into the Builder Center project form)

**Title:** Patience: I gave my agent the ability to wait

**Tagline:** One EventBridge Scheduler tool lets a Strands agent come back later, on its own, and finish the job.

---

## The agent I started with

**Kopi** is a small data assistant I built with the **Strands Agents SDK** on **Amazon Bedrock (Nova Pro)** for a (fictional) Malaysian F&B company. It had three tools:

- `list_bucket`: see what's in the team's S3 data bucket
- `summarise_csv`: totals, means and group-by summaries of a CSV
- `notify_user`: email the user through Amazon SES

It was good at anything that could be done *right now*. But a lot of real requests aren't like that:

> "Finance is uploading q3_sales.csv this afternoon. When it lands, email me revenue by region."

Kopi checked the bucket, found nothing, and said: *"The file has not been uploaded yet. I will check again in an hour. Please wait."* It never did, because it couldn't. The agent had every tool it needed to do the work. What it was missing was **time**. Each agent run lives inside one request, so anything about "later" got handed back to the human.

## The one tool I added: `schedule_wakeup`

```python
@tool(context=True)
def schedule_wakeup(minutes_from_now: int, instruction: str, note_to_self: str, tool_context): ...
```

When the agent calls it, the tool books a **one-shot Amazon EventBridge Scheduler** schedule (`at(...)`, `ActionAfterCompletion=DELETE`). The schedule re-invokes the agent itself, through a Lambda function or an SQS queue, carrying a payload **the agent wrote for its future self**.

When the schedule fires, `handle_wakeup()` starts a fresh agent with the same tools. It tells the agent *"⏰ WAKE-UP #1, you scheduled this yourself 2 min ago"* and passes in the original request, the instruction and the note. The agent re-checks the world, then either finishes (and emails the result) or schedules another wake-up.

**Why this tool:** most "add a tool" ideas give an agent more *reach*: another API, another data source. This one gives it a new *dimension*. Monitoring, follow-ups, polling, reminders and retry-later all come from one primitive, and the model decides when to use it.

## What it can do now that it couldn't before

Same prompt, same model, same three tools, plus one:

1. Lists the bucket, no file → **schedules itself** for 2 minutes and tells me when it'll check
2. ⏰ Wakes up, still no file → **reschedules** (wake #2), carrying its notes forward
3. I upload the file → ⏰ wakes, finds it, summarises revenue by region, **emails me**, and stops

I never asked twice. The agent did the waiting.

## How it plugs into Strands (reusable pattern)

```python
from patience.wakeup import schedule_wakeup, WakeupGuard
agent = Agent(tools=[*your_tools, schedule_wakeup], hooks=[WakeupGuard()])
```

- **`ToolContext.invocation_state`** carries `wake_depth`, `chain_id` and `original_task` through the run without exposing them to the model as parameters.
- **`WakeupGuard` (a Strands `HookProvider`)** uses `BeforeToolCallEvent`. It sets `cancel_tool` if the agent tries to go back to sleep on a wake-up turn before re-checking anything, and it can call `event.interrupt(...)` for human approval (`PATIENCE_REQUIRE_APPROVAL=1`).
- **The payload is the memory.** A woken agent remembers nothing, so the tool's schema makes the model write `instruction` and `note_to_self`. State carries across time with no database.
- **Safety rails:** max chained wake-ups per task, a cap on how far ahead the agent can schedule, idempotent schedule names (retries don't create duplicates), Scheduler retry policy, least-privilege IAM (the agent can only create schedules in its own group and pass a single role).
- **Tested offline:** a scripted Strands `Model` drives the full sleep → wake → reschedule → finish loop in `pytest` with no AWS calls. `scripts/eval_before_after.py` measures the behaviour change on real Bedrock.

Any Strands agent can reuse it: point the schedule target at anything that calls `handle_wakeup(payload)` and deploy the SAM template.

## AWS services
Amazon Bedrock (Nova Pro), **Amazon EventBridge Scheduler**, AWS Lambda, Amazon SQS, Amazon S3, Amazon SES, AWS IAM, AWS SAM / CloudFormation

## Links
- Code: https://github.com/ShermaineYap/Weekend-Challenge-Give-your-Agent-a-Tool
- Demo video (< 3 min): <ADD YOUTUBE LINK>

## Eval results
The most surprising finding: **the original agent didn't just fail to follow up. It promised to.** In 3 of 5 cases it said things like *"I will check again in an hour. Please wait."* It had no way to do that. Giving it the tool turned empty promises into real ones.

| Prompt (needs waiting) | BEFORE | AFTER |
|---|---|---|
| When q3_sales.csv shows up in the bucket, email me revenue by region | ❌ empty promise | ✅ booked |
| Finance will upload q3_sales.csv this afternoon. Let me know the top region | ❌ empty promise | ✅ booked |
| Keep an eye on the bucket and tell me as soon as any new CSV arrives | ❌ empty promise | ✅ booked |
| Remind me tomorrow morning to review the Q3 numbers | ⚠️ asked me to come back | ✅ booked |
| Check the bucket every 30 minutes for the next 2 hours | — did nothing | ✅ booked |

| | BEFORE (3 tools) | AFTER (+ `schedule_wakeup`) |
|---|---|---|
| Follow-ups actually booked | **0 / 5** | **5 / 5** |
| Empty promises ("I'll check again…" with nothing booked) | **3 / 5** | **0 / 5** |
| Asked the human to come back | 1 / 5 | 0 / 5 |
| Unnecessary wake-ups on control prompts ("what's in the bucket?") | n/a | **0 / 2** |

*Amazon Nova Pro on Bedrock, `scripts/eval_before_after.py`, wake-ups in dry-run, empty bucket. Heuristic regex scoring; one control reply that described capabilities ("I'll notify you…") also matched the promise pattern.*

**Live run on AWS (us-east-1):** turn 1 checked the bucket and slept → ⏰ wake #1 fired on its own, re-checked, booked wake #2 → I uploaded the file → ⏰ wake #2 found it, summarised revenue by region (Johor RM151,947 top), notified me. The fired schedules deleted themselves; nothing was left behind.
