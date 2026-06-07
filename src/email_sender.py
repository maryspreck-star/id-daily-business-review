import os
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

load_dotenv()


def send(html: str, subject: str) -> None:
    """Send the HTML email via SendGrid. Raises RuntimeError on non-202 response."""
    message = Mail(
        from_email=os.environ["EMAIL_FROM"],
        to_emails=os.environ["EMAIL_TO"],
        subject=subject,
        html_content=html,
    )
    client   = SendGridAPIClient(os.environ["SENDGRID_API_KEY"])
    response = client.send(message)

    if response.status_code != 202:
        raise RuntimeError(
            f"SendGrid returned status {response.status_code}: {response.body}"
        )
