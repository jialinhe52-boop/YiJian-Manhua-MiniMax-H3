from __future__ import annotations

import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "workflows" / "generated" / "h3_manhua_draft.json"
IMAGE_SOURCE = ROOT / "workflows" / "upstream" / "official_h3_ref2va.json"
RUNNINGHUB_SOURCE = (
    ROOT / "workflows" / "generated" / "RunningHub_MiniMax_H3_Omni_4Step_5s.json"
)
OUT = ROOT / "workflows" / "generated"

PROMPTS = {
    "t2va": """summary:\n保持人物设定和服饰一致的连续短视频。\n\ndetailed_description:\n一名古装少女站在雨后的长街上，听见身后动静后缓慢回头，衣摆和发丝随风摆动；镜头从中景平稳推近到面部近景，动作连续自然，不瞬移，不增加多余人物。\n\noverall_soundscape:\n细雨声、远处风铃声、轻微脚步声与衣料摩擦声，和动作同步。\n\nnon_diegetic_music:\n低音弦乐和稀疏古琴，缓慢推进，结尾自然收束。""",
    "i2va": """summary:\n以首帧人物和场景为锚点生成连续镜头，严格保持首帧身份与构图关系。\n\ndetailed_description:\n从首帧开始，古装少女在雨后的长街上听见身后动静，缓慢回头；镜头从中景平稳推近到面部近景，发丝和衣摆随风轻动，首帧中的人物脸部、服装、年龄和空间关系保持一致。\n\noverall_soundscape:\n细雨、远处风铃和轻微脚步声，声音与回头动作同步。\n\nnon_diegetic_music:\n克制的古琴与低音弦乐，结尾淡出。""",
    "fl2va": """summary:\n以首帧和尾帧共同约束一段连续转场镜头，人物身份与服饰保持一致。\n\ndetailed_description:\n从首帧的雨后长街构图开始，古装少女听见身后动静后缓慢回头，镜头平稳推近；自然过渡到尾帧的面部近景和稳定表情，动作连续，不瞬移，不改变人物身份，不新增人物。\n\noverall_soundscape:\n细雨、风铃、脚步和衣料声连续贯穿，并与可见动作同步。\n\nnon_diegetic_music:\n低音弦乐渐进，尾帧处轻柔收束。""",
    "l2va": """summary:\n以尾帧构图为终点生成连续镜头，运动自然并准确落到尾帧。\n\ndetailed_description:\n古装少女站在雨后的长街上听见身后动静，缓慢回头，镜头从中景推近；动作和空间连续，最后准确停在尾帧的面部近景与稳定表情，保持尾帧人物身份、服饰和光线。\n\noverall_soundscape:\n细雨、远处风铃、脚步声与衣摆声自然同步。\n\nnon_diegetic_music:\n稀疏古琴和低音弦乐，结尾淡出。""",
}


def _node(data: dict, node_id: int) -> dict:
    return next(n for n in data["nodes"] if n["id"] == node_id)


def _image_node(template: dict, node_id: int, title: str, pos: list[float]) -> dict:
    node = copy.deepcopy(template)
    node["id"] = node_id
    node["pos"] = pos
    node["title"] = title
    node["widgets_values"] = ["example.png", "image"]
    node["mode"] = 4
    node["order"] = node_id
    return node


def _link(data: dict, link_id: int, source_id: int, target_id: int, target_name: str) -> None:
    source = _node(data, source_id)
    target = _node(data, target_id)
    slot = next(i for i, item in enumerate(target["inputs"]) if item["name"] == target_name)
    data["links"].append([link_id, source_id, 0, target_id, slot, "IMAGE"])
    source["outputs"][0].setdefault("links", []).append(link_id)
    target["inputs"][slot]["link"] = link_id


