"""Command line entry for slicing an MP4 with an XML danmaku file."""

from __future__ import annotations

import argparse
from pathlib import Path

from xmlslice.danmaku import extract_timestamps
from xmlslice.density import UNIT_SECONDS, find_auto_periods, find_dense_periods, find_ranked_auto_periods
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
        help="切出几段。普通模式，以及自动模式未设置 -m 时，按密度取前几段，默认 1",
    )
    parser.add_argument(
        "-m",
        "--min-count",
        type=int,
        default=None,
        dest="min_count",
        help=f"至少多少条弹幕才切片。普通模式按 -d 秒计算；自动模式按每 {UNIT_SECONDS:g} 秒计算。不填时普通模式为 1，自动模式按密度自动选择",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help=f"自动切片，按每 {UNIT_SECONDS:g} 秒统计弹幕。设置 -m 时达到该数量才收录；不设置 -m 时按每秒弹幕数选出 -n 段",
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


def run(
    xml_path: str,
    video_path: str,
    duration: float,
    top_n: int,
    overlap: float,
    step: float,
    output_dir: str | None,
    min_count: int | None = None,
    auto: bool = False,
) -> list[str]:
    timestamps = extract_timestamps(xml_path)
    if not timestamps:
        raise ValueError("XML 里没有可用的弹幕时间")

    ranked = auto and min_count is None
    if ranked:
        spans = find_ranked_auto_periods(timestamps, top_n)
        periods = [(start, end - start, count) for start, end, count in spans]
    elif auto:
        spans = find_auto_periods(timestamps, min_count)
        periods = [(start, end - start, count) for start, end, count in spans]
    else:
        periods = [
            (start, duration, count)
            for start, count in find_dense_periods(
                timestamps, duration, top_n, overlap, step, 1 if min_count is None else min_count
            )
        ]
    if not periods:
        raise ValueError("没有找到可切片的时间段")

    folder = Path(output_dir) if output_dir else Path(video_path).resolve().parent
    folder.mkdir(parents=True, exist_ok=True)
    taken: set[str] = set()
    written: list[str] = []
    print(f"共读取 {len(timestamps)} 条弹幕，准备切 {len(periods)} 段。")
    for start, length, count in periods:
        name = output_name(video_path, start, taken)
        target = folder / name
        if ranked:
            rate = count / length if length else 0
            detail = f"弹幕 {count} 条，每秒 {rate:.2f} 条"
        else:
            detail = f"弹幕 {count} 条"
        print(f"从 {start:.3f}s 起，{length:g} 秒，{detail} -> {target}")
        slice_video(video_path, str(target), start, length)
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
            args.min_count,
            args.auto,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"错误: {exc}")
        return 1
    return 0
