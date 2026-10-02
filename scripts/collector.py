"""CLI entrypoint: run configured collectors and update the processed workbook."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.antibes import AntibesCollector
from collectors.base import BaseCollector
from collectors.cannes import CannesCollector
from collectors.explorenicecotedazur import ExploreNiceCoteDAzurCollector
from collectors.helloasso import HelloAssoCollector
from collectors.manual_events import ManualEventsCollector
from collectors.menton import MentonCollector
from collectors.opera_de_nice import OperaDeNiceCollector
from collectors.panda_events import PandaEventsCollector
from collectors.songkick import SongkickCollector
from core.config import load_settings
from core.deduplication import deduplicate_records, merge_cross_source_duplicates
from core.filters import drop_finished_events
from core.priority import sort_by_theme_priority
from core.storage import load_records, merge_records, save_records
from core.taxonomy import CATEGORIES, OTHER, parse_category_filter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"

COLLECTOR_REGISTRY: dict[str, type[BaseCollector]] = {
    "explorenicecotedazur": ExploreNiceCoteDAzurCollector,
    "songkick": SongkickCollector,
    "opera_de_nice": OperaDeNiceCollector,
    "helloasso": HelloAssoCollector,
    "panda_events": PandaEventsCollector,
    "manual_events": ManualEventsCollector,
    "cannes": CannesCollector,
    "antibes": AntibesCollector,
    "menton": MentonCollector,
}

# Sources whose collector takes a category_filter kwarg (they list mixed
# categories and need it to narrow down to the wanted ones). Songkick, Panda
# Events and HelloAsso are concert-only by nature and need no filter.
CATEGORY_FILTERED_SOURCES = {"explorenicecotedazur", "opera_de_nice", "cannes", "antibes", "menton"}


def configured_categories(settings: dict) -> str | list[str] | None:
    """The `collection.categories` setting, or the older single `category_filter`."""
    collection = settings.get("collection", {})
    if "categories" in collection:
        return collection["categories"]
    return collection.get("category_filter")


def build_collector(source_name: str, settings: dict, categories: list[str] | None = None) -> BaseCollector:
    """Instantiate a source's collector; `categories` overrides the settings."""
    collector_class = COLLECTOR_REGISTRY[source_name]
    if source_name in CATEGORY_FILTERED_SOURCES:
        wanted = categories if categories else configured_categories(settings)
        return collector_class(category_filter=wanted)
    if source_name == "helloasso":
        associations = settings.get("helloasso", {}).get("associations", [])
        return collector_class(association_slugs=associations)
    return collector_class()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Nice-area events into an Excel workbook.")
    parser.add_argument(
        "--source",
        choices=sorted(COLLECTOR_REGISTRY),
        action="append",
        help="Limit the run to one source (repeatable). Default: all sources in settings.yaml.",
    )
    parser.add_argument(
        "--category",
        action="append",
        help=f"Collect this category instead of settings.yaml's (repeatable): {', '.join(CATEGORIES)}, {OTHER} or all.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap the number of records per source.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = load_settings(CONFIG_PATH)
    sources = args.source or settings.get("sources", [])

    session = requests.Session()
    all_records = []

    # Fail on a misspelt category before any request goes out.
    wanted = parse_category_filter(args.category or configured_categories(settings))
    print(f"Categories: {', '.join(sorted(wanted)) if wanted else 'all'}")

    for source_name in sources:
        collector = build_collector(source_name, settings, categories=args.category)
        print(f"Collecting from {source_name}...")
        result = collector.collect(session, limit=args.limit)
        print(f"  {result.found} records, {result.errors} errors")
        for message in result.error_messages:
            print(f"  ERROR: {message}")
        all_records.extend(result.records)

    cross_source_result = merge_cross_source_duplicates(all_records)
    print(
        f"\nCollected {len(all_records)} records, "
        f"merged {cross_source_result.merged_groups} cross-source duplicates"
    )

    dedup_result = deduplicate_records(cross_source_result.records)
    print(f"{dedup_result.duplicates} exact duplicates within this run")

    raw_path = PROJECT_ROOT / settings["storage"]["raw_path"]
    processed_path = PROJECT_ROOT / settings["storage"]["processed_path"]
    deprioritized_themes = settings.get("collection", {}).get("deprioritized_themes", [])

    save_records(sort_by_theme_priority(dedup_result.records, deprioritized_themes), raw_path, workbook_kind="raw")
    print(f"Saved raw run to {raw_path}")

    upcoming_records, finished = drop_finished_events(dedup_result.records, date.today().isoformat())
    if finished:
        print(f"Skipped {finished} events that already ended")

    existing_records = load_records(processed_path)
    merged_records, counts = merge_records(existing_records, upcoming_records, run_sources=sources)
    merged_records = sort_by_theme_priority(merged_records, deprioritized_themes)
    save_records(merged_records, processed_path, workbook_kind="processed")
    print(
        f"Processed workbook: {len(merged_records)} total "
        f"({counts['new']} new, {counts['updated']} updated, {counts['existing']} unchanged, "
        f"{counts['absorbed']} duplicates absorbed) -> {processed_path}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
