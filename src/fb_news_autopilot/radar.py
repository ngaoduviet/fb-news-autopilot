"""M01: discovery, immutable normalization, deterministic clustering and ranking."""
from dataclasses import asdict
from jsonschema import ValidationError
import math
from .models import RunContext, Observation, normalized_text, stable_id, url_key, valid_url, timestamp
from .contracts import validate

HOT_WEIGHTS = dict(viral_potential=.25, direct_life_impact=.25, money_benefit_value=.20,
                   emotional_pull=.15, debate_potential=.10, freshness_score=.05)
TOP_WEIGHTS = dict(hot_score=.40, audience_quality_score=.30, money_value_score=.20, production_score=.10)
INPUT_SCORES = set(HOT_WEIGHTS) | {'audience_quality_score', 'money_value_score', 'production_score'}
TOPIC_PREFERENCE = {'money_policy':.30,'breaking_social':.25,'life_alert':.20,'tech_trend':.15,'global':.10,'sport':.10,'entertainment':.10,'other':0}


def weights_checked(weights, expected):
    import math
    if set(weights) != set(expected) or any(not math.isfinite(v) or v < 0 for v in weights.values()) or abs(sum(weights.values())-1) > 1e-9:
        raise ValueError('Weights must contain expected components and sum to one')
    return dict(weights)


class NewsRadar:
    def __init__(self, *, limit=10, hot_weights=None, top_weights=None):
        if limit < 1: raise ValueError('limit must be positive')
        self.limit = limit
        self.hot_weights = weights_checked(HOT_WEIGHTS if hot_weights is None else hot_weights, HOT_WEIGHTS)
        self.top_weights = weights_checked(TOP_WEIGHTS if top_weights is None else top_weights, TOP_WEIGHTS)

    def run(self, context: RunContext, observations: list[Observation]):
        candidates, audit = [], []
        raw = []
        for o in observations:
            raw.append(asdict(o))
            news_id = stable_id('news-', url_key(o.url) if valid_url(o.url) else o.url)
            if not valid_url(o.url):
                audit.append(dict(stage='M01',news_id=news_id,code='REJECT_INVALID_URL',detail=o.url))
                continue
            try:
                pub = timestamp(o.publication_time) if o.publication_time else None
            except (ValueError,TypeError):
                pub = None
                audit.append(dict(stage='M01',news_id=news_id,code='M01_PUBLICATION_OBSERVATION_UNCLEAR',detail='Malformed or timezone-free observation retained in raw evidence'))
            at = timestamp(context.run_at)
            age = (at-pub).total_seconds()/3600 if pub else None
            bucket = ('UNKNOWN' if age is None or age < 0 else 'LIVE' if age <= context.live_window_hours
                      else 'HOT' if age <= context.hot_window_hours else 'OLD')
            requires_freshness_verification = bucket != 'LIVE'
            values = dict(o.score_components)
            if set(values) != INPUT_SCORES:
                # No invented ratings: incomplete observations stay auditable outside the contract.
                audit.append(dict(stage='M01',news_id=news_id,code='M01_SCORES_UNAVAILABLE',detail='Explicit component scores are required; observation retained in raw audit'))
                continue
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=100 for v in values.values()):
                audit.append(dict(stage='M01',news_id=news_id,code='M01_INPUT_INVALID',detail='Scores must be finite numbers from 0 to 100'))
                continue
            values['hot_score'] = sum(values[k]*v for k,v in self.hot_weights.items())
            values['top_content_score'] = sum(values[k]*v for k,v in self.top_weights.items())
            # Headline equality is only a weak discovery hint. It cannot prove that
            # different URLs describe the same event.
            cluster_basis = ('event:' + normalized_text(o.event_key)) if o.event_key else ('url:' + url_key(o.url))
            key = cluster_basis
            candidate = {'news_id':news_id,'story_cluster_id':stable_id('cluster-',key),
                'discovery':{'query_or_feed':o.query_or_feed,'discovered_at':o.discovered_at,'discovered_url':o.url,'publisher_name':o.publisher,'headline_observed':o.headline,'publication_time_observed':pub.isoformat() if pub else None},
                'normalized':{'title':o.headline,'topic':o.topic,'summary_facts':list(o.facts),'main_entities':list(o.entities),'location':o.location},
                'scores':values,'preliminary_freshness':{'bucket':bucket,'age_hours':max(0,age) if age is not None and age>=0 else None,'new_development_claimed':o.new_development_claimed,'requires_m02_freshness_verification':requires_freshness_verification},
                'm01_status':'DISCOVERED'}
            try:
                validate('candidate-news-package',candidate)
            except (ValidationError,ValueError):
                audit.append(dict(stage='M01',news_id=news_id,code='M01_INPUT_INVALID',detail='Observation does not conform to candidate contract; raw observation retained'))
                continue
            candidates.append(candidate)
            if requires_freshness_verification:
                audit.append(dict(stage='M01',news_id=news_id,code='M01_NEEDS_FRESHNESS_VERIFICATION',detail='Observed freshness is not LIVE; exact-article verification is delegated to M02'))
        candidates.sort(key=lambda c: (-c['scores']['top_content_score'], -c['scores']['direct_life_impact'], -TOPIC_PREFERENCE[c['normalized']['topic']], c['news_id']))
        clusters, urls = set(), set()
        selected = 0
        for c in candidates:
            if c['m01_status']=='REJECTED_PRELIMINARY': continue
            cluster, url = c['story_cluster_id'], url_key(c['discovery']['discovered_url'])
            if cluster in clusters or url in urls:
                c['m01_status']='REJECTED_PRELIMINARY'
                audit.append(dict(stage='M01',news_id=c['news_id'],code='REJECT_DUPLICATE_STORY',detail='Duplicate preliminary cluster/URL; original observation retained'))
            elif selected < self.limit:
                c['m01_status']='SHORTLISTED'
                selected += 1
                clusters.add(cluster); urls.add(url)
            validate('candidate-news-package',c)
        summary = validate('radar-summary',dict(run_id=context.run_id,candidate_count=len(candidates),shortlisted_count=selected,
            preliminary_rejected_count=sum(c['m01_status']=='REJECTED_PRELIMINARY' for c in candidates),
            shortlisted_news_ids=[c['news_id'] for c in candidates if c['m01_status']=='SHORTLISTED']))
        return candidates, summary, audit, raw
