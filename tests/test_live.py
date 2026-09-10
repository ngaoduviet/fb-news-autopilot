"""Opt-in live probes. These skip unless explicitly enabled and configured."""
import os
from pathlib import Path

import pytest

from fb_news_autopilot.discovery.rss import RSSDiscoveryAdapter
from fb_news_autopilot.publishers import PublisherRegistry
from fb_news_autopilot.sources import HTTPSFetcher, parse_article


pytestmark=pytest.mark.live


def live_enabled():
    return os.getenv('LIVE_TESTS')=='1'


@pytest.mark.skipif(not live_enabled(),reason='set LIVE_TESTS=1 to run external live probes')
def test_live_rss_returns_current_direct_candidates():
    from fb_news_autopilot.shadow import new_context
    registry=PublisherRegistry.load(Path(__file__).parents[1]/'config/publishers.yaml')
    fetcher=HTTPSFetcher(registry.hosts)
    discovery=RSSDiscoveryAdapter(fetcher,registry.feed_urls)
    observations=discovery.discover(new_context())
    assert observations, 'No configured live RSS feed produced a candidate; errors='+repr(discovery.errors)
    assert all(item.url.startswith('https://') for item in observations)
    inspected=[]
    for item in observations[:20]:
        try:
            fetched=fetcher.get(item.url)
            inspected.append(parse_article(item.url,fetched.final_url,fetched.body,
                registry.as_source_mapping(),fetch_result=fetched))
        except OSError:
            continue
    assert inspected, 'No discovered current article could be fetched for exact classification'
    assert any(item.page_type=='ARTICLE' for item in inspected)
    assert any(item.publication_time for item in inspected if item.page_type=='ARTICLE')
