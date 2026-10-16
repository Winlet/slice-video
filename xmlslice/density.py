"""Find the busiest time windows in a list of danmaku timestamps."""


def find_dense_periods(
    timestamps: list[float],
    duration: float,
    top_n: int,
    max_overlap: float,
    step: float,
) -> list[tuple[float, int]]:
    """Return up to top_n windows as (start_seconds, danmaku_count).

    Windows are [start, start + duration). Candidates move forward by `step`
    seconds. A later window is kept only when its overlap with every already
    chosen window is no greater than max_overlap.
    """
    if duration <= 0:
        raise ValueError("切片时长必须大于 0")
    if top_n <= 0:
        raise ValueError("切片数量必须大于 0")
    if step <= 0:
        raise ValueError("步长必须大于 0")
    if max_overlap < 0:
        raise ValueError("重叠秒数不能为负数")
    if not timestamps:
        return []

    times = sorted(timestamps)
    last_start = times[-1]
    candidates: list[tuple[float, int]] = []
    left = 0
    right = 0
    start = 0.0
    # Guard against float drift on long videos.
    limit = last_start + step / 2
    while start <= limit:
        end = start + duration
        while right < len(times) and times[right] < end:
            right += 1
        while left < len(times) and times[left] < start:
            left += 1
        count = right - left
        if count:
            candidates.append((start, count))
        start += step

    candidates.sort(key=lambda item: (-item[1], item[0]))
    chosen: list[tuple[float, int]] = []
    for start_time, count in candidates:
        if all(
            _overlap(start_time, selected, duration) <= max_overlap
            for selected, _count in chosen
        ):
            chosen.append((start_time, count))
            if len(chosen) == top_n:
                break
    chosen.sort(key=lambda item: item[0])
    return chosen


def _overlap(start_a: float, start_b: float, duration: float) -> float:
    return min(start_a + duration, start_b + duration) - max(start_a, start_b)
