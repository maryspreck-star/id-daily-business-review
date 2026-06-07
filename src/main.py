import datetime
import sys

from src.collectors.snowflake   import fetch_all
from src.collectors.deals       import fetch_deals
from src.collectors.slack_notes import fetch_slack_notes
from src.synthesizer            import synthesize
from src.renderer               import render
from src.email_sender           import send


def _safe(fn, fallback):
    """Call fn(); return fallback if it raises (non-fatal collector failure)."""
    try:
        return fn()
    except Exception as exc:
        print(f"[warn] {getattr(fn, '__name__', repr(fn))} failed: {exc}", file=sys.stderr)
        return fallback


def main() -> None:
    today     = datetime.date.today()
    is_monday = today.weekday() == 0

    data = {
        **fetch_all(),
        "deals": _safe(
            fetch_deals,
            {"inbound_mtd": 0, "inbound_yesterday": 0,
             "cvr_14day_mtd": 0.0, "cvr_meaningful_mtd": 0.0,
             "by_studio": [], "by_rep": []},
        ),
        "slack_notes": _safe(
            fetch_slack_notes,
            {"messages": [], "channel": "#id--retail-closing-notes"},
        ),
    }

    narrative = synthesize(data, is_monday=is_monday)
    html      = render(data, narrative, is_monday=is_monday)

    day_label = "Monday Mode — " if is_monday else ""
    subject   = f"Interior Define Daily Review — {day_label}{today.strftime('%a %b %-d, %Y')}"

    send(html, subject)
    print(f"[ok] Report sent: {subject}", file=sys.stderr)


if __name__ == "__main__":
    main()
