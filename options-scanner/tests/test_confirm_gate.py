"""The Confirm → Place gate shared by every order-entry screen.

The property under test: **Place can only exist for numbers the user actually
confirmed.** An edit after confirming, or an order that stops validating, has to
drop back to Confirm — otherwise Place sits there attached to values nobody
approved, which is exactly the confusing state this gate exists to prevent.
"""

import pytest

from options_scanner import confirm_gate as cg

LIMIT, QTY = "lim_key", "qty_key"
KEYS = (LIMIT, QTY)
CONFIRM = "place_confirm_X"


class FakeSt:
    """Just the session_state surface confirm_gate touches."""

    def __init__(self, state=None):
        self.session_state = dict(state or {})


@pytest.fixture
def st(monkeypatch):
    fake = FakeSt({LIMIT: 1.25, QTY: 2})
    monkeypatch.setattr(cg, "st", fake)
    return fake


# ── arming ───────────────────────────────────────────────────────────────────

def test_not_armed_before_confirm(st):
    assert cg.armed(CONFIRM, KEYS) is False


def test_arm_then_armed(st):
    cg.arm(CONFIRM, KEYS)()
    assert cg.armed(CONFIRM, KEYS) is True


def test_arm_clears_a_stale_result_banner(st):
    st.session_state["result_X"] = {"ok": False, "msg": "earlier failure"}
    cg.arm(CONFIRM, KEYS, clear_keys=("result_X",))()
    assert "result_X" not in st.session_state


def test_arm_snapshot_survives_repeated_checks(st):
    cg.arm(CONFIRM, KEYS)()
    assert cg.armed(CONFIRM, KEYS) and cg.armed(CONFIRM, KEYS)


# ── an edit after confirming disarms ─────────────────────────────────────────

def test_editing_the_limit_disarms(st):
    cg.arm(CONFIRM, KEYS)()
    st.session_state[LIMIT] = 1.30
    assert cg.armed(CONFIRM, KEYS) is False


def test_editing_the_quantity_disarms(st):
    cg.arm(CONFIRM, KEYS)()
    st.session_state[QTY] = 3
    assert cg.armed(CONFIRM, KEYS) is False


def test_editing_back_to_the_confirmed_value_stays_disarmed(st):
    # The arm is dropped on the first mismatch, so retyping the original number
    # does not silently re-arm — Confirm has to be pressed again.
    cg.arm(CONFIRM, KEYS)()
    st.session_state[QTY] = 3
    assert cg.armed(CONFIRM, KEYS) is False
    st.session_state[QTY] = 2
    assert cg.armed(CONFIRM, KEYS) is False


def test_float_noise_does_not_disarm(st):
    # A repaint can round-trip 1.25 through float math; that must not read as an
    # edit and make the user confirm twice.
    cg.arm(CONFIRM, KEYS)()
    st.session_state[LIMIT] = 1.25 + 1e-12
    assert cg.armed(CONFIRM, KEYS) is True


# ── invalid orders can't leave Place behind ──────────────────────────────────

def test_invalid_order_disarms_and_clears(st):
    cg.arm(CONFIRM, KEYS)()
    assert cg.armed(CONFIRM, KEYS, valid=False) is False
    # Cleared, not merely hidden: fixing the order must not resurrect Place
    # without a fresh Confirm.
    assert cg.armed(CONFIRM, KEYS, valid=True) is False


def test_emptied_input_is_invalid(st):
    # st.number_input returns None when its box is cleared.
    st.session_state[QTY] = None
    assert cg.valid_values(KEYS) is False


def test_zero_and_negative_values_are_valid(st):
    # A roll's net limit is legitimately zero or negative (a net debit), so
    # validity must test for None, not falsiness.
    st.session_state[LIMIT] = 0.0
    assert cg.valid_values(KEYS) is True
    st.session_state[LIMIT] = -0.45
    assert cg.valid_values(KEYS) is True


def test_arming_with_an_empty_input_cannot_produce_a_live_place(st):
    st.session_state[LIMIT] = None
    cg.arm(CONFIRM, KEYS)()
    assert cg.armed(CONFIRM, KEYS, valid=cg.valid_values(KEYS)) is False


# ── validation happens in the callback, so Confirm can stay clickable ─────────
# Confirm is deliberately NOT disabled on invalid input: Streamlit only commits a
# number box on blur, so a disabled button would force "click away, wait for the
# button to re-enable, then click Confirm". The click itself commits the field
# and the callback re-validates.

def _reject_over_four(_limit, qty):
    return None if (qty or 0) <= 4 else f"{qty} exceeds the 4 you can cover"


def test_confirm_with_an_invalid_value_refuses_to_arm(st):
    st.session_state[QTY] = 5
    cg.arm(CONFIRM, KEYS, validate=_reject_over_four)()
    assert cg.armed(CONFIRM, KEYS) is False
    assert not st.session_state.get(CONFIRM)


