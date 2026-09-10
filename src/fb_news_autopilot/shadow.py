"""API-free deterministic radar queue orchestration for Codex Automation."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from .discovery import RSSDiscoveryAdapter
from .history import SQLiteHistory, sanitize_error
from .models import RunContext
from .publishers import PublisherRegistry
from .queueing import run_directory, write_candidate_queue
from .radar import NewsRadar
from .sources import HTTPSFetcher, WebSourceProvider


def new_context(now=None,run_id=None):
    current=now or datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
    identifier=run_id or 'TN5S-'+current.strftime('%Y%m%dT%H%M%S%z')
    return RunContext(run_id=identifier,run_at=current.isoformat(),mode='shadow')


def _immutable_json(path,value):
    payload=json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n'
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('x',encoding='utf-8') as stream: stream.write(payload)
    except FileExistsError:
        if path.read_text(encoding='utf-8')!=payload:
            raise ValueError('Existing run artifact differs')
    return path


def _human(report):
    summary=report['radar_summary']
    return '\n'.join([
        '# PACKAGE 01 DETERMINISTIC RADAR RUN','',
        f"Run ID: `{report['run_context']['run_id']}`",
        f"Run time: `{report['run_context']['run_at']}`",
        f"Outcome: **{report['outcome']}**",'',
        f"Candidates: {summary['candidate_count']}",
        f"Shortlisted: {summary['shortlisted_count']}",
        f"Preliminary rejected: {summary['preliminary_rejected_count']}",
        f"Discovery failures: {len(report['discovery_errors'])}",
        f"Candidate fetch failures: {len(report.get('candidate_failures',[]))}",'',
        f"Candidate queue: `{report['candidate_queue_path']}`",'',
        'Semantic status remains pending for Codex Automation. No model API or publishing action was called.','',
    ])


def persist_failure(directory,payload):
    body=json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    digest=hashlib.sha256(body.encode()).hexdigest()
    target=Path(directory)/'failures'/(digest+'.json')
    target.parent.mkdir(parents=True,exist_ok=True)
    try:
        with target.open('x',encoding='utf-8') as stream: stream.write(body)
    except FileExistsError:
        if target.read_text(encoding='utf-8')!=body: raise ValueError('Existing failure audit differs')
    return target


def run_radar(*,queue_root='data/queue',context=None,history_path=None,publisher_path=None,
              discovery=None,fetcher=None,radar=None):
    context=context or new_context()
    directory=run_directory(queue_root,context.run_id)
    history=None
    stage='HISTORY_INIT'
    try:
        history=SQLiteHistory(history_path or os.getenv('FBNA_HISTORY_DB','data/history/fb_news_autopilot.db'),context.run_id)
        history.start_run(context)
        stage='CONFIG'
        registry=PublisherRegistry.load(publisher_path or os.getenv('FBNA_PUBLISHER_CONFIG','config/publishers.yaml'))
        fetcher=fetcher or HTTPSFetcher(registry.hosts)
        discovery=discovery or RSSDiscoveryAdapter(fetcher,registry.feed_urls)
        stage='DISCOVERY'
        observations=discovery.discover(context)
        stage='M01'
        candidates,summary,audit,raw=(radar or NewsRadar()).run(context,observations)
        for candidate in candidates: history.record_candidate(candidate)
        stage='EXACT_FETCH'
        candidate_failures=[]
        def record_candidate_failure(exc,news_id):
            failure=history.record_failure('EXACT_FETCH',exc)
            candidate_failures.append({**failure,'news_id':news_id})
        queue,queue_path=write_candidate_queue(context,candidates,
            WebSourceProvider(fetcher,registry.as_source_mapping()),root=queue_root,
            on_failure=record_candidate_failure)
        errors=list(getattr(discovery,'errors',()))
        outcome=('RUN_PARTIAL_FAILURE' if errors or candidate_failures else
                 ('SEMANTIC_PENDING' if queue['candidates'] else 'NO_CANDIDATES'))
        report={'schema_version':'1.0.0','run_context':context.to_dict(),'outcome':outcome,
            'radar_summary':summary,'candidate_queue_path':str(queue_path.resolve()),
            'discovery_errors':errors,'candidate_failures':candidate_failures,
            'audit':audit,'raw_observation_count':len(raw)}
        history.complete_run(outcome)
        json_path=_immutable_json(directory/'radar-report.json',report)
        markdown_path=directory/'radar-report.md'
        text=_human(report)
        try:
            with markdown_path.open('x',encoding='utf-8') as stream: stream.write(text)
        except FileExistsError:
            if markdown_path.read_text(encoding='utf-8')!=text: raise ValueError('Existing report differs')
        return report,json_path,markdown_path
    except Exception as exc:
        failure={'run_id':context.run_id,'stage':stage,'error_type':type(exc).__name__,
            'sanitized_message':sanitize_error(exc),'timestamp':datetime.now(ZoneInfo(context.timezone)).isoformat()}
        if history is not None:
            try:
                failure=history.record_failure(stage,exc)
                history.complete_run('RUN_FAILURE')
            except Exception:
                pass
        payload={'summary':{'run_id':context.run_id,'run_at':context.run_at,'outcome':'RUN_FAILURE'},
            'failure':failure}
        return payload,persist_failure(directory,payload),None


def run_shadow(**kwargs):
    """Backward-compatible name for an API-free radar queue run."""
    if 'output_dir' in kwargs:
        kwargs['queue_root']=kwargs.pop('output_dir')
    return run_radar(**kwargs)
