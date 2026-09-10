"""Read-back verification for a normalized Page post."""


def verify_publication(client, post_id):
    if not post_id:
        raise ValueError('post_id is required')
    response = client.request('GET', f'/{post_id}', fields={'fields': 'id,permalink_url,is_published'},
                              logical_name='verify_publication')
    return {'post_id': str(response.get('id')) if response.get('id') else None,
            'permalink': response.get('permalink_url'),
            'is_published': response.get('is_published') is True}
