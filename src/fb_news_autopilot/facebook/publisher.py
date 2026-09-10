"""Photo publishing through the official Page photos edge."""
from datetime import datetime, timezone
from pathlib import Path

from .errors import MetaError
from .models import PublicationResult


def normalize_photo_response(page_id, response, published_at=None):
    photo_id = response.get('id') or response.get('photo_id')
    post_id = response.get('post_id')
    if not photo_id and not post_id:
        raise MetaError('INVALID_RESPONSE', 'Photo response did not include an id or post_id')
    return PublicationResult(page_id=str(page_id), photo_id=str(photo_id) if photo_id else None,
                             post_id=str(post_id) if post_id else None,
                             published_at=published_at or datetime.now(timezone.utc).isoformat(),
                             permalink=response.get('permalink_url'))


def publish_photo(client, page_id, image_path, caption):
    if not str(page_id).isdigit():
        raise ValueError('page_id must be numeric')
    image_path = Path(image_path)
    if not image_path.is_file():
        raise ValueError('Poster file does not exist')
    if not caption.strip():
        raise ValueError('Caption cannot be empty')
    response = client.request('POST', f'/{page_id}/photos', fields={'caption': caption, 'published': 'true'},
                              files={'source': image_path}, logical_name='publish_photo')
    return normalize_photo_response(page_id, response)
