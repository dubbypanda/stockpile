"""Tests for the brokerage-CSV merge engine (stocks_shared.csv_merge)."""

import csv
import io

import pytest

from stocks_shared.csv_merge import (
    MergeError,
    detect_brokerage,
    get_spec,
    merge_csv,
    read_file,
    render,
)

# ── Fixtures in each brokerage's real dialect ─────────────────────────────

FID_HDR = ("Run Date,Action,Symbol,Description,Type,Price ($),Quantity,"
           "Commission ($),Fees ($),Accrued Interest ($),Amount ($),"
           "Cash Balance ($),Settlement Date")

# The two rows already in fidelity_522.csv before today's merge, plus the
# Fidelity export's blank lead-in and disclaimer footer.
FID_EXISTING = f"""

{FID_HDR}
12/01/2025,YOU BOUGHT UBER TECHNOLOGIES INC COM (UBER) (Cash),UBER,UBER TECHNOLOGIES INC COM,Cash,86.24,230,"","","","-19835.89",645.89,12/02/2025
"""

FID_INCOMING = f"""

{FID_HDR}
08/07/2026,YOU BOUGHT UBER TECHNOLOGIES INC COM (UBER) (Cash),UBER,UBER TECHNOLOGIES INC COM,Cash,74.14,20,"","","","-1482.7",Processing,08/10/2026
12/01/2025,YOU BOUGHT UBER TECHNOLOGIES INC COM (UBER) (Cash),UBER,UBER TECHNOLOGIES INC COM,Cash,86.24,230,"","","","-19835.89",645.89,12/02/2025

"The data and information in this spreadsheet is provided to you solely for your use and is not for distribution."
Date downloaded 08/07/2026 10:16 am
"""

# Same trade as the 08/07 row above, but settled: Cash Balance and
# Settlement Date have filled in. Must replace, not duplicate.
FID_SETTLED = f"""

{FID_HDR}
08/07/2026,YOU BOUGHT UBER TECHNOLOGIES INC COM (UBER) (Cash),UBER,UBER TECHNOLOGIES INC COM,Cash,74.14,20,"","","","-1482.7",20903.12,08/10/2026
"""

SCHWAB_HDR = '"Date","Action","Symbol","Description","Quantity","Price","Fees & Comm","Amount"'

SCHWAB_EXISTING = (
    SCHWAB_HDR + "\r\n"
    '"12/19/2022 as of 12/16/2022","Buy","GOOGL","ALPHABET INC. CLASS A","100","$95.00","","-$9500.00"\r\n'
)
SCHWAB_INCOMING = (
    SCHWAB_HDR + "\r\n"
    '"08/05/2026","Sell","GOOGL","ALPHABET INC CLASS A","100","$371.33","$0.78","$37132.22"\r\n'
    '"12/19/2022 as of 12/16/2022","Buy","GOOGL","ALPHABET INC. CLASS A","100","$95.00","","-$9500.00"\r\n'
)

RH_HDR = ('"Activity Date","Process Date","Settle Date","Instrument",'
          '"Description","Trans Code","Quantity","Price","Amount"')

# Robinhood wraps the stock Description across embedded newlines.
RH_EXISTING = (
    RH_HDR + "\n"
    '"3/24/2025","3/24/2025","3/25/2025","GOOGL","Alphabet Class A\nCommon Stock","Buy","100","$167.27","($16727.23)"\n'
)
RH_INCOMING = (
    RH_HDR + "\n"
    '"6/15/2026","6/15/2026","6/15/2026","GOOGL","Cash Div: R/D 2026-06-08","CDIV","","","$44.00"\n'
    '"3/24/2025","3/24/2025","3/25/2025","GOOGL","Alphabet Class A\nCommon Stock","Buy","100","$167.27","($16727.23)"\n'
)


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8", newline="")
    return p


# ── Core merge behavior ───────────────────────────────────────────────────

