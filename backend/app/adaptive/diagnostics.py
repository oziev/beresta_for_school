"""FR-12: initial level formula from ТЗ."""
from __future__ import annotations


def calculate_initial_level(
    correct: int,
    total: int,
    avg_time: float,
    max_time: float = 60.0,
) -> int:
    """Return level 1–3.

    score = (correct/total)*0.7 + (1 - avg_time/max_time)*0.3
    Note: faster answers → higher score, so we invert time ratio.
    """
    if total == 0:
        return 1
    time_ratio = min(avg_time / max(max_time, 1), 1.0)
    # быстрый правильный ответ → выше уровень
    score = (correct / total) * 0.7 + (1.0 - time_ratio) * 0.3
    if score < 0.4:
        return 1
    if score < 0.7:
        return 2
    return 3
