#!/usr/bin/env python3
"""PR_HEAD_REF must be SET by the invoking step, and must RESOLVE on every trigger.

Two checks, two corpora, two different questions. They are separate because the exemption that is correct for one is wrong for the other, and collapsing them is what let a real bug through green.

CHECK 1 -- every script that PREFERS PR_HEAD_REF is invoked by a step that SETS it.

WHY THIS EXISTS. `check-pr-epic-block.ts`, `check-pr-task-trailers.ts` and `wl_git.py` all already preferred `PR_HEAD_REF` (falling back to `GITHUB_HEAD_REF`, then a bare `git` derivation) before this repo's own workflow steps caught up. The pattern was CORRECT at the reader; the gap was always at the SETTER: a workflow step invoking one of these scripts without a
`PR_HEAD_REF` (or an explicit `GITHUB_HEAD_REF: ${{ github.head_ref }}`) in its
`env:` block. On this repo's `workflow_call` chain, the runner's own default `GITHUB_HEAD_REF` does not reliably materialise, so an unset pair means the script falls all the way to `git branch --show-current`, which is EMPTY on the detached checkout every pull_request run uses -- silently skipping real work (`check-pr-epic-block.ts`) or silently degrading to a coarser check
(`check-review-report-replies.sh`).

THIS RECURRED THREE TIMES IN ONE SESSION (2026-08-28: `891ff49db`, `946e0e6da`, `74114a26b`), each found by hand-sweeping `grep -rn PR_HEAD_REF`. A check-first gate that cannot fail is worth nothing, so this checks BOTH directions with real fixtures below, not merely one reader against one setter.

CHECK 2 -- every setter's EXPRESSION resolves non-empty on every trigger its step can actually run under.

WHY CHECK 1 WAS NOT ENOUGH, and this is a receipt. `f1ce6911f` fixed `claude-review-reusable.yml:139`, which read

    PR_HEAD_REF: ${{ github.event.pull_request.head.ref || github.event.workflow_run.head_branch }}

Two clauses, THREE effective triggers: that file declares `workflow_call` only, its sole caller `claude-review.yml:90` declares `workflow_run`, `pull_request` and `workflow_dispatch`, and the calling job's `if:` (`claude-review.yml:70-88`) admits all three. On the `workflow_dispatch` path both clauses are empty, `.ci/rediacc_ci/review/discover_epics.py:151` refused, and the review
died at its first job. CHECK 1 was green throughout, for two independent reasons:

  1. It never reads the VALUE. `step_sets_var()` is presence-only, so any
     expression -- including the empty string -- satisfies it.
  2. It never reached that step at all. Its corpus is READERS, and `find_readers()`
     drops a reader matching `LOUD_FAILURE`, on the argument that a reader which
     fails LOUD when the variable is unset has already solved the problem. That
     premise is right for CHECK 1's question and WRONG for this one: a loud reader
     has not solved anything, it has converted a silent skip into a guaranteed red
     run. So the `LOUD_FAILURE` exemption stays where it is and is deliberately
     ABSENT here, and CHECK 2 takes a different corpus entirely -- workflow steps
     that SET the variable, enumerated from the workflow files directly, with no
     reader resolution anywhere in the path.

WHAT CHECK 2 PROVES, AND WHAT IT DOES NOT. It proves NON-EMPTINESS, not CORRECTNESS. `github.ref_name` is non-empty on every event, so it makes any expression trivially covered; on a `pull_request` event its value is `<n>/merge`, which is a real ref and the wrong answer to "which branch is this PR". That is acceptable here only because it is always LAST in these chains and an
event-scoped clause wins ahead of it -- and this gate cannot check that ordering. A gate that pretended otherwise would be worse than one that names the hole.

Two more things it deliberately does not do:

  * `with:` INPUTS ARE NOT JUDGED. `claude-review-reusable.yml:76` passes a two-clause
    `ref:` to `actions/checkout` against three effective triggers, and it is
    uncovered on `workflow_dispatch` -- correctly, because an empty `ref:` is
    MEANINGFUL to that action (it falls back to the workflow's own ref, which on that
    dispatch is the right branch). "Resolves empty" is not a defect predicate for an
    action input; deciding it needs per-action input semantics.
  * PR_NUMBER IS EXCLUDED, AND THE NUMBERS BELOW WERE MEASURED, NOT ASSUMED --
    by running this file with `SETTER_VARS = ("PR_NUMBER",)` against the real tree
    on 2026-09-16. 16 setter steps, 4 unmodelled, and:

      WITHOUT E1: 5 findings. Two are the multi-clause sites the exclusion was
      argued from, and both ARE false positives -- `review-status.yml:114`
      (empty on `workflow_run`) and `claude-review-reusable.yml:289` (likewise),
      because `.ci/scripts/review/review-status.sh:148` and
      `.ci/scripts/review/claude-review-gate.sh:782` each `case` on `$EVENT_NAME`
      and resolve the PR from a run id and an artifact on that event instead.
      WITH E1: 2 findings, and they are NOT those two -- E1 silences both, for
      exactly the reason it exists. What is left is `ci-quality.yml:1106` and
      `ci.yml:430`, single-clause `github.event.pull_request.number` setters
      empty on push/schedule/dispatch: the SAME class this gate just fixed for
      PR_HEAD_REF, not noise.

    So the honest statement is narrower than "it would be all noise": the
    generalisation is not unsafe, it is simply a DIFFERENT gate. PR_NUMBER's
    readers do not share PR_HEAD_REF's one property that makes "empty here" a
    sound defect predicate -- every PR_HEAD_REF reader resolves the value the
    SAME way on every event (env, then `GITHUB_HEAD_REF`, then `git branch
    --show-current`: `check-pr-epic-block.ts:134`, `check-pr-task-trailers.ts:439`,
    `review_report_replies.py:392`, `discover_epics.py:149`), whereas PR_NUMBER's
    branch on the event, so judging them means statically reading a shell `case`.
    Adding it is a decision with its own acceptance and its own two live findings
    to fix first; it is deliberately not smuggled in here. The coverage table, the
    `if:` narrower and the caller-chain resolver are separately named functions, so
    doing it later is a name plus an exemption rule rather than a rewrite.

NOT AN EXEMPTION: A WAIVER COMMENT. House rule is never to suppress a gate to get past it. The two honest fixes are a covering clause or a narrowing `if:`, both one line; a marker would only preserve the ambiguity this gate exists to end.

SCOPE. CHECK 1 reads only `.ci/scripts/**` and `scripts/**`, and only files that are not themselves test fixtures (`test-*.sh`, `*.control.ts`, anything under a `test/` or `__tests__/` directory) -- those set the variable to drive a specific scenario, they are not a real CI caller needing a workflow setter. `.claude/hooks/**` is out of scope entirely: those run as local git hooks,
not CI workflow steps, and have no `run:` line to resolve. CHECK 2 reads `.github/workflows/*.yml` and nothing else -- in particular it does NOT use `EXCLUDE_DIR_PARTS`, which once carried `"gates"` and silently blinded CHECK 1 to `scripts/gates/`, both of its own founding motivating cases, from the day it was written.

---- gate ---- step: PR_HEAD_REF completeness emit: false blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails. needs: none lane: quality-code ---- end gate ----
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
PACKAGE_JSON = REPO_ROOT / "package.json"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

SCAN_ROOTS = [".ci/scripts", "scripts"]
# NOT "gates": `scripts/gates/` is where the real registered TS gates live, including this gate's own two founding motivating cases (check-pr-epic-block.ts, check-pr-task-trailers.ts, named in the module docstring above). Excluding it left this gate blind to both since the day it was written -- "test" and "__tests__" already cover the bash-side test fixtures
# (`.ci/scripts/test/gates/*.sh`) that "gates" was presumably meant to protect, without also swallowing the production directory.
EXCLUDE_DIR_PARTS = {"test", "__tests__", "fixtures"}

BASH_PREFERENCE = re.compile(r"\$\{PR_HEAD_REF(?::-|\})")
TS_PREFERENCE = re.compile(r"process\.env\.PR_HEAD_REF")

# A reader that fails LOUD when the variable is unset (rather than silently falling through to git) has already solved the problem itself and does not need a workflow-level setter. Matched as "the reader's own text names both the variable and an explicit refusal", so a real future case is still caught if the loud-failure text ever drifts away from the variable. DELIBERATELY NOT
# APPLIED TO CHECK 2 -- see the module docstring.
LOUD_FAILURE = re.compile(r"PR_HEAD_REF[^\n]{0,80}(unset|refus|is required)", re.IGNORECASE)

# Vacuity floors. Both corpora are enumerated, and an enumerator that finds nothing prints a tick indistinguishable from a clean tree.
MIN_READERS = 2
# SIX setter steps exist today: ci.yml x1 (`:673`), ci-quality.yml x4 (`:538`, `:665`, `:1114`, `:1121`) and claude-review-reusable.yml x1 (`:139`). The floor sits ONE below, not AT, the live count: a floor equal to the corpus turns every legitimate retirement into a red, which is how a floor stops being a vacuity guard and starts being a freeze. `ci-quality.yml:2200` was the
# seventh until its key was deleted as dead, and that retirement is exactly the shape this headroom is for.
MIN_SETTER_STEPS = 5

SETTER_VARS = ("PR_HEAD_REF", "GITHUB_HEAD_REF")


def is_fixture_path(rel: Path) -> bool:
    parts = set(rel.parts)
    if parts & EXCLUDE_DIR_PARTS:
        return True
    return rel.name.startswith("test-") or rel.name.endswith(".control.ts")


def find_readers() -> list[Path]:
    out: list[Path] = []
    for root in SCAN_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in (".sh", ".ts"):
                continue
            rel = path.relative_to(REPO_ROOT)
            if is_fixture_path(rel.relative_to(root)):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if BASH_PREFERENCE.search(text) or TS_PREFERENCE.search(text):
                if LOUD_FAILURE.search(text):
                    continue
                out.append(rel)
    return sorted(set(out))


def npm_script_map() -> dict[str, str]:
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    return dict(data.get("scripts", {}))


def step_invokes(step: dict, reader: Path, npm_map: dict[str, str]) -> bool:
    run = step.get("run")
    if not isinstance(run, str):
        return False
    rel_str = str(reader)
    if rel_str in run:
        return True
    for m in re.finditer(r"npm run ([a-zA-Z0-9:_-]+)", run):
        cmd = npm_map.get(m.group(1), "")
        if rel_str in cmd:
            return True
    return False


def step_sets_var(step: dict) -> bool:
    env = step.get("env")
    if not isinstance(env, dict):
        return False
    return any(var in env for var in SETTER_VARS)


def find_invoking_steps(reader: Path, npm_map: dict[str, str]) -> list[tuple[str, str, str, bool]]:
    """(workflow_file, job_id, step_name, sets_var) for every step invoking reader."""
    hits: list[tuple[str, str, str, bool]] = []
    for wf in sorted(WORKFLOWS_DIR.glob("*.yml")):
        try:
            doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict):
            continue
        jobs = doc.get("jobs") or {}
        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                if step_invokes(step, reader, npm_map):
                    hits.append(
                        (wf.name, job_id, step.get("name", "(unnamed)"), step_sets_var(step))
                    )
    return hits


# --------------------------------------------------------------------------- CHECK 2: expression -> triggers ---------------------------------------------------------------------------

# Events on which each context is populated. The PR family is deliberately wide: `github.event.pull_request` exists on every event whose payload carries a pull request, not only on `pull_request` itself.
PR_PAYLOAD_EVENTS = frozenset(
    {
        "pull_request",
        "pull_request_target",
        "pull_request_review",
        "pull_request_review_comment",
    }
)
# `github.head_ref` / `github.base_ref` are narrower than the payload: the runner populates them only for the two pull-request *trigger* events.
HEAD_REF_EVENTS = frozenset({"pull_request", "pull_request_target"})
ISSUE_PAYLOAD_EVENTS = frozenset({"issue_comment", "issues"})
COMMENT_PAYLOAD_EVENTS = frozenset({"issue_comment", "pull_request_review_comment"})
# Populated on every event, so a clause naming one of these covers everything.
UNIVERSAL_CONTEXTS = frozenset(
    {
        "github.ref_name",
        "github.ref",
        "github.sha",
        "github.repository",
        "github.repository_owner",
        "github.run_id",
        "github.run_number",
        "github.event_name",
        "github.actor",
        "github.workflow",
    }
)

# Three verdicts, and the caller must handle all three: "exact" -> covered on precisely this set of events "all" -> non-empty on every event
#   "unknown" -> not modelled; treated as covering everything, and COUNTED so
# the gate cannot go quiet by failing to understand its corpus
Verdict = tuple[str, set]

EVENT_EQ = re.compile(r"github\.event_name\s*==\s*'([A-Za-z_]+)'")
EVENT_NE = re.compile(r"github\.event_name\s*!=\s*'([A-Za-z_]+)'")
EXPR_GROUP = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
EVENT_NAME_VALUE = re.compile(r"^\$\{\{\s*github\.event_name\s*\}\}$")


def split_top(expr: str, op: str) -> list[str]:
    """Split on `op` at paren depth 0, ignoring occurrences inside quotes."""
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch in "'\"":
            j = i + 1
            while j < len(expr) and expr[j] != ch:
                j += 1
            cur.append(expr[i : j + 1])
            i = j + 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and expr.startswith(op, i):
            parts.append("".join(cur))
            cur = []
            i += len(op)
            continue
        cur.append(ch)
        i += 1
    parts.append("".join(cur))
    return [p.strip() for p in parts]


def strip_parens(expr: str) -> str:
    """Remove redundant outer parentheses, only when they really are a matched pair."""
    out = expr.strip()
    while out.startswith("(") and out.endswith(")"):
        depth = 0
        matched = True
        for k, ch in enumerate(out):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and k != len(out) - 1:
                    matched = False
                    break
        if not matched:
            break
        out = out[1:-1].strip()
    return out


def narrow_by_if(triggers: set[str], condition) -> set[str]:
    """Intersect `triggers` with what an `if:` condition can admit. NEVER widens.

    Sound because `A && github.event_name == 'x'` cannot be true off `x`, whatever
    `A` is. Four conjunct rules, applied to the top-level `&&` conjuncts:

      1. `github.event_name == 'X'`          -> intersect with {X}
      2. `github.event_name != 'X'`          -> remove X
      3. a disjunction in which EVERY disjunct carries a `github.event_name == '...'`
         term -> intersect with the union of those names
      4. anything else                       -> no narrowing

    Real anchors, all verified 2026-09-16:
      * `ci.yml:592` -- `needs.initialize.outputs.is_bot != 'true' &&
        github.event_name == 'pull_request'`. Rule 1 beside an unmodelled `needs.`
        conjunct. WITHOUT THIS THE GATE EMITS A FALSE POSITIVE ON `ci.yml:673`,
        which is already correct.
      * `ci-quality.yml:514` -- same shape; narrows `quality-branch` to
        `{pull_request}` and covers `ci-quality.yml:538`.
      * `claude-review.yml:70-88` -- a three-way disjunction, every disjunct
        carrying an event equality. Rule 3 narrows to `{workflow_run,
        pull_request, workflow_dispatch}`: no loss, which is exactly what made
        the `f1ce6911f` bug reachable.
      * `ci-quality.yml:634` -- `inputs.is_bot != 'true' && (github.event_name ==
        'pull_request' || github.ref == 'refs/heads/main')`. One disjunct is not an
        event test, so rule 3 REFUSES to narrow and rule 4 applies. Handled by
        exemption E1 instead.
    """
    out = set(triggers)
    if not isinstance(condition, str):
        return out
    cond = condition.strip()
    if not cond:
        return out
    if cond.startswith("${{") and cond.endswith("}}"):
        cond = cond[3:-2].strip()

    for conjunct in split_top(cond, "&&"):
        clause = strip_parens(conjunct)
        disjuncts = split_top(clause, "||")
        if len(disjuncts) > 1:
            names: set[str] | None = set()
            for disjunct in disjuncts:
                found = set(EVENT_EQ.findall(strip_parens(disjunct)))
                if not found:
                    names = None
                    break
                names |= found
            if names is not None:
                out &= names
            continue
        m = EVENT_EQ.fullmatch(clause)
        if m:
            out &= {m.group(1)}
            continue
        m = EVENT_NE.fullmatch(clause)
        if m:
            out -= {m.group(1)}
    return out


def has_event_name_env(env) -> bool:
    """Exemption E1: the step hands its reader `github.event_name`.

    A step that passes the event name is telling the script to BRANCH on it, and a script that branches takes a different resolution path on the triggers the expression does not cover -- so static trigger coverage stops being a defect predicate. Every one of these is a real reader that really behaves this way:

      * `ci-quality.yml:536-540` -> `.ci/rediacc_ci/quality/branch.py:219` returns
        early unless `GITHUB_EVENT_NAME == 'pull_request'`.
      * `ci-quality.yml:663-668` passes `GITHUB_EVENT_NAME` beside an
        empty-on-push `github.head_ref`; this is what keeps `:665` silent, since its
        job `if:` (`:634`) does not narrow.
      * `review-status.yml:106` (`EVENT_NAME`) ->
        `.ci/scripts/review/review-status.sh:148` `case "${EVENT_NAME:-}"`, whose
        `workflow_run` arm resolves the PR from `WR_RUN_ID` and an artifact instead.
      * `claude-review-reusable.yml:283` ->
        `.ci/scripts/review/claude-review-gate.sh:782`, the same shape.
    """
    if not isinstance(env, dict):
        return False
    return any(isinstance(v, str) and EVENT_NAME_VALUE.match(v.strip()) for v in env.values())


@dataclass
class SetterStep:
    workflow: str
    job: str
    name: str
    var: str
    value: str
    line: int
    job_if: object = None
    step_if: object = None
    env: dict = field(default_factory=dict)

    @property
    def where(self) -> str:
        return f"{self.workflow}:{self.line}" if self.line else self.workflow


@dataclass
class Finding:
    setter: SetterStep
    missing: list[str]

    def render(self) -> str:
        return (
            f"{self.setter.where} job {self.setter.job!r} step {self.setter.name!r}: "
            f"{self.setter.var} is EMPTY on {', '.join(self.missing)} -- "
            f"{self.setter.value}"
        )


class WorkflowSet:
    """Every workflow in a directory, with trigger resolution across call edges."""

    def __init__(self, directory: Path):
        self.dir = directory
        self.docs: dict[str, dict] = {}
        self.lines: dict[str, list[str]] = {}
        for wf in sorted(directory.glob("*.yml")):
            text = wf.read_text(encoding="utf-8", errors="replace")
            try:
                doc = yaml.safe_load(text)
            except yaml.YAMLError:
                continue
            if not isinstance(doc, dict):
                continue
            self.docs[wf.name] = doc
            self.lines[wf.name] = text.split("\n")

    # -- triggers ----------------------------------------------------------

    def on_block(self, wf_name: str) -> dict:
        """The `on:` mapping.

        PyYAML RESOLVES A BARE `on:` KEY TO THE BOOLEAN `True` (YAML 1.1 y/n/on/off booleans), so `'on' in doc` is False on every workflow in this repo and a naive read finds no triggers at all and silently checks nothing. `check_secret_reachability.py` carries the same workaround and `.ci/rediacc_ci/workflows.py:44-52` documents it as its one deliberate divergence from PyYAML.
        Asserted in `controls()`, not merely remembered.
        """
        doc = self.docs.get(wf_name) or {}
        block = doc.get(True)
        if block is None:
            block = doc.get("on")
        if isinstance(block, dict):
            return block
        if isinstance(block, list):
            return {str(k): None for k in block}
        if isinstance(block, str):
            return {block: None}
        return {}

    def callers(self, wf_name: str) -> list[tuple[str, str, dict]]:
        """(caller_workflow, job_id, job) for every local `uses:` edge into wf_name."""
        target = f"./.github/workflows/{wf_name}"
        out: list[tuple[str, str, dict]] = []
        for name, doc in self.docs.items():
            for job_id, job in (doc.get("jobs") or {}).items():
                if isinstance(job, dict) and job.get("uses") == target:
                    out.append((name, str(job_id), job))
        return sorted(out, key=lambda t: (t[0], t[1]))

    def effective_triggers(self, wf_name: str, _seen: frozenset = frozenset()) -> set[str]:
        """The events this workflow can really run under.

        A `workflow_call`-only file is a CALLEE and has no triggers of its own: its effective set is the union over its local callers of (that caller's own effective set, narrowed by the calling job's `if:`). Verified edges in this tree, depth 2: `ci.yml:506 -> ci-quality.yml`, `claude-review.yml:90 -> claude-review-reusable.yml`. `_seen` is the cycle guard.
        """
        if wf_name in _seen:
            return set()
        keys = set(self.on_block(wf_name).keys())
        out = {k for k in keys if k != "workflow_call"}
        if "workflow_call" in keys:
            seen = _seen | {wf_name}
            for caller_wf, _job_id, job in self.callers(wf_name):
                out |= narrow_by_if(self.effective_triggers(caller_wf, seen), job.get("if"))
        return out

    # -- expressions -------------------------------------------------------

    def input_events(self, wf_name: str, key: str, depth: int) -> Verdict:
        """Events on which `inputs.<key>` is non-empty for this workflow."""
        if depth > 4:
            return ("unknown", set())
        on = self.on_block(wf_name)
        dispatch = on.get("workflow_dispatch")
        if isinstance(dispatch, dict) and key in (dispatch.get("inputs") or {}):
            return ("exact", {"workflow_dispatch"})
        call = on.get("workflow_call")
        spec = (call.get("inputs") or {}).get(key) if isinstance(call, dict) else None
        if spec is None:
            return ("unknown", set())
        if isinstance(spec, dict) and str(spec.get("default", "")) != "":
            return ("all", set())
        callers = self.callers(wf_name)
        if not callers:
            return ("unknown", set())
        total: set[str] = set()
        for caller_wf, _job_id, job in callers:
            with_map = job.get("with") or {}
            if not isinstance(with_map, dict) or key not in with_map:
                return ("unknown", set())
            kind, events = self.value_events(caller_wf, with_map[key], depth + 1)
            if kind == "unknown":
                return ("unknown", set())
            caller_triggers = narrow_by_if(self.effective_triggers(caller_wf), job.get("if"))
            total |= caller_triggers if kind == "all" else (events & caller_triggers)
        return ("exact", total)

    def clause_events(self, wf_name: str, clause: str, depth: int = 0) -> Verdict:
        """Events on which ONE `||` clause of an expression is non-empty."""
        c = strip_parens(clause)
        if not c:
            return ("exact", set())
        if c[0] in "'\"":
            return ("all", set()) if len(c) > 2 else ("exact", set())
        if re.match(r"^[A-Za-z_]+\s*\(", c):
            # `format(...)` and friends: a function call producing a literal-shaped value. Non-empty on every event.
            return ("all", set()) if c.startswith("format") else ("unknown", set())
        if c.startswith("github.event.pull_request."):
            return ("exact", set(PR_PAYLOAD_EVENTS))
        if c.startswith("github.event.workflow_run."):
            return ("exact", {"workflow_run"})
        if c.startswith("github.event.issue."):
            return ("exact", set(ISSUE_PAYLOAD_EVENTS))
        if c.startswith("github.event.comment."):
            return ("exact", set(COMMENT_PAYLOAD_EVENTS))
        if re.fullmatch(r"github\.event\.inputs\.[A-Za-z0-9_-]+", c):
            return ("exact", {"workflow_dispatch"})
        if c in ("github.head_ref", "github.base_ref"):
            return ("exact", set(HEAD_REF_EVENTS))
        if c in UNIVERSAL_CONTEXTS:
            return ("all", set())
        m = re.fullmatch(r"inputs\.([A-Za-z0-9_-]+)", c)
        if m:
            return self.input_events(wf_name, m.group(1), depth)
        # env.*, steps.*, needs.*, secrets.*, vars.*, anything unmodelled.
        return ("unknown", set())

    def value_events(self, wf_name: str, value, depth: int = 0) -> Verdict:
        """Events on which a whole `env:`/`with:` VALUE is non-empty."""
        text = "" if value is None else str(value)
        groups = EXPR_GROUP.findall(text)
        literal = EXPR_GROUP.sub("", text)
        if literal.strip():
            # Literal text outside the expression makes the value non-empty on
            # every event regardless (`PR_BASE_REF: origin/${{ ... }}`).
            return ("all", set())
        if not groups:
            return ("all", set()) if text.strip() else ("exact", set())
        covered: set[str] = set()
        for group in groups:
            for clause in split_top(group.strip(), "||"):
                kind, events = self.clause_events(wf_name, clause, depth)
                if kind == "unknown":
                    return ("unknown", set())
                if kind == "all":
                    return ("all", set())
                covered |= events
        return ("exact", covered)

    # -- the setter corpus -------------------------------------------------

    def _env_line(self, wf_name: str, var: str, value, used: set[int]) -> int:
        """The source line of `var: <value>` in wf_name, or 0.

        PyYAML's `safe_load` discards marks, and a loader subclass that injects them pollutes every mapping it touches -- including the `on:` block this gate reads. A text scan matched in document order is cheaper and cannot change what is parsed.
        """
        want = str(value).strip()
        pattern = re.compile(rf"^\s*{re.escape(var)}:\s*(\S.*?)\s*$")
        for idx, line in enumerate(self.lines.get(wf_name, []), start=1):
            if idx in used:
                continue
            m = pattern.match(line)
            if m and m.group(1).strip("'\"") == want:
                used.add(idx)
                return idx
        return 0

    def setter_steps(self) -> list[SetterStep]:
        """Every (workflow, job, step) whose `env:` carries a setter variable."""
        out: list[SetterStep] = []
        for wf_name in sorted(self.docs):
            used: set[int] = set()
            doc = self.docs[wf_name]
            for job_id, job in (doc.get("jobs") or {}).items():
                if not isinstance(job, dict):
                    continue
                for step in job.get("steps") or []:
                    if not isinstance(step, dict):
                        continue
                    env = step.get("env")
                    if not isinstance(env, dict):
                        continue
                    for var in SETTER_VARS:
                        if var not in env:
                            continue
                        out.append(
                            SetterStep(
                                workflow=wf_name,
                                job=str(job_id),
                                name=str(step.get("name", "(unnamed)")),
                                var=var,
                                value=str(env[var]),
                                line=self._env_line(wf_name, var, env[var], used),
                                job_if=job.get("if"),
                                step_if=step.get("if"),
                                env=env,
                            )
                        )
        return out

    # -- the check ---------------------------------------------------------

    def check_setters(self) -> tuple[list[Finding], int, int]:
        """(findings, unknown_expressions, steps_examined)."""
        findings: list[Finding] = []
        unknown = 0
        setters = self.setter_steps()
        for setter in setters:
            triggers = self.effective_triggers(setter.workflow)
            triggers = narrow_by_if(triggers, setter.job_if)
            triggers = narrow_by_if(triggers, setter.step_if)
            if not triggers:
                continue
            if has_event_name_env(setter.env):  # E1
                continue
            kind, covered = self.value_events(setter.workflow, setter.value)
            if kind == "unknown":
                unknown += 1
                continue
            if kind == "all":
                continue
            missing = sorted(triggers - covered)
            if missing:
                findings.append(Finding(setter=setter, missing=missing))
        return findings, unknown, len(setters)


def fail(msg: str) -> None:
    print(f"{RED}✗ CONTROL FAILED{NC}: {msg}", file=sys.stderr)
    print("  A clean result below would mean nothing, so this gate refuses.", file=sys.stderr)
    sys.exit(1)


# The callee half of `claude-review-reusable.yml` as it stood at `f1ce6911f^`,
# byte-shaped. `{expr}` is the only thing the two directions differ by.
_CALLEE_TMPL = """\
name: Callee
on:
  workflow_call:
    inputs:
      pr_number:
        required: false
        type: string
        default: ''
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - name: Read the published snapshot
        run: bash discover-epics.sh
        env:
          PR_HEAD_REF: ${{{{ {expr} }}}}
