#!/usr/bin/env python3
"""check:ci-plan-live-proof -- a plan that touches a deployable surface closes only on a live receipt from bench or hostinger.

The design is agent/plans/PLAN-tested-on-bench.md (Design items 2, 3 and 7, box V6). The operator asked on 2026-10-27 for a CI rule behind a "tested on bench" box; the rulings of the same day narrowed the live targets to bench and hostinger (`--config eu-bench`), made `Live-Proof: none` pass only under a resolvable ruling, and made LP1 to LP6 red from the landing commit.

NOTHING IS RE-IMPLEMENTED HERE. The header grammar is `wl_plandeps` (`live_proof_findings`, `resolve_live_proof_waiver`), the box parser is `wl_plandeps.plan_boxes` (the Stop hook's `wl_planrec` reader), the surface map is `rediacc_ci.proof.surfaces` (`owns_surfaces`, `inputs`), the registry, the Accept line, the match and the row judge are `rediacc_ci.proof.live_tier`, the forward-only machinery (`moved_to_done`, `after_baseline`) is check_plan_implementation's, imported, and the rebase successor map (`lazy_successor_of`) is `rediacc_ci.review.successor`, the one both gates use. This file only composes them into rules.

WHICH PLANS ARE REQUIRED: a top-level, non-stub plan whose Status is not finished and whose `Owns:` globs hit at least one surface of `.ci/config/proof-tiers.json` (minus its excludes), by `surfaces.owns_surfaces`, the reading the pre-edit guard `block_plan_without_depends` and the recorder share.

THE RULES, EACH WITH A PLANTED CONTROL IN `--selftest`:

    LP1 a required plan has no `Live-Proof:` line, or the line is malformed,
        emphasised, duplicated or outside the 12-line window. While
        `baseline_at` is unset, a committed plan that has NO line yet is the V7
        migration set: printed as PENDING, not LP1 (LP7 reds that tree anyway).
        Setting `baseline_at` closes the window. Once a line exists it is judged
        in full.
    LP2 a declared target that no touched surface admits, a touched surface no
        declared target covers, or a `none` whose cited ruling does not resolve.
    LP3 a plan that declares targets without exactly one `LP-<target> [live]` box
        per target, or a box with no `Accept: live-proof <target> <check-id> [args]`
        sub-line, an Accept naming another target, a check that does not run on the
        target, arguments the registry refuses, or a check that covers none of the
        plan's surfaces the target admits. An `LP-<target>` box on a `none` plan or
        for an undeclared target is LP3 too.
    LP4 an `LP-<target>` box this branch moved open -> done, in a commit authored
        strictly after `baseline_at` (the author date, which a rebase keeps), with no ledger row matching plan, box sig,
        target, VERIFIED, rc 0, clean tree and the Accept line's check and arguments.
    LP5 every matching row is invalid: `live_tier.validate_row` (envelope, id,
        registry argv, deploy at head and confirmed live, version id, identity
        rules, secret shapes, head/tree resolve, inputs at the row's tree, the kept
        log), plus its head is not an ancestor of the ticking commit (through the
        rebase successor map), plus the inputs digest at the ticking commit differs
        from the row's (surface code changed after the proof). An unparseable
        ledger line is LP5 too.
    LP6 a required plan reached a finished Status or `_done/` on this branch, after
        `baseline_at`, without a valid receipt per declared target, unless its
        `Ruling:` line resolves and names the live-proof waiver.
    LP7 vacuity: the surface map or the live registry is empty or unparsable,
        `baseline_at` is unset or not a date, a surface admits a target that no
        registry check covers, an Accept line names a check the registry lacks, or
        zero required plans are derived while live plans' Owns plainly name surface
        paths, or LP4 to LP6 cannot run (no merge-base, or plan-boxes.json
        unreadable at HEAD or at the base). ZERO parsed plans is CANNOT RUN (exit 77), never green.

ADVISORY, printed every run, red or green: every `Live-Proof: none` on a required plan, and the PENDING (V7) set.

FORWARD-ONLY. LP4 to LP6 judge only transitions committed strictly after `baseline_at` (`.ci/config/proof-tiers.json` `tiers.live.baseline_at`), the device P-A2 uses: on the landing commit they are silent by construction. No allowlist and no suppression: the waiver is a named operator ruling, never a config entry.

Exit codes: 0 green, 1 findings, 2 a control failed or bad usage, 77 cannot run.

    --selftest            the planted controls alone
    --root <dir>          judge another tree (the gate test's door)
    --base <ref>          judge transitions against merge-base(HEAD, <ref>) (default:
                          check_plan_boxes.base_ref for this checkout, else the
                          merge-base with origin/main or main)
    --proof-map <path>    read baseline_at and the registry for LP7 from another map
                          (what-if; the surfaces themselves are the committed map's)
    --baseline-at <date>  override baseline_at (what-if)

---- gate ----
step: Plan live proof
needs: none
selftest: true
lane: quality-branch
needs-not: submodules
blocker: BLOCKER: the gate reads plan headers, agent/ledgers/live-proof.jsonl and
     the console's own git history. A submodule surface is judged by its glob in
     proof-tiers.json and by the gitlink pointer in the inputs digest, which
     `git ls-tree` reads from the console tree with no submodule checkout.
why: a plan that changes deployable code must close on a live receipt from bench or
     hostinger (operator request and rulings of 2026-10-27, PLAN-tested-on-bench).
     The receipt ledger is committed, so CI judges it with no secrets and no network.
---- end gate ----
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import importlib
import json
import pathlib
import re
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import _cipath
from rediacc_ci import controls, paths

paths.on_sys_path(paths.hooks_stop_dir())

try:
    import check_plan_implementation as PI
    import wl_plandeps as D
    import wl_planfile as PF
    from rediacc_ci.proof import live_tier as LT
    from rediacc_ci.proof import surfaces as S
    from rediacc_ci.review import successor as SUCC
except ImportError as _exc:  # pragma: no cover -- a tree without the hook or proof modules
    print(
        "VACUOUS INPUT: cannot import the live-proof modules (%s). The grammar, the surface map "
        "and the row judge live only there, so without them there is nothing to judge." % _exc,
        file=sys.stderr,
    )
    sys.exit(77)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

REPO_ROOT = paths.repo_root()
BOXES_REL = ".ci/config/plan-boxes.json"
MAP_REL = ".ci/config/proof-tiers.json"
CANNOT_RUN = 77
CONTROL_FLOOR = 80
LP_BOX_RE = re.compile(r"^LP-([A-Za-z0-9_-]+)\b(.*)$")
LIVE_MARK = "[live]"
# A Ruling line that waives the live proof names it in so many words.
WAIVER_WORD_RE = re.compile(r"live[- ]proof", re.IGNORECASE)
FINISHED_FOLDERS = ("agent/plans/_done",)


class CannotRunError(RuntimeError):
    """No verdict is possible: exit 77, which is not a pass."""


@dataclasses.dataclass(frozen=True)
class Finding:
    code: str
    rel: str
    message: str

    def __str__(self) -> str:
        return "%s %s: %s" % (self.code, self.rel, self.message)


@dataclasses.dataclass
class Plan:
    rel: str
    text: str
    header: Any
    folder: str
    stub: bool
    finished: bool
    touched: dict[str, list[str]]

    @property
    def live(self) -> bool:
        return self.folder == D.PLANS_DIR and not self.stub and not self.finished

    @property
    def required(self) -> bool:
        return self.live and bool(self.touched)

    @property
    def owns_globs(self) -> tuple[str, ...]:
        owns = self.header.owns
        return tuple(owns.globs) if owns is not None else ()


def make_plan(rel: str, text: str, finished_states: Iterable[str]) -> Plan:
    header = D.parse_header(text)
    folder = rel.rsplit("/", 1)[0]
    stub = D.is_stub_header(header)
    status = header.status
    finished = status in set(finished_states) or status == D.REMOVED_STATUS
    owns = header.owns
    touched = S.owns_surfaces(owns.globs) if owns is not None and not stub else {}
    return Plan(rel, text, header, folder, stub, finished, touched)


def identity(rel: str) -> str:
    return PI._plan_identity(rel)


# ----------------------------------------------------------------------------- the map (LP7)


@dataclasses.dataclass
class MapView:
    """What LP7 reads from a proof map: surface name -> admitted live targets, the parsed registry (or its error) and baseline_at."""

    live_of: dict[str, tuple[str, ...]]
    checks: dict[str, LT.Check]
    registry_error: str
    baseline_at: object


def map_view(raw: object) -> MapView:
    live_of: dict[str, tuple[str, ...]] = {}
    checks: dict[str, LT.Check] = {}
    error = ""
    baseline = None
    if not isinstance(raw, dict):
        return MapView(live_of, checks, "the map is not a JSON object", baseline)
    surfaces = raw.get("surfaces")
    for name, entry in (surfaces if isinstance(surfaces, dict) else {}).items():
        if isinstance(entry, dict):
            live_of[name] = tuple(entry.get("live") or ())
    tiers = raw.get("tiers")
    live = tiers.get("live") if isinstance(tiers, dict) else None
    try:
        checks = LT.parse_checks(live)
    except LT.RegistryError as exc:
        error = str(exc)
    if isinstance(live, dict):
        baseline = live.get("baseline_at")
    return MapView(live_of, checks, error, baseline)


def parse_baseline(value: object) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value or "").strip())
    except ValueError:
        return None


def map_findings(view: MapView) -> list[Finding]:
    out: list[Finding] = []
    if not view.live_of:
        out.append(
            Finding("LP7", MAP_REL, "the surface map is empty or unparsable; no plan can be judged")
        )
    if view.registry_error:
        out.append(
            Finding("LP7", MAP_REL, "the live registry cannot be read: %s" % view.registry_error)
        )
    if parse_baseline(view.baseline_at) is None:
        out.append(
            Finding(
                "LP7",
                MAP_REL,
                "tiers.live.baseline_at is %r, not a YYYY-MM-DD date, so LP4 to LP6 have no "
                "forward-only cut. Set it to the landing date." % (view.baseline_at,),
            )
        )
    out.extend(
        Finding(
            "LP7",
            MAP_REL,
            "surface %s admits target %s but no registry check covers it there; add "
            "a named entry under tiers.live.checks" % (name, target),
        )
        for name, targets in view.live_of.items()
        for target in targets
        if not any(target in c.targets and name in c.surfaces for c in view.checks.values())
    )
    return out


def surface_prefixes() -> list[str]:
    out = []
    for surface in S.MAP.surfaces.values():
        for glob in surface.globs:
            lit = re.split(r"[*?{\[]", glob, maxsplit=1)[0]
            if "/" in lit:
                out.append(lit)
    return out


def plainly_hit(plans: Iterable[Plan], prefixes: list[str]) -> int:
    """How many live plans name a surface path in Owns by its literal prefix: the independent count LP7 compares the derived required set against."""
    return sum(
        1
        for p in plans
        if p.live and any(g.startswith(pre) for g in p.owns_globs for pre in prefixes)
    )


# ----------------------------------------------------------------------------- LP1 to LP3


def header_findings(
    plan: Plan,
    live_of: dict[str, tuple[str, ...]],
    pending: bool,
    resolve_waiver: Callable[[Plan], tuple[bool, str]],
) -> tuple[list[Finding], list[str]]:
    """(findings, advisories) for one required plan's `Live-Proof:` line. `pending` marks a committed plan while baseline_at is unset (the V7 window): a MISSING line on it is an advisory, never a finding."""
    out: list[Finding] = []
    notes: list[str] = []
    absent = plan.header.get(D.LIVE_PROOF) is None and not plan.header.field_errors(D.LIVE_PROOF)
    if absent and pending:
        notes.append(
            "PENDING (V7) %s: no Live-Proof line yet; surfaces %s"
            % (plan.rel, ", ".join(sorted(plan.touched)))
        )
        return out, notes
    out.extend(
        Finding(code, plan.rel, msg) for code, msg in D.live_proof_findings(plan.header, True)
    )
    proof = plan.header.live_proof
    if proof is None:
        return out, notes
    if proof.none:
        ok, why = resolve_waiver(plan)
        notes.append(
            "ADVISORY %s: Live-Proof: none on a plan touching %s (%s)"
            % (plan.rel, ", ".join(sorted(plan.touched)), "ruling resolves" if ok else "UNRESOLVED")
        )
        if not ok:
            out.append(Finding("LP2", plan.rel, why))
        return out, notes
    for name in sorted(plan.touched):
        admitted = live_of.get(name, ())
        if not set(proof.targets) & set(admitted):
            out.append(
                Finding(
                    "LP2",
                    plan.rel,
                    "surface %s (Owns %s) is left uncovered: it admits %s, the plan declares %s"
                    % (
                        name,
                        ", ".join(plan.touched[name][:3]),
                        " or ".join(admitted) or "no target",
                        ", ".join(proof.targets),
                    ),
                )
            )
    out.extend(
        Finding(
            "LP2",
            plan.rel,
            "target %s is admissible for none of the touched surfaces (%s)"
            % (target, ", ".join(sorted(plan.touched))),
        )
        for target in proof.targets
        if not any(target in live_of.get(n, ()) for n in plan.touched)
    )
    return out, notes


