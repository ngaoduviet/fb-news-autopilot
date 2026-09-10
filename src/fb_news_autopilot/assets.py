"""Immutable rendered-asset manifests used by the publication gate."""
from datetime import datetime, timezone
from dataclasses import dataclass
import hashlib
from pathlib import Path

import yaml

from .contracts import validate
from .queueing import HandoffHold, _write_immutable, artifact_path, run_directory, safe_identifier


APPROVED_RIGHTS = ('OWNED', 'LICENSED', 'PERMITTED')


@dataclass(frozen=True)
class ResolvedAsset:
    path: Path
    rights: str
    source: str


def resolve_asset(candidate, *, explicit_path=None, explicit_rights=None,
                  config_path='config/image_sources.yaml'):
    """Resolve only explicitly approved files; article image URLs are never fetched."""
    if explicit_path is not None:
        path=Path(explicit_path)
        if explicit_rights in APPROVED_RIGHTS and path.is_file():
            return ResolvedAsset(path.resolve(),explicit_rights,'explicit')
    try:
        config=yaml.safe_load(Path(config_path).read_text(encoding='utf-8'))
        owned_root=Path(config['owned_library_root']).resolve()
        fallbacks=config['fallbacks']
        if not isinstance(fallbacks,dict): raise ValueError
    except (OSError,KeyError,TypeError,ValueError,yaml.YAMLError) as exc:
        raise HandoffHold('HOLD_IMAGE_RIGHTS','Approved asset configuration is unavailable') from exc
    topic=candidate.get('candidate_contract',{}).get('normalized',{}).get('topic')
    entry=fallbacks.get(topic) or fallbacks.get('default')
    if isinstance(entry,dict) and entry.get('rights') in APPROVED_RIGHTS:
        path=(owned_root/entry.get('path','')).resolve()
        if path.is_relative_to(owned_root) and path.is_file():
            return ResolvedAsset(path,entry['rights'],'owned_fallback')
    raise HandoffHold('HOLD_IMAGE_RIGHTS','No owned, licensed, or permitted asset is available')


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_asset_manifest(run_id, news_id, source_path, poster_path, rights, metadata,
                         *, root='data/queue'):
    if not safe_identifier(news_id):
        raise ValueError('news_id is unsafe for an asset path')
    directory = run_directory(root, run_id)
    poster_path = Path(poster_path)
    document = validate('rendered-asset', {
        'schema_version': '1.0.0', 'news_id': news_id,
        'rendered_at': datetime.now(timezone.utc).isoformat(),
        'image_rights_status': rights,
        'source_image_sha256': sha256_file(source_path),
        'poster_sha256': sha256_file(poster_path),
        'poster_path': str(poster_path.relative_to(directory)),
        'width': 1080, 'height': 1350, 'safe_margin_valid': True,
    })
    return document, _write_immutable(directory / 'assets' / (news_id + '.json'), document)


def load_asset_manifest(run_id, news_id, *, root='data/queue'):
    import json
    directory = run_directory(root, run_id)
    if not safe_identifier(news_id):
        raise HandoffHold('HOLD_ARTIFACT_PATH_INVALID', 'Asset news_id is unsafe')
    path = directory / 'assets' / (news_id + '.json')
    if not path.exists():
        raise HandoffHold('HOLD_ASSET_MISSING', 'Rendered asset manifest is missing')
    try:
        document = validate('rendered-asset', json.loads(path.read_text(encoding='utf-8')))
        poster = artifact_path(directory, document['poster_path'])
    except Exception as exc:
        if isinstance(exc, HandoffHold):
            raise
        raise HandoffHold('HOLD_ASSET_INVALID', 'Rendered asset manifest is invalid') from exc
    if not poster.is_file() or sha256_file(poster) != document['poster_sha256']:
        raise HandoffHold('HOLD_ASSET_TAMPERED', 'Poster is missing or differs from its manifest')
    return document, poster
