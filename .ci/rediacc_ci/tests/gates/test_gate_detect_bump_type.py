"""Port of `.ci/scripts/test/gates/test-detect-bump-type.sh`.

Both-ways test for `.ci/scripts/version/detect-bump-type.sh`, the script that turns PR labels into the version bump a release takes.

WHY THIS CLASS NEEDS A GATE. The thing being replaced was green forever while answering nothing: it resolved the PR by grepping `(#123)` out of the HEAD commit title, so on any merge whose title did not carry that shape it silently answered `patch`. Every case here that expects `patch` therefore also proves the API was REACHED, from a call log the fake `gh` appends to. A `patch`
that came from a fallback is not the same verdict as a `patch` that came from a lookup, and without the call log the two are indistinguishable.

THE FAKE `gh` IS THE TWIN'S, BYTE FOR BYTE. It is a routing shim over per-SHA fixture files that applies the caller's own `--jq`, and it is the thing the subject is actually driven against; translating it would mean the two sides drive different subjects.

WHERE THE FIXTURE BUILDER DIFFERS FROM THE TWIN, AND WHY THEY AGREE. The twin builds each PR object with `jq -nc` and each fixture array with `jq -s '.'`; this module builds the same structures with `json.dumps`. The consumer is `jq -r <expr> <file>` inside the fake, which parses the file, so only the PARSED structure is observable and formatting is not. `jq` is still required, by
the fake and by the subject, and this module probes for it rather than letting a missing binary surface as an unrouted-path exit code.

NO `xdist_group`. Every case builds its own git repository, fixture directory and call log inside pytest's own `tmp_path`; nothing outside it is written, no port is bound and no module global is mutated. The two tracked files it reads (`.github/labels.yml` and the subject) are never written.
"""

import json
import os
import pathlib
import re
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-detect-bump-type.sh"

UNDER_TEST = paths.from_root(".ci", "scripts", "version", "detect-bump-type.sh")
LABELS_FILE = paths.from_root(".github", "labels.yml")

BUMP_LABELS = ("bump-major", "bump-minor")

# Lifted verbatim from the twin's FAKE heredoc.
FAKE_GH = r"""#!/bin/bash
# Routing fake for `gh api repos/<repo>/commits/<sha>/pulls`. Serves the
# per-SHA fixture (falling back to pulls-default.json, which is how a commit
# with no associated PR is expressed) and applies the caller's own --jq to it.
# EVERY call is appended to $GH_CALLS: see the header for why a test that
# expects "patch" must also prove the API was reached.
set -uo pipefail
printf '%s\n' "$*" >>"$GH_CALLS"
if [ -n "${GH_FAIL_ALL:-}" ]; then
    echo "fake gh: forced API failure" >&2
    exit 1
fi
path=""
jqexpr=""
args=("$@")
n=${#args[@]}
i=0
while [ "$i" -lt "$n" ]; do
    a="${args[$i]}"
    case "$a" in
        api) ;;
        --jq)
            i=$((i + 1))
            jqexpr="${args[$i]}"
            ;;
        --paginate | --silent) ;;
        -*) ;;
        *)
            if [ -z "$path" ]; then path="$a"; fi
            ;;
    esac
    i=$((i + 1))
done

case "$path" in
    */commits/*/pulls)
        sha="${path#*/commits/}"
        sha="${sha%/pulls}"
        file="$GH_FIXTURES/pulls-$sha.json"
        if [ ! -f "$file" ]; then file="$GH_FIXTURES/pulls-default.json"; fi
        if [ ! -f "$file" ]; then
            echo "fake gh: no fixture for $sha and no default" >&2
            exit 4
        fi
        ;;
    *)
        echo "fake gh: unrouted path: $path" >&2
        exit 3
        ;;
esac

if [ -n "$jqexpr" ]; then
    jq -r "$jqexpr" "$file"
else
    cat "$file"
fi
"""


