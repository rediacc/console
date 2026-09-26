#!/usr/bin/env python3
"""Shared context-budget arithmetic for the compaction-proximity hooks.

WHY THIS EXISTS. `agent/<session>/STATE.md` is the document that survives compaction, and until now it was refreshed on a 60-minute TIMER. A timer is blind to the only event that matters: it rewrites when nothing has changed and stays quiet when the window is about to close. This module gives the hooks a real proximity signal instead.

WHAT CLAUDE CODE ACTUALLY EXPOSES (verified against 2.1.235, not assumed):

  * NO hook payload carries token usage. `createBaseHookInput` in the bundle
    emits session_id, transcript_path, cwd, prompt_id, permission_mode,
    agent_id, agent_type, effort -- and nothing about the context window.
  * The TRANSCRIPT does. Every non-sidechain assistant entry carries
    `message.usage`, and input_tokens + cache_creation_input_tokens +
    cache_read_input_tokens on the LAST one is the size of the context that
    request carried. That is the number the status line shows.
  * Every hook gets `transcript_path`. So any hook can compute proximity from
    a tail read of one file. That is the whole mechanism.

THE THRESHOLD IS MEASURED, NOT DERIVED. There is no "reserve" setting, and the formula in the bundle turned out to predict the wrong number in the only unit this module can see; see COMPACT_MARGIN below for what was measured instead and why the derivation misled. With the window at 900_000 the trigger is treated as 885_000.

RESOLUTION ORDER, as this module implements it (env, then settings highest-scope-first, then the model cap, then evidence):

    1. CLAUDE_CODE_AUTO_COMPACT_WINDOW           clamped to [100_000, 1_000_000]
    2. <project>/.claude/settings.local.json     autoCompactWindow
    3. <project>/.claude/settings.json           autoCompactWindow
    4. $HOME/.claude/settings.json               autoCompactWindow
    5. the model's own max context               when nothing above is set
    then window = min(that, model max context), threshold = window - 15_000.

    OVERRIDING ALL OF IT: `window_floor`, the caller's evidence. Claude Code
    reads settings ONCE, at session start; this module reads them live. A
    window pinned into settings today does not apply to a session that started
    yesterday, and no hook payload reveals which window the running session
    actually got. A session carrying more tokens than the configured window
    permits has settled the question by surviving, and that observation wins.
"""

import calendar
import json
import os
import re
import sys
import time
from pathlib import Path

# --- Where the trigger actually is ----------------------------------------- DERIVED, and the derivation was right the first time. This constant was 15_000
# for one reason: reading the bundle gives trigger = window - min(maxOutputTokens,
# 20_000) - 13_000, and 53 observed compactions appeared to contradict it, so the formula was declared "checked against the wrong unit" and replaced by a measurement.
#
# `/context` settles it by printing the number outright:
#
# Auto-compact window: 1m tokens ⛝ Autocompact buffer: 33k tokens (3.3%)
#
# 33_000 is exactly min(20_000, 20_000) + 13_000. The formula describes the shipped behaviour; what was wrong was the inference drawn from compaction timings, which cluster where they do because a 1M window is reached in REPORTED prompt tokens long before the message list alone reaches 967_000.
#
# The old value was wrong in the dangerous direction: it under-reserved by 18_000 tokens, so every notice promised more headroom than existed.
COMPACT_MARGIN = 33_000
# Kept because the disproof logic below reasons about the hard blocking limit, which IS in the reported-token unit.
OUTPUT_RESERVE = 20_000
# The accepted range for the window, enforced by Claude Code on both the setting and the environment variable.
WINDOW_MIN = 100_000
WINDOW_MAX = 1_000_000