"""

_CALLER_YML = """\
name: Caller
on:
  workflow_run:
    workflows: [Console CI]
    types: [completed]
  pull_request:
    types: [ready_for_review]
  workflow_dispatch:
    inputs:
      pr_number:
        required: true
        type: string
jobs:
  review:
    if: >-
      (github.event_name == 'workflow_run' &&
       github.event.workflow_run.conclusion == 'success') ||
      (github.event_name == 'pull_request' &&
       github.event.pull_request.draft == false) ||
      github.event_name == 'workflow_dispatch'
    uses: ./.github/workflows/callee.yml
    with:
      pr_number: ${{ inputs.pr_number || '' }}
"""


def _pair_findings(tmp: Path, expr: str) -> tuple[list[Finding], int]:
    """Build the caller/callee pair with `expr` in the callee's setter, and judge it."""
    (tmp / "callee.yml").write_text(_CALLEE_TMPL.format(expr=expr), encoding="utf-8")
    (tmp / "caller.yml").write_text(_CALLER_YML, encoding="utf-8")
    findings, unknown, _n = WorkflowSet(tmp).check_setters()
    return findings, unknown


def _single_findings(tmp: Path, body: str) -> tuple[list[Finding], int]:
    (tmp / "one.yml").write_text(body, encoding="utf-8")
    findings, unknown, _n = WorkflowSet(tmp).check_setters()
    return findings, unknown


