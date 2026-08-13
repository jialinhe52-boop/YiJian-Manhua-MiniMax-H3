from gateway.prompt_builder import build_prompt
from gateway.settings import load_presets
from gateway.workflow_builder import build_workflow, dimensions, frame_count


PRESETS = load_presets()


def test_exact_requested_duration_is_not_replaced() -> None:
    assert frame_count(4) >= 4 * 24
    assert frame_count(15) >= 15 * 24


def test_invalid_duration_is_rejected() -> None:
    for value in (3, 16):
        try:
            frame_count(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"duration {value} should fail")


def test_portrait_and_landscape_dimensions_are_stable() -> None:
    assert dimensions("9:16", 480) == (480, 864)
    assert dimensions("16:9", 480) == (864, 480)


def test_draft_inserts_turbo_lora_and_one_save_node() -> None:
    workflow = build_workflow(
        prompt="test",
        duration=15,
        aspect_ratio="9:16",
        seed=1,
        preset=PRESETS["draft"],
    )
    assert workflow["7"]["inputs"]["steps"] == 4
    assert workflow["7"]["inputs"]["model"] == ["20", 0]
    assert workflow["20"]["class_type"] == "MiniMaxH3TurboLoRA"
    assert workflow["10"]["inputs"]["sampler"] == ["21", 0]
    assert workflow["11"]["inputs"]["samples"] == ["10", 0]
    assert workflow["12"]["inputs"]["samples"] == ["10", 0]
    assert workflow["5"]["inputs"]["length"] == frame_count(15)
    assert sum(node["class_type"] == "SaveVideo" for node in workflow.values()) == 1
    assert workflow["14"]["inputs"]["codec"] == {"codec": "auto"}


def test_quality_uses_base_model_without_lora() -> None:
    workflow = build_workflow(
        prompt="test",
        duration=5,
        aspect_ratio="16:9",
        seed=1,
        preset=PRESETS["quality"],
    )
    assert "20" not in workflow
    assert "21" not in workflow
    assert workflow["7"]["inputs"]["steps"] == 20


def test_first_and_last_frames_are_wired_independently() -> None:
    workflow = build_workflow(
        prompt="test",
        duration=5,
        aspect_ratio="9:16",
        seed=1,
        preset=PRESETS["balanced"],
        first_frame="first.png",
        last_frame="last.png",
    )
    assert workflow["5"]["inputs"]["first_frame"] == ["30", 0]
    assert workflow["5"]["inputs"]["last_frame"] == ["31", 0]


def test_multi_reference_uses_ref2va_and_official_autogrow_inputs() -> None:
    workflow = build_workflow(
        prompt="<Picture 1> 锁定角色，<Picture 2> 锁定场景",
        duration=8,
        aspect_ratio="9:16",
        seed=1,
        preset=PRESETS["draft"],
        reference_images=["character.png", "scene.png"],
    )
    assert workflow["1"]["inputs"]["unet_name"].startswith("minimax_h3_ref2va")
    assert workflow["5"]["class_type"] == "MiniMaxH3ReferenceToVideo"
    assert workflow["5"]["inputs"]["audio_vae"] == ["4", 0]
    assert workflow["5"]["inputs"]["ref_images.ref_image_0"] == ["30", 0]
    assert workflow["5"]["inputs"]["ref_images.ref_image_1"] == ["31", 0]
    assert workflow["7"]["inputs"]["scheduler"] == "beta"
    assert workflow["7"]["inputs"]["steps"] == 12
    assert "20" not in workflow and "21" not in workflow


def test_omni_reference_wires_video_soundtrack_and_standalone_audio() -> None:
    workflow = build_workflow(
        prompt="参考动作、运镜和音色",
        duration=8,
        aspect_ratio="16:9",
        seed=1,
        preset=PRESETS["balanced"],
        reference_videos=[("motion.mp4", True), ("silent.mp4", False)],
        reference_audios=["voice.wav"],
    )
    assert workflow["30"]["class_type"] == "LoadVideo"
    assert workflow["31"]["class_type"] == "GetVideoComponents"
    assert workflow["5"]["inputs"]["ref_videos.ref_video_0"] == ["31", 0]
    assert workflow["5"]["inputs"]["ref_video_audios.ref_video_audio_0"] == ["31", 1]
    assert "ref_video_audios.ref_video_audio_1" not in workflow["5"]["inputs"]
    assert workflow["34"]["class_type"] == "LoadAudio"
    assert workflow["5"]["inputs"]["ref_audios.ref_audio_0"] == ["34", 0]