# --- Bands ----------------------------------------------------------------- TWO bands, not one, and the second one is not merely "later". The late band is where the operator wants the refresh; the early band exists because a rewrite is not free and a rewrite that gets interrupted by the compaction it was racing is worse than no rewrite at all.
#
# Measured, not guessed: 414 real `worklist.py --state` turns across this project's transcripts cost p50 2,246 / p90 3,603 / p99 4,876 tokens for the write step, and p50 4,802 / p99 10,344 / max 17,765 when you charge the whole preceding stretch of the turn to it. At 98% of a 867,000 threshold the headroom is 17,340 tokens, which covers the p99 comfortably and the worst
# case observed by 425 tokens. The early band is the insurance on that tail.
BANDS = (("early", 0.75), ("late", 0.98))

# Models with a native 1M window. Everything else Claude-shaped is 200K unless the id carries an explicit [1m] selector.
NATIVE_1M = ("claude-sonnet-5", "claude-fable-5")
# Models Claude Code holds to the 200K boundary when their window is under 1M.
BOUNDARY_200K = 200_000


def model_max_context(model):
    """Model max context in tokens, or None when the id is unrecognised.

    None is a real answer and the callers treat it as one: an unknown model means the derived threshold is a guess, and a guess is reported as such rather than dressed up as a measurement.
    """
    if not model:
        return None
    m = str(model).lower()
    if "[1m]" in m:
        return 1_000_000
    base = m.split("[")[0]
    if base in NATIVE_1M:
        return 1_000_000
    if base.startswith("claude-"):
        return BOUNDARY_200K
    return None


def _settings_files(project_dir):
    """Settings sources for `autoCompactWindow`, highest priority first.

    Managed/policy settings outrank all of these and are NOT read here: they live outside the repo and outside this hook's business. If one is ever set, this module's threshold will be wrong in the safe direction only when the managed window is LARGER; `--explain` names the sources it actually read so the gap is inspectable.
    """
    p = Path(project_dir) if project_dir else None
    out = []
    if p:
        out.append(p / ".claude" / "settings.local.json")
        out.append(p / ".claude" / "settings.json")
    home = os.environ.get("HOME")
    if home:
        out.append(Path(home) / ".claude" / "settings.json")
    return out


def configured_window(project_dir):
    """(window, source) as Claude Code would resolve it, env first."""
    env = os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW")
    if env:
        try:
            v = int(env.strip())
        except ValueError:
            v = None
        if v:
            return max(WINDOW_MIN, min(WINDOW_MAX, v)), "env"
    for f in _settings_files(project_dir):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001, S112 -- an unreadable settings file is not this hook's problem
            continue
        v = data.get("autoCompactWindow")
        if isinstance(v, int) and WINDOW_MIN <= v <= WINDOW_MAX:
            return v, str(f)
    return None, "unset"


# THE CAP-DISPROOF MECHANISM WAS DELETED ON 2026-08-24, because the pin rule below made it unreachable rather than merely redundant. It watched for a session carrying more tokens than its inferred model cap allows and, on that proof, kept the configured window. But with a pin present the pin now wins outright, so there is nothing left to prove; and with no pin `configured` is None,
# which its own guard rejected. Neither branch could ever fire again.
#
# Three mutation controls died with it, and that is the correct reading: they could no longer distinguish a working disproof from a missing one, because the outcome no longer depended on it. What survives is `window_floor`, which is a different and still-live claim -- evidence that the window is bigger than ANY configured value, which is the case where a pin was added after a
# session had already started.


def resolve_threshold(model, project_dir, window_floor=None):
    """Return the dict of everything the caller needs to explain itself.

    `window_floor` is the caller's accumulated EVIDENCE about this session, and it outranks every configured value. It exists because settings are read by Claude Code once, at session start, while this module reads them live: a window pinned into settings.json today does not apply to a session that started yesterday, and nothing in any hook payload reveals which window the running
    session actually got. A session that has carried more tokens than the configured window allows has answered that question by surviving.
    """
    configured, source = configured_window(project_dir)
    mmax = model_max_context(model)
    if window_floor and (not configured or window_floor > configured):
        return _finish(model, None, window_floor, "observed", from_evidence=True)
    if configured is None:
        # No pin. Claude Code would fall back to a model-tuned window; the honest answer here is the model's own max, flagged as derived.
        configured = mmax
    return _finish(model, mmax, configured, source)


