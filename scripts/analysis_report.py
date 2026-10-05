"""CLI: print the aggregate tables behind the README's Findings section.

Reads the processed workbook and the ratings export (both local and
gitignored) and prints markdown tables of counts and percentages: price
coverage before and after, and like rates by source, theme, venue and price.
No event title, URL or single event's rating is ever printed.

    python scripts/analysis_report.py --before-workbook <older workbook>

`--before-workbook` is a copy of the processed workbook from an earlier date.
Without it the before/after tables are skipped.

A price counts as given when the price field is not empty (a value such as
"free" counts). A merged event is counted under every source it contains, and
its price may come from any of them.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from math import comb
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import load_settings
from core.models import EventRecord
from core.storage import load_records

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"
DEFAULT_RATINGS = PROJECT_ROOT / "data" / "processed" / "ratings_export.json"
NOT_GIVEN = "(not given)"


def price_known(record: EventRecord) -> bool:
    return bool(record.price.strip())


def atomic_sources(record: EventRecord) -> list[str]:
    """Sources behind a record; a merged record's `source` is "a+b"."""
    return [name for name in record.source.split("+") if name]


def coverage(records: Iterable[EventRecord]) -> tuple[int, int]:
    """(records with a price, all records)."""
    records = list(records)
    return sum(price_known(record) for record in records), len(records)


def coverage_by_source(records: Iterable[EventRecord]) -> dict[str, tuple[int, int]]:
    known: Counter[str] = Counter()
    total: Counter[str] = Counter()
    for record in records:
        for source in atomic_sources(record):
            total[source] += 1
            known[source] += price_known(record)
    return {source: (known[source], total[source]) for source in total}


def load_ratings(path: Path) -> dict[str, str]:
    """event_id -> "like" or "dislike", from the ratings export."""
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    return {entry["event_id"]: entry["rating"] for entry in entries if entry.get("rating") in ("like", "dislike")}


def like_rates(
    records: Iterable[EventRecord],
    ratings: Mapping[str, str],
    groups: Callable[[EventRecord], Iterable[str]],
    min_rated: int = 1,
) -> tuple[list[tuple[str, int, int]], int, int]:
    """Like rate per group over rated events.

    Returns (rows of (group, rated, likes) with at least `min_rated` ratings,
    most rated first; ratings and groups left out below that threshold).
    """
    rated: Counter[str] = Counter()
    liked: Counter[str] = Counter()
    for record in records:
        rating = ratings.get(record.event_id)
        if rating is None:
            continue
        for group in groups(record):
            rated[group] += 1
            liked[group] += rating == "like"
    rows = [(group, rated[group], liked[group]) for group in rated if rated[group] >= min_rated]
    rows.sort(key=lambda row: (-row[1], row[0]))
    hidden = [group for group in rated if rated[group] < min_rated]
    return rows, sum(rated[group] for group in hidden), len(hidden)


def compare_cohorts(before: Sequence[EventRecord], after: Sequence[EventRecord], rated_ids: Iterable[str]) -> dict:
    """Price coverage on the same events before and after, on the events added since, and overall."""
    before_by_id = {record.event_id: record for record in before}
    after_by_id = {record.event_id: record for record in after}
    same = [event_id for event_id in after_by_id if event_id in before_by_id]
    added = [event_id for event_id in after_by_id if event_id not in before_by_id]
    rated_same = [event_id for event_id in rated_ids if event_id in before_by_id and event_id in after_by_id]

    def known(by_id: dict[str, EventRecord], ids: Iterable[str]) -> int:
        return sum(price_known(by_id[event_id]) for event_id in ids)

    return {
        "rated": (len(rated_same), known(before_by_id, rated_same), known(after_by_id, rated_same)),
        "same": (len(same), known(before_by_id, same), known(after_by_id, same)),
        "added": (len(added), known(after_by_id, added)),
        "whole": (coverage(before), coverage(after)),
    }


def fisher_two_sided(liked_a: int, rated_a: int, liked_b: int, rated_b: int) -> float:
    """Exact two-sided p-value for the like rates of two groups (Fisher's exact test)."""
    likes, total = liked_a + liked_b, rated_a + rated_b

    def probability(x: int) -> float:
        return comb(rated_a, x) * comb(rated_b, likes - x) / comb(total, likes)

    observed = probability(liked_a)
    low, high = max(0, likes - rated_b), min(rated_a, likes)
    p_value = sum(p for x in range(low, high + 1) if (p := probability(x)) <= observed * (1 + 1e-9))
    return min(1.0, p_value)


def format_p(p_value: float) -> str:
    return "<0.001" if p_value < 0.001 else f"{p_value:.3f}"


def pct(part: int, whole: int) -> str:
    return f"{int(100 * part / whole + 0.5)}%" if whole else "n/a"


def share(part: int, whole: int) -> str:
    return f"{part} ({pct(part, whole)})"


def ratio(part: int, whole: int) -> str:
    return f"{part}/{whole} ({pct(part, whole)})"


