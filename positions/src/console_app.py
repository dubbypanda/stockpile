"""Streamlit console for the positions tracker.

Three panels over the same config.toml the CLI reads:

* **Run Sheets** — pick accounts by name and run the tracker over them,
  streaming its output.
* **Merge Transactions** — find brokerage exports sitting in `input/` that
  no account points at, route each to its account, preview the merge, and
  write it with a backup.
* **History** — every merge, archive, deletion and run the console has
  performed, plus every tracker run parsed out of `tracker.log`.

Run it with::

    uv run streamlit run positions/run_console.py

Nothing here reaches into the tracker's internals: a run shells out to
`run_tracker.py` exactly as the CLI does, so `sheets.configure()`'s global
state lives and dies in a process of its own.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import config
import history
from stocks_shared.csv_merge import (
    MergeError,
    detect_brokerage,
    file_tickers,
    merge_csv,
    norm,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = REPO_ROOT / "input"
BACKUP_DIR = INPUT_DIR / ".backups"
MERGED_DIR = INPUT_DIR / "merged"
TRACKER = REPO_ROOT / "positions" / "run_tracker.py"

#: Repo fixtures that live in input/ but are not brokerage exports.
_NOT_EXPORTS = {"test_stockpile.csv", "stockpile.csv.example"}


# ── Shared helpers ─────────────────────────────────────────────────────────

def _stamp(path: Path) -> float:
    """Cache key that changes whenever a file does."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


@st.cache_data(show_spinner=False)
def _tickers(path_str: str, brokerage: str, _mtime: float) -> set[str]:
    return file_tickers(path_str, brokerage)


@st.cache_data(show_spinner="Comparing files…")
def _preview(existing: str, incoming: str, brokerage: str,
             _m1: float, _m2: float):
    """Merge preview. Returns (result, error) — never raises into the page."""
    try:
        return merge_csv(existing, incoming, brokerage), None
    except MergeError as e:
        return None, str(e)


def _accounts():
    return config.get_all_accounts()


