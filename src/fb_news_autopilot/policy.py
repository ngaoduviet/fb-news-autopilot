"""Config-driven publishing and compliance gates."""
import os
from pathlib import Path

import yaml

from .models import timestamp


ALLOWED_IMAGE_RIGHTS = {'OWNED', 'LICENSED', 'PERMITTED'}


def load_policy(path='config/publish_policy.yaml'):
    with Path(path).open(encoding='utf-8') as stream:
        policy = yaml.safe_load(stream)
    required = {'max_posts_per_cycle', 'review_auto_publish', 'rejected_auto_publish',
                'unknown_image_rights_publish', 'minimum_verification_confidence',
                'allowed_source_tiers', 'freshness_maximum_hours', 'duplicate_cooldown_hours'}
    if set(policy) != required:
        raise ValueError('Publish policy keys are incomplete or unknown')
    return policy


def auto_publish_enabled(environment=None):
    value = (environment if environment is not None else os.environ).get('META_AUTO_PUBLISH', 'false').strip().lower()
    return value == 'true'


def compliance_gate(candidate, decision, editorial, poster_valid, policy, *, duplicate=False):
    reasons = []
    if decision['status'] != 'VERIFIED' or decision['handoff_allowed'] is not True:
        reasons.append('HOLD_SEMANTIC_STATUS')
    if decision['confidence'] < policy['minimum_verification_confidence']:
        reasons.append('HOLD_VERIFICATION_CONFIDENCE')
    if candidate.get('origin_quality') not in policy['allowed_source_tiers']:
        reasons.append('HOLD_SOURCE_TIER')
    effective = decision.get('material_development_time') or candidate.get('published_at')
    if not effective:
        reasons.append('HOLD_FRESHNESS_UNCLEAR')
    else:
        age = (timestamp(candidate['discovered_at']) - timestamp(effective)).total_seconds() / 3600
        if age < 0 or age > policy['freshness_maximum_hours']:
            reasons.append('HOLD_FRESHNESS_POLICY')
    if not all(editorial['compliance'].values()):
        reasons.append('HOLD_EDITORIAL_COMPLIANCE')
    if candidate['image_rights_status'] not in ALLOWED_IMAGE_RIGHTS:
        reasons.append('HOLD_IMAGE_RIGHTS')
    if not poster_valid:
        reasons.append('HOLD_POSTER_INVALID')
    if duplicate:
        reasons.append('HOLD_DUPLICATE_PUBLICATION')
    return {'passed': not reasons, 'reason_codes': reasons}
