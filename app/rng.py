from typing import Callable, Sequence, TypeVar

MASK = 0xFFFFFFFF
T = TypeVar("T")


def _imul(a: int, b: int) -> int:
    return (a * b) & MASK


def mulberry32(seed: int) -> Callable[[], float]:
    """A small 32-bit generator: the same seed always replays the same stream."""
    state = seed & MASK

    def draw() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & MASK
        t = state
        t = _imul(t ^ (t >> 15), t | 1)
        t = (t ^ (t + _imul(t ^ (t >> 7), t | 61))) & MASK
        return ((t ^ (t >> 14)) & MASK) / 4294967296


    return draw


class Rng:
    def __init__(self, seed: int) -> None:
        self._draw = mulberry32(seed)

    def float(self) -> float:
        return self._draw()

    def int(self, low: int, high: int) -> int:
        return low + int(self._draw() * (high - low + 1))

    def pick(self, items: Sequence[T]) -> T:
        return items[int(self._draw() * len(items))]

    def chance(self, p: float) -> bool:
        return self._draw() < p

    def hex(self, length: int) -> str:
        out = ""
        while len(out) < length:
            out += format(int(self._draw() * 16), "x")
        return out
