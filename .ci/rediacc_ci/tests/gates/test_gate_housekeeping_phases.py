"""Port of `.ci/scripts/test/gates/test-housekeeping-phases.sh`.

Both-ways test for `.ci/scripts/housekeeping/cleanup-versions.sh`, specifically for
the parts of it that had never executed anywhere.

WHY THIS GATE EXISTS. A single `return 1` in Phase 8d, placed inside that phase's own
`set +e` region, produced three failures at once and every one of them was silent:

  1. The nightly reported SUCCESS on every drifted run (08-18 .. 08-23). The return
     was swallowed by `set +e`, so `cleanup_r2` looked clean.
  2. It jumped over the `set -e` that closes the region, so Phases 9-12 then ran with
     errexit OFF for the rest of the script.
  3. It skipped Phase 8f entirely, disabling apt/rpm/apk/archlinux/npm artifact
     retention from 2026-08-22 on. Run 32616474098's log jumps straight from `8d:` to
     `Phase 9:` with no `8f:` line in between.

Nothing caught any of that because nothing ever ran the script's failure paths. Phase
9's DELETE arm in particular had never executed anywhere in this repo's history: every
real run either found no stale branch or ran with `--dry-run`, which takes a different
branch of the code.

HOW. The script is driven as a real program with `gh` and `aws` replaced by routing
fakes on PATH, so no case can reach GitHub or R2. Every fake records its argv, and
every assertion that a call was NOT made is PAIRED with a control proving the recorder
does capture that call when it happens. Without the pairing, "no DELETE was issued"
would also pass against a fake that recorded nothing at all.

THE ONE STATIC CASE IS THE ONE THAT NAMES THE BUG.
`test_no_return_inside_the_errexit_relaxed_region` is lexical rather than behavioural,
because a `set +e` region spanning ~340 lines cannot be exercised into every early
exit. Its control plants the exact defect into a COPY under `tmp_path` and requires it
to be reported; the real subject is never written to.
"""

import datetime
import os
import pathlib
import re
import shutil
import stat

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-housekeeping-phases.sh"

UNDER_TEST = paths.from_root(".ci", "scripts", "housekeeping", "cleanup-versions.sh")

FAKE_AWS = r"""#!/bin/bash
# Routing fake for the four aws shapes cleanup_r2 uses. Anything unrouted returns
# empty rather than failing, because the phases under test walk past prefixes they
# find nothing in and that is the uninteresting case here.
set -uo pipefail
[ -n "${AWS_CALLS:-}" ] && printf '%s\n' "$*" >>"$AWS_CALLS"
svc="${1:-}"
op="${2:-}"
query=""
prefix=""
args=("$@")
i=0
while [ "$i" -lt "${#args[@]}" ]; do
    case "${args[$i]}" in
        --query)
            i=$((i + 1))
            query="${args[$i]}"
            ;;
        --prefix)
            i=$((i + 1))
            prefix="${args[$i]}"
            ;;
    esac
    i=$((i + 1))
done
fixture() {
    local name="$1"
    [ -f "$AWS_FIXTURES/$name" ] && cat "$AWS_FIXTURES/$name"
    return 0
}
case "$svc/$op" in
    s3/ls)
        target="${3#s3://}"
        fixture "ls.$(printf '%s' "${target#*/}" | tr '/' '~')"
        ;;
    s3api/list-objects-v2)
        case "$query" in
            *ends_with*) fixture "sentinels" ;;
            *LastModified*) echo "None" ;;
            *) echo "None" ;;
        esac
        ;;
    s3api/list-multipart-uploads) echo "[]" ;;
    *) ;;
esac
exit 0
"""

