import json
from dataclasses import replace

import pytest

from fb_news_autopilot.queueing import HandoffHold,load_semantic_decisions,write_candidate_queue
from fb_news_autopilot.radar import NewsRadar
from conftest import FixedProvider


def make_queue(tmp_path,context,observation,article):
    candidates=NewsRadar().run(context,[observation])[0]
    queue,path=write_candidate_queue(context,candidates,FixedProvider(article),root=tmp_path)
    return queue,path,path.parent


def decision(queue,status='VERIFIED',reason_codes=None,handoff_allowed=None):
    item=queue['candidates'][0]
    if handoff_allowed is None: handoff_allowed=status=='VERIFIED'
    return {'schema_version':'1.0.0','run_id':queue['run_id'],'generated_at':queue['generated_at'],
        'decisions':[{'news_id':item['news_id'],'status':status,'reason_codes':reason_codes or [],
            'article_title_verified':True if status=='VERIFIED' else None,
            'publication_time_verified':True if status=='VERIFIED' else None,
            'facts_supported':True if status=='VERIFIED' else None,'event_time_verified':None,
            'new_development_verified':None,'material_development_time':None,
            'verified_event_key':'event-one' if status=='VERIFIED' else None,
            'verified_facts':['City approved the new benefit'] if status=='VERIFIED' else [],
            'unsupported_claims':[],'evidence':[{'claim':'approval','quote':'The new decision was issued',
                'source_url':item['source_url']}],
            'confidence':0.9,'handoff_allowed':handoff_allowed}]}


def test_candidate_queue_schema_and_evidence_files(tmp_path,context,observation,article):
    queue,path,directory=make_queue(tmp_path,context,observation,article)
    item=queue['candidates'][0]
    assert path.name=='candidates.json'
    assert (directory/item['article_text_path']).read_text()==article.body
    assert item['needs_semantic_verification'] is True
    assert item['image_rights_status']=='UNKNOWN'
    assert 'verification' not in item


def test_semantic_handoff_invalid_json_fails_closed(tmp_path,context,observation,article):
    _,_,directory=make_queue(tmp_path,context,observation,article)
    (directory/'semantic_decisions.json').write_text('{broken')
    with pytest.raises(HandoffHold) as error:
        load_semantic_decisions(context.run_id,root=tmp_path)
    assert error.value.code=='HOLD_SEMANTIC_INVALID'


def test_semantic_timeout_marker_fails_closed(tmp_path,context,observation,article):
    _,_,directory=make_queue(tmp_path,context,observation,article)
    (directory/'semantic.timeout').write_text('timeout',encoding='utf-8')
    with pytest.raises(HandoffHold) as error:
        load_semantic_decisions(context.run_id,root=tmp_path)
    assert error.value.code=='HOLD_SEMANTIC_TIMEOUT'


@pytest.mark.parametrize('status,code',[('REVIEW','REVIEW_HEADLINE_SUPPORT_UNCLEAR'),('REJECTED','REJECT_HEADLINE_UNSUPPORTED')])
def test_review_and_rejected_never_handoff(tmp_path,context,observation,article,status,code):
    queue,_,directory=make_queue(tmp_path,context,observation,article)
    payload=decision(queue,status,[code],False)
    (directory/'semantic_decisions.json').write_text(json.dumps(payload))
    _,loaded=load_semantic_decisions(context.run_id,root=tmp_path)
    assert loaded['decisions'][0]['handoff_allowed'] is False


def test_verified_semantic_handoff(tmp_path,context,observation,article):
    queue,_,directory=make_queue(tmp_path,context,observation,article)
    (directory/'semantic_decisions.json').write_text(json.dumps(decision(queue)))
    _,loaded=load_semantic_decisions(context.run_id,root=tmp_path)
    assert loaded['decisions'][0]['status']=='VERIFIED'
    assert loaded['decisions'][0]['handoff_allowed'] is True


def test_semantic_quote_must_exist_in_exact_article(tmp_path,context,observation,article):
    queue,_,directory=make_queue(tmp_path,context,observation,article)
    payload=decision(queue); payload['decisions'][0]['evidence'][0]['quote']='invented quote'
    (directory/'semantic_decisions.json').write_text(json.dumps(payload))
    with pytest.raises(HandoffHold) as error:
        load_semantic_decisions(context.run_id,root=tmp_path)
    assert error.value.code=='HOLD_EVIDENCE_QUOTE_INVALID'


def test_candidate_fetch_failure_is_isolated_when_audit_callback_exists(tmp_path,context,observation,article):
    other=replace(observation,url='https://publisher.example/news/second',headline='Second current event')
    candidates=NewsRadar().run(context,[observation,other])[0]
    failures=[]
    class Provider:
        def inspect(self,candidate,ctx):
            url=candidate['discovery']['discovered_url']
            if url==observation.url:
                raise ValueError('fixture parser failure')
            return replace(article,requested_url=url,final_url=url,canonical_url=url,title=candidate['normalized']['title'])
    queue,_=write_candidate_queue(context,candidates,Provider(),root=tmp_path,
                                  on_failure=lambda exc,news_id: failures.append((type(exc).__name__,news_id)))
    assert len(queue['candidates'])==1
    assert failures[0][0]=='ValueError'
