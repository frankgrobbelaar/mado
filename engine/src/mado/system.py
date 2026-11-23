"""What the engine asks of Windows: that the programs it starts end with it; where the owner's
Pictures folder is; and how it runs itself again, for work that's safer in a process of its own
(the PC check)."""

import ctypes
import sys
from pathlib import Path

_KILL_ON_JOB_CLOSE = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
_EXTENDED_LIMITS = 9  # JobObjectExtendedLimitInformation


class _BasicLimits(ctypes.Structure):  # JOBOBJECT_BASIC_LIMIT_INFORMATION
    _fields_ = (
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    )


class _ExtendedLimits(ctypes.Structure):  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    _fields_ = (
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", ctypes.c_uint64 * 6),  # IO_COUNTERS
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    )


def end_programs_with_engine() -> bool:
    """Puts the engine in a Windows job that ends every program it starts (ffmpeg, say) when the
    engine ends, however it ends: the app stopping it, a crash, or Task Manager. Nothing then
    writes to a file or holds the graphics card after Mado is gone. True once that's so."""
    if sys.platform != "win32":
        return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = ctypes.c_void_p
    kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
    kernel.SetInformationJobObject.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    )
    kernel.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        return False
    limits = _ExtendedLimits(BasicLimitInformation=_BasicLimits(LimitFlags=_KILL_ON_JOB_CLOSE))
    size = ctypes.sizeof(limits)
    if not kernel.SetInformationJobObject(job, _EXTENDED_LIMITS, ctypes.byref(limits), size) or (
        not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess())
    ):
        kernel.CloseHandle(job)
        return False
    return True  # the job stays open till the engine ends: Windows closes it, ending the rest


class _Guid(ctypes.Structure):
    _fields_ = (
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    )


# FOLDERID_Pictures: {33E28130-4E1E-4676-835A-98395C3BC3BB}
_PICTURES = _Guid(
    0x33E28130, 0x4E1E, 0x4676, (ctypes.c_ubyte * 8)(0x83, 0x5A, 0x98, 0x39, 0x5C, 0x3B, 0xC3, 0xBB)
)


def pictures_folder() -> Path:
    """The owner's Pictures folder, wherever Windows keeps it (moved to another drive, or kept
    by OneDrive); their home's Pictures where Windows doesn't say."""
    if sys.platform == "win32":
        shell = ctypes.WinDLL("shell32")
        ole = ctypes.WinDLL("ole32")
        found = ctypes.c_wchar_p()
        if shell.SHGetKnownFolderPath(ctypes.byref(_PICTURES), 0, None, ctypes.byref(found)) == 0:
            try:
                if found.value:
                    return Path(found.value)
            finally:
                ole.CoTaskMemFree(found)
    return Path.home() / "Pictures"


def own_command() -> list[str]:
    """The command that runs this engine again: its bundled mado-engine.exe, or Python with
    Mado's package, as `mado` from source."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "mado"]
