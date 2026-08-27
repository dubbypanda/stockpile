"""Pure analysis functions — no API calls, no I/O."""

import re
from datetime import date, timedelta
from collections import defaultdict


def _norm_opt_symbol(symbol):
    """Strip adjustment-digit suffix from option ticker so adjusted symbols match originals.
    e.g. 'AMC1 12/16/2022 24.00 P' → 'AMC 12/16/2022 24.00 P'
    """
    return re.sub(r"^([A-Z]+)\d+(\s)", r"\1\2", symbol)


def detect_open_positions(transactions):
    """Return list of currently open short option positions (net contracts > 0)."""
    pos = defaultdict(lambda: {
        "contracts": 0, "premium": 0.0,
        "type": None, "strike": None, "expiration": None, "open_date": None,
    })
    for row in transactions:
        date_str, action, opt_type, symbol, strike, expiration, qty, _, _, amount, _ = row
        if opt_type == "Stock" or qty == "":
            continue
        key = _norm_opt_symbol(symbol)
        p = pos[key]
        p["type"] = opt_type
        p["strike"] = strike
        p["expiration"] = expiration
        amt = float(amount) if amount != "" else 0.0
        q = int(qty)
        if action in ("Sell to Open", "Buy to Open"):
            if p["contracts"] == 0:
                p["open_date"] = date_str  # record date of first open
            p["contracts"] += q
            p["premium"] += amt
        elif action in ("Buy to Close", "Sell to Close", "Expired", "Assigned",
                        "Exercised"):
            p["contracts"] -= q
            p["premium"] += amt
            if p["contracts"] == 0:
                p["open_date"] = None  # reset if fully closed

    return [{"symbol": s, **v} for s, v in pos.items() if v["contracts"] > 0]


def detect_suspicious_positions(transactions, open_positions):
    """Return list of warning strings for open positions that look suspicious.

    Three signals:
    1. Option expiration date has already passed (most reliable).
    2. Open call but net share count is 0 — shares were sold or called away.
    3. Open put where a stock buy at the put strike occurred near expiration —
       likely an unrecorded assignment.
    """
    if not open_positions:
        return []

    today = date.today()
    warnings = []

    # transactions are oldest-first; treat Transfer In as an authoritative
    # balance snapshot (TDA->Schwab migration) that resets the running total,
    # since any pre-transfer Buy/Sell rows are already baked into that quantity.
    # stock_buys still only records real Buy executions — those are what Signal 3
    # looks for when detecting assignment-shaped patterns.
    net_shares = 0.0
    stock_buys = []  # [(date_obj, price_per_share), ...]
    for row in transactions:
        date_str, action, opt_type, _, _, _, qty, price, _, _, _ = row
        if opt_type != "Stock" or qty == "":
            continue
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
        if not m:
            continue
        q = float(qty)
        d = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        if action == "Transfer In":
            net_shares = q                      # snapshot reset, not delta
        elif action == "Buy":
            net_shares += q
            if price != "":
                stock_buys.append((d, float(price)))
        elif action == "Reinvest Shares":
            net_shares += q
        elif action == "Sell":
            net_shares -= q

    for pos in open_positions:
        sym      = pos["symbol"]
        exp_str  = pos["expiration"] or ""
        opt_type = pos["type"]
        strike   = pos["strike"]

        exp_date = None
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", exp_str)
        if m:
            exp_date = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))

        # Signal 1: expiration already passed
        if exp_date and exp_date < today:
            warnings.append(
                f"open {opt_type} {sym} expired {exp_str} — "
                "check for missing Assigned or Expired transaction"
            )
            continue

        # Signal 2: open call but no shares held
        if opt_type == "Call" and net_shares <= 0.001:
            warnings.append(
                f"open {opt_type} {sym} but no shares held — "
                "check for missing Assigned transaction"
            )

        # Signal 3: open put with stock buy at the put strike near expiration
        if opt_type == "Put" and exp_date:
            for buy_date, buy_price in stock_buys:
                if (exp_date - timedelta(days=30)) <= buy_date <= (exp_date + timedelta(days=5)):
                    if abs(buy_price - strike) < 0.01:
                        warnings.append(
                            f"open {opt_type} {sym} — stock bought at strike "
                            f"${strike:.2f} on {buy_date:%m/%d/%Y}, "
                            "check for missing Assigned transaction"
                        )
                        break

    return warnings


