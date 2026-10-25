"""AWS Lambda entry point: EventBridge Scheduler delivers the wake-up payload here."""

import json
import logging

from patience.agent import handle_wakeup

logging.getLogger().setLevel(logging.INFO)


def lambda_handler(event, context):
    payload = event if "patience" in event else json.loads(event.get("body", "{}"))
    logging.info("Wake-up #%s chain=%s", payload.get("wake_depth"), payload.get("chain_id"))
    result = handle_wakeup(payload, callback_handler=None)
    return {"chain_id": payload["chain_id"], "wake_depth": payload["wake_depth"], "reply": str(result)[:2000]}
