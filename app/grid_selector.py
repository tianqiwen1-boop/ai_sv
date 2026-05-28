from __future__ import annotations

from app.models import GenerateMessage

SMALL_CANDIDATES = [24, 28, 32, 36, 40]
DEFAULT_CANDIDATES = [32, 36, 40, 44, 48, 56, 64, 72, 80]


def default_range(size_mode: str | None) -> tuple[int, int]:
    if (size_mode or "").strip().lower() == "small":
        return 24, 40
    return 30, 80


def default_candidates(size_mode: str | None) -> list[int]:
    if (size_mode or "").strip().lower() == "small":
        return SMALL_CANDIDATES.copy()
    return DEFAULT_CANDIDATES.copy()


def resolve_grid_range(message: GenerateMessage) -> tuple[int, int]:
    fallback_min, fallback_max = default_range(message.sizeMode)
    grid_min = int(message.gridMin or fallback_min)
    grid_max = int(message.gridMax or fallback_max)
    if grid_min > grid_max:
        grid_min, grid_max = grid_max, grid_min
    return grid_min, grid_max


def resolve_candidate_grids(message: GenerateMessage) -> list[int]:
    grid_min, grid_max = resolve_grid_range(message)
    raw = message.candidateGrids or default_candidates(message.sizeMode)
    candidates = sorted({int(v) for v in raw if grid_min <= int(v) <= grid_max})
    if candidates:
        return candidates

    fallback = 32 if (message.sizeMode or "").strip().lower() == "small" else 48
    fallback = min(max(fallback, grid_min), grid_max)
    return [fallback]


def choose_final_grid_size(
    message: GenerateMessage,
    detected_width: int | None,
    detected_height: int | None,
) -> int:
    candidates = resolve_candidate_grids(message)
    fallback = 32 if (message.sizeMode or "").strip().lower() == "small" else 48

    if detected_width and detected_height and detected_width > 0 and detected_height > 0:
        detected = (float(detected_width) + float(detected_height)) / 2.0
        return min(candidates, key=lambda value: abs(value - detected))

    if fallback in candidates:
        return fallback

    return min(candidates, key=lambda value: abs(value - fallback))
