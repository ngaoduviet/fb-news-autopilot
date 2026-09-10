"""Pillow renderer that crops source imagery and never alters depicted content."""
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw
import yaml

from .layout import PosterLayout, cover_crop
from .typography import fit_headline, load_font
from .validation import validate_poster


ALLOWED_RIGHTS = {'OWNED', 'LICENSED', 'PERMITTED'}


class ImageRightsHold(ValueError):
    code = 'HOLD_IMAGE_RIGHTS'


def _config(path):
    with Path(path).open(encoding='utf-8') as stream:
        return yaml.safe_load(stream)


def _gradient(image, top, bottom, start):
    draw = ImageDraw.Draw(image)
    first = ImageColor.getrgb(top)
    second = ImageColor.getrgb(bottom)
    span = image.height - start
    for offset in range(span):
        ratio = offset / max(1, span - 1)
        color = tuple(round(a + (b - a) * ratio) for a, b in zip(first, second))
        draw.line((0, start + offset, image.width, start + offset), fill=color)


def _draw_headline_line(draw, position, line, font, normal_color, highlight_color, keywords):
    matches = []
    folded = line.casefold()
    for keyword in keywords:
        start = folded.find(keyword.casefold())
        if start >= 0:
            matches.append((start, start + len(keyword), keyword))
    matches.sort()
    cursor = 0
    x, y = position
    for start, end, _ in matches:
        if start < cursor:
            continue
        normal = line[cursor:start]
        draw.text((x, y), normal, font=font, fill=normal_color)
        x += draw.textlength(normal, font=font)
        highlighted = line[start:end]
        draw.text((x, y), highlighted, font=font, fill=highlight_color)
        x += draw.textlength(highlighted, font=font)
        cursor = end
    remainder = line[cursor:]
    draw.text((x, y), remainder, font=font, fill=normal_color)
    return x + draw.textlength(remainder, font=font)


def render_poster(source_path, editorial, image_rights_status, output_path, *, config_path='config/tin_nong_5s_poster.yaml'):
    if image_rights_status not in ALLOWED_RIGHTS:
        raise ImageRightsHold('Source image rights are not confirmed')
    config = _config(config_path)
    canvas = config['canvas']
    layout = PosterLayout(canvas['width'], canvas['height'], round(canvas['height'] * canvas['image_ratio']), canvas['safe_margin'])
    source = Image.open(source_path).convert('RGB')
    output = Image.new('RGB', (layout.width, layout.height))
    output.paste(cover_crop(source, (layout.width, layout.image_height)), (0, 0))
    _gradient(output, config['colors']['gradient_top'], config['colors']['gradient_bottom'], layout.image_height)
    draw = ImageDraw.Draw(output)
    draw.rectangle((0, layout.image_height, layout.width, layout.image_height + 8), fill=config['colors']['separator'])
    ribbon_font = load_font(config['typography']['font_bold'], config['typography']['ribbon_size'])
    ribbon_text = config['brand']['ribbon_text']
    ribbon_box = draw.textbbox((0, 0), ribbon_text, font=ribbon_font)
    ribbon_width = ribbon_box[2] - ribbon_box[0] + 42
    ribbon_top = layout.image_height + 24
    draw.rounded_rectangle((layout.safe_margin, ribbon_top, layout.safe_margin + ribbon_width, ribbon_top + 58), radius=8, fill=config['colors']['ribbon'])
    draw.text((layout.safe_margin + 21, ribbon_top + 7), ribbon_text, font=ribbon_font, fill='white')
    headline_top = ribbon_top + 84
    text_box = (layout.safe_margin, headline_top, layout.width - layout.safe_margin, layout.height - layout.safe_margin)
    lines = editorial['headline_lines']
    font, heights = fit_headline(draw, lines, text_box, config['typography']['font_bold'],
                                 config['typography']['headline_size'], config['typography']['headline_min_size'],
                                 config['typography']['line_spacing'])
    y = headline_top
    right = layout.safe_margin
    for line, height in zip(lines, heights):
        line_right = _draw_headline_line(draw, (layout.safe_margin, y), line, font,
                                         config['colors']['headline'], config['colors']['highlight'],
                                         editorial['yellow_keywords'])
        right = max(right, line_right)
        y += height + config['typography']['line_spacing']
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.save(output_path, format='PNG', optimize=True)
    metadata = {'safe_margin': layout.safe_margin, 'image_height': layout.image_height,
                'headline_bounds': [layout.safe_margin, headline_top, right, y - config['typography']['line_spacing']]}
    validate_poster(output_path, metadata)
    return output_path, metadata