def _mtime_label(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%b %d, %H:%M")
    except OSError:
        return "missing"


# ── Panel 1: Merge ─────────────────────────────────────────────────────────

def _candidates(accounts):
    """Exports in input/ that no configured account points at.

    Top level only — input/one_off/ holds PDFs and scratch files, not
    exports.
    """
    configured = {Path(a.csv).resolve() for a in accounts if a.csv}
    out = []
    for path in sorted(INPUT_DIR.glob("*.csv")):
        if path.name in _NOT_EXPORTS or path.resolve() in configured:
            continue
        out.append((path, detect_brokerage(path)))
    return out


def _route(path: Path, brokerage: str | None, accounts):
    """Pick the account a candidate export belongs to.

    Brokerage narrows it; ticker overlap with each account's current CSV
    picks between the several accounts most brokerages have.
    """
    if brokerage is None:
        return None, "unrecognized format"
    same = [a for a in accounts if a.brokerage == brokerage and a.csv]
    if not same:
        return None, f"no {brokerage} account configured"
    if len(same) == 1:
        return same[0], f"only {brokerage} account"

    mine = _tickers(str(path), brokerage, _stamp(path))
    if not mine:
        return None, "no tickers found in file"
    scored = sorted(
        ((len(mine & _tickers(a.csv, brokerage, _stamp(Path(a.csv)))), a)
         for a in same),
        key=lambda s: -s[0],
    )
    best, acct = scored[0]
    if best == 0:
        return None, "no ticker overlap with any account"
    runner_up = scored[1][0] if len(scored) > 1 else 0
    note = f"{best} ticker(s) in common"
    if best == runner_up:
        note += " — tied, check before merging"
    return acct, note


def _render_replaced(result, columns):
    """Before/after for rows the incoming export updated, changed cols only."""
    rows = []
    for before, after in result.replaced:
        # `norm`, not a string compare: 16.30 -> 16.3 is not a change and
        # should not be shown as one.
        changed = [
            (columns[i].strip(), before[i], after[i])
            for i in range(min(len(before), len(after), len(columns)))
            if norm(before[i]) != norm(after[i])
        ]
        for col, was, now in changed:
            rows.append({
                "Date": after[0], "Column": col,
                "Was": was or "(empty)", "Now": now or "(empty)",
            })
    return rows


#: File / Downloaded / Merges into / Status / Archive / Delete
_ROW_COLS = [4, 2, 3, 3, 1, 1]


def _merge_status(path: Path, acct) -> str:
    """What merging this file would actually do.

    Shown per row so "which of these still need merging?" is answerable
    from the list, without selecting each one to find out. The preview is
    cached per (file, target) mtime pair, so this costs one parse per file
    on the first render and nothing after.
    """
    if acct is None:
        return "—"
    target = Path(acct.csv)
    result, error = _preview(str(target), str(path), acct.brokerage,
                             _stamp(target), _stamp(path))
    if error:
        return "⚠️ error"
    bits = []
    if result.added:
        bits.append(f"{len(result.added)} new")
    if result.replaced:
        bits.append(f"{len(result.replaced)} updated")
    return "🟢 " + ", ".join(bits) if bits else "already merged"


def _archive(path: Path) -> None:
    MERGED_DIR.mkdir(parents=True, exist_ok=True)
    dest = MERGED_DIR / path.name
    shutil.move(str(path), str(dest))
    history.record("archive", file=path.name,
                   to=dest.relative_to(REPO_ROOT).as_posix())
    _clear_caches()


def _delete(path: Path) -> None:
    size = path.stat().st_size if path.exists() else 0
    path.unlink(missing_ok=True)
    history.record("delete", file=path.name, bytes=size)
    _clear_caches()


def _candidate_rows(routed):
    """The candidate list, with archive and delete on every row.

    Actions live per-row rather than on a single selected file so a
    handful of stale exports can be cleared in a handful of clicks,
    without selecting each one first.
    """
    head = st.columns(_ROW_COLS)
    for col, label in zip(head, ["**File**", "**Downloaded**",
                                 "**Merges into**", "**Status**", "", ""]):
        col.markdown(label)

    pending = st.session_state.get("_pending_delete")

    for path, brokerage, acct, note in routed:
        c = st.columns(_ROW_COLS, vertical_alignment="center")
        c[0].markdown(f"`{path.name}`")
        c[1].caption(_mtime_label(path))
        c[2].caption(acct.name if acct else f"— {note}")
        c[3].caption(_merge_status(path, acct))

        if pending == str(path):
            # Confirm inline, in this row, so it is unmistakable which file
            # is about to go — several rows can look alike.
            if c[4].button("✅", key=f"yes_{path.name}",
                           help=f"Delete {path.name} permanently"):
                _delete(path)
                st.session_state.pop("_pending_delete", None)
                st.rerun()
            if c[5].button("✖️", key=f"no_{path.name}", help="Cancel"):
                st.session_state.pop("_pending_delete", None)
                st.rerun()
        else:
            # Archive is a move and needs no confirmation; delete is
            # irreversible and arms this row instead of acting.
            if c[4].button("📦", key=f"arch_{path.name}",
                           help=f"Archive {path.name} to input/merged/ — "
                                f"nothing is lost"):
                _archive(path)
                st.rerun()
            if c[5].button("🗑", key=f"del_{path.name}",
                           help=f"Delete {path.name} from disk"):
                st.session_state["_pending_delete"] = str(path)
                st.rerun()

    if pending:
        st.error(
            f"Delete `{Path(pending).name}` permanently? Confirm with ✅ on "
            f"its row. There is no undo — it does not go to the Recycle Bin. "
            f"📦 archives it instead, which is reversible."
        )
    else:
        st.caption("📦 archive to `input/merged/` · 🗑 delete from disk")


def panel_merge(accounts):
    st.subheader("Merge transactions")
    st.caption(
        "Brokerage exports in `input/` that no account points at. Each one "
        "is a full history re-download, so merging reconciles the overlap "
        "rather than appending."
    )

    cands = _candidates(accounts)
    if not cands:
        st.success("No unmerged exports in `input/` — everything is accounted for.")
        return

    routed = [(p, b, *_route(p, b, accounts)) for p, b in cands]
    _candidate_rows(routed)

    st.divider()

    # Only routable files can be previewed — there is nothing to show for a
    # file with no account to merge into. Clearing one out is a row action
    # above, so nothing is unreachable.
    labels = {f"{p.name}  →  {acct.name}": (p, b, acct)
              for p, b, acct, _ in routed if acct is not None}
    if not labels:
        st.warning("None of these could be routed to a configured account.")
        return

    # The picker's remembered choice can name a file that was just archived
    # or deleted; drop it before the widget sees an option that is gone.
    if st.session_state.get("merge_pick") not in labels:
        st.session_state.pop("merge_pick", None)

    chosen = st.selectbox("Preview a merge", list(labels), key="merge_pick")
    if not chosen:
        return
    path, brokerage, acct = labels[chosen]
    target = Path(acct.csv)

    result, error = _preview(str(target), str(path), brokerage,
                             _stamp(target), _stamp(path))
    if error:
        st.error(error)
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Added", len(result.added))
    c2.metric("Replaced", len(result.replaced))
    c3.metric("Unchanged", len(result.unchanged))
    c4.metric("Only in existing", len(result.existing_only))
    st.caption(
        f"`{target.name}` would go from {len(result.unchanged) + len(result.replaced) + len(result.existing_only)} "
        f"to {result.total_rows} rows — and from {result.txn_before} to "
        f"{result.txn_after} transactions as the {brokerage} parser reads "
        f"them. Verified: the merged file parses to exactly the union of "
        f"both inputs."
    )

    already_merged = not result.added and not result.replaced
    if already_merged:
        st.info(
            f"Nothing new — every row in `{path.name}` is already in "
            f"`{target.name}`. Use 📦 or 🗑 on its row above to clear it "
            f"from the list."
        )

    if result.added:
        with st.expander(f"{len(result.added)} new row(s)", expanded=True):
            st.dataframe(
                [dict(zip([h.strip() for h in result.header], r))
                 for r in result.added],
                hide_index=True, width="stretch",
            )

    if result.replaced:
        with st.expander(
            f"{len(result.replaced)} row(s) updated in place", expanded=True
        ):
            st.caption(
                "Same transaction, changed values — a settling trade filling "
                "in its cash balance, say. Matched on the identity columns, "
                "so these replace rather than duplicate."
            )
            st.dataframe(_render_replaced(result, result.header),
                         hide_index=True, width="stretch")

    if result.existing_only:
        with st.expander(f"{len(result.existing_only)} row(s) only in {target.name}"):
            st.caption(
                "The export does not contain these — hand-backfilled history, "
                "usually. They are kept."
            )
            st.dataframe(
                [dict(zip([h.strip() for h in result.header], r))
                 for r in result.existing_only],
                hide_index=True, width="stretch",
            )

    st.divider()
    archive = st.checkbox(
        f"Move `{path.name}` to `input/merged/` afterwards", value=True,
        help="Keeps it from showing up as a candidate on every visit.",
        disabled=already_merged,
    )
    # Always rendered, disabled when there is nothing to write. Hiding it
    # made the panel look broken on the common case where every export has
    # already been merged — a greyed-out button with a reason teaches the
    # control exists; a missing one just reads as a bug.
    if st.button(
        f"Merge into {target.name}", type="primary", disabled=already_merged,
        help=("Nothing to merge — every row in this export is already in "
              f"{target.name}." if already_merged else
              f"Backs up {target.name}, then writes {len(result.added)} new "
              f"and {len(result.replaced)} updated row(s) into it."),
    ):
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup = BACKUP_DIR / f"{target.stem}.{datetime.now():%Y%m%dT%H%M%S}.csv"
        shutil.copy2(target, backup)
        target.write_text(result.text, encoding="utf-8", newline="")
        moved = ""
        if archive:
            MERGED_DIR.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(MERGED_DIR / path.name))
            moved = f" · moved `{path.name}` to `input/merged/`"
        history.record(
            "merge", file=path.name, target=target.name, account=acct.name,
            added=len(result.added), replaced=len(result.replaced),
            unchanged=len(result.unchanged), rows=result.total_rows,
            txn_before=result.txn_before, txn_after=result.txn_after,
            backup=backup.relative_to(REPO_ROOT).as_posix(), archived=archive,
        )
        _clear_caches()
        st.success(
            f"Merged into `{target.name}` — {len(result.added)} added, "
            f"{len(result.replaced)} replaced. Backup at "
            f"`{backup.relative_to(REPO_ROOT).as_posix()}`{moved}. "
            f"Run **{acct.name}** on the next panel to push it to the sheet."
        )


