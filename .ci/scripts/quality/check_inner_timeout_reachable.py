#!/usr/bin/env python3
"""An in-script kill timer above its own job's ceiling is dead code in CI.

WHY THIS EXISTS, and it is a defect this repository actually shipped for a few hours on 2026-09-08. `check:ci-pytest` carries its own `RUN_TIMEOUT_S`, raised to 3600s so a long suite would be KILLED with a named cause rather than crash. It runs as the `Python package tests` step of `quality-security` in `ci-quality.yml`, and that job declares `timeout-minutes: 20`. 3600 > 1200, so
the timer could never fire: GitHub cancels the job at twenty minutes, and a cancelled job's only clue is

    The operation was canceled.

No verdict, no KILLED line, no cause -- exactly the chain `check_job_timeout_headroom.py` documents, one level down. Seven gates were green over that raise. They could not see it: the number is legal Python, the suite passes locally where no ceiling applies, and nothing compared the two.

WHY THE HEADROOM GATE DOES NOT COVER IT. `check:ci-timeout-headroom` asks whether a JOB's declared `timeout-minutes` clears its OBSERVED worst case. That is the outer dimension and a different question, and its baseline names two jobs (`Validate Promotion`, `Stage Artifacts`), both in `ci.yml`. It never reads a script, so an in-script timer is invisible to it in every workflow.

WHAT THIS ASSERTS. For every registered gate that declares a `*_TIMEOUT_S` constant and runs as a CI step, that timer must be STRICTLY BELOW its job's `timeout-minutes`. Equal is a finding too: a timer that fires at the same instant the job dies is a race, not a diagnostic.

THE SECOND DOOR: MODULES A WORKFLOW STEP RUNS. Reading only registered gates left every other Python module a step runs invisible, and the same defect shipped through that door. `rediacc_ci.testrun.install_methods` held `CONTAINER_TIMEOUT = 1800` while `Validate Promotion` runs it under `timeout-minutes: 20`; on 2026-10-06 (run 37437282770) a silent `dnf install` outlived the job and the log held nothing. The name carries no `_S`, the module is not a gate, and this gate passed over it. So the scan now also walks every `run:` block of every workflow under `.github/workflows` (and of any local composite action a step `uses:`), resolves `python3 -m rediacc_ci.<x>` and every `<path>.py` the block names, and compares that module's timeout constants against the STEP's `timeout-minutes` when it declares one, else its job's.

A timeout constant is any module-level name ending in `TIMEOUT`, optionally followed by a unit: `_S`/`_SEC`/`_SECS`/`_SECONDS`, `_MS`/`_MILLIS`, `_MIN`/`_MINS`/`_MINUTES`. A bare `*_TIMEOUT` counts as seconds, the unit of every Python timeout parameter; the one module that means milliseconds by it is declared in `DECLARED_UNITS`, by name and with its reason, and printed on every run. The value is read with `ast`, so `15 * 60` is 900 and not 15, an env-default `int(os.environ.get("X") or 600)` is its default, and a string default `"120"` is 120. A timer whose value cannot be folded statically is a finding, never a pass: unknown is unchecked.

WHAT IT DOES NOT ASSERT. Not that the number is big enough -- that is a measurement, and it belongs with the suite that measures. Only that the smaller of the two guards is the one that can actually speak. Nor does it follow a module's imports: a timer declared in a helper the step module imports is out of reach, and so is a module started from a shell script or an npm script that is not a registered gate.

---- gate ----
step: Inner kill timers are reachable
needs: none
selftest: true
lane: quality-code
why: A gate's own kill timer must sit below its job's timeout-minutes, or CI
     cancels the job first and the gate's diagnostic never prints -- the failure
     shape reads as an unexplained cancel rather than as a named verdict.
---- end gate ----
"""

import ast
import dataclasses
import json
import math
import pathlib
import re
import sys
from collections.abc import Callable, Sequence

import _cipath  # noqa: F401
from rediacc_ci.controls import Controls, plant
from rediacc_ci.quality.gh_retry_shell import run_blocks

LOCK_REL = "scripts/ci-runner/gates.lock.json"
WORKFLOWS_REL = ".github/workflows"

