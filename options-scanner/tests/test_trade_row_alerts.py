"""Rows on the Trades tab that are **not live positions**.

The everyday case, and the one this was built for: you place a sell-to-open in
the afternoon, it doesn't fill, and at 16:00 ET the broker retires the order.
No position was ever created — but the tracker keeps the record, the store
still calls it "open", and the row goes on sitting among real positions with a
murmured lowercase "expired" where a status word goes. It reads as a position
whose quotes just failed.

The rarer case is the same shape: a position that *did* fill, whose contract
has since expired (`past_expiry_days`).

`row_alert` is the one place that decides, and the heading count, the row
styling and the row header all read it, so they can't disagree. What the answer
looks like on screen is pinned here too — the first two attempts (an amber
tint, then a small red pill) both came back as "still doesn't stand out", and a
summary banner above the list was tried and cut.

A row can also be tinted for a happier reason: an order still working gets a
light-yellow row and shows the market against its own limit, so "is my price
anywhere near?" doesn't need the row opened.
"""

from datetime import date

from options_scanner.tabs.trades import (_EXPIRED_GRAY, _EXPIRED_GRAY_DARK,
                                         _EXPIRED_RED, _alert_note,
                                         _fmt_exp, _row_tint_css, _stamp_md,
                                         _working_order_md,
                                         past_expiry_days as ped, row_alert)

TODAY = date(2026, 8, 21)


def trade(expiration, status="open", **kw):
    return {"id": "abc123", "ticker": "AMD", "strike": 120,
            "expiration": expiration, "status": status, **kw}


def stamp(store_status="open", disp="held", age=None):
    return row_alert(store_status, disp, age)


# ── an opening order that died ───────────────────────────────────────────────
# These words reach the row from the broker via _display_status, and only while
# the store still says "open".

def test_an_order_that_expired_at_the_close_is_flagged():
    # The real report: NKE placed in the afternoon, unfilled, retired at 16:00.
    assert stamp(disp="expired") == "⚠️ ORDER EXPIRED — NEVER FILLED"


def test_the_stamp_says_no_position_was_created():
    # The fact that matters is not "expired" but "you don't own this" — the
    # lowercase status word said the first part and left out the second.
    for word in ("expired", "rejected", "canceled"):
        assert "NEVER FILLED" in stamp(disp=word)


def test_a_rejected_or_broker_canceled_order_is_flagged_the_same_way():
    assert stamp(disp="rejected") == "⚠️ ORDER REJECTED — NEVER FILLED"
    assert stamp(disp="canceled") == "⚠️ ORDER CANCELED — NEVER FILLED"


def test_a_live_row_is_not_flagged():
    assert stamp(disp="held") is None
    assert stamp(disp="working") is None      # still out there, may yet fill
    assert stamp(disp="queued") is None


def test_a_settled_record_is_not_stamped():
    # A record the STORE calls expired/canceled is history and already says so.
    # Only the broker's word about a still-"open" record means a dead order —
    # otherwise every closed trade in the archive would light up.
    assert stamp(store_status="expired", disp="expired") is None
    assert stamp(store_status="canceled", disp="canceled") is None
    assert stamp(store_status="closed", disp="closed") is None


def test_a_cancel_you_made_yourself_is_not_flagged():
    # Canceling in the app writes status="canceled" to the store, so it lands
    # in the settled case above. Only a cancel that happened at the broker,
    # behind the app's back, reaches the row as a broker word.
    assert stamp(store_status="canceled", disp="canceled") is None


# ── a contract that expired under a filled position ──────────────────────────

def test_an_expired_contract_is_flagged_with_its_age():
    assert stamp(disp="held", age=6) == "⚠️ EXPIRED — 6D AGO"


def test_a_dead_order_outranks_an_expired_contract():
    # Both can technically apply. "You never had this position" is the more
    # important of the two, so it's the one that gets said.
    assert stamp(disp="expired", age=6) == "⚠️ ORDER EXPIRED — NEVER FILLED"


# ── the stamp on screen: red, bold, SHOUTING ─────────────────────────────────

def test_the_stamp_shouts():
    text = _stamp_md("⚠️ ORDER EXPIRED — NEVER FILLED")
    inner = text.partition("[**")[2].rpartition("**]")[0]
    letters = [c for c in inner if c.isalpha()]
    assert letters and all(c.isupper() for c in letters)


