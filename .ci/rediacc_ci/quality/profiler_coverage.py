"""Every Linux job must be profiled, and every profiled job configured correctly.

Ported from `.ci/scripts/quality/check-profiler-coverage.sh`, which is NOT deleted; see `rediacc_ci.quality.__init__` for why both copies live until W7 phase 5. The twin's own registration is `kind: test`, covered by `.ci/scripts/test/gates/test-profiler-coverage.sh`, whose BLOCKER reads: `test-profiler-coverage.sh:584 runs the gate seam-free against the real tree inside the
gate-test battery (ci-quality.yml quality-security, "Quality-gate unit tests")`
with the real `.github/workflows`, the real `.profiler-coverage-allowlist`, the
real `.github/actions/profiler/action.yml` and the real floors, so the full 121-job parse and both relations execute every CI run; the 22 fixture cases around it prove every fire direction, including the anti-vacuity refusals (empty dir, missing dir, zero jobs, three floors, missing action.yml) that a real-tree run can never exercise.

-----------------------------------------------------------------------------
THE TWIN'S ARCHAEOLOGY, CARRIED.
-----------------------------------------------------------------------------

WHY. Standard runners are free and unlimited on this public repo, which is exactly what makes oversizing invisible: a job that uses about 1 core on a 4-vCPU ubuntu-latest VM burns four cores' worth of the world's electricity to do one core's work, and no bill ever says so. The profiler action (`.github/actions/profiler`) turns runner sizing into a measurement. A measurement that
covers 20 of 97 jobs measures nothing useful, and coverage maintained by habit decays the moment somebody adds a job in a hurry. This gate makes coverage an INVARIANT instead: a new Linux job is red until it is either profiled or written down here with a reason.

TWO RELATIONS, because there are two ways the wiring is wrong:

  (a) COVERAGE -- a Linux job that does not use the action is invisible to the
      whole exercise.
  (b) CONFIG   -- a job that uses the action with a bad `interval`, an
      undeclared input, or a `runner-label` that disagrees with its own
      `runs-on` produces a profile that LOOKS fine and is wrong. `runner-label`
      arms the HOST_LEAK check; a copy-pasted `runner-label: ubuntu-latest` on
      an ubuntu-slim job disarms it in the dangerous direction (4 cores / 16 GB
      read off a 1-core / 5 GB box).

FAIL-CLOSED ON WHAT IT CANNOT RESOLVE. `runs-on: ${{ inputs.runner }}` cannot be
resolved statically. An unresolvable runner counts as REQUIRING coverage, never as exempt: "we could not tell" must cost an allowlist line with a reason, because the alternative is a silent hole shaped exactly like the ones this repo keeps finding.

COVERAGE IS DIRECT OR THROUGH A VERIFIED WRAPPER. A job is covered when its own steps use the action, or when they use a composite that carries it. Whether a JavaScript action's `post:` hook still fires when the action is nested inside a composite was the open question profiler-probe.yml existed to answer, and on 2026-08-08 it answered YES on real runners (run 31252148469: the
panel appeared on ubuntu-slim and on ubuntu-latest through a composite wrapper). So `./.github/actions/setup-workspace` is a wrapper from here on, and the roughly 26 jobs that already call it are covered without an edit each.

A WRAPPER IS VERIFIED, NOT TRUSTED. Coverage for those jobs now hangs on one `uses:` line inside somebody else's file, and deleting that line would leave 26 jobs reporting as profiled while profiling nothing, a fail-open of exactly the shape this gate exists to prevent. So each wrapper's own `action.yml` must be shown to reference the profiler before it counts, and a wrapper that
stops doing so REFUSES rather than quietly covering nothing.

ANTI-VACUITY. Every extractor self-tests against a planted sample BEFORE the sweep, and the sweep refuses on zero workflows, zero jobs, zero declared action inputs, or counts under the floors. An empty scan is a broken instrument, never a clean tree; this repo has shipped gates that checked zero files for weeks.

TEST SEAMS, all optional, used by `.ci/rediacc_ci/tests/gates/test_gate_profiler_coverage.py`:

  PROFILER_COVERAGE_WORKFLOW_DIR      directory of workflow YAML to scan
  PROFILER_COVERAGE_ALLOWLIST         allowlist path
  PROFILER_COVERAGE_ACTION_DIR        directory holding the profiler action.yml
  PROFILER_COVERAGE_WRAPPER_DIRS      composite dirs that carry the profiler
                                      (each is verified; empty means none)
  PROFILER_COVERAGE_COVERING_ACTIONS  extra `uses:` refs that count as coverage
  PROFILER_COVERAGE_MIN_WORKFLOWS     floor on workflow files parsed
  PROFILER_COVERAGE_MIN_JOBS          floor on jobs parsed
  PROFILER_COVERAGE_MIN_LINUX         floor on Linux jobs found

Usage: python3 -m rediacc_ci.quality.profiler_coverage Exits 0 when both relations hold, 1 on any gap or any refusal.

THE ALLOWLIST is a suppression list and is held to the same BLOCKER quality bar as every other allowlist in the repo, which is why the twin sources `blocker-validator.sh` and why this module reaches `rediacc_ci.core.allowlist`.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE EIGHT EXTRACTORS ARE PORTED AS awk WAS WRITTEN, NOT AS YAML SHOULD BE READ. It is tempting to replace the whole file with a YAML parser, and it would be wrong twice over. First, the twin is the thing this port is judged against, and a real parser answers differently on every workflow the awk mis-reads, which is
where the interesting cases live (`runs-on: ${{ inputs.runner }}`, a matrix
`include:` block, a `uses:` with a trailing comment). Second, PyYAML is not a dependency of this package and adding one to a gate that must run inside the anti-vacuity fixture is how a gate stops being runnable. So the state machines below are transliterations, rule for rule, in awk's evaluation order.

awk's RULE ORDER IS SEMANTICS, and two of these machines depend on it. In `job_block`, the "a new top-level key ends the jobs block" rule does NOT `next`,
so control falls through to `!in_jobs { next }` on the same line; writing the
Python as an if/elif chain in a different order silently changes which line ends a block. Each machine below therefore keeps the twin's order and says so where the order is load-bearing.

`[[:space:]]` UNDER `LC_ALL=C` IS THE ASCII SET MINUS THE NEWLINE, spelled out
rather than written as `\\s`, because Python's `\\s` on a `str` pattern also matches U+00A0 and the other Unicode separators. A non-breaking space in a workflow would then parse differently on the two sides, which is invisible in every ASCII fixture.

`covering_uses` ESCAPES ONLY THE DOT. The twin builds its pattern with
`${ref//./\\.}`, which escapes `.` and nothing else, so a reference containing
another regex metacharacter is a regex on both sides. `re.escape` would be STRICTER and would therefore differ; the twin's exact substitution is reproduced, and the difference is named here rather than improved in silence.

THE INLINE SELF-TEST RUNS ON EVERY INVOCATION, exactly as the twin's does. It is not behind the `--selftest` flag: the twin plants a sample and checks ten extractor answers before it looks at the real tree, and a port that moved that behind a flag would change what a plain run does. `--selftest` is an ADDITION on top, driving the decision function through plants and mirrors the
inline controls cannot express.

THE `mktemp -d` SCRATCH DIRECTORIES ARE GONE and nothing depends on them. The twin writes each job's body to `$WORK_DIR/block.txt` because its extractors take FILES; these take lists of lines. The `trap 'rm -rf ...' EXIT` that cleaned them up, and the second `trap` that had to re-list both directories after the work directory appeared, disappear with them.

EXIT CODES ARE UNCHANGED: 0 and 1 only. Every refusal in the twin is `exit 1`, including the ones a reader might expect to be a setup error, and that is deliberate on the twin's part: an unscannable surface is a broken instrument, not a clean tree, and reporting it as a different class would let a runner treat it as skippable.
"""

