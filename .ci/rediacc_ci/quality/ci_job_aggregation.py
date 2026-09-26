"""Every top-level job in `ci.yml` must reach the `ci-complete` verdict.

Ported from `.ci/scripts/quality/check-ci-job-aggregation.sh`, which is NOT deleted; see `rediacc_ci.quality.__init__` for why both copies live.

The twin's header, carried in full because the four checks and the direction argument are the gate:

    WHY. `ci-complete` is the single required status check for branch
    protection. It is green when, and only when, the jobs it aggregates are
    green. A job that is not in its `needs:` list, or is in `needs:` but has no
    `RESULT_*` env var feeding assert-ci-complete.sh, is invisible to it: the job
    can go red and the required check still reports success.

    Nothing enforced the relationship, so it decayed. ci.yml declares 24
    top-level jobs; `ci-complete` aggregated 18 of them. Adding a job is the
    natural motion, and wiring it into the aggregator twice (once in `needs:`,
    once in `env:`) is the step people skip. This makes forgetting it a build
    failure instead of an unguarded job.

    FOUR CHECKS, because there are four ways the wiring breaks:
      1. A job is missing from `needs:`         -> its result is unreadable.
      2. A job is in `needs:` but has no        -> assert-ci-complete.sh never
         RESULT_<JOB> in the `env:` block          sees it, so it cannot judge it.
      3. `needs:` names a job that does not     -> GitHub refuses the workflow at
         exist                                     parse time.
      4. A RESULT_<JOB> var is in neither       -> the var is passed and dropped;
         HARD_REQUIRED nor SOFT_REQUIRED, or       or the tier reads an unset var
         a tier names a var nobody passes          and every run is red.

    DIRECTION IS DELIBERATE for check 4 only. Checks 1 and 2 say jobs subset of
    aggregator. Check 4 is an equality, because a tier entry and an env var are
    two halves of one wire: either half alone is dead.

    THE EXEMPT SET IS A HOLE, so every entry carries a BLOCKER reason validated
    by the shared validator (see docs/agent-reference/suppressions.md). It lives
    inline rather than in a tracked dotfile: it describes the shape of THIS
    workflow's DAG, it is only meaningful next to the four checks above, and a
    repo-root suppression file would need a liveness probe whose oracle is
    exactly the parsing done here.

    TEST SEAM. CI_JOB_AGGREGATION_WORKFLOW and CI_JOB_AGGREGATION_ASSERT
    override the two inputs so the gate test can drive fixtures without touching
    a tracked file.

    Usage: check-ci-job-aggregation.sh

    Exits 0 when the wiring is complete, 1 on any gap.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE FIVE AWK PROGRAMS ARE THE GATE, so each is ported as its own named function
with the awk it replaces quoted above it. They are not YAML parsers and must not
become ones: a real parser would see `needs:` under an `if:` expression, would resolve anchors, and would therefore change WHICH jobs the gate believes exist. That is a different gate. The line-oriented reading is the specification here, and `check:ci-gates-lock` is not its oracle -- the workflow file is.

THE EXEMPT SET IS CARRIED VERBATIM, REASONS INCLUDED. It is a suppression list, so its five BLOCKER reasons are the part that must survive a port intact: each one records why `ci-complete` genuinely cannot aggregate that job, and one of them (build-renet) is an explicit note that the current safety is ACCIDENTAL and should be removed the next time the tier logic is touched.
Deleting that paragraph would delete the only record that the hole is known.

`parse_blockered_list` AND `verify_all_blockers` COME FROM `rediacc_ci.core.allowlist`, which is the one implementation of this repository's BLOCKER contract and is proved byte-compatible with `.ci/scripts/lib/blocker-validator.sh` over a frozen corpus. The twin sources the bash copy; using a fourth hand-rolled reader here would be exactly the duplication that module exists to end.

THE VALIDATOR ARM CANNOT FIRE FROM A FIXTURE, and that is worth stating rather than discovering. The exempt block lives INSIDE the gate file, so a differential fixture cannot plant a low-effort reason without editing the twin, which invariant 5 forbids. The arm is therefore exercised by the selftest, in both directions, against blocks written by construction.

BASH ASSOCIATIVE-ARRAY ORDER IS NOT REPRODUCED, and it does not matter. The
twin's `for n in "${!NEEDS[@]}"` walks a hash, so its phantom / untiered /
orphan lists come out in an order that is neither insertion nor sorted. This port sorts them. Every one of those lines is an `echo` on STDOUT under a `log_error` header on STDERR, so the differential reads them as progress and compares the headers, which carry the COUNTS; a reader gets a stable order instead of a hash order, which is strictly better and changes no verdict.

`tr '[:lower:]-' '[:upper:]_'` IS A TWO-SET TRANSLATION, NOT AN UPPERCASE. The set on the left is the 26 lowercase letters PLUS the hyphen, and the right is the 26 uppercase letters PLUS the underscore. Digits, dots and any character outside those sets pass through untouched, and an already-uppercase letter is not touched either. `result_var_for` reproduces exactly that, because a
port that called `.upper().replace("-", "_")` would agree on every job name this workflow has ever had and would diverge the first time one contains a character the translation leaves alone.
"""

