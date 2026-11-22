"""What the engine asks of Windows: that the programs it starts end with it."""

import ctypes
import sys

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