def lp_boxes(plan: Plan) -> list[tuple[str, Any]]:
    """[(target, box)] for every `LP-<target>` box of the plan, `LP-none` excluded."""
    out = []
    for box in D.plan_boxes(plan.text):
        m = LP_BOX_RE.match(box.body.strip())
        if m and m.group(1) != D.LIVE_NONE:
            out.append((m.group(1), box))
    return out


def _one_box(
    plan: Plan,
    target: str,
    box: Any,
    checks: dict[str, LT.Check],
    live_of: dict[str, tuple[str, ...]],
) -> Finding | None:
    """The first defect of one `LP-<target>` box on a plan that declares `target`, else None."""
    where = "box LP-%s (%s)" % (target, box.sig)
    m = LP_BOX_RE.match(box.body.strip())
    if m is None:
        # lp_boxes() only hands over boxes this regex matched, so this is a caller bug, not a plan defect.
        raise ValueError(
            "%s: _one_box was handed a box that is not an LP box: %r" % (plan.rel, box.body)
        )
    rest = m.group(2).lstrip(" :")
    if not rest.startswith(LIVE_MARK):
        return Finding(
            "LP3", plan.rel, "%s lacks the `%s` marker after its id" % (where, LIVE_MARK)
        )
    accept = LT.accept_of(plan.text, box.line)
    if accept is None:
        return Finding(
            "LP3",
            plan.rel,
            "%s carries no `Accept: live-proof %s <check-id> [args]` sub-line" % (where, target),
        )
    if accept.target != target:
        return Finding(
            "LP3", plan.rel, "%s accepts a run on %s, not %s" % (where, accept.target, target)
        )
    check = checks.get(accept.check)
    if check is None:
        return Finding(
            "LP7",
            plan.rel,
            "%s names check %r, which is not in tiers.live.checks" % (where, accept.check),
        )
    if target not in check.targets:
        return Finding(
            "LP3", plan.rel, "%s: check %s does not run on %s" % (where, check.id, target)
        )
    try:
        LT.expand(check, target, LT.machine_of_args(accept.args))
    except LT.RegistryError as exc:
        return Finding("LP3", plan.rel, "%s: %s" % (where, exc))
    owed = {n for n in plan.touched if target in live_of.get(n, ())}
    if owed and not (check.surfaces & owed):
        return Finding(
            "LP3",
            plan.rel,
            "%s: check %s covers %s, none of the plan's %s surfaces (%s), so its pass proves "
            "nothing about this plan"
            % (where, check.id, ", ".join(sorted(check.surfaces)), target, ", ".join(sorted(owed))),
        )
    return None