def build(mode: str) -> dict:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    runninghub = json.loads(RUNNINGHUB_SOURCE.read_text(encoding="utf-8"))
    rh_lora = copy.deepcopy(
        next(n for n in runninghub["nodes"] if n["type"] == "LoraLoaderModelOnly")
    )
    official_ref = json.loads(IMAGE_SOURCE.read_text(encoding="utf-8"))
    official_sampler = copy.deepcopy(_node(official_ref, 123))

    # RunningHub does not provide the Turbo plugin's convenience loader/sampler.
    # Replace both with equivalent stock nodes that the cloud runtime supports.
    old_lora = _node(data, 134)
    rh_lora.update({
        "id": 134,
        "pos": old_lora["pos"],
        "order": old_lora.get("order", 134),
        "title": "4步极速 LoRA｜RunningHub兼容",
        "widgets_values": [
            "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors",
            1,
        ],
    })
    rh_lora["inputs"][0]["link"] = old_lora["inputs"][0]["link"]
    rh_lora["outputs"][0]["links"] = list(old_lora["outputs"][0]["links"])
    data["nodes"][data["nodes"].index(old_lora)] = rh_lora

    old_sampler = _node(data, 135)
    official_sampler.update({
        "id": 135,
        "pos": old_sampler["pos"],
        "order": old_sampler.get("order", 135),
        "title": "H3 官方采样器｜RunningHub兼容",
        "widgets_values": ["res_multistep"],
    })
    official_sampler["outputs"][0]["links"] = list(old_sampler["outputs"][0]["links"])
    data["nodes"][data["nodes"].index(old_sampler)] = official_sampler
    data["extra"]["creator"] = "一键漫剧"
    data["extra"]["workflow_version"] = "1.1.0"
    data["extra"]["mode"] = mode
    prompt = _node(data, 131)
    prompt["title"] = {
        "t2va": "T2VA 文生视频｜六段导演提示词",
        "i2va": "I2VA 首帧生视频｜六段导演提示词",
        "fl2va": "FL2VA 首尾帧｜六段导演提示词",
        "l2va": "L2VA 尾帧生视频｜六段导演提示词",
    }[mode]
    prompt["widgets_values"][0] = PROMPTS[mode]
    prompt["widgets_values"][1] = 480
    prompt["widgets_values"][2] = 864
    prompt["widgets_values"][3] = 124
    image_template = _node(official_ref, 137)
    next_id = 140
    next_link = max(link[0] for link in data["links"]) + 1
    if mode in {"i2va", "fl2va"}:
        data["nodes"].append(_image_node(image_template, next_id, "首帧图片｜Picture 1", [-640, 40]))
        _link(data, next_link, next_id, 131, "first_frame")
        next_id += 1
        next_link += 1
    if mode in {"l2va", "fl2va"}:
        data["nodes"].append(_image_node(image_template, next_id, "尾帧图片｜Picture 2", [-640, 470]))
        _link(data, next_link, next_id, 131, "last_frame")
        next_id += 1
        next_link += 1
    labels = {
        "t2va": "T2VA 文生视频｜无需上传图片",
        "i2va": "I2VA 首帧生视频｜上传一张首帧",
        "fl2va": "FL2VA 首尾帧｜上传首帧与尾帧",
        "l2va": "L2VA 尾帧生视频｜上传一张尾帧",
    }
    _node(data, 92)["widgets_values"][0] = f"video/YiJianManJu_H3_{mode}"
    data["last_node_id"] = max(data["last_node_id"], next_id - 1)
    data["last_link_id"] = max(data["last_link_id"], next_link - 1)
    data["groups"] = data.get("groups", []) + [{
        "id": 90,
        "title": labels[mode],
        "bounding": [-700, -80, 1050, 720],
        "color": "#2A9D8F",
        "font_size": 24,
        "flags": {},
    }]
    return data


def main() -> None:
    for mode in PROMPTS:
        out = OUT / f"RunningHub_YiJianManJu_H3_{mode}_v1.json"
        out.write_text(json.dumps(build(mode), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{out.name}: ok")


if __name__ == "__main__":
    main()
