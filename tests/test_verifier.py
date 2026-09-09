from copy import deepcopy
from dataclasses import replace
import pytest
from fb_news_autopilot.verifier import SourceVerifier
from fb_news_autopilot.models import DuplicateIndex
from fb_news_autopilot.sources import parse_article
from conftest import FixedProvider


def rejected(result,code):
    assert result['verification']['status']=='REJECTED'
    assert code in result['verification']['rejection_codes']
    assert result['verification']['review_codes']==[]
    assert not result['handoff']['eligible_for_editorial_module']
    assert result['content']['verified_title'] is None


def reviewed(result,code):
    assert result['verification']['status']=='REVIEW'
    assert code in result['verification']['review_codes']
    assert not result['verification']['rejection_codes']
    assert not result['handoff']['eligible_for_editorial_module']


def test_a_current_article(verify):
    r=verify(); assert r['verification']['status']=='VERIFIED'
    assert r['freshness']['bucket']=='LIVE'
    assert r['handoff']=={'eligible_for_editorial_module':True,'package_01_complete':True}

@pytest.mark.parametrize('kind,code',[('HOMEPAGE','REJECT_HOMEPAGE_URL'),('CATEGORY','REJECT_CATEGORY_URL'),('SEARCH_RESULTS','REJECT_SEARCH_URL'),('TAG_TOPIC','REJECT_TAG_TOPIC_URL'),('AGGREGATOR','REJECT_AGGREGATOR_AS_FINAL_SOURCE'),('REDIRECT_ONLY','REJECT_REDIRECT_TO_NON_ARTICLE'),('UNKNOWN','REJECT_NOT_DIRECT_ARTICLE')])
def test_bcd_invalid_page_classes(verify,kind,code):
    r=verify(page_type=kind); rejected(r,code); rejected(r,'REJECT_NOT_DIRECT_ARTICLE')
    assert r['source']['resolved_article_url'] is None


def test_configured_category_with_listing_cards_is_rejected(candidate,context):
    category_url='https://publisher.example/kinh-te'
    candidate=deepcopy(candidate)
    candidate['discovery']['discovered_url']=category_url
    html='<html><body><article>Listing one</article><article>Listing two</article></body></html>'
    evidence=parse_article(category_url,category_url,html,{
        'publisher.example':{
            'name':'Publisher','origin_quality':'DIRECT_REPUTABLE_ARTICLE',
            'category_paths':['/kinh-te'],
        }
    })
    result,_=SourceVerifier(FixedProvider(evidence)).verify(candidate,context)
    rejected(result,'REJECT_NOT_DIRECT_ARTICLE')
    rejected(result,'REJECT_CATEGORY_URL')
    assert result['source']['resolved_article_url'] is None

@pytest.mark.parametrize('url',['not-a-url','http://publisher.example/article','https://','https://user:password@publisher.example/article','javascript:alert(1)','https://publisher.example:broken/a','https://publisher.example/a b'])
def test_e_invalid_url(candidate,context,article,url):
    candidate=deepcopy(candidate); candidate['discovery']['discovered_url']=url
    provider=FixedProvider(article)
    r,_=SourceVerifier(provider).verify(candidate,context)
    rejected(r,'REJECT_INVALID_URL'); assert provider.calls==0
    assert r['source']['discovered_url']==url


def test_e_non_resolving(verify):
    rejected(verify(page_type='INACCESSIBLE',accessible=False,final_url=None,network_error='DNS failure'),'REJECT_ARTICLE_INACCESSIBLE')

@pytest.mark.parametrize('claim',['proposal -> approved','allegation -> proven','possibility -> certainty','old -> current','local -> universal','forecast -> actual'])
def test_f_headline_misrepresentation(verify,claim):
    rejected(verify(headline_supported=False,semantic_evidence='Article contradicts candidate: '+claim),'REJECT_HEADLINE_UNSUPPORTED')


def test_g_old(verify):
    rejected(verify(publication_time='2026-09-07T12:00:00+07:00'),'REJECT_OLD_NEWS')


def test_h_hot_without_development(verify):
    rejected(verify(publication_time='2026-09-09T06:00:00+07:00',material_development_supported=False),'REJECT_NO_NEW_DEVELOPMENT')


