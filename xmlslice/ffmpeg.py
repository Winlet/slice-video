"""Cut a video segment with ffmpeg stream copy."""

import shutil
import subprocess
from pathlib import Path


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("未找到 ffmpeg，请先安装后再切片")
    return path


def slice_video(video_path: str, output_path: str, start: float, duration: float) -> None:
    source = Path(video_path)
    if not source.is_file():
        raise FileNotFoundError(f"找不到视频文件: {video_path}")

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        require_ffmpeg(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(source),
        "-t",
        f"{duration:.3f}",
        "-c",
        "copy",
        "-reset_timestamps",
        "1",
        str(target),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"ffmpeg 切片失败: {detail}") from exc