import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls
from rediacc_ci.core import allowlist
from rediacc_ci.policy_paths import policy_rel

# `[[:space:]]` in the C locale, minus the newline, which cannot occur inside a line either implementation looks at.
_HS = r"[ \t\r\f\v]"

# The defaults, and the environment names that override them. `${VAR:-default}`
# for all but the wrapper list.
WORKFLOW_DIR_ENV = "PROFILER_COVERAGE_WORKFLOW_DIR"
ALLOWLIST_ENV = "PROFILER_COVERAGE_ALLOWLIST"
ACTION_DIR_ENV = "PROFILER_COVERAGE_ACTION_DIR"
WRAPPER_DIRS_ENV = "PROFILER_COVERAGE_WRAPPER_DIRS"
COVERING_ACTIONS_ENV = "PROFILER_COVERAGE_COVERING_ACTIONS"
MIN_WORKFLOWS_ENV = "PROFILER_COVERAGE_MIN_WORKFLOWS"
MIN_JOBS_ENV = "PROFILER_COVERAGE_MIN_JOBS"
MIN_LINUX_ENV = "PROFILER_COVERAGE_MIN_LINUX"

DEFAULT_WORKFLOW_DIR = ".github/workflows"
# THROUGH THE SEAM (W4 P4a). Still a repo-RELATIVE string, because the twin's
# `${PROFILER_COVERAGE_ALLOWLIST:-.ci/policy/.profiler-coverage-allowlist}` is
# relative too and this gate is compared against it byte for byte.
DEFAULT_ALLOWLIST = policy_rel(".profiler-coverage-allowlist")
DEFAULT_ACTION_DIR = ".github/actions/profiler"

# `${VAR-default}` rather than `${VAR:-default}` ON PURPOSE: a test that sets it
# to the empty string means "no wrappers at all", which is the control for the wrapper path. `os.environ.get(name, default)` is the same distinction.
DEFAULT_WRAPPER_DIRS = ".github/actions/setup-workspace"

# THE FLOORS ARE THE TWIN'S, CARRIED AT THE SAME VALUES. The tree carries 28 workflows / 121 jobs / 97 Linux jobs; anything far under these numbers means the parse found a layout it does not understand, and "all covered" off three jobs is precisely the lie this gate exists to prevent. They are hand-typed in the twin and are NOT re-derived here, because a port that changes a floor
# changes the verdict and the differential would rule MISMATCH on the tree that proves the new floor right.
DEFAULT_MIN_WORKFLOWS = 10
DEFAULT_MIN_JOBS = 60
DEFAULT_MIN_LINUX = 40

# The interval bounds, from the twin's message: below 1 the profiler perturbs the job it measures, above 300 a 15-minute slim job yields under three samples.
INTERVAL_MIN = 1
INTERVAL_MAX = 300


# --------------------------------------------------------------------------- Extractors. Each is self-tested below against a planted sample. ---------------------------------------------------------------------------


def job_keys(lines: list[str]) -> list[str]:
    """One top-level job id per line.

    Job keys are the only 2-space-indented bare keys inside the `jobs:` block;
    bodies sit at 4 spaces or deeper. Scoping to that block keeps `on:`, `permissions:` and `concurrency:` (also 2-space) out.
    """
    out: list[str] = []
    in_jobs = False
    for line in lines:
        if re.match(r"^jobs:%s*$" % _HS, line):
            in_jobs = True
            continue
        if in_jobs and re.match(r"^[^ \t\r\f\v#]", line):
            in_jobs = False
        if in_jobs and re.match(r"^  [A-Za-z0-9_-]+:%s*$" % _HS, line):
            key = line[2:]
            key = re.sub(r":%s*$" % _HS, "", key)
            out.append(key)
    return out


def job_block(lines: list[str], job: str) -> list[str]:
    """The body lines of one job.

    Anchored inside the `jobs:` block so a job named after a trigger (`push`) cannot accidentally match the `on:` section instead.

    RULE ORDER IS LOAD-BEARING HERE. In the twin the "a new top-level key ends the jobs block" rule does not `next`, so the very same line then hits
    `!in_jobs { next }` and is dropped. `job` is interpolated into a REGEX by
    awk, not quoted, so a job id containing a metacharacter is a pattern on both sides; every real id is `[A-Za-z0-9_-]+`.
    """
    out: list[str] = []
    in_jobs = False
    in_job = False
    start = re.compile(r"^  %s:%s*$" % (job, _HS))
    boundary = re.compile(r"^  [A-Za-z0-9_-]+:%s*$" % _HS)
    for line in lines:
        if re.match(r"^jobs:%s*$" % _HS, line):
            in_jobs = True
            continue
        if in_jobs and re.match(r"^[^ \t\r\f\v#]", line):
            in_jobs = False
            in_job = False
        if not in_jobs:
            continue
        if start.match(line):
            in_job = True
            continue
        if in_job and boundary.match(line):
            in_job = False
        if in_job:
            out.append(line)
    return out


def runs_on(block: list[str]) -> str:
    """The raw `runs-on:` value, trailing comment stripped.

    Empty when the job declares none (a reusable-workflow caller, or malformed). The FIRST one wins, which is the `!seen` guard in the twin.
    """
    for line in block:
        if not re.match(r"^    runs-on:", line):
            continue
        value = re.sub(r"^    runs-on:%s*" % _HS, "", line)
        value = re.sub(r"%s+#.*$" % _HS, "", value)
        return re.sub(r"%s*$" % _HS, "", value)
    return ""


