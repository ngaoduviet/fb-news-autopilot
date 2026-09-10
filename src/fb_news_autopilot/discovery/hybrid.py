"""Hybrid discovery with deterministic URL/event-key observation merging."""
from dataclasses import replace

from ..models import Observation, normalized_text, url_key, valid_url


class HybridDiscovery:
    def __init__(self, providers):
        self.providers=tuple(providers)
        self.errors=[]

    def discover(self, context):
        self.errors=[]
        merged: dict[str,Observation]={}
        for provider in self.providers:
            try:
                observations=provider.discover(context)
            except Exception as exc:
                self.errors.append({'provider':type(provider).__name__,'error':type(exc).__name__})
                continue
            self.errors.extend(getattr(provider,'errors',[]))
            for item in observations:
                key=('event:'+normalized_text(item.event_key)) if item.event_key else (
                    'url:'+url_key(item.url) if valid_url(item.url) else 'raw:'+item.url)
                existing=merged.get(key)
                if existing is None:
                    merged[key]=item
                    continue
                providers=sorted(set(existing.discovery_provider.split('+')+[item.discovery_provider]))
                citations=[]
                seen=set()
                for citation in (*existing.citation_metadata,*item.citation_metadata):
                    marker=(citation.get('reference_id'),citation.get('url'))
                    if marker not in seen:
                        seen.add(marker); citations.append(citation)
                merged[key]=replace(existing,discovery_provider='+'.join(providers),
                    citation_metadata=tuple(citations),facts=tuple(dict.fromkeys((*existing.facts,*item.facts))))
        return list(merged.values())
