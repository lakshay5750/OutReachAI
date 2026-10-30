import logging
from config import SLACK_WEBHOOK_URL

logger = logging.getLogger("notifier")


def notify_slack(message: str) -> None:
    """
    Send a Slack notification via incoming webhook.
    Silently no-ops if SLACK_WEBHOOK_URL is not configured.
    """
    if not SLACK_WEBHOOK_URL:
        safe_message = message.encode("ascii", errors="replace").decode("ascii")
        logger.info(f"[Slack disabled] {safe_message}")
        return
    try:
        from slack_sdk.webhook import WebhookClient
        client   = WebhookClient(SLACK_WEBHOOK_URL)
        response = client.send(text=message)
        if response.status_code != 200:
            logger.warning(f"Slack returned {response.status_code}: {response.body}")
    except Exception as exc:
        logger.error(f"Slack notification failed (non-fatal): {exc}")
