import unittest

from scripts.collector import build_collector, configured_categories, parse_args


class ConfiguredCategoriesTests(unittest.TestCase):
    def test_reads_the_categories_list(self) -> None:
        settings = {"collection": {"categories": ["Concert", "Exhibition"]}}

        self.assertEqual(configured_categories(settings), ["Concert", "Exhibition"])

    def test_falls_back_to_the_older_single_category_filter(self) -> None:
        self.assertEqual(configured_categories({"collection": {"category_filter": "Concert"}}), "Concert")

    def test_categories_wins_over_category_filter(self) -> None:
        settings = {"collection": {"categories": ["Market"], "category_filter": "Concert"}}

        self.assertEqual(configured_categories(settings), ["Market"])


class BuildCollectorTests(unittest.TestCase):
    SETTINGS = {"collection": {"categories": ["Concert"]}}

    def test_a_filtered_source_gets_the_configured_categories(self) -> None:
        collector = build_collector("cannes", self.SETTINGS)

        self.assertEqual(collector.categories, frozenset({"Concert"}))

    def test_the_command_line_overrides_the_settings(self) -> None:
        collector = build_collector("explorenicecotedazur", self.SETTINGS, categories=["exhibition", "Market"])

        self.assertEqual(collector.categories, frozenset({"Exhibition", "Market"}))

    def test_a_misspelt_category_fails_before_collecting(self) -> None:
        with self.assertRaises(ValueError):
            build_collector("menton", {"collection": {"categories": ["Concerts"]}})

    def test_category_is_a_repeatable_flag(self) -> None:
        args = parse_args(["--category", "Sport", "--category", "Market"])

        self.assertEqual(args.category, ["Sport", "Market"])


if __name__ == "__main__":
    unittest.main()