def merged_pr(number: int, labels: str) -> dict:
    """`merged_pr <number> <labels-csv>`."""
    return {
        "number": number,
        "merged_at": "2026-08-01T00:00:00Z",
        "state": "closed",
        "labels": [{"name": name} for name in labels.split(",") if labels],
    }


def open_pr(number: int, labels: str) -> dict:
    """`open_pr`: contains the commit, but nothing is released from it yet, so its label must not count."""
    return {
        "number": number,
        "merged_at": None,
        "state": "open",
        "labels": [{"name": name} for name in labels.split(",") if labels],
    }


class World:
    """`setup`, `commit`, `pulls_for`, `run_detect` and the call-log assertion."""

    def __init__(self, gate, root: pathlib.Path) -> None:
        self.gate = gate
        self.root = root
        self.git = harness.require_tool("git", "install git")
        harness.require_tool("jq", "install jq (the fake gh and the subject both use it)")
        if not UNDER_TEST.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(UNDER_TEST))
        self.out = ""
        self.err = ""
        self.rc = 0
        self.setup()

    def setup(self) -> None:
        """Idempotent, exactly as the twin's is: a case that drives two worlds in one directory calls this twice, and a leftover repo would make the second world inherit the first one's tags."""
        for name in ("fixtures", "repo"):
            shutil.rmtree(self.root / name, ignore_errors=True)
        (self.root / "fixtures").mkdir(parents=True)
        (self.root / "repo").mkdir(parents=True)
        (self.root / "bin").mkdir(exist_ok=True)
        fake = self.root / "bin" / "gh"
        fake.write_text(FAKE_GH, encoding="utf-8")
        fake.chmod(0o755)
        self.calls.write_text("", encoding="utf-8")
        # A commit with no associated PR. Not an error: most commits in a range resolve to one PR, some to none.
        (self.root / "fixtures" / "pulls-default.json").write_text("[]\n", encoding="utf-8")
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "gate-test@example.invalid")
        self._git("config", "user.name", "Gate Test")
        self._git("config", "commit.gpgsign", "false")

    @property
    def repo(self) -> pathlib.Path:
        return self.root / "repo"

    @property
    def calls(self) -> pathlib.Path:
        return self.root / "calls.txt"

    def _git(self, *args: str) -> harness.RunResult:
        result = harness.run([self.git, "-C", str(self.repo), *args])
        if result.rc != 0:
            self.gate.log_fail(
                "git %s failed in the fixture repo (rc=%d): %s"
                % (" ".join(args), result.rc, result.err.strip())
            )
        return result

    def commit(self, subject: str) -> str:
        """One real commit in the scratch repo; returns its SHA."""
        target = self.repo / "file.txt"
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(subject + "\n")
        self._git("add", "file.txt")
        self._git("commit", "-q", "-m", subject)
        return self._git("rev-parse", "HEAD").out.strip()

    def tag(self, name: str, sha: str) -> None:
        self._git("tag", name, sha)

    def retag(self, name: str, sha: str) -> None:
        self._git("tag", "-d", name)
        self._git("tag", name, sha)

    def pulls_for(self, sha: str, *prs: dict) -> None:
        (self.root / "fixtures" / ("pulls-%s.json" % sha)).write_text(
            json.dumps(list(prs)), encoding="utf-8"
        )

    def clear_calls(self) -> None:
        self.calls.write_text("", encoding="utf-8")

    def run_detect(self, **overrides: str) -> None:
        env = {
            "PATH": "%s:%s" % (self.root / "bin", os.environ.get("PATH", "")),
            "GH_FIXTURES": str(self.root / "fixtures"),
            "GH_CALLS": str(self.calls),
            "GH_TOKEN": "fake",
            "GITHUB_REPOSITORY": "rediacc/console",
            "NO_COLOR": "1",
        }
        env.update(overrides)
        result = harness.run(["bash", str(UNDER_TEST), "--verbose"], cwd=self.repo, env=env)
        self.rc = result.rc
        # The twin strips nothing but captures via `$(...)`, which drops trailing newlines; `.strip()` here is the same normalisation on the one-word verdict this script prints.
        self.out = result.out.strip()
        self.err = result.err

    def assert_api_was_reached(self, message: str) -> None:
        if not self.calls.read_text(encoding="utf-8").strip():
            self.gate.log_fail(
                "%s: the fake gh was never called, so this verdict came from a fallback "
                "and asserts nothing" % message
            )