def get_last_option(transactions, option_type):
    """Return stats for the most recently opened option of the given type.

    Finds the last Sell/Buy-to-Open for the given type, locates its close
    transaction, and returns the holding period plus key fields.
    Returns None if no such option exists in the transaction history.
    """
    opens = [
        row for row in transactions
        if row[2] == option_type
        and row[1] in ("Sell to Open", "Buy to Open")
        and row[6] != ""
    ]
    if not opens:
        return None

    # transactions are chronologically sorted; last entry is the most recent open
    last       = opens[-1]
    open_date  = last[0]
    symbol     = last[3]
    strike     = last[4]
    expiration = last[5]
    contracts  = int(last[6])
    premium    = round(float(last[9]), 2) if last[9] != "" else 0.0

    _CLOSE_ACTIONS = {"Buy to Close", "Sell to Close", "Expired", "Assigned",
                      "Exercised"}
    close_rows = sorted(
        (row[0], row[1]) for row in transactions
        if _norm_opt_symbol(row[3]) == _norm_opt_symbol(symbol)
        and row[1] in _CLOSE_ACTIONS
    )
    close_date   = close_rows[-1][0]  if close_rows else None
    close_action = close_rows[-1][1]  if close_rows else None

    def _parse(s):
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s or "")
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None

    days_open = None
    if open_date and close_date:
        od, cd = _parse(open_date), _parse(close_date)
        if od and cd:
            days_open = (cd - od).days

    # Disposition and ITM/OTM at close
    if close_action == "Assigned":
        disposition  = "Assigned"
        itm_at_close = True
    elif close_action == "Exercised":
        disposition  = "Exercised"
        itm_at_close = True
    elif close_action == "Expired":
        disposition  = "Expired"
        itm_at_close = False
    elif close_action in ("Buy to Close", "Sell to Close"):
        exp_date = _parse(expiration)
        cl_date  = _parse(close_date) if close_date else None
        if exp_date and cl_date and cl_date >= exp_date:
            disposition = "Closed at expiration"
        else:
            disposition = "Closed early"
        itm_at_close = None  # requires stock price at close; filled by caller
    else:
        disposition  = ""
        itm_at_close = None

    # Roll count: BTC transactions whose date matches a same-day STO of the same type
    sto_dates = {row[0] for row in transactions
                 if row[2] == option_type and row[1] in ("Sell to Open", "Buy to Open")}
    roll_count = sum(
        1 for row in transactions
        if row[2] == option_type
        and row[1] in ("Buy to Close", "Sell to Close")
        and row[0] in sto_dates
    )

    return {
        "strike":        strike,
        "expiration":    expiration,
        "open_date":     open_date,
        "close_date":    close_date,
        "days_open":     days_open,
        "contracts":     contracts,
        "premium":       premium,
        "disposition":   disposition,
        "itm_at_close":  itm_at_close,
        "roll_count":    roll_count,
        "price_at_open": None,  # filled by caller
        "price_at_close": None, # filled by caller for BTC cases
    }


def compute_avg_held_anchor(transactions):
    """Return (year, month, day) of the share-weighted average acquisition date
    for currently-held shares, or None if no shares are held.

    Stock Sell rows consume lots FIFO — so shares that have been sold no
    longer contribute to the weighted average. Reinvest Shares add lots at
    the reinvest date. Transfer In acts as a balance snapshot: any missing
    quantity (pre-CSV history) gets a synthetic lot at the transfer date,
    which is the best approximation available without the original buy dates.
    """
    lots = []  # [[date, shares_remaining], ...], chronological order
    for row in transactions:
        date_str, action, opt_type, _sym, _strike, _exp, qty, _, _, _, _ = row
        if opt_type != "Stock" or qty == "":
            continue
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
        if not m:
            continue
        lot_date = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        q = float(qty)
        if action in ("Buy", "Reinvest Shares"):
            lots.append([lot_date, q])
        elif action == "Transfer In":
            # Reconcile to authoritative broker balance: add a synthetic lot
            # for missing pre-CSV history, or trim FIFO lots if our running
            # count is inflated by CSV anomalies.
            tracked = sum(s for _, s in lots)
            diff = q - tracked
            if diff > 0.001:
                lots.append([lot_date, diff])
            elif diff < -0.001:
                excess = -diff
                while excess > 0.001 and lots:
                    if lots[0][1] <= excess + 1e-9:
                        excess -= lots[0][1]
                        lots.pop(0)
                    else:
                        lots[0][1] -= excess
                        excess = 0
        elif action == "Sell":
            remaining = q
            while remaining > 0.001 and lots:
                if lots[0][1] <= remaining + 1e-9:
                    remaining -= lots[0][1]
                    lots.pop(0)
                else:
                    lots[0][1] -= remaining
                    remaining = 0

    total = sum(shares for _, shares in lots)
    if total < 0.001:
        return None
    EPOCH = date(1899, 12, 30)
    weighted = round(sum((d - EPOCH).days * s for d, s in lots) / total)
    anchor = EPOCH + timedelta(days=weighted)
    return anchor.year, anchor.month, anchor.day


