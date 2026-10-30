"""
Automated pipeline orchestrator.

Flow: Discover → Filter → Enrich → Personalize → Send → Log → Notify

Key improvements vs. original:
  - Pipeline stages are defined ONCE here (no duplication with main.py)
  - main.py calls these same functions for its manual endpoints
  - Retry on transient network errors via tenacity
  - Fresh BackgroundScheduler created each time to avoid ThreadPoolExecutor
    "cannot schedule new futures after shutdown" error
  - Slack summary after every run
"""

import json
import logging
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from notifier import notify_slack
from database import get_db
from models import InfluencerRaw, InfluencerFiltered
from config import DATA_SOURCE

logger = logging.getLogger("automation")
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers= [
        logging.FileHandler("automation.log"),
        logging.StreamHandler(),
    ],
)

# ─── Shared scheduler state ───────────────────────────────────────────────────

_lock           = threading.Lock()
_scheduler: BackgroundScheduler | None = None
_current_config = {"niche": "fitness", "interval_minutes": 30}


# ─── Adapter factory ──────────────────────────────────────────────────────────

def _make_adapter():
    if DATA_SOURCE == "apify":
        from discovery.apify_adapter import ApifyAdapter
        return ApifyAdapter()
    from discovery.mock_adapter import MockAdapter
    return MockAdapter()


# ─── Pipeline stages (single authoritative definitions) ───────────────────────

