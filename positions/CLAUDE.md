# CLAUDE.md — positions

Claude Code instructions for the Google Sheets position tracker.

## Purpose

Turn a brokerage transaction CSV into a fully formatted Google Sheet —
stock positions, covered calls, sold puts, dividends, a P&L breakdown,
and a cross-position summary — with live prices from Yahoo Finance.

## Running the tool

Always run from the **repo root** using `uv run`:

```bash
uv run positions/run_tracker.py                       # all configured accounts
uv run positions/run_tracker.py --brokerage schwab    # one brokerage only
uv run positions/run_tracker.py --csv input/OTHER.csv # override the CSV path
uv run positions/run_tracker.py --list-accounts       # show account names
uv run positions/run_tracker.py --accounts fidelity_522 schwab556
```

Reads `positions/config.toml` (per-account Google Sheet IDs + CSV
paths). Supported brokerages: **Schwab, Robinhood, Fidelity, Merrill
Edge** — set `brokerage` in config to match the export. CSV parsers
come from the `stocks-shared` package (`shared/stocks_shared/parsers/`),
dispatched by `parsers.get_parser(brokerage)`.

`--accounts` selects by the optional `name` key in config.toml, which
defaults to the CSV's basename. Everything named runs in one process so
the Yahoo cache stays shared.

## The console

```bash
uv run streamlit run positions/run_console.py     # http://localhost:8502
```

`run_console.py` → `src/console_app.py`. Three panels: **Run Sheets**
(tick accounts, run, watch the output stream), **Merge Transactions**
(fold a new brokerage export into the CSV an account points at, with a
preview; each candidate row also carries its own archive and delete
buttons), and **History** (`src/history.py`).

History has two sources, deliberately. The console appends its own
actions — merges, archives, deletions, runs — to
`positions/console_history.jsonl` as JSON Lines; `history.record()`
swallows its own errors, because a failed log entry must never undo the
action it was describing. Runs started from the CLI never reach that
file, so `history.tracker_runs()` parses `positions/tracker.log` as
well. Both are gitignored.

The console never imports the tracker — a run shells out to
`run_tracker.py` so `sheets.configure()`'s module-global state lives and
dies in its own process. It reads `config.toml` and never writes it.

Merging lives in `shared/stocks_shared/csv_merge.py`, not here, because
it needs the same per-brokerage column knowledge the parsers have. Its
`_SPECS` table names each brokerage's date column, identity columns, and
volatile columns; when you change a parser's column handling, check that
table. Correctness is enforced by re-parsing the merged output and
requiring the transaction set to equal the union of both inputs — which
is why the writer does not have to reproduce Merrill's space padding or
Robinhood's embedded newlines byte-for-byte.

## Credentials & auth

Google Sheets OAuth client at `~/.config/google-sheets-oauth.json`
(setup steps in `../google-sheets-setup/`). The first run opens a
browser to authorize; subsequent runs are silent.

## Behavior notes

- The script deletes and recreates each ticker tab on every run; the
  Summary tabs are preserved.
- Multiple accounts run **serially**, not in parallel — the Google
  Sheets API quota and Yahoo's rate limit are per-project / per-IP, so
  serial avoids 429s. Prices and option chains are cached in memory
  across accounts, so each ticker is fetched once per run.
- Option market values use the Yahoo `(bid + ask) / 2` midpoint.

## Brokerage CSV input

Place exports in the repo-root `input/` directory (gitignored). Config
CSV paths resolve relative to the repo root. For a hand-written manual
format (when you lack a supported export), see
[../docs/stockpile-format.md](../docs/stockpile-format.md).
