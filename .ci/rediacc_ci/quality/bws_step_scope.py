"""check:ci-bws-step-scope -- a production signing key fetched from Bitwarden lives for ONE step, not for the rest of the job.

WHY THIS EXISTS. `.github/actions/bws-secrets` writes every value it fetches to GITHUB_ENV, so a name fetched at job start is readable by every later step: third-party actions, the CLI build, test code. Per-commit review 047cc812.1 found the production licence-signing key (ACCOUNT_ED25519_PRIVATE_KEY) exported that way in 17 jobs, each with exactly one step that needed it. Anyone who
reads that key can mint a licence every released renet accepts. agent/plans/PLAN-scope-bws-signing-key-to-consuming-step.md moved each such fetch to sit immediately before its consumer and added `.github/actions/bws-scrub` immediately after it. This gate keeps that shape from eroding.

THE NAMES are `.ci/config/bws-step-scoped.json`, by Bitwarden NAME (the left-hand side of `NAME > ENV_NAME`). The exported variable is derived from each fetch line, so a renamed export cannot slip past. For every listed name, in every job, a WINDOW opens at each fetch of it and runs to its scrub (or to the next fetch of it, or to the end of the job). The gate refuses:

  (i)   a fetch of the name that also fetches a name NOT in the config. The job-start
        fetch is exactly that, and a shared fetch cannot be moved next to one consumer.
  (ii)  a step inside the window, before the last consumer, that does not read the
        variable. It runs with the key in its environment for no reason. A window
        with no consumer at all is refused under the same rule.
  (iii) no bws-scrub naming the variable IMMEDIATELY after the last consumer. A step
        between the two inherits the key.
  (iv)  a scrub without `if: always()`. Under the default `success()` a failed
        consumer would skip the scrub and leave the key set for every `always()` and
        `failure()` step after it.
  (v)   a read of the variable after the scrub, or before any fetch of it. After the
        scrub the value is empty, so such a read is a silent misconfiguration.

A READ is `env.NAME`, `$NAME`, `${NAME}` or a quoted `'NAME'`/`"NAME"` inside an `environ` lookup, outside comments, anywhere in the step (its `env:`, `with:`, `if:` and `run:`). What a step reads IMPLICITLY from its process environment cannot be seen by any text scan, which is why (ii) refuses EVERY non-consumer step in the window rather than only the ones that mention the name.

THE PARSE IS SHARED, NOT RE-TYPED. The `NAME > ENV` grammar is `check_bws_map.parse_requests`, loaded by path (`.ci/scripts/quality/check_bws_map.py` is an entry point, not a package module), because two parsers for one grammar is how a block comes to mean different things to two gates. Steps come from `rediacc_ci.workflows`, the tree's one YAML parser; each structural step is mapped to its line range by a line scan, and a disagreement
between the two counts is an instrument failure (exit 2), never a silent skip.

ANTI-VACUITY. Zero windows is a failure. Fewer windows than `MIN_WINDOWS` is a failure (raise it when a job gains a scoped fetch; lower it only when a job is deleted). A config name that is not in `.ci/config/bws-secret-map.json`, or that no fetch requests, is a dead entry and a failure. A config reason that does not start with `BLOCKER:` or fails `rediacc_ci.core.allowlist.validate_reason` is a failure. The success line prints files, jobs, windows and consumers so a collapse is visible.

THE SEAM. `WORKFLOW_DIR` replaces the corpus with every `*.yml` in that directory, and `BWS_STEP_SCOPED_CONFIG` replaces the config, so a test can drive the real scan against a fixture. Neither weakens a rule: an empty directory has zero windows and reds.

KNOWN LIMIT, recorded rather than hidden. A process the consumer starts and leaves running keeps the key in its own environment (`.ci/rediacc_ci/testrun/start_account.py` starts the per-run account server with `**os.environ`), and a later step running as the same user can read `/proc/<pid>/environ`. Blanking GITHUB_ENV cannot reach it; the plan's follow-up item owns it.
"""

from __future__ import annotations

import contextlib
import functools
import importlib.util
import io
import json
import os
import pathlib
import re
import sys
import tempfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rediacc_ci import paths, workflows
from rediacc_ci.controls import Checker, controls_first, plant
from rediacc_ci.core import allowlist

if TYPE_CHECKING:
    import types

