"""Vietnamese-safe font selection and deterministic headline fitting."""
from pathlib import Path

from PIL import ImageFont


def load_font(name, size):
    candidates = [name, '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
                  '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf']
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(Path(candidate).expanduser()), size)
        except OSError:
            continue
    raise OSError('No Vietnamese-capable TrueType font is available')


def fit_headline(draw, lines, box, font_name, start_size, min_size, spacing):
    width = box[2] - box[0]
    height = box[3] - box[1]
    for size in range(start_size, min_size - 1, -2):
        font = load_font(font_name, size)
        bounds = [draw.textbbox((0, 0), line, font=font) for line in lines]
        line_heights = [bottom - top for left, top, right, bottom in bounds]
        if max((right - left for left, top, right, bottom in bounds), default=0) <= width and sum(line_heights) + spacing * (len(lines) - 1) <= height:
            return font, line_heights
    raise ValueError('Headline does not fit the configured safe area')
