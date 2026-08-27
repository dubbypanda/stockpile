"""Merge a fresh brokerage export into an existing transaction CSV.

Every brokerage export is a *full history* re-download, so merging one
into the file `positions/config.toml` points at means reconciling a large
overlap rather than appending a tail. Two things make that non-trivial:

1. **Volatile columns.** A row can repeat with a changed value that is not
   part of the transaction — Fidelity writes ``Cash Balance = Processing``
   for trades that have not settled and a real balance on the next export.
   Byte-exact dedupe would admit both copies and double the transaction.
   So rows are matched on *identity* columns only, and on a match the
   incoming row wins (the settled balance replaces ``Processing``).

2. **File shape.** Each brokerage writes a different dialect: Schwab is
   CRLF with every field quoted, Robinhood embeds newlines inside
   Description, Merrill space-pads its quoted fields, and Fidelity leads
   with blank lines and trails with a legal disclaimer block.

Byte-level fidelity on the way out is explicitly *not* a goal — Merrill's
space padding and Robinhood's embedded newlines will not survive a
``csv.writer`` round trip, and chasing that would buy nothing. Instead
:func:`merge_csv` re-parses its own output with the brokerage's real
parser and checks that the transactions the tracker will see are exactly
the union of the two inputs. That is the property that actually matters.

Usage::

    result = merge_csv("input/fidelity_522.csv", "input/fid2522.csv",
                       "fidelity")
    print(result.summary())        # nothing has been written yet
    Path("input/fidelity_522.csv").write_text(result.text, ...)
"""

from __future__ import annotations

import csv
import io
import re
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from stocks_shared.parsers import get_parser

_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
#: A data row's date column *starts* with the date. Anchoring matters:
#: Fidelity's footer line "Date downloaded 08/07/2026 10:16 am" lands in
#: column 0 and contains a date, but is not a transaction. Schwab's
#: "12/19/2022 as of 12/16/2022" still matches, as it must.
_DATE_START_RE = re.compile(r"^\s*\d{1,2}/\d{1,2}/\d{4}")


class MergeError(Exception):
    """Raised when a merge cannot be performed or fails verification."""


@dataclass(frozen=True)
class FileSpec:
    """Per-brokerage description of a transaction CSV's shape.

    Column names mirror the ones the matching parser reads in
    ``stocks_shared/parsers/`` — keep the two in step.
    """

    date_col: str
    #: Columns that together identify a transaction. Two rows agreeing on
    #: all of these are the same trade, even if other columns differ.
    identity_cols: tuple[str, ...]
    #: Columns a re-export may legitimately change for the same trade.
    #: Documentation for the reader — the code simply never matches on
    #: anything outside `identity_cols` — but they are what motivates the
    #: identity rule, so they are recorded rather than implied.
    volatile_cols: tuple[str, ...] = ()


# Derived from the parsers in stocks_shared/parsers/. The identity columns
# deliberately exclude free-text Description on brokerages where the symbol
# and numbers already pin the trade down; Robinhood is the exception —
# there Description *is* the option contract.
_SPECS: dict[str, FileSpec] = {
    # parsers/schwab.py — dates can read "12/19/2022 as of 12/16/2022";
    # the raw string is stable across exports, so it is matched verbatim.
    "schwab": FileSpec(
        date_col="Date",
        identity_cols=("Date", "Action", "Symbol", "Quantity", "Price",
                       "Amount"),
    ),
    # parsers/robinhood.py — Description carries the contract, and stock
    # rows wrap it across embedded newlines.
    "robinhood": FileSpec(
        date_col="Activity Date",
        identity_cols=("Activity Date", "Instrument", "Description",
                       "Trans Code", "Quantity", "Price", "Amount"),
    ),
    # parsers/fidelity.py — Cash Balance is "Processing" until settlement,
    # and Settlement Date fills in at the same time.
    "fidelity": FileSpec(
        date_col="Run Date",
        identity_cols=("Run Date", "Action", "Symbol", "Quantity",
                       "Price ($)", "Amount ($)"),
        volatile_cols=("Cash Balance ($)", "Settlement Date"),
    ),
    # parsers/merrill.py — header is space-padded ("Trade Date" ,"...") and
    # ends in a blank column; both are handled by stripping.
    "merrill": FileSpec(
        date_col="Trade Date",
        identity_cols=("Trade Date", "Description", "Symbol/ CUSIP",
                       "Quantity", "Price", "Amount"),
    ),
}

