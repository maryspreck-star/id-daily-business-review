# scripts/smoke_test.py
import json
import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collectors.snowflake import fetch_all


def _serialize(obj):
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


if __name__ == "__main__":
    print("Running fetch_all() against live Snowflake...", file=sys.stderr)
    data = fetch_all()
    print(json.dumps(data, indent=2, default=_serialize))