def table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def like_table(
    label: str,
    rows: list[tuple[str, int, int]],
    hidden_ratings: int,
    hidden_groups: int,
    min_rated: int,
    all_rated: int,
    all_liked: int,
) -> str:
    """Like rates with `p vs rest`: Fisher's exact test of the group against every other rated event.

    A group that only says a value is missing ("(not given)", "not given") gets no p-value.
    """

    def p_cell(name: str, rated: int, liked: int) -> str:
        if name in (NOT_GIVEN, "not given") or rated == all_rated:
            return "-"
        return format_p(fisher_two_sided(liked, rated, all_liked - liked, all_rated - rated))

    text = table(
        [label, "Rated", "Liked", "Like rate", "p vs rest"],
        [(name, rated, liked, pct(liked, rated), p_cell(name, rated, liked)) for name, rated, liked in rows],
    )
    if hidden_groups:
        text += f"\n\n{hidden_ratings} further ratings in {hidden_groups} groups with fewer than {min_rated} ratings are not shown."
    return text


def render_report(
    after: Sequence[EventRecord],
    ratings: Mapping[str, str],
    before: Sequence[EventRecord] | None = None,
    deprioritized_themes: Sequence[str] = (),
    min_rated: int = 5,
    today: date | None = None,
) -> str:
    today = today or date.today()
    ids = {record.event_id for record in after}
    rated_ids = [event_id for event_id in ratings if event_id in ids]
    likes = sum(ratings[event_id] == "like" for event_id in rated_ids)
    known, total = coverage(after)
    parts = [
        f"# Findings data, {today.isoformat()}",
        f"- Events: {total}\n- Rated: {len(rated_ids)} (liked {likes}, disliked {len(rated_ids) - likes})\n- Price given: {share(known, total)}",
    ]

    if before is not None:
        compared = compare_cohorts(before, after, rated_ids)
        rated_n, rated_before, rated_after = compared["rated"]
        same_n, same_before, same_after = compared["same"]
        added_n, added_known = compared["added"]
        (whole_before_known, whole_before_total), (whole_after_known, whole_after_total) = compared["whole"]
        parts.append(
            "## Price coverage, before and after\n\n"
            + table(
                ["Population", "Events", "Price given before", "Price given now"],
                [
                    ("Rated events that existed before", rated_n, share(rated_before, rated_n), share(rated_after, rated_n)),
                    ("Events that existed before", same_n, share(same_before, same_n), share(same_after, same_n)),
                    ("Events added since", added_n, "-", share(added_known, added_n)),
                    (
                        "Whole dataset (different populations)",
                        f"{whole_before_total} -> {whole_after_total}",
                        share(whole_before_known, whole_before_total),
                        share(whole_after_known, whole_after_total),
                    ),
                ],
            )
        )

    now_by_source = coverage_by_source(after)
    before_by_source = coverage_by_source(before) if before is not None else {}
    source_rows = []
    for source in sorted(now_by_source, key=lambda name: (-now_by_source[name][1], name)):
        row = [source]
        if before is not None:
            row.append(ratio(*before_by_source[source]) if source in before_by_source else "-")
        row.append(ratio(*now_by_source[source]))
        source_rows.append(row)
    headers = ["Source"] + (["Price given before"] if before is not None else []) + ["Price given now"]
    parts.append("## Price coverage by source\n\n" + table(headers, source_rows))

    sections = (
        ("Like rate by source", "Source", atomic_sources, min_rated),
        ("Like rate by theme", "Theme", lambda record: [record.theme.strip() or NOT_GIVEN], min_rated),
        ("Like rate by venue", "Venue", lambda record: [record.venue.strip() or NOT_GIVEN], min_rated),
        ("Like rate by price", "Price", lambda record: ["given" if price_known(record) else "not given"], 1),
    )
    for title, label, groups, threshold in sections:
        rows, hidden_ratings, hidden_groups = like_rates(after, ratings, groups, threshold)
        parts.append(f"## {title}\n\n" + like_table(label, rows, hidden_ratings, hidden_groups, threshold, len(rated_ids), likes))

    if deprioritized_themes:
        themes = set(deprioritized_themes)
        rows, _, _ = like_rates(after, ratings, lambda record: ["together"] if record.theme.strip() in themes else [])
        rated, liked = (rows[0][1], rows[0][2]) if rows else (0, 0)
        p_text = ""
        if rated and rated < len(rated_ids):
            p_text = f", p vs rest {format_p(fisher_two_sided(liked, rated, likes - liked, len(rated_ids) - rated))}"
        parts.append(f"Themes the ranking pushes down ({', '.join(sorted(themes))}), together: {rated} rated, {liked} liked{p_text}.")
    return "\n\n".join(parts) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print the aggregate tables behind the README's Findings section.")
    parser.add_argument("--workbook", type=Path, default=None, help="Default: storage.processed_path from settings.yaml.")
    parser.add_argument("--ratings", type=Path, default=DEFAULT_RATINGS, help="Ratings export JSON (event_id, rating).")
    parser.add_argument("--before-workbook", type=Path, default=None, help="An earlier copy of the processed workbook.")
    parser.add_argument("--min-rated", type=int, default=5, help="Smallest number of ratings for a theme or venue to be shown.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = load_settings(CONFIG_PATH)
    workbook = args.workbook or PROJECT_ROOT / settings["storage"]["processed_path"]
    after = load_records(workbook)
    before = load_records(args.before_workbook) if args.before_workbook else None
    if not after:
        print(f"No records in {workbook}", file=sys.stderr)
        return 1
    ratings = load_ratings(args.ratings)
    sys.stdout.reconfigure(encoding="utf-8")
    print(
        render_report(
            after,
            ratings,
            before=before,
            deprioritized_themes=settings.get("collection", {}).get("deprioritized_themes", []),
            min_rated=args.min_rated,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
