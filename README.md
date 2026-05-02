# stockpile

Monorepo of stock portfolio tools: position tracker, cost basis
charts, and shared parsing/finance utilities.

## Projects

- **shared** — pip-installable package (`stocks-shared`): CSV parsers
  (Schwab, Robinhood), Yahoo Finance helpers, FIFO analysis,
  Black-Scholes pricing
- **positions** — Google Sheets position tracker
- **cost-basis-charts** — Interactive cost basis vs. price charts
  (YouTube tutorial project)
- **google-sheets-setup** — Google Sheets API setup docs

## Using Claude Code with this repo

The easiest way to get any of these tools running is with a Claude
Code subscription. Clone the repo, open Claude Code in the project
directory, and ask it to help you configure and run the tool with
your own brokerage export. It can walk you through setup, fix any
issues, and add new features — no manual coding required. All of the
tools in this repo were built this way.

Get Claude Code at: https://claude.ai/code

Subscriptions start at $20/month (Pro plan). The Max plan ($100/month)
gives higher usage limits, which is useful for longer coding sessions.

## Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/) — fast Python package and project
  manager (replaces pip + venv)

## Installing Python

If you don't have Python 3.12+, the easiest way is to let `uv` manage
it for you:

```bash
uv python install 3.12
```

Or install manually from [python.org](https://www.python.org/downloads/)
and ensure `python3 --version` reports 3.12+.

## Installing uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

After installation, restart your terminal so `uv` is on your PATH.

## How the virtual environment works

This repo uses **uv workspaces**. The root `pyproject.toml` declares
all three sub-projects (`shared`, `positions`, `cost-basis-charts`) as
workspace members. When you run `uv sync`, uv:

1. Creates a single shared `.venv/` at the repo root
2. Installs all dependencies for every workspace member into it
3. Installs `shared` (the `stocks-shared` package) as an editable
   local package so changes to it are immediately reflected in the
   other projects

You never need to activate the virtual environment manually — `uv run`
handles that automatically.

## Setup

Clone the repo and sync dependencies (run once, and again after any
`pyproject.toml` change):

```bash
git clone https://github.com/medloh/stockpile.git
cd stockpile
uv sync
```

## Running the projects

Always use `uv run` from the **repo root**. This ensures the correct
virtual environment and the `stocks-shared` package are available
regardless of which sub-project you're running.

```bash
# Cost basis charts
uv run cost-basis-charts/run_charts.py

# Cost basis charts — single symbol only
uv run cost-basis-charts/run_charts.py --symbol SCHW

# Position tracker (Google Sheets)
uv run positions/run_tracker.py
```

**Do not** use `python` or `python3` directly — those will use the
system Python which doesn't have the project's dependencies installed.

## Configuration

Each sub-project has a `config.toml.example`. Copy it and fill in
your details:

```bash
# macOS / Linux / Git Bash
cp cost-basis-charts/config.toml.example cost-basis-charts/config.toml
cp positions/config.toml.example positions/config.toml

# Windows PowerShell or CMD
copy cost-basis-charts\config.toml.example cost-basis-charts\config.toml
copy positions\config.toml.example positions\config.toml
```

See the comments inside each file for what each field means.

Place your brokerage CSV exports in `input/` — both tools look there
by default. The `input/` directory is gitignored so your files stay
local.

## Adding new dependencies

To add a package to a specific sub-project:

```bash
uv add plotly --project cost-basis-charts
```

Then re-run `uv sync` to update the lockfile.

