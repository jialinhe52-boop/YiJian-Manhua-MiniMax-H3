from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_SOURCE = ROOT / "workflows" / "upstream" / "official_h3_ref2va.json"
RUNNINGHUB_SCHEMA_SOURCE = (
    ROOT / "workflows" / "generated" / "RunningHub_MiniMax_H3_Omni_4Step_5s.json"
)
OUTPUT = (
    ROOT / "workflows" / "generated" / "RunningHub_YiJianManJu_H3_Director_Studio_v1.json"
)


DEFAULT_PROMPT = """subject_definitions:
<Subject 1> 是由 <Picture 1> 定义的主角，严格保持脸型、发型、服装、年龄感、身材比例和身份。
<Subject 2> 是由 <Picture 2> 定义的配角，严格保持脸型、发型、服装、年龄感、身材比例和身份。
<Subject 3> 是由 <Picture 4> 和 <Picture 5> 定义的主场景，保持空间结构、光线方向和地标位置。
<Subject 4> 是由 <Picture 7> 和 <Picture 8> 定义的关键物品或服装细节，保持形状、材质、颜色和位置。
<Picture 3> 用作角色或构图参考，<Picture 6> 用作氛围或构图参考，<Picture 9> 用作视觉风格参考。
<Video 1>、<Video 2> 和 <Video 3> 是可选动作与运镜参考，只在镜头正文明确点名时使用。
<Audio 1>、<Audio 2> 和 <Audio 3> 是三条参考视频的同步音轨；<Audio 4>、<Audio 5> 和 <Audio 6> 是独立人物音色或声音参考，只复制指定声音特征，不复制原台词。

summary:
[reference generation] 生成一条连续的中文漫剧视听片段，使用已定义的人物、场景、物品、动作和音频参考；所有标签必须与实际上传顺序一致。

retention_analysis:
<Subject 1>: fully_preserved - 保持主角身份、脸部、发型、服装和身材比例。
<Subject 2>: fully_preserved - 保持配角身份和服装细节。
<Subject 3>: fully_preserved - 保持场景结构、光线和空间地标。
<Subject 4>: fully_preserved - 保持关键物品的形状、材质、颜色和位置。
<Picture 1>、<Picture 2>: fully_preserved - 用于保持人物一致性。
<Picture 4>、<Picture 5>、<Picture 6>: fully_preserved - 用于保持场景和构图一致。
<Picture 7>、<Picture 8>、<Picture 9>: attribute_transfer - 只转移指定物品或风格属性，不增加无关物体。
<Video 1>、<Video 2>、<Video 3>: weak_reference - 只借用点名的动作、摄影机路径或节奏。
<Audio 1> 至 <Audio 6>: reference - 只使用点名的音色、环境声、音效、节奏或连续性职责；人物音色不得串到其他人物。

detailed_description:
[Shot 1] 中远景，<Subject 1> 站在由 <Subject 3> 定义的雨后街道左侧中景，穿着 <Picture 1> 中的服装与配饰；<Subject 4> 保持在既定位置。镜头以小幅度、慢速向前推进，人物望向远处并对身后脚步声作出反应。保持人物身份、左右站位、视线、空间轴线和参考外观连续。
[Shot 2] At 00:02.000, 切到中近景。<Subject 1> 自然转向画面右侧，发丝和衣角被微风轻推；<Subject 2> 从右侧后景接近但不遮挡主角。只在此处参考 <Video 1> 指定的动作或运镜节奏。镜头停在人物稳定反应上，禁止瞬移、左右互换或增加无关人物。

overall_soundscape:
持续雨声、远处风铃、轻微脚步和衣料摩擦声与画面动作同步。正文没有明确对白或画外音时，不新增任何人声。

non_diegetic_music:
N/A"""


GUIDE = """# 一键漫剧 H3 导演台 v1

面向漫剧教学与批量分镜的全能参考工作流。

1. 在下方启用并上传至少一个参考素材。
2. 参考图按角色、场景、物品/画风分区，提示词中使用对应 `<Picture n>`。
3. 参考视频使用 `<Video n>`；视频原声与独立音频依次使用 `<Audio n>`。
4. 时长可填写 5-15 秒，工作流按 24fps 自动换算 H3 合法帧数，不擅自改成 6 秒。
5. 默认启用 4 步极速档；切换 8 步档时同步把 Scheduler 的 steps 改为 8。
6. 每次运行只输出一条带同步音频的 MP4。

即梦式自然语言可以直接改写到 `detailed_description`；完整提示词必须保留上面的六段顺序和参考标签绑定。"""