# A module-level constant naming seconds, for a NON-Python leaf (a shell gate's `RUN_TIMEOUT_S=900`). Anchored at column 0 so a timer discussed in a comment or held in a string fixture is not mistaken for one that is declared -- the same trap `check_pytest.py`'s corpus counter fell into. Python sources are read with `ast` instead.
TIMER_RE = re.compile(r"^([A-Z][A-Z0-9_]*_TIMEOUT_S)\s*=.*?(\d{2,})", re.MULTILINE)

# `CONTAINER_TIMEOUT`, `RUN_TIMEOUT_S`, `TIMEOUT_SECONDS`, `DEFAULT_TIMEOUT_SECS`, `_TIMEOUT`. Not `TIMEOUT_RETRIES` or `MAX_TIMEOUT_COUNT`: the word has to END the name, a unit suffix aside.
TIMER_NAME_RE = re.compile(
    r"^_?(?:[A-Z][A-Z0-9_]*_)?TIMEOUT"
    r"(?:_(?P<unit>S|SEC|SECS|SECONDS|MS|MILLIS|MIN|MINS|MINUTES))?$"
)
UNIT_SECONDS = {
    "S": 1.0,
    "SEC": 1.0,
    "SECS": 1.0,
    "SECONDS": 1.0,
    "MS": 0.001,
    "MILLIS": 0.001,
    "MIN": 60.0,
    "MINS": 60.0,
    "MINUTES": 60.0,
}

# A bare `*_TIMEOUT` is seconds unless declared here. Each entry is a UNIT declaration, not an exemption: the timer is still converted and still compared. An entry that no longer matches a scanned constant is reported as stale, so this table cannot outlive the code it describes.
DECLARED_UNITS: dict[tuple[str, str], tuple[str, str]] = {
    (".ci/rediacc_ci/env/create_e2e_env.py", "DEFAULT_TIMEOUT"): (
        "MS",
        (
            "the twin's BRIDGE_TIMEOUT default, read by packages/e2e-tests "
            "BridgeTestRunner.ts as milliseconds"
        ),
    ),
}

# A step that runs a second checkout of this repository names its scripts under that checkout's path. The working tree's copy is the stand-in.
CHECKOUT_ALIASES = (".review-scripts/",)

MODULE_RE = re.compile(r"-m\s+(rediacc_ci(?:\.[A-Za-z_][A-Za-z0-9_]*)+)")
SCRIPT_RE = re.compile(r"[\w./-]+\.py\b")
USES_LOCAL_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*['\"]?(\./[^\s'\"#]+)", re.MULTILINE)


def job_ceilings(workflow_text: str) -> dict[str, int]:
    """`{job id: timeout-minutes}` for one workflow.

    Read with a line scanner rather than a YAML parser on purpose: this gate must run with no third-party import, and the two shapes it needs -- a job key at two spaces, its `timeout-minutes` at four -- are pinned by the repo's own workflow lint. A job with no declared ceiling is simply absent, which the caller reports rather than treats as infinity. A trailing comment is allowed: `timeout-minutes: 20 # budget cap` is how `ci.yml` spells the ceiling of `Validate Promotion`, and an end-anchored pattern read that job as having none.
    """
    out: dict[str, int] = {}
    current = None
    for line in workflow_text.splitlines():
        key = re.match(r"^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$", line)
        if key:
            current = key.group(1)
        cap = re.match(r"^    timeout-minutes:\s*(\d+)\s*(?:#.*)?$", line)
        if cap and current:
            out[current] = int(cap.group(1))
    return out


# ---------------------------------------------------------------------------
# Reading the timers.
# ---------------------------------------------------------------------------


class _NotADuration:
    """A value that is plainly not a number of anything: a regex, a word, a table."""


NOT_A_DURATION = _NotADuration()
_ENV_GETTERS = {"os.environ.get", "environ.get", "os.getenv", "getenv"}
_CASTS = {"int", "float", "str", "round", "abs"}


