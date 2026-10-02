import unittest

from bs4 import BeautifulSoup

from unittest import mock

import requests

from collectors import opera_de_nice
from collectors.opera_de_nice import OperaDeNiceCollector, page_url, parse_event

CONCERT_ARTICLE_HTML = """
<article id="event-1527" class="event--block post-1527 event_type-concert" itemscope itemtype="https://schema.org/Event">
  <div class="wrapper-info">
    <h2 itemprop="name">Chopin</h2>
    <p itemprop="location" itemscope itemtype="https://schema.org/Place">
      <span itemprop="name">Foyer Montserrat Caballe de l'Opera</span>
    </p>
  </div>
  <div class="wrapper-meta">
    <p class="meta--item event--event-type">
      <a class="link cat-event" href="https://www.opera-nice.org/agenda/type-evenement/concert/">Concert</a>
    </p>
    <p class="event--date">
      <meta itemprop="startDate" content="2026-09-18">
    </p>
    <p class="text-end mb-2"><span class="event--price">gratuit</span></p>
  </div>
</article>
"""

RENCONTRE_ARTICLE_HTML = """
<article id="event-1532" class="event--block post-1532 event_type-rencontre" itemscope itemtype="https://schema.org/Event">
  <div class="wrapper-info">
    <h2 itemprop="name">De l'operette a la comedie musicale</h2>
  </div>
  <div class="wrapper-meta">
    <p class="meta--item event--event-type">
      <a class="link cat-event" href="https://www.opera-nice.org/agenda/type-evenement/rencontre/">Rencontre</a>
    </p>
    <p class="event--date">
      <meta itemprop="startDate" content="2026-09-20">
    </p>
  </div>
</article>
"""

ARTICLE_WITHOUT_TITLE_HTML = """<article id="event-1"><div class="wrapper-meta"></div></article>"""


class ParseEventTests(unittest.TestCase):
    def test_extracts_a_concert_with_category_and_venue(self) -> None:
        soup = BeautifulSoup(CONCERT_ARTICLE_HTML, "lxml")
        record = parse_event(soup.select_one("article"))

        self.assertEqual(record.title, "Chopin")
        self.assertEqual(record.category, "Concert")
        self.assertEqual(record.venue, "Foyer Montserrat Caballe de l'Opera")
        self.assertEqual(record.start_date, "2026-09-18")
        self.assertEqual(record.end_date, "2026-09-18")
        self.assertEqual(record.price, "gratuit")
        self.assertEqual(record.source, "opera_de_nice")

    def test_extracts_the_real_category_for_a_non_concert_event(self) -> None:
        soup = BeautifulSoup(RENCONTRE_ARTICLE_HTML, "lxml")
        record = parse_event(soup.select_one("article"))
        self.assertEqual(record.category, "Rencontre")

    def test_returns_none_without_a_title(self) -> None:
        soup = BeautifulSoup(ARTICLE_WITHOUT_TITLE_HTML, "lxml")
        self.assertIsNone(parse_event(soup.select_one("article")))


class FakeSession:
    """Serves saved agenda pages; anything else is a 404, which ends the crawl."""

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages

    def get(self, url, headers=None, timeout=None):
        response = mock.Mock()
        if url not in self.pages:
            error = requests.HTTPError("404")
            error.response = mock.Mock(status_code=404)
            response.raise_for_status.side_effect = error
            return response
        response.text = self.pages[url]
        response.raise_for_status = lambda: None
        return response


class CategoryTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(opera_de_nice.time, "sleep")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.session = FakeSession({page_url(1): f"<html><body>{CONCERT_ARTICLE_HTML}{RENCONTRE_ARTICLE_HTML}</body></html>"})

    def test_an_opera_production_is_a_show(self) -> None:
        html = CONCERT_ARTICLE_HTML.replace(">Concert</a>", ">Opéra</a>")
        record = parse_event(BeautifulSoup(html, "lxml").select_one("article"))

        self.assertEqual(record.category, "Show")

    def test_the_default_keeps_concerts_only(self) -> None:
        result = OperaDeNiceCollector().collect(self.session)

        self.assertEqual([r.title for r in result.records], ["Chopin"])

    def test_other_collects_the_labels_the_taxonomy_does_not_know(self) -> None:
        result = OperaDeNiceCollector(category_filter=["Other"]).collect(self.session)

        self.assertEqual([(r.title, r.category) for r in result.records], [("De l'operette a la comedie musicale", "Rencontre")])


if __name__ == "__main__":
    unittest.main()
