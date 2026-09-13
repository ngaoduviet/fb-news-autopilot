"""One-shot commands called manually or by Codex Desktop Automation."""
import argparse
import json
import sys
from pathlib import Path
from .models import Observation, RunContext
from .radar import NewsRadar
from .verifier import SourceVerifier
from .sources import HTTPSFetcher, WebSourceProvider, RSSDiscovery
from .pipeline import run_pipeline,persist_run
from .shadow import run_radar,run_shadow


def _print(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _run_id_parser(description):
    parser=argparse.ArgumentParser(description=description)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--queue-root',default='data/queue')
    return parser


def _manual(argv):
    parser=argparse.ArgumentParser(description='Run Package 01 M01/M02 manually')
    parser.add_argument('--input',required=True,help='JSON with run_context, publishers, observations and/or feed_urls')
    parser.add_argument('--output',default='runs')
    args=parser.parse_args(argv)
    config=json.loads(Path(args.input).read_text())
    context=RunContext(**config['run_context'])
    publishers=config.get('publishers',{})
    fetcher=HTTPSFetcher(set(publishers))
    observations=[]
    for record in config.get('observations',[]):
        record=dict(record)
        record['score_components']=tuple(record.get('score_components',{}).items())
        for key in ['facts','entities']:
            if key in record: record[key]=tuple(record[key])
        observations.append(Observation(**record))
    errors=[]
    if config.get('feed_urls'):
        # Ratings are explicit operator input keyed by article URL, never invented.
        ratings=config.get('ratings_by_url',{})
        discovery=RSSDiscovery(fetcher,config['feed_urls'],lambda title,url:ratings.get(url,{}))
        observations.extend(discovery.discover(context)); errors=discovery.errors
    result,evidence=run_pipeline(context,NewsRadar(limit=config.get('shortlist_limit',10)),SourceVerifier(WebSourceProvider(fetcher,publishers)),observations,discovery_errors=errors)
    path=persist_run(args.output,result,evidence)
    print(json.dumps({'outcome':result['outcome'],'audit_file':str(path.resolve())},ensure_ascii=False))
    return 0


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {'-h','--help'}:
        print('''usage: fb-news-autopilot COMMAND [options]

commands:
  radar-run            collect RSS candidates and exact evidence
  shadow-run           alias for API-free radar-run
  validate-semantic    validate Codex semantic decisions
  validate-editorial   validate Codex editorial artifacts
  render               render one rights-approved 1080x1350 poster
  select-publishable   select policy-compliant publication IDs
  meta-preflight       perform read-only Page identity/capability checks
  meta-live-publish-test
                       execute one explicitly confirmed Gate 6 photo/comment test
  publish              dry-run or execute one fully gated publication
  run-cycle            inspect one bounded automation cycle

Legacy manual fixture mode remains available with --input FILE.''')
        return 0
    if argv and argv[0]=='validate-semantic':
        from .queueing import HandoffHold, load_semantic_decisions
        parser=_run_id_parser('Validate Codex semantic decisions')
        args=parser.parse_args(argv[1:])
        try:
            queue,decisions=load_semantic_decisions(args.run_id,root=args.queue_root)
            _print({'valid':True,'candidate_count':len(queue['candidates']),
                    'decision_count':len(decisions['decisions'])})
            return 0
        except HandoffHold as hold:
            _print({'valid':False,'hold_code':hold.code})
            return 1
    if argv and argv[0]=='validate-editorial':
        from .editorial import load_editorial
        from .queueing import HandoffHold
        parser=_run_id_parser('Validate Codex editorial artifacts')
        args=parser.parse_args(argv[1:])
        try:
            _,_,editorial=load_editorial(args.run_id,root=args.queue_root)
            _print({'valid':True,'editorial_count':len(editorial)})
            return 0
        except HandoffHold as hold:
            _print({'valid':False,'hold_code':hold.code})
            return 1
    if argv and argv[0]=='render':
        from .editorial import load_editorial
        from .image import ImageRightsHold,render_poster
        parser=_run_id_parser('Render a deterministic 4:5 poster')
        parser.add_argument('--news-id',required=True)
        parser.add_argument('--source-image')
        parser.add_argument('--image-rights',choices=['OWNED','LICENSED','PERMITTED','UNKNOWN'])
        parser.add_argument('--image-sources',default='config/image_sources.yaml')
        parser.add_argument('--poster-config',default='config/tin_nong_5s_poster.yaml')
        args=parser.parse_args(argv[1:])
        queue,_,editorial=load_editorial(args.run_id,root=args.queue_root)
        if args.news_id not in editorial:
            parser.error('news-id is not editorial eligible')
        candidate=next(item for item in queue['candidates'] if item['news_id']==args.news_id)
        from .assets import resolve_asset
        try:
            resolved=resolve_asset(candidate,explicit_path=args.source_image,
                                   explicit_rights=args.image_rights,config_path=args.image_sources)
        except HandoffHold as hold:
            _print({'rendered':False,'hold_code':hold.code})
            return 1
        output=Path(args.queue_root)/args.run_id/'assets'/(args.news_id+'.png')
        try:
            path,metadata=render_poster(resolved.path,editorial[args.news_id],resolved.rights,
                                        output,config_path=args.poster_config)
        except ImageRightsHold as hold:
            _print({'rendered':False,'hold_code':hold.code})
            return 1
        from .assets import write_asset_manifest
        manifest,manifest_path=write_asset_manifest(args.run_id,args.news_id,resolved.path,path,
                                                     resolved.rights,metadata,root=args.queue_root)
        _print({'rendered':True,'poster':str(path.resolve()),'asset_manifest':str(manifest_path.resolve()),
                'metadata':metadata})
        return 0
    if argv and argv[0]=='select-publishable':
        from .selection import select_publishable
        parser=_run_id_parser('Select deterministic publishable candidates')
        parser.add_argument('--history-db',default='data/history/fb_news_autopilot.db')
        parser.add_argument('--policy',default='config/publish_policy.yaml')
        args=parser.parse_args(argv[1:])
        _print(select_publishable(args.run_id,queue_root=args.queue_root,
                                  history_path=args.history_db,policy_path=args.policy))
        return 0
    if argv and argv[0]=='meta-preflight':
        from .facebook.auth import run_preflight
        result=run_preflight()
        _print(result.to_dict())
        return 0 if result.ok else 1
    if argv and argv[0]=='meta-live-publish-test':
        from .live_publish import LivePublishHold,run_live_publish_test
        from .security import redact
        parser=_run_id_parser('Run one explicitly confirmed Gate 6 Meta write test')
        parser.add_argument('--news-id',required=True)
        parser.add_argument('--confirm-page-id',required=True)
        parser.add_argument('--history-db',default='data/history/fb_news_autopilot.db')
        parser.add_argument('--policy',default='config/publish_policy.yaml')
        args=parser.parse_args(argv[1:])
        try:
            result=run_live_publish_test(
                args.run_id,args.news_id,args.confirm_page_id,queue_root=args.queue_root,
                history_path=args.history_db,policy_path=args.policy,reporter=_print)
            _print(result)
            return 0 if result['ok'] else 1
        except LivePublishHold as hold:
            _print({'ok':False,'hold_code':hold.code,'message':str(hold),
                    'auto_publish':False})
            return 1
        except Exception as exc:
            _print({'ok':False,'state':'FAILED','error':redact(exc),
                    'auto_publish':False})
            return 1
    if argv and argv[0]=='run-cycle':
        from .cycle import run_cycle
        parser=_run_id_parser('Run one API-free automation cycle')
        parser.add_argument('--history-db')
        parser.add_argument('--publisher-config')
        args=parser.parse_args(argv[1:])
        result=run_cycle(args.run_id,queue_root=args.queue_root,history_path=args.history_db,
                         publisher_path=args.publisher_config)
        _print(result)
        return 1 if result['outcome']=='RUN_FAILURE' else 0
    if argv and argv[0]=='publish':
        from .editorial import load_editorial
        from .facebook import MetaClient,MetaConfig,run_preflight
        from .assets import load_asset_manifest
        from .image import validate_poster
        from .policy import compliance_gate,load_policy
        from .publication import PublicationCoordinator
        from .state import StateStore
        parser=_run_id_parser('Publish one fully gated story through Meta Graph API')
        parser.add_argument('--news-id',required=True)
        parser.add_argument('--dry-run',action='store_true')
        parser.add_argument('--history-db',default='data/history/fb_news_autopilot.db')
        parser.add_argument('--policy',default='config/publish_policy.yaml')
        args=parser.parse_args(argv[1:])
        from .selection import select_publishable
        selection=select_publishable(args.run_id,queue_root=args.queue_root,
                                     history_path=args.history_db,policy_path=args.policy)
        if args.news_id not in selection['selected_news_ids']:
            _print({'published':False,'hold_code':'HOLD_NOT_SELECTED','selection':selection})
            return 1
        queue,semantic,editorial=load_editorial(args.run_id,root=args.queue_root)
        candidates={item['news_id']:item for item in queue['candidates']}
        decisions={item['news_id']:item for item in semantic['decisions']}
        candidate=candidates[args.news_id]; document=editorial[args.news_id]
        manifest,poster=load_asset_manifest(args.run_id,args.news_id,root=args.queue_root)
        poster_ok=validate_poster(poster)
        store=StateStore(args.history_db,args.run_id)
        candidate={**candidate,'image_rights_status':manifest['image_rights_status']}
        gate=compliance_gate(candidate,decisions[args.news_id],document,poster_ok,load_policy(args.policy))
        if args.dry_run:
            _print({'dry_run':True,'gate':gate,'would_publish':gate['passed']})
            return 0 if gate['passed'] else 1
        config=MetaConfig.from_env()
        if not config.auto_publish:
            _print({'published':False,'hold_code':'HOLD_AUTO_PUBLISH_DISABLED'})
            return 1
        if not gate['passed']:
            _print({'published':False,'gate':gate})
            return 1
        client=MetaClient(config.version,config.access_token)
        preflight=run_preflight(config,client)
        if not preflight.ok or not preflight.publication_ready:
            _print({'published':False,
                    'hold_code':'HOLD_META_PUBLISH_AUTHORIZATION_UNVERIFIED',
                    'preflight':preflight.to_dict()})
            return 1
        result=PublicationCoordinator(client,store).execute(news_id=args.news_id,
            canonical_url=candidate['canonical_url'] or candidate['source_url'],editorial=document,
            image_path=poster,page_id=config.page_id)
        _print(result)
        return 0
    if argv and argv[0] in {'shadow-run','radar-run'}:
        command=argv[0]
        parser=argparse.ArgumentParser(description='Run deterministic Package 01 radar and write the Codex queue')
        parser.add_argument('--queue-root',default='data/queue')
        parser.add_argument('--output',dest='queue_root',help=argparse.SUPPRESS)
        parser.add_argument('--run-id')
        parser.add_argument('--history-db')
        parser.add_argument('--publisher-config')
        args=parser.parse_args(argv[1:])
        context=None
        if args.run_id:
            from .shadow import new_context
            context=new_context(run_id=args.run_id)
        payload,json_path,markdown_path=(run_shadow if command=='shadow-run' else run_radar)(
            queue_root=args.queue_root,history_path=args.history_db,publisher_path=args.publisher_config,context=context)
        outcome=payload.get('outcome') or payload['summary']['outcome']
        print(json.dumps({'outcome':outcome,'json_report':str(json_path.resolve()),
            'human_report':str(markdown_path.resolve()) if markdown_path else None},ensure_ascii=False))
        return 0 if outcome!='RUN_FAILURE' else 1
    return _manual(argv)

if __name__=='__main__': main()
