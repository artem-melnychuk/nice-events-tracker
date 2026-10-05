import unittest
from datetime import date

from core.models import EventRecord
from scripts.analysis_report import (
    compare_cohorts,
    coverage,
    coverage_by_source,
    fisher_two_sided,
    format_p,
    like_rates,
    price_known,
    render_report,
)


def rec(event_id: str, source: str = "a", price: str = "", theme: str = "", venue: str = "", title: str = "") -> EventRecord:
    return EventRecord(event_id=event_id, source=source, price=price, theme=theme, venue=venue, title=title)


class CoverageTests(unittest.TestCase):
    def test_a_price_is_given_when_the_field_is_not_blank(self) -> None:
        self.assertFalse(price_known(rec("e1", price="")))
        self.assertFalse(price_known(rec("e1", price="   ")))
        self.assertTrue(price_known(rec("e1", price="free")))
        self.assertTrue(price_known(rec("e1", price="12 EUR")))

    def test_coverage_counts_records_with_a_price(self) -> None:
        self.assertEqual(coverage([rec("e1", price="5"), rec("e2"), rec("e3", price="free")]), (2, 3))
        self.assertEqual(coverage([]), (0, 0))

    def test_a_merged_record_counts_under_every_source_it_contains(self) -> None:
        records = [rec("e1", "a+b", price="10"), rec("e2", "a"), rec("e3", "b", price="4")]
        self.assertEqual(coverage_by_source(records), {"a": (1, 2), "b": (2, 2)})


class LikeRateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = [
            rec("e1", theme="Jazz"),
            rec("e2", theme="Jazz"),
            rec("e3", theme="Rock"),
            rec("e4", theme=""),
            rec("e5", theme="Jazz"),  # not rated
        ]
        self.ratings = {"e1": "like", "e2": "dislike", "e3": "like", "e4": "dislike"}

    def test_groups_rated_events_and_ignores_unrated_ones(self) -> None:
        rows, hidden_ratings, hidden_groups = like_rates(self.records, self.ratings, lambda r: [r.theme or "(none)"])
        self.assertEqual(rows, [("Jazz", 2, 1), ("(none)", 1, 0), ("Rock", 1, 1)])
        self.assertEqual((hidden_ratings, hidden_groups), (0, 0))

    def test_groups_below_the_threshold_are_counted_but_not_listed(self) -> None:
        rows, hidden_ratings, hidden_groups = like_rates(self.records, self.ratings, lambda r: [r.theme or "(none)"], min_rated=2)
        self.assertEqual(rows, [("Jazz", 2, 1)])
        self.assertEqual((hidden_ratings, hidden_groups), (2, 2))

    def test_a_merged_event_is_counted_under_each_source(self) -> None:
        records = [rec("e1", "a+b"), rec("e2", "a")]
        rows, _, _ = like_rates(records, {"e1": "like", "e2": "dislike"}, lambda r: r.source.split("+"))
        self.assertEqual(rows, [("a", 2, 1), ("b", 1, 1)])


class SignificanceTests(unittest.TestCase):
    def test_matches_the_textbook_two_sided_fisher_value(self) -> None:
        # The tea-tasting table [[3, 1], [1, 3]]: two-sided p = 34/70.
        self.assertAlmostEqual(fisher_two_sided(3, 4, 1, 4), 34 / 70, places=9)

    def test_equal_rates_give_one_and_a_clear_gap_gives_a_small_p(self) -> None:
        self.assertAlmostEqual(fisher_two_sided(5, 10, 10, 20), 1.0, places=9)
        self.assertLess(fisher_two_sided(0, 10, 43, 88), 0.005)

    def test_the_result_does_not_depend_on_which_group_comes_first(self) -> None:
        self.assertAlmostEqual(fisher_two_sided(2, 7, 30, 60), fisher_two_sided(30, 60, 2, 7), places=12)

    def test_p_values_are_printed_to_three_places(self) -> None:
        self.assertEqual(format_p(0.4857142), "0.486")
        self.assertEqual(format_p(0.0004), "<0.001")


class CohortTests(unittest.TestCase):
    def test_compares_the_same_events_the_added_ones_and_the_whole_dataset(self) -> None:
        before = [rec("e1"), rec("e2", price="9"), rec("e9", price="3")]  # e9 was later removed
        after = [rec("e1", price="5"), rec("e2", price="9"), rec("e3", price="1"), rec("e4")]
        compared = compare_cohorts(before, after, rated_ids=["e1", "e4", "gone"])

        self.assertEqual(compared["rated"], (1, 0, 1))  # only e1 existed on both dates
        self.assertEqual(compared["same"], (2, 1, 2))
        self.assertEqual(compared["added"], (2, 1))
        self.assertEqual(compared["whole"], ((2, 3), (3, 4)))


class ReportTests(unittest.TestCase):
    def test_the_report_has_tables_and_only_aggregates(self) -> None:
        after = [
            rec("secret-id-1", "a", price="5", theme="Jazz", venue="Hall", title="Secret Title One"),
            rec("secret-id-2", "a+b", theme="Jazz", venue="Hall", title="Secret Title Two"),
        ]
        before = [rec("secret-id-1", "a"), rec("secret-id-2", "a+b")]
        text = render_report(
            after,
            {"secret-id-1": "like", "secret-id-2": "dislike"},
            before=before,
            deprioritized_themes=["Pop music"],
            min_rated=2,
            today=date(2026, 10, 5),
        )

        for expected in ("# Findings data, 2026-10-05", "- Rated: 2 (liked 1, disliked 1)", "## Price coverage, before and after",
                         "## Price coverage by source", "## Like rate by source", "## Like rate by theme", "## Like rate by venue",
                         "## Like rate by price", "Themes the ranking pushes down (Pop music), together: 0 rated, 0 liked."):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)
        for private in ("secret-id", "Secret Title"):
            with self.subTest(private=private):
                self.assertNotIn(private, text)

    def test_like_tables_carry_a_p_value_except_for_missing_value_groups(self) -> None:
        after = [rec(f"e{i}", theme="Jazz" if i < 4 else "") for i in range(12)]
        ratings = {f"e{i}": ("like" if i < 4 else "dislike") for i in range(12)}

        text = render_report(after, ratings, min_rated=1, today=date(2026, 10, 5))

        self.assertIn("| Theme | Rated | Liked | Like rate | p vs rest |", text)
        self.assertIn("| Jazz | 4 | 4 | 100% | 0.002 |", text)
        self.assertIn("| (not given) | 8 | 0 | 0% | - |", text)

    def test_without_a_before_workbook_the_comparison_is_skipped(self) -> None:
        text = render_report([rec("e1", price="5")], {"e1": "like"}, today=date(2026, 10, 5))
        self.assertNotIn("before and after", text)
        self.assertIn("## Price coverage by source", text)


if __name__ == "__main__":
    unittest.main()
