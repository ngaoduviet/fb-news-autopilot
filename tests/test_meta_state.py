import json

from PIL import Image
import pytest

from fb_news_autopilot.facebook.auth import MetaConfig, run_preflight
from fb_news_autopilot.facebook.client import MetaClient
from fb_news_autopilot.facebook.comments import publish_first_comment
from fb_news_autopilot.facebook.errors import MetaError
from fb_news_autopilot.facebook.publisher import normalize_photo_response, publish_photo
from fb_news_autopilot.policy import auto_publish_enabled, compliance_gate, load_policy
from fb_news_autopilot.publication import PublicationCoordinator
from fb_news_autopilot.state import State, StateStore, publication_key
from fb_news_autopilot.selection import rank_publishable, select_publishable
from fb_news_autopilot.image import render_poster
from fb_news_autopilot.assets import write_asset_manifest
from fb_news_autopilot.cycle import run_cycle
from test_editorial_image import editorial_document
from test_queueing import decision, make_queue


class Transport:
    def __init__(self, responses=(), errors=()):
        self.responses = list(responses)
        self.errors = list(errors)
        self.calls = []

    def request(self, method, url, fields, files=None):
        self.calls.append((method, url, fields, files))
        if self.errors:
            error = self.errors.pop(0)
            if error:
                raise error
        return 200, self.responses.pop(0)


PERMISSIONS=['pages_show_list','pages_read_engagement','pages_manage_posts','pages_manage_engagement']


def preflight(tasks, permissions=PERMISSIONS):
    transport=Transport(responses=[{'id':'42','name':'Tin Nóng 5s','tasks':tasks},
        {'data':[{'permission':name,'status':'granted'} for name in permissions]}])
    return run_preflight(MetaConfig('42','fixture-token','v26.0'),
                         MetaClient('v26.0','fixture-token',transport=transport))


def prepare_ready(store, news_id):
    for state in (State.DISCOVERED,State.FETCHED,State.SEMANTIC_PENDING,State.VERIFIED,
                  State.EDITORIAL_PENDING,State.EDITORIAL_READY,State.ASSET_PENDING,
                  State.ASSET_READY,State.READY_TO_PUBLISH):
        store.transition(news_id,state,'test fixture')


def publication_editorial():
    return {'editorial_version':'v1','recommended_caption':'[NÓNG] caption',
            'hashtags':['#Mot','#Hai','#Ba','#Bon','#Nam'],'first_comment':'first comment'}


def test_meta_missing_credentials_preflight(monkeypatch):
    for name in ('META_PAGE_ID', 'META_PAGE_ACCESS_TOKEN', 'META_GRAPH_API_VERSION'):
        monkeypatch.delenv(name, raising=False)
    result = run_preflight()
    assert result.ok is False
    assert result.error_category == 'MISSING_CREDENTIALS'


def test_meta_token_never_logged():
    token = 'meta-sensitive-token-value'
    transport = Transport(errors=[MetaError('API_ERROR', 'access_token=' + token, 400)])
    client = MetaClient('v26.0', token, transport=transport)
    with pytest.raises(MetaError) as error:
        client.request('GET', '/page', logical_name='test')
    assert token not in str(error.value)
    assert token not in json.dumps(client.audit)


def test_meta_preflight_identity_and_tasks():
    transport = Transport(responses=[{'id': '42', 'name': 'Tin Nóng 5s',
                                      'tasks': ['CREATE_CONTENT', 'MODERATE']},
                                     {'data': [
                                         {'permission': 'pages_show_list', 'status': 'granted'},
                                         {'permission': 'pages_read_engagement', 'status': 'granted'},
                                         {'permission': 'pages_manage_posts', 'status': 'granted'},
                                         {'permission': 'pages_manage_engagement', 'status': 'granted'},
                                     ]}])
    client = MetaClient('v26.0', 'fixture-token', transport=transport)
    result = run_preflight(MetaConfig('42', 'fixture-token', 'v26.0'), client)
    assert result.ok is True
    assert result.page_id == '42'
    assert 'pages_manage_posts' in result.permissions


@pytest.mark.parametrize('tasks',[['CREATE_CONTENT','MODERATE'],
    ['PROFILE_PLUS_CREATE_CONTENT','PROFILE_PLUS_MODERATE'],['PROFILE_PLUS_FULL_CONTROL']])