def test_reference_limits_are_enforced() -> None:
    try:
        build_workflow(
            prompt="test", duration=5, aspect_ratio="9:16", seed=1,
            preset=PRESETS["balanced"], reference_images=["x.png"] * 10,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("more than 9 reference images should fail")


def test_jimeng_prompt_is_preserved_and_structured() -> None:
    source = "女孩回头，镜头推近"
    result = build_prompt(source, mode="jimeng", duration=8)
    assert source in result
    assert "8 秒" in result
    assert "人物身份" in result
    sections = (
        "integrated_multimodal_description:", "overall_soundscape:",
        "non_diegetic_music:",
    )
    assert all(section in result for section in sections)
    assert [result.index(section) for section in sections] == sorted(result.index(section) for section in sections)
    assert "subject_definitions:" not in result


def test_first_last_prompt_contains_exact_time_anchors() -> None:
    result = build_prompt(
        "女孩从门口走到窗边",
        mode="jimeng",
        duration=15,
        has_first_frame=True,
        has_last_frame=True,
    )
    assert "0.00 秒" in result
    assert "15.00 秒" in result
    assert "首帧状态" in result
    assert "尾帧状态" in result


def test_reference_prompt_has_exact_official_tags() -> None:
    result = build_prompt(
        "两人走入车站", mode="jimeng", duration=8,
        reference_images=["character：林晚", "scene：雨夜车站"],
        reference_videos=[("缓慢推镜", True)],
        reference_audios=["远处风铃"],
    )
    for tag in ("<Picture 1>", "<Picture 2>", "<Video 1>", "<Audio 1>", "<Audio 2>"):
        assert tag in result
    for section in (
        "subject_definitions:", "summary:", "retention_analysis:",
        "detailed_description:", "overall_soundscape:", "non_diegetic_music:",
    ):
        assert section in result
    assert "integrated_multimodal_description:" not in result


def test_explicit_generation_modes_require_matching_inputs() -> None:
    cases = (
        ("t2va", None, None),
        ("i2va", "first.png", None),
        ("fl2va", "first.png", "last.png"),
        ("l2va", None, "last.png"),
    )
    for generation_mode, first_frame, last_frame in cases:
        workflow = build_workflow(
            prompt="test", duration=5, aspect_ratio="9:16", seed=1,
            preset=PRESETS["balanced"], generation_mode=generation_mode,
            first_frame=first_frame, last_frame=last_frame,
        )
        assert workflow["5"]["class_type"] == "MiniMaxH3ImageToVideo"
        assert ("first_frame" in workflow["5"]["inputs"]) == bool(first_frame)
        assert ("last_frame" in workflow["5"]["inputs"]) == bool(last_frame)

    reference_workflow = build_workflow(
        prompt="test", duration=5, aspect_ratio="9:16", seed=1,
        preset=PRESETS["balanced"], generation_mode="ref2va",
        reference_images=["character.png"],
    )
    assert reference_workflow["5"]["class_type"] == "MiniMaxH3ReferenceToVideo"


def test_generation_mode_rejects_wrong_inputs() -> None:
    invalid = (
        ("i2va", None, None, []),
        ("fl2va", "first.png", None, []),
        ("l2va", None, None, []),
        ("ref2va", None, None, []),
        ("t2va", None, None, ["reference.png"]),
    )
    for generation_mode, first_frame, last_frame, references in invalid:
        try:
            build_workflow(
                prompt="test", duration=5, aspect_ratio="9:16", seed=1,
                preset=PRESETS["balanced"], generation_mode=generation_mode,
                first_frame=first_frame, last_frame=last_frame,
                reference_images=references,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"{generation_mode} accepted mismatched inputs")
