from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
import pytest
from jsonschema import ValidationError
from fb_news_autopilot.models import RunContext,url_key
from fb_news_autopilot.radar import NewsRadar
from fb_news_autopilot.verifier import SourceVerifier
from fb_news_autopilot.contracts import validate,validator
from fb_news_autopilot.pipeline import run_pipeline,persist_run
from conftest import FixedProvider


def test_m01_never_creates_resolved_url(context,observation):
    c,_,_,_=NewsRadar().run(context,[observation])
    assert 'resolved_article_url' not in json.dumps(c)
    assert 'verification' not in c[0]
    assert c[0]['scores']['hot_score']==80
    assert c[0]['scores']['top_content_score']==80


def test_scores_correct_without_rounding(context,observation):
    scores=dict(observation.score_components); scores.update(viral_potential=11.12345,direct_life_impact=92.9876)
    c=NewsRadar().run(context,[replace(observation,score_components=tuple(scores.items()))])[0][0]
    expected=.25*11.12345+.25*92.9876+.5*80
    assert c['scores']['hot_score']==pytest.approx(expected)
    assert c['scores']['top_content_score']==pytest.approx(.4*expected+.6*80)


def test_stable_id_order_independent(context,observation):
    other=replace(observation,url='https://publisher.example/other',headline='Other event')
    a=NewsRadar().run(context,[observation,other])[0]
    b=NewsRadar().run(context,[other,observation])[0]
    assert a==b


def test_same_story_cluster_only_one_shortlisted(context,observation):
    a=replace(observation,event_key='city-benefit-decision-20260909')
    b=replace(observation,url='https://second.example/report',event_key='city-benefit-decision-20260909')
    c,s,audit,_=NewsRadar().run(context,[a,b])
    assert s['shortlisted_count']==1
    assert c[0]['story_cluster_id']==c[1]['story_cluster_id']
    assert audit[0]['code']=='REJECT_DUPLICATE_STORY'


def test_old_observed_article_can_reach_m02_if_new_development_claimed(context,observation):
    o=replace(observation,publication_time='2026-09-06T11:00:00+07:00',new_development_claimed=True)
    c=NewsRadar().run(context,[o])[0][0]
    assert c['m01_status']=='SHORTLISTED'; assert c['preliminary_freshness']['bucket']=='OLD'

@pytest.mark.parametrize('time,bucket',[('2026-09-06T11:00:00+07:00','OLD'),('2026-09-09T06:00:00+07:00','HOT')])
def test_non_live_observations_are_delegated_to_m02(context,observation,time,bucket):
    c,s,audit,_=NewsRadar().run(context,[replace(observation,publication_time=time)])
    assert s['preliminary_rejected_count']==0
    assert s['shortlisted_count']==1
    assert c[0]['m01_status']=='SHORTLISTED'
    assert c[0]['preliminary_freshness']['bucket']==bucket
    assert c[0]['preliminary_freshness']['requires_m02_freshness_verification'] is True
    assert audit[0]['code']=='M01_NEEDS_FRESHNESS_VERIFICATION'


def test_tracking_url_dedup():
    assert url_key('https://publisher.example/a?id=3&utm_source=x#ref')==url_key('https://publisher.example/a?id=3')
    assert url_key('https://publisher.example/a?id=3')!=url_key('https://publisher.example/a?id=4')


def test_unknown_metadata_not_fabricated(context,observation):
    c=NewsRadar().run(context,[replace(observation,publication_time=None,publisher=None,location=None)])[0][0]
    assert c['discovery']['publication_time_observed'] is None
    assert c['preliminary_freshness']==dict(bucket='UNKNOWN',age_hours=None,new_development_claimed=False,requires_m02_freshness_verification=True)


def test_missing_scores_audited_without_fabrication(context,observation):
    c,s,audit,raw=NewsRadar().run(context,[replace(observation,score_components=())])
    assert not c; assert raw; assert audit[0]['code']=='M01_SCORES_UNAVAILABLE'

@pytest.mark.parametrize('changes',[{'run_at':'2026-09-09T11:00:00'},{'timezone':'invalid/zone'},{'live_window_hours':24},{'hot_window_hours':0}])
def test_context_validation(context,changes):
    with pytest.raises((ValueError,ValidationError,KeyError)):
        RunContext(**{**context.to_dict(),**changes})


def test_m01_unknown_fields_prohibited(candidate):
    candidate=deepcopy(candidate); candidate['resolved_article_url']='https://publisher.example/article'
    with pytest.raises(ValidationError): validate('candidate-news-package',candidate)


def test_all_checked_in_schemas_valid():
    root=Path(__file__).resolve().parents[1]/'schemas'
    for p in root.glob('*.schema.json'): validator(p.name.removesuffix('.schema.json'))