def test_meta_capability_aliases_pass(tasks):
    result=preflight(tasks)
    assert result.ok is True
    assert set(result.normalized_capabilities)=={'publish_content','moderate'}
    assert result.raw_tasks==tuple(tasks)


def test_meta_unrelated_tasks_and_missing_permissions_fail():
    result=preflight(['PROFILE_PLUS_ANALYZE'])
    assert set(result.missing_capabilities)=={'publish_content','moderate'}
    assert result.error_category=='INSUFFICIENT_PAGE_TASKS'
    for missing in ('pages_manage_posts','pages_manage_engagement'):
        result=preflight(['CREATE_CONTENT','MODERATE'],[p for p in PERMISSIONS if p!=missing])
        assert result.error_category=='INSUFFICIENT_PERMISSIONS'
        assert result.missing_permissions==(missing,)


def test_photo_publish_request_mock_and_response_normalization(tmp_path):
    image_path = tmp_path / 'poster.png'
    Image.new('RGB', (1080, 1350), 'red').save(image_path)
    transport = Transport(responses=[{'id': 'photo-1', 'post_id': '42_99'}])
    client = MetaClient('v26.0', 'fixture-token', transport=transport)
    result = publish_photo(client, '42', image_path, 'Caption')
    method, url, fields, files = transport.calls[0]
    assert (method, url.rsplit('/', 2)[-2:]) == ('POST', ['42', 'photos'])
    assert fields['caption'] == 'Caption' and files['source'] == image_path
    assert result.photo_id == 'photo-1' and result.post_id == '42_99'
    photo_only = normalize_photo_response('42', {'id': 'photo-2'})
    assert photo_only.photo_id == 'photo-2' and photo_only.post_id is None


def test_comment_only_after_confirmed_post():
    client = MetaClient('v26.0', 'fixture-token', transport=Transport(responses=[]))
    with pytest.raises(ValueError):
        publish_first_comment(client, None, 'comment')
    assert client.transport.calls == []


def test_comment_retry_does_not_duplicate_post(tmp_path):
    image_path = tmp_path / 'poster.png'
    Image.new('RGB', (1080, 1350), 'red').save(image_path)
    transport = Transport(responses=[{'id': 'photo-1', 'post_id': '42_99'}, {'id': 'comment-1'},
                                     {'id': '42_99', 'is_published': True,
                                      'permalink_url': 'https://facebook.example/post'}],
                          errors=[None, MetaError('API_ERROR', 'temporary'), None, None])
    client = MetaClient('v26.0', 'fixture-token', transport=transport)
    store = StateStore(tmp_path / 'history.db', 'run-1')
    editorial = publication_editorial()
    coordinator = PublicationCoordinator(client, store)
    prepare_ready(store,'news-1')
    first = coordinator.execute(news_id='news-1', canonical_url='https://example.com/a',
                                editorial=editorial, image_path=image_path, page_id='42')
    assert transport.calls[0][2]['caption']=='[NÓNG] caption\n\n#Mot #Hai #Ba #Bon #Nam'
    second = coordinator.execute(news_id='news-1', canonical_url='https://example.com/a',
                                 editorial=editorial, image_path=image_path, page_id='42')
    assert first['state'] == 'PUBLISHED_COMMENT_PENDING'
    assert second['state'] == 'VERIFIED_ON_FACEBOOK'
    assert [call[1].endswith('/photos') for call in transport.calls].count(True) == 1
    assert [call[1].endswith('/42_99') for call in transport.calls].count(True) == 1
    assert store.publication(second['idempotency_key'])['status'] == 'VERIFIED_ON_FACEBOOK'
    calls=len(transport.calls)
    third = coordinator.execute(news_id='news-1', canonical_url='https://example.com/a',
                                editorial=editorial, image_path=image_path, page_id='42')
    assert third['state']=='VERIFIED_ON_FACEBOOK' and len(transport.calls)==calls