ORIGINALITY = """# 原创与上游说明

本工作流原创部分：
- 面向漫剧的角色 / 场景 / 物品语义分区；
- 9 图、3 视频、3 视频原声、3 独立音频的教学式控制面；
- 5-15 秒真实时长换算与单结果输出约束；
- 4 步极速 / 8 步均衡双档路由；
- 即梦自然语言到 H3 Ref2VA 六段式导演提示词的编写框架；
- 学员使用顺序、节点命名、画布布局与中文说明。

上游组件：MiniMax H3 模型及算法、ComfyUI H3 节点和官方 Ref2VA 示例、LightX2V 加速 LoRA、Video Helper Suite。模型与节点不声明原创，发布时必须保留对应署名与许可。"""


def _find_node(workflow: dict[str, Any], node_id: int) -> dict[str, Any]:
    return next(node for node in workflow["nodes"] if node["id"] == node_id)


def _clone(
    exemplar: dict[str, Any],
    *,
    node_id: int,
    pos: tuple[float, float],
    title: str | None = None,
    widgets: Any = None,
    size: tuple[float, float] | None = None,
    mode: int = 0,
) -> dict[str, Any]:
    node = copy.deepcopy(exemplar)
    node["id"] = node_id
    node["pos"] = list(pos)
    node["mode"] = mode
    node["order"] = node_id
    node["flags"] = {}
    if title is None:
        node.pop("title", None)
    else:
        node["title"] = title
    if widgets is not None:
        node["widgets_values"] = widgets
    if size is not None:
        node["size"] = list(size)
    for item in node.get("inputs", []):
        item["link"] = None
    for item in node.get("outputs", []):
        item["links"] = []
    return node


def _group(
    group_id: int,
    title: str,
    x: float,
    y: float,
    width: float,
    height: float,
    color: str,
) -> dict[str, Any]:
    return {
        "id": group_id,
        "title": title,
        "bounding": [x, y, width, height],
        "color": color,
        "font_size": 24,
        "flags": {},
    }


class Workflow:
    def __init__(self) -> None:
        self.nodes: list[dict[str, Any]] = []
        self.links: list[list[Any]] = []
        self.groups: list[dict[str, Any]] = []
        self._links_by_id: dict[int, list[Any]] = {}
        self._next_link_id = 1

    def add(self, node: dict[str, Any]) -> dict[str, Any]:
        self.nodes.append(node)
        return node

    def link(
        self,
        source_id: int,
        source_slot: int,
        target_id: int,
        target_name: str,
        link_type: str,
    ) -> int:
        source = next(node for node in self.nodes if node["id"] == source_id)
        target = next(node for node in self.nodes if node["id"] == target_id)
        target_slot = next(
            index for index, item in enumerate(target["inputs"]) if item["name"] == target_name
        )
        link_id = self._next_link_id
        self._next_link_id += 1
        link = [link_id, source_id, source_slot, target_id, target_slot, link_type]
        self.links.append(link)
        self._links_by_id[link_id] = link
        source["outputs"][source_slot].setdefault("links", []).append(link_id)
        target["inputs"][target_slot]["link"] = link_id
        return link_id

    def document(self) -> dict[str, Any]:
        return {
            "last_node_id": max(node["id"] for node in self.nodes),
            "last_link_id": self._next_link_id - 1,
            "nodes": sorted(self.nodes, key=lambda node: node["id"]),
            "links": self.links,
            "groups": self.groups,
            "config": {},
            "extra": {
                "ds": {"scale": 0.72, "offset": [2160, 560]},
                "frontendVersion": "1.47.11",
                "VHS_latentpreview": False,
                "VHS_latentpreviewrate": 0,
                "VHS_MetadataImage": True,
                "VHS_KeepIntermediate": True,
                "creator": "一键漫剧",
                "workflow_version": "1.0.0",
                "upstream": "MiniMax H3 + ComfyUI official Ref2VA",
            },
            "version": 0.4,
        }


