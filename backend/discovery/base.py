from abc import ABC, abstractmethod
from typing import List
from models import InfluencerRaw


class DiscoveryAdapter(ABC):
    """All discovery adapters must implement this interface."""

    @abstractmethod
    def discover(self, niche: str, limit: int = 50) -> List[InfluencerRaw]:
        """Return at least `limit` raw influencer profiles for the given niche."""
        ...