CONFIG_REL = ".ci/config/bws-step-scoped.json"
MAP_REL = ".ci/config/bws-secret-map.json"
BWS_MAP_GATE_REL = ".ci/scripts/quality/check_bws_map.py"
BWS_MAP_MODULE = "check_bws_map_for_step_scope"
FETCH_ACTION = "./.github/actions/bws-secrets"
SCRUB_ACTION = "./.github/actions/bws-scrub"

WORKFLOW_DIR_ENV = "WORKFLOW_DIR"
CONFIG_ENV = "BWS_STEP_SCOPED_CONFIG"
MIN_WINDOWS_ENV = "BWS_STEP_SCOPE_MIN_WINDOWS"
# Counted per exported variable: 17 ACCOUNT_ED25519_PRIVATE_KEY windows, 3 ACCOUNT_X25519_PRIVATE_KEY windows sharing the deploy jobs' fetch, and two cd-stage windows for each of the two GPG variables. Raise it when a job gains a scoped fetch.
DEFAULT_MIN_WINDOWS = 24

ALWAYS = "always()"
MIN_CONTROLS = 20

CANNOT_RUN = 2


class InstrumentError(Exception):
    """The scan cannot produce a verdict for a file: a parse refusal, or a structural and line-scan disagreement."""


@dataclass
class ScanStep:
    index: int
    line: int  # 1-based line of the step's `- ` item
    label: str
    uses: str
    cond: object
    text: str  # the step's lines with comments removed
    requests: list[tuple[int, str, str]] = field(default_factory=list)
    scrub_names: list[str] = field(default_factory=list)


@dataclass
class ScanJob:
    job_id: str
    steps: list[ScanStep]


@dataclass
class Report:
    findings: list[str] = field(default_factory=list)
    files: int = 0
    jobs: int = 0
    windows: int = 0
    consumers: int = 0
    seen_names: set[str] = field(default_factory=set)


# --------------------------------------------------------------------------- The shared request grammar ---------------------------------------------------------------------------


@functools.cache
def bws_map_gate() -> types.ModuleType:
    """`.ci/scripts/quality/check_bws_map.py`, loaded by path once."""
    path = paths.repo_root() / BWS_MAP_GATE_REL
    # The entry point opens with `import _cipath`, which resolves from its own directory; a path LOAD does not put that directory on sys.path the way a path INVOCATION does.
    paths.on_sys_path(path.parent)
    spec = importlib.util.spec_from_file_location(BWS_MAP_MODULE, path)
    if spec is None or spec.loader is None:
        msg = "cannot load %s" % path
        raise InstrumentError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "parse_requests", None)):
        msg = (
            "%s no longer defines parse_requests; this gate reuses it and cannot parse a fetch without it"
            % path
        )
        raise InstrumentError(msg)
    return module


def parse_requests(text: str) -> list[tuple[int, str, str]]:
    """`check_bws_map.parse_requests`: [(line_no, name, env_name)] for every bws-secrets request line."""
    return bws_map_gate().parse_requests(text)


# --------------------------------------------------------------------------- Reads, scrubs and conditions ---------------------------------------------------------------------------


def read_re(var: str) -> re.Pattern:
    """A read of `var`: `env.VAR`, `$VAR`, `${VAR}`, or `environ...["VAR"]`/`('VAR')`."""
    v = re.escape(var)
    return re.compile(
        r"(?:(?<![\w.])env\.%s|\$\{?%s|environ[\w.]*[\[(]\s*[\"']%s[\"'])(?!\w)" % (v, v, v)
    )


def is_always(cond: object) -> bool:
    """`if: always()` or `if: ${{ always() }}`, and nothing weaker."""
    if not isinstance(cond, str):
        return False
    text = cond.strip()
    m = re.fullmatch(r"\$\{\{\s*(.*?)\s*\}\}", text)
    if m:
        text = m.group(1)
    return text.strip() == ALWAYS


def _step_label(raw: dict) -> str:
    name = raw.get("name")
    if name:
        return str(name)
    if raw.get("uses"):
        return "uses: %s" % raw["uses"]
    run = str(raw.get("run") or "").strip().split("\n")[0]
    return "run: %s" % run[:60]


# --------------------------------------------------------------------------- Structure: steps with their line ranges ---------------------------------------------------------------------------


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _significant(line: str) -> bool:
    s = line.strip()
    return bool(s) and not s.startswith("#")


