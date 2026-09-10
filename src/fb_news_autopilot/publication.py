"""Idempotent post-then-comment coordinator."""
from .editorial import compose_facebook_caption
from .facebook.comments import publish_first_comment
from .facebook.publisher import publish_photo
from .facebook.verifier import verify_publication
from .state import State, publication_key


class PublicationCoordinator:
    def __init__(self, client, store):
        self.client = client
        self.store = store

    def execute(self, *, news_id, canonical_url, editorial, image_path, page_id):
        expected_key=publication_key(canonical_url,editorial['editorial_version'])
        if self.store.publication(expected_key) is None and self.store.current(news_id) != State.READY_TO_PUBLISH:
            raise ValueError('Candidate is not READY_TO_PUBLISH')
        key, created, record = self.store.reserve_publication(news_id, canonical_url,
                                                               editorial['editorial_version'])
        if created:
            self.store.transition(news_id, State.PUBLISHING, 'Meta photo publish started')
            try:
                publication = publish_photo(self.client, page_id, image_path, compose_facebook_caption(editorial))
            except Exception:
                self.store.transition(news_id, State.FAILED,
                                      'Photo publish outcome is uncertain; automatic retry prohibited')
                raise
            self.store.record_publication(key, publication,
                                          'PUBLISHED' if publication.post_id else 'PUBLISHED_COMMENT_PENDING')
            self.store.transition(news_id, State.PUBLISHED if publication.post_id
                                  else State.PUBLISHED_COMMENT_PENDING,
                                  'Meta photo response normalized')
            record = self.store.publication(key)
        if not record.get('post_id'):
            return {'idempotency_key': key, 'publication': record, 'comment': None,
                    'state': 'PUBLISHED_COMMENT_PENDING' if record.get('photo_id') else 'COMPLIANCE_HOLD'}
        post_id = record['post_id']
        if self.store.comment_recorded(post_id):
            state = 'VERIFIED_ON_FACEBOOK' if record['status']=='VERIFIED_ON_FACEBOOK' else 'COMMENTED'
            return {'idempotency_key': key, 'publication': record, 'comment': None, 'state': state}
        try:
            comment = publish_first_comment(self.client, post_id, editorial['first_comment'])
        except Exception:
            self.store.set_publication_status(key, 'PUBLISHED_COMMENT_PENDING')
            if self.store.current(news_id) == State.PUBLISHED:
                self.store.transition(news_id, State.PUBLISHED_COMMENT_PENDING,
                                      'First comment failed and may be retried')
            return {'idempotency_key': key, 'publication': record, 'comment': None,
                    'state': 'PUBLISHED_COMMENT_PENDING'}
        self.store.record_comment(comment)
        self.store.set_publication_status(key, 'COMMENTED')
        self.store.transition(news_id, State.COMMENTED, 'First comment confirmed')
        verification = None
        try:
            verification = verify_publication(self.client, post_id)
            if verification['post_id']==post_id and verification['is_published']:
                self.store.set_publication_status(key, 'VERIFIED_ON_FACEBOOK')
                self.store.transition(news_id, State.VERIFIED_ON_FACEBOOK,
                                      'Published post verified by read-back')
        except Exception:
            pass
        state = self.store.publication(key)['status']
        return {'idempotency_key': key, 'publication': self.store.publication(key),
                'comment': comment.to_dict(), 'verification': verification, 'state': state}
