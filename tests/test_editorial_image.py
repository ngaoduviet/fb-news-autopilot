import json

from PIL import Image
import pytest

from fb_news_autopilot.editorial import DISCLOSURE, compose_facebook_caption, load_editorial, validate_editorial
from fb_news_autopilot.assets import load_asset_manifest, resolve_asset, write_asset_manifest
from fb_news_autopilot.image import ImageRightsHold, render_poster, validate_poster
from fb_news_autopilot.queueing import HandoffHold
from test_queueing import decision, make_queue


def words(count, prefix='từ'):
    return ' '.join(f'{prefix}{index}' for index in range(count))


def editorial_document(queue):
    item = queue['candidates'][0]
    caption_one = '[HÀ NỘI] ' + words(24, 'tin')
    caption_two = '[CẬP NHẬT] ' + words(24, 'tinmới')
    headline_lines = ['Thành phố phê duyệt', 'chính sách hỗ trợ', 'mới trong hôm nay']
    return {
        'schema_version': '1.0.0', 'news_id': item['news_id'],
        'editorial_version': 'v1', 'generated_at': queue['generated_at'],
        'caption_option_1': caption_one, 'caption_option_2': caption_two,
        'recommended_option': 1, 'recommended_caption': caption_one,
        'hashtags': ['#TinNong5s', '#HaNoi', '#ChinhSach', '#HoTro', '#TinMoi'],
        'first_comment': words(82, 'chiTiet') + f" Nguồn tham khảo: Publisher Link bài viết gốc: {item['source_url']} {DISCLOSURE}",
        'source_name': 'Publisher', 'source_url': item['source_url'],
        'headline': ' '.join(headline_lines), 'headline_lines': headline_lines,
        'yellow_keywords': ['chính sách hỗ trợ'], 'image_prompt': 'Giữ nguyên ảnh nguồn, crop trung tâm.',
        'compliance': {'facts_grounded': True, 'sensitive_words_transformed': True,
                       'has_exactly_5_hashtags': True, 'caption_length_ok': True,
                       'comment_length_ok': True},
    }


def test_editorial_schema_and_exactly_five_hashtags(tmp_path, context, observation, article):
    queue, _, directory = make_queue(tmp_path, context, observation, article)
    semantic = decision(queue)
    (directory / 'semantic_decisions.json').write_text(json.dumps(semantic), encoding='utf-8')
    document = editorial_document(queue)
    editorial_dir = directory / 'editorial'
    editorial_dir.mkdir()
    (editorial_dir / (document['news_id'] + '.json')).write_text(json.dumps(document), encoding='utf-8')
    assert load_editorial(context.run_id, root=tmp_path)[2][document['news_id']]['hashtags'][-1] == '#TinMoi'
    invalid = {**document, 'hashtags': document['hashtags'][:4]}
    with pytest.raises(HandoffHold) as error:
        validate_editorial(invalid, queue['candidates'][0], semantic['decisions'][0])
    assert error.value.code == 'HOLD_EDITORIAL_INVALID'


def test_composed_caption_preserves_text_and_has_exact_five_hashtags(tmp_path, context, observation, article):
    queue,_,_=make_queue(tmp_path,context,observation,article)
    document=editorial_document(queue)
    result=compose_facebook_caption(document)
    assert result.startswith(document['recommended_caption']+'\n\n')
    assert result.splitlines()[-1].split()==document['hashtags']
    assert result.count('#')==5
    assert result.removesuffix('\n\n'+' '.join(document['hashtags']))==document['recommended_caption']
    assert DISCLOSURE in document['first_comment']


def test_sensitive_word_configuration_matches_governing_instruction():
    from fb_news_autopilot.editorial import load_sensitive_words
    assert load_sensitive_words()==('đối tượng','nghi phạm','tử vong','chết','thi thể','quyên sinh',
        'tự tử','tai nạn','trọng thương','máu','vết thương','bắt giữ','cướp','giết','sát hại',
        'hiếp','xâm hại','đánh nhau','ma túy','kích dục','vũ khí','súng','dao')


