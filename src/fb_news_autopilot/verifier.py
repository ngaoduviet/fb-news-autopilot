"""M02: independent evidence gate. Only this module creates resolved_article_url."""
from copy import deepcopy
from datetime import datetime
from dataclasses import asdict
from zoneinfo import ZoneInfo
from .contracts import validate, validator
import json
from .models import ArticleEvidence, DuplicateIndex, RunContext, SourceProvider, normalized_text, timestamp, valid_url

PAGE_CODES = {
    'HOMEPAGE':'REJECT_HOMEPAGE_URL', 'CATEGORY':'REJECT_CATEGORY_URL',
    'SEARCH_RESULTS':'REJECT_SEARCH_URL', 'TAG_TOPIC':'REJECT_TAG_TOPIC_URL',
    'AGGREGATOR':'REJECT_AGGREGATOR_AS_FINAL_SOURCE',
    'REDIRECT_ONLY':'REJECT_REDIRECT_TO_NON_ARTICLE', 'UNKNOWN':'REJECT_NOT_DIRECT_ARTICLE',
}
REPUTABLE = {'PRIMARY_OFFICIAL','DIRECT_REPUTABLE_ARTICLE','SECONDARY_REPUTABLE_ARTICLE'}



class SourceVerifier:
    def __init__(self, provider: SourceProvider, duplicates: DuplicateIndex | None = None, *, clock=None):
        self.provider = provider
        self.clock = clock
        self.duplicates = duplicates if duplicates is not None else DuplicateIndex()

    def verify(self, candidate: dict, context: RunContext) -> tuple[dict, dict]:
        # Validate valid inter-module candidates. A malformed URL is a supported
        # ingress failure; retain the exact raw URL in the terminal audit object.
        checked = deepcopy(candidate)
        url = candidate['discovery']['discovered_url']
        if not valid_url(url):
            json.dumps(checked, allow_nan=False)
            for error in validator('candidate-news-package').iter_errors(checked):
                if list(error.absolute_path) != ['discovery', 'discovered_url']:
                    raise error
        else:
            validate('candidate-news-package',checked)
        rejection, reviews, notes = [], [], []
        def reject(code):
            if code not in rejection: rejection.append(code)
        def review(code):
            if code not in reviews: reviews.append(code)
        if not valid_url(url):
            e = ArticleEvidence(requested_url=url, evidence_notes=('Input URL failed HTTPS syntax validation',))
            reject('REJECT_INVALID_URL')
        else:
            try:
                e = self.provider.inspect(deepcopy(candidate), context)
            except (OSError, TimeoutError) as exc:
                e = ArticleEvidence(requested_url=url,page_type='INACCESSIBLE',accessible=False,network_error=type(exc).__name__)
            if e.requested_url != url:
                raise ValueError('Source provider returned evidence for a different candidate URL')
        notes.extend(e.evidence_notes)
        if e.network_error: notes.append('Network/source failure: '+e.network_error)
        final = e.final_url if e.final_url and valid_url(e.final_url) else None
        canonical = e.canonical_url if e.canonical_url and valid_url(e.canonical_url) else None
        if e.final_url and final is None: reject('REJECT_INVALID_URL')
        if e.page_type in PAGE_CODES:
            reject('REJECT_NOT_DIRECT_ARTICLE')
            reject(PAGE_CODES[e.page_type])
            if e.final_url and e.final_url != url:
                reject('REJECT_REDIRECT_TO_NON_ARTICLE')
        if e.accessible is False or e.page_type == 'INACCESSIBLE':
            if (e.access_claim_corroborated and e.access_identity_corroborated and e.corroborating_urls
                    and all(valid_url(u) for u in e.corroborating_urls)):
                review('REVIEW_ARTICLE_ACCESS_LIMITED_CORROBORATED')
            else:
                reject('REJECT_ARTICLE_INACCESSIBLE')
        elif e.accessible is None:
            review('REVIEW_SOURCE_IDENTITY_UNCLEAR')
        if e.source_identity is False: reject('REJECT_SOURCE_UNVERIFIABLE')
        elif e.source_identity is None or e.origin_quality not in REPUTABLE:
            review('REVIEW_SOURCE_IDENTITY_UNCLEAR')
        if final is None and not rejection and e.accessible is True:
            reject('REJECT_NOT_DIRECT_ARTICLE')
        at = timestamp(context.run_at)
        def parse(value, unclear_code):
            if value is None: return None
            try:
                dt = timestamp(value)
                if dt > at:
                    review(unclear_code)
                    return None
                return dt
            except (ValueError, TypeError):
                review(unclear_code)
                return None
        pub = parse(e.publication_time,'REVIEW_PUBLICATION_TIME_UNCLEAR')
        updated = parse(e.last_updated_time,'REVIEW_NEW_DEVELOPMENT_UNCLEAR')
        development = parse(e.material_development_time,'REVIEW_NEW_DEVELOPMENT_UNCLEAR')
        event = parse(e.event_time,'REVIEW_EVENT_TIME_UNCLEAR')
        if pub is None: review('REVIEW_PUBLICATION_TIME_UNCLEAR')
        if e.event_time_material and event is None: review('REVIEW_EVENT_TIME_UNCLEAR')
        if e.event_date_mismatch: reject('REJECT_HEADLINE_UNSUPPORTED')
        if e.conflicting_sources: review('REVIEW_CONFLICTING_SOURCES')
        if e.duplicate_uncertain: review('REVIEW_DUPLICATE_UNCERTAIN')
        evidence_in_article = bool(e.development_evidence and normalized_text(e.development_evidence) in normalized_text(e.body))
        material_valid = bool(development and e.material_development_supported is True and evidence_in_article)
        update_valid = bool(updated and e.substantive_update_supported is True and evidence_in_article)
        effective = development if material_valid else updated if update_valid else pub
        basis = ('Verified material development supported by exact article: '+e.development_evidence if material_valid
                 else 'Verified substantive article update: '+e.development_evidence if update_valid
                 else 'Original article publication time; no verified substantive update replaces it')
        publication_age = (at-pub).total_seconds()/3600 if pub else None
        freshness_requires_development = bool(
            publication_age is not None and publication_age > context.live_window_hours)
        explicit_development_unclear = (
            (development is not None and e.material_development_supported is None)
            or (e.material_development_supported is True and not material_valid)
            or (e.substantive_update_supported is True and not update_valid))
        uncertain_development = (explicit_development_unclear
            or (e.semantic_assessment_unclear and freshness_requires_development))
        if uncertain_development: review('REVIEW_NEW_DEVELOPMENT_UNCLEAR')
        age = (at-effective).total_seconds()/3600 if effective else None
        bucket = ('UNKNOWN' if age is None else 'LIVE' if age<=context.live_window_hours
                  else 'HOT' if age<=context.hot_window_hours else 'OLD')
        if bucket=='OLD':
            # Claimed but unverified update does not pass; a plausible unresolved
            # material development is REVIEW, while proven stale content rejects.
            if not uncertain_development: reject('REJECT_OLD_NEWS')
        if e.recirculated_without_development:
            reject('REJECT_NO_NEW_DEVELOPMENT')
        if bucket=='HOT':
            new_time = development if material_valid else updated if update_valid else None
            today = at.astimezone(ZoneInfo(context.timezone)).date()
            if new_time is None:
                if uncertain_development: review('REVIEW_NEW_DEVELOPMENT_UNCLEAR')
                else: reject('REJECT_NO_NEW_DEVELOPMENT')
            elif new_time.astimezone(ZoneInfo(context.timezone)).date()!=today:
                reject('REJECT_NO_NEW_DEVELOPMENT')
        # Missing timestamps cannot be filled from M01 or search snippets.
        title = candidate['normalized']['title']
        facts = candidate['normalized']['summary_facts']
        h = e.headline_supported
        f = e.facts_supported
        if (h is not None or f is not None) and not e.semantic_evidence:
            raise ValueError('Semantic decisions require an evidence explanation')
        # Lexical matches do not establish entailment (quotation, negation and
        # allegations require context). An absent semantic assessment stays unknown.
        if f is None and not facts: f = True
        if e.event_date_mismatch: h = False
        if h is False: reject('REJECT_HEADLINE_UNSUPPORTED')
        elif h is None: review('REVIEW_HEADLINE_SUPPORT_UNCLEAR')
        if f is False: reject('REJECT_FACTS_UNSUPPORTED')
        elif f is None: review('REVIEW_FACT_SUPPORT_UNCLEAR')
        duplicate_decision = self.duplicates.decision(e)
        if duplicate_decision == 'DUPLICATE':
            reject('REJECT_DUPLICATE_STORY')
        elif duplicate_decision == 'UNCERTAIN':
            review('REVIEW_DUPLICATE_UNCERTAIN')
        if e.semantic_evidence: notes.append(e.semantic_evidence)
        notes.append(basis)
        status = 'REJECTED' if rejection else 'REVIEW' if reviews else 'VERIFIED'
        if status=='REJECTED': reviews=[]
        # The dedicated access review is sufficient when corroboration is valid;
        # do not suggest support or metadata were verified through a blocked page.
        if status=='REVIEW' and 'REVIEW_ARTICLE_ACCESS_LIMITED_CORROBORATED' in reviews:
            reviews=['REVIEW_ARTICLE_ACCESS_LIMITED_CORROBORATED']
        n = candidate['normalized']
        result = dict(schema_version='1.0.0',run_context=context.to_dict(),news_id=candidate['news_id'],story_cluster_id=candidate['story_cluster_id'],
            source=dict(publisher_name=e.publisher_name or candidate['discovery']['publisher_name'],discovered_url=url,
                resolved_article_url=final if e.page_type=='ARTICLE' else None,canonical_url=canonical,
                publication_time=pub.isoformat() if pub else None,last_updated_time=updated.isoformat() if updated else None,
                event_time=event.isoformat() if event else None,material_development_time=development.isoformat() if material_valid else None,
                corroborating_urls=[u for u in e.corroborating_urls if valid_url(u)]),
            content=dict(candidate_title=title,candidate_summary_facts=deepcopy(facts),main_entities=deepcopy(n['main_entities']),topic=n['topic'],location=n['location'],
                verified_title=title if status=='VERIFIED' else None,verified_summary_facts=deepcopy(facts) if status=='VERIFIED' else []),
            freshness=dict(bucket=bucket,age_hours=age,effective_freshness_time=effective.isoformat() if effective else None,basis=basis),
            scores=deepcopy(candidate['scores']),
            verification=dict(status=status,verified_at=(self.clock() if self.clock else datetime.now(ZoneInfo(context.timezone))).isoformat(),page_type=e.page_type,article_accessible=e.accessible,headline_supported=h,facts_supported=f,origin_quality=e.origin_quality,
                rejection_codes=rejection,review_codes=reviews,evidence_summary='; '.join(notes)),
            handoff=dict(eligible_for_editorial_module=status=='VERIFIED',package_01_complete=True))
        validate('package-01-result',result)
        validate('source-verification',{'verification':result['verification']})
        if status=='VERIFIED':
            validate('verified-news-package',result)
            self.duplicates.accept(e, effective.isoformat() if effective else None)
        # Raw evidence is append-only in the pipeline's audit bundle, including
        # unusable timestamps, redirect destinations, original text and M01 data.
        return result, dict(candidate=deepcopy(candidate),evidence=asdict(e),result=deepcopy(result))
