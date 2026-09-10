"""Poster geometry and crop helpers."""
from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class PosterLayout:
    width: int
    height: int
    image_height: int
    safe_margin: int

    @property
    def text_box(self):
        return (self.safe_margin, self.image_height + self.safe_margin,
                self.width - self.safe_margin, self.height - self.safe_margin)


def cover_crop(image, size):
    """Resize without stretching, then center-crop to size."""
    target_width, target_height = size
    scale = max(target_width / image.width, target_height / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - target_width) // 2
    top = (resized.height - target_height) // 2
    return resized.crop((left, top, left + target_width, top + target_height))
