from app import hardware


def test_tiering_from_fake_ram_and_vram_values():
    assert hardware.recommend(32, None) == (hardware.TIER_HIGH, "qwen3:14b")
    assert hardware.recommend(0, 12) == (hardware.TIER_HIGH, "qwen3:14b")
    assert hardware.recommend(16, None) == (hardware.TIER_PLUS, "qwen3:8b")
    assert hardware.recommend(0, 6) == (hardware.TIER_PLUS, "qwen3:8b")
    assert hardware.recommend(8, None) == (hardware.TIER_LAPTOP, "qwen3:4b")
    assert hardware.recommend(7.9, 0) == (hardware.TIER_LOW, "qwen3:1.7b")
    assert hardware.recommend(None, None) == (hardware.TIER_LOW, "qwen3:1.7b")


def test_context_budget_is_keyed_to_hardware_tier():
    assert hardware.recommended_num_ctx_for_tier(hardware.TIER_HIGH) == 8192
    assert hardware.recommended_num_ctx_for_tier(hardware.TIER_PLUS) == 4096
    assert hardware.recommended_num_ctx_for_tier(hardware.TIER_LAPTOP) == 4096
    assert hardware.recommended_num_ctx_for_tier(hardware.TIER_LOW) == 2048
    assert hardware.recommended_num_ctx_for_tier("unknown") == 4096


def test_detect_caches_hardware_for_process_lifetime(monkeypatch):
    calls = {"ram": 0, "vram": 0}
    hardware.detect.cache_clear()

    def read_ram():
        calls["ram"] += 1
        return 16.0

    def read_vram():
        calls["vram"] += 1
        return 6.0

    monkeypatch.setattr(hardware, "_read_ram_gb", read_ram)
    monkeypatch.setattr(hardware, "_read_gpu_vram_gb", read_vram)
    try:
        first = hardware.detect()
        second = hardware.detect()
    finally:
        hardware.detect.cache_clear()

    assert first is second
    assert calls == {"ram": 1, "vram": 1}


def test_hardware_endpoint_reports_detected_fields():
    from app.main import api_hardware

    result = api_hardware()
    assert set(result) == {
        "ram_gb", "cpu_count", "gpu_vram_gb", "tier", "recommended_model", "recommended_num_ctx"
    }
    assert result["cpu_count"] >= 1
    assert result["recommended_model"].startswith("qwen3:")
    assert result["recommended_num_ctx"] in {2048, 4096, 8192}