import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls
from rediacc_ci.core import allowlist

# The aggregator job. Named once, here, so a rename fails loudly below rather than silently matching nothing.
AGGREGATOR = "ci-complete"

# Anti-vacuity floor. ci.yml has carried 20+ top-level jobs for its whole life;
# a parse that returns fewer than this found a layout it does not understand, and reporting "all wired" off three jobs is the failure this gate exists to prevent.
MIN_JOBS = 10

# The two test seams, spelled the twin's way so a gate test driving one drives both implementations.
WORKFLOW_ENV = "CI_JOB_AGGREGATION_WORKFLOW"
ASSERT_ENV = "CI_JOB_AGGREGATION_ASSERT"

# ---------------------------------------------------------------------------
# The exempt set. Entry = job name; reason = why ci-complete cannot or must not
# aggregate it. Parsed and quality-checked by the shared BLOCKER validator, so a "# tbd" exemption fails this gate the same way it fails every other list. ---------------------------------------------------------------------------
EXEMPT_BLOCK = """
# BLOCKER: this IS the aggregator; a job listed in its own needs is a self-edge and GitHub rejects the workflow at parse time, so the exemption is structural rather than a judgment call
ci-complete

# BLOCKER: runs downstream of the aggregator (needs: [initialize, ci-complete]), so aggregating it would close a cycle; its conclusion is asserted instead by pipeline-sentinel via assert-job-succeeded.sh
finalize-release-sentinel

# BLOCKER: transitively downstream of the aggregator (needs finalize-release-sentinel, which needs ci-complete), so aggregating it would close a cycle; it is the terminal assertion of the release DAG and has nothing above it to report to
pipeline-sentinel

# BLOCKER: designed to be force-cancelled by a newer run (its if: is !cancelled(), and cancel-older-runs.sh cancels peers), so a cancelled conclusion is the routine outcome; the soft tier accepts only success or skipped, so aggregating it would turn every superseded push red
cancel-watchdog

# BLOCKER: its failure already reaches the aggregator, but only INDIRECTLY and by accident. build-docker, build-docker-fast and build-cli each gate on needs.build-renet.result == 'success', so a red build-renet skips all three, and all three are HARD_REQUIRED where a skip is red. ops-tests runs under always() and then dies fetching the missing renet artifact, which is a second, equally accidental path. The outcome is correct today and nothing pins it: dropping the build-renet clause from any of those four ifs, or moving one job to the soft tier, silently makes a red build-renet read as green. Aggregate it directly when the pointer-bump tier logic is next touched, and delete this entry.
build-renet
"""


# --------------------------------------------------------------------------- Parsers. All three read the real files, not a copy. ---------------------------------------------------------------------------