@pytest.mark.parametrize('field', ['caption_option_1','caption_option_2','first_comment','headline'])
def test_sensitive_words_are_checked_in_every_editorial_surface(tmp_path, context, observation, article, field):
    queue,_,_=make_queue(tmp_path,context,observation,article)
    document=editorial_document(queue)
    if field.startswith('caption'):
        document[field]+=' chết'
        if field == 'caption_option_1': document['recommended_caption']=document[field]
    elif field == 'first_comment': document[field]+=' chết'
    else:
        document['headline']='Thành phố xác nhận vụ chết mới hôm nay'
        document['headline_lines']=['Thành phố xác nhận','vụ chết mới','hôm nay']
        document['yellow_keywords']=[]
    with pytest.raises(HandoffHold) as error:
        validate_editorial(document,queue['candidates'][0],decision(queue)['decisions'][0])
    assert error.value.code=='HOLD_SENSITIVE_WORD_UNTRANSFORMED'


def test_sensitive_word_in_source_url_is_excluded_from_content_scan(tmp_path, context, observation, article):
    queue,_,_=make_queue(tmp_path,context,observation,article)
    source_url='https://example.com/tin-tuc/con-dao'
    queue['candidates'][0]['source_url']=source_url
    queue['candidates'][0]['canonical_url']=source_url
    document=editorial_document(queue)
    document['first_comment']='Thông tin về vụ việc. '+words(78, 'chiTiet')+f" Nguồn tham khảo: Publisher Link bài viết gốc: {source_url} {DISCLOSURE}"
    assert validate_editorial(document,queue['candidates'][0],decision(queue)['decisions'][0]) is document


def test_sensitive_word_in_recommended_caption_is_rejected(tmp_path, context, observation, article):
    queue,_,_=make_queue(tmp_path,context,observation,article)
    document=editorial_document(queue)
    document['caption_option_1']+=' chết'
    document['recommended_caption']=document['caption_option_1']
    with pytest.raises(HandoffHold) as error:
        validate_editorial(document,queue['candidates'][0],decision(queue)['decisions'][0])
    assert error.value.code=='HOLD_SENSITIVE_WORD_UNTRANSFORMED'


def test_sensitive_word_in_headline_is_rejected(tmp_path, context, observation, article):
    queue,_,_=make_queue(tmp_path,context,observation,article)
    document=editorial_document(queue)
    document['headline']='Thành phố xác nhận vụ chết mới hôm nay'
    document['headline_lines']=['Thành phố xác nhận','vụ chết mới','hôm nay']
    document['yellow_keywords']=[]
    with pytest.raises(HandoffHold) as error:
        validate_editorial(document,queue['candidates'][0],decision(queue)['decisions'][0])
    assert error.value.code=='HOLD_SENSITIVE_WORD_UNTRANSFORMED'


def test_sensitive_word_in_source_name_is_excluded_from_content_scan(tmp_path, context, observation, article):
    queue,_,_=make_queue(tmp_path,context,observation,article)
    document=editorial_document(queue)
    document['source_name']='Côn Dao Media'
    document['first_comment']=document['first_comment'].replace(
        'Nguồn tham khảo: Publisher', 'Nguồn tham khảo: Côn Dao Media')
    assert validate_editorial(document,queue['candidates'][0],decision(queue)['decisions'][0]) is document


def test_caption_hook_and_emoji_limit(tmp_path, context, observation, article):
    queue,_,_=make_queue(tmp_path,context,observation,article)
    document=editorial_document(queue)
    document['caption_option_2']='Không có hook '+words(24)
    with pytest.raises(HandoffHold) as error:
        validate_editorial(document,queue['candidates'][0],decision(queue)['decisions'][0])
    assert error.value.code=='HOLD_CAPTION_HOOK'
    document=editorial_document(queue)
    document['caption_option_2']='[NÓNG] 🔥🚨 '+words(23)
    with pytest.raises(HandoffHold) as error:
        validate_editorial(document,queue['candidates'][0],decision(queue)['decisions'][0])
    assert error.value.code=='HOLD_CAPTION_EMOJI_LIMIT'