def controls() -> None:
    """Every direction, on synthetic fixtures, before anything real is judged."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        reader = tdp / "fake-reader.sh"
        reader.write_text('branch="${PR_HEAD_REF:-$(git branch --show-current)}"\n')

        missing_wf = tdp / "missing.yml"
        missing_wf.write_text(
            f"jobs:\n  j:\n    steps:\n      - name: runs it\n        run: bash {reader}\n"
        )
        present_wf = tdp / "present.yml"
        present_wf.write_text(
            "jobs:\n"
            "  j:\n"
            "    steps:\n"
            "      - name: runs it\n"
            f"        run: bash {reader}\n"
            "        env:\n"
            "          PR_HEAD_REF: x\n"
        )

        def hits_for(wf_dir: Path) -> list[tuple[str, str, str, bool]]:
            out = []
            for wf in wf_dir.glob("*.yml"):
                doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
                for job in (doc.get("jobs") or {}).values():
                    out.extend(
                        (wf.name, "j", step.get("name"), step_sets_var(step))
                        for step in job.get("steps") or []
                        if step_invokes(step, reader, {})
                    )
            return out

        missing_dir = tdp / "missing_only"
        missing_dir.mkdir()
        (missing_dir / "missing.yml").write_text(missing_wf.read_text())
        got_missing = hits_for(missing_dir)
        if not got_missing or got_missing[0][3] is not False:
            fail("a step invoking the reader WITHOUT PR_HEAD_REF was not detected as missing it")

        present_dir = tdp / "present_only"
        present_dir.mkdir()
        (present_dir / "present.yml").write_text(present_wf.read_text())
        got_present = hits_for(present_dir)
        if not got_present or got_present[0][3] is not True:
            fail("a step invoking the reader WITH PR_HEAD_REF was not detected as satisfying it")

        # The reader-detection regex itself: must fire on the bash form, and a loud-failure reader must be exempt.
        if not BASH_PREFERENCE.search(reader.read_text()):
            fail("the bash preference pattern did not match its own fixture")
        loud = tdp / "loud.sh"
        loud.write_text(
            '[ -n "$PR_HEAD_REF" ] || { echo "PR_HEAD_REF is unset, refusing"; exit 1; }\n'
        )
        if not LOUD_FAILURE.search(loud.read_text()):
            fail("a reader that fails loud on a missing PR_HEAD_REF was not recognised as exempt")

    controls_check2()


def controls_check2() -> None:
    """CHECK 2's own directions. Each exemption route gets a control so none can rot."""

    # -- the planted defect: `f1ce6911f^`, which must FIRE, naming the event ---
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        broken, _unknown = _pair_findings(
            tmp, "github.event.pull_request.head.ref || github.event.workflow_run.head_branch"
        )
        if not broken:
            fail(
                "the pre-f1ce6911f claude-review-reusable.yml shape (two clauses, three "
                "effective triggers) was not reported as empty on workflow_dispatch"
            )
        if broken[0].missing != ["workflow_dispatch"]:
            fail(
                "the planted defect fired with the WRONG reason: expected exactly "
                f"['workflow_dispatch'], got {broken[0].missing!r}. A gate that fires for "
                "the wrong reason sends the next reader to the wrong file."
            )
        if "callee.yml" not in broken[0].render():
            fail("the finding did not name the file it is about")

    # -- the fixed form: `f1ce6911f` as landed, which must stay SILENT --------
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        fixed, unknown = _pair_findings(
            tmp,
            "github.event.pull_request.head.ref || github.event.workflow_run.head_branch "
            "|| github.ref_name",
        )
        if fixed:
            fail(
                "appending `|| github.ref_name` (the f1ce6911f fix) did not silence the "
                f"finding: {[f.render() for f in fixed]}"
            )
        # SILENT FOR THE RIGHT REASON. Found by mutation 2026-09-16: drop `github.ref_name` from UNIVERSAL_CONTEXTS and the clause falls to the UNKNOWN arm, which also silences this fixture -- so the assertion above alone cannot tell "the fix is understood" from "the fix is unreadable", and a later edit could quietly stop modelling the very context the fix is made of. The unknown
        # tally is what separates them.
        if unknown:
            fail(
                "the f1ce6911f fix went silent via the UNKNOWN arm, not because "
                f"`github.ref_name` was recognised as universally non-empty (tally {unknown})"
            )

    # -- silent control 1 (MANDATORY): `if:` narrowing, models ci.yml:592/:673 -
    with tempfile.TemporaryDirectory() as td:
        narrowed = """\
name: N
on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: '0 1 * * *'
  workflow_dispatch:
jobs:
  j:
    if: needs.initialize.outputs.is_bot != 'true' && github.event_name == 'pull_request'
    steps:
      - name: Check unreplied review reports
        run: ./check.py
        env:
          PR_HEAD_REF: ${{ github.event.pull_request.head.ref }}
"""
        found, _ = _single_findings(Path(td), narrowed)
        if found:
            fail(
                "a `pull_request.head.ref`-only setter under an `if:` that narrows to "
                f"pull_request was reported as a finding: {[f.render() for f in found]}. "
                "This is ci.yml:673, which is already correct."
            )

    # -- the narrower's own negative control: it must REFUSE to narrow --------
    with tempfile.TemporaryDirectory() as td:
        not_narrowed = """\
name: N
on:
  push:
    branches: [main]
  pull_request:
jobs:
  j:
    if: inputs.is_bot != 'true' && (github.event_name == 'pull_request' || github.ref == 'refs/heads/main')
    steps:
      - name: Validate submodule branches
        run: ./check.py
        env:
          GITHUB_HEAD_REF: ${{ github.head_ref }}
"""
        found, _ = _single_findings(Path(td), not_narrowed)
        if [f.missing for f in found] != [["push"]]:
            fail(
                "the narrower over-narrowed: a disjunction with ONE non-event disjunct "
                "(ci-quality.yml:634) must not narrow at all, so `github.head_ref` must "
                f"still be reported empty on push. Got {[f.missing for f in found]!r}"
            )

    # -- silent control 2: exemption E1, models ci-quality.yml:663-668 --------
    with tempfile.TemporaryDirectory() as td:
        exempt = """\
name: N
on:
  push:
    branches: [main]
  pull_request:
jobs:
  j:
    if: inputs.is_bot != 'true' && (github.event_name == 'pull_request' || github.ref == 'refs/heads/main')
    steps:
      - name: Validate submodule branches
        run: ./check.py
        env:
          GITHUB_HEAD_REF: ${{ github.head_ref }}
          GITHUB_EVENT_NAME: ${{ github.event_name }}
"""
        found, _ = _single_findings(Path(td), exempt)
        if found:
            fail(
                "E1 did not exempt a step that hands its reader `github.event_name` "
                f"(ci-quality.yml:663-668): {[f.render() for f in found]}"
            )

    # -- silent control 3: all-event-equality disjunction, claude-review.yml:70 -
    with tempfile.TemporaryDirectory() as td:
        disjunction = """\
name: N
on:
  workflow_run:
    workflows: [X]
  pull_request:
  workflow_dispatch:
jobs:
  j:
    if: >-
      (github.event_name == 'workflow_run' && github.event.workflow_run.conclusion == 'success') ||
      (github.event_name == 'pull_request' && github.event.pull_request.draft == false)
    steps:
      - name: Read the published snapshot
        run: ./check.py
        env:
          PR_HEAD_REF: ${{ github.event.pull_request.head.ref || github.event.workflow_run.head_branch }}
"""
        found, _ = _single_findings(Path(td), disjunction)
        if found:
            fail(
                "rule 3 did not narrow a disjunction whose disjuncts are ALL event "
                f"equalities down to exactly the covered set: {[f.render() for f in found]}"
            )

    # -- silent control 4: an UNKNOWN clause is covered AND counted -----------
    with tempfile.TemporaryDirectory() as td:
        unknown_yml = """\
name: N
on:
  push:
    branches: [main]
  pull_request:
jobs:
  j:
    steps:
      - name: Something
        run: ./check.py
        env:
          PR_HEAD_REF: ${{ github.event.pull_request.head.ref || env.SOMETHING }}
"""
        found, unknown = _single_findings(Path(td), unknown_yml)
        if found:
            fail("an expression with an UNKNOWN clause must be treated as covered, not reported")
        if unknown != 1:
            fail(
                f"an UNKNOWN clause must be COUNTED so the gate cannot go quiet by failing "
                f"to understand its corpus; tally was {unknown}, expected 1"
            )

    # -- parser control A: PyYAML's `on:` -> True key, on a REAL workflow -----
    real = WORKFLOWS_DIR / "ci.yml"
    if real.is_file():
        doc = yaml.safe_load(real.read_text(encoding="utf-8"))
        if "on" in doc:
            fail("ci.yml parsed with a literal 'on' key; the True-key workaround is now wrong")
        if not isinstance(doc.get(True), dict):
            fail(
                "PyYAML did not resolve ci.yml's `on:` to the boolean True key. Every "
                "trigger read here depends on it, and a wrong read checks nothing."
            )
        ws = WorkflowSet(WORKFLOWS_DIR)
        if ws.effective_triggers("ci.yml") != {
            "push",
            "pull_request",
            "schedule",
            "workflow_dispatch",
        }:
            fail(
                "ci.yml's own triggers did not resolve to its four declared events; got "
                f"{sorted(ws.effective_triggers('ci.yml'))}"
            )

        # -- parser control B: the caller-chain resolver on the real tree -----
        callers = [c[0] for c in ws.callers("ci-quality.yml")]
        if "ci.yml" not in callers:
            fail(
                "the caller-chain resolver did not find ci.yml as ci-quality.yml's caller "
                f"(got {callers}); every workflow_call-only file would then resolve to no "
                "triggers and be checked vacuously"
            )
        if not ws.effective_triggers("ci-quality.yml"):
            fail("ci-quality.yml, a workflow_call-only file, resolved to NO effective triggers")


