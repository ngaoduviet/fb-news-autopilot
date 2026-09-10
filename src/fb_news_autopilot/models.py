"""Immutable input/evidence types. Observations never become proof implicitly."""
from dataclasses import dataclass, asdict, field
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Protocol
import hashlib
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from .contracts import validate


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('A timezone offset is required')
    return parsed


def normalized_text(value: str) -> str:
    import unicodedata
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', value).casefold()).strip()


def valid_url(value: str) -> bool:
    try:
        p = urlsplit(value)
        return (p.scheme == 'https' and bool(p.hostname) and p.username is None
                and p.password is None and p.port in (None, 443)
                and not any(c.isspace() or ord(c) < 32 for c in value))
    except ValueError:
        return False


def url_key(value: str) -> str:
    p = urlsplit(value)
    # Retain article-identifying queries. Strip only recognized tracking parameters.
    query = [(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in {'fbclid','gclid'}]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or '/', urlencode(sorted(query)), ''))


def stable_id(prefix: str, value: str) -> str:
    return prefix + hashlib.sha256(value.encode()).hexdigest()[:24]


@dataclass(frozen=True)
class RunContext:
    run_id: str
    run_at: str
    timezone: str = 'Asia/Ho_Chi_Minh'
    live_window_hours: float = 2
    hot_window_hours: float = 24
    brand_profile: str = 'tin_nong_5s_v3'
    mode: str = 'shadow'

    def __post_init__(self):
        validate('run-context', asdict(self))
        timestamp(self.run_at)
        ZoneInfo(self.timezone)
        if self.hot_window_hours <= self.live_window_hours:
            raise ValueError('hot_window_hours must exceed live_window_hours')

    def to_dict(self): return asdict(self)


@dataclass(frozen=True)
class Observation:
    url: str
    headline: str
    query_or_feed: str
    discovered_at: str
    publisher: str | None = None
    publication_time: str | None = None
    topic: str = 'other'
    facts: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    location: str | None = None
    new_development_claimed: bool = False
    development_time_observed: str | None = None
    # Optional event/development key is a discovery hint, never M02 proof.
    event_key: str | None = None
    score_components: tuple[tuple[str, float], ...] = ()
    discovery_provider: str = 'manual'
    search_evidence: str | None = None
    citation_metadata: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ArticleEvidence:
    requested_url: str
    final_url: str | None = None
    canonical_url: str | None = None
    page_type: str = 'UNKNOWN'
    accessible: bool | None = None
    publisher_name: str | None = None
    source_identity: bool | None = None
    origin_quality: str = 'UNKNOWN'
    title: str | None = None
    body: str = ''
    raw_document: str | None = None
    publication_time: str | None = None
    last_updated_time: str | None = None
    event_time: str | None = None
    material_development_time: str | None = None
    # True means independently established from this exact article's body.
    material_development_supported: bool | None = None
    substantive_update_supported: bool | None = None
    development_evidence: str | None = None
    event_time_material: bool = False
    event_date_mismatch: bool = False
    recirculated_without_development: bool = False
    conflicting_sources: bool = False
    duplicate_uncertain: bool = False
    verified_event_key: str | None = None
    corroborating_urls: tuple[str, ...] = ()
    access_claim_corroborated: bool = False
    access_identity_corroborated: bool = False
    # Provider decisions use tri-state semantics; explanations must cite article text.
    headline_supported: bool | None = None
    facts_supported: bool | None = None
    semantic_evidence: str | None = None
    semantic_assessment_unclear: bool = False
    evidence_notes: tuple[str, ...] = ()
    network_error: str | None = None
    http_status: int | None = None
    redirect_outcome: str | None = None
    content_type: str | None = None
    fetched_at: str | None = None
    publisher_host: str | None = None
    source_image_url: str | None = None


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    status: int
    content_type: str
    fetched_at: str
    body: str
    redirects: tuple[str, ...] = ()


class SourceProvider(Protocol):
    def inspect(self, candidate: dict, context: RunContext) -> ArticleEvidence: ...


class DiscoveryProvider(Protocol):
    def discover(self, context: RunContext) -> list[Observation]: ...


@dataclass
class DuplicateRecord:
    normalized_url: str
    verified_event_key: str | None
    effective_freshness_time: str | None


@dataclass
class DuplicateIndex:
    records: list[DuplicateRecord] = field(default_factory=list)

    def decision(self, evidence: ArticleEvidence) -> str:
        """Return UNIQUE, DUPLICATE, or UNCERTAIN from verified identity evidence."""
        urls = {url_key(u) for u in [evidence.final_url, evidence.canonical_url]
                if u and valid_url(u)}
        event_key = evidence.verified_event_key

        if event_key is not None and any(
                record.verified_event_key == event_key for record in self.records):
            return 'DUPLICATE'

        same_url = [record for record in self.records
                    if record.normalized_url in urls]
        if not same_url:
            return 'UNIQUE'
        if event_key is None or any(
                record.verified_event_key is None for record in same_url):
            return 'UNCERTAIN'

        # The same URL with established, different non-null event identities is a
        # new material phase. Same identities were handled above.
        return 'UNIQUE'

    def accept(self, evidence: ArticleEvidence, effective_freshness_time: str | None):
        urls = {url_key(u) for u in [evidence.final_url, evidence.canonical_url]
                if u and valid_url(u)}
        for normalized_url in urls:
            record = DuplicateRecord(normalized_url, evidence.verified_event_key,
                                     effective_freshness_time)
            if record not in self.records:
                self.records.append(record)