def test_confirm_after_correcting_the_value_arms_on_that_click(st):
    # The failing click, then the user fixes the size and clicks Confirm again:
    # the callback sees the corrected value and arms — no blur dance.
    arm_cb = cg.arm(CONFIRM, KEYS, validate=_reject_over_four)
    st.session_state[QTY] = 5
    arm_cb()
    assert cg.armed(CONFIRM, KEYS) is False
    st.session_state[QTY] = 4
    arm_cb()
    assert cg.armed(CONFIRM, KEYS) is True


def test_a_refused_arm_leaves_a_previous_result_banner_alone(st):
    # Nothing was armed, so nothing about the last attempt should change.
    st.session_state["result_X"] = {"ok": False, "msg": "earlier failure"}
    st.session_state[QTY] = 5
    cg.arm(CONFIRM, KEYS, clear_keys=("result_X",),
           validate=_reject_over_four)()
    assert st.session_state["result_X"]["msg"] == "earlier failure"


def test_validator_sees_values_as_of_the_click(st):
    seen = []

    def _spy(limit, qty):
        seen.append((limit, qty))
        return None

    arm_cb = cg.arm(CONFIRM, KEYS, validate=_spy)
    st.session_state[LIMIT] = 2.50
    st.session_state[QTY] = 3
    arm_cb()
    assert seen == [(2.50, 3)]


# ── getting back ─────────────────────────────────────────────────────────────

def test_cancel_disarms(st):
    cg.arm(CONFIRM, KEYS)()
    cg.disarm(CONFIRM)()
    assert cg.armed(CONFIRM, KEYS) is False


def test_reset_disarms(st):
    cg.arm(CONFIRM, KEYS)()
    cg.reset(CONFIRM)
    assert cg.armed(CONFIRM, KEYS) is False


# ── the arm must not outlive the screen ──────────────────────────────────────

def test_arm_is_stored_as_a_dict(st):
    # run_app re-asserts str/int/float/tuple session keys every rerun so widget
    # values survive tab switches. The arm must NOT be one of those types, or an
    # armed order would follow the user across tabs instead of resetting.
    cg.arm(CONFIRM, KEYS)()
    stored = st.session_state[CONFIRM]
    assert isinstance(stored, dict)
    assert not isinstance(stored, (str, int, float, tuple, bool))


# ── reseed_on_change: a live default that doesn't eat what you typed ──────────

WID, SEED = "close_qty_1", "close_qty_seed_1"


def test_reseed_initializes_an_empty_field(st):
    cg.reseed_on_change(WID, SEED, 4)
    assert st.session_state[WID] == 4


def test_reseed_leaves_a_user_value_alone_while_the_basis_holds(st):
    # The regression: clamping on every rerun ate an over-max entry on the same
    # rerun the Confirm click caused, so the error never rendered — the number
    # just snapped back to the max.
    cg.reseed_on_change(WID, SEED, 4)
    st.session_state[WID] = 5              # user typed 5 against a 4-lot
    cg.reseed_on_change(WID, SEED, 4)
    assert st.session_state[WID] == 5, "the typed value must survive to be reported"


def test_reseed_when_the_basis_changes(st):
    # A partial close shrank the position from 4 to 2 → re-default the field.
    cg.reseed_on_change(WID, SEED, 4)
    st.session_state[WID] = 3
    cg.reseed_on_change(WID, SEED, 2)
    assert st.session_state[WID] == 2


def test_reseed_recovers_an_emptied_field(st):
    cg.reseed_on_change(WID, SEED, 4)
    st.session_state[WID] = None           # box cleared
    cg.reseed_on_change(WID, SEED, 4)
    assert st.session_state[WID] == 4


def test_reseed_is_idempotent(st):
    for _ in range(3):
        cg.reseed_on_change(WID, SEED, 4)
    assert st.session_state[WID] == 4 and st.session_state[SEED] == 4


def test_two_screens_arm_independently(st):
    other = "place_confirm_Y"
    cg.arm(CONFIRM, KEYS)()
    assert cg.armed(CONFIRM, KEYS) is True
    assert cg.armed(other, KEYS) is False


# ── place_button: the click is acknowledged before the order goes out ─────────
# A live placement is a couple of Schwab round trips, seconds long. The plain
# button sat there looking unpressed for all of it, got pressed again, and the
# second click opened a second script run that re-entered placement while the
# first was still in flight — which surfaced as a bogus "couldn't resolve the
# account" on an order that had actually been sent.

PLACE_KEY = "confirm_AMD_120_2026-09-18"


class FakeSlot:
    """An ``st.empty()`` slot: records every button drawn into it. Only the
    first draw is the real (clickable) button, so only it can report a click."""

    def __init__(self, clicked: bool):
        self._clicked = clicked
        self.drawn: list[dict] = []

    def button(self, label, **kw):
        self.drawn.append({"label": label, **kw})
        return self._clicked if len(self.drawn) == 1 else False

    @property
    def last(self) -> dict:
        return self.drawn[-1]


