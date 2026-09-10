"""Deterministic candidate queue and fail-closed Codex handoff boundaries."""
from dataclasses import asdict
import json
from pathlib import Path
import re
from jsonschema import ValidationError

from .contracts import validate
from .models import valid_url


class HandoffHold(ValueError):
    """A missing or invalid external Codex artifact must stop dependent stages."""

    def __init__(self,code,message):
        super().__init__(message)
        self.code=code


def run_directory(root, run_id):
    if not safe_identifier(run_id):
        raise ValueError('run_id is unsafe for a queue path')
    return Path(root)/run_id


def safe_identifier(value):
    return isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9._+-]+',value) is not None


def _write_immutable(path: Path, value):
    payload=json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n'
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('x',encoding='utf-8') as stream: stream.write(payload)
    except FileExistsError:
        if path.read_text(encoding='utf-8')!=payload:
            raise ValueError('Existing queue artifact differs: '+str(path))
    return path


def artifact_path(directory, relative):
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise HandoffHold('HOLD_ARTIFACT_PATH_INVALID','Artifact path escapes the run directory')
    base = Path(directory).resolve()
    target = (base / relative).resolve()
    if target != base and base not in target.parents:
        raise HandoffHold('HOLD_ARTIFACT_PATH_INVALID','Artifact path escapes the run directory')
    return target


def write_candidate_queue(context,candidates,provider,*,root='data/queue',on_failure=None):
    directory=run_directory(root,context.run_id)
    records=[]
    for candidate in candidates:
        if candidate['m01_status']!='SHORTLISTED':
            continue
        try:
            evidence=provider.inspect(candidate,context)
            if not safe_identifier(candidate['news_id']):
                raise ValueError('news_id is unsafe for a queue path')
            if evidence.requested_url!=candidate['discovery']['discovered_url']:
                raise ValueError('Evidence URL does not match candidate URL')
            article_path=directory/'articles'/(candidate['news_id']+'.txt')
            evidence_path=directory/'evidence'/(candidate['news_id']+'.json')
            article_path.parent.mkdir(parents=True,exist_ok=True)
            article_text=evidence.body or ''
            try:
                with article_path.open('x',encoding='utf-8') as stream: stream.write(article_text)
            except FileExistsError:
                if article_path.read_text(encoding='utf-8')!=article_text:
                    raise ValueError('Existing article evidence differs')
            _write_immutable(evidence_path,asdict(evidence))
            facts=candidate['normalized']['summary_facts']
            records.append({
                'news_id':candidate['news_id'],'story_cluster_id':candidate['story_cluster_id'],
                'title':candidate['normalized']['title'],'source':evidence.publisher_name or candidate['discovery']['publisher_name'],
                'source_url':candidate['discovery']['discovered_url'],
                'canonical_url':evidence.canonical_url if evidence.canonical_url and valid_url(evidence.canonical_url) else None,
                'published_at':evidence.publication_time,'origin_quality':evidence.origin_quality,
                'discovered_at':candidate['discovery']['discovered_at'],
                'rss_summary':facts[0] if facts else None,
                'article_text_path':str(article_path.relative_to(directory)),
                'article_evidence_path':str(evidence_path.relative_to(directory)),
                'source_image_url':evidence.source_image_url if evidence.source_image_url and valid_url(evidence.source_image_url) else None,
                'image_rights_status':'UNKNOWN',
                'deterministic_checks':{
                    'url_valid':valid_url(candidate['discovery']['discovered_url']),
                    'page_type':evidence.page_type,'article_accessible':evidence.accessible,
                    'source_identity':evidence.source_identity,
                    'publication_time_found':evidence.publication_time is not None,
                    'preliminary_freshness':candidate['preliminary_freshness']['bucket'],
                    'exact_article_candidate':evidence.page_type=='ARTICLE' and evidence.accessible is True,
                },
                'needs_semantic_verification':True,'candidate_contract':candidate,
            })
        except Exception as exc:
            if on_failure is None:
                raise
            on_failure(exc,candidate.get('news_id'))
    queue=validate('candidate-queue',{'schema_version':'1.0.0','run_id':context.run_id,
        'generated_at':context.run_at,'timezone':context.timezone,'candidates':records})
    return queue,_write_immutable(directory/'candidates.json',queue)


def load_semantic_decisions(run_id,*,root='data/queue'):
    directory=run_directory(root,run_id)
    queue_path=directory/'candidates.json'
    decision_path=directory/'semantic_decisions.json'
    if not queue_path.exists(): raise HandoffHold('HOLD_CANDIDATE_QUEUE_MISSING','Candidate queue is missing')
    if (directory/'semantic.timeout').exists():
        raise HandoffHold('HOLD_SEMANTIC_TIMEOUT','Codex semantic stage recorded a timeout')
    if not decision_path.exists(): raise HandoffHold('HOLD_SEMANTIC_FILE_MISSING','Semantic decision file is missing')
    try:
        queue=json.loads(queue_path.read_text(encoding='utf-8'))
        decisions=json.loads(decision_path.read_text(encoding='utf-8'))
        validate('candidate-queue',queue); validate('semantic-decisions',decisions)
    except (json.JSONDecodeError,ValidationError,ValueError,OSError) as exc:
        raise HandoffHold('HOLD_SEMANTIC_INVALID','Semantic decision file is invalid') from exc
    if queue['run_id']!=run_id or decisions['run_id']!=run_id:
        raise HandoffHold('HOLD_RUN_ID_MISMATCH','Queue and semantic run IDs must match')
    candidates={item['news_id']:item for item in queue['candidates']}
    provided=[item['news_id'] for item in decisions['decisions']]
    if len(provided)!=len(set(provided)) or set(provided)!=set(candidates):
        raise HandoffHold('HOLD_SEMANTIC_COVERAGE','Every queued candidate needs exactly one decision')
    for decision in decisions['decisions']:
        candidate=candidates[decision['news_id']]
        if decision['status']=='VERIFIED':
            checks=candidate['deterministic_checks']
            if not (checks['url_valid'] and checks['exact_article_candidate'] and
                    checks['publication_time_found'] and checks['source_identity'] is True):
                raise HandoffHold('HOLD_DETERMINISTIC_GATE','Semantic VERIFIED cannot override deterministic gates')
        try:
            article=artifact_path(directory,candidate['article_text_path']).read_text(encoding='utf-8')
        except OSError as exc:
            raise HandoffHold('HOLD_ARTICLE_EVIDENCE_MISSING','Exact article evidence is missing') from exc
        for evidence in decision['evidence']:
            if evidence['quote'] not in article:
                raise HandoffHold('HOLD_EVIDENCE_QUOTE_INVALID','Semantic evidence quote is not in exact article text')
            allowed={candidate['source_url'],candidate['canonical_url']}
            if evidence['source_url'] not in allowed:
                raise HandoffHold('HOLD_EVIDENCE_SOURCE_INVALID','Semantic evidence source does not match candidate')
    return queue,decisions
