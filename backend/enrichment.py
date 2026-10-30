"""
Profile Enrichment module.

Enriches shortlisted influencer profiles by:
  1. Extracting emails embedded in bio text (regex)
  2. Attempting to find contact email from the influencer's linked website
     (looks for mailto: links and common contact-page patterns)
  3. Normalising all mandatory fields (never invents data)
  4. Marking truly unfindable emails as 'Not Found'

No third-party paid email-lookup API is required.
Real email extraction works when influencers list their email in their bio
(very common on Instagram and TikTok).
"""

import re
import logging
from typing import List, Optional
from models import InfluencerFiltered

logger = logging.getLogger(__name__)

# ─── Regex patterns ────────────────────────────────────────────────────────────

_EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# Words commonly used to obfuscate emails in bios
_OBFUSCATION_MAP = {
    " [at] ": "@", "[at]": "@",
    " (at) ": "@", "(at)": "@",
    " dot ":  ".", "[dot]": ".", "(dot)": ".",
}


def _deobfuscate(text: str) -> str:
    """Replace common email obfuscation patterns before regex matching."""
    for pattern, replacement in _OBFUSCATION_MAP.items():
        text = text.replace(pattern, replacement)
    return text


def _extract_email_from_text(text: str) -> Optional[str]:
    """
    Try to extract a valid email address from a plain-text string.
    Returns the first match or None.
    """
    if not text:
        return None
    clean = _deobfuscate(text)
    match = _EMAIL_REGEX.search(clean)
    if match:
        email = match.group(0).strip(".,;:")
        # Basic sanity check — must have a real TLD
        if "." in email.split("@")[-1]:
            return email
    return None


def _try_website_email(url: str) -> Optional[str]:
    """
    Attempt to scrape a contact email from the influencer's website.
    Checks the homepage and /contact page for mailto: links.
    Non-fatal — returns None on any error.
    """
    if not url:
        return None
    try:
        import httpx
        headers = {"User-Agent": "Mozilla/5.0 (compatible; OutreachBot/1.0)"}
        pages_to_try = [url.rstrip("/"), url.rstrip("/") + "/contact"]
        for page_url in pages_to_try:
            try:
                resp = httpx.get(page_url, headers=headers, timeout=5, follow_redirects=True)
                if resp.status_code == 200:
                    # Look for mailto: links first
                    mailto_matches = re.findall(r'mailto:([^\s"\'<>]+)', resp.text, re.IGNORECASE)
                    for m in mailto_matches:
                        email = m.strip(".,;:)")
                        if _EMAIL_REGEX.match(email):
                            logger.info(f"[Enrich] Found email via website {page_url}: {email}")
                            return email
                    # Fallback: look for bare email addresses in page text
                    found = _extract_email_from_text(resp.text[:20_000])
                    if found:
                        logger.info(f"[Enrich] Found email in page body {page_url}: {found}")
                        return found
            except Exception:
                continue
    except ImportError:
        logger.warning("[Enrich] httpx not installed — skipping website email lookup")
    except Exception as e:
        logger.debug(f"[Enrich] Website scrape failed for {url}: {e}")
    return None


def enrich_profiles(influencers: List[InfluencerFiltered]) -> List[InfluencerFiltered]:
    """
    Enrich each influencer record in-place:
      - Try to find email from bio, caption, and website
      - Normalise missing mandatory fields
      - Never invent or guess data
    """
    for inf in influencers:
        # ── Email enrichment ──────────────────────────────────────────────────
        if not inf.contact_email:
            found_email: Optional[str] = None

            # 1. Check bio text
            found_email = _extract_email_from_text(inf.bio or "")

            # 2. Check recent post caption
            if not found_email:
                found_email = _extract_email_from_text(inf.recent_post_caption or "")

            # 3. Check the influencer's linked website
            if not found_email and inf.website:
                found_email = _try_website_email(inf.website)

            if found_email:
                logger.info(f"[Enrich] {inf.name}: email enriched → {found_email}")
                inf.contact_email = found_email
            else:
                inf.contact_email = "Not Found"

        # ── Normalise other mandatory fields ──────────────────────────────────
        if inf.engagement_rate is None:
            inf.engagement_rate = 0.0

        if not inf.content_themes:
            # Fall back to the niche as a content theme
            inf.content_themes = [inf.niche or "general"]

        # Audience demographics: fill with 'Unknown' if absent (not invented)
        if not inf.audience_age:
            inf.audience_age = "Unknown"
        if not inf.audience_gender:
            inf.audience_gender = "Unknown"
        if not inf.audience_geography:
            inf.audience_geography = "Unknown"

    return influencers
