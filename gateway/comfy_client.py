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
        payload = await self.queue_state()
        return len(payload.get("queue_running", [])) + len(
            payload.get("queue_pending", [])
        )

    async def queue_state(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/queue")
            response.raise_for_status()
            return response.json()

    async def prompt_state(self, prompt_id: str) -> str | None:
        payload = await self.queue_state()
        for state, key in (("running", "queue_running"), ("queued", "queue_pending")):
            for item in payload.get(key, []):
                if isinstance(item, (list, tuple)) and len(item) > 1 and str(item[1]) == prompt_id:
                    return state
                if isinstance(item, dict) and str(item.get("prompt_id") or item.get("id")) == prompt_id:
                    return state
        return None

    async def cancel(self, prompt_id: str) -> str | None:
        state = await self.prompt_state(prompt_id)
        if state is None:
            return None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if state == "queued":
                response = await client.post(f"{self.base_url}/queue", json={"delete": [prompt_id]})
            else:
                response = await client.post(f"{self.base_url}/interrupt")
            response.raise_for_status()
        return state


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


def find_error_message(history: dict[str, Any]) -> str:
    messages = history.get("status", {}).get("messages", [])
    for item in reversed(messages if isinstance(messages, list) else []):
        if not isinstance(item, (list, tuple)) or not item:
            continue
        event = str(item[0])
        payload = item[1] if len(item) > 1 and isinstance(item[1], dict) else {}
        if event in {"execution_error", "execution_interrupted"}:
            return str(
                payload.get("exception_message")
                or payload.get("message")
                or event.replace("_", " ")
            )[:2000]
    return "ComfyUI generation failed"