SUPPORTED_BROKERAGES = tuple(sorted(_SPECS))


def get_spec(brokerage: str) -> FileSpec:
    try:
        return _SPECS[brokerage.lower()]
    except KeyError:
        raise MergeError(
            f"No merge spec for brokerage {brokerage!r}. "
            f"Supported: {', '.join(SUPPORTED_BROKERAGES)}"
        ) from None


# ── Reading ────────────────────────────────────────────────────────────────

@dataclass
class ParsedFile:
    """A transaction CSV split into the parts a merge needs."""

    header: list[str]
    rows: list[list[str]]
    #: Raw lines above the header (Fidelity's blank lead-in), reproduced
    #: verbatim on output.
    preamble: list[str]
    has_bom: bool
    line_terminator: str
    quote_all: bool
    path: Path

    def col(self, name: str) -> int:
        """Index of a column, matched on its stripped name."""
        for i, h in enumerate(self.header):
            if h.strip() == name:
                return i
        raise MergeError(
            f"{self.path.name}: expected column {name!r}, found "
            f"{[h.strip() for h in self.header]}"
        )


def read_file(path: str | Path, spec: FileSpec) -> ParsedFile:
    """Read a transaction CSV into header + data rows.

    Rows above the header line are preserved as a preamble; rows below the
    data whose date column does not parse as a date (Fidelity's disclaimer)
    are dropped.
    """
    path = Path(path)
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    line_terminator = "\r\n" if "\r\n" in text else "\n"

    # csv.reader, not a line split: Robinhood embeds newlines in fields, so
    # a "line" is not a record.
    all_rows = list(csv.reader(io.StringIO(text)))

    hdr_i = next(
        (i for i, r in enumerate(all_rows)
         if r and r[0].strip() == spec.date_col),
        None,
    )
    if hdr_i is None:
        raise MergeError(
            f"{path.name}: header row starting with {spec.date_col!r} not found"
        )

    header = all_rows[hdr_i]
    date_i = next(i for i, h in enumerate(header) if h.strip() == spec.date_col)
    # A data row has every column *and* opens its date column with a date.
    # Either test alone would drop Fidelity's one-field disclaimer lines;
    # together they also reject anything else trailing the data block.
    rows = [
        r for r in all_rows[hdr_i + 1:]
        if len(r) == len(header) and _DATE_START_RE.match(r[date_i])
    ]

    # Preamble lines are reproduced verbatim, so take them from the raw text
    # rather than round-tripping them through the csv writer.
    preamble = text.splitlines()[:hdr_i] if hdr_i else []

    # Quote style: brokerages either quote every field (Schwab, Robinhood,
    # Merrill) or only what needs it (Fidelity). Judge by the header, which
    # is always plain text and never needs quoting on its own merits.
    hdr_line = text.splitlines()[hdr_i] if hdr_i < len(text.splitlines()) else ""
    quote_all = hdr_line.lstrip().startswith('"')

    return ParsedFile(
        header=header, rows=rows, preamble=preamble, has_bom=has_bom,
        line_terminator=line_terminator, quote_all=quote_all, path=path,
    )


# ── Merging ────────────────────────────────────────────────────────────────

def _sort_key(row: list[str], date_i: int):
    m = _DATE_RE.search(row[date_i]) if len(row) > date_i else None
    if not m:
        return datetime.min
    mm, dd, yyyy = (int(g) for g in m.groups())
    try:
        return datetime(yyyy, mm, dd)
    except ValueError:
        return datetime.min