def test_photo_id_is_never_used_as_comment_post_id(tmp_path):
    image_path=tmp_path/'poster.png'; Image.new('RGB',(1080,1350),'red').save(image_path)
    transport=Transport(responses=[{'id':'photo-only'}])
    client=MetaClient('v26.0','fixture-token',transport=transport)
    store=StateStore(tmp_path/'history.db','run-1'); prepare_ready(store,'news-1')
    result=PublicationCoordinator(client,store).execute(news_id='news-1',canonical_url='https://example.com/a',
        editorial=publication_editorial(),image_path=image_path,page_id='42')
    assert result['state']=='PUBLISHED_COMMENT_PENDING'
    assert result['publication']['photo_id']=='photo-only' and result['publication']['post_id'] is None
    assert len(transport.calls)==1
    again=PublicationCoordinator(client,store).execute(news_id='news-1',canonical_url='https://example.com/a',
        editorial=publication_editorial(),image_path=image_path,page_id='42')
    assert again['state']=='PUBLISHED_COMMENT_PENDING' and len(transport.calls)==1


def test_publication_coordinator_persists_operational_transitions(tmp_path):
    image_path=tmp_path/'poster.png'; Image.new('RGB',(1080,1350),'red').save(image_path)
    transport=Transport(responses=[{'id':'photo','post_id':'42_9'},{'id':'comment'},
        {'id':'42_9','is_published':True}])
    store=StateStore(tmp_path/'history.db','run-1'); prepare_ready(store,'news-1')
    PublicationCoordinator(MetaClient('v26.0','token',transport=transport),store).execute(
        news_id='news-1',canonical_url='https://example.com/a',editorial=publication_editorial(),
        image_path=image_path,page_id='42')
    tail=[row['next_state'] for row in store.transitions('news-1')[-4:]]
    assert tail==['PUBLISHING','PUBLISHED','COMMENTED','VERIFIED_ON_FACEBOOK']


def test_max_posts_per_cycle_is_a_hard_deterministic_cap():
    assert rank_publishable([(90,'b'),(90,'a'),(80,'c')],1)==['a']


def test_duplicate_cooldown_queries_canonical_url_across_versions(tmp_path):
    store=StateStore(tmp_path/'history.db','run-1')
    store.reserve_publication('old-news','https://example.com/a','v1')
    assert store.recent_publication('https://example.com/a','2000-01-01T00:00:00+00:00',
                                    exclude_news_id='new-news')['news_id']=='old-news'


def test_select_publishable_persists_full_upstream_state_path(tmp_path, context, observation, article):
    queue,_,directory=make_queue(tmp_path,context,observation,article)
    (directory/'semantic_decisions.json').write_text(json.dumps(decision(queue)),encoding='utf-8')
    document=editorial_document(queue); editorial_dir=directory/'editorial'; editorial_dir.mkdir()
    (editorial_dir/(document['news_id']+'.json')).write_text(json.dumps(document),encoding='utf-8')
    source=tmp_path/'owned.png'; Image.new('RGB',(1600,900),'blue').save(source)
    poster,metadata=render_poster(source,document,'OWNED',directory/'assets'/(document['news_id']+'.png'))
    write_asset_manifest(context.run_id,document['news_id'],source,poster,'OWNED',metadata,root=tmp_path)
    db=tmp_path/'history.db'
    result=select_publishable(context.run_id,queue_root=tmp_path,history_path=db)
    assert result['selected_news_ids']==[document['news_id']]
    states=[row['next_state'] for row in StateStore(db,context.run_id).transitions(document['news_id'])]
    assert states==['DISCOVERED','FETCHED','SEMANTIC_PENDING','VERIFIED','EDITORIAL_PENDING',
                    'EDITORIAL_READY','ASSET_PENDING','ASSET_READY','READY_TO_PUBLISH']