class TestMergeBasics:
    def test_appends_new_rows_newest_first(self, tmp_path):
        old = write(tmp_path, "old.csv", FID_EXISTING)
        new = write(tmp_path, "new.csv", FID_INCOMING)
        r = merge_csv(old, new, "fidelity")

        assert len(r.added) == 1
        assert len(r.unchanged) == 1
        assert not r.replaced and not r.existing_only
        assert r.total_rows == 2

        rows = list(csv.reader(io.StringIO(r.text)))
        data = [x for x in rows if x and x[0].startswith(("08/", "12/"))]
        assert data[0][0] == "08/07/2026", "newest row must sort first"
        assert data[1][0] == "12/01/2025"

    def test_full_overlap_is_a_noop(self, tmp_path):
        """Re-merging an export already merged adds nothing.

        This is the state input/fid2522.csv is in after today's hand merge.
        """
        old = write(tmp_path, "old.csv", FID_INCOMING)
        new = write(tmp_path, "new.csv", FID_INCOMING)
        r = merge_csv(old, new, "fidelity")
        assert not r.added and not r.replaced and not r.existing_only
        assert len(r.unchanged) == 2

    def test_disclaimer_and_blank_lines_dropped(self, tmp_path):
        old = write(tmp_path, "old.csv", FID_EXISTING)
        new = write(tmp_path, "new.csv", FID_INCOMING)
        r = merge_csv(old, new, "fidelity")
        assert "not for distribution" not in r.text
        assert "Date downloaded" not in r.text

    def test_preamble_preserved(self, tmp_path):
        old = write(tmp_path, "old.csv", FID_EXISTING)
        new = write(tmp_path, "new.csv", FID_INCOMING)
        r = merge_csv(old, new, "fidelity")
        assert r.text.startswith("\n\nRun Date,"), "Fidelity's blank lead-in"

    def test_rows_only_in_existing_survive(self, tmp_path):
        """Hand-backfilled history (schwab444.csv) must never be dropped."""
        old = write(tmp_path, "old.csv", SCHWAB_EXISTING)
        new = write(
            tmp_path, "new.csv",
            SCHWAB_HDR + "\r\n"
            '"08/05/2026","Sell","GOOGL","ALPHABET INC CLASS A","100","$371.33","$0.78","$37132.22"\r\n')
        r = merge_csv(old, new, "schwab")
        assert len(r.added) == 1
        assert len(r.existing_only) == 1
        assert "-$9500.00" in r.text


class TestVolatileColumns:
    def test_settled_row_replaces_processing(self, tmp_path):
        """The Processing → settled-balance case, the reason for identity keys."""
        old = write(tmp_path, "old.csv", FID_INCOMING)
        new = write(tmp_path, "new.csv", FID_SETTLED)
        r = merge_csv(old, new, "fidelity")

        assert len(r.replaced) == 1
        before, after = r.replaced[0]
        assert before[11] == "Processing"
        assert after[11] == "20903.12"
        assert not r.added

        assert r.text.count("74.14") == 1, "must not duplicate the trade"
        assert "Processing" not in r.text

    def test_identity_ignores_volatile_columns(self):
        spec = get_spec("fidelity")
        assert "Cash Balance ($)" in spec.volatile_cols
        assert "Cash Balance ($)" not in spec.identity_cols

    def test_reformatted_number_is_not_a_change(self, tmp_path):
        """16.30 -> 16.3 is the same balance, not an update."""
        row = ('08/07/2026,YOU BOUGHT UBER TECHNOLOGIES INC COM (UBER) (Cash),'
               'UBER,UBER TECHNOLOGIES INC COM,Cash,74.14,20,"","","",'
               '"-1482.7",{bal},08/10/2026')
        old = write(tmp_path, "old.csv",
                    f"\n\n{FID_HDR}\n{row.format(bal='16.30')}\n")
        new = write(tmp_path, "new.csv",
                    f"\n\n{FID_HDR}\n{row.format(bal='16.3')}\n")
        r = merge_csv(old, new, "fidelity")
        assert not r.replaced and not r.added
        assert len(r.unchanged) == 1

    def test_respelled_identity_is_not_a_new_row(self, tmp_path):
        """-1482.70 and -1482.7 are the same trade, not two of them."""
        row = ('08/07/2026,YOU BOUGHT UBER TECHNOLOGIES INC COM (UBER) (Cash),'
               'UBER,UBER TECHNOLOGIES INC COM,Cash,74.14,20,"","","",'
               '"{amt}",100.00,08/10/2026')
        old = write(tmp_path, "old.csv",
                    f"\n\n{FID_HDR}\n{row.format(amt='-1482.70')}\n")
        new = write(tmp_path, "new.csv",
                    f"\n\n{FID_HDR}\n{row.format(amt='-1482.7')}\n")
        r = merge_csv(old, new, "fidelity")
        assert not r.added, "respelled amount must not look like a new trade"
        assert r.total_rows == 1


