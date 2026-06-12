import pandas as pd

from stocks_shared.schwab_live import _parse_schwab_candles


def test_parse_schwab_candles_normalizes_timezone_aware_strings_to_utc_epoch():
    rows = _parse_schwab_candles({
        "candles": [
            {
                "datetime": "2026-06-12T16:00:00-04:00",
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "volume": 100,
            }
        ]
    })

    assert len(rows) == 1
    assert rows[0]["time"] == int(pd.Timestamp("2026-06-12T20:00:00Z").timestamp())
