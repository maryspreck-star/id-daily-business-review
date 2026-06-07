import pytest
from unittest.mock import MagicMock, patch


_SAMPLE_DATA = {
    "report_date": "2026-06-06",
    "yesterday": {"revenue_total": 320000, "orders_total": 112, "aov_blended": 2857,
                  "revenue_b2c": 235000, "revenue_trade": 72000, "revenue_havenly": 13000,
                  "orders_b2c": 84, "orders_trade": 22, "orders_havenly": 6,
                  "aov_b2c": 2797.0, "aov_trade": 3272.0, "assisted_pct": 0.67, "upt": 2.15},
    "mtd": {"revenue_total": 4200000, "revenue_total_ly": 4800000, "orders_total": 1480},
    "engagements": {"yesterday": 315, "yesterday_ly": 323, "weekly_rolling": []},
    "swatches": {"mtd_orders": 8200, "mtd_customers": 6900, "monthly_rolling": []},
}

_SAMPLE_OUTPUT = '{"tldr": "<p>Solid Friday.</p>", "yesterday_story": "<p>NBE <strong>$320K</strong>.</p>", "watch_items": [{"tag": "AOV", "text": "Soft at $2,718"}]}'


def test_synthesize_returns_required_keys():
    """synthesize() returns dict with tldr, yesterday_story, watch_items."""
    from src.synthesizer import synthesize

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=_SAMPLE_OUTPUT)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("src.synthesizer.anthropic.Anthropic", return_value=mock_client):
        result = synthesize(_SAMPLE_DATA)

    assert "tldr" in result
    assert "yesterday_story" in result
    assert "watch_items" in result
    assert isinstance(result["watch_items"], list)


def test_synthesize_monday_mode_passes_flag():
    """synthesize() includes Monday context in prompt when is_monday=True."""
    from src.synthesizer import synthesize

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=_SAMPLE_OUTPUT)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("src.synthesizer.anthropic.Anthropic", return_value=mock_client):
        synthesize(_SAMPLE_DATA, is_monday=True)

    call_args = mock_client.messages.create.call_args
    user_content = call_args.kwargs["messages"][0]["content"]
    assert "Monday" in user_content or "monday" in user_content.lower()


def test_synthesize_passes_slack_notes():
    """synthesize() includes Slack notes in prompt when provided."""
    from src.synthesizer import synthesize

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=_SAMPLE_OUTPUT)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    data_with_notes = {**_SAMPLE_DATA, "slack_notes": {"messages": ["Chicago closed 3 big ones"]}}

    with patch("src.synthesizer.anthropic.Anthropic", return_value=mock_client):
        synthesize(data_with_notes)

    call_args = mock_client.messages.create.call_args
    user_content = call_args.kwargs["messages"][0]["content"]
    assert "Chicago" in user_content
