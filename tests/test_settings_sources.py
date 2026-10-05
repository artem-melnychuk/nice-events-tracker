import unittest
from pathlib import Path

from core.config import load_settings
from scripts.collector import COLLECTOR_REGISTRY

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"


class ConfiguredSourcesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sources = load_settings(SETTINGS_PATH)["sources"]

    def test_every_configured_source_has_a_collector(self) -> None:
        for name in self.sources:
            with self.subTest(source=name):
                self.assertIn(name, COLLECTOR_REGISTRY)

    def test_sources_switched_off_over_their_terms_stay_off(self) -> None:
        # Antibes forbids extracting from its database and Songkick prohibits
        # scrapers, both without written consent. The adapters stay in the
        # code and in COLLECTOR_REGISTRY; only the settings line is off.
        for name in ("antibes", "songkick"):
            with self.subTest(source=name):
                self.assertIn(name, COLLECTOR_REGISTRY)
                self.assertNotIn(name, self.sources)


if __name__ == "__main__":
    unittest.main()
