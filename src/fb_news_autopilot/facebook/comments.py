"""First-comment publishing through the official comments edge."""
from datetime import datetime, timezone
import re

from .models import CommentResult


def publish_first_comment(client, post_id, message, *, already_recorded=False):
    if already_recorded:
        raise ValueError('First comment is already recorded')
    if not post_id or not re.fullmatch(r'[A-Za-z0-9_.-]+',str(post_id)):
        raise ValueError('A confirmed post_id is required')
    if not message or not message.strip():
        raise ValueError('First comment cannot be empty')
    response = client.request('POST', f'/{post_id}/comments', fields={'message': message},
                              logical_name='publish_first_comment')
    comment_id = response.get('id')
    if not comment_id:
        raise ValueError('Comment response did not include an id')
    return CommentResult(str(post_id), str(comment_id), datetime.now(timezone.utc).isoformat())