def test_bump_labels_are_declared(gate):
    # Anti-drift with the declaration file: the labels this script matches on must exist in .github/labels.yml, or the inventory gates cannot keep them alive.
    if not UNDER_TEST.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(UNDER_TEST))
    if not LABELS_FILE.is_file():
        gate.log_fail("the labels file is missing: %s" % paths.relative_to_root(LABELS_FILE))
    labels = LABELS_FILE.read_text(encoding="utf-8")
    script = UNDER_TEST.read_text(encoding="utf-8")
    for label in BUMP_LABELS:
        if not re.search(r"^- name: %s$" % re.escape(label), labels, re.MULTILINE):
            gate.log_fail(
                "detect-bump-type.sh matches '%s' but .github/labels.yml does not declare it"
                % label
            )
        if '"%s"' % label not in script:
            gate.log_fail(
                "detect-bump-type.sh no longer matches '%s'; the label is declared and "
                "consumed by nothing" % label
            )
    gate.log_pass("both bump labels are declared in labels.yml and still matched by the script")


def test_head_pr_minor_yields_minor(gate, tmp_path):
    world = World(gate, tmp_path)
    first = world.commit("released work")
    world.tag("v1.0.0", first)
    head = world.commit("new capability")
    world.pulls_for(head, merged_pr(100, "bump-minor"))

    world.run_detect()
    gate.assert_exit_code(0, world.rc, "the script always exits 0")
    gate.assert_eq(
        world.out, "minor", "FIRE: a bump-minor label on the merged PR must escalate the release"
    )
    gate.assert_contains(world.err, "PR #100", "the verbose log names the PR it read")
    gate.log_pass("FIRE: bump-minor on the PR containing HEAD => minor")


def test_major_beats_minor_in_either_order(gate, tmp_path):
    world = World(gate, tmp_path)
    first = world.commit("released work")
    world.tag("v1.0.0", first)
    feature = world.commit("a feature")
    breaking = world.commit("a break")
    world.pulls_for(feature, merged_pr(100, "bump-minor"))
    world.pulls_for(breaking, merged_pr(101, "bump-major"))
    world.run_detect()
    gate.assert_eq(world.out, "major", "major outranks minor when it is nearest HEAD")

    # SAME range, priorities swapped between the two commits. The scan walks newest-first, so this is the case a short-circuit could get wrong: it must not stop at the first bump label it meets.
    world.setup()
    first = world.commit("released work")
    world.tag("v1.0.0", first)
    breaking = world.commit("a break")
    feature = world.commit("a feature")
    world.pulls_for(breaking, merged_pr(100, "bump-major"))
    world.pulls_for(feature, merged_pr(101, "bump-minor"))
    world.run_detect()
    gate.assert_eq(
        world.out, "major", "major outranks minor when it is DEEPER in the range than the minor"
    )
    gate.log_pass("FIRE: major beats minor from either end of the range")