class TestNorm:
    @pytest.mark.parametrize("a,b", [
        ("16.30", "16.3"),
        ("$1,234.50", "1234.5"),
        ("(1234.50)", "-1234.50"),
        ("  100  ", "100.0"),
        ("($16,727.23)", "-16727.23"),
    ])
    def test_numerically_equal(self, a, b):
        from stocks_shared.csv_merge import norm
        assert norm(a) == norm(b)

    @pytest.mark.parametrize("a,b", [
        ("16.30", "16.31"),
        ("100", "-100"),
        ("UBER", "UBER "),          # equal after strip
        ("-UBER270617C100", "-UBER270617C100"),
    ])
    def test_non_numeric_and_distinct(self, a, b):
        from stocks_shared.csv_merge import norm
        if a.strip() == b.strip():
            assert norm(a) == norm(b)
        else:
            assert norm(a) != norm(b)


class TestDuplicateTrades:
    def test_two_identical_trades_same_day_both_kept(self, tmp_path):
        """Genuinely repeated trades are not duplicates of each other."""
        dup = (
            '08/07/2026,YOU BOUGHT UBER TECHNOLOGIES INC COM (UBER) (Cash),UBER,'
            'UBER TECHNOLOGIES INC COM,Cash,74.14,20,"","","","-1482.7",100.00,08/10/2026'
        )
        both = f"\n\n{FID_HDR}\n{dup}\n{dup}\n"
        old = write(tmp_path, "old.csv", both)
        new = write(tmp_path, "new.csv", both)
        r = merge_csv(old, new, "fidelity")
        assert len(r.unchanged) == 2
        assert r.total_rows == 2, "both copies survive; neither is dropped"


class TestDialects:
    def test_schwab_crlf_and_quote_all_preserved(self, tmp_path):
        old = write(tmp_path, "old.csv", SCHWAB_EXISTING)
        new = write(tmp_path, "new.csv", SCHWAB_INCOMING)
        r = merge_csv(old, new, "schwab")
        assert "\r\n" in r.text
        assert r.text.startswith('"Date","Action"')

    def test_schwab_as_of_date_matches_verbatim(self, tmp_path):
        old = write(tmp_path, "old.csv", SCHWAB_EXISTING)
        new = write(tmp_path, "new.csv", SCHWAB_INCOMING)
        r = merge_csv(old, new, "schwab")
        assert len(r.unchanged) == 1, "'as of' row must match itself"
        assert len(r.added) == 1

    def test_robinhood_embedded_newlines_round_trip(self, tmp_path):
        old = write(tmp_path, "old.csv", RH_EXISTING)
        new = write(tmp_path, "new.csv", RH_INCOMING)
        r = merge_csv(old, new, "robinhood")
        assert len(r.added) == 1
        assert len(r.unchanged) == 1
        rows = list(csv.reader(io.StringIO(r.text)))
        stock = [x for x in rows if len(x) > 5 and x[5] == "Buy"][0]
        assert stock[4] == "Alphabet Class A\nCommon Stock"

    def test_fidelity_quote_minimal(self, tmp_path):
        old = write(tmp_path, "old.csv", FID_EXISTING)
        new = write(tmp_path, "new.csv", FID_INCOMING)
        r = merge_csv(old, new, "fidelity")
        assert not r.text.lstrip().startswith('"Run Date"')


