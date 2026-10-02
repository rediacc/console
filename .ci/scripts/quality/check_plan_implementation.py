#!/usr/bin/env python3
"""check:ci-plan-implementation -- the plan corpus is being DRAINED, and every box this branch closed can be re-derived rather than believed.

WHY THIS EXISTS. The operator's ask, paraphrased because the verbatim wording carries a first-person pronoun the house style keeps out of prose: the repo plans and does not implement, and the stated aim is to eliminate 'planned but not implemented'. Offered three narrower scopes -- per-PR-diff, per-branch, per-plan-adoption -- the answer was ALL. Design:
agent/plans/PLAN-plan-implementation-enforcement.md.

THIS GATE DOES NOT RE-SCAN `agent/`, AND THAT IS THE WHOLE REASON IT CAN BE SMALL. `.ci/config/plan-boxes.json` is already a committed second reading of every checkbox in the corpus, and check:ci-plan-boxes G-A0 already proves it equals the tree. So P-A0 asks that sibling whether the ledger still agrees and REFUSES TO JUDGE if it does not; every assertion after that reads the
ledger. A second parser here would be a second opinion about what a box is, which is exactly what the ledger exists to prevent.

THE ASYMMETRY WITH THE STOP HOOK IS DELIBERATE AND STATED. `wl_planenforce` knows WHO IS RUNNING and adjusts what it demands of that session: boxes owned by a peer this machine reads as live are subtracted, because demanding drainage of work somebody else is doing right now makes the ceiling unreachable by any action. CI has no liveness oracle and must not invent one, so P-A1
compares the WHOLE in-scope count with no ownership term at all. A branch whose peers are all idle owes all of it. What is in scope is the operator's ruling of 2026-10-02 ("Clock the PR's plan only", worklist #508defc2): the live PR's plan (the queue head) and the plans this
branch ticked; plans queued for later PRs are reported as one informational line, never a finding (see clock_scope).

FORWARD-ONLY, AND THE CUT IS ONE COMMITTED DATE. Measured corpus-wide before this was written: 13 `    (ticked) ` evidence lines across all four plan folders, all of them in ONE file, against 589 done boxes. About 2% of the boxes `--plan-tick` was written for went through it; the rest were flipped with the Edit tool and carry nothing to re-check, ever. So P-A2..P-A4 judge a box
only when the commit that ticked it is dated STRICTLY AFTER `baseline_at`, the landing date in `.ci/config/plan-implementation.json`. On the landing commit that set is empty by construction and this gate is silent, which is the point: nobody is punished for a tick that predates the rule, and the very next day's ticks are bound. A control pins both sides of that cut, because a
date comparison that always answers "exempt" is a gate that cannot fail.

CONTROL-FIRST, the shape `.ci/scripts/quality/check_hint_corpus.py` established here. Before the real corpus is judged at all, every assertion below is driven against synthetic inputs carrying one planted defect apiece, plus a healthy fixture that must stay silent under all of them. If any plant is not caught, this gate declares itself broken and exits non-zero WITHOUT judging
the real corpus.

THE GATE SHIPS WITH NO ALLOWLIST, NO SUPPRESSION AND NO BYPASS. docs/agent-reference/suppressions.md governs every escape hatch in this repo, and an allowlist here would be an allowlist against "implement the plan", which is the whole ask. The clock is in config so it can be RETUNED, which is a different thing from exempting a file.

---- gate ----
step: Plan implementation clock
needs: none
selftest: true
lane: quality-branch
---- end gate ----
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any

import _cipath  # noqa: F401
from rediacc_ci import log, paths
from rediacc_ci.controls import plant

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
HOOK_DIR = os.path.join(REPO_ROOT, ".claude", "hooks", "stop")
CONFIG_REL = ".ci/config/plan-implementation.json"
LEDGER_REL = ".ci/config/plan-boxes.json"

#: Anti-vacuity floors. Well under the live numbers (120 plans, 810 raw checkbox lines on 2026-09-22) so an added plan is never a failure, and far enough above zero that an emptied, relocated or mis-globbed corpus reds instead of passing over nothing. Same device check_plan_boxes.py's G-A6 uses, same reason.
MIN_PLANS = 20
MIN_BOXES = 60

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"


def die(msg: str) -> None:
    print(f"{RED}x{NC} {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_modules():
    """The Stop-hook module and the sibling gate, with contract guards on both.

    A MISSING MODULE IS A LOUD FAILURE WITH THE FIX IN THE MESSAGE, never a stack trace that reads as flake and never a pass over an absent subject. The two imports are the entire oracle set of this gate: `wl_planenforce` owns the clock and `check_plan_boxes` owns the ledger-versus-tree comparison, and neither is re-implemented here.
    """
    if not os.path.isdir(HOOK_DIR):
        die(f"{HOOK_DIR} not found; cannot read a clock that is not there")
    paths.on_sys_path(HOOK_DIR)
    try:
        import wl_planenforce as E  # noqa: PLC0415
        import wl_planfile as PF  # noqa: PLC0415
        import wl_planrec as R  # noqa: PLC0415
    except ImportError as exc:
        die(
            f"cannot import the Stop-hook plan modules ({exc}). Refusing to pass while "
            "measuring nothing. They live in .claude/hooks/stop/."
        )
    for name, mod, fns in (
        ("wl_planenforce", E, ("load_clock", "ceiling", "CLOCK_KEYS")),
        ("wl_planrec", R, ("resolve", "read_investigations", "ledger_at", "box_sig")),
        ("wl_planfile", PF, ("FINISHED_STATES",)),
    ):
        for fn in fns:
            if not hasattr(mod, fn):
                die(
                    f"{name}.{fn} is missing (renamed? removed?). The contract this gate reads "
                    "changed; update the gate deliberately rather than letting it pass."
                )
    spec = importlib.util.spec_from_file_location(
        "_cpb", os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_plan_boxes.py")
    )
    if spec is None or spec.loader is None:
        raise ImportError("cannot load module spec")
    boxes_gate = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(boxes_gate)
    except Exception as exc:  # noqa: BLE001
        die(f"cannot load check_plan_boxes.py ({exc}); P-A0 has no oracle to ask")
    for fn in (
        "scan",
        "diff_problems",
        "transition_problems",
        "base_ledger",
        "base_ref",
        "_added_plans",
    ):
        if not hasattr(boxes_gate, fn):
            die(
                f"check_plan_boxes.{fn} is missing. P-A0 and P-A5 both read that gate rather "
                "than duplicating it; fix the wiring deliberately."
            )
    return E, PF, R, boxes_gate


# --------------------------------------------------------------------------- P-A1, the clock. No threshold (2026-09-26), scoped to the PR's plan and the plans this branch ticked (2026-10-02); each piece is a pure function, so the controls drive the same code main() runs.


#: OPERATOR RULING 2026-09-26, TEMPORARY: "Let's define parked status until we make CI green as a temporary status for all other plans since we focus on time budgeting and CI fixes. So, plan-implementation check should give as a warning for now and that status will be removed after we complete all the plans." A plan whose Status is `held` (the ruling's "parked": `parked` already names a compacted record, wl_planrec.STATUS_PARKED, which stays on the clock) leaves the clock and is reported as a warning. P-A7 fails the gate once no plan is parked, so this exemption cannot outlive the ruling: that red is the order to delete PARKED_EXEMPT, parked_scope, P-A7 and the exempt parameter of in_scope.
PARKED_EXEMPT = frozenset({"held"})


def parked_scope(ledger_plans):
    """(n_plans, n_open) of the plans the temporary parked exemption keeps off the clock."""
    n_plans = n_open = 0
    for _rel, row in sorted((ledger_plans or {}).items()):
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").strip().lower() not in PARKED_EXEMPT:
            continue
        open_n = int(row.get("open") or 0)
        if open_n <= 0:
            continue
        n_plans += 1
        n_open += open_n
    return n_plans, n_open


def in_scope(ledger_plans, finished_states, exempt=frozenset()):
    """(n_plans, n_open) for the ledger rows that are IN SCOPE.

    `finished_states` is IMPORTED from `wl_planfile` by the caller rather than restated, exactly as check_plan_boxes.py's G-A3 does it: the Stop hook's scope and this gate's scope are one frozenset read twice, so the two halves cannot drift into disagreeing about which plans count.

    `NOT_STARTED_STATES` IS DELIBERATELY NOT APPLIED. `draft` is this repo's default header on plans under active execution and carries most of the debt; exempting it would leave this gate asserting almost nothing.
    """
    n_plans = n_open = 0
    for _rel, row in sorted((ledger_plans or {}).items()):
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip().lower()
        if status in finished_states or status in exempt:
            continue
        open_n = int(row.get("open") or 0)
        if open_n <= 0:
            continue
        n_plans += 1
        n_open += open_n
    return n_plans, n_open


def clock_findings(offenders):
    """P-A1. [] when no plan on the clock has an open box; one finding naming every plan that has.

    OPERATOR RULING 2026-09-26: "each new plan should be implemented, there should be no threshold to tolerate. Remove that threshold number at plan-implementation check." The descending ceiling (a baseline minus a daily drain) is gone: a plan that is not held and not finished is either fully implemented or red. `offenders` is [(rel, open)].

    OPERATOR RULING 2026-10-02 (worklist #508defc2, "Clock the PR's plan only"): the 2026-09-26 rule above holds unchanged, but only over the plans `clock_scope` puts on the clock, the live PR's plan and the plans this branch ticked. The caller filters `offenders` to that scope before calling here.
    """
    if not offenders:
        return []
    listed = ", ".join("%s (%d)" % (rel, n) for rel, n in offenders)
    return [
        "P-A1 OPEN BOXES: %d plan(s) on this PR's clock (the queue head and the plans this branch ticked) "
        "are neither finished nor held and carry open boxes: %s. There is no threshold (operator ruling "
        "2026-09-26): implement and tick every box, or finish the plan." % (len(offenders), listed)
    ]


#: Where the queue head is read. `rediacc_hooks.plan_gate.queue_head` is the merge gate's own reader of agent/plans/QUEUE.md, so the plan this clock judges is the plan the merge gate judges; a second QUEUE.md parser here could disagree with it.
HOOK_PKG_PARENT = os.path.join(REPO_ROOT, ".claude")


def load_plan_gate():
    """(module, problem). `rediacc_hooks.plan_gate`, or None and the reason it could not be loaded. The caller FAILS CLOSED on a problem: without the queue head there is no way to tell the PR's plan from the queued ones, and judging nothing would read exactly like a finished plan."""
    paths.on_sys_path(HOOK_PKG_PARENT)
    try:
        from rediacc_hooks import plan_gate  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return None, "cannot import rediacc_hooks.plan_gate from %s (%s)" % (HOOK_PKG_PARENT, exc)
    return plan_gate, ""


def pr_event_body(event_path=None):
    """The pull request body from the Actions event payload, or None outside a pull_request run.

    The payload is the event that started THIS run, so a `synchronize` run reads the body as it stood at the push. A body edited later reaches the gate with the next push.
    """
    path = event_path if event_path is not None else os.environ.get("GITHUB_EVENT_PATH", "")
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            event = json.load(fh)
    except (OSError, ValueError):
        return None
    pr = event.get("pull_request") if isinstance(event, dict) else None
    body = pr.get("body") if isinstance(pr, dict) else None
    return body if isinstance(body, str) else None


def pr_admits_open_boxes(gate, body):
    """True when the PR body carries an `Operational-Reason:` line, read by plan_gate's own parser.

    OPERATOR RULING 2026-10-02 (#591 "merges as one PR, with an Operational-Reason line"): the merge gate (`plan_gate.plan_merge_refusal`) admits a PR whose plan still has open boxes when its body says why. Without the same admission here a plan whose last box IS the merge (PLAN-plan-per-pr-loop M7: "merge #591 through the loop") keeps CI red forever, and a red CI is the one thing the merge cannot pass. One parser for both, so the two can never disagree about what counts as a reason.
    """
    if gate is None or not body:
        return False
    check = getattr(gate, "has_operational_reason", None)
    return bool(check(body)) if callable(check) else False


def clock_scope(gate, root, base_plans, head_plans):
    """(scope, notes, problem) for P-A1 under the operator ruling of 2026-10-02 ("Clock the PR's plan only", worklist #508defc2).

    The plan-per-PR loop queues plans in agent/plans/QUEUE.md for FUTURE PRs, so judging every unfinished plan reds CI for ever. The clock is two sets instead:
      (a) the live PR's plan, `gate.queue_head(root)`: the first queued plan that exists, which QUEUE.md's header names as the plan the live branch works;
      (b) every plan in which this branch TICKED a box, read by `moved_to_done` (a sig open at the base and done at head, or a plan new on the branch with a done box).
    `base_plans` None means no base is resolvable, so the scope is (a) only; a queue head of "" makes it (b) only. Both are said in `notes` rather than folded into silence.

    `scope` is {rel: reason}. `problem` is non-empty when the queue head could not be read at all (`gate` None, no `queue_head`, or it raised): the caller fails closed on it.
    """
    notes: list[str] = []
    if gate is None or not callable(getattr(gate, "queue_head", None)):
        return (
            {},
            notes,
            "rediacc_hooks.plan_gate.queue_head is not available, so the PR's plan cannot be told from the queued ones",
        )
    try:
        head = str(gate.queue_head(root) or "").strip()
    except Exception as exc:  # noqa: BLE001
        return {}, notes, "rediacc_hooks.plan_gate.queue_head raised (%s)" % exc
    scope: dict[str, str] = {}
    if head:
        scope[head] = "queue head"
    else:
        notes.append(
            "no queue head (agent/plans/QUEUE.md has no entry that exists), so only plans this branch ticked are on the clock"
        )
    if base_plans is None:
        notes.append(
            "no base is resolvable, so ticks cannot be read and only the queue head is on the clock"
        )
    else:
        for rel, _sig in moved_to_done(base_plans, head_plans):
            scope.setdefault(rel, "ticked on this branch")
    return scope, notes, ""


def split_by_scope(offenders, scope):
    """(on, off): `offenders` split by membership of the P-A1 scope. `off` is reported as one informational line, never a finding."""
    on = [(rel, n) for rel, n in offenders if rel in scope]
    off = [(rel, n) for rel, n in offenders if rel not in scope]
    return on, off


def open_offenders(ledger_plans, finished_states, exempt):
    """[(rel, open)] for every plan that is not finished, not exempt, and has an open box."""
    out = []
    for rel, row in sorted((ledger_plans or {}).items()):
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip().lower()
        if status in finished_states or status in exempt:
            continue
        open_n = int(row.get("open") or 0)
        if open_n > 0:
            out.append((rel, open_n))
    return out


#: The held set is FROZEN at the ruling (operator, 2026-09-26: "we should never allow NEW parked plans"). A plan may leave it (finish it, or restore its old status); none may join. P-A8 reds on a held plan not listed here.
HELD_PLANS = frozenset(
    {
        "agent/plans/PLAN-account-env-to-bws.md",
        "agent/plans/PLAN-agent-tree-lifecycle.md",
        "agent/plans/PLAN-app-wide-org-selection.md",
        "agent/plans/PLAN-biome-only-lint.md",
        "agent/plans/PLAN-chunk-store-browse-toc-and-remote.md",
        "agent/plans/PLAN-ci-watch-enforcement.md",
        "agent/plans/PLAN-commit-as-you-go.md",
        "agent/plans/PLAN-config-handoff-relay-only.md",
        "agent/plans/PLAN-config-networkid-sync.md",
        "agent/plans/PLAN-config-passkey-optional.md",
        "agent/plans/PLAN-config-sync-hardening.md",
        "agent/plans/PLAN-config-team-scoping.md",
        "agent/plans/PLAN-env-to-bitwarden-v2.md",
        "agent/plans/PLAN-haiku-model-routing.md",
        "agent/plans/PLAN-per-commit-review.md",
        "agent/plans/PLAN-plan-dependencies.md",
        "agent/plans/PLAN-plan-priority-concurrency.md",
        "agent/plans/PLAN-rdc-readonly-mode.md",
        "agent/plans/PLAN-repair-prose-style-findings.md",
        "agent/plans/PLAN-retire-bash-oracles.md",
        "agent/plans/PLAN-secret-namespace-migration.md",
        "agent/plans/PLAN-stop-hook-focus-mode.md",
        "agent/plans/PLAN-stop-hook-refactor-enforcement.md",
        "agent/plans/PLAN-stop-hook-retro-20260924.md",
        "agent/plans/PLAN-stop-hook-retro-20260925.md",
        "agent/plans/PLAN-stop-hook-rulings-campaign.md",
        "agent/plans/PLAN-submodule-branch-coordination-guard.md",
        "agent/plans/PLAN-token-ip-rebind.md",
        "agent/plans/PLAN-tooling-transformation.md",
        "agent/plans/PLAN-trap-enforcement.md",
        "agent/plans/PLAN-uncommitted-work-exposure-check.md",
        "agent/plans/PLAN-w7p5a-real-run-dispatch.md",
    }
)


def new_held_findings(ledger_plans):
    """P-A8: a plan with Status `held` that the frozen ruling did not hold."""
    return [
        "P-A8 A NEW HELD PLAN: %s is `held` but was not held at the 2026-09-26 ruling, which froze the set; "
        "implement it instead of holding it." % rel
        for rel, row in sorted((ledger_plans or {}).items())
        if isinstance(row, dict)
        and str(row.get("status") or "").strip().lower() in PARKED_EXEMPT
        and rel not in HELD_PLANS
    ]


# --------------------------------------------------------------------------- FINDING KEYS (agent/plans/PLAN-carried-red-finding-keys.md). Each finding is printed with a `::finding::<key>` line, so a push that carries this gate carries its findings one by one and a NEW finding still refuses.


class Finding(str):
    """A finding message that also carries its key. A `str`, so every control that reads the message (`startswith`, `in`) reads it unchanged."""

    __slots__ = ("key",)
    key: str

    def __new__(cls, message, key):
        obj = super().__new__(cls, message)
        obj.key = _safe_key(key)
        return obj


def _safe_key(key):
    """`key` when it fits the alphabet and the length bound, else `<rule>:<sha256(key)[:12]>`: an over-long plan path must not turn a finding into an exception."""
    if log.FINDING_KEY_RE.match(key):
        return key
    rule = key.split(":", 1)[0] or "key"
    return "%s:%s" % (rule, hashlib.sha256(key.encode("utf-8")).hexdigest()[:12])


def box_key(rule, rel, sig, extra=None):
    """`<rule>:<rel>#<sig>[:<sha256(extra)[:12]>]`. The plan path and the box signature (check_plan_boxes.sig, a hash of the task text) are the finding's identity; neither moves when a commit, a date or a count does. `extra` separates two findings on one box, such as two dead pointers, and is hashed UNMASKED because a pointer's line number is part of which pointer it is."""
    key = "%s:%s#%s" % (rule, rel, sig)
    if extra is not None:
        key += ":" + hashlib.sha256(extra.encode("utf-8")).hexdigest()[:12]
    return key


def key_of(finding):
    """The key a finding is emitted under: its own when it carries one, else `<rule>:<hash of the masked message>` (log.finding_key), where the rule is the message's first word (`P-A1`, `P-A5`, ...)."""
    key = getattr(finding, "key", None)
    if key:
        return key
    rule = str(finding).split(" ", 1)[0].strip(":") or "finding"
    return _safe_key(log.finding_key(rule, str(finding)))


# --------------------------------------------------------------------------- P-A2/P-A3/P-A4, the forward-only proof. Every oracle is injected so the controls drive the same function the real run does.


#: The plan folders a lifecycle move relocates between; a plan's identity is its basename under any of them.
PLAN_FOLDERS = ("agent/plans/", "agent/plans/_done/", "agent/plans/_removed/")


def _plan_identity(rel):
    """The basename for a path under a plan folder, else the path itself (so an unrelated file never pairs)."""
    for folder in sorted(PLAN_FOLDERS, key=len, reverse=True):
        if rel.startswith(folder) and "/" not in rel[len(folder) :]:
            return "plan:" + rel[len(folder) :]
    return rel


def moved_to_done(base_plans, head_plans):
    """[(rel, sig)] for every box this branch CLOSED. Two cases, and the second was a gap.

    A box already done at the base is NEVER judged, and neither is a box that is still open. The set this returns is exactly "what this branch claims to have finished", which is the only set a proof rule can honestly bind.

    THE SECOND CASE IS A PLAN THE BASE NEVER HAD, and leaving it out was a hole measured on this gate's own landing tree: the plan being implemented was itself new on the branch, so all sixteen of its boxes were added AND ticked here, `base_plans` held no row for it at all, and the first version of this function returned ZERO judged boxes while reporting a clean run. A session
    could write a plan, tick every box with no evidence and no investigation row, and P-A2 would see nothing.

    It is NOT a false-positive surface, because the date cut still applies downstream: a plan imported with boxes already ticked has `done_commit` dates at or before `baseline_at` and is exempt for the same reason every other pre-landing tick is. What is caught is the case that matters -- a box ticked on this branch AFTER the rule arrived.

    A FOLDER MOVE IS NOT A NEW PLAN. `check:ci-plan-folders --move` relocates a finished plan into `_done/` (or `_removed/`) and leaves a stub at the old path, so the head row sits at a path the base never had while the base row for the same plan sits beside it. Measured on 0930-1 (3490aa3e3): PLAN-b2-emit-matrix had all 13 boxes ticked on main, and after its move 7 of them read as "closed on this branch" with no evidence, 14 false P-A2 findings. The base row is looked up under every plan folder by basename before the plan is treated as new.
    """
    out: list[Any] = []
    by_name: dict[str, Any] = {}
    for base_rel, base_val in sorted((base_plans or {}).items()):
        if isinstance(base_val, dict):
            by_name.setdefault(_plan_identity(base_rel), base_val)
    for rel, head_row in sorted((head_plans or {}).items()):
        if not isinstance(head_row, dict):
            continue
        base_row = (base_plans or {}).get(rel)
        if not isinstance(base_row, dict):
            base_row = by_name.get(_plan_identity(rel))
        head_done = sorted(set(head_row.get("done_sigs") or []))
        if not isinstance(base_row, dict):
            out.extend((rel, sig) for sig in head_done)
            continue
        was_open = set(base_row.get("open_sigs") or [])
        was_done = set(base_row.get("done_sigs") or [])
        out.extend((rel, sig) for sig in head_done if sig in was_open and sig not in was_done)
    return out


def after_baseline(baseline_at, when):
    """Is a tick dated STRICTLY AFTER the landing date?

    STRICTLY, so the landing day itself is amnesty: `baseline_at` is the day the rule arrives, and a tick made that same day was made under the old rule. An unknown or unparseable date answers False, which exempts rather than accuses -- the forward-only rule has no business ruling on a commit whose date it could not read.
    """
    try:
        base = dt.date.fromisoformat(str(baseline_at or "").strip())
    except ValueError:
        return False
    if not when:
        return False
    try:
        got = dt.date.fromisoformat(str(when).strip()[:10])
    except ValueError:
        return False
    return got > base


def bound_by_the_rule(judged, done_commit_of, date_of, baseline_at):
    """[(rel, sig)] -- the subset of closed boxes the forward-only rule actually BINDS.

    SEPARATE FROM `tick_findings` SO THE SUMMARY CAN PRINT IT. On the landing tree 619 boxes had moved open -> done and NONE of them was bound, because every one predates `baseline_at` or is not committed yet. A success line that reported the 619 and stayed silent about the 0 would read exactly like a proof that ran, which is the vacuity this whole estate keeps paying for. Print
    both numbers and a reader can see the day the second one starts moving.
    """
    return [
        (rel, sig)
        for rel, sig in judged
        if after_baseline(baseline_at, date_of(done_commit_of(rel, sig)))
    ]


def tick_findings(
    judged, evidence_of, row_of, resolve_fn, done_commit_of, date_of, ancestor_fn, baseline_at
):
    """P-A2, P-A3 and P-A4 over one branch's newly-done boxes. [] when they hold.

    P-A2 every judged box carries an `(ticked)` evidence line in the plan AND a
          matching investigation row.
    P-A3 every pointer on that row is RE-RESOLVED IN THE CI CHECKOUT, never
          trusted from the row's own `resolved` field. A row whose pointers
          resolved locally and not here is a finding, and the message says which
          kind failed. `ancestor` is the kind most likely to differ, which is
          exactly why the row's own answer is not read.
    P-A4 `merge-base --is-ancestor <row.head> <the commit that ticked the box>`.
          Clause 1 of the design, enforced where the full topology is available.

    Every oracle is a parameter. That is not abstraction for its own sake: it is what lets the controls drive THIS function -- the one the real run calls -- against planted inputs, rather than a copy of it that could pass while the real one is broken.
    """
    out = []
    for rel, sig in bound_by_the_rule(judged, done_commit_of, date_of, baseline_at):
        commit = done_commit_of(rel, sig)
        if not evidence_of(rel, sig):
            out.append(
                Finding(
                    "P-A2 %s box %s moved open -> done in %s with no `    (ticked) ` evidence line "
                    "beneath it. `worklist.py --plan-tick` writes that line; a box flipped with the "
                    "Edit tool leaves nothing a later reader can check." % (rel, sig, commit[:12]),
                    box_key("P-A2:no-evidence", rel, sig),
                )
            )
        row = row_of(rel, sig)
        if row is None:
            out.append(
                Finding(
                    "P-A2 %s box %s was closed with no row in agent/ledgers/plan-investigation.jsonl. "
                    "The rule is investigate, then implement, then tick -- so that a box already done "
                    "is closed by finding it rather than by doing it again. Record what was looked at:"
                    "\n    worklist.py --plan-investigate <me> %s %s <absent|present|partial> "
                    "<kind>:<token> <kind>:<token> -- <note> --write" % (rel, sig, rel, sig),
                    box_key("P-A2:no-row", rel, sig),
                )
            )
            continue
        for kind, token in row.get("pointers") or []:
            ok, why = resolve_fn(kind, token)
            if not ok:
                out.append(
                    Finding(
                        "P-A3 %s box %s: the investigation row's `%s:%s` pointer does not resolve in "
                        "this checkout -- %s. The row's own `resolved` field is deliberately not "
                        "read; a pointer that resolved on one machine and not here is the finding."
                        % (rel, sig, kind, token, why),
                        box_key("P-A3", rel, sig, "%s:%s" % (kind, token)),
                    )
                )
        head = str(row.get("head") or "").strip()
        if head and commit and not ancestor_fn(head, commit):
            out.append(
                Finding(
                    "P-A4 %s box %s: the investigation recorded HEAD=%s and the commit that ticked "
                    "the box (%s) is not a descendant of it, so the investigation was written after "
                    "the implementation rather than before it."
                    % (rel, sig, head[:12], commit[:12]),
                    box_key("P-A4", rel, sig),
                )
            )
    return out


def vacuity_findings(n_plans_total, n_boxes_total, raw_ledger_rows):
    """P-A6. Zero inputs is a FAILURE, never a pass.

    Three floors, because the three ways this gate could go blind are different: a corpus that shrank below MIN_PLANS, a corpus whose boxes vanished, and a ledger that parsed to nothing at all while the tree plainly holds plans. The success line prints the counts too, so a reader can watch a number collapse instead of reading "OK".
    """
    out = []
    if raw_ledger_rows <= 0:
        out.append(
            "P-A6 VACUOUS: %s parsed to zero plan rows, so every assertion above is true over "
            "nothing, which reads exactly like a healthy corpus." % LEDGER_REL
        )
    if n_plans_total < MIN_PLANS:
        out.append(
            "P-A6 FLOOR: %d plan(s) in the ledger, under MIN_PLANS=%d. An emptied, truncated or "
            "relocated corpus reds instead of passing vacuously." % (n_plans_total, MIN_PLANS)
        )
    if n_boxes_total < MIN_BOXES:
        out.append(
            "P-A6 FLOOR: %d checkbox(es) in the ledger, under MIN_BOXES=%d."
            % (n_boxes_total, MIN_BOXES)
        )
    return out


# --------------------------------------------------------------------------- The controls. Every plant is driven BEFORE the real corpus is judged, and a plant that is not caught makes this gate declare itself broken.


def _clock(base=100, at="2026-01-01", rate=7, slack=20, floor=0):
    return {
        "baseline_open": base,
        "baseline_at": at,
        "drain_per_day": rate,
        "warn_slack": slack,
        "floor_open": floor,
    }


def controls_fired(enforce, planfile, planrec=None):
    """([missed], n_driven). `missed` names every planted defect that was NOT caught.

    THE COUNT IS DERIVED, NEVER A LITERAL. A constant in the success line saying "18 plants" is a claim about this function that nothing checks, and a plant deleted from the middle would leave the constant asserting coverage that is gone. `plant` both records and counts, so the two cannot disagree.
    """
    missed = []
    driven = []

    # NAMED `caught`, NOT `plant`, AND THE NAME IS LOAD-BEARING. `rediacc_ci.controls.plant` is this repo's mutation harness, which raises when a substitution silently does nothing, and `check-control-vacuity` reports any module that defines a local `plant` as one whose plants are unproven -- correctly, because a shadowed name reads as compliance. Nothing here builds a mutant by
    # substitution: every control drives the real judge with injected oracles, so the harness does not apply and borrowing its name would be a claim this file cannot make.
    def caught(label, fired):
        driven.append(label)
        if not fired:
            missed.append(label)

    # CONTROL 0 -- HEALTHY. Every judge must be silent on clean input, or every red below means nothing.
    if clock_findings([]):
        die(
            "CONTROL 0 FAILED: P-A1 reported a finding with no open box anywhere, so every planted result below is meaningless"
        )
    healthy_base = {"p.md": {"status": "draft", "open_sigs": ["aaaaaaaa"], "done_sigs": []}}
    healthy_head = {"p.md": {"status": "draft", "open_sigs": [], "done_sigs": ["aaaaaaaa"]}}
    healthy_row = {
        "plan": "p.md",
        "sig": "aaaaaaaa",
        "head": "H0",
        "verdict": "present",
        "pointers": [["fileline", "x.py:1"], ["commit", "C1"]],
    }
    healthy = tick_findings(
        moved_to_done(healthy_base, healthy_head),
        lambda _r, _s: "ran the gate, exit 0",
        lambda _r, _s: healthy_row,
        lambda _k, _t: (True, "ok"),
        lambda _r, _s: "C1",
        lambda _c: "2026-01-05",
        lambda _a, _b: True,
        "2026-01-01",
    )
    if healthy:
        die(f"CONTROL 0 FAILED: a fully-evidenced tick was reported: {healthy}")
    if vacuity_findings(120, 810, 120):
        die("CONTROL 0 FAILED: a healthy corpus tripped an anti-vacuity floor")

    # C8 -- NO THRESHOLD (operator ruling 2026-09-26). One open box in a plan that is neither finished nor held is red; a held or finished plan's boxes are not.
    rows = {
        "a.md": {"status": "draft", "open": 1},
        "b.md": {"status": "done", "open": 5},
        "c.md": {"status": "held", "open": 9},
    }
    offenders = open_offenders(rows, planfile.FINISHED_STATES, PARKED_EXEMPT)
    caught("C8a: ONE open box in a live plan was not reported", bool(clock_findings(offenders)))
    caught("C8b: a finished or held plan's boxes were counted", offenders == [("a.md", 1)])
    caught(
        "C8c: the finding does not name the plan and its count",
        "a.md (1)" in " ".join(clock_findings(offenders)),
    )
    caught(
        "C8d: a held plan outside the frozen set was not reported (P-A8)",
        bool(new_held_findings({"agent/plans/PLAN-zz-new.md": {"status": "held", "open": 1}})),
    )
    caught(
        "C8e: CONTROL: a plan held at the ruling was reported as new",
        not new_held_findings({min(HELD_PLANS): {"status": "held", "open": 1}}),
    )

    # C12 -- THE PR'S PLAN ONLY (operator ruling 2026-10-02, worklist #508defc2). Each plant is driven through clock_scope + split_by_scope + clock_findings, the path main() takes; the queue head is injected through a stand-in for rediacc_hooks.plan_gate.
    def queue_at(head):
        return type("_Gate", (), {"queue_head": staticmethod(lambda _root: head)})

    def pa1(gate, base, head_rows):
        scope, notes, problem = clock_scope(gate, "/nonexistent", base, head_rows)
        on, off = split_by_scope(
            open_offenders(head_rows, planfile.FINISHED_STATES, PARKED_EXEMPT), scope
        )
        return clock_findings(on), off, notes, problem

    queued = {
        "h.md": {"status": "draft", "open": 2, "open_sigs": ["h1", "h2"], "done_sigs": []},
        "q.md": {"status": "draft", "open": 3, "open_sigs": ["q1", "q2", "q3"], "done_sigs": []},
    }
    got, off, _notes, _problem = pa1(queue_at("h.md"), dict(queued), queued)
    caught(
        "C12a: the queue head plan with an open box was not reported P-A1",
        "h.md (2)" in " ".join(got),
    )
    caught(
        "C12b: a queued non-head plan the branch did not touch was judged; it must sit off the clock",
        "q.md" not in " ".join(got) and off == [("q.md", 3)],
    )
    ticked_base = {
        "t.md": {"status": "draft", "open": 2, "open_sigs": ["t1", "t2"], "done_sigs": []}
    }
    ticked_head = {"t.md": {"status": "draft", "open": 1, "open_sigs": ["t2"], "done_sigs": ["t1"]}}
    got, _off, _notes, _problem = pa1(queue_at("h.md"), ticked_base, ticked_head)
    caught(
        "C12c: a non-head plan where the branch ticked one box and left another open was not reported P-A1",
        "t.md (1)" in " ".join(got),
    )
    finished_head = {
        "h.md": {"status": "draft", "open": 0, "open_sigs": [], "done_sigs": ["h1", "h2"]}
    }
    got, _off, _notes, problem = pa1(
        queue_at("h.md"),
        {"h.md": {"status": "draft", "open": 2, "open_sigs": ["h1", "h2"], "done_sigs": []}},
        finished_head,
    )
    caught("C12d: CONTROL: a fully ticked queue head plan was reported", not got and not problem)
    got, off, notes, problem = pa1(queue_at(""), dict(queued), queued)
    caught(
        "C12e: with no queue head and no ticks, P-A1 either fired or did not say why the clock is empty",
        not got
        and not problem
        and off == [("h.md", 2), ("q.md", 3)]
        and any("no queue head" in n for n in notes),
    )
    caught(
        "C12f: an unloadable plan_gate gave a silent empty scope instead of a diagnostic",
        bool(pa1(None, dict(queued), queued)[3]),
    )

    def raising(_root):
        raise OSError("planted")

    caught(
        "C12g: a queue_head that raised gave a silent empty scope instead of a diagnostic",
        "planted" in pa1(type("_Gate", (), {"queue_head": staticmethod(raising)}), None, queued)[3],
    )
    got, _off, notes, _problem = pa1(queue_at("h.md"), None, ticked_head)
    caught(
        "C12h: with no base, a plan was put on the clock as ticked, or the reduced scope was not said",
        not got and any("no base" in n for n in notes),
    )

    # C13 -- THE OPERATIONAL-REASON ADMISSION (#591): plan_gate's own parser, fed through a real event payload file. A reason admits; a body without one, a reason inside a machine-written block, no payload, and no gate do not.
    real_gate, _gate_problem = load_plan_gate()
    with tempfile.TemporaryDirectory() as tmp:
        event = os.path.join(tmp, "event.json")
        reason_body = (
            "Plan: agent/plans/PLAN-x.md\nOperational-Reason: the plan's last box is this merge\n"
        )
        with open(event, "w", encoding="utf-8") as fh:
            json.dump({"pull_request": {"body": reason_body}}, fh)
        caught(
            "C13a: a PR body with an Operational-Reason line did not admit the open boxes",
            pr_admits_open_boxes(real_gate, pr_event_body(event)),
        )
        with open(event, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "pull_request": {
                        "body": plant(reason_body, "Operational-Reason:", "Operational note:")
                    }
                },
                fh,
            )
        caught(
            "C13b: a PR body without an Operational-Reason line admitted the open boxes",
            not pr_admits_open_boxes(real_gate, pr_event_body(event)),
        )
    caught(
        "C13c: no event payload (a local run, a push or cron event) admitted the open boxes",
        not pr_admits_open_boxes(
            real_gate, pr_event_body(os.path.join("/nonexistent", "event.json"))
        ),
    )
    caught(
        "C13d: an unloadable plan_gate admitted the open boxes",
        not pr_admits_open_boxes(None, reason_body),
    )

    # C1 -- THE INVESTIGATION-LESS TICK, the CI third of it. A box that moved open -> done carrying evidence but NO row must red on P-A2.
    got = tick_findings(
        moved_to_done(healthy_base, healthy_head),
        lambda _r, _s: "exit 0, done, verified",
        lambda _r, _s: None,
        lambda _k, _t: (True, "ok"),
        lambda _r, _s: "C1",
        lambda _c: "2026-01-05",
        lambda _a, _b: True,
        "2026-01-01",
    )
    caught(
        "C1: a tick with no investigation row was not reported P-A2",
        any(f.startswith("P-A2") and "plan-investigation" in f for f in got),
    )

    # C1b -- the same box WITH a row but with no `(ticked)` evidence line in the plan.
    got = tick_findings(
        moved_to_done(healthy_base, healthy_head),
        lambda _r, _s: "",
        lambda _r, _s: healthy_row,
        lambda _k, _t: (True, "ok"),
        lambda _r, _s: "C1",
        lambda _c: "2026-01-05",
        lambda _a, _b: True,
        "2026-01-01",
    )
    caught(
        "C1b: a tick with no evidence line in the plan was not reported P-A2",
        any("no `    (ticked) ` evidence line" in f for f in got),
    )

    # P-A3 -- a pointer that resolved for the author and does NOT resolve here.
    got = tick_findings(
        moved_to_done(healthy_base, healthy_head),
        lambda _r, _s: "ran the gate, exit 0",
        lambda _r, _s: dict(
            healthy_row, resolved=[["fileline", True, "lied"], ["commit", True, "lied"]]
        ),
        lambda k, _t: (k != "commit", "no such commit"),
        lambda _r, _s: "C1",
        lambda _c: "2026-01-05",
        lambda _a, _b: True,
        "2026-01-01",
    )
    caught(
        "P-A3: a pointer that fails to resolve in CI was not reported, or the row's own `resolved` field was trusted",
        any(f.startswith("P-A3") and "commit" in f for f in got),
    )

    # P-A4 / C5 -- the investigation written AFTER the implementation commit.
    got = tick_findings(
        moved_to_done(healthy_base, healthy_head),
        lambda _r, _s: "ran the gate, exit 0",
        lambda _r, _s: healthy_row,
        lambda _k, _t: (True, "ok"),
        lambda _r, _s: "C1",
        lambda _c: "2026-01-05",
        lambda _a, _b: False,
        "2026-01-01",
    )
    caught(
        "P-A4: an investigation row written after the implementation commit was not reported",
        any(f.startswith("P-A4") for f in got),
    )

    # FORWARD-ONLY, BOTH SIDES. A date comparison that always answers "exempt" is a gate that cannot fail, so the cut is pinned in both directions.
    pre = tick_findings(
        moved_to_done(healthy_base, healthy_head),
        lambda _r, _s: "",
        lambda _r, _s: None,
        lambda _k, _t: (True, "ok"),
        lambda _r, _s: "C0",
        lambda _c: "2026-01-01",
        lambda _a, _b: True,
        "2026-01-01",
    )
    caught(
        "FORWARD-ONLY: a box ticked ON the landing date was judged; the landing day is amnesty by design",
        not (pre),
    )
    post = tick_findings(
        moved_to_done(healthy_base, healthy_head),
        lambda _r, _s: "",
        lambda _r, _s: None,
        lambda _k, _t: (True, "ok"),
        lambda _r, _s: "C1",
        lambda _c: "2026-01-02",
        lambda _a, _b: True,
        "2026-01-01",
    )
    caught(
        "FORWARD-ONLY: a box ticked the day AFTER the landing date was NOT judged, so the cut exempts everything",
        post,
    )

    # moved_to_done -- a box already done at the base must never be judged.
    already = moved_to_done(
        {"p.md": {"open_sigs": [], "done_sigs": ["aaaaaaaa"]}},
        {"p.md": {"open_sigs": [], "done_sigs": ["aaaaaaaa"]}},
    )
    caught(
        "a box already done at the merge-base was judged, which is the retroactive demand this design forbids",
        not (already),
    )
    still_open = moved_to_done(
        {"p.md": {"open_sigs": ["aaaaaaaa"], "done_sigs": []}},
        {"p.md": {"open_sigs": ["aaaaaaaa"], "done_sigs": []}},
    )
    # THE PLAN THE BASE NEVER HAD. Measured as a live hole on this gate's own landing tree; see moved_to_done.
    caught(
        "a box on a plan this branch ADDED and ticked was not judged, so a new plan is a way past P-A2",
        moved_to_done({}, {"new.md": {"open_sigs": [], "done_sigs": ["bbbbbbbb"]}})
        == [("new.md", "bbbbbbbb")],
    )
    # A FOLDER MOVE IS NOT A NEW PLAN (3490aa3e3: 14 false P-A2 findings on PLAN-b2-emit-matrix).
    caught(
        "a plan moved into _done/ had its boxes ticked at the base judged as closed on this branch",
        moved_to_done(
            {"agent/plans/PLAN-m.md": {"open_sigs": [], "done_sigs": ["cccccccc"]}},
            {"agent/plans/_done/PLAN-m.md": {"open_sigs": [], "done_sigs": ["cccccccc"]}},
        )
        == [],
    )
    caught(
        "a box open at the base and ticked in the same commit that moved its plan into _done/ was not judged",
        moved_to_done(
            {"agent/plans/PLAN-m.md": {"open_sigs": ["dddddddd"], "done_sigs": []}},
            {"agent/plans/_done/PLAN-m.md": {"open_sigs": [], "done_sigs": ["dddddddd"]}},
        )
        == [("agent/plans/_done/PLAN-m.md", "dddddddd")],
    )
    caught(
        "a plan this branch added with a box still OPEN was judged as closed",
        moved_to_done({}, {"new.md": {"open_sigs": ["bbbbbbbb"], "done_sigs": []}}) == [],
    )
    caught(
        "a box that is still open was judged as though it had been closed",
        not (still_open),
    )

    # THE BOUND SET IS THE NUMBER THE SUMMARY PRINTS, so it is controlled in both directions too.
    caught(
        "bound_by_the_rule bound a box ticked ON the landing date",
        bound_by_the_rule(
            [("p.md", "aaaaaaaa")], lambda _r, _s: "C0", lambda _c: "2026-01-01", "2026-01-01"
        )
        == [],
    )
    caught(
        "bound_by_the_rule did NOT bind a box ticked the day after, so the summary would report zero for ever",
        bound_by_the_rule(
            [("p.md", "aaaaaaaa")], lambda _r, _s: "C1", lambda _c: "2026-01-02", "2026-01-01"
        )
        == [("p.md", "aaaaaaaa")],
    )

    # P-A6 -- anti-vacuity, all three floors.
    caught(
        "P-A6: a ledger parsing to zero rows was not refused",
        any("VACUOUS" in f for f in vacuity_findings(120, 810, 0)),
    )
    caught(
        "P-A6: a corpus under MIN_PLANS was not refused",
        any("MIN_PLANS" in f for f in vacuity_findings(3, 810, 3)),
    )
    caught(
        "P-A6: a corpus under MIN_BOXES was not refused",
        any("MIN_BOXES" in f for f in vacuity_findings(120, 5, 120)),
    )

    # C10 -- THE RECURSIVE CLAUSE. Both halves must read the SAME key names out of the SAME file, so a rename in one cannot leave the other reading a default. Asserted as OBJECT IDENTITY rather than by comparing two literals: a copied tuple would satisfy an equality test and still drift.
    caught(
        "C10: in_scope moved out of this module unexpectedly",
        in_scope.__module__ == __name__,
    )
    caught(
        "C10: this gate does not read wl_planenforce's own CLOCK_KEYS, so a key rename could leave the two halves reading different fields",
        not (CLOCK_KEYS is not enforce.CLOCK_KEYS),
    )
    caught(
        "C10: the two halves name different config files (%s vs %s)"
        % (enforce.CONFIG_REL, CONFIG_REL),
        enforce.CONFIG_REL == CONFIG_REL,
    )
    caught(
        "C10: this gate does not read wl_planfile's own FINISHED_STATES, so the two halves could disagree about which plans are in scope",
        not (FINISHED_STATES is not planfile.FINISHED_STATES),
    )

    # in_scope -- the FINISHED filter must actually filter, and must not filter everything.
    scoped = in_scope(
        {
            "live.md": {"status": "draft", "open": 4},
            "hist.md": {"status": "done", "open": 9},
            "clean.md": {"status": "draft", "open": 0},
        },
        planfile.FINISHED_STATES,
    )
    parked_rows = {
        "live.md": {"status": "draft", "open": 4},
        "held.md": {"status": "held", "open": 7},
    }
    caught(
        "in_scope: a parked plan is still on the clock when exempted",
        in_scope(parked_rows, planfile.FINISHED_STATES, PARKED_EXEMPT) == (1, 4),
    )
    caught(
        "CONTROL: without the exemption a parked plan must stay on the clock",
        in_scope(parked_rows, planfile.FINISHED_STATES) == (2, 11),
    )
    caught(
        "parked_scope did not count the parked plan (wanted (1, 7))",
        parked_scope(parked_rows) == (1, 7),
    )
    caught(
        "in_scope: the FINISHED/zero-box filter returned %r, wanted (1, 4)" % (scoped,),
        scoped == (1, 4),
    )
    # EVIDENCE SLOT: a box with a note line beneath it carries its evidence AFTER the note, where `--plan-tick` writes it, and a box with nothing beneath it carries none.
    if planrec is not None:
        box = "- [x] Planted box for the evidence-slot control"
        sig = planrec.box_sig(re.sub(r"[*_`]+", "", box[6:]).strip())
        tick = "    (ticked) 2026-01-01T00:00:00Z by c0ntr01: ran the gate, exit 0"
        caught(
            "evidence_in_lines missed a (ticked) line written after the box's continuation note",
            evidence_in_lines(planrec, [box, "      a continuation note", tick], sig) != "",
        )
        caught(
            "evidence_in_lines invented an evidence line for a box that has none",
            evidence_in_lines(planrec, [box, "      a continuation note", "", "text"], sig) == "",
        )
    # ABSENT SUBMODULE: a pointer into an unpopulated submodule is skipped, one into a populated path is still resolved, and a non-fileline token under that prefix is never excused.
    if planrec is not None:
        caught(
            "resolve_here failed a fileline into an unpopulated submodule",
            resolve_here(planrec, "fileline", "private/zz-absent/x.sh:1", ["private/zz-absent"])[0],
        )
        caught(
            "resolve_here excused a dead fileline outside every absent submodule",
            not resolve_here(planrec, "fileline", "no/such/file-zz.py:1", ["private/zz-absent"])[0],
        )
    # MOVED PLAN: a row written under the plan's pre-move path must still be found once the plan sits in _done/, and a same-sig row from a DIFFERENT plan must not be.
    moved_rows = [{"plan": "agent/plans/PLAN-m.md", "sig": "bbbbbbbb", "head": "H0"}]
    caught(
        "row_under_any_path did not find the pre-move row for a plan moved into _done/",
        row_under_any_path(moved_rows, "agent/plans/_done/PLAN-m.md", "bbbbbbbb") is moved_rows[0],
    )
    caught(
        "row_under_any_path borrowed a same-sig row from a different plan",
        row_under_any_path(
            [{"plan": "agent/plans/PLAN-other.md", "sig": "bbbbbbbb"}],
            "agent/plans/_done/PLAN-m.md",
            "bbbbbbbb",
        )
        is None,
    )
    # RE-SPELLED CITATIONS (53ae662a4, box V3): a row keyed to the box's pre-rewrite sig still answers for it; a changed TASK does not, and neither does another plan's row.
    v3_old = (
        "V3 Stall removal: `Review Complete` leaves the ruleset's required checks (part of M4's single diff); "
        "pr-merge.md:108 and pr-babysitter.md:16,110 drop the claude-reviewed marker and thread preconditions"
    )
    v3_new = plant(
        plant(v3_old, "pr-merge.md:108", ".claude/commands/pr-merge.md:111"),
        "pr-babysitter.md:16,110",
        ".claude/agents/pr-babysitter.md:16,122",
    )
    v3_rows = [{"plan": "agent/plans/PLAN-v.md", "sig": "7a6762cd", "box": v3_old}]
    caught(
        "a ticked box whose citations were only re-spelled lost its investigation row",
        row_under_any_path(v3_rows, "agent/plans/PLAN-v.md", "4d461643", (), v3_new) is v3_rows[0],
    )
    caught(
        "a row was borrowed for a box whose TASK changed, not just its citation spelling",
        row_under_any_path(
            v3_rows,
            "agent/plans/PLAN-v.md",
            "4d461643",
            (),
            plant(v3_new, "drop the claude-reviewed marker", "keep the claude-reviewed marker"),
        )
        is None,
    )
    caught(
        "a citation-respelled row was borrowed from a different plan",
        row_under_any_path(v3_rows, "agent/plans/PLAN-w.md", "4d461643", (), v3_new) is None,
    )

    # C11 -- FINDING KEYS. The box C1 plants (no investigation row) must be emitted as `::finding::P-A2:no-row:<rel>#<sig>`, through the real emitter; and the SAME finding judged against a different ticking commit, head and date must keep the same key, or a carried finding would read as new every time the tree moved.
    def keyed(commit, head, when):
        base = {"agent/plans/_done/PLAN-k.md": {"open_sigs": ["aaaaaaaa"], "done_sigs": []}}
        head_plans = {"agent/plans/_done/PLAN-k.md": {"open_sigs": [], "done_sigs": ["aaaaaaaa"]}}
        with_row = dict(healthy_row, head=head)
        no_row = tick_findings(
            moved_to_done(base, head_plans),
            lambda _r, _s: "",
            lambda _r, _s: None,
            lambda _k, _t: (True, "ok"),
            lambda _r, _s: commit,
            lambda _c: when,
            lambda _a, _b: True,
            "2026-01-01",
        )
        late = tick_findings(
            moved_to_done(base, head_plans),
            lambda _r, _s: "evidence",
            lambda _r, _s: with_row,
            lambda k, _t: (k != "commit", "no such commit"),
            lambda _r, _s: commit,
            lambda _c: when,
            lambda _a, _b: False,
            "2026-01-01",
        )
        return [key_of(f) for f in no_row + late]

    buf = io.StringIO()
    first = keyed("c0ffee1234567", "abcdef0123456", "2026-01-05")
    for k in first:
        log.emit_finding(k, buf)
    caught(
        "C11: box C1 was not emitted as ::finding::P-A2:no-row:<rel>#<sig>",
        "::finding::P-A2:no-row:agent/plans/_done/PLAN-k.md#aaaaaaaa\n" in buf.getvalue(),
    )
    caught(
        "C11: a missing evidence line was not keyed P-A2:no-evidence:<rel>#<sig>",
        "P-A2:no-evidence:agent/plans/_done/PLAN-k.md#aaaaaaaa" in first,
    )
    caught(
        "C11: P-A3 and P-A4 were not keyed by their box",
        any(k.startswith("P-A3:agent/plans/_done/PLAN-k.md#aaaaaaaa:") for k in first)
        and "P-A4:agent/plans/_done/PLAN-k.md#aaaaaaaa" in first,
    )
    caught(
        "C11: CONTROL: the same findings under a different commit, head and date changed key",
        first == keyed("feedface9876543", "0123456abcdef", "2026-03-09"),
    )
    caught(
        "C11: a message-hashed key moved with a count in its message",
        key_of("P-A6 FLOOR: 3 plan(s) in the ledger")
        == key_of("P-A6 FLOOR: 17 plan(s) in the ledger"),
    )
    caught(
        "C11: CONTROL: two different message-hashed findings shared one key",
        key_of("P-A6 FLOOR: 3 plan(s) in the ledger") != key_of("P-A6 VACUOUS: 3 plan rows"),
    )
    return missed, len(driven)