def test_label_on_a_non_head_commit_still_escalates(gate, tmp_path):
    # THE UNION PROPERTY, and the reason the range exists rather than HEAD alone. CI auto-cancels superseded pushes, so the commit that finally releases need not belong to the PR that carried the label.
    world = World(gate, tmp_path)
    first = world.commit("released work")
    world.tag("v1.0.0", first)
    labelled = world.commit("the labelled PR")
    followup = world.commit("an unlabelled follow-up")
    world.pulls_for(labelled, merged_pr(100, "bump-minor"))
    world.pulls_for(followup, merged_pr(101, ""))

    world.run_detect()
    gate.assert_eq(
        world.out,
        "minor",
        "FIRE: a label on a PR inside tag..HEAD counts even when HEAD's own PR carries "
        "none (HEAD-only resolution answers patch here)",
    )
    gate.log_pass(
        "FIRE: bump-minor on a non-HEAD commit in range => minor (the union, not the tip)"
    )


def test_commits_before_the_tag_are_out_of_range(gate, tmp_path):
    world = World(gate, tmp_path)
    older = world.commit("an older release")
    breaking = world.commit("a breaking change, released as v1.0.0")
    today = world.commit("todays work")
    world.pulls_for(breaking, merged_pr(99, "bump-major"))
    world.pulls_for(today, merged_pr(100, ""))

    # v1.0.0 IS the breaking change's release. Its label was consumed then, and re-reading it now would ship a second major for the same work.
    world.tag("v1.0.0", breaking)
    world.run_detect()
    gate.assert_eq(
        world.out,
        "patch",
        "a bump-major already consumed by the release that tagged it must not escalate the next",
    )
    world.assert_api_was_reached("out-of-range case")
    gate.assert_not_contains(world.err, "PR #99", "the out-of-range PR is never even queried")

    # CONTROL: identical fixtures, tag moved back exactly one commit so PR #99 falls INSIDE the range. If this does not flip to major, the range is not being read and the assertion above is vacuous.
    world.retag("v1.0.0", older)
    world.clear_calls()
    world.run_detect()
    gate.assert_eq(
        world.out, "major", "CONTROL: the same bump-major, one tag position earlier, DOES escalate"
    )
    gate.log_pass("the tag..HEAD range is load-bearing (same fixtures, tag moved by one)")


def test_range_cap_is_real(gate, tmp_path):
    world = World(gate, tmp_path)
    first = world.commit("released work")
    world.tag("v1.0.0", first)
    labelled = world.commit("the labelled PR")
    filler = world.commit("filler")
    head = world.commit("head")
    world.pulls_for(labelled, merged_pr(100, "bump-minor"))
    world.pulls_for(filler, merged_pr(101, ""))
    world.pulls_for(head, merged_pr(102, ""))

    world.run_detect()
    gate.assert_eq(world.out, "minor", "CONTROL: uncapped, the label three commits deep is seen")

    world.clear_calls()
    world.run_detect(DETECT_BUMP_MAX_COMMITS="1")
    gate.assert_eq(world.out, "patch", "capped at 1 commit, the deeper label is out of reach")
    world.assert_api_was_reached("capped case")
    gate.log_pass(
        "DETECT_BUMP_MAX_COMMITS genuinely bounds the scan (3 commits => minor, 1 => patch)"
    )


def test_no_tag_scans_head_alone(gate, tmp_path):
    world = World(gate, tmp_path)
    # initialize.sh calls this BEFORE its own `git fetch --tags`, so a shallow checkout with no tags is a real state, not a hypothetical.
    old = world.commit("an old breaking change")
    head = world.commit("todays work")
    world.pulls_for(old, merged_pr(99, "bump-major"))
    world.pulls_for(head, merged_pr(100, "bump-minor"))

    world.run_detect()
    gate.assert_eq(
        world.out,
        "minor",
        "with no tag the scan is HEAD ALONE: a blind window of history would re-read "
        "PR #99 and escalate to major",
    )
    gate.assert_not_contains(
        world.err, "PR #99", "the older PR is never queried without a range to justify it"
    )
    gate.log_pass("no usable tag => HEAD alone, not a blind history window")