def _finish(model, mmax, configured, source, from_evidence=False):
    if configured is None:
        return {
            "model": model,
            "model_max": None,
            "configured": None,
            "window": None,
            "threshold": None,
            "source": source,
            "confident": False,
            "window_from_evidence": from_evidence,
            "assumed_cap_overruled": False,
        }
    # THE PIN IS THE WINDOW. A cap inferred from the model id may not clip it: `claude-opus-5` is exactly what a 1M session reports (verified again on 2026-08-24 against a transcript entry carrying 228,201 prompt tokens), so clipping a pinned 1,000,000 down to the 200K boundary produced "1.9% until auto-compact" on a session that was 21% full -- every turn, for hours. Crying wolf
    # changes behaviour on every turn; going quiet is survivable, because PreCompact writes its facts snapshot either way.
    #
    # AND AN EXPLICIT CAP CANNOT CLIP EITHER, which is why there is no `min()` here at all: an explicit cap (a `[1m]` marker) is only ever 1,000,000, and `configured_window` clamps every pin to WINDOW_MAX, which is 1,000,000. A branch for it would be unreachable, and unreachable code in a module that decides when to warn is how the next reader is misled about what runs.
    window = configured
    assumed_cap_overruled = bool(mmax) and configured > mmax
    return {
        "model": model,
        "model_max": mmax,
        "configured": configured,
        "window": window,
        "threshold": window - COMPACT_MARGIN,
        "source": source,
        # A window taken on trust from a model id is not a measurement, a window derived from a session's own high-water mark is a fallback, and a pin allowed to overrule an assumed cap is a bet on the pin. None of the three is "confident"; the notice says so out loud in every case.
        "confident": mmax is not None and not from_evidence and not assumed_cap_overruled,
        "window_from_evidence": from_evidence,
        "assumed_cap_overruled": assumed_cap_overruled,
    }


def _iter_tail_lines(path, chunk):
    size = os.path.getsize(path)
    start = max(0, size - chunk)
    with open(path, "rb") as fh:
        fh.seek(start)
        data = fh.read()
    if start:
        # The first line is almost certainly truncated; drop it.
        data = data.split(b"\n", 1)[-1]
    return start, data.split(b"\n")


def _is_compact_boundary(d):
    """True for the `system` / `compact_boundary` entry a compaction writes.

    Kept SEPARATE from reading its size on purpose. The two questions have different answers when the entry is malformed, and conflating them is a real defect this project's own test caught: a boundary carrying no usable `postTokens` must still STOP the backward scan, because the entries behind it belong to a context that no longer exists. Treating "no size" as "no boundary" walks
    straight back to the pre-compaction peak -- the exact bug the boundary check exists to prevent.
    """
    return d.get("type") == "system" and d.get("subtype") == "compact_boundary"


def _compact_post_tokens(d):
    """Post-compaction context size from a compact_boundary entry, or None.

    The boundary entry carries `compactMetadata.postTokens` -- the size of the context the summary produced. It is the authoritative answer to "how much is in use" for the window between the compaction and the first assistant entry that follows it.
    """
    if not _is_compact_boundary(d):
        return None
    meta = d.get("compactMetadata") or {}
    post = meta.get("postTokens")
    return int(post) if isinstance(post, (int, float)) and post > 0 else None


