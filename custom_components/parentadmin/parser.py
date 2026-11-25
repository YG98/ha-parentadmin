"""HTML parser for the ParentAdmin child diary page.

Kept free of Home Assistant imports so it can be tested on its own
(see tools/test_parser.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from hashlib import sha1
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


# ---------------------------------------------------------------------------
# Account pages
# ---------------------------------------------------------------------------

_MONEY_RE = re.compile(r"(-)?\s*£\s*([\d,]+(?:\.\d{1,2})?)")
_DATE_FORMATS = ("%d %b %Y", "%d %B %Y", "%d/%m/%Y")


def _money(text: str | None) -> float | None:
    match = _MONEY_RE.search(text or "")
    if not match:
        return None
    value = float(match.group(2).replace(",", ""))
    return -value if match.group(1) else value


def _parse_date(text: str | None) -> date | None:
    text = re.sub(r"\s+", " ", (text or "").strip())
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _first_string(el) -> str:
    if el is None:
        return ""
    return next((s.strip() for s in el.strings if s.strip()), "")


def _classes(el) -> list[str]:
    return list(el.get("class", [])) if el is not None else []


@dataclass
class Invoice:
    """One row of Invoice History."""

    period: str
    issue_date: date | None
    number: str
    total: float | None


def parse_invoices(html: str) -> list[Invoice]:
    """Invoices, newest first (the order the site lists them)."""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.tablesaw tbody tr") or soup.select("table tbody tr")
    invoices: list[Invoice] = []
    for tr in rows:
        cells = tr.find_all("td")
        if len(cells) < 4:
            continue
        number = _text(cells[2])
        if not number:
            continue
        invoices.append(
            Invoice(
                period=_text(cells[0]),
                issue_date=_parse_date(_text(cells[1])),
                number=number,
                total=_money(_text(cells[3])),
            )
        )
    return invoices


@dataclass
class Transaction:
    """One row of Account History. Payments are positive, charges negative."""

    date: date | None
    description: str
    reference: str
    amount: float | None
    kind: str  # "payment" or "charge"


@dataclass
class Account:
    """Account balance (negative = in debit) and recent transactions."""

    balance: float | None
    transactions: list[Transaction] = field(default_factory=list)

    @property
    def last_payment(self) -> Transaction | None:
        return next((t for t in self.transactions if t.kind == "payment"), None)


def parse_account(html: str) -> Account:
    soup = BeautifulSoup(html, "html.parser")
    balance = None
    box = soup.select_one(".balance-col")
    if box is not None:
        amount_el = box.select_one("[class*='amt-']") or box
        balance = _money(_text(amount_el))
        negative = "amt-neg" in _classes(amount_el) or "balance-neg" in _classes(
            box.select_one("h4")
        )
        if balance is not None and negative and balance > 0:
            balance = -balance

    transactions: list[Transaction] = []
    for tr in soup.select("table.table-accounts tbody tr"):
        amount_el = tr.select_one(".amt-col a") or tr.select_one(".amt-col")
        if amount_el is None:
            continue
        amount = _money(_text(amount_el))
        is_payment = "amt-pos" in _classes(amount_el) or tr.select_one(".fa-arrow-right") is not None
        if amount is not None:
            amount = abs(amount) if is_payment else -abs(amount)
        transactions.append(
            Transaction(
                date=_parse_date(_first_string(tr.select_one(".date-col"))),
                description=_first_string(tr.select_one(".desc-col a") or tr.select_one(".desc-col")),
                reference=_text(tr.select_one(".ref-col")),
                amount=amount,
                kind="payment" if is_payment else "charge",
            )
        )
    return Account(balance=balance, transactions=transactions)


@dataclass
class BookingDay:
    """Booking for one weekday."""

    date: date
    hours: str | None  # "09:00-17:00"
    status: str  # booked, sick, absent, closed, none


def parse_booking(html: str) -> dict[date, BookingDay]:
    soup = BeautifulSoup(html, "html.parser")
    days: dict[date, BookingDay] = {}
    for tr in soup.select("table tbody tr"):
        cells = tr.find_all("td")
        if len(cells) < 6:
            continue
        week = _parse_date(_first_string(cells[0]))
        if week is None:
            continue
        for offset in range(5):
            cell = cells[1 + offset]
            span = cell.select_one(".times")
            classes = _classes(cell) + _classes(span)
            hours = _text(span) or None
            if "closed" in classes:
                status = "closed"
            elif "sick" in classes:
                status = "sick"
            elif "absent" in classes:
                status = "absent"
            elif hours:
                status = "booked"
            else:
                status = "none"
            day = week + timedelta(days=offset)
            days[day] = BookingDay(date=day, hours=hours, status=status)
    return days


@dataclass
class FormsPage:
    """Accident / incident forms page."""

    count: int | None  # None = forms present but couldn't be counted
    signature: str  # changes whenever the page content changes


def parse_forms(html: str, heading_word: str = "Accident") -> FormsPage:
    soup = BeautifulSoup(html, "html.parser")
    heading = next(
        (h for h in soup.select("h1, h2, h3, h4, h5") if heading_word in h.get_text()), None
    )
    container = heading.parent if heading is not None else soup.body or soup
    text = _text(container)
    empty = re.search(r"\bNo\b[^.]*\brecorded\b", text, re.I) is not None
    rows = container.select("tbody tr")
    count = 0 if empty else (len(rows) if rows else None)
    return FormsPage(count=count, signature=sha1(text.encode()).hexdigest()[:16])


@dataclass
class Message:
    """One inbox message."""

    key: str
    sender: str
    subject: str
    preview: str
    received: str  # as shown, e.g. "12:34 24 Nov"


@dataclass
class Inbox:
    unread: list[Message]
    read_count: int


def parse_inbox(html: str) -> Inbox:
    soup = BeautifulSoup(html, "html.parser")
    unread: list[Message] = []
    read_count = 0
    for brick in soup.select(".col-md-9 .brick") or soup.select(".brick"):
        title = _text(brick.select_one("h4")).lower()
        messages = []
        for link in brick.select("a.feed-link"):
            if "feed-complete" in _classes(link):  # "Woo hoo! No unread messages" placeholder
                continue
            sender = _text(link.select_one(".feed-cname"))
            subject = _text(link.select_one(".feed-subject"))
            received = _text(link.select_one(".feed-datetime"))
            messages.append(
                Message(
                    key=sha1(f"{received}|{sender}|{subject}".encode()).hexdigest()[:16],
                    sender=sender,
                    subject=subject,
                    preview=_text(link.select_one(".feed-message"))[:200],
                    received=received,
                )
            )
        if "unread" in title:
            unread = messages
        elif "read" in title:
            read_count = len(messages)
    return Inbox(unread=unread, read_count=read_count)
