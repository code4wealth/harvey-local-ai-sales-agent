from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import hardware
from app.hardware import HardwareInfo, detect_hardware, recommend_model


@pytest.mark.parametrize(
    ("info", "tier", "model"),
    [
        (HardwareInfo(ram_gb=32, cpu_cores=8), "high-performance", "qwen3:14b"),
        (HardwareInfo(ram_gb=16, cpu_cores=8), "standard-plus", "qwen3:8b"),
        (HardwareInfo(ram_gb=12, cpu_cores=4), "standard-laptop", "qwen3:4b"),
        (HardwareInfo(ram_gb=8, cpu_cores=2), "low-resource", "qwen3:1.7b"),
        (
            HardwareInfo(ram_gb=8, cpu_cores=8, gpu_name="Sample GPU", gpu_vram_gb=12),
            "high-performance",
            "qwen3:14b",
        ),
        (
            HardwareInfo(ram_gb=8, cpu_cores=8, gpu_name="Sample GPU", gpu_vram_gb=6),
            "standard-plus",
            "qwen3:8b",
        ),
    ],
)
def test_recommend_model_uses_documented_tiers(info, tier, model):
    recommendation = recommend_model(info)
    assert recommendation.tier == tier
    assert recommendation.model == model
    assert recommendation.reason


def test_detect_hardware_reads_ram_cpu_and_optional_gpu(monkeypatch):
    monkeypatch.setattr(
        hardware.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=16 * 1024**3),
    )
    monkeypatch.setattr(hardware.psutil, "cpu_count", lambda logical=True: 12)
    monkeypatch.setattr(
        hardware,
        "_detect_nvidia_gpus",
        lambda: [("Sample GPU", 8.0), ("Larger Sample GPU", 10.0)],
    )

    info = detect_hardware()
    assert info.ram_gb == 16
    assert info.cpu_cores == 12
    assert info.gpu_name == "Larger Sample GPU"
    assert info.gpu_vram_gb == 10.0


def test_detect_hardware_degrades_gracefully_without_gpu(monkeypatch):
    monkeypatch.setattr(
        hardware.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=8 * 1024**3),
    )
    monkeypatch.setattr(hardware.psutil, "cpu_count", lambda logical=True: 4)
    monkeypatch.setattr(hardware, "_detect_nvidia_gpus", lambda: [])

    info = detect_hardware()
    assert info.gpu_name is None
    assert info.gpu_vram_gb is None
    assert info.cpu_cores == 4