def last_usage(transcript_path):
    """(context_tokens, model) from the last real assistant entry, or None.

    Reads the TAIL, growing the window until an entry is found, because a single transcript line here can be hundreds of kilobytes and the file can be tens of megabytes. Sidechain entries are skipped: a subagent's usage is not this session's context.

    THE SCAN STOPS AT A COMPACTION BOUNDARY, and that is the whole point of the boundary check below. Measured on this project's own transcript 2026-08-26: a PostToolUse hook fired in the gap between the compact_boundary entry and the first assistant entry after it, so the backward scan ran straight past the summary and returned the PRE-compaction peak -- 958,036 against a 967,000
    threshold, i.e. "0.9% until auto-compact, a headroom of 8,964 tokens", when the real post-compaction size was 30,359. Truncating the transcript one line earlier reproduces it exactly; one line later returns 98,043.

    That is the worst possible direction to be wrong in: the stale value is by construction the session's MAXIMUM, so the notice screams "nearly full" at precisely the moment the context has just been emptied. It is also not self-correcting within the turn -- the session reads the notice, believes it, and makes real decisions on it (this one delegated work and rushed a hand-off it
    did not need to). The usage-drop backstop in band-notice does clean up afterwards, but only on a LATER call, and only after the ladder has already been re-seated from a false peak.

    So: walking back past a compact_boundary is never valid. Its own `postTokens` is the correct reading for that window, and returning it beats returning nothing -- the notice stays useful instead of going silent for a call. The model is unchanged by compaction, so the scan continues purely to recover it.
    """
    p = Path(transcript_path)
    if not p.is_file():
        return None
    for chunk in (256 * 1024, 2 * 1024 * 1024, 16 * 1024 * 1024):
        try:
            start, lines = _iter_tail_lines(p, chunk)
        except OSError:
            return None
        hit_boundary = False
        post_tokens = None
        for raw_line in reversed(lines):
            raw = raw_line.strip()
            if not raw or not raw.startswith(b"{"):
                continue
            try:
                d = json.loads(raw)
            except Exception:  # noqa: BLE001, S112 -- a torn line is expected at a tail boundary
                continue
            if not hit_boundary and _is_compact_boundary(d):
                # Everything older than this belongs to a context that no longer exists. Stop treating it as usage; keep scanning ONLY to recover the model, which compaction does not change.
                hit_boundary = True
                post_tokens = _compact_post_tokens(d)
                continue
            if d.get("type") != "assistant" or d.get("isSidechain"):
                continue
            msg = d.get("message") or {}
            if hit_boundary:
                # This entry is OLDER than the boundary. Its usage is dead; the boundary's own postTokens is the only honest reading, and if the boundary did not carry one, silence beats the peak.
                return (post_tokens, msg.get("model")) if post_tokens else None
            u = msg.get("usage") or {}
            total = (
                (u.get("input_tokens") or 0)
                + (u.get("cache_creation_input_tokens") or 0)
                + (u.get("cache_read_input_tokens") or 0)
            )
            if total:
                return total, msg.get("model")
        if hit_boundary:
            # Boundary seen, no assistant entry in the window to name the model. Never grow the window past it -- there is nothing valid back there.
            return (post_tokens, None) if post_tokens else None
        if start == 0:
            return None
    return None


def band_for(usage, threshold):
    """Index of the highest band this usage has reached, or -1."""
    if not threshold or threshold <= 0:
        return -1
    idx = -1
    for i, (_name, pct) in enumerate(BANDS):
        if usage >= threshold * pct:
            idx = i
    return idx


# --- runtime state ---------------------------------------------------------


