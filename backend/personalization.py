"""
AI-powered message personalization module.

Primary path  : Groq API (llama-3.3-70b-versatile) — free tier.
Fallback path : Rule-based template that is still personalized
                (niche, themes, name, caption, audience, collaboration type)
                — works without any API key.

Key fixes vs. original:
  • Uses the correct Groq model: llama-3.3-70b-versatile
  • Each influencer gets a different collaboration angle (UGC / affiliate /
    sponsorship / barter / ambassador) — no longer the same for everyone
  • Prompt explicitly asks the LLM to vary the opening line each time
  • Word count enforcement with _trim_to_range() (unchanged, works correctly)
"""

import json
import re
import logging
from typing import Tuple
from models import InfluencerFiltered
from config import GROQ_API_KEY, GROQ_MODEL, BRAND_NAME

logger = logging.getLogger(__name__)

# ─── Collaboration angle rotation ─────────────────────────────────────────────

_COLLAB_TYPES = [
    "a paid UGC content creation campaign",
    "a long-term brand ambassador programme",
    "an affiliate partnership with a 15% commission",
    "a sponsored post + Instagram Story series",
    "a product seeding / barter collaboration",
    "a co-created limited-edition product launch",
]

# Brand description varies slightly per niche so the email feels tailored
_BRAND_CONTEXT: dict[str, str] = {
    "fitness":    f"a science-backed sports nutrition and wellness brand",
    "beauty":     f"a clean, dermatologist-tested skincare brand",
    "fashion":    f"a sustainable fashion and accessories label",
    "fintech":    f"a personal-finance app helping millennials grow wealth",
    "crypto":     f"a beginner-friendly crypto education platform",
    "parenting":  f"a family wellness and baby essentials brand",
    "gaming":     f"a gaming gear and accessories brand",
    "lifestyle":  f"a productivity & wellness brand for modern creators",
    "technology": f"a consumer-tech review platform",
}


def _collab_for(inf: InfluencerFiltered, index: int) -> str:
    return _COLLAB_TYPES[index % len(_COLLAB_TYPES)]


def _brand_ctx(inf: InfluencerFiltered) -> str:
    niche = (inf.niche or "lifestyle").lower()
    return _BRAND_CONTEXT.get(niche, f"a modern lifestyle brand")


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text.strip()))


def _trim_to_range(text: str, min_w: int, max_w: int) -> str:
    """
    Enforce a word-count window without fabricating content.
    - Too long → truncate to max_w words + ellipsis
    - Too short → append a neutral closing line
    """
    words = text.split()
    if len(words) > max_w:
        return " ".join(words[:max_w]) + "…"
    if len(words) < min_w:
        return text.strip() + " Looking forward to connecting with you."
    return text


# ─── Groq LLM path ────────────────────────────────────────────────────────────

def _generate_via_groq(
    inf: InfluencerFiltered,
    collab_type: str,
    brand_context: str,
) -> Tuple[str, str, str]:
    """
    Call the Groq API to generate personalized outreach messages.
    Returns (email_subject, email_body, dm_text).
    Raises on any failure so the caller can fall back to the template.
    """
    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)
    first_name    = inf.name.split()[0]
    theme_str     = ", ".join(inf.content_themes[:3]) if inf.content_themes else (inf.niche or "content")
    caption_snip  = (inf.recent_post_caption or f"your recent {theme_str} posts")[:80]
    audience_info = ", ".join(filter(None, [
        inf.audience_age if inf.audience_age != "Unknown" else None,
        inf.audience_gender if inf.audience_gender != "Unknown" else None,
        inf.audience_geography if inf.audience_geography != "Unknown" else None,
    ])) or "your audience"

    prompt = f"""You are a senior influencer marketing manager writing outreach messages.

Influencer profile:
  Name         : {inf.name}
  Platform     : {inf.platform}
  Niche        : {inf.niche}
  Content themes: {theme_str}
  Recent content: "{caption_snip}"
  Followers    : {inf.follower_count:,}
  Engagement   : {inf.engagement_rate:.1f}%
  Audience     : {audience_info}

Brand: {BRAND_NAME} — {brand_context}.
Proposed collaboration: {collab_type}.

Write TWO messages. Return ONLY valid JSON with exactly these keys:
  "email_subject": one compelling subject line (6-10 words)
  "email_body"   : collaboration pitch email, 60-90 words
  "dm_text"      : short Instagram/TikTok DM, 15-30 words

Rules for email_body:
  - Address {first_name} by first name
  - Reference the specific recent content snippet above naturally
  - Mention the brand {BRAND_NAME} and the collaboration type ({collab_type})
  - State ONE clear value proposition for the influencer
  - Professional but warm and conversational tone
  - Do NOT start with generic openers like "I hope this finds you well"
  - Do NOT use the same sentence structure as a previous message

Rules for dm_text:
  - Casual and platform-native (no formal language)
  - Mention something specific from their content
  - Max 30 words, no hashtags

Do NOT invent any facts not provided above."""

    completion = client.chat.completions.create(
        model           = GROQ_MODEL,
        messages        = [{"role": "user", "content": prompt}],
        temperature     = 0.75,
        response_format = {"type": "json_object"},
        max_tokens      = 400,
    )

    raw = completion.choices[0].message.content
    data = json.loads(raw)

    subject    = str(data["email_subject"]).strip()
    email_body = _trim_to_range(str(data["email_body"]).strip(), 60, 90)
    dm_text    = _trim_to_range(str(data["dm_text"]).strip(), 15, 30)

    # Log if trimming occurred
    orig_email_wc = _word_count(str(data["email_body"]))
    orig_dm_wc    = _word_count(str(data["dm_text"]))
    if _word_count(email_body) != orig_email_wc:
        logger.debug(f"[Personalize] Email trimmed for {inf.name}: {orig_email_wc}→{_word_count(email_body)} words")
    if _word_count(dm_text) != orig_dm_wc:
        logger.debug(f"[Personalize] DM trimmed for {inf.name}: {orig_dm_wc}→{_word_count(dm_text)} words")

    return subject, email_body, dm_text


