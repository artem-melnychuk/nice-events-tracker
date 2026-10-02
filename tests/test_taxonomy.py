import unittest

from core.taxonomy import (
    CATEGORIES,
    canonical_category,
    category_matches,
    normalize_category,
    only_cultural,
    parse_category_filter,
    pick_category,
)


class CanonicalCategoryTests(unittest.TestCase):
    def test_maps_source_labels_in_english_and_french(self) -> None:
        cases = {
            "Concert": "Concert",
            "Récital": "Concert",
            "Fête de la musique": "Festival",
            "Opéra": "Show",
            "Théâtre": "Show",
            "Exposition": "Exhibition",
            "Exhibition": "Exhibition",
            "Marché de Noël": "Market",
            "Commercial event": "Market",
            "Wine tasting": "Gastronomy",
            "Dégustation": "Gastronomy",
            "Sports and recreation": "Sport",
            "Trail": "Sport",
        }
        for label, expected in cases.items():
            with self.subTest(label=label):
                self.assertEqual(canonical_category(label), expected)

    def test_every_canonical_name_maps_to_itself(self) -> None:
        for category in CATEGORIES:
            with self.subTest(category=category):
                self.assertEqual(canonical_category(category), category)

    def test_matches_whole_words_only(self) -> None:
        # "concertina" and "marchepied" must not read as Concert / Market.
        self.assertEqual(canonical_category("Concertina workshop"), "")
        self.assertEqual(canonical_category("Marchepied"), "")

    def test_unknown_and_blank_labels_have_no_category(self) -> None:
        self.assertEqual(canonical_category("Rencontre"), "")
        self.assertEqual(canonical_category(""), "")

    def test_normalize_keeps_an_unknown_label_as_written(self) -> None:
        self.assertEqual(normalize_category(" Rencontre "), "Rencontre")
        self.assertEqual(normalize_category("Exposition"), "Exhibition")


class PickCategoryTests(unittest.TestCase):
    def test_the_highest_ranked_chip_wins(self) -> None:
        self.assertEqual(pick_category(["Festival", "Concert", "Jazz"]), ("Concert", "Concert"))
        self.assertEqual(pick_category(["Sports and recreation", "Exhibition"]), ("Exhibition", "Exhibition"))

    def test_returns_the_chip_the_category_came_from(self) -> None:
        self.assertEqual(pick_category(["Heritage", "Sports and recreation"]), ("Sport", "Sports and recreation"))

    def test_falls_back_to_the_first_chip_when_none_is_recognised(self) -> None:
        self.assertEqual(pick_category(["", "Heritage", "Guided tour"]), ("Heritage", "Heritage"))

    def test_no_chips(self) -> None:
        self.assertEqual(pick_category([]), ("", ""))


class CategoryFilterTests(unittest.TestCase):
    def test_none_and_all_mean_no_filter(self) -> None:
        self.assertIsNone(parse_category_filter(None))
        self.assertIsNone(parse_category_filter("all"))
        self.assertIsNone(parse_category_filter(["Concert", "ALL"]))

    def test_a_single_name_and_a_list_are_both_accepted_case_insensitively(self) -> None:
        self.assertEqual(parse_category_filter("concert"), frozenset({"Concert"}))
        self.assertEqual(parse_category_filter(["market", "Other"]), frozenset({"Market", "Other"}))

    def test_an_unknown_name_is_an_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Exhibitions"):
            parse_category_filter(["Concert", "Exhibitions"])

    def test_an_empty_list_is_an_error_not_everything(self) -> None:
        with self.assertRaises(ValueError):
            parse_category_filter([])
        with self.assertRaises(ValueError):
            parse_category_filter("")

    def test_matching_goes_through_the_canonical_category(self) -> None:
        wanted = parse_category_filter(["Exhibition"])
        self.assertTrue(category_matches("Exposition", wanted))
        self.assertFalse(category_matches("Concert", wanted))

    def test_unknown_labels_count_as_other(self) -> None:
        self.assertTrue(category_matches("Rencontre", frozenset({"Other"})))
        self.assertFalse(category_matches("Rencontre", frozenset({"Concert"})))
        self.assertTrue(category_matches("", frozenset({"Other"})))

    def test_no_filter_matches_everything(self) -> None:
        self.assertTrue(category_matches("Rencontre", None))

    def test_only_cultural(self) -> None:
        self.assertTrue(only_cultural(frozenset({"Concert", "Exhibition"})))
        self.assertFalse(only_cultural(frozenset({"Concert", "Market"})))
        self.assertFalse(only_cultural(frozenset({"Other"})))
        self.assertFalse(only_cultural(None))


class LabelsSeenOnLiveSitesTests(unittest.TestCase):
    """Labels read off the live Opera de Nice and explorenicecotedazur listings on 2026-10-02.

    Pinned with the category each one should get, after looking at the events
    behind the ambiguous ones. "Afterwork" (musical evenings at the Opera) is
    deliberately not here: whether it counts as Concert changes what a normal
    run collects, and that is the owner's call.
    """

    def test_labels_map_to_the_category_their_events_belong_to(self) -> None:
        cases = {
            # Opera de Nice
            "Concert": "Concert",
            "Spectacle musical": "Show",  # children's shows ("Viens avec ton doudou")
            "Opéra": "Show",
            "Ballet": "Show",
            "Événement": "",  # escape game, stand-up
            "Rencontre": "",  # talks and lectures
            # explorenicecotedazur
            "Theatre": "Show",
            "Exhibition": "Exhibition",
            "Show": "Show",
            "One man Show / One woman show": "Show",
            "Dance evening": "Show",
            "Festival": "Festival",
            "Traditional festival": "Festival",
            "Tasting": "Gastronomy",
            "Competitive sport": "Sport",
            "Water sports": "Sport",
            "Climbing sports": "Sport",
            "Conference": "",
            "Meeting": "",
            # trade fairs and salons ("Annual Autumn Fair", "Foire du Village"), not shows
            "Fair or show": "Market",
            # a flea market and a retailers' sale
            "Clearance sale": "Market",
            "Soldes": "Market",
        }
        for label, expected in cases.items():
            with self.subTest(label=label):
                self.assertEqual(canonical_category(label), expected)

    def test_the_fair_or_show_override_is_not_a_general_show_to_market_swap(self) -> None:
        self.assertEqual(canonical_category("FAIR  or  Show"), "Market")
        self.assertEqual(canonical_category("Show"), "Show")
        self.assertEqual(canonical_category("Fair"), "Market")
        self.assertEqual(canonical_category("Comedy show"), "Show")


if __name__ == "__main__":
    unittest.main()
