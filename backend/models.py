from pydantic import BaseModel, Field
from typing import Optional, List


class InfluencerRaw(BaseModel):
    """Raw influencer profile as returned by a discovery adapter."""
    name: str
    platform: str                          # instagram | youtube | tiktok
    profile_url: str
    follower_count: int
    engagement_rate: Optional[float] = None
    niche: Optional[str] = None
    content_themes: List[str] = Field(default_factory=list)
    contact_email: Optional[str] = None
    bio: Optional[str] = None
    recent_post_caption: Optional[str] = None
    recent_post_url: Optional[str] = None
    # Optional enrichment fields
    audience_age: Optional[str] = None
    audience_gender: Optional[str] = None
    audience_geography: Optional[str] = None
    website: Optional[str] = None


class InfluencerFiltered(InfluencerRaw):
    """Influencer that has been through the filter + enrichment pipeline."""
    passed_filter: bool
    filter_reason: str
    category: str


class OutreachRecord(BaseModel):
    """A single row from the outreach_log table."""
    id: int
    influencer_name: str
    platform: str
    email: Optional[str]
    email_subject: Optional[str]
    email_body: Optional[str]
    dm_text: Optional[str]
    sent_at: Optional[str]
    status: str
    error_message: Optional[str]
