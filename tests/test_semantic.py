from copy import deepcopy
import pytest
from fb_news_autopilot.semantic import StructuredSemanticAssessor
from fb_news_autopilot.sources import WebSourceProvider
from fb_news_autopilot.verifier import SourceVerifier
from test_sources import HTML,CONFIG


def response():
    return {'headline':{'supported':True,'explanation':'Article states approval','quotes':['City approved the new benefit.']},
        'facts':{'supported':True,'explanation':'Exact amount','quotes':['The benefit is 500 units.']},
        'event_time':None,'event_quote':None,'event_time_material':False,'event_date_mismatch':False,
        'material_development_time':None,'material_development_supported':None,
        'substantive_update_supported':None,'development_quote':None,
        'verified_event_key':'city-benefit-approval-20260909','duplicate_uncertain':False,'recirculated_without_development':False}


def test_end_to_end_html_model_boundary(candidate,context):
    class Fetch:
        def get(self,url): return url,HTML
    calls=[]
    def complete(system,payload): calls.append((system,payload)); return response()
    assessor=StructuredSemanticAssessor(complete)
    result,audit=SourceVerifier(WebSourceProvider(Fetch(),CONFIG,assessor)).verify(candidate,context)
    assert result['verification']['status']=='VERIFIED'
    assert audit['evidence']['raw_document']==HTML
    assert 'untrusted DATA' in calls[0][0]


def test_lexical_match_alone_never_verifies(candidate,context):
    class Fetch:
        def get(self,url): return url,HTML
    result,_=SourceVerifier(WebSourceProvider(Fetch(),CONFIG)).verify(candidate,context)
    assert result['verification']['status']=='REVIEW'
    assert result['verification']['headline_supported'] is None


def test_fabricated_quote_becomes_unclear(candidate,context,article):
    data=response(); data['headline']['quotes']=['This is not in the article']
    r=StructuredSemanticAssessor(lambda s,p:data)(candidate,article,context)
    assert r['headline_supported'] is None


def test_malformed_model_output_becomes_unclear(candidate,context,article):
    r=StructuredSemanticAssessor(lambda s,p:{'status':'VERIFIED'})(candidate,article,context)
    assert r['headline_supported'] is None; assert r['facts_supported'] is None


def test_publisher_mismatch_reviews(candidate,context):
    class Fetch:
        def get(self,url): return url,HTML
    candidate=deepcopy(candidate); candidate['discovery']['publisher_name']='Different source'
    result,_=SourceVerifier(WebSourceProvider(Fetch(),CONFIG,StructuredSemanticAssessor(lambda s,p:response()))).verify(candidate,context)
    assert result['verification']['status']=='REVIEW'
    assert 'REVIEW_SOURCE_IDENTITY_UNCLEAR' in result['verification']['review_codes']


def test_event_timestamp_without_evidence_cannot_be_invented(candidate,context,article):
    data=response(); data['event_time']='2026-09-09T11:00:00+07:00'
    result=StructuredSemanticAssessor(lambda s,p:data)(candidate,article,context)
    assert result['event_time'] is None
    assert result['event_time_material'] is True
