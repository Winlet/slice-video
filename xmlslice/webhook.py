"""Receive recorder webhooks and slice the closed video."""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from xmlslice.cli import run

HOST = "127.0.0.1"
PORT = 18010
BILILIVE_PORT = 18010
PATH = "/webhook/custom"
RECORDER_PATH = "/webhook/bililiverecorder"
PATHS = {PATH, RECORDER_PATH}
FORWARD_URL = f"http://{HOST}:{BILILIVE_PORT}{PATH}"
EVENTS = {"FileClosed", "FileOpening", "FileError"}
REQUIRED_TEXT = ("event", "filePath", "time", "title", "username")

SliceJob = Callable[[str, str], None]
ForwardJob = Callable[[bytes], None]


class WebhookError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def parse_event(payload: object, record_dir: str | None = None) -> tuple[str, str] | None:
    """Return (video, xml) when a closed file should be sliced.

    Accepts the biliLive-tools custom webhook, 录播姬 Webhook v2,
    and a wrapped event ``{id, version, time, type, data}``.
    Other events are acknowledged without slicing.
    """
    if not isinstance(payload, dict):
        raise WebhookError(400, "请求体必须是 JSON 对象")
    if _is_wrapped(payload):
        return _parse_wrapped(payload, record_dir)
    if "EventType" in payload:
        return _parse_recorder_event(payload, record_dir)
    missing = [name for name in REQUIRED_TEXT if name not in payload]
    if "roomId" not in payload:
        missing.append("roomId")
    if missing:
        raise WebhookError(400, f"缺少参数: {', '.join(missing)}")

    event = payload["event"]
    if event not in EVENTS:
        raise WebhookError(400, f"event 必须是 {', '.join(sorted(EVENTS))}")
    for name in ("filePath", "time", "title", "username"):
        value = payload[name]
        if not isinstance(value, str) or not value.strip() or "{{" in value:
            raise WebhookError(400, f"{name} 必须是非空字符串")
    _check_room_id(payload["roomId"])
    if event != "FileClosed":
        return None

    return _video_and_xml(payload["filePath"].strip(), payload.get("danmuPath"))


def _is_wrapped(payload: dict) -> bool:
    return (
        "event" not in payload
        and "EventType" not in payload
        and isinstance(payload.get("type"), str)
        and "data" in payload
    )


def _parse_wrapped(payload: dict, record_dir: str | None) -> tuple[str, str] | None:
    event_type = payload["type"]
    data = payload["data"]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise WebhookError(400, "data 不是 JSON") from exc
    if not isinstance(data, dict):
        raise WebhookError(400, "data 必须是对象")
    fields = ", ".join(data.keys()) or "无"
    print(f"[webhook] 事件 {event_type}，data 字段: {fields}", flush=True)
    if "EventType" in data:
        return _parse_recorder_event(data, record_dir)

    event_name = data.get("event") if isinstance(data.get("event"), str) else event_type
    video = data.get("filePath") if isinstance(data.get("filePath"), str) else None
    if not video:
        video = _find_video(data)
    if not _is_closed(event_name):
        return None
    if not video or not video.strip():
        raise WebhookError(400, f"事件 {event_type} 没有视频路径；data 字段: {fields}")
    path = Path(video.strip())
    if not path.is_absolute():
        if not record_dir:
            raise WebhookError(400, f"相对路径需要设置 --record-dir: {video.strip()}")
        path = Path(record_dir) / video.strip()
    return _video_and_xml(str(path), data.get("danmuPath"))


def _is_closed(event_type: str) -> bool:
    name = event_type.lower()
    if any(word in name for word in ("open", "create", "start", "error", "launch", "exit", "cancel")):
        return False
    return any(word in name for word in ("close", "finish", "complet", "end", "ready"))


def _find_video(data: dict) -> str | None:
    for key in ("filePath", "output", "path", "RelativePath", "videoFile"):
        value = data.get(key)
        if isinstance(value, str) and value.strip() and not value.strip().startswith(("http://", "https://")):
            return value
    for value in data.values():
        if isinstance(value, dict):
            found = _find_video(value)
            if found:
                return found
    return None


def _video_and_xml(video: str, danmu: object) -> tuple[str, str]:
    if isinstance(danmu, str) and danmu.strip():
        return video, danmu.strip()
    return video, str(Path(video).with_suffix(".xml"))


def _parse_recorder_event(payload: dict, record_dir: str | None) -> tuple[str, str] | None:
    if payload.get("EventType") != "FileClosed":
        return None
    data = payload.get("EventData")
    if not isinstance(data, dict):
        raise WebhookError(400, "FileClosed 缺少 EventData")
    relative = data.get("RelativePath")
    if not isinstance(relative, str) or not relative.strip():
        raise WebhookError(400, "FileClosed 缺少 RelativePath")
    path = Path(relative)
    if not path.is_absolute():
        if not record_dir:
            raise WebhookError(400, "相对路径需要设置 --record-dir")
        path = Path(record_dir) / relative
    return str(path), str(path.with_suffix(".xml"))