def _clear_caches():
    _preview.clear()
    _tickers.clear()


# ── Panel 2: Run ───────────────────────────────────────────────────────────

#: Account (checkbox) / Brokerage / CSV / Updated / Run / Sheet link. Kept
#: narrow and left-packed: the earlier [3, 2] split pushed the details to
#: 60% of a wide window, so a row read as two unrelated halves.
_RUN_COLS = [3, 2, 3, 2, 1.4, 2]

#: Lines of the live tail sent per output line, and the pixel height of the
#: box holding it. The tail is short enough to fit without scrolling, so
#: the newest line is always the visible one; the finished log is written
#: whole into the same box, which scrolls.
_LIVE_TAIL = 14
_LOG_HEIGHT = 280

#: Progress is read off the tracker's own stdout. Nothing in the tracker
#: was changed to enable this, deliberately: `history.tracker_runs()`
#: parses the very same "Processing:" line out of tracker.log, so a new
#: field or a reworded banner there would silently break the History
#: panel. Everything needed is already emitted.
#:
#:   [ts] Processing: schwab | CSV: ./input/schwab556.csv   ← account starts
#:   Found 67 ticker(s): AAPL, AMD, ...                     ← denominator
#:     Processing MRNA...                                   ← one tick
#:   [ts] Done: schwab / 1a2b3c                             ← account ends
#:
#: The timestamp prefix on the account lines is what keeps them clear of
#: the per-ticker pattern, which is indented and never bracketed.
_ACCT_RE = re.compile(r"^\[[^\]]+\]\s*Processing:.*\bCSV:\s*(.+?)\s*$")
_DONE_RE = re.compile(r"^\[[^\]]+\]\s*Done:\s")
_FOUND_RE = re.compile(r"^\s*Found\s+(\d+)\s+ticker")
_TICK_RE = re.compile(r"^\s+Processing\s+(\S+?)\.{3}\s*$")