def is_caller(block: list[str]) -> bool:
    """True when the job is a reusable-workflow call.

    Such a job has no runner of its own: its steps are the called workflow's jobs, which this gate sees separately in that workflow's file.
    """
    pattern = re.compile(r"^    uses:%s*\./\.github/workflows/" % _HS)
    return any(pattern.search(line) for line in block)


def matrix_values(block: list[str], key: str) -> list[str]:
    """Every literal value the job's `strategy.matrix` gives `key`.

    Across the `include:` form, the inline-list form (`os: [a, b]`) and the block-list form. `key` is interpolated into a regex by the twin, so it is here too.
    """
    out: list[str] = []
    in_strategy = False
    collecting = False
    head = re.compile(r"^%s*(-%s+)?%s:" % (_HS, _HS, key))
    head_sub = re.compile(r"^%s*(-%s+)?%s:%s*" % (_HS, _HS, key, _HS))
    item = re.compile(r"^%s*-%s+[^ \t\r\f\v]" % (_HS, _HS))
    for raw in block:
        if re.match(r"^    strategy:%s*$" % _HS, raw):
            in_strategy = True
            continue
        if in_strategy and re.match(r"^    [A-Za-z0-9_-]+:", raw):
            in_strategy = False
        if not in_strategy:
            continue
        line = re.sub(r"%s+#.*$" % _HS, "", raw)
        if head.match(line):
            value = head_sub.sub("", line, count=1)
            value = re.sub(r"[\[\],]", " ", value)
            value = re.sub(r"[\"']", "", value)
            collecting = bool(re.match(r"^%s*$" % _HS, value))
            out.extend(part for part in re.split(r"%s+" % _HS, value) if part)
            continue
        if collecting and item.match(line):
            value = re.sub(r"^%s*-%s+" % (_HS, _HS), "", line, count=1)
            value = re.sub(r"[\"']", "", value)
            if value:
                out.append(value)
            continue
        collecting = False
    return out


def _uses_pattern(ref: str) -> re.Pattern:
    """The twin's `${ref//./\\.}` substitution, and only that.

    `re.escape` would escape more characters and therefore answer differently on a reference containing another metacharacter. See the PORT NOTES.
    """
    return re.compile(
        r"^%s*(-%s+)?uses:%s*%s%s*(#.*)?$" % (_HS, _HS, _HS, ref.replace(".", r"\."), _HS)
    )


def covering_uses(block: list[str], ref: str) -> int:
    """Count of steps in the job that use `ref` EXACTLY.

    A trailing comment is allowed, a longer path is not, so `.../profiler/nest-probe` does not match `.../profiler`. `grep -c` counts LINES, not occurrences, and a line can carry only one `uses:`.
    """
    pattern = _uses_pattern(ref)
    return sum(1 for line in block if pattern.search(line))


def malformed_refs(block: list[str], ref: str) -> list[str]:
    """`uses:` lines that mention the profiler but are not a legal local ref.

    `uses: .github/actions/profiler` (no leading `./`) is not a local action reference at all: GitHub reads it as owner/repo and the job fails at parse time.
    """
    out: list[str] = []
    for raw in block:
        if "uses:" not in raw or not re.search(r"actions/profiler", raw):
            continue
        line = re.sub(r"%s+#.*$" % _HS, "", raw)
        line = re.sub(r"%s*$" % _HS, "", line)
        # `.*` is greedy, so the LAST `uses:` on the line is the one stripped.
        value = re.sub(r"^.*uses:%s*" % _HS, "", line)
        if value == ref or value == ref + "/nest-probe":
            continue
        out.append(line)
    return out


def _indent(text: str) -> int:
    return len(text) - len(text.lstrip(" "))


def step_inputs(block: list[str], ref: str) -> list[str]:
    """`key=value` for every input passed to the profiler step's `with:` block.

    The `uses:` key column is the anchor: in ` - uses: X` and in the ` uses: X` of a named step, `uses:` starts at the same column as the sibling `with:`, and `with:`'s own keys sit two columns deeper. A non-blank line left of that column ends the step.
    """
    out: list[str] = []
    state = 0
    base = 0
    withcol = -1
    for raw in block:
        line = re.sub(r"%s+#.*$" % _HS, "", raw)
        line = re.sub(r"%s*$" % _HS, "", line)
        if state == 0 and "uses:" in line:
            value = re.sub(r"^.*uses:%s*" % _HS, "", line)
            if value == ref:
                base = line.index("uses:")
                state = 1
                withcol = -1
            continue
        if state == 0:
            continue
        if line == "":
            continue
        if _indent(line) < base:
            state = 0
            continue
        if state == 1 and re.match(r"^ *with:%s*$" % _HS, line):
            withcol = _indent(line)
            state = 2
            continue
        if state == 2 and _indent(line) <= withcol:
            state = 1
            continue
        if state == 2 and _indent(line) == withcol + 2 and re.match(r"^ *[A-Za-z0-9_-]+:", line):
            key = re.sub(r":.*$", "", line.lstrip(" "))
            value = re.sub(r"^ *[A-Za-z0-9_-]+:%s*" % _HS, "", line)
            value = re.sub(r'^["\']', "", value)
            value = re.sub(r'["\']$', "", value)
            out.append("%s=%s" % (key, value))
    return out


def declared_inputs(lines: list[str]) -> list[str]:
    """One declared input name per line, out of an `action.yml`."""
    out: list[str] = []
    in_inputs = False
    for line in lines:
        if re.match(r"^inputs:%s*$" % _HS, line):
            in_inputs = True
            continue
        if in_inputs and re.match(r"^[^ \t\r\f\v#]", line):
            in_inputs = False
        if in_inputs and re.match(r"^  [A-Za-z0-9_-]+:%s*$" % _HS, line):
            out.append(re.sub(r":%s*$" % _HS, "", line[2:]))
    return out


LINUX = 0
NOT_LINUX = 1
UNKNOWN = 2


def is_linux_label(label: str) -> int:
    """0 linux, 1 not linux, 2 unknown. The twin's return codes, kept."""
    if label.startswith("ubuntu-"):
        return LINUX
    if label.startswith(("macos-", "windows-")):
        return NOT_LINUX
    return UNKNOWN


# --------------------------------------------------------------------------- The inline self-test, which runs on EVERY invocation ---------------------------------------------------------------------------

SAMPLE = """\
on:
  workflow_dispatch:
jobs:
  selftest-job:
    name: Selftest
    runs-on: ${{ matrix.runner }}  # trailing comment
    strategy:
      matrix:
        include:
          - runner: ubuntu-slim
    steps:
      - uses: ./.github/actions/profiler
        with:
          interval: '7'
          runner-label: ubuntu-slim
  selftest-caller:
    uses: ./.github/workflows/other.yml
"""