def norm(value: str) -> str:
    """Canonical form of a cell, for comparing rows across two exports.

    Numbers are compared by value, not spelling: the same trade can come
    back as ``16.30`` or ``16.3``, and money as ``$1,234.50`` or
    ``(1234.50)``. Left as strings this bites twice — a cosmetic
    difference is reported to the user as a real change, and an identity
    column spelled differently makes a row look brand new, duplicating a
    transaction. Non-numeric cells are returned stripped, unchanged.
    """
    s = value.strip()
    if not s:
        return ""
    t = s.replace("$", "").replace(",", "").strip()
    negated = t.startswith("(") and t.endswith(")")   # (1234.50) == -1234.50
    if negated:
        t = t[1:-1].strip()
    try:
        f = float(t)
    except ValueError:
        return s
    return repr(-f if negated else f)


def _same_row(a: list[str], b: list[str]) -> bool:
    return [norm(c) for c in a] == [norm(c) for c in b]


def _keys(rows: list[list[str]], idx: list[int]) -> list[tuple]:
    """Identity key per row, disambiguated by occurrence.

    Two genuinely identical trades on the same day are not duplicates, so
    the nth occurrence of an identity only ever matches the nth occurrence
    in the other file.
    """
    seen: dict[tuple, int] = {}
    out = []
    for row in rows:
        ident = tuple(norm(row[i]) if i < len(row) else "" for i in idx)
        n = seen.get(ident, 0)
        seen[ident] = n + 1
        out.append(ident + (n,))
    return out


@dataclass
class MergeResult:
    """Outcome of a merge. Computes; does not write."""

    text: str
    added: list[list[str]] = field(default_factory=list)
    replaced: list[tuple[list[str], list[str]]] = field(default_factory=list)
    unchanged: list[list[str]] = field(default_factory=list)
    existing_only: list[list[str]] = field(default_factory=list)
    header: list[str] = field(default_factory=list)
    txn_before: int = 0
    txn_after: int = 0

    @property
    def total_rows(self) -> int:
        return (len(self.added) + len(self.replaced)
                + len(self.unchanged) + len(self.existing_only))

    def summary(self) -> str:
        return (
            f"{len(self.added)} added, {len(self.replaced)} replaced, "
            f"{len(self.unchanged)} unchanged, "
            f"{len(self.existing_only)} only in existing "
            f"-> {self.total_rows} rows; "
            f"transactions {self.txn_before} -> {self.txn_after}"
        )


def render(pf: ParsedFile, rows: list[list[str]]) -> str:
    """Serialize a header + rows back to CSV in the source file's dialect."""
    buf = io.StringIO()
    writer = csv.writer(
        buf,
        lineterminator=pf.line_terminator,
        quoting=csv.QUOTE_ALL if pf.quote_all else csv.QUOTE_MINIMAL,
    )
    writer.writerow(pf.header)
    writer.writerows(rows)
    body = buf.getvalue()
    if pf.preamble:
        body = pf.line_terminator.join(pf.preamble) + pf.line_terminator + body
    return ("﻿" if pf.has_bom else "") + body


def _txn_counts(path: str | Path, brokerage: str) -> Counter:
    """Every transaction the brokerage parser finds, counted.

    A Counter rather than a set: duplicate transactions are exactly the
    failure this guards against, and a set would hide them.
    """
    ticker_txns, _ = get_parser(brokerage)(str(path))
    return Counter(
        (ticker,) + tuple(str(c) for c in row)
        for ticker, rows in ticker_txns.items()
        for row in rows
    )