def _picked(accounts):
    """Accounts currently ticked.

    Read out of session_state rather than from the checkbox return
    values, because the Run button sits beside the heading — above the
    list — and Streamlit executes top to bottom, so those widgets have
    not run yet at that point. Their keyed state is already current for
    this rerun, so this agrees with what the boxes render a moment later.
    """
    out = []
    for a in accounts:
        if not st.session_state.get(f"run_{a.name}"):
            continue
        if a.csv and not Path(a.csv).exists():
            continue        # stale tick on an account whose CSV has gone
        out.append(a)
    return out


def _scroll_to_log(token):
    """Bring the run log into view as a run starts.

    Streamlit has no scroll API, so this goes out through a zero-height
    component and reaches back into the host page from its iframe — same
    origin, so window.parent is readable.

    Two details keep it working:

    * The token is embedded in the markup. Streamlit reuses a component
      whose HTML has not changed, so without something varying per run
      the script would fire once a session and never again.
    * It polls for the target instead of assuming it. The container is
      created moments earlier in the same rerun, and the script can win
      the race with its own delta being applied.
    """
    components.html(
        f"""
        <script>
          // run {token}
          (function () {{
            const doc = window.parent.document;
            let tries = 0;
            const timer = setInterval(function () {{
              // The whole block — heading, status, bar, log — not just the
              // log box, so the bar does not land above the fold.
              const el = doc.querySelector('[class*="st-key-pc_runblock"]');
              if (el) {{
                clearInterval(timer);
                el.scrollIntoView({{behavior: "smooth", block: "center"}});
              }} else if (++tries > 40) {{
                clearInterval(timer);
              }}
            }}, 50);
          }})();
        </script>
        """,
        height=0,
    )


def _duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"


def _run_label(s: dict) -> str:
    """One-line verdict for a finished run, used as the status header."""
    who = ", ".join(s["accounts"])
    dur = _duration(s["seconds"])
    if s["ok"]:
        return f"✅ {who} — {s['tickers']} ticker(s) in {dur}"
    return f"❌ {who} — exited with code {s['code']} after {dur}"


def _render_last(status_slot, log_slot):
    """The previous run, redrawn on later reruns.

    Placeholders only hold what the script run that filled them put there,
    so without this the result would vanish the moment anything else on the
    page was touched.
    """
    s = st.session_state.get("run_summary")
    if s:
        status_slot.markdown(_run_label(s))
    if log_slot is not None:
        log_slot.code("\n".join(st.session_state["run_log"]), language="text")


