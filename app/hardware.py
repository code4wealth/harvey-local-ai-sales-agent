"""Hardware detection and Qwen3 tier recommendation. Stdlib only.

RAM: /proc/meminfo (Linux), sysctl (macOS), GlobalMemoryStatusEx (Windows).
GPU VRAM: nvidia-smi if present (no vendor SDK required). Unknown VRAM is
reported as None and the tier falls back to RAM.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from functools import lru_cache

TIER_HIGH = "high-performance"
TIER_PLUS = "standard-plus"
TIER_LAPTOP = "standard-laptop"
TIER_LOW = "low-resource"
DEFAULT_NUM_CTX = 4096
NUM_CTX_BY_TIER = {
    TIER_HIGH: 8192,
    TIER_PLUS: 4096,
    TIER_LAPTOP: 4096,
    TIER_LOW: 2048,
}


@dataclass(frozen=True)
class HardwareInfo:
    ram_gb: float | None
    cpu_count: int
    gpu_vram_gb: float | None
    tier: str
    recommended_model: str
    recommended_num_ctx: int

    def as_dict(self) -> dict:
        result = asdict(self)
        result["gpu_status"] = (
            "none detected" if self.gpu_vram_gb is None else "NVIDIA GPU detected"
        )
        return result


def recommend(ram_gb: float | None, vram_gb: float | None) -> tuple[str, str]:
    """Pure tiering rule (PRD §6). Unknown RAM is treated as 0."""
    ram = ram_gb or 0.0
    vram = vram_gb or 0.0
    if vram >= 12 or ram >= 32:
        return TIER_HIGH, "qwen3:14b"
    if vram >= 6 or ram >= 16:
        return TIER_PLUS, "qwen3:8b"
    if ram >= 8:
        return TIER_LAPTOP, "qwen3:4b"
    return TIER_LOW, "qwen3:1.7b"


def recommended_num_ctx_for_tier(tier: str) -> int:
    """Conservative context window for the detected hardware tier."""
    return NUM_CTX_BY_TIER.get(tier, DEFAULT_NUM_CTX)


def _read_ram_gb() -> float | None:
    if os.path.exists("/proc/meminfo"):
        try:
            with open("/proc/meminfo", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemTotal"):
                        match = re.search(r"(\d+)\s*kB", line)
                        return int(match.group(1)) / (1024 * 1024) if match else None
        except OSError:
            pass
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
            return int(out) / (1024**3)
        except Exception:
            return None
    if sys.platform.startswith("win"):
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return status.ullTotalPhys / (1024**3)
        except Exception:
            return None
    return None


def _read_gpu_vram_gb() -> float | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        values = [float(line.strip()) for line in out.stdout.splitlines() if line.strip()]
        return max(values) / 1024 if values else None  # MiB -> GiB
    except Exception:
        return None


@lru_cache(maxsize=1)
def detect() -> HardwareInfo:
    """Detect hardware once per process; the result is stable for this run."""
    ram = _read_ram_gb()
    vram = _read_gpu_vram_gb()
    tier, model = recommend(ram, vram)
    return HardwareInfo(
        ram_gb=round(ram, 1) if ram is not None else None,
        cpu_count=os.cpu_count() or 1,
        gpu_vram_gb=round(vram, 1) if vram is not None else None,
        tier=tier,
        recommended_model=model,
        recommended_num_ctx=recommended_num_ctx_for_tier(tier),
    )