def main() -> int:
    controls()

    npm_map = npm_script_map()
    readers = find_readers()
    if len(readers) < MIN_READERS:
        print(
            f"{RED}✗{NC} only {len(readers)} PR_HEAD_REF reader(s) found, floor {MIN_READERS}; "
            "the scan is likely broken, not the repo.",
            file=sys.stderr,
        )
        return 1

    offenders: list[str] = []
    unresolved: list[str] = []
    checked = 0

    for reader in readers:
        steps = find_invoking_steps(reader, npm_map)
        if not steps:
            # Not every reader is invoked from a workflow (e.g. a script only ever run by hand or by another script). Nothing to check.
            unresolved.append(str(reader))
            continue
        checked += 1
        for wf_name, job_id, step_name, sets_var in steps:
            if not sets_var:
                offenders.append(
                    f"{reader}: {wf_name}#{job_id} step {step_name!r} sets neither PR_HEAD_REF nor GITHUB_HEAD_REF"
                )

    workflows = WorkflowSet(WORKFLOWS_DIR)
    findings, unknown, setter_count = workflows.check_setters()
    if setter_count < MIN_SETTER_STEPS:
        print(
            f"{RED}✗{NC} only {setter_count} workflow step(s) set PR_HEAD_REF/GITHUB_HEAD_REF, "
            f"floor {MIN_SETTER_STEPS}; the setter scan is likely broken, not the repo.",
            file=sys.stderr,
        )
        return 1

    for line in offenders:
        print(f"{RED}✗{NC} {line}", file=sys.stderr)
    for finding in findings:
        print(f"{RED}✗{NC} {finding.render()}", file=sys.stderr)

    if offenders or findings:
        if offenders:
            print(
                f"\n{RED}✗{NC} {len(offenders)} step(s) invoke a PR_HEAD_REF-preferring script "
                "without setting it.",
                file=sys.stderr,
            )
        if findings:
            print(
                f"\n{RED}✗{NC} {len(findings)} setter expression(s) resolve to the EMPTY STRING "
                "on a trigger their step really runs under. Add a covering clause (`|| "
                "github.ref_name` was the f1ce6911f fix) or narrow the step with `if: "
                "github.event_name == '...'`.",
                file=sys.stderr,
            )
        return 1

    print(
        f"{GREEN}✓{NC} {checked} PR_HEAD_REF reader(s) all have a setter in every invoking step "
        f"({len(unresolved)} not invoked from any workflow, nothing to check); "
        f"{setter_count} setter step(s) resolve non-empty on every trigger they run under "
        f"({unknown} expression(s) unmodelled and conservatively passed)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
