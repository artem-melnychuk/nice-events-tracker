# Nice Events Tracker

A personal tool that collects upcoming concerts around Nice and the Côte d'Azur from several public sources, merges the same event when more than one site lists it, and keeps a running Excel dataset that I review and rate. Built as a hands-on project in data pipelines, scraping and agent-driven development, and developed with [Claude Code](https://claude.com/claude-code).

> Personal, non-commercial project. Read [Responsible use](#responsible-use) before running it.

## Status

Works end to end on a few hundred upcoming events. Runs are started by hand: no scheduler and no push notifications yet (see the [Roadmap](#roadmap)).

## What it does

- **Collectors.** One adapter per source behind a common `BaseCollector` interface: plain HTTP with BeautifulSoup for server-rendered pages, headless Playwright for sites that reject plain HTTP clients or render in the browser.
- **Cross-source deduplication.** The same concert often appears on two or three sites under different titles ("Ninho – Quatro Tour" vs "Ninho @ Palais Nikaïa", "Isha & Limsa" vs "LIMSA + ISHA"). Records are grouped by date and merged on title, word prefix, reordered words or shared venue, keeping the richest fields of each.
- **Stable identity.** An event keeps its id when a new source joins it or its title or URL changes, so reruns update rows instead of duplicating them and my ratings stay attached.
- **One category vocabulary.** Each source's own labels ("Exposition", "Récital", "Sports and recreation") are mapped onto a small shared taxonomy: Concert, Festival, Show, Exhibition, Gastronomy, Market, Sport, plus Other for labels it doesn't know. `config/settings.yaml` picks which ones to collect; it is set to concerts only for now.
- **Ranking.** Themes I consistently dislike sink to the bottom of the workbook (config-driven), events that already ended are not added, cancellations are flagged.
- **Excel output.** A raw workbook per run and a processed workbook merged across runs.
- **Manual channel.** Events from sources that can't or shouldn't be scraped go into `config/manual_events.yaml` and flow through the same pipeline.
- **Review loop.** A small private review UI (a Claude artifact with a persistent database) collects thumbs up/down. `scripts/sync_diff.py` works out what to write to it: only new documents and changed collector fields, never a rating and never a delete.

## Pipeline

```text
collectors ─▶ cross-source merge ─▶ in-run dedup ─▶ drop finished ─▶ merge into stored workbook ─▶ theme ranking ─▶ Excel
(per source)  (title/date/venue)    (by URL)                        (stable ids, absorbs duplicates)
```

### Example

Four invented listings (fictional artist, venues and URLs) for the same day, run through the real `merge_cross_source_duplicates`:

| Source | Title as listed | Theme | Venue | Price |
|---|---|---|---|---|
| explorenicecotedazur | Marlowe & the Tides — Blue Hour Tour | Jazz and blues | – | – |
| cannes | Marlowe & the Tides | – | Salle Fictive | – |
| panda_events | MARLOWE & THE TIDES | – | Salle Fictive | from 18 € |
| opera_de_nice | Quartet Nocturne | – | Halle du Port | – |

Result: two rows.

| Source | Title | Theme | Venue | Price |
|---|---|---|---|---|
| cannes+explorenicecotedazur+panda_events | Marlowe & the Tides | Jazz and blues | Salle Fictive | from 18 € |
| opera_de_nice | Quartet Nocturne | – | Halle du Port | – |

The first three share a date and a title (exactly, or as a word prefix), so they become one row that takes the theme from one source, the venue from another and the price from the third. The all-caps title is replaced by the mixed-case one. The fourth is a different act on the same day and stays separate. The rules are covered in `tests/test_cross_source_dedup.py` and `tests/test_second_pass_dedup.py`.

## Sources

| Source | How | Notes |
|---|---|---|
| Nice Côte d'Azur tourist office | HTTP | Official agenda; category filtered client-side |
| Opéra de Nice | HTTP | Programme with categories |
| Panda Events | HTTP | Club and mid-size venues; real prices on almost every card |
| Cannes tourist office | HTTP | Concert detected from the detail page; includes nearby communes |
| Menton tourist office | HTTP | Same platform as Cannes; several nearby communes |
| HelloAsso | Playwright | Hand-picked organizers only (JSON-LD). See [Responsible use](#responsible-use) |
| Manual entries | YAML | For events from sources that aren't scraped |

Switched off: Antibes, whose legal notice forbids extracting from its database without agreement, and Songkick, whose terms prohibit scrapers and automated data mining without written consent. I collected from Songkick from mid-September 2026 until 2026-10-05; the events collected stay in the dataset as history and are no longer refreshed. Both adapters stay in the code as commented-out lines in `config/settings.yaml`, to be re-enabled only with the site's written consent.

Not used: Resident Advisor, Shotgun and Instagram (bot protection and/or terms rule scraping out).

## Findings

Data as of 2026-10-05: 321 events, 98 of them rated in the review tool (43 liked, 55 disliked). `scripts/analysis_report.py` prints the tables below from the processed workbook and the ratings export. Both stay local (`data/` is gitignored), so the figures can be regenerated on my machine but not from this repository; only counts and shares are published.

### Price coverage

Price was the weakest field. In the workbook of 2026-09-19, 94 of the 98 rated events (96%) had no price.

| Population | Events | Price given 2026-09-19 | Price given now |
|---|---|---|---|
| Rated events that existed on 2026-09-19 | 98 | 4 (4%) | 16 (16%) |
| Events that existed on 2026-09-19 | 190 | 20 (11%) | 36 (19%) |
| Events added since | 131 | - | 90 (69%) |
| Whole dataset (different populations) | 225 -> 321 | 21 (9%) | 126 (39%) |

Two things raised it. Events already in the dataset gained a price when a source that publishes prices, here Panda Events, listed the same event (190 events, 11% to 19%). And most of the events added since come from sources that publish a price (69% of 131); 74 of those 131 come from the Cannes and Menton tourist offices, added for geography. 35 of the 225 rows of 2026-09-19 no longer exist (duplicates removed or merged); counting only the 190 that remain, the starting share is 11% rather than 9%.

By source (a merged event counts under every source it contains, and its price may come from any of them):

| Source | Price given 2026-09-19 | Price given now |
|---|---|---|
| explorenicecotedazur | 12/137 (9%) | 21/142 (15%) |
| songkick | 0/81 (0%) | 15/82 (18%) |
| opera_de_nice | 20/35 (57%) | 39/54 (72%) |
| cannes | - | 43/48 (90%) |
| panda_events | - | 28/28 (100%) |
| menton | - | 14/26 (54%) |
| helloasso | 1/1 (100%) | 2/2 (100%) |

No Songkick-only event has a price (0 of 42); the 15 priced events listed on Songkick were merged with Panda Events listings. A price counts as given when the field is not empty (7 of the 126 just say the event is free).

### What I liked

Share of the rated events I liked, by source, theme, venue and price. Themes and venues with fewer than 5 ratings are left out. About half of the rated events have no venue or theme, because the source listed none. Songkick's 42 rated events date from the period it was collected (see [Sources](#sources)).

| Source | Rated | Liked | Like rate | p vs rest |
|---|---|---|---|---|
| explorenicecotedazur | 68 | 28 | 41% | 0.509 |
| songkick | 42 | 18 | 43% | 1.000 |
| panda_events | 11 | 6 | 55% | 0.527 |
| opera_de_nice | 7 | 3 | 43% | 1.000 |

| Theme | Rated | Liked | Like rate | p vs rest |
|---|---|---|---|---|
| (not given) | 46 | 20 | 43% | - |
| Classical music | 14 | 6 | 43% | 1.000 |
| Jazz and blues | 5 | 4 | 80% | 0.165 |
| Rock | 5 | 2 | 40% | 1.000 |

| Venue | Rated | Liked | Like rate | p vs rest |
|---|---|---|---|---|
| (not given) | 48 | 21 | 44% | - |
| Théâtre Lino Ventura | 9 | 3 | 33% | 0.727 |
| Frigo 16 | 7 | 5 | 71% | 0.235 |
| Le 109 | 5 | 3 | 60% | 0.651 |
| Palais Nikaïa | 5 | 1 | 20% | 0.381 |

| Price | Rated | Liked | Like rate | p vs rest |
|---|---|---|---|---|
| not given | 82 | 34 | 41% | - |
| given | 16 | 9 | 56% | 0.288 |

With 98 ratings these describe one person's taste. `p vs rest` is Fisher's exact test of each group against all other rated events: 13 comparisons, uncorrected. Only one difference is unlikely to be chance: Pop music, Rap/R&B/Soul and Light music together got 0 likes in 10 ratings, against 43 of 88 for everything else (p = 0.002; I chose that group after seeing the ratings, so the p-value flatters it). That is the one pattern I acted on: `config/settings.yaml` sinks those themes to the bottom of the workbook (they are still collected). Every other difference shown has p of 0.16 or more, including the higher like rate for events with a price (9 of 16 against 34 of 82). Only 16 rated events have a price at all, which is why price coverage was worth improving.

## Quick start (Windows)

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\python scripts\collector.py
```

`--category Exhibition` (repeatable, or `--category all`) collects other categories for one run without touching the settings.

Output goes to `data/raw/nice_events_raw.xlsx` and `data/processed/nice_events_processed.xlsx` (gitignored). A partial run (`--source X`) refreshes X's fields on rows already merged from several sources and keeps what the other sources contributed (theme, venue, ...); run all sources to re-decide a merge from scratch.

Tests run offline on saved markup and fake sessions:

```bash
.venv\Scripts\python -m unittest discover -s tests
```

## Responsible use

- Personal, non-commercial use. The data files are not committed (`data/` is gitignored) and nothing is republished.
- One run a day at most, a pause between requests, and no more than around a hundred requests per source per run.
- The HTTP adapters identify themselves (`nice-events-tracker; personal project`). The browser adapters (HelloAsso in use; Songkick and Antibes switched off) use a standard Chrome User-Agent, because those sites reject plain HTTP clients.
- Terms differ by source. The tourist-office notices restrict reproduction and publication of their content and say nothing about automated access. HelloAsso's terms contain no scraping clause I could find. **Songkick's terms prohibit scrapers and automated data mining without written consent.** I used its adapter for my own private use for about three weeks, then switched it off on 2026-10-05 because of that prohibition. If you fork this, read each site's terms yourself, and do not run the Songkick adapter publicly, commercially or at any volume.
- New sources get a manual review of `robots.txt` and the site's legal notice first. That review is why Resident Advisor was never added and why Antibes was switched off.

## Built with Claude Code

I set the requirements, choose and vet the sources, rate events, and make the calls on scope and legal risk; Claude Code implements and tests. [`CLAUDE.md`](CLAUDE.md) holds the standing rules for the agent: work in an isolated git worktree, run the full test suite, and merge to `master` only when it is green and, where practical, after a live smoke test against the real source. Two of the sources (Antibes, Menton) were added that way.

## Roadmap

- [x] Concerts from several sources with cross-source deduplication.
- [x] Broaden geography from Nice to the wider Côte d'Azur (Cannes, Menton done).
- [ ] Broaden from concerts to the full event taxonomy (festivals, markets, exhibitions, sports, gastronomy). The taxonomy, the per-source mapping and the category setting are in, and the Opéra and explorenicecotedazur labels have been checked against live listings; still to do is checking the Cannes and Menton labels and switching more categories on.
- [ ] Broaden geography further (Grasse, Monaco, nearby major cities), preferably from open data such as DATAtourisme rather than scraping.
- [ ] Add more sources, dedup across them, automate a daily run, and (maybe) push notifications for new events.
- [ ] A separate, related project: a music-festival tracker across Europe, reusing the same core once it's proven here.

## Project layout

```text
collectors/   one adapter per source, plus BaseCollector
core/         EventRecord, ids, category taxonomy, dedup and merge, Excel storage, filters, ranking, sync diff
scripts/      collector.py (main run), sync_diff.py, add_manual_events.py, drop_source.py, analysis_report.py (the Findings tables)
config/       settings.yaml (sources, disliked themes), manual_events.yaml
tests/        unit tests
scrape_mvp.py the original single-source prototype, kept for reference
```
