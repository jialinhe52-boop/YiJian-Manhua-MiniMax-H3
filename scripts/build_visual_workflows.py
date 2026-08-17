from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

if str(ROOT := Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gateway.settings import load_presets
from gateway.workflow_builder import build_workflow

UPSTREAM = ROOT / "workflows" / "upstream"
OUTPUT = ROOT / "workflows" / "generated"

PROMPT = """镜头：一名古装少女站在雨后的长街上，听见身后动静后缓慢回头，衣摆和发丝随风摆动，镜头从中景平稳推近到面部近景。

动作连续自然，不瞬移，不改变人物身份，不增加多余人物。

声音：细雨声、远处风铃声、轻微脚步声，无旁白，无字幕。"""


def node(workflow: dict, node_id: int) -> dict:
    return next(item for item in workflow["nodes"] if item["id"] == node_id)


def subgraph_node(workflow: dict, node_type: str) -> dict:
    return next(
        item
        for subgraph in workflow["definitions"]["subgraphs"]
        for item in subgraph["nodes"]
        if item["type"] == node_type
    )


def build_turbo(*, name: str, steps: int, megapixels: float) -> None:
    source = json.loads((UPSTREAM / "turbo_h3_example.json").read_text(encoding="utf-8"))
    workflow = copy.deepcopy(source)
    node(workflow, 115)["widgets_values"] = ["9:16 (Portrait Widescreen)", megapixels, 32]
    node(workflow, 124)["widgets_values"] = ["simple", steps, 1]
    node(workflow, 127)["widgets_values"] = [
        "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "default",
    ]
    node(workflow, 128)["widgets_values"] = [
        "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "minimax",
        "default",
    ]
    node(workflow, 131)["widgets_values"] = [PROMPT, 480, 864, 124]
    node(workflow, 133)["widgets_values"] = 5
    node(workflow, 134)["widgets_values"] = [
        "minimax_h3_turbo_v4_step600_ema.safetensors",
        1,
        False,
    ]
    node(workflow, 92)["widgets_values"] = [f"video/H3_Manhua_{name}", "auto", "auto"]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / f"h3_manhua_{name}.json").write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def build_quality() -> None:
    source = json.loads((UPSTREAM / "official_h3_fl2va.json").read_text(encoding="utf-8"))
    workflow = copy.deepcopy(source)
    node(workflow, 115)["widgets_values"] = ["9:16 (Portrait Widescreen)", 0.9, 32]
    subgraph = node(workflow, 105)
    values = list(subgraph["widgets_values"])
    values[0] = PROMPT
    values[1] = 736
    values[2] = 1280
    values[3] = 5
    subgraph["widgets_values"] = values
    subgraph_node(workflow, "BasicScheduler")["widgets_values"] = ["simple", 12, 1]
    node(workflow, 92)["widgets_values"] = ["video/H3_Manhua_quality", "auto", "auto"]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "h3_manhua_quality.json").write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def build_reference_examples() -> None:
    preset = load_presets()["balanced"]
    examples = {
        "h3_manhua_multi_reference_api.json": build_workflow(
            prompt=(
                "<Picture 1> 锁定女主角五官与服饰，<Picture 2> 锁定男主角，"
                "<Picture 3> 锁定雨夜车站场景。两人隔着雨幕对视，镜头缓慢推近。"
            ),
            duration=8,
            aspect_ratio="9:16",
            seed=1,
            preset=preset,
            reference_images=["character_a.png", "character_b.png", "rain_station.png"],
        ),
        "h3_manhua_omni_reference_api.json": build_workflow(
            prompt=(
                "<Picture 1> 锁定人物身份，复用 <Video 1> 的动作与运镜，"
                "沿用 <Audio 1> 的视频原声音色，并使用 <Audio 2> 的环境氛围。"
            ),
            duration=8,
            aspect_ratio="9:16",
            seed=1,
            preset=preset,
            reference_images=["character.png"],
            reference_videos=[("motion.mp4", True)],
            reference_audios=["ambience.wav"],
        ),
    }
    for filename, graph in examples.items():
        (OUTPUT / filename).write_text(
            json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def main() -> None:
    build_turbo(name="draft", steps=4, megapixels=0.4)
    build_turbo(name="balanced", steps=8, megapixels=0.6)
    build_quality()
    build_reference_examples()
    print("已生成三档首尾帧、多参和全能参考工作流。")


if __name__ == "__main__":
    main()
