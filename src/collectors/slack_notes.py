import datetime
import os
import time
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()

_CHANNEL_ID   = "C08MYB2S3DH"
_CHANNEL_NAME = "#id--retail-closing-notes"


def fetch_slack_notes(target_date: datetime.date | None = None) -> dict:
    """Read closing notes from #id--retail-closing-notes for a specific date.

    Defaults to yesterday (notes are posted in the evenings after close).
    Uses a 36-hour window (noon the target date through midnight+12h) to
    capture late-evening posts without pulling the next day's notes.
    """
    if target_date is None:
        target_date = datetime.date.today() - datetime.timedelta(days=1)

    # noon on target date → midnight + 12h to catch all evening posts
    oldest = datetime.datetime(target_date.year, target_date.month, target_date.day,
                               12, 0, 0, tzinfo=datetime.timezone.utc).timestamp()
    latest = datetime.datetime(target_date.year, target_date.month, target_date.day,
                               tzinfo=datetime.timezone.utc).timestamp() + 86400 + 43200  # +36h

    try:
        client   = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        response = client.conversations_history(
            channel=_CHANNEL_ID,
            oldest=str(oldest),
            latest=str(latest),
            limit=50,
        )
        messages = [m["text"] for m in response["messages"] if m.get("text")]
    except (SlackApiError, KeyError):
        messages = []

    return {
        "channel":  _CHANNEL_NAME,
        "messages": messages,
        "date":     target_date,
    }
