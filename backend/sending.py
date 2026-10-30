"""
Sending layer.

Responsibilities:
  - Select influencers with a valid contact email
  - Send or simulate sending the personalized email
  - Record sending status in outreach_log
  - Prevent duplicate outreach (UNIQUE constraint + pre-check)
  - Maintain a queryable outreach log
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from database import get_db
from config import SEND_MODE, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, BRAND_NAME
from models import InfluencerFiltered

logger = logging.getLogger(__name__)


def _get_influencer_id(db, profile_url: str) -> int:
    row = db.execute(
        "SELECT id FROM influencers WHERE profile_url = ?", (profile_url,)
    ).fetchone()
    return int(row["id"]) if row else 0


def _log_outreach(
    db,
    influencer: InfluencerFiltered,
    subject: str,
    body: str,
    dm_text: str,
    status: str,
    error: str | None,
) -> None:
    iid = _get_influencer_id(db, influencer.profile_url)
    sent_at = datetime.now().isoformat() if status.startswith("sent") else None
    db.execute(
        """
        INSERT INTO outreach_log
            (influencer_id, platform, email, email_subject, email_body,
             dm_text, sent_at, status, error_message)
        VALUES (?, 'email', ?, ?, ?, ?, ?, ?, ?)
        """,
        (iid, influencer.contact_email, subject, body,
         dm_text, sent_at, status, error),
    )
    db.commit()


def _is_already_sent(db, influencer_id: int) -> bool:
    row = db.execute(
        "SELECT id FROM outreach_log WHERE influencer_id = ? AND platform = 'email'",
        (influencer_id,),
    ).fetchone()
    return row is not None


def _send_smtp(to_email: str, subject: str, body: str) -> None:
    """Raises on any SMTP error so the caller can record the failure."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{BRAND_NAME} <{SMTP_USER}>"
    msg["To"]      = to_email

    # Plain-text part
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


def send_outreach(
    influencer: InfluencerFiltered,
    subject: str,
    body: str,
    dm_text: str,
) -> dict:
    """
    Attempt to send an outreach email to one influencer.
    Returns a dict with status, email, and optional error.
    """
    db  = get_db()
    iid = _get_influencer_id(db, influencer.profile_url)

    # ── Duplicate guard ───────────────────────────────────────────────────────
    if _is_already_sent(db, iid):
        db.close()
        logger.info(f"[Send] Skipped (duplicate): {influencer.name}")
        return {"status": "skipped", "reason": "Already contacted", "email": influencer.contact_email}

    # ── Email validation ──────────────────────────────────────────────────────
    email = influencer.contact_email
    if not email or email == "Not Found":
        _log_outreach(db, influencer, subject, body, dm_text, "skipped_no_email", "No valid email")
        db.close()
        logger.info(f"[Send] Skipped (no email): {influencer.name}")
        return {"status": "skipped_no_email", "reason": "No valid email", "email": None}

    # ── Send ──────────────────────────────────────────────────────────────────
    if SEND_MODE == "smtp" and SMTP_USER and SMTP_PASS:
        try:
            _send_smtp(email, subject, body)
            status = "sent"
            error  = None
            logger.info(f"[Send] SMTP sent : {influencer.name} <{email}>")
        except Exception as exc:
            status = "failed"
            error  = str(exc)
            logger.error(f"[Send] SMTP failed : {influencer.name}: {exc}")
    else:
        # Simulate mode — records as sent without actually emailing
        status = "sent (simulated)"
        error  = None
        logger.info(f"[Send] Simulated : {influencer.name} <{email}>")

    _log_outreach(db, influencer, subject, body, dm_text, status, error)
    db.close()
    return {"status": status, "email": email, "error": error}


def get_outreach_log() -> list[dict]:
    """Return all outreach log entries joined with influencer name and platform."""
    db   = get_db()
    rows = db.execute("""
        SELECT
            o.id, i.name, i.platform, i.profile_url,
            o.email, o.email_subject, o.email_body, o.dm_text,
            o.sent_at, o.status, o.error_message
        FROM outreach_log o
        JOIN influencers i ON o.influencer_id = i.id
        ORDER BY o.id DESC
    """).fetchall()
    db.close()
    return [dict(r) for r in rows]
