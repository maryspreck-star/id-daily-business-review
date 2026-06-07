import pytest
from unittest.mock import MagicMock, patch


def test_send_calls_sendgrid_with_html():
    """send() calls SendGrid API with HTML content and correct subject."""
    from src.email_sender import send

    mock_client = MagicMock()
    mock_client.send.return_value = MagicMock(status_code=202)

    with patch("src.email_sender.SendGridAPIClient", return_value=mock_client), \
         patch.dict("os.environ", {
             "SENDGRID_API_KEY": "test-key",
             "EMAIL_TO": "test@example.com",
             "EMAIL_FROM": "from@example.com",
         }):
        send("<html><body>Test</body></html>", "Test Subject")

    mock_client.send.assert_called_once()
    mail_arg = mock_client.send.call_args[0][0]
    assert mail_arg.subject.subject == "Test Subject"


def test_send_raises_on_non_202():
    """send() raises RuntimeError when SendGrid returns a non-202 status."""
    from src.email_sender import send

    mock_client = MagicMock()
    mock_client.send.return_value = MagicMock(status_code=400, body="Bad Request")

    with patch("src.email_sender.SendGridAPIClient", return_value=mock_client), \
         patch.dict("os.environ", {
             "SENDGRID_API_KEY": "test-key",
             "EMAIL_TO": "test@example.com",
             "EMAIL_FROM": "from@example.com",
         }):
        with pytest.raises(RuntimeError, match="400"):
            send("<html>Test</html>", "Subject")
