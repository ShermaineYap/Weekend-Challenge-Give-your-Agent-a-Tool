"""The agent's original toolbox ("before"): look at S3, summarise a CSV, notify the user."""

from __future__ import annotations

import csv
import io
import os
from collections import defaultdict

import boto3
from strands import tool

BUCKET = os.environ.get("PATIENCE_BUCKET", "")
NOTIFY_FROM = os.environ.get("PATIENCE_NOTIFY_FROM", "")  # SES-verified address
NOTIFY_TO = os.environ.get("PATIENCE_NOTIFY_TO", "")

NOTIFICATIONS: list[dict] = []  # local record (used when SES isn't configured)


def _s3():
    return boto3.client("s3")


@tool
def list_bucket(prefix: str = "") -> dict:
    """List files in the team's S3 data bucket.

    Args:
        prefix: Optional key prefix (folder) to filter by, e.g. "reports/".
    """
    resp = _s3().list_objects_v2(Bucket=BUCKET, Prefix=prefix, MaxKeys=200)
    files = [
        {"key": o["Key"], "size_bytes": o["Size"], "last_modified": o["LastModified"].isoformat()}
        for o in resp.get("Contents", [])
    ]
    return {"status": "success", "content": [{"json": {"bucket": BUCKET, "prefix": prefix, "files": files}}]}


@tool
def summarise_csv(key: str, group_by: str = "", value_column: str = "") -> dict:
    """Read a CSV from the data bucket and compute a summary.

    Returns row count, columns, numeric column totals/means, and optionally
    totals of `value_column` grouped by `group_by`.

    Args:
        key: S3 key of the CSV file.
        group_by: Optional column to group by (e.g. "region").
        value_column: Optional numeric column to total per group (e.g. "revenue_myr").
    """
    body = _s3().get_object(Bucket=BUCKET, Key=key)["Body"].read().decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(body)))
    if not rows:
        return {"status": "success", "content": [{"json": {"key": key, "rows": 0}}]}

    cols = list(rows[0].keys())
    numeric = {}
    for c in cols:
        try:
            vals = [float(r[c]) for r in rows if r[c] != ""]
            numeric[c] = {"total": round(sum(vals), 2), "mean": round(sum(vals) / len(vals), 2)}
        except ValueError:
            pass

    summary = {"key": key, "rows": len(rows), "columns": cols, "numeric": numeric}
    if group_by and value_column and group_by in cols and value_column in numeric:
        groups: dict[str, float] = defaultdict(float)
        for r in rows:
            groups[r[group_by]] += float(r[value_column] or 0)
        summary["grouped"] = dict(sorted(((k, round(v, 2)) for k, v in groups.items()), key=lambda kv: -kv[1]))
    return {"status": "success", "content": [{"json": summary}]}


@tool
def notify_user(subject: str, message: str) -> str:
    """Send the user an email (Amazon SES). Use for finished results, not for questions.

    Args:
        subject: Short email subject.
        message: Plain-text body.
    """
    NOTIFICATIONS.append({"subject": subject, "message": message})
    if NOTIFY_FROM and NOTIFY_TO:
        boto3.client("sesv2").send_email(
            FromEmailAddress=NOTIFY_FROM,
            Destination={"ToAddresses": [NOTIFY_TO]},
            Content={"Simple": {"Subject": {"Data": subject}, "Body": {"Text": {"Data": message}}}},
        )
        return f"Email sent to {NOTIFY_TO}."
    print(f"\n📧 [notify_user] {subject}\n{message}\n")
    return "Notification recorded (SES not configured, printed to console)."


BASE_TOOLS = [list_bucket, summarise_csv, notify_user]
