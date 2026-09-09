from dataclasses import replace
import pytest
from fb_news_autopilot.models import RunContext,Observation,ArticleEvidence
from fb_news_autopilot.radar import NewsRadar,INPUT_SCORES
from fb_news_autopilot.verifier import SourceVerifier

@pytest.fixture
def context(): return RunContext(run_id='test-01',run_at='2026-09-09T12:00:00+07:00')

@pytest.fixture
def observation(context):
    return Observation(url='https://publisher.example/news/decision-123',headline='City approved the new benefit',query_or_feed='fixture',discovered_at=context.run_at,
        publisher='Publisher',publication_time='2026-09-09T11:00:00+07:00',facts=('The benefit is 500 units',),entities=('City',),topic='money_policy',score_components=tuple((key,80) for key in sorted(INPUT_SCORES)))

@pytest.fixture
def candidate(context,observation): return NewsRadar().run(context,[observation])[0][0]

@pytest.fixture
def article(observation):
    return ArticleEvidence(requested_url=observation.url,final_url=observation.url,canonical_url=observation.url,page_type='ARTICLE',accessible=True,publisher_name='Publisher',source_identity=True,
        origin_quality='DIRECT_REPUTABLE_ARTICLE',title=observation.headline,body='City approved the new benefit.\nThe benefit is 500 units.\nThe new decision was issued at 11:00 today.',publication_time=observation.publication_time,
        headline_supported=True,facts_supported=True,semantic_evidence='Exact article states the city approved the benefit and specifies 500 units.')

class FixedProvider:
    def __init__(self,article): self.article=article; self.calls=0
    def inspect(self,candidate,context): self.calls+=1; return self.article

@pytest.fixture
def verify(candidate,context,article):
    def run(**changes): return SourceVerifier(FixedProvider(replace(article,**changes))).verify(candidate,context)[0]
    return run
