"""The little of pyclipper that Mado uses, typed: the package ships no type information."""

from collections.abc import Sequence

JT_ROUND: int
ET_CLOSEDPOLYGON: int

class PyclipperOffset:
    def __init__(self) -> None: ...
    def AddPath(  # noqa: N802 - pyclipper's own name
        self, path: Sequence[Sequence[float]], join_type: int, end_type: int
    ) -> None: ...
    def Execute(self, delta: float) -> list[list[list[int]]]: ...  # noqa: N802
