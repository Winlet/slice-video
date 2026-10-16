import unittest
from pathlib import Path

from xmlslice.danmaku import extract_timestamps
from xmlslice.density import find_dense_periods

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


if __name__ == "__main__":
    unittest.main()
