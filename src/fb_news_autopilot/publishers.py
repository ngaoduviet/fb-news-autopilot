"""Configuration-driven publisher identity and parsing rules."""
from copy import deepcopy
from pathlib import Path
import sys
from urllib.parse import urlsplit

import yaml


class PublisherConfigError(ValueError):
    pass


class PublisherRegistry:
    def __init__(self, records: list[dict]):
        self._by_host: dict[str, dict] = {}
        self._feed_urls: list[str] = []
        for source in records:
            record = deepcopy(source)
            name = record.get('canonical_name')
            hosts = record.get('host_aliases') or []
            if not name or not hosts:
                raise PublisherConfigError('Each publisher needs canonical_name and host_aliases')
            normalized = {
                'name': name,
                'canonical_name': name,
                'aliases': list(dict.fromkeys([*(record.get('name_aliases') or []),*hosts])),
                'origin_quality': record.get('origin_quality', 'UNKNOWN'),
                'timezone': record.get('timezone', 'Asia/Ho_Chi_Minh'),
                'category_paths': list(record.get('category_paths') or []),
                'category_path_patterns': list(record.get('category_path_patterns') or []),
                'article_path_patterns': list(record.get('article_path_patterns') or []),
                'article_body_selectors': list(record.get('article_body_selectors') or []),
                'title_selectors': list(record.get('title_selectors') or []),
                'publication_time_selectors': list(record.get('publication_time_selectors') or []),
                'update_time_selectors': list(record.get('update_time_selectors') or []),
            }
            self._feed_urls.extend(str(value) for value in record.get('feed_urls') or [])
            for host in hosts:
                key = str(host).lower().rstrip('.')
                if key in self._by_host:
                    raise PublisherConfigError('Duplicate publisher host alias: ' + key)
                self._by_host[key] = deepcopy(normalized)

    @classmethod
    def load(cls, path: str | Path):
        source=Path(path)
        if not source.exists() and source.as_posix()=='config/publishers.yaml':
            installed=Path(sys.prefix)/'share/fb-news-autopilot/config/publishers.yaml'
            if installed.exists(): source=installed
        data = yaml.safe_load(source.read_text(encoding='utf-8')) or {}
        if data.get('version') != 1 or not isinstance(data.get('publishers'), list):
            raise PublisherConfigError('Publisher registry must have version 1 and publishers[]')
        return cls(data['publishers'])

    @property
    def hosts(self) -> set[str]:
        return set(self._by_host)

    @property
    def feed_urls(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self._feed_urls))

    def resolve_host(self, host: str | None) -> dict | None:
        if not host:
            return None
        return deepcopy(self._by_host.get(host.lower().rstrip('.')))

    def resolve_url(self, url: str) -> dict | None:
        return self.resolve_host(urlsplit(url).hostname)

    def as_source_mapping(self) -> dict[str, dict]:
        return deepcopy(self._by_host)