def _fold(node: ast.expr, env: dict[str, float]) -> "float | _NotADuration | None":
    """The number `node` evaluates to with the environment unset, or None when that cannot be known statically."""
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or value is None:
            return NOT_A_DURATION
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return float(value) if re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", value) else NOT_A_DURATION
        return NOT_A_DURATION
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _fold(node.operand, env)
        return -inner if isinstance(inner, float) else inner
    if isinstance(node, ast.BinOp):
        left, right = _fold(node.left, env), _fold(node.right, env)
        if isinstance(left, float) and isinstance(right, float):
            ops: dict[type, Callable[[float, float], float]] = {
                ast.Add: lambda a, b: a + b,
                ast.Sub: lambda a, b: a - b,
                ast.Mult: lambda a, b: a * b,
                ast.Div: lambda a, b: a / b if b else math.inf,
                ast.FloorDiv: lambda a, b: a // b if b else math.inf,
            }
            op = ops.get(type(node.op))
            return op(left, right) if op else None
        if left is NOT_A_DURATION or right is NOT_A_DURATION:
            return NOT_A_DURATION
        return None
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        # `os.environ.get("X") or 600`: with the variable unset, the LAST operand that is a number is the one that applies.
        folded = [_fold(v, env) for v in node.values]
        for candidate in reversed(folded):
            if isinstance(candidate, float):
                return candidate
        return NOT_A_DURATION if all(v is NOT_A_DURATION for v in folded) else None
    if isinstance(node, ast.Call):
        func = ast.unparse(node.func)
        if func in _CASTS and node.args:
            return _fold(node.args[0], env)
        if func in ("max", "min") and node.args:
            values = [_fold(a, env) for a in node.args]
            if all(isinstance(v, float) for v in values):
                nums = [v for v in values if isinstance(v, float)]
                return max(nums) if func == "max" else min(nums)
            return None
        if func in _ENV_GETTERS:
            return _fold(node.args[1], env) if len(node.args) > 1 else None
        if func == "re.compile":
            return NOT_A_DURATION
        return None
    if isinstance(
        node,
        (ast.Dict, ast.List, ast.Set, ast.Tuple, ast.Lambda, ast.JoinedStr, ast.ListComp),
    ):
        return NOT_A_DURATION
    return None