def compute_closed_avg_days(transactions):
    """Return FIFO-weighted average holding period in days across all sold lots.

    For a fully closed position this gives the actual weighted avg time each
    share was held, so annualized-yield formulas don't keep drifting as time
    passes after the close.  Returns None if no sells were matched to buys.
    """
    lots = []  # [[buy_date, shares_remaining], ...]
    total_share_days = 0.0
    total_shares = 0.0
    for row in transactions:
        date_str, action, opt_type, _sym, _strike, _exp, qty, _, _, _, _ = row
        if opt_type != "Stock" or qty == "":
            continue
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
        if not m:
            continue
        lot_date = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        q = float(qty)
        if action in ("Buy", "Reinvest Shares"):
            lots.append([lot_date, q])
        elif action == "Transfer In":
            # Reconcile to authoritative broker balance (see compute_avg_held_anchor).
            tracked = sum(s for _, s in lots)
            diff = q - tracked
            if diff > 0.001:
                lots.append([lot_date, diff])
            elif diff < -0.001:
                excess = -diff
                while excess > 0.001 and lots:
                    if lots[0][1] <= excess + 1e-9:
                        excess -= lots[0][1]
                        lots.pop(0)
                    else:
                        lots[0][1] -= excess
                        excess = 0
        elif action == "Sell":
            remaining = q
            while remaining > 0.001 and lots:
                if lots[0][1] <= remaining + 1e-9:
                    days = (lot_date - lots[0][0]).days
                    total_share_days += days * lots[0][1]
                    total_shares += lots[0][1]
                    remaining -= lots[0][1]
                    lots.pop(0)
                else:
                    days = (lot_date - lots[0][0]).days
                    total_share_days += days * remaining
                    total_shares += remaining
                    lots[0][1] -= remaining
                    remaining = 0
    if total_shares < 0.001:
        return None
    return round(total_share_days / total_shares)


def compute_status(transactions, open_positions):
    """Return (status, issues) where status is 'Closed', 'Consistent', or 'Inconsistent'.

    Checks:
    - Share count never goes negative in transaction history
    - Option contract counts never go negative for any symbol
    """
    issues = []

    if any(row[1] == "Transfer In" for row in transactions):
        issues.append("position includes a broker transfer — locate original buy transactions to resolve")

    shares = 0.0
    for row in transactions:
        _, action, opt_type, _sym, _, _, qty, _, _, _, _ = row
        if opt_type == "Stock" and qty != "":
            if action == "Transfer In":
                shares = float(qty)
            elif action in ("Buy", "Reinvest Shares"):
                shares += float(qty)
            elif action == "Sell":
                shares -= float(qty)
            if shares < -0.001:
                issues.append("share count went negative")
                break

    option_net = defaultdict(int)
    for row in transactions:
        _, action, opt_type, symbol, _, _, qty, _, _, _, _ = row
        if opt_type in ("Call", "Put") and qty != "":
            key = _norm_opt_symbol(symbol)
            q = int(qty)
            if action in ("Sell to Open", "Buy to Open"):
                option_net[key] += q
            elif action in ("Buy to Close", "Sell to Close", "Expired", "Assigned",
                            "Exercised"):
                option_net[key] -= q
                if option_net[key] < 0:
                    issues.append(f"option contracts went negative for {key}")

    if issues:
        return "Inconsistent", issues
    if shares <= 0.001 and not open_positions:
        return "Closed", []
    return "Consistent", []