def stage_discover(niche: str = "fitness", limit: int = 50) -> int:
    """Discover influencers and insert new ones into the DB. Returns new count."""
    from filtering  import filter_and_classify
    from enrichment import enrich_profiles

    adapter = _make_adapter()
    raw     = adapter.discover(niche, limit)

    db       = get_db()
    inserted = 0
    for inf in raw:
        cur = db.execute("""
            INSERT OR IGNORE INTO influencers
                (name, platform, profile_url, follower_count, engagement_rate,
                 niche, content_themes, contact_email, bio, recent_post_caption,
                 recent_post_url, audience_age, audience_gender,
                 audience_geography, website)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            inf.name, inf.platform, inf.profile_url, inf.follower_count,
            inf.engagement_rate, inf.niche, json.dumps(inf.content_themes),
            inf.contact_email, inf.bio, inf.recent_post_caption,
            inf.recent_post_url, inf.audience_age, inf.audience_gender,
            inf.audience_geography, inf.website,
        ))
        inserted += cur.rowcount
    db.commit()
    db.close()

    logger.info(f"[DISCOVER] fetched={len(raw)} new_inserted={inserted} niche={niche}")
    return inserted


def stage_filter(niche: str = "fitness") -> int:
    """Run filter + enrichment on all unprocessed influencers. Returns passed count."""
    from filtering  import filter_and_classify
    from enrichment import enrich_profiles

    db   = get_db()
    rows = db.execute("SELECT * FROM influencers").fetchall()
    db.close()

    raw = [InfluencerRaw(
        name               = r["name"],
        platform           = r["platform"],
        profile_url        = r["profile_url"],
        follower_count     = r["follower_count"],
        engagement_rate    = r["engagement_rate"],
        niche              = r["niche"],
        content_themes     = json.loads(r["content_themes"] or "[]"),
        contact_email      = r["contact_email"],
        bio                = r["bio"],
        recent_post_caption= r["recent_post_caption"],
        recent_post_url    = r["recent_post_url"],
        audience_age       = r["audience_age"],
        audience_gender    = r["audience_gender"],
        audience_geography = r["audience_geography"],
        website            = r["website"],
    ) for r in rows]

    enriched = enrich_profiles(filter_and_classify(raw, niche))

    db = get_db()
    for inf in enriched:
        db.execute("""
            UPDATE influencers
            SET passed_filter=?, filter_reason=?, category=?,
                contact_email=?, engagement_rate=?
            WHERE profile_url=?
        """, (
            1 if inf.passed_filter else 0,
            inf.filter_reason, inf.category,
            inf.contact_email, inf.engagement_rate,
            inf.profile_url,
        ))
    db.commit()
    db.close()

    passed = sum(1 for i in enriched if i.passed_filter)
    logger.info(f"[FILTER] total={len(enriched)} passed={passed} niche={niche}")
    return passed


def stage_send() -> int:
    """
    Personalize and send outreach to all qualifying influencers not yet contacted.
    Returns count of emails sent.
    """
    from personalization import generate_messages
    from sending import send_outreach

    db   = get_db()
    rows = db.execute("""
        SELECT i.*
        FROM influencers i
        WHERE i.passed_filter = 1
          AND i.contact_email IS NOT NULL
          AND i.contact_email != 'Not Found'
          AND NOT EXISTS (
              SELECT 1 FROM outreach_log o
              WHERE o.influencer_id = i.id AND o.platform = 'email'
          )
        ORDER BY i.engagement_rate DESC
    """).fetchall()
    db.close()

    sent_count = 0
    for idx, r in enumerate(rows):
        try:
            inf = InfluencerFiltered(
                name               = r["name"],
                platform           = r["platform"],
                profile_url        = r["profile_url"],
                follower_count     = r["follower_count"],
                engagement_rate    = r["engagement_rate"],
                niche              = r["niche"],
                content_themes     = json.loads(r["content_themes"] or "[]"),
                contact_email      = r["contact_email"],
                bio                = r["bio"],
                recent_post_caption= r["recent_post_caption"],
                recent_post_url    = r["recent_post_url"],
                audience_age       = r["audience_age"],
                audience_gender    = r["audience_gender"],
                audience_geography = r["audience_geography"],
                website            = r["website"],
                passed_filter      = True,
                filter_reason      = r["filter_reason"],
                category           = r["category"],
            )
            subject, body, dm = generate_messages(inf, index=idx)
            result = send_outreach(inf, subject, body, dm)

            if result["status"].startswith("sent"):
                sent_count += 1
            logger.info(f"[SEND] {inf.name} :{result['status']}")

        except Exception as exc:
            logger.error(f"[SEND ERROR] {r['name']}: {exc}")

    logger.info(f"[SEND] completed sent={sent_count}")
    return sent_count


# ─── Retry wrapper ─────────────────────────────────────────────────────────────

@retry(
    stop   = stop_after_attempt(3),
    wait   = wait_exponential(multiplier=1, min=2, max=30),
    retry  = retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    reraise= True,
)
def _with_retry(fn, *args, **kwargs):
    return fn(*args, **kwargs)


# ─── Full pipeline ─────────────────────────────────────────────────────────────

def run_full_pipeline(niche: str = "fitness", limit: int = 50) -> dict:
    """
    Execute all pipeline stages sequentially with retry.
    Returns a results dict { stage → 'ok' | 'failed: <reason>' }.
    """
    logger.info("=" * 60)
    logger.info(f"PIPELINE START niche={niche} at {datetime.now().isoformat()}")

    results: dict[str, str] = {}
    for name, fn in (
        ("discover", lambda: stage_discover(niche, limit)),
        ("filter",   lambda: stage_filter(niche)),
        ("send",     stage_send),
    ):
        try:
            value          = _with_retry(fn)
            results[name]  = f"ok ({value})"
            logger.info(f"[{name.upper()}] OK : {value}")
        except Exception as exc:
            results[name] = f"failed: {exc}"
            logger.error(f"[{name.upper()}] FAILED after retries: {exc}")

    logger.info("PIPELINE END")
    logger.info("=" * 60)

    # ── Slack summary ─────────────────────────────────────────────────────────
    try:
        ok_count = sum(1 for v in results.values() if v.startswith("ok"))
        total    = len(results)
        icon     = "✅" if ok_count == total else ("⚠️" if ok_count > 0 else "❌")
        msg = (
            f"{icon} *Influencer Pipeline* — niche=`{niche}`\n"
            + "\n".join(f"• {k.title()}: {v}" for k, v in results.items())
            + f"\n• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        notify_slack(msg)
    except Exception as exc:
        logger.warning(f"Slack summary failed (non-fatal): {exc}")

    return results


# ─── Scheduler control ────────────────────────────────────────────────────────

def start_scheduler(niche: str = "fitness", interval_minutes: int = 30) -> None:
    """
    Start a fresh BackgroundScheduler.  Always creates a new instance
    so the thread pool is clean (avoids post-shutdown RuntimeError).
    """
    global _scheduler, _current_config

    with _lock:
        # Cleanly shut down any existing scheduler
        if _scheduler is not None:
            try:
                if _scheduler.running:
                    _scheduler.shutdown(wait=False)
            except Exception as exc:
                logger.warning(f"Old scheduler shutdown warning: {exc}")
            _scheduler = None

        _scheduler = BackgroundScheduler()
        _scheduler.add_job(
            run_full_pipeline,
            trigger          = IntervalTrigger(minutes=interval_minutes),
            id               = "full_pipeline",
            kwargs           = {"niche": niche},
            replace_existing = True,
            next_run_time    = datetime.now(),   # run immediately on start
            max_instances    = 1,
            coalesce         = True,
            misfire_grace_time = 60,
        )
        _scheduler.start()
        _current_config = {"niche": niche, "interval_minutes": interval_minutes}
        logger.info(f"Scheduler started: every {interval_minutes} min (niche={niche})")


def stop_scheduler() -> None:
    global _scheduler
    with _lock:
        if _scheduler is not None:
            try:
                if _scheduler.running:
                    _scheduler.shutdown(wait=False)
                    logger.info("Scheduler stopped")
            except Exception as exc:
                logger.warning(f"Scheduler stop warning: {exc}")
            finally:
                _scheduler = None


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running


def get_status() -> dict:
    with _lock:
        if _scheduler is None or not _scheduler.running:
            return {"running": False, "jobs": [], "config": _current_config}
        jobs = [
            {"id": j.id, "next_run": str(j.next_run_time) if j.next_run_time else None}
            for j in _scheduler.get_jobs()
        ]
        return {"running": True, "jobs": jobs, "config": _current_config}
