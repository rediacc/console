"""wl_outcomes: what followed each check the Stop hook emitted (agent/plans/PLAN-stop-hook-effort-tuning.md T1).

THE ASK (operator 2026-10-14): the `smart` effort level should improve itself from what sessions live through. The session a check blocks is the worst judge of whether the check should exist, so the table is tuned by OUTCOME, and this module records the outcomes.

EVERY EMISSION GETS AN ID. A check that fires on a stop becomes one pending entry in the session's state doc (`effort_outcomes`): its key, the verdict the effort level gave it (`block`, `advise` or `off`), the level, the subjects its text names (item ids, plan files, paths) and when. `observe` runs once per stop, beside the effort verdicts in `wl_checks.run_stop`, and `note` runs inside `outq_add` for every advisory. A key already pending, or the same key with the same text as the emission last classified, is not a new emission: a check that holds a stop for ten stops with the same words is one emission.

THE FOLLOW-UP IS CLASSIFIED within WINDOW_STOPS stops (operator ruling: "A commit or tick naming the item, within 3 stops"):
  `work`       a worklist tick or lease, a plan tick (the plan file moved) or a commit touching what the check named after it fired; a check that names nothing takes any of this session's ticks, leases or commits;
  `overruled`  the operator lowered the effort level so the key is quieter now, answered a demotion /ask for the key, or the check's claim was refuted at emission (every item it named was already closed);
  `paperwork`  the window closed and only a status reply (a `## Remaining` section) or a STATE.md rewrite followed;
  `expired`    the window closed with neither.
A classified emission becomes one row of agent/ledgers/effort-outcomes.jsonl. Operator actions are rows of their own (`kind: operator`, `strong: true`). A row also carries `miss`: a CI red or a review finding (MISS_KEYS) fired after it inside the window, which is how a demoted key that should have spoken is found (wl_effort_tune).

The judge's `continue` verdicts are emissions too, under the key `judge`, read from its per-session log at the next stop; they feed the judge-error shapes (wl_effort_tune.judge_shapes), not the table.

NEVER WEDGES A STOP. Every entry point swallows its own failure: a measurement that cannot be taken is a missing row, never a block. Reads no environment variable.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import pathlib
import re
import secrets
import subprocess

import wl_effort
import wl_floor
import wl_judge
import wl_retro

LEDGER_REL = ("agent", "ledgers", "effort-outcomes.jsonl")
PROPOSALS_REL = ("agent", "ledgers", "effort-proposals.jsonl")
STATE_KEY = "effort_outcomes"
WINDOW_STOPS = 3
OUTCOMES = ("work", "paperwork", "overruled", "expired")
# A CI red, an unanswered PR review or a per-commit review finding after an emission: the miss a quieter check may have let through.
MISS_KEYS = frozenset({"ci-red", "commit-review", "pr-review"})
# The tuner's own request is not a check to tune.
UNTRACKED = frozenset({"effort-tune"})
PENDING_CAP = 200
SEEN_CAP = 400
TEXT_CAP = 200

_ITEM = re.compile(r"#([0-9a-f]{8}(?:[0-9a-f]{4})?)\b")
_PLAN = re.compile(r"\b(PLAN-[A-Za-z0-9._-]+?\.md)\b")
_PATH = re.compile(
    r"(?<![\w/.-])((?:\.claude|\.ci|\.github|agent|docs|packages|private|scripts)/[\w./-]*\w\.\w+)"
)
_HEX = re.compile(r"^[0-9a-f]{8}(?:[0-9a-f]{4})?$")
_REMAINING = re.compile(r"^#{1,6}\s*Remaining\b", re.MULTILINE)


def now_stamp():
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch_of(stamp):
    try:
        return (
            datetime.datetime.strptime(str(stamp), "%Y-%m-%dT%H:%M:%SZ")
            .replace(tzinfo=datetime.UTC)
            .timestamp()
        )
    except ValueError:
        return None


def ledger_path(root):
    return pathlib.Path(root).joinpath(*LEDGER_REL)


def proposals_path(root):
    return pathlib.Path(root).joinpath(*PROPOSALS_REL)


def read_rows(path):
    """Every JSON object line of `path`; a torn or foreign line is skipped, a missing file is []."""
    out = []
    with contextlib.suppress(OSError):
        for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(ValueError):
                row = json.loads(line)
                if isinstance(row, dict):
                    out.append(row)
    return out


def append_rows(path, rows):
    """One O_APPEND write per row, so concurrent sessions interleave whole lines."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        for row in rows:
            os.write(fd, (json.dumps(row, sort_keys=True) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def new_id(prefix="eo"):
    return "%s-%s" % (prefix, secrets.token_hex(4))


def subjects(key, text):
    """What a check names: `items` (#ids), `plans` (PLAN-*.md basenames), `paths` (repo paths) and `tokens` (a key's `:<subject>` suffix that is not an item id)."""
    text = str(text or "")
    items = set(_ITEM.findall(text))
    tokens = set()
    if ":" in str(key):
        suffix = str(key).split(":", 1)[1]
        if _HEX.match(suffix):
            items.add(suffix)
        elif suffix:
            tokens.add(suffix)
    return {
        "items": sorted(items),
        "plans": sorted(set(_PLAN.findall(text))),
        "paths": sorted(set(_PATH.findall(text))),
        "tokens": sorted(tokens),
    }


def _named(subj):
    return any(subj.get(k) for k in ("items", "plans", "paths", "tokens"))


def _sig(key, text):
    return hashlib.sha1(("%s\0%s" % (key, text)).encode("utf-8", "replace")).hexdigest()[:12]


def _st(state_doc):
    st = state_doc.get(STATE_KEY)
    if not isinstance(st, dict):
        st = {}
        state_doc[STATE_KEY] = st
    st.setdefault("stop", 0)
    st.setdefault("pending", [])
    st.setdefault("seen", {})
    return st


def _entry(st, key, verdict, level, text, epoch, at=None):
    """A new pending entry, or None when `key` is already pending or is the emission last classified."""
    key = str(key)
    if wl_floor.base(key) in UNTRACKED:
        return None
    sig = _sig(key, text)
    if any(e.get("key") == key for e in st["pending"]) or st["seen"].get(key) == sig:
        return None
    entry = {
        "id": new_id(),
        "key": key,
        "verdict": verdict,
        "level": level,
        "text": str(text or "").strip().splitlines()[0][:TEXT_CAP]
        if str(text or "").strip()
        else "",
        "sig": sig,
        "subjects": subjects(key, text),
        "at": at or now_stamp(),
        "stop": int(st["stop"]),
        "epoch": epoch,
        "paper": False,
        "miss": False,
        "refuted": "",
    }
    st["pending"].append(entry)
    del st["pending"][:-PENDING_CAP]
    return entry


def note(state_doc, key, text, shown):
    """Record an advisory (`wl_checks.outq_add`) as an emission: `advise` when the level queues it, `off` when it hides it. Only inside a stop (`wl_effort.active()`), so a verb's or a SessionStart's queue writes record nothing."""
    with contextlib.suppress(Exception):
        level = wl_effort.active()
        if level is None:
            return
        st = _st(state_doc)
        _entry(st, key, wl_effort.ADVISE if shown else wl_effort.OFF, level, text, st.get("epoch"))


# ---- the facts a classification reads -----------------------------------------------------------


def _git(root, *args):
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def commits_since(root, since):
    """[(sha, epoch, message, files)] for commits on HEAD committed at or after `since` (an ISO stamp), newest first, at most 60."""
    out = _git(
        root,
        "log",
        "-n",
        "60",
        "--since=%s" % since,
        "--format=%x1e%H%x1f%ct%x1f%B%x1f",
        "--name-only",
    )
    rows = []
    for chunk in (out or "").split("\x1e"):
        parts = chunk.split("\x1f")
        if len(parts) < 4:
            continue
        with contextlib.suppress(ValueError):
            rows.append(
                (
                    parts[0].strip(),
                    int(parts[1]),
                    parts[2],
                    [f for f in parts[3].split("\n") if f.strip()],
                )
            )
    return rows


def _owner8(rec):
    return str(rec.get("owner") or "")[:8]


def _work(entry, fold, me8, commits, root):
    """The evidence string for `work` after `entry`, or ""."""
    at = entry["at"]
    subj = entry.get("subjects") or {}
    items = set(subj.get("items") or ())
    named = _named(subj)
    for rec in getattr(fold, "items", None) or ():
        rid = str(rec.get("id") or "")
        if items:
            if rid not in items:
                continue
        elif named or _owner8(rec) != me8:
            continue
        if rec.get("state") == "x" and str(rec.get("upd") or "") >= at:
            return "tick #%s" % rid
        if str(rec.get("lease_at") or "") >= at:
            return "lease #%s" % rid
    plans_dir = pathlib.Path(root) / "agent" / "plans"
    at_s = _epoch_of(at) or 0
    for plan in subj.get("plans") or ():
        for path in (plans_dir / plan, plans_dir / "_done" / plan):
            with contextlib.suppress(OSError):
                if path.stat().st_mtime >= at_s:
                    return "plan tick %s" % plan
    for sha, when, msg, files in commits:
        if when < at_s:
            continue
        if not named:
            return "commit %s" % sha[:10]
        hay = msg + "\n" + "\n".join(files)
        needles = [*items, *(subj.get("plans") or ()), *(subj.get("tokens") or ())]
        if any(n in hay for n in needles) or set(subj.get("paths") or ()) & set(files):
            return "commit %s" % sha[:10]
    return ""


def _refuted(entry, fold):
    """`refuted: ...` when every item the check named was already closed when it fired."""
    items = (entry.get("subjects") or {}).get("items") or ()
    if not items:
        return ""
    by_id = getattr(fold, "by_id", None) or {}
    for rid in items:
        rec = by_id.get(rid)
        if not rec or rec.get("state") not in ("x", "~") or str(rec.get("upd") or "") > entry["at"]:
            return ""
    return "refuted: %s already closed" % ", ".join("#" + r for r in items)


def _row(entry, outcome, why, me8, strong=False):
    return {
        "id": entry["id"],
        "kind": "outcome",
        "key": entry["key"],
        "level": entry.get("level"),
        "verdict": entry.get("verdict"),
        "outcome": outcome,
        "why": why[:200],
        "session": me8,
        "epoch": entry.get("epoch"),
        "stop": entry.get("stop"),
        "at": entry.get("at"),
        "decided": now_stamp(),
        "subjects": entry.get("subjects"),
        "strong": bool(strong),
        "miss": bool(entry.get("miss")),
        "text": entry.get("text", ""),
    }


def _operator_row(me8, signal, **fields):
    return {
        "id": new_id(),
        "kind": "operator",
        "signal": signal,
        "strong": True,
        "session": me8,
        "at": now_stamp(),
        **fields,
    }


def _ctx_epoch(session_id):
    with contextlib.suppress(Exception):
        return int(wl_retro.ctx().load_state(session_id).get("epoch") or 0)
    return None


def _judge_rows(worklist, me8, since_ts):
    """[(ts, reason)] for the judge's `continue` verdicts logged after `since_ts`."""
    out = []
    with contextlib.suppress(Exception):
        for row in read_rows(wl_judge.judge_log_path(worklist, me8)):
            ts = int(row.get("ts") or 0)
            if ts > since_ts and row.get("verdict") == "continue":
                out.append((ts, str(row.get("reason") or "")))
    return out


def _answers_since(root, since):
    """[(key, row)] for operator /ask answers recorded after `since` that accept a demotion: the operator overruling that check."""
    return [
        (str(row.get("key") or ""), row)
        for row in read_rows(proposals_path(root))
        if row.get("kind") == "answer"
        and row.get("decision") == "accept"
        and str(row.get("at") or "") > since
    ]


def observe(
    root, worklist, session_id, state_doc, level, violations, fold, last_msg, compaction_due=False
):
    """One stop's bookkeeping: record this stop's emissions, the operator's actions since the last stop, and classify what is due. Returns the rows written. Never raises."""
    with contextlib.suppress(Exception):
        return _observe(
            root, worklist, session_id, state_doc, level, violations, fold, last_msg, compaction_due
        )
    return []


def _observe(
    root, worklist, session_id, state_doc, level, violations, fold, last_msg, compaction_due
):
    me8 = str(session_id or "unknown")[:8]
    st = _st(state_doc)
    st["stop"] = int(st["stop"]) + 1
    stop = st["stop"]
    epoch = _ctx_epoch(session_id)
    st["epoch"] = epoch
    rows = []
    overruled = {}

    # Operator actions since the last stop: an effort change, and accepted demotion answers.
    prev = st.get("level")
    if prev and prev != level and level in wl_effort.LEVELS:
        rows.append(_operator_row(me8, "effort-change", **{"from": prev, "to": level}))
        for e in st["pending"]:
            if wl_effort.rank(level) < wl_effort.rank(prev) and wl_effort.verdict(
                e["key"], level
            ) != e.get("verdict"):
                overruled[e["id"]] = "operator lowered effort %s -> %s" % (prev, level)
    st["level"] = level
    since = str(st.get("answers_at") or now_stamp())
    for key, ans in _answers_since(root, since):
        rows.append(_operator_row(me8, "ask-answer", key=key, answer=ans.get("id")))
        for e in st["pending"]:
            if wl_floor.base(e["key"]) == key:
                overruled[e["id"]] = "operator accepted a demotion of %s" % key
    st["answers_at"] = now_stamp()

    # This stop's emissions.
    fired = set()
    for vkey, _always, text in violations or ():
        fired.add(wl_floor.base(vkey))
        verdict = wl_effort.verdict(vkey, level, compaction_due=compaction_due)
        entry = _entry(st, vkey, verdict, level, text, epoch)
        if entry is not None:
            entry["refuted"] = _refuted(entry, fold)
    judge_ts = int(st.get("judge_ts") or 0)
    for ts, reason in _judge_rows(worklist, me8, judge_ts):
        judge_ts = max(judge_ts, ts)
        entry = _entry(
            st,
            "judge",
            wl_effort.BLOCK,
            level,
            reason,
            epoch,
            at=datetime.datetime.fromtimestamp(ts, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        if entry is not None:
            entry["refuted"] = _refuted(entry, fold)
    st["judge_ts"] = judge_ts

    # What this stop says about the earlier emissions.
    status_reply = bool(_REMAINING.search(last_msg or ""))
    state_md = pathlib.Path(root) / "agent" / me8 / "STATE.md"
    try:
        state_mtime = state_md.stat().st_mtime
    except OSError:
        state_mtime = None
    for e in st["pending"]:
        if e["stop"] >= stop:
            continue
        at_s = _epoch_of(e["at"]) or 0
        if status_reply or (state_mtime is not None and state_mtime >= at_s):
            e["paper"] = True
        if fired & MISS_KEYS:
            e["miss"] = True

    # Classify.
    keep = []
    commits = None
    for e in st["pending"]:
        if e["id"] in overruled:
            rows.append(_row(e, "overruled", overruled[e["id"]], me8, strong=True))
        elif e.get("refuted"):
            rows.append(_row(e, "overruled", e["refuted"], me8))
        elif e["stop"] >= stop:
            keep.append(e)
            continue
        else:
            if commits is None:
                oldest = min(x["at"] for x in st["pending"])
                commits = commits_since(root, oldest)
            why = _work(e, fold, me8, commits, root)
            if why:
                rows.append(_row(e, "work", why, me8))
            elif stop - e["stop"] >= WINDOW_STOPS:
                if e.get("paper"):
                    rows.append(
                        _row(e, "paperwork", "only a status reply or a STATE.md rewrite", me8)
                    )
                else:
                    rows.append(
                        _row(e, "expired", "nothing followed in %d stops" % WINDOW_STOPS, me8)
                    )
            else:
                keep.append(e)
                continue
        st["seen"][e["key"]] = e.get("sig")
    st["pending"] = keep
    if len(st["seen"]) > SEEN_CAP:
        st["seen"] = dict(list(st["seen"].items())[-SEEN_CAP:])
    if rows:
        append_rows(ledger_path(root), rows)
    return rows