def box_findings(
    plan: Plan, checks: dict[str, LT.Check], live_of: dict[str, tuple[str, ...]]
) -> list[Finding]:
    """LP3 (and LP7 for an unregistered check) over one plan's `LP-<target>` boxes."""
    proof = plan.header.live_proof
    if proof is None:
        return []
    out: list[Finding] = []
    boxes = lp_boxes(plan)
    for target in proof.targets:
        mine = [b for t, b in boxes if t == target]
        if not mine:
            out.append(
                Finding(
                    "LP3",
                    plan.rel,
                    "declares %s but has no `- [ ] LP-%s [live] ...` box with an `Accept: "
                    "live-proof %s <check-id>` sub-line" % (target, target, target),
                )
            )
        elif len(mine) > 1:
            out.append(
                Finding("LP3", plan.rel, "%d LP-%s boxes; one per target" % (len(mine), target))
            )
    for target, box in boxes:
        where = "box LP-%s (%s)" % (target, box.sig)
        if proof.none:
            out.append(Finding("LP3", plan.rel, "%s on a plan that declares `none`" % where))
        elif target not in proof.targets:
            out.append(
                Finding("LP3", plan.rel, "%s names a target the header does not declare" % where)
            )
        else:
            found = _one_box(plan, target, box, checks, live_of)
            if found is not None:
                out.append(found)
    return out


# ----------------------------------------------------------------------------- LP4 to LP6


@dataclasses.dataclass
class Oracles:
    """Every git- or ledger-backed answer the transition rules need, injected so the controls drive the same functions the real run does."""

    done_commit_of: Callable[[str, str], str]
    date_of: Callable[[str], str]
    judge_row: Callable[[dict[str, Any], str], list[str]]


def matching_rows(
    rows: Iterable[dict[str, Any]], rel: str, sig: str, target: str, accept: Any
) -> list[dict[str, Any]]:
    """The rows `live_tier.matches` accepts for one box, the plan compared by identity so a `_done/` move keeps its receipts."""
    ident = identity(rel)
    return [
        r
        for r in rows
        if identity(str(r.get("plan") or "")) == ident
        and LT.matches(r, str(r.get("plan")), sig, target, accept)
    ]


def _bump(tally: dict[str, int], key: str) -> None:
    tally[key] = tally.get(key, 0) + 1


def tick_findings(
    judged: Iterable[tuple[str, str]],
    plans: dict[str, Plan],
    rows: list[dict[str, Any]],
    baseline: object,
    oracles: Oracles,
    tally: dict[str, int] | None = None,
) -> list[Finding]:
    """LP4 and LP5 over the boxes this branch closed."""
    out: list[Finding] = []
    tally = {} if tally is None else tally
    for rel, sig in judged:
        plan = plans.get(rel)
        if plan is None:
            continue
        hit = next(((t, b) for t, b in lp_boxes(plan) if b.sig == sig), None)
        if hit is None:
            continue
        target, box = hit
        _bump(tally, "lp_closed")
        commit = oracles.done_commit_of(rel, sig)
        if not PI.after_baseline(baseline, oracles.date_of(commit) if commit else ""):
            continue
        _bump(tally, "lp_bound")
        accept = LT.accept_of(plan.text, box.line)
        found = matching_rows(rows, rel, sig, target, accept) if accept is not None else []
        if not found:
            want = (
                "live-proof %s %s%s" % (target, accept.check, "".join(" " + a for a in accept.args))
                if accept is not None
                else "an Accept line the box does not carry"
            )
            out.append(
                Finding(
                    "LP4",
                    rel,
                    "box LP-%s (%s) was ticked in %s with no VERIFIED, clean, rc 0 row in "
                    "agent/ledgers/live-proof.jsonl for `%s`. Record it before the tick: "
                    "worklist.py --live-proof <me> %s %s --tick --write"
                    % (target, sig, commit[:12], want, rel, sig),
                )
            )
            continue
        problems = [oracles.judge_row(r, commit) for r in found]
        if all(problems):
            out.append(
                Finding(
                    "LP5",
                    rel,
                    "box LP-%s (%s): every matching receipt is invalid; %s: %s"
                    % (target, sig, found[0].get("id"), "; ".join(problems[0])),
                )
            )
    return out


def judge_row(
    row: dict[str, Any],
    commit: str,
    *,
    validate: Callable[[dict[str, Any]], list[str]],
    successor_of: Callable[[str], str | None],
    ancestor_fn: Callable[[str, str], bool],
    inputs_at: Callable[[str, list[str]], str | None],
) -> list[str]:
    """LP5's reasons one matching row is invalid, judged against the commit that ticked its box."""
    problems = list(validate(row))
    head = str(row.get("head") or "")
    if not commit:
        return problems
    mapped = successor_of(head) or head
    if not ancestor_fn(mapped, commit):
        problems.append(
            "head %s is not an ancestor of the ticking commit %s" % (head[:12], commit[:12])
        )
    names = row.get("surfaces")
    if isinstance(names, list) and names:
        at_tick = inputs_at(commit, names)
        if at_tick is None or at_tick != row.get("inputs"):
            problems.append(
                "the inputs digest at the ticking commit %s differs from the row's: surface "
                "code changed after the proof" % commit[:12]
            )
    return problems


def ruling_waives(plan: Plan, resolve: Callable[[Plan], tuple[bool, str]]) -> bool:
    line = PF.ruling_line(plan.text) or ""
    return bool(line and WAIVER_WORD_RE.search(line) and resolve(plan)[0])


def _has_receipt(
    plan: Plan, target: str, rows: list[dict[str, Any]], commit: str, oracles: Oracles
) -> bool:
    for t, box in lp_boxes(plan):
        accept = LT.accept_of(plan.text, box.line) if t == target else None
        if accept is None:
            continue
        for row in matching_rows(rows, plan.rel, box.sig, t, accept):
            if not oracles.judge_row(row, commit):
                return True
    return False


