"""
FastAPI application — Micro-Influencer Outreach System

Manual endpoints  (step-by-step via UI):
  POST /api/discover       – run discovery
  POST /api/filter         – run filtering + enrichment
  POST /api/personalize    – generate AI messages (preview only, no send)
  POST /api/send           – send / simulate outreach
  GET  /api/log            – outreach tracker
  GET  /api/stats          – pipeline stats

Automation endpoints:
  POST /api/automation/start      – start scheduled pipeline
  POST /api/automation/stop       – stop scheduler
  POST /api/automation/run-once   – run pipeline once immediately
  GET  /api/automation/status     – scheduler status

Export endpoints:
  GET /api/export/influencers.csv
  GET /api/export/messages.csv
"""

import csv
import io
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from database import init_db, get_db
from models import InfluencerRaw, InfluencerFiltered
from config import DATA_SOURCE
from automation import (
    start_scheduler, stop_scheduler, run_full_pipeline, get_status,
    stage_discover, stage_filter, stage_send,
)
from personalization import generate_messages
from sending import send_outreach, get_outreach_log

logger = logging.getLogger(__name__)


# ─── Lifespan (replaces deprecated @app.on_event) ────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialised")
    yield
    stop_scheduler()
    logger.info("Scheduler stopped on shutdown")


app = FastAPI(title="Micro-Influencer Outreach System", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins  = ["*"],
    allow_methods  = ["*"],
    allow_headers  = ["*"],
)

app.mount("/static", StaticFiles(directory="../frontend"), name="static")


# ─── Root ─────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return FileResponse("../frontend/index.html")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_adapter():
    if DATA_SOURCE == "apify":
        from discovery.apify_adapter import ApifyAdapter
        return ApifyAdapter()
    from discovery.mock_adapter import MockAdapter
    return MockAdapter()


def _row_to_filtered(r) -> InfluencerFiltered:
    return InfluencerFiltered(
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
        passed_filter      = bool(r["passed_filter"]),
        filter_reason      = r["filter_reason"] or "",
        category           = r["category"] or "other",
    )


# ─── Manual pipeline endpoints ────────────────────────────────────────────────

@app.post("/api/discover")
def discover(
    niche: str = Query("fitness"),
    limit: int = Query(50, ge=10, le=200),
):
    """Discover influencers and store them in the database."""
    try:
        adapter  = _make_adapter()
        raw_list = adapter.discover(niche, limit)
    except Exception as exc:
        raise HTTPException(500, f"Discovery failed: {exc}")

    if len(raw_list) < 50:
        raise HTTPException(400, f"Only found {len(raw_list)} influencers (need ≥ 50).")

    db = get_db()
    inserted = 0
    for inf in raw_list:
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

    return {
        "count":       len(raw_list),
        "new":         inserted,
        "influencers": [i.model_dump() for i in raw_list],
    }


@app.post("/api/filter")
def filter_influencers(niche: str = Query("fitness")):
    """Apply filtering + enrichment to all discovered influencers."""
    from filtering  import filter_and_classify
    from enrichment import enrich_profiles

    db   = get_db()
    rows = db.execute("SELECT * FROM influencers").fetchall()
    db.close()

    if not rows:
        raise HTTPException(400, "No influencers in database. Run /api/discover first.")

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

    passed = [i for i in enriched if i.passed_filter]
    failed = [i for i in enriched if not i.passed_filter]

    return {
        "total":       len(enriched),
        "passed":      len(passed),
        "failed":      len(failed),
        "passed_list": [i.model_dump() for i in passed],
        "failed_list": [i.model_dump() for i in failed],
    }


@app.post("/api/personalize")
def personalize():
    """Preview AI-generated messages for all passed influencers (does NOT send)."""
    db   = get_db()
    rows = db.execute("SELECT * FROM influencers WHERE passed_filter = 1").fetchall()
    db.close()

    if not rows:
        raise HTTPException(400, "No passed influencers. Run /api/filter first.")

    out = []
    for idx, r in enumerate(rows):
        inf = _row_to_filtered(r)
        subject, body, dm = generate_messages(inf, index=idx)
        out.append({
            "influencer":    inf.model_dump(),
            "email_subject": subject,
            "email_body":    body,
            "dm_text":       dm,
        })

    return {"count": len(out), "messages": out}


