"""Discovery interfaces and deterministic preliminary scoring."""
from typing import Protocol

from ..models import Observation, RunContext, normalized_text


class DiscoveryConfigError(ValueError):
    pass


class DiscoveryAdapter(Protocol):
    errors: list[dict]
    def discover(self, context: RunContext) -> list[Observation]: ...


def deterministic_scores(title: str, summary: str = '', topic: str = 'other') -> dict[str, float]:
    """Transparent keyword scoring for M01 priority; it never verifies a claim."""
    text=normalized_text(title+' '+summary)
    money=('thuế','lương','giá vàng','lãi suất','đất','trợ cấp','phúc lợi','ngân hàng','tiền')
    life=('cảnh báo','bão','lũ','cháy','tai nạn','sức khỏe','an toàn','triệu hồi')
    breaking=('khẩn','mới nhất','vừa','chính thức','công bố','quyết định')
    impact=max(sum(term in text for term in money),sum(term in text for term in life))
    timely=sum(term in text for term in breaking)
    topic_bonus={'money_policy':20,'breaking_social':18,'life_alert':16,'tech_trend':10}.get(topic,5)
    return {
        'viral_potential': min(100,40+8*timely+4*impact),
        'direct_life_impact': min(100,35+12*impact+topic_bonus),
        'money_benefit_value': min(100,25+15*sum(term in text for term in money)),
        'emotional_pull': min(100,30+8*sum(term in text for term in life)),
        'debate_potential': min(100,30+5*impact),
        'freshness_score': 70,
        'audience_quality_score': min(100,45+topic_bonus),
        'money_value_score': min(100,30+15*sum(term in text for term in money)),
        'production_score': 60,
    }