SAMPLE_REF = "./.github/actions/profiler"


def _selftest_fail(name: str, got: object, want: str) -> int:
    log.error(
        "SELF-TEST FAILED: extractor '%s' produced '%s', expected '%s'"
        % (name, got if got not in ("", [], None) else "<nothing>", want)
    )
    log.error(
        "The extractor is broken; the sweep below would silently under-report instead of failing."
    )
    return 1


def inline_selftest() -> int:
    """Every extractor must produce its known answer from a planted sample.

    An extractor that silently stopped matching would under-report coverage, which reads exactly like a clean tree. Returns 0 or 1; the caller exits.
    """
    lines = records(SAMPLE)

    got = ",".join(job_keys(lines)) + ","
    if got != "selftest-job,selftest-caller,":
        return _selftest_fail("job_keys", got, "selftest-job,selftest-caller,")

    block = job_block(lines, "selftest-job")
    caller = job_block(lines, "selftest-caller")

    got = runs_on(block)
    if got != "${{ matrix.runner }}":
        return _selftest_fail("runs_on", got, "${{ matrix.runner }}")

    if not is_caller(caller):
        return _selftest_fail("is_caller", "", "yes")
    if is_caller(block):
        return _selftest_fail("is_caller(negative)", "yes", "<nothing>")

    got = ",".join(matrix_values(block, "runner")) + ","
    if got != "ubuntu-slim,":
        return _selftest_fail("matrix_values", got, "ubuntu-slim,")

    if covering_uses(block, SAMPLE_REF) != 1:
        return _selftest_fail("covering_uses", covering_uses(block, SAMPLE_REF), "1")
    if covering_uses(caller, SAMPLE_REF) != 0:
        return _selftest_fail("covering_uses(negative)", covering_uses(caller, SAMPLE_REF), "0")

    # LC_ALL=C: same sibling risk as test_gate_scope_gate_outputs.py (see
    # docs/agent-reference/TRAPS.md). A shell `sort` compared against a hand-written literal is locale-dependent by construction. Currently correct under en_US.UTF-8 only because 'i' < 'r' in both orderings; pinned
    # so it stays correct everywhere rather than by luck. `sorted(key=encode)`
    # is that byte sort.
    got = ",".join(sorted(step_inputs(block, SAMPLE_REF), key=str.encode)) + ","
    if got != "interval=7,runner-label=ubuntu-slim,":
        return _selftest_fail("step_inputs", got, "interval=7,runner-label=ubuntu-slim,")

    bad = ["      - uses: .github/actions/profiler"]
    if not malformed_refs(bad, SAMPLE_REF):
        return _selftest_fail("malformed_refs", "<nothing>", "the malformed uses line")
    if malformed_refs(block, SAMPLE_REF):
        return _selftest_fail(
            "malformed_refs(negative)", malformed_refs(block, SAMPLE_REF), "<nothing>"
        )
    return 0


# --------------------------------------------------------------------------- The sweep ---------------------------------------------------------------------------


