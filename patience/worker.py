"""Local wake-up worker: drains the SQS wake queue and resumes the agent.

Use this when PATIENCE_TARGET_ARN points at the SQS queue (no Lambda deploy needed).

    python -m patience.worker
"""

import json
import os
import time

import boto3

from .agent import handle_wakeup


def main():
    url = os.environ["PATIENCE_QUEUE_URL"]
    sqs = boto3.client("sqs")
    print(f"⏳ Waiting for wake-ups on {url} … (Ctrl+C to stop)")
    while True:
        resp = sqs.receive_message(QueueUrl=url, WaitTimeSeconds=20, MaxNumberOfMessages=1)
        for m in resp.get("Messages", []):
            payload = json.loads(m["Body"])
            print(f"\n⏰ Wake-up #{payload['wake_depth']} for chain {payload['chain_id']}\n")
            try:
                handle_wakeup(payload)
            finally:
                sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
        time.sleep(0.5)


if __name__ == "__main__":
    main()
