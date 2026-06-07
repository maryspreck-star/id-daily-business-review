import datetime
import pytest
from unittest.mock import MagicMock, patch


def test_fetch_slack_notes_returns_message_texts():
    """fetch_slack_notes() returns list of message text strings."""
    from src.collectors.slack_notes import fetch_slack_notes

    mock_response = {
        "messages": [
            {"text": "Chicago had a strong day — closed 3 big Trade orders", "ts": "1749168000.000"},
            {"text": "NYC slow morning but picked up after noon", "ts": "1749164400.000"},
        ],
        "has_more": False,
    }

    mock_client = MagicMock()
    mock_client.conversations_history.return_value = mock_response

    with patch("src.collectors.slack_notes.WebClient", return_value=mock_client):
        result = fetch_slack_notes()

    assert result["channel"] == "#id--retail-closing-notes"
    assert len(result["messages"]) == 2
    assert "Chicago" in result["messages"][0]


def test_fetch_slack_notes_empty_channel():
    """fetch_slack_notes() returns empty messages list when channel has no messages."""
    from src.collectors.slack_notes import fetch_slack_notes

    mock_client = MagicMock()
    mock_client.conversations_history.return_value = {"messages": [], "has_more": False}

    with patch("src.collectors.slack_notes.WebClient", return_value=mock_client):
        result = fetch_slack_notes()

    assert result["messages"] == []


def test_fetch_slack_notes_handles_api_error():
    """fetch_slack_notes() returns empty messages when Slack API fails (non-fatal)."""
    from src.collectors.slack_notes import fetch_slack_notes
    from slack_sdk.errors import SlackApiError

    mock_client = MagicMock()
    mock_client.conversations_history.side_effect = SlackApiError(
        "channel_not_found", {"error": "channel_not_found"}
    )

    with patch("src.collectors.slack_notes.WebClient", return_value=mock_client):
        result = fetch_slack_notes()

    assert result["messages"] == []
