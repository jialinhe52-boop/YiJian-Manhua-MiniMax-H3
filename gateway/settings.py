from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    comfy_url: str = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")
    comfy_input_dir: Path = Path(
        os.getenv("COMFYUI_INPUT_DIR", "/root/ComfyUI/input")
    )
    comfy_output_dir: Path = Path(
        os.getenv("COMFYUI_OUTPUT_DIR", "/root/ComfyUI/output")
    )
    data_dir: Path = Path(os.getenv("H3_GATEWAY_DATA_DIR", "/root/h3-app/data"))
    request_timeout_seconds: float = float(os.getenv("COMFYUI_TIMEOUT", "60"))
    max_queue_size: int = int(os.getenv("H3_MAX_QUEUE_SIZE", "4"))
    api_key: str = os.getenv("H3_API_KEY", "")


def load_presets(path: Path | None = None) -> dict[str, dict[str, Any]]:
    source = path or ROOT / "config" / "presets.json"
    with source.open("r", encoding="utf-8") as handle:
        return json.load(handle)