def _python_timers(source: str, rel: str) -> list[tuple[str, int | None]] | None:
    """Every module-level timeout constant, in whole seconds, or None when `source` is not Python."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    env: dict[str, float] = {}
    out: list[tuple[str, int | None]] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets, value = stmt.targets, stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets, value = [stmt.target], stmt.value
        else:
            continue
        folded = _fold(value, env)
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if isinstance(folded, float):
                env[target.id] = folded
            m = TIMER_NAME_RE.match(target.id)
            if not m or folded is NOT_A_DURATION:
                continue
            unit = DECLARED_UNITS.get((rel, target.id), (m.group("unit") or "S", ""))[0]
            if isinstance(folded, float):
                out.append((target.id, math.ceil(folded * UNIT_SECONDS[unit])))
            else:
                out.append((target.id, None))
    return out


def inner_timers(source: str, rel: str = "") -> list[tuple[str, int | None]]:
    """`[(name, seconds)]`; seconds is None for a timer whose value cannot be folded."""
    if not rel or rel.endswith(".py") or source.startswith("#!/usr/bin/env python"):
        found = _python_timers(source, rel)
        if found is not None:
            return list(found)
    return [(name, int(value)) for name, value in TIMER_RE.findall(source)]


def findings(
    timers: Sequence[tuple[str, int | None]],
    ceiling_minutes: int | None,
    gate_id: str,
    leaf: str,
) -> list[str]:
    """One line per timer that cannot fire. An absent ceiling is NOT a pass, and neither is a timer whose value is unknown."""
    out = []
    for name, seconds in timers:
        if seconds is None:
            out.append(
                "%s (%s): %s has a value this gate cannot fold to a number, so its "
                "reachability is unchecked. Spell it as a literal (an env default "
                "`int(os.environ.get(...) or 600)` folds)." % (gate_id, leaf, name)
            )
            continue
        if ceiling_minutes is None:
            out.append(
                "%s (%s): %s=%ds, but its job declares no timeout-minutes, so nothing "
                "bounds the step and this timer's reachability cannot be established."
                % (gate_id, leaf, name, seconds)
            )
            continue
        ceiling = ceiling_minutes * 60
        if seconds >= ceiling:
            out.append(
                "%s (%s): %s=%ds is at or above its ceiling of %ds "
                "(timeout-minutes: %d). CI cancels the job first, so this timer never "
                "fires and the failure arrives as `The operation was canceled.` with no "
                "verdict. Lower the timer below the ceiling, or raise the job."
                % (gate_id, leaf, name, seconds, ceiling, ceiling_minutes)
            )
    return out


# ---------------------------------------------------------------------------
# Reading the workflow steps.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Step:
    job: str
    name: str
    line: int  # 1-based line of the step's `- ` item
    timeout: int | None  # the step's own numeric `timeout-minutes`, if any
    text: str  # the step item's lines, as written


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _make_step(job: str, lines: list[str], start: int, end: int) -> Step:
    body = lines[start:end]
    dash = _indent(lines[start])
    name = "<unnamed step>"
    timeout = None
    for k, raw in enumerate(body):
        m = re.match(r"^(\s*)(-\s+)?([A-Za-z_-]+):\s*(.*?)\s*(?:#.*)?$", raw)
        if not m:
            continue
        col = len(m.group(1)) + len(m.group(2) or "")
        if col != dash + 2 or (k == 0) != bool(m.group(2)):
            continue
        key, value = m.group(3), m.group(4)
        if key == "name" and name == "<unnamed step>":
            name = value.strip("'\"")
        elif key == "timeout-minutes" and re.fullmatch(r"\d+", value):
            timeout = int(value)
    return Step(job, name, start + 1, timeout, "\n".join(body) + "\n")


def workflow_steps(text: str) -> list[Step]:
    """Every step of every job under `jobs:`, with the step's own ceiling when it declares one.

    A line scanner for the same reason as `job_ceilings`. A step is a `- ` item at the first dash column under a job's `steps:` key, and runs until the next item at that column or a line at or left of the `steps:` key.
    """
    lines = text.split("\n")
    out: list[Step] = []
    in_jobs = False
    job: str | None = None
    steps_col: int | None = None
    dash_col: int | None = None
    start: int | None = None

    def close(end: int) -> None:
        nonlocal start
        if start is not None and job is not None:
            out.append(_make_step(job, lines, start, end))
        start = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        ind = _indent(line)
        if ind == 0:
            close(i)
            in_jobs = bool(re.match(r"^jobs:\s*(?:#.*)?$", line))
            job, steps_col = None, None
            continue
        if not in_jobs:
            continue
        key = re.match(r"^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$", line)
        if key:
            close(i)
            job, steps_col = key.group(1), None
            continue
        if job is None:
            continue
        if steps_col is not None:
            is_item = stripped == "-" or stripped.startswith("- ")
            if is_item and ind >= steps_col and (dash_col is None or ind == dash_col):
                close(i)
                dash_col, start = ind, i
                continue
            if ind > steps_col and not (is_item and dash_col is not None and ind < dash_col):
                continue
            close(i)
            steps_col = None
        if re.match(r"^\s+steps:\s*(?:#.*)?$", line):
            steps_col, dash_col = ind, None
    close(len(lines))
    return out


def step_refs(run_text: str) -> tuple[list[str], list[str]]:
    """`(modules, scripts)` one `run:` block names: `python3 -m rediacc_ci.<x>` and `<path>.py` tokens."""
    modules = MODULE_RE.findall(run_text)
    scripts = [t for t in SCRIPT_RE.findall(run_text) if t not in modules]
    return modules, scripts


def module_path(module: str) -> list[str]:
    """Where `python3 -m <module>` finds its code, with `.ci` on the path: a module file or a package's `__main__`."""
    base = ".ci/" + module.replace(".", "/")
    return [base + ".py", base + "/__main__.py"]


def script_path(token: str) -> str | None:
    """The repo-relative path a `<x>.py` token names, or None when it names no file this gate can read."""
    if token.startswith("/") or "$" in token:
        return None
    rel = token.removeprefix("./")
    for alias in CHECKOUT_ALIASES:
        rel = rel.removeprefix(alias)
    return rel


@dataclasses.dataclass
class StepScan:
    workflows: int = 0
    steps: int = 0
    modules: set[str] = dataclasses.field(default_factory=set)
    unresolved_scripts: set[str] = dataclasses.field(default_factory=set)
    problems: list[str] = dataclasses.field(default_factory=list)
    # (rel, workflow, job, ceiling) -> where it was first seen
    subjects: dict[tuple[str, str, str, int | None], str] = dataclasses.field(default_factory=dict)


