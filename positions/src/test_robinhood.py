"""Tests for the Robinhood CSV parser."""

import pytest
from stocks_shared.parsers.robinhood import (
    parse_dollar,
    parse_date,
    _parse_opt_description,
    _parse_qty,
    _build_opt_symbol,
    _parse_rows_to_transactions,
    parse_all_transactions,
)


# ── parse_dollar ──────────────────────────────────────────────────────────────

class TestParseDollar:
    def test_positive(self):
        assert parse_dollar("$4,649.77") == 4649.77

    def test_negative_parens(self):
        assert parse_dollar("($3,811.80)") == -3811.80

    def test_no_dollar_sign(self):
        assert parse_dollar("254.12") == 254.12

    def test_empty(self):
        assert parse_dollar("") is None

    def test_zero(self):
        assert parse_dollar("$0.00") == 0.0

    def test_small_amount(self):
        assert parse_dollar("$0.01") == 0.01

    def test_negative_small(self):
        assert parse_dollar("($72.40)") == -72.40


# ── parse_date ────────────────────────────────────────────────────────────────

class TestParseDate:
    def test_single_digit_month_and_day(self):
        assert parse_date("4/7/2025") == "04/07/2025"

    def test_double_digit_month_and_day(self):
        assert parse_date("12/19/2025") == "12/19/2025"

    def test_mixed(self):
        assert parse_date("1/16/2026") == "01/16/2026"

    def test_single_digit_day(self):
        assert parse_date("4/22/2026") == "04/22/2026"


# ── _parse_opt_description ────────────────────────────────────────────────────

class TestParseOptDescription:
    def test_sto_format(self):
        result = _parse_opt_description("MOH 1/15/2027 Call $200.00")
        assert result == ("MOH", "01/15/2027", "Call", 200.0)

    def test_oexp_format(self):
        result = _parse_opt_description("Option Expiration for PYPL 3/20/2026 Call $95.00")
        assert result == ("PYPL", "03/20/2026", "Call", 95.0)

    def test_put_option(self):
        result = _parse_opt_description("ADBE 1/15/2027 Put $250.00")
        assert result == ("ADBE", "01/15/2027", "Put", 250.0)

    def test_adjusted_ticker(self):
        result = _parse_opt_description("RKT1 1/16/2026 Call $15.00")
        assert result == ("RKT1", "01/16/2026", "Call", 15.0)

    def test_double_digit_month(self):
        result = _parse_opt_description("HSY 12/18/2026 Call $200.00")
        assert result == ("HSY", "12/18/2026", "Call", 200.0)

    def test_strike_with_cents(self):
        result = _parse_opt_description("BBY 12/18/2026 Call $75.00")
        assert result == ("BBY", "12/18/2026", "Call", 75.0)

    def test_non_option_description_returns_none(self):
        assert _parse_opt_description("Adobe\nCUSIP: 00724F101") is None

    def test_dividend_description_returns_none(self):
        assert _parse_opt_description("Cash Div: R/D 2026-03-24 P/D 2026-04-14 - 200 shares at 0.96") is None

    def test_multiline_description(self):
        # CSV can have multiline quoted fields
        result = _parse_opt_description("UBER 12/18/2026 Call $125.00\nsome extra line")
        assert result == ("UBER", "12/18/2026", "Call", 125.0)


# ── _parse_qty ────────────────────────────────────────────────────────────────

class TestParseQty:
    def test_plain_number(self):
        assert _parse_qty("3") == 3

    def test_short_suffix(self):
        assert _parse_qty("8S") == 8

    def test_large_short(self):
        assert _parse_qty("20S") == 20

    def test_empty(self):
        assert _parse_qty("") == ""

    def test_float_qty(self):
        # The fraction has to survive. Dividend reinvestment and money-market
        # sweeps both hold fractional shares, and truncating them silently
        # loses real holdings — the same defect _txn_display carried until it
        # stopped rounding sell quantities with int().
        assert _parse_qty("437.844241") == 437.844241


# ── _build_opt_symbol ─────────────────────────────────────────────────────────