# ─── Template fallback path ────────────────────────────────────────────────────

def _generate_via_template(
    inf: InfluencerFiltered,
    collab_type: str,
    brand_context: str,
) -> Tuple[str, str, str]:
    """
    Rule-based personalised template — used when Groq is unavailable.
    Still uses influencer-specific fields so every message is different.
    """
    first     = inf.name.split()[0]
    theme_str = ", ".join(inf.content_themes[:2]) if inf.content_themes else (inf.niche or "your niche")
    caption   = (inf.recent_post_caption or f"your recent {theme_str} content")[:60]
    geo       = inf.audience_geography if inf.audience_geography not in (None, "Unknown") else "your community"
    age       = inf.audience_age       if inf.audience_age       not in (None, "Unknown") else None

    audience_desc = f"{age}, {geo}" if age else geo

    subject = f"{BRAND_NAME} x {inf.name} — {collab_type.split()[2]} opportunity"

    email_body = (
        f"Hi {first},\n\n"
        f"Your recent content — especially \"{caption}...\" — caught our eye. "
        f"As {brand_context}, {BRAND_NAME} is looking for authentic voices in {inf.niche}, "
        f"and your {theme_str} focus resonates strongly with our audience. "
        f"We'd love to explore {collab_type} with you. "
        f"Your {audience_desc} followers are exactly who we're trying to reach, "
        f"and we offer full creative control plus competitive compensation.\n\n"
        f"Open to a quick chat?\n\nBest,\n{BRAND_NAME} Team"
    )

    dm_text = (
        f"Hey {first}! Loved your {theme_str} content 🙌 "
        f"We're {BRAND_NAME} — would love to explore {collab_type.split()[0]} {collab_type.split()[1]} with you!"
    )

    email_body = _trim_to_range(email_body, 60, 90)
    dm_text    = _trim_to_range(dm_text,    15, 30)

    return subject, email_body, dm_text


# ─── Public API ───────────────────────────────────────────────────────────────

def generate_messages(
    inf: InfluencerFiltered,
    index: int = 0,
) -> Tuple[str, str, str]:
    """
    Generate (email_subject, email_body, dm_text) for one influencer.
    `index` rotates the collaboration type so consecutive influencers
    receive different pitches even with the template fallback.

    Primary: Groq API (requires GROQ_API_KEY in .env)
    Fallback: rule-based template
    """
    collab_type   = _collab_for(inf, index)
    brand_context = _brand_ctx(inf)

    if GROQ_API_KEY:
        try:
            subject, email_body, dm_text = _generate_via_groq(inf, collab_type, brand_context)
            logger.info(f"[Personalize] Groq ✓  {inf.name}")
            return subject, email_body, dm_text
        except Exception as e:
            logger.warning(f"[Personalize] Groq failed for {inf.name} ({e}) — using template fallback")

    subject, email_body, dm_text = _generate_via_template(inf, collab_type, brand_context)
    logger.info(f"[Personalize] Template generated successfully: {inf.name}")
    return subject, email_body, dm_text