def test_the_stamp_is_red_and_bold():
    # Bold via **, which is also the <strong> hook _row_tint_css forces the
    # red onto — drop the ** and the CSS quietly stops applying.
    md = _stamp_md("⚠️ ORDER EXPIRED — NEVER FILLED")
    assert md.startswith(":red[**") and md.endswith("**]")


# ── the row: solid gray, red edge ────────────────────────────────────────────

def test_nothing_flagged_means_no_style_block():
    assert _row_tint_css({}) == ""


def test_the_row_gets_a_solid_light_gray_background():
    css = _row_tint_css({"abc123abc123": "dead"})
    assert f"background:{_EXPIRED_GRAY} !important" in css
    # Solid, not a wash: the translucent version was the one nobody could see.
    assert "rgba" not in css


def test_the_dark_theme_gets_its_own_gray():
    # The header's label color is pinned to --osc-ink-2 and flips with the
    # theme, so a literal light gray would be near-white text on near-white.
    css = _row_tint_css({"abc123abc123": "dead"})
    assert 'html[data-osc-theme="dark"]' in css
    assert f"background:{_EXPIRED_GRAY_DARK} !important" in css


def test_the_stamp_is_forced_red_over_the_header_color_pin():
    # The header pins `button p {color: … !important}`; the rule that beats it
    # has to land on the <strong> itself, not be inherited into it.
    css = _row_tint_css({"abc123abc123": "dead"})
    assert f"color:{_EXPIRED_RED} !important" in css
    assert "button p strong" in css


def test_rules_are_scoped_to_the_flagged_rows_only():
    css = _row_tint_css({"aaaaaaaaaaaa": "dead", "bbbbbbbbbbbb": "dead"})
    assert "st-key-trade_hdr_aaaaaaaaaaaa" in css
    assert "st-key-trade_hdr_bbbbbbbbbbbb" in css
    # Never the bare prefix — that would gray out every trade in the list.
    assert "[class*='st-key-trade_hdr_']" not in css


def test_the_block_is_a_single_style_element():
    css = _row_tint_css({"aaaaaaaaaaaa": "dead", "bbbbbbbbbbbb": "dead"})
    assert css.startswith("<style>") and css.endswith("</style>")
    assert css.count("<style>") == 1


def test_the_braces_balance():
    # This block is built by concatenating f-strings (where a literal brace is
    # doubled) with plain ones (where it isn't), and the first version shipped
    # `}}` on three rules — CSS a browser recovers from silently, which is the
    # worst kind of wrong.
    css = _row_tint_css({"aaaaaaaaaaaa": "dead", "bbbbbbbbbbbb": "dead"})
    assert css.count("{") == css.count("}")
    depth = 0
    for ch in css:
        depth += (ch == "{") - (ch == "}")
        assert depth in (0, 1), "a rule opened or closed twice"
    assert depth == 0


# ── a working order: yellow row, market + limit in the header ────────────────

def test_a_working_row_is_yellow_not_gray():
    css = _row_tint_css({"abc123abc123": "working"})
    assert "background:#fef3c7 !important" in css
    assert _EXPIRED_GRAY not in css


def test_a_working_row_carries_no_red_stamp_rule():
    # Nothing is wrong with it — it's an order that may yet fill. Only a dead
    # row's label has a <strong> to color anyway.
    css = _row_tint_css({"abc123abc123": "working"})
    assert _EXPIRED_RED not in css
    assert "strong" not in css


def test_both_tints_coexist_in_one_block():
    css = _row_tint_css({"aaaaaaaaaaaa": "dead", "bbbbbbbbbbbb": "working"})
    assert css.count("<style>") == 1
    assert f"background:{_EXPIRED_GRAY} !important" in css
    assert "background:#fef3c7 !important" in css
    assert css.count("{") == css.count("}")


def test_the_working_header_shows_the_market_and_your_limit():
    md = _working_order_md({"bid": 2.4, "ask": 2.6}, 2.95)
    assert "bid" in md and "ask" in md and "limit" in md
    assert "2.40" in md and "2.60" in md and "2.95" in md


