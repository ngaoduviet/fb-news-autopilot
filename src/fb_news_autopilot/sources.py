"""Public HTTPS/RSS adapters. Semantic judgement is an explicit evidence adapter."""
from dataclasses import replace
from datetime import datetime, timezone
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
from .models import ArticleEvidence, FetchResult, Observation, RunContext, valid_url, timestamp, normalized_text


class SourceFetchError(OSError):
    def __init__(self,message,*,status=None,content_type=None,final_url=None):
        super().__init__(message)
        self.status=status
        self.content_type=content_type
        self.final_url=final_url


class _Redirects(HTTPRedirectHandler):
    def __init__(self, allowed, limit):
        self.allowed=allowed
        self.limit=limit
        self.redirects=[]
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not valid_url(newurl) or urlsplit(newurl).hostname not in self.allowed:
            raise SourceFetchError('Redirect destination is outside configured HTTPS source hosts')
        self.redirects.append(newurl)
        if len(self.redirects) > self.limit:
            raise SourceFetchError('Redirect limit exceeded')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


class HTTPSFetcher:
    SUPPORTED_CONTENT_TYPES = frozenset({
        'text/html', 'application/xhtml+xml', 'application/rss+xml',
        'application/atom+xml', 'application/xml', 'text/xml',
    })

    def __init__(self, allowed_hosts: set[str], *, timeout=15, max_bytes=2_000_000, redirect_limit=5):
        self.allowed_hosts = frozenset(allowed_hosts)
        self.timeout, self.max_bytes, self.redirect_limit = timeout, max_bytes, redirect_limit

    def get(self, url: str) -> FetchResult:
        if not valid_url(url) or urlsplit(url).hostname not in self.allowed_hosts:
            raise SourceFetchError('URL is outside configured HTTPS source hosts')
        redirects=_Redirects(self.allowed_hosts,self.redirect_limit)
        opener=build_opener(redirects,HTTPSHandler(context=ssl.create_default_context()))
        try:
            with opener.open(Request(url,headers={'User-Agent':'FBNewsAutopilot-Package01/0.1','Accept':'text/html, application/rss+xml, application/atom+xml'}),timeout=self.timeout) as response:
                content_type=response.headers.get_content_type().lower()
                if content_type not in self.SUPPORTED_CONTENT_TYPES:
                    raise SourceFetchError('Unsupported content type: '+content_type,status=response.status,
                        content_type=content_type,final_url=response.url)
                raw=response.read(self.max_bytes+1)
                if len(raw)>self.max_bytes: raise SourceFetchError('Source response exceeds size limit')
                return FetchResult(requested_url=url,final_url=response.url,status=response.status,
                    content_type=content_type,fetched_at=datetime.now(timezone.utc).isoformat(),
                    body=raw.decode(response.headers.get_content_charset() or 'utf-8',errors='replace'),
                    redirects=tuple(redirects.redirects))
        except HTTPError as exc:
            raise SourceFetchError('HTTPError',status=exc.code,
                content_type=exc.headers.get_content_type() if exc.headers else None,
                final_url=exc.geturl()) from exc
        except (URLError,TimeoutError) as exc:
            raise SourceFetchError(type(exc).__name__) from exc


def _fetch_parts(value, requested_url: str):
    """Support small tuple fakes used by offline tests while production returns FetchResult."""
    if isinstance(value, FetchResult):
        return value
    final_url, body = value
    return FetchResult(requested_url=requested_url, final_url=final_url, status=200,
        content_type='text/html', fetched_at=datetime.now(timezone.utc).isoformat(), body=body)


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


def _selector_value(soup, selectors):
    for specification in selectors or []:
        selector, separator, attribute = specification.partition('@')
        node=soup.select_one(selector)
        if node:
            value=node.get(attribute) if separator else node.get_text(' ',strip=True)
            if value: return value
    return None


