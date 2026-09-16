r"""Port of `.ci/scripts/test/gates/test-review-status.sh`.

Both-ways test for `.ci/scripts/review/review-status.sh` -- the script behind
the `Review Complete` check-run -- and, from the second half onward, for the two
top-level review-hygiene gates it shells out to.

WHY THIS CLASS NEEDS A GATE. The thing being replaced (`Review Gate` inside
Console CI) was green for months while asserting nothing about the review it is
named after: it runs on `pull_request`, before any review can have happened, and
its three scripts never look at a SHA. A successor that is merely *shaped* like a
check is worthless -- so every conclusion this script can reach is driven here
against planted state, in BOTH directions:

  - Too quiet: a stale marker, an unreviewed head, a failed review run, or a
    failing hygiene script must produce conclusion=failure. If any of those
    silently pass, the check is decoration.
  - Too loud: an empty diff, a submodule-pointer-only diff, and a cancelled
    (superseded) review run must NOT fail, and a draft PR must be neutral.
  - The deadlock case: once the review cap is reached the review pipeline refuses
    to run again, so the marker can NEVER advance. Failing there would make the
    PR permanently unmergeable. It must pass, with a warning.

GitHub is stubbed with a routing fake `gh` that applies the script's own --jq
expressions to fixture JSON, so the real jq/sed extraction is exercised rather
than reimplemented. Every write (check-run POST/PATCH) is captured and asserted
on, including WHICH SHA it was anchored to.

--------------------------------------------------------------------------
WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP
--------------------------------------------------------------------------
Read from the lock rather than inferred from the fixtures, which would mislead:
almost every case here builds a temp world and would suggest no isolation is
needed. `gates.lock.json` declares `gate-test:review-status` with
`reads: ["tree:repo"]`, and it is right. Seven cases read tracked files with no
seam at all:

  * `test_real_gate_constants_parseable` sed-parses the real
    `claude-review-gate.sh` and sources the real `.ci/scripts/lib/common.sh`.
  * `test_no_ci_job_references_review_complete` greps the real
    `.github/workflows` tree.
  * `test_workflow_does_not_trigger_on_pull_request` and
    `test_review_status_has_workflow_dispatch_with_pr_number` read the real
    `review-status.yml`.
  * `test_findings_fence_key_is_shared_with_the_pipeline` and
    `test_report_prefix_is_shared_with_the_pipeline` grep three real producer
    and consumer scripts.
  * `test_reply_thresholds_match_across_both_gates` and
    `test_review_report_count_is_shared_and_unqualified` parse constants out of
    the two real hygiene gates and `common.sh`.

Every temp-world case also RUNS the real `review-status.sh`,
`check-review-comments.sh`, `check-review-report-replies.sh` and
`claude-review-gate.sh` off the tracked tree. A battery step rewriting any of
those mid-sweep is a divergence that would be blamed on this port.

`REAL_TREE_TWIN = True` buys the serialisation, and it is honoured ONLY because
this module declares no `XDIST_GROUP` of its own; see `real_tree_admission` in
`test_twin_parity.py`, where an own group silently makes the opt-in vacuous.

NO `TWIN_TIMEOUT`. The twin was MEASURED at 75s on this machine (most of it
wall-clock spent in `common.sh`'s retry backoff on the deliberately-unreadable-API
cases, `user` time is only 7s), which is inside the driver's 600s default even
with the port driven serially after it. A declaration here would be a guess
dressed as a measurement.

--------------------------------------------------------------------------
DOES ANY SUBJECT SELF-SCAN? ONE DOES, AND IT CANNOT SEE THIS FILE
--------------------------------------------------------------------------
Asked before a fixture was written, because a subject that can see this source
turns a literal transcription into a tree-wide red for whoever runs the gate
next. Three sweeps in this file walk directories rather than named files:

  * `test_no_ci_job_references_review_complete` greps `.github/workflows` with
    `--include='*.yml'`. This file is neither.
  * `test_review_report_count_is_shared_and_unqualified` runs
    `grep -rlE '^review_report_count\(\)' .ci/scripts/` -- a RECURSIVE sweep, and
    the one that could in principle see a new file. It cannot see this one:
    the root is `.ci/scripts/`, and this module lives under
    `.ci/rediacc_ci/tests/gates/`. That is asserted rather than asserted-by-
    comment: `test_this_module_is_outside_the_review_report_count_sweep` below
    points the REAL sweep at this very directory and requires it to find
    NOTHING, so a widening of the scan root reds HERE, by name, instead of
    reddening the gate for the next session.
  * `test_findings_fence_key_is_shared_with_the_pipeline` and
    `test_report_prefix_is_shared_with_the_pipeline` grep three NAMED files.

So the fixtures are written out literally, exactly as the twin writes them, and
the port's diff can be read against its original.
"""

import json
import os
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-review-status.sh"

# Seven cases read tracked files seam-free and every temp-world case runs the
# real scripts off the tracked tree. The lock says `tree:repo` too. See the
# docstring.
REAL_TREE_TWIN = True

REPO_ROOT = paths.repo_root()
UNDER_TEST_REL = ".ci/scripts/review/review-status.sh"
UNDER_TEST = paths.from_root(*UNDER_TEST_REL.split("/"))
REAL_GATE_REL = ".ci/scripts/review/claude-review-gate.sh"
REAL_GATE = paths.from_root(*REAL_GATE_REL.split("/"))
COMMON_REL = ".ci/scripts/lib/common.sh"
COMMON = paths.from_root(*COMMON_REL.split("/"))
# TWO POINTERS PER GATE, and the split is the W7 P4 pin rule. Each of these was
# used three ways: to RUN the gate, to read it for a behavioural needle, and to
# parse a numeric threshold out of it. After the cutover those want different
# files. A harness that RUNS the gate takes the ENTRY POINT, because that is what
# CI invokes; one that reads the gate's own text takes the MODULE, because the
# entry point is a three-line shim carrying no needles and no constants.
REVIEW_COMMENTS_GATE_REL = ".ci/scripts/quality/check_review_comments.py"
REVIEW_COMMENTS_GATE = paths.from_root(*REVIEW_COMMENTS_GATE_REL.split("/"))
REVIEW_COMMENTS_SRC_REL = ".ci/rediacc_ci/quality/review_comments.py"
REVIEW_COMMENTS_SRC = paths.from_root(*REVIEW_COMMENTS_SRC_REL.split("/"))
REPORT_REPLIES_GATE_REL = ".ci/scripts/quality/check_review_report_replies.py"
REPORT_REPLIES_GATE = paths.from_root(*REPORT_REPLIES_GATE_REL.split("/"))
REPORT_REPLIES_SRC_REL = ".ci/rediacc_ci/quality/review_report_replies.py"
REPORT_REPLIES_SRC = paths.from_root(*REPORT_REPLIES_SRC_REL.split("/"))
INITIAL_PROMPT_REL = ".ci/scripts/review/prompts/initial.md"
INITIAL_PROMPT = paths.from_root(*INITIAL_PROMPT_REL.split("/"))
WORKFLOWS = paths.from_root(".github", "workflows")
REVIEW_STATUS_YML = paths.from_root(".github", "workflows", "review-status.yml")

OLD_SHA = "1111111111111111111111111111111111111111"
NEW_SHA = "2222222222222222222222222222222222222222"

# The needle the comment gate keys off to recognise a review summary, and the
# file that must keep emitting it. Asserted below so the two cannot drift apart.
FINDINGS_FENCE_KEY = "json:review-findings"
# The header the pipeline writes and the report gate matches on.
REPORT_PREFIX_KEY = "**Claude finished"


# ---------------------------------------------------------------------------
# Fixture scaffolding
# ---------------------------------------------------------------------------

FAKE_GH = r"""#!/bin/bash
# Routing fake for `gh api`. Serves fixture JSON per endpoint and applies the
# caller's own --jq expression to it (gh applies --jq per page; the fixtures are
# single-page, so this is faithful). Non-GET calls are captured, never served.
set -uo pipefail
method="GET"
explicit_method=0
has_field=0
fields=""
path=""
jqexpr=""
args=("$@")
n=${#args[@]}
i=0
while [ "$i" -lt "$n" ]; do
    a="${args[$i]}"
    case "$a" in
        api) ;;
        -X | --method)
            i=$((i + 1))
            method="${args[$i]}"
            explicit_method=1
            ;;
        --jq)
            i=$((i + 1))
            jqexpr="${args[$i]}"
            ;;
        --input | -f | -F | --field | --raw-field)
            i=$((i + 1))
            has_field=1
            fields="${fields}${args[$i]}
"
            ;;
        --paginate | --silent) ;;
        -*) ;;
        *)
            if [ -z "$path" ]; then path="$a"; fi
            ;;
    esac
    i=$((i + 1))
done
# gh INFERS POST when a field is passed without -X, and so must this fake.
# Without the inference such a call was classified GET, served a fixture, and
# never captured -- so a test asserting "the write happened" passed while
# nothing was written. That is the harness itself failing vacuously, which is
# the one bug class this whole suite exists to catch.
if [ "$explicit_method" -eq 0 ] && [ "$has_field" -eq 1 ]; then
    method="POST"
fi

if [ "$method" != "GET" ]; then
    {
        echo "METHOD=$method PATH=$path"
        cat
        echo
    } >>"$GH_CAPTURE"
    # `-f key=value` fields go to a SIDECAR file, never into $GH_CAPTURE: the
    # check-run assertions parse that file as raw JSON with jq, so anything
    # extra in it would break every existing case. A write whose payload is
    # fields rather than stdin (the attempt marker) is read from here.
    {
        echo "METHOD=$method PATH=$path"
        printf '%s' "$fields"
    } >>"${GH_CAPTURE}.fields"
    echo '{"id": 999}'
    exit 0
fi

key=""
case "$path" in
    # `gh pr view --json additions,deletions` -- how the review budget learns the
    # diff size. Without this the call falls through to "unrouted" and every test
    # silently gets a 0-line diff, i.e. the smallest cap, which would make the
    # size-tiered budget untestable.
    pr) key="pr-size" ;;
    */commits/*/pulls) key="commit-pulls" ;;
    # The workflow_run PR handoff. Two calls: list the run's artifacts, then
    # download the zip. The zip route writes a REAL zip so the script's
    # `unzip -p` runs for real rather than against a stub -- the extraction is
    # part of what can break.
    */actions/runs/*/artifacts) key="run-artifacts" ;;
    */actions/artifacts/*/zip)
        # A REAL zip on stdout, built with python3 because `zip` is not
        # installed on this box (only unzip is) and the suite already requires
        # python3. The script's `unzip -p` therefore runs for real: extraction
        # is part of what can break, so stubbing it away would leave the most
        # fragile step untested.
        if [ -f "$GH_FIXTURES/review-target.txt" ]; then
            python3 -c 'import sys,zipfile,io
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.write(sys.argv[1], "review-target.txt")
sys.stdout.buffer.write(buf.getvalue())' "$GH_FIXTURES/review-target.txt"
            exit 0
        fi
        exit 1
        ;;
    */commits/*/check-runs) key="check-runs" ;;
    */issues/*/comments) key="comments" ;;
    */compare/*) key="compare" ;;
    */pulls/*) key="pull" ;;
    *)
        echo "fake gh: unrouted path: $path" >&2
        exit 3
        ;;
esac

file="$GH_FIXTURES/$key.json"
if [ ! -f "$file" ]; then
    echo "fake gh: missing fixture $file" >&2
    exit 4
fi
if [ -n "$jqexpr" ]; then
    jq -r "$jqexpr" "$file"
else
    cat "$file"
fi
"""

FAKE_GH_COMMENTS = r"""#!/bin/bash
# Routing fake for the two comment endpoints check-review-comments.sh reads.
# Anything else is an error, never an empty list: a silently-served [] is the
# exact shape of blindness these tests exist to catch.
set -uo pipefail
# GH_FAIL_ISSUE_COMMENTS=1 makes the REST issues route fail the way a degraded
# API does. It exists so the GraphQL fallback in check-review-report-replies.sh
# can be exercised WITHOUT depending on GitHub actually being unwell -- a test
# that waited for a real outage would never run, and one that hit the live API
# would be flaky by construction.
for a in "$@"; do
    case "$a" in
        graphql)
            [ -f "$GH_FIXTURES/graphql-comments.json" ] || { echo "missing graphql-comments fixture" >&2; exit 4; }
            exec cat "$GH_FIXTURES/graphql-comments.json" ;;
        */issues/*/comments)
            if [ "${GH_FAIL_ISSUE_COMMENTS:-0}" = "1" ]; then
                echo '{"message":"Not Found","status":"404"}' >&2
                echo "gh: Not Found (HTTP 404)" >&2
                exit 1
            fi
            [ -f "$GH_FIXTURES/issue-comments.json" ] || { echo "missing issue-comments fixture" >&2; exit 4; }
            exec cat "$GH_FIXTURES/issue-comments.json" ;;
        */pulls/*/comments)
            [ -f "$GH_FIXTURES/inline-comments.json" ] || { echo "missing inline-comments fixture" >&2; exit 4; }
            exec cat "$GH_FIXTURES/inline-comments.json" ;;
    esac
done
echo "fake gh: unrouted: $*" >&2
exit 3
"""

# THE PORTS. `review-status.sh` enumerates these three by name, and W7 P4 cut it
# over on 2026-09-08; a stub written under the old name is a file the pipeline no
# longer looks for, which is a hard abort, not a green.
HYGIENE_NAMES = (
    "check_resolved_threads.py",
    "check_review_comments.py",
    "check_review_report_replies.py",
)


