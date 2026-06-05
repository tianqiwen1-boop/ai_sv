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
            sample_method="median",
            refine_intensity=0.25,
            debug=False,
        )

        if width is None or height is None or refined is None:
            raise RuntimeError("Perfect Pixel failed to detect a valid grid")

        refined_array = np.asarray(refined, dtype=np.uint8)
        if self._has_center_cross_seam(refined_array):
            raise RuntimeError("Perfect Pixel produced a suspicious center seam")

        refined_image = Image.fromarray(refined_array, mode="RGB")
        output = io.BytesIO()
        refined_image.save(output, format="PNG")
        return PerfectPixelResult(int(width), int(height), output.getvalue())

    @staticmethod
    def _has_center_cross_seam(image: np.ndarray) -> bool:
        if image.ndim != 3 or image.shape[2] < 3:
            return False

        height, width = image.shape[:2]
        if width < 12 or height < 12:
            return False

        rgb = image[:, :, :3].astype(np.int16)
        near_white = (
            (rgb[:, :, 0] >= 245)
            & (rgb[:, :, 1] >= 245)
            & (rgb[:, :, 2] >= 245)
        )

        row_ratios = near_white.mean(axis=1)
        col_ratios = near_white.mean(axis=0)

        row_band_start = height // 4
        row_band_end = height - row_band_start
        col_band_start = width // 4
        col_band_end = width - col_band_start

        row_index = int(row_band_start + np.argmax(row_ratios[row_band_start:row_band_end]))
        col_index = int(col_band_start + np.argmax(col_ratios[col_band_start:col_band_end]))

        row_ratio = float(row_ratios[row_index])
        col_ratio = float(col_ratios[col_index])
        row_neighbors = [
            float(row_ratios[i])
            for i in (row_index - 1, row_index + 1)
            if 0 <= i < height
        ]
        col_neighbors = [
            float(col_ratios[i])
            for i in (col_index - 1, col_index + 1)
            if 0 <= i < width
        ]

        row_jump = row_ratio - max(row_neighbors or [0.0])
        col_jump = col_ratio - max(col_neighbors or [0.0])

        return row_ratio >= 0.95 and col_ratio >= 0.95 and row_jump >= 0.35 and col_jump >= 0.35