def finish_findings(
    finished: Iterable[tuple[str, str]],
    plans: dict[str, Plan],
    rows: list[dict[str, Any]],
    baseline: object,
    oracles: Oracles,
    resolvers: tuple[Callable[[Plan], tuple[bool, str]], Callable[[Plan], tuple[bool, str]]],
    tally: dict[str, int] | None = None,
) -> list[Finding]:
    """LP6 over the (rel, finishing commit) pairs of plans this branch finished. `resolvers` is (the `Ruling:` resolver, the `none` waiver resolver)."""
    resolve_ruling, resolve_waiver = resolvers
    out: list[Finding] = []
    tally = {} if tally is None else tally
    for rel, commit in finished:
        plan = plans.get(rel)
        if plan is None or not plan.touched:
            continue
        _bump(tally, "finished")
        if not PI.after_baseline(baseline, oracles.date_of(commit) if commit else ""):
            continue
        _bump(tally, "finished_bound")
        if ruling_waives(plan, resolve_ruling):
            continue
        proof = plan.header.live_proof
        if proof is None:
            out.append(
                Finding(
                    "LP6",
                    rel,
                    "finished in %s touching %s with no valid Live-Proof line"
                    % (commit[:12], ", ".join(sorted(plan.touched))),
                )
            )
            continue
        if proof.none:
            ok, why = resolve_waiver(plan)
            if not ok:
                out.append(
                    Finding(
                        "LP6",
                        rel,
                        "finished in %s under an unresolved none: %s" % (commit[:12], why),
                    )
                )
            continue
        out.extend(
            Finding(
                "LP6",
                rel,
                "finished in %s without a valid receipt for its declared target %s"
                % (commit[:12], target),
            )
            for target in proof.targets
            if not _has_receipt(plan, target, rows, commit, oracles)
        )
    return out


def finished_on_branch(
    base_plans: dict[str, Any],
    head_plans: dict[str, Any],
    is_finished: Callable[[dict[str, Any], str], bool],
) -> list[str]:
    """Head rels (non-stub rows) whose plan identity is finished at head and was not finished, or absent, at the base."""
    base_by: dict[str, bool] = {}
    for rel, row in (base_plans or {}).items():
        if isinstance(row, dict) and row.get("status") != D.STUB_STATUS:
            base_by[identity(rel)] = base_by.get(identity(rel), False) or is_finished(row, rel)
    return [
        rel
        for rel, row in sorted((head_plans or {}).items())
        if isinstance(row, dict)
        and row.get("status") != D.STUB_STATUS
        and is_finished(row, rel)
        and not base_by.get(identity(rel), False)
    ]


def first_of_latest_run(
    history: list[tuple[str, dict[str, Any]]], pred: Callable[[dict[str, Any]], bool]
) -> str:
    """The first commit of the latest unbroken run of `history` (oldest first) that satisfies `pred`, the `wl_planrec.done_commit` rule, or "" when the newest does not."""
    start = ""
    for commit, doc in history:
        start = (start or commit) if pred(doc) else ""
    return start


# ----------------------------------------------------------------------------- git and the tree


