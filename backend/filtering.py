"""
Filtering & Classification module.

Applies multi-criteria rules to raw influencer profiles and returns
classified InfluencerFiltered objects with explicit pass/fail reasons.

Criteria checked per influencer:
  1. Follower count within micro-influencer range (5K–100K)
  2. Engagement rate above minimum threshold (platform-aware)
  3. Content themes / niche keyword match
  4. Niche category alignment (optional brand-fit check)
"""

from typing import List
from models import InfluencerRaw, InfluencerFiltered

# ─── Category rules ───────────────────────────────────────────────────────────

CATEGORY_RULES: dict[str, dict] = {
    "fitness": {
        "min_followers":  5_000,
        "max_followers":  100_000,
        "min_engagement": 2.0,
        "keywords": [
            "workout", "fitness", "nutrition", "training", "gym", "health",
            "mobility", "running", "strength", "calisthenics", "bodyweight",
            "hiit", "yoga", "marathon", "weightloss", "muscle", "recovery",
        ],
    },
    "beauty": {
        "min_followers":  5_000,
        "max_followers":  100_000,
        "min_engagement": 1.8,
        "keywords": [
            "skincare", "makeup", "beauty", "haircare", "anti-aging", "derm",
            "glow", "routine", "fragrance", "spf", "foundation", "grwm",
            "cleanbeauty", "serum", "moisturiser", "sunscreen", "nailart",
        ],
    },
    "fashion": {
        "min_followers":  5_000,
        "max_followers":  100_000,
        "min_engagement": 1.5,
        "keywords": [
            "fashion", "style", "thrift", "streetwear", "capsule", "ootd",
            "sneaker", "wardrobe", "accessories", "vintage", "luxury", "outfit",
            "sustainable", "trendy", "lookbook",
        ],
    },
    "fintech": {
        "min_followers":  5_000,
        "max_followers":  100_000,
        "min_engagement": 1.5,
        "keywords": [
            "finance", "investing", "budget", "money", "etf", "stocks",
            "wealth", "saving", "credit", "realestate", "sidehustle",
            "passive income", "tax", "fintech", "portfolio",
        ],
    },
    "crypto": {
        "min_followers":  5_000,
        "max_followers":  100_000,
        "min_engagement": 2.0,
        "keywords": [
            "bitcoin", "crypto", "blockchain", "defi", "nft", "ethereum",
            "altcoin", "web3", "token", "staking", "trading", "market",
        ],
    },
    "parenting": {
        "min_followers":  5_000,
        "max_followers":  100_000,
        "min_engagement": 2.5,
        "keywords": [
            "mom", "dad", "parent", "baby", "toddler", "newborn",
            "kids", "family", "homeschool", "pregnancy", "motherhood",
            "fatherhood", "childcare", "playtime",
        ],
    },
    "gaming": {
        "min_followers":  5_000,
        "max_followers":  100_000,
        "min_engagement": 2.0,
        "keywords": [
            "gaming", "gamer", "gameplay", "esports", "fps", "rpg",
            "twitch", "stream", "indie", "retro", "speedrun", "console",
            "pc gaming", "review",
        ],
    },
    "lifestyle": {
        "min_followers":  5_000,
        "max_followers":  100_000,
        "min_engagement": 1.8,
        "keywords": [
            "lifestyle", "morning routine", "productivity", "wellness",
            "selfcare", "minimalism", "travel", "journal", "plantbased",
            "homedecor", "books", "routine", "vlog",
        ],
    },
    "technology": {
        "min_followers":  5_000,
        "max_followers":  100_000,
        "min_engagement": 1.5,
        "keywords": [
            "tech", "ai", "coding", "developer", "software", "gadget",
            "review", "cybersecurity", "robotics", "startup", "opensource",
            "machinelearning", "programming", "app",
        ],
    },
}


def classify_niche(raw: InfluencerRaw) -> str:
    """
    Identify the best-matching category for an influencer based on their
    niche field, content themes, and bio text.
    Returns the category name or 'other'.
    """
    text = " ".join([
        raw.niche or "",
        " ".join(raw.content_themes),
        raw.bio or "",
        raw.recent_post_caption or "",
    ]).lower()

    best_cat   = "other"
    best_hits  = 0
    for cat, rules in CATEGORY_RULES.items():
        hits = sum(1 for kw in rules["keywords"] if kw in text)
        if hits > best_hits:
            best_hits = hits
            best_cat  = cat

    return best_cat


def filter_and_classify(
    influencers: List[InfluencerRaw],
    target_niche: str,
) -> List[InfluencerFiltered]:
    """
    Apply filtering rules to every influencer and return annotated results.
    Each record includes passed_filter (bool) and a human-readable filter_reason.
    """
    rules   = CATEGORY_RULES.get(target_niche.lower(), CATEGORY_RULES["fitness"])
    results = []

    for inf in influencers:
        reasons: List[str] = []
        passed = True

        # ── Rule 1: Follower count ────────────────────────────────────────────
        if inf.follower_count < rules["min_followers"]:
            passed = False
            reasons.append(
                f"Followers {inf.follower_count:,} below minimum {rules['min_followers']:,}"
            )
        elif inf.follower_count > rules["max_followers"]:
            passed = False
            reasons.append(
                f"Followers {inf.follower_count:,} above maximum {rules['max_followers']:,}"
            )

        # ── Rule 2: Engagement rate ───────────────────────────────────────────
        if inf.engagement_rate is not None and inf.engagement_rate < rules["min_engagement"]:
            passed = False
            reasons.append(
                f"Engagement rate {inf.engagement_rate:.1f}% below "
                f"minimum {rules['min_engagement']:.1f}%"
            )

        # ── Rule 3: Content relevance (keyword check) ─────────────────────────
        text = " ".join([
            inf.niche or "",
            " ".join(inf.content_themes),
            inf.bio or "",
            inf.recent_post_caption or "",
        ]).lower()

        keyword_hits = [kw for kw in rules["keywords"] if kw in text]
        if not keyword_hits:
            passed = False
            reasons.append(
                f"Content not relevant to '{target_niche}' "
                f"(none of the niche keywords matched)"
            )

        # ── Build result ──────────────────────────────────────────────────────
        category = classify_niche(inf)
        results.append(InfluencerFiltered(
            **inf.model_dump(),
            passed_filter = passed,
            filter_reason = (
                "All criteria met" if passed
                else "; ".join(reasons)
            ),
            category = category,
        ))

    return results
