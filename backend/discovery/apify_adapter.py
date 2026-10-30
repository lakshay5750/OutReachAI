"""
Real-data discovery adapter using Apify.

Requires:
  pip install apify-client
  DATA_SOURCE=apify
  APIFY_TOKEN=<your token from https://console.apify.com>

Actor used: apify/instagram-hashtag-scraper
  – searches Instagram posts by hashtag and extracts creator profiles.
  – Free tier allows ~1000 results/month.
  – Docs: https://apify.com/apify/instagram-hashtag-scraper

NOTE: Never fabricates emails — uses only what the public API returns.
      Missing emails are marked 'Not Found' by enrichment.py.
"""

import logging
from typing import List
from models import InfluencerRaw
from discovery.base import DiscoveryAdapter
from config import APIFY_TOKEN

logger = logging.getLogger(__name__)

# Maps niche → hashtags to search on Instagram
_NICHE_HASHTAGS: dict[str, list[str]] = {
    "fitness":    ["fitnessmotivation", "homeworkout", "fitlife"],
    "beauty":     ["skincareroutine", "makeuptutorial", "cleanbeauty"],
    "fashion":    ["ootd", "streetstyle", "sustainablefashion"],
    "fintech":    ["personalfinance", "investingtips", "moneymindset"],
    "crypto":     ["bitcoin", "defi", "cryptotrading"],
    "parenting":  ["momlife", "toddleractivities", "newbornbaby"],
    "gaming":     ["gaming", "gamer", "indiegames"],
    "lifestyle":  ["lifestyleblogger", "morningroutine", "selfcare"],
    "technology": ["techreview", "aitools", "developerlife"],
}


class ApifyAdapter(DiscoveryAdapter):
    """
    Fetches real micro-influencer profiles from Instagram via Apify.
    Falls back gracefully if token is missing or API call fails.
    """

    def discover(self, niche: str, limit: int = 50) -> List[InfluencerRaw]:
        if not APIFY_TOKEN:
            raise ValueError(
                "APIFY_TOKEN is not set. Add it to your .env file or "
                "use DATA_SOURCE=mock for testing without an API token."
            )

        try:
            from apify_client import ApifyClient
        except ImportError:
            raise RuntimeError("apify-client not installed. Run: pip install apify-client")

        hashtags = _NICHE_HASHTAGS.get(niche.lower(), [niche])
        client   = ApifyClient(APIFY_TOKEN)

        logger.info(f"[Apify] Running hashtag scraper for niche='{niche}', hashtags={hashtags}")

        # Run the Instagram hashtag scraper
        run = client.actor("apify/instagram-hashtag-scraper").call(run_input={
            "hashtags":       hashtags,
            "resultsLimit":   limit * 3,   # fetch more posts → more unique creators
            "addParentData":  True,         # include author profile data
        })

        # Deduplicate by profile URL
        seen_urls: set[str] = set()
        results:   List[InfluencerRaw] = []

        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            owner = item.get("ownerUsername") or item.get("owner", {}).get("username", "")
            if not owner:
                continue

            profile_url = f"https://instagram.com/{owner}"
            if profile_url in seen_urls:
                continue
            seen_urls.add(profile_url)

            followers = (
                item.get("ownerFollowersCount")
                or item.get("owner", {}).get("followersCount", 0)
                or 0
            )

            # Skip if outside micro-influencer range
            if not (5_000 <= followers <= 100_000):
                continue

            bio = (
                item.get("ownerBiography")
                or item.get("owner", {}).get("biography", "")
                or ""
            )
            full_name = (
                item.get("ownerFullName")
                or item.get("owner", {}).get("fullName", owner)
                or owner
            )
            engagement = item.get("likesCount", 0) / max(followers, 1) * 100

            results.append(InfluencerRaw(
                name                = full_name,
                platform            = "instagram",
                profile_url         = profile_url,
                follower_count      = followers,
                engagement_rate     = round(engagement, 2),
                niche               = niche,
                content_themes      = [h.lstrip("#") for h in hashtags],
                contact_email       = None,   # enrichment.py will attempt lookup
                bio                 = bio,
                recent_post_caption = item.get("caption", "")[:200] if item.get("caption") else None,
                recent_post_url     = item.get("url"),
                website             = item.get("ownerExternalUrl"),
            ))

            if len(results) >= limit:
                break

        logger.info(f"[Apify] Discovered {len(results)} micro-influencers for niche='{niche}'")

        if len(results) < 50:
            logger.warning(
                f"[Apify] Only found {len(results)} influencers (need 50). "
                "Try broader hashtags or increase resultsLimit."
            )

        return results
