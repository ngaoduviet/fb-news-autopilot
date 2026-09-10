"""One-shot orchestration status for Codex Automation; never loops internally."""
import json
import time

from .editorial import load_editorial
from .policy import auto_publish_enabled
from .queueing import HandoffHold, load_semantic_decisions, run_directory
from .shadow import new_context, run_radar


def _summary(run_id, directory, *, started, **changes):
    value = {
        'run_id': run_id, 'outcome': 'SEMANTIC_PENDING',
        'candidates_discovered': 0, 'shortlisted': 0,
        'VERIFIED': 0, 'REVIEW': 0, 'REJECTED': 0,
        'editorial_ready': 0, 'images_rendered': 0,
        'holds': [], 'posts_published': 0, 'comments_published': 0,
        'failures': 0, 'file_paths': [str(directory.resolve())],
    }
    value.update(changes)
    decisions = value['VERIFIED'] + value['REVIEW'] + value['REJECTED']
    value['metrics'] = {
        'candidates_per_cycle': value['candidates_discovered'],
        'verified_ratio': value['VERIFIED'] / decisions if decisions else 0.0,
        'review_ratio': value['REVIEW'] / decisions if decisions else 0.0,
        'reject_ratio': value['REJECTED'] / decisions if decisions else 0.0,
        'render_success': value['images_rendered'],
        'publish_success': value['posts_published'],
        'comment_success': value['comments_published'],
        'duplicate_suppression': sum(code == 'HOLD_DUPLICATE_PUBLICATION' for code in value['holds']),
        'cycle_duration_ms': round((time.monotonic() - started) * 1000),
    }
    return value


def run_cycle(run_id, *, queue_root='data/queue', history_path=None, publisher_path=None,
              radar_runner=run_radar):
    started = time.monotonic()
    directory = run_directory(queue_root, run_id)
    radar_report = None
    queue_path = directory / 'candidates.json'
    if not queue_path.exists():
        radar_report, _, _ = radar_runner(queue_root=queue_root, history_path=history_path,
                                         publisher_path=publisher_path,
                                         context=new_context(run_id=run_id))
        if (radar_report.get('outcome') or radar_report.get('summary', {}).get('outcome')) == 'RUN_FAILURE':
            return _summary(run_id, directory, started=started, outcome='RUN_FAILURE', failures=1)
    candidate_count = 0
    shortlisted = 0
    try:
        raw_queue = json.loads(queue_path.read_text(encoding='utf-8'))
        shortlisted = len(raw_queue.get('candidates', []))
        candidate_count = (radar_report or {}).get('radar_summary', {}).get('candidate_count', shortlisted)
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    if shortlisted == 0 and queue_path.exists():
        return _summary(run_id, directory, started=started, outcome='NO_CANDIDATES',
                        candidates_discovered=candidate_count, shortlisted=0)
    try:
        queue, semantic = load_semantic_decisions(run_id, root=queue_root)
    except HandoffHold as hold:
        return _summary(run_id, directory, started=started, candidates_discovered=candidate_count,
                        shortlisted=shortlisted, holds=[hold.code],
                        file_paths=[str(queue_path.resolve())])
    counts = {status: sum(item['status'] == status for item in semantic['decisions'])
              for status in ('VERIFIED', 'REVIEW', 'REJECTED')}
    try:
        _, _, editorial = load_editorial(run_id, root=queue_root)
    except HandoffHold as hold:
        return _summary(run_id, directory, started=started, outcome='EDITORIAL_PENDING',
                        candidates_discovered=len(queue['candidates']),
                        shortlisted=len(queue['candidates']), **counts,
                        holds=[hold.code])
    return _summary(
        run_id, directory, started=started,
        outcome='SHADOW_COMPLETE' if not auto_publish_enabled() else 'READY_TO_PUBLISH',
        candidates_discovered=len(queue['candidates']), shortlisted=len(queue['candidates']),
        **counts, editorial_ready=len(editorial),
        images_rendered=len(list((directory / 'assets').glob('*.png'))),
    )
