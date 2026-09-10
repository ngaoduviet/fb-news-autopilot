"""Small official Graph API HTTP client with injectable transport and safe audit data."""
from datetime import datetime, timezone
import json
import mimetypes
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import uuid
import re

from ..security import redact
from .errors import MetaError


def _multipart(fields, files):
    boundary = '----fbna' + uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name, path in files.items():
        path = Path(path)
        mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{path.name}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
        body.extend(path.read_bytes())
        body.extend(b'\r\n')
    body.extend(f'--{boundary}--\r\n'.encode())
    return bytes(body), f'multipart/form-data; boundary={boundary}'


class UrllibTransport:
    def request(self, method, url, fields, files=None):
        fields = {key: str(value) for key, value in fields.items()}
        headers = {'Accept': 'application/json'}
        if files:
            data, content_type = _multipart(fields, files)
            headers['Content-Type'] = content_type
        else:
            data = urlencode(fields).encode() if method == 'POST' else None
            if method == 'GET' and fields:
                url += ('&' if '?' in url else '?') + urlencode(fields)
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read().decode('utf-8'))
        except HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')
            raise MetaError('API_ERROR', redact(body), exc.code) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise MetaError('NETWORK_ERROR', redact(exc)) from exc


class MetaClient:
    def __init__(self, version, access_token, transport=None, audit=None):
        if not re.fullmatch(r'v\d+\.\d+',version or ''):
            raise ValueError('A safe META_GRAPH_API_VERSION is required')
        if not access_token:
            raise ValueError('A Page access token is required')
        self.base_url = f'https://graph.facebook.com/{version}'
        self._access_token = access_token
        self.transport = transport or UrllibTransport()
        self.audit = audit if audit is not None else []

    def request(self, method, path, *, fields=None, files=None, logical_name):
        if not re.fullmatch(r'/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?',path):
            raise ValueError('Unsafe Graph API path')
        start = time.monotonic()
        status = None
        category = None
        try:
            payload = dict(fields or {})
            payload['access_token'] = self._access_token
            status, result = self.transport.request(method, self.base_url + path, payload, files)
            if not isinstance(result, dict):
                raise MetaError('INVALID_RESPONSE', 'Graph API response must be an object', status)
            if 'error' in result:
                error = result['error'] if isinstance(result['error'], dict) else {}
                raise MetaError('PERMISSION_OR_API_ERROR', redact(error.get('message', 'Graph API error')), status)
            return result
        except MetaError as exc:
            status = exc.status_code
            category = exc.category
            raise MetaError(exc.category, redact(exc), exc.status_code) from exc
        finally:
            self.audit.append({'endpoint': logical_name, 'status_code': status,
                               'duration_ms': round((time.monotonic() - start) * 1000),
                               'attempt': 1, 'error_category': category,
                               'timestamp': datetime.now(timezone.utc).isoformat()})
