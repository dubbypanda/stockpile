"""Load configuration from config.toml."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent.parent / "config.toml"
_REPO_ROOT = Path(__file__).parents[2]


def _load():
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


_cfg = _load()


@dataclass
class AccountConfig:
    brokerage: str
    csv: str | None
    symbols: list[str] | None  # None = chart all symbols in the CSV


def get_all_accounts(brokerage_filter: str | None = None) -> list[AccountConfig]:
    results = []
    for entry in _cfg.get("accounts", []):
        brokerage = entry.get("brokerage", "").lower()
        csv_raw = entry.get("csv") or None
        csv = str(_REPO_ROOT / csv_raw) if csv_raw else None
        symbols = entry.get("symbols") or None
        if not brokerage:
            continue
        if brokerage_filter and brokerage != brokerage_filter.lower():
            continue
        results.append(AccountConfig(brokerage=brokerage, csv=csv, symbols=symbols))
    return results


OUTPUT_DIR = _REPO_ROOT / _cfg.get("output", {}).get("dir", "charts")