def state_dir():
    """Where the per-session band marker lives.

    Overridable so the control suite can drive the real hooks against a scratch directory instead of the live one.
    """
    override = os.environ.get("CTX_BAND_STATE_DIR")
    d = Path(override) if override else Path(__file__).resolve().parent / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def session_slug(session_id):
    """The same [:8] rule wl_store.agent_session_slug uses, so this module and the worklist store name the same session the same way."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(session_id or "unknown"))[:8] or "unknown"


def state_file(session_id):
    return state_dir() / ("%s.json" % session_slug(session_id))


def load_state(session_id):
    try:
        return json.loads(state_file(session_id).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- absent or corrupt both mean "no band announced yet"
        return {"epoch": 0, "band": -1}


_last_cleanup_time: list[float] = [
    0
]  # a one-element cell, not a bare module global -- see save_state()


def cleanup_stale_state_files(grace_hours=24, now=None):
    """Delete `*.json`/`*-onboard.json` in `state_dir()` older than `grace_hours`.

    Pure with respect to time: `now` is injectable so a test can pin it.
    Exceptions are caught and logged rather than propagated, the same contract `log_error` documents for the rest of this file, since a cleanup failure must stay a non-event for the caller.
    Safe because the only readers of a state file (`band-notice.py`, `epoch-reset.py`, `onboard.py`) load it for the currently running session only, and a live session's own file is refreshed on every save, so it stays out of the grace window while that session runs.
    """
    cutoff = (now if now is not None else time.time()) - grace_hours * 3600
    deleted = []
    total = 0
    try:
        for f in state_dir().iterdir():
            if not f.name.endswith(".json"):
                continue
            total += 1
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    deleted.append(f.name)
            except OSError:
                continue
    except Exception as exc:  # noqa: BLE001 -- a sweep failure must never break save_state
        log_error("cleanup_stale_state_files", exc)
    return len(deleted), total, deleted


def save_state(session_id, data):
    f = state_file(session_id)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, f)
    now = time.time()
    if now - _last_cleanup_time[0] > 60:
        _last_cleanup_time[0] = now
        try:
            deleted, total, names = cleanup_stale_state_files()
            if deleted:
                log_error(
                    "cleanup_stale_state_files",
                    Exception("swept %d of %d stale state file(s): %s" % (deleted, total, names)),
                )
        except Exception as exc:  # noqa: BLE001 -- fire-and-forget, save_state must still succeed
            log_error("cleanup_stale_state_files", exc)


def log_error(where, exc):
    """A hook that fails silently is a hook that cannot fire.

    Every entry point swallows its exceptions so it can never block a tool call or a compaction, which means the ONLY way a broken hook becomes visible is this file. It is append-only and never read by the hooks themselves.
    """
    try:
        line = "%s\t%s\t%s: %s\n" % (
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            where,
            type(exc).__name__,
            exc,
        )
        with open(state_dir() / "errors.log", "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:  # noqa: BLE001 -- nothing left to do if even this fails
        pass


def read_event():
    """The hook event off stdin. Never blocks on a terminal."""
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001
        return {}
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}


def project_dir(event):
    return (
        os.environ.get("CLAUDE_PROJECT_DIR")
        or event.get("cwd")
        or str(Path(__file__).resolve().parents[3])
    )


def state_md_path(project, session_id):
    return Path(project) / "agent" / session_slug(session_id) / "STATE.md"


def fmt(n):
    return f"{int(n):,}"


# --- the stop-hook retro before compaction ---------------------------------
# agent/plans/PLAN-stop-hook-retro-20260924.md section 8, box R20260924.11. The ledger is the ONE record of which retros were ordered, and it lives in the repo rather than in state_dir(): the band state file is reset on every compaction epoch, and the dedupe key `(session, band)` has to survive that. `.claude/hooks/stop/wl_retro.py` loads these helpers from this file
# rather than keeping a second reader of the same rows.
RETRO_LEDGER_REL = ("agent", "ledgers", "stop-hook-retros.jsonl")
RETRO_BANDS = ("early", "late", "post-compact")

# The order, emitted once per session per band on the first PostToolUse after STATE.md was rewritten past the crossing. Framed as a repo procedure with its source named, not as a system command: see band-notice.py's docstring for the one exception this text is to its "does not instruct" rule.
RETRO_ORDER = (
    "Stop-hook retro due (standing procedure PLAN-stop-hook-continuity.md P3.1, operator order 2026-09-24; band %(band)s, session %(me8)s). STATE.md was rewritten at %(state_at)s, after this band was crossed, so the recovery document is safe; this session's stop-hook experience is still in context and on disk.\n"
    "  1. Print the brief:  python3 .claude/hooks/stop/worklist.py --retro-brief %(me8)s %(band)s\n"
    "  2. Dispatch ONE Agent with subagent_type Plan and run_in_background true, with that brief as its prompt. Plan agents are read-only and do not count toward the writer cap.\n"
    "  3. Save what it returns verbatim to agent/plans/PLAN-stop-hook-retro-%(date)s.md (update the file if it exists).\n"
    "The tracking item is created at your next stop and auto-leased to the agent from the #id in its brief. Ledger: agent/ledgers/stop-hook-retros.jsonl. Emitted once per session per band."
)


def utc_stamp(epoch_seconds=None):
    """The ISO8601Z stamp the worklist store writes (wl_core.stamp_now), so ledger rows sort against its logs."""
    return time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if epoch_seconds is None else epoch_seconds)
    )


def retro_ledger_path(project):
    return Path(project).joinpath(*RETRO_LEDGER_REL)


def retro_rows(project):
    """Every parseable ledger row, oldest first. A torn or foreign line is skipped, never fatal."""
    try:
        text = retro_ledger_path(project).read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def retro_append(project, row):
    """One O_APPEND line, so two writers can never interleave inside a row; rows stay far under the 4 KB PIPE_BUF bound."""
    path = retro_ledger_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, (json.dumps(row, sort_keys=True) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def retro_live(rows):
    """The rows a `voided` event has not cancelled, voided events themselves dropped. A `voided` row cancels every EARLIER row of its `(session, band)`, so the pair's dedupe key is free again and a later `ordered` row for it is live (R20260924.17)."""
    dead: set[int] = set()
    seen: dict[tuple, list[int]] = {}
    for i, row in enumerate(rows):
        key = (row.get("session"), row.get("band"))
        if row.get("ev") == "voided":
            dead.update(seen.pop(key, ()))
            dead.add(i)
        else:
            seen.setdefault(key, []).append(i)
    return [r for i, r in enumerate(rows) if i not in dead]


