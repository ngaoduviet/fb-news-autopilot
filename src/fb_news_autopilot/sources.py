"""Public HTTPS/RSS adapters. Semantic judgement is an explicit evidence adapter."""
from dataclasses import replace
from datetime import datetime
from email.utils import parsedate_to_datetime
import json
import ssl
import re
from typing import Callable
from urllib.parse import urlsplit, urljoin, parse_qsl
from urllib.request import Request, HTTPSHandler, HTTPRedirectHandler, build_opener
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from .models import ArticleEvidence, Observation, RunContext, valid_url, timestamp, normalized_text


class SourceFetchError(OSError): pass


class _Redirects(HTTPRedirectHandler):
    def __init__(self, allowed): self.allowed=allowed
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not valid_url(newurl) or urlsplit(newurl).hostname not in self.allowed:
            raise SourceFetchError('Redirect destination is outside configured HTTPS source hosts')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


class HTTPSFetcher:
    def __init__(self, allowed_hosts: set[str], *, timeout=15, max_bytes=2_000_000):
        self.allowed_hosts = frozenset(allowed_hosts)
        self.timeout, self.max_bytes = timeout, max_bytes

    def get(self, url: str) -> tuple[str, str]:
        if not valid_url(url) or urlsplit(url).hostname not in self.allowed_hosts:
            raise SourceFetchError('URL is outside configured HTTPS source hosts')
        opener=build_opener(_Redirects(self.allowed_hosts),HTTPSHandler(context=ssl.create_default_context()))
        try:
            with opener.open(Request(url,headers={'User-Agent':'FBNewsAutopilot-Package01/0.1','Accept':'text/html, application/rss+xml, application/atom+xml'}),timeout=self.timeout) as response:
                raw=response.read(self.max_bytes+1)
                if len(raw)>self.max_bytes: raise SourceFetchError('Source response exceeds size limit')
                return response.url,raw.decode(response.headers.get_content_charset() or 'utf-8',errors='replace')
        except (HTTPError,URLError,TimeoutError) as exc:
            raise SourceFetchError(type(exc).__name__) from exc


def _time(value: str | None, timezone: str | None = None):
    if not value: return None
    try: return timestamp(value).isoformat()
    except ValueError:
        try:
            dt=datetime.fromisoformat(value)
            if dt.tzinfo is None and timezone:
                from zoneinfo import ZoneInfo
                return dt.replace(tzinfo=ZoneInfo(timezone)).isoformat()
        except ValueError: pass
    return None


def parse_article(url: str, final_url: str, html: str, publishers: dict[str, dict]) -> ArticleEvidence:
    soup=BeautifulSoup(html,'html.parser')
    def meta(key):
        node=soup.find('meta',attrs={'property':key}) or soup.find('meta',attrs={'name':key})
        return node.get('content') if node else None
    records=[]
    def collect(value):
        if isinstance(value,list):
            for child in value: collect(child)
        elif isinstance(value,dict):
            records.append(value)
            if '@graph' in value: collect(value['@graph'])
    for script in soup.find_all('script',attrs={'type':'application/ld+json'}):
        try: collect(json.loads(script.string or script.get_text()))
        except (ValueError,TypeError): pass
    def types(record):
        t=record.get('@type',[])
        return t if isinstance(t,list) else [t]
    article=next((v for v in records if set(types(v)) & {'NewsArticle','Article','ReportageNewsArticle'}),{})
    host=urlsplit(final_url).hostname
    config=publishers.get(host,{})
    publisher=config.get('name')
    path=urlsplit(final_url).path.rstrip('/')
    page_type='UNKNOWN'
    category_paths={str(value).rstrip('/') or '/' for value in config.get('category_paths',[])}
    article_selector=config.get('article_selector')
    article_path_patterns=config.get('article_path_patterns',[])
    configured_article = bool(article_selector and soup.select_one(article_selector)) or any(
        re.search(pattern, path) for pattern in article_path_patterns
    )
    if not path: page_type='HOMEPAGE'
    elif re.search(r'/(search|tim-kiem)(/|$)',path) or bool({k for k,_ in parse_qsl(urlsplit(final_url).query)} & {'q','search','s'}): page_type='SEARCH_RESULTS'
    elif re.search(r'/(tag|tags|topic|chu-de)(/|$)',path): page_type='TAG_TOPIC'
    elif (path or '/') in category_paths: page_type='CATEGORY'
    elif any('CollectionPage' in types(v) for v in records): page_type='CATEGORY'
    elif config.get('origin_quality')=='AGGREGATOR_ONLY': page_type='AGGREGATOR'
    elif article or meta('og:type')=='article' or configured_article: page_type='ARTICLE'
    node=soup.select_one(article_selector) if article_selector else soup.find('article')
    body_node=(node.select_one(config['body_selector']) if node and config.get('body_selector') else node)
    if body_node:
        for unwanted in body_node.find_all(['script','style','nav','header','footer']): unwanted.decompose()
    body=body_node.get_text('\n',strip=True) if body_node else article.get('articleBody','')
    paywall = article.get('isAccessibleForFree') in [False,'false','False']
    access = bool(body.strip()) and not paywall if page_type=='ARTICLE' else True
    canonical_node=soup.find('link',attrs={'rel':'canonical'})
    canonical=urljoin(final_url,canonical_node.get('href','')) if canonical_node else None
    notes=['HTML independently fetched from '+final_url]
    if canonical and (not valid_url(canonical) or urlsplit(canonical).hostname!=host):
        notes.append('Untrusted cross-origin/invalid canonical ignored: '+canonical)
        canonical=None
    raw_pub=article.get('datePublished') or meta('article:published_time')
    raw_update=article.get('dateModified') or meta('article:modified_time')
    if raw_pub: notes.append('Raw publication metadata: '+str(raw_pub))
    if raw_update: notes.append('Raw update metadata (not evidence of substantive change): '+str(raw_update))
    return ArticleEvidence(requested_url=url,final_url=final_url,canonical_url=canonical,page_type=page_type,accessible=access,
        publisher_name=publisher,source_identity=True if publisher and config.get('origin_quality') in {'PRIMARY_OFFICIAL','DIRECT_REPUTABLE_ARTICLE','SECONDARY_REPUTABLE_ARTICLE'} else None,
        origin_quality=config.get('origin_quality','UNKNOWN'),title=article.get('headline') or meta('og:title') or (soup.title.get_text(strip=True) if soup.title else None),body=body,raw_document=html,
        publication_time=_time(raw_pub,config.get('timezone')),last_updated_time=_time(raw_update,config.get('timezone')),
        evidence_notes=tuple(notes))