# ── Money-weighted return (XIRR) ──────────────────────────────────────────────

#: A position held only a few days annualizes to an absurd rate — a two-day
#: put sale in schwab556 came out at 1045%. Arithmetically right, practically
#: useless, so short-lived positions report nothing at all.
MIN_XIRR_DAYS = 14


def _flow_date(date_str):
    """Trade date from a CSV date cell, ignoring any 'as of' processing date."""
    s = str(date_str).split(" as of ")[-1].strip()
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if not m:
        return None
    return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))


def build_cash_flows(transactions, terminal_value=None, terminal_date=None):
    """Dated cash flows for one position, ready for :func:`xirr`.

    Three sources, and the second is the one that matters:

    1. Every transaction's net amount — buys negative, premium and sales
       positive, exactly as the broker recorded them.

    2. **Collateral for short puts.** Selling a cash-secured put deploys
       capital that never appears as a cash flow, so the raw series is
       financing-shaped: money in for months, one big outflow at
       assignment. IRR on that has multiple roots and returns nonsense —
       schwab556's GXO scored +3101% on a $1,596 loss. Emitting the
       collateral (strike x 100 x contracts) as an outflow when the short
       opens, reversed when it closes, makes it an investment again and
       GXO becomes -40.9%. Rolls are handled by tracking total collateral
       and emitting only the change.

       Short *calls* get no such flow: the shares backing them are already
       in the series as a purchase. A naked call would be understated, but
       this portfolio does not hold them.

    3. A terminal flow for an open position — what liquidating today would
       net, which is the sheet's Close-out Value.
    """
    flows = []
    collateral = 0.0
    short_puts = defaultdict(float)

    for row in sorted(transactions, key=lambda r: _flow_date(r[0]) or date.min):
        d = _flow_date(row[0])
        if d is None:
            continue
        action, opt_type, strike, qty, amount = row[1], row[2], row[4], row[6], row[9]

        if amount not in ("", None):
            try:
                flows.append((d, float(amount)))
            except (TypeError, ValueError):
                pass

        if opt_type == "Put" and qty not in ("", None) and strike not in ("", None):
            try:
                q, k = float(qty), (strike, row[5])
            except (TypeError, ValueError):
                continue
            if action == "Sell to Open":
                short_puts[k] += q
            elif action in ("Buy to Close", "Expired", "Assigned"):
                short_puts[k] = max(0.0, short_puts[k] - q)
            else:
                continue
            try:
                need = sum(c * float(s) * 100 for (s, _e), c in short_puts.items())
            except (TypeError, ValueError):
                continue
            if abs(need - collateral) > 1e-9:
                flows.append((d, -(need - collateral)))
                collateral = need

    if terminal_value is not None:
        flows.append((terminal_date or date.today(), float(terminal_value)))
    return flows


def xirr(flows, min_days=MIN_XIRR_DAYS):
    """Money-weighted annual return, or None when it is not meaningful.

    Bisection rather than Newton: these series change sign several times,
    and Newton wanders off or lands on whichever root it happens to find.
    Bisection over a fixed bracket returns the root nearest normal returns
    or nothing at all, which is the honest outcome for a series that has
    no single rate of return.
    """
    if not flows or len(flows) < 2:
        return None
    if not (any(c < 0 for _, c in flows) and any(c > 0 for _, c in flows)):
        return None                       # all one direction: no return to find
    lo_d, hi_d = min(d for d, _ in flows), max(d for d, _ in flows)
    if (hi_d - lo_d).days < min_days:
        return None

    def npv(rate):
        return sum(cf / ((1.0 + rate) ** ((d - lo_d).days / 365.0))
                   for d, cf in flows)

    a, b = -0.9999, 50.0                  # -100% to +5000%
    fa, fb = npv(a), npv(b)
    if fa * fb > 0:
        return None                       # no root in range
    for _ in range(300):
        m = (a + b) / 2.0
        fm = npv(m)
        if fa * fm <= 0:
            b, fb = m, fm
        else:
            a, fa = m, fm
    return (a + b) / 2.0