def top_level_jobs(text: str) -> list[str]:
    """One job name per line, from the workflow's `jobs:` block.

        awk '
            /^jobs:[[:space:]]*$/ { in_jobs = 1; next }
            in_jobs && /^[^[:space:]#]/ { in_jobs = 0 }
            in_jobs && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ { ... print key }
        '

    Job keys are the only 2-space-indented bare keys after the `jobs:` line; job bodies sit at 4 spaces or deeper. Scoping to the jobs block keeps the `on:` / `permissions:` / `concurrency:` keys (also 2-space) out.

    THE `next` MATTERS: the `jobs:` line itself never reaches the third rule, so a file whose first job is on the same line as `jobs:` yields nothing rather than a phantom entry.
    """
    in_jobs = False
    out: list[str] = []
    for line in text.split("\n"):
        if re.match(r"^jobs:[ \t]*$", line):
            in_jobs = True
            continue
        if in_jobs and re.match(r"^[^ \t#]", line):
            in_jobs = False
        if in_jobs and re.match(r"^  [A-Za-z0-9_-]+:[ \t]*$", line):
            key = re.sub(r"^  ", "", line)
            key = re.sub(r":[ \t]*$", "", key)
            out.append(key)
    return out


def job_block(text: str, job: str) -> str:
    """The lines of one job, body only.

        awk -v want="$2" '
            $0 ~ ("^  " want ":[[:space:]]*$") { in_job = 1; next }
            in_job && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ { in_job = 0 }
            in_job { print }
        '

    The start pattern is a REGEX built from the job name, exactly as awk builds it, so a job name containing a regex metacharacter behaves the same on both sides. This is reproduced rather than tidied to a literal comparison for that reason alone: `re.escape` here would make the port disagree with its twin on an input neither of them should ever be given.
    """
    start = re.compile("^  " + job + r":[ \t]*$")
    in_job = False
    out: list[str] = []
    for line in text.split("\n"):
        if start.search(line):
            in_job = True
            continue
        if in_job and re.match(r"^  [A-Za-z0-9_-]+:[ \t]*$", line):
            in_job = False
        if in_job:
            out.append(line)
    # awk's `print` appends a newline per record, so a non-empty block always ends in one. The twin then tests `[[ ! -s "$BLOCK_FILE" ]]`, which is a SIZE test: an empty block is an empty file.
    return "".join(line + "\n" for line in out)


def needs_names(block: str) -> list[str]:
    """One dependency job name per line.

        awk '/^[[:space:]]*needs:/ { strip the key, turn []`,` into spaces, split }'

    `needs: [a, b, c]` is the form ci.yml uses. The brackets, commas and the key itself are stripped; a bare `needs: a` form also survives.
    """
    out: list[str] = []
    for line in block.split("\n"):
        if not re.match(r"^[ \t]*needs:", line):
            continue
        stripped = re.sub(r"^[ \t]*needs:[ \t]*", "", line)
        stripped = re.sub(r"[\]\[,]", " ", stripped)
        out.extend(part for part in re.split(r"[ \t]+", stripped) if part != "")
    return out


def result_vars(block: str) -> list[str]:
    """One `RESULT_*` env var name per line.

        awk 'match($0, /RESULT_[A-Z0-9_]+:/) { print substr($0, RSTART, RLENGTH - 1) }'

    ONE PER LINE, because awk's `match` finds only the first. Two RESULT_ vars on one line would be read as one by the twin, and the port keeps that so the two agree about a shape neither of them handles well.
    """
    out: list[str] = []
    for line in block.split("\n"):
        found = re.search(r"RESULT_[A-Z0-9_]+:", line)
        if found:
            out.append(found.group(0)[:-1])
    return out


def tier_entries(text: str) -> list[str]:
    """One tier member per line, from HARD_REQUIRED and SOFT_REQUIRED.

        awk '
            /^(HARD_REQUIRED|SOFT_REQUIRED)\\+?=\\(/ { collecting = 1; sub(/^[^(]*\\(/, "") }
            collecting { ... strip a trailing ")" and any comment, split on whitespace }
        '

    Reads the real arrays, including the `+=` form the pointer-bump fast path
    uses, so a member added there is seen here. The closing-paren test is `index(line, ")") > 0` on the WHOLE line, so an array whose last element sits on the same line as the `)` still yields that element.
    """
    out: list[str] = []
    collecting = False
    for raw in text.split("\n"):
        line = raw
        if re.match(r"^(HARD_REQUIRED|SOFT_REQUIRED)\+?=\(", line):
            collecting = True
            line = re.sub(r"^[^(]*\(", "", line, count=1)
        if not collecting:
            continue
        if ")" in line:
            line = re.sub(r"\).*$", "", line, count=1)
            collecting = False
        line = re.sub(r"#.*$", "", line, count=1)
        out.extend(part for part in re.split(r"[ \t]+", line) if part != "")
    return out