def _reference_inputs(template: dict[str, Any]) -> list[dict[str, Any]]:
    by_name = {item["name"]: copy.deepcopy(item) for item in template["inputs"]}
    inputs: list[dict[str, Any]] = []

    def append(name: str, input_type: str, *, shape: int | None = None) -> None:
        item = copy.deepcopy(by_name.get(name, {"name": name, "type": input_type}))
        item["name"] = name
        item["type"] = input_type
        item["link"] = None
        item["localized_name"] = item.get("localized_name", name.split(".")[-1])
        item["label"] = item.get("label", name)
        if shape is not None:
            item["shape"] = shape
        inputs.append(item)

    append("clip", "CLIP")
    append("vae", "VAE")
    append("audio_vae", "VAE")
    for index in range(9):
        append(f"ref_images.ref_image_{index}", "IMAGE", shape=7)
    for index in range(3):
        append(f"ref_videos.ref_video_{index}", "IMAGE", shape=7)
    for index in range(3):
        append(f"ref_video_audios.ref_video_audio_{index}", "AUDIO", shape=7)
    for index in range(3):
        append(f"ref_audios.ref_audio_{index}", "AUDIO", shape=7)
    for name, input_type in (
        ("prompt", "STRING"),
        ("width", "INT"),
        ("height", "INT"),
        ("length", "INT"),
        ("ref_image_size", "COMBO"),
    ):
        append(name, input_type)
    return inputs