def test_no_merged_prs_yields_patch(gate, tmp_path):
    world = World(gate, tmp_path)
    first = world.commit("direct push")
    world.tag("v1.0.0", first)
    world.commit("another direct push")

    world.run_detect()
    gate.assert_eq(world.out, "patch", "a range with no merged PR is a patch release")
    world.assert_api_was_reached("no-PR case")
    gate.assert_contains(
        world.err, "no merged PRs found", "and it says so rather than blaming a failure"
    )
    gate.log_pass("no merged PRs in range => patch, with the API actually consulted")


def test_open_pr_label_is_ignored(gate, tmp_path):
    world = World(gate, tmp_path)
    first = world.commit("released work")
    world.tag("v1.0.0", first)
    head = world.commit("work in flight")
    world.pulls_for(head, open_pr(100, "bump-major"))

    world.run_detect()
    gate.assert_eq(
        world.out, "patch", "an UNMERGED PR's label describes a release that has not happened"
    )
    world.assert_api_was_reached("open-PR case")

    # CONTROL: the only difference is merged_at. If this does not flip, the merged filter is not what produced the patch above.
    world.pulls_for(head, merged_pr(100, "bump-major"))
    world.clear_calls()
    world.run_detect()
    gate.assert_eq(world.out, "major", "CONTROL: the same PR, merged, DOES escalate")
    gate.log_pass("open PRs are ignored and merged ones are not (merged_at is the only difference)")


def test_api_failure_yields_patch(gate, tmp_path):
    world = World(gate, tmp_path)
    first = world.commit("released work")
    world.tag("v1.0.0", first)
    head = world.commit("new capability")
    world.pulls_for(head, merged_pr(100, "bump-major"))

    world.run_detect(GH_FAIL_ALL="1")
    gate.assert_exit_code(0, world.rc, "an API failure must not fail the release job")
    gate.assert_eq(world.out, "patch", "unresolvable PRs fail OPEN and SMALL")
    world.assert_api_was_reached("API-failure case")
    gate.assert_contains(
        world.err, "every commits/<sha>/pulls lookup failed", "the fallback names its reason"
    )
    gate.log_pass("total API failure => patch (fail open and small), with the reason logged")


def test_missing_token_yields_patch_without_calling_the_api(gate, tmp_path):
    world = World(gate, tmp_path)
    world.commit("work")
    world.run_detect(GH_TOKEN="")
    gate.assert_eq(world.out, "patch", "no token means no lookup")
    if world.calls.read_text(encoding="utf-8").strip():
        gate.log_fail("the API was called without a token; the prerequisite check is not running")
    gate.log_pass("no GH_TOKEN => patch, and the API is not called (calls.txt discriminates)")


def test_commit_title_pr_number_is_never_used(gate, tmp_path):
    # THE CLEAN BREAK. The old resolution path must be gone, asserted by BEHAVIOUR rather than by grepping for its absence.
    world = World(gate, tmp_path)
    first = world.commit("released work")
    world.tag("v1.0.0", first)
    # A squash-merge-shaped title naming a DIFFERENT PR than the API reports.
    head = world.commit("fix the thing (#999)")
    world.pulls_for(head, merged_pr(100, "bump-minor"))

    world.run_detect()
    gate.assert_eq(world.out, "minor", "the API's PR #100 is the answer, not the title's #999")
    # SHAs MASKED FIRST. This asserted a bare "999" against a file that records whole gh command lines, including 40-hex commit SHAs, so it went red on CI run 32659064316 because that run's generated SHA happened to contain the digits. Roughly a 1-in-100 flake and nothing to do with PR numbers.
    calls = world.calls.read_text(encoding="utf-8")
    gate.assert_not_contains(
        re.sub(r"[0-9a-f]{40}", "<sha>", calls),
        "999",
        "PR #999 is never queried (commit SHAs masked, since hex can spell 999)",
    )
    gate.assert_not_contains(calls, "pr view", "and no per-PR gh pr view call is made at all")
    gate.log_pass("the commit TITLE is not a PR source any more (title says #999, API says #100)")