# `tr '[:lower:]-' '[:upper:]_'`, spelled out. See the port notes for why this is a translation table rather than `.upper()`.
_TR = str.maketrans("abcdefghijklmnopqrstuvwxyz-", "ABCDEFGHIJKLMNOPQRSTUVWXYZ_")


def result_var_for(job: str) -> str:
    """`RESULT_<JOB>` with dashes folded to underscores."""
    return "RESULT_" + job.translate(_TR)


def exempt_entries() -> dict[str, str]:
    """The exempt job names mapped to their BLOCKER reasons.

    `pairs` and not `records`, because the twin populates two bash ASSOCIATIVE ARRAYS and an associative array cannot hold two rows for one key. See `rediacc_ci.core.allowlist`'s docstring for why that distinction is not academic.
    """
    return allowlist.pairs(allowlist.parse_text(EXEMPT_BLOCK))


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 when the wiring is complete, 1 on any gap.

    `--selftest` is intercepted BEFORE either input is read, so the controls run on a tree whose ci.yml is missing.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    workflow = pathlib.Path(
        os.environ.get(WORKFLOW_ENV) or str(root / ".github" / "workflows" / "ci.yml")
    )
    assert_script = pathlib.Path(
        os.environ.get(ASSERT_ENV) or str(root / ".ci" / "scripts" / "ci" / "assert-ci-complete.sh")
    )

    # require_input -f: refuse, in the gate's own words, rather than skip.
    for candidate in (workflow, assert_script):
        if not candidate.is_file():
            log.error("input not found: %s" % candidate)
            log.error(
                "This gate cannot assert anything without it. Fix the path, do not skip the check."
            )
            return 1

    entries = allowlist.parse_text(EXEMPT_BLOCK)
    exempt = allowlist.pairs(entries)
    problems = allowlist.verify(entries, "the EXEMPT block")
    if problems:
        for problem in problems:
            log.error(problem)
        # The validator names the file it was handed, which tells the reader nothing about where to edit. Name the real one.
        log.error(
            "The offending entry lives in the EXEMPT block of "
            ".ci/rediacc_ci/quality/ci_job_aggregation.py"
        )
        log.error("An exemption is a hole in the 'ci-complete is the required check' promise.")
        log.error("It must say why the job genuinely cannot be aggregated.")
        return 1

    log.step("Checking that every ci.yml job reaches the %s verdict..." % AGGREGATOR)

    workflow_text = workflow.read_text(encoding="utf-8", errors="replace")
    assert_text = assert_script.read_text(encoding="utf-8", errors="replace")

    jobs = [j for j in top_level_jobs(workflow_text) if j != ""]

    if len(jobs) < MIN_JOBS:
        log.error(
            "Parsed only %d top-level job(s) from %s (floor is %d)."
            % (len(jobs), workflow, MIN_JOBS)
        )
        log.error(
            "The workflow layout changed and this gate is blind. Fix the parser, do not "
            "lower the floor."
        )
        return 1

    block = job_block(workflow_text, AGGREGATOR)

    if block == "":
        log.error("No job named '%s' in %s." % (AGGREGATOR, workflow))
        log.error(
            "Either the required status check was renamed (update AGGREGATOR here) or it is gone."
        )
        return 1

    needs_list = [n for n in needs_names(block) if n != ""]
    needs = dict.fromkeys(needs_list, 1)
    needs_count = len(needs_list)

    results = dict.fromkeys((r for r in result_vars(block) if r != ""), 1)
    tiers = dict.fromkeys(("RESULT_%s" % t for t in tier_entries(assert_text) if t != ""), 1)

    # Anti-vacuity, one floor per input: an empty set here would make its checks pass by asserting over nothing.
    if needs_count == 0:
        log.error("%s has no 'needs:' list in %s: it aggregates nothing." % (AGGREGATOR, workflow))
        return 1
    if len(results) == 0:
        log.error(
            "%s passes no RESULT_* env vars in %s: assert-ci-complete.sh judges nothing."
            % (AGGREGATOR, workflow)
        )
        return 1
    if len(tiers) == 0:
        log.error(
            "No HARD_REQUIRED / SOFT_REQUIRED members parsed from %s: this gate is blind."
            % assert_script
        )
        return 1

    is_job = set(jobs)

    # --------------------------------------------------------------------- Check. ---------------------------------------------------------------------
    missing_needs: list[str] = []
    missing_results: list[str] = []

    # Liveness. A BLOCKER proves a reason existed once; it cannot prove the reason is still true. An exemption for a job that no longer exists is a hole held open by nothing, and it is invisible unless something asks. See the liveness section of docs/agent-reference/suppressions.md.
    dead_exemptions = [entry for entry in sorted(exempt) if entry not in is_job]

    for job in jobs:
        if job in exempt:
            continue
        var = result_var_for(job)
        if job not in needs:
            missing_needs.append(job)
        if var not in results:
            missing_results.append("%s -> %s" % (job, var))

    phantom_needs = [name for name in sorted(needs) if name not in is_job]
    untiered_results = [name for name in sorted(results) if name not in tiers]
    orphan_tiers = [name for name in sorted(tiers) if name not in results]

    print()
    print("CI Job Aggregation")
    print("============================================================")
    print(
        "%d top-level job(s) in %s; %d exempt; %d in %s's needs; %d RESULT_* var(s); "
        "%d tier member(s)."
        % (len(jobs), workflow.name, len(exempt), needs_count, AGGREGATOR, len(results), len(tiers))
    )
    print()

    failed = False

    if missing_needs:
        log.error(
            "%d job(s) NOT in %s's needs: they can fail while the required check stays "
            "green:" % (len(missing_needs), AGGREGATOR)
        )
        for job in missing_needs:
            print("  %s" % job)
        print("  Fix: add each to the 'needs:' list of %s in %s," % (AGGREGATOR, workflow))
        print("  or add it to the exempt block in this script with a BLOCKER reason.")
        failed = True

    if missing_results:
        log.error(
            "%d job(s) with no RESULT_* env var: assert-ci-complete.sh never sees them:"
            % len(missing_results)
        )
        for job in missing_results:
            print("  %s" % job)
        print(
            "  Fix: add 'RESULT_<JOB>: ${{ needs.<job>.result }}' to the env: block of %s."
            % AGGREGATOR
        )
        failed = True

    if phantom_needs:
        log.error(
            "%d needs entry/entries naming no such job: GitHub rejects this workflow:"
            % len(phantom_needs)
        )
        for name in phantom_needs:
            print("  %s" % name)
        failed = True

    if untiered_results:
        log.error(
            "%d RESULT_* var(s) in neither HARD_REQUIRED nor SOFT_REQUIRED: passed and "
            "dropped:" % len(untiered_results)
        )
        for name in untiered_results:
            print("  %s" % name)
        print("  Fix: add the job to a tier in %s." % assert_script)
        failed = True

    if orphan_tiers:
        log.error(
            "%d tier member(s) that %s never passes: the tier reads an unset var and every "
            "run is red:" % (len(orphan_tiers), AGGREGATOR)
        )
        for name in orphan_tiers:
            print("  %s" % name)
        failed = True

    if dead_exemptions:
        log.error(
            "%d exempt entry/entries naming no such job: a hole held open for nothing:"
            % len(dead_exemptions)
        )
        for entry in dead_exemptions:
            print("  %s" % entry)
        print("  Fix: delete the entry (and its BLOCKER) from the exempt block in this script.")
        failed = True

    if failed:
        print()
        log.error(
            "%s is the required status check. A job it cannot see is a job that cannot "
            "block a merge." % AGGREGATOR
        )
        return 1

    log.info("OK: every non-exempt ci.yml job is aggregated by %s and tiered." % AGGREGATOR)
    return 0


