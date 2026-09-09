"""Manual run orchestration, immutable evidence persistence, Package 01 STOP."""
from pathlib import Path
import hashlib
import json
from .contracts import validate


def run_pipeline(context,radar,verifier,observations,*,discovery_errors=()):
    candidates,summary,audit,raw=radar.run(context,observations)
    results,evidence=[],[]
    failures=len(discovery_errors)
    for error in discovery_errors:
        audit.append(dict(stage='RUN',news_id=None,code='SOURCE_DISCOVERY_FAILURE',detail=json.dumps(error,ensure_ascii=False)))
    for c in candidates:
        if c['m01_status']!='SHORTLISTED': continue
        result,record=verifier.verify(c,context)
        results.append(result); evidence.append(record)
        if record['evidence']['network_error']: failures+=1
        v=result['verification']
        audit.append(dict(stage='M02',news_id=c['news_id'],code=v['status'],detail=json.dumps(v,ensure_ascii=False)))
    if failures:
        usable_attempts=len(results)-sum(bool(v['evidence']['network_error']) for v in evidence)
        outcome='RUN_PARTIAL_FAILURE' if usable_attempts or candidates else 'RUN_FAILURE'
        if results and not usable_attempts and not any(c['m01_status']=='REJECTED_PRELIMINARY' for c in candidates): outcome='RUN_FAILURE'
    else:
        outcome='VERIFIED_CANDIDATES_AVAILABLE' if any(r['verification']['status']=='VERIFIED' for r in results) else 'NO_VERIFIED_CANDIDATES'
    result=validate('run-result',dict(run_context=context.to_dict(),outcome=outcome,candidates=candidates,results=results,radar_summary=summary,audit=audit))
    return result,dict(raw_observations=raw,source_evidence=evidence)


def persist_run(directory, result, evidence):
    """Content-addressed append-only bundle: identical reruns reuse the same file."""
    bundle={'run':result,'evidence':evidence}
    payload=json.dumps(bundle,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n'
    digest=hashlib.sha256(payload.encode()).hexdigest()
    root=Path(directory); root.mkdir(parents=True,exist_ok=True)
    target=root/(digest+'.json')
    try:
        with target.open('x') as file: file.write(payload)
    except FileExistsError:
        if target.read_text()!=payload: raise ValueError('Existing audit record differs')
    return target
