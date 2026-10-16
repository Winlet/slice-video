"""Find the busiest time windows in a list of danmaku timestamps."""

# 自动模式的统计窗口（秒）。改这一处即可。
UNIT_SECONDS = 10


def find_dense_periods(
    timestamps: list[float],
    duration: float,
    top_n: int,
    max_overlap: float,
    step: float,
    min_count: int = 1,
) -> list[tuple[float, int]]:
    """Return up to top_n windows as (start_seconds, danmaku_count).

    Windows are [start, start + duration). Candidates move forward by `step`
    seconds. A window is kept only when it contains at least min_count
    danmaku, and its overlap with every already chosen window is no greater
    than max_overlap.
    """
    if duration <= 0:
        raise ValueError("切片时长必须大于 0")
    if top_n <= 0:
        raise ValueError("切片数量必须大于 0")
    if step <= 0:
        raise ValueError("步长必须大于 0")
    if max_overlap < 0:
        raise ValueError("重叠秒数不能为负数")
    if min_count < 1:
        raise ValueError("弹幕数量必须大于 0")
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
        if count >= min_count:
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


def find_auto_periods(
    timestamps: list[float],
    min_count: int,
    window: float = UNIT_SECONDS,
    hold: float = 10,
) -> list[tuple[float, float, int]]:
    """Return (start, end, danmaku_count) for each stretch over min_count.

    A second is over the line when the following `window` seconds contain at
    least min_count danmaku. The segment covers those windows exactly. If the
    count crosses the line again within `hold` seconds, the stretch continues
    instead of being cut.
    """
    if min_count < 1:
        raise ValueError("弹幕数量必须大于 0")
    if window <= 0 or hold <= 0:
        raise ValueError("自动切片的秒数必须大于 0")
    times = sorted(stamp for stamp in timestamps if stamp >= 0)
    hot_seconds = _forward_hot_seconds(times, window, min_count)
    if not hot_seconds:
        return []

    groups: list[list[int]] = [[hot_seconds[0]]]
    for second in hot_seconds[1:]:
        if second - groups[-1][-1] <= hold:
            groups[-1].append(second)
        else:
            groups.append([second])

    periods: list[tuple[float, float, int]] = []
    previous_end = 0.0
    for group in groups:
        start = max(previous_end, float(group[0]))
        end = float(group[-1]) + window
        if start >= end:
            continue
        periods.append((start, end, _count_between(times, start, end)))
        previous_end = end
    return periods


def _forward_hot_seconds(times: list[float], window: float, min_count: int) -> list[int]:
    if not times:
        return []
    hot: list[int] = []
    left = 0
    right = 0
    total = len(times)
    for second in range(int(times[-1]) + 1):
        end = second + window
        while right < total and times[right] < end:
            right += 1
        while left < total and times[left] < second:
            left += 1
        if right - left >= min_count:
            hot.append(second)
    return hot


def find_ranked_auto_periods(
    timestamps: list[float],
    top_n: int,
    window: float = UNIT_SECONDS,
    hold: float = 10,
) -> list[tuple[float, float, int]]:
    """Return the top_n auto segments with the most danmaku per second.

    Peaks are the busiest `window`-second spans. Each peak grows while the
    surrounding windows stay at least half as busy. Results are sorted by
    danmaku per second, highest first.
    """
    if top_n <= 0:
        raise ValueError("切片数量必须大于 0")
    if window <= 0 or hold <= 0:
        raise ValueError("自动切片的秒数必须大于 0")
    times = sorted(stamp for stamp in timestamps if stamp >= 0)
    counts = _window_counts(times, window)
    if not counts or max(counts) <= 0:
        return []

    segments = _peak_segments(counts, window, hold)
    periods: list[tuple[float, float, int]] = []
    for left, right in segments:
        start = float(left)
        end = float(right) + window
        if start >= end:
            continue
        periods.append((start, end, _count_between(times, start, end)))

    periods = _merge_overlapping(periods, times)
    periods.sort(key=lambda item: (-_density(item), -item[2], item[0]))
    return periods[:top_n]


def _window_counts(times: list[float], window: float) -> list[int]:
    if not times:
        return []
    counts: list[int] = []
    left = 0
    right = 0
    total = len(times)
    for second in range(int(times[-1]) + 1):
        end = second + window
        while right < total and times[right] < end:
            right += 1
        while left < total and times[left] < second:
            left += 1
        counts.append(right - left)
    return counts


def _peak_segments(counts: list[int], window: float, hold: float) -> list[tuple[int, int]]:
    span = max(1, int(window))
    peaks: list[int] = []
    for second, count in enumerate(counts):
        if count <= 0:
            continue
        left = max(0, second - span)
        right = min(len(counts), second + span + 1)
        neighborhood = counts[left:right]
        if count == max(neighborhood) and second == left + neighborhood.index(count):
            peaks.append(second)

    peaks.sort(key=lambda second: (-counts[second], second))
    chosen: list[int] = []
    for second in peaks:
        if all(abs(second - other) >= span for other in chosen):
            chosen.append(second)

    regions: list[tuple[int, int]] = []
    for second in chosen:
        level = max(1, (counts[second] + 1) // 2)
        left = second
        while left > 0 and counts[left - 1] >= level:
            left -= 1
        right = second
        while right + 1 < len(counts) and counts[right + 1] >= level:
            right += 1
        regions.append((left, right))

    regions.sort()
    merged: list[tuple[int, int]] = []
    for left, right in regions:
        if merged and left - merged[-1][1] <= hold:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))
    return merged


def _merge_overlapping(
    periods: list[tuple[float, float, int]],
    times: list[float],
) -> list[tuple[float, float, int]]:
    if not periods:
        return []
    ordered = sorted(periods)
    merged: list[tuple[float, float]] = [ordered[0][:2]]
    for start, end, _count in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return [(start, end, _count_between(times, start, end)) for start, end in merged]


def _density(period: tuple[float, float, int]) -> float:
    start, end, count = period
    length = end - start
    if length <= 0:
        return 0.0
    return count / length


def _count_between(times: list[float], start: float, end: float) -> int:
    return sum(1 for stamp in times if start <= stamp < end)
