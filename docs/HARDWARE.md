# Hardware detection and model recommendation

`GET /api/hardware` reports total system RAM, logical CPU count, NVIDIA VRAM
when available through `nvidia-smi`, the selected tier, model recommendation,
and context-window recommendation. `GET /api/status` includes the same
hardware object plus the currently configured model. CPU count is informational;
the current tier rule uses RAM and NVIDIA VRAM. Only NVIDIA GPUs are detected
by this implementation.

## Tier selection rule

The detector checks the highest tier first. A tier threshold is met if **either**
the RAM condition or the detected NVIDIA VRAM condition is met; when no usable
VRAM reading is available, the RAM conditions still apply. Unknown RAM and VRAM
are treated as zero for selection.

| Tier | Selection condition after higher tiers are excluded | Recommended model | Context window |
|---|---|---|---:|
| high-performance | RAM at least 32 GiB **or** NVIDIA VRAM at least 12 GiB | `qwen3:14b` | 8192 |
| standard-plus | RAM at least 16 GiB **or** NVIDIA VRAM at least 6 GiB | `qwen3:8b` | 4096 |
| standard-laptop | RAM at least 8 GiB | `qwen3:4b` | 4096 |
| low-resource | Otherwise, including unknown RAM with no qualifying GPU | `qwen3:1.7b` | 2048 |

Therefore, the **standard-laptop tier** covers machines with at least 8 GiB RAM
that do not meet the standard-plus or high-performance rules. The
**high-performance tier** is selected at 32 GiB RAM or 12 GiB NVIDIA VRAM,
including when only one of those thresholds is met. The implementation is in
`app/hardware.py` (`recommend`). Set `DEFAULT_MODEL` to override the recommended
model. Recommendations are configuration guidance, not measured speed, quality,
or memory-fit claims. The selected model must already be available in Ollama.
The hardware tier is not a model-fit guarantee; inspect the exact pulled model
artifact and its licence before use (`docs/MODELS_AND_LICENCES.md`; unconfirmed
items are `VERIFY`). No physical-hardware benchmark is implied by the
selection tests.

This hardware tier is separate from prospect **Size Fit**. Hardware selection
uses local RAM/NVIDIA VRAM; Size Fit compares imported employee count with ICP
size bounds and cannot infer either value from the hardware profile.

## Decision-rule tests

`tests/test_hardware.py` contains deterministic tests using supplied RAM/VRAM
values; they exercise the selection rule, not physical hardware detection or
model performance:

- `test_standard_laptop_tier_recommendation` checks the standard-laptop
  recommendation and its 4096-token context window.
- `test_high_performance_tier_recommendation` checks both the RAM and NVIDIA
  VRAM routes to the high-performance recommendation and its 8192-token context
  window.

The broader tier-boundary tests also cover the standard-plus and low-resource
fallbacks. `gpu_status` is `none detected` when no usable NVIDIA VRAM reading is
available. The `/api/status` response shows the effective model, Ollama state,
latest inference settings, and frozen signal/reply prompt hashes.
