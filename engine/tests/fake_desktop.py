"""Windows' desktop as the tests have it: made-up monitors, and every wallpaper set written down
rather than set, so no test touches the owner's own."""

from mado.core.wallpaper import Monitor
from mado.desktop import FILL, DesktopError, Seen, Slideshow

STUDIO = Monitor(r"\\?\DISPLAY#MADE0001#5&1a2b&0&UID1", "Studio 27", 1, 0, 0, 160, 90, main=True)
SIDE = Monitor(r"\\?\DISPLAY#MADE0002#5&1a2b&0&UID2", "Side 24", 2, 160, 0, 120, 68)
TALL = Monitor(r"\\?\DISPLAY#MADE0003#5&1a2b&0&UID3", "Panel 24", 3, 160, 10, 68, 120, rotation=90)


class FakeDesktop:
    """A desktop with made-up monitors. `papers` is what each shows (by its id); setting one
    turns Windows' slideshow and spotlight off, as setting a picture does."""

    here = True

    def __init__(
        self,
        monitors: list[Monitor] | None = None,
        papers: dict[str, str | None] | None = None,
        *,
        position: int = FILL,
        slideshow: Slideshow | None = None,
        spotlight: bool = False,
    ) -> None:
        self.shown = list(monitors if monitors is not None else [STUDIO, SIDE])
        self.papers: dict[str, str | None] = dict(papers or {})
        self.position_now = position
        self.slides = slideshow
        self.spot = spotlight
        self.sets: list[tuple[str, str]] = []
        self.positions: list[int] = []
        self.started: list[Slideshow] = []
        self.refuse: str | None = None  # a sentence Windows answers every change with
        self.refuse_on: set[str] = set()  # monitors whose wallpaper Windows won't set
        self.then: list[Monitor] | None = None  # the monitors after `reads` more reads
        self.reads = 0

    def monitors(self) -> list[Seen]:
        if self.then is not None:
            self.reads -= 1
            if self.reads < 0:
                self.shown, self.then = self.then, None
        return [Seen(each, self.papers.get(each.id)) for each in self.shown]

    def set_wallpaper(self, monitor: str, path: str) -> None:
        if self.refuse:
            raise DesktopError(self.refuse)
        if monitor in self.refuse_on:
            raise DesktopError("Windows wouldn't set the wallpaper.")
        self.sets.append((monitor, path))
        self.papers[monitor] = path or None
        self.slides = None
        self.spot = False

    def position(self) -> int | None:
        return self.position_now

    def set_position(self, position: int) -> None:
        if self.refuse:
            raise DesktopError(self.refuse)
        self.positions.append(position)
        self.position_now = position

    def slideshow(self) -> Slideshow | None:
        return self.slides

    def start_slideshow(self, slideshow: Slideshow) -> None:
        if self.refuse:
            raise DesktopError(self.refuse)
        self.started.append(slideshow)
        self.slides = slideshow

    def spotlight(self) -> bool:
        return self.spot
