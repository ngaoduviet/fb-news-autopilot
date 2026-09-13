import json

from PIL import Image
import pytest

import fb_news_autopilot.live_publish as live_publish
from fb_news_autopilot.assets import write_asset_manifest
from fb_news_autopilot.editorial import compose_facebook_caption
from fb_news_autopilot.facebook.auth import MetaConfig, run_preflight
from fb_news_autopilot.facebook.client import MetaClient
from fb_news_autopilot.facebook.errors import MetaError
from fb_news_autopilot.image import render_poster
from fb_news_autopilot.live_publish import LivePublishHold, run_live_publish_test
from fb_news_autopilot.models import timestamp
from fb_news_autopilot.state import StateStore
from test_editorial_image import editorial_document
from test_meta_state import Transport, meta_requirements
from test_queueing import decision, make_queue


def gate6_fixture(tmp_path, context, observation, article, *, status='VERIFIED'):
    queue,_,directory=make_queue(tmp_path,context,observation,article)
    semantic=decision(
        queue,status,
        [] if status == 'VERIFIED' else ['REVIEW_HEADLINE_SUPPORT_UNCLEAR'],
        status == 'VERIFIED')
    (directory/'semantic_decisions.json').write_text(json.dumps(semantic),encoding='utf-8')
    if status == 'VERIFIED':
        document=editorial_document(queue)
        editorial_dir=directory/'editorial'; editorial_dir.mkdir()
        (editorial_dir/(document['news_id']+'.json')).write_text(
            json.dumps(document),encoding='utf-8')
        source=tmp_path/'owned-source.png'
        Image.new('RGB',(1600,900),'blue').save(source)
        poster,metadata=render_poster(
            source,document,'OWNED',directory/'assets'/(document['news_id']+'.png'))
        write_asset_manifest(
            context.run_id,document['news_id'],source,poster,'OWNED',metadata,root=tmp_path)
    return {
        'run_id': context.run_id,
        'news_id': queue['candidates'][0]['news_id'],
        'queue_root': tmp_path,
        'history_path': tmp_path/'history.db',
        'requirements_path': meta_requirements(tmp_path,['CREATE_CONTENT','MODERATE']),
        'authorization_path': tmp_path/'meta-publication-authorization.json',
        'config': MetaConfig('42','fixture-token','v26.0'),
        'environment': {'META_LIVE_PUBLISH_TEST':'1','META_AUTO_PUBLISH':'false'},
        'now': timestamp(context.run_at),
    }


def execute(fixture, transport, **changes):
    values={**fixture,**changes}
    return run_live_publish_test(
        values['run_id'],values['news_id'],values.get('confirm_page_id','42'),
        queue_root=values['queue_root'],history_path=values['history_path'],
        requirements_path=values['requirements_path'],
        authorization_path=values['authorization_path'],config=values['config'],
        client=MetaClient('v26.0','fixture-token',transport=transport),
        environment=values['environment'],reporter=values.get('reporter'),
        selector=values.get('selector',live_publish.select_publishable),now=values['now'])


def successful_transport():
    return Transport(responses=[
        {'id':'42','name':'Tin Nóng 5s'},
        {'id':'photo-1','post_id':'42_99'},
        {'id':'comment-1'},
        {'id':'42_99','is_published':True,'permalink_url':'https://facebook.example/post'},
    ])


