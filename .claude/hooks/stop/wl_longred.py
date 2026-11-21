"""wl_longred: the landing PR's per-round ledger and the long-red verdict read from it (agent/plans/PLAN-simple-two-tree-loop.md D4, box B6).

ONE ROW PER ROUND. Every push, rerun or watchdog retry on the landing PR whose run has finished appends one row to agent/ledgers/landing-rounds.jsonl (created on the first write, never by hand): `round, utc, kind (push|rerun|watchdog-retry), run_id, heads, fix_target, reds (each with its category), greens, delta (newly_green, newly_red, regressed, repeat), open_hours, trigger`, plus `pr` and `ids` (the job ids that identify the round, so the same finished run is never recorded twice).

ONE VERDICT PER STOP, read from the rows alone, so a restart resumes where the ledger is. The rulings of 2026-11-21 (ruling 8) fix the thresholds:

  operator-only  a red ci_diagnose classed `operator-only` (HTTP 401, an expired secret, a billing refusal): ask at once; no retry fixes it.
  outage-retry   every red of the latest round is an outside outage (GitHub 5xx, a registry refusal, no runner, an unreachable upstream): rerun after 10, 20, 40 and 80 minutes, then every 120.
  outage-ask     outage rounds have run back to back for 24 h: ask the operator.
  wall-ask       72 h since the PR opened and still red: ask the operator, DEFAULT "keep fixing".
  stuck          one check red after 3 rounds whose fix_target named THAT check: hand it to the development session with the rows as evidence.
  churn          a push regressed a previously green check in 2 of the last 4 rounds: pause and consult the development session (keep, change or undo).

`handover_trigger` turns a stuck or churn verdict into the record the handover contract (box B7) consumes; nothing here writes a handover itself.

No network and no rediacc_ci import: wl_ci hands in what it already read.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import os
import re
from typing import Any

LEDGER_REL = ("agent", "ledgers", "landing-rounds.jsonl")
KINDS = ("push", "rerun", "watchdog-retry")

OUTAGE_GAPS_MIN = (10, 20, 40, 80)
OUTAGE_STEADY_MIN = 120
OUTAGE_ASK_H = 24
WALL_H = 72
STUCK_FIXES = 3
CHURN_REGRESSIONS = 2
CHURN_WINDOW = 4
WALL_DEFAULT = "keep fixing"

# ci_diagnose signatures that name a failure OUTSIDE the tree: a rerun is the fix. `slow-setup` is absent on purpose (a renet phase running long is renet's code), and so is every code row.
OUTAGE_SIGNATURES = frozenset(
    {
        "github-api-5xx",
        "registry-refused",
        "runner-lost",
        "runner-not-acquired",
        "upstream-unreachable",
        "bitwarden-5xx",
        "network",
        "pkg-mirror",
        "pkg-install-stall",
    }
)

FIX_TARGET_RE = re.compile(r"^Fix-Target:\s*(.+?)\s*$", re.MULTILINE)

# Verdict order: the first that fires is the primary; every other one that fires rides `also`.
ORDER = ("operator-only", "outage-ask", "wall-ask", "outage-retry", "stuck", "churn")
ASKS = frozenset({"operator-only", "outage-ask", "wall-ask"})
HANDOVERS = frozenset({"stuck", "churn"})


@dataclasses.dataclass
class Verdict:
    kind: str = "none"
    check: str = ""
    rounds: list[int] = dataclasses.field(default_factory=list)
    next_gap_min: int = 0
    due_utc: str = ""
    default: str = ""
    why: str = ""
    pr: Any = None
    also: list[str] = dataclasses.field(default_factory=list)

    @property
    def ask(self) -> bool:
        return self.kind in ASKS

    def as_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["ask"] = self.ask
        return d


def ledger_path(root) -> str:
    return os.path.join(str(root), *LEDGER_REL)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _stamp(t: datetime.datetime) -> str:
    return t.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(stamp: Any) -> datetime.datetime | None:
    if not stamp:
        return None
    try:
        t = datetime.datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.UTC)


def _now(now: Any) -> datetime.datetime:
    if now is None:
        return _utcnow()
    if isinstance(now, datetime.datetime):
        return now if now.tzinfo else now.replace(tzinfo=datetime.UTC)
    return _parse(now) or _utcnow()


def read_rows(root, pr: Any = None) -> list[dict[str, Any]]:
    """The ledger's rows, oldest first, only `pr`'s when given. A malformed line is skipped; an absent ledger is []."""
    out: list[dict[str, Any]] = []
    try:
        with open(ledger_path(root), encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and (pr is None or str(row.get("pr")) == str(pr)):
                    out.append(row)
    except OSError:
        return []
    return out


def _lock_path(path: str) -> str:
    """The flock sidecar in TMPDIR, not beside the ledger, so no untracked `.lock` lands in the tree (wl_claimcheck._census_lock's reason)."""
    base = os.path.join(os.environ.get("TMPDIR", "/tmp"), "claude-worklist", ".judge")
    os.makedirs(base, exist_ok=True)
    key = hashlib.sha1(path.encode("utf-8", "replace")).hexdigest()[:12]
    return os.path.join(base, "landing-rounds-%s.lock" % key)


def append_row(root, row: dict[str, Any]) -> dict[str, Any]:
    """Append one row under the store's locked append; the ledger and its directory are created on the first write."""
    import wl_store as S

    path = ledger_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    S._append_lines(path, _lock_path(path), [row])
    return row


def red_names(row: dict[str, Any] | None) -> list[str]:
    return [str(r.get("check")) for r in (row or {}).get("reds") or [] if r.get("check")]


def delta(
    prev: dict[str, Any] | None, reds: list[dict[str, Any]], greens: list[str]
) -> dict[str, list[str]]:
    """newly_green: red before, green now. newly_red: red now, not red before. regressed: red now, GREEN in the previous round. repeat: red in both."""
    now_red = [str(r.get("check")) for r in reds if r.get("check")]
    was_red = set(red_names(prev))
    was_green = {str(g) for g in (prev or {}).get("greens") or []}
    return {
        "newly_green": sorted(g for g in greens if g in was_red),
        "newly_red": sorted(c for c in now_red if c not in was_red),
        "regressed": sorted(c for c in now_red if c in was_green),
        "repeat": sorted(c for c in now_red if c in was_red),
    }


def round_kind(
    prev: dict[str, Any] | None, heads: str, ids: dict[str, Any], retryable=None
) -> str | None:
    """`push` for a new head, `watchdog-retry` when every job that changed id on the same head is one the watchdog retries, `rerun` otherwise; None when the round is already recorded (same head, same job ids)."""
    if prev is None or str(prev.get("heads") or "") != str(heads or ""):
        return "push"
    old = {str(k): str(v) for k, v in (prev.get("ids") or {}).items()}
    new = {str(k): str(v) for k, v in (ids or {}).items()}
    changed = [k for k, v in new.items() if old.get(k) != v]
    if not changed:
        return None
    if retryable is not None and all(retryable(k) for k in changed):
        return "watchdog-retry"
    return "rerun"


def fix_targets(messages: str, prev_reds: list[str]) -> list[str]:
    """The checks a push's commits aimed at: every `Fix-Target:` trailer, else every previous red the messages name (case-insensitive). A commit that names nothing aims at nothing, so it never counts toward `stuck`."""
    text = messages or ""
    named = [t for m in FIX_TARGET_RE.findall(text) for t in (x.strip() for x in m.split(",")) if t]
    if named:
        return sorted(set(named))
    low = text.lower()
    return sorted({c for c in prev_reds if c and c.lower() in low})


def build_row(
    rows: list[dict[str, Any]],
    *,
    pr: Any,
    kind: str,
    run_id: Any,
    heads: str,
    reds: list[dict[str, Any]],
    greens: list[str],
    ids: dict[str, Any] | None = None,
    fix_target: list[str] | None = None,
    opened_at: Any = None,
    trigger: str = "",
    now: Any = None,
) -> dict[str, Any]:
    """The next row for `pr` after `rows` (its own rows, oldest first). `opened_at` is the PR's creation stamp; without it the PR's first row stands in."""
    mine = [r for r in rows if str(r.get("pr")) == str(pr)]
    prev = mine[-1] if mine else None
    t = _now(now)
    opened = (
        _parse(opened_at)
        or _parse((mine[0] if mine else {}).get("opened_at"))
        or _parse((mine[0] if mine else {}).get("utc"))
        or t
    )
    return {
        "pr": pr,
        "round": int((prev or {}).get("round") or 0) + 1,
        "utc": _stamp(t),
        "kind": kind,
        "run_id": run_id,
        "heads": heads,
        "fix_target": sorted(set(fix_target or [])) if kind == "push" else [],
        "reds": [
            {
                "check": str(r.get("check")),
                "category": r.get("category") or "unknown",
                "signature": r.get("signature") or "",
            }
            for r in reds
            if r.get("check")
        ],
        "greens": sorted({str(g) for g in greens}),
        "delta": delta(prev, reds, greens),
        "open_hours": round((t - opened).total_seconds() / 3600.0, 2),
        "opened_at": _stamp(opened),
        "trigger": trigger,
        "ids": {str(k): v for k, v in (ids or {}).items()},
    }


def next_gap_min(outage_rounds: int) -> int:
    """The wait before the rerun that follows the `outage_rounds`-th back-to-back outage round: 10, 20, 40, 80, then 120 for every later one."""
    n = max(1, int(outage_rounds))
    return OUTAGE_GAPS_MIN[n - 1] if n <= len(OUTAGE_GAPS_MIN) else OUTAGE_STEADY_MIN


def is_outage_red(red: dict[str, Any]) -> bool:
    return red.get("category") == "infra-likely" and red.get("signature") in OUTAGE_SIGNATURES


def is_outage_round(row: dict[str, Any]) -> bool:
    reds = row.get("reds") or []
    return bool(reds) and all(is_outage_red(r) for r in reds)


def _operator_only(latest):
    for r in latest.get("reds") or []:
        if r.get("category") == "operator-only":
            return Verdict(
                "operator-only",
                check=str(r.get("check")),
                rounds=[latest.get("round")],
                why="%s failed on %s, which no rerun fixes"
                % (r.get("check"), r.get("signature") or "an operator-only signature"),
            )
    return None


def _outage_run(rows):
    k = 0
    for row in reversed(rows):
        if not is_outage_round(row):
            break
        k += 1
    return k


def _outage(rows, latest, now, ask):
    k = _outage_run(rows)
    if not k:
        return None
    first = _parse(rows[-k].get("utc")) or now
    rounds = [r.get("round") for r in rows[-k:]]
    sigs = sorted({r.get("signature") for r in latest.get("reds") or []})
    if (now - first).total_seconds() >= OUTAGE_ASK_H * 3600:
        if not ask:
            return None
        return Verdict(
            "outage-ask",
            rounds=rounds,
            why="outside outage (%s) for %d rounds since %s, past %d h"
            % (", ".join(sigs), k, _stamp(first), OUTAGE_ASK_H),
        )
    if ask:
        return None
    gap = next_gap_min(k)
    due = (_parse(latest.get("utc")) or now) + datetime.timedelta(minutes=gap)
    return Verdict(
        "outage-retry",
        rounds=rounds,
        next_gap_min=gap,
        due_utc=_stamp(due),
        why="every red is an outside outage (%s), outage round %d" % (", ".join(sigs), k),
    )


def _wall(rows, latest, now):
    opened = _parse(latest.get("opened_at")) or _parse(rows[0].get("utc"))
    if opened is None or (now - opened).total_seconds() < WALL_H * 3600:
        return None
    return Verdict(
        "wall-ask",
        rounds=[latest.get("round")],
        default=WALL_DEFAULT,
        why="red %d h after the PR opened (%s), past the %d h wall"
        % (int((now - opened).total_seconds() // 3600), _stamp(opened), WALL_H),
    )


def stuck_rounds(rows: list[dict[str, Any]], check: str) -> list[int]:
    """The rounds whose fix_target named `check` and in which `check` was still red. A fix aimed at another check does not count."""
    return [
        r.get("round")
        for r in rows
        if r.get("kind") == "push"
        and check in (r.get("fix_target") or [])
        and check in red_names(r)
    ]


def _stuck(rows, latest):
    for check in red_names(latest):
        hits = stuck_rounds(rows, check)
        if len(hits) >= STUCK_FIXES:
            return Verdict(
                "stuck",
                check=check,
                rounds=hits,
                why="%s still red after %d fixes aimed at it (rounds %s)"
                % (check, len(hits), ", ".join(map(str, hits))),
            )
    return None


def churn_rounds(rows: list[dict[str, Any]]) -> list[int]:
    """The pushes among the last CHURN_WINDOW rounds that turned a previously green check red. A rerun or watchdog retry that flips a check is a flake, not a fix's regression."""
    return [
        r.get("round")
        for r in rows[-CHURN_WINDOW:]
        if r.get("kind") == "push" and ((r.get("delta") or {}).get("regressed") or [])
    ]


def _churn(rows):
    hits = churn_rounds(rows)
    if len(hits) < CHURN_REGRESSIONS:
        return None
    regressed = sorted(
        {
            c
            for r in rows
            if r.get("round") in hits
            for c in (r.get("delta") or {}).get("regressed") or []
        }
    )
    return Verdict(
        "churn",
        check=", ".join(regressed),
        rounds=hits,
        why="fixes regressed green checks (%s) in %d of the last %d rounds"
        % (", ".join(regressed), len(hits), CHURN_WINDOW),
    )


def verdict(rows: list[dict[str, Any]], now: Any = None) -> Verdict:
    """The verdict for the latest PR in `rows` (oldest first). A green latest round, or no rows, is `none`."""
    if not rows:
        return Verdict()
    pr = rows[-1].get("pr")
    rows = [r for r in rows if str(r.get("pr")) == str(pr)]
    latest = rows[-1]
    t = _now(now)
    if not latest.get("reds"):
        return Verdict(pr=pr)
    rules = {
        "operator-only": lambda: _operator_only(latest),
        "outage-ask": lambda: _outage(rows, latest, t, ask=True),
        "wall-ask": lambda: _wall(rows, latest, t),
        "outage-retry": lambda: _outage(rows, latest, t, ask=False),
        "stuck": lambda: _stuck(rows, latest),
        "churn": lambda: _churn(rows),
    }
    fired = [v for v in (rules[k]() for k in ORDER) if v is not None]
    if not fired:
        return Verdict(pr=pr)
    top = fired[0]
    top.pr = pr
    top.also = [v.kind for v in fired[1:]]
    return top


def handover_trigger(v: Verdict) -> dict[str, Any] | None:
    """The record box B7's `--handover` consumes for a stuck or churn verdict, None for every other kind: {kind, check, pr, rounds, evidence}."""
    if v.kind not in HANDOVERS:
        return None
    return {
        "kind": v.kind,
        "check": v.check,
        "pr": v.pr,
        "rounds": list(v.rounds),
        "evidence": "%s (%s rounds %s)"
        % (v.why, "/".join(LEDGER_REL), ", ".join(map(str, v.rounds))),
    }


def render(v: Verdict) -> str:
    """One line for the CI status text, "" for `none`."""
    if v.kind == "none":
        return ""
    if v.kind == "outage-retry":
        act = "rerun the failed jobs at %s (gap %d min): gh run rerun <run> --failed" % (
            v.due_utc,
            v.next_gap_min,
        )
    elif v.kind == "wall-ask":
        act = "ask the operator, DEFAULT: %s" % v.default
    elif v.ask:
        act = "ask the operator now"
    else:
        act = "hand it to the development session with the ledger rows as evidence"
        if v.kind == "churn":
            act = "pause and consult the development session: keep, change or undo"
    also = " (also: %s)" % ", ".join(v.also) if v.also else ""
    return "long red: %s -- %s; %s%s" % (v.kind, v.why, act, also)