def _execute_run(picked, status_slot, bar_slot, log_slot):
    names = [a.name for a in picked]
    # The tracker names each account by CSV path rather than by its
    # config name, so map the stem back to something the user recognises.
    by_stem = {Path(a.csv).stem: a.name for a in picked if a.csv}

    log: list[str] = []
    st.session_state["run_log"] = log
    st.session_state.pop("run_summary", None)
    started = datetime.now()

    # -u is load-bearing: the tracker reports progress with plain print(),
    # and Python block-buffers stdout (~8KB) whenever it is a pipe rather
    # than a TTY. Without it the log arrives in bursts — often nothing
    # until an account finishes — so the run reads as hung. Unbuffered,
    # the stream is live and line-by-line, which is what drives the bar.
    argv = [sys.executable, "-u", str(TRACKER), "--accounts", *names]

    n_accts = len(picked)
    done_accts = 0
    # With one account there is no ambiguity worth a placeholder; with
    # several, the first "Processing:" line lands within a second or two.
    acct = names[0] if n_accts == 1 else "starting…"
    stage, tick, total, tick_n = "starting", "", 0, 0

    def detail():
        """Ticker-level text, shown under the bar."""
        if total and tick:
            return f"{tick} ({min(tick_n, total)}/{total})"
        return stage

    def label():
        """Account-level text, shown on the status header."""
        who = acct if n_accts == 1 else \
            f"{acct} ({min(done_accts + 1, n_accts)} of {n_accts})"
        return f"Running {who} — {detail()}"

    def fraction():
        # Accounts are weighted equally. Their ticker counts are only known
        # once each one's "Found N" line arrives, so weighting by real size
        # would make the bar jump backwards as later accounts report in.
        part = (tick_n / total) if total else 0.0
        return min((done_accts + part) / n_accts, 1.0)

    status_slot.markdown(f"⏳ Starting {', '.join(names)}…")
    bar_slot.progress(0.0, text=detail())
    proc = subprocess.Popen(
        argv, cwd=REPO_ROOT, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1,
        encoding="utf-8", errors="replace",
    )
    for raw in proc.stdout:
        line = raw.rstrip()
        log.append(line)

        moved = True
        if m := _ACCT_RE.match(line):
            stem = Path(m.group(1)).stem
            acct = by_stem.get(stem, stem)
            stage, tick, total, tick_n = "reading CSV", "", 0, 0
        elif m := _FOUND_RE.match(line):
            total = int(m.group(1))
            stage = f"{total} ticker(s)"
        elif m := _TICK_RE.match(line):
            tick, tick_n = m.group(1), tick_n + 1
        elif _DONE_RE.match(line):
            done_accts += 1
            total, stage = 0, "finished"
        else:
            moved = False

        # The tail redraws on every line; the bar and status line only when
        # something actually advanced, since most lines are neither. Only
        # the last few lines go out per line — sending the whole log each
        # time would make the run quadratic in its own output.
        if moved:
            status_slot.markdown(f"⏳ {label()}")
            bar_slot.progress(fraction(), text=detail())
        log_slot.code("\n".join(log[-_LIVE_TAIL:]), language="text")
    proc.wait()

    tickers = sum(1 for ln in log if _TICK_RE.match(ln))
    summary = {
        "ok": proc.returncode == 0,
        "code": proc.returncode,
        "accounts": names,
        "tickers": tickers,
        "seconds": round((datetime.now() - started).total_seconds(), 1),
    }
    st.session_state["run_summary"] = summary
    history.record(
        "run", accounts=names, exit_code=proc.returncode,
        seconds=summary["seconds"], tickers=tickers,
    )
    bar_slot.progress(1.0 if summary["ok"] else fraction(),
                      text=f"{tickers} ticker(s) across {n_accts} account(s)")
    status_slot.markdown(_run_label(summary))
    # The full log once the run is over: cheap now that it is written once
    # rather than per line, and the box it sits in scrolls.
    log_slot.code("\n".join(log), language="text")