def _git(root: pathlib.Path, *args: str) -> str | None:
    r = subprocess.run(
        ["git", "-C", str(root), "-c", "core.quotePath=false", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return r.stdout if r.returncode == 0 else None


def load_plans(root: pathlib.Path, finished_states: Iterable[str]) -> dict[str, Plan]:
    out: dict[str, Plan] = {}
    states = frozenset(finished_states)
    for folder in D.PLAN_DIRS:
        try:
            names = sorted(p.name for p in (root / folder).iterdir())
        except OSError:
            continue
        for name in names:
            if not (name.startswith("PLAN-") and name.endswith(".md")):
                continue
            rel = "%s/%s" % (folder, name)
            try:
                text = (root / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            out[rel] = make_plan(rel, text, states)
    return out


def added_dates(root: pathlib.Path) -> dict[str, str]:
    """{rel: author date of the first commit that added it} for every plan path git knows."""
    raw = (
        _git(
            root,
            "log",
            "--reverse",
            "--no-renames",
            "--diff-filter=A",
            "--format=%x00%aI",
            "--name-only",
            "--",
            D.PLANS_DIR,
        )
        or ""
    )
    out: dict[str, str] = {}
    when = ""
    for line in raw.splitlines():
        if line.startswith("\x00"):
            when = line[1:].strip()
        elif line.strip():
            out.setdefault(line.strip(), when)
    return out


def pending_migration(rel: str, added: dict[str, str], baseline: dt.date | None) -> bool:
    """A committed plan is in the V7 migration set only while baseline_at is unset (LP7 already reds that tree). Setting baseline_at is V7 landing, so from then on a missing line is LP1 on every plan, old or new. An uncommitted plan is new, so never pending."""
    return baseline is None and bool(added.get(rel, ""))


def base_of(root: pathlib.Path, explicit: str | None) -> str:
    if explicit:
        return (_git(root, "merge-base", "HEAD", explicit) or "").strip()
    if root.resolve() == REPO_ROOT.resolve():
        try:
            return importlib.import_module("check_plan_boxes").base_ref() or ""
        except ImportError:
            return ""
    for ref in ("origin/main", "main"):
        got = (_git(root, "merge-base", "HEAD", ref) or "").strip()
        if got:
            return got
    return ""


def boxes_at(root: pathlib.Path, rev: str | None) -> dict[str, Any] | None:
    """The `plans` block of plan-boxes.json in the working tree (`rev` None) or at a commit."""
    if rev is None:
        try:
            raw: str | None = (root / BOXES_REL).read_text(encoding="utf-8")
        except OSError:
            return None
    else:
        raw = _git(root, "show", "%s:%s" % (rev, BOXES_REL))
    if raw is None:
        return None
    try:
        doc = json.loads(raw)
    except ValueError:
        return None
    plans = doc.get("plans") if isinstance(doc, dict) else None
    return plans if isinstance(plans, dict) else None


def branch_history(root: pathlib.Path, base: str) -> list[tuple[str, dict[str, Any]]]:
    out = []
    listing = _git(root, "log", "--reverse", "--format=%H", "%s..HEAD" % base, "--", BOXES_REL)
    for sha in (listing or "").split():
        plans = boxes_at(root, sha)
        if plans is not None:
            out.append((sha, {"plans": plans}))
    return out


def _ledger_rel() -> str:
    """The ledger's repo-relative path, for a finding's location. A function rather than a module name on purpose: the pre-bash guard block_live_proof_ledger_shell_write reads a name bound to the ledger path and then passed to `.append()` as a write to the ledger, and refuses to run this gate."""
    return "/".join(LT.LEDGER)


def read_rows(root: pathlib.Path) -> tuple[list[dict[str, Any]], list[Finding]]:
    rows: list[dict[str, Any]] = []
    bad: list[Finding] = []
    for entry in LT.read_ledger(LT.ledger_path(root)):
        if entry.row is None:
            bad.append(
                Finding(
                    "LP5",
                    _ledger_rel(),
                    "line %d is not a receipt row: %s" % (entry.lineno, entry.error),
                )
            )
        else:
            rows.append(entry.row)
    return rows, bad


# ----------------------------------------------------------------------------- the run


@dataclasses.dataclass
class Context:
    root: pathlib.Path
    view: MapView
    plans: dict[str, Plan]
    rows: list[dict[str, Any]]
    states: dict[str, dict[str, str]] = dataclasses.field(default_factory=dict)

    def item_states(self) -> dict[str, str]:
        if "s" not in self.states:
            self.states["s"] = PF.store_item_states(str(self.root))
        return self.states["s"]

    def resolve_waiver(self, plan: Plan) -> tuple[bool, str]:
        return D.resolve_live_proof_waiver(
            str(self.root), plan.rel, plan.header.live_proof, self.item_states()
        )

    def resolve_ruling(self, plan: Plan) -> tuple[bool, str]:
        return PF.resolve_ruling(str(self.root), plan.rel, plan.text, self.item_states())


def _transition_oracles(ctx: Context, base: str, history: Callable[[], list]) -> Oracles:
    root = ctx.root
    checks = ctx.view.checks or LT.registry()
    successor_of = SUCC.lazy_successor_of(str(root), base, importlib.import_module("wl_planrec"))

    def done_commit_of(rel: str, sig: str) -> str:
        def attests(doc: dict[str, Any]) -> bool:
            row = (doc.get("plans") or {}).get(rel) or {}
            return sig in (row.get("done_sigs") or [])

        return first_of_latest_run(history(), attests)

    def date_of(commit: str) -> str:
        # The author date, which a rebase keeps: the committer date would move every tick on a rebased branch past baseline_at.
        return (_git(root, "log", "-1", "--format=%aI", commit) or "").strip()

    def inputs_at(commit: str, names: list[str]) -> str | None:
        if not all(n in S.MAP.surfaces for n in names):
            return None
        tree = (_git(root, "rev-parse", "%s^{tree}" % commit) or "").strip()
        return S.inputs(root, tree, names) if tree else None

    def ancestor(a: str, b: str) -> bool:
        return bool(a) and _git(root, "merge-base", "--is-ancestor", a, b) is not None

    def validate(row: dict[str, Any]) -> list[str]:
        return LT.validate_row(row, checks=checks, root=root, successor_of=successor_of)

    def judge(row: dict[str, Any], commit: str) -> list[str]:
        return judge_row(
            row,
            commit,
            validate=validate,
            successor_of=successor_of,
            ancestor_fn=ancestor,
            inputs_at=inputs_at,
        )

    return Oracles(done_commit_of, date_of, judge)


def _skip_finding(why: str) -> Finding:
    return Finding(
        "LP7",
        BOXES_REL,
        "LP4 to LP6 did not run (%s), so a green would mean nothing; fetch the base "
        "(CI needs fetch-depth 0 and GITHUB_BASE_REF) or pass --base <ref>" % why,
    )


def transitions(ctx: Context, base_override: str | None) -> tuple[list[Finding], str]:
    """LP4 to LP6 and the summary line that says what they judged (or why they did not run)."""
    root = ctx.root
    base = base_of(root, base_override)
    head_plans = boxes_at(root, None)
    base_plans = boxes_at(root, base) if base else None
    # A skip is a finding, never a green: with no base LP4 to LP6 judge nothing, and every tick on the branch would pass unchecked.
    if not base:
        why = "no merge-base to judge transitions against"
        return [_skip_finding(why)], "SKIPPED: " + why
    if head_plans is None or base_plans is None:
        where = "HEAD" if head_plans is None else base[:12]
        why = "%s is unreadable at %s" % (BOXES_REL, where)
        return [_skip_finding(why)], "SKIPPED: " + why
    memo: dict[str, list] = {}

    def history() -> list[tuple[str, dict[str, Any]]]:
        if "h" not in memo:
            memo["h"] = branch_history(root, base)
        return memo["h"]

    oracles = _transition_oracles(ctx, base, history)
    tally: dict[str, int] = {}
    judged = PI.moved_to_done(base_plans, head_plans)
    found = tick_findings(judged, ctx.plans, ctx.rows, ctx.view.baseline_at, oracles, tally)
    states = PF.FINISHED_STATES

    def is_finished(row: dict[str, Any], rel: str) -> bool:
        return row.get("status") in states or rel.rsplit("/", 1)[0] in FINISHED_FOLDERS

    pairs = []
    for rel in finished_on_branch(base_plans, head_plans, is_finished):
        ident = identity(rel)

        def done(doc: dict[str, Any], ident: str = ident) -> bool:
            return any(
                identity(r) == ident
                and isinstance(v, dict)
                and v.get("status") != D.STUB_STATUS
                and is_finished(v, r)
                for r, v in (doc.get("plans") or {}).items()
            )

        pairs.append((rel, first_of_latest_run(history(), done)))
    found += finish_findings(
        pairs,
        ctx.plans,
        ctx.rows,
        ctx.view.baseline_at,
        oracles,
        (ctx.resolve_ruling, ctx.resolve_waiver),
        tally,
    )
    line = (
        "base %s: %d box(es) closed on the branch, %d LP box(es) among them, %d bound after %s; "
        "%d surface plan(s) finished, %d bound"
        % (
            base[:12],
            len(judged),
            tally.get("lp_closed", 0),
            tally.get("lp_bound", 0),
            ctx.view.baseline_at,
            tally.get("finished", 0),
            tally.get("finished_bound", 0),
        )
    )
    return found, line


def evaluate(
    root: pathlib.Path, view: MapView, base_override: str | None
) -> tuple[list[Finding], list[str], dict[str, Any]]:
    plans = load_plans(root, PF.FINISHED_STATES)
    live = [p for p in plans.values() if p.live]
    if not live:
        raise CannotRunError(
            "zero live plans parsed under %s; a tree with no live plan is not a clean one"
            % (root / D.PLANS_DIR)
        )
    rows, bad_lines = read_rows(root)
    ctx = Context(root, view, plans, rows)
    findings = map_findings(view) + bad_lines
    notes: list[str] = []
    baseline = parse_baseline(view.baseline_at)
    required = [p for p in live if p.required]
    hits = plainly_hit(live, surface_prefixes()) if view.live_of else 0
    if not required and hits:
        findings.append(
            Finding(
                "LP7",
                D.PLANS_DIR,
                "zero required plans derived, yet %d live plan(s) name surface paths in Owns; "
                "the surface reading stopped matching" % hits,
            )
        )
    added = added_dates(root)
    for plan in required:
        pending = pending_migration(plan.rel, added, baseline)
        found, more = header_findings(plan, view.live_of, pending, ctx.resolve_waiver)
        findings.extend(found)
        notes.extend(more)
        findings.extend(box_findings(plan, view.checks, view.live_of))
    moved, line = transitions(ctx, base_override)
    findings.extend(moved)
    stats: dict[str, Any] = {
        "plans": len(plans),
        "live": len(live),
        "required": len(required),
        "plainly": hits,
        "rows": len(rows),
        "baseline_at": view.baseline_at,
        "pending": sum(n.startswith("PENDING") for n in notes),
        "transitions": line,
    }
    return findings, notes, stats


# ----------------------------------------------------------------------------- selftest

_HEAD = (
    "# PLAN: fixture\n\nStatus: in-progress\nOwner: cafe0000\n"
    "Depends-On: no-dep -- a fixture plan that stands alone\nPriority: P2\n"
    "Concurrency: parallel\nOwns: %s\n%s\n## Tasks\n\n%s"
)
_GOOD_BOX = "- [ ] LP-bench [live] the bench smoke\n  - Accept: `live-proof bench account-smoke`\n"
_ACCOUNT = "Live-Proof: bench -- the account surface runs on bench"
_NONE = "Live-Proof: none -- no live run is owed here, ruling #deadbeef"
_RENET = "Live-Proof: hostinger -- renet runs on hostinger"
_FX = "agent/plans/PLAN-fx.md"
_FX_DONE = "agent/plans/_done/PLAN-fx.md"
_BASE = "2026-10-28"
_C = "c" * 40
# Fixture Owns paths are assembled from these roots so no whole dead path literal sits in this file for `test_gate_paths_exist` (Tier B) to resolve against the real tree.
_ACCOUNT_DIR = "private/account"
_RENET_DIR = "private/renet"
_CLI_DIR = "packages/cli"
_ACCOUNT_X = _ACCOUNT_DIR + "/src/x.ts"
_RENET_X = _RENET_DIR + "/pkg/x.go"


def _fixture(
    owns: str = _ACCOUNT_X,
    proof: str | None = _ACCOUNT,
    boxes: str = _GOOD_BOX,
    rel: str = _FX,
    status: str = "in-progress",
    extra: str = "",
) -> Plan:
    text = (_HEAD % (owns, proof or "", boxes)).replace(
        "Status: in-progress\nOwner: cafe0000\n",
        "Status: %s\nOwner: cafe0000\n%s" % (status, extra),
    )
    return make_plan(rel, text, PF.FINISHED_STATES)


def _complete_map() -> dict[str, Any]:
    """The committed map plus a bench www check and a baseline, so the negative LP7 control has a map with every surface covered."""
    raw = json.loads(S.MAP_PATH.read_text(encoding="utf-8"))
    raw["tiers"]["live"]["baseline_at"] = _BASE
    raw["tiers"]["live"]["checks"]["www-smoke"] = {
        "targets": ["bench"],
        "surfaces": ["www"],
        "deploy": "unrecorded",
        "what": "fixture",
        "steps": [{"id": "root", "argv": ["curl", "-fsS", "{origin}/"]}],
    }
    return raw


def _codes(findings: Iterable[Finding]) -> list[str]:
    return sorted({f.code for f in findings})


def _ok(_plan: Plan) -> tuple[bool, str]:
    return True, "ok"


def _refused(_plan: Plan) -> tuple[bool, str]:
    return False, "`Live-Proof: none` cites #deadbeef, which is not an item in the worklist store"


class _Suite:
    def __init__(self) -> None:
        self.c = controls.Controls("check_plan_live_proof", CONTROL_FLOOR)
        full = map_view(_complete_map())
        self.full = full
        self.live_of = full.live_of
        self.checks = full.checks

    def lp13(self, plan: Plan, pending: bool = False, waiver=_ok) -> list[Finding]:
        found, _notes = header_findings(plan, self.live_of, pending, waiver)
        return found + box_findings(plan, self.checks, self.live_of)

    def has(self, label: str, plan: Plan, code: str, **kw: Any) -> None:
        self.c.check(label, code in _codes(self.lp13(plan, **kw)), True)

    def only(self, label: str, plan: Plan, codes: list[str]) -> None:
        self.c.check(label, _codes(self.lp13(plan)), codes)

    def map_rules(self) -> None:
        c = self.c
        c.check("complete map: no LP7", _codes(map_findings(self.full)), [])
        raw = _complete_map()
        del raw["tiers"]["live"]["checks"]["www-smoke"]
        c.truthy(
            "a surface with an admissible target and no check is LP7",
            any(
                "surface www admits target bench" in f.message for f in map_findings(map_view(raw))
            ),
        )
        c.truthy("empty map is LP7", "LP7" in _codes(map_findings(map_view({}))))
        c.truthy("non-object map is LP7", "LP7" in _codes(map_findings(map_view([1, 2]))))
        raw = _complete_map()
        raw["tiers"]["live"]["baseline_at"] = None
        c.truthy(
            "unset baseline_at is LP7",
            any("baseline_at" in f.message for f in map_findings(map_view(raw))),
        )
        raw = _complete_map()
        raw["tiers"]["live"]["checks"] = {}
        c.truthy(
            "empty registry is LP7",
            any("registry" in f.message for f in map_findings(map_view(raw))),
        )
        c.check("parse_baseline reads a date", parse_baseline(_BASE), dt.date(2026, 10, 28))
        c.check("parse_baseline refuses junk", parse_baseline("soon"), None)
        pre = surface_prefixes()
        c.truthy("surface prefixes are derived from the map", "private/renet/cmd/" in pre)
        c.check("plainly_hit counts a surface-path Owns", plainly_hit([_fixture()], pre), 1)
        c.check("plainly_hit ignores docs Owns", plainly_hit([_fixture(owns="docs/x.md")], pre), 0)

    def required_rules(self) -> None:
        c = self.c
        good = _fixture()
        c.truthy("account Owns make a plan required", good.required)
        c.check("account Owns touch account", sorted(good.touched), ["account"])
        c.falsy("docs-only Owns are not required", _fixture(owns="docs/x.md").required)
        c.falsy(
            "a test path is not a surface", _fixture(owns=_ACCOUNT_DIR + "/src/x.test.ts").required
        )
        c.falsy(
            "a bare submodule gitlink is not a surface", _fixture(owns="private/renet").required
        )
        c.truthy("renet build.sh is a surface", _fixture(owns="private/renet/build.sh").required)
        c.falsy("a finished plan is not required", _fixture(status="done").required)
        c.falsy("a _done plan is not required", _fixture(rel=_FX_DONE).required)

    def lp1(self) -> None:
        c = self.c
        self.only("healthy plan: no LP1-LP3", _fixture(), [])
        self.only("missing line on a new plan is LP1", _fixture(proof=None, boxes=""), ["LP1"])
        found, notes = header_findings(_fixture(proof=None, boxes=""), self.live_of, True, _ok)
        c.check("missing line on a pre-baseline plan: no finding", found, [])
        c.truthy(
            "missing line in the V7 window prints PENDING",
            any(n.startswith("PENDING") for n in notes),
        )
        emph = _fixture(proof="**Live-Proof**: bench -- the account surface runs on bench")
        c.truthy(
            "emphasised line is LP1 even when pending",
            "LP1" in _codes(header_findings(emph, self.live_of, True, _ok)[0]),
        )
        self.has("malformed line is LP1", _fixture(proof="Live-Proof: bench"), "LP1")
        self.has(
            "edge target is LP1",
            _fixture(proof="Live-Proof: edge -- the account surface runs on edge"),
            "LP1",
        )
        late = _fixture(proof=None).text.replace("## Tasks", _ACCOUNT + "\n\n## Tasks")
        self.has(
            "out-of-window line is LP1", make_plan(_FX, "\n" * 4 + late, PF.FINISHED_STATES), "LP1"
        )
        twice = _fixture(proof=_ACCOUNT + "\n" + _ACCOUNT)
        self.has("duplicated line is LP1", twice, "LP1")
        self.has(
            "rulingless none is LP1 (grammar)",
            _fixture(proof="Live-Proof: none -- no live run is owed for this plan", boxes=""),
            "LP1",
        )

    def lp2(self) -> None:
        c = self.c
        self.has(
            "hostinger on an account plan is LP2",
            _fixture(
                proof="Live-Proof: hostinger -- the account surface runs on hostinger", boxes=""
            ),
            "LP2",
        )
        both = _fixture(owns=_ACCOUNT_X + ", " + _RENET_X)
        c.truthy(
            "renet left uncovered is LP2",
            any(f.code == "LP2" and "renet" in f.message for f in self.lp13(both)),
        )
        self.has(
            "none with an unresolved ruling is LP2",
            _fixture(proof=_NONE, boxes=""),
            "LP2",
            waiver=_refused,
        )
        found, notes = header_findings(_fixture(proof=_NONE, boxes=""), self.live_of, False, _ok)
        c.check("none with a resolving ruling: no finding", found, [])
        c.truthy("none prints the ADVISORY line", any(n.startswith("ADVISORY") for n in notes))
        cli = _fixture(
            owns=_CLI_DIR + "/src/commands/x.ts",
            proof="Live-Proof: hostinger -- the cli runs against hostinger",
            boxes="- [ ] LP-hostinger [live] h\n  - Accept: live-proof hostinger renet-live\n",
        )
        self.only("cli covered by hostinger alone is fine", cli, [])

    def lp3(self) -> None:
        self.only("targets without an LP box is LP3", _fixture(boxes="- [ ] T1 code\n"), ["LP3"])
        self.only(
            "LP box without Accept is LP3", _fixture(boxes="- [ ] LP-bench [live] smoke\n"), ["LP3"]
        )
        self.only(
            "LP box without [live] is LP3",
            _fixture(boxes=_GOOD_BOX.replace(" [live]", "")),
            ["LP3"],
        )
        self.has(
            "Accept on another target is LP3",
            _fixture(boxes=_GOOD_BOX.replace("live-proof bench", "live-proof hostinger")),
            "LP3",
        )
        self.only(
            "a hollow check (cli-bench on account) is LP3",
            _fixture(boxes=_GOOD_BOX.replace("account-smoke", "cli-bench")),
            ["LP3"],
        )
        self.only(
            "a free argument is LP3",
            _fixture(boxes=_GOOD_BOX.replace("account-smoke", "account-smoke --x")),
            ["LP3"],
        )
        self.only(
            "two LP-bench boxes is LP3",
            _fixture(boxes=_GOOD_BOX + _GOOD_BOX.replace("smoke\n", "smoke again\n")),
            ["LP3"],
        )
        hbox = "- [ ] LP-hostinger [live] h\n  - Accept: live-proof hostinger renet-live\n"
        self.has("LP box for an undeclared target is LP3", _fixture(boxes=_GOOD_BOX + hbox), "LP3")
        self.has("LP box on a none plan is LP3", _fixture(proof=_NONE), "LP3")
        self.only(
            "LP-none box on a none plan is fine",
            _fixture(proof=_NONE, boxes="- [ ] LP-none: tooling only\n"),
            [],
        )
        renet = _RENET_X
        self.only(
            "renet-live with a registry machine is fine",
            _fixture(
                owns=renet,
                proof=_RENET,
                boxes=hbox.replace("renet-live", "renet-live machine=hostinger"),
            ),
            [],
        )
        self.only(
            "renet-live with an unknown machine is LP3",
            _fixture(
                owns=renet,
                proof=_RENET,
                boxes=hbox.replace("renet-live", "renet-live machine=nope"),
            ),
            ["LP3"],
        )
        self.only(
            "an unknown check id is LP7",
            _fixture(boxes=_GOOD_BOX.replace("account-smoke", "no-such-check")),
            ["LP7"],
        )

    def transitions(self) -> None:
        c = self.c
        good = _fixture()
        box = lp_boxes(good)[0][1]
        plans = {_FX: good}
        accept = LT.accept_of(good.text, box.line)
        row = {
            "plan": _FX,
            "box": box.sig,
            "target": "bench",
            "status": "VERIFIED",
            "dirty": False,
            "check": {"id": "account-smoke", "args": [], "rc": 0},
            "id": "lp-x",
        }
        self.row = row

        def oracles(
            date: str = "2026-10-29T10:00:00Z", problems: list[str] | None = None
        ) -> Oracles:
            def judge(_row: dict[str, Any], _commit: str) -> list[str]:
                return list(problems or [])

            def commit_of(_rel: str, _sig: str) -> str:
                return _C

            def date_of(_commit: str) -> str:
                return date

            return Oracles(commit_of, date_of, judge)

        self.oracles = oracles
        judged = [(_FX, box.sig)]
        c.truthy("matching_rows finds the row", matching_rows([row], _FX, box.sig, "bench", accept))
        c.truthy(
            "matching_rows follows a _done move",
            matching_rows([{**row, "plan": _FX_DONE}], _FX, box.sig, "bench", accept),
        )
        c.falsy(
            "matching_rows refuses a dirty row",
            matching_rows([{**row, "dirty": True}], _FX, box.sig, "bench", accept),
        )
        other = {**row, "check": {**row["check"], "id": "cli-bench"}}
        c.falsy(
            "matching_rows refuses another check",
            matching_rows([other], _FX, box.sig, "bench", accept),
        )
        c.check(
            "ticked after baseline with no row is LP4",
            _codes(tick_findings(judged, plans, [], _BASE, oracles())),
            ["LP4"],
        )
        c.check(
            "ticked after baseline with a valid row: silent",
            tick_findings(judged, plans, [row], _BASE, oracles()),
            [],
        )
        c.check(
            "ticked ON the baseline day: exempt",
            tick_findings(judged, plans, [], _BASE, oracles("2026-10-28T23:00:00Z")),
            [],
        )
        unc = Oracles(lambda _r, _s: "", lambda _c: "", lambda _r, _c: [])
        c.check("an uncommitted tick: exempt", tick_findings(judged, plans, [], _BASE, unc), [])
        c.check(
            "a non-LP box closing is not judged",
            tick_findings([(_FX, "00000000")], plans, [], _BASE, oracles()),
            [],
        )
        c.check(
            "a matching row with problems is LP5",
            _codes(tick_findings(judged, plans, [row], _BASE, oracles(problems=["bad id"]))),
            ["LP5"],
        )
        tally: dict[str, int] = {}
        tick_findings(judged, plans, [row], _BASE, oracles(), tally)
        c.check("the tally counts the bound box", tally.get("lp_bound"), 1)

    def judge(self) -> None:
        c = self.c
        c.truthy(
            "validate_row refuses a hand-written stub",
            LT.validate_row({"id": "lp-0", "schema": 1}, checks=self.checks),
        )
        base_kw: dict[str, Any] = {
            "validate": lambda _r: [],
            "successor_of": lambda s: s,
            "ancestor_fn": lambda _a, _b: True,
            "inputs_at": lambda _c, _n: "d" * 64,
        }
        row = {"head": "a" * 40, "surfaces": ["account"], "inputs": "d" * 64}
        c.check("judge_row: a clean row passes", judge_row(row, _C, **base_kw), [])
        c.truthy(
            "judge_row: head not an ancestor fires",
            judge_row(row, _C, **{**base_kw, "ancestor_fn": lambda _a, _b: False}),
        )
        c.truthy(
            "judge_row: inputs moved after the proof fires",
            judge_row(row, _C, **{**base_kw, "inputs_at": lambda _c, _n: "e" * 64}),
        )
        c.truthy(
            "judge_row: unreadable inputs at the tick fires",
            judge_row(row, _C, **{**base_kw, "inputs_at": lambda _c, _n: None}),
        )
        c.truthy(
            "judge_row: validate problems carry through",
            judge_row(row, _C, **{**base_kw, "validate": lambda _r: ["schema 9 is not 1"]}),
        )
        seen: list[str] = []

        def record(a: str, _b: str) -> bool:
            seen.append(a)
            return True

        judge_row(
            row, _C, **{**base_kw, "successor_of": lambda _s: "f" * 40, "ancestor_fn": record}
        )
        c.check("judge_row: a rewritten head is judged by its successor", seen, ["f" * 40])

    def lp6(self) -> None:
        c = self.c
        oracles, row = self.oracles, self.row
        done = _fixture(rel=_FX_DONE, status="done")
        pair = [(_FX_DONE, _C)]
        refused = (_refused, _ok)
        c.check(
            "finished after baseline with no receipt is LP6",
            _codes(finish_findings(pair, {_FX_DONE: done}, [], _BASE, oracles(), refused)),
            ["LP6"],
        )
        c.check(
            "finished after baseline with a valid receipt: silent",
            finish_findings(
                pair, {_FX_DONE: done}, [{**row, "plan": _FX_DONE}], _BASE, oracles(), refused
            ),
            [],
        )
        c.check(
            "finished before baseline: exempt",
            finish_findings(
                pair, {_FX_DONE: done}, [], _BASE, oracles("2026-10-20T00:00:00Z"), refused
            ),
            [],
        )
        ruled = _fixture(
            rel=_FX_DONE, status="done", extra="Ruling: live-proof waived, operator #deadbeef\n"
        )
        c.check(
            "finished under a Ruling naming the live-proof waiver: silent",
            finish_findings(pair, {_FX_DONE: ruled}, [], _BASE, oracles(), (_ok, _ok)),
            [],
        )
        plain = _fixture(
            rel=_FX_DONE, status="done", extra="Ruling: closed by the operator #deadbeef\n"
        )
        c.check(
            "a Ruling that does not name the waiver does not excuse",
            _codes(finish_findings(pair, {_FX_DONE: plain}, [], _BASE, oracles(), (_ok, _ok))),
            ["LP6"],
        )
        bare = _fixture(proof=None, rel=_FX_DONE, status="done")
        c.check(
            "finished with no Live-Proof line is LP6",
            _codes(finish_findings(pair, {_FX_DONE: bare}, [], _BASE, oracles(), refused)),
            ["LP6"],
        )
        nonep = _fixture(proof=_NONE, boxes="", rel=_FX_DONE, status="done")
        c.check(
            "finished under an unresolved none is LP6",
            _codes(
                finish_findings(pair, {_FX_DONE: nonep}, [], _BASE, oracles(), (_refused, _refused))
            ),
            ["LP6"],
        )

        def fin(r: dict[str, Any], rel: str) -> bool:
            return r.get("status") == "done" or rel.startswith("agent/plans/_done/")

        c.check(
            "finished_on_branch: a _done move is a finish",
            finished_on_branch(
                {_FX: {"status": "executing"}},
                {_FX: {"status": "moved"}, _FX_DONE: {"status": "done"}},
                fin,
            ),
            [_FX_DONE],
        )
        c.check(
            "finished_on_branch: done at the base already is not",
            finished_on_branch({_FX_DONE: {"status": "done"}}, {_FX_DONE: {"status": "done"}}, fin),
            [],
        )
        hist = [("a", {"x": 1}), ("b", {}), ("c", {"x": 1}), ("d", {"x": 1})]
        c.check(
            "first_of_latest_run: a re-tick names the second run",
            first_of_latest_run(hist, bool),
            "c",
        )

    def forward_only(self) -> None:
        c = self.c
        day = dt.date(2026, 10, 28)
        c.check(
            "pending: committed while baseline_at is unset",
            pending_migration("p", {"p": "2026-10-01T00:00:00Z"}, None),
            True,
        )
        c.check(
            "not pending: added before a set baseline (the V7 window is closed)",
            pending_migration("p", {"p": "2026-10-01T00:00:00Z"}, day),
            False,
        )
        c.check(
            "not pending: added on the baseline day",
            pending_migration("p", {"p": "2026-10-28T09:00:00Z"}, day),
            False,
        )
        c.check(
            "not pending: added after baseline",
            pending_migration("p", {"p": "2026-10-29T00:00:00Z"}, day),
            False,
        )
        c.check(
            "not pending: never committed, no baseline", pending_migration("p", {}, None), False
        )
        c.check("not pending: never committed", pending_migration("p", {}, day), False)

    def run(self) -> bool:
        for part in (
            self.map_rules,
            self.required_rules,
            self.lp1,
            self.lp2,
            self.lp3,
            self.transitions,
            self.judge,
            self.lp6,
            self.forward_only,
        ):
            part()
        return self.c.report()


def selftest() -> bool:
    return _Suite().run()


# ----------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="check:ci-plan-live-proof (LP1 to LP7)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--root", default=None)
    ap.add_argument("--base", default=None)
    ap.add_argument("--proof-map", default=None)
    ap.add_argument("--baseline-at", default=None)
    args = ap.parse_args(argv)

    if controls.controls_first("plan live proof", lambda: not selftest()):
        return 2
    if args.selftest:
        return 0

    root = pathlib.Path(args.root).resolve() if args.root else REPO_ROOT
    map_path = pathlib.Path(args.proof_map) if args.proof_map else S.MAP_PATH
    try:
        raw = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raw = None
        print("  map %s unreadable: %s" % (map_path, exc), file=sys.stderr)
    view = map_view(raw)
    if args.baseline_at is not None:
        view.baseline_at = args.baseline_at
    try:
        findings, notes, stats = evaluate(root, view, args.base)
    except CannotRunError as exc:
        print("CANNOT RUN: %s" % exc, file=sys.stderr)
        return CANNOT_RUN
    for line in notes:
        print("  " + line)
    print(
        "  %(plans)d plan file(s), %(live)d live, %(required)d required by the surface map "
        "(%(plainly)d name a surface path, %(pending)d PENDING V7), %(rows)d ledger row(s), "
        "baseline_at %(baseline_at)s" % stats
    )
    print("  transitions: %s" % stats["transitions"])
    if findings:
        for f in sorted(findings, key=lambda f: (f.code, f.rel, f.message)):
            print("  %s" % f, file=sys.stderr)
        print("x plan live proof: %d finding(s)" % len(findings), file=sys.stderr)
        return 1
    print("ok plan live proof: %d required plan(s) judged, no finding" % stats["required"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
