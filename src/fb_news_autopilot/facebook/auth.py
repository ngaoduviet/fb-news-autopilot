"""Environment configuration and fail-closed Page capability preflight."""
from dataclasses import asdict, dataclass, field
import os
from pathlib import Path
import re

import yaml

from .errors import MetaConfigurationError, MetaError


@dataclass(frozen=True)
class MetaConfig:
    page_id: str
    access_token: str = field(repr=False)
    version: str
    auto_publish: bool = False

    def __post_init__(self):
        if not re.fullmatch(r'\d+',self.page_id):
            raise MetaConfigurationError('INVALID_CONFIGURATION','META_PAGE_ID must be numeric')
        if not re.fullmatch(r'v\d+\.\d+',self.version):
            raise MetaConfigurationError('INVALID_CONFIGURATION','META_GRAPH_API_VERSION must look like v26.0')

    @classmethod
    def from_env(cls):
        missing = [name for name in ('META_PAGE_ID', 'META_PAGE_ACCESS_TOKEN', 'META_GRAPH_API_VERSION')
                   if not os.getenv(name)]
        if missing:
            raise MetaConfigurationError('MISSING_CREDENTIALS', 'Missing required Meta configuration: ' + ', '.join(missing))
        raw = os.getenv('META_AUTO_PUBLISH', 'false').strip().lower()
        if raw not in {'true', 'false'}:
            raise MetaConfigurationError('INVALID_CONFIGURATION', 'META_AUTO_PUBLISH must be true or false')
        return cls(os.environ['META_PAGE_ID'], os.environ['META_PAGE_ACCESS_TOKEN'],
                   os.environ['META_GRAPH_API_VERSION'], raw == 'true')


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    page_id: str | None
    page_name: str | None
    raw_tasks: tuple[str, ...]
    normalized_capabilities: tuple[str, ...]
    granted_permissions: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    missing_permissions: tuple[str, ...]
    error_category: str | None
    message: str

    def to_dict(self):
        return asdict(self)

    @property
    def tasks(self): return self.raw_tasks

    @property
    def permissions(self): return self.granted_permissions

def _requirements(path):
    try:
        with Path(path).open(encoding='utf-8') as stream:
            value = yaml.safe_load(stream)
        if not isinstance(value,dict) or set(value) != {'required_capabilities', 'required_permissions'}:
            raise ValueError('invalid keys')
        groups=value['required_capabilities']
        if not isinstance(groups,dict) or not groups:
            raise ValueError('invalid capability groups')
        original_count=len(groups)
        groups={name:frozenset(rule['any_of']) for name,rule in groups.items()
                if isinstance(name,str) and isinstance(rule,dict) and isinstance(rule.get('any_of'),list)}
        if len(groups)!=original_count or any(not aliases or any(not isinstance(item,str) for item in aliases)
                             for aliases in groups.values()):
            raise ValueError('invalid capability aliases')
        if not isinstance(value['required_permissions'],list) or any(
                not isinstance(item,str) or not item for item in value['required_permissions']):
            raise ValueError('invalid permissions')
    except (OSError,ValueError,TypeError,yaml.YAMLError) as exc:
        raise MetaConfigurationError('INVALID_CONFIGURATION', 'Meta requirements configuration is invalid') from exc
    return groups, set(value['required_permissions'])


def normalize_capabilities(tasks, groups):
    actual=set(tasks)
    return tuple(sorted(name for name,aliases in groups.items() if actual & aliases))


def run_preflight(config=None, client=None, requirements_path='config/meta.yaml'):
    try:
        config = config or MetaConfig.from_env()
        if client is None:
            from .client import MetaClient
            client = MetaClient(config.version, config.access_token)
        response = client.request('GET', f'/{config.page_id}',
                                  fields={'fields': 'id,name,tasks'}, logical_name='page_identity')
        actual = str(response.get('id', ''))
        tasks = tuple(response.get('tasks') or ())
        if actual != config.page_id:
            return PreflightResult(False, actual or None, response.get('name'), tasks, (), (), (), (),
                                   'PAGE_ID_MISMATCH', 'The token resolved to a different Page')
        permissions_response = client.request('GET', '/me/permissions', fields={},
                                              logical_name='token_permissions')
        permissions = tuple(item.get('permission') for item in permissions_response.get('data', [])
                            if item.get('status') == 'granted' and item.get('permission'))
        groups, required_permissions = _requirements(requirements_path)
        capabilities=normalize_capabilities(tasks,groups)
        missing_capabilities=tuple(sorted(set(groups)-set(capabilities)))
        missing_permissions=tuple(sorted(required_permissions-set(permissions)))
        if missing_capabilities:
            return PreflightResult(False, actual, response.get('name'), tasks, capabilities, permissions,
                                   missing_capabilities, missing_permissions,
                                   'INSUFFICIENT_PAGE_TASKS', 'Page task response does not prove configured capability')
        if missing_permissions:
            return PreflightResult(False, actual, response.get('name'), tasks, capabilities, permissions,
                                   (), missing_permissions,
                                   'INSUFFICIENT_PERMISSIONS', 'Token response does not include every configured permission')
        return PreflightResult(True, actual, response.get('name'), tasks, capabilities, permissions,
                               (), (), None, 'Meta preflight passed')
    except MetaError as exc:
        return PreflightResult(False, None, None, (), (), (), (), (), exc.category, str(exc))
