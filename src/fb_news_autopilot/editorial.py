"""Strict deterministic validation for Codex-authored editorial artifacts."""
import json
from pathlib import Path
import re
import unicodedata

import yaml

from jsonschema import ValidationError

from .contracts import validate
from .models import normalized_text
from .queueing import HandoffHold, load_semantic_decisions, run_directory, safe_identifier


DISCLOSURE = ('Bài đăng được biên tập/tóm tắt với sự hỗ trợ của AI. '
              'Tuân thủ nghiêm ngặt Nghị định 237/2026/NĐ-CP.')
HOOK = re.compile(r'^\[[^\]\n]+\]')
HASHTAG = re.compile(r'(?<!\w)#[^\s#]+')


def word_count(value):
    return len(value.split())


def load_sensitive_words(path='config/editorial.yaml'):
    try:
        value = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
        words = value['facebook_sensitive_words']
        if not isinstance(words, list) or not words or any(not isinstance(word, str) or not word.strip() for word in words):
            raise ValueError
        return tuple(word.strip().casefold() for word in words)
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise HandoffHold('HOLD_EDITORIAL_RULES_INVALID', 'Sensitive-word configuration is invalid') from exc


def _contains_raw_term(text, term):
    return re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text.casefold()) is not None


def _hook_symbol_count(caption):
    first_line = caption.splitlines()[0]
    return sum(unicodedata.category(character) == 'So' for character in first_line)


def compose_facebook_caption(editorial):
    """Compose the exact publish payload once, without mutating editorial text."""
    caption = editorial['recommended_caption']
    hashtags = editorial['hashtags']
    if len(hashtags) != 5 or len(set(hashtags)) != 5 or HASHTAG.search(caption):
        raise HandoffHold('HOLD_HASHTAG_INVALID', 'Publishing requires five unique separate hashtags')
    composed = caption + '\n\n' + ' '.join(hashtags)
    if HASHTAG.findall(composed) != hashtags:
        raise HandoffHold('HOLD_HASHTAG_INVALID', 'Published hashtags differ from the editorial contract')
    return composed


def validate_editorial(document, candidate, decision, *, sensitive_words=None):
    """Validate structure and all mechanically enforceable editorial rules."""
    try:
        validate('editorial', document)
    except (ValidationError, ValueError, TypeError) as exc:
        raise HandoffHold('HOLD_EDITORIAL_INVALID', 'Editorial JSON does not match its schema') from exc
    if decision['status'] != 'VERIFIED' or decision['handoff_allowed'] is not True:
        raise HandoffHold('HOLD_EDITORIAL_NOT_ALLOWED', 'Only verified candidates may enter editorial')
    if document['news_id'] != candidate['news_id'] or document['news_id'] != decision['news_id']:
        raise HandoffHold('HOLD_EDITORIAL_ID_MISMATCH', 'Editorial news_id does not match its evidence')
    if document['source_url'] not in {candidate['source_url'], candidate['canonical_url']}:
        raise HandoffHold('HOLD_EDITORIAL_SOURCE_MISMATCH', 'Editorial source URL does not match the verified candidate')
    expected = document['caption_option_1'] if document['recommended_option'] == 1 else document['caption_option_2']
    if document['recommended_caption'] != expected:
        raise HandoffHold('HOLD_EDITORIAL_RECOMMENDATION_MISMATCH', 'Recommended caption must equal the selected option')
    for key in ('caption_option_1', 'caption_option_2'):
        if not HOOK.match(document[key]):
            raise HandoffHold('HOLD_CAPTION_HOOK', 'Each caption must begin with a square-bracket hook or location')
        if _hook_symbol_count(document[key]) > 1:
            raise HandoffHold('HOLD_CAPTION_EMOJI_LIMIT', 'A caption hook may contain at most one icon or emoji')
        if HASHTAG.search(document[key]):
            raise HandoffHold('HOLD_HASHTAG_INVALID', 'Hashtags must remain in the separate five-item array')
    if not 25 <= word_count(document['caption_option_1']) <= 65:
        raise HandoffHold('HOLD_CAPTION_LENGTH', 'Caption option 1 must contain 25-65 words')
    if not 25 <= word_count(document['caption_option_2']) <= 65:
        raise HandoffHold('HOLD_CAPTION_LENGTH', 'Caption option 2 must contain 25-65 words')
    if not 80 <= word_count(document['first_comment']) <= 150:
        raise HandoffHold('HOLD_COMMENT_LENGTH', 'First comment must contain 80-150 words')
    if f"Nguồn tham khảo: {document['source_name']}" not in document['first_comment'] or f"Link bài viết gốc: {document['source_url']}" not in document['first_comment']:
        raise HandoffHold('HOLD_COMMENT_SOURCE_MISSING', 'First comment must name and link the exact source')
    if DISCLOSURE not in document['first_comment']:
        raise HandoffHold('HOLD_COMMENT_DISCLOSURE_MISSING', 'First comment must include the required disclosure')
    if HASHTAG.search(document['first_comment']):
        raise HandoffHold('HOLD_HASHTAG_INVALID', 'First comment cannot contain extra hashtags')
    if not 7 <= word_count(document['headline']) <= 15:
        raise HandoffHold('HOLD_HEADLINE_LENGTH', 'Headline must contain 7-15 words')
    if normalized_text(' '.join(document['headline_lines'])) != normalized_text(document['headline']):
        raise HandoffHold('HOLD_HEADLINE_LINES', 'Headline lines must reproduce the headline exactly')
    headline = normalized_text(document['headline'])
    if any(normalized_text(keyword) not in headline for keyword in document['yellow_keywords']):
        raise HandoffHold('HOLD_YELLOW_KEYWORD_INVALID', 'Yellow keywords must occur in the headline')
    terms = sensitive_words if sensitive_words is not None else load_sensitive_words()
    fields = [document['caption_option_1'], document['caption_option_2'], document['first_comment'],
              document['headline'], *document['headline_lines']]
    if any(_contains_raw_term(text, term) for text in fields for term in terms):
        raise HandoffHold('HOLD_SENSITIVE_WORD_UNTRANSFORMED', 'Editorial output contains a raw sensitive term')
    compose_facebook_caption(document)
    return document


def load_editorial(run_id, *, root='data/queue'):
    directory = run_directory(root, run_id)
    queue, semantic = load_semantic_decisions(run_id, root=root)
    candidates = {item['news_id']: item for item in queue['candidates']}
    decisions = {item['news_id']: item for item in semantic['decisions']}
    eligible = {news_id for news_id, item in decisions.items()
                if item['status'] == 'VERIFIED' and item['handoff_allowed'] is True}
    editorial_directory = directory / 'editorial'
    loaded = {}
    for news_id in eligible:
        if not safe_identifier(news_id):
            raise HandoffHold('HOLD_ARTIFACT_PATH_INVALID', 'Editorial news_id is unsafe')
        path = editorial_directory / (news_id + '.json')
        if not path.exists():
            raise HandoffHold('HOLD_EDITORIAL_FILE_MISSING', 'Editorial file is missing for a verified candidate')
        try:
            document = json.loads(path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError) as exc:
            raise HandoffHold('HOLD_EDITORIAL_INVALID', 'Editorial JSON cannot be read') from exc
        loaded[news_id] = validate_editorial(document, candidates[news_id], decisions[news_id])
    unexpected = {path.stem for path in editorial_directory.glob('*.json')} - eligible if editorial_directory.exists() else set()
    if unexpected:
        raise HandoffHold('HOLD_EDITORIAL_NOT_ALLOWED', 'Editorial exists for a review or rejected candidate')
    return queue, semantic, loaded
