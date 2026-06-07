import datetime
import os
import time
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()

_CHANNEL_ID   = "C08MYB2S3DH"
_CHANNEL_NAME = "#id--retail-closing-notes"


def fetch_slack_notes() -> dict:
    """Read last 24h of messages from #id--retail-closing-notes. Non-fatal on error."""
    oldest = time.time() - 86400  # 24 hours ago

    try:
        client   = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        response = client.conversations_history(
            channel=_CHANNEL_ID,
            oldest=str(oldest),
            limit=50,
        )
        messages = [m["text"] for m in response["messages"] if m.get("text")]
    except (SlackApiError, KeyError):
        messages = []

    return {
        "channel":  _CHANNEL_NAME,
        "messages": messages,
        "date":     datetime.date.today(),
    }
