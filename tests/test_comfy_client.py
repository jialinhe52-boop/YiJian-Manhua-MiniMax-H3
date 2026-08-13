from pathlib import Path

from gateway.comfy_client import find_output_file


def test_find_output_file_supports_core_save_video() -> None:
    history = {
        "outputs": {
            "14": {
                "videos": [
                    {"filename": "result.mp4", "subfolder": "h3_manhua"}
                ]
            }
        }
    }
    assert find_output_file(history) == Path("h3_manhua") / "result.mp4"


def test_find_output_file_supports_new_save_video_ui_metadata() -> None:
    history = {
        "outputs": {
            "14": {
                "ui": {
                    "videos": [
                        {"filename": "new.mp4", "subfolder": "h3_manhua"}
                    ]
                }
            }
        }
    }
    assert find_output_file(history) == Path("h3_manhua") / "new.mp4"


def test_find_output_file_supports_nested_history_metadata() -> None:
    history = {
        "outputs": {
            "14": {
                "result": {
                    "preview": {"filename": "thumb.png"},
                    "saved": {"filename": "clip.mp4", "subfolder": "video"},
                }
            }
        }
    }
    assert find_output_file(history) == Path("video") / "clip.mp4"