FAKE_GH = r"""#!/bin/bash
# Routing fake for every `gh` shape the housekeeping phases reach. Unrouted READ calls
# return an empty JSON array so the phases that are not under test walk through
# without work; an unrouted WRITE call is a hard error, because a destructive call
# landing somewhere the test did not model must not read as a pass.
set -uo pipefail
[ -n "${GH_CALLS:-}" ] && printf '%s\n' "$*" >>"$GH_CALLS"
method="GET"
path=""
jqexpr=""
args=("$@")
i=0
while [ "$i" -lt "${#args[@]}" ]; do
    a="${args[$i]}"
    case "$a" in
        api | --paginate | --silent) ;;
        -X)
            i=$((i + 1))
            method="${args[$i]}"
            ;;
        --jq | -q)
            i=$((i + 1))
            jqexpr="${args[$i]}"
            ;;
        -*) ;;
        *) [ -z "$path" ] && path="$a" ;;
    esac
    i=$((i + 1))
done
fixture() {
    [ -f "$GH_FIXTURES/$1" ] && cat "$GH_FIXTURES/$1"
    return 0
}
if [ "$method" = "DELETE" ]; then
    case "$path" in
        */git/refs/heads/*)
            if [ -n "${GH_DELETE_FAIL:-}" ]; then
                echo "gh: Resource not accessible by integration (HTTP 403)" >&2
                exit 1
            fi
            exit 0
            ;;
        *)
            echo "fake gh: unmodelled DELETE: $*" >&2
            exit 3
            ;;
    esac
fi
case "$path" in
    */git/*)
        # Tag-object lookups (Phase 2). Empty output makes that phase skip the tag,
        # which is what keeps this gate focused on Phases 8d and 9.
        ;;
    */tags) fixture "tags" ;;
    */branches\?*)
        repo="${path#repos/}"
        repo="${repo%%/branches*}"
        fixture "branches.$(printf '%s' "$repo" | tr '/' '~')"
        ;;
    */branches/*)
        # Branch names contain slashes; fixtures flatten them to `~`.
        branch="${path##*/branches/}"
        fixture "branchdate.$(printf '%s' "$branch" | tr '/' '~')"
        ;;
    */pulls\?head=*)
        branch="${path##*head=}"
        branch="${branch%%&*}"
        branch="${branch#*:}"
        branch="$(printf '%s' "$branch" | tr '/' '~')"
        if [ -f "$GH_FIXTURES/openpr.$branch" ]; then cat "$GH_FIXTURES/openpr.$branch"; else echo 0; fi
        ;;
    *)
        if [ -n "$jqexpr" ]; then echo ""; else echo "[]"; fi
        ;;
esac
exit 0
"""