def test_i_hot_with_verified_development_today(verify):
    r=verify(publication_time='2026-09-08T06:00:00+07:00',material_development_time='2026-09-09T06:00:00+07:00',material_development_supported=True,development_evidence='The new decision was issued')
    assert r['verification']['status']=='VERIFIED'; assert r['freshness']['bucket']=='HOT'


def test_j_duplicate_canonical(candidate,context,article):
    article=replace(article,verified_event_key='city-decision-20260909')
    verifier=SourceVerifier(FixedProvider(article))
    assert verifier.verify(candidate,context)[0]['verification']['status']=='VERIFIED'
    rejected(verifier.verify(candidate,context)[0],'REJECT_DUPLICATE_STORY')


def test_j_duplicate_event_across_publishers(candidate,context,article):
    index=DuplicateIndex()
    index.accept(replace(article,final_url='https://other.example/report',canonical_url='https://other.example/report',verified_event_key='city-decision-20260909'),'2026-09-09T11:00:00+07:00')
    r,_=SourceVerifier(FixedProvider(replace(article,verified_event_key='city-decision-20260909')),index).verify(candidate,context)
    rejected(r,'REJECT_DUPLICATE_STORY')


def test_same_url_new_verified_phase_not_duplicate(candidate,context,article):
    index=DuplicateIndex()
    index.accept(replace(article,verified_event_key='city-proposal-20260908'),'2026-09-08T11:00:00+07:00')
    r,_=SourceVerifier(FixedProvider(replace(article,verified_event_key='city-decision-20260909')),index).verify(candidate,context)
    assert r['verification']['status']=='VERIFIED'
    assert {record.verified_event_key for record in index.records}=={
        'city-proposal-20260908','city-decision-20260909'}
    assert all(record.effective_freshness_time for record in index.records)


def test_same_url_uncertain_event_identity_reviews(candidate,context,article):
    index=DuplicateIndex()
    index.accept(replace(article,verified_event_key='city-proposal-20260908'),'2026-09-08T11:00:00+07:00')
    r,_=SourceVerifier(FixedProvider(replace(article,verified_event_key=None)),index).verify(candidate,context)
    reviewed(r,'REVIEW_DUPLICATE_UNCERTAIN')


def test_k_missing_publication(verify): reviewed(verify(publication_time=None),'REVIEW_PUBLICATION_TIME_UNCLEAR')
def test_l_event_date_mismatch(verify): rejected(verify(event_date_mismatch=True),'REJECT_HEADLINE_UNSUPPORTED')
def test_m_fact_failure(verify): rejected(verify(facts_supported=False),'REJECT_FACTS_UNSUPPORTED')

@pytest.mark.parametrize('changes,code',[
    ({'source_identity':False},'REJECT_SOURCE_UNVERIFIABLE'),
    ({'page_type':'HOMEPAGE','final_url':'https://publisher.example/'},'REJECT_REDIRECT_TO_NON_ARTICLE'),
    ({'recirculated_without_development':True},'REJECT_NO_NEW_DEVELOPMENT'),
])
def test_other_rejections(verify,changes,code): rejected(verify(**changes),code)

@pytest.mark.parametrize('changes,code',[
    ({'event_time_material':True,'event_time':None},'REVIEW_EVENT_TIME_UNCLEAR'),
    ({'source_identity':None},'REVIEW_SOURCE_IDENTITY_UNCLEAR'),
    ({'material_development_time':'2026-09-09T11:00:00+07:00','material_development_supported':None},'REVIEW_NEW_DEVELOPMENT_UNCLEAR'),
    ({'conflicting_sources':True},'REVIEW_CONFLICTING_SOURCES'),
    ({'duplicate_uncertain':True},'REVIEW_DUPLICATE_UNCERTAIN'),
    ({'headline_supported':None,'body':'A proposal is being discussed.'},'REVIEW_HEADLINE_SUPPORT_UNCLEAR'),
    ({'facts_supported':None,'body':'A proposal is being discussed.'},'REVIEW_FACT_SUPPORT_UNCLEAR'),
])
def test_all_other_reviews(verify,changes,code): reviewed(verify(**changes),code)


def test_blocked_corroborated(verify):
    r=verify(accessible=False,page_type='INACCESSIBLE',access_claim_corroborated=True,access_identity_corroborated=True,corroborating_urls=('https://other.example/exact-article',))
    reviewed(r,'REVIEW_ARTICLE_ACCESS_LIMITED_CORROBORATED')
    assert r['verification']['review_codes']==['REVIEW_ARTICLE_ACCESS_LIMITED_CORROBORATED']