def _check_room_id(room_id: object) -> None:
    if isinstance(room_id, bool) or not isinstance(room_id, (int, float)):
        if isinstance(room_id, str) and room_id.strip().isdigit():
            return
        raise WebhookError(400, "roomId 必须是数字")


def forward_webhook(raw: bytes, url: str = FORWARD_URL) -> None:
    request = urllib.request.Request(
        url,
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            print(f"[webhook] 已转发给 biliLive-tools: {response.status}", flush=True)
    except urllib.error.URLError as exc:
        print(f"[webhook] 转发给 biliLive-tools 失败: {exc.reason}", flush=True)


def make_handler(
    slice_job: SliceJob,
    forward: ForwardJob | None = None,
    record_dir: str | None = None,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] not in PATHS:
                self._send(404, {"ok": False, "error": "未找到接口"})
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b""
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else None
                job = parse_event(payload, record_dir)
            except WebhookError as exc:
                keys = ", ".join(payload.keys()) if isinstance(payload, dict) else "非对象"
                print(f"[webhook] 拒绝请求: {exc}；收到的字段: {keys}", flush=True)
                self._send(exc.status, {"ok": False, "error": str(exc)})
                return
            except json.JSONDecodeError:
                print("[webhook] 拒绝请求: 无法解析 JSON", flush=True)
                self._send(400, {"ok": False, "error": "无法解析 JSON"})
                return
            if forward is not None and raw:
                threading.Thread(target=forward, args=(raw,), daemon=True).start()
            if job is not None:
                video, xml_path = job
                threading.Thread(
                    target=_run_job,
                    args=(slice_job, video, xml_path),
                    daemon=True,
                ).start()
            self._send(200, {"ok": True})

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"[webhook] {self.address_string()} {fmt % args}")

        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def _run_job(slice_job: SliceJob, video: str, xml_path: str) -> None:
    print(f"[webhook] 开始切片: {video}")
    try:
        slice_job(video, xml_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[webhook] 切片失败: {exc}")


def _port_holder(port: int) -> str | None:
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    for line in result.stdout.splitlines()[1:]:
        name = line.split(None, 1)[0]
        if name:
            return name
    return None


def serve(
    slice_job: SliceJob,
    host: str = HOST,
    port: int = PORT,
    forward: ForwardJob | None = None,
    record_dir: str | None = None,
) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(slice_job, forward, record_dir))
    print(f"自定义 Webhook 已监听 http://{host}:{port}{PATH}", flush=True)
    if record_dir:
        print(f"录播目录: {record_dir}", flush=True)
    print("若 biliLive-tools 也在使用 18010，请先退出它，或给本程序换 --port", flush=True)
    if forward is not None:
        print(f"收到的 Webhook 会转发给 {FORWARD_URL}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nwebhook 已停止")
    finally:
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xmlslice-webhook",
        description="监听录播 webhook，文件关闭后自动切片。",
    )
    parser.add_argument("--host", default=HOST, help=f"监听地址，默认 {HOST}")
    parser.add_argument("--port", type=int, default=PORT, help=f"监听端口，默认 {PORT}")
    parser.add_argument("--record-dir", default=None, help="录播姬工作目录，用来把 RelativePath 拼成绝对路径")
    parser.add_argument("--forward", action="store_true", help="额外把请求转发给 biliLive-tools 的 18010")
    parser.add_argument("-d", "--duration", type=float, default=60, help="普通模式每段时长（秒），默认 60")
    parser.add_argument("-n", "--top-n", type=int, default=1, dest="top_n", help="自动模式未设置 -m 时切几段，默认 1")
    parser.add_argument("-m", "--min-count", type=int, default=None, dest="min_count", help="至少多少条弹幕才切片")
    parser.add_argument("--auto", action=argparse.BooleanOptionalAction, default=True, help="按弹幕密度自动决定时长，默认开启")
    parser.add_argument("--overlap", type=float, default=30, help="普通模式允许的最大重叠（秒），默认 30")
    parser.add_argument("--step", type=float, default=1, help="普通模式滑动步长（秒），默认 1")
    parser.add_argument("-o", "--output", default=None, help="输出目录，默认与视频同一目录")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    def slice_job(video: str, xml_path: str) -> None:
        run(
            xml_path,
            video,
            args.duration,
            args.top_n,
            args.overlap,
            args.step,
            args.output,
            args.min_count,
            args.auto,
        )

    forward = forward_webhook if args.forward else None
    try:
        serve(slice_job, args.host, args.port, forward, args.record_dir)
    except OSError as exc:
        holder = _port_holder(args.port)
        if holder:
            print(f"错误: {args.host}:{args.port} 已被 {holder} 占用", flush=True)
        else:
            print(f"错误: 无法监听 {args.host}:{args.port}: {exc}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
