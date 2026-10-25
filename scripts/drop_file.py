"""Demo helper: upload (or remove) the Q3 sales CSV in the data bucket.

    python scripts/drop_file.py            # upload data/q3_sales.csv
    python scripts/drop_file.py --remove   # reset the demo
"""

import argparse
import os
import sys
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import patience  # noqa: E402,F401  (loads .env)

ap = argparse.ArgumentParser()
ap.add_argument("--remove", action="store_true")
a = ap.parse_args()

s3 = boto3.client("s3")
bucket = os.environ["PATIENCE_BUCKET"]
if a.remove:
    s3.delete_object(Bucket=bucket, Key="q3_sales.csv")
    print(f"🗑  removed s3://{bucket}/q3_sales.csv")
else:
    s3.upload_file(str(Path(__file__).resolve().parent.parent / "data" / "q3_sales.csv"), bucket, "q3_sales.csv")
    print(f"📤 uploaded s3://{bucket}/q3_sales.csv")