@pytest.mark.parametrize('claim,identity,urls',[(True,False,('https://other.example/article',)),(False,True,('https://other.example/article',)),(True,True,())])
def test_blocked_insufficient_corroboration(verify,claim,identity,urls):
    rejected(verify(accessible=False,page_type='INACCESSIBLE',access_claim_corroborated=claim,access_identity_corroborated=identity,corroborating_urls=urls),'REJECT_ARTICLE_INACCESSIBLE')


def test_old_article_new_development_inside_exact_article(verify):
    r=verify(publication_time='2026-09-07T12:00:00+07:00',material_development_time='2026-09-09T11:15:00+07:00',material_development_supported=True,development_evidence='The new decision was issued')
    assert r['verification']['status']=='VERIFIED'
    assert r['freshness']['age_hours']==.75
    assert r['source']['publication_time']=='2026-09-07T12:00:00+07:00'


def test_old_article_new_development_only_elsewhere(verify):
    rejected(verify(publication_time='2026-09-07T12:00:00+07:00',material_development_time='2026-09-09T11:15:00+07:00',material_development_supported=False,corroborating_urls=('https://other.example/new',)),'REJECT_OLD_NEWS')


def test_cosmetic_update_does_not_refresh(verify):
    rejected(verify(publication_time='2026-09-07T12:00:00+07:00',last_updated_time='2026-09-09T11:00:00+07:00',substantive_update_supported=False),'REJECT_OLD_NEWS')


def test_substantive_update_can_refresh(verify):
    r=verify(publication_time='2026-09-07T12:00:00+07:00',last_updated_time='2026-09-09T11:00:00+07:00',substantive_update_supported=True,development_evidence='The new decision was issued')
    assert r['verification']['status']=='VERIFIED'


def test_material_time_precedes_later_cosmetic_update(verify):
    r=verify(publication_time='2026-09-07T12:00:00+07:00',last_updated_time='2026-09-09T11:59:00+07:00',material_development_time='2026-09-09T06:00:00+07:00',material_development_supported=True,development_evidence='The new decision was issued')
    assert r['freshness']['age_hours']==6

@pytest.mark.parametrize('published,bucket,code',[
    ('2026-09-09T12:00:00+07:00','LIVE',None),
    ('2026-09-09T10:00:00+07:00','LIVE',None),
    ('2026-09-09T09:59:59+07:00','HOT','REJECT_NO_NEW_DEVELOPMENT'),
    ('2026-09-08T12:00:00+07:00','HOT','REJECT_NO_NEW_DEVELOPMENT'),
    ('2026-09-08T11:59:59+07:00','OLD','REJECT_OLD_NEWS')])
def test_boundary_times(verify,published,bucket,code):
    r=verify(publication_time=published); assert r['freshness']['bucket']==bucket
    if code: rejected(r,code)
    else: assert r['verification']['status']=='VERIFIED'


def test_hot_new_development_yesterday(verify):
    rejected(verify(publication_time='2026-09-08T18:00:00+07:00',material_development_time='2026-09-08T23:00:00+07:00',material_development_supported=True,development_evidence='The new decision was issued'),'REJECT_NO_NEW_DEVELOPMENT')

@pytest.mark.parametrize('time',['2026-09-10T11:00:00+07:00','2026-09-09T11:00:00','not a date'])
def test_bad_publication_is_review(verify,time): reviewed(verify(publication_time=time),'REVIEW_PUBLICATION_TIME_UNCLEAR')


def test_original_evidence_preserved(candidate,context,article):
    original=deepcopy(candidate)
    r,audit=SourceVerifier(FixedProvider(replace(article,headline_supported=False))).verify(candidate,context)
    assert candidate==original
    assert r['scores']==candidate['scores']
    assert r['content']['candidate_title']==candidate['normalized']['title']
    assert audit['candidate']==candidate
    assert audit['evidence']['body']==article.body


def test_failed_candidate_does_not_poison_duplicate_index(candidate,context,article):
    index=DuplicateIndex()
    SourceVerifier(FixedProvider(replace(article,headline_supported=False)),index).verify(candidate,context)
    r,_=SourceVerifier(FixedProvider(article),index).verify(candidate,context)
    assert r['verification']['status']=='VERIFIED'
