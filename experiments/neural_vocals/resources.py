"""Windows process memory accounting without changing GPU/system settings."""

import ctypes
import os


def cpu_memory() -> dict[str, int] | None:
    if os.name != "nt":
        return None
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("page_faults", wintypes.DWORD),
                    ("peak_working_set", ctypes.c_size_t), ("working_set", ctypes.c_size_t),
                    ("peak_paged_pool", ctypes.c_size_t), ("paged_pool", ctypes.c_size_t),
                    ("peak_nonpaged_pool", ctypes.c_size_t), ("nonpaged_pool", ctypes.c_size_t),
                    ("pagefile", ctypes.c_size_t), ("peak_pagefile", ctypes.c_size_t),
                    ("private_usage", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    values = Counters()
    values.cb = ctypes.sizeof(values)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(values), values.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {"working_set_bytes": values.working_set, "peak_working_set_bytes": values.peak_working_set,
            "private_committed_bytes": values.private_usage, "peak_pagefile_bytes": values.peak_pagefile}
