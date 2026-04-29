"""Unit tests for cost_watch.consistency."""
import unittest

from consistency import (
    DIVERGENT_THRESHOLD_PCT,
    WARNING_THRESHOLD_PCT,
    calc_comparisons,
    evaluate_consistency,
)


class TestEvaluateConsistency(unittest.TestCase):
    def test_empty(self):
        r = evaluate_consistency([])
        self.assertEqual(r.flag, "single")
        self.assertEqual(r.sources_count, 0)

    def test_single_source(self):
        r = evaluate_consistency([100.0])
        self.assertEqual(r.flag, "single")
        self.assertEqual(r.sources_count, 1)
        self.assertEqual(r.value_min, 100.0)
        self.assertEqual(r.value_max, 100.0)

    def test_consistent_three_sources(self):
        # spec example: 174.8, 175.4, 175.6 -> 0.46% deviation
        r = evaluate_consistency([174.8, 175.4, 175.6])
        self.assertEqual(r.flag, "consistent")
        self.assertEqual(r.sources_count, 3)
        self.assertEqual(r.value_min, 174.8)
        self.assertEqual(r.value_max, 175.6)
        self.assertAlmostEqual(r.max_deviation_pct, 0.46, places=2)

    def test_warning_band(self):
        # 100, 103 -> 3/101.5 * 100 = 2.96%
        r = evaluate_consistency([100.0, 103.0])
        self.assertEqual(r.flag, "warning")

    def test_divergent_band(self):
        # 100, 110 -> 10/105 * 100 = 9.52%
        r = evaluate_consistency([100.0, 110.0])
        self.assertEqual(r.flag, "divergent")

    def test_threshold_boundary_warning(self):
        # exactly 2% should fall into warning, not consistent
        # values around mean=100 with diff=2.0
        r = evaluate_consistency([99.0, 101.0])  # diff=2, mean=100, dev=2.00
        self.assertEqual(r.flag, "warning")

    def test_threshold_boundary_divergent(self):
        # exactly 5% should fall into divergent
        r = evaluate_consistency([97.5, 102.5])  # diff=5, mean=100, dev=5.00
        self.assertEqual(r.flag, "divergent")

    def test_ignores_none(self):
        r = evaluate_consistency([100.0, None, 102.0])
        self.assertEqual(r.sources_count, 2)


class TestCalcComparisons(unittest.TestCase):
    def test_empty_history(self):
        c = calc_comparisons([])
        self.assertEqual(c, {"wow_pct": None, "mom_pct": None, "yoy_pct": None})

    def test_full_history_all_periods(self):
        history = [
            {"date": "2025-04-29", "value": 165.0},  # ~1y prior
            {"date": "2026-03-29", "value": 173.0},  # ~1m prior
            {"date": "2026-04-22", "value": 174.8},  # ~1w prior
            {"date": "2026-04-29", "value": 175.4},  # current
        ]
        c = calc_comparisons(history)
        # wow: (175.4 - 174.8) / 174.8 * 100 = 0.343 -> 0.34
        self.assertAlmostEqual(c["wow_pct"], 0.34, places=2)
        # mom: (175.4 - 173.0) / 173.0 * 100 = 1.387 -> 1.39
        self.assertAlmostEqual(c["mom_pct"], 1.39, places=2)
        # yoy: (175.4 - 165.0) / 165.0 * 100 = 6.303 -> 6.30
        self.assertAlmostEqual(c["yoy_pct"], 6.30, places=2)

    def test_partial_history_only_recent(self):
        # only week of data: yoy/mom should be None
        history = [
            {"date": "2026-04-22", "value": 100.0},
            {"date": "2026-04-29", "value": 101.0},
        ]
        c = calc_comparisons(history)
        self.assertAlmostEqual(c["wow_pct"], 1.0, places=2)
        self.assertIsNone(c["mom_pct"])
        self.assertIsNone(c["yoy_pct"])


if __name__ == "__main__":
    unittest.main()