def _is_item(line: str) -> bool:
    return line.lstrip().startswith("- ") or line.strip() == "-"


def _block_end(lines: list[str], start: int, indent: int) -> int:
    """The first line after `start` that is significant and indented at most `indent`."""
    for i in range(start + 1, len(lines)):
        if _significant(lines[i]) and _indent(lines[i]) <= indent:
            return i
    return len(lines)


def _step_starts(lines: list[str], lo: int, hi: int, label: str) -> list[int]:
    """0-based start lines of the step items under the first `steps:` key in [lo, hi)."""
    key = next((i for i in range(lo, hi) if re.match(r"^\s*steps:\s*$", lines[i])), None)
    if key is None:
        return []
    end = min(_block_end(lines, key, _indent(lines[key])), hi)
    item_indent = None
    starts: list[int] = []
    for i in range(key + 1, end):
        line = lines[i]
        if not _significant(line):
            continue
        if item_indent is None:
            if not _is_item(line):
                msg = "%s:%d: the first line under `steps:` is not a sequence item" % (label, i + 1)
                raise InstrumentError(msg)
            item_indent = _indent(line)
        if _indent(line) == item_indent and _is_item(line):
            starts.append(i)
    return starts


def _job_ranges(lines: list[str]) -> dict[str, tuple[int, int]]:
    """job_id -> [lo, hi) for each two-space job header under the top-level `jobs:` key."""
    jobs_key = next((i for i, ln in enumerate(lines) if re.match(r"^jobs:\s*$", ln)), None)
    if jobs_key is None:
        return {}
    end = _block_end(lines, jobs_key, 0)
    headers = [
        (i, m.group(1)) for i in range(jobs_key + 1, end) if (m := workflows.JOB_RE.match(lines[i]))
    ]
    out: dict[str, tuple[int, int]] = {}
    for k, (i, job_id) in enumerate(headers):
        out[job_id] = (i, headers[k + 1][0] if k + 1 < len(headers) else end)
    return out


def _build_steps(
    raw_steps: list,
    lines: list[str],
    starts: list[int],
    hi: int,
    requests: list[tuple[int, str, str]],
    where: str,
) -> list[ScanStep]:
    dict_steps = [s for s in raw_steps if isinstance(s, dict)]
    if len(dict_steps) != len(starts):
        msg = (
            "%s: the YAML parse found %d step(s) and the line scan %d; the gate cannot map steps to "
            "lines, so it refuses rather than judge the wrong step"
            % (where, len(dict_steps), len(starts))
        )
        raise InstrumentError(msg)
    out: list[ScanStep] = []
    for k, (raw, lo) in enumerate(zip(dict_steps, starts, strict=True)):
        end = starts[k + 1] if k + 1 < len(starts) else hi
        uses = str(raw.get("uses") or "")
        step = ScanStep(
            index=k,
            line=lo + 1,
            label=_step_label(raw),
            uses=uses,
            cond=raw.get("if"),
            text="\n".join(workflows.code_part(ln) for ln in lines[lo:end]),
            requests=[r for r in requests if lo < r[0] <= end],
        )
        if step.requests and not uses.startswith(FETCH_ACTION):
            msg = (
                "%s, line %d: a bws-secrets request line fell inside a step that is not a fetch; the line map is wrong"
                % (
                    where,
                    step.requests[0][0],
                )
            )
            raise InstrumentError(msg)
        if uses.startswith(SCRUB_ACTION):
            names = (raw.get("with") or {}).get("names") or ""
            step.scrub_names = [n.strip() for n in str(names).split("\n") if n.strip()]
        out.append(step)
    return out


