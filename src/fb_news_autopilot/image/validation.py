"""Mechanical validation for generated social assets."""
from pathlib import Path

from PIL import Image


def validate_poster(path, metadata=None):
    path = Path(path)
    with Image.open(path) as image:
        if image.size != (1080, 1350):
            raise ValueError('Poster must be exactly 1080x1350')
        if image.format not in {'PNG', 'JPEG'}:
            raise ValueError('Poster must be PNG or JPEG')
    if metadata:
        margin = metadata['safe_margin']
        left, top, right, bottom = metadata['headline_bounds']
        if left < margin or right > 1080 - margin or bottom > 1350 - margin:
            raise ValueError('Poster text exceeds the safe area')
        if top < metadata['image_height']:
            raise ValueError('Poster headline overlaps the source image area')
    return True
