import pytest
from fb_news_autopilot.sources import parse_article,WebSourceProvider,RSSDiscovery,HTTPSFetcher,SourceFetchError

CONFIG={'publisher.example':{'name':'Publisher','origin_quality':'DIRECT_REPUTABLE_ARTICLE','timezone':'Asia/Ho_Chi_Minh','category_paths':['/kinh-te']}}
URL='https://publisher.example/news/article-123'
HTML='''<html><head><link rel="canonical" href="/news/article-123"><script type="application/ld+json">{"@type":"NewsArticle","headline":"A new decision","datePublished":"2026-09-09T11:00:00+07:00","dateModified":"2026-09-09T11:30:00+07:00"}</script></head><body><article><p>City approved the new benefit.</p><p>The benefit is 500 units.</p></article></body></html>'''


def test_html_extracts_independent_metadata():
    e=parse_article(URL,URL,HTML,CONFIG)
    assert e.page_type=='ARTICLE'; assert e.accessible
    assert e.publication_time=='2026-09-09T11:00:00+07:00'
    assert e.last_updated_time=='2026-09-09T11:30:00+07:00'
    assert e.substantive_update_supported is None
    assert e.canonical_url==URL

@pytest.mark.parametrize('path,kind',[('/','HOMEPAGE'),('/kinh-te','CATEGORY'),('/tim-kiem?q=test','SEARCH_RESULTS'),('/tags/news','TAG_TOPIC')])
def test_page_classification(path,kind):
    assert parse_article(URL,'https://publisher.example'+path,'<html/>',CONFIG).page_type==kind


def test_paywall_is_not_accessible():
    e=parse_article(URL,URL,HTML.replace('"@type":"NewsArticle"','"@type":"NewsArticle","isAccessibleForFree":false'),CONFIG)
    assert e.accessible is False


def test_untrusted_canonical_ignored():
    e=parse_article(URL,URL,HTML.replace('href="/news/article-123"','href="https://evil.example/fake"'),CONFIG)
    assert e.canonical_url is None


def test_publication_without_offset_requires_configured_timezone():
    html=HTML.replace('2026-09-09T11:00:00+07:00','2026-09-09T11:00:00')
    assert parse_article(URL,URL,html,CONFIG).publication_time=='2026-09-09T11:00:00+07:00'
    assert parse_article(URL,URL,html,{}).publication_time is None


def test_semantic_adapter_cannot_overwrite_raw_body(candidate,context):
    class Fetch:
        def get(self,url):return url,HTML
    provider=WebSourceProvider(Fetch(),CONFIG,lambda c,e,ctx:{'body':'invented'})
    with pytest.raises(ValueError):provider.inspect(candidate,context)


def test_rss_discovery(context):
    class Fetch:
        def get(self,url):return url,'<rss><channel><item><title>A decision</title><link>https://publisher.example/news/123</link><pubDate>Wed, 09 Sep 2026 04:00:00 GMT</pubDate></item></channel></rss>'
    d=RSSDiscovery(Fetch(),['https://publisher.example/rss'],lambda title,url:{'viral_potential':50})
    o=d.discover(context)[0]
    assert o.publication_time=='2026-09-09T04:00:00+00:00'
    assert o.url=='https://publisher.example/news/123'


def test_discovery_source_failure_explicit(context):
    class Fetch:
        def get(self,url):raise SourceFetchError('timeout')
    d=RSSDiscovery(Fetch(),['https://publisher.example/rss'],lambda t,u:{})
    assert d.discover(context)==[]; assert d.errors


def test_fetcher_blocks_unconfigured_hosts_before_network():
    with pytest.raises(SourceFetchError):HTTPSFetcher({'publisher.example'}).get('https://elsewhere.example/article')


def test_article_identifying_query_is_not_search_page():
    e=parse_article(URL,URL+'?news=123',HTML,CONFIG)
    assert e.page_type=='ARTICLE'


@pytest.mark.parametrize('cards',[1,3])
def test_configured_category_with_article_listing_cards_stays_category(cards):
    html='<html><body>'+''.join(
        f'<article><h2>Listing {number}</h2><p>Summary</p></article>'
        for number in range(cards))+'</body></html>'
    evidence=parse_article(URL,'https://publisher.example/kinh-te',html,CONFIG)
    assert evidence.page_type=='CATEGORY'


def test_generic_article_tag_alone_is_not_direct_article():
    evidence=parse_article(URL,URL,'<html><body><article>Generic card</article></body></html>',CONFIG)
    assert evidence.page_type=='UNKNOWN'
