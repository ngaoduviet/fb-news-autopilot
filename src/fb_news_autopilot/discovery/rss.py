"""RSS/Atom discovery normalized to M01 observations."""
from ..sources import RSSDiscovery
from .base import deterministic_scores


class RSSDiscoveryAdapter(RSSDiscovery):
    def __init__(self, fetcher, feed_urls):
        super().__init__(fetcher,feed_urls,lambda title,url:deterministic_scores(title))
