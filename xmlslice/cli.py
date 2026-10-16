"""Command line entry for slicing an MP4 with an XML danmaku file."""

from __future__ import annotations

import argparse
from pathlib import Path

from xmlslice.danmaku import extract_timestamps
from xmlslice.density import find_dense_periods
from xmlslice.ffmpeg import slice_video


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xmlslice",
        description="根据 XML 弹幕密度，从 MP4 中切出高能片段。",
    )
    parser.add_argument("-x", "--xml", required=True, help="XML 弹幕文件")
    parser.add_argument("-v", "--video", required=True, help="MP4 视频文件")
    parser.add_argument(
        "-d",
        "--duration",
        type=float,
        default=60,
        help="每段切片时长（秒），默认 60",
    )
    parser.add_argument(
        "-n",
        "--top-n",
        type=int,
        default=1,
        dest="top_n",
        help="切出几段，默认 1",
    )
    parser.add_argument(
        "--overlap",
        type=float,
        default=30,
        help="两段之间允许的最大重叠（秒），默认 30",
    )
    parser.add_argument(
        "--step",
        type=float,
        default=1,
        help="滑动窗口步长（秒），默认 1",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="输出目录，默认与视频放在同一目录",
    )
    return parser


def output_name(video_path: str, start: float, taken: set[str]) -> str:
    stem = Path(video_path).stem
    suffix = Path(video_path).suffix or ".mp4"
    base = f"{int(start)}s_{stem}{suffix}"
    if base not in taken:
        taken.add(base)
        return base
    index = 2
    while True:
        candidate = f"{int(start)}s_{index}_{stem}{suffix}"
        if candidate not in taken:
            taken.add(candidate)
            return candidate
        index += 1


def run(xml_path: str, video_path: str, duration: float, top_n: int, overlap: float, step: float, output_dir: str | None) -> list[str]:
    timestamps = extract_timestamps(xml_path)
    if not timestamps:
        raise ValueError("XML 里没有可用的弹幕时间")

    periods = find_dense_periods(timestamps, duration, top_n, overlap, step)
    if not periods:
        raise ValueError("没有找到可切片的时间段")

    folder = Path(output_dir) if output_dir else Path(video_path).resolve().parent
    folder.mkdir(parents=True, exist_ok=True)
    taken: set[str] = set()
    written: list[str] = []
    print(f"共读取 {len(timestamps)} 条弹幕，准备切 {len(periods)} 段。")
    for start, count in periods:
        name = output_name(video_path, start, taken)
        target = folder / name
        print(f"从 {start:.3f}s 起，{duration:g} 秒，弹幕 {count} 条 -> {target}")
        slice_video(video_path, str(target), start, duration)
        written.append(str(target))
    return written


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run(
            args.xml,
            args.video,
            args.duration,
            args.top_n,
            args.overlap,
            args.step,
            args.output,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"错误: {exc}")
        return 1
    return 0