class TestBuildOptSymbol:
    def test_call(self):
        assert _build_opt_symbol("MOH", "01/15/2027", 200.0, "Call") == "MOH 01/15/2027 200.00 C"

    def test_put(self):
        assert _build_opt_symbol("PYPL", "03/20/2026", 95.0, "Put") == "PYPL 03/20/2026 95.00 P"

    def test_strike_formatting(self):
        assert _build_opt_symbol("BBY", "12/18/2026", 75.0, "Call") == "BBY 12/18/2026 75.00 C"


# ── _parse_rows_to_transactions ───────────────────────────────────────────────

def _make_row(code, instrument, description, qty="", price="", amount="", date="4/22/2026"):
    return {
        "Activity Date": date,
        "Process Date": date,
        "Settle Date": date,
        "Instrument": instrument,
        "Description": description,
        "Trans Code": code,
        "Quantity": qty,
        "Price": price,
        "Amount": amount,
    }


class TestParseRowsToTransactions:
    def test_stock_buy(self):
        rows = [_make_row("Buy", "ADBE", "Adobe\nCUSIP: 00724F101", qty="15", price="$254.12", amount="($3,811.80)")]
        txns = _parse_rows_to_transactions(rows)
        assert len(txns) == 1
        date, action, opt_type, symbol, strike, exp, qty, price, fees, amount, _ = txns[0]
        assert action == "Buy"
        assert opt_type == "Stock"
        assert symbol == "ADBE"
        assert qty == 15
        assert price == 254.12
        assert amount == -3811.80

    def test_stock_sell(self):
        rows = [_make_row("Sell", "FDX", "FedEx\nCUSIP: 31428X106", qty="200", price="$250.00", amount="$49,999.96")]
        txns = _parse_rows_to_transactions(rows)
        assert txns[0][1] == "Sell"
        assert txns[0][2] == "Stock"
        assert txns[0][9] == 49999.96

    def test_sell_to_open(self):
        rows = [_make_row("STO", "MOH", "MOH 1/15/2027 Call $200.00", qty="3", price="$15.50", amount="$4,649.77", date="4/21/2026")]
        txns = _parse_rows_to_transactions(rows)
        assert len(txns) == 1
        _, action, opt_type, symbol, strike, exp, qty, price, _, amount, _ = txns[0]
        assert action == "Sell to Open"
        assert opt_type == "Call"
        assert symbol == "MOH 01/15/2027 200.00 C"
        assert strike == 200.0
        assert exp == "01/15/2027"
        assert qty == 3
        assert amount == 4649.77

    def test_buy_to_close(self):
        rows = [_make_row("BTC", "HSY", "HSY 6/18/2026 Call $200.00", qty="2", price="$20.30", amount="($4,060.08)", date="3/20/2026")]
        txns = _parse_rows_to_transactions(rows)
        _, action, opt_type, symbol, _, _, _, _, _, amount, _ = txns[0]
        assert action == "Buy to Close"
        assert opt_type == "Call"
        assert symbol == "HSY 06/18/2026 200.00 C"
        assert amount == -4060.08

    def test_option_expiration(self):
        rows = [_make_row("OEXP", "PYPL", "Option Expiration for PYPL 3/20/2026 Call $95.00", qty="11", date="3/20/2026")]
        txns = _parse_rows_to_transactions(rows)
        assert txns[0][1] == "Expired"
        assert txns[0][2] == "Call"
        assert txns[0][3] == "PYPL 03/20/2026 95.00 C"
        assert txns[0][6] == 11

    def test_option_assignment(self):
        rows = [_make_row("OASGN", "FDX", "FDX 1/16/2026 Call $250.00", qty="2", date="1/16/2026")]
        txns = _parse_rows_to_transactions(rows)
        assert txns[0][1] == "Assigned"
        assert txns[0][2] == "Call"

    def test_dividend(self):
        rows = [_make_row("CDIV", "BBY", "Cash Div: R/D 2026-03-24 P/D 2026-04-14 - 200 shares at 0.96", amount="$192.00")]
        txns = _parse_rows_to_transactions(rows)
        assert len(txns) == 1
        assert txns[0][1] == "Dividend"
        assert txns[0][2] == "Dividend"
        assert txns[0][9] == 192.0

    def test_acati_stock(self):
        rows = [_make_row("ACATI", "ADBE", "Adobe\nCUSIP: 00724F101", qty="100", date="4/12/2024")]
        txns = _parse_rows_to_transactions(rows)
        assert len(txns) == 1
        assert txns[0][1] == "Buy"
        assert txns[0][2] == "Stock"
        assert txns[0][6] == 100

    def test_acati_short_option(self):
        rows = [_make_row("ACATI", "T", "T 1/17/2025 Call $20.00", qty="8S", date="4/12/2024")]
        txns = _parse_rows_to_transactions(rows)
        assert len(txns) == 1
        assert txns[0][1] == "Sell to Open"
        assert txns[0][2] == "Call"
        assert txns[0][6] == 8

    def test_slip_ignored(self):
        rows = [_make_row("SLIP", "MOH", "Stock Lending", amount="$0.01")]
        txns = _parse_rows_to_transactions(rows)
        assert len(txns) == 0

    def test_transactions_reversed_to_chronological(self):
        # CSV is newest-first; parser should reverse to oldest-first
        rows = [
            _make_row("Buy", "ADBE", "Adobe", qty="10", date="4/22/2026"),
            _make_row("Buy", "ADBE", "Adobe", qty="5",  date="4/15/2026"),
        ]
        txns = _parse_rows_to_transactions(rows)
        assert txns[0][6] == 5   # April 15 comes first chronologically
        assert txns[1][6] == 10