class WebSourceProvider:
    def __init__(self, fetcher, publishers, semantic_assessor: Callable | None = None):
        self.fetcher,self.publishers,self.semantic_assessor=fetcher,publishers,semantic_assessor

    def inspect(self,candidate:dict,context:RunContext) -> ArticleEvidence:
        url=candidate['discovery']['discovered_url']
        try:
            final,html=self.fetcher.get(url)
        except OSError as exc:
            return ArticleEvidence(requested_url=url,page_type='INACCESSIBLE',accessible=False,network_error=str(exc))
        evidence=parse_article(url,final,html,self.publishers)
        observed=candidate['discovery']['publisher_name']
        config=self.publishers.get(urlsplit(final).hostname,{})
        names=[config.get('name',''),*config.get('aliases',[])]
        if observed and normalized_text(observed) not in {normalized_text(v) for v in names}:
            evidence=replace(evidence,source_identity=None,evidence_notes=(*evidence.evidence_notes,'Observed publisher identity does not match configured source name or aliases'))
        # Assessor receives copied candidate + independent article evidence.
        # Never let a model replace URL, body, timestamps or publisher metadata.
        if self.semantic_assessor:
            decision=self.semantic_assessor(candidate,evidence,context)
            allowed={'headline_supported','facts_supported','semantic_evidence','event_time','event_time_material','event_date_mismatch',
                'material_development_time','material_development_supported','substantive_update_supported','development_evidence',
                'verified_event_key','duplicate_uncertain','conflicting_sources','recirculated_without_development'}
            if not set(decision)<=allowed: raise ValueError('Semantic adapter tried to overwrite source evidence')
            evidence=replace(evidence,**decision)
        return evidence


class RSSDiscovery:
    """Discover RSS/Atom observations; an explicit scorer supplies subjective ratings."""
    def __init__(self,fetcher,feed_urls,scorer:Callable):
        self.fetcher,self.feed_urls,self.scorer=fetcher,tuple(feed_urls),scorer
        self.errors=[]

    def discover(self,context):
        self.errors=[]
        observations=[]
        for feed in self.feed_urls:
            try:
                _,xml=self.fetcher.get(feed)
                root=ET.fromstring(xml)
                items=root.findall('.//item')+root.findall('.//{http://www.w3.org/2005/Atom}entry')
                for item in items:
                    def text(tag):
                        child=item.find(tag)
                        if child is None: child=item.find('{http://www.w3.org/2005/Atom}'+tag)
                        return child.text.strip() if child is not None and child.text else None
                    title=text('title'); url=text('link')
                    if url is None:
                        link=item.find('{http://www.w3.org/2005/Atom}link')
                        if link is not None: url=link.get('href')
                    if not title or not url: continue
                    raw=text('pubDate') or text('published')
                    pub=_time(raw)
                    if raw and pub is None:
                        try:
                            dt=parsedate_to_datetime(raw)
                            pub=dt.isoformat() if dt.tzinfo else None
                        except (ValueError,TypeError): pass
                    ratings=self.scorer(title,url)
                    observations.append(Observation(url=url,headline=title,query_or_feed=feed,discovered_at=context.run_at,publication_time=pub,score_components=tuple(ratings.items())))
            except (OSError,ET.ParseError) as exc:
                self.errors.append({'feed':feed,'error':type(exc).__name__})
        return observations