class TestVerification:
    def test_transaction_counts_reported(self, tmp_path):
        old = write(tmp_path, "old.csv", FID_EXISTING)
        new = write(tmp_path, "new.csv", FID_INCOMING)
        r = merge_csv(old, new, "fidelity")
        assert r.txn_before == 1
        assert r.txn_after == 2

    def test_dropped_row_is_caught(self, tmp_path, monkeypatch):
        """Corrupt the render step; verification must refuse the merge."""
        import stocks_shared.csv_merge as cm

        real_render = cm.render
        monkeypatch.setattr(
            cm, "render", lambda pf, rows: real_render(pf, rows[:-1]))

        old = write(tmp_path, "old.csv", FID_EXISTING)
        new = write(tmp_path, "new.csv", FID_INCOMING)
        with pytest.raises(MergeError, match="failed parser verification"):
            merge_csv(old, new, "fidelity")

    def test_duplicated_transaction_is_caught(self, tmp_path, monkeypatch):
        """The failure that matters: a trade written twice.

        A set-based check would miss this — the copies collapse. Counting
        is what makes it visible.
        """
        import stocks_shared.csv_merge as cm

        real_render = cm.render
        monkeypatch.setattr(
            cm, "render", lambda pf, rows: real_render(pf, rows + rows[:1]))

        old = write(tmp_path, "old.csv", FID_EXISTING)
        new = write(tmp_path, "new.csv", FID_INCOMING)
        with pytest.raises(MergeError, match="duplicated or invented"):
            merge_csv(old, new, "fidelity")

    def test_verify_can_be_skipped(self, tmp_path, monkeypatch):
        import stocks_shared.csv_merge as cm

        real_render = cm.render
        monkeypatch.setattr(
            cm, "render", lambda pf, rows: real_render(pf, rows[:-1]))
        old = write(tmp_path, "old.csv", FID_EXISTING)
        new = write(tmp_path, "new.csv", FID_INCOMING)
        merge_csv(old, new, "fidelity", verify=False)  # no raise


class TestGuards:
    def test_header_mismatch_rejected(self, tmp_path):
        old = write(tmp_path, "old.csv", FID_EXISTING)
        new = write(tmp_path, "new.csv", SCHWAB_INCOMING)
        with pytest.raises(MergeError):
            merge_csv(old, new, "fidelity")

    def test_unknown_brokerage(self, tmp_path):
        old = write(tmp_path, "old.csv", FID_EXISTING)
        with pytest.raises(MergeError, match="No merge spec"):
            merge_csv(old, old, "etrade")

    def test_missing_header_row(self, tmp_path):
        bad = write(tmp_path, "bad.csv", "some,other,file\n1,2,3\n")
        with pytest.raises(MergeError, match="header row"):
            read_file(bad, get_spec("fidelity"))


class TestDetectBrokerage:
    @pytest.mark.parametrize("text,expected", [
        (FID_EXISTING, "fidelity"),
        (SCHWAB_EXISTING, "schwab"),
        (RH_EXISTING, "robinhood"),
        ('"Trade Date" ,"Settlement Date" ,"Account"\n', "merrill"),
    ])
    def test_detects_from_header(self, tmp_path, text, expected):
        p = write(tmp_path, "x.csv", text)
        assert detect_brokerage(p) == expected

    def test_unknown_returns_none(self, tmp_path):
        p = write(tmp_path, "x.csv", "a,b,c\n1,2,3\n")
        assert detect_brokerage(p) is None