def scan_steps(workflows: dict[str, str], read: Callable[[str], str | None]) -> StepScan:
    """Resolve every module a workflow step runs. `read(rel)` returns a repo file's text or None; injected so the selftest drives the whole path over fixtures."""
    out = StepScan(workflows=len(workflows))
    for wf_rel, text in sorted(workflows.items()):
        ceilings = job_ceilings(text)
        for step in workflow_steps(text):
            out.steps += 1
            job_cap = ceilings.get(step.job)
            caps = [c for c in (job_cap, step.timeout) if c is not None]
            ceiling = min(caps) if caps else None
            where = "%s: job %s, step '%s' (line %d)" % (wf_rel, step.job, step.name, step.line)
            texts = [b.text for b in run_blocks(step.text)]
            texts.extend(_composite_runs(step.text, read, set()))
            for run_text in texts:
                modules, scripts = step_refs(run_text)
                for module in modules:
                    rel = next((p for p in module_path(module) if read(p) is not None), None)
                    if rel is None:
                        out.problems.append(
                            "%s: runs `python3 -m %s`, and neither %s exists. The step "
                            "would fail at import; its timers are unchecked."
                            % (where, module, " nor ".join(module_path(module)))
                        )
                        continue
                    out.modules.add(rel)
                    out.subjects.setdefault((rel, wf_rel, step.job, ceiling), where)
                for token in scripts:
                    rel = script_path(token)
                    if rel is None or read(rel) is None:
                        out.unresolved_scripts.add(token)
                        continue
                    out.modules.add(rel)
                    out.subjects.setdefault((rel, wf_rel, step.job, ceiling), where)
    return out


def _composite_runs(step_text: str, read: Callable[[str], str | None], seen: set[str]) -> list[str]:
    """The `run:` blocks of every local composite action this text `uses:`, followed transitively. A composite step has no ceiling of its own, so they run under the caller's."""
    out: list[str] = []
    for ref in USES_LOCAL_RE.findall(step_text):
        rel = script_path(ref) or ""
        if rel in seen or rel.endswith((".yml", ".yaml")):
            continue  # a reusable workflow is scanned as a workflow of its own
        seen.add(rel)
        for name in ("action.yml", "action.yaml"):
            body = read(rel.rstrip("/") + "/" + name)
            if body is not None:
                out.extend(b.text for b in run_blocks(body))
                out.extend(_composite_runs(body, read, seen))
                break
    return out


# ---------------------------------------------------------------------------
# Controls.
# ---------------------------------------------------------------------------

_WF = """\
name: x
jobs:
  quality-code:
    timeout-minutes: 15
    steps: []
  no-ceiling:
    steps: []
  commented:
    timeout-minutes: 20 # budget cap, operator ruling
    steps: []
"""

_STEP_WF = """\
name: s
on: push
jobs:
  # a comment at job indent is not a job
  validate-promote:
    name: Validate Promotion
    timeout-minutes: 20 # budget cap
    steps:
      - uses: actions/checkout@v4
      - name: Test DNF install
        run: |
          PYTHONPATH=.ci python3 -m rediacc_ci.testrun.mod \\
            --method dnf
        env:
          X: y
      - name: Quick probe
        timeout-minutes: 5
        run: .ci/scripts/probe.py --fast
      - name: Composite
        uses: ./.github/actions/thing
  other:
    timeout-minutes: 30
    steps:
    - name: same-column items
      run: python3 -m pytest -q && python3 -m rediacc_ci.missing.mod
"""

_ACTION = """\
name: thing
runs:
  using: composite
  steps:
    - shell: bash
      run: PYTHONPATH=.ci python3 -m rediacc_ci.testrun.deep
"""


def _fixture_reader(files: dict[str, str]) -> Callable[[str], str | None]:
    return files.get