#: BOUND AT RUN TIME FROM THE STOP-HOOK MODULES, never restated as literals here, and C10 asserts the binding is by IDENTITY rather than by equality. A copied tuple satisfies an equality test and still drifts the day one half is renamed; a shared object cannot.
CLOCK_KEYS = None
FINISHED_STATES = None

#: A FLOOR under the number of plants, not the number itself. The count is derived from `controls_fired` and printed, so a collapse is visible; this catches the other direction, where a plant loop silently stops running and reports a small honest number nobody reads.
MIN_CONTROLS = 15


def main(argv=None) -> int:
    global CLOCK_KEYS, FINISHED_STATES  # noqa: PLW0603 -- see C10: the two halves must share the OBJECT, not a copy

    argv = list(sys.argv[1:] if argv is None else argv)
    selftest_only = "--selftest" in argv or "--selftest-only" in argv

    cfg = os.path.join(REPO_ROOT, CONFIG_REL)
    if not os.path.isfile(cfg):
        print(
            f"{RED}x VACUOUS INPUT{NC}: {CONFIG_REL} does not exist, so there is no clock to "
            "compare against. A missing config makes every assertion true over nothing, which "
            "reads exactly like a drained corpus. Refusing to report a pass.",
            file=sys.stderr,
        )
        return 1
    if not os.path.isfile(os.path.join(REPO_ROOT, LEDGER_REL)):
        print(
            f"{RED}x VACUOUS INPUT{NC}: {LEDGER_REL} does not exist, so the corpus this gate "
            "reads is absent. Refusing to report a pass.",
            file=sys.stderr,
        )
        return 1

    enforce, planfile, planrec, boxes_gate = load_modules()
    CLOCK_KEYS = enforce.CLOCK_KEYS
    FINISHED_STATES = planfile.FINISHED_STATES

    print("plan implementation clock: controls first, then the verdict")
    missed, n_driven = controls_fired(enforce, planfile, planrec)
    if missed:
        print(
            f"{RED}x{NC} CONTROLS DID NOT FIRE, so this gate cannot detect what it exists for; "
            "no verdict is rendered and the real corpus was not judged:",
            file=sys.stderr,
        )
        for m in missed:
            print(f"  {m}", file=sys.stderr)
        # 2, NOT 1, and it is not arbitrary: these gates use 1 for "the tree has a finding" and 2 for "the instrument is broken, so there is no verdict". A caller that collapsed the two would report a defective gate as a defective tree.
        return 2
    if n_driven < MIN_CONTROLS:
        print(
            f"{RED}x{NC} only {n_driven} plant(s) were driven, under MIN_CONTROLS={MIN_CONTROLS}. "
            "A control loop that stopped running reports a small honest number and reads as a "
            "pass; refusing a verdict rather than trusting a shrunken control set.",
            file=sys.stderr,
        )
        return 2
    print(
        f"  {n_driven} planted defect(s) were driven and every one was caught, before anything real was read"
    )
    # `--selftest` STOPS HERE. The controls are the claim that this instrument can fail; the verdict below is a claim about the tree, and a caller that wants only the first must not be made to pay for the second. test-planenforce.py's C10e drives exactly this mode.
    if selftest_only:
        return 0

    clock, problem = enforce.load_clock(REPO_ROOT)
    if problem:
        print(f"{RED}x{NC} {problem}", file=sys.stderr)
        return 1

    with open(os.path.join(REPO_ROOT, LEDGER_REL), encoding="utf-8") as fh:
        head_doc = json.load(fh)
    head_plans = head_doc.get("plans") or {}

    findings = []

    # ---- P-A0: the ledger IS the corpus, and the sibling gate says whether it still agrees with the tree. Refusing here rather than judging is what stops this gate papering over a red sibling.
    scanned = boxes_gate.scan(boxes_gate.ROOT)
    agree_problems = boxes_gate.diff_problems(scanned, head_doc)
    compared = len(scanned)
    if agree_problems:
        print(
            f"{RED}x{NC} P-A0: {LEDGER_REL} disagrees with the tree in "
            f"{len(agree_problems)} place(s), so every count below would be measured against a "
            "stale corpus. check:ci-plan-boxes owns this comparison and reports the remedy; "
            "REFUSING TO JUDGE rather than papering over it:",
            file=sys.stderr,
        )
        for problem_line in agree_problems[:5]:
            print(f"  {problem_line}", file=sys.stderr)
        return 1

    # ---- P-A5: the sibling gate that owns every way a box can DISAPPEAR must still be wired, or 221 boxes could be "drained" with `rm`. The check of the check, which TRAPS.md's check-cannot-fail names as a recursive clause.
    findings.extend(registration_findings(boxes_gate))

    # ---- P-A6 first among the value judgements, so a collapsed corpus cannot satisfy P-A1 by having nothing in it.
    raw_rows = len(head_plans)
    total_boxes = sum(
        int(r.get("open") or 0) + int(r.get("done") or 0)
        for r in head_plans.values()
        if isinstance(r, dict)
    )
    findings.extend(vacuity_findings(raw_rows, total_boxes, raw_rows))

    # The base ledger is read ONCE, here, because P-A1's scope (the plans this branch ticked) and the forward-only proof below both read it.
    base = boxes_gate.base_ref() or ""
    base_plans = None
    skipped_reason = ""
    if not base:
        skipped_reason = "no merge-base is available (not a pull_request checkout)"
    else:
        base_doc, err = boxes_gate.base_ledger(base)
        if err:
            skipped_reason = err
        elif not (base_doc.get("plans") or {}):
            skipped_reason = "the base predates the box ledger"
        else:
            base_plans = base_doc.get("plans") or {}

    # ---- P-A1, scoped to the live PR's plan and the plans this branch ticked (operator ruling 2026-10-02). A plan_gate that cannot be read is a finding, never an empty scope.
    n_plans, n_open = in_scope(head_plans, planfile.FINISHED_STATES, PARKED_EXEMPT)
    gate, gate_problem = load_plan_gate()
    scope, scope_notes, scope_problem = clock_scope(gate, REPO_ROOT, base_plans, head_plans)
    scope_problem = gate_problem or scope_problem
    on_clock, off_clock = split_by_scope(
        open_offenders(head_plans, planfile.FINISHED_STATES, PARKED_EXEMPT), scope
    )
    if scope_problem:
        findings.append(
            "P-A1 NO SCOPE: %s. Refusing to judge nothing: restore .claude/rediacc_hooks/plan_gate.py "
            "(queue_head) or agent/plans/QUEUE.md's reader before this gate can tell the PR's plan "
            "from the queued ones." % scope_problem
        )
    elif on_clock and pr_admits_open_boxes(gate, pr_event_body()):
        print(
            "  INFO: P-A1 admitted by the PR body's `Operational-Reason:` line, the same admission "
            "plan_gate.plan_merge_refusal grants the merge: %s"
            % ", ".join("%s (%d)" % (rel, n) for rel, n in on_clock)
        )
    else:
        findings.extend(clock_findings(on_clock))
    findings.extend(new_held_findings(head_plans))
    parked_plans, parked_open = parked_scope(head_plans)
    if parked_plans == 0:
        findings.append(
            "P-A7 THE PARKED EXEMPTION HAS OUTLIVED ITS RULING: no plan is held any more. The operator's "
            "2026-09-26 ruling made `parked` a temporary warning-only status until the focus plans closed; "
            "remove PARKED_EXEMPT, parked_scope, P-A7 and in_scope's `exempt` parameter from this gate now."
        )

    # ---- P-A2/P-A3/P-A4: the forward-only proof over what this branch actually closed.
    judged = []
    bound = []
    if base_plans is not None:
        judged = moved_to_done(base_plans, head_plans)
        history = planrec.ledger_history(REPO_ROOT)
        rows = planrec.read_investigations(REPO_ROOT)
        bound = bound_by_the_rule(
            judged,
            lambda rel, sig: planrec.done_commit(history, rel, sig),
            lambda commit: planrec._git_out(REPO_ROOT, "log", "-1", "--format=%cI", commit),
            clock.get("baseline_at"),
        )
        findings.extend(
            tick_findings(
                judged,
                lambda rel, sig: _evidence_line(REPO_ROOT, planrec, rel, sig),
                lambda rel, sig: row_under_any_path(
                    rows, rel, sig, follow_names(rel), _box_text(REPO_ROOT, planrec, rel, sig)
                ),
                lambda kind, token: resolve_here(
                    planrec, kind, token, absent_submodules(REPO_ROOT)
                ),
                lambda rel, sig: planrec.done_commit(history, rel, sig),
                lambda commit: planrec._git_out(REPO_ROOT, "log", "-1", "--format=%cI", commit),
                lambda a, b: planrec._git_ok(REPO_ROOT, "merge-base", "--is-ancestor", a, b),
                clock.get("baseline_at"),
            )
        )

    if parked_plans:
        print(
            f"  WARNING: {parked_open} open box(es) in {parked_plans} held plan(s) are off the clock "
            "(operator ruling 2026-09-26, temporary; P-A7 fails once none is held).",
            file=sys.stderr,
        )
    # P-A1's scope, printed on red and green alike so a collapsed scope is visible rather than read as a drained corpus.
    if not scope_problem:
        listed = ", ".join("%s (%s)" % (rel, why) for rel, why in sorted(scope.items())) or "none"
        print(
            f"  P-A1 clock (operator ruling 2026-10-02, the PR's plan only): {len(scope)} plan(s) on the "
            f"clock: {listed}; {sum(n for _r, n in on_clock)} open box(es) among them"
        )
        for note in scope_notes:
            print(f"  P-A1 scope: {note}")
        print(
            f"  INFO: {len(off_clock)} queued plan(s) with {sum(n for _r, n in off_clock)} open box(es) "
            "wait off the clock for their own PR (not a finding)"
        )
    if findings:
        print(f"{RED}x{NC} plan implementation:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        # One `::finding::<key>` line per finding, after the prose, so the push receipt can carry them one by one (PLAN-carried-red-finding-keys).
        sys.stderr.flush()
        for finding in findings:
            log.emit_finding(key_of(finding))
        return 1

    print(
        f"{GREEN}v{NC} plan implementation: no open box on the PR's clock; {n_open} open box(es) across "
        f"{n_plans} unfinished, unheld plan(s) corpus-wide, no threshold"
    )
    print(
        f"  {raw_rows} plan(s) and {total_boxes} checkbox(es) in {LEDGER_REL}, "
        f"{compared} compared against the tree by check:ci-plan-boxes' own comparison"
    )
    if skipped_reason:
        print(f"  forward-only proof SKIPPED, not passed: {skipped_reason}")
    else:
        print(
            f"  {len(judged)} box(es) moved open -> done on this branch, of which {len(bound)} "
            f"were ticked after {clock.get('baseline_at')} and are BOUND by the forward-only "
            "proof (evidence line, investigation row, pointers re-resolved here, ordering)."
        )
        if not bound:
            print(
                "  P-A2/P-A3/P-A4 therefore asserted NOTHING this run, which is the expected "
                "state on and before the landing day and is said out loud rather than folded "
                "into the green above."
            )
    print("  every plant above was caught first, so this green means the check can fail")
    return 0


def pre_move_paths(rel, follow_names=()):
    """Every path the plan at `rel` has had, `rel` first.

    A PLAN THAT CLOSES MOVES, AND ITS INVESTIGATION ROWS DO NOT. `check:ci-plan-folders --move` takes `agent/plans/PLAN-x.md` into `_done/` or `_removed/`, while every row in agent/ledgers/plan-investigation.jsonl keeps the `plan` it was written under. Matching rows by the CURRENT path alone read 78 honestly investigated boxes across nine closed plans as "closed with no row" on 2026-09-24,
    and the remedy it printed (investigate now) is the one P-A4 then refuses, because a row written after the tick records a head the tick cannot descend from. `check_plan_record.attested_under_any_path` answers the same question for the box ledger. The derived pre-move path comes first; `follow_names` (git's own rename walk) covers a plan that moved more than once.
    """
    out = [rel]
    out.extend(rel.replace(seg, "/", 1) for seg in ("/_done/", "/_removed/") if seg in rel)
    out.extend(n for n in follow_names if n not in out)
    return out


#: A cited path's directory prefix and a citation's line suffix (`:12`, `:16,122`, `:353-394`).
CITE_DIR_RE = re.compile(r"(?:[\w.@~-]+/)+([\w.@~-]+\.[A-Za-z0-9]{1,6})")
CITE_LINE_RE = re.compile(r"(\.[A-Za-z0-9]{1,6}):\d+(?:[-,]\d+)*")


def cite_key(text):
    """The box text with every citation reduced to its basename: directory prefixes and line suffixes dropped, markdown emphasis removed, whitespace folded. PURE.

    A box whose citations are only RE-SPELLED is the same task. Measured on 0930-1: 53ae662a4 rewrote `pr-merge.md:108` to `.claude/commands/pr-merge.md:111` inside the ticked box V3, which re-signed it (7a6762cd -> 4d461643). Its investigation row kept the old sig, `--plan-investigate` accepts only open boxes, so no verb could ever re-key it and P-A2 named it "closed with no row" for good.
    """
    t = re.sub(r"[*_`]+", "", str(text or ""))
    t = CITE_LINE_RE.sub(r"\1", CITE_DIR_RE.sub(r"\1", t))
    return " ".join(t.split()).lower()


def row_under_any_path(rows, rel, sig, follow_names=(), box_text=""):
    """The LATEST investigation row for box `sig` under any path the plan has had, or None.

    LATEST across all of them, for the reason `wl_planrec.investigation_for` gives for taking the latest: an earlier row must not outrank a later one. The sig must match exactly, so a different plan's box can never be borrowed.

    THE ONE FALLBACK: with no exact-sig row, a row of the SAME plan whose recorded box text equals this box's text up to citation spelling (`cite_key`) answers for it. Rows record the first 200 characters of the box, so the comparison is over the shorter of the two keys' common prefix length, never less than 80 characters.
    """
    paths = set(pre_move_paths(rel, follow_names))
    hits = [r for r in rows if r.get("sig") == sig and r.get("plan") in paths]
    if hits or not box_text:
        return hits[-1] if hits else None
    want = cite_key(box_text)
    loose = []
    for r in rows:
        if r.get("plan") not in paths:
            continue
        got = cite_key(r.get("box") or "")
        n = min(len(got), len(want))
        if n >= 80 and got[:n] == want[:n]:
            loose.append(r)
    return loose[-1] if loose else None


_FOLLOW: dict[str, tuple[str, ...]] = {}


def follow_names(rel):
    """`git log --follow` names of `rel`, walked once per path."""
    if rel not in _FOLLOW:
        # A git failure ends the run instead of reading as "no pre-move paths", the same blindness check_plan_record.follow_walk closes; three tries absorb a transient lazy fetch on CI's blob:none clone.
        for _ in range(3):
            r = subprocess.run(
                [
                    "git",
                    "-C",
                    str(REPO_ROOT),
                    "log",
                    "--follow",
                    "--name-only",
                    "--format=",
                    "--",
                    rel,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if r.returncode == 0:
                break
        if r.returncode != 0:
            print(
                "CANNOT SEE: `git log --follow -- %s` exited %d: %s"
                % (rel, r.returncode, r.stderr.strip() or "(no stderr)"),
                file=sys.stderr,
            )
            sys.exit(1)
        out = r.stdout.strip()
        _FOLLOW[rel] = tuple(sorted({ln.strip() for ln in out.splitlines() if ln.strip()} - {rel}))
    return _FOLLOW[rel]


def absent_submodules(root):
    """Declared submodule paths whose working tree is NOT populated in this checkout.

    `quality-branch` checks out with no `submodules:` key, so in CI `private/renet/**` is an empty directory, and on run 36016859754 a correct `fileline:private/renet/.ci/ci.sh:26` pointer read as P-A3 "does not resolve". check_plan_citations.absent_submodules answers the same question for the citation gate and gives the reasoning in full: the filter lives in the CALLER, and the shared resolver keeps failing closed, because a session that DOES have the submodule checked out must still be refused.
    """
    out: list[str] = []
    manifest = os.path.join(root, ".gitmodules")
    if not os.path.isfile(manifest):
        return out
    import subprocess  # noqa: PLC0415 -- used only here

    listing = subprocess.run(
        ["git", "config", "-f", manifest, "--get-regexp", r"\.path$"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        path = os.path.join(root, parts[1])
        # Populated means "has content": an uninitialised submodule is an empty directory, not a missing one.
        if not os.path.isdir(path) or not os.listdir(path):
            out.append(parts[1])
    return sorted(out)


def resolve_here(planrec, kind, token, absent):
    """(ok, why) for one investigation pointer. A `fileline` into a submodule this checkout did not populate is SKIPPED, never failed: it is a pointer this lane chose not to fetch, not a dead one. Every other pointer goes to the shared resolver unchanged."""
    if kind == "fileline" and any(token.startswith(sub + "/") for sub in absent):
        return True, "skipped: %s is not populated in this checkout" % token.split(":", 1)[0]
    return planrec.resolve(REPO_ROOT, kind, token)


def registration_findings(boxes_gate):
    """P-A5. The sibling gate that owns box DISAPPEARANCE must still be reachable.

    NOT A RE-IMPLEMENTATION of G-A1/G-A4/G-A5. This asserts they are still REGISTERED, so that unwiring check:ci-plan-boxes reds here instead of quietly turning `rm` into a way to drain 221 boxes. TRAPS.md's check-cannot-fail states the recursive clause this obeys: the check, and the check of the check.
    """
    out = []
    try:
        import wl_planrec as planrec  # noqa: PLC0415
        import wl_reggate as reggate  # noqa: PLC0415
    except ImportError as exc:
        return ["P-A5: cannot import the reachability oracle (%s)" % exc]
    scripts = planrec._package_scripts(REPO_ROOT)
    for key in ("check:ci-plan-boxes", "check:ci-plan-implementation"):
        if key not in scripts:
            out.append(
                "P-A5 %s is not a key in package.json. This gate reads the ledger that gate "
                "maintains; unwired, `rm` on a plan file becomes a way to drain the clock." % key
            )
        elif not reggate.gate_reachable(scripts, key, REPO_ROOT):
            out.append(
                "P-A5 %s exists in package.json but is NOT reachable from `npm run ci`, so it "
                "is a gate nothing runs." % key
            )
    if not hasattr(boxes_gate, "_added_plans"):
        out.append(
            "P-A5 check_plan_boxes._added_plans is gone, so G-A4 (new debt must name an Owner) cannot be running"
        )
    return out


def _box_text(root, planrec, rel, sig):
    """The text of the ticked box `sig` in the plan at `rel`, or ""."""
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return ""
    for raw in lines:
        m = planrec.BOX_LINE_RE.match(raw)
        if m and planrec.box_sig(re.sub(r"[*_`]+", "", m.group(2)).strip()) == sig:
            return m.group(2)
    return ""


def _evidence_line(root, planrec, rel, sig):
    """The `    (ticked) ` line beneath the box `sig` names, or "".

    READ FROM THE PLAN'S OWN TEXT, matched by SIGNATURE rather than by position in a list, so a plan that grew a paragraph above the box still answers correctly.
    """
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return ""
    return evidence_in_lines(planrec, lines, sig)


def evidence_in_lines(planrec, lines, sig):
    """The evidence line for box `sig` in `lines`, or "". PURE, so the controls drive it directly.

    THE SLOT IS THE VERB'S OWN, `wl_planrec._evidence_slot`: after the box AND its continuation lines. This read `lines[i + 1]` while `--plan-tick` had moved to inserting after the continuation (the 2026-09-24 fix for a wrapped box being split from its own second line), so every box with a note beneath it read as carrying no evidence line even when the verb had
    just written one. Reading the same slot the writer uses is what keeps the two from drifting again.
    """
    for i, raw in enumerate(lines):
        m = planrec.BOX_LINE_RE.match(raw)
        if not m or m.group(1).lower() != "x":
            continue
        body = re.sub(r"[*_`]+", "", m.group(2)).strip()
        if planrec.box_sig(body) != sig:
            continue
        j = planrec._evidence_slot(lines, i)
        if j < len(lines) and planrec.TICK_LINE_RE.match(lines[j]):
            return lines[j].strip()
        return ""
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
