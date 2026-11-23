"""Local hardware detection and deterministic Ollama model recommendation."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Iterable

import psutil


@dataclass(frozen=True)
class HardwareInfo:
    ram_gb: float | None
    cpu_cores: int | None
    gpu_name: str | None = None
    gpu_vram_gb: float | None = None


@dataclass(frozen=True)
class ModelRecommendation:
    tier: str
    model: str
    reason: str


def _detect_nvidia_gpus() -> list[tuple[str, float]]:
    """Read NVIDIA GPU name and total VRAM when nvidia-smi is available."""
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    devices: list[tuple[str, float]] = []
    for line in completed.stdout.splitlines():
        name, separator, memory = line.partition(",")
        if not separator:
            continue
        try:
            vram_gb = float(memory.strip()) / 1024.0
        except ValueError:
            continue
        devices.append((name.strip(), vram_gb))
    return devices


def detect_hardware() -> HardwareInfo:
    """Return available RAM, CPU count, and optional NVIDIA GPU information."""
    try:
        ram_gb = float(psutil.virtual_memory().total) / (1024**3)
    except (OSError, AttributeError, TypeError):
        ram_gb = None
    try:
        cpu_cores = psutil.cpu_count(logical=True) or os.cpu_count()
    except (OSError, AttributeError):
        cpu_cores = os.cpu_count()
    try:
        devices = _detect_nvidia_gpus()
    except Exception:
        devices = []
    if devices:
        gpu_name, gpu_vram_gb = max(devices, key=lambda device: device[1])
    else:
        gpu_name, gpu_vram_gb = None, None
    return HardwareInfo(
        ram_gb=ram_gb,
        cpu_cores=int(cpu_cores) if cpu_cores is not None else None,
        gpu_name=gpu_name,
        gpu_vram_gb=gpu_vram_gb,
    )


def recommend_model(info: HardwareInfo | None = None) -> ModelRecommendation:
    """Map the detected resources to the project-defined local model tiers."""
    hardware = info or detect_hardware()
    ram = hardware.ram_gb or 0.0
    vram = hardware.gpu_vram_gb or 0.0
    if vram >= 12 or ram >= 32:
        return ModelRecommendation(
            "high-performance", "qwen3:14b", "VRAM is at least 12 GB or RAM is at least 32 GB."
        )
    if vram >= 6 or ram >= 16:
        return ModelRecommendation(
            "standard-plus", "qwen3:8b", "VRAM is at least 6 GB or RAM is at least 16 GB."
        )
    if ram > 8:
        return ModelRecommendation(
            "standard-laptop", "qwen3:4b", "RAM is greater than 8 GB."
        )
    return ModelRecommendation(
        "low-resource", "qwen3:1.7b", "Available RAM and detected GPU memory are below the larger tiers."
    )
