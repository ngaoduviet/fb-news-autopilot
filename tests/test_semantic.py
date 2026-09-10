from copy import deepcopy
from dataclasses import replace
import pytest
from fb_news_autopilot.semantic import validate_assessment
from fb_news_autopilot.sources import WebSourceProvider
from fb_news_autopilot.verifier import SourceVerifier
from test_sources import HTML,CONFIG
from conftest import FixedProvider


def response():
    return {'headline':{'supported':True,'explanation':'Article states approval','quotes':['City approved the new benefit.']},
        'facts':{'supported':True,'explanation':'Exact amount','quotes':['The benefit is 500 units.']},
        'event_time':None,'event_quote':None,'event_time_material':False,'event_date_mismatch':False,
        'material_development_time':None,'material_development_supported':None,
        'substantive_update_supported':None,'development_quote':None,
        'verified_event_key':'city-benefit-approval-20260909','duplicate_uncertain':False,'recirculated_without_development':False}


def test_end_to_end_html_external_semantic_boundary(candidate,context):
    class Fetch:
        def get(self,url): return url,HTML
    evidence=WebSourceProvider(Fetch(),CONFIG).inspect(candidate,context)
    evidence=replace(evidence,**validate_assessment(evidence,response()))
    result,audit=SourceVerifier(FixedProvider(evidence)).verify(candidate,context)
    assert result['verification']['status']=='VERIFIED'
    assert audit['evidence']['raw_document']==HTML


def test_lexical_match_alone_never_verifies(candidate,context):
    class Fetch:
        def get(self,url): return url,HTML
    result,_=SourceVerifier(WebSourceProvider(Fetch(),CONFIG)).verify(candidate,context)
    assert result['verification']['status']=='REVIEW'
    assert result['verification']['headline_supported'] is None


def test_fabricated_quote_becomes_unclear(candidate,context,article):
    data=response(); data['headline']['quotes']=['This is not in the article']
    r=validate_assessment(article,data)
    assert r['headline_supported'] is None


def test_malformed_external_output_becomes_unclear(candidate,context,article):
    r=validate_assessment(article,{'status':'VERIFIED'})
    assert r['headline_supported'] is None; assert r['facts_supported'] is None


def test_publisher_mismatch_reviews(candidate,context):
    class Fetch:
        def get(self,url): return url,HTML
    candidate=deepcopy(candidate); candidate['discovery']['publisher_name']='Different source'
    evidence=WebSourceProvider(Fetch(),CONFIG).inspect(candidate,context)
    evidence=replace(evidence,**validate_assessment(evidence,response()))
    result,_=SourceVerifier(FixedProvider(evidence)).verify(candidate,context)
    assert result['verification']['status']=='REVIEW'
    assert 'REVIEW_SOURCE_IDENTITY_UNCLEAR' in result['verification']['review_codes']


def test_event_timestamp_without_evidence_cannot_be_invented(candidate,context,article):
    data=response(); data['event_time']='2026-09-09T11:00:00+07:00'
    result=validate_assessment(article,data)
    assert result['event_time'] is None
    assert result['event_time_material'] is True
