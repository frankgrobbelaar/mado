"""Windows' desktop: joining the display APIs' view of each monitor with IDesktopWallpaper's, and
the real desktop read (never set: no test changes the owner's wallpaper)."""

import ctypes
import logging
import sys

import pytest

from mado import desktop
from mado.desktop import Display, Listed, Named, NoDesktop, Slideshow, joined

STUDIO = r"\\?\DISPLAY#MADE0001#5&1a2b3c&0&UID4352#{e6f07b5f-ee97-4a90-b076-33f57bf4eaa7}"
SIDE = r"\\?\DISPLAY#MADE0002#5&1a2b3c&0&UID4353#{e6f07b5f-ee97-4a90-b076-33f57bf4eaa7}"


def test_a_monitor_is_found_by_its_device_path_with_its_own_name_scale_and_turn():
    found = joined(
        [Display(r"\\.\DISPLAY1", 0, 0, 2560, 1440, 120, 0, True)],
        [Named(r"\\.\DISPLAY1", "Studio 27", STUDIO.upper())],
        [Listed(STUDIO, 0, 0, 2560, 1440, r"D:\Pictures\Harbour at dusk.jpg")],
    )

    assert len(found) == 1
    monitor = found[0].monitor
    assert (monitor.id, monitor.name, monitor.number) == (STUDIO, "Studio 27", 1)
    assert (monitor.x, monitor.y, monitor.width, monitor.height) == (0, 0, 2560, 1440)
    assert (monitor.scale, monitor.rotation, monitor.main) == (1.25, 0, True)
    assert found[0].wallpaper == r"D:\Pictures\Harbour at dusk.jpg"


def test_a_monitor_displayconfig_doesnt_name_is_found_by_its_rectangle_and_numbered():
    found = joined(
        [
            Display(r"\\.\DISPLAY1", 0, 0, 2560, 1440, 96, 0, True),
            Display(r"\\.\DISPLAY2", 2560, 0, 1080, 1920, 96, 90, False),
        ],
        [],
        [Listed(SIDE, 2560, 0, 1080, 1920, None)],
    )

    monitor = found[0].monitor
    assert (monitor.name, monitor.number, monitor.rotation) == ("Screen 2", 2, 90)
    assert found[0].wallpaper is None


def test_a_monitor_windows_lists_that_isnt_showing_is_left_out():
    found = joined(
        [Display(r"\\.\DISPLAY1", 0, 0, 2560, 1440, 96, 0, True)],
        [Named(r"\\.\DISPLAY1", "Studio 27", STUDIO)],
        [Listed(STUDIO, 0, 0, 2560, 1440, None), Listed(SIDE, 0, 0, 0, 0, None)],
    )

    assert [each.monitor.id for each in found] == [STUDIO]


def test_where_wallpapers_cant_be_set_nothing_is_read_or_set():
    nowhere = NoDesktop()

    assert not nowhere.here
    assert nowhere.monitors() == []
    with pytest.raises(desktop.DesktopError):
        nowhere.set_wallpaper(STUDIO, r"C:\x.png")
    with pytest.raises(desktop.DesktopError):
        nowhere.start_slideshow(Slideshow(r"D:\Slides", 60000, False))


def test_windows_refusing_is_said_in_words_and_its_code_kept_in_the_log(
    caplog: pytest.LogCaptureFixture,
):
    paper = desktop._Paper  # pyright: ignore[reportPrivateUsage]

    with caplog.at_level(logging.WARNING), pytest.raises(desktop.DesktopError) as refused:
        paper.check(-2147024891, "Windows wouldn't set the wallpaper")

    assert str(refused.value) == "Windows wouldn't set the wallpaper."
    assert "0x80070005" in caplog.text


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' own structures")
def test_the_structures_are_the_sizes_windows_expects():
    sizes = {
        desktop._PathInfo: 72,  # pyright: ignore[reportPrivateUsage]
        desktop._ModeInfo: 64,  # pyright: ignore[reportPrivateUsage]
        desktop._SourceName: 84,  # pyright: ignore[reportPrivateUsage]
        desktop._TargetName: 420,  # pyright: ignore[reportPrivateUsage]
        desktop._DevMode: 220,  # pyright: ignore[reportPrivateUsage]
    }
    assert {kind: ctypes.sizeof(kind) for kind in sizes} == sizes


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' own desktop")
def test_the_real_desktop_is_read_and_nothing_on_it_changes():
    try:
        found = desktop.WindowsDesktop().monitors()
    except desktop.DesktopError:
        return  # a PC without a desktop session (a build server) says so, in words
    for each in found:
        assert each.monitor.width > 0
        assert each.monitor.height > 0
        assert each.monitor.id
    assert sum(each.monitor.main for each in found) <= 1