class FakeRender(FakeSt):
    """session_state plus the one element call place_button makes."""

    def __init__(self, clicked: bool = False):
        super().__init__()
        self.slot = FakeSlot(clicked)

    def empty(self):
        return self.slot


@pytest.fixture
def render(monkeypatch):
    def _make(clicked: bool = False):
        fake = FakeRender(clicked)
        monkeypatch.setattr(cg, "st", fake)
        return fake
    return _make


def test_unclicked_place_draws_one_live_button(render):
    fake = render(clicked=False)
    with cg.place_button("Place Trade · 🔴 LIVE", key=PLACE_KEY,
                         confirm_key=CONFIRM) as go:
        assert go is False
    assert len(fake.slot.drawn) == 1
    assert fake.slot.last["label"] == "Place Trade · 🔴 LIVE"
    assert not fake.slot.last.get("disabled")


def test_the_click_swaps_in_a_dead_button_before_the_order_is_sent(render):
    fake = render(clicked=True)
    with cg.place_button("Place Trade · 🔴 LIVE", key=PLACE_KEY,
                         confirm_key=CONFIRM) as go:
        assert go is True
        # What the user is looking at while Schwab is being called: this is the
        # whole point, so it must already be drawn when the body runs.
        assert fake.slot.last["label"] == cg.SENDING_LABEL
        assert fake.slot.last["disabled"] is True


def test_nothing_clickable_remains_once_placement_starts(render):
    fake = render(clicked=True)
    with cg.place_button("Place Trade · 🔴 LIVE", key=PLACE_KEY,
                         confirm_key=CONFIRM):
        pass
    # Every draw after the first is disabled — a second click can't reach the
    # submit, whatever the user does with the mouse while the order is in
    # flight.
    assert all(b.get("disabled") for b in fake.slot.drawn[1:])


def test_each_draw_gets_its_own_widget_key(render):
    fake = render(clicked=True)
    with cg.place_button("Place Trade · 🔴 LIVE", key=PLACE_KEY,
                         confirm_key=CONFIRM):
        pass
    keys = [b["key"] for b in fake.slot.drawn]
    assert keys[0] == PLACE_KEY
    assert len(set(keys)) == len(keys), "duplicate keys would crash Streamlit"


def test_a_failed_order_leaves_the_original_label_disabled(render):
    # Falling out of the body without rerunning means the order failed and its
    # error is about to render. "⏳ Sending order…" frozen above a rejection
    # would claim an order is still on its way.
    fake = render(clicked=True)
    with cg.place_button("Place Trade · 🔴 LIVE", key=PLACE_KEY,
                         confirm_key=CONFIRM):
        pass
    assert fake.slot.last["label"] == "Place Trade · 🔴 LIVE"
    assert fake.slot.last["disabled"] is True


class _Rerun(Exception):
    """Stand-in for the exception st.rerun() raises."""


def test_a_placed_order_ends_on_the_sending_button(render):
    # The success paths end in st.rerun(), whose exception unwinds through the
    # generator — nothing is drawn after it, and the rerun repaints anyway.
    fake = render(clicked=True)
    with pytest.raises(_Rerun):
        with cg.place_button("Place Trade · 🔴 LIVE", key=PLACE_KEY,
                             confirm_key=CONFIRM):
            raise _Rerun
    assert fake.slot.last["label"] == cg.SENDING_LABEL


def test_the_button_is_drawn_into_the_column_it_was_given(render):
    # The Place button lives in a column; the submit and its spinner render
    # below, outside it. So the slot has to come from the caller's container.
    fake = render(clicked=False)
    col = FakeRender(clicked=False)
    with cg.place_button("Place Trade", key=PLACE_KEY, confirm_key=CONFIRM,
                         container=col):
        pass
    assert col.slot.drawn and not fake.slot.drawn


def test_the_click_disarms_before_the_order_is_sent(render):
    # Ahead of the caller's own disarm: an element call after the submit (the
    # spinner closing, an error) can raise Streamlit's rerun exception and cut
    # this run short. Whatever runs next must find Confirm, not an armed Place
    # with a queued second click waiting to fire it.
    fake = render(clicked=True)
    fake.session_state[CONFIRM] = {"values": [1.25, 2]}
    with cg.place_button("Place Trade · 🔴 LIVE", key=PLACE_KEY,
                         confirm_key=CONFIRM):
        assert fake.session_state[CONFIRM] is False


def test_an_unclicked_place_leaves_the_arm_alone(render):
    # Every rerun redraws this button; only a click may disarm.
    fake = render(clicked=False)
    fake.session_state[CONFIRM] = {"values": [1.25, 2]}
    with cg.place_button("Place Trade · 🔴 LIVE", key=PLACE_KEY,
                         confirm_key=CONFIRM):
        pass
    assert fake.session_state[CONFIRM] == {"values": [1.25, 2]}