def scan_jobs(text: str, label: str) -> list[ScanJob]:
    """Every job in one workflow (or the one step list of a composite action), with line-mapped steps."""
    try:
        doc = workflows.parse(text)
    except (workflows.WorkflowParseError, workflows.UnsupportedYAMLError) as exc:
        msg = "%s: %s" % (label, exc)
        raise InstrumentError(msg) from exc
    if not isinstance(doc, dict):
        return []
    lines = text.split("\n")
    requests = parse_requests(text)
    out: list[ScanJob] = []
    jobs = doc.get("jobs")
    if isinstance(jobs, dict):
        ranges = _job_ranges(lines)
        for job_id, body in jobs.items():
            raw_steps = body.get("steps") if isinstance(body, dict) else None
            if not raw_steps:
                continue
            if job_id not in ranges:
                msg = "%s: job %r has steps but no two-space header line was found for it" % (
                    label,
                    job_id,
                )
                raise InstrumentError(msg)
            lo, hi = ranges[job_id]
            where = "%s job %r" % (label, job_id)
            steps = _build_steps(
                raw_steps, lines, _step_starts(lines, lo, hi, label), hi, requests, where
            )
            out.append(ScanJob(job_id, steps))
    runs = doc.get("runs")
    if isinstance(runs, dict) and runs.get("steps"):
        starts = _step_starts(lines, 0, len(lines), label)
        steps = _build_steps(
            runs["steps"], lines, starts, len(lines), requests, "%s runs.steps" % label
        )
        out.append(ScanJob("(composite)", steps))
    claimed = sum(len(s.requests) for j in out for s in j.steps)
    if claimed != len(requests):
        msg = (
            "%s: %d bws-secrets request line(s) parsed but %d fall inside a step; the line map is wrong"
            % (
                label,
                len(requests),
                claimed,
            )
        )
        raise InstrumentError(msg)
    return out


# --------------------------------------------------------------------------- The five rules ---------------------------------------------------------------------------


def _rule_i(job: ScanJob, label: str, scoped: set[str], report: Report) -> None:
    for s in job.steps:
        mine = sorted({name for _l, name, _e in s.requests if name in scoped})
        if not mine:
            continue
        extra = sorted({name for _l, name, _e in s.requests if name not in scoped})
        if extra:
            report.findings.append(
                "%s:%d job %r rule (i): the fetch %r requests %s together with %s, which %s does not list. "
                "A shared fetch exports the key for the whole job. Fix: remove %s from this fetch and add a "
                "dedicated bws-secrets step requesting only step-scoped names immediately before its consumer."
                % (
                    label,
                    s.line,
                    job.job_id,
                    s.label,
                    ", ".join(mine),
                    ", ".join(extra),
                    CONFIG_REL,
                    ", ".join(mine),
                )
            )


def _window(
    job: ScanJob,
    label: str,
    var: str,
    f: int,
    end: int,
    reads: list[int],
    scrubs: list[int],
    report: Report,
) -> None:
    """Rules (ii) to (v) for the window opened by the fetch at step `f` and closed by `end`."""
    steps = job.steps
    where = "%s:%%d job %r" % (label, job.job_id)
    report.windows += 1
    scrub = next((s for s in scrubs if f < s < end), None)
    consumers = [r for r in reads if f < r < (scrub if scrub is not None else end)]
    report.consumers += len(consumers)
    if not consumers:
        closer = (
            "the scrub"
            if scrub is not None
            else ("the next fetch of it" if end < len(steps) else "the end of the job")
        )
        report.findings.append(
            (where % steps[f].line)
            + " rule (ii): the fetch %r exports %s but no step reads it before %s. Fix: delete the fetch, or place "
            "it immediately before the step that reads the key." % (steps[f].label, var, closer)
        )
        return
    last = max(consumers)
    for i in range(f + 1, last):
        if i not in consumers:
            report.findings.append(
                (where % steps[i].line)
                + " rule (ii): step %r sits between the fetch of %s at line %d and its consumer %r at line %d "
                "without reading it, so it runs with the key in its environment. Fix: move the fetch to "
                "immediately before the consumer, or give each consumer its own fetch and scrub pair."
                % (steps[i].label, var, steps[f].line, steps[last].label, steps[last].line)
            )
    if scrub is None:
        hint = (
            ""
            if var.startswith("BWS_")
            else " The variable must be exported under a BWS_ name for bws-scrub to accept it."
        )
        report.findings.append(
            (where % steps[last].line)
            + " rule (iii): no %s step names %s after its last consumer %r, so every later step inherits the key. "
            "Fix: add `uses: %s` with `if: always()` and `names: %s` immediately after it.%s"
            % (SCRUB_ACTION, var, steps[last].label, SCRUB_ACTION, var, hint)
        )
        return
    if scrub != last + 1:
        between = ", ".join(repr(steps[i].label) for i in range(last + 1, scrub))
        report.findings.append(
            (where % steps[scrub].line)
            + " rule (iii): the scrub of %s is not immediately after the last consumer %r; %s run(s) with the key "
            "in between. Fix: move the scrub to directly after the consumer."
            % (var, steps[last].label, between)
        )
    if not is_always(steps[scrub].cond):
        have = "no `if:`" if steps[scrub].cond is None else "`if: %s`" % steps[scrub].cond
        report.findings.append(
            (where % steps[scrub].line)
            + " rule (iv): the scrub of %s has %s, so a failed or cancelled consumer skips it and the key stays set "
            "for every later always() or failure() step. Fix: `if: always()`." % (var, have)
        )
    for r in reads:
        if scrub < r < end:
            report.findings.append(
                (where % steps[r].line)
                + " rule (v): step %r reads %s after the scrub at line %d, where it is empty. Fix: move the read "
                "before the scrub, or give the step its own fetch and scrub pair."
                % (steps[r].label, var, steps[scrub].line)
            )