def require_bash(gate) -> str:
    """Every subject in this file is a bash script; prove bash exists first."""
    for rel, path in (
        (UNDER_TEST_REL, UNDER_TEST),
        (REAL_GATE_REL, REAL_GATE),
        (COMMON_REL, COMMON),
    ):
        if not path.is_file():
            gate.log_fail("subject under test is missing: %s" % rel)
    return harness.require_tool("bash", "install bash; every subject here IS a bash script")


def require_jq(_gate=None) -> str:
    return harness.require_tool(
        "jq", "install jq; the fake gh applies the subject's own --jq expressions"
    )


def write_exec(path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def write_fake_gh(directory) -> None:
    (directory / "bin").mkdir(parents=True, exist_ok=True)
    write_exec(directory / "bin" / "gh", FAKE_GH)


def write_fake_gh_comments(directory) -> None:
    (directory / "bin").mkdir(parents=True, exist_ok=True)
    write_exec(directory / "bin" / "gh", FAKE_GH_COMMENTS)


def write_hygiene(directory, a: int, b: int, c: int) -> None:
    """`write_hygiene <dir> <rc-threads> <rc-comments> <rc-reports>`."""
    hygiene = directory / "hygiene"
    hygiene.mkdir(parents=True, exist_ok=True)
    for name, rc in zip(HYGIENE_NAMES, (a, b, c), strict=True):
        write_exec(
            hygiene / name,
            '#!/bin/bash\necho "stub %s for PR ${PR_NUMBER:-?}"\nexit %d\n' % (name, rc),
        )


def marker_comment(sha: str) -> dict:
    return {
        "id": 1,
        "user": {"login": "github-actions[bot]"},
        "body": "<!-- claude-reviewed: %s -->\nAutomated Claude review completed." % sha,
    }


def report_comments(n: int) -> list:
    """`report_comments <n>` -- n finished review reports, in the shape both this
    script and claude-review-gate.sh count against the cap."""
    return [
        {
            "id": 100 + i,
            "user": {"login": "github-actions[bot]"},
            "body": "**Claude finished** the review.\n### Review\nlooks fine",
        }
        for i in range(1, n + 1)
    ]


def attempt_comments(n: int) -> list:
    """Spent review passes: budget burned, NOTHING posted. Counted against the
    same cap as a posted report, because the cost is identical."""
    return [
        {
            "id": 200 + i,
            "user": {"login": "github-actions[bot]"},
            "body": "<!-- claude-review-attempt: deadbeef -->\nburned its turns",
        }
        for i in range(1, n + 1)
    ]


def write_json(path, value) -> None:
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def setup(gate, t) -> None:
    """`setup <TEMP>` -- default world: open non-draft PR #42, head NEW_SHA,
    marker on NEW_SHA, no reports, all hygiene green."""
    require_bash(gate)
    require_jq(gate)
    (t / "fixtures").mkdir(parents=True, exist_ok=True)
    write_fake_gh(t)
    write_hygiene(t, 0, 0, 0)
    (t / ".gitmodules").write_text(
        "".join(
            line + "\n"
            for line in (
                '[submodule "private/renet"]',
                "\tpath = private/renet",
                "\turl = git@github.com:rediacc/renet.git",
                '[submodule "private/account"]',
                "\tpath = private/account",
                "\turl = git@github.com:rediacc/account.git",
            )
        ),
        encoding="utf-8",
    )

    write_json(t / "fixtures" / "commit-pulls.json", [{"number": 42, "state": "open"}])
    write_json(
        t / "fixtures" / "pull.json", {"state": "open", "draft": False, "head": {"sha": NEW_SHA}}
    )
    write_json(t / "fixtures" / "comments.json", [marker_comment(NEW_SHA)])
    write_json(t / "fixtures" / "compare.json", {"files": []})
    write_json(t / "fixtures" / "check-runs.json", {"check_runs": []})
    # Default: a small PR, so the default review budget is the smallest tier.
    write_json(t / "fixtures" / "pr-size.json", {"additions": 100, "deletions": 40})


def pr_size(t, additions: int, deletions: int) -> None:
    """`pr_size <dir> <additions> <deletions>` -- resize the PR the fake gh reports."""
    write_json(t / "fixtures" / "pr-size.json", {"additions": additions, "deletions": deletions})


class Run:
    """`LAST_OUT` and `LAST_RC`, handed back instead of set as globals.

    The twin keeps both in shell globals because a shell function cannot return
    two things. Nothing else about the contract changes: `out` is the MERGED
    stream, because every `run_*` helper in the twin captures `2>&1`.
    """

    def __init__(self, out: str, rc: int) -> None:
        self.out = out
        self.rc = rc


def run_status(gate, t, **env) -> Run:
    """`run_status <TEMP> [KEY=VALUE ...]` -- runs the script under the fake world."""
    bash = require_bash(gate)
    base = {
        "PATH": "%s%s%s" % (t / "bin", os.pathsep, os.environ.get("PATH", "")),
        "GH_FIXTURES": os.fspath(t / "fixtures"),
        "GH_CAPTURE": os.fspath(t / "capture.txt"),
        "GH_TOKEN": "fake",
        "GITHUB_REPOSITORY": "rediacc/console",
        "REVIEW_STATUS_HYGIENE_DIR": os.fspath(t / "hygiene"),
        "NO_COLOR": "1",
    }
    base.update(env)
    result = harness.run([bash, os.fspath(UNDER_TEST)], cwd=t, env=base)
    return Run(result.combined, result.rc)


def jq_r(gate, expr: str, document: str) -> str:
    """`jq -r <expr>` over a JSON document, so the twin's expressions are the
    ones that run rather than a Python re-reading of what they mean."""
    jq = require_jq(gate)
    result = harness.run([jq, "-r", expr], stdin=document)
    if result.rc != 0:
        gate.log_fail(
            "jq could not read the captured payload (rc=%s): %s\npayload: %r"
            % (harness.describe_exit(result.rc), result.err, document)
        )
    return result.out.rstrip("\n")


def posted(gate, t, expr: str) -> str:
    """`posted <TEMP> <jq-path>` -- field of the captured check-run payload.

    `sed -n '/^METHOD=/,$p' | sed '1d'`: everything from the FIRST `METHOD=`
    line onward, minus that line. Transcribed rather than simplified, because
    `test_retryable_head_with_a_stale_marker_still_fails` carries a comment
    explaining that a second capture in one directory makes this unparseable,
    and a tidier reader would quietly change which world that case describes.
    """
    capture = t / "capture.txt"
    if not capture.is_file():
        gate.log_fail(
            "no check-run was captured at all, so there is no payload to read %r out of" % expr
        )
    lines = capture.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("METHOD=")), None)
    if start is None:
        gate.log_fail("the capture file carries no METHOD= line: %r" % lines)
    return jq_r(gate, expr, "".join(line + "\n" for line in lines[start + 1 :]))


def captured_method(t) -> str:
    """`sed -n 's/^METHOD=\\([A-Z]*\\) .*/\\1/p' | tail -n 1`.

    `[ -f ]` guard, not an assumption: a test that asserts NOTHING was posted
    leaves no capture file at all, and erroring on the missing path would make
    "correctly silent" look like a harness fault.
    """
    capture = t / "capture.txt"
    if not capture.is_file():
        return ""
    methods = [
        line.split(" ", 1)[0][len("METHOD=") :]
        for line in capture.read_text(encoding="utf-8").splitlines()
        if line.startswith("METHOD=") and " " in line
    ]
    return methods[-1] if methods else ""


def captured_paths(t) -> str:
    """`sed -n 's/^METHOD=[A-Z]* PATH=//p'` over the capture."""
    capture = t / "capture.txt"
    if not capture.is_file():
        return ""
    return "\n".join(
        line.split(" PATH=", 1)[1]
        for line in capture.read_text(encoding="utf-8").splitlines()
        if line.startswith("METHOD=") and " PATH=" in line
    )


def source_common(gate, snippet: str) -> harness.RunResult:
    """`source .ci/scripts/lib/common.sh` and run one line against it.

    A SUBPROCESS per call, like the twin's own `source`-in-the-test-file, and for
    a reason the twin does not have to state: sourcing a shell library cannot
    happen in-process here at all, and shelling out keeps every helper probe in a
    process that dies with the case.
    """
    bash = require_bash(gate)
    return harness.run([bash, "-c", 'source "$1"; shift; %s' % snippet, "_", os.fspath(COMMON)])


# ---------------------------------------------------------------------------
# Anti-vacuity: the marker prefix must still be parseable out of the real gate
# script, and the review cap must come from ONE shared table.
#
# The cap used to be a constant sed-parsed out of the gate script. It is now
# sized to the diff by review_cap_for() in ../lib/common.sh, which both review
# scripts source. That is a stronger contract, not a weaker one: sed-parsing a
# number out of a sibling file was always one edit away from the two scripts
# disagreeing, and disagreement is precisely the deadlock this suite exists to
# prevent. So this asserts the SHARED function exists and that both scripts see
# identical values for it.
# ---------------------------------------------------------------------------


def test_real_gate_constants_parseable(gate):
    require_bash(gate)
    marker = ""
    for line in REAL_GATE.read_text(encoding="utf-8").splitlines():
        if line.startswith("MARKER_PREFIX='") and line.rstrip().endswith("'"):
            marker = line.rstrip()[len("MARKER_PREFIX='") : -1]
            break
    gate.assert_eq(
        marker, "<!-- claude-reviewed:", "marker prefix parsed from the real gate script"
    )

    # BLOCKER: the shared review-budget table both review scripts depend on
    probe = source_common(gate, "declare -F review_cap_for >/dev/null && echo yes || echo no")
    if probe.out.strip() != "yes":
        gate.log_fail("review_cap_for() is missing from %s" % COMMON_REL)

    # The operator's tiers, asserted at their boundaries so an off-by-one in the
    # comparison cannot pass. A cap that only ever returns its default would
    # satisfy a single-value check.
    tiers = (
        ("0", "3", "an empty diff gets the smallest budget"),
        ("10000", "3", "10k lines is still 3 reviews"),
        ("10001", "5", "just over 10k moves to 5"),
        ("50000", "5", "50k lines is still 5 reviews"),
        ("50001", "7", "just over 50k moves to 7"),
        ("250000", "7", "a huge diff stays at 7, it does not keep growing"),
        (
            "abc",
            "3",
            "an unreadable size falls to the SMALLEST budget, never a larger one",
        ),
    )
    bash = require_bash(gate)
    for size, want, why in tiers:
        result = harness.run(
            [bash, "-c", 'source "$1"; review_cap_for "$2"', "_", os.fspath(COMMON), size]
        )
        gate.assert_eq(result.out.strip(), want, why)
    gate.log_pass("review budget comes from one shared table and honours every tier boundary")


# ---------------------------------------------------------------------------
# Too loud: healthy states must not fail
# ---------------------------------------------------------------------------


