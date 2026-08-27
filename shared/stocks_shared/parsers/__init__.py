"""Brokerage CSV parsers. Import directly: from stocks_shared.parsers.schwab import ..."""

SUPPORTED = ("schwab", "robinhood", "fidelity", "merrill")

#: Money-market sweep funds — where idle cash sits, not positions taken.
#: They hold a fixed $1.00 NAV, so every concept a position tab is built
#: around (cost basis, holding period, gain, annualized yield on capital)
#: is meaningless for them, and the constant churn actively distorts it:
#: schwab556's SWVXX recycled the same few hundred dollars into $122,756
#: of lifetime "Amount Invested". Parsers route these to other_rows so the
#: transactions stay visible without being modelled as a position.
#:
#: Defined here rather than per-parser because the same cash shows up
#: under a different symbol at each brokerage.
CASH_EQUIVALENTS = frozenset({
    "SWVXX",   # Schwab Value / Prime Advantage Money
    "SNVXX", "SNSXX", "SNAXX", "SWGXX", "SGUXX", "SCOXX",  # other Schwab
    "SPAXX",   # Fidelity Government Money Market
    "FDRXX", "FZFXX", "SPRXX",                             # other Fidelity
})


def get_parser(brokerage: str):
    """Return a brokerage's ``parse_all_transactions`` callable.

    Imports lazily so a caller only pays for the parser it uses. Raises
    ValueError on an unknown brokerage; callers that want to exit with a
    message should catch it.
    """
    b = brokerage.lower()
    if b == "schwab":
        from stocks_shared.parsers.schwab import parse_all_transactions
    elif b == "robinhood":
        from stocks_shared.parsers.robinhood import parse_all_transactions
    elif b == "fidelity":
        from stocks_shared.parsers.fidelity import parse_all_transactions
    elif b == "merrill":
        from stocks_shared.parsers.merrill import parse_all_transactions
    else:
        raise ValueError(
            f"Unknown brokerage '{brokerage}'. Supported: {', '.join(SUPPORTED)}")
    return parse_all_transactions