def judge_job(job: ScanJob, label: str, scoped: set[str], report: Report) -> None:
    """Append every finding for one job to `report`."""
    steps = job.steps
    _rule_i(job, label, scoped, report)
    # The exported variable of every scoped name this job fetches, with the fetch steps that export it, in order.
    fetches: dict[str, list[int]] = {}
    for s in steps:
        for _line, name, env in s.requests:
            if name in scoped:
                report.seen_names.add(name)
                if s.index not in fetches.setdefault(env, []):
                    fetches[env].append(s.index)
    for var, fetch_idx in fetches.items():
        rx = read_re(var)
        reads = [s.index for s in steps if rx.search(s.text)]
        scrubs = [s.index for s in steps if var in s.scrub_names]
        for r in reads:
            if r < fetch_idx[0]:
                report.findings.append(
                    "%s:%d job %r rule (v): step %r reads %s before any fetch of it, where it is empty. "
                    "Fix: move the read inside a fetch and scrub window."
                    % (label, steps[r].line, job.job_id, steps[r].label, var)
                )
        for k, f in enumerate(fetch_idx):
            end = fetch_idx[k + 1] if k + 1 < len(fetch_idx) else len(steps)
            _window(job, label, var, f, end, reads, scrubs, report)


def scan_text(text: str, label: str, scoped: set[str], report: Report) -> None:
    jobs = scan_jobs(text, label)
    report.files += 1
    report.jobs += len(jobs)
    for job in jobs:
        judge_job(job, label, scoped, report)


# --------------------------------------------------------------------------- Config, corpus, verdict ---------------------------------------------------------------------------


def _rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(paths.repo_root()))
    except ValueError:
        return str(path)


