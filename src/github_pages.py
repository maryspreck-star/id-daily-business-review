import base64
import os

import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = "maryspreck-star/id-daily-business-review"
PAGE_URL     = "https://maryspreck-star.github.io/id-daily-business-review/"


def push_report_page(html: str, date_label: str) -> str | None:
    if not GITHUB_TOKEN:
        print("  ⚠  No GITHUB_TOKEN — skipping GitHub Pages publish")
        return None

    encoded = base64.b64encode(html.encode()).decode()
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }

    # Get current sha so we can update in-place (required by GitHub API)
    r = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/index.html",
        headers=headers,
        params={"ref": "gh-pages"},
    )
    body = {"message": f"Report {date_label}", "content": encoded, "branch": "gh-pages"}
    if r.ok:
        body["sha"] = r.json()["sha"]

    r2 = requests.put(
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/index.html",
        headers=headers,
        json=body,
    )
    if r2.ok:
        print(f"✅  Published to {PAGE_URL}")
        return PAGE_URL

    print(f"  ⚠  Page publish failed: {r2.status_code} {r2.text[:300]}")
    return None


def post_slack_link(page_url: str, subject: str) -> None:
    token      = os.environ.get("SLACK_BOT_TOKEN", "")
    channel_id = os.environ.get("SLACK_REPORT_CHANNEL_ID", "")
    if not token or not channel_id:
        print("  ⚠  SLACK_BOT_TOKEN or SLACK_REPORT_CHANNEL_ID not set — skipping Slack post")
        return

    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "channel": channel_id,
            "text": f"📊 *{subject}*\n<{page_url}|View Report →>",
        },
    )
    data = r.json()
    if data.get("ok"):
        print("✅  Slack link posted")
    else:
        print(f"  ⚠  Slack post failed: {data.get('error')}")