def build() -> dict[str, Any]:
    official = json.loads(OFFICIAL_SOURCE.read_text(encoding="utf-8"))
    rh_schema = json.loads(RUNNINGHUB_SCHEMA_SOURCE.read_text(encoding="utf-8"))
    official_nodes = {node["id"]: node for node in official["nodes"]}
    rh_by_type: dict[str, dict[str, Any]] = {}
    for node in rh_schema["nodes"]:
        rh_by_type.setdefault(node["type"], node)

    workflow = Workflow()

    # Guide and provenance notes.
    workflow.add(
        _clone(
            official_nodes[116], node_id=1, pos=(-3180, -780), title="使用顺序",
            widgets=[GUIDE], size=(660, 700)
        )
    )
    workflow.add(
        _clone(
            official_nodes[117], node_id=2, pos=(-2490, -780), title="原创与上游署名",
            widgets=[ORIGINALITY], size=(650, 700)
        )
    )

    # User controls.
    workflow.add(
        _clone(
            official_nodes[115], node_id=10, pos=(-1780, -690),
            title="画面比例与清晰度", widgets=["9:16 (Portrait Widescreen)", 0.6, 32],
            size=(330, 180)
        )
    )
    workflow.add(
        _clone(
            rh_by_type["PrimitiveFloat"], node_id=11, pos=(-1780, -460),
            title="成片时长（5-15秒）", widgets=[5], size=(330, 80)
        )
    )
    workflow.add(
        _clone(
            official_nodes[131], node_id=12, pos=(-1780, -330),
            title="时长转 H3 合法帧数",
            widgets=["max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17"],
            size=(330, 140)
        )
    )
    workflow.add(
        _clone(
            official_nodes[129], node_id=13, pos=(-1780, -140),
            title="随机种子｜可复现", widgets=[20260813, "randomize"], size=(330, 95)
        )
    )
    workflow.add(
        _clone(
            official_nodes[138], node_id=14, pos=(-1390, -690),
            title="H3 导演提示词｜支持即梦自然语言", widgets=[DEFAULT_PROMPT],
            size=(960, 650)
        )
    )

    # Image reference nodes: all are bypassed until the student uploads their own assets.
    image_titles = [
        "Picture 1｜主角", "Picture 2｜配角", "Picture 3｜角色补充",
        "Picture 4｜主场景", "Picture 5｜副场景", "Picture 6｜氛围/构图",
        "Picture 7｜关键物品", "Picture 8｜服装/道具", "Picture 9｜画风参考",
    ]
    image_ids: list[int] = []
    for index, title in enumerate(image_titles):
        node_id = 20 + index
        image_ids.append(node_id)
        column = index % 3
        row = index // 3
        x = -3180 + column * 350
        y = 100 + row * 450
        workflow.add(
            _clone(
                rh_by_type["LoadImage"], node_id=node_id, pos=(x, y), title=title,
                widgets=["example.png", "image"], size=(310, 360), mode=4
            )
        )

    # Three reference videos, including their embedded soundtracks.
    video_ids: list[int] = []
    for index in range(3):
        node_id = 30 + index
        video_ids.append(node_id)
        video_widgets = copy.deepcopy(rh_by_type["VHS_LoadVideo"]["widgets_values"])
        video_widgets["video"] = "example.mp4"
        if isinstance(video_widgets.get("videopreview"), dict):
            video_widgets["videopreview"]["params"]["filename"] = "example.mp4"
        workflow.add(
            _clone(
                rh_by_type["VHS_LoadVideo"], node_id=node_id,
                pos=(-2050 + index * 590, 100),
                title=f"Video {index + 1}｜动作/运镜参考（含原声）",
                widgets=video_widgets, size=(540, 780), mode=4
            )
        )

    # Three independent audio references.
    audio_ids: list[int] = []
    for index in range(3):
        node_id = 33 + index
        audio_ids.append(node_id)
        workflow.add(
            _clone(
                rh_by_type["LoadAudio"], node_id=node_id,
                pos=(-2050 + index * 430, 950),
                title=f"Audio {index + 1}｜独立声音参考",
                widgets=["example.mp3", None, None], size=(390, 170), mode=4
            )
        )

    # Model stack and speed presets.
    workflow.add(
        _clone(
            official_nodes[127], node_id=40, pos=(220, -690), title="H3 Ref2VA 主模型",
            widgets=["minimax_h3_ref2va_pruned_int8_convrot.safetensors", "default"],
            size=(630, 100)
        )
    )
    workflow.add(
        _clone(
            rh_by_type["MiniMaxH3MemoryEfficientSageAttentionPatch"],
            node_id=41, pos=(220, -540), title="显存优化", size=(630, 55)
        )
    )
    workflow.add(
        _clone(
            rh_by_type["LoraLoaderModelOnly"], node_id=42, pos=(220, -430),
            title="8步均衡档｜默认旁路",
            widgets=["minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", 1],
            size=(630, 95), mode=4
        )
    )
    workflow.add(
        _clone(
            rh_by_type["LoraLoaderModelOnly"], node_id=43, pos=(220, -280),
            title="4步极速档｜默认启用",
            widgets=["minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors", 1],
            size=(630, 95)
        )
    )
    workflow.add(
        _clone(
            official_nodes[128], node_id=44, pos=(220, -120), title="H3 文本编码器",
            widgets=["qwen3vl_32b_minimax_h3_int8_convrot.safetensors", "minimax", "default"],
            size=(630, 125)
        )
    )
    workflow.add(
        _clone(
            official_nodes[119], node_id=45, pos=(220, 70), title="视频 VAE",
            widgets=["minimax_h3_video_vae_fp16.safetensors"], size=(630, 75)
        )
    )
    workflow.add(
        _clone(
            official_nodes[120], node_id=46, pos=(220, 195), title="音频 VAE",
            widgets=["minimax_h3_audio_vae_fp32.safetensors"], size=(630, 75)
        )
    )

    # H3 conditioning and sampler.
    reference = _clone(
        official_nodes[136], node_id=50, pos=(920, -690), title="H3 全能参考编码",
        widgets=["", 608, 1088, 124, "match"], size=(520, 800)
    )
    reference["inputs"] = _reference_inputs(official_nodes[136])
    workflow.add(reference)
    workflow.add(
        _clone(official_nodes[126], node_id=51, pos=(1510, -690), title="条件引导", size=(390, 70))
    )
    workflow.add(
        _clone(
            official_nodes[124], node_id=52, pos=(1510, -560), title="采样步数｜极速4 / 均衡8",
            widgets=["simple", 4, 1], size=(390, 145)
        )
    )
    workflow.add(
        _clone(official_nodes[123], node_id=53, pos=(1510, -360), title="H3 采样器", widgets=["res_multistep"], size=(390, 75))
    )
    workflow.add(
        _clone(official_nodes[125], node_id=54, pos=(1960, -560), title="联合声画采样", size=(300, 165))
    )

    # Decode and output.
    workflow.add(
        _clone(official_nodes[122], node_id=60, pos=(2340, -640), title="视频解码", size=(280, 70))
    )
    workflow.add(
        _clone(official_nodes[121], node_id=61, pos=(2340, -500), title="音频解码", size=(280, 70))
    )
    workflow.add(
        _clone(official_nodes[130], node_id=62, pos=(2690, -570), title="24fps 声画合流", widgets=[24, 8], size=(320, 120))
    )
    workflow.add(
        _clone(
            official_nodes[92], node_id=63, pos=(3070, -690), title="一键漫剧｜成片预览与下载",
            widgets=["video/YiJianManJu_H3", "auto", "auto"], size=(700, 980)
        )
    )

    # User control links.
    workflow.link(11, 0, 12, "values.a", "FLOAT")

    # Reference links. Bypassed loaders act as disconnected optional inputs.
    for index, node_id in enumerate(image_ids):
        workflow.link(node_id, 0, 50, f"ref_images.ref_image_{index}", "IMAGE")
    for index, node_id in enumerate(video_ids):
        workflow.link(node_id, 0, 50, f"ref_videos.ref_video_{index}", "IMAGE")
        workflow.link(node_id, 2, 50, f"ref_video_audios.ref_video_audio_{index}", "AUDIO")
    for index, node_id in enumerate(audio_ids):
        workflow.link(node_id, 0, 50, f"ref_audios.ref_audio_{index}", "AUDIO")

    # Model and H3 inputs.
    workflow.link(40, 0, 41, "model", "MODEL")
    workflow.link(41, 0, 42, "model", "MODEL")
    workflow.link(42, 0, 43, "model", "MODEL")
    workflow.link(43, 0, 51, "model", "MODEL")
    workflow.link(43, 0, 52, "model", "MODEL")
    workflow.link(44, 0, 50, "clip", "CLIP")
    workflow.link(45, 0, 50, "vae", "VAE")
    workflow.link(46, 0, 50, "audio_vae", "VAE")
    workflow.link(14, 0, 50, "prompt", "STRING")
    workflow.link(10, 0, 50, "width", "INT")
    workflow.link(10, 1, 50, "height", "INT")
    workflow.link(12, 1, 50, "length", "INT")

    # Sampling and decode links.
    workflow.link(50, 0, 51, "conditioning", "CONDITIONING")
    workflow.link(13, 0, 54, "noise", "NOISE")
    workflow.link(51, 0, 54, "guider", "GUIDER")
    workflow.link(53, 0, 54, "sampler", "SAMPLER")
    workflow.link(52, 0, 54, "sigmas", "SIGMAS")
    workflow.link(50, 1, 54, "latent_image", "LATENT")
    workflow.link(54, 0, 60, "samples", "LATENT")
    workflow.link(54, 0, 61, "samples", "LATENT")
    workflow.link(45, 0, 60, "vae", "VAE")
    workflow.link(46, 0, 61, "vae", "VAE")
    workflow.link(60, 0, 62, "images", "IMAGE")
    workflow.link(61, 0, 62, "audio", "AUDIO")
    workflow.link(62, 0, 63, "video", "VIDEO")

    workflow.groups.extend(
        [
            _group(1, "① 使用说明与原创信息", -3220, -830, 1420, 810, "#355C7D"),
            _group(2, "② 基础控制｜比例·清晰度·5-15秒·种子", -1820, -830, 420, 850, "#2A9D8F"),
            _group(3, "③ H3 导演提示词｜即梦自然语言兼容", -1410, -830, 1020, 850, "#E9C46A"),
            _group(4, "④ 角色参考｜Picture 1-3", -3220, 40, 1040, 470, "#D1495B"),
            _group(5, "⑤ 场景参考｜Picture 4-6", -3220, 490, 1040, 470, "#5B8E7D"),
            _group(6, "⑥ 物品/画风参考｜Picture 7-9", -3220, 940, 1040, 470, "#B56576"),
            _group(7, "⑦ 动作与运镜参考｜Video 1-3（可带原声）", -2090, 40, 1750, 880, "#457B9D"),
            _group(8, "⑧ 独立声音参考｜Audio 1-3", -2090, 910, 1360, 250, "#F4A261"),
            _group(9, "⑨ 速度档位与模型｜4步极速 / 8步均衡", 180, -830, 710, 1140, "#6D597A"),
            _group(10, "⑩ H3 推理核心｜学员无需修改", 900, -830, 1410, 980, "#264653"),
            _group(11, "⑪ 24fps 原生声画成片", 2310, -830, 1500, 1160, "#287271"),
        ]
    )
    return workflow.document()


def main() -> None:
    workflow = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {OUTPUT.name}: {len(workflow['nodes'])} nodes, {len(workflow['links'])} links")


if __name__ == "__main__":
    main()