def panel_run(accounts):
    picked = _picked(accounts)

    # Title only. The batch button used to sit here, but a run control at
    # the top of a nine-account list scrolls out of sight exactly when it
    # is needed — every way to start a run now lives with the rows.
    with st.container(key="pc_runhead", horizontal=True,
                      vertical_alignment="center", gap="medium"):
        st.subheader("Run sheets", width="content")
    go = False

    st.caption(
        "Rebuilds each selected account's Google Sheet from its CSV. "
        "Selected accounts run in one process, serially, so the Yahoo price "
        "cache is shared between them. Each run deletes and recreates every "
        "ticker tab in that sheet; the Summary tabs are preserved."
    )

    if not config.TOKEN_PATH.exists():
        st.warning(
            f"No Google token at `{config.TOKEN_PATH}` — the first run will "
            "open a browser to authorize. That popup is expected.",
            icon="🔐",
        )

    head = st.columns(_RUN_COLS)
    for col, label in zip(head, ["**Account**", "**Brokerage**", "**CSV**",
                                 "**Updated**", "", ""]):
        col.markdown(label)

    # Every row carries its own ▶ Run. The batch button lives beside the
    # title, which scrolls away on a long list — tick an account near the
    # bottom and the only control that would start it is off screen, which
    # reads as "there is no way to run this". A per-row verb is always
    # where the eye already is, and it needs no checkbox at all.
    row_pick = None
    for acct in accounts:
        csv_path = Path(acct.csv) if acct.csv else None
        missing = csv_path is not None and not csv_path.exists()
        c = st.columns(_RUN_COLS, vertical_alignment="center")
        c[0].checkbox(f"**{acct.name}**", key=f"run_{acct.name}",
                      disabled=missing)
        c[1].caption(acct.brokerage)
        if missing:
            c[2].caption(f"⚠️ `{csv_path.name}` missing")
        elif csv_path:
            c[2].caption(f"`{csv_path.name}`")
            c[3].caption(_mtime_label(csv_path))
        # Read directly rather than via on_click: the dispatch below runs
        # after this loop, so the click is already visible by then.
        if c[4].button("▶ Run", key=f"go_{acct.name}", type="primary",
                       disabled=missing,
                       help=f"Rebuild {acct.name}'s sheet now"):
            row_pick = acct
        c[5].link_button(
            "📊 Open sheet",
            f"https://docs.google.com/spreadsheets/d/{acct.sheet_id}",
            help=f"Open {acct.name}'s Google Sheet in a new tab",
        )

    # The batch control belongs with the checkboxes it reads, at the end of
    # the list where ticking them leaves you — not only at the top.
    if picked:
        st.divider()
        with st.container(key="pc_runfoot", horizontal=True,
                          vertical_alignment="center", gap="medium"):
            st.markdown(f"**{len(picked)} selected** — "
                        f"{', '.join(a.name for a in picked)}", width="content")
            go = st.button(
                "▶ Run Selected as Batch", key="pc_run_btn_foot",
                type="primary",
                help="One process, serially, so the Yahoo price cache is "
                     "shared between them.",
            )

    # Plainly always there while a run has output — no expander. It used to
    # live in an st.status, which collapsed itself out from under anyone
    # reading along. A live log has no business behind a disclosure
    # control, and Streamlit never reports expander state back to the
    # server, so "reopen what the user opened" was never available anyway.
    # Fixed height keeps a long log from walking off the bottom of the page.
    # Status line, progress bar and log in one block. They used to be split
    # — progress under the title, log down here — which meant scrolling to
    # the log on a fresh run left the bar behind at the top of the page.
    # Kept together, one scroll shows all of it.
    #
    # All three are placeholders filled in later, because the run loop
    # blocks: Streamlit renders top to bottom, so every slot the loop
    # writes into has to exist before the subprocess starts.
    status_slot = bar_slot = log_slot = None
    starting = bool(go or row_pick)
    if starting or st.session_state.get("run_log"):
        st.divider()
        with st.container(key="pc_runblock"):
            st.markdown("**Run log**")
            status_slot = st.empty()
            bar_slot = st.empty()
            with st.container(key="pc_runlog", height=_LOG_HEIGHT):
                log_slot = st.empty()
        # Only on a fresh run. Scrolling the page out from under someone
        # who clicked something else would be its own bug.
        if starting:
            seq = st.session_state.get("run_seq", 0) + 1
            st.session_state["run_seq"] = seq
            _scroll_to_log(seq)

    # A row button runs that one account. It wins over the batch button
    # because it is the more specific instruction, and both cannot be
    # clicked in the same rerun anyway.
    if row_pick:
        _execute_run([row_pick], status_slot, bar_slot, log_slot)
    elif go:
        _execute_run(picked, status_slot, bar_slot, log_slot)
    elif st.session_state.get("run_log"):
        _render_last(status_slot, log_slot)