def merge_csv(existing_path: str | Path, incoming_path: str | Path,
              brokerage: str, verify: bool = True) -> MergeResult:
    """Merge ``incoming_path`` into ``existing_path`` without writing.

    Rows are matched on the brokerage's identity columns; a match takes the
    incoming version. Rows found only in the existing file are kept — some
    of these files carry hand-backfilled history that no export contains.
    Output is sorted newest-first.

    With ``verify`` (the default) the merged text is re-parsed with the
    brokerage's own parser and checked to contain exactly the union of the
    two inputs' transactions; a mismatch raises :class:`MergeError`.
    """
    spec = get_spec(brokerage)
    existing = read_file(existing_path, spec)
    incoming = read_file(incoming_path, spec)

    if [h.strip() for h in existing.header] != [h.strip() for h in incoming.header]:
        raise MergeError(
            f"Header mismatch — {existing.path.name} and {incoming.path.name} "
            f"are not the same export format.\n"
            f"  existing: {[h.strip() for h in existing.header]}\n"
            f"  incoming: {[h.strip() for h in incoming.header]}"
        )

    idx = [existing.col(c) for c in spec.identity_cols]
    date_i = existing.col(spec.date_col)

    old_keys = _keys(existing.rows, idx)
    new_keys = _keys(incoming.rows, idx)
    old_by_key = dict(zip(old_keys, existing.rows))
    new_key_set = set(new_keys)

    result = MergeResult(text="", header=existing.header)
    merged: list[list[str]] = []

    # Incoming order first — it is the newer, more complete view.
    for key, row in zip(new_keys, incoming.rows):
        prior = old_by_key.get(key)
        if prior is None:
            result.added.append(row)
        elif _same_row(prior, row):
            result.unchanged.append(row)
        else:
            result.replaced.append((prior, row))
        merged.append(row)

    # Then anything the export does not know about (hand-backfilled rows).
    for key, row in zip(old_keys, existing.rows):
        if key not in new_key_set:
            result.existing_only.append(row)
            merged.append(row)

    # Stable, so same-date rows keep the order established above.
    merged.sort(key=lambda r: _sort_key(r, date_i), reverse=True)
    result.text = render(existing, merged)

    if verify:
        _verify(result, existing_path, incoming_path, brokerage)
    return result


def _verify(result: MergeResult, existing_path, incoming_path,
            brokerage: str) -> None:
    """Check the merged output through the brokerage's real parser.

    Both inputs are full-history exports of the same account, so merging
    them should yield, for each distinct transaction, ``max`` of the two
    counts — enough copies to satisfy whichever input saw more, and no
    more. Counting rather than set-comparing is what catches a transaction
    written twice, which is the costly failure here: the sheet would book
    the trade's P&L twice and nothing downstream would flag it.

    This is also what makes byte-level dialect fidelity unnecessary. What
    matters is that the tracker reads the same trades back out, so the
    writer is free to normalize Merrill's space padding away.
    """
    before = _txn_counts(existing_path, brokerage)
    incoming_txns = _txn_counts(incoming_path, brokerage)
    expected = Counter({
        txn: max(before[txn], incoming_txns[txn])
        for txn in set(before) | set(incoming_txns)
    })

    with tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    ) as fh:
        fh.write(result.text)
        tmp = fh.name
    try:
        after = _txn_counts(tmp, brokerage)
    finally:
        Path(tmp).unlink(missing_ok=True)

    lost = expected - after          # Counter subtraction keeps positives only
    extra = after - expected
    if lost or extra:
        detail = []
        if lost:
            txn, n = sorted(lost.items())[0]
            detail.append(f"  {sum(lost.values())} transaction(s) lost, "
                          f"e.g. {n}x {txn}")
        if extra:
            txn, n = sorted(extra.items())[0]
            detail.append(f"  {sum(extra.values())} transaction(s) duplicated or "
                          f"invented, e.g. {n} extra {txn}")
        raise MergeError(
            "Merged output failed parser verification — refusing to write.\n"
            + "\n".join(detail)
        )

    result.txn_before = sum(before.values())
    result.txn_after = sum(after.values())


# ── Account routing ────────────────────────────────────────────────────────

def detect_brokerage(path: str | Path) -> str | None:
    """Guess a CSV's brokerage from its header row.

    Each brokerage's date column name is unique across the four, so the
    header alone identifies the format.
    """
    try:
        text = Path(path).read_bytes()[:8192].decode("utf-8-sig", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        first = line.split(",", 1)[0].strip().strip('"').strip()
        for brokerage, spec in _SPECS.items():
            if first == spec.date_col:
                return brokerage
    return None


def file_tickers(path: str | Path, brokerage: str) -> set[str]:
    """Tickers the brokerage parser finds in a file (empty on failure)."""
    try:
        ticker_txns, _ = get_parser(brokerage)(str(path))
        return set(ticker_txns)
    except Exception:
        return set()