def test_current_head_succeeds(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        run = run_status(gate, t, EVENT_NAME="pull_request_review", PR_NUMBER="42")
        gate.assert_exit_code(0, run.rc, "healthy PR must not error")
        gate.assert_eq(posted(gate, t, ".conclusion"), "success", "current marker + clean hygiene")
        gate.assert_eq(posted(gate, t, ".head_sha"), NEW_SHA, "check-run anchored to the PR head")
        gate.assert_eq(captured_method(t), "POST", "no existing check-run means create")
        gate.log_pass("current head + clean hygiene => success on the head SHA")


def test_empty_diff_succeeds(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(t / "fixtures" / "comments.json", [marker_comment(OLD_SHA)])
        write_json(t / "fixtures" / "compare.json", {"files": []})
        run_status(gate, t, EVENT_NAME="pull_request_review", PR_NUMBER="42")
        gate.assert_eq(
            posted(gate, t, ".conclusion"),
            "success",
            "empty diff since the reviewed SHA is equivalent",
        )
        gate.log_pass("stale marker with an EMPTY diff => success")


def test_gitlink_only_succeeds(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(t / "fixtures" / "comments.json", [marker_comment(OLD_SHA)])
        write_json(
            t / "fixtures" / "compare.json",
            {"files": [{"filename": "private/renet"}, {"filename": "private/account"}]},
        )
        run_status(gate, t, EVENT_NAME="pull_request_review", PR_NUMBER="42")
        gate.assert_eq(
            posted(gate, t, ".conclusion"),
            "success",
            "submodule pointer bumps are not reviewable code",
        )
        gate.assert_contains(
            posted(gate, t, ".output.summary"),
            "only submodule pointer bumps",
            "summary says why it passed",
        )
        gate.log_pass("stale marker with a GITLINK-ONLY diff => success")


def test_cancelled_review_run_is_not_a_failure(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        # The PR handoff Claude Review now uploads; without it the resolver is
        # correctly silent, so every workflow_run test needs it to reach the
        # behaviour it is actually asserting.
        write_json(
            t / "fixtures" / "run-artifacts.json",
            {"artifacts": [{"id": 42, "name": "review-target"}]},
        )
        (t / "fixtures" / "review-target.txt").write_text("42\n", encoding="utf-8")
        run_status(
            gate,
            t,
            EVENT_NAME="workflow_run",
            WR_RUN_ID="4242",
            WR_CONCLUSION="cancelled",
            WR_HTML_URL="https://example.invalid/run/1",
        )
        gate.assert_eq(
            posted(gate, t, ".conclusion"),
            "success",
            "a superseded (cancelled) review run must not fail the head",
        )
        gate.log_pass("cancelled Claude Review run => success (cancel-in-progress is by design)")


def test_draft_is_neutral(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(
            t / "fixtures" / "pull.json",
            {"state": "open", "draft": True, "head": {"sha": NEW_SHA}},
        )
        run_status(gate, t, EVENT_NAME="pull_request_review", PR_NUMBER="42")
        gate.assert_eq(
            posted(gate, t, ".conclusion"), "neutral", "a draft PR is not expected to be reviewed"
        )
        gate.log_pass("draft PR => neutral")


# ---------------------------------------------------------------------------
# Too quiet: PLANTED DEFECTS that must FIRE
# ---------------------------------------------------------------------------


def test_stale_head_fails(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(t / "fixtures" / "comments.json", [marker_comment(OLD_SHA)])
        write_json(
            t / "fixtures" / "compare.json",
            {"files": [{"filename": "packages/cli/src/commands/repo.ts"}]},
        )
        run = run_status(gate, t, EVENT_NAME="pull_request_review", PR_NUMBER="42")
        gate.assert_exit_code(0, run.rc, "a failing verdict is still a successful report")
        gate.assert_eq(
            posted(gate, t, ".conclusion"),
            "failure",
            "real code changed since the reviewed SHA",
        )
        summary = posted(gate, t, ".output.summary")
        gate.assert_contains(summary, NEW_SHA, "failure names the head SHA")
        gate.assert_contains(summary, OLD_SHA, "failure names the reviewed SHA")
        gate.log_pass("PLANTED stale marker => FAILURE naming both SHAs")


def test_unreviewed_head_fails(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(t / "fixtures" / "comments.json", [])
        run_status(gate, t, EVENT_NAME="pull_request_review", PR_NUMBER="42")
        gate.assert_eq(
            posted(gate, t, ".conclusion"),
            "failure",
            "no marker at all means nothing was reviewed",
        )
        gate.assert_contains(
            posted(gate, t, ".output.summary"), "no reviewed-SHA marker", "failure says why"
        )
        gate.log_pass("PLANTED missing marker => FAILURE")


def test_wrong_marker_prefix_is_seen_as_unreviewed(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        # A marker written under a DIFFERENT prefix must not be honoured -- this
        # is the shape a drifted MARKER_PREFIX would take.
        write_json(
            t / "fixtures" / "comments.json",
            [
                {
                    "id": 1,
                    "user": {"login": "github-actions[bot]"},
                    "body": "<!-- reviewed-by-somebody: %s -->" % NEW_SHA,
                }
            ],
        )
        run_status(gate, t, EVENT_NAME="pull_request_review", PR_NUMBER="42")
        gate.assert_eq(
            posted(gate, t, ".conclusion"), "failure", "a foreign marker prefix proves nothing"
        )
        gate.log_pass("PLANTED foreign marker prefix => FAILURE")


def test_failed_review_run_fails(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        # The PR handoff Claude Review now uploads; without it the resolver is
        # correctly silent, so every workflow_run test needs it to reach the
        # behaviour it is actually asserting.
        write_json(
            t / "fixtures" / "run-artifacts.json",
            {"artifacts": [{"id": 42, "name": "review-target"}]},
        )
        (t / "fixtures" / "review-target.txt").write_text("42\n", encoding="utf-8")
        run_status(
            gate,
            t,
            EVENT_NAME="workflow_run",
            WR_RUN_ID="4242",
            WR_CONCLUSION="failure",
            WR_HTML_URL="https://example.invalid/run/7",
        )
        gate.assert_eq(posted(gate, t, ".conclusion"), "failure", "the review produced no verdict")
        gate.assert_contains(
            posted(gate, t, ".output.summary"),
            "https://example.invalid/run/7",
            "failure links the run that failed",
        )
        gate.log_pass("PLANTED failed Claude Review run => FAILURE with a link")


def test_hygiene_failure_fails(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        write_hygiene(t, 0, 1, 0)
        run_status(gate, t, EVENT_NAME="issue_comment", PR_NUMBER="42")
        gate.assert_eq(
            posted(gate, t, ".conclusion"),
            "failure",
            "an unreplied review comment must block",
        )
        gate.assert_contains(
            posted(gate, t, ".output.summary"),
            "check_review_comments.py",
            "failure names the script that failed",
        )
        gate.log_pass("PLANTED hygiene failure => FAILURE naming the script")


def test_compare_failure_fails_closed(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(t / "fixtures" / "comments.json", [marker_comment(OLD_SHA)])
        (t / "fixtures" / "compare.json").unlink()  # compare API unavailable
        run_status(gate, t, EVENT_NAME="pull_request_review", PR_NUMBER="42")
        gate.assert_eq(
            posted(gate, t, ".conclusion"), "failure", "unproven equivalence is not equivalence"
        )
        gate.assert_contains(
            posted(gate, t, ".output.summary"), "compare API failed", "failure says why"
        )
        gate.log_pass("PLANTED compare-API failure => FAILURE (fails closed)")


def test_missing_hygiene_dir_hard_fails(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        (t / "hygiene" / "check_review_report_replies.py").unlink()
        run = run_status(gate, t, EVENT_NAME="pull_request_review", PR_NUMBER="42")
        if run.rc == 0:
            gate.log_fail(
                "a missing hygiene script must abort, not silently reduce the check to "
                "currency only"
            )
        gate.assert_contains(run.out, "hygiene script missing", "the abort says what is missing")
        gate.log_pass("PLANTED missing hygiene script => hard exit %d (anti-vacuity)" % run.rc)


def test_unparseable_constants_hard_fail(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        # The MARKER renamed, as a drifting refactor would leave it. The cap is
        # no longer parsed from this file (it comes from the shared
        # review_cap_for()), but the marker still is, and a silent default there
        # would make the gate compare against a prefix nothing ever posts.
        (t / "fake-gate.sh").write_text("MARKER='<!-- claude-reviewed:'\n", encoding="utf-8")
        run = run_status(
            gate,
            t,
            EVENT_NAME="pull_request_review",
            PR_NUMBER="42",
            REVIEW_STATUS_GATE_SCRIPT=os.fspath(t / "fake-gate.sh"),
        )
        if run.rc == 0:
            gate.log_fail(
                "an unparseable marker must abort, never fall back to a hard-coded default"
            )
        gate.assert_contains(
            run.out, "could not parse", "the abort names the parse it could not do"
        )
        gate.log_pass(
            "PLANTED renamed constant => hard exit %d instead of a silent default" % run.rc
        )


# ---------------------------------------------------------------------------
# The deadlock guard, driven in BOTH directions so the cap number is proven
# load-bearing rather than incidental.
# ---------------------------------------------------------------------------

# BOTH prefixes: review-status.sh parses ATTEMPT_PREFIX as well now, because the
# cap counts posted reports PLUS spent attempts. It REFUSES TO RUN without it,
# deliberately -- a missing prefix reads the cap LOW and silently recreates the
# deadlock these very tests assert against. A stub carrying only MARKER_PREFIX
# therefore exits before posting, which is exactly what this fixture used to do.
BOTH_PREFIXES = (
    "MARKER_PREFIX='<!-- claude-reviewed:'\nATTEMPT_PREFIX='<!-- claude-review-attempt:'\n"
)


def test_cap_reached_warns_instead_of_deadlocking(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(t / "fixtures" / "comments.json", [marker_comment(OLD_SHA), *report_comments(3)])
        write_json(
            t / "fixtures" / "compare.json",
            {"files": [{"filename": "packages/cli/src/commands/repo.ts"}]},
        )
        (t / "gate-cap3.sh").write_text(BOTH_PREFIXES, encoding="utf-8")
        pr_size(t, 900, 100)  # 1,000 lines -> smallest tier, cap 3

        run_status(
            gate,
            t,
            EVENT_NAME="pull_request_review",
            PR_NUMBER="42",
            REVIEW_STATUS_GATE_SCRIPT=os.fspath(t / "gate-cap3.sh"),
        )
        gate.assert_eq(
            posted(gate, t, ".conclusion"),
            "success",
            "cap reached + stale marker must stay mergeable",
        )
        gate.assert_contains(
            posted(gate, t, ".output.summary"),
            "REVIEW CAP REACHED",
            "the pass is loud, not silent",
        )
        gate.log_pass("cap reached + stale marker => success WITH A WARNING (no permanent block)")


def test_cap_reached_by_spent_attempts_alone(gate):
    """THE SHAPE THAT ACTUALLY HAPPENED, and that the case above cannot see. PR
    #553 hit its cap with ZERO posted reports and THREE spent attempts -- three
    reviews that burned their turn budget and posted nothing. review-status.sh
    counted posted reports alone, read 0/3, concluded the cap was NOT reached,
    and posted a REQUIRED failure, leaving a green, ready, thread-clean PR
    permanently unmergeable: exactly what the guard above exists to prevent. The
    sibling case passes under EITHER numerator, because 3 posted reports look
    identical to both."""
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(
            t / "fixtures" / "comments.json", [marker_comment(OLD_SHA), *attempt_comments(3)]
        )
        write_json(
            t / "fixtures" / "compare.json",
            {"files": [{"filename": "packages/cli/src/commands/repo.ts"}]},
        )
        (t / "gate-cap3.sh").write_text(BOTH_PREFIXES, encoding="utf-8")
        pr_size(t, 900, 100)  # 1,000 lines -> smallest tier, cap 3

        run_status(
            gate,
            t,
            EVENT_NAME="pull_request_review",
            PR_NUMBER="42",
            REVIEW_STATUS_GATE_SCRIPT=os.fspath(t / "gate-cap3.sh"),
        )
        gate.assert_eq(
            posted(gate, t, ".conclusion"),
            "success",
            "cap reached by SPENT attempts alone must stay mergeable (the #553 deadlock)",
        )
        gate.assert_contains(
            posted(gate, t, ".output.summary"),
            "REVIEW CAP REACHED",
            "the pass is loud here too",
        )
        gate.log_pass("0 posted + 3 spent => cap reached => success WITH A WARNING")


def test_below_cap_the_same_state_fails(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(t / "fixtures" / "comments.json", [marker_comment(OLD_SHA), *report_comments(3)])
        write_json(
            t / "fixtures" / "compare.json",
            {"files": [{"filename": "packages/cli/src/commands/repo.ts"}]},
        )
        # Identical world, cap raised: the warning must become a failure. If it
        # does not, the cap value is not actually being read.
        (t / "gate-cap9.sh").write_text(BOTH_PREFIXES, encoding="utf-8")
        # THE POINT OF THE TIERS: identical review count, different verdict,
        # purely because the diff is large enough to earn a bigger budget.
        pr_size(t, 60000, 10000)  # 70,000 lines -> top tier, cap 7

        run_status(
            gate,
            t,
            EVENT_NAME="pull_request_review",
            PR_NUMBER="42",
            REVIEW_STATUS_GATE_SCRIPT=os.fspath(t / "gate-cap9.sh"),
        )
        gate.assert_eq(
            posted(gate, t, ".conclusion"),
            "failure",
            "below the cap the same stale state must fail",
        )
        gate.assert_not_contains(
            posted(gate, t, ".output.summary"),
            "REVIEW CAP REACHED",
            "no cap warning below the cap",
        )
        gate.log_pass("same state with the cap raised => FAILURE (the parsed cap is load-bearing)")


# ---------------------------------------------------------------------------
# SHA-awareness -- the property `Review Gate` structurally cannot have
# ---------------------------------------------------------------------------


def test_anchors_to_current_head_not_event_sha(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        # The event carries the OLD sha (a late-finishing run for a superseded
        # push); the PR has moved on. The verdict must be posted against the PR's
        # CURRENT head, and must report that head as unreviewed.
        write_json(t / "fixtures" / "comments.json", [marker_comment(OLD_SHA)])
        write_json(
            t / "fixtures" / "compare.json",
            {"files": [{"filename": "packages/cli/src/commands/repo.ts"}]},
        )
        write_json(
            t / "fixtures" / "run-artifacts.json",
            {"artifacts": [{"id": 42, "name": "review-target"}]},
        )
        (t / "fixtures" / "review-target.txt").write_text("42\n", encoding="utf-8")
        run_status(
            gate,
            t,
            EVENT_NAME="workflow_run",
            WR_RUN_ID="4242",
            WR_CONCLUSION="success",
            WR_HTML_URL="https://example.invalid/run/9",
        )
        gate.assert_eq(
            posted(gate, t, ".head_sha"),
            NEW_SHA,
            "the check-run is anchored to the PR head, not the event's SHA",
        )
        gate.assert_eq(posted(gate, t, ".conclusion"), "failure", "the current head is unreviewed")
        gate.log_pass("check-run anchors to the PR's CURRENT head, not the triggering event's SHA")


def test_existing_check_run_is_patched(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(
            t / "fixtures" / "check-runs.json",
            {"check_runs": [{"id": 555, "app": {"slug": "github-actions"}}]},
        )
        run_status(gate, t, EVENT_NAME="pull_request_review", PR_NUMBER="42")
        gate.assert_eq(
            captured_method(t), "PATCH", "an existing check-run is updated, not duplicated"
        )
        gate.assert_contains(
            captured_paths(t), "check-runs/555", "the PATCH targets the existing run"
        )
        gate.assert_eq(
            posted(gate, t, '.head_sha // "absent"'),
            "absent",
            "head_sha is not a PATCH field and must be stripped",
        )
        gate.log_pass("existing check-run => PATCH without head_sha (no per-comment duplicates)")


# ---------------------------------------------------------------------------
# ACYCLICITY -- the invariant that keeps this out of CI's dependency graph.
# ---------------------------------------------------------------------------

PLANTED_DEPENDENCY = "jobs:\n  bad:\n    if: needs.review.outputs.context == 'Review Complete'\n"


def review_complete_hits(root) -> list[str]:
    """`grep -rn "Review Complete" <root> --include='*.yml'` and the three
    filters the twin applies to it, transcribed one for one.

    Python's `re`/`str` rather than `grep -E`: CLAUDE.md records that ugrep's
    `-E` returns silent false zeros when `^` is alternated with a negated class,
    and a filter chain that quietly drops everything would make this gate read
    clean for the worst possible reason.
    """
    hits = []
    for path in sorted(pathlib.Path(root).rglob("*.yml")):
        rel = os.fspath(path)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "Review Complete" not in line:
                continue
            row = "%s:%d:%s" % (rel, number, line)
            # grep -v '^.*review-status.yml'
            if "review-status.yml" in row:
                continue
            # grep -v ':.*WATCHDOG_EXCLUDE_PATTERNS:.*Review Complete'
            wat = row.find(":")
            if wat != -1:
                tail = row[wat:]
                i = tail.find("WATCHDOG_EXCLUDE_PATTERNS:")
                if i != -1 and "Review Complete" in tail[i:]:
                    continue
            # grep -vE '^[^:]*watchdog-monitor\.yml:[0-9]+: *#'
            head, _, rest = row.partition(":")
            if "watchdog-monitor.yml" in path.name and ":" not in head:
                lineno, _, text = rest.partition(":")
                if lineno.isdigit() and text.lstrip(" ").startswith("#"):
                    continue
            hits.append(row)
    return hits


def test_no_ci_job_references_review_complete(gate):
    with harness.temp_dir() as t:
        # CONTROL A, planted first: a genuine dependency on the context (a
        # `needs` or `if` style reference, anywhere other than the two documented
        # exceptions below) must still be caught.
        planted_a = t / "A"
        planted_a.mkdir()
        (planted_a / "planted.yml").write_text(PLANTED_DEPENDENCY, encoding="utf-8")
        if not review_complete_hits(planted_a):
            gate.log_fail(
                "CONTROL A failed: a genuine dependency reference on 'Review Complete' was not "
                "caught by the narrowed grep below"
            )

        # CONTROL B, review finding 2026-08-01 (PR #550): an EXECUTABLE line
        # inside a file NAMED watchdog-monitor.yml must still be caught by the
        # exact production filter chain -- the comment-line exemption below must
        # not widen into "the whole file is exempt".
        wf = t / "wf"
        wf.mkdir()
        (wf / "watchdog-monitor.yml").write_text(PLANTED_DEPENDENCY, encoding="utf-8")
        if not review_complete_hits(wf):
            gate.log_fail(
                "CONTROL B failed: an executable reference inside watchdog-monitor.yml itself "
                "was swallowed by the comment-line exemption"
            )

    # The real assertion. TWO narrow, documented exceptions, both scoped to
    # watchdog-monitor.yml specifically:
    #   1. The WATCHDOG_EXCLUDE_PATTERNS line, which EXCLUDES 'Review Complete'
    #      from the watchdog's failure scan -- the opposite of a dependency.
    #      Verified live 2026-07-31 (run 30660765759, raw
    #      `GET .../actions/runs/{id}/jobs`): the check-run this script posts is
    #      genuinely attributed to the SAME run_id as an unrelated Console CI run
    #      (both ride the github-actions app's shared check_suite for that head
    #      SHA), so the watchdog's per-run job listing sees it and MUST be told
    #      to ignore it, or a not-yet-re-reviewed head deadlocks the very run
    #      that would re-review it.
    #   2. Comment lines (matched by content, `# ...`, never by wording) in that
    #      same file explaining the exclusion above. Review finding 2026-08-01
    #      (PR #550): the first version of this gate exempted exactly ONE line by
    #      content match, and the explanatory comment one line above it survived
    #      only by ACCIDENT -- it happens to also contain the substring
    #      "review-status.yml", which the OLDER, unrelated exemption above (meant
    #      for review-status.yml's own self-references) also matches. A comment
    #      reword that keeps the same meaning but drops that one substring would
    #      have flipped this gate red for no functional reason, and CONTROL A
    #      alone could not catch it (it only plants a synthetic executable
    #      reference, never a comment). Comments cannot create a real
    #      `needs`/`if` coupling in GitHub Actions' dependency graph, so
    #      exempting them by shape is sound, not just convenient.
    # Neither exception applies outside watchdog-monitor.yml.
    hits = review_complete_hits(WORKFLOWS)
    if hits:
        gate.log_fail(
            "a workflow other than review-status.yml references 'Review Complete' outside the "
            "documented watchdog exceptions -- that is a cycle:\n%s" % "\n".join(hits)
        )
    if "Review Complete" not in UNDER_TEST.read_text(encoding="utf-8"):
        gate.log_fail(
            "review-status.sh no longer names the check it posts; this acyclicity check went blind"
        )
    gate.log_pass(
        "no workflow but review-status.yml mentions the 'Review Complete' context, apart from "
        "the documented watchdog exceptions"
    )


def test_workflow_does_not_trigger_on_pull_request(gate):
    text = REVIEW_STATUS_YML.read_text(encoding="utf-8")
    lines = text.splitlines()
    # `pull_request` would run the PR's OWN copy of this workflow, letting a PR
    # edit the logic that judges it. All four real triggers run the default
    # branch copy.
    if any(line.rstrip() == "  pull_request:" for line in lines):
        gate.log_fail(
            "review-status.yml triggers on pull_request; a PR could then edit its own judge"
        )
    for ev in (
        "workflow_run:",
        "pull_request_review:",
        "pull_request_review_comment:",
        "issue_comment:",
    ):
        if not any(line.startswith("  " + ev) for line in lines):
            gate.log_fail("review-status.yml lost its '%s' trigger" % ev)
    if "checks: write" not in text:
        gate.log_fail("review-status.yml cannot post a check-run without checks: write")
    gate.log_pass("workflow keeps its four default-branch triggers and never uses pull_request")


# ---------------------------------------------------------------------------
# workflow_dispatch -- closes the head-SHA gap a workflow_run event hits when
# Claude Review was itself invoked via workflow_dispatch (its head_sha is the
# dispatch ref, e.g. main, never the PR head -- documented GitHub Actions
# behavior). See agent/PLAN-github-actions-workflow-run-trigger-fix.md.
# ---------------------------------------------------------------------------


def test_workflow_dispatch_resolves_pr_directly(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        # No commit-pulls fixture entry needed at all for this path -- the whole
        # point is EVENT_NAME=workflow_dispatch must never call commits/.../pulls.
        write_json(t / "fixtures" / "commit-pulls.json", [])
        run = run_status(gate, t, EVENT_NAME="workflow_dispatch", PR_NUMBER="42")
        gate.assert_exit_code(
            0, run.rc, "workflow_dispatch must resolve without a commit->PR lookup"
        )
        gate.assert_eq(
            posted(gate, t, ".conclusion"),
            "success",
            "current marker + clean hygiene, same as any other entry point",
        )
        gate.assert_eq(
            posted(gate, t, ".head_sha"),
            NEW_SHA,
            "check-run anchored to the PR's live head, not any dispatch ref",
        )
        gate.log_pass(
            "workflow_dispatch (PLANTED: empty commit-pulls) still resolves PR #42 via PR_NUMBER"
        )


# THIS CASE USED TO ASSERT THE BUG AS THE SPECIFICATION.
#
# It was `test_workflow_run_with_unassociated_sha_reports_nothing`, and it drove
# EVENT_NAME=workflow_run with main's SHA expecting silent success -- codifying
# the exact no-op that left the REQUIRED `Review Complete` check unposted on
# every PR. Its log line even argued the lookup could not be fixed and a separate
# dispatch path was the answer. Measured 2026-08-06: that arm had never resolved
# a PR in production, so the suite was green on a path that never worked.
#
# The three cases below replace it, and they split the case the old one
# conflated: no artifact (a push to main, legitimately PR-less) must stay silent,
# while an artifact that exists and cannot be honoured must be LOUD.


def test_workflow_run_without_artifact_is_silent(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        # No review-target artifact: the triggering run had no PR. This is the
        # main-push case and silence is correct -- reddening it would redden
        # every push to main.
        write_json(t / "fixtures" / "run-artifacts.json", {"artifacts": []})
        run = run_status(
            gate,
            t,
            EVENT_NAME="workflow_run",
            WR_RUN_ID="9001",
            WR_CONCLUSION="success",
            WR_HTML_URL="https://example.invalid/run/9001",
        )
        gate.assert_exit_code(0, run.rc, "a PR-less triggering run is a no-op, not an error")
        gate.assert_eq(
            captured_method(t), "", "nothing is posted when no review-target artifact exists"
        )
        gate.log_pass("workflow_run with no artifact stays silent (main-push safe)")


def test_workflow_run_with_artifact_posts_the_check(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        # The artifact names PR 42, which setup() wires as open at NEW_SHA.
        write_json(
            t / "fixtures" / "run-artifacts.json",
            {"artifacts": [{"id": 77, "name": "review-target"}]},
        )
        (t / "fixtures" / "review-target.txt").write_text("42\n", encoding="utf-8")
        run = run_status(
            gate,
            t,
            EVENT_NAME="workflow_run",
            WR_RUN_ID="9002",
            WR_CONCLUSION="success",
            WR_HTML_URL="https://example.invalid/run/9002",
        )
        gate.assert_exit_code(0, run.rc, "a resolvable PR reports normally")
        gate.assert_eq(
            captured_method(t), "POST", "FIRE: the check-run is posted for the handed-over PR"
        )
        gate.assert_eq(
            posted(gate, t, ".head_sha"),
            NEW_SHA,
            "anchored to the PR's live head, not the triggering run's",
        )
        gate.log_pass(
            "FIRE: workflow_run resolves the PR from the artifact and posts (the case that "
            "never worked)"
        )


def test_workflow_run_with_unhonourable_artifact_is_loud(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        # The artifact EXISTS but carries no PR number. Under the old code every
        # failure to resolve exited 0; here presence makes it binding, so this
        # must be a non-zero exit rather than another silent success.
        write_json(
            t / "fixtures" / "run-artifacts.json",
            {"artifacts": [{"id": 78, "name": "review-target"}]},
        )
        (t / "fixtures" / "review-target.txt").write_text("\n", encoding="utf-8")
        run = run_status(
            gate,
            t,
            EVENT_NAME="workflow_run",
            WR_RUN_ID="9003",
            WR_CONCLUSION="success",
            WR_HTML_URL="https://example.invalid/run/9003",
        )
        gate.assert_exit_code(
            1, run.rc, "an artifact that cannot be honoured is a REPORTER failure, not silence"
        )
        gate.assert_contains(
            run.out,
            "resolving the PR",
            "and it must have REACHED the resolve path before failing, not died earlier",
        )
        gate.assert_eq(captured_method(t), "", "nothing is posted when the handoff is malformed")
        gate.log_pass(
            "CONTROL: the loud path is reachable -- a present-but-empty artifact exits non-zero"
        )


def test_workflow_dispatch_requires_pr_number(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        run = run_status(gate, t, EVENT_NAME="workflow_dispatch")
        if run.rc == 0:
            gate.log_fail(
                "workflow_dispatch without PR_NUMBER must abort, not silently report nothing"
            )
        gate.assert_contains(run.out, "PR_NUMBER", "the abort names the missing var")
        gate.log_pass("PLANTED missing PR_NUMBER on workflow_dispatch => hard exit")


# ---------------------------------------------------------------------------
# F2 -- a hygiene-only failure (head genuinely reviewed, a hygiene script
# failed) must read differently in the check-run TITLE than a never-reviewed
# head, so the checks list communicates the right next action on its own.
# ---------------------------------------------------------------------------


def test_hygiene_only_failure_title_says_reviewed(gate):
    with harness.temp_dir() as t:
        setup(gate, t)  # marker already on NEW_SHA (current head) by default
        write_hygiene(t, 0, 1, 0)  # check_review_comments.py fails; currency stays true
        run_status(gate, t, EVENT_NAME="pull_request_review", PR_NUMBER="42")
        gate.assert_eq(
            posted(gate, t, ".conclusion"), "failure", "hygiene failure still fails the check"
        )
        gate.assert_eq(
            posted(gate, t, ".output.title"),
            "Reviewed, but needs attention (see failures)",
            "title distinguishes a reviewed-but-unaddressed head from a never-reviewed one",
        )
        gate.log_pass(
            "PLANTED hygiene failure on a CURRENT-head PR => title says 'Reviewed, but needs "
            "attention'"
        )


def test_unreviewed_head_title_unchanged(gate):
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(t / "fixtures" / "comments.json", [])  # CONTROL: no marker at all
        run_status(gate, t, EVENT_NAME="pull_request_review", PR_NUMBER="42")
        gate.assert_eq(posted(gate, t, ".conclusion"), "failure", "still fails")
        gate.assert_eq(
            posted(gate, t, ".output.title"),
            "Review is not complete for this head",
            "CONTROL: a genuinely unreviewed head keeps the original title",
        )
        gate.log_pass(
            "CONTROL: unreviewed head keeps 'Review is not complete for this head', unaffected by F2"
        )


# ===========================================================================
# check-review-comments.sh -- the TOP-LEVEL review summary.
#
# The cases above stub the three hygiene scripts, so nothing there had ever
# driven the real one. That mattered: until 2026-08-05 check-review-comments.sh
# read ONLY repos/{REPO}/pulls/{PR}/comments (the inline review threads), and the
# review's actual verdict is posted as a TOP-LEVEL comment on
# repos/{REPO}/issues/{PR}/comments. So the reviewer could post a full verdict
# with findings, nobody answer it, and this gate report the PR clean.
#
# Live proof, PR #551: issue comment 5189236393, github-actions[bot], 8141
# chars, opening "## Review verdict: approve with one correctness finding to
# fix", sat unanswered while the Review Gate went green.
#
# These cases drive the REAL script (no stub) against a routing fake `gh`,
# separate from the one above so the review-status fixtures stay untouched --
# the review-status fake maps `*/pulls/*` to the PR object, which is the wrong
# body for the inline-comments endpoint.
# ===========================================================================

# The fence delimiter is assembled from a variable rather than written inline:
# three literal backticks inside a string are a parsing hazard for no benefit.
TICKS = "```"

SUMMARY_BODY = "\n".join(
    (
        "## Review verdict: approve with one correctness finding to fix",
        "",
        "The CLI datastore path is stat-ed against the machine default.",
        "",
        "<details><summary>machine-readable findings</summary>",
        "",
        TICKS + FINDINGS_FENCE_KEY,
        '[{"path": "a.ts", "line": 4, "severity": "medium", "title": "t", "body": "b"}]',
        TICKS,
        "",
        "</details>",
    )
)


def summary_comment(id_: int, created: str, body: str = "") -> dict:
    """The real shape: bot author, plus the machine-readable findings fence that
    claude-review-gate.sh --post-findings uses to locate this very comment."""
    return {
        "id": id_,
        "created_at": created,
        "user": {"login": "github-actions[bot]"},
        "body": body or SUMMARY_BODY,
    }


def chatter_comment(id_: int, created: str, author: str, body: str) -> dict:
    return {"id": id_, "created_at": created, "user": {"login": author}, "body": body}


def human_answer_body() -> str:
    """A per-finding answer of the shape the operator actually posted on #551
    (2856 chars, no id citation) -- long-form, by a human."""
    return (
        "The finding was correct and is fixed. The datastore-scoped stat now resolves the "
        "named datastore mount before measuring, mirroring recordedDatastoreMount, so a fork "
        "out of a named datastore is metered against its real size rather than the 1 GB "
        "floor. The nit about the duplicated jq expression is deferred to the follow-up "
        "worklist item; the coverage map lists the translation bundles as unreviewed, which "
        "is acceptable because they are generated."
    )


def comments_fixture(t, *objects: dict) -> None:
    """`comments_fixture <dir> <json-object...>` -- assemble the issue-comment list."""
    write_json(t / "fixtures" / "issue-comments.json", list(objects))


def setup_comments(gate, t) -> None:
    require_bash(gate)
    require_jq(gate)
    (t / "fixtures").mkdir(parents=True, exist_ok=True)
    write_fake_gh_comments(t)
    # No inline threads by default: the top-level path must work on its own, and
    # it used to be unreachable because an empty inline list exited 0 early.
    write_json(t / "fixtures" / "inline-comments.json", [])
    write_json(t / "fixtures" / "issue-comments.json", [])


def run_comments_gate(gate, t, **env) -> Run:
    # The CALL is the assertion, not the value: it proves bash exists and that
    # the three bash subjects are on disk. The gate below is invoked by its own
    # shebang, so nothing here needs the interpreter path any more.
    require_bash(gate)
    base = {
        "PATH": "%s%s%s" % (t / "bin", os.pathsep, os.environ.get("PATH", "")),
        "GH_FIXTURES": os.fspath(t / "fixtures"),
        "GH_TOKEN": "fake",
        "GITHUB_REPOSITORY": "rediacc/console",
        "PR_NUMBER": "42",
        "NO_COLOR": "1",
    }
    base.update(env)
    # NO `bash` PREFIX: the entry point is a `.py` with its own shebang, and
    # bash handed a Python file reports a syntax error rather than a verdict.
    result = harness.run([os.fspath(REVIEW_COMMENTS_GATE)], env=base)
    return Run(result.combined, result.rc)


# ANTI-VACUITY. The gate recognises the summary by the fence the review pipeline
# emits. If that key is ever renamed in the pipeline and not here, the gate goes
# permanently blind while still reporting "OK" -- the original defect, regrown.
# Assert the key still exists in BOTH producers.


def test_findings_fence_key_is_shared_with_the_pipeline(gate):
    if FINDINGS_FENCE_KEY not in REAL_GATE.read_text(encoding="utf-8"):
        gate.log_fail(
            "claude-review-gate.sh no longer emits/parses '%s'; check-review-comments.sh keys "
            "off it and just went blind" % FINDINGS_FENCE_KEY
        )
    if FINDINGS_FENCE_KEY not in REVIEW_COMMENTS_SRC.read_text(encoding="utf-8"):
        gate.log_fail(
            "review_comments.py no longer keys off '%s'; it cannot recognise a review "
            "summary" % FINDINGS_FENCE_KEY
        )
    if FINDINGS_FENCE_KEY not in INITIAL_PROMPT.read_text(encoding="utf-8"):
        gate.log_fail(
            "the review prompt no longer mandates the '%s' block, so summaries will stop "
            "carrying the marker the gate needs" % FINDINGS_FENCE_KEY
        )
    gate.log_pass(
        "the review-findings fence is emitted by the prompt, parsed by the review gate, and "
        "keyed off by the comment gate"
    )


def test_unreplied_summary_blocks(gate):
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        comments_fixture(t, summary_comment(900, "2026-08-05T08:06:53Z"))
        run = run_comments_gate(gate, t)
        gate.assert_exit_code(1, run.rc, "an unanswered top-level review verdict must BLOCK")
        gate.assert_contains(run.out, "UNANSWERED REVIEW SUMMARY", "the block names the class")
        gate.assert_contains(run.out, "issuecomment-900", "and links the exact comment")
        # Autofix guidance is part of the contract, not decoration: a future
        # agent must be able to act from this output with no rediscovery.
        gate.assert_contains(
            run.out,
            "gh api repos/rediacc/console/issues/42/comments -X POST",
            "the output carries the exact command that posts an answer",
        )
        gate.assert_contains(run.out, "Re: review summary 900", "pre-filled with the comment id")
        gate.assert_contains(
            run.out,
            "comments/900/replies",
            "and warns about the replies endpoints that 404 for an issue comment",
        )
        gate.log_pass(
            "PLANTED unanswered review summary => BLOCKS, with a copy-pasteable answer command"
        )


def test_answered_summary_passes(gate):
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        comments_fixture(
            t,
            summary_comment(900, "2026-08-05T08:06:53Z"),
            chatter_comment(903, "2026-08-05T10:29:55Z", "mfbayraktar", human_answer_body()),
        )
        run = run_comments_gate(gate, t)
        gate.assert_exit_code(0, run.rc, "a per-finding human answer addresses the summary")
        gate.assert_contains(
            run.out, "answered by comment 903", "and the pass says which comment answered it"
        )
        gate.log_pass("a substantive human answer => PASSES (the live shape of PR #551 today)")


def test_ordinary_chatter_is_ignored(gate):
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        # CONTROL: issues/{PR}/comments carries every kind of PR chatter. None of
        # it is a review verdict, so none of it may block. A gate that blocked
        # here would be suppressed within a day.
        comments_fixture(
            t,
            chatter_comment(
                800,
                "2026-08-05T07:00:00Z",
                "github-actions[bot]",
                "Deploy preview is ready: https://pr-42.example.invalid and the bundle grew by "
                "3 kB since the last push, which is within budget.",
            ),
            chatter_comment(
                801,
                "2026-08-05T07:10:00Z",
                "github-actions[bot]",
                "<!-- claude-reviewed: 2222222222222222222222222222222222222222 -->\n"
                "Automated Claude review completed for commit 2222222. Cost: $4.66",
            ),
            chatter_comment(
                802,
                "2026-08-05T07:20:00Z",
                "mfbayraktar",
                "Rebased onto main to pick up the label fix; rerunning the failed jobs now "
                "rather than pushing an empty commit.",
            ),
        )
        run = run_comments_gate(gate, t)
        gate.assert_exit_code(0, run.rc, "ordinary PR chatter is not a review verdict")
        gate.assert_contains(
            run.out, "No top-level review summary found", "and the gate says it found none"
        )
        gate.assert_not_contains(run.out, "UNANSWERED REVIEW SUMMARY", "nothing was blocked on")
        gate.log_pass(
            "CONTROL: deploy notes, the reviewed-SHA marker and operator notes are all IGNORED"
        )


def test_second_bot_comment_is_not_a_reply(gate):
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        # THE TRAP. The pipeline posts several comments in a row under one
        # identity: on #551 the marker comment landed 14 SECONDS after the
        # summary, and the "**Claude finished" wrapper 10 seconds after it. Both
        # are long enough to clear every substance test. If author were ignored,
        # the review would "answer" itself on every PR and this gate could never
        # fire once.
        comments_fixture(
            t,
            summary_comment(900, "2026-08-05T08:06:53Z"),
            chatter_comment(
                901,
                "2026-08-05T08:07:03Z",
                "github-actions[bot]",
                "**Claude finished the automated review of 208c8a2**\n\n---\n\nPosted the "
                "review. Verdict: approve with one correctness finding. I read the CLI "
                "datastore paths deeply and skimmed the generated bundles, which is recorded "
                "in the coverage map above.",
            ),
            chatter_comment(
                902,
                "2026-08-05T08:07:07Z",
                "github-actions[bot]",
                "<!-- claude-reviewed: 2222222222222222222222222222222222222222 -->\n"
                "Automated Claude review completed for commit 208c8a2. Cost: $4.6617 "
                "(claude-sonnet-5 35771out) | 84 turns | 21m3s",
            ),
        )
        run = run_comments_gate(gate, t)
        gate.assert_exit_code(
            1, run.rc, "the reviewer's own follow-up comments are not an answer to its verdict"
        )
        gate.assert_contains(run.out, "UNANSWERED REVIEW SUMMARY", "still reported as unanswered")
        gate.assert_contains(
            run.out,
            "second comment from the reviewer is not an answer",
            "and the output says why those two did not count",
        )
        gate.log_pass(
            "PLANTED bot self-replies (report + marker, both substantial) => still BLOCKS"
        )


def test_low_effort_answer_does_not_clear_the_summary(gate):
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        comments_fixture(
            t,
            summary_comment(900, "2026-08-05T08:06:53Z"),
            chatter_comment(
                903, "2026-08-05T09:00:00Z", "mfbayraktar", "Acknowledged, all addressed."
            ),
        )
        run = run_comments_gate(gate, t)
        gate.assert_exit_code(
            1, run.rc, "a stock acknowledgement does not address a multi-finding verdict"
        )
        # NAME THE FINDING. This gate exits 1 for an unreadable API, a missing
        # token and a failed probe as well, so a bare code cannot tell "it
        # blocked on the unanswered summary" from "it could not look".
        gate.assert_contains(
            run.out,
            "UNANSWERED REVIEW SUMMARY",
            "and it must block ON the unanswered summary, not for another reason",
        )
        gate.log_pass("PLANTED low-effort human answer => still BLOCKS")


def test_summary_check_survives_an_empty_inline_list(gate):
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        # REGRESSION GUARD for the shape of the original defect. The gate used to
        # `exit 0` the moment pulls/{PR}/comments came back empty, which is the
        # commonest case: most reviews post a verdict and no inline comment at
        # all. The summary check must run regardless.
        write_json(t / "fixtures" / "inline-comments.json", [])
        comments_fixture(t, summary_comment(900, "2026-08-05T08:06:53Z"))
        run = run_comments_gate(gate, t)
        gate.assert_exit_code(
            1, run.rc, "an empty inline list must not short-circuit the summary check"
        )
        gate.assert_contains(
            run.out,
            "No inline review comments found",
            "the inline path still reports its own emptiness",
        )
        gate.assert_contains(
            run.out, "UNANSWERED REVIEW SUMMARY", "and the summary is still judged"
        )
        gate.log_pass("PLANTED empty inline list + unanswered summary => BLOCKS (no early exit)")


def test_inline_thread_behaviour_is_unchanged(gate):
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        # The inline path is correct today and must stay bit-for-bit correct.
        # Both directions in one case: comment 10 has a substantive reply,
        # comment 20 has none. Only 20 may be reported.
        write_json(
            t / "fixtures" / "inline-comments.json",
            [
                {
                    "id": 10,
                    "in_reply_to_id": None,
                    "path": "packages/cli/src/a.ts",
                    "line": 4,
                    "user": {"login": "github-actions[bot]"},
                    "body": "**[HIGH]** - stat targets the wrong path",
                },
                {
                    "id": 11,
                    "in_reply_to_id": 10,
                    "path": "packages/cli/src/a.ts",
                    "line": 4,
                    "user": {"login": "mfbayraktar"},
                    "body": "Fixed by resolving the named datastore mount first.",
                },
                {
                    "id": 20,
                    "in_reply_to_id": None,
                    "path": "packages/cli/src/b.ts",
                    "line": 9,
                    "user": {"login": "github-actions[bot]"},
                    "body": "**[MEDIUM]** - unchecked exit code",
                },
            ],
        )
        run = run_comments_gate(gate, t)
        gate.assert_exit_code(1, run.rc, "an unreplied inline thread still blocks")
        gate.assert_contains(run.out, "UNREPLIED COMMENTS (1)", "exactly one thread is unreplied")
        gate.assert_contains(run.out, "packages/cli/src/b.ts:9", "and it is the one with no reply")
        gate.assert_not_contains(
            run.out, "packages/cli/src/a.ts:4", "the answered thread is not reported"
        )
        gate.assert_contains(
            run.out, "comments/{COMMENT_ID}/replies", "the inline autofix guidance is intact"
        )
        gate.assert_not_contains(
            run.out, "UNANSWERED REVIEW SUMMARY", "and no summary was invented"
        )
        gate.log_pass(
            "CONTROL: inline-thread behaviour unchanged (replied thread quiet, unreplied thread "
            "reported)"
        )


def test_unreadable_issue_comments_fail_closed(gate):
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        (t / "fixtures" / "issue-comments.json").unlink()  # the issues endpoint is unavailable
        run = run_comments_gate(gate, t)
        if run.rc == 0:
            gate.log_fail(
                "an unfetchable issue-comment list must block, not read as 'the review posted "
                "no summary'"
            )
        gate.assert_contains(run.out, "Failing closed", "the abort says it is failing closed")
        gate.log_pass(
            "PLANTED unreadable issues/{PR}/comments => FAILS CLOSED (not a silent clean PR)"
        )


# ===========================================================================
# check-review-report-replies.sh -- the pipeline's REPORT WRAPPER.
#
# The second half of the same blind spot. That gate matched the report by its
# "**Claude finished" header AND-ed with "carries the findings fence or a
# '### Review' heading". The header is a producer constant; the second clause is
# a guess about WORDING that no producer emits. On #551 the wrapper (5189238220)
# carried neither marker, so the gate found no report and exited 0 vacuously
# while an 8141-char verdict sat unanswered -- it passed that PR silently for the
# same reason check-review-comments.sh did.
#
# The two gates key off two DIFFERENT producer constants (the fence vs the
# header) and own two DIFFERENT comments, so they are complementary. What makes
# that coverage rather than a tax is that they share one reply rule, proven by
# test_one_reply_clears_both_gates below.
# ===========================================================================

REPORT_BODY = "\n".join(
    (
        REPORT_PREFIX_KEY + " the automated review of 208c8a2**",
        "",
        "---",
        "",
        "Posted the review. Summary of what I did:",
        "",
        (
            "Verdict: approve with one correctness finding. I read the CLI datastore paths "
            "deeply and skimmed the generated bundles."
        ),
    )
)


def report_comment(id_: int, created: str, body: str = "") -> dict:
    """Default body is the LIVE #551 SHAPE: the header, then the model's short
    wrap-up. No findings fence, no "### Review" heading -- the exact shape the
    old selector could not see."""
    return {
        "id": id_,
        "created_at": created,
        "user": {"login": "github-actions[bot]"},
        "body": body or REPORT_BODY,
    }


def epic_report_comment(id_: int, epic: str, created: str) -> dict:
    """The per-epic producer header. It is the SAME constant with the epic
    appended, which is what makes the fan-out an extension by dimension rather
    than a second, drifting key."""
    return report_comment(
        id_,
        created,
        "\n".join(
            (
                "%s (epic %s) the automated review of 208c8a2**" % (REPORT_PREFIX_KEY, epic),
                "",
                "---",
                "",
                "Verdict: approve with one finding in this task.",
            )
        ),
    )


def human_reply_comment(id_: int, report_id: int, created: str) -> dict:
    return chatter_comment(
        id_, created, "mfbayraktar", "Re: review report %d -- %s" % (report_id, human_answer_body())
    )


def marker_issue_comment(id_: int, created: str) -> dict:
    return chatter_comment(
        id_,
        created,
        "github-actions[bot]",
        "<!-- claude-reviewed: 2222222222222222222222222222222222222222 -->\n"
        "Automated Claude review completed for commit 208c8a2. Cost: $4.6617 "
        "(claude-sonnet-5 35771out) | 84 turns | 21m3s",
    )


def run_report_gate(gate, t, *, head_ref: str = "", publish_root: str = "", **env) -> Run:
    """PIN THE BRANCH. The reply gate fans out per epic by reading
    agent/pr/<branch>.md from the CHECKOUT, so with no pin it read whatever
    branch the developer happened to be on: on a branch that declares epics,
    every flat-path assertion below silently inverted, because the planted bare
    "**Claude finished" fixture does not match a per-epic header. A test must not
    depend on the tree it is running in. Callers that want the fan-out set
    `head_ref` to a branch whose snapshot they planted."""
    # The CALL is the assertion, not the value: it proves bash exists and that
    # the three bash subjects are on disk. The gate below is invoked by its own
    # shebang, so nothing here needs the interpreter path any more.
    require_bash(gate)
    base = {
        "PATH": "%s%s%s" % (t / "bin", os.pathsep, os.environ.get("PATH", "")),
        "GH_FIXTURES": os.fspath(t / "fixtures"),
        "GH_TOKEN": "fake",
        "GITHUB_REPOSITORY": "rediacc/console",
        "PR_NUMBER": "42",
        "NO_COLOR": "1",
        "PR_HEAD_REF": head_ref or "rs-fixture-branch-with-no-snapshot",
        "WORKLIST_PUBLISH_ROOT": publish_root,
    }
    base.update(env)
    result = harness.run([os.fspath(REPORT_REPLIES_GATE)], env=base)
    return Run(result.combined, result.rc)


# ANTI-VACUITY, same shape as the fence test: the header must still be a constant
# BOTH the producer and this consumer carry.


def test_report_prefix_is_shared_with_the_pipeline(gate):
    if REPORT_PREFIX_KEY not in REAL_GATE.read_text(encoding="utf-8"):
        gate.log_fail(
            "claude-review-gate.sh no longer writes '%s'; check-review-report-replies.sh keys "
            "off it and just went blind" % REPORT_PREFIX_KEY
        )
    if REPORT_PREFIX_KEY not in REPORT_REPLIES_SRC.read_text(encoding="utf-8"):
        gate.log_fail(
            "review_report_replies.py no longer keys off '%s'; it cannot recognise a "
            "report" % REPORT_PREFIX_KEY
        )
    gate.log_pass("the report header is a constant the pipeline writes and the report gate reads")


def test_per_epic_fanout_gates_every_epic_not_just_the_newest(gate):
    """THE PIN ABOVE HAS A COST, AND THIS PAYS IT. Pinning PR_HEAD_REF to a
    branch with no snapshot makes every flat-path test deterministic, but it
    would also hide a fan-out that had stopped working entirely: with zero epics
    the gate takes the flat path, which is exactly what those tests assert. So
    drive the OTHER side here, with a snapshot the test plants itself.

    WORKLIST_PUBLISH_ROOT points review_epic_ids() at the fixture, so this reads
    the planted snapshot and never the real tree's. It is the same override
    --publish honours, for the same reason: a test must not write into, or read
    its answer out of, the working tree another session is using."""
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        (t / "agent" / "pr").mkdir(parents=True, exist_ok=True)
        (t / "agent" / "pr" / "epicfix.md").write_text(
            "### first task\nPR-TASK: aaa111\n\n### second task\nPR-TASK: bbb222\n",
            encoding="utf-8",
        )
        # aaa111's report is answered; bbb222's is not. Newest-overall would look
        # at bbb222 alone and, if it were answered, excuse aaa111 silently. Here
        # the UNANSWERED one is newest, so the assertion that matters is that the
        # output names the per-epic accounting rather than a single global report.
        comments_fixture(
            t,
            epic_report_comment(801, "aaa111", "2026-08-26T10:00:00Z"),
            human_reply_comment(802, 801, "2026-08-26T10:05:00Z"),
            epic_report_comment(803, "bbb222", "2026-08-26T10:10:00Z"),
        )
        run = run_report_gate(gate, t, head_ref="epicfix", publish_root=os.fspath(t))
        gate.assert_exit_code(
            1,
            run.rc,
            "an unanswered epic report must block even when another epic's report was answered",
        )
        gate.assert_contains(run.out, "bbb222", "the failure names the epic that is unanswered")
        gate.log_pass("per-epic fan-out gates EVERY epic, not just the newest report")


def test_report_without_fence_or_heading_blocks(gate):
    """THE REGRESSION PIN. This is the exact live shape that slipped through: a
    real finished report with neither the fence nor a "### Review" heading."""
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        comments_fixture(t, report_comment(901, "2026-08-05T08:07:03Z"))
        run = run_report_gate(gate, t)
        gate.assert_exit_code(
            1,
            run.rc,
            "a finished report must be gated on its HEADER, not on whether its prose happens to "
            "contain a fence or a '### Review' heading",
        )
        gate.assert_contains(run.out, "issuecomment-901", "the block links the exact report")
        gate.assert_contains(
            run.out,
            "gh api repos/rediacc/console/issues/42/comments -X POST",
            "and carries the exact command that posts an answer",
        )
        gate.assert_contains(
            run.out,
            "comments/901/replies",
            "and warns about the replies endpoints that 404 for an issue comment",
        )
        gate.log_pass("PLANTED live #551 report shape (no fence, no '### Review') => BLOCKS")


def test_report_answered_passes(gate):
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        comments_fixture(
            t,
            report_comment(901, "2026-08-05T08:07:03Z"),
            chatter_comment(903, "2026-08-05T10:29:55Z", "mfbayraktar", human_answer_body()),
        )
        run = run_report_gate(gate, t)
        gate.assert_exit_code(0, run.rc, "a per-finding human answer addresses the report")
        gate.assert_contains(
            run.out, "answered by comment 903", "and the pass says which comment answered it"
        )
        gate.log_pass("report + substantive human answer => PASSES")


def test_report_bot_self_reply_does_not_count(gate):
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        # On #551 the reviewed-SHA marker landed 4 SECONDS after the report and
        # is long enough to clear every substance test. Same identity, so it must
        # not count -- otherwise the pipeline answers itself on every PR.
        comments_fixture(
            t,
            report_comment(901, "2026-08-05T08:07:03Z"),
            marker_issue_comment(902, "2026-08-05T08:07:07Z"),
        )
        run = run_report_gate(gate, t)
        gate.assert_exit_code(
            1, run.rc, "the pipeline's own marker comment is not an answer to its report"
        )
        gate.assert_contains(
            run.out,
            "second comment from the pipeline is not an answer",
            "and the output says why it did not count",
        )
        gate.log_pass("PLANTED bot self-reply (the reviewed-SHA marker) => still BLOCKS")


def test_report_ordinary_chatter_is_ignored(gate):
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        # CONTROL: no comment carries the report header, so nothing may block.
        comments_fixture(
            t,
            chatter_comment(
                800,
                "2026-08-05T07:00:00Z",
                "github-actions[bot]",
                "Deploy preview is ready: https://pr-42.example.invalid and the bundle grew by "
                "3 kB, which is within budget.",
            ),
            chatter_comment(
                802,
                "2026-08-05T07:20:00Z",
                "mfbayraktar",
                "Rebased onto main to pick up the label fix; rerunning the failed jobs now.",
            ),
        )
        run = run_report_gate(gate, t)
        gate.assert_exit_code(0, run.rc, "ordinary PR chatter is not a review report")
        gate.assert_contains(
            run.out, "No finished review report found", "and the gate says it found none"
        )
        gate.log_pass("CONTROL: deploy notes and operator notes are IGNORED by the report gate")


def test_report_unreadable_comments_fail_closed(gate):
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        (t / "fixtures" / "issue-comments.json").unlink()
        run = run_report_gate(gate, t)
        if run.rc == 0:
            gate.log_fail(
                "an unfetchable comment list must block, not read as 'no report was posted'"
            )
        gate.assert_contains(run.out, "Failing closed", "the abort says it is failing closed")
        gate.log_pass("PLANTED unreadable issues/{PR}/comments => FAILS CLOSED (report gate)")


# ---------------------------------------------------------------------------
# THE GRAPHQL FALLBACK, and why it is tested at all.
#
# On 2026-08-17 a GitHub incident made repos/<r>/issues/<n>/comments fail most
# calls. This gate then could not RUN, and a gate that cannot run does not judge
# a merge -- it blocks every one of them, which is what happened to a live
# submodule land. The fix reads the same thread over GraphQL when REST fails.
#
# NOTE WHAT IS *NOT* BEING ASSERTED. The endpoint's failure had nothing to do
# with the repo being private, though it looked exactly like that at the time:
# sampled 8 calls per repo, the private one passed ONCE and the public 8/8, and a
# single success rules an access-level cause out. So these cases inject a
# TRANSPORT failure and say nothing about visibility -- pinning a public/private
# distinction here would encode a diagnosis that measurement disproved.
#
# The fallback must not become a softer verdict, so all three directions are
# pinned: it recovers, it still DETECTS, and losing both instruments still fails
# closed.
# ---------------------------------------------------------------------------


def graphql_comments_fixture(t, *objects: dict) -> None:
    """The same comment objects in GraphQL's shape, so the fixture cannot drift
    from what the fallback actually parses: databaseId/createdAt/author.login
    rather than id/created_at/user.login."""
    write_json(
        t / "fixtures" / "graphql-comments.json",
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "comments": {
                            "nodes": [
                                {
                                    "databaseId": o["id"],
                                    "body": o["body"],
                                    "createdAt": o["created_at"],
                                    "author": {"login": o["user"]["login"]},
                                }
                                for o in objects
                            ]
                        }
                    }
                }
            }
        },
    )


def test_report_graphql_fallback_recovers_when_rest_fails(gate):
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        answered = (
            report_comment(901, "2026-08-05T08:07:03Z"),
            chatter_comment(903, "2026-08-05T10:29:55Z", "mfbayraktar", human_answer_body()),
        )
        comments_fixture(t, *answered)
        graphql_comments_fixture(t, *answered)
        run = run_report_gate(gate, t, GH_FAIL_ISSUE_COMMENTS="1")
        gate.assert_exit_code(
            0,
            run.rc,
            "with REST down the gate must still RUN via GraphQL, not block a merge it cannot judge",
        )
        gate.assert_contains(
            run.out, "903", "and it names the answering comment it found over GraphQL"
        )
        gate.log_pass("PLANTED REST 404 + answered report => GraphQL fallback RUNS and passes")


def test_report_graphql_fallback_still_detects_unanswered(gate):
    """THE CONTROL. Without this the case above proves only that the gate went
    quiet."""
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        unanswered = (report_comment(901, "2026-08-05T08:07:03Z"),)
        comments_fixture(t, *unanswered)
        graphql_comments_fixture(t, *unanswered)
        run = run_report_gate(gate, t, GH_FAIL_ISSUE_COMMENTS="1")
        gate.assert_exit_code(
            1,
            run.rc,
            "the fallback is a different TRANSPORT, not a softer verdict: an unanswered report "
            "must still block",
        )
        gate.assert_contains(
            run.out, "issuecomment-901", "and still links the exact unanswered report"
        )
        gate.log_pass("PLANTED REST 404 + UNANSWERED report => GraphQL fallback still BLOCKS")


def test_report_both_instruments_down_fails_closed(gate):
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        comments_fixture(t, report_comment(901, "2026-08-05T08:07:03Z"))
        graphql = t / "fixtures" / "graphql-comments.json"
        if graphql.is_file():
            graphql.unlink()
        run = run_report_gate(gate, t, GH_FAIL_ISSUE_COMMENTS="1")
        gate.assert_exit_code(
            1,
            run.rc,
            "losing BOTH instruments must fail closed; a fallback that swallows its own failure "
            "is worse than no fallback",
        )
        gate.assert_contains(run.out, "Failing closed", "the abort still says it is failing closed")
        gate.log_pass("PLANTED REST 404 + GraphQL unreadable => FAILS CLOSED")


# ---------------------------------------------------------------------------
# THE PROPERTY THAT MAKES TWO GATES DEFENSIBLE.
#
# One review pass leaves two top-level comments, and the two gates own one each.
# That is only worth having if answering the pass ONCE clears both -- otherwise
# the second gate is a tax on the operator and gets suppressed. Both scripts are
# driven here against ONE fixture in the live #551 arrangement, in both
# directions.
# ---------------------------------------------------------------------------


def test_one_reply_clears_both_gates(gate):
    with harness.temp_dir() as t:
        setup_comments(gate, t)
        # The #551 arrangement: reviewer's own summary (fence), then the
        # pipeline's wrapper (header, no fence), then the marker -- all within 14
        # seconds.
        unanswered = (
            summary_comment(900, "2026-08-05T08:06:53Z"),
            report_comment(901, "2026-08-05T08:07:03Z"),
            marker_issue_comment(902, "2026-08-05T08:07:07Z"),
        )
        comments_fixture(t, *unanswered)

        run = run_comments_gate(gate, t)
        gate.assert_exit_code(1, run.rc, "unanswered: the summary gate must block")
        gate.assert_contains(
            run.out,
            "UNANSWERED REVIEW SUMMARY",
            "and it must name the unanswered summary rather than fail to look",
        )
        run = run_report_gate(gate, t)
        gate.assert_exit_code(1, run.rc, "unanswered: the report gate must block too")
        gate.assert_contains(
            run.out,
            "Review Report Requires a Reply",
            "and the REPORT gate must block on the report, not on something else",
        )

        # ONE reply, posted after all three, by a human. Nothing else changes.
        comments_fixture(
            t,
            *unanswered,
            chatter_comment(903, "2026-08-05T10:29:55Z", "mfbayraktar", human_answer_body()),
        )

        run = run_comments_gate(gate, t)
        gate.assert_exit_code(0, run.rc, "one reply must clear the summary gate")
        gate.assert_contains(run.out, "answered by comment 903", "summary gate credits that reply")
        run = run_report_gate(gate, t)
        gate.assert_exit_code(
            0,
            run.rc,
            "the SAME reply must clear the report gate; a second required reply would be a tax, "
            "not coverage",
        )
        gate.assert_contains(
            run.out, "answered by comment 903", "report gate credits the same reply"
        )
        gate.log_pass(
            "ONE reply clears BOTH gates (and its absence blocks both) -- the two keys are "
            "coverage, not duplication"
        )


def parse_threshold(text: str, name: str) -> str:
    """The module-level `<name> = <digits>` assignment, or "".

    PYTHON SPELLING, not bash's `<name>=<digits>`: the constants moved into the
    modules with the port, and a parser left on the bash spelling matches nothing
    and returns "" for both sides. The callers below turn "" into a failure
    precisely so that a parser which has stopped parsing cannot masquerade as two
    thresholds that agree.
    """
    prefix = name + " = "
    for line in text.splitlines():
        if not line.startswith(prefix):
            continue
        value = line[len(prefix) :]
        digits = value.rstrip(" \t")
        if digits.isdigit():
            return digits
    return ""


def test_reply_thresholds_match_across_both_gates(gate):
    """Anti-drift for the property above: the shared rule is spelled out in two
    files, so the thresholds must be asserted equal. If one file is tuned and the
    other is not, a reply can satisfy one gate and not the other, and the
    property test above would start failing for a reason nobody could see."""
    comments_src = REVIEW_COMMENTS_SRC.read_text(encoding="utf-8")
    replies_src = REPORT_REPLIES_SRC.read_text(encoding="utf-8")
    for name in ("SUMMARY_MIN_CHARS", "SUMMARY_LONGFORM_CHARS"):
        a = parse_threshold(comments_src, name)
        b = parse_threshold(replies_src, name)
        if not a:
            gate.log_fail(
                "%s is not parseable out of review_comments.py; the two gates can no "
                "longer be proven to agree" % name
            )
        if not b:
            gate.log_fail(
                "%s is not parseable out of review_report_replies.py; the two gates can "
                "no longer be proven to agree" % name
            )
        gate.assert_eq(b, a, "%s must be identical in both gates so one reply clears both" % name)
    gate.log_pass(
        "both top-level gates carry identical reply thresholds (%s/%s)"
        % (
            parse_threshold(comments_src, "SUMMARY_MIN_CHARS"),
            parse_threshold(comments_src, "SUMMARY_LONGFORM_CHARS"),
        )
    )


def review_report_count_defs(root) -> list[str]:
    """`grep -rlE '^review_report_count\\(\\)' <root>`, sorted.

    A FUNCTION rather than an inline sweep so that
    `test_this_module_is_outside_the_review_report_count_sweep` can point the
    SAME code at this directory. A control that re-implements the sweep it is
    controlling proves nothing about the sweep.
    """
    found = []
    for path in sorted(pathlib.Path(root).rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(line.startswith("review_report_count()") for line in text.splitlines()):
            found.append(os.fspath(path))
    return sorted(found)


def test_review_report_count_is_shared_and_unqualified(gate):
    # The numerator in "X/Y reviews used". Two failures are pinned here because
    # both actually happened.
    #
    # ONE DEFINITION. It existed as identical copies in claude-review-gate.sh
    # (which counts) and review-status.sh (which reports the fraction). Two
    # copies of a numerator drift, and the denominator already lives in common.sh
    # for exactly that reason.
    defs = review_report_count_defs(paths.from_root(".ci", "scripts"))
    if defs != [os.fspath(COMMON)]:
        gate.log_fail(
            "review_report_count() must be defined ONLY in %s, found in: %s"
            % (COMMON_REL, ", ".join(defs) or "<nowhere>")
        )

    # NO CONTENT QUALIFIER. Both copies used to AND the header with
    # (json:review-findings OR "### Review"), a guess about the report's wording
    # that no producer emits. Measured live when it was removed: #551 counted 0
    # of 1 -- a completed, marked review registering as never having happened, so
    # the cap never advanced and every push re-reviewed at full price.
    lines = COMMON.read_text(encoding="utf-8").splitlines()
    body_lines, inside = [], False
    for line in lines:
        if not inside and line.startswith("review_report_count()"):
            inside = True
        if inside:
            body_lines.append(line)
            if line == "}":
                break
    body = "".join(line + "\n" for line in body_lines)
    if not body:
        gate.log_fail("could not extract review_report_count() from common.sh")
    # The per-epic review PARAMETERISES the header, so the constant no longer
    # sits literally inside startswith(). What must still hold is that the key IS
    # the producer constant: the base needle is the bare header, the epic form
    # EXTENDS that same header with its id, and startswith() keys on that
    # variable and nothing else. Extending by DIMENSION is allowed here; ANDing a
    # guess about the body's prose is what the next check forbids.
    if 'needle="**Claude finished"' not in body:
        gate.log_fail(
            "review_report_count()'s base needle is no longer the bare **Claude finished "
            "header, which is the producer constant claude-review-gate.sh writes verbatim"
        )
    if 'needle="**Claude finished (epic ' not in body:
        gate.log_fail(
            "review_report_count() lost its per-epic form; with one report per epic a global "
            "count blows the cap on round one"
        )
    if r"startswith(\"${needle}\")" not in body:
        gate.log_fail(
            "review_report_count() no longer keys startswith() on the needle, so the header it "
            "counts is not the one the producer writes"
        )
    if "json:review-findings" in body or "### Review" in body:
        gate.log_fail(
            "review_report_count() has regained a content qualifier; that undercounts real "
            "reviews and makes the cap unreachable -- exclude on something the producer emits "
            "on purpose, not on its prose"
        )
    gate.log_pass(
        "review_report_count() is defined once, in common.sh, and keys on the producer header "
        "alone, per epic"
    )


def test_this_module_is_outside_the_review_report_count_sweep(gate):
    """ADDED BY THE PORT, and the docstring explains why it has to exist.

    `test_review_report_count_is_shared_and_unqualified` runs a RECURSIVE sweep
    and asserts it finds exactly ONE file. This module is not under its root
    today, so the fixtures above are written literally. That is a claim about a
    scan root, and a claim is worth a control: this points the SAME sweep
    function at the directory these ports live in and requires it to find
    NOTHING. A widened scan root, or a `.sh` file appearing beside these ports
    with that definition in it, reds HERE by name instead of reddening
    `check:ci-review-*` for whoever runs it next.
    """
    here = pathlib.Path(__file__).resolve().parent
    seen = review_report_count_defs(here)
    if seen:
        gate.log_fail(
            "the review_report_count() sweep can now see the ported gate tests (%s). The "
            "fixtures in this module are written LITERALLY on the strength of it not being "
            "able to; either scope the sweep back to .ci/scripts or render those fixtures "
            "through a template." % ", ".join(seen)
        )
    # ANTI-VACUITY for the control itself: an empty result also happens when the
    # sweep is pointed at a directory with no files in it at all.
    scanned = len([p for p in here.rglob("*") if p.is_file()])
    if scanned == 0:
        gate.log_fail(
            "the control scanned ZERO files, so its silence is about an empty directory rather "
            "than about the sweep's scope"
        )
    gate.log_pass(
        "the review_report_count() sweep sees none of the %d file(s) in %s"
        % (scanned, here.relative_to(REPO_ROOT))
    )


def test_review_status_has_workflow_dispatch_with_pr_number(gate):
    lines = REVIEW_STATUS_YML.read_text(encoding="utf-8").splitlines()
    if not any(line.rstrip() == "  workflow_dispatch:" for line in lines):
        gate.log_fail("review-status.yml lost its workflow_dispatch trigger")
    if not any("pr_number:" in line for line in lines):
        gate.log_fail("review-status.yml's workflow_dispatch has no pr_number input")
    gate.log_pass("review-status.yml declares workflow_dispatch with a pr_number input")


# ---------------------------------------------------------------------------
# THE ATTEMPT BUDGET (2026-08-09). A reportless review attempt used to be
# terminal for its head: it charged a budget unit and its marker said "push a
# change to earn another pass". On PR #560 that stalled a fully-green,
# autopilot-driven PR behind a human, because there was no legitimate change to
# push. An INFRA-CLASS death now gets bounded free re-attempts on the same head.
#
# These cases live in this file, rather than beside the --apply-labels tests,
# because the attempt marker is the SHARED STATE between claude-review-gate.sh
# and review-status.sh, and this file already owns the budget contract that both
# of them read. Splitting it would recreate the #553 split-numerator problem in
# the tests instead of in the code.
# ---------------------------------------------------------------------------


def attempt_marker(id_: int, sha: str, attempts: int, cls: str) -> dict:
    """`attempt_marker <id> <sha> <attempts> <class>` -- the NEW marker shape."""
    return {
        "id": id_,
        "user": {"login": "github-actions[bot]"},
        "body": (
            "<!-- claude-review-attempt: %s -->\nattempts: %d\nclass: %s\n"
            "A review pass was attempted and produced no report." % (sha, attempts, cls)
        ),
    }


def chargeable(gate, table: str) -> str:
    bash = require_bash(gate)
    result = harness.run(
        [
            bash,
            "-c",
            'source "$1"; review_chargeable_attempts "$2"',
            "_",
            os.fspath(COMMON),
            table,
        ]
    )
    if result.rc != 0:
        gate.log_fail(
            "review_chargeable_attempts could not be driven (rc=%s): %s"
            % (harness.describe_exit(result.rc), result.combined)
        )
    return result.out.strip()


def head_is_exhausted(gate, table: str, head: str) -> int:
    bash = require_bash(gate)
    return harness.run(
        [
            bash,
            "-c",
            'source "$1"; review_head_is_exhausted "$2" "$3"',
            "_",
            os.fspath(COMMON),
            table,
            head,
        ]
    ).rc


def test_attempt_accounting_helpers(gate):
    """PURE, so both directions are provable without a network. These functions
    are the numerator the cap is measured against; the integration cases below
    can only show one point of the curve each."""
    # BLOCKER: the shared review-budget helpers both review scripts depend on
    gate.assert_eq(
        chargeable(gate, "aaa\t1\terror_max_turns"),
        "0",
        "the first infra-class attempt on a head is free",
    )
    gate.assert_eq(chargeable(gate, "aaa\t2\terror_max_turns"), "0", "so is the second")
    gate.assert_eq(chargeable(gate, "aaa\t3\terror_max_turns"), "1", "the third is charged")
    gate.assert_eq(
        chargeable(gate, "aaa\t3\terror_during_execution"),
        "1",
        "error_during_execution is the same class of failure",
    )

    # CONTROL: an unknown failure keeps the old rule exactly. "We do not know why
    # it died" is the case where retrying forever is most expensive.
    gate.assert_eq(
        chargeable(gate, "aaa\t1\treview step did not succeed"),
        "1",
        "a non-infra attempt is charged from the first one",
    )
    gate.assert_eq(
        chargeable(gate, "aaa\t1\t"),
        "1",
        "a LEGACY marker with no class line still charges, exactly as before",
    )

    gate.assert_eq(
        chargeable(gate, "aaa\t2\terror_max_turns\nbbb\t1\t\nccc\t3\terror_max_turns"),
        "2",
        "heads are accounted independently (0 + 1 + 1)",
    )

    # The ceiling, both ways.
    if head_is_exhausted(gate, "aaa\t3\terror_max_turns", "aaa") == 0:
        gate.log_pass("  a head with 3 infra attempts is exhausted")
    else:
        gate.log_fail("a head with 3 infra attempts must be exhausted")
    if head_is_exhausted(gate, "aaa\t2\terror_max_turns", "aaa") == 0:
        gate.log_fail("a head with 2 infra attempts must NOT be exhausted")
    if head_is_exhausted(gate, "aaa\t9\t", "aaa") == 0:
        gate.log_fail(
            "a non-infra head must never be per-head blocked; that would be a NEW restriction"
        )
    if head_is_exhausted(gate, "aaa\t3\terror_max_turns", "bbb") == 0:
        gate.log_fail("exhaustion must be keyed on the head, not on any head")
    gate.log_pass(
        "attempt accounting: infra gets 2 free re-attempts per head, everything else is unchanged"
    )


def run_mark(gate, t, subtype: str = "") -> Run:
    """`run_mark <TEMP> <subtype-or-empty>` -- drive claude-review-gate.sh --mark."""
    bash = require_bash(gate)
    execution = [{"type": "result", "subtype": subtype, "result": ""}] if subtype else []
    write_json(t / "execution.json", execution)
    result = harness.run(
        [bash, os.fspath(REAL_GATE), "--mark"],
        cwd=t,
        env={
            "PATH": "%s%s%s" % (t / "bin", os.pathsep, os.environ.get("PATH", "")),
            "GH_FIXTURES": os.fspath(t / "fixtures"),
            "GH_CAPTURE": os.fspath(t / "capture.txt"),
            "GH_TOKEN": "fake",
            "GITHUB_REPOSITORY": "rediacc/console",
            "PR_NUMBER": "42",
            "HEAD_SHA": NEW_SHA,
            "EXECUTION_FILE": os.fspath(t / "execution.json"),
            "REVIEW_OUTCOME": "failure",
            "NO_COLOR": "1",
        },
    )
    return Run(result.combined, result.rc)


def marked_body(t) -> str:
    """`marked_body <TEMP>` -- the captured attempt write: its method, path and
    the `-f body=` payload the gate sent."""
    fields = pathlib.Path("%s.fields" % (t / "capture.txt"))
    if not fields.is_file():
        return ""
    return fields.read_text(encoding="utf-8")


def test_mark_records_the_first_infra_attempt_as_retryable(gate):
    """FIRES: the old code POSTed "Push a change to earn another pass" here,
    which is the message that stalled #560."""
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(t / "fixtures" / "comments.json", [])
        run = run_mark(gate, t, "error_max_turns")
        gate.assert_eq(run.rc, 0, "--mark must not fail the job (output: %s)" % run.out)
        body = marked_body(t)
        gate.assert_contains(body, "METHOD=POST", "the first attempt on a head CREATES its marker")
        gate.assert_contains(body, "attempts: 1", "the marker carries its own count")
        gate.assert_contains(body, "class: error_max_turns", "and the class the count is judged by")
        gate.assert_contains(body, "INFRASTRUCTURE-class", "it says why this one is retryable")
        gate.assert_contains(
            body,
            "gh workflow run claude-review.yml",
            "and names the existing dispatch that retries it",
        )
        gate.assert_not_contains(
            body,
            "Push a change to earn another pass",
            "an infra failure with re-attempts left must NOT demand a push",
        )
        gate.log_pass("attempt 1 (infra) records a RETRYABLE marker, no push demanded")


def test_mark_upserts_the_second_attempt(gate):
    """The marker is upserted, not re-posted: N deaths on one head must be one
    comment carrying N, or the count cannot be read back at all."""
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(
            t / "fixtures" / "comments.json",
            [attempt_marker(301, NEW_SHA, 1, "error_max_turns")],
        )
        run_mark(gate, t, "error_max_turns")
        body = marked_body(t)
        gate.assert_contains(body, "METHOD=PATCH", "a second attempt UPDATES the existing marker")
        gate.assert_contains(body, "issues/comments/301", "and patches the one for THIS head")
        gate.assert_contains(body, "attempts: 2", "the count advances")
        gate.assert_not_contains(
            body,
            "Push a change to earn another pass",
            "the second infra attempt still has one left",
        )
        gate.log_pass("attempt 2 (infra) upserts the same marker and stays retryable")


def test_mark_closes_the_head_on_the_third_attempt(gate):
    """CONTROL for the two above: the bound is real. The third reportless failure
    on one head reverts to today's terminal message."""
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(
            t / "fixtures" / "comments.json",
            [attempt_marker(301, NEW_SHA, 2, "error_max_turns")],
        )
        run_mark(gate, t, "error_max_turns")
        body = marked_body(t)
        gate.assert_contains(body, "attempts: 3", "the count reaches the ceiling")
        gate.assert_contains(
            body,
            "Push a change to earn another pass",
            "the third attempt is terminal, exactly as before",
        )
        gate.assert_not_contains(body, "INFRASTRUCTURE-class", "and it no longer offers a re-run")
        gate.log_pass("attempt 3 (infra) closes the head with today's terminal message")


def test_mark_keeps_the_old_rule_for_unknown_failures(gate):
    """CONTROL: a failure the pipeline cannot classify gets no free retries at
    all. The relaxation is scoped to the classes it was argued for."""
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(t / "fixtures" / "comments.json", [])
        run_mark(gate, t, "")
        body = marked_body(t)
        gate.assert_contains(body, "attempts: 1", "still counted")
        gate.assert_contains(
            body, "class: review step did not succeed", "and its class recorded verbatim"
        )
        gate.assert_contains(
            body,
            "Push a change to earn another pass",
            "an unclassified failure is terminal on the first attempt, as before",
        )
        gate.log_pass("an unclassified reportless failure keeps the old single-shot rule")


def run_gate_decision(gate, t) -> Run:
    """`run_gate_decision <TEMP>` -- drive the gate's DECISION mode for PR 42 at
    NEW_SHA."""
    bash = require_bash(gate)
    (t / "gate-output.txt").write_text("", encoding="utf-8")
    result = harness.run(
        [bash, os.fspath(REAL_GATE)],
        cwd=t,
        env={
            "PATH": "%s%s%s" % (t / "bin", os.pathsep, os.environ.get("PATH", "")),
            "GH_FIXTURES": os.fspath(t / "fixtures"),
            "GH_CAPTURE": os.fspath(t / "capture.txt"),
            "GH_TOKEN": "fake",
            "GITHUB_REPOSITORY": "rediacc/console",
            "GITHUB_OUTPUT": os.fspath(t / "gate-output.txt"),
            "EVENT_NAME": "workflow_dispatch",
            "PR_NUMBER": "42",
            "PR_HEAD_SHA": NEW_SHA,
            "NO_COLOR": "1",
        },
    )
    return Run(result.combined, result.rc)


def test_gate_refuses_an_exhausted_head(gate):
    """THE REFUSAL ITSELF. Free re-attempts have to end somewhere and it cannot
    be the per-PR cap, because the free ones are not charged -- without this a
    head that dies infra-class would be retried forever at no visible cost."""
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(
            t / "fixtures" / "comments.json",
            [attempt_marker(301, NEW_SHA, 3, "error_max_turns")],
        )
        run = run_gate_decision(gate, t)
        gate.assert_eq(run.rc, 0, "the gate exits cleanly when it declines (output: %s)" % run.out)
        gate.assert_contains(
            (t / "gate-output.txt").read_text(encoding="utf-8"),
            "go=false",
            "an exhausted head is not reviewed again",
        )
        gate.assert_contains(run.out, "spent all 3 attempts", "and the log says why")

        # CONTROL: one attempt fewer and the same head IS reviewed. This is the
        # whole point of the change, so it is asserted rather than assumed.
        setup(gate, t)
        write_json(
            t / "fixtures" / "comments.json",
            [attempt_marker(301, NEW_SHA, 2, "error_max_turns")],
        )
        run_gate_decision(gate, t)
        gate.assert_contains(
            (t / "gate-output.txt").read_text(encoding="utf-8"),
            "go=true",
            "a head with a re-attempt left must still be reviewable WITHOUT a push",
        )
        gate.log_pass(
            "the gate refuses an exhausted head and reviews one that still has an attempt left"
        )


def test_head_exhaustion_does_not_deadlock_the_pr(gate):
    """THE #553 SHAPE, ONE LEVEL DOWN. The free attempts are not charged, so a
    head can exhaust its ceiling while the PR sits well under its cap. The gate
    then refuses this head; if review-status could not see that, it would post a
    required FAILURE and leave a green PR permanently unmergeable."""
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(
            t / "fixtures" / "comments.json",
            [marker_comment(OLD_SHA), attempt_marker(301, NEW_SHA, 3, "error_max_turns")],
        )
        write_json(
            t / "fixtures" / "compare.json",
            {"files": [{"filename": "packages/cli/src/commands/repo.ts"}]},
        )
        (t / "gate-cap3.sh").write_text(BOTH_PREFIXES, encoding="utf-8")
        pr_size(t, 900, 100)  # cap 3, and only ONE unit charged -- well under it

        run_status(
            gate,
            t,
            EVENT_NAME="pull_request_review",
            PR_NUMBER="42",
            REVIEW_STATUS_GATE_SCRIPT=os.fspath(t / "gate-cap3.sh"),
        )
        gate.assert_eq(
            posted(gate, t, ".conclusion"),
            "success",
            "an exhausted head with budget left must stay mergeable",
        )
        gate.assert_contains(
            posted(gate, t, ".output.summary"),
            "HEAD REVIEW ATTEMPTS EXHAUSTED",
            "and say so, rather than passing quietly",
        )
        gate.log_pass("an exhausted head passes with a warning instead of deadlocking the PR")


def test_retryable_head_with_a_stale_marker_still_fails(gate):
    """CONTROL for the case above, in its OWN temp dir because `posted` parses
    the single capture file from the first METHOD= line onward -- a second
    run_status in the same directory appends a second check-run payload and makes
    it unparseable. One run per world, like every other case here.

    One attempt fewer, so the head is still retryable and a stale marker is a
    real failure again. Without this the new guard could swallow every stale head
    and nothing would notice."""
    with harness.temp_dir() as t:
        setup(gate, t)
        write_json(
            t / "fixtures" / "comments.json",
            [marker_comment(OLD_SHA), attempt_marker(301, NEW_SHA, 2, "error_max_turns")],
        )
        write_json(
            t / "fixtures" / "compare.json",
            {"files": [{"filename": "packages/cli/src/commands/repo.ts"}]},
        )
        (t / "gate-cap3.sh").write_text(BOTH_PREFIXES, encoding="utf-8")
        pr_size(t, 900, 100)

        run_status(
            gate,
            t,
            EVENT_NAME="pull_request_review",
            PR_NUMBER="42",
            REVIEW_STATUS_GATE_SCRIPT=os.fspath(t / "gate-cap3.sh"),
        )
        gate.assert_eq(
            posted(gate, t, ".conclusion"),
            "failure",
            "a retryable head with a stale marker must still fail",
        )
        gate.assert_not_contains(
            posted(gate, t, ".output.summary"),
            "HEAD REVIEW ATTEMPTS EXHAUSTED",
            "no exhaustion warning while an attempt remains",
        )
        gate.log_pass("a head that still has an attempt left keeps failing on a stale marker")
