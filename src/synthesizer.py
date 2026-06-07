import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

_SYSTEM_PROMPT = """You are writing the Interior Define Daily Business Review — a morning email that gives the GM a fast read on yesterday's performance and what to watch.

Output ONLY valid JSON with these exact keys:
- "tldr": 1-2 sentence HTML string (may use <strong>) summarizing the day vs expectations
- "yesterday_story": 2-4 sentence HTML prose about yesterday — be specific with numbers, highlight what drove performance
- "watch_items": array of {"tag": string, "text": string} objects — 2-3 items flagging anomalies or trends to monitor

Rules:
- Use actual numbers from the data (revenue, orders, AOV, CVR, engagements)
- Frame YoY comparisons when data is available (▲/▼ language)
- watch_items tags are short labels like "AOV", "CVR", "Trade", "Engagements"
- Do not make up data not present in the input
- Closing notes from Slack (if present) may surface qualitative context"""


def synthesize(data: dict, is_monday: bool = False) -> dict:
    """Call Claude API to generate narrative HTML snippets from the data dict."""
    client = anthropic.Anthropic()

    slack_notes = data.get("slack_notes", {}).get("messages", [])
    notes_section = ""
    if slack_notes:
        notes_section = "\n\nClosing notes from #id--retail-closing-notes:\n" + "\n".join(f"- {m}" for m in slack_notes[:10])

    monday_note = "\nThis is a MONDAY report — include last-week context in the tldr and yesterday_story.\n" if is_monday else ""

    user_content = (
        f"{monday_note}"
        f"Data (JSON):\n{json.dumps(data, indent=2, default=str)}"
        f"{notes_section}"
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=[{
            "type": "text",
            "text": _SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_content}],
    )

    return json.loads(response.content[0].text)
