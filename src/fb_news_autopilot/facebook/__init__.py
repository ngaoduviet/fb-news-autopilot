"""Official Meta Graph API boundary; no browser automation."""

from .auth import MetaConfig, PreflightResult, run_preflight
from .client import MetaClient
from .comments import publish_first_comment
from .publisher import publish_photo

__all__ = ['MetaClient', 'MetaConfig', 'PreflightResult', 'publish_first_comment',
           'publish_photo', 'run_preflight']