def _exec(path: pathlib.Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class World:
    """One temp housekeeping world: fake gh and aws, their fixtures, their recorders."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.bin = root / "bin"
        self.gh_fixtures = root / "fixtures"
        self.aws_fixtures = root / "aws-fixtures"
        self.gh_log = root / "gh-calls.log"
        self.aws_log = root / "aws-calls.log"
        self.out = ""
        self.rc = 0

    def setup(self) -> None:
        """`setup`, RESETTING: several cases call it twice in one function to run a
        control arm, and a leftover recorder would make the second arm read the first."""
        for path in (self.gh_fixtures, self.aws_fixtures, self.bin):
            shutil.rmtree(path, ignore_errors=True)
        for path in (self.gh_log, self.aws_log):
            if path.exists():
                path.unlink()
        self.bin.mkdir(parents=True)
        self.gh_fixtures.mkdir(parents=True)
        self.aws_fixtures.mkdir(parents=True)
        _exec(self.bin / "gh", FAKE_GH)
        _exec(self.bin / "aws", FAKE_AWS)
        # No drift and no branches by default; each case adds only what it needs.
        (self.gh_fixtures / "tags").write_text("", encoding="utf-8")
        (self.aws_fixtures / "sentinels").write_text("", encoding="utf-8")

    # -- fixture builders, one per twin helper -----------------------------

    def r2_has_version(self, version: str) -> None:
        with (self.aws_fixtures / "ls.cli~").open("a", encoding="utf-8") as handle:
            handle.write("                           PRE %s/\n" % version)

    def r2_has_sentinel(self, version: str) -> None:
        with (self.aws_fixtures / "sentinels").open("a", encoding="utf-8") as handle:
            handle.write("cli/%s/.released\n" % version)

    def git_has_tag(self, version: str) -> None:
        with (self.gh_fixtures / "tags").open("a", encoding="utf-8") as handle:
            handle.write("%s\n" % version)

    def branch(self, name: str, age_days: int | None, open_prs: int = 0) -> None:
        key = name.replace("/", "~")
        with (self.gh_fixtures / "branches.rediacc~console").open("a", encoding="utf-8") as handle:
            handle.write("%s\n" % name)
        if age_days is not None:
            when = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=age_days)
            (self.gh_fixtures / ("branchdate.%s" % key)).write_text(
                when.strftime("%Y-%m-%dT%H:%M:%SZ") + "\n", encoding="utf-8"
            )
        (self.gh_fixtures / ("openpr.%s" % key)).write_text("%d\n" % open_prs, encoding="utf-8")

    # -- driving -----------------------------------------------------------

    def run(self, *args: str, env: dict[str, str] | None = None) -> None:
        overlay = {
            "PATH": "%s%s%s" % (self.bin, os.pathsep, os.environ.get("PATH", "")),
            "GH_FIXTURES": str(self.gh_fixtures),
            "AWS_FIXTURES": str(self.aws_fixtures),
            "GH_CALLS": str(self.gh_log),
            "AWS_CALLS": str(self.aws_log),
            "GH_TOKEN": "fake",
            "GITHUB_ACTIONS": "true",
            "CLOUDFLARE_R2_ACCESS_KEY_ID": "fake",
            "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "fake",
            "CLOUDFLARE_R2_ENDPOINT": "https://r2.invalid",
            "RSV_GRANDFATHER_BEFORE": "v0.0.1",
            "NO_COLOR": "1",
        }
        overlay.update(env or {})
        bash = harness.require_tool("bash", "install bash; the subject is a bash script")
        result = harness.run([bash, str(UNDER_TEST), *args], env=overlay, timeout=300)
        self.out = result.combined
        self.rc = result.rc

    def gh_calls(self) -> str:
        return self.gh_log.read_text(encoding="utf-8") if self.gh_log.is_file() else ""


def make_world(gate, tmp_path) -> World:
    if not os.access(UNDER_TEST, os.X_OK):
        gate.log_fail("%s is not executable" % paths.relative_to_root(UNDER_TEST))
    world = World(tmp_path)
    world.setup()
    return world


def returns_in_relaxed_region(path: pathlib.Path) -> list[str]:
    """One entry per `return`/`exit` lexically between `set +e` and the `set -e`
    that closes it; empty means clean.

    A PURE FUNCTION over the file's text, exported so the control below can run the
    IDENTICAL code path against a planted copy. The twin shells out to an inline
    `python3` heredoc twice; this is the same predicate, called twice.
    """
    lines = path.read_text(encoding="utf-8").split("\n")
    start = next((i for i, ln in enumerate(lines) if ln.strip() == "set +e"), None)
    end = None
    if start is not None:
        end = next((i for i, ln in enumerate(lines) if i > start and ln.strip() == "set -e"), None)
    if start is None or end is None:
        return ["could not locate the set +e / set -e bracket in cleanup_r2 at all"]
    found = []
    for i in range(start + 1, end):
        body = lines[i].split("#", 1)[0]
        if re.search(r"(^|[;&|{(\s])(return|exit)(\s|$)", body):
            found.append("line %d leaves the region early: %s" % (i + 1, lines[i].strip()))
    return found


# --- 8d: drift must fail the run, and must not cost the phases after it -----


def test_drift_fails_the_run(gate, tmp_path):
    """THE FEATURE. A sentinel with no matching git tag is the live state that went
    unreported for six consecutive nightlies."""
    world = make_world(gate, tmp_path)
    world.r2_has_version("v1.2.27")
    world.r2_has_sentinel("v1.2.27")
    world.run()
    gate.assert_exit_code(1, world.rc, "release-state drift must fail the housekeeping run")
    gate.assert_contains(
        world.out,
        "drift: cli/v1.2.27/.released exists but git tag v1.2.27 missing",
        "naming the drifted version",
    )
    gate.assert_contains(
        world.out,
        "::error title=Release-state drift::",
        "as a real GHA annotation, not a log_error nobody sees",
    )
    gate.assert_contains(world.out, "Housekeeping FAILED", "and the run says it failed")
    gate.log_pass("FIRE: sentinel without a tag => exit 1 plus an ::error annotation")


def test_no_drift_passes_cleanly(gate, tmp_path):
    """CONTROL. Without it the case above would pass against a script that failed
    unconditionally."""
    world = make_world(gate, tmp_path)
    world.r2_has_version("v1.2.27")
    world.r2_has_sentinel("v1.2.27")
    world.git_has_tag("v1.2.27")
    world.run()
    gate.assert_exit_code(0, world.rc, "a committed release is not drift")
    gate.assert_not_contains(world.out, "::error title=", "and emits no error annotation")
    gate.assert_not_contains(world.out, "Housekeeping FAILED", "and does not report failure")
    gate.log_pass("CONTROL: sentinel AND tag => exit 0, no annotation")


def test_drift_does_not_skip_phase_8f(gate, tmp_path):
    """THE SECOND DEFECT: the old `return 1` fired before Phase 8f."""
    world = make_world(gate, tmp_path)
    world.r2_has_version("v1.2.27")
    world.r2_has_sentinel("v1.2.27")
    world.run()
    gate.assert_exit_code(1, world.rc, "the run still fails")
    gate.assert_contains(
        world.out,
        "8f: channel artifact retention",
        "but Phase 8f ran anyway -- the drift finding must not disable package retention",
    )
    gate.assert_contains(world.out, "8e: ", "and so did Phase 8e")

    # CONTROL: 8f is not simply always in this log for trivial reasons.
    world.setup()
    world.r2_has_version("v1.2.27")
    world.r2_has_sentinel("v1.2.27")
    world.git_has_tag("v1.2.27")
    world.run()
    gate.assert_contains(
        world.out,
        "8f: channel artifact retention",
        "CONTROL: the no-drift run reaches 8f too, so the marker tracks the phase",
    )
    gate.log_pass("drift no longer eats Phase 8f (control: 8f present on the clean run too)")


def test_drift_does_not_skip_phases_9_to_12(gate, tmp_path):
    """THE THIRD DEFECT: the old return left errexit OFF for everything after cleanup_r2."""
    world = make_world(gate, tmp_path)
    world.r2_has_version("v1.2.27")
    world.r2_has_sentinel("v1.2.27")
    world.run()
    gate.assert_exit_code(1, world.rc, "the drift still fails the run at the very end")
    gate.assert_contains(world.out, "Phase 9: Cleaning up stale branches", "Phase 9 ran")
    gate.assert_contains(world.out, "Phase 10: Cleaning up completed workflow runs", "Phase 10 ran")
    gate.assert_contains(world.out, "Phase 11", "Phase 11 ran")
    gate.assert_contains(world.out, "Phase 12", "Phase 12 ran")
    gate.assert_contains(
        world.out, "Housekeeping complete", "and the run reached its own end marker"
    )
    gate.log_pass("a drift finding is latched, not thrown: Phases 9-12 all still run")


def test_no_return_inside_the_errexit_relaxed_region(gate, tmp_path):
    """STATIC. The `set +e` / `set -e` bracket spans ~340 lines and guards SIGPIPE on
    `aws | awk` pipes. ANY early exit out of that span leaves errexit off for the rest
    of the script, which is the bug this file is named for."""
    found = returns_in_relaxed_region(UNDER_TEST)
    if found:
        gate.log_fail("cleanup_r2 leaves its set +e region early: %s" % "; ".join(found))

    # CONTROL: plant the exact defect on a COPY under tmp_path and require a report. The real subject is never written to.
    lines = UNDER_TEST.read_text(encoding="utf-8").split("\n")
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "set +e")
    end = next(i for i, ln in enumerate(lines) if i > start and ln.strip() == "set -e")
    lines.insert((start + end) // 2, "    return 1  # planted control")
    planted = tmp_path / "planted.sh"
    planted.write_text("\n".join(lines), encoding="utf-8")
    if not returns_in_relaxed_region(planted):
        gate.log_fail(
            "CONTROL FAILED: the planted 'return 1' inside the set +e region was not "
            "reported, so this check cannot detect the original bug"
        )
    gate.log_pass(
        "no early exit inside cleanup_r2's set +e region (control: a planted return IS reported)"
    )


# --- Phase 9: the delete arm ------------------------------------------------


def test_a_stale_branch_is_deleted(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.branch("feature/old", 40)
    world.run()
    gate.assert_exit_code(0, world.rc, "a clean sweep exits 0")
    gate.assert_contains(
        world.gh_calls(),
        "DELETE repos/rediacc/console/git/refs/heads/feature/old",
        "a 40-day-old branch with no open PR is deleted",
    )
    gate.assert_contains(world.out, "Branches (console): deleted 1", "and counted as deleted")
    gate.log_pass("FIRE: 40d branch, no open PR => DELETE issued, reported as deleted 1")


def test_a_young_branch_is_kept(gate, tmp_path):
    """CONTROL for age."""
    world = make_world(gate, tmp_path)
    world.branch("feature/new", 10)
    world.run()
    gate.assert_not_contains(world.gh_calls(), "DELETE ", "a 10-day-old branch must not be deleted")
    gate.assert_contains(
        world.out, "Branches (console): deleted 0, kept 1", "and is counted as kept"
    )
    gate.log_pass("CONTROL: 10d branch => no DELETE, kept 1")


def test_a_stale_branch_with_an_open_pr_is_kept(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.branch("feature/reviewing", 40, 1)
    world.run()
    gate.assert_not_contains(world.gh_calls(), "DELETE ", "an open PR protects a stale branch")
    gate.assert_contains(
        world.out, "Branches (console): deleted 0, kept 1", "and it is counted as kept"
    )

    world.setup()
    world.branch("feature/reviewing", 40, 0)
    world.run()
    gate.assert_contains(
        world.gh_calls(),
        "DELETE repos/rediacc/console/git/refs/heads/feature/reviewing",
        "CONTROL: with no open PR the identical branch is deleted, so the open PR is what saved it",
    )
    gate.log_pass("an open PR protects a stale branch (control: zero open PRs deletes it)")


def test_main_is_never_deleted(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.branch("main", 900)
    world.run()
    gate.assert_not_contains(world.gh_calls(), "DELETE ", "main must never be deleted, at any age")

    world.setup()
    world.branch("ancient/thing", 900)
    world.run()
    gate.assert_contains(
        world.gh_calls(),
        "DELETE repos/rediacc/console/git/refs/heads/ancient/thing",
        "CONTROL: 900 days is well past the threshold for any other branch",
    )
    gate.log_pass("main survives at 900 days (control: another 900d branch is deleted)")


def test_an_undatable_branch_is_kept(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.branch("mystery", None)
    world.run()
    gate.assert_not_contains(
        world.gh_calls(), "DELETE ", "a branch whose age cannot be resolved is kept"
    )
    gate.assert_contains(world.out, "Branches (console): deleted 0, kept 1", "and counted as kept")

    world.setup()
    world.branch("mystery", 40)
    world.run()
    gate.assert_contains(
        world.gh_calls(),
        "DELETE repos/rediacc/console/git/refs/heads/mystery",
        "CONTROL: the same branch with a resolvable stale date IS deleted",
    )
    gate.log_pass(
        "an unresolvable commit date keeps the branch (control: a resolvable one deletes it)"
    )


def test_dry_run_deletes_nothing_and_says_so(gate, tmp_path):
    """The old code incremented the SAME counter in dry-run, so a dry run reported
    'deleted 7' having deleted nothing."""
    world = make_world(gate, tmp_path)
    world.branch("feature/old", 40)
    world.run("--dry-run")
    gate.assert_exit_code(0, world.rc, "a dry run exits 0")
    gate.assert_contains(
        world.out, "[DRY-RUN] Would delete feature/old", "it says what it would delete"
    )
    gate.assert_contains(
        world.out,
        "Branches (console): would delete 1, kept 0",
        "and the summary says WOULD delete, not deleted",
    )
    gate.assert_not_contains(
        world.out, "Branches (console): deleted 1", "a dry run must never claim a deletion"
    )
    gate.assert_not_contains(world.gh_calls(), "DELETE ", "and issues no DELETE")
    gate.assert_contains(world.out, "Total deletes this run: 0 /", "consuming no delete budget")

    world.setup()
    world.branch("feature/old", 40)
    world.run()
    gate.assert_contains(
        world.gh_calls(),
        "DELETE repos/rediacc/console/git/refs/heads/feature/old",
        "CONTROL: the same fixture without --dry-run DOES delete",
    )
    gate.assert_contains(
        world.out, "Total deletes this run: 1 /", "CONTROL: and DOES consume budget"
    )
    gate.log_pass("--dry-run deletes nothing, consumes no budget, and reports 'would delete'")


def test_the_branch_listing_paginates(gate, tmp_path):
    """`?per_page=100` without `--paginate` silently caps the sweep at 100 branches."""
    world = make_world(gate, tmp_path)
    world.branch("feature/old", 40)
    world.run()
    calls = world.gh_calls()
    gate.assert_contains(
        calls,
        "repos/rediacc/console/branches?per_page=100",
        "the recorder captured the branch listing (so the next assertion is about a call that happened)",
    )
    listing = [
        ln for ln in calls.splitlines() if "repos/rediacc/console/branches?per_page=100" in ln
    ]
    if not any("--paginate" in ln for ln in listing):
        gate.log_fail("the branch listing does not pass --paginate, so it stops at 100 branches")
    gate.log_pass(
        "the branch listing paginates (asserted on a call the recorder actually captured)"
    )


def test_a_failed_delete_fails_the_run(gate, tmp_path):
    """A 403 from a token missing contents:write used to be a log_warn nobody saw."""
    world = make_world(gate, tmp_path)
    world.branch("feature/old", 40)
    world.run(env={"GH_DELETE_FAIL": "1"})
    gate.assert_exit_code(1, world.rc, "a failed branch delete must fail the run")
    gate.assert_contains(
        world.out, "::error title=Stale-branch delete failed::", "as a GHA annotation"
    )
    gate.assert_contains(world.out, "HTTP 403", "carrying gh's own stderr, not a generic message")
    gate.assert_contains(world.out, "Phase 10", "and the later phases still ran")

    world.setup()
    world.branch("feature/old", 40)
    world.run()
    gate.assert_exit_code(0, world.rc, "CONTROL: a succeeding delete exits 0")
    gate.assert_not_contains(
        world.out,
        "::error title=Stale-branch delete failed::",
        "CONTROL: and emits no annotation",
    )
    gate.log_pass("a 403 on DELETE annotates and fails the run (control: a 200 does neither)")
