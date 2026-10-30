"""
Mock discovery adapter — generates realistic, deterministic influencer profiles.

Fixes vs. original:
  • Names are human-readable (no 'Riley Lee3' suffixes)
  • Emails use realistic domains, not @example.com
  • Covers all 9 assignment niches, not just 3
  • Engagement rates vary realistically by platform
  • 'Not Found' emails (~25%) clearly marked
  • Profile URLs point to realistic slugs
"""

import random
import hashlib
from typing import List
from models import InfluencerRaw
from discovery.base import DiscoveryAdapter

# ─── Data pools ──────────────────────────────────────────────────────────────

_FIRST = [
    "Ava", "Zoe", "Mia", "Lily", "Emma", "Chloe", "Sophie", "Grace",
    "Liam", "Noah", "Ethan", "Mason", "Lucas", "Jack", "Aiden", "Ryan",
    "Priya", "Ananya", "Riya", "Kavya", "Sara", "Maya", "Aisha", "Leila",
    "Diego", "Carlos", "Miguel", "Mateo", "Omar", "Yusuf", "Kwame", "Jae",
    "Hana", "Yuki", "Suki", "Mina", "Nadia", "Kira", "Tara", "Jade",
    "Alex", "Jordan", "Casey", "Morgan", "Riley", "Quinn", "Avery", "Parker",
]

_LAST = [
    "Chen", "Patel", "Torres", "Kim", "Nguyen", "Rivera", "Hassan", "Singh",
    "Monroe", "Hayes", "Foster", "Reed", "Brooks", "West", "Cole", "Price",
    "Martinez", "Ramirez", "Okafor", "Adeyemi", "Nakamura", "Tanaka",
    "Dubois", "Muller", "Rossi", "Kowalski", "Santos", "Ferreira",
]

_EMAIL_DOMAINS = [
    "gmail.com", "outlook.com", "yahoo.com", "protonmail.com",
    "icloud.com", "hotmail.com", "me.com",
]

_PLATFORMS = ["instagram", "youtube", "tiktok"]

# Per-niche content themes
_THEMES: dict[str, list[str]] = {
    "fitness":    ["home workouts", "nutrition", "recovery", "strength training",
                   "running", "mobility", "HIIT", "weight loss", "marathon prep",
                   "calisthenics", "yoga", "gym motivation"],
    "beauty":     ["skincare", "makeup tutorials", "GRWM", "anti-aging", "haircare",
                   "clean beauty", "drugstore dupes", "fragrance", "nail art",
                   "glass skin", "SPF education", "dermatology tips"],
    "fashion":    ["OOTD", "thrift hauls", "capsule wardrobe", "streetwear",
                   "sustainable style", "sneaker reviews", "luxury fashion",
                   "vintage finds", "accessories", "fashion week recaps"],
    "fintech":    ["investing basics", "budgeting", "stock market", "ETFs",
                   "personal finance", "side hustles", "credit scores",
                   "real estate investing", "passive income", "tax tips"],
    "crypto":     ["DeFi", "NFTs", "Bitcoin", "altcoins", "blockchain basics",
                   "crypto trading", "Web3", "staking", "tokenomics", "market analysis"],
    "parenting":  ["newborn tips", "toddler activities", "mom life", "dad life",
                   "homeschooling", "baby products", "child development",
                   "meal prep for kids", "pregnancy journey", "family vlogs"],
    "gaming":     ["game reviews", "streaming highlights", "esports", "RPG",
                   "FPS gameplay", "indie games", "retro gaming",
                   "gaming setup tours", "speedruns", "tips & tricks"],
    "lifestyle":  ["morning routines", "productivity", "minimalism", "travel",
                   "wellness", "self-care", "journaling", "plant-based living",
                   "book recommendations", "home decor"],
    "technology": ["AI tools", "gadget reviews", "coding tutorials", "tech news",
                   "app recommendations", "cybersecurity", "robotics",
                   "developer life", "open source", "startup culture"],
}

# Sample captions per niche
_CAPTIONS: dict[str, list[str]] = {
    "fitness":    ["My 15-minute morning workout routine 🔥", "Week 6 of marathon training",
                   "What I eat in a day as a certified trainer", "Best mobility drills for desk workers"],
    "beauty":     ["My 5-step glass skin routine", "Drugstore vs high-end foundation dupe test",
                   "Dermatologist-approved skincare routine for beginners", "GRWM for a date night 💄"],
    "fashion":    ["Thrift haul: $40 fall fits 🍂", "10-piece capsule wardrobe you need this season",
                   "How I style one blazer 5 different ways", "Sneaker rotation for September"],
    "fintech":    ["How I saved $10k in 6 months 💰", "ETFs every beginner should know",
                   "Stop making these credit card mistakes", "My side hustle made $3k last month"],
    "crypto":     ["Why Bitcoin is outperforming this week", "Beginner's guide to DeFi in 2024",
                   "My altcoin portfolio breakdown", "How to stake ETH safely"],
    "parenting":  ["Toddler activity ideas for rainy days ☔", "Honest newborn product review",
                   "What a realistic mom morning looks like", "Homeschool curriculum we love"],
    "gaming":     ["I played this indie gem for 20 hours straight", "Best FPS settings for competitive play",
                   "Ranking every game I played this month", "Gaming setup upgrade on a budget"],
    "lifestyle":  ["My 5am morning routine changed everything", "30-day minimalism challenge results",
                   "Books that genuinely changed my mindset 📚", "A week of meal prep in 2 hours"],
    "technology": ["AI tools that replaced 3 of my apps", "Honest review: new M4 MacBook Pro",
                   "I built an app in 24 hours with no-code tools", "Cybersecurity habits everyone needs"],
}

