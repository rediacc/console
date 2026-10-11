"""The LEARNED gate model: red classes, clock gates, clusters, change associations and upgrade companions, all derived from the outcome ledger plus `scripts/ci-runner/gates.lock.json` (PLAN-gate-scheduling-learned sections 2-4 and 6).

    PYTHONPATH=.ci python3 -m rediacc_ci.ci.gate_model refresh [--force] [--owner <sid8>] [--no-ci] [--no-probe]
    PYTHONPATH=.ci python3 -m rediacc_ci.ci.gate_model show

NOTHING HERE IS A LIST OF GATES. The only hand-written inputs are the tunables below, each with its reason; a test (T9) plants a gate id into a copy of this file and must go red. Every class, cluster and association is recomputed from the rows on every refresh, so a gate that stops being clock-driven leaves the clock set on the next refresh without anyone editing anything.

`model.json` v1 is a CONTRACT the runner (`scripts/ci-runner/rank.ts`) codes against:

    {v, built_at, cold_start:{on,reason}, runs,
     gates:{<id>:{obs, p_red, p_red_by_class:{<class>:p}, wall_ms, class, findings:{<key>:class}}},
     clock_set:[ids], clusters:[[ids]], associations:{<class>:{<id>:p}},
     companions:[{from,to,support,reliable}]}

`class` is one of real|flaky|clock|chronic|infra|none. Edge provenance (which rule joined two gates) is in `edges.json` beside it, and the human summary in `reports/<date>.md`.

RED CLASSIFICATION (section 3). Episodes run per (gate, side), side local or CI, from onset (first red after a green) to recovery (next green). Rules, in order:
  1. infra: outcome blocked/cancel, or a CI red whose ci_diagnose category is infrastructure. Excluded from every rate and every episode.
  2. flaky: green again at the SAME input key and salt as one of the episode's reds.
  3. clock: red with the key unchanged since the last green: the key at onset EQUALS the last green's (the strong rule); or probes at the last green head are red CLOCK_PERSIST times while a control head is green; or, passively, at least CLOCK_MIN_ONSETS of the gate's onsets bracket a UTC day boundary (last green before it, onset after it, under a day apart). A green probe proves the red real.
  4. real: green again only after the inputs changed. An episode still open is real until something says otherwise.
  5. chronic: never green on that side in the window. Classification then DESCENDS to finding keys, and every finding gets its own episodes under the same rules.
"""

from __future__ import annotations

import argparse
import contextlib
import itertools
import json
import math
import os
import pathlib
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from rediacc_ci import gitx, log, paths
from rediacc_ci.ci import gate_ledger as L

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

MODEL_VERSION = 1
CLASSES = ("real", "flaky", "clock", "chronic", "infra", "none")
INPUT_HASH_REL = "scripts/ci-runner/input-hash.ts"
WORKLIST_REL = (".claude", "hooks", "stop", "worklist.py")
TOKEN_PREFIX = "gate-model"  # noqa: S105 -- the worklist dedup token's prefix, not a credential
LOCAL_SIDE = "local"
CI_SIDE = "ci"
CI_SOURCES = ("ci-step", "ci-nightly")
WHOLE_SOURCES = ("prepush", "quick", "backfill")
DAY_S = 86400.0

# ---- tunables (plan section 8; each reason is the plan's) ------------------------
# Branches live 1-2 days and dependencies drift weekly: a fixed red fades within about a week.
HALF_LIFE_REAL_DAYS = 7.0
# Flakes are rare, so they need a longer memory.
HALF_LIFE_FLAKY_DAYS = 21.0
# One onset or one rerun cannot separate a clock from a coincidence or a flake.
CLOCK_MIN_ONSETS = 2
CLOCK_PERSIST = 2
# About 25 runs a day: rules out pairs that co-occur once.
MIN_SUPPORT = 3
MIN_LIFT = 2.0
MIN_JACCARD = 0.3
# A next-run red is weaker evidence than a same-run red.
CONSECUTIVE_WEIGHT = 0.5
# One occurrence is only a candidate.
COMPANION_MIN_SUPPORT = 2
# Matches the preflight target.
PROBE_BUDGET_S = 120
# About one working day of pre-push runs (the 10-08 replay day had 11).
COLD_START_RUNS = 8
MIN_LEDGER_RUNS = COLD_START_RUNS
# Below these, recency weighting is noise. MIN_GATE_OBS is also the weight of the Beta prior a thin gate takes at the global red rate.
MIN_GATE_OBS = 5
MIN_COVERAGE = 0.5
# The nightly artifact cadence.
MODEL_TTL_H = 24
# Stage 1 should hold most expected reds; model-quality opens below it.
STAGE1_MASS = 0.9
# INFERRED (the brief's item list was truncated): a gate whose recent median wall grew by half, measured on gates long enough for it to matter, gets a wall-drift item.
WALL_DRIFT_RATIO = 1.5
WALL_DRIFT_MIN_MS = 30_000


# ---------------------------------------------------------------------------- lock and globs