def test_asset_resolver_never_uses_unknown_article_image(tmp_path, context, observation, article):
    queue,_,_=make_queue(tmp_path,context,observation,article)
    candidate={**queue['candidates'][0],'source_image_url':'https://example.com/copyrighted.jpg'}
    config=tmp_path/'images.yaml'; owned=tmp_path/'owned'; owned.mkdir()
    config.write_text(f'owned_library_root: {owned}\nfallbacks: {{}}\n',encoding='utf-8')
    with pytest.raises(HandoffHold) as error:
        resolve_asset(candidate,config_path=config)
    assert error.value.code=='HOLD_IMAGE_RIGHTS'


def test_asset_resolver_priority_and_owned_fallback(tmp_path, context, observation, article):
    queue,_,_=make_queue(tmp_path,context,observation,article); candidate=queue['candidates'][0]
    explicit=tmp_path/'explicit.png'; fallback=tmp_path/'owned'/'default.png'
    fallback.parent.mkdir(); Image.new('RGB',(10,10),'red').save(explicit); Image.new('RGB',(10,10),'blue').save(fallback)
    config=tmp_path/'images.yaml'
    config.write_text(f'owned_library_root: {fallback.parent}\nfallbacks:\n  default:\n    path: default.png\n    rights: OWNED\n',encoding='utf-8')
    assert resolve_asset(candidate,explicit_path=explicit,explicit_rights='LICENSED',config_path=config).source=='explicit'
    result=resolve_asset(candidate,explicit_path=explicit,explicit_rights='UNKNOWN',config_path=config)
    assert result.path==fallback.resolve() and result.rights=='OWNED'


def test_review_never_enters_editorial(tmp_path, context, observation, article):
    queue, _, directory = make_queue(tmp_path, context, observation, article)
    semantic = decision(queue, 'REVIEW', ['REVIEW_HEADLINE_SUPPORT_UNCLEAR'], False)
    (directory / 'semantic_decisions.json').write_text(json.dumps(semantic), encoding='utf-8')
    editorial_dir = directory / 'editorial'
    editorial_dir.mkdir()
    document = editorial_document(queue)
    (editorial_dir / (document['news_id'] + '.json')).write_text(json.dumps(document), encoding='utf-8')
    with pytest.raises(HandoffHold) as error:
        load_editorial(context.run_id, root=tmp_path)
    assert error.value.code == 'HOLD_EDITORIAL_NOT_ALLOWED'


def test_poster_dimensions_and_safe_area(tmp_path, context, observation, article):
    queue, _, _ = make_queue(tmp_path, context, observation, article)
    document = editorial_document(queue)
    source = tmp_path / 'source.png'
    Image.new('RGB', (1600, 900), '#395779').save(source)
    output, metadata = render_poster(source, document, 'PERMITTED', tmp_path / 'poster.png')
    with Image.open(output) as rendered:
        assert rendered.size == (1080, 1350)
    assert metadata['headline_bounds'][0] >= metadata['safe_margin']
    assert validate_poster(output, metadata) is True


def test_unknown_image_rights_holds(tmp_path, context, observation, article):
    queue, _, _ = make_queue(tmp_path, context, observation, article)
    source = tmp_path / 'source.png'
    Image.new('RGB', (100, 100), 'gray').save(source)
    with pytest.raises(ImageRightsHold) as error:
        render_poster(source, editorial_document(queue), 'UNKNOWN', tmp_path / 'poster.png')
    assert error.value.code == 'HOLD_IMAGE_RIGHTS'


def test_rendered_asset_manifest_detects_tampering(tmp_path, context, observation, article):
    queue, _, directory = make_queue(tmp_path, context, observation, article)
    source = tmp_path / 'source.png'
    Image.new('RGB', (1600, 900), '#395779').save(source)
    output, metadata = render_poster(source, editorial_document(queue), 'OWNED',
                                     directory / 'assets' / 'poster.png')
    document, _ = write_asset_manifest(context.run_id, queue['candidates'][0]['news_id'],
                                       source, output, 'OWNED', metadata, root=tmp_path)
    assert load_asset_manifest(context.run_id, document['news_id'], root=tmp_path)[0]['width'] == 1080
    output.write_bytes(b'tampered')
    with pytest.raises(HandoffHold) as error:
        load_asset_manifest(context.run_id, document['news_id'], root=tmp_path)
    assert error.value.code == 'HOLD_ASSET_TAMPERED'
