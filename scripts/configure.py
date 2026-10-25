"""Read the deployed CloudFormation stack outputs and write .env for the local CLI/worker.

    python scripts/configure.py --stack patience [--target lambda|sqs] [--region us-east-1]
"""

import argparse
from pathlib import Path

import boto3

ap = argparse.ArgumentParser()
ap.add_argument("--stack", default="patience")
ap.add_argument("--target", choices=["lambda", "sqs"], default="lambda")
ap.add_argument("--region", default=None)
ap.add_argument("--model", default="us.amazon.nova-pro-v1:0")
ap.add_argument("--notify-from", default="")
ap.add_argument("--notify-to", default="")
a = ap.parse_args()

cf = boto3.client("cloudformation", region_name=a.region)
stack = cf.describe_stacks(StackName=a.stack)["Stacks"][0]
out = {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}
region = a.region or cf.meta.region_name

env = {
    "AWS_REGION": region,
    "PATIENCE_MODEL_ID": a.model,
    "PATIENCE_BUCKET": out["Bucket"],
    "PATIENCE_GROUP": out["ScheduleGroupName"],
    "PATIENCE_SCHEDULER_ROLE": out["SchedulerRoleArn"],
    "PATIENCE_TARGET_ARN": out["WakeFunctionArn"] if a.target == "lambda" else out["WakeQueueArn"],
    "PATIENCE_QUEUE_URL": out["WakeQueueUrl"],
    "PATIENCE_NOTIFY_FROM": a.notify_from,
    "PATIENCE_NOTIFY_TO": a.notify_to,
}
path = Path(__file__).resolve().parent.parent / ".env"
path.write_text("".join(f"{k}={v}\n" for k, v in env.items()))
print(f"Wrote {path}")
for k, v in env.items():
    print(f"  {k}={v}")
