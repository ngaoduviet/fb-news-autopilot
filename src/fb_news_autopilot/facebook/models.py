"""Internal normalized Meta results."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PublicationResult:
    page_id: str
    photo_id: str | None
    post_id: str | None
    published_at: str
    permalink: str | None = None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class CommentResult:
    post_id: str
    comment_id: str
    published_at: str

    def to_dict(self):
        return asdict(self)
