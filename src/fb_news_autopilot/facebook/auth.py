"""Environment configuration and read-only Page identity preflight."""
from dataclasses import asdict, dataclass, field
from datetime import datetime
import os
from pathlib import Path
import re

import yaml

from .errors import MetaConfigurationError, MetaError


NOT_RUNTIME_VERIFIABLE = 'NOT_RUNTIME_VERIFIABLE'
PROVISIONING_VERIFIED = 'PROVISIONING_VERIFIED'
PROVISIONING_NOT_VERIFIED = 'PROVISIONING_NOT_VERIFIED'
PERMISSIONS_RUNTIME_STATUS = 'NOT_DIRECTLY_VERIFIABLE_WITH_PAGE_TOKEN'
PUBLISH_AUTHORIZATION_STATUS = 'NOT_YET_PROVEN_BY_EXPLICIT_TEST'


@dataclass(frozen=True)
class MetaConfig:
    page_id: str
    access_token: str = field(repr=False)
    version: str
    auto_publish: bool = False

    def __post_init__(self):
        if not re.fullmatch(r'\d+', self.page_id):
            raise MetaConfigurationError('INVALID_CONFIGURATION', 'META_PAGE_ID must be numeric')
        if not re.fullmatch(r'v\d+\.\d+', self.version):
            raise MetaConfigurationError('INVALID_CONFIGURATION', 'META_GRAPH_API_VERSION must look like v26.0')

    @classmethod
    def from_env(cls):
        required = ('META_PAGE_ID', 'META_PAGE_ACCESS_TOKEN', 'META_GRAPH_API_VERSION')
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            raise MetaConfigurationError(
                'MISSING_CREDENTIALS', 'Missing required Meta configuration: ' + ', '.join(missing))
        raw = os.getenv('META_AUTO_PUBLISH', 'false').strip().lower()
        if raw not in {'true', 'false'}:
            raise MetaConfigurationError(
                'INVALID_CONFIGURATION', 'META_AUTO_PUBLISH must be true or false')
        return cls(os.environ['META_PAGE_ID'], os.environ['META_PAGE_ACCESS_TOKEN'],
                   os.environ['META_GRAPH_API_VERSION'], raw == 'true')


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    page_id: str | None
    page_name: str | None
    token_valid: bool
    runtime_identity_verified: bool
    capabilities: dict[str, str]
    permissions: dict[str, object]
    provisioning_tasks: tuple[str, ...]
    normalized_capabilities: tuple[str, ...]
    provisioning_evidence_status: str
    publication_authorization: str
    publication_ready: bool
    auto_publish: bool
    error_category: str | None
    message: str

    def to_dict(self):
        return asdict(self)

    @property
    def tasks(self):
        return self.provisioning_tasks


def _valid_timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _requirements(path):
    try:
        with Path(path).open(encoding='utf-8') as stream:
            value = yaml.safe_load(stream)
        allowed = {'required_capabilities', 'required_permissions', 'provisioning_evidence'}
        if not isinstance(value, dict) or not set(value) <= allowed or not {
                'required_capabilities', 'required_permissions'} <= set(value):
            raise ValueError('invalid keys')
        groups = value['required_capabilities']
        if not isinstance(groups, dict) or not groups:
            raise ValueError('invalid capability groups')
        original_count = len(groups)
        groups = {name: frozenset(rule['any_of']) for name, rule in groups.items()
                  if isinstance(name, str) and isinstance(rule, dict)
                  and isinstance(rule.get('any_of'), list)}
        if len(groups) != original_count or any(
                not aliases or any(not isinstance(item, str) or not item for item in aliases)
                for aliases in groups.values()):
            raise ValueError('invalid capability aliases')
        permissions = value['required_permissions']
        if not isinstance(permissions, list) or any(
                not isinstance(item, str) or not item for item in permissions):
            raise ValueError('invalid permissions')
        evidence = value.get('provisioning_evidence')
        if evidence is not None:
            evidence_keys = {
                'page_id', 'page_name', 'tasks', 'normalized_capabilities',
                'verified_at', 'graph_api_version'}
            if not isinstance(evidence, dict) or set(evidence) != evidence_keys:
                raise ValueError('invalid provisioning evidence keys')
            if (not isinstance(evidence['page_id'], str)
                    or not re.fullmatch(r'\d+', evidence['page_id'])
                    or not isinstance(evidence['page_name'], str)
                    or not evidence['page_name'].strip()
                    or not isinstance(evidence['tasks'], list)
                    or any(not isinstance(task, str) or not task for task in evidence['tasks'])
                    or not isinstance(evidence['normalized_capabilities'], list)
                    or any(not isinstance(capability, str) or not capability
                           for capability in evidence['normalized_capabilities'])
                    or not _valid_timestamp(evidence['verified_at'])
                    or not isinstance(evidence['graph_api_version'], str)
                    or not re.fullmatch(r'v\d+\.\d+', evidence['graph_api_version'])):
                raise ValueError('invalid provisioning evidence')
            normalized = tuple(sorted(
                name for name, aliases in groups.items()
                if set(evidence['tasks']) & aliases))
            if tuple(sorted(set(evidence['normalized_capabilities']))) != normalized:
                raise ValueError('normalized capabilities do not match tasks')
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        raise MetaConfigurationError(
            'INVALID_CONFIGURATION', 'Meta requirements configuration is invalid') from exc
    return groups, tuple(sorted(set(permissions))), evidence


