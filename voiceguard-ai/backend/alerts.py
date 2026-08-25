"""Alert dispatch module.

Dispatches impersonation-risk alerts to configured channels.
Currently supports in-app logging (always on) and a console/log
channel.  SMS and e-mail channels are scaffolded; enable them by
setting the corresponding environment variables.

Environment variables
---------------------
ALERT_CONSOLE_ENABLED   : "true" / "false"  (default true)
ALERT_EMAIL_ENABLED     : "true" / "false"  (default false)
ALERT_SMS_ENABLED       : "true" / "false"  (default false)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

logger = logging.getLogger("voiceguard.alerts")

_CONSOLE_ENABLED = os.getenv("ALERT_CONSOLE_ENABLED", "true").lower() == "true"
_EMAIL_ENABLED = os.getenv("ALERT_EMAIL_ENABLED", "false").lower() == "true"
_SMS_ENABLED = os.getenv("ALERT_SMS_ENABLED", "false").lower() == "true"


def _build_message(alert: dict) -> str:
    """Compose a human-readable alert message."""
    return (
        f"[VoiceGuard AI] Risk alert — level={alert['level']} "
        f"score={alert['risk_score']} "
        f"analysis_id={alert['analysis_id']} "
        f"action='{alert['recommended_action']}'"
    )


def _dispatch_console(alert: dict) -> None:
    if not _CONSOLE_ENABLED:
        return
    message = _build_message(alert)
    if alert["level"] == "CRITICAL":
        logger.critical(message)
    elif alert["level"] == "HIGH":
        logger.warning(message)
    else:
        logger.info(message)


def _dispatch_email(alert: dict) -> None:
    """Email dispatch stub — implement with smtplib or SendGrid SDK."""
    if not _EMAIL_ENABLED:
        return
    # TODO: integrate with SMTP_HOST / SMTP_PORT / ALERT_EMAIL_RECIPIENTS env vars
    logger.debug("Email alert suppressed (not configured): %s", alert["analysis_id"])


def _dispatch_sms(alert: dict) -> None:
    """SMS dispatch stub — implement with Twilio or MSG91 SDK."""
    if not _SMS_ENABLED:
        return
    # TODO: integrate with SMS_API_KEY / SMS_RECIPIENT env vars
    logger.debug("SMS alert suppressed (not configured): %s", alert["analysis_id"])


def build_alert_events(
    analysis_id: str,
    risk_score: int,
    risk_level: str,
    recommended_action: str,
    indicators: list[str],
) -> list[dict]:
    """Return a list of alert event dicts for a given analysis result.

    Returns an empty list for LOW risk so the calling code can treat
    the returned list as truthy when action is required.
    """
    if risk_level == "LOW":
        return []

    event: dict = {
        "id": str(uuid4()),
        "analysis_id": analysis_id,
        "level": risk_level,
        "risk_score": risk_score,
        "recommended_action": recommended_action,
        "indicators": indicators,
        "channel": "in-app",
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
    }
    return [event]


def dispatch_alerts(alert_events: list[dict]) -> None:
    """Dispatch a list of alert events to all configured channels."""
    for event in alert_events:
        _dispatch_console(event)
        _dispatch_email(event)
        _dispatch_sms(event)