def load_lock(root: pathlib.Path) -> list[dict[str, Any]]:
    """The lock entries, or a loud refusal: a model built against no lock would derive no classes and look clean."""
    try:
        data = json.loads((root / L.LOCK_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit("gate_model: cannot read %s: %s" % (L.LOCK_REL, exc)) from exc
    if not isinstance(data, list) or not data:
        raise SystemExit("gate_model: %s holds no entries" % L.LOCK_REL)
    return [e for e in data if isinstance(e, dict) and isinstance(e.get("id"), str)]


_MATCH: Callable[[str, str], bool] | None = None


def match_glob(glob: str, path: str) -> bool:
    """The input-hash glob grammar, through the push guard's own Python twin (`v2_match_glob`), imported rather than copied so the two can never disagree."""
    global _MATCH  # noqa: PLW0603 -- one import per process
    if _MATCH is None:
        import importlib  # noqa: PLC0415

        paths.on_sys_path(paths.repo_root() / ".claude")
        guard = importlib.import_module("rediacc_hooks.guards.block_unverified_push")
        _MATCH = guard.v2_match_glob
    return bool(_MATCH(glob, path))


def global_inputs(root: pathlib.Path) -> list[str]:
    """`GLOBAL_INPUTS` as `input-hash.ts` exports it, parsed from the source of truth rather than restated."""
    try:
        text = (root / INPUT_HASH_REL).read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit("gate_model: cannot read %s: %s" % (INPUT_HASH_REL, exc)) from exc
    m = re.search(r"export const GLOBAL_INPUTS[^=]*=\s*\[(.*?)\];", text, re.DOTALL)
    if not m:
        raise SystemExit(
            "gate_model: %s no longer exports GLOBAL_INPUTS as an array literal" % INPUT_HASH_REL
        )
    found = [a or b for a, b in re.findall(r"'([^']*)'|\"([^\"]*)\"", m.group(1))]
    if not found:
        raise SystemExit("gate_model: GLOBAL_INPUTS in %s parsed to nothing" % INPUT_HASH_REL)
    return found


# ---------------------------------------------------------------------------- path classes (section 2)


@dataclass(frozen=True)
class Anchor:
    name: str
    kind: str  # glob | file
    weight: int


def anchors(lock: list[dict[str, Any]], root: pathlib.Path, globals_: list[str]) -> list[Anchor]:
    """Every declared `paths` glob, every repo-file leaf, every `ci.test` path and every global input. Weight is the anchor's length with a trailing `/**` reduced to its directory, so the most specific anchor wins."""
    out: dict[str, Anchor] = {}

    def add(name: str, kind: str) -> None:
        if name and name not in out:
            out[name] = Anchor(name, kind, len(name.removesuffix("/**")))

    for e in lock:
        for g in e.get("paths") or []:
            add(str(g), "glob" if "*" in str(g) else "file")
        for leaf in e.get("leaves") or []:
            if "/" in str(leaf) and (root / str(leaf)).is_file():
                add(str(leaf), "file")
        ci = e.get("ci") or {}
        if isinstance(ci, dict) and isinstance(ci.get("test"), str):
            add(ci["test"], "file")
    for g in globals_:
        add(g, "glob" if "*" in g else "file")
    return sorted(out.values(), key=lambda a: (-a.weight, a.name))


def path_class(path: str, anchor_list: list[Anchor]) -> str:
    """The longest anchor matching `path`, else `~<first two segments>`."""
    for a in anchor_list:
        if (a.kind == "file" and path == a.name) or (a.kind == "glob" and match_glob(a.name, path)):
            return a.name
    return "~" + "/".join(path.split("/")[:2])


# ---------------------------------------------------------------------------- observations


@dataclass
class Obs:
    run: str
    gate: str
    side: str
    t: float
    key: str | None
    salt: str | None
    outcome: str
    findings: list[str] | None
    branch: str | None
    root: str | None
    category: str | None
    wall_ms: int | None
    stage: str | None
    tree: str | None = None

    @property
    def infra(self) -> bool:
        return self.outcome in ("blocked", "cancel") or (
            self.outcome in ("fail", "timeout") and self.category in infra_categories()
        )

    @property
    def red(self) -> bool:
        return self.outcome in ("fail", "timeout") and not self.infra

    @property
    def green(self) -> bool:
        return self.outcome == "pass"


_INFRA: frozenset[str] | None = None


def infra_categories() -> frozenset[str]:
    """ci_diagnose's infrastructure and stopped-job categories, read from that module: `infra-likely` plus every cancel category it maps to."""
    global _INFRA  # noqa: PLW0603
    if _INFRA is None:
        from rediacc_ci.ci import ci_diagnose  # noqa: PLC0415

        _INFRA = frozenset(
            {
                c
                for c in ci_diagnose.CATEGORIES
                if c.startswith("infra")
                or c in ci_diagnose.CANCEL_CATEGORIES.values()
                or c in ci_diagnose.RUN_CANCEL_CATEGORIES.values()
            }
        )
    return _INFRA


@dataclass
class Ledger:
    runs: dict[str, dict[str, Any]]
    obs: list[Obs]
    probes: list[tuple[dict[str, Any], dict[str, Any]]]
    malformed: int = 0


def fold_rows(rows: Iterable[dict[str, Any]], malformed: int = 0) -> Ledger:
    """Rows to observations. A g row whose run row is missing is dropped (it cannot be placed in time); skips are not observations."""
    runs: dict[str, dict[str, Any]] = {}
    grows: list[dict[str, Any]] = []
    for r in rows:
        if r.get("t") == "run":
            runs[str(r["id"])] = r
        elif r.get("t") == "g":
            grows.append(r)
    obs: list[Obs] = []
    probes: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for g in grows:
        run = runs.get(str(g.get("run")))
        if run is None or g.get("outcome") == "skip":
            continue
        if run.get("src") == "probe":
            probes.append((run, g))
            continue
        at = L.epoch(run.get("at")) or 0.0
        t0 = g.get("t0_ms")
        obs.append(
            Obs(
                run=str(run["id"]),
                gate=str(g["gate"]),
                side=CI_SIDE if run.get("src") in CI_SOURCES else LOCAL_SIDE,
                t=at + (t0 / 1000.0 if isinstance(t0, int | float) else 0.0),
                key=g.get("key"),
                salt=run.get("salt"),
                outcome=str(g.get("outcome")),
                findings=g.get("findings") if isinstance(g.get("findings"), list) else None,
                branch=run.get("branch"),
                root=run.get("root"),
                category=(run.get("ci") or {}).get("category")
                if isinstance(run.get("ci"), dict)
                else None,
                wall_ms=g.get("wall_ms") if isinstance(g.get("wall_ms"), int) else None,
                stage=g.get("stage") if isinstance(g.get("stage"), str) else None,
                tree=run.get("tree"),
            )
        )
    obs = merge_legs(obs, runs)
    obs.sort(key=lambda o: (o.t, o.run, o.gate))
    return Ledger(runs=runs, obs=obs, probes=probes, malformed=malformed)


# Worst first: a gate run in several CI legs (a sharded or matrix job) is ONE observation of that CI run attempt.
_SEVERITY = ("fail", "timeout", "cancel", "blocked", "pass")


def merge_legs(obs: list[Obs], runs: dict[str, dict[str, Any]]) -> list[Obs]:
    """Fold the per-JOB CI observations of one gate in one CI run attempt into one: red when any leg was red. Left apart, leg 1 green and leg 2 red at one commit read as a gate going green again at the same key, which is the flaky rule."""
    out: list[Obs] = []
    groups: dict[tuple[Any, Any, str], list[Obs]] = {}
    for o in obs:
        ci = runs[o.run].get("ci") if o.side == CI_SIDE else None
        if not isinstance(ci, dict):
            out.append(o)
            continue
        groups.setdefault((ci.get("run"), ci.get("attempt"), o.gate), []).append(o)
    for legs in groups.values():
        legs.sort(
            key=lambda o: (
                _SEVERITY.index(o.outcome) if o.outcome in _SEVERITY else len(_SEVERITY),
                o.t,
            )
        )
        head = legs[0]
        if len(legs) > 1:
            found = [k for o in legs for k in (o.findings or [])]
            head = Obs(
                **{
                    **head.__dict__,
                    "t": min(o.t for o in legs),
                    "findings": list(dict.fromkeys(found))
                    if any(o.findings is not None for o in legs)
                    else None,
                }
            )
        out.append(head)
    return out


# ---------------------------------------------------------------------------- episodes (section 3)


@dataclass
class Point:
    """One judged observation of a gate, or of one finding inside it."""

    t: float
    red: bool
    key: str | None
    salt: str | None
    run: str
    tree: str | None = None


@dataclass
class Episode:
    subject: str
    side: str
    onset: Point
    last_green: Point | None
    reds: list[Point] = field(default_factory=list)
    recovery: Point | None = None
    cls: str = "real"
    why: str = ""
    # True when a flaky or clock verdict rests on a key that is EQUAL while the whole tree is not: the key covers only the declared inputs, so an undeclared input explains the red as well as a clock or a flake does.
    weak: bool = False


def episodes_of(subject: str, side: str, points: list[Point]) -> tuple[list[Episode], bool]:
    """(episodes, ever_green) for one ordered point sequence."""
    eps: list[Episode] = []
    cur: Episode | None = None
    last_green: Point | None = None
    ever_green = False
    for p in points:
        if p.red:
            if cur is None:
                cur = Episode(subject, side, onset=p, last_green=last_green, reds=[p])
            else:
                cur.reds.append(p)
        else:
            ever_green = True
            if cur is not None:
                cur.recovery = p
                eps.append(cur)
                cur = None
            last_green = p
    if cur is not None:
        eps.append(cur)
    return eps, ever_green


def brackets_day_boundary(ep: Episode) -> bool:
    """The last green ran before a UTC midnight and the onset after it, less than a day apart (a longer gap brackets one trivially)."""
    if ep.last_green is None:
        return False
    a, b = ep.last_green.t, ep.onset.t
    return 0 < b - a < DAY_S and math.floor(a / DAY_S) != math.floor(b / DAY_S)


@dataclass
class Rules:
    """The switches the replay controls flip; every one is on in production."""

    strong_key: bool = True
    utc_boundary: bool = True
    probes: bool = True


def classify(
    eps: list[Episode],
    probe_votes: dict[tuple[str, str], tuple[int, int, int]] | None = None,
    rules: Rules | None = None,
) -> None:
    """Assign `cls`/`why` to each episode of ONE subject and side, rules in the module docstring's order (infra was excluded upstream)."""
    rules = rules or Rules()
    probe_votes = probe_votes or {}
    boundary = [ep for ep in eps if brackets_day_boundary(ep)] if rules.utc_boundary else []
    passive = len(boundary) >= CLOCK_MIN_ONSETS
    for ep in eps:
        red_keys = {(r.key, r.salt) for r in ep.reds if r.key}
        if (
            ep.recovery is not None
            and ep.recovery.key
            and (ep.recovery.key, ep.recovery.salt) in red_keys
        ):
            ep.cls, ep.why = "flaky", "green again at the same input key"
            same = [r for r in ep.reds if (r.key, r.salt) == (ep.recovery.key, ep.recovery.salt)]
            ep.weak = _trees_differ(same[0], ep.recovery)
            continue
        if ep.last_green is not None:
            if (
                rules.strong_key
                and ep.onset.key
                and (ep.onset.key, ep.onset.salt) == (ep.last_green.key, ep.last_green.salt)
            ):
                ep.cls, ep.why = "clock", "red at the input key of the last green"
                ep.weak = _trees_differ(ep.onset, ep.last_green)
                continue
            red_n, green_n, control_ok = probe_votes.get((ep.subject, ep.onset.run), (0, 0, 0))
            if rules.probes and green_n:
                ep.cls, ep.why = "real", "a probe at the last green head was green"
                continue
            if rules.probes and red_n >= CLOCK_PERSIST and control_ok:
                ep.cls, ep.why = "clock", "%d probes at the last green head were red" % red_n
                continue
            if passive and ep in boundary:
                ep.cls, ep.why = "clock", "%d onsets bracket a UTC day boundary" % len(boundary)
                continue
        if ep.recovery is not None:
            ep.cls, ep.why = "real", "green again only after the inputs changed"
        else:
            ep.cls, ep.why = "real", "still red; no evidence it is anything but real"


def _trees_differ(a: Point, b: Point) -> bool:
    return bool(a.tree and b.tree and a.tree != b.tree)


def weight(age_s: float, half_life_days: float) -> float:
    return 2.0 ** (-max(age_s, 0.0) / (half_life_days * DAY_S))


def summarise(eps: list[Episode], ever_green: bool, any_red: bool, now: float) -> str:
    """One class for one subject and side: chronic when never green, else the recency-weighted heaviest episode class."""
    if any_red and not ever_green:
        return "chronic"
    if not eps:
        return "none"
    w: dict[str, float] = {}
    for ep in eps:
        hl = HALF_LIFE_FLAKY_DAYS if ep.cls == "flaky" else HALF_LIFE_REAL_DAYS
        w[ep.cls] = w.get(ep.cls, 0.0) + weight(now - ep.onset.t, hl)
    return max(sorted(w), key=lambda c: w[c])


# ---------------------------------------------------------------------------- the model


@dataclass
class Built:
    model: dict[str, Any]
    edges: list[dict[str, Any]]
    episodes: list[Episode]
    finding_eps: dict[str, list[Episode]]
    items: list[tuple[str, str, str]]
    notes: dict[str, Any]


def _points(seq: list[Obs]) -> list[Point]:
    return [Point(o.t, o.red, o.key, o.salt, o.run, o.tree) for o in seq if o.red or o.green]


def probe_votes(ledger: Ledger) -> dict[tuple[str, str], tuple[int, int, int]]:
    """{(gate, onset run): (red at the green head, green at the green head, control green)} from `src: probe` rows."""
    votes: dict[tuple[str, str], list[int]] = {}
    for run, g in ledger.probes:
        k = (str(g.get("gate")), str(run.get("probe_of")))
        v = votes.setdefault(k, [0, 0, 0])
        role = run.get("probe_role")
        if role == "green-head":
            if g.get("outcome") == "pass":
                v[1] += 1
            elif g.get("outcome") in ("fail", "timeout"):
                v[0] += 1
        elif role == "control" and g.get("outcome") == "pass":
            v[2] = 1
    return {k: (v[0], v[1], v[2]) for k, v in votes.items()}


def run_classes(
    ledger: Ledger, anchor_list: list[Anchor]
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """({run: classes of its diff}, {class: example paths}) for every run with a known diff base."""
    memo: dict[str, str] = {}
    out: dict[str, set[str]] = {}
    examples: dict[str, set[str]] = {}
    for rid, run in ledger.runs.items():
        if run.get("base_tree") is None or run.get("src") in CI_SOURCES:
            continue
        cl: set[str] = set()
        for p in run.get("changed") or []:
            c = memo.get(p)
            if c is None:
                c = memo[p] = path_class(p, anchor_list)
            cl.add(c)
            ex = examples.setdefault(c, set())
            if len(ex) < 3:
                ex.add(p)
        out[rid] = cl
    return out, examples


def _uf_clusters(nodes: Iterable[str], edges: list[dict[str, Any]]) -> list[list[str]]:
    parent: dict[str, str] = {n: n for n in nodes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        a, b = e["a"], e["b"]
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    groups: dict[str, list[str]] = {}
    for n in parent:
        groups.setdefault(find(n), []).append(n)
    return sorted((sorted(g) for g in groups.values() if len(g) > 1), key=lambda g: (-len(g), g))


def structural_edges(lock: list[dict[str, Any]], root: pathlib.Path) -> list[dict[str, Any]]:
    """Edges the lock itself implies: a shared `paths` glob, a shared repo-file leaf, `needs`, a shared CI (job, step)."""
    by: dict[tuple[str, str], list[str]] = {}
    edges: list[dict[str, Any]] = []
    for e in lock:
        gid = e["id"]
        for g in e.get("paths") or []:
            by.setdefault(("paths", str(g)), []).append(gid)
        for leaf in e.get("leaves") or []:
            if "/" in str(leaf) and (root / str(leaf)).is_file():
                by.setdefault(("leaf", str(leaf)), []).append(gid)
        edges.extend(
            {"a": gid, "b": str(n), "origin": "needs", "detail": "%s needs %s" % (gid, n)}
            for n in e.get("needs") or []
        )
        ci = e.get("ci") or {}
        if isinstance(ci, dict) and ci.get("kind") == "step":
            by.setdefault(("step", "%s / %s" % (ci.get("job"), ci.get("step"))), []).append(gid)
    for (origin, detail), members in sorted(by.items()):
        ids = sorted(set(members))
        edges.extend(
            {"a": ids[0], "b": other, "origin": origin, "detail": detail} for other in ids[1:]
        )
    return edges


def build(
    rows: list[dict[str, Any]],
    lock: list[dict[str, Any]],
    root: pathlib.Path,
    *,
    now: float | None = None,
    malformed: int = 0,
    rules: Rules | None = None,
    globals_: list[str] | None = None,
) -> Built:
    now = time.time() if now is None else now
    ledger = fold_rows(rows, malformed)
    lock_ids = {e["id"] for e in lock if e.get("gate")}
    anchor_list = anchors(lock, root, globals_ if globals_ is not None else global_inputs(root))
    votes = probe_votes(ledger)

    by_gs: dict[tuple[str, str], list[Obs]] = {}
    for o in ledger.obs:
        by_gs.setdefault((o.gate, o.side), []).append(o)

    all_eps: list[Episode] = []
    finding_eps: dict[str, list[Episode]] = {}
    side_class: dict[tuple[str, str], str] = {}
    finding_class: dict[str, dict[str, str]] = {}
    for (gid, side), seq in sorted(by_gs.items()):
        judged = [o for o in seq if not o.infra]
        eps, ever_green = episodes_of(gid, side, _points(judged))
        classify(eps, votes, rules)
        all_eps.extend(eps)
        any_red = any(o.red for o in judged)
        side_class[(gid, side)] = (
            summarise(eps, ever_green, any_red, now) if judged else ("infra" if seq else "none")
        )
        # Descent to findings: a finding is red where the gate's keys name it and green where the gate ran without it.
        keys = sorted({k for o in judged if o.red and o.findings for k in o.findings})
        for fk in keys:
            pts = [
                Point(o.t, fk in (o.findings or []), o.key, o.salt, o.run, o.tree)
                for o in judged
                if o.green or (o.red and o.findings is not None)
            ]
            subject = "%s|%s" % (gid, fk)
            feps, f_green = episodes_of(subject, side, pts)
            classify(feps, votes, rules)
            finding_eps.setdefault(gid, []).extend(feps)
            if side == LOCAL_SIDE or fk not in finding_class.get(gid, {}):
                finding_class.setdefault(gid, {})[fk] = summarise(feps, f_green, True, now)

    # ---- per-gate figures
    def side_of(gid: str) -> str:
        return LOCAL_SIDE if (gid, LOCAL_SIDE) in by_gs else CI_SIDE

    onset_runs: dict[tuple[str, str], Episode] = {(ep.subject, ep.onset.run): ep for ep in all_eps}
    flaky_runs = {(ep.subject, p.run) for ep in all_eps if ep.cls == "flaky" for p in ep.reds}
    tot_w = tot_red = 0.0
    per: dict[str, tuple[float, float]] = {}
    for (gid, side), seq in by_gs.items():
        if side != side_of(gid):
            continue
        sw = sr = 0.0
        for o in seq:
            if o.infra or not (o.red or o.green):
                continue
            w = weight(now - o.t, HALF_LIFE_REAL_DAYS)
            sw += w
            if o.red and (gid, o.run) not in flaky_runs:
                sr += w
        per[gid] = (sw, sr)
        tot_w += sw
        tot_red += sr
    prior = tot_red / tot_w if tot_w else 0.0

    rclasses, examples = run_classes(ledger, anchor_list)
    gates: dict[str, Any] = {}
    for gid in sorted({g for g, _s in by_gs}):
        side = side_of(gid)
        seq = [o for o in by_gs[(gid, side)] if not o.infra and (o.red or o.green)]
        sw, sr = per.get(gid, (0.0, 0.0))
        p_red = (sr + MIN_GATE_OBS * prior) / (sw + MIN_GATE_OBS)
        # P(this gate TURNS red | class in the diff): onsets and greens only; a red that persists was not caused by the next diff.
        cw: dict[str, list[float]] = {}
        for o in seq:
            cls = rclasses.get(o.run)
            if not cls:
                continue
            onset = (gid, o.run) in onset_runs
            if o.red and not onset:
                continue
            w = weight(now - o.t, HALF_LIFE_REAL_DAYS)
            for c in cls:
                acc = cw.setdefault(c, [0.0, 0.0])
                acc[0] += w
                acc[1] += w if (o.red and onset) else 0.0
        by_class = {
            c: round((r + MIN_GATE_OBS * p_red) / (w + MIN_GATE_OBS), 4)
            for c, (w, r) in sorted(cw.items())
            if r > 0
        }
        walls = [
            (o.wall_ms, weight(now - o.t, HALF_LIFE_REAL_DAYS))
            for o in by_gs[(gid, side)]
            if o.wall_ms is not None
        ]
        gates[gid] = {
            "obs": len(seq),
            "p_red": round(p_red, 4),
            "p_red_by_class": by_class,
            "wall_ms": _weighted_median(walls),
            "class": side_class.get((gid, side), "none"),
            "findings": finding_class.get(gid, {}),
        }
    clock_set = sorted(g for g, v in gates.items() if v["class"] == "clock")

    # ---- co-failure clusters (section 4)
    real_onsets: dict[str, set[str]] = {}
    n_onsets: dict[str, int] = {}
    for ep in all_eps:
        if ep.cls != "real":
            continue
        real_onsets.setdefault(ep.onset.run, set()).add(ep.subject)
        n_onsets[ep.subject] = n_onsets.get(ep.subject, 0) + 1
    seq_runs = _run_sequences(ledger)
    pair_w: dict[tuple[str, str], float] = {}
    for gs in real_onsets.values():
        for a in gs:
            for b in gs:
                if a < b:
                    pair_w[(a, b)] = pair_w.get((a, b), 0.0) + 1.0
    for chain in seq_runs:
        for r0, r1 in itertools.pairwise(chain):
            for a in real_onsets.get(r0, ()):
                for b in real_onsets.get(r1, ()):
                    if a != b:
                        k = (min(a, b), max(a, b))
                        pair_w[k] = pair_w.get(k, 0.0) + CONSECUTIVE_WEIGHT
    n_runs = len({o.run for o in ledger.obs if not o.infra})
    edges: list[dict[str, Any]] = []
    for (a, b), w in sorted(pair_w.items()):
        na, nb = n_onsets.get(a, 0), n_onsets.get(b, 0)
        if not na or not nb:
            continue
        lift = w * n_runs / (na * nb)
        jac = w / max(na + nb - w, 1e-9)
        if w >= MIN_SUPPORT and lift >= MIN_LIFT and jac >= MIN_JACCARD:
            edges.append(
                {
                    "a": a,
                    "b": b,
                    "origin": "co-failure",
                    "detail": "support %.1f lift %.2f jaccard %.2f" % (w, lift, jac),
                }
            )
    edges.extend(structural_edges(lock, root))
    clusters = _uf_clusters(lock_ids | set(gates), edges)

    # ---- change-to-red associations
    diff_runs = list(rclasses)
    n_diff = len(diff_runs)
    in_diff: dict[str, int] = {}
    for rid in diff_runs:
        for g in real_onsets.get(rid, ()):
            in_diff[g] = in_diff.get(g, 0) + 1
    base = {g: n / n_diff for g, n in in_diff.items()} if n_diff else {}
    runs_with: dict[str, int] = {}
    for rid in diff_runs:
        for c in rclasses[rid]:
            runs_with[c] = runs_with.get(c, 0) + 1
    hits: dict[tuple[str, str], int] = {}
    for rid in diff_runs:
        for g in real_onsets.get(rid, ()):
            for c in rclasses[rid]:
                hits[(c, g)] = hits.get((c, g), 0) + 1
    associations: dict[str, dict[str, float]] = {}
    assoc_support: dict[tuple[str, str], int] = {}
    for (c, g), h in sorted(hits.items()):
        base_g = base.get(g, 0.0)
        p = (h + MIN_GATE_OBS * base_g) / (runs_with[c] + MIN_GATE_OBS)
        if base_g > 0 and p / base_g >= MIN_LIFT:
            associations.setdefault(c, {})[g] = round(p, 4)
            assoc_support[(c, g)] = h

    # ---- upgrade companions
    comp: dict[tuple[str, str], int] = {}
    by_run: dict[str, dict[str, Obs]] = {}
    for o in ledger.obs:
        if o.side == LOCAL_SIDE:
            by_run.setdefault(o.run, {})[o.gate] = o
    real_onset_keys = {
        (ep.subject, ep.onset.run) for ep in all_eps if ep.cls == "real" and ep.side == LOCAL_SIDE
    }
    for chain in seq_runs:
        for r0, r1 in itertools.pairwise(chain):
            g0, g1 = by_run.get(r0, {}), by_run.get(r1, {})
            healed = [a for a, o in g0.items() if o.red and a in g1 and g1[a].green]
            broke = [
                b for b, o in g1.items() if (b, r1) in real_onset_keys and b in g0 and g0[b].green
            ]
            for a in healed:
                for b in broke:
                    comp[(a, b)] = comp.get((a, b), 0) + 1
    companions = [
        {"from": a, "to": b, "support": n, "reliable": n >= COMPANION_MIN_SUPPORT}
        for (a, b), n in sorted(comp.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    # ---- cold start
    whole = sum(1 for r in ledger.runs.values() if r.get("src") in WHOLE_SOURCES and r.get("whole"))
    covered = sum(1 for g in lock_ids if gates.get(g, {}).get("obs", 0) >= MIN_GATE_OBS)
    coverage = covered / len(lock_ids) if lock_ids else 0.0
    if whole < MIN_LEDGER_RUNS:
        cold = {
            "on": True,
            "reason": "%d whole run(s) in the ledger, fewer than %d" % (whole, MIN_LEDGER_RUNS),
        }
    elif coverage < MIN_COVERAGE:
        cold = {
            "on": True,
            "reason": "%d of %d gates have %d+ observations (%.0f%% < %.0f%%)"
            % (covered, len(lock_ids), MIN_GATE_OBS, coverage * 100, MIN_COVERAGE * 100),
        }
    else:
        cold = {
            "on": False,
            "reason": "%d whole run(s); %d of %d gates have %d+ observations"
            % (whole, covered, len(lock_ids), MIN_GATE_OBS),
        }

    model = {
        "v": MODEL_VERSION,
        "built_at": L.iso(now),
        "cold_start": cold,
        "runs": count_runs(ledger),
        "gates": gates,
        "clock_set": clock_set,
        "clusters": clusters,
        "associations": associations,
        "companions": companions,
    }
    notes = {
        "whole_runs": whole,
        "coverage": coverage,
        "malformed": malformed,
        "assoc_support": assoc_support,
        "examples": examples,
        "lock_ids": lock_ids,
        "infra": _infra_summary(ledger, now),
        "quality": _quality(ledger),
        "wall_drift": _wall_drift(by_gs, now),
        "obs": len(ledger.obs),
        "side_class": side_class,
    }
    built = Built(model, edges, all_eps, finding_eps, [], notes)
    built.items = items_for(built, lock)
    return built


def count_runs(ledger: Ledger) -> int:
    """Local runs plus CI run ATTEMPTS: the ledger keeps one run row per CI job (a job is where a step's outcome and category live), so counting rows would count a 13-job attempt 13 times. Probes are not runs of the gate set."""
    local = sum(1 for r in ledger.runs.values() if r.get("src") not in (*CI_SOURCES, "probe"))
    attempts = {
        (r["ci"].get("run"), r["ci"].get("attempt"))
        for r in ledger.runs.values()
        if r.get("src") in CI_SOURCES and isinstance(r.get("ci"), dict)
    }
    return local + len(attempts)


def _weighted_median(pairs: list[tuple[int, float]]) -> int | None:
    if not pairs:
        return None
    pairs = sorted(pairs)
    half = sum(w for _v, w in pairs) / 2.0
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= half:
            return int(v)
    return int(pairs[-1][0])


def _run_sequences(ledger: Ledger) -> list[list[str]]:
    """Local runs as consecutive chains, one per (checkout, branch), in time order."""
    chains: dict[tuple[str, str], list[tuple[float, str]]] = {}
    for rid, r in ledger.runs.items():
        if r.get("src") in CI_SOURCES or r.get("src") == "probe":
            continue
        chains.setdefault((str(r.get("root")), str(r.get("branch"))), []).append(
            (L.epoch(r.get("at")) or 0.0, rid)
        )
    return [[rid for _t, rid in sorted(v)] for _k, v in sorted(chains.items())]


def _infra_summary(ledger: Ledger, now: float) -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = {}
    seen: set[str] = set()
    for o in ledger.obs:
        if (
            o.side != CI_SIDE
            or not o.infra
            or o.run in seen
            or now - o.t > HALF_LIFE_REAL_DAYS * DAY_S
        ):
            continue
        seen.add(o.run)
        job = str((ledger.runs[o.run].get("ci") or {}).get("job") or "?")
        k = (str(o.category or o.outcome), job)
        out[k] = out.get(k, 0) + 1
    return out


def _quality(ledger: Ledger) -> tuple[int, int] | None:
    """(reds in preflight or stage 1, all reds) over runs whose rows carry a `stage`, or None before the runner writes one."""
    staged = [o for o in ledger.obs if o.stage]
    if not staged:
        return None
    reds = [o for o in staged if o.red]
    return sum(1 for o in reds if o.stage in ("preflight", "stage1")), len(reds)


def _wall_drift(by_gs: dict[tuple[str, str], list[Obs]], now: float) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    edge = now - HALF_LIFE_REAL_DAYS * DAY_S
    for (gid, side), seq in by_gs.items():
        if side != LOCAL_SIDE:
            continue
        new = [o.wall_ms for o in seq if o.wall_ms is not None and o.green and o.t >= edge]
        old = [o.wall_ms for o in seq if o.wall_ms is not None and o.green and o.t < edge]
        if len(new) < MIN_GATE_OBS or len(old) < MIN_GATE_OBS:
            continue
        a, b = statistics.median(old), statistics.median(new)
        if b >= WALL_DRIFT_MIN_MS and a > 0 and b / a >= WALL_DRIFT_RATIO:
            out[gid] = (int(a), int(b))
    return out


# ---------------------------------------------------------------------------- items (section 6)


def token(kind: str, key: str) -> str:
    return "[%s:%s:%s]" % (TOKEN_PREFIX, kind, key)


def items_for(b: Built, lock: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """[(token, kind, text)]: what the worklist should hold after this refresh. Every kind after `flaky-test` is INFERRED (the brief's list was truncated)."""
    m = b.model
    out: list[tuple[str, str, str]] = []

    def add(kind: str, key: str, text: str) -> None:
        tok = token(kind, key)
        out.append((tok, kind, "%s %s (gate_model refresh %s)" % (tok, text, m["built_at"][:10])))

    for gid, eps in sorted(b.finding_eps.items()):
        for fk in sorted({ep.subject.split("|", 1)[1] for ep in eps if ep.cls == "flaky"}):
            if fk.startswith("pytest-fail:"):
                node = fk[len("pytest-fail:") :]
                mine = [ep for ep in eps if ep.cls == "flaky" and ep.subject.endswith("|" + fk)]
                weak = all(ep.weak for ep in mine)
                add(
                    "flaky-test",
                    node,
                    "%s failed and passed again at the same input key %d time(s) under %s; %s"
                    % (
                        node,
                        len(mine),
                        gid,
                        "WEAK evidence: the key is the gate's declared paths and the tree changed, so a read outside those paths explains it as well as a flake (fix the isolation or declare the input)"
                        if weak
                        else "fix the test or its isolation",
                    ),
                )
    for gid, g in sorted(m["gates"].items()):
        if g["class"] == "flaky" or b.notes["side_class"].get((gid, CI_SIDE)) == "flaky":
            add(
                "flaky-gate",
                gid,
                "%s goes green again at unchanged inputs (p_red %.2f over %d obs)"
                % (gid, g["p_red"], g["obs"]),
            )
        if g["class"] == "chronic":
            chronic_f = sorted(k for k, c in g["findings"].items() if c == "chronic")
            add(
                "chronic",
                gid,
                "%s was never green in the ledger window (%d obs); chronic findings: %s"
                % (gid, g["obs"], ", ".join(chronic_f[:6]) or "none keyed"),
            )
    for c in m["companions"]:
        if c["reliable"]:
            add(
                "companion",
                "%s->%s" % (c["from"], c["to"]),
                "fixing %s sent %s red on the next run %d times"
                % (c["from"], c["to"], c["support"]),
            )
    declared = {e["id"]: list(e.get("paths") or []) for e in lock}
    for (cls, gid), h in sorted(b.notes["assoc_support"].items()):
        globs = declared.get(gid) or []
        if not globs or h < MIN_SUPPORT:
            continue
        ex = sorted(b.notes["examples"].get(cls, ()))
        if ex and not any(match_glob(g, p) for g in globs for p in ex):
            add(
                "paths-gap",
                "%s:%s" % (gid, cls),
                "%s turned red after %d diffs touching %s (e.g. %s), which its declared paths do not cover"
                % (gid, h, cls, ex[0]),
            )
    for (cat, job), n in sorted(b.notes["infra"].items()):
        add(
            "infra",
            "%s:%s" % (cat, job),
            "%d CI run(s) in %d days stopped %s as %s" % (n, int(HALF_LIFE_REAL_DAYS), job, cat),
        )
    if m["clock_set"]:
        add("clock-set", "clock-set", "clock-driven gates: %s" % ", ".join(m["clock_set"]))
    for gid, (a, bb) in sorted(b.notes["wall_drift"].items()):
        add("wall-drift", gid, "%s median wall %ds -> %ds" % (gid, a // 1000, bb // 1000))
    if b.notes["malformed"] or not m["runs"]:
        add(
            "ledger-health",
            "ledger-health",
            "%d malformed ledger line(s), %d run(s)" % (b.notes["malformed"], m["runs"]),
        )
    q = b.notes["quality"]
    if q is not None and q[1] and q[0] / q[1] < STAGE1_MASS:
        add(
            "model-quality",
            "model-quality",
            "preflight plus stage 1 caught %d of %d reds (%.0f%% < %.0f%%)"
            % (q[0], q[1], 100 * q[0] / q[1], 100 * STAGE1_MASS),
        )
    return out


def _open_ids(listing: str) -> set[str]:
    return set(re.findall(r"#([0-9a-f]{6,})\b", listing))


def sync_items(
    d: pathlib.Path,
    items: list[tuple[str, str, str]],
    *,
    owner: str,
    worklist_cmd: list[str],
    cwd: pathlib.Path,
    env: dict[str, str] | None = None,
) -> dict[str, int]:
    """Open or refresh one worklist item per token, through the worklist VERBS. The token's item id lives in `claims/<token sha>.json`; an O_EXCL `.claim` beside it means two refreshes racing add one item, not two (the wl_schedred claim shape)."""
    claims = L.ensure_dir(d / "claims")

    def wl(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*worklist_cmd, *args], capture_output=True, text=True, cwd=cwd, env=env, check=False
        )

    listing = wl("--list", "--open", owner)
    if listing.returncode != 0:
        raise RuntimeError(
            "worklist --list --open failed (%d): %s"
            % (listing.returncode, (listing.stderr or listing.stdout)[:300])
        )
    open_ids = _open_ids(listing.stdout)
    counts = {"added": 0, "updated": 0, "raced": 0, "failed": 0}
    for tok, _kind, text in items:
        stem = L.sha(tok)[:20]
        rec_path = claims / (stem + ".json")
        rec: dict[str, Any] = {}
        with contextlib.suppress(OSError, ValueError):
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
        item_id = str(rec.get("id") or "")
        if item_id and item_id in open_ids:
            res = wl("--update", owner, item_id, text)
            counts["updated" if res.returncode == 0 else "failed"] += 1
            continue
        claim = claims / (stem + ".claim")
        try:
            fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            if time.time() - claim.stat().st_mtime < MODEL_TTL_H * 3600:
                counts["raced"] += 1
                continue
            claim.unlink()
            fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        try:
            os.write(fd, json.dumps({"pid": os.getpid(), "at": time.time()}).encode("utf-8"))
            os.close(fd)
            res = wl("--add", owner, text)
            m = re.search(r"#([0-9a-f]{6,})\b", res.stdout)
            if res.returncode != 0 or not m:
                counts["failed"] += 1
                log.error(
                    "gate_model: worklist --add failed (%d): %s"
                    % (res.returncode, (res.stderr or res.stdout)[:300])
                )
                continue
            rec_path.write_text(
                json.dumps({"token": tok, "id": m.group(1), "at": time.time()}), encoding="utf-8"
            )
            counts["added"] += 1
        finally:
            with contextlib.suppress(OSError):
                claim.unlink()
    return counts


# ---------------------------------------------------------------------------- probes


def probe_candidates(
    b: Built, ledger_runs: dict[str, dict[str, Any]], now: float
) -> list[tuple[Episode, dict[str, Any], dict[str, Any] | None]]:
    """Local gate episodes the strong and passive rules left undecided (keyed on the tree, onset in the last MODEL_TTL_H), with the last green run and the recovery run (the control head), cheapest first."""
    out = []
    for ep in b.episodes:
        if ep.side != LOCAL_SIDE or ep.last_green is None or ep.cls != "real" or "|" in ep.subject:
            continue
        if now - ep.onset.t > MODEL_TTL_H * 3600:
            continue
        green_run = ledger_runs.get(ep.last_green.run)
        if not green_run or not green_run.get("head"):
            continue
        ctrl = ledger_runs.get(ep.recovery.run) if ep.recovery else None
        out.append((ep, green_run, ctrl))
    walls = b.model["gates"]
    return sorted(out, key=lambda c: walls.get(c[0].subject, {}).get("wall_ms") or 0)


def clone_runner(root: pathlib.Path) -> Callable[[str, str, float], str]:
    """`runner(gate, head, timeout_s) -> pass|fail|unknown`: the gate at `head` in a disposable shared clone, `node_modules` linked from the checkout. Anything that is not a clean exit or a clean failure is `unknown`, never red."""

    def run(gate: str, head: str, timeout_s: float) -> str:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="gate-probe-"))
        try:
            clone = tmp / "repo"
            for args in (
                ["clone", "--shared", "--no-checkout", "--quiet", str(root), str(clone)],
                ["-C", str(clone), "checkout", "--quiet", "--detach", head],
            ):
                if gitx.git(args, timeout=60).returncode != 0:
                    return "unknown"
            nm = root / "node_modules"
            if nm.is_dir():
                (clone / "node_modules").symlink_to(nm)
            try:
                proc = subprocess.run(
                    ["npm", "run", "--silent", gate],
                    cwd=clone,
                    capture_output=True,
                    timeout=max(timeout_s, 1.0),
                    check=False,
                    env={k: v for k, v in os.environ.items() if k != "CI"},
                )
            except (OSError, subprocess.TimeoutExpired):
                return "unknown"
            if proc.returncode == 0:
                return "pass"
            return "fail" if proc.stdout or proc.stderr else "unknown"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    return run


def run_probes(
    d: pathlib.Path,
    b: Built,
    runs: dict[str, dict[str, Any]],
    runner: Callable[[str, str, float], str],
    *,
    budget_s: float = PROBE_BUDGET_S,
    now: float | None = None,
) -> dict[str, int]:
    """Probe undecided onsets inside `budget_s`, writing `src: probe` rows. A red at the last green head is repeated up to CLOCK_PERSIST times and counts only beside a control head that is green in the same environment."""
    now = time.time() if now is None else now
    deadline = time.monotonic() + budget_s
    counts = {"candidates": 0, "probed": 0, "skipped_budget": 0, "unknown": 0}
    for ep, green_run, ctrl in probe_candidates(b, runs, now):
        counts["candidates"] += 1
        est = (b.model["gates"].get(ep.subject, {}).get("wall_ms") or 0) / 1000.0
        left = deadline - time.monotonic()
        if est > left:
            counts["skipped_budget"] += 1
            continue
        rows: list[dict[str, Any]] = []
        results = []
        for _ in range(CLOCK_PERSIST):
            left = deadline - time.monotonic()
            if left <= 0:
                break
            res = runner(ep.subject, str(green_run["head"]), left)
            results.append(res)
            counts["unknown"] += res == "unknown"
            rows.extend(_probe_rows(ep, green_run, "green-head", res, now))
            if res != "fail":
                break
        if results and all(r == "fail" for r in results) and ctrl and ctrl.get("head"):
            left = deadline - time.monotonic()
            if left > 0:
                res = runner(ep.subject, str(ctrl["head"]), left)
                counts["unknown"] += res == "unknown"
                rows.extend(_probe_rows(ep, ctrl, "control", res, now))
        L.append_rows(d, rows, now=now)
        counts["probed"] += 1
    return counts


def _probe_rows(
    ep: Episode, at_run: dict[str, Any], role: str, res: str, now: float
) -> list[dict[str, Any]]:
    rid = (
        "probe-" + L.sha(ep.subject, ep.onset.run, role, now, os.getpid(), time.monotonic_ns())[:16]
    )
    outcome = {"pass": "pass", "fail": "fail"}.get(res, "skip")
    return [
        {
            "t": "run",
            "v": L.SCHEMA,
            "id": rid,
            "src": "probe",
            "at": L.iso(now),
            "branch": at_run.get("branch"),
            "head": at_run.get("head"),
            "tree": at_run.get("tree"),
            "salt": at_run.get("salt"),
            "clean": True,
            "whole": False,
            "base_tree": None,
            "changed": [],
            "changed_n": 0,
            "lock_sha": None,
            "classes": None,
            "ci": None,
            "probe_of": ep.onset.run,
            "probe_role": role,
        },
        {
            "t": "g",
            "v": L.SCHEMA,
            "run": rid,
            "gate": ep.subject,
            "outcome": outcome,
            "wall_ms": None,
            "t0_ms": 0,
            "key": at_run.get("tree"),
            "key_kind": "tree",
            "findings": None,
            "attr": "own",
        },
        {
            "t": "end",
            "v": L.SCHEMA,
            "run": rid,
            "wall_ms": None,
            "exit": 0 if res == "pass" else 1,
            "cut": False,
        },
    ]


# ---------------------------------------------------------------------------- report and refresh


def report(b: Built, extra: list[str]) -> str:
    m = b.model
    g = m["gates"]
    by_cls: dict[str, list[str]] = {}
    for gid, v in g.items():
        by_cls.setdefault(v["class"], []).append(gid)
    lines = [
        "# Gate model %s" % m["built_at"],
        "",
        "Generated by `PYTHONPATH=.ci python3 -m rediacc_ci.ci.gate_model refresh`; derived from the ledger and `scripts/ci-runner/gates.lock.json`, never hand-written.",
        "",
        "- runs: %d (%d whole local), observations: %d, gates observed: %d, malformed ledger lines: %d"
        % (m["runs"], b.notes["whole_runs"], b.notes["obs"], len(g), b.notes["malformed"]),
        "- cold start: %s (%s)"
        % ("ON" if m["cold_start"]["on"] else "off", m["cold_start"]["reason"]),
        "- classes: %s" % ", ".join("%s %d" % (c, len(by_cls.get(c, []))) for c in CLASSES),
        "- clock set: %s" % (", ".join(m["clock_set"]) or "(empty)"),
        "- clusters: %d (largest %d), edges: %d (%s)"
        % (
            len(m["clusters"]),
            max((len(c) for c in m["clusters"]), default=0),
            len(b.edges),
            ", ".join("%s %d" % kv for kv in sorted(_count(e["origin"] for e in b.edges).items())),
        ),
        "- associations: %d (class, gate) pairs over %d classes"
        % (sum(len(v) for v in m["associations"].values()), len(m["associations"])),
        "- companions: %d candidate(s), %d reliable"
        % (len(m["companions"]), sum(1 for c in m["companions"] if c["reliable"])),
        "- model quality: %s"
        % (
            "%d of %d reds in preflight or stage 1" % b.notes["quality"]
            if b.notes["quality"]
            else "unmeasured (no staged runs in the ledger yet)"
        ),
        *("- %s" % x for x in extra),
        "",
        "## Episodes by gate (non-pass gates only)",
        "",
    ]
    by_gate: dict[str, list[Episode]] = {}
    for ep in b.episodes:
        by_gate.setdefault(ep.subject, []).append(ep)
    for gid in sorted(by_gate):
        eps = by_gate[gid]
        lines.append(
            "- `%s` %s: %s"
            % (
                gid,
                g.get(gid, {}).get("class", "?"),
                "; ".join(
                    "%s %s %s (%s%s)"
                    % (
                        ep.side,
                        L.iso(ep.onset.t)[:16],
                        ep.cls,
                        ep.why,
                        "; WEAK: the tree changed" if ep.weak else "",
                    )
                    for ep in eps[-6:]
                ),
            )
        )
    lines += ["", "## Clusters", ""]
    lines += ["- %s" % ", ".join("`%s`" % x for x in c) for c in m["clusters"][:30]]
    lines += ["", "## Worklist tokens", ""]
    lines += ["- %s" % text for _tok, _k, text in b.items] or ["- (none)"]
    return "\n".join(lines) + "\n"


def _count(xs: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return out


def write_json(path: pathlib.Path, doc: Any) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def is_fresh(d: pathlib.Path, now: float) -> float | None:
    """Age in hours of `model.json` when younger than MODEL_TTL_H, else None."""
    try:
        built = L.epoch(json.loads((d / "model.json").read_text(encoding="utf-8")).get("built_at"))
    except (OSError, ValueError, AttributeError):
        return None
    if built is None:
        return None
    age = (now - built) / 3600.0
    return age if age < MODEL_TTL_H else None


def refresh(
    d: pathlib.Path,
    root: pathlib.Path,
    *,
    force: bool = False,
    owner: str | None = None,
    ci: bool = True,
    probe: bool = True,
    backfill: bool = True,
    now: float | None = None,
    worklist_cmd: list[str] | None = None,
    runner: Callable[[str, str, float], str] | None = None,
    out: Callable[[str], None] = log.info,
) -> int:
    """Backfill, fold CI, probe, rebuild `model.json`, write the report, sync worklist items. 0 green, 1 nothing to model, 2 built but PARTIAL (a step was unchecked, named on stderr)."""
    now = time.time() if now is None else now
    L.ensure_dir(d)
    age = is_fresh(d, now)
    if age is not None and not force:
        out(
            "gate_model refresh: model.json is %.1fh old (TTL %dh); nothing to do (--force rebuilds)"
            % (age, MODEL_TTL_H)
        )
        return 0
    partial: list[str] = []
    with L.held(d / "refresh.lock"):
        if backfill and L.backfill(d, root, []) != 0:
            partial.append("backfill")
        if ci:
            from rediacc_ci.well_known import GH_REPO  # noqa: PLC0415

            if L.fold_ci(d, root, repo=GH_REPO) != 0:
                partial.append("fold-ci")
        rows, bad = L.read_rows(d)
        lock = load_lock(root)
        b = build(rows, lock, root, now=now, malformed=bad)
        extra = []
        if probe:
            pc = run_probes(
                d,
                b,
                {str(r["id"]): r for r in rows if r.get("t") == "run"},
                runner or clone_runner(root),
                now=now,
            )
            extra.append(
                "probes: %(candidates)d candidate(s), %(probed)d probed, %(skipped_budget)d over budget, %(unknown)d unknown"
                % pc
            )
            if pc["probed"]:
                rows, bad = L.read_rows(d)
                b = build(rows, lock, root, now=now, malformed=bad)
        if not b.model["runs"]:
            log.error(
                "gate_model refresh: the ledger at %s holds 0 runs; a model of nothing would turn ranking on with no evidence"
                % d
            )
            return 1
        write_json(d / "model.json", b.model)
        write_json(d / "edges.json", b.edges)
        if owner:
            try:
                cmd = worklist_cmd or [sys.executable, str(root.joinpath(*WORKLIST_REL))]
                counts = sync_items(d, b.items, owner=owner, worklist_cmd=cmd, cwd=root)
                extra.append(
                    "worklist: %(added)d added, %(updated)d refreshed, %(raced)d claimed by a concurrent refresh, %(failed)d failed"
                    % counts
                )
                if counts["failed"]:
                    partial.append("worklist")
            except (OSError, RuntimeError) as exc:
                partial.append("worklist")
                log.error("gate_model refresh: worklist sync failed: %s" % exc)
        else:
            extra.append(
                "worklist: NOT written (no --owner); %d item(s) listed below" % len(b.items)
            )
        rep = L.ensure_dir(d / "reports") / ("%s.md" % L.iso(now)[:10])
        rep.write_text(report(b, extra), encoding="utf-8")
    m = b.model
    out(
        "gate_model refresh: %d run(s), %d gate(s) modelled, clock set %d, %d cluster(s), %d association(s), %d companion(s), %d item(s); cold start %s (%s); model %s; report %s%s"
        % (
            m["runs"],
            len(m["gates"]),
            len(m["clock_set"]),
            len(m["clusters"]),
            sum(len(v) for v in m["associations"].values()),
            len(m["companions"]),
            len(b.items),
            "ON" if m["cold_start"]["on"] else "off",
            m["cold_start"]["reason"],
            d / "model.json",
            rep,
            "; PARTIAL: %s unchecked" % ", ".join(partial) if partial else "",
        )
    )
    return 2 if partial else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gate_model", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    rf = sub.add_parser("refresh", help="rebuild model.json when older than MODEL_TTL_H")
    rf.add_argument("--force", action="store_true")
    rf.add_argument(
        "--owner",
        help="session prefix the worklist items are written as; without it no item is written",
    )
    rf.add_argument("--no-ci", action="store_true", help="skip the CI fold-in")
    rf.add_argument("--no-probe", action="store_true", help="skip the clock probes")
    rf.add_argument("--no-backfill", action="store_true", help="skip the receipt backfill")
    sub.add_parser("show", help="print model.json")
    args = ap.parse_args(argv)
    root = paths.repo_root()
    d = L.ledger_dir(root=root)
    if d is None:
        log.error("gate_model: the ledger is OFF (CI=true and no $%s)" % L.LEDGER_ENV)
        return 1
    if args.cmd == "show":
        try:
            sys.stdout.write((d / "model.json").read_text(encoding="utf-8"))
        except OSError as exc:
            log.error("gate_model: no model at %s: %s" % (d / "model.json", exc))
            return 1
        return 0
    return refresh(
        d,
        root,
        force=args.force,
        owner=args.owner,
        ci=not args.no_ci,
        probe=not args.no_probe,
        backfill=not args.no_backfill,
    )


if __name__ == "__main__":
    raise SystemExit(main())