def selftest(*, verbose: bool = False) -> bool:
    """Both directions for every rule, before the live scan is believed."""
    c = Controls("inner-timeout-reachable", floor=39, verbose=verbose)

    caps = job_ceilings(_WF)
    c.check("a declared ceiling is read", caps.get("quality-code"), 15)
    c.check("a job without one is ABSENT, not zero and not infinite", "no-ceiling" in caps, False)
    c.check("and an unknown job is absent too", caps.get("nope"), None)
    c.check("a ceiling with a trailing comment is still read", caps.get("commented"), 20)

    c.check(
        "a module-level timer is found",
        inner_timers("RUN_TIMEOUT_S = 900\n"),
        [("RUN_TIMEOUT_S", 900)],
    )
    c.check(
        "one wrapped in an env default is found at its default",
        inner_timers('RUN_TIMEOUT_S = int(os.environ.get("X") or 1080)\n'),
        [("RUN_TIMEOUT_S", 1080)],
    )
    # THE TWO A LOOSER PATTERN WOULD GET WRONG.
    c.check(
        "an INDENTED assignment is not a module constant",
        inner_timers("if x:\n    RUN_TIMEOUT_S = 900\n"),
        [],
    )
    c.check(
        "a timer named in a comment is not a declaration",
        inner_timers("# RUN_TIMEOUT_S = 900\n"),
        [],
    )
    # THE NAMES AND UNITS THE `_S`-ONLY PATTERN COULD NOT SEE.
    c.check(
        "a bare *_TIMEOUT is a timer, in seconds",
        inner_timers("CONTAINER_TIMEOUT = 360\n"),
        [("CONTAINER_TIMEOUT", 360)],
    )
    c.check(
        "a *_TIMEOUT_MIN is minutes",
        inner_timers("JOB_TIMEOUT_MIN = 25\n"),
        [("JOB_TIMEOUT_MIN", 1500)],
    )
    c.check(
        "a *_TIMEOUT_MS is milliseconds, rounded up",
        inner_timers("HTTP_TIMEOUT_MS = 1500\n"),
        [("HTTP_TIMEOUT_MS", 2)],
    )
    c.check(
        "TIMEOUT_SECONDS and a numeric string default are both read",
        inner_timers('TIMEOUT_SECONDS = 180\nDEFAULT_TIMEOUT_SECS = "120"\n'),
        [("TIMEOUT_SECONDS", 180), ("DEFAULT_TIMEOUT_SECS", 120)],
    )
    c.check(
        "arithmetic is folded, where the first-number pattern read 15",
        inner_timers("RUN_TIMEOUT_S = 15 * 60\n"),
        [("RUN_TIMEOUT_S", 900)],
    )
    c.check(
        "a timer built from an earlier constant is folded through it",
        inner_timers("BASE = 60\nPULL_TIMEOUT_S = BASE * 30\n"),
        [("PULL_TIMEOUT_S", 1800)],
    )
    c.check(
        "a declared unit overrides the bare-name default",
        inner_timers('DEFAULT_TIMEOUT = "120000"\n', ".ci/rediacc_ci/env/create_e2e_env.py"),
        [("DEFAULT_TIMEOUT", 120)],
    )
    c.check(
        "and only for the file it names",
        inner_timers('DEFAULT_TIMEOUT = "120000"\n', "elsewhere.py"),
        [("DEFAULT_TIMEOUT", 120000)],
    )
    # MUST NOT FIRE: names that are not timers, values that are not durations.
    c.check(
        "a regex named _TIMEOUT is not a duration",
        inner_timers('_TIMEOUT = re.compile(r"[0-9]+")\n'),
        [],
    )
    c.check(
        "TIMEOUT in the middle of a name is not a timer",
        inner_timers("TIMEOUT_RETRIES = 9000\nMAX_TIMEOUT_COUNT = 9000\n"),
        [],
    )
    c.check(
        "a lower-case local is not a module constant",
        inner_timers("container_timeout = 9000\n"),
        [],
    )
    # UNKNOWN IS UNCHECKED, never folded into fine.
    c.check(
        "an unfoldable timer is kept, with no value",
        inner_timers("RUN_TIMEOUT_S = compute()\n"),
        [("RUN_TIMEOUT_S", None)],
    )
    c.check(
        "and reported",
        len(findings([("RUN_TIMEOUT_S", None)], 15, "g", "f")),
        1,
    )
    c.check(
        "a non-Python leaf keeps the column-0 pattern",
        inner_timers("RUN_TIMEOUT_S=900\n", "gate.sh"),
        [("RUN_TIMEOUT_S", 900)],
    )

    below = [("T_TIMEOUT_S", 600)]
    c.check("a timer below its ceiling is clean", findings(below, 15, "g", "f"), [])
    c.check(
        "one ABOVE it is reported",
        len(findings([("T_TIMEOUT_S", 1800)], 15, "g", "f")),
        1,
    )
    # EQUAL IS A FINDING: firing at the instant the job dies is a race.
    c.check(
        "one EQUAL to it is reported too", len(findings([("T_TIMEOUT_S", 900)], 15, "g", "f")), 1
    )
    c.check("a missing ceiling is reported, never passed", len(findings(below, None, "g", "f")), 1)
    c.check("no timer at all yields nothing to say", findings([], 15, "g", "f"), [])

    # THE STEP SCANNER.
    steps = workflow_steps(_STEP_WF)
    c.check(
        "every step of every job is found, comments and nested keys aside",
        [(s.job, s.name) for s in steps],
        [
            ("validate-promote", "<unnamed step>"),
            ("validate-promote", "Test DNF install"),
            ("validate-promote", "Quick probe"),
            ("validate-promote", "Composite"),
            ("other", "same-column items"),
        ],
    )
    c.check(
        "a step's own timeout-minutes is read, and only its own",
        [s.timeout for s in steps],
        [None, None, 5, None, None],
    )
    c.check(
        "a module a run block names is found, and `-m pytest` is not",
        step_refs("PYTHONPATH=.ci python3 -m pytest && python3 -m rediacc_ci.a.b --x\n"),
        (["rediacc_ci.a.b"], []),
    )
    c.check(
        "a script path is found, and the module is not counted twice",
        step_refs("python3 ./.ci/scripts/x.py\n")[1],
        ["./.ci/scripts/x.py"],
    )
    c.check(
        "a module resolves to its file, then to its package's __main__",
        module_path("rediacc_ci.testrun.mod"),
        [".ci/rediacc_ci/testrun/mod.py", ".ci/rediacc_ci/testrun/mod/__main__.py"],
    )
    c.check(
        "a second checkout's path is read from the working tree",
        script_path("./.review-scripts/.ci/rediacc_ci/review/g.py"),
        ".ci/rediacc_ci/review/g.py",
    )

    clean_mod = "CONTAINER_TIMEOUT = 360\n"
    files = {
        "w.yml": _STEP_WF,
        ".ci/rediacc_ci/testrun/mod.py": clean_mod,
        ".ci/scripts/probe.py": "PROBE_TIMEOUT_S = 240\n",
        ".github/actions/thing/action.yml": _ACTION,
        ".ci/rediacc_ci/testrun/deep.py": "DEEP_TIMEOUT = 60\n",
    }
    scan = scan_steps({"w.yml": _STEP_WF}, _fixture_reader(files))
    c.check(
        "every module the steps run is resolved, through the composite action too",
        sorted(scan.modules),
        [".ci/rediacc_ci/testrun/deep.py", ".ci/rediacc_ci/testrun/mod.py", ".ci/scripts/probe.py"],
    )
    c.check(
        "a module that does not exist is a finding, not a skip",
        len([p for p in scan.problems if "rediacc_ci.missing.mod" in p]),
        1,
    )
    c.check(
        "the step's own ceiling wins over its job's",
        {k[3] for k in scan.subjects if k[0] == ".ci/scripts/probe.py"},
        {5},
    )
    c.check(
        "a composite action runs under its caller's job ceiling",
        {k[3] for k in scan.subjects if k[0].endswith("deep.py")},
        {20},
    )

    # A PLANTED SUBJECT, so the reader is a real one and not the pattern's echo.
    clean = 'RUN_TIMEOUT_S = int(os.environ.get("X") or 600)\n'
    mutant = plant(clean, "600", "9000")
    c.check(
        "PLANT: raising the constant in a real source flips the verdict",
        (
            len(findings(inner_timers(clean), 15, "g", "f")),
            len(findings(inner_timers(mutant), 15, "g", "f")),
        ),
        (0, 1),
    )
    # THE DEFECT THAT OPENED THE SECOND DOOR, end to end through the step path: a step module's bare CONTAINER_TIMEOUT above its 20-minute job.
    planted = dict(files)
    planted[".ci/rediacc_ci/testrun/mod.py"] = plant(clean_mod, "360", "1800")
    c.check(
        "PLANT: CONTAINER_TIMEOUT=1800 under a 20-minute job flips the step verdict",
        (
            len(step_findings(scan, _fixture_reader(files))),
            len(step_findings(scan_steps({"w.yml": _STEP_WF}, planted.get), planted.get)),
        ),
        (0, 1),
    )
    return c.report()


