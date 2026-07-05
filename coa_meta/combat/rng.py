from __future__ import annotations

import random


class SeededRng:
    def __init__(self, seed: int = 1):
        self._random = random.Random(seed)

    def chance(self, probability: float) -> bool:
        return self._random.random() < probability

    def uniform(self, minimum: float, maximum: float) -> float:
        return self._random.uniform(minimum, maximum)