_GEOGRAPHIES = ["US", "US", "US", "UK", "CA", "AU", "IN", "SG", "AE", "NG"]
_AGE_GROUPS   = ["18-24", "18-24", "25-34", "25-34", "25-34", "35-44"]
_GENDERS      = ["Female", "Female", "Male", "Mixed"]

# ─── Engagement rate ranges per platform (realistic) ─────────────────────────
_ENGAGEMENT_RANGES = {
    "instagram": (1.5, 6.0),
    "tiktok":    (3.0, 12.0),
    "youtube":   (0.8, 4.5),
}


def _slug(name: str) -> str:
    return name.lower().replace(" ", "").replace(".", "")


def _deterministic_rng(seed_str: str) -> random.Random:
    """Create a seeded RNG from any string so output is deterministic."""
    seed = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2**32)
    return random.Random(seed)


def _build_pool(target: int = 300) -> list[dict]:
    """Pre-build a diverse pool of fictional influencers, deterministically."""
    rng = _deterministic_rng("influencer_pool_v2")
    niches = list(_THEMES.keys())
    pool: list[dict] = []
    used_names: set[str] = set()

    while len(pool) < target:
        first = rng.choice(_FIRST)
        last  = rng.choice(_LAST)
        name  = f"{first} {last}"
        # Ensure unique names by adding a middle initial if needed
        if name in used_names:
            name = f"{first} {rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}. {last}"
        used_names.add(name)

        niche    = niches[len(pool) % len(niches)]
        platform = rng.choice(_PLATFORMS)
        slug     = _slug(name)
        followers = rng.randint(5_000, 100_000)
        geo       = rng.choice(_GEOGRAPHIES)

        # ~25% of influencers have no public email
        if rng.random() < 0.25:
            email = None
        else:
            domain = rng.choice(_EMAIL_DOMAINS)
            email  = f"{slug}@{domain}"

        themes  = rng.sample(_THEMES[niche], min(3, len(_THEMES[niche])))
        caption = rng.choice(_CAPTIONS[niche])

        pool.append({
            "name":     name,
            "platform": platform,
            "niche":    niche,
            "followers": followers,
            "email":    email,
            "themes":   themes,
            "caption":  caption,
            "bio":      f"{niche.title()} creator | {themes[0]} & {themes[1]}",
            "geo":      geo,
            "age":      rng.choice(_AGE_GROUPS),
            "gender":   rng.choice(_GENDERS),
            "website":  f"https://{slug}.com" if rng.random() < 0.3 else None,
        })

    return pool


_POOL = _build_pool(300)


class MockAdapter(DiscoveryAdapter):
    """
    Returns realistic fictional influencer profiles.
    Deterministic: same niche + limit always yields the same people.
    """

    def discover(self, niche: str, limit: int = 50) -> List[InfluencerRaw]:
        niche = niche.lower()
        rng   = _deterministic_rng(f"engagement_{niche}")

        # Filter pool to requested niche first; fall back to full pool
        matched = [c for c in _POOL if c["niche"] == niche]
        if len(matched) < limit:
            # Top up with other niches so we always hit the limit
            others = [c for c in _POOL if c["niche"] != niche]
            rng.shuffle(others)
            matched = matched + others
        matched = matched[:limit]

        results: List[InfluencerRaw] = []
        for item in matched:
            platform = item["platform"]
            lo, hi   = _ENGAGEMENT_RANGES[platform]
            eng_rate = round(rng.uniform(lo, hi), 2)

            results.append(InfluencerRaw(
                name               = item["name"],
                platform           = platform,
                profile_url        = f"https://{platform}.com/@{_slug(item['name'])}",
                follower_count     = item["followers"],
                engagement_rate    = eng_rate,
                niche              = item["niche"],
                content_themes     = item["themes"],
                contact_email      = item["email"],
                bio                = item["bio"],
                recent_post_caption= item["caption"],
                recent_post_url    = f"https://{platform}.com/p/latest_{_slug(item['name'])}",
                audience_age       = item["age"],
                audience_gender    = item["gender"],
                audience_geography = item["geo"],
                website            = item["website"],
            ))

        return results
