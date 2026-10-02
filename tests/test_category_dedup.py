import unittest

from core.deduplication import merge_cross_source_duplicates
from core.models import EventRecord

DAY = "2026-12-12"
HALL = "Place Masséna"


class CategoryAwareDedupTests(unittest.TestCase):
    def test_a_market_and_a_concert_at_one_venue_stay_apart(self) -> None:
        records = [
            EventRecord(source="explorenicecotedazur", title="Village de Noël", category="Market", start_date=DAY, venue=HALL),
            EventRecord(source="songkick", title="Village People @ Place Masséna", category="Concert", start_date=DAY, venue=HALL),
        ]

        self.assertEqual(len(merge_cross_source_duplicates(records).records), 2)

    def test_a_word_prefix_does_not_link_two_categories(self) -> None:
        records = [
            EventRecord(source="explorenicecotedazur", title="Marché de Noël", category="Market", start_date=DAY),
            EventRecord(source="menton", title="Marché de Noël - Concert de clôture", category="Concert", start_date=DAY),
        ]

        self.assertEqual(len(merge_cross_source_duplicates(records).records), 2)

    def test_an_exact_title_still_merges_across_categories(self) -> None:
        records = [
            EventRecord(source="explorenicecotedazur", title="Fête de la Musique", category="Festival", start_date=DAY),
            EventRecord(source="cannes", title="Fête de la musique", category="Concert", start_date=DAY),
        ]

        self.assertEqual(len(merge_cross_source_duplicates(records).records), 1)

    def test_a_blank_or_unknown_category_never_blocks_a_link(self) -> None:
        records = [
            EventRecord(source="explorenicecotedazur", title="Isha & Limsa", category="Rencontre", start_date=DAY),
            EventRecord(source="panda_events", title="LIMSA + ISHA", category="", start_date=DAY),
            EventRecord(source="songkick", title="Isha @ Le 109", category="Concert", start_date=DAY),
        ]

        self.assertEqual(len(merge_cross_source_duplicates(records).records), 1)


if __name__ == "__main__":
    unittest.main()