# --------------------------------------------------------------------------- Selftest ---------------------------------------------------------------------------

# A workflow written by CONSTRUCTION, never by mutating the real ci.yml. A substitution against real source silently yields an unmutated copy the day the targeted line is reworded, which is the vacuous-plant failure check-control-vacuity.sh exists for.
FIXTURE_WORKFLOW = """name: CI
on:
  push:
    branches: [main]
permissions:
  contents: read
concurrency:
  group: ci
jobs:
  initialize:
    runs-on: ubuntu-latest
  quality:
    runs-on: ubuntu-latest
  build-cli:
    runs-on: ubuntu-latest
  ci-complete:
    needs: [initialize, quality, build-cli]
    runs-on: ubuntu-latest
    env:
      RESULT_INITIALIZE: ${{ needs.initialize.result }}
      RESULT_QUALITY: ${{ needs.quality.result }}
      RESULT_BUILD_CLI: ${{ needs.build-cli.result }}
"""

FIXTURE_ASSERT = """#!/bin/bash
HARD_REQUIRED=(
    INITIALIZE
    QUALITY
)
SOFT_REQUIRED=(BUILD_CLI)
"""


def selftest() -> int:
    """Both directions for every parser and both directions for the validator.

    Each of the four checks has a plant AND a mirror, because a gate whose only controls are plants will happily flag a correctly wired workflow.
    """
    ctl = Controls("ci-job-aggregation", floor=28, verbose=True)

    # -- top_level_jobs -----------------------------------------------------
    jobs = top_level_jobs(FIXTURE_WORKFLOW)
    ctl.check(
        "PLANT: the four job keys are found, in file order",
        jobs,
        ["initialize", "quality", "build-cli", "ci-complete"],
    )
    ctl.falsy("MIRROR: the top-level `on:` key is not a job", "on" in jobs)
    ctl.falsy("MIRROR: `permissions:` is not a job", "permissions" in jobs)
    ctl.falsy("MIRROR: `concurrency:` is not a job", "concurrency" in jobs)
    ctl.falsy("MIRROR: a 4-space body key is not a job", "env" in jobs)
    ctl.check(
        "MIRROR: a workflow with no jobs: block yields nothing",
        top_level_jobs("name: x\non:\n  push:\n"),
        [],
    )
    ctl.check(
        "MIRROR: a key after the jobs block closes it",
        top_level_jobs("jobs:\n  a:\ntop:\n  b:\n"),
        ["a"],
    )

    # -- job_block ----------------------------------------------------------
    block = job_block(FIXTURE_WORKFLOW, AGGREGATOR)
    ctl.truthy("PLANT: the aggregator's body is extracted", "needs: [" in block)
    ctl.falsy("MIRROR: the body stops at the next job key", "runs-on: ubuntu-latest\n  q" in block)
    ctl.check(
        "MIRROR: an absent job yields an EMPTY block, which the gate must refuse",
        job_block(FIXTURE_WORKFLOW, "no-such-job"),
        "",
    )

    # -- needs_names --------------------------------------------------------
    ctl.check(
        "PLANT: the bracketed needs list is split",
        needs_names(block),
        ["initialize", "quality", "build-cli"],
    )
    ctl.check(
        "MIRROR: the bare `needs: a` form also survives",
        needs_names("    needs: solo\n"),
        ["solo"],
    )
    ctl.check("MIRROR: a body with no needs: yields nothing", needs_names("    runs-on: x\n"), [])

    # -- result_vars --------------------------------------------------------
    ctl.check(
        "PLANT: every RESULT_ var in the env block is found",
        result_vars(block),
        ["RESULT_INITIALIZE", "RESULT_QUALITY", "RESULT_BUILD_CLI"],
    )
    ctl.check(
        "MIRROR: a line with no RESULT_ var yields nothing",
        result_vars("      FOO: ${{ needs.x.result }}\n"),
        [],
    )
    ctl.check(
        "TWIN SHAPE: awk's match() finds only the FIRST var on a line",
        result_vars("  RESULT_A: x RESULT_B: y\n"),
        ["RESULT_A"],
    )

    # -- tier_entries -------------------------------------------------------
    ctl.check(
        "PLANT: both tiers are read, including the single-line form",
        tier_entries(FIXTURE_ASSERT),
        ["INITIALIZE", "QUALITY", "BUILD_CLI"],
    )
    ctl.check(
        "PLANT: the `+=` form is read too",
        tier_entries("HARD_REQUIRED+=(EXTRA)\n"),
        ["EXTRA"],
    )
    ctl.check(
        "MIRROR: a comment inside the array is stripped",
        tier_entries("HARD_REQUIRED=(\n  A  # why\n)\n"),
        ["A"],
    )
    ctl.check(
        "MIRROR: an unrelated array is not read",
        tier_entries("OTHER=(A B)\n"),
        [],
    )

    # -- result_var_for -----------------------------------------------------
    ctl.check("dashes fold to underscores", result_var_for("build-cli"), "RESULT_BUILD_CLI")
    ctl.check("lowercase folds to uppercase", result_var_for("quality"), "RESULT_QUALITY")
    ctl.check(
        "a character outside both tr sets passes through untouched",
        result_var_for("a.b"),
        "RESULT_A.B",
    )

    # -- the exempt set, both directions ------------------------------------
    exempt = exempt_entries()
    ctl.check("the exempt set has exactly five entries", len(exempt), 5)
    ctl.truthy("the aggregator itself is exempt", AGGREGATOR in exempt)
    ctl.check(
        "every exempt entry carries a BLOCKER reason",
        allowlist.verify(allowlist.parse_text(EXEMPT_BLOCK), "the EXEMPT block"),
        [],
    )
    ctl.truthy(
        "PLANT: a low-effort reason is REJECTED by the same validator",
        allowlist.verify(allowlist.parse_text("# BLOCKER: tbd\nsome-job\n"), "fixture"),
    )
    ctl.truthy(
        "PLANT: an entry with NO reason is rejected",
        allowlist.verify(allowlist.parse_text("some-job\n"), "fixture"),
    )

    # -- the whole gate over fixture files ----------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        def run(workflow: str, assert_body: str) -> int:
            (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
            (root / ".ci" / "scripts" / "ci").mkdir(parents=True, exist_ok=True)
            (root / ".github" / "workflows" / "ci.yml").write_text(workflow, encoding="utf-8")
            (root / ".ci" / "scripts" / "ci" / "assert-ci-complete.sh").write_text(
                assert_body, encoding="utf-8"
            )
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    os.environ.pop(paths.ROOT_ENV, None)
                else:
                    os.environ[paths.ROOT_ENV] = saved

        # FOUR jobs is under MIN_JOBS, so the floor fires before any check does. That is the anti-vacuity arm, and it must fire on a workflow that is otherwise perfectly wired.
        ctl.check(
            "PLANT: a short workflow trips the job floor rather than passing",
            run(FIXTURE_WORKFLOW, FIXTURE_ASSERT),
            1,
        )
        ctl.check(
            "PLANT: a missing workflow refuses rather than skipping",
            run_missing(root),
            1,
        )

    return 0 if ctl.report() else 1


def run_missing(root: pathlib.Path) -> int:
    """Drive the gate against a root whose ci.yml has been removed.

    Separated from the closure above so the deletion is visible: an input that is not there must be a REFUSAL, and a gate that skipped it would report a clean tree for a workflow nobody read.
    """
    (root / ".github" / "workflows" / "ci.yml").unlink()
    saved = os.environ.get(paths.ROOT_ENV)
    os.environ[paths.ROOT_ENV] = str(root)
    try:
        return main([])
    finally:
        if saved is None:
            os.environ.pop(paths.ROOT_ENV, None)
        else:
            os.environ[paths.ROOT_ENV] = saved


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
