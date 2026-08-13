from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from gateway.settings import load_presets
from gateway.workflow_builder import build_workflow


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    args = parser.parse_args()
    with urllib.request.urlopen(f"{args.url.rstrip('/')}/object_info", timeout=30) as response:
        object_info = json.load(response)

    graphs = [
        build_workflow(
            prompt="节点自检",
            duration=duration,
            aspect_ratio=aspect,
            seed=1,
            preset=preset,
            first_frame="self-test.png" if mode != "text" else None,
            last_frame="self-test.png" if mode == "first_last" else None,
        )
        for preset in load_presets().values()
        for duration in (4, 15)
        for aspect in ("9:16", "16:9")
        for mode in ("text", "first", "first_last")
    ]
    graphs.extend([
        build_workflow(
            prompt="<Picture 1> 锁定角色，<Picture 2> 锁定场景",
            duration=8,
            aspect_ratio="9:16",
            seed=1,
            preset=load_presets()["balanced"],
            reference_images=["self-test.png", "self-test.png"],
        ),
        build_workflow(
            prompt="参考视频动作、原声和独立音频",
            duration=8,
            aspect_ratio="16:9",
            seed=1,
            preset=load_presets()["balanced"],
            reference_videos=[("self-test.mp4", True)],
            reference_audios=["self-test.wav"],
        ),
    ])

    errors: list[str] = []
    for graph in graphs:
        for node_id, node in graph.items():
            class_type = node["class_type"]
            schema = object_info.get(class_type)
            if not schema:
                errors.append(f"missing node: {class_type}")
                continue
            allowed = set()
            for group in ("required", "optional", "hidden"):
                allowed.update(schema.get("input", {}).get(group, {}).keys())
            unknown = set(node["inputs"]) - allowed
            dynamic_prefixes = {
                "ref_images.", "ref_videos.", "ref_video_audios.", "ref_audios."
            }
            unknown = {
                name for name in unknown
                if not any(name.startswith(prefix) for prefix in dynamic_prefixes)
            }
            if unknown:
                errors.append(
                    f"node {node_id} {class_type} has unknown inputs: {sorted(unknown)}"
                )
    if errors:
        raise SystemExit("\n".join(sorted(set(errors))))
    print(f"ComfyUI 节点契约通过，共验证 {len(graphs)} 组工作流。")


if __name__ == "__main__":
    main()