def parse_article(url: str, final_url: str, html: str, publishers: dict[str, dict], *, fetch_result: FetchResult | None = None) -> ArticleEvidence:
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
    body_selectors=config.get('article_body_selectors') or ([config['article_selector']] if config.get('article_selector') else [])
    article_path_patterns=config.get('article_path_patterns',[])
    configured_article = any(soup.select_one(selector) for selector in body_selectors) or any(
        re.search(pattern, path) for pattern in article_path_patterns
    )
    if not path: page_type='HOMEPAGE'
    elif re.search(r'/(search|tim-kiem)(/|$)',path) or bool({k for k,_ in parse_qsl(urlsplit(final_url).query)} & {'q','search','s'}): page_type='SEARCH_RESULTS'
    elif re.search(r'/(tag|tags|topic|chu-de)(/|$)',path): page_type='TAG_TOPIC'
    elif (path or '/') in category_paths: page_type='CATEGORY'
    elif any(re.search(pattern,path) for pattern in config.get('category_path_patterns',[])) and not any(re.search(pattern,path) for pattern in article_path_patterns): page_type='CATEGORY'
    elif any('CollectionPage' in types(v) for v in records): page_type='CATEGORY'
    elif config.get('origin_quality')=='AGGREGATOR_ONLY': page_type='AGGREGATOR'
    elif article or meta('og:type')=='article' or configured_article: page_type='ARTICLE'
    body_node=next((soup.select_one(selector) for selector in body_selectors if soup.select_one(selector)),None)
    if body_node is None and article:
        body_node=soup.find('article')
    if body_node:
        for unwanted in body_node.find_all(['script','style','nav','header','footer']): unwanted.decompose()
    body=body_node.get_text('\n',strip=True) if body_node else article.get('articleBody','')
    paywall = article.get('isAccessibleForFree') in [False,'false','False']
    visible=normalized_text((soup.title.get_text(' ',strip=True) if soup.title else '')+' '+body)
    interstitial=any(token in visible for token in ('enable javascript','access denied','verify you are human','captcha','cloudflare ray id'))
    access = bool(body.strip()) and not paywall and not interstitial if page_type=='ARTICLE' else True
    canonical_node=soup.find('link',attrs={'rel':'canonical'})
    canonical=urljoin(final_url,canonical_node.get('href','')) if canonical_node else None
    notes=['HTML independently fetched from '+final_url]
    canonical_host=urlsplit(canonical).hostname if canonical and valid_url(canonical) else None
    same_publisher=bool(canonical_host and publishers.get(canonical_host,{}).get('name')==config.get('name'))
    if canonical and (not valid_url(canonical) or (canonical_host!=host and not same_publisher)):
        notes.append('Untrusted cross-origin/invalid canonical ignored: '+canonical)
        canonical=None
    raw_pub=article.get('datePublished') or meta('article:published_time') or _selector_value(soup,config.get('publication_time_selectors'))
    raw_update=article.get('dateModified') or meta('article:modified_time') or _selector_value(soup,config.get('update_time_selectors'))
    source_image=meta('og:image')
    if source_image:
        source_image=urljoin(final_url,source_image)
        if not valid_url(source_image): source_image=None
    if raw_pub: notes.append('Raw publication metadata: '+str(raw_pub))
    if raw_update: notes.append('Raw update metadata (not evidence of substantive change): '+str(raw_update))
    return ArticleEvidence(requested_url=url,final_url=final_url,canonical_url=canonical,page_type=page_type,accessible=access,
        publisher_name=publisher,source_identity=True if publisher and config.get('origin_quality') in {'PRIMARY_OFFICIAL','DIRECT_REPUTABLE_ARTICLE','SECONDARY_REPUTABLE_ARTICLE'} else None,
        origin_quality=config.get('origin_quality','UNKNOWN'),title=article.get('headline') or meta('og:title') or _selector_value(soup,config.get('title_selectors')) or (soup.title.get_text(strip=True) if soup.title else None),body=body,raw_document=html,
        publication_time=_time(raw_pub,config.get('timezone')),last_updated_time=_time(raw_update,config.get('timezone')),
        evidence_notes=tuple(notes),http_status=fetch_result.status if fetch_result else None,
        redirect_outcome=('REDIRECTED' if fetch_result and fetch_result.redirects else 'NO_REDIRECT') if fetch_result else None,
        content_type=fetch_result.content_type if fetch_result else None,fetched_at=fetch_result.fetched_at if fetch_result else None,
        publisher_host=host,source_image_url=source_image)


class WebSourceProvider:
    def __init__(self, fetcher, publishers):
        self.fetcher,self.publishers=fetcher,publishers

    def inspect(self,candidate:dict,context:RunContext) -> ArticleEvidence:
        url=candidate['discovery']['discovered_url']
        try:
            fetched=_fetch_parts(self.fetcher.get(url),url)
        except OSError as exc:
            return ArticleEvidence(requested_url=url,final_url=getattr(exc,'final_url',None),page_type='INACCESSIBLE',accessible=False,
                network_error=str(exc),http_status=getattr(exc,'status',None),content_type=getattr(exc,'content_type',None),
                publisher_host=urlsplit(getattr(exc,'final_url',None) or url).hostname)
        if fetched.content_type not in {'text/html','application/xhtml+xml'}:
            return ArticleEvidence(requested_url=url,final_url=fetched.final_url,page_type='INACCESSIBLE',accessible=False,
                network_error='Unsupported article content type',http_status=fetched.status,content_type=fetched.content_type,
                fetched_at=fetched.fetched_at,publisher_host=urlsplit(fetched.final_url).hostname,
                redirect_outcome='REDIRECTED' if fetched.redirects else 'NO_REDIRECT')
        final=fetched.final_url
        evidence=parse_article(url,final,fetched.body,self.publishers,fetch_result=fetched)
        observed=candidate['discovery']['publisher_name']
        config=self.publishers.get(urlsplit(final).hostname,{})
        names=[config.get('name',''),*config.get('aliases',[])]
        if observed and normalized_text(observed) not in {normalized_text(v) for v in names}:
            evidence=replace(evidence,source_identity=None,evidence_notes=(*evidence.evidence_notes,'Observed publisher identity does not match configured source name or aliases'))
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
                fetched=_fetch_parts(self.fetcher.get(feed),feed)
                xml=fetched.body
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
                    summary=text('description') or text('summary')
                    observations.append(Observation(url=url,headline=title,query_or_feed=feed,discovered_at=context.run_at,
                        publication_time=pub,facts=(summary,) if summary else (),score_components=tuple(ratings.items()),
                        discovery_provider='rss'))
            except (OSError,ET.ParseError) as exc:
                self.errors.append({'feed':feed,'error':type(exc).__name__})
        return observations
