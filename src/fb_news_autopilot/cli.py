"""Explicit manual runs only; no scheduler or publishing code."""
import argparse
import json
from pathlib import Path
from .models import Observation, RunContext
from .radar import NewsRadar
from .verifier import SourceVerifier
from .sources import HTTPSFetcher, WebSourceProvider, RSSDiscovery
from .pipeline import run_pipeline,persist_run


def main():
    parser=argparse.ArgumentParser(description='Run Package 01 M01/M02 manually')
    parser.add_argument('--input',required=True,help='JSON with run_context, publishers, observations and/or feed_urls')
    parser.add_argument('--output',default='runs')
    args=parser.parse_args()
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

if __name__=='__main__': main()