def test_missing_live_publish_switch_blocks_before_meta_call(
        tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    fixture['environment']={'META_AUTO_PUBLISH':'false'}
    transport=Transport()
    with pytest.raises(LivePublishHold) as error:
        execute(fixture,transport)
    assert error.value.code=='HOLD_LIVE_PUBLISH_TEST_DISABLED'
    assert transport.calls==[]


def test_conflicting_auto_publish_switch_blocks_before_meta_call(
        tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    fixture['environment']['META_AUTO_PUBLISH']='true'
    transport=Transport()
    with pytest.raises(LivePublishHold) as error:
        execute(fixture,transport)
    assert error.value.code=='HOLD_CONFLICTING_PUBLISH_SWITCHES'
    assert transport.calls==[]


def test_wrong_confirm_page_id_blocks_before_meta_call(tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    transport=Transport()
    with pytest.raises(LivePublishHold) as error:
        execute(fixture,transport,confirm_page_id='84')
    assert error.value.code=='HOLD_PAGE_CONFIRMATION_MISMATCH'
    assert transport.calls==[]


def test_preflight_failure_blocks_all_meta_writes(tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    transport=Transport(errors=[MetaError('PERMISSION_OR_API_ERROR','invalid token',400)])
    with pytest.raises(LivePublishHold) as error:
        execute(fixture,transport)
    assert error.value.code=='HOLD_META_PREFLIGHT_FAILED'
    assert all(call[0]=='GET' for call in transport.calls)


def test_non_verified_candidate_blocks_write(tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article,status='REVIEW')
    transport=Transport(responses=[{'id':'42','name':'Tin Nóng 5s'}])
    with pytest.raises(LivePublishHold) as error:
        execute(fixture,transport)
    assert error.value.code=='HOLD_SEMANTIC_STATUS'
    assert all(call[0]=='GET' for call in transport.calls)


def test_handoff_false_candidate_blocks_write(tmp_path,context,observation,article,monkeypatch):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    queue,semantic=live_publish.load_semantic_decisions(context.run_id,root=tmp_path)
    semantic['decisions'][0]['handoff_allowed']=False
    monkeypatch.setattr(live_publish,'load_semantic_decisions',lambda *args,**kwargs:(queue,semantic))
    transport=Transport(responses=[{'id':'42','name':'Tin Nóng 5s'}])
    with pytest.raises(LivePublishHold) as error:
        execute(fixture,transport)
    assert error.value.code=='HOLD_EDITORIAL_NOT_ALLOWED'
    assert all(call[0]=='GET' for call in transport.calls)


def test_not_selected_candidate_blocks_write(tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    fixture['selector']=lambda *args,**kwargs:{'selected_news_ids':[],'holds':{}}
    transport=Transport(responses=[{'id':'42','name':'Tin Nóng 5s'}])
    with pytest.raises(LivePublishHold) as error:
        execute(fixture,transport)
    assert error.value.code=='HOLD_NOT_SELECTED'
    assert all(call[0]=='GET' for call in transport.calls)


@pytest.mark.parametrize('manifest_change,expected_code',[
    ({'image_rights_status':'UNKNOWN'},'HOLD_IMAGE_RIGHTS'),
    ({'image_layout':'MULTI'},'HOLD_IMAGE_LAYOUT'),
    ({'width':1200},'HOLD_IMAGE_DIMENSIONS'),
])
def test_invalid_live_asset_blocks_write(
        tmp_path,context,observation,article,monkeypatch,manifest_change,expected_code):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    manifest,poster=live_publish.load_asset_manifest(context.run_id,fixture['news_id'],root=tmp_path)
    monkeypatch.setattr(
        live_publish,'load_asset_manifest',
        lambda *args,**kwargs:({**manifest,**manifest_change},poster))
    transport=Transport(responses=[{'id':'42','name':'Tin Nóng 5s'}])
    with pytest.raises(LivePublishHold) as error:
        execute(fixture,transport)
    assert error.value.code==expected_code
    assert all(call[0]=='GET' for call in transport.calls)


def test_successful_gate6_calls_photo_once_and_uses_exact_caption(
        tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    summaries=[]
    transport=successful_transport()
    def report(summary):
        assert not any(call[0]=='POST' for call in transport.calls)
        summaries.append(summary)
    fixture['reporter']=report
    result=execute(fixture,transport)
    posts=[call for call in transport.calls if call[0]=='POST' and call[1].endswith('/42/photos')]
    comments=[call for call in transport.calls if call[0]=='POST' and call[1].endswith('/42_99/comments')]
    assert len(posts)==1 and len(comments)==1
    _,_,editorials=live_publish.load_editorial(context.run_id,root=tmp_path)
    assert posts[0][2]['caption']==compose_facebook_caption(editorials[fixture['news_id']])
    assert posts[0][2]['caption'].splitlines()[-1].count('#')==5
    assert summaries[0]['event']=='PRE_WRITE_SUMMARY'
    assert summaries[0]['exactly_5_hashtags_confirmed'] is True
    assert result['ok'] is True and result['state']=='VERIFIED_ON_FACEBOOK'


def test_ambiguous_photo_network_result_requires_reconciliation(
        tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    transport=Transport(
        responses=[{'id':'42','name':'Tin Nóng 5s'}],
        errors=[None,MetaError('NETWORK_ERROR','connection lost')])
    result=execute(fixture,transport)
    assert result['state']=='RECONCILIATION_REQUIRED'
    assert result['publication']['status']=='RECONCILIATION_REQUIRED'
    assert not any(call[1].endswith('/comments') for call in transport.calls)


def test_definite_photo_api_failure_persists_failed_state(
        tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    transport=Transport(
        responses=[{'id':'42','name':'Tin Nóng 5s'}],
        errors=[None,MetaError('PERMISSION_OR_API_ERROR','write denied',400)])
    with pytest.raises(MetaError):
        execute(fixture,transport)
    store=StateStore(fixture['history_path'],context.run_id)
    assert store.current(fixture['news_id']).value=='FAILED'
    assert not any(call[1].endswith('/comments') for call in transport.calls)


def test_missing_post_id_requires_reconciliation_and_never_comments(
        tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    transport=Transport(responses=[
        {'id':'42','name':'Tin Nóng 5s'},{'id':'photo-only'}])
    result=execute(fixture,transport)
    assert result['state']=='RECONCILIATION_REQUIRED'
    assert result['publication']['photo_id']=='photo-only'
    assert result['publication']['post_id'] is None
    assert not any(call[1].endswith('/photo-only/comments') for call in transport.calls)
    with pytest.raises(LivePublishHold) as error:
        execute(fixture,Transport(responses=[{'id':'42','name':'Tin Nóng 5s'}]))
    assert error.value.code=='RECONCILIATION_REQUIRED'


def test_comment_failure_then_retry_never_recreates_photo(
        tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    first_transport=Transport(
        responses=[{'id':'42','name':'Tin Nóng 5s'},{'id':'photo-1','post_id':'42_99'}],
        errors=[None,None,MetaError('API_ERROR','comment unavailable',500)])
    first=execute(fixture,first_transport)
    assert first['state']=='PUBLISHED_COMMENT_PENDING'
    retry_transport=Transport(responses=[
        {'id':'42','name':'Tin Nóng 5s'},
        {'id':'comment-1'},
        {'id':'42_99','is_published':True}])
    retry=execute(fixture,retry_transport)
    assert retry['ok'] is True
    assert not any(call[1].endswith('/42/photos') for call in retry_transport.calls)
    assert len([call for call in first_transport.calls if call[1].endswith('/42/photos')])==1


def test_duplicate_idempotency_key_blocks_second_photo(tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    first_transport=successful_transport()
    execute(fixture,first_transport)
    second_transport=Transport(responses=[{'id':'42','name':'Tin Nóng 5s'}])
    with pytest.raises(LivePublishHold) as error:
        execute(fixture,second_transport)
    assert error.value.code=='HOLD_DUPLICATE_PUBLICATION'
    assert not any(call[0]=='POST' for call in second_transport.calls)
    assert len([call for call in first_transport.calls if call[1].endswith('/42/photos')])==1


def test_existing_success_evidence_blocks_another_gate6_post(
        tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    fixture['authorization_path'].write_text(json.dumps({
        'page_id':'42','graph_api_version':'v26.0',
        'tested_at':'2026-09-13T12:00:00+00:00',
        'operations':[
            {'name':'photo_publish','status':'EXPLICITLY_PROVEN'},
            {'name':'first_comment','status':'EXPLICITLY_PROVEN'}],
        'success':True}),encoding='utf-8')
    transport=Transport(responses=[{'id':'42','name':'Tin Nóng 5s'}])
    with pytest.raises(LivePublishHold) as error:
        execute(fixture,transport)
    assert error.value.code=='HOLD_GATE6_ALREADY_COMPLETED'
    assert not any(call[0]=='POST' for call in transport.calls)


def test_success_stores_non_secret_authorization_evidence(
        tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    result=execute(fixture,successful_transport())
    evidence=json.loads(fixture['authorization_path'].read_text(encoding='utf-8'))
    assert set(evidence)=={'page_id','graph_api_version','tested_at','operations','success'}
    assert evidence['success'] is True
    assert {(item['name'],item['status']) for item in evidence['operations']}=={
        ('photo_publish','EXPLICITLY_PROVEN'),('first_comment','EXPLICITLY_PROVEN')}
    assert 'token' not in json.dumps(evidence).casefold()
    preflight=run_preflight(
        fixture['config'],MetaClient('v26.0','fixture-token',transport=Transport(
            responses=[{'id':'42','name':'Tin Nóng 5s'}])),
        requirements_path=fixture['requirements_path'],
        authorization_path=fixture['authorization_path'])
    assert result['publication_authorization']=='EXPLICITLY_VERIFIED'
    assert preflight.publication_authorization=='EXPLICITLY_VERIFIED'
    assert preflight.publication_ready is True


def test_gate6_output_never_contains_token_and_does_not_change_switches(
        tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    original=dict(fixture['environment']); summaries=[]; fixture['reporter']=summaries.append
    result=execute(fixture,successful_transport())
    serialized=json.dumps([summaries,result])
    assert 'fixture-token' not in serialized
    assert fixture['environment']==original
    assert fixture['environment']['META_AUTO_PUBLISH']=='false'


def test_gate6_publication_history_contains_non_secret_result(
        tmp_path,context,observation,article):
    fixture=gate6_fixture(tmp_path,context,observation,article)
    result=execute(fixture,successful_transport())
    record=StateStore(fixture['history_path'],context.run_id).publication(
        result['idempotency_key'])
    assert record['run_id']==context.run_id
    assert record['news_id']==fixture['news_id']
    assert record['page_id']=='42'
    assert record['photo_id']=='photo-1'
    assert record['post_id']=='42_99'
    assert record['status']=='VERIFIED_ON_FACEBOOK'
    assert 'token' not in json.dumps(record).casefold()
