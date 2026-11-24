# Hardware detection and model recommendation

`GET /api/hardware` reports the process machine's total RAM, logical CPU count,
NVIDIA VRAM when available through `nvidia-smi`, the selected tier, model
recommendation, and context-window recommendation. `GET /api/status` includes
the same hardware object plus the currently configured model. `gpu_status` is
`none detected` when no usable NVIDIA VRAM reading is available. CPU count is
informational; the current tier rule uses RAM and NVIDIA VRAM.

| Tier | Detected condition | Recommended model | Context window |
|---|---|---|---:|
| low-resource | Otherwise (including unknown RAM and no detected NVIDIA VRAM) | `qwen3:1.7b` | 2048 |
| standard-laptop | RAM at least 8 GiB, below 16 GiB, and NVIDIA VRAM below 6 GiB | `qwen3:4b` | 4096 |
| standard-plus | RAM at least 16 GiB or NVIDIA VRAM at least 6 GiB, unless the high-performance rule matches | `qwen3:8b` | 4096 |
| high-performance | RAM at least 32 GiB or NVIDIA VRAM at least 12 GiB | `qwen3:14b` | 8192 |

The detector applies the tiers from highest to lowest. The **standard laptop
configuration** is the standard-laptop row; the **high-performance
configuration** is the high-performance row. The recommendations are
configuration guidance, not measured performance claims. GPU detection uses
`nvidia-smi`; other GPU vendors are not detected by this implementation.

Set `DEFAULT_MODEL` to override the recommendation. Without that setting, the
local Ollama client selects the recommended model. The `/api/status` response
shows the effective model, Ollama state, latest inference settings, and frozen
signal/reply prompt hashes.
