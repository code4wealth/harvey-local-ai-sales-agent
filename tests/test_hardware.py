from app import hardware


def test_tiering_from_fake_ram_and_vram_values():
    assert hardware.recommend(32, None) == (hardware.TIER_HIGH, "qwen3:14b")
    assert hardware.recommend(0, 12) == (hardware.TIER_HIGH, "qwen3:14b")
    assert hardware.recommend(16, None) == (hardware.TIER_PLUS, "qwen3:8b")
    assert hardware.recommend(0, 6) == (hardware.TIER_PLUS, "qwen3:8b")
    assert hardware.recommend(8, None) == (hardware.TIER_LAPTOP, "qwen3:4b")
    assert hardware.recommend(7.9, 0) == (hardware.TIER_LOW, "qwen3:1.7b")
    assert hardware.recommend(None, None) == (hardware.TIER_LOW, "qwen3:1.7b")


def test_hardware_endpoint_reports_detected_fields():
    from app.main import api_hardware

    result = api_hardware()
    assert set(result) == {"ram_gb", "cpu_count", "gpu_vram_gb", "tier", "recommended_model"}
    assert result["cpu_count"] >= 1
    assert result["recommended_model"].startswith("qwen3:")