# ── Panel 3: History ───────────────────────────────────────────────────────

_ACTION_ICON = {"merge": "🔀", "archive": "📦", "delete": "🗑",
                "run": "▶️"}


def _describe(e: dict) -> tuple[str, str]:
    """(what, detail) for one recorded action."""
    a = e.get("action")
    if a == "merge":
        return (
            f"{e.get('file')} → {e.get('target')}",
            f"{e.get('added', 0)} added, {e.get('replaced', 0)} replaced · "
            f"{e.get('txn_before', '?')} → {e.get('txn_after', '?')} transactions"
            + (" · archived" if e.get("archived") else ""),
        )
    if a == "archive":
        return e.get("file", ""), f"moved to {e.get('to', 'input/merged/')}"
    if a == "delete":
        kb = (e.get("bytes") or 0) / 1024
        return e.get("file", ""), f"deleted permanently · {kb:.1f} KB"
    if a == "run":
        accts = ", ".join(e.get("accounts", [])) or "—"
        ok = e.get("exit_code") == 0
        return accts, (("succeeded" if ok else
                        f"FAILED (exit {e.get('exit_code')})")
                       + f" · {e.get('seconds', 0):.0f}s")
    return str(a), ""


def panel_history():
    st.subheader("History")
    st.caption(
        "Everything this console has done. Deletions are listed here "
        "because this is the only remaining record that the file existed."
    )

    rows = history.entries()
    if not rows:
        st.info(
            "Nothing yet. Merges, archives, deletions and runs started from "
            "this console will appear here. Past runs from the command line "
            "are below — those come from `positions/tracker.log`."
        )
    else:
        st.dataframe(
            [{
                "When": e.get("ts", "").replace("T", "  "),
                "Action": f"{_ACTION_ICON.get(e.get('action'), '•')} "
                          f"{e.get('action', '')}",
                "What": _describe(e)[0],
                "Detail": _describe(e)[1],
            } for e in rows],
            hide_index=True, width="stretch",
        )
        c1, c2 = st.columns([1, 3])
        c1.download_button(
            "Download as JSONL",
            data=history.HISTORY_PATH.read_text(encoding="utf-8"),
            file_name="console_history.jsonl", mime="application/x-ndjson",
        )
        with c2.expander("Clear history"):
            st.caption(
                "Removes the log only — merged files, backups and sheets are "
                "untouched. The record of past deletions goes with it."
            )
            if st.button("Clear all history"):
                n = history.clear()
                st.success(f"Cleared {n} entries.")
                st.rerun()

    st.divider()
    runs = history.tracker_runs(limit=60)
    st.markdown("**Tracker runs** — from `positions/tracker.log`, so this "
                "includes runs started from the command line.")
    if not runs:
        st.caption("No runs logged yet.")
        return
    st.dataframe(
        [{
            "When": r["ts"],
            "Status": {"ok": "✅ ok", "error": "❌ error",
                       "incomplete": "⚠️ incomplete"}.get(r["status"], r["status"]),
            "Accounts": ", ".join(r["csvs"]) or "—",
            "Took": f"{r['seconds']:.0f}s",
            "Error": r["error"][:80],
        } for r in runs],
        hide_index=True, width="stretch",
    )
    st.caption(
        "⚠️ incomplete = the log has no completion line for that run — the "
        "tracker was interrupted, or is still running."
    )


# ── Entry point ────────────────────────────────────────────────────────────

