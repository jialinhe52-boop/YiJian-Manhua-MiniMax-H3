from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx


class ComfyClient:
    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def queue(self, workflow: dict[str, Any], client_id: str) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow, "client_id": client_id},
            )
            response.raise_for_status()
            return str(response.json()["prompt_id"])

    async def history(self, prompt_id: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/history/{prompt_id}")
            response.raise_for_status()
            payload = response.json()
        return payload.get(prompt_id)

    async def queue_size(self) -> int:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/queue")
            response.raise_for_status()
            payload = response.json()
        return len(payload.get("queue_running", [])) + len(
            payload.get("queue_pending", [])
        )


def find_output_file(history: dict[str, Any]) -> Path | None:
    candidates: list[Path] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            filename = value.get("filename")
            if isinstance(filename, str) and filename:
                candidates.append(Path(value.get("subfolder", "")) / filename)
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    for node in history.get("outputs", {}).values():
        # Current core SaveVideo exposes files as UI metadata rather than a
        # traditional videos output collection.
        ui = node.get("ui", {})
        for collection in ("videos", "images"):
            for item in ui.get(collection, []):
                filename = item.get("filename")
                if filename:
                    return Path(item.get("subfolder", "")) / filename
        for collection in ("videos", "gifs", "images"):
            for item in node.get(collection, []):
                filename = item.get("filename")
                if filename:
                    subfolder = item.get("subfolder", "")
                    return Path(subfolder) / filename
        collect(node)
    video_extensions = {".mp4", ".webm", ".mov", ".mkv"}
    return next((path for path in candidates if path.suffix.lower() in video_extensions), None)
