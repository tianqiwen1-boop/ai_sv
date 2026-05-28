from __future__ import annotations

import io

import numpy as np
from PIL import Image


class PerfectPixelResult:
    def __init__(self, width: int, height: int, png_bytes: bytes) -> None:
        self.width = width
        self.height = height
        self.png_bytes = png_bytes


class PerfectPixelProcessor:
    def refine(self, image_bytes: bytes) -> PerfectPixelResult:
        from perfect_pixel import get_perfect_pixel

        with Image.open(io.BytesIO(image_bytes)) as image:
            rgb = np.array(image.convert("RGB"))

        width, height, refined = get_perfect_pixel(
            rgb,
            sample_method="center",
            refine_intensity=0.25,
            debug=False,
        )

        if width is None or height is None or refined is None:
            raise RuntimeError("Perfect Pixel failed to detect a valid grid")

        refined_image = Image.fromarray(np.asarray(refined, dtype=np.uint8), mode="RGB")
        output = io.BytesIO()
        refined_image.save(output, format="PNG")
        return PerfectPixelResult(int(width), int(height), output.getvalue())