def records(text: str) -> list[str]:
    """awk's records, not Python's `split`.

    THE ONE-ELEMENT DIFFERENCE THAT IS NOT COSMETIC. A POSIX text file ends with a newline, and awk reads it as N records; `str.split("\n")` reads it as N+1, the last being the empty string. That phantom record sits INSIDE the last job's block, so `job_block` emitted one extra blank line and the port and the twin disagreed byte for byte on the final job of every workflow.

    It changes no verdict today -- every consumer either skips a blank line or is unaffected by one, which is why the shadow differential over five trees and the real 124-job tree all read EQUIVALENT. It is still fixed rather than documented as harmless: the next consumer added to `job_block`'s output will not know the phantom is there, and "harmless" is a property of today's
    callers rather than of the data.

    Only ONE trailing empty element is dropped, because a file ending in two newlines really does have a trailing blank record and awk prints it.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _read(path: pathlib.Path) -> list[str]:
    return records(path.read_text(encoding="utf-8", errors="replace"))


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 when both relations hold, 1 on any gap or refusal."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    workflow_dir = os.environ.get(WORKFLOW_DIR_ENV) or DEFAULT_WORKFLOW_DIR
    allowlist_path = os.environ.get(ALLOWLIST_ENV) or DEFAULT_ALLOWLIST
    action_dir = os.environ.get(ACTION_DIR_ENV) or DEFAULT_ACTION_DIR
    # `read -r -a` splits on IFS whitespace and drops empties, which is what `.split()` with no argument does.
    wrapper_dirs = os.environ.get(WRAPPER_DIRS_ENV, DEFAULT_WRAPPER_DIRS).split()
    extra_covering = (os.environ.get(COVERING_ACTIONS_ENV) or "").split()
    min_workflows = int(os.environ.get(MIN_WORKFLOWS_ENV) or DEFAULT_MIN_WORKFLOWS)
    min_jobs = int(os.environ.get(MIN_JOBS_ENV) or DEFAULT_MIN_JOBS)
    min_linux = int(os.environ.get(MIN_LINUX_ENV) or DEFAULT_MIN_LINUX)

    # The twin `cd`s to the repository root, so every path above is relative to it and every path PRINTED is relative too.
    os.chdir(str(root))

    if inline_selftest() != 0:
        return 1

    # -- The action contract ------------------------------------------------- Input names come from the real action.yml, never from a list hand-copied here that would drift the day an input is added.
    action_yml = pathlib.Path(action_dir) / "action.yml"
    if not action_yml.is_file():
        log.error("profiler action not found at %s" % action_yml)
        log.error(
            "This gate derives the input contract from that file; without it, it can "
            "assert nothing. Fix the path, do not skip the check."
        )
        return 1

    action_ref = "./%s" % action_dir
    declared = declared_inputs(_read(action_yml))
    if len(declared) < 1:
        log.error(
            "parsed ZERO inputs from %s; the action declares some, so the parser is broken"
            % action_yml
        )
        return 1

    # -- The wrapper contract ------------------------------------------------ A composite counts as coverage only once it is SHOWN to reference the profiler, using the same matcher the job sweep uses, so the day somebody edits that line out this gate goes red instead of certifying 26 jobs as profiled.
    covering_actions: list[str] = []
    for raw_dir in wrapper_dirs:
        if not raw_dir:
            continue
        wdir = raw_dir.removeprefix("./")
        wyml = pathlib.Path(wdir) / "action.yml"
        if not wyml.is_file():
            log.error("covering wrapper '%s' has no action.yml at %s" % (wdir, wyml))
            log.error(
                "Every job counted as covered through this wrapper would be counted off "
                "a file that does not exist. Fix the path, do not drop the check."
            )
            return 1
        if covering_uses(_read(wyml), action_ref) < 1:
            log.error("covering wrapper '%s' does not use %s" % (wdir, action_ref))
            log.error(
                "It is treated as coverage for every job that calls it, so without that "
                "step those jobs are unprofiled while reporting as profiled -- the exact "
                "fail-open this gate exists to prevent."
            )
            return 1
        covering_actions.append("./%s" % wdir)
    covering_actions.extend(extra_covering)

    # -- The allowlist -------------------------------------------------------
    allow_entries: dict[str, str] = {}
    allow_path = pathlib.Path(allowlist_path)
    if allow_path.is_file():
        entries = allowlist.parse_file(allow_path, missing_ok=True)
        allow_entries = allowlist.pairs(entries)
        failures = [
            message
            for entry, reason in allow_entries.items()
            for message in _verify_one(entry, reason, str(allow_path))
        ]
        if failures:
            for message in failures:
                head, _, tail = message.partition("\n")
                # `ci_error`, not `log.error`: the twin's head line comes from `verify_all_blockers`, which is `ci_error`. The tail is a plain `echo` on both sides and stays on stdout.
                ci_error(head)
                if tail:
                    print(tail)
            log.error(
                "An entry in %s is a hole in the 'every Linux job is profiled' invariant."
                % allowlist_path
            )
            log.error(
                "It must say WHY that job cannot carry the profiler, not that it does not yet."
            )
            return 1

    # -- The sweep -----------------------------------------------------------
    wdir_path = pathlib.Path(workflow_dir)
    if not wdir_path.is_dir():
        log.error("workflow directory not found: %s" % workflow_dir)
        log.error("An unscannable surface is a broken instrument, not a clean tree.")
        return 1

    # `find -maxdepth 1 -type f \( -name '*.yml' -o -name '*.yaml' \) | sort`.
    workflows = sorted(
        (
            str(entry)
            for entry in wdir_path.iterdir()
            if entry.is_file() and entry.suffix in (".yml", ".yaml")
        ),
        key=str.encode,
    )
    if not workflows:
        log.error("found ZERO workflow files under %s" % workflow_dir)
        log.error(
            "This gate cannot report a clean tree off an empty scan. Fix the path, "
            "do not skip the check."
        )
        return 1
    if len(workflows) < min_workflows:
        log.error(
            "found only %d workflow file(s) under %s (floor: %d); the scan surface is "
            "wrong, not clean" % (len(workflows), workflow_dir, min_workflows)
        )
        return 1

    total_jobs = 0
    linux_jobs = 0
    covered_linux = 0
    caller_jobs = 0
    failures_count = 0
    required_uncovered: dict[str, str] = {}
    known_keys: dict[str, str] = {}

    for wf in workflows:
        base = os.path.basename(wf)
        lines = _read(pathlib.Path(wf))
        for job in job_keys(lines):
            if not job:
                continue
            key = "%s:%s" % (base, job)
            known_keys[key] = "1"
            total_jobs += 1
            block = job_block(lines, job)

            # (b) CONFIGURATION -- checked for every job that uses the action, on any OS, because a misconfigured profile is wrong wherever it runs.
            for bad in malformed_refs(block, action_ref):
                if not bad:
                    continue
                log.error("%s: malformed profiler reference: %s" % (key, bad.removeprefix(" ")))
                log.error(
                    "  A local action must be referenced as '%s' (leading './' required); "
                    "anything else is read as owner/repo and fails at workflow parse time."
                    % action_ref
                )
                failures_count += 1

            uses_count = covering_uses(block, action_ref)
            covered_count = uses_count
            for extra in covering_actions:
                covered_count += covering_uses(block, extra)
            if uses_count > 1:
                log.error(
                    "%s: uses the profiler %d times; the post hook runs once per action "
                    "instance and the panels would interleave" % (key, uses_count)
                )
                failures_count += 1

            declared_runs_on = runs_on(block)

            if uses_count >= 1:
                seen_runner_label = ""
                for kv in step_inputs(block, action_ref):
                    if not kv:
                        continue
                    k, _, v = kv.partition("=")
                    if k not in declared:
                        log.error(
                            "%s: passes input '%s', which %s does not declare (declared: %s)"
                            % (key, k, action_yml, " ".join(declared) + " ")
                        )
                        failures_count += 1
                        continue
                    if k == "interval":
                        if not re.fullmatch(r"[0-9]+", v):
                            log.error(
                                "%s: interval '%s' is not an integer; the sampler sleeps for "
                                "it, and a non-numeric value makes the sample loop spin or die"
                                % (key, v)
                            )
                            failures_count += 1
                        elif int(v) < INTERVAL_MIN or int(v) > INTERVAL_MAX:
                            log.error(
                                "%s: interval '%s' is outside 1..300s; below 1 the profiler "
                                "perturbs the job it measures, above 300 a 15-minute slim job "
                                "yields under three samples" % (key, v)
                            )
                            failures_count += 1
                    elif k == "strict":
                        if v not in ("true", "false"):
                            log.error(
                                "%s: strict '%s' is neither 'true' nor 'false'; every other "
                                "value is truthy to the action and silently arms hard failure"
                                % (key, v)
                            )
                            failures_count += 1
                    elif k == "runner-label":
                        seen_runner_label = v
                        if not v:
                            log.error(
                                "%s: runner-label is empty, which disarms the HOST_LEAK check "
                                "the label exists to arm" % key
                            )
                            failures_count += 1
                        elif (
                            not v.startswith("${{")
                            and declared_runs_on
                            and not declared_runs_on.startswith("${{")
                            and v != declared_runs_on
                        ):
                            log.error(
                                "%s: runner-label '%s' disagrees with runs-on '%s'; the "
                                "sampler would size the job against the wrong runner and "
                                "every conclusion drawn from it is wrong"
                                % (key, v, declared_runs_on)
                            )
                            failures_count += 1

                if not seen_runner_label:
                    log.error(
                        "%s: uses the profiler without runner-label. Unlabelled costs two "
                        "things: HOST_LEAK cannot fire at all (sampler-linux.sh:209-222 arms "
                        "it off the label), and at PROC_HOST tier the advisor goes MUTE "
                        "rather than wrong (report.awk advise(): 'a VM cannot be told from a "
                        "container'), so the job is profiled and yields no advice. At a "
                        "cgroup tier the enforced quota substitutes for the label, so the "
                        "loss there is only HOST_LEAK." % key
                    )
                    failures_count += 1

            # (a) COVERAGE
            if is_caller(block):
                caller_jobs += 1
                known_keys[key] = "caller"
                continue

            if not declared_runs_on:
                log.error(
                    "%s: has neither 'runs-on:' nor a reusable-workflow 'uses:'; this gate "
                    "cannot classify it and refuses to guess" % key
                )
                failures_count += 1
                continue

            labels: list[str] = []
            unresolved = ""
            if declared_runs_on.startswith("${{ matrix."):
                mkey = declared_runs_on.split("matrix.", 1)[1]
                mkey = re.match(r"^[A-Za-z0-9_-]*", mkey).group(0)
                labels = matrix_values(block, mkey)
                if not labels:
                    unresolved = "matrix.%s has no literal values in this job" % mkey
            elif declared_runs_on.startswith("${{"):
                unresolved = (
                    "runs-on is the expression '%s', which no static parse can resolve"
                    % declared_runs_on
                )
            else:
                stripped = re.sub(r"[\[\],]", "", declared_runs_on)
                labels = [part for part in stripped.split(" ") if part]

            required = False
            reason = ""
            if unresolved:
                # Fail-closed: unresolvable means "we could not prove it is not Linux", and that must cost a line in the allowlist.
                required = True
                reason = unresolved
            else:
                for label in labels:
                    if not label:
                        continue
                    verdict = is_linux_label(label)
                    if verdict == LINUX:
                        required = True
                        reason = "runs on %s" % label
                    elif verdict == UNKNOWN:
                        required = True
                        reason = (
                            "runner label '%s' is neither ubuntu-*, macos-* nor windows-*; "
                            "add it to is_linux_label rather than letting an unknown runner "
                            "go unprofiled" % label
                        )

            if not required:
                known_keys[key] = "nonlinux"
                continue

            linux_jobs += 1
            known_keys[key] = "required"

            if covered_count >= 1:
                covered_linux += 1
                continue

            required_uncovered[key] = reason

    if total_jobs == 0:
        log.error(
            "parsed ZERO jobs from %d workflow file(s) under %s" % (len(workflows), workflow_dir)
        )
        log.error(
            "Every workflow declares jobs, so the parser is broken. This is not a clean tree."
        )
        return 1
    if total_jobs < min_jobs:
        log.error(
            "parsed only %d job(s) (floor: %d); the job parser found a layout it does not "
            "understand" % (total_jobs, min_jobs)
        )
        return 1
    if linux_jobs < min_linux:
        log.error(
            "classified only %d job(s) as needing a profile (floor: %d); the runner "
            "classifier is broken, so 'all covered' would be vacuous" % (linux_jobs, min_linux)
        )
        return 1

    # -- Verdict (a): uncovered jobs, minus the allowlist ---------------------
    uncovered = 0
    for key in sorted(required_uncovered, key=str.encode):
        if allow_entries.get(key):
            continue
        log.error("%s: %s but does not use %s" % (key, required_uncovered[key], action_ref))
        uncovered += 1

    if uncovered > 0:
        log.error("%d Linux job(s) are unprofiled. Add a step to each:" % uncovered)
        log.error("      - uses: %s" % action_ref)
        log.error("        with:")
        log.error("          runner-label: <the job's runs-on label>")
        log.error(
            "or add '<workflow>.yml:<job>' to %s with a '# BLOCKER: <reason>' saying why "
            "it cannot carry one." % allowlist_path
        )
        failures_count += uncovered

    # -- Verdict (a'): allowlist liveness ------------------------------------- An entry is stale the moment its job disappears, becomes covered, or stops needing coverage, so this list can only shrink and the rollout cannot leave paid-down debt sitting in it.
    stale = 0
    for key in sorted(allow_entries, key=str.encode):
        kind = known_keys.get(key, "")
        if not kind:
            log.error(
                "%s: '%s' names no job in %s; it suppresses nothing"
                % (allowlist_path, key, workflow_dir)
            )
            stale += 1
        elif kind == "caller":
            log.error(
                "%s: '%s' is a reusable-workflow caller, which has no runner of its own and "
                "was never required; drop the entry" % (allowlist_path, key)
            )
            stale += 1
        elif kind == "nonlinux":
            log.error(
                "%s: '%s' does not run on Linux, so it was never required; drop the entry"
                % (allowlist_path, key)
            )
            stale += 1
        elif not required_uncovered.get(key):
            log.error(
                "%s: '%s' IS profiled now; drop the entry (an exemption that exempts nothing "
                "hides the next real one)" % (allowlist_path, key)
            )
            stale += 1

    if stale > 0:
        log.error(
            "%d stale entr(ies) in %s. Remove them; this list is only ever allowed to shrink."
            % (stale, allowlist_path)
        )
        failures_count += stale

    if failures_count > 0:
        return 1

    # THE SHAPE, NOT JUST THE VERDICT.
    log.info(
        "profiler coverage: %d/%d Linux job(s) profiled, %d allowlisted, across %d job(s) "
        "in %d workflow(s) (%d reusable-workflow caller(s) excluded)"
        % (
            covered_linux,
            linux_jobs,
            len(allow_entries),
            total_jobs,
            len(workflows),
            caller_jobs,
        )
    )
    return 0


def _in_ci() -> bool:
    """`[[ "${CI:-}" == "true" ]]`, the exact test the shell libraries use."""
    return os.environ.get("CI", "") == "true"


def ci_error(message: str) -> None:
    """`::error::<m>` on stdout under CI, `log_error <m>` on stderr otherwise.

    THE TWIN REACHES THIS THROUGH `blocker-validator.sh`, WHICH REACHES `emit-advisory.sh:136`. Every head line `verify_all_blockers` prints -- the missing reason, the low-effort placeholder, the routine-bump deferral and the too-short reason -- goes through `ci_error`, while the CONTINUATION lines beneath each are plain `echo` to stdout and the gate's own two "this is a hole in
    the invariant" lines are plain `log_error` to stderr. Three different renderings in one failure, and only the head moves stream.

    THIS WAS A REAL PORT GAP, found by the W7 P4 batch 8a cutover differential
    and not by any test. Driven with CI=true against an allowlist entry whose
    BLOCKER had been reset by an inserted blank line, the twin put `::error::Allowlist ...` on STDOUT and this port put `✗ Allowlist ...` on STDERR: same exit code, same words, different stream and different prefix.
    Under `CI=true`, which is how CI runs it, the annotation is what surfaces
    the finding in the Actions UI, so losing it is losing the report while keeping the red. `go_deps.py:220` and `swallowed_failures.py:525` carry the same helper for the same reason.
    """
    if _in_ci():
        print("::error::%s" % message)
    else:
        log.error(message)


def _verify_one(entry: str, reason: str, file: str) -> list[str]:
    """`verify_all_blockers`, for one entry. Zero or one message."""
    if not reason:
        return [allowlist.missing_reason(entry, file)]
    rejection = allowlist.validate_reason(entry, reason, file)
    return [] if rejection is None else [rejection.message]


# --------------------------------------------------------------------------- The selftest, which is an ADDITION on top of the inline controls ---------------------------------------------------------------------------

_ACTION_YML = """\
name: profiler
inputs:
  interval:
    description: seconds
  runner-label:
    description: label
  strict:
    description: fail hard
