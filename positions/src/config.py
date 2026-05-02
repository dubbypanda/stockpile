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
    sheet_id: str
    csv: str | None


def get_all_accounts(brokerage_filter: str | None = None) -> list[AccountConfig]:
    """Return all configured accounts, optionally filtered by brokerage."""
    results = []
    for entry in _cfg.get("accounts", []):
        brokerage = entry.get("brokerage", "").lower()
        sheet_id = entry.get("sheet_id", "")
        csv_raw = entry.get("csv") or None
        csv = str(_REPO_ROOT / csv_raw) if csv_raw else None
        if not brokerage or not sheet_id:
            continue
        if brokerage_filter and brokerage != brokerage_filter.lower():
            continue
        results.append(AccountConfig(brokerage=brokerage, sheet_id=sheet_id, csv=csv))
    return results


_paths = _cfg.get("paths", {})
CREDS_PATH = Path(_paths.get("credentials", "~/.config/google-sheets-oauth.json")).expanduser()
TOKEN_PATH = Path(_paths.get("token", "~/.config/google-sheets-token.json")).expanduser()
