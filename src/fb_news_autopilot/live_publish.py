"""Explicit one-shot Meta publish test with fail-closed pre-write gates."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .assets import APPROVED_RIGHTS, load_asset_manifest
from .editorial import compose_facebook_caption, load_editorial
from .facebook.auth import EXPLICITLY_VERIFIED, MetaConfig, PROVISIONING_VERIFIED, run_preflight
from .facebook.client import MetaClient
from .image import validate_poster
from .publication import PublicationCoordinator
from .queueing import load_semantic_decisions
from .selection import select_publishable
from .state import StateStore, publication_key


AUTHORIZATION_EVIDENCE_PATH = 'data/config/meta-publication-authorization.json'


class LivePublishHold(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _hold(condition, code, message):
    if condition:
        raise LivePublishHold(code, message)


def _write_authorization_evidence(page_id, graph_api_version, path):
    evidence = {
        'page_id': page_id,
        'graph_api_version': graph_api_version,
        'tested_at': datetime.now(timezone.utc).isoformat(),
        'operations': [
            {'name': 'photo_publish', 'status': 'EXPLICITLY_PROVEN'},
            {'name': 'first_comment', 'status': 'EXPLICITLY_PROVEN'},
        ],
        'success': True,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        from .facebook.auth import publication_authorization_status
        status = publication_authorization_status(
            path, page_id=page_id, graph_api_version=graph_api_version)
        _hold(status != 'EXPLICITLY_VERIFIED', 'HOLD_AUTHORIZATION_EVIDENCE_INVALID',
              'Existing publication authorization evidence is invalid')
        return path
    with path.open('x', encoding='utf-8') as stream:
        json.dump(evidence, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write('\n')
    return path


def _validate_live_asset(manifest, poster):
    _hold(manifest.get('image_rights_status') not in APPROVED_RIGHTS,
          'HOLD_IMAGE_RIGHTS', 'Gate 6 requires owned, licensed, or permitted image rights')
    _hold((manifest.get('width'), manifest.get('height')) != (1080, 1350),
          'HOLD_IMAGE_DIMENSIONS', 'Gate 6 requires an exact 1080x1350 poster')
    # Schema 1.0.0 manifests predate the explicit field and contain exactly one poster.
    layout = manifest.get('image_layout', 'SINGLE')
    _hold(layout != 'SINGLE', 'HOLD_IMAGE_LAYOUT', 'Gate 6 supports SINGLE image layout only')
    try:
        validate_poster(poster)
    except Exception as exc:
        raise LivePublishHold('HOLD_IMAGE_INVALID', 'Rendered poster validation failed') from exc
    return layout


def run_live_publish_test(
        run_id, news_id, confirm_page_id, *, queue_root='data/queue',
        history_path='data/history/fb_news_autopilot.db',
        policy_path='config/publish_policy.yaml', requirements_path='config/meta.yaml',
        authorization_path=AUTHORIZATION_EVIDENCE_PATH, environment=None,
        config=None, client=None, reporter=None, selector=select_publishable, now=None):
    """Execute one guarded photo/comment test; callers must provide explicit Page ID."""
    environment = os.environ if environment is None else environment
    _hold(environment.get('META_LIVE_PUBLISH_TEST') != '1',
          'HOLD_LIVE_PUBLISH_TEST_DISABLED', 'META_LIVE_PUBLISH_TEST=1 is required')
    config = config or MetaConfig.from_env()
    auto_publish_raw = environment.get('META_AUTO_PUBLISH', 'false').strip().lower()
    _hold(config.auto_publish or auto_publish_raw == 'true',
          'HOLD_CONFLICTING_PUBLISH_SWITCHES',
          'META_AUTO_PUBLISH must remain false during the one-shot live test')
    _hold(confirm_page_id != config.page_id,
          'HOLD_PAGE_CONFIRMATION_MISMATCH', 'Confirmed Page ID does not match META_PAGE_ID')

    client = client or MetaClient(config.version, config.access_token)
    preflight = run_preflight(
        config, client, requirements_path=requirements_path,
        authorization_path=authorization_path)
    _hold(not preflight.ok or not preflight.runtime_identity_verified or not preflight.token_valid,
          'HOLD_META_PREFLIGHT_FAILED', 'Runtime Meta Page identity preflight failed')
    _hold(preflight.page_id != confirm_page_id,
          'HOLD_PAGE_CONFIRMATION_MISMATCH', 'Preflight Page ID differs from confirmation')
    required_capabilities = ('publish_content', 'moderate')
    _hold(any(preflight.capabilities.get(name) != PROVISIONING_VERIFIED
              for name in required_capabilities),
          'HOLD_PROVISIONING_CAPABILITIES',
          'Provisioning evidence does not verify publish_content and moderate')
    gate_already_completed = preflight.publication_authorization == EXPLICITLY_VERIFIED

    queue, semantic = load_semantic_decisions(run_id, root=queue_root)
    candidates = {item['news_id']: item for item in queue['candidates']}
    decisions = {item['news_id']: item for item in semantic['decisions']}
    _hold(news_id not in candidates or news_id not in decisions,
          'HOLD_NEWS_ID_UNKNOWN', 'Requested news_id is not present in the run')
    decision = decisions[news_id]
    _hold(decision['status'] != 'VERIFIED',
          'HOLD_SEMANTIC_STATUS', 'Gate 6 requires a VERIFIED candidate')
    _hold(decision['handoff_allowed'] is not True,
          'HOLD_EDITORIAL_NOT_ALLOWED', 'Gate 6 requires handoff_allowed=true')

    queue, _, editorials = load_editorial(run_id, root=queue_root)
    _hold(news_id not in editorials,
          'HOLD_EDITORIAL_NOT_ALLOWED', 'Validated editorial is unavailable for news_id')
    candidate = candidates[news_id]
    editorial = editorials[news_id]

    selection = selector(
        run_id, queue_root=queue_root, history_path=history_path,
        policy_path=policy_path, now=now)
    _hold(news_id not in selection['selected_news_ids'],
          'HOLD_NOT_SELECTED', 'news_id was not selected by deterministic policy')

    try:
        manifest, poster = load_asset_manifest(run_id, news_id, root=queue_root)
    except Exception as exc:
        raise LivePublishHold(
            getattr(exc, 'code', 'HOLD_ASSET_INVALID'), 'Rendered asset validation failed') from exc
    layout = _validate_live_asset(manifest, poster)
    caption = compose_facebook_caption(editorial)
    _hold(len(editorial['hashtags']) != 5 or len(set(editorial['hashtags'])) != 5,
          'HOLD_HASHTAG_INVALID', 'Gate 6 requires exactly five unique hashtags')

    canonical_url = candidate.get('canonical_url') or candidate['source_url']
    key = publication_key(canonical_url, editorial['editorial_version'])
    store = StateStore(history_path, run_id)
    existing = store.publication(key)
    mode = 'PHOTO_AND_COMMENT'
    if existing:
        if existing.get('post_id') and not store.comment_recorded(existing['post_id']):
            mode = 'COMMENT_ONLY_RETRY'
        elif existing.get('post_id'):
            raise LivePublishHold(
                'HOLD_DUPLICATE_PUBLICATION', 'Confirmed publication already exists')
        elif existing.get('photo_id'):
            raise LivePublishHold(
                'RECONCILIATION_REQUIRED', 'Photo ID exists without a confirmed post_id')
        else:
            raise LivePublishHold(
                'HOLD_AMBIGUOUS_PUBLICATION_HISTORY',
                'An earlier photo attempt has no confirmed result; automatic retry is prohibited')
    _hold(gate_already_completed, 'HOLD_GATE6_ALREADY_COMPLETED',
          'Gate 6 publication authorization has already been explicitly verified')

    summary = {
        'event': 'PRE_WRITE_SUMMARY',
        'mode': mode,
        'run_id': run_id,
        'news_id': news_id,
        'page_id': config.page_id,
        'page_name': preflight.page_name,
        'source_name': candidate['source'],
        'source_url': candidate['source_url'],
        'rendered_image_path': str(poster.resolve()),
        'image_rights_status': manifest['image_rights_status'],
        'image_dimensions': [manifest['width'], manifest['height']],
        'image_layout': layout,
        'caption_character_count': len(caption),
        'exactly_5_hashtags_confirmed': True,
        'first_comment_character_count': len(editorial['first_comment']),
        'idempotency_key': key,
        'auto_publish': False,
    }
    if reporter:
        reporter(summary)

    result = PublicationCoordinator(client, store).execute(
        news_id=news_id, canonical_url=canonical_url, editorial=editorial,
        image_path=poster, page_id=config.page_id)
    result.update({'run_id': run_id, 'news_id': news_id, 'page_id': config.page_id,
                   'pre_write_summary': summary, 'auto_publish': False})
    if result['state'] == 'RECONCILIATION_REQUIRED':
        result.update({'ok': False, 'publication_authorization':
                       'NOT_YET_PROVEN_BY_EXPLICIT_TEST'})
        return result
    if result['state'] == 'PUBLISHED_COMMENT_PENDING':
        result.update({'ok': False, 'publication_authorization':
                       'NOT_YET_PROVEN_BY_EXPLICIT_TEST'})
        return result
    if result['state'] in {'COMMENTED', 'VERIFIED_ON_FACEBOOK'}:
        evidence_path = _write_authorization_evidence(
            config.page_id, config.version, authorization_path)
        result.update({'ok': True, 'publication_authorization': 'EXPLICITLY_VERIFIED',
                       'authorization_evidence_path': str(evidence_path.resolve())})
        return result
    result.update({'ok': False, 'publication_authorization':
                   'NOT_YET_PROVEN_BY_EXPLICIT_TEST'})
    return result
