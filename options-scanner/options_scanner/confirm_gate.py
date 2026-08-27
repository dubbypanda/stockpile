"""Two-step order placement: **Confirm** arms an order, **Place** sends it.

Every order-entry screen in the app — the Sell Put/Call dialog, the tracked-trade
close, the live-position close, and the roll — follows the same rules, kept here
so they can't drift apart:

* **Place** exists only after Confirm was pressed *on the values now on screen*,
  and only while those values still validate.
* Editing the limit or the contract count after confirming **disarms**: you drop
  back to Confirm rather than being offered Place for a price or size you never
  confirmed. That is the whole point of the confirm step — it attests to specific
  numbers, not to a general intention to trade.
* Confirm is disabled while armed, and Cancel is the way back. The two buttons
  are never both live.
* Confirm stays **clickable while the inputs are invalid** — it just refuses to
  arm. Disabling it there would strand the user: Streamlit only commits a number
  box on blur, so they'd have to click away, wait for the button to re-enable,
  and only then press Confirm. Validation lives in the ``arm`` callback, which
  sees the values as of the click.
* **Place acknowledges the click before it blocks** (``place_button``): it swaps
  itself for a disabled "sending" button on the way to the broker, so a
  placement that takes seconds can't be pressed twice.

The arm is stored under `confirm_key` as a snapshot of the input widgets' values,
read from session_state by widget key. Two deliberate choices:

* **A dict, not a tuple.** ``run_app`` re-asserts str/int/float/tuple session
  keys on every rerun so widget values survive tab switches. An order arm must
  *not* survive that — leaving a tab and coming back should land you on Confirm.
  A dict is skipped by that loop and garbage-collected with the tab.
* **``on_click`` callbacks, not ``if st.button(...)``.** A callback runs before
  the rerun renders, so Confirm draws disabled and Place appears in the *same*
  frame. It also reads the widgets after Streamlit applies this interaction's
  edits, so typing a size and hitting Confirm arms the size you typed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager

import streamlit as st


def _norm(v):
    """Normalize a widget value for comparison. Floats are rounded so a repaint's
    floating-point noise can't read as a user edit; None (an emptied number box)
    stays None so `valid_values` can reject it."""
    if isinstance(v, float):
        return round(v, 6)
    return v


def snapshot(value_keys: Iterable[str]) -> dict:
    """The current values of the input widgets named in `value_keys`."""
    return {"values": [_norm(st.session_state.get(k)) for k in value_keys]}


def valid_values(value_keys: Iterable[str]) -> bool:
    """Whether every input has a usable value.

    ``st.number_input`` returns None when its box is emptied, which would
    otherwise reach the order builder as ``int(None)``. Callers combine this with
    their own domain validation (coverage, collateral, market hours).
    """
    return all(st.session_state.get(k) is not None for k in value_keys)


def armed(confirm_key: str, value_keys: Iterable[str], *,
          valid: bool = True) -> bool:
    """Whether the **Place** step should render.

    Returns False *and drops the arm* when the order stopped validating or any
    input changed since Confirm. Call this **before** drawing the Confirm button
    so that button can be disabled in the same frame.
    """
    stored = st.session_state.get(confirm_key)
    if not stored:
        return False
    if not valid or stored != snapshot(value_keys):
        st.session_state[confirm_key] = False
        return False
    return True


def arm(confirm_key: str, value_keys: Iterable[str], *,
        clear_keys: Iterable[str] = (),
        validate: Callable[..., str | None] | None = None
        ) -> Callable[[], None]:
    """``on_click`` callback for the Confirm button.

    `validate` is called with the values behind `value_keys` **as of this click**
    and returns an error string (don't arm) or None (arm). Validating here, not
    by disabling the button, is what lets Confirm stay clickable while an error
    is on screen: a click commits the number box you were just typing in *and*
    fires this callback, so correcting a value and pressing Confirm works in one
    action instead of "click away to commit, wait for the button to re-enable,
    then click Confirm".

    `clear_keys` are session keys to drop when arming — typically the previous
    placement result, so a stale success/error banner doesn't sit under a fresh
    confirm panel.
    """
    keys = list(value_keys)
    clear = list(clear_keys)

    def _cb() -> None:
        if validate is not None:
            if validate(*[st.session_state.get(k) for k in keys]):
                return  # still invalid — the rerun re-renders the error
        st.session_state[confirm_key] = snapshot(keys)
        for k in clear:
            st.session_state.pop(k, None)
    return _cb


def disarm(confirm_key: str) -> Callable[[], None]:
    """``on_click`` callback for the Cancel button — collapses the confirm panel
    on the first click (a callback runs before the body re-renders)."""
    def _cb() -> None:
        st.session_state[confirm_key] = False
    return _cb


def reseed_on_change(widget_key: str, seed_key: str, value) -> None:
    """Re-default a keyed input when its *basis* changes — never otherwise.

    A keyed ``number_input`` ignores its ``value=`` after first render, so a
    default that tracks something live (the position size, a quote) has to be
    written through session_state. Doing that on every rerun silently overwrites
    whatever the user just typed: an over-max contract count got clamped back to
    the position size on the very rerun the Confirm click triggered, so the error
    describing it never rendered — the number just snapped back with no
    explanation.

    Writing only when `value` differs from the recorded seed keeps both
    behaviors: a position that shrank (partial close) re-seeds the field, while a
    number the user is in the middle of correcting survives to be validated and
    reported.
    """
    if st.session_state.get(widget_key) is None or (
            st.session_state.get(seed_key) != value):
        st.session_state[widget_key] = value
        st.session_state[seed_key] = value


def reset(confirm_key: str) -> None:
    """Disarm right now, outside a callback — for screens that bail out early
    (e.g. the order stopped building at all), so a later fix can't resurrect a
    Place button the user never re-confirmed."""
    st.session_state[confirm_key] = False


# Shared button copy, so every screen explains the disabled Confirm the same way.
ARMED_HELP = "Already confirmed — use Cancel below to change the order."

SENDING_LABEL = "⏳ Sending order…"
SENDING_HELP = ("Your order is on its way to Schwab — this can take a few "
                "seconds.")
SENDING_SPINNER = "Sending your order to Schwab — this can take a few seconds…"
SENT_HELP = ("Already submitted — read the result below. To try again, Cancel "
             "and confirm the order afresh.")


@contextmanager
def place_button(label: str, *, key: str, confirm_key: str,
                 container=None) -> Iterator[bool]:
    """The **Place** button, as a context manager whose value is "send it now".

    ::

        with confirm_gate.place_button("Place Trade · 🔴 LIVE", key=k,
                                       confirm_key=ck, container=col) as submit:
            if submit:
                with st.spinner(confirm_gate.SENDING_SPINNER):
                    result = _submit_order(...)
                ...

    Placing takes seconds — Schwab is a couple of round trips away — and a
    plain ``st.button`` goes on looking unpressed for every one of them. It got
    pressed a second time, and that click opened a *second* script run that
    re-entered placement while the first was still in flight; two runs hitting
    Schwab at once surfaced as a bogus "Couldn't resolve the target account" on
    an order that had in fact been sent.

    So the button is drawn into an ``st.empty()`` slot and, on the click that
    yields True, immediately overwrites itself with a disabled copy. That swap
    is enqueued *before* the caller's submit blocks, so the frontend shows a
    dead "sending" button for the whole trip and there is nothing left to
    click.

    On the way out the slot is rewritten once more, back to the original label
    but still disabled — reached only when the body returns without rerunning,
    i.e. the order failed and its error is about to render. Leaving "⏳ Sending
    order…" frozen above a rejection would say an order is still in flight when
    none is. Retrying goes through Cancel → Confirm on purpose: "rejected" and
    "sent, then the connection dropped" look identical from here, so the way
    back to Place is the same one that attests to the numbers.

    The acknowledgement itself keeps no session flag, deliberately: it lives and
    dies inside the run that places the order, so a run interrupted between the
    click and the submit can't leave a latch behind that fires an order later
    without a click.

    The click does drop the arm (`confirm_key`) on the way in, ahead of the
    caller's own disarm. An order in flight is no longer a confirmable order,
    and any element call after the submit — the spinner closing, an error — can
    raise Streamlit's rerun exception and end this run early. Disarming first
    means the next run comes back to Confirm rather than to an armed Place with
    a queued second click waiting to fire it.
    """
    slot = (container if container is not None else st).empty()
    clicked = slot.button(label, key=key, type="primary", width="stretch")
    if clicked:
        st.session_state[confirm_key] = False
        slot.button(SENDING_LABEL, key=f"{key}__sending", type="primary",
                    width="stretch", disabled=True, help=SENDING_HELP)
    yield clicked
    # Skipped by construction on the success paths: they end in st.rerun(),
    # whose exception unwinds straight through this generator.
    if clicked:
        slot.button(label, key=f"{key}__sent", type="primary", width="stretch",
                    disabled=True, help=SENT_HELP)
