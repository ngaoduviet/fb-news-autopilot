"""Build the checked-in, self-contained Draft 2020-12 contracts."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def obj(properties, **kw):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False, **kw}
def enum(*values): return {'enum': list(values)}
def arr(items): return {'type': 'array', 'items': items}
def nullable(schema): return {'anyOf': [schema, {'type': 'null'}]}
S = {'type': 'string'}
TEXT = {'type': 'string', 'minLength': 1}
N = {'type': 'number', 'minimum': 0}
BOOL = {'type': 'boolean'}
TRI = nullable(BOOL)
TIME = {'type': 'string', 'format': 'date-time', 'pattern': r'(Z|[+-]\d{2}:\d{2})$'}
URL = {'type': 'string', 'format': 'uri', 'pattern': r'^https://[^/\s?#]+(?:[/?#].*)?$'}
SCORE_NAMES = 'viral_potential direct_life_impact money_benefit_value emotional_pull debate_potential freshness_score hot_score audience_quality_score money_value_score production_score top_content_score'.split()
SCORES = obj({k: {'type': 'number', 'minimum': 0, 'maximum': 100} for k in SCORE_NAMES})
TOPIC = enum('money_policy', 'breaking_social', 'life_alert', 'tech_trend', 'global', 'sport', 'entertainment', 'other')
BUCKET = enum('LIVE', 'HOT', 'OLD', 'UNKNOWN')
PAGE = enum('ARTICLE', 'HOMEPAGE', 'CATEGORY', 'TAG_TOPIC', 'SEARCH_RESULTS', 'AGGREGATOR', 'REDIRECT_ONLY', 'INACCESSIBLE', 'UNKNOWN')
ORIGIN = enum('PRIMARY_OFFICIAL', 'DIRECT_REPUTABLE_ARTICLE', 'SECONDARY_REPUTABLE_ARTICLE', 'AGGREGATOR_ONLY', 'UNKNOWN')
REJECT = ['REJECT_'+x for x in 'OLD_NEWS NO_NEW_DEVELOPMENT NOT_DIRECT_ARTICLE HOMEPAGE_URL CATEGORY_URL SEARCH_URL TAG_TOPIC_URL AGGREGATOR_AS_FINAL_SOURCE REDIRECT_TO_NON_ARTICLE ARTICLE_INACCESSIBLE SOURCE_UNVERIFIABLE HEADLINE_UNSUPPORTED FACTS_UNSUPPORTED DUPLICATE_STORY INVALID_URL'.split()]
REVIEW = ['REVIEW_'+x for x in 'PUBLICATION_TIME_UNCLEAR EVENT_TIME_UNCLEAR SOURCE_IDENTITY_UNCLEAR NEW_DEVELOPMENT_UNCLEAR CONFLICTING_SOURCES DUPLICATE_UNCERTAIN ARTICLE_ACCESS_LIMITED_CORROBORATED HEADLINE_SUPPORT_UNCLEAR FACT_SUPPORT_UNCLEAR'.split()]
CONTEXT = obj({'run_id': TEXT, 'run_at': TIME, 'timezone': TEXT, 'live_window_hours': {'type':'number','exclusiveMinimum':0}, 'hot_window_hours': {'type':'number','exclusiveMinimum':0}, 'brand_profile': TEXT, 'mode': enum('shadow','approval','production')})
DISCOVERY_CITATION = obj({'reference_id':nullable(TEXT),'url':URL,'title':nullable(TEXT),'kind':nullable(TEXT)})
DISCOVERY = obj({'query_or_feed': TEXT, 'discovered_at': TIME, 'discovered_url': URL, 'publisher_name': nullable(TEXT), 'headline_observed': TEXT, 'publication_time_observed': nullable(TIME),
                 'discovery_provider':TEXT,'search_evidence':nullable(S),'citation_metadata':arr(DISCOVERY_CITATION)})
CANDIDATE = obj({'news_id': TEXT, 'story_cluster_id': TEXT, 'discovery': DISCOVERY, 'normalized': obj({'title': TEXT, 'topic': TOPIC, 'summary_facts': arr(TEXT), 'main_entities':arr(TEXT), 'location':nullable(S)}), 'scores': SCORES, 'preliminary_freshness': obj({'bucket':BUCKET,'age_hours':nullable(N),'new_development_claimed':BOOL,'requires_m02_freshness_verification':BOOL}), 'm01_status':enum('DISCOVERED','SHORTLISTED','REJECTED_PRELIMINARY')})
# Raw discovery URLs are deliberately strings at the terminal audit boundary:
# invalid/non-HTTPS submissions must remain recordable with REJECT_INVALID_URL.
SOURCE = obj({'publisher_name':nullable(TEXT),'discovered_url':S,'resolved_article_url':nullable(URL),'canonical_url':nullable(URL),'publication_time':nullable(TIME),'last_updated_time':nullable(TIME),'event_time':nullable(TIME),'material_development_time':nullable(TIME),'corroborating_urls':arr(URL)})
VERIFICATION = obj({'status':enum('VERIFIED','REVIEW','REJECTED'),'verified_at':TIME,'page_type':PAGE,'article_accessible':TRI,'headline_supported':TRI,'facts_supported':TRI,'origin_quality':ORIGIN,'rejection_codes':arr(enum(*REJECT)),'review_codes':arr(enum(*REVIEW)),'evidence_summary':TEXT})
VERIFICATION['allOf'] = []
for status in ['VERIFIED', 'REVIEW', 'REJECTED']:
    rules = {'rejection_codes': {'maxItems': 0}, 'review_codes': {'maxItems': 0}}
    if status == 'VERIFIED':
        rules.update({'page_type': {'const': 'ARTICLE'}, 'article_accessible': {'const': True},
                      'headline_supported': {'const': True}, 'facts_supported': {'const': True}})
    else:
        rules['review_codes' if status == 'REVIEW' else 'rejection_codes'] = {'minItems': 1}
    VERIFICATION['allOf'].append({'if': {'properties': {'status': {'const': status}}},
                                  'then': {'properties': rules}})
RESULT = obj({'schema_version':{'const':'1.0.0'},'run_context':CONTEXT,'news_id':TEXT,'story_cluster_id':TEXT,'source':SOURCE,'content':obj({'candidate_title':TEXT,'candidate_summary_facts':arr(TEXT),'main_entities':arr(TEXT),'topic':TOPIC,'location':nullable(S),'verified_title':nullable(TEXT),'verified_summary_facts':arr(TEXT)}),'freshness':obj({'bucket':BUCKET,'age_hours':nullable(N),'effective_freshness_time':nullable(TIME),'basis':TEXT}),'scores':SCORES,'verification':VERIFICATION,'handoff':obj({'eligible_for_editorial_module':BOOL,'package_01_complete':{'const':True}})})
RESULT['allOf'] = []
for status in ['VERIFIED','REVIEW','REJECTED']:
    v = {'rejection_codes': {'maxItems':0}, 'review_codes':{'maxItems':0}}
    prop = {'verification': {'properties':v},'handoff':{'properties':{'eligible_for_editorial_module':{'const':status=='VERIFIED'}}}}
    if status=='VERIFIED':
        v.update({'page_type':{'const':'ARTICLE'},'article_accessible':{'const':True},'headline_supported':{'const':True},'facts_supported':{'const':True},'origin_quality':enum('PRIMARY_OFFICIAL','DIRECT_REPUTABLE_ARTICLE','SECONDARY_REPUTABLE_ARTICLE')})
        prop['source']={'properties':{'resolved_article_url':URL,'publication_time':TIME}}
        prop['content']={'properties':{'verified_title':TEXT}}
        prop['freshness']={'properties':{'bucket':enum('LIVE','HOT'),'effective_freshness_time':TIME,'age_hours':N}}
    else:
        v['review_codes' if status=='REVIEW' else 'rejection_codes']={'minItems':1}
        prop['content']={'properties':{'verified_title':{'type':'null'},'verified_summary_facts':{'maxItems':0}}}
    RESULT['allOf'].append({'if':{'properties':{'verification':{'properties':{'status':{'const':status}}}}},'then':{'properties':prop}})
SUMMARY=obj({'run_id':TEXT,'candidate_count':{'type':'integer','minimum':0},'shortlisted_count':{'type':'integer','minimum':0},'preliminary_rejected_count':{'type':'integer','minimum':0},'shortlisted_news_ids':arr(TEXT)})
RUN=obj({'run_context':CONTEXT,'outcome':enum('VERIFIED_CANDIDATES_AVAILABLE','NO_VERIFIED_CANDIDATES','RUN_PARTIAL_FAILURE','RUN_FAILURE'),'candidates':arr(CANDIDATE),'results':arr(RESULT),'radar_summary':SUMMARY,'audit':arr(obj({'stage':enum('M01','M02','RUN'),'news_id':nullable(TEXT),'code':TEXT,'detail':S}))})
QUEUE_CHECKS=obj({'url_valid':BOOL,'page_type':PAGE,'article_accessible':TRI,'source_identity':TRI,
                  'publication_time_found':BOOL,'preliminary_freshness':BUCKET,'exact_article_candidate':BOOL})
QUEUE_ITEM=obj({'news_id':TEXT,'story_cluster_id':TEXT,'title':TEXT,'source':nullable(TEXT),
                'source_url':URL,'canonical_url':nullable(URL),'published_at':nullable(TIME),
                'origin_quality':ORIGIN,
                'discovered_at':TIME,'rss_summary':nullable(S),'article_text_path':TEXT,
                'article_evidence_path':TEXT,'source_image_url':nullable(URL),
                'image_rights_status':enum('OWNED','LICENSED','PERMITTED','UNKNOWN'),
                'deterministic_checks':QUEUE_CHECKS,'needs_semantic_verification':{'const':True},
                'candidate_contract':CANDIDATE})
CANDIDATE_QUEUE=obj({'schema_version':{'const':'1.0.0'},'run_id':TEXT,'generated_at':TIME,
                     'timezone':TEXT,'candidates':arr(QUEUE_ITEM)})
SEMANTIC_EVIDENCE=obj({'claim':TEXT,'quote':TEXT,'source_url':URL})
SEMANTIC_DECISION=obj({'news_id':TEXT,'status':enum('VERIFIED','REVIEW','REJECTED'),
                       'reason_codes':arr(enum(*(REJECT+REVIEW))),
                       'article_title_verified':TRI,'publication_time_verified':TRI,
                       'facts_supported':TRI,'event_time_verified':TRI,
                       'new_development_verified':TRI,'material_development_time':nullable(TIME),
                       'verified_event_key':nullable(TEXT),'verified_facts':arr(TEXT),
                       'unsupported_claims':arr(TEXT),'evidence':arr(SEMANTIC_EVIDENCE),
                       'confidence':{'type':'number','minimum':0,'maximum':1},'handoff_allowed':BOOL})
SEMANTIC_DECISION['allOf']=[
    {'if':{'properties':{'status':{'const':'VERIFIED'}}},'then':{'properties':{
        'reason_codes':{'maxItems':0},'article_title_verified':{'const':True},
        'publication_time_verified':{'const':True},'facts_supported':{'const':True},
        'unsupported_claims':{'maxItems':0},'evidence':{'minItems':1},
        'handoff_allowed':{'const':True}}}},
    {'if':{'properties':{'status':{'const':'REVIEW'}}},'then':{'properties':{
        'reason_codes':{'type':'array','minItems':1,'items':enum(*REVIEW)},
        'handoff_allowed':{'const':False}}}},
    {'if':{'properties':{'status':{'const':'REJECTED'}}},'then':{'properties':{
        'reason_codes':{'type':'array','minItems':1,'items':enum(*REJECT)},
        'handoff_allowed':{'const':False}}}},
]
SEMANTIC_DECISIONS=obj({'schema_version':{'const':'1.0.0'},'run_id':TEXT,
                        'generated_at':TIME,'decisions':arr(SEMANTIC_DECISION)})
EDITORIAL_COMPLIANCE=obj({'facts_grounded':{'const':True},
                          'sensitive_words_transformed':{'const':True},
                          'has_exactly_5_hashtags':{'const':True},
                          'caption_length_ok':{'const':True},
                          'comment_length_ok':{'const':True}})
EDITORIAL=obj({'schema_version':{'const':'1.0.0'},'news_id':TEXT,
               'editorial_version':TEXT,'generated_at':TIME,
               'caption_option_1':TEXT,'caption_option_2':TEXT,
               'recommended_option':enum(1,2),'recommended_caption':TEXT,
               'hashtags':{'type':'array','minItems':5,'maxItems':5,'uniqueItems':True,
                           'items':{'type':'string','pattern':r'^#[^\s#]+$'}},
               'first_comment':TEXT,'source_name':TEXT,'source_url':URL,
               'headline':TEXT,
               'headline_lines':{'type':'array','minItems':3,'maxItems':4,'items':TEXT},
               'yellow_keywords':{'type':'array','maxItems':2,'uniqueItems':True,'items':TEXT},
               'image_prompt':TEXT,'compliance':EDITORIAL_COMPLIANCE})
ASSET=obj({'schema_version':{'const':'1.0.0'},'news_id':TEXT,'rendered_at':TIME,
           'image_rights_status':enum('OWNED','LICENSED','PERMITTED'),
           'source_image_sha256':{'type':'string','pattern':r'^[0-9a-f]{64}$'},
           'poster_sha256':{'type':'string','pattern':r'^[0-9a-f]{64}$'},
           'poster_path':TEXT,'width':{'const':1080},'height':{'const':1350},
           'safe_margin_valid':{'const':True}})
SCHEMAS={'run-context':CONTEXT,'candidate-news-package':CANDIDATE,
         'source-verification':obj({'verification':VERIFICATION}),'package-01-result':RESULT,
         'verified-news-package':{**RESULT, 'properties':{**RESULT['properties'],'verification':{**VERIFICATION,'properties':{**VERIFICATION['properties'],'status':{'const':'VERIFIED'}}}}},
         'radar-summary':SUMMARY,'run-result':RUN,'candidate-queue':CANDIDATE_QUEUE,
         'semantic-decisions':SEMANTIC_DECISIONS,'editorial':EDITORIAL,
         'rendered-asset':ASSET}
for name, schema in SCHEMAS.items():
    schema = {'$schema':'https://json-schema.org/draft/2020-12/schema','$id':f'urn:fb-news-autopilot:{name}:1.0.0',**schema}
    (ROOT/'schemas'/f'{name}.schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2)+'\n')
