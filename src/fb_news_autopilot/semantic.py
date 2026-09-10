"""Deterministically validate already-authored external semantic assessments.

Codex Automation authors semantic decisions through files. This module contains only
the legacy assessment shape and quote-grounding validation used by regression tests; it
does not invoke a model, network transport, or callback.
"""
import json
from jsonschema import Draft202012Validator, ValidationError
from .models import normalized_text

CHECK = {
    'type':'object', 'additionalProperties':False,
    'required':['supported','explanation','quotes'],
    'properties':{
        'supported':{'type':['boolean','null']},
        'explanation':{'type':'string','minLength':1},
        'quotes':{'type':'array','items':{'type':'string','minLength':1}},
    },
}
ASSESSMENT = {
    'type':'object','additionalProperties':False,
    'required':['headline','facts','event_time','event_quote','event_time_material','event_date_mismatch',
                'material_development_time','material_development_supported',
                'substantive_update_supported','development_quote',
                'verified_event_key','duplicate_uncertain','recirculated_without_development'],
    'properties':{
        'headline':CHECK,'facts':CHECK,
        'event_time':{'type':['string','null']},'event_quote':{'type':['string','null']},'event_time_material':{'type':'boolean'},
        'event_date_mismatch':{'type':'boolean'},'material_development_time':{'type':['string','null']},
        'material_development_supported':{'type':['boolean','null']},
        'substantive_update_supported':{'type':['boolean','null']},
        'development_quote':{'type':['string','null']},'verified_event_key':{'type':['string','null']},
        'duplicate_uncertain':{'type':'boolean'},'recirculated_without_development':{'type':'boolean'},
    },
}
def validate_assessment(evidence, decision):
        """Return only grounded M02 fields from an externally supplied decision object."""
        try:
            Draft202012Validator(ASSESSMENT).validate(decision)
        except (ValueError,TypeError,ValidationError) as exc:
            return {'headline_supported':None,'facts_supported':None,
                    'semantic_evidence':'Semantic assessment unavailable: '+type(exc).__name__,
                    'semantic_assessment_unclear':True}
        checked={}
        explanation=[]
        support_quotes_anchored=False
        support_grounding_invalid=False
        for name in ['headline','facts']:
            check=decision[name]
            valid_quotes=bool(check['quotes']) and all(normalized_text(q) in normalized_text(evidence.body) for q in check['quotes'])
            support_quotes_anchored=support_quotes_anchored or valid_quotes
            support_grounding_invalid=support_grounding_invalid or (check['supported'] is not None and not valid_quotes)
            checked[name+'_supported']=check['supported'] if valid_quotes else None
            explanation.append(name+': '+check['explanation']+'; quotes='+json.dumps(check['quotes'],ensure_ascii=False))
        quote=decision['development_quote']
        anchored=bool(quote and normalized_text(quote) in normalized_text(evidence.body))
        event_quote=decision['event_quote']
        event_anchored=bool(event_quote and normalized_text(event_quote) in normalized_text(evidence.body))
        development_judgment=(decision['material_development_supported'] is not None
            or decision['substantive_update_supported'] is not None)
        ungrounded=(decision['event_date_mismatch'] and not event_anchored) or (
            development_judgment and not anchored) or (
            decision['recirculated_without_development'] and not (anchored or event_anchored))
        identity_anchored=support_quotes_anchored or anchored or event_anchored
        if ungrounded:
            checked['headline_supported']=None
            checked['facts_supported']=None
        checked.update({
            'semantic_evidence':' | '.join(explanation)+' | raw_assessment='+json.dumps(decision,ensure_ascii=False),
            'event_time':decision['event_time'] if event_anchored else None, 'event_time_material':decision['event_time_material'] or bool(decision['event_time'] and not event_anchored),
            'event_date_mismatch':decision['event_date_mismatch'] if event_anchored else False,
            'material_development_time':decision['material_development_time'],
            'material_development_supported':decision['material_development_supported'] if anchored else None,
            'substantive_update_supported':decision['substantive_update_supported'] if anchored else None,
            'development_evidence':quote if anchored else None,
            'verified_event_key':decision['verified_event_key'] if identity_anchored else None,
            'duplicate_uncertain':decision['duplicate_uncertain'],
            'recirculated_without_development':decision['recirculated_without_development'] if (anchored or event_anchored) else False,
            'semantic_assessment_unclear':support_grounding_invalid or ungrounded or bool(decision['verified_event_key'] and not identity_anchored),
        })
        return checked