def normalize_capabilities(tasks, groups):
    actual = set(tasks)
    return tuple(sorted(name for name, aliases in groups.items() if actual & aliases))


def _result(*, config=None, ok=False, page_id=None, page_name=None, token_valid=False,
            runtime_identity_verified=False, capabilities=None, permissions=None,
            provisioning_tasks=(), normalized_capabilities=(),
            provisioning_evidence_status=NOT_RUNTIME_VERIFIABLE,
            error_category=None, message=''):
    return PreflightResult(
        ok=ok,
        page_id=page_id,
        page_name=page_name,
        token_valid=token_valid,
        runtime_identity_verified=runtime_identity_verified,
        capabilities=capabilities or {},
        permissions=permissions or {
            'runtime_status': PERMISSIONS_RUNTIME_STATUS,
            'provisioning_status': 'SETUP_VERIFICATION_REQUIRED',
            'required': (),
        },
        provisioning_tasks=tuple(provisioning_tasks),
        normalized_capabilities=tuple(normalized_capabilities),
        provisioning_evidence_status=provisioning_evidence_status,
        publication_authorization=PUBLISH_AUTHORIZATION_STATUS,
        publication_ready=False,
        auto_publish=config.auto_publish if config else False,
        error_category=error_category,
        message=message,
    )


def run_preflight(config=None, client=None, requirements_path='config/meta.yaml'):
    """Verify Page-token identity without treating it as provisioning evidence."""
    try:
        config = config or MetaConfig.from_env()
        groups, required_permissions, evidence = _requirements(requirements_path)
        if client is None:
            from .client import MetaClient
            client = MetaClient(config.version, config.access_token)
        response = client.request(
            'GET', f'/{config.page_id}', fields={'fields': 'id,name'}, logical_name='page_identity')
        actual = str(response.get('id', ''))
        page_name = response.get('name')
        if actual != config.page_id:
            return _result(
                config=config, page_id=actual or None, page_name=page_name, token_valid=True,
                error_category='PAGE_ID_MISMATCH',
                message='The Page token resolved to a different Page')
        if not isinstance(page_name, str) or not page_name.strip():
            return _result(
                config=config, page_id=actual, token_valid=True,
                error_category='INVALID_PAGE_RESPONSE',
                message='The Page identity response did not include a Page name')

        permissions = {
            'runtime_status': PERMISSIONS_RUNTIME_STATUS,
            'provisioning_status': 'SETUP_VERIFICATION_REQUIRED',
            'required': required_permissions,
        }
        if evidence is None:
            capabilities = {name: NOT_RUNTIME_VERIFIABLE for name in groups}
            return _result(
                config=config, ok=True, page_id=actual, page_name=page_name, token_valid=True,
                runtime_identity_verified=True, capabilities=capabilities,
                permissions=permissions,
                message='Page identity verified; capabilities and permissions require provisioning evidence')

        tasks = tuple(evidence['tasks'])
        normalized = normalize_capabilities(tasks, groups)
        capabilities = {
            name: PROVISIONING_VERIFIED if name in normalized else PROVISIONING_NOT_VERIFIED
            for name in groups
        }
        if evidence['page_id'] != config.page_id:
            return _result(
                config=config, page_id=actual, page_name=page_name, token_valid=True,
                runtime_identity_verified=True, capabilities=capabilities, permissions=permissions,
                provisioning_tasks=tasks, normalized_capabilities=normalized,
                provisioning_evidence_status='PAGE_ID_MISMATCH',
                error_category='PROVISIONING_PAGE_ID_MISMATCH',
                message='Provisioning evidence belongs to a different Page')
        return _result(
            config=config, ok=True, page_id=actual, page_name=page_name, token_valid=True,
            runtime_identity_verified=True, capabilities=capabilities, permissions=permissions,
            provisioning_tasks=tasks, normalized_capabilities=normalized,
            provisioning_evidence_status=PROVISIONING_VERIFIED,
            message='Page identity verified; provisioning capability evidence loaded')
    except MetaError as exc:
        return _result(config=config, error_category=exc.category, message=str(exc))
    except MetaConfigurationError as exc:
        return _result(config=config, error_category=exc.category, message=str(exc))