def step_findings(scan: StepScan, read: Callable[[str], str | None]) -> list[str]:
    """The reachability findings for every resolved (module, ceiling) pair. Resolution problems are the caller's to add."""
    out: list[str] = []
    for (rel, _wf, _job, ceiling), where in sorted(scan.subjects.items(), key=str):
        source = read(rel)
        if source is None:
            continue
        out.extend(findings(inner_timers(source, rel), ceiling, where, rel))
    return out


def _repo_reader(root: pathlib.Path) -> Callable[[str], str | None]:
    cache: dict[str, str | None] = {}

    def read(rel: str) -> str | None:
        if rel not in cache:
            path = root / rel
            try:
                cache[rel] = (
                    path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None
                )
            except OSError:
                cache[rel] = None
        return cache[rel]

    return read


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return 0 if selftest(verbose=True) else 1
    if not selftest():
        print(
            "✗ CONTROL FAILED: this gate's own controls did not pass, so it refuses to "
            "report on the tree.",
            file=sys.stderr,
        )
        return 1

    root = pathlib.Path(__file__).resolve().parents[3]
    read = _repo_reader(root)
    lock = json.loads((root / LOCK_REL).read_text(encoding="utf-8"))
    workflows: dict[str, dict[str, int]] = {}
    problems: list[str] = []
    examined = 0
    timers_compared = 0
    seen: set[tuple[str, str, str, int | None]] = set()

    for entry in lock:
        ci = entry.get("ci") or {}
        if ci.get("kind") != "step":
            continue
        wf_rel = ci.get("workflow", "")
        if wf_rel not in workflows:
            workflows[wf_rel] = job_ceilings(read(wf_rel) or "")
        ceiling = workflows[wf_rel].get(ci.get("job", ""))
        for leaf in entry.get("leaves", []):
            source = read(leaf)
            if source is None:
                continue
            timers = inner_timers(source, leaf)
            if not timers:
                continue
            examined += 1
            timers_compared += len(timers)
            seen.add((leaf, wf_rel, ci.get("job", ""), ceiling))
            problems.extend(findings(timers, ceiling, entry.get("id", "?"), leaf))

    # ANTI-VACUITY. Finding no timer anywhere means the reader broke or the convention was renamed, and a green would then mean "checked nothing".
    if examined == 0:
        print(
            "✗ scanned %d registered gate(s) and found NO script declaring a `*_TIMEOUT_S`\n"
            "  constant. At least one exists (check:ci-pytest), so either the lock stopped\n"
            "  naming leaves or the convention was renamed. This gate is checking nothing."
            % len(lock),
            file=sys.stderr,
        )
        return 1

    # THE SECOND DOOR: every module a workflow step runs.
    wf_dir = root / WORKFLOWS_REL
    wf_texts = {
        "%s/%s" % (WORKFLOWS_REL, p.name): p.read_text(encoding="utf-8", errors="replace")
        for p in sorted(wf_dir.glob("*.y*ml"))
    }
    scan = scan_steps(wf_texts, read)
    if not scan.modules:
        print(
            "✗ walked %d workflow(s) and %d step(s) and resolved NO Python module a step\n"
            "  runs. `python3 -m rediacc_ci.<x>` and `<path>.py` steps exist in\n"
            "  ci.yml and ci-quality.yml, so the step scanner is broken or pointed at the\n"
            "  wrong tree. This half of the gate is checking nothing."
            % (scan.workflows, scan.steps),
            file=sys.stderr,
        )
        return 1
    problems.extend(scan.problems)
    step_subjects = 0
    used_units: set[tuple[str, str]] = set()
    for key, where in sorted(scan.subjects.items(), key=str):
        rel = key[0]
        source = read(rel)
        if source is None or key in seen:
            continue
        timers = inner_timers(source, rel)
        used_units.update((rel, name) for name, _ in timers if (rel, name) in DECLARED_UNITS)
        if not timers:
            continue
        step_subjects += 1
        timers_compared += len(timers)
        problems.extend(findings(timers, key[3], where, rel))

    for (rel, name), (unit, reason) in sorted(DECLARED_UNITS.items()):
        if (rel, name) not in used_units:
            problems.append(
                "DECLARED_UNITS names %s %s, and no step module declares it any more. "
                "Delete the stale entry." % (rel, name)
            )
        else:
            print("  declared unit: %s %s is %s (%s)" % (rel, name, unit.lower(), reason))

    if problems:
        print(
            "✗ %d finding(s): a kill timer that cannot fire, or one this gate cannot check:"
            % len(problems),
            file=sys.stderr,
        )
        for line in problems:
            print("    %s" % line, file=sys.stderr)
        return 1

    print(
        "✓ %d timer(s) sit below their ceilings: %d registered gate script(s), plus %d "
        "step subject(s) out of %d module(s) resolved from %d step(s) in %d workflow(s) "
        "(%d `.py` token(s) named no file in this tree)"
        % (
            timers_compared,
            examined,
            step_subjects,
            len(scan.modules),
            scan.steps,
            scan.workflows,
            len(scan.unresolved_scripts),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
