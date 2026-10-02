"""Canonical event categories shared by every source.

Each source labels its events in its own words and language: "Concert" and
"Exhibition" on explorenicecotedazur, "Récital" and "Rencontre" at the
Opéra, a list of criteria chips ("Cultural", "Sports and recreation", ...)
on the Tourism System sites. This module maps those labels onto one small
taxonomy so the workbook speaks one vocabulary and `settings.yaml` can pick
categories without knowing each site's wording.

A label nothing here recognises is kept as the source wrote it and counts
as "Other" for filtering, so a new label shows up in the workbook (and can
be added below) instead of being silently renamed.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

# Order is precedence: when one event carries several recognisable labels
# ("Festival" and "Concert" chips), the first category listed wins.
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Concert": ("concert", "concerts", "recital", "recitals", "gig", "gigs"),
    "Festival": ("festival", "festivals", "fete", "fetes", "carnaval", "carnival", "festivities", "festivites"),
    "Show": (
        "show", "shows", "spectacle", "spectacles", "theatre", "theater", "dance", "danse", "ballet",
        "opera", "operas", "humour", "humor", "comedy", "cirque", "circus", "cinema", "film", "films",
        "screening", "projection",
    ),
    "Exhibition": ("exhibition", "exhibitions", "exposition", "expositions", "expo", "expos", "museum", "musee", "gallery", "galerie"),
    "Gastronomy": (
        "gastronomy", "gastronomie", "gastronomic", "gastronomique", "food", "tasting", "degustation",
        "wine", "wines", "vin", "vins", "culinary", "culinaire", "terroir",
    ),
    "Market": (
        "market", "markets", "marche", "marches", "flea", "brocante", "brocantes", "vide", "braderie",
        "fair", "fairs", "foire", "foires", "salon", "commercial", "sale", "sales", "soldes", "clearance",
    ),
    "Sport": (
        "sport", "sports", "sporting", "sportif", "sportive", "running", "race", "races", "course",
        "trail", "marathon", "match", "tournament", "tournoi", "regatta", "regate", "cycling",
        "cyclisme", "golf", "tennis", "football", "rugby", "swimming", "natation",
    ),
}

CATEGORIES: tuple[str, ...] = tuple(CATEGORY_KEYWORDS)
OTHER = "Other"

# Whole labels whose words point at the wrong category, checked before the
# keyword lists. Keys are the label folded to lowercase words.
LABEL_OVERRIDES: dict[str, str] = {
    # A trade fair or salon ("Annual Autumn Fair", "Foire du Village"); the
    # word "show" alone would make it a Show.
    "fair or show": "Market",
}

# Categories the Tourism System sites (Cannes, Menton) file under their
# CULTURAL or ENTERTAINMENT/RECREATION listing types. Asking only for these
# keeps the crawl to the detail pages it already opened for concerts.
CULTURAL_CATEGORIES = frozenset({"Concert", "Festival", "Show", "Exhibition"})

_WORD = re.compile(r"[a-z]+")


def _folded_words(label: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii").lower()
    return _WORD.findall(folded)


def canonical_category(label: str) -> str:
    """The canonical category a source label belongs to, or "" if none fits."""
    ordered = _folded_words(label or "")
    override = LABEL_OVERRIDES.get(" ".join(ordered))
    if override:
        return override
    words = set(ordered)
    for category, keywords in CATEGORY_KEYWORDS.items():
        if words.intersection(keywords):
            return category
    return ""


def normalize_category(label: str) -> str:
    """The canonical category for `label`, or the label itself (stripped) if unknown."""
    return canonical_category(label) or (label or "").strip()


def pick_category(labels: Iterable[str]) -> tuple[str, str]:
    """Choose one category from a list of chips; return (category, chip it came from).

    The chip whose canonical category ranks highest wins. With no
    recognisable chip the first non-empty one is kept as-is, so the record
    still says something ("Cultural") rather than nothing.
    """
    labels = [label.strip() for label in labels if label and label.strip()]
    best: tuple[int, str, str] | None = None
    for label in labels:
        category = canonical_category(label)
        if category:
            rank = CATEGORIES.index(category)
            if best is None or rank < best[0]:
                best = (rank, category, label)
    if best is not None:
        return best[1], best[2]
    return (labels[0], labels[0]) if labels else ("", "")


def parse_category_filter(value: str | Iterable[str] | None) -> frozenset[str] | None:
    """Turn the `categories` setting into the set of wanted categories.

    None or "all" mean no filter (None). A single name or a list of names
    is checked against CATEGORIES plus "Other", case-insensitively, so a
    typo in settings.yaml fails the run instead of quietly collecting
    nothing. An empty list is an error too: it reads as "nothing", and
    collecting everything instead would be the opposite surprise.
    """
    if value is None:
        return None
    names = [value] if isinstance(value, str) else list(value)
    names = [str(name).strip() for name in names if name is not None and str(name).strip()]
    if not names:
        raise ValueError("No categories given; list some or write 'all'")
    if any(name.lower() in ("all", "*") for name in names):
        return None

    known = {category.lower(): category for category in (*CATEGORIES, OTHER)}
    unknown = [name for name in names if name.lower() not in known]
    if unknown:
        raise ValueError(f"Unknown categor{'y' if len(unknown) == 1 else 'ies'} {unknown}; choose from {list(known.values())} or 'all'")
    return frozenset(known[name.lower()] for name in names)


def category_matches(label: str, wanted: frozenset[str] | None) -> bool:
    """True if a record labelled `label` belongs to one of the wanted categories."""
    if wanted is None:
        return True
    return (canonical_category(label) or OTHER) in wanted


def only_cultural(wanted: frozenset[str] | None) -> bool:
    """True if every wanted category is one the cultural listing types cover."""
    return wanted is not None and wanted <= CULTURAL_CATEGORIES