@app.post("/api/send")
def send_all():
    """Send (or simulate sending) outreach to all qualifying influencers."""
    db   = get_db()
    rows = db.execute("SELECT * FROM influencers WHERE passed_filter = 1").fetchall()
    db.close()

    if not rows:
        raise HTTPException(400, "No passed influencers. Run /api/filter first.")

    results = []
    for idx, r in enumerate(rows):
        inf = _row_to_filtered(r)
        subject, body, dm = generate_messages(inf, index=idx)
        res = send_outreach(inf, subject, body, dm)
        results.append({"influencer": inf.name, "email": inf.contact_email, **res})

    return {"sent": results}


@app.get("/api/log")
def log():
    """Return the full outreach tracker log."""
    return {"log": get_outreach_log()}


@app.get("/api/stats")
def stats():
    """Return pipeline summary statistics."""
    db      = get_db()
    total   = db.execute("SELECT COUNT(*) c FROM influencers").fetchone()["c"]
    passed  = db.execute("SELECT COUNT(*) c FROM influencers WHERE passed_filter=1").fetchone()["c"]
    sent    = db.execute("SELECT COUNT(*) c FROM outreach_log WHERE status LIKE 'sent%'").fetchone()["c"]
    skipped = db.execute("SELECT COUNT(*) c FROM outreach_log WHERE status LIKE 'skipped%'").fetchone()["c"]
    failed  = db.execute("SELECT COUNT(*) c FROM outreach_log WHERE status='failed'").fetchone()["c"]
    db.close()
    return {
        "total": total, "passed": passed,
        "sent": sent, "skipped": skipped, "failed": failed,
    }


# ─── Automation endpoints ─────────────────────────────────────────────────────

@app.post("/api/automation/start")
def auto_start(niche: str = Query("fitness"), interval_minutes: int = Query(30, ge=1)):
    start_scheduler(niche, interval_minutes)
    return {"status": "started", "niche": niche, "interval_minutes": interval_minutes}


@app.post("/api/automation/stop")
def auto_stop():
    stop_scheduler()
    return {"status": "stopped"}


@app.post("/api/automation/run-once")
def auto_run_once(niche: str = Query("fitness")):
    results = run_full_pipeline(niche)
    return {"status": "completed", "results": results}


@app.get("/api/automation/status")
def auto_status():
    return get_status()


# ─── Export endpoints ─────────────────────────────────────────────────────────

@app.get("/api/export/influencers.csv")
def export_influencers_csv():
    """Download influencer dataset as CSV."""
    db   = get_db()
    rows = db.execute("""
        SELECT name, platform, profile_url, follower_count, engagement_rate,
               niche, content_themes, contact_email, bio,
               audience_age, audience_gender, audience_geography, website,
               passed_filter, filter_reason, category, discovered_at
        FROM influencers
        ORDER BY passed_filter DESC, engagement_rate DESC
    """).fetchall()
    db.close()

    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow([
        "Name", "Platform", "Profile URL", "Followers", "Engagement %",
        "Niche", "Content Themes", "Contact Email", "Bio",
        "Audience Age", "Audience Gender", "Audience Geography", "Website",
        "Passed Filter", "Filter Reason", "Category", "Discovered At",
    ])
    for r in rows:
        w.writerow([
            r["name"], r["platform"], r["profile_url"],
            r["follower_count"], r["engagement_rate"],
            r["niche"], r["content_themes"], r["contact_email"], r["bio"],
            r["audience_age"], r["audience_gender"], r["audience_geography"],
            r["website"],
            "Yes" if r["passed_filter"] else "No",
            r["filter_reason"], r["category"], r["discovered_at"],
        ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type = "text/csv",
        headers    = {"Content-Disposition": "attachment; filename=influencers.csv"},
    )


@app.get("/api/export/messages.csv")
def export_messages_csv():
    """Download outreach messages and log as CSV."""
    db   = get_db()
    rows = db.execute("""
        SELECT i.name, i.platform, i.niche, i.follower_count,
               o.email, o.email_subject, o.email_body, o.dm_text,
               o.status, o.sent_at, o.error_message
        FROM outreach_log o
        JOIN influencers i ON o.influencer_id = i.id
        ORDER BY o.id DESC
    """).fetchall()
    db.close()

    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow([
        "Influencer", "Platform", "Niche", "Followers",
        "Email", "Subject", "Email Body", "DM Text",
        "Status", "Sent At", "Error",
    ])
    for r in rows:
        w.writerow([
            r["name"], r["platform"], r["niche"], r["follower_count"],
            r["email"], r["email_subject"], r["email_body"], r["dm_text"],
            r["status"], r["sent_at"], r["error_message"],
        ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type = "text/csv",
        headers    = {"Content-Disposition": "attachment; filename=messages.csv"},
    )