def test_the_working_header_escapes_its_dollar_signs():
    # It shares a label with the strike and the spot; an unescaped pair of $
    # anywhere in one markdown string is read as LaTeX math.
    md = _working_order_md({"bid": 2.4, "ask": 2.6}, 2.95)
    assert "$" not in md.replace("\\$", "")


def test_the_limit_shows_even_when_the_quote_does_not():
    # The limit comes off the record, so it's known whether or not Schwab
    # answered — and it's the half you can't get anywhere else on the row.
    md = _working_order_md(None, 2.95)
    assert md == "limit \\$2.95"


def test_a_half_quote_is_dropped_rather_than_half_shown():
    # A lone bid with no ask says nothing about the spread.
    assert _working_order_md({"bid": 2.4}, 2.95) == "limit \\$2.95"


def test_nothing_to_say_is_an_empty_segment():
    assert _working_order_md(None, None) == ""
    assert _working_order_md({}, "not a number") == ""


# ── the notice inside an opened row ──────────────────────────────────────────

def test_the_dead_order_notice_says_there_is_no_position():
    note = _alert_note("expired", "Dec 15 '28")
    assert "never became a position" in note
    assert "16:00 ET" in note, "say WHY it died — a day order is retired"
    assert "Remove from Tracker" in note


def test_the_dead_order_notice_names_the_ending():
    assert "expired without filling" in _alert_note("expired", "Dec 15 '28")
    assert "was rejected" in _alert_note("rejected", "Dec 15 '28")


def test_the_expired_contract_notice_is_a_different_story():
    # Here a position DID exist, so the question is worthless vs assigned.
    note = _alert_note("held", "Aug 15 '26", 6)
    assert "assigned" in note and "expired worthless" in note


def test_notices_escape_their_dollar_signs():
    # A pair of unescaped $ in one markdown string is read as LaTeX math.
    for note in (_alert_note("expired", "Dec 15 '28"),
                 _alert_note("held", "Aug 15 '26", 6)):
        assert "$" not in note.replace("\\$", "")


# ── past_expiry_days: the contract-date rule ─────────────────────────────────

def test_a_past_expiration_reports_its_age():
    assert ped(trade("2026-08-15"), TODAY) == 6


def test_yesterday_is_expired():
    # The first day it can possibly count, so pin it: an off-by-one here either
    # flags live positions or hides a fresh expiry for a day.
    assert ped(trade("2026-08-20"), TODAY) == 1


def test_expiring_today_is_not_expired():
    # It trades until the close and the row is still actionable — flagging it
    # would cry wolf on every expiration Friday.
    assert ped(trade("2026-08-21"), TODAY) is None


def test_a_future_expiration_is_not_expired():
    # Every record in the real store looked like this, which is how the first
    # version of this feature shipped without ever rendering once.
    assert ped(trade("2028-12-15"), TODAY) is None


def test_a_long_dead_position_still_reports_days():
    assert ped(trade("2025-01-17"), TODAY) == 581


def test_a_working_close_or_roll_still_counts():
    assert ped(trade("2026-08-15", status="closing"), TODAY) == 6
    assert ped(trade("2026-08-15", status="rolling"), TODAY) == 6


def test_settled_records_are_left_alone():
    for status in ("closed", "expired", "assigned", "canceled"):
        assert ped(trade("2026-08-15", status=status), TODAY) is None


def test_a_missing_status_is_treated_as_open():
    t = trade("2026-08-15")
    del t["status"]
    assert ped(t, TODAY) == 6


def test_an_unparseable_or_missing_date_claims_nothing():
    for exp in ("", None, "next friday", "08/15/2026", "2026-13-45"):
        assert ped(trade(exp), TODAY) is None


def test_today_defaults_to_the_real_clock():
    assert ped(trade("2020-01-17")) == ped(trade("2020-01-17"), date.today())


# ── the shared expiration formatter ──────────────────────────────────────────

def test_expirations_format_the_way_the_rest_of_the_app_writes_them():
    assert _fmt_exp("2026-08-15") == "Aug 15 '26"


def test_a_broken_expiration_still_names_itself():
    assert _fmt_exp("whenever") == "whenever"
    assert _fmt_exp("") == "?"
    assert _fmt_exp(None) == "?"
