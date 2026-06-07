"""End-to-end smoke test: runs full pipeline and saves HTML to disk for browser QA.
Does NOT send email. Open output/report.html in a browser after running.

Usage:
    cd /Users/mc.spreck/mary-claire-daily-business-review
    source venv/bin/activate
    python scripts/smoke_test.py
    open output/report.html

Add --monday to test Monday mode:
    python scripts/smoke_test.py --monday
"""
import json
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collectors.snowflake   import fetch_all
from src.collectors.deals       import fetch_deals
from src.collectors.slack_notes import fetch_slack_notes
from src.synthesizer            import synthesize
from src.renderer               import render


def _serialize(obj):
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


if __name__ == "__main__":
    is_monday = "--monday" in sys.argv

    print("Fetching Snowflake data...",    file=sys.stderr)
    snowflake_data = fetch_all()

    print("Fetching deal/CVR metrics...",  file=sys.stderr)
    deals_data = fetch_deals()

    print("Fetching Slack notes...",       file=sys.stderr)
    slack_data = fetch_slack_notes()

    data = {**snowflake_data, "deals": deals_data, "slack_notes": slack_data}

    print("Calling Claude synthesizer...", file=sys.stderr)
    narrative = synthesize(data, is_monday=is_monday)

    print("Rendering HTML...",             file=sys.stderr)
    html = render(data, narrative, is_monday=is_monday)

    os.makedirs("output", exist_ok=True)
    with open("output/report.html", "w") as f:
        f.write(html)

    with open("output/data.json", "w") as f:
        json.dump(data, f, indent=2, default=_serialize)

    print("Done. Open output/report.html in a browser.", file=sys.stderr)
    print(f"Narrative preview:", file=sys.stderr)
    print(f"  TL;DR:          {narrative.get('tldr', '')[:100]}", file=sys.stderr)
    print(f"  Watch items:    {len(narrative.get('watch_items', []))} item(s)", file=sys.stderr)