@pytest.mark.parametrize('field,value',[('headline_supported',False),('facts_supported',None),('page_type','CATEGORY'),('rejection_codes',['REJECT_OLD_NEWS']),('review_codes',['REVIEW_CONFLICTING_SOURCES'])])
def test_verified_schema_cannot_bypass_gate(verify,field,value):
    r=verify(); r['verification'][field]=value
    with pytest.raises(ValidationError): validate('package-01-result',r)


def test_review_cannot_handoff(verify):
    r=verify(publication_time=None); r['handoff']['eligible_for_editorial_module']=True
    with pytest.raises(ValidationError): validate('package-01-result',r)


def test_pipeline_and_append_only_idempotent_audit(context,observation,article,tmp_path):
    r,e=run_pipeline(context,NewsRadar(),SourceVerifier(FixedProvider(article)),[observation])
    assert r['outcome']=='VERIFIED_CANDIDATES_AVAILABLE'
    a=persist_run(tmp_path,r,e); b=persist_run(tmp_path,r,e)
    assert a==b; assert len(list(tmp_path.iterdir()))==1
    altered=deepcopy(r); altered['run_context']['run_id']='different'
    c=persist_run(tmp_path,altered,e)
    assert c!=a; assert json.loads(a.read_text())['run']==r


def test_empty_run_is_valid(context,article):
    r,_=run_pipeline(context,NewsRadar(),SourceVerifier(FixedProvider(article)),[])
    assert r['outcome']=='NO_VERIFIED_CANDIDATES'


def test_run_failure_no_discovery(context,article):
    r,_=run_pipeline(context,NewsRadar(),SourceVerifier(FixedProvider(article)),[],discovery_errors=[{'feed':'fixture','error':'timeout'}])
    assert r['outcome']=='RUN_FAILURE'


def test_partial_failure(context,observation,article):
    r,_=run_pipeline(context,NewsRadar(),SourceVerifier(FixedProvider(article)),[observation],discovery_errors=[{'feed':'fixture','error':'timeout'}])
    assert r['outcome']=='RUN_PARTIAL_FAILURE'


def test_entire_source_network_failure(context,observation,article):
    bad=replace(article,page_type='INACCESSIBLE',accessible=False,network_error='timeout')
    r,_=run_pipeline(context,NewsRadar(),SourceVerifier(FixedProvider(bad)),[observation])
    assert r['outcome']=='RUN_FAILURE'


def test_standalone_verification_schema_requires_review_code(verify):
    block=verify()['verification']; block['status']='REVIEW'
    with pytest.raises(ValidationError): validate('source-verification',{'verification':block})


def test_invalid_observation_timestamp_preserves_raw(context,observation):
    c,_,audit,raw=NewsRadar().run(context,[replace(observation,publication_time='unknown')])
    assert c[0]['discovery']['publication_time_observed'] is None
    assert raw[0]['publication_time']=='unknown'
    assert audit[0]['code']=='M01_PUBLICATION_OBSERVATION_UNCLEAR'


def test_invalid_score_does_not_abort_run(context,observation):
    scores=dict(observation.score_components); scores['viral_potential']=101
    c,_,audit,raw=NewsRadar().run(context,[replace(observation,score_components=tuple(scores.items()))])
    assert not c; assert raw; assert audit[0]['code']=='M01_INPUT_INVALID'


def test_money_priority_only_breaks_score_ties(context,observation):
    other=replace(observation,url='https://publisher.example/sport',headline='Different story',topic='sport')
    c=NewsRadar(limit=1).run(context,[other,observation])[0]
    assert c[0]['normalized']['topic']=='money_policy'


def test_identical_headline_different_urls_and_facts_are_preserved(context,observation):
    other=replace(observation,url='https://publisher.example/news/another-event',
                  facts=('A different fact',),entities=('Different entity',),event_key=None)
    candidates,summary,audit,_=NewsRadar(limit=10).run(context,[observation,other])
    assert summary['shortlisted_count']==2
    assert all(item['m01_status']=='SHORTLISTED' for item in candidates)
    assert candidates[0]['story_cluster_id'] != candidates[1]['story_cluster_id']
    assert not any(item['code']=='REJECT_DUPLICATE_STORY' for item in audit)


def test_hot_without_development_hint_reaches_m02(context,observation):
    hot=replace(observation,publication_time='2026-09-09T06:00:00+07:00',
                new_development_claimed=False)
    candidates,summary,_,_=NewsRadar().run(context,[hot])
    assert summary['shortlisted_count']==1
    assert candidates[0]['m01_status']=='SHORTLISTED'
    assert candidates[0]['preliminary_freshness']=={
        'bucket':'HOT','age_hours':6.0,'new_development_claimed':False,
        'requires_m02_freshness_verification':True,
    }
