"""Read danmaku timestamps from recorder XML."""

import xml.etree.ElementTree as ET
from pathlib import Path


def extract_timestamps(xml_path: str) -> list[float]:
    """Return each <d> comment's offset in seconds from the start of the video.

    Recorder XML (DanmakuFactory / 弹幕姬) stores that offset as the first field
    of the p attribute, for example p="12.345,1,25,...".
    """
    path = Path(xml_path)
    if not path.is_file():
        raise FileNotFoundError(f"找不到弹幕文件: {xml_path}")
    if path.suffix.lower() != ".xml":
        raise ValueError(f"弹幕文件需要是 .xml: {xml_path}")

    timestamps: list[float] = []
    try:
        for _event, elem in ET.iterparse(path, events=("end",)):
            if elem.tag != "d":
                elem.clear()
                continue
            raw = elem.get("p")
            elem.clear()
            if not raw:
                continue
            head = raw.split(",", 1)[0].strip()
            try:
                timestamps.append(float(head))
            except ValueError:
                continue
    except ET.ParseError as exc:
        raise ValueError(f"无法解析 XML: {xml_path}") from exc

    return timestamps
