"""State machine for per-student adaptive level tracking (FR-13)."""
from __future__ import annotations


class AdaptiveEngine:
    MIN_LEVEL = 1
    MAX_LEVEL = 3

    def process_answer(
        self,
        level: int,
        correct: bool,
        time_spent: float,
        time_limit: float,
    ) -> int:
        """Return new level after one answer."""
        if correct and time_spent <= time_limit:
            return min(level + 1, self.MAX_LEVEL)
        if not correct:
            return max(level - 1, self.MIN_LEVEL)
        # correct but slow → keep level
        return level

    def should_show_hint(self, wrong_streak: int) -> bool:
        return wrong_streak >= 2

    def pick_next_task(
        self,
        tasks: list[dict],
        current_level: int,
        answered_indices: set[int],
    ) -> int | None:
        """Return index of next task matching level, else nearest, else None."""
        candidates = [
            i for i, t in enumerate(tasks)
            if i not in answered_indices and t.get("adaptive_level") == current_level
        ]
        if candidates:
            return candidates[0]
        # fallback: any unanswered
        fallback = [i for i in range(len(tasks)) if i not in answered_indices]
        return fallback[0] if fallback else None
