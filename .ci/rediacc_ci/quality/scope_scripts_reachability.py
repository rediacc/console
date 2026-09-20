r"""Every ROOT `scripts/` path reachable from non-quality CI code must classify FULL.

Ported from `.ci/scripts/quality/check-scope-scripts-reachability.sh`, which is NOT deleted; see `rediacc_ci.quality.__init__` for why both copies live.

WHY THIS EXISTS, in the twin's own words, because the failure is invisible:

    On 2026-08-06 the blanket `scripts/` harness rule in
    .ci/scripts/ci/scope-map.cjs was narrowed: gate sources became a zero-job
    `gates` module so an attribution-URL check would stop running the ceph fork
    test. Two subsets were carved out to stay full because a GATED job genuinely
    executes them -- scripts/drills/ and scripts/gen/generate-third-party-licenses.ts.

    That carve-out list was traced BY HAND, once, at one commit. Nothing stopped
    the next reachable file from being added and silently narrowed: a new
    scripts/foo.sh invoked from a build or deploy script would classify as
    `gates`, pull nothing into scope, and the job that depends on it would be
    skipped on the very delta that changed it. The failure is invisible -- CI goes
    green faster, and nobody looks for a job that was never scheduled.

    THE INVARIANT, and why it is drawn here. A root scripts/ path referenced from
    .github/workflows/ or from the BUILD/DEPLOY/SETUP/PRIVATE halves of
    .ci/scripts is reachable from a gated job, so it must force full. Paths
    referenced only from .ci/scripts/quality/ or .ci/scripts/test/ are
    quality-lane consumers, and narrowing those is the entire point of the split
    -- quality lanes carry no run_* gate at all (ci-quality.yml has zero `run_`
    references), so the engine cannot skip them however a path classifies.

    CONTROL-FIRST. Before judging real paths this plants a synthetic reachable
    path and asserts the checker calls it a violation. If the control cannot fire,
    the gate exits non-zero without looking at anything else: a checker that
    cannot fail would report "all reachable paths force full" on a tree where none
    do.

INVOKED, NOT MENTIONED, and the distinction is the whole accuracy of the gate:

    Measured 2026-08-06: the first version flagged scripts/ops/scrub-sentinel.sh
    from two call sites, and BOTH were `log_error` strings printing remediation
    advice to a human (cleanup-versions.sh:1258, upload-to-r2.sh:223). Treating a
    mention as a dependency would have forced full CI on every scripts/dev edit
    forever, on evidence that was only ever a help message.

    So a reference counts only in COMMAND POSITION: at the start of a command, or
    directly after an interpreter / path prefix. Output statements are excluded
    outright, because a path inside a message is documentation. The leading class
    also rejects `.ci/scripts/` and `packages/www/scripts/`: a match must begin at
    a path boundary that is not itself a path segment.

THE LEGACY BODY IS SCANNED TOO, and the twin records what leaving it out cost:

    The 2026-09-06 router split moved every verb implementation to
    .ci/legacy/run-legacy.sh, taking the `drill` arm's dispatch with it. This loop
    would then have found ZERO `scripts/` references in run.sh -- and there is no
    anti-vacuity floor on this half, so the gate would have stayed GREEN while
    covering nothing. Measured before the fix: 6 references in run.sh became 0.

THE OLD PREMISE WAS WRONG IN THE OTHER DIRECTION, and the correction is carried:

    Several `.ci/scripts/quality/` files are executed from NON-quality jobs --
    `.github/workflows/ci-build-renet.yml:131` ran the no-otlp-creds gate against
    the real release binaries, `ci.yml:834` runs check_release_state.py, and
    `ci.yml:531,536,539` run three `.ci/scripts/test/gates/` tests in
    `run-sh-tests`. Those jobs happen to carry no `run_*` gate TODAY, which is
    luck rather than architecture. Scanning workflow-wide (not per-job) keeps that
    luck from being load-bearing.

CONTROL A EXISTS BECAUSE THE OTHER CONTROLS DID NOT TOUCH THE EXTRACTOR:

    The controls below this used to be the whole control section, and they only
    ever called classify_mode on two real paths. Neither touched extract_refs. A
    regression that made the extractor return NOTHING would leave this gate
    printing its success line over an empty scan -- "I flagged nothing today"
    reported as "nothing is reachable". Found by review 2026-08-26, one round
    after the identical defect shipped in test-ci-compat-prose.sh.

THE awk ATTRIBUTION IS NOT A WINDOW, and both wrong versions are recorded:

    This was `grep -A 12` and review found it one line short: run.sh drill
    dispatches THREE targets and the window ended at :1994, so
    scripts/drills/license.sh at :1995 was never checked. A scan that stops early
    is exactly the under-match this gate exists to catch, so a bigger magic number
    is the wrong fix -- 16 works today and breaks on the fourth drill.

    Trying to read the arm to its closing `;;` was worse: run.sh nests case
    statements and its arms terminate inline (`stop) account_stop ;;`), so the
    block scan ran PAST `account)` and mis-attributed scripts/dev/worktree.sh to
    it.

    Attribution by nearest preceding TOP-LEVEL label needs no understanding of arm
    termination at all: every dispatch belongs to the last subcommand label seen at
    the outermost indentation.

THE DISPATCH HALF HAD NO FLOOR AND NEEDED ONE MOST:

    Only `ci_scanned` was ever floored, and only the .ci/scripts count was ever
    printed -- so the run.sh half could fall to zero references and this gate would
    report a healthy "262 .ci/scripts reference(s) scanned" and exit 0. That is not
    hypothetical: the 2026-09-06 router split moved the drill dispatch out of
    run.sh and took this loop's 6 references with it, and the gate stayed green. A
    half of a scan with no floor and no printed count is a half that can vanish in
    silence.

-----------------------------------------------------------------------------
DEFECT FOUND WHILE PORTING, REPRODUCED RATHER THAN FIXED.
-----------------------------------------------------------------------------

THE DISPATCH-HALF ANTI-VACUITY REFUSAL CALLS A FUNCTION THAT DOES NOT EXIST. The twin never sources `.ci/scripts/lib/common.sh` -- it assigns its own RED/GREEN/NC -- yet the branch added to close the hole above opens with

    log_fail "the dispatch scan found 0 scripts/ reference(s) across ..."

`log_fail` is defined in `.ci/scripts/test/lib/test-helpers.sh` and in four test scripts, in NONE of the libraries this gate loads. Under `set -euo pipefail` an unknown command exits 127 immediately, so the three explanatory `echo` lines and the `exit 1` beneath it never run: the refusal prints `...: line N: log_fail: command not found` and exits 127.

THIS IS THE SAME DEFECT, IN THE SAME SHAPE, AS ONE ALREADY RECORDED IN THIS TREE.
`.ci/scripts/test/run-all.sh:215-219` says of the pool-writer-safety gate: "the anti-vacuity refusal that exists for exactly that case called a log_fail() that does not exist, so the gate exited 127 rather than refusing. Two failures had to be repaired before this one line became visible." That gate was given its own `log_fail` at its bash twin's line 76; this one was not.

The port reproduces the 127 and the diagnostic's shape, because invariant 5 says the twin is not edited in the change that ports it and the differential rules on behaviour. See `dispatch_floor_refusal` for exactly how far the reproduction goes and where it stops.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

WHICH grep RUNS THIS GATE, because getting that wrong invalidates every probe. A script resolves `grep` to `/usr/bin/grep`, GNU grep 3.12. An interactive Claude Code shell resolves it to a FUNCTION wrapping a bundled ugrep 7.8.4 with
`-G --ignore-files --hidden -I --exclude-dir=.git ...`. Measured 2026-09-06, the
same pipeline over `.github/workflows` yields 231 references under the wrapper and 226 under the real grep, and the five-reference gap is the `\x27` defect above. Under the wrapper, `-P` on `[^A-Za-z0-9_./-]` additionally exits 2 with "range out of order in character class" (it appends `\n` to the class, making the trailing `-` a range start) while `-E` matches; under GNU grep both
flags agree. So: probe
with `/usr/bin/grep`, or from inside a script, and treat any grep measurement
taken at an interactive prompt as being about a different program.

THE FIVE-STAGE PIPELINE IS FIVE STAGES HERE TOO. Each `grep`/`sed` in `extract_refs` narrows differently and the ORDER is observable: the output-statement filter runs on the WHOLE LINE, before the command-position match, so a line that both invokes and logs is dropped entirely. Collapsing the stages into one regex would change that.

`node` IS SHELLED OUT TO, exactly as the twin does it. `classify()` lives in `.ci/scripts/ci/scope-map.cjs`, whose rule ORDER is semantics (first match wins, per driver contract section 3). Re-deriving it in Python would produce a gate that agrees with itself about a file it no longer reads.

A MISSING `node` IS A LOUD FAILURE WITH THE FIX IN THE MESSAGE, not a stack trace: `classify_mode` returns the twin's literal `"ERROR"` string, which is not `"full"` and therefore reports every path as a violation -- the same conservative direction the twin takes.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The twin's escape sequences, unconditional. It never sources common.sh.
RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# "Directories whose code runs in gated jobs. Deliberately NOT .ci/scripts/quality or .ci/scripts/test: those are the quality lanes, which are unscopeable."
GATED_DIRS = (
    ".github/workflows",
    ".ci/scripts/build",
    ".ci/scripts/deploy",
    ".ci/scripts/setup",
    ".ci/scripts/private",
    ".ci/scripts/housekeeping",
)

# `run.sh` is the drill dispatcher and is itself a ROOT_MANIFEST path, so editing it forces full on its own. It is scanned because what it DISPATCHES to must still be full. The legacy body is here for the reason in the module docstring.
GATED_FILES = ("run.sh", ".ci/legacy/run-legacy.sh")

# Where the gate lives, as the CI invocation spells it. Used ONLY to reproduce bash's `command not found` diagnostic; see dispatch_floor_refusal.
TWIN_REL = ".ci/scripts/quality/check-scope-scripts-reachability.sh"

# Stage 1: a line mentioning a root `scripts/` path at a path boundary.
ROOT_LINE = re.compile(r"(^|[^A-Za-z0-9_./-])(\./|\"?\$[A-Za-z_]+/)?scripts/")
CI_LINE = re.compile(r"(^|[^A-Za-z0-9_./-])(\./)?\.ci/scripts/")

# Stage 2: output statements are documentation, never a dependency.
OUTPUT_STATEMENT = re.compile(r"\b(log_error|log_warn|log_info|log_debug|echo|printf)\b")

# Stage 3: COMMAND POSITION.
#
# `\x27` IS NOT A SINGLE QUOTE HERE, AND THAT IS A DEFECT IN THE TWIN, MEASURED RATHER THAN ASSUMED. The twin's lead alternation is `(^|[[:space:]]|"|\x27|\$\(|`|&&|\|\||;)`, written to admit a command that starts after an opening single quote. GNU grep 3.12, which is what `/usr/bin/grep` is on this host and therefore what the twin actually runs, does NOT read `\x27` as a hex
# escape in an ERE: it treats `\x` as an escaped ordinary `x`, so the alternative matches the literal three characters `x27`. Probed 2026-09-06 on a two-line file containing `a'b` and `ax27b`: `/usr/bin/grep -oE '\x27'` printed `x27`.
#
# The consequence is a real blind spot, not a curiosity. Five `.cjs` paths in `.github/workflows` are invoked as `require('./.ci/scripts/ci/<name>.cjs')` -- autopilot-guide-comment, label-guide-comment, report-nightly-status, validate-pr and watchdog-monitor -- and the twin does not see any of them: its `.ci` scan counts 226 references from that directory where a grep with a
# working single-quote alternative counts 231. So an invocation whose only lead character is `'` is invisible to this gate.
#
# Reproduced, not repaired: invariant 5 forbids editing the twin in the change that ports it, and the differential rules on behaviour. Reported as a defect.
_LEAD = r"(^|[ \t\v\f\r]|\"|x27|\$\(|`|&&|\|\||;)[ \t\v\f\r]*"
_PREFIX = r"((bash|sh|source|node|python3)[ \t\v\f\r]+|npx[ \t\v\f\r]+tsx[ \t\v\f\r]+|"
ROOT_COMMAND = re.compile(_LEAD + _PREFIX + r"\./|\"?\$[A-Za-z_]+/)?scripts/[A-Za-z0-9_./-]+")
CI_COMMAND = re.compile(_LEAD + _PREFIX + r"\./)?\.ci/scripts/[A-Za-z0-9_./-]+")

# Stage 4: the bare path out of the command-position match.
ROOT_PATH = re.compile(r"scripts/[A-Za-z0-9_./-]+")
CI_PATH = re.compile(r"\.ci/scripts/[A-Za-z0-9_./-]+")

# Stage 5: trailing punctuation, then documentation extensions.
TRAILING_JUNK = re.compile(r"[^A-Za-z0-9_./-]+$")
DOC_EXT = re.compile(r"\.(md|txt)$")

# `./run.sh <sub>` as a workflow invokes it.
RUNSH_SUBCOMMAND = re.compile(r"\./run\.sh[ \t\v\f\r]+[a-z][a-z0-9-]*")

# The awk attribution: a TOP-LEVEL case label, eight spaces of indent.
TOP_LEVEL_LABEL = re.compile(r'^        [A-Za-z0-9_"|-]+\)')
LABEL_LEAD = re.compile(r'^[ \t\v\f\r]*"?')
LABEL_TAIL = re.compile(r'"?\).*$')

# The two floors. `ci_scanned` had one from the start; the dispatch half did not, and the module docstring records what that cost.
CI_SCAN_FLOOR = 20
DISPATCH_FLOOR = 1


def walk_text(root: pathlib.Path):
    """Every file `grep -r` would read under `root`, as text.

    Reproduces GNU grep 3.12 (`/usr/bin/grep`, which is what a SCRIPT resolves `grep` to on this host) as measured 2026-09-06: `-r` does not descend a directory symlink, a file symlink found in the tree is skipped, and a file containing a NUL byte contributes NOTHING TO STDOUT -- with `-o` GNU grep prints no matching text for a binary file, only the diagnostic `grep: <path>: binary
    file matches`, and that goes to STDERR, which every caller of these extractors sends to /dev/null.

    THE grep IN AN INTERACTIVE CLAUDE CODE SHELL IS NOT THIS grep, and measuring against it produced a wrong model twice while this port was written. That shell defines `grep` as a FUNCTION wrapping a bundled ugrep 7.8.4 with
    `-G --ignore-files --hidden -I --exclude-dir=.git ...`; a script sees
    `/usr/bin/grep`, GNU grep 3.12. The two differ on `\x27` (see _LEAD above), on how a binary file is reported, and on which files are searched at all. Probe with `/usr/bin/grep` explicitly, or from inside a script file, when the question is what a gate does.
    """
    if root.is_file() and not root.is_symlink():
        candidates = [root]
    elif root.is_dir():
        candidates = []
        for dirpath, _dirnames, filenames in paths.walk_tree(root):
            candidates.extend(pathlib.Path(dirpath) / name for name in filenames)
    else:
        return
    for path in candidates:
        if path.is_symlink() or not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data:
            continue
        yield data.decode("utf-8", "replace")


def _refs(lines, line_re, command_re, path_re) -> list[str]:
    """The five-stage pipeline, in the twin's order.

    THE ORDER IS OBSERVABLE. The output-statement filter runs on the WHOLE line before command position is considered, so a line that both invokes a script and logs about one is dropped entirely. That is a known imprecision of the twin and it is carried, because narrowing it changes which paths get judged.
    """
    out: set[str] = set()
    for line in lines:
        if not line_re.search(line):
            continue
        if OUTPUT_STATEMENT.search(line):
            continue
        for hit in command_re.findall(line):
            # `findall` returns the group tuple when the pattern has groups, so the match text is taken from finditer instead. Kept as a named step rather than an inline comprehension because getting this wrong is silent: a tuple stringifies without raising.
            del hit
        for match in command_re.finditer(line):
            for path in path_re.findall(match.group(0)):
                cleaned = TRAILING_JUNK.sub("", path)
                if DOC_EXT.search(cleaned):
                    continue
                out.add(cleaned)
    return sorted(out)


def extract_refs(target: pathlib.Path) -> list[str]:
    """Root `scripts/` paths INVOKED under `target`, sorted and deduplicated."""
    return _refs(
        (line for text in walk_text(target) for line in text.split("\n")),
        ROOT_LINE,
        ROOT_COMMAND,
        ROOT_PATH,
    )


def extract_ci_refs(target: pathlib.Path) -> list[str]:
    """`.ci/scripts/` paths INVOKED under `target`.

    "`.ci/scripts/**` is currently ALL harness (scope-map.cjs's `ci-harness`), so every reference below classifies `full` today and this scan is green. It exists for the day someone narrows part of `.ci/`."
    """
    return _refs(
        (line for text in walk_text(target) for line in text.split("\n")),
        CI_LINE,
        CI_COMMAND,
        CI_PATH,
    )


def ci_invoked_runsh_subcommands(root: pathlib.Path) -> list[str]:
    """`./run.sh <sub>` names a WORKFLOW actually invokes.

    "run.sh dispatches many subcommands; only the ones a WORKFLOW actually invokes are reachable from a gated job. `./run.sh drill ...` appears in ct-tests.yml, `./run.sh worktree` does not, so scripts/dev/worktree.sh is legitimately narrowable even though run.sh names it."
    """
    out: set[str] = set()
    for text in walk_text(root / ".github" / "workflows"):
        for line in text.split("\n"):
            for hit in RUNSH_SUBCOMMAND.findall(line):
                fields = hit.split()
                if len(fields) >= 2:
                    out.add(fields[1])
    return sorted(out)


def dispatch_targets(text: str, subcommand: str) -> list[str]:
    """`scripts/` paths under the nearest preceding TOP-LEVEL label `subcommand`.

    NOT A WINDOW AND NOT A BLOCK SCAN. See the module docstring for what each of those two earlier shapes missed and mis-attributed.
    """
    out: set[str] = set()
    current = ""
    for line in text.split("\n"):
        if TOP_LEVEL_LABEL.match(line):
            label = LABEL_LEAD.sub("", line, count=1)
            label = LABEL_TAIL.sub("", label, count=1)
            current = label
        if current == subcommand:
            out.update(ROOT_PATH.findall(line))
    return sorted(out)


def classify_mode(root: pathlib.Path, path: str) -> str:
    """`scope-map.cjs`'s verdict for one path, or the twin's literal "ERROR".

    SHELLED OUT TO node ON PURPOSE. The rule ORDER inside scope-map.cjs is semantics (first match wins), and a Python re-derivation would be a second copy that drifts silently. "ERROR" is not "full", so a node that cannot run makes every path a violation, which is the conservative direction.
    """
    script = (
        'const {classify} = require(process.argv[1] + "/.ci/scripts/ci/scope-map.cjs");\n'
        "process.stdout.write(classify([process.argv[2]], {}).mode);\n"
    )
    try:
        proc = subprocess.run(
            ["node", "-e", script, str(root), path],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return "ERROR"
    if proc.returncode != 0:
        return "ERROR"
    return proc.stdout


def dispatch_floor_refusal() -> int:
    """The twin's dispatch-half refusal, defect and all. Returns 127.

    THIS REPRODUCES A BUG. `log_fail` is undefined in the twin, so bash exits 127 at that line and the three explanatory `echo`s below it never run. See the module docstring for the identical, already-recorded instance in the pool-writer-safety gate's own twin.

    HOW FAR THE REPRODUCTION GOES, stated so nobody reads more into it. bash's diagnostic is `<script as invoked>: line <n>: log_fail: command not found`, and both halves of that prefix belong to bash, not to the gate: the path is whatever argv[0] was, and the line number is the twin's. The port emits the canonical relative path and finds the line number by reading the twin, which
    is exact when the gate is invoked the way CI invokes it and merely approximate when it is invoked by absolute path. The STATUS, which is what a caller acts on, is exact either way.
    """
    lineno = 0
    twin = paths.repo_root() / TWIN_REL
    try:
        for number, line in enumerate(
            twin.read_text(encoding="utf-8", errors="replace").split("\n"), start=1
        ):
            if line.lstrip().startswith("log_fail "):
                lineno = number
                break
    except OSError:
        lineno = 0
    print("%s: line %d: log_fail: command not found" % (TWIN_REL, lineno), file=sys.stderr)
    return 127


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 clean, 1 a violation or a failed control, 127 the defect above.

    `--selftest` is intercepted BEFORE the controls, let alone the real scan.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    os.chdir(root)

    violations: list[str] = []

    def check_path(path: str, src: str) -> None:
        # "a reference to a path that does not exist is a different bug;
        # check-command-paths owns that."
        if not pathlib.Path(path).exists():
            return
        mode = classify_mode(root, path)
        if mode != "full":
            violations.append(
                "%s (referenced from %s) classifies '%s', expected 'full'" % (path, src, mode)
            )

    # ---- CONTROL A: the EXTRACTOR must actually fire -----------------------
    with tempfile.TemporaryDirectory() as ctl_dir:
        probe = pathlib.Path(ctl_dir) / "probe.sh"
        probe.write_text(
            "bash scripts/synthetic-control-probe.sh\n"
            'log_error "see scripts/not-a-dependency.sh for details"\n',
            encoding="utf-8",
        )
        got = " ".join(extract_refs(pathlib.Path(ctl_dir)))
        if got != "scripts/synthetic-control-probe.sh":
            print(
                "%s✗ CONTROL FAILED%s: the reference extractor did not return the planted path."
                % (RED, NC),
                file=sys.stderr,
            )
            print(
                "  expected exactly 'scripts/synthetic-control-probe.sh', got: '%s'"
                % (got or "<nothing>"),
                file=sys.stderr,
            )
            print(
                "  A scanner that matches nothing reports every tree as clean, so this",
                file=sys.stderr,
            )
            print("  gate refuses to report a result.", file=sys.stderr)
            return 1

        probe.write_text(
            "bash .ci/scripts/synthetic-ci-probe.sh\n"
            'log_error "see .ci/scripts/not-a-dependency.sh for details"\n',
            encoding="utf-8",
        )
        got_ci = " ".join(extract_ci_refs(pathlib.Path(ctl_dir)))
        if got_ci != ".ci/scripts/synthetic-ci-probe.sh":
            print(
                "%s✗ CONTROL FAILED%s: the .ci extractor did not return the planted path."
                % (RED, NC),
                file=sys.stderr,
            )
            print(
                "  expected exactly '.ci/scripts/synthetic-ci-probe.sh', got: '%s'"
                % (got_ci or "<nothing>"),
                file=sys.stderr,
            )
            return 1

    # ---- CONTROL: a synthetic reachable path MUST be judged a violation ----
    control_mode = classify_mode(root, "scripts/gates/check-embed-credits.ts")
    if control_mode != "reduced":
        print(
            "%s✗ CONTROL FAILED%s: a known gate source classified '%s', not 'reduced'."
            % (RED, NC, control_mode),
            file=sys.stderr,
        )
        print(
            "  The checker cannot tell a narrowed path from a full one, so its verdict",
            file=sys.stderr,
        )
        print("  on real paths is meaningless. Refusing to report a result.", file=sys.stderr)
        return 1
    control_full = classify_mode(root, "scripts/drills/lib.sh")
    if control_full != "full":
        print(
            "%s✗ CONTROL FAILED%s: a known carve-out classified '%s', not 'full'."
            % (RED, NC, control_full),
            file=sys.stderr,
        )
        print("  The carve-outs this gate exists to protect are not in force.", file=sys.stderr)
        return 1

    # ---- the real scan -----------------------------------------------------
    for directory in GATED_DIRS:
        target = pathlib.Path(directory)
        if not target.is_dir():
            continue
        for ref in extract_refs(target):
            check_path(ref, directory)

    dispatch_scanned = 0
    subcommands = ci_invoked_runsh_subcommands(root)
    for name in GATED_FILES:
        target = pathlib.Path(name)
        if not target.is_file():
            continue
        text = target.read_text(encoding="utf-8", errors="replace")
        for sub in subcommands:
            for ref in dispatch_targets(text, sub):
                dispatch_scanned += 1
                check_path(ref, "%s (%s)" % (name, sub))

    ci_scanned = 0
    for directory in GATED_DIRS:
        target = pathlib.Path(directory)
        if not target.is_dir():
            continue
        for ref in extract_ci_refs(target):
            ci_scanned += 1
            check_path(ref, directory)

    if dispatch_scanned < DISPATCH_FLOOR:
        # THE DEFECT. See dispatch_floor_refusal and the module docstring: the explanation the twin wrote for this branch is unreachable.
        return dispatch_floor_refusal()

    if ci_scanned < CI_SCAN_FLOOR:
        print(
            "%s✗ VACUOUS SCAN%s: only %d .ci/scripts reference(s) found across %d dirs."
            % (RED, NC, ci_scanned, len(GATED_DIRS)),
            file=sys.stderr,
        )
        print(
            "  The real tree invokes far more than that, so the enumeration broke.", file=sys.stderr
        )
        return 1

    if violations:
        print(
            "%s✗ %d path(s) reachable from a gated job do not force full CI:%s"
            % (RED, len(violations), NC),
            file=sys.stderr,
        )
        for line in violations:
            print("  %s" % line, file=sys.stderr)
        print(file=sys.stderr)
        print(
            "Each of these is executed by (or dispatched from) code that runs in a gated",
            file=sys.stderr,
        )
        print(
            "job, so a delta touching only that file would skip the job that depends on",
            file=sys.stderr,
        )
        print("it. Add a carve-out rule in .ci/scripts/ci/scope-map.cjs ABOVE the", file=sys.stderr)
        print(
            "'scripts-gates' rule (first match wins), mirroring 'scripts-drills'.", file=sys.stderr
        )
        return 1

    print(
        "%s✓%s every root scripts/ and .ci/scripts/ path reachable from a gated job forces "
        "full CI" % (GREEN, NC)
    )
    print(
        "  (%d .ci/scripts and %d dispatch reference(s) scanned;" % (ci_scanned, dispatch_scanned)
    )
    print("   extractor controls fired, so this is not an empty pass)")
    print("  Blind spot: scanning is workflow-WIDE, not per-job. A path referenced from")
    print("  an ungated job is held to the same rule, which is conservative, and a")
    print("  second-level dependency (a script a scanned script calls) is not followed.")
    return 0


def selftest() -> int:
    """Both directions on the extractor, the attribution and the floors.

    THE FLOOR IS DERIVED from the case corpus, so a case that stops running turns the suite red rather than quietly shortening it.
    """
    # (label, one line of a scanned file, expected root refs)
    root_cases = [
        ("a bash invocation is a dependency", "bash scripts/x.sh", ["scripts/x.sh"]),
        ("a bare ./ invocation is a dependency", "./scripts/y.sh --flag", ["scripts/y.sh"]),
        ("an npx tsx invocation is a dependency", "npx tsx scripts/z.ts", ["scripts/z.ts"]),
        # THE 2026-08-06 FALSE POSITIVE. A remediation string is documentation.
        ("a log_error mention is NOT a dependency", 'log_error "run scripts/x.sh"', []),
        ("an echo mention is NOT a dependency", 'echo "see scripts/x.sh"', []),
        # THE BOUNDARY CLASS. A longer path must not be truncated into a root one.
        (".ci/scripts is not root scripts", "bash .ci/scripts/x.sh", []),
        ("packages/www/scripts is not root scripts", "bash packages/www/scripts/x.sh", []),
        # DOCUMENTATION EXTENSIONS ARE DROPPED.
        ("a markdown target is dropped", "bash scripts/readme.md", []),
        ("a text target is dropped", "bash scripts/notes.txt", []),
    ]
    ci_cases = [
        ("a .ci invocation is a dependency", "bash .ci/scripts/x.sh", [".ci/scripts/x.sh"]),
        ("a .ci mention is NOT a dependency", 'log_info "see .ci/scripts/x.sh"', []),
    ]
    # The dispatch attribution, over a miniature run.sh.
    runsh = (
        "case $1 in\n"
        "        drill)\n"
        "            bash scripts/drills/a.sh\n"
        "            bash scripts/drills/b.sh\n"
        "            bash scripts/drills/c.sh\n"
        "            ;;\n"
        "        worktree)\n"
        "            bash scripts/dev/worktree.sh\n"
        "            ;;\n"
        "esac\n"
    )
    attribution = [
        (
            "every target of an arm is attributed, not the first twelve lines",
            "drill",
            ["scripts/drills/a.sh", "scripts/drills/b.sh", "scripts/drills/c.sh"],
        ),
        # THE MIS-ATTRIBUTION THE BLOCK SCAN PRODUCED: worktree's target must not land under drill, and drill's must not land under worktree.
        ("a neighbouring arm's target is not attributed", "worktree", ["scripts/dev/worktree.sh"]),
        ("an unknown subcommand attributes nothing", "nosuchverb", []),
    ]

    floor = len(root_cases) + len(ci_cases) + len(attribution) + 4
    ctl = Controls("scope-scripts-reachability", floor=floor)

    with tempfile.TemporaryDirectory() as tmp:
        probe = pathlib.Path(tmp) / "probe.sh"
        for label, line, want in root_cases:
            probe.write_text(line + "\n", encoding="utf-8")
            ctl.check("root: %s" % label, extract_refs(pathlib.Path(tmp)), want)
        for label, line, want in ci_cases:
            probe.write_text(line + "\n", encoding="utf-8")
            ctl.check("ci: %s" % label, extract_ci_refs(pathlib.Path(tmp)), want)

    for label, sub, want in attribution:
        ctl.check("dispatch: %s" % label, dispatch_targets(runsh, sub), want)

    # THE FLOORS ARE THE TWIN'S, and the dispatch one is the half that had none.
    ctl.check("the .ci scan floor is 20", CI_SCAN_FLOOR, 20)
    ctl.check("the dispatch floor is 1", DISPATCH_FLOOR, 1)
    ctl.check("six gated directories are scanned", len(GATED_DIRS), 6)
    # THE LEGACY BODY MUST STAY IN THE LIST. Removing it took this half to zero references on 2026-09-06 and the gate stayed green.
    ctl.check("the legacy router body is scanned", ".ci/legacy/run-legacy.sh" in GATED_FILES, True)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
