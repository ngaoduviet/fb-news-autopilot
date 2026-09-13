"""Deterministic publication selection and persisted operational state."""
from datetime import datetime, timedelta, timezone

from .assets import load_asset_manifest
from .editorial import load_editorial
from .image import validate_poster
from .models import timestamp
from .policy import compliance_gate, load_policy
from .state import State, StateStore


def _advance(store, news_id, path):
    current=store.current(news_id)
    states=[state for state,_ in path]
    if current in states:
        start=states.index(current)+1
    elif current is None:
        start=0
    else:
        return current
    for state,reason in path[start:]:
        store.transition(news_id,state,reason)
    return store.current(news_id)


def rank_publishable(items, maximum):
    """Order score/news-id pairs deterministically and apply the hard cycle cap."""
    return [news_id for _,news_id in sorted((-score,news_id) for score,news_id in items)[:maximum]]


def select_publishable(run_id, *, queue_root='data/queue',
                       history_path='data/history/fb_news_autopilot.db',
                       policy_path='config/publish_policy.yaml', now=None):
    """Return eligible IDs ordered by score and capped by configured cycle limit."""
    policy=load_policy(policy_path)
    queue,semantic,editorials=load_editorial(run_id,root=queue_root)
    store=StateStore(history_path,run_id)
    decisions={item['news_id']:item for item in semantic['decisions']}
    eligible=[]; holds={}
    now=(now if isinstance(now,datetime) else timestamp(now)) if now else datetime.now(timezone.utc)
    since=(now-timedelta(hours=policy['duplicate_cooldown_hours'])).isoformat()
    for candidate in queue['candidates']:
        news_id=candidate['news_id']; decision=decisions[news_id]
        _advance(store,news_id,[(State.DISCOVERED,'Candidate discovered'),
            (State.FETCHED,'Exact article evidence fetched'),
            (State.SEMANTIC_PENDING,'Semantic decision requested')])
        if decision['status'] in {'REVIEW','REJECTED'}:
            if store.current(news_id) == State.SEMANTIC_PENDING:
                store.transition(news_id,State(decision['status']),'Semantic terminal decision')
            continue
        _advance(store,news_id,[(State.SEMANTIC_PENDING,'Semantic decision requested'),
            (State.VERIFIED,'Semantic verification passed'),
            (State.EDITORIAL_PENDING,'Editorial artifact requested'),
            (State.EDITORIAL_READY,'Editorial artifact validated'),
            (State.ASSET_PENDING,'Approved asset requested')])
        if store.current(news_id) in {State.COMPLIANCE_HOLD,State.FAILED}:
            holds[news_id]=[store.current(news_id).value]
            continue
        try:
            manifest,poster=load_asset_manifest(run_id,news_id,root=queue_root)
        except Exception as exc:
            code=getattr(exc,'code','HOLD_ASSET_MISSING')
            if code == 'HOLD_ASSET_MISSING' and candidate.get('image_rights_status') == 'UNKNOWN':
                code='HOLD_IMAGE_RIGHTS'
            if code == 'HOLD_IMAGE_RIGHTS' and store.current(news_id)==State.ASSET_PENDING:
                store.transition(news_id,State.HOLD_IMAGE_RIGHTS,'No approved asset is available')
            holds[news_id]=[code]
            continue
        if store.current(news_id) == State.HOLD_IMAGE_RIGHTS:
            store.transition(news_id,State.ASSET_PENDING,
                             'Approved rendered asset is now available')
        if store.current(news_id) == State.ASSET_PENDING:
            store.transition(news_id,State.ASSET_READY,'Rendered asset validated')
        canonical=candidate.get('canonical_url') or candidate['source_url']
        duplicate=store.recent_publication(canonical,since,exclude_news_id=news_id) is not None
        gated_candidate={**candidate,'image_rights_status':manifest['image_rights_status']}
        gate=compliance_gate(gated_candidate,decision,editorials[news_id],
                             validate_poster(poster),policy,duplicate=duplicate)
        if not gate['passed']:
            holds[news_id]=gate['reason_codes']
            if store.current(news_id) == State.ASSET_READY:
                store.transition(news_id,State.COMPLIANCE_HOLD,','.join(gate['reason_codes']))
            continue
        eligible.append((candidate['candidate_contract']['scores']['top_content_score'],news_id))
    selected=rank_publishable(eligible,policy['max_posts_per_cycle'])
    for news_id in selected:
        if store.current(news_id) == State.ASSET_READY:
            store.transition(news_id,State.READY_TO_PUBLISH,'Selected by deterministic publish policy')
    return {'run_id':run_id,'selected_news_ids':selected,'holds':holds,
            'max_posts_per_cycle':policy['max_posts_per_cycle']}
