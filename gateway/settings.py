from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
    create_requests_per_minute: int = int(os.getenv("H3_CREATE_REQUESTS_PER_MINUTE", "12"))
    job_ttl_hours: int = int(os.getenv("H3_JOB_TTL_HOURS", "72"))
    cleanup_interval_seconds: int = int(os.getenv("H3_CLEANUP_INTERVAL_SECONDS", "3600"))
    startup_wait_seconds: int = int(os.getenv("H3_STARTUP_WAIT_SECONDS", "180"))
    low_vram: bool = env_bool("H3_LOW_VRAM", False)


def load_presets(path: Path | None = None) -> dict[str, dict[str, Any]]:
    source = path or ROOT / "config" / "presets.json"
    with source.open("r", encoding="utf-8") as handle:
        return json.load(handle)