def load_config(path: pathlib.Path) -> tuple[set[str], list[str]]:
    """(names, problems). A missing or malformed file is a problem, never an empty set."""
    rel = _rel(path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return set(), [
            "%s cannot be read (%s); the gate has nothing to hold the tree to" % (rel, exc)
        ]
    names = doc.get("names") if isinstance(doc, dict) else None
    if not isinstance(names, dict) or not names:
        return set(), ["%s has no `names` object, or it is empty; refusing to pass vacuously" % rel]
    problems: list[str] = []
    for name, rec in names.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            problems.append("%s: %r is not a Bitwarden secret name" % (rel, name))
        reason = rec.get("reason") if isinstance(rec, dict) else None
        if not isinstance(reason, str) or not reason.startswith("BLOCKER:"):
            problems.append("%s: %s has no `reason` starting with 'BLOCKER:'" % (rel, name))
            continue
        rejection = allowlist.validate_reason(name, reason[len("BLOCKER:") :], rel)
        if rejection is not None:
            problems.append(rejection.message)
    return set(names), problems


def corpus(root: pathlib.Path) -> list[pathlib.Path]:
    override = os.environ.get(WORKFLOW_DIR_ENV)
    if override:
        return sorted(pathlib.Path(override).glob("*.yml"))
    return workflows.call_sites(root)


def verdict(root: pathlib.Path) -> int:
    config_path = pathlib.Path(os.environ.get(CONFIG_ENV) or root / CONFIG_REL)
    scoped, problems = load_config(config_path)
    raw_floor = os.environ.get(MIN_WINDOWS_ENV) or ""
    floor = int(raw_floor) if raw_floor.isdigit() else DEFAULT_MIN_WINDOWS
    try:
        mapped = set(json.loads((root / MAP_REL).read_text(encoding="utf-8")).get("secrets") or {})
    except (OSError, ValueError) as exc:
        print(
            "✗ %s cannot be read (%s); a dead config entry cannot be told from a live one"
            % (MAP_REL, exc),
            file=sys.stderr,
        )
        return CANNOT_RUN
    problems += [
        "%s: %s is not in %s; a typo here would scope nothing" % (_rel(config_path), name, MAP_REL)
        for name in sorted(scoped - mapped)
    ]

    report = Report()
    try:
        for f in corpus(root):
            scan_text(f.read_text(encoding="utf-8"), _rel(f), scoped, report)
    except InstrumentError as exc:
        print("✗ instrument: %s" % exc, file=sys.stderr)
        return CANNOT_RUN

    problems += report.findings
    problems += [
        "%s: %s is requested by no bws-secrets fetch in %d file(s); a dead entry, or the scan lost its subject"
        % (_rel(config_path), name, report.files)
        for name in sorted(scoped - report.seen_names)
    ]
    if report.windows == 0:
        problems.append(
            "no fetch of a step-scoped name in %d file(s); the gate is not seeing the tree, and its green would mean nothing"
            % report.files
        )
    elif report.windows < floor:
        problems.append(
            "only %d fetch window(s) found, floor is %d (%s). A job lost its scoped fetch, or the scan lost it; "
            "lower the floor only when a job was deleted" % (report.windows, floor, MIN_WINDOWS_ENV)
        )
    if problems:
        print("✗ bws step scope (%d problem(s)):" % len(problems), file=sys.stderr)
        for p in problems:
            print("    %s" % p, file=sys.stderr)
        return 1
    print(
        "✓ bws step scope: %d name(s) from %s, %d file(s), %d job(s), %d fetch window(s) (floor %d), "
        "%d consumer step(s); every window is fetch, consumers, then an always() scrub, with nothing between"
        % (
            len(scoped),
            CONFIG_REL,
            report.files,
            report.jobs,
            report.windows,
            floor,
            report.consumers,
        )
    )
    print(
        "  Blind spot: a process a consumer leaves running keeps its own copy of the key (/proc/<pid>/environ)."
    )
    return 0


# --------------------------------------------------------------------------- Controls ---------------------------------------------------------------------------

SCOPED = frozenset({"ACCOUNT_ED25519_PRIVATE_KEY", "ACCOUNT_X25519_PRIVATE_KEY"})

# The fixed shape: shared fetch without the key, dedicated fetch, one consumer, always() scrub.
FIXED = """\
name: probe
on: push
jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - name: Fetch secrets from Bitwarden
        uses: ./.github/actions/bws-secrets
        with:
          access-token: ${{ secrets.BWS_ACCESS_TOKEN }}
          secrets: |
            DOCKERHUB_TOKEN > BWS_DOCKERHUB_TOKEN
            ACCOUNT_ED25519_PUBLIC_KEY > BWS_ACCOUNT_ED25519_PUBLIC_KEY
      - name: Login to Docker Hub
        run: echo "$BWS_DOCKERHUB_TOKEN" | docker login --password-stdin
      # the consumer's own comment, which mentions env.BWS_ACCOUNT_ED25519_PRIVATE_KEY in prose only
      - name: Fetch the signing key for the next step only
        uses: ./.github/actions/bws-secrets
        with:
          access-token: ${{ secrets.BWS_ACCESS_TOKEN }}
          secrets: |
            ACCOUNT_ED25519_PRIVATE_KEY > BWS_ACCOUNT_ED25519_PRIVATE_KEY
      - name: Start the per-run account server
        env:
          ACCOUNT_ED25519_PRIVATE_KEY: ${{ env.BWS_ACCOUNT_ED25519_PRIVATE_KEY }}
          ACCOUNT_ED25519_PUBLIC_KEY: ${{ env.BWS_ACCOUNT_ED25519_PUBLIC_KEY }}
        run: python3 -m start_account
      - name: Blank the signing key for the rest of the job
        if: always()
        uses: ./.github/actions/bws-scrub
        with:
          names: |
            BWS_ACCOUNT_ED25519_PRIVATE_KEY
      - name: Run the tests
        run: npm test
"""

# The pre-fix ct-tests.yml:435/493 shape: the key rides the job-start fetch and lives to the end of the job.
PRE_FIX = """\
name: probe
on: push
jobs:
  test-e2e-workers:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - name: Fetch secrets from Bitwarden
        uses: ./.github/actions/bws-secrets
        with:
          access-token: ${{ secrets.BWS_ACCESS_TOKEN }}
          secrets: |
            GITHUB_APP_PRIVATE_KEY > BWS_GITHUB_APP_PRIVATE_KEY
            ACCOUNT_ED25519_PRIVATE_KEY > BWS_ACCOUNT_ED25519_PRIVATE_KEY
            ACCOUNT_ED25519_PUBLIC_KEY > BWS_ACCOUNT_ED25519_PUBLIC_KEY
      - uses: ./.github/actions/app-token
        with:
          private-key: ${{ env.BWS_GITHUB_APP_PRIVATE_KEY }}
      - run: PYTHONPATH=.ci python3 -m rediacc_ci.build.build_cli
      - name: Start the per-run account server
        env:
          ACCOUNT_ED25519_PRIVATE_KEY: ${{ env.BWS_ACCOUNT_ED25519_PRIVATE_KEY }}
        run: PYTHONPATH=.ci python3 -m rediacc_ci.testrun.start_account --port 4900 --require-env-pair
      - name: Install the shared renet
        uses: ./.github/actions/renet-test-binary
"""

_DEDICATED = """\
      - name: Fetch the signing key for the next step only
        uses: ./.github/actions/bws-secrets
        with:
          access-token: ${{ secrets.BWS_ACCESS_TOKEN }}
          secrets: |
            ACCOUNT_ED25519_PRIVATE_KEY > BWS_ACCOUNT_ED25519_PRIVATE_KEY
"""

_SCRUB = """\
      - name: Blank the signing key for the rest of the job
        if: always()
        uses: ./.github/actions/bws-scrub
        with:
          names: |
            BWS_ACCOUNT_ED25519_PRIVATE_KEY
"""

_TAIL = "      - name: Run the tests\n        run: npm test\n"


def plants() -> dict[str, str]:
    """rule -> a fixture that breaks that rule. Exported for the pytest that drives the CLI through WORKFLOW_DIR."""
    return {
        # (i) the pre-fix shape, a shared job-start fetch. It also breaks (ii) and (iii), which the controls assert separately.
        "i": PRE_FIX,
        # (ii) a step slipped between the dedicated fetch and its consumer.
        "ii": plant(
            FIXED,
            _DEDICATED,
            _DEDICATED + "      - name: Install CLI Globally\n        run: npm i -g ./cli\n",
        ),
        # (iii) the scrub is missing.
        "iii": plant(FIXED, _SCRUB, ""),
        # (iv) the scrub runs under the default success() condition.
        "iv": plant(
            FIXED,
            "        if: always()\n        uses: ./.github/actions/bws-scrub",
            "        uses: ./.github/actions/bws-scrub",
        ),
        # (v) a step after the scrub still reads the key.
        "v": plant(
            FIXED,
            _TAIL,
            '      - name: Run the tests\n        run: echo "${BWS_ACCOUNT_ED25519_PRIVATE_KEY}" | wc -c\n',
        ),
    }


def fired_rules(findings: list[str]) -> set[str]:
    """The rule numerals named by `findings`, as strings: {'i', 'iii', ...}."""
    return set(re.findall(r"rule \((i{1,3}|iv|v)\)", "\n".join(findings)))


def _scan(text: str) -> Report:
    report = Report()
    scan_text(text, "probe.yml", set(SCOPED), report)
    return report


def _empty_corpus_rc() -> int:
    with tempfile.TemporaryDirectory() as empty:
        saved = os.environ.get(WORKFLOW_DIR_ENV)
        os.environ[WORKFLOW_DIR_ENV] = empty
        try:
            with (
                contextlib.redirect_stderr(io.StringIO()),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                return verdict(paths.repo_root())
        finally:
            if saved is None:
                os.environ.pop(WORKFLOW_DIR_ENV, None)
            else:
                os.environ[WORKFLOW_DIR_ENV] = saved


def selftest() -> bool:
    """True when a control failed, which is what `controls_first` expects."""
    check = Checker()

    fixed = _scan(FIXED)
    check("the fixed shape is silent (%d finding(s))" % len(fixed.findings), not fixed.findings)
    check(
        "the fixed shape opens one window with one consumer",
        (fixed.windows, fixed.consumers) == (1, 1),
    )
    check(
        "the fixed shape sees the scoped name", fixed.seen_names == {"ACCOUNT_ED25519_PRIVATE_KEY"}
    )

    for rule, text in plants().items():
        got = fired_rules(_scan(text).findings)
        check("plant (%s) fires rule (%s) (fired: %s)" % (rule, rule, sorted(got)), rule in got)
    check(
        "the pre-fix ct-tests shape fires (i), (ii) and (iii)",
        {"i", "ii", "iii"} <= fired_rules(_scan(PRE_FIX).findings),
    )
    for rule in ("ii", "iii", "iv", "v"):
        others = fired_rules(_scan(plants()[rule]).findings) - {rule}
        check("plant (%s) fires no other rule (%s)" % (rule, sorted(others)), not others)

    # Two consumers with an unrelated step between them, each in its own window: the cd-stage shape, which must be silent.
    second_consumer = "      - name: Second consumer\n        env:\n          K: ${{ env.BWS_ACCOUNT_ED25519_PRIVATE_KEY }}\n        run: sign\n"
    two = _scan(
        plant(
            FIXED,
            _TAIL,
            "      - name: Unrelated\n        run: 'true'\n"
            + _DEDICATED
            + second_consumer
            + _SCRUB,
        )
    )
    check(
        "two fetch and scrub pairs in one job are silent (%s)" % two.findings[:1],
        not two.findings and two.windows == 2,
    )

    orphan = plant(
        FIXED,
        "          ACCOUNT_ED25519_PRIVATE_KEY: ${{ env.BWS_ACCOUNT_ED25519_PRIVATE_KEY }}\n",
        "",
    )
    check("a window with no consumer fires (ii)", "ii" in fired_rules(_scan(orphan).findings))
    early = plant(
        FIXED,
        '        run: echo "$BWS_DOCKERHUB_TOKEN" | docker login --password-stdin\n',
        '        run: test -n "$BWS_ACCOUNT_ED25519_PRIVATE_KEY"\n',
    )
    check("a read before any fetch fires (v)", "v" in fired_rules(_scan(early).findings))

    check("`${{ always() }}` counts as always()", is_always("${{ always() }}"))
    check("`always() && x` does not", not is_always("always() && x"))
    check("`success()` does not", not is_always("success()"))
    check("no `if:` does not", not is_always(None))

    rx = read_re("BWS_K")
    check("env.BWS_K is a read", rx.search("${{ env.BWS_K }}"))
    check("$BWS_K and ${BWS_K} are reads", rx.search("echo $BWS_K") and rx.search("x=${BWS_K}"))
    check("os.environ['BWS_K'] is a read", rx.search("os.environ['BWS_K']"))
    check("a bare BWS_K (a scrub's names line) is not a read", not rx.search("            BWS_K"))
    check("a fetch line `> BWS_K` is not a read", not rx.search("K > BWS_K"))
    check("env.BWS_K_PUBLIC is not a read of BWS_K", not rx.search("${{ env.BWS_K_PUBLIC }}"))

    composite = "name: x\nruns:\n  using: composite\n  steps:\n" + "\n".join(
        "  " + ln if ln else ln for ln in PRE_FIX.split("    steps:\n", 1)[1].split("\n")
    )
    check("a composite action's step list is judged", "i" in fired_rules(_scan(composite).findings))

    check(
        "parse_requests is check_bws_map's",
        bws_map_gate().parse_requests.__module__ == BWS_MAP_MODULE,
    )

    rc = _empty_corpus_rc()
    check("the real verdict over an empty corpus is a failure (rc=%d)" % rc, rc == 1)

    if check.count < MIN_CONTROLS:
        print(
            "  FAIL  only %d control(s) ran; the file is not being executed as written"
            % check.count,
            file=sys.stderr,
        )
        return True
    return not check.ok


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if "--selftest" in argv:
            return 1 if selftest() else 0
        rc = controls_first("bws step scope", selftest)
    except InstrumentError as exc:
        print("✗ instrument: %s" % exc, file=sys.stderr)
        return CANNOT_RUN
    if rc:
        return rc
    return verdict(paths.repo_root())


__all__ = [
    "CONFIG_REL",
    "FIXED",
    "PRE_FIX",
    "InstrumentError",
    "Report",
    "bws_map_gate",
    "fired_rules",
    "is_always",
    "judge_job",
    "load_config",
    "main",
    "parse_requests",
    "plants",
    "read_re",
    "scan_jobs",
    "scan_text",
    "selftest",
    "verdict",
]
