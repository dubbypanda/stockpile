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
    #: Human label, from the optional `name` key in config.toml. Several
    #: accounts share a brokerage, so brokerage alone cannot tell them
    #: apart in a picker; falls back to the CSV's basename.
    name: str = ""

    def __post_init__(self):
        # Fall back to the CSV's basename: already unique across the
        # configured accounts, ASCII (these get typed as --accounts
        # arguments and printed to a cp1252 console), and short.
        if not self.name:
            self.name = Path(self.csv).stem if self.csv else self.sheet_id[:8]


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
        results.append(AccountConfig(brokerage=brokerage, sheet_id=sheet_id,
                                     csv=csv, name=entry.get("name", "").strip()))
    return results


_paths = _cfg.get("paths", {})
CREDS_PATH = Path(_paths.get("credentials", "~/.config/google-sheets-oauth.json")).expanduser()
TOKEN_PATH = Path(_paths.get("token", "~/.config/google-sheets-token.json")).expanduser()