# ── parse_all_transactions ────────────────────────────────────────────────────

class TestParseAllTransactions:
    def test_routes_to_correct_tickers(self, tmp_path):
        csv_content = (
            '"Activity Date","Process Date","Settle Date","Instrument","Description","Trans Code","Quantity","Price","Amount"\n'
            '"4/22/2026","4/22/2026","4/23/2026","ADBE","Adobe","Buy","15","$254.12","($3,811.80)"\n'
            '"4/21/2026","4/21/2026","4/22/2026","MOH","MOH 1/15/2027 Call $200.00","STO","3","$15.50","$4,649.77"\n'
            '"4/14/2026","4/14/2026","4/14/2026","BBY","Cash Div: R/D 2026-03-24 - 200 shares at 0.96","CDIV","","","$192.00"\n'
            '"4/8/2026","4/8/2026","4/8/2026","MOH","Stock Lending","SLIP","","","$0.01"\n'
        )
        f = tmp_path / "robinhood.csv"
        f.write_text(csv_content, encoding="utf-8")
        ticker_txns, other_rows = parse_all_transactions(str(f))

        assert "ADBE" in ticker_txns
        assert "MOH" in ticker_txns
        assert len(ticker_txns["ADBE"]) == 1
        assert len(ticker_txns["MOH"]) == 1
        # BBY dividend goes to other_rows (BBY has no Buy/Sell/option rows)
        assert "BBY" not in ticker_txns
        assert any(r.get("Instrument") == "BBY" for r in other_rows)
        # SLIP goes to other_rows
        assert any(r.get("Trans Code") == "SLIP" for r in other_rows)

    def test_dividend_assigned_to_position_ticker(self, tmp_path):
        csv_content = (
            '"Activity Date","Process Date","Settle Date","Instrument","Description","Trans Code","Quantity","Price","Amount"\n'
            '"4/22/2026","4/22/2026","4/23/2026","ADBE","Adobe","Buy","15","$254.12","($3,811.80)"\n'
            '"4/14/2026","4/14/2026","4/14/2026","ADBE","Cash Div: R/D 2026-03-24","CDIV","","","$100.00"\n'
        )
        f = tmp_path / "robinhood.csv"
        f.write_text(csv_content, encoding="utf-8")
        ticker_txns, other_rows = parse_all_transactions(str(f))
        assert "ADBE" in ticker_txns
        assert len(ticker_txns["ADBE"]) == 2  # Buy + Dividend
