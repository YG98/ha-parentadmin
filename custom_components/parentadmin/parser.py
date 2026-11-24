"""HTML parser for the ParentAdmin child diary page.

Kept free of Home Assistant imports so it can be tested on its own
(see tools/test_parser.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

_TIME = r"\d{1,2}:\d{2}\s*[ap]m"
_SUBTITLE_RE = re.compile(rf"^\s*({_TIME})(?:\s*[-\u2013]\s*(.*))?$", re.I | re.S)
_TIME_ONLY_RE = re.compile(rf"^\s*({_TIME})\s*$", re.I)
_ML_RE = re.compile(r"(\d+(?:\.\d+)?)\s*ml", re.I)
_HRS_RE = re.compile(r"(\d+)\s*h", re.I)
_MINS_RE = re.compile(r"(\d+)\s*m", re.I)
_NAME_RE = re.compile(r"^(.+?)['\u2019]s$")


def _parse_time(value: str) -> time | None:
    try:
        return datetime.strptime(value.replace(" ", "").upper(), "%I:%M%p").time()
    except ValueError:
        return None


@dataclass
class DiaryEntry:
    """One row in the child diary."""

    kind: str  # check-in, food, drink, nappy, sleep, photo, ...
    title: str  # Snack, Lunch, Water, Nappy, Sleep, ...
    figure: str  # "100", "30ml", "Wet", "1Hrs 30Mins", "In", ""
    start: time | None
    end: time | None
    detail: str
    photos: list[str] = field(default_factory=list)

    @property
    def percent(self) -> int | None:
        """Percentage eaten, for food entries."""
        return int(self.figure) if self.figure.isdigit() else None

    @property
    def millilitres(self) -> float | None:
        """Volume, for drink entries."""
        match = _ML_RE.search(self.figure)
        return float(match.group(1)) if match else None

    @property
    def minutes(self) -> int | None:
        """Duration in minutes, for sleep entries."""
        hrs = _HRS_RE.search(self.figure)
        mins = _MINS_RE.search(self.figure)
        if not hrs and not mins:
            return None
        return (int(hrs.group(1)) if hrs else 0) * 60 + (int(mins.group(1)) if mins else 0)


def is_login_page(html: str) -> bool:
    """Return True if the HTML is the login form (i.e. we are logged out)."""
    return 'name="uemail"' in html or "name='uemail'" in html


def _text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


def _child_name(soup: BeautifulSoup) -> str | None:
    strings = list(soup.stripped_strings)
    for idx, value in enumerate(strings):
        if value == "Child Diary" and idx > 0:
            match = _NAME_RE.match(strings[idx - 1])
            if match:
                return match.group(1).strip()
    return None


def parse_diary(html: str, base_url: str) -> tuple[str | None, list[DiaryEntry]]:
    """Parse the diary page into (child name, entries in page order)."""
    soup = BeautifulSoup(html, "html.parser")
    entries: list[DiaryEntry] = []

    for row in soup.select(".cdbreakdown > .row-entry-edit"):
        kind = next((c for c in row.get("class", []) if c != "row-entry-edit"), "unknown")
        content = row.select_one(".bd-content")
        if content is None:
            continue

        subtitle = _text(content.select_one(":scope > .subtitle"))
        start = end = None
        detail = subtitle
        if match := _SUBTITLE_RE.match(subtitle):
            start = _parse_time(match.group(1))
            detail = (match.group(2) or "").strip()
            # Sleep rows are "11:30am - 1:00pm": the detail is really an end time.
            if end_match := _TIME_ONLY_RE.match(detail):
                end = _parse_time(end_match.group(1))
                detail = ""

        entries.append(
            DiaryEntry(
                kind=kind,
                title=_text(content.select_one(":scope > .title")),
                figure=_text(content.select_one(".bd-figure")),
                start=start,
                end=end,
                detail=detail,
                photos=[
                    urljoin(base_url, img["src"])
                    for img in row.select('img[src*="content/child"]')
                    if img.get("src")
                ],
            )
        )

    return _child_name(soup), entries