#: Streamlit reserves ~6rem above the content to clear its fixed header,
#: then an st.title() adds another ~3rem of its own — most of a screen's
#: worth of nothing before the first control. This app has no sidebar, so
#: the left half of that header strip is empty and the title fits in it,
#: beside the toolbar rather than below it.
_COMPACT_CSS = """
<style>
  /* Positioned on the keyed CONTAINER, not on a <div> inside a markdown
     block. A raw div there renders inside .stMarkdown and never escapes to
     the header row — it just disappears behind Streamlit's chrome. Pinning
     an `st.container(key=...)` by its st-key- class is the pattern that
     works, same as the scanner's title-bar pills in
     options-scanner/options_scanner/styles.css. */
  [class*="st-key-pc_masthead"] {
      position: fixed;
      top: 14px;              /* near the scanner's proven --pill-top: 13px */
      left: 1.5rem;
      z-index: 999990;        /* Streamlit's chrome tops out around 999000 */
      width: auto !important;
      pointer-events: none;   /* never swallow a click meant for the app */
  }
  [class*="st-key-pc_masthead"] p {
      font-size: 1.3rem !important;
      font-weight: 600 !important;
      line-height: 1.2 !important;
      margin: 0 !important;
      white-space: nowrap;
  }
  /* Content starts just clear of the 3.75rem header instead of 6rem down.
     The header keeps its own background, so content scrolling beneath it
     is masked as usual. */
  .stMainBlockContainer, .main .block-container {
      padding-top: 3.8rem;
  }
  /* Run-sheets heading row. The h3 ships with its own top and bottom
     margin, which are unequal — so vertical_alignment:center centers the
     *box*, not the text, and the button reads as riding high. Zeroing the
     margins makes the centering true rather than compensating for it with
     a guessed nudge. */
  [class*="st-key-pc_runhead"] h3 {
      margin: 0 !important;
      padding: 0 !important;
  }
  /* Bigger than a default button: this is the one control on the panel that
     does something irreversible-ish, and it needs to read as switched on
     the moment an account is ticked. The selector is a substring match, so
     it still catches the batch button (key pc_run_btn_foot). */
  [class*="st-key-pc_run_btn"] button {
      font-size: 1.05rem !important;
      font-weight: 600 !important;
      padding: 0.5rem 1.4rem !important;
  }
  /* Batch row: air above it, because the divider sits close. The spacing
     goes on the CONTAINER rather than the button — padding on the button
     alone would push it off the text's centre line and undo the alignment
     the horizontal container establishes. */
  [class*="st-key-pc_runfoot"] {
      margin-top: 0.75rem !important;
  }
  /* Same reason as the h3 above: a <p> carries unequal top and bottom
     margins, so vertical_alignment:center centres the box rather than the
     text and the button reads as riding high next to it. */
  [class*="st-key-pc_runfoot"] p {
      margin: 0 !important;
      padding: 0 !important;
  }

  /* st.divider() is a 1px line carrying ~2em of its own margin, sitting in
     a block that the vertical layout's flex `gap` spaces again on both
     sides. Both have to come down or the rule still floats in whitespace. */
  hr {
      margin-top: 0.4rem !important;
      margin-bottom: 0.4rem !important;
  }
  .stElementContainer:has(hr) {
      margin-top: -0.5rem;
      margin-bottom: -0.5rem;
  }
</style>
"""


def main():
    st.set_page_config(page_title="Positions Console", page_icon="📒",
                       layout="wide")
    # Both the stylesheet and the title go inside the pinned container. A
    # style-only st.markdown at top level still gets its own element
    # container, and the vertical layout's flex `gap` spaces it like any
    # other row — ~1rem of blank above the tabs from an element that draws
    # nothing. Inside a position:fixed container it is out of flow, so it
    # costs no height. The <style> applies globally wherever it sits.
    with st.container(key="pc_masthead"):
        st.markdown(_COMPACT_CSS, unsafe_allow_html=True)
        st.markdown("📒 Positions Console")

    accounts = _accounts()
    if not accounts:
        st.error(
            "No accounts in `positions/config.toml`. Copy "
            "`config.toml.example` and add an `[[accounts]]` entry."
        )
        return

    panel = st.segmented_control(
        "Panel", ["Run Sheets", "Merge Transactions", "History"],
        default="Run Sheets", label_visibility="collapsed",
    )
    st.divider()
    if panel == "Merge Transactions":
        panel_merge(accounts)
    elif panel == "History":
        panel_history()
    else:
        panel_run(accounts)

    st.divider()
    st.caption(
        f"{len(accounts)} account(s) from `positions/config.toml` — "
        "still hand-edited; this console reads it, never writes it."
    )