runs:
  using: node20
"""

_WRAPPER_YML = """\
name: setup-workspace
runs:
  using: composite
  steps:
    - uses: ./.github/actions/profiler
      with:
        runner-label: ubuntu-slim
"""

_GOOD_REASON = "this job runs on a self-hosted box with no writable temp for the sampler"

# The fixture mirrors the tree's own layout so that the `uses:` strings planted in a workflow are the strings the gate resolves. See the note on `build`.
WF_DIR = ".github/workflows"
ACT_DIR = ".github/actions/profiler"
WRAP_DIR = ".github/actions/setup-workspace"


def _workflow(jobs: str) -> str:
    return "on:\n  workflow_dispatch:\njobs:\n%s" % jobs


def _profiled_job(name: str, label: str = "ubuntu-slim") -> str:
    return (
        "  %s:\n    runs-on: %s\n    steps:\n"
        "      - uses: ./.github/actions/profiler\n"
        "        with:\n          runner-label: %s\n" % (name, label, label)
    )


def _bare_job(name: str, label: str = "ubuntu-slim") -> str:
    return "  %s:\n    runs-on: %s\n    steps:\n      - run: echo hi\n" % (name, label)


def selftest() -> int:
    """Both directions on every extractor, then the gate on real trees."""
    ctl = Controls("profiler-coverage", floor=30, verbose=True)

    sample = records(SAMPLE)
    block = job_block(sample, "selftest-job")
    caller = job_block(sample, "selftest-caller")

    ctl.check(
        "EXTRACT: job_keys reads both jobs", job_keys(sample), ["selftest-job", "selftest-caller"]
    )
    ctl.check(
        "EXTRACT MIRROR: the top-level `on:` block contributes no job key",
        [k for k in job_keys(sample) if k == "workflow_dispatch"],
        [],
    )
    ctl.check(
        "EXTRACT: runs_on strips the trailing comment", runs_on(block), "${{ matrix.runner }}"
    )
    ctl.check("EXTRACT: runs_on is empty for a caller", runs_on(caller), "")
    ctl.truthy("EXTRACT: is_caller fires on a reusable-workflow call", is_caller(caller))
    ctl.falsy("EXTRACT MIRROR: is_caller does not fire on a normal job", is_caller(block))
    ctl.check(
        "EXTRACT: matrix_values reads an include block",
        matrix_values(block, "runner"),
        ["ubuntu-slim"],
    )
    ctl.check(
        "EXTRACT MIRROR: matrix_values answers nothing for an absent key",
        matrix_values(block, "nosuchkey"),
        [],
    )
    ctl.check(
        "EXTRACT: covering_uses counts the profiler step", covering_uses(block, SAMPLE_REF), 1
    )
    ctl.check(
        "EXTRACT MIRROR: covering_uses counts nothing in a caller",
        covering_uses(caller, SAMPLE_REF),
        0,
    )
    ctl.check(
        "EXTRACT: a longer path is NOT the same action",
        covering_uses(["      - uses: ./.github/actions/profiler/nest-probe"], SAMPLE_REF),
        0,
    )
    ctl.check(
        "EXTRACT: step_inputs reads the with: block",
        sorted(step_inputs(block, SAMPLE_REF), key=str.encode),
        ["interval=7", "runner-label=ubuntu-slim"],
    )
    ctl.truthy(
        "EXTRACT: a `uses:` without './' is malformed",
        malformed_refs(["      - uses: .github/actions/profiler"], SAMPLE_REF),
    )
    ctl.falsy(
        "EXTRACT MIRROR: the correct reference is not malformed", malformed_refs(block, SAMPLE_REF)
    )
    ctl.check(
        "EXTRACT: declared_inputs reads an action.yml",
        declared_inputs(records(_ACTION_YML)),
        ["interval", "runner-label", "strict"],
    )
    ctl.check("LABEL: ubuntu-* is linux", is_linux_label("ubuntu-slim"), LINUX)
    ctl.check("LABEL: macos-* is not linux", is_linux_label("macos-14"), NOT_LINUX)
    ctl.check("LABEL: windows-* is not linux", is_linux_label("windows-latest"), NOT_LINUX)
    ctl.check(
        "LABEL: anything else is UNKNOWN, never 'not linux'", is_linux_label("self-hosted"), UNKNOWN
    )
    ctl.check("INLINE: the gate's own pre-sweep controls pass", inline_selftest(), 0)

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        saved_cwd = os.getcwd()

        # THE FIXTURE USES THE REAL PATHS, and the first cut of it did not. Pointing ACTION_DIR at `action` while every planted workflow still said `uses: ./.github/actions/profiler` meant the action_ref was `./action`, nothing matched it, and three controls failed on the WRAPPER contract before the sweep they were written for ever ran. A control that fires for the wrong reason is
        # worse than one that does not fire, so the fixture now mirrors the tree's own layout and the literal refs in the workflows are the refs the gate resolves.
        def build(name: str, workflows: dict[str, str], allow: str | None = None) -> pathlib.Path:
            tree = base / name
            (tree / WF_DIR).mkdir(parents=True, exist_ok=True)
            for filename, body in workflows.items():
                (tree / WF_DIR / filename).write_text(body, encoding="utf-8")
            (tree / ACT_DIR).mkdir(parents=True, exist_ok=True)
            (tree / ACT_DIR / "action.yml").write_text(_ACTION_YML, encoding="utf-8")
            (tree / WRAP_DIR).mkdir(parents=True, exist_ok=True)
            (tree / WRAP_DIR / "action.yml").write_text(_WRAPPER_YML, encoding="utf-8")
            if allow is not None:
                (tree / "allow").write_text(allow, encoding="utf-8")
            return tree

        def run(tree: pathlib.Path, **over: str) -> int:
            names = {
                paths.ROOT_ENV: str(tree),
                WORKFLOW_DIR_ENV: WF_DIR,
                ALLOWLIST_ENV: "allow",
                ACTION_DIR_ENV: ACT_DIR,
                WRAPPER_DIRS_ENV: WRAP_DIR,
                COVERING_ACTIONS_ENV: "",
                MIN_WORKFLOWS_ENV: "1",
                MIN_JOBS_ENV: "1",
                MIN_LINUX_ENV: "1",
            }
            names.update(over)
            saved = {k: os.environ.get(k) for k in names}
            os.environ.update(names)
            try:
                return main([])
            finally:
                os.chdir(saved_cwd)
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

        clean = build("clean", {"a.yml": _workflow(_profiled_job("build"))})
        ctl.check("CONTROL: one profiled Linux job passes", run(clean), 0)

        bare = build("bare", {"a.yml": _workflow(_bare_job("build"))})
        ctl.check("PLANT: an unprofiled Linux job is caught", run(bare), 1)

        allowed = build(
            "allowed",
            {"a.yml": _workflow(_bare_job("build"))},
            "# BLOCKER: %s\na.yml:build\n" % _GOOD_REASON,
        )
        ctl.check("SUPPRESSION: a BLOCKER-ed allowlist entry silences it", run(allowed), 0)

        stale = build(
            "stale",
            {"a.yml": _workflow(_profiled_job("build"))},
            "# BLOCKER: %s\na.yml:build\n" % _GOOD_REASON,
        )
        ctl.check("LIVENESS: an entry whose job IS profiled is stale", run(stale), 1)

        low_effort = build(
            "low-effort",
            {"a.yml": _workflow(_bare_job("build"))},
            "# BLOCKER: tbd\na.yml:build\n",
        )
        ctl.check("PLANT: a low-effort BLOCKER is refused", run(low_effort), 1)

        macos = build("macos", {"a.yml": _workflow(_bare_job("build", "macos-14"))})
        ctl.check(
            "MIRROR: a macOS job needs no profile, so the LINUX floor refuses instead",
            run(macos, **{MIN_LINUX_ENV: "0"}),
            0,
        )

        unknown = build("unknown", {"a.yml": _workflow(_bare_job("build", "self-hosted"))})
        ctl.check("FAIL-CLOSED: an unknown runner label REQUIRES coverage", run(unknown), 1)

        expression = build(
            "expression",
            {
                "a.yml": _workflow(
                    "  build:\n    runs-on: ${{ inputs.runner }}\n    steps:\n      - run: x\n"
                )
            },
        )
        ctl.check("FAIL-CLOSED: an unresolvable runs-on REQUIRES coverage", run(expression), 1)

        malformed = build(
            "malformed",
            {
                "a.yml": _workflow(
                    "  build:\n    runs-on: ubuntu-slim\n    steps:\n"
                    "      - uses: .github/actions/profiler\n"
                )
            },
        )
        ctl.check("PLANT: a `uses:` without './' is caught", run(malformed), 1)

        bad_interval = build(
            "bad-interval",
            {
                "a.yml": _workflow(
                    "  build:\n    runs-on: ubuntu-slim\n    steps:\n"
                    "      - uses: ./.github/actions/profiler\n"
                    "        with:\n          interval: '9000'\n          runner-label: ubuntu-slim\n"
                )
            },
        )
        ctl.check("PLANT: an out-of-range interval is caught", run(bad_interval), 1)

        undeclared = build(
            "undeclared",
            {
                "a.yml": _workflow(
                    "  build:\n    runs-on: ubuntu-slim\n    steps:\n"
                    "      - uses: ./.github/actions/profiler\n"
                    "        with:\n          nosuch: x\n          runner-label: ubuntu-slim\n"
                )
            },
        )
        ctl.check("PLANT: an undeclared input is caught", run(undeclared), 1)

        mismatched = build(
            "mismatched",
            {
                "a.yml": _workflow(
                    "  build:\n    runs-on: ubuntu-slim\n    steps:\n"
                    "      - uses: ./.github/actions/profiler\n"
                    "        with:\n          runner-label: ubuntu-latest\n"
                )
            },
        )
        ctl.check("PLANT: a runner-label disagreeing with runs-on is caught", run(mismatched), 1)

        unlabelled = build(
            "unlabelled",
            {
                "a.yml": _workflow(
                    "  build:\n    runs-on: ubuntu-slim\n    steps:\n"
                    "      - uses: ./.github/actions/profiler\n"
                )
            },
        )
        ctl.check("PLANT: the profiler without a runner-label is caught", run(unlabelled), 1)

        # -- THE REFUSALS, which are the whole anti-vacuity half ---------------
        empty = build("empty", {})
        ctl.check("VACUITY: zero workflow files is a refusal", run(empty), 1)
        ctl.check(
            "VACUITY: a missing workflow directory is a refusal",
            run(clean, **{WORKFLOW_DIR_ENV: "nosuchdir"}),
            1,
        )
        ctl.check(
            "VACUITY: a missing profiler action.yml is a refusal",
            run(clean, **{ACTION_DIR_ENV: "nosuchdir"}),
            1,
        )
        ctl.check(
            "VACUITY: a wrapper with no action.yml is a refusal",
            run(clean, **{WRAPPER_DIRS_ENV: "nosuchwrapper"}),
            1,
        )
        ctl.check(
            "VACUITY: the workflow floor refuses a scan that lost the corpus",
            run(clean, **{MIN_WORKFLOWS_ENV: "99"}),
            1,
        )
        ctl.check(
            "VACUITY: the job floor refuses a parse that lost the jobs",
            run(clean, **{MIN_JOBS_ENV: "99"}),
            1,
        )
        ctl.check(
            "VACUITY: the Linux floor refuses a classifier that lost the runners",
            run(clean, **{MIN_LINUX_ENV: "99"}),
            1,
        )

        # A WRAPPER THAT NO LONGER CARRIES THE PROFILER must REFUSE rather than quietly covering every job that calls it. This is the fail-open the gate exists to prevent, driven for real.
        broken_wrapper = build("broken-wrapper", {"a.yml": _workflow(_profiled_job("build"))})
        (broken_wrapper / WRAP_DIR / "action.yml").write_text(
            "name: setup-workspace\nruns:\n  using: composite\n  steps:\n    - run: echo hi\n",
            encoding="utf-8",
        )
        ctl.check(
            "FAIL-OPEN: a wrapper that stopped using the profiler refuses", run(broken_wrapper), 1
        )

        # ...and the mirror: a job covered ONLY through a verified wrapper is covered. Without this the wrapper path could be dead code.
        wrapped = build(
            "wrapped",
            {
                "a.yml": _workflow(
                    "  build:\n    runs-on: ubuntu-slim\n    steps:\n"
                    "      - uses: ./%s\n" % WRAP_DIR
                )
            },
        )
        ctl.check("WRAPPER: a job covered only through the wrapper passes", run(wrapped), 0)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