def retro_void(project, me8, band, why):
    """Append the `voided` row freeing (me8, band); the one writer for it, so a misattributed order is corrected in the ledger's own format rather than by hand."""
    row = {"ev": "voided", "at": utc_stamp(), "session": me8, "band": band, "why": why}
    retro_append(project, row)
    return row


def retro_ordered(rows, me8, band):
    """The live `ordered` row for (session, band), or None. THE DEDUPE KEY is exactly this pair (the plan's Decision): a later epoch does not earn a second retro for a band already covered, unless a `voided` row freed it."""
    for row in retro_live(rows):
        if row.get("ev") == "ordered" and row.get("session") == me8 and row.get("band") == band:
            return row
    return None


def retro_window_start(rows, me8, before=None):
    """The `ordered` row the next retro's window starts after: the newest live one for this session, earlier than `before` (a row object) when given, whose band reached `saved`; failing that, the newest that reached `dispatched`; else None.

    NOT the newest `ordered` row (R20260924.17). An order nobody reviewed covered nothing, and taking its end as the next start is how a sub-agent's misattributed row at 19:01:46Z hid 19 blocked stops from the next brief.
    """
    live = retro_live(rows)
    cut = next((i for i, r in enumerate(live) if r is before), len(live))
    reached = {
        ev: {(r.get("session"), r.get("band")) for r in live if r.get("ev") == ev}
        for ev in ("saved", "dispatched")
    }
    earlier = [r for r in live[:cut] if r.get("ev") == "ordered" and r.get("session") == me8]
    for ev in ("saved", "dispatched"):
        hits = [r for r in earlier if (me8, r.get("band")) in reached[ev]]
        if hits:
            return hits[-1]
    return None


