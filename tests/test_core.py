import unittest
from pathlib import Path

from xmlslice.danmaku import extract_timestamps
from xmlslice.density import find_auto_periods, find_dense_periods, find_ranked_auto_periods

FIXTURE = Path(__file__).parent / "fixtures" / "sample.xml"


class DanmakuTests(unittest.TestCase):
    def test_reads_offset_from_p_attribute(self):
        stamps = extract_timestamps(str(FIXTURE))
        self.assertEqual(stamps, [0.777, 6.292, 6.669, 42.065])

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            extract_timestamps("/tmp/does-not-exist.xml")


class DensityTests(unittest.TestCase):
    def test_picks_the_busiest_nonoverlapping_windows(self):
        stamps = [1, 1, 1, 10, 50, 50, 50, 50]
        periods = find_dense_periods(stamps, duration=10, top_n=2, max_overlap=0, step=1)
        self.assertEqual(periods, [(1.0, 4), (41.0, 4)])

    def test_empty_input(self):
        self.assertEqual(find_dense_periods([], 10, 1, 0, 1), [])

    def test_keeps_only_windows_that_meet_min_count(self):
        stamps = [1, 1, 1, 10, 50, 50, 50, 50]
        periods = find_dense_periods(
            stamps, duration=10, top_n=2, max_overlap=0, step=1, min_count=4
        )
        self.assertEqual(periods, [(1.0, 4), (41.0, 4)])

    def test_returns_nothing_when_no_window_meets_min_count(self):
        stamps = [1, 1, 1, 10, 50, 50, 50, 50]
        periods = find_dense_periods(
            stamps, duration=10, top_n=2, max_overlap=0, step=1, min_count=5
        )
        self.assertEqual(periods, [])

    def test_rejects_non_positive_min_count(self):
        with self.assertRaises(ValueError):
            find_dense_periods([1], 10, 1, 0, 1, min_count=0)


class AutoPeriodTests(unittest.TestCase):
    def test_covers_the_qualifying_windows_without_padding(self):
        periods = find_auto_periods([15, 16, 17], min_count=3, window=10)
        self.assertEqual(periods, [(8.0, 25.0, 3)])

    def test_keeps_going_when_the_count_exceeds_again_within_ten_seconds(self):
        stamps = [15, 16, 17, 30, 31, 32]
        periods = find_auto_periods(stamps, min_count=3, window=10)
        self.assertEqual(periods, [(8.0, 40.0, 6)])

    def test_splits_when_quiet_lasts_ten_seconds(self):
        stamps = [15, 16, 17, 40, 41, 42]
        periods = find_auto_periods(stamps, min_count=3, window=10)
        self.assertEqual(periods, [(8.0, 25.0, 3), (33.0, 50.0, 3)])

    def test_returns_nothing_below_the_line(self):
        self.assertEqual(find_auto_periods([15, 16], min_count=3, window=10), [])

    def test_rejects_non_positive_min_count(self):
        with self.assertRaises(ValueError):
            find_auto_periods([15, 16, 17], min_count=0)


class RankedAutoTests(unittest.TestCase):
    def test_returns_the_densest_segments_first(self):
        busy = [float(second) for second in range(20, 30)]
        quiet = [100.0, 101.0, 102.0]
        periods = find_ranked_auto_periods(busy + quiet, top_n=2, window=10)
        self.assertEqual(periods, [(15.0, 35.0, 10), (92.0, 111.0, 3)])

    def test_limits_to_top_n(self):
        busy = [float(second) for second in range(20, 30)]
        quiet = [100.0, 101.0, 102.0]
        periods = find_ranked_auto_periods(busy + quiet, top_n=1, window=10)
        self.assertEqual(periods, [(15.0, 35.0, 10)])

    def test_rejects_non_positive_top_n(self):
        with self.assertRaises(ValueError):
            find_ranked_auto_periods([20.0], top_n=0, window=10)


if __name__ == "__main__":
    unittest.main()