def test_select_publishable_enforces_duplicate_cooldown(tmp_path, context, observation, article):
    queue,_,directory=make_queue(tmp_path,context,observation,article)
    (directory/'semantic_decisions.json').write_text(json.dumps(decision(queue)),encoding='utf-8')
    document=editorial_document(queue); editorial_dir=directory/'editorial'; editorial_dir.mkdir()
    (editorial_dir/(document['news_id']+'.json')).write_text(json.dumps(document),encoding='utf-8')
    source=tmp_path/'owned.png'; Image.new('RGB',(1600,900),'blue').save(source)
    poster,metadata=render_poster(source,document,'OWNED',directory/'assets'/(document['news_id']+'.png'))
    write_asset_manifest(context.run_id,document['news_id'],source,poster,'OWNED',metadata,root=tmp_path)
    db=tmp_path/'history.db'; canonical=queue['candidates'][0]['canonical_url']
    StateStore(db,'older-run').reserve_publication('older-news',canonical,'older-version')
    result=select_publishable(context.run_id,queue_root=tmp_path,history_path=db)
    assert result['selected_news_ids']==[]
    assert result['holds'][document['news_id']]==['HOLD_DUPLICATE_PUBLICATION']


def test_duplicate_article_not_republished(tmp_path):
    store = StateStore(tmp_path / 'history.db', 'run-1')
    first = store.reserve_publication('news-1', 'https://example.com/a', 'v1')
    second = store.reserve_publication('news-2', 'https://example.com/a', 'v1')
    assert first[1] is True and second[1] is False
    assert first[0] == publication_key('https://example.com/a', 'v1')


def test_state_machine_persists_transition_audit(tmp_path):
    store = StateStore(tmp_path / 'history.db', 'run-1')
    assert store.transition('news-1', State.DISCOVERED, 'rss') == State.DISCOVERED
    assert store.transition('news-1', State.FETCHED, 'http') == State.FETCHED
    with pytest.raises(ValueError):
        store.transition('news-1', State.PUBLISHED, 'unsafe jump')


def test_meta_auto_publish_default_false(monkeypatch):
    monkeypatch.delenv('META_AUTO_PUBLISH', raising=False)
    assert auto_publish_enabled() is False


def test_review_rejected_and_unknown_rights_fail_compliance(candidate):
    policy = load_policy()
    editorial = {'compliance': {'facts_grounded': True, 'sensitive_words_transformed': True,
                                'has_exactly_5_hashtags': True, 'caption_length_ok': True,
                                'comment_length_ok': True}}
    queued = {'image_rights_status': 'UNKNOWN', 'origin_quality': 'DIRECT_REPUTABLE_ARTICLE',
              'published_at': '2026-09-09T11:00:00+07:00',
              'discovered_at': '2026-09-09T12:00:00+07:00'}
    decision = {'status': 'REVIEW', 'handoff_allowed': False, 'confidence': 1.0}
    result = compliance_gate(queued, decision, editorial, True, policy)
    assert set(result['reason_codes']) == {'HOLD_SEMANTIC_STATUS', 'HOLD_IMAGE_RIGHTS'}


def test_publish_policy_enforces_source_tier_and_freshness():
    policy = load_policy()
    editorial = {'compliance': {key: True for key in (
        'facts_grounded', 'sensitive_words_transformed', 'has_exactly_5_hashtags',
        'caption_length_ok', 'comment_length_ok')}}
    queued = {'image_rights_status': 'OWNED', 'origin_quality': 'UNKNOWN',
              'published_at': '2026-09-01T12:00:00+07:00',
              'discovered_at': '2026-09-09T12:00:00+07:00'}
    decision = {'status': 'VERIFIED', 'handoff_allowed': True, 'confidence': 0.95,
                'material_development_time': None}
    result = compliance_gate(queued, decision, editorial, True, policy)
    assert set(result['reason_codes']) == {'HOLD_SOURCE_TIER', 'HOLD_FRESHNESS_POLICY'}


def test_run_cycle_shadow_mode(tmp_path, context, observation, article, monkeypatch):
    monkeypatch.delenv('META_AUTO_PUBLISH', raising=False)
    queue, _, directory = make_queue(tmp_path, context, observation, article)
    (directory / 'semantic_decisions.json').write_text(json.dumps(decision(queue)), encoding='utf-8')
    document = editorial_document(queue)
    editorial_dir = directory / 'editorial'
    editorial_dir.mkdir()
    (editorial_dir / (document['news_id'] + '.json')).write_text(json.dumps(document), encoding='utf-8')
    result = run_cycle(context.run_id, queue_root=tmp_path)
    assert result['outcome'] == 'SHADOW_COMPLETE'
    assert result['VERIFIED'] == 1
    assert result['posts_published'] == 0
    assert result['metrics']['verified_ratio'] == 1.0