def retro_from_off(rows, me8, before=None):
    """Where the next retro's transcript range starts: the `to_off` of retro_window_start's row, or 0."""
    start = retro_window_start(rows, me8, before)
    return int(start.get("to_off") or 0) if start else 0


# --- who compacted ----------------------------------------------------------
# R20260924.16. A sub-agent's PostCompact reaches the hooks with the LEAD's session_id and transcript_path and no agent_id (measured 2026-09-24T19:01:44Z, agent a149262d8b6a1601f), so the payload cannot say whose context was replaced. The transcripts can: the compaction writes its `compact_boundary` into the compacting context's own file seconds before the hook runs.
COMPACT_ATTRIB_S = 120
COMPACT_TAIL = 2 * 1024 * 1024


def _stamp_epoch(stamp):
    try:
        return calendar.timegm(time.strptime(str(stamp)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, OverflowError):
        return None


def _newest_boundary(path, sidechain):
    """(epoch, record) of the newest compact_boundary in the file's last COMPACT_TAIL bytes whose isSidechain equals `sidechain`, or None."""
    try:
        _start, lines = _iter_tail_lines(path, COMPACT_TAIL)
    except OSError:
        return None
    for raw_line in reversed(lines):
        raw = raw_line.strip()
        if b"compact_boundary" not in raw or not raw.startswith(b"{"):
            continue
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        if _is_compact_boundary(d) and bool(d.get("isSidechain")) == sidechain:
            at = _stamp_epoch(d.get("timestamp"))
            return (at, d) if at is not None else None
    return None


def compaction_owner(transcript_path, sid, now=None):
    """ "lead", "agent:<id>" or "unknown": whose context the compaction that fired this PostCompact replaced.

    "lead" when the lead transcript's newest `isSidechain:false` boundary is within COMPACT_ATTRIB_S of `now`; else "agent:<id>" for the newest such boundary in a `<transcript minus .jsonl>/subagents/agent-*.jsonl` modified in that window; else "unknown", which the caller must treat as NOT the lead (the Decision: a wrong row takes a band for good, a missing one costs one retro).
    """
    now = time.time() if now is None else now
    if not transcript_path:
        return "unknown"
    lead = Path(transcript_path)
    hit = _newest_boundary(lead, False) if lead.is_file() else None
    if hit and abs(now - hit[0]) <= COMPACT_ATTRIB_S:
        return "lead"
    best = None
    try:
        agents = list((lead.with_suffix("") / "subagents").glob("agent-*.jsonl"))
    except OSError:
        agents = []
    for path in agents:
        try:
            if now - path.stat().st_mtime > COMPACT_ATTRIB_S:
                continue
        except OSError:
            continue
        got = _newest_boundary(path, True)
        if not got or abs(now - got[0]) > COMPACT_ATTRIB_S:
            continue
        rec_sid = got[1].get("sessionId")
        if sid and rec_sid and rec_sid != sid and session_slug(rec_sid) != session_slug(sid):
            continue
        if best is None or got[0] > best[0]:
            agent = got[1].get("agentId") or path.stem[len("agent-") :]
            best = (got[0], agent)
    return "agent:%s" % best[1] if best else "unknown"


def retro_order_row(
    project, me8, band, transcript, usage=None, threshold=None, epoch=None, state_md_at=""
):
    """Append the `ordered` row for (me8, band) and return it. The byte range runs from the previous retro's end to the transcript's current size."""
    rows = retro_rows(project)
    try:
        to_off = os.path.getsize(transcript) if transcript else 0
    except OSError:
        to_off = 0
    row = {
        "ev": "ordered",
        "at": utc_stamp(),
        "session": me8,
        "band": band,
        "epoch": epoch,
        "usage": usage,
        "threshold": threshold,
        "transcript": str(transcript or ""),
        "from_off": min(retro_from_off(rows, me8), to_off),
        "to_off": to_off,
        "state_md_at": state_md_at,
    }
    retro_append(project, row)
    return row
