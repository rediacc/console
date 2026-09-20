"""Port of `.ci/scripts/test/gates/test-dispatch-release.sh`.

Both-ways test for `.ci/scripts/ci/dispatch-release.sh`, the step that decides whether a merge to main earns a release at all.

WHY THIS CLASS NEEDS A GATE. The decision is invisible when it is wrong in the direction that matters. A release that should not have happened is noticed immediately, because a tag appears; a release that was silently WITHHELD looks like nothing at all, and stays looking like nothing until somebody wonders why the version stream stopped. So the fail-open paths are tested as
carefully as the skip: an API failure, an unresolvable commit and a mixed PR set must all end in a dispatch, and each of those is asserted here rather than reasoned about.

THE DISPATCH IS NEVER REAL. `DISPATCH_RELEASE_DRY_RUN=1` is the seam, and the fake
`gh` deliberately does NOT route `gh workflow run`: a bug that reached the real dispatch fails loudly with "unrouted call" instead of being quietly served.

THE TWO ci.yml PREDICATES ARE PURE FUNCTIONS TAKING JOB TEXT, which is the whole reason a control is possible. `ordering_violations` and `polarity_violations` are run against the REAL `finalize-release-sentinel` job AND against synthetic blocks carrying the exact defect, and the synthetic ones must be reported. A predicate that has never been shown to fire proves nothing. Both are
module-level so the controls exercise the same code path the real assertion does.

THE PORT'S ONE STRUCTURAL CHANGE. The twin's fixtures are built with `jq -nc`; here they are `json.dumps`, which removes `jq` from the fixture-BUILDING path. The fake `gh` still shells out to `jq` to apply the caller's own `--jq`, so the real extraction expression in the subject is still evaluated by the real tool, which is the half that matters.
"""

import json
import os
import pathlib
import re
import stat

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-dispatch-release.sh"

UNDER_TEST = paths.from_root(".ci", "scripts", "ci", "dispatch-release.sh")
CI_WORKFLOW = paths.from_root(".github", "workflows", "ci.yml")
LABELS_FILE = paths.from_root(".github", "labels.yml")
REVIEW_APPLIER = paths.from_root(".ci", "scripts", "review", "claude-review-gate.sh")

SHA = "abc1234def5678901234567890123456789abcde"

FAKE_GH = r"""#!/bin/bash
# Routing fake for `gh api repos/<repo>/commits/<sha>/pulls`, applying the caller's
# own --jq so the real extraction runs. `gh workflow run` is NOT routed: the tests
# drive the dry-run seam instead, so a bug that reached the real dispatch fails
# loudly here rather than being quietly served.
set -uo pipefail
if [ -n "${GH_CALLS:-}" ]; then
    printf '%s\n' "$*" >>"$GH_CALLS"
fi
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
        [ -f "$file" ] || file="$GH_FIXTURES/pulls-default.json"
        [ -f "$file" ] || { echo "fake gh: no fixture for $sha" >&2; exit 1; }
        if [ -n "$jqexpr" ]; then jq -r "$jqexpr" "$file"; else cat "$file"; fi
        ;;
    *)
        echo "fake gh: unrouted call: $*" >&2
        exit 3
        ;;
esac
"""


def merged_pr(number: int, labels: str) -> dict:
    return {
        "number": number,
        "merged_at": "2026-08-01T00:00:00Z",
        "state": "closed",
        "labels": [{"name": n} for n in (labels.split(",") if labels else [])],
    }


def open_pr(number: int, labels: str) -> dict:
    """An UNMERGED PR, which must never be consulted: its label describes a release that has not happened."""
    return {
        "number": number,
        "merged_at": None,
        "state": "open",
        "labels": [{"name": n} for n in (labels.split(",") if labels else [])],
    }


class Fixture:
    """One temp world: a fake `gh` on PATH, a fixture dir, an argv recorder."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.bin = root / "bin"
        self.fixtures = root / "fixtures"
        self.output = root / "github-output"
        self.calls = root / "gh-calls.log"
        self.out = ""
        self.rc = 0

    def setup(self) -> None:
        """`setup`. Idempotent, and it RESETS: several cases call it repeatedly in one function and would otherwise read the previous arm's recorder."""
        self.bin.mkdir(exist_ok=True)
        self.fixtures.mkdir(exist_ok=True)
        gh = self.bin / "gh"
        gh.write_text(FAKE_GH, encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        (self.fixtures / "pulls-default.json").write_text("[]\n", encoding="utf-8")
        for path in (self.output, self.calls):
            if path.exists():
                path.unlink()

    def pulls_for(self, sha: str, *prs: dict) -> None:
        (self.fixtures / ("pulls-%s.json" % sha)).write_text(
            json.dumps(list(prs)), encoding="utf-8"
        )

    def run(self, *args: str, env: dict[str, str] | None = None) -> None:
        overlay = {
            "PATH": "%s%s%s" % (self.bin, os.pathsep, os.environ.get("PATH", "")),
            "GH_FIXTURES": str(self.fixtures),
            "GH_CALLS": str(self.calls),
            "GH_TOKEN": "fake",
            "GITHUB_REPOSITORY": "rediacc/console",
            "GITHUB_SHA": SHA,
            "GITHUB_RUN_ID": "999",
            "GITHUB_OUTPUT": str(self.output),
            "DISPATCH_RELEASE_DRY_RUN": "1",
            "NO_COLOR": "1",
        }
        overlay.update(env or {})
        bash = harness.require_tool("bash", "install bash; the subject is a bash script")
        result = harness.run([bash, str(UNDER_TEST), *args], env=overlay, timeout=120)
        self.out = result.combined
        self.rc = result.rc

    def step_output(self) -> str:
        """The `$GITHUB_OUTPUT` this run produced; empty when the script wrote none."""
        return self.output.read_text(encoding="utf-8") if self.output.is_file() else ""

    def gh_calls(self) -> str:
        return self.calls.read_text(encoding="utf-8") if self.calls.is_file() else ""


def make_fixture(gate, tmp_path) -> Fixture:
    if not os.access(UNDER_TEST, os.X_OK):
        gate.log_fail("%s is not executable" % paths.relative_to_root(UNDER_TEST))
    harness.require_tool("jq", "install jq; the fake gh applies the caller's own --jq")
    fixture = Fixture(tmp_path)
    fixture.setup()
    return fixture


def assert_dispatched(gate, fixture: Fixture, msg: str) -> None:
    gate.assert_contains(fixture.out, "DRY-RUN: gh workflow run cd-v2.yml", msg)
    gate.assert_contains(fixture.out, "ci_run_id=999", "the run id is passed through")


def assert_not_dispatched(gate, fixture: Fixture, msg: str) -> None:
    gate.assert_not_contains(fixture.out, "DRY-RUN: gh workflow run", msg)


# --- the decision ----------------------------------------------------------


def test_bump_none_skips_the_release(gate, tmp_path):
    """THE FEATURE. A merged PR labelled bump-none earns no release at all."""
    fx = make_fixture(gate, tmp_path)
    fx.pulls_for(SHA, merged_pr(561, "bump-none"))
    fx.run()
    gate.assert_exit_code(0, fx.rc, "the decision must never fail the sentinel job")
    assert_not_dispatched(gate, fx, "a bump-none PR must NOT dispatch cd-v2")
    gate.assert_contains(
        fx.out, "::notice title=Release skipped::", "it announces the skip as an annotation"
    )
    gate.assert_contains(fx.out, "#561", "naming the PR that carried the label")
    gate.assert_contains(
        fx.out,
        "no tag, no GitHub release, no R2 upload, no edge deploy",
        "and stating exactly what was skipped",
    )
    gate.assert_contains(
        fx.out, "ship with the next release-worthy merge", "and that the commits are not lost"
    )
    gate.log_pass(
        "FIRE: bump-none on the merged PR => release skipped, with a notice naming the PR"
    )


def test_an_unlabelled_pr_releases(gate, tmp_path):
    """CONTROL: same shape, no label. If this dispatched either way the case above would prove nothing."""
    fx = make_fixture(gate, tmp_path)
    fx.pulls_for(SHA, merged_pr(561, ""))
    fx.run()
    gate.assert_exit_code(0, fx.rc, "a normal release path exits clean")
    assert_dispatched(gate, fx, "an unlabelled PR must dispatch cd-v2")
    gate.assert_not_contains(fx.out, "Release skipped", "and say nothing about skipping")
    gate.log_pass("CONTROL: no bump-none => the release dispatches as before")


def test_the_rest_of_the_bump_family_still_releases(gate, tmp_path):
    """bump-none is the only member that subtracts; the others size a release."""
    fx = make_fixture(gate, tmp_path)
    for label in ("bump-minor", "bump-major"):
        fx.setup()
        fx.pulls_for(SHA, merged_pr(561, label))
        fx.run()
        assert_dispatched(gate, fx, "%s must still dispatch cd-v2" % label)
    gate.log_pass("CONTROL: bump-minor and bump-major size the release, they do not skip it")


def test_an_unmerged_pr_is_never_consulted(gate, tmp_path):
    """Reading an OPEN PR's label would let an in-flight PR suppress someone else's release."""
    fx = make_fixture(gate, tmp_path)
    fx.pulls_for(SHA, open_pr(900, "bump-none"))
    fx.run()
    assert_dispatched(gate, fx, "an unmerged bump-none PR must not suppress the release")
    gate.log_pass("CONTROL: an OPEN bump-none PR is ignored; only merged PRs decide")


def test_a_mixed_pr_set_releases(gate, tmp_path):
    """The dangerous direction: withholding here would lose a real release."""
    fx = make_fixture(gate, tmp_path)
    fx.pulls_for(SHA, merged_pr(561, "bump-none"), merged_pr(562, ""))
    fx.run()
    assert_dispatched(gate, fx, "a mixed PR set must still release")
    gate.assert_contains(fx.out, "#562", "the release-worthy PR is named")
    gate.assert_contains(fx.out, "releasing", "and the reason is logged rather than left implicit")
    gate.log_pass("CONTROL: bump-none plus a release-worthy PR on one commit => releases")


def test_a_lookup_failure_fails_open(gate, tmp_path):
    """FAIL OPEN. A flaky API must never silently kill a release."""
    fx = make_fixture(gate, tmp_path)
    fx.run(env={"GH_FAIL_ALL": "1"})
    gate.assert_exit_code(0, fx.rc, "a lookup failure must not fail the job either")
    assert_dispatched(gate, fx, "an unresolvable PR must still dispatch")
    gate.assert_contains(fx.out, "PR lookup failed", "and say the lookup failed")
    gate.assert_contains(
        fx.out,
        "rather than risking a silently withheld release",
        "naming the asymmetry that decides the direction",
    )
    gate.log_pass("FAIL OPEN: a failed PR lookup releases anyway, loudly")


def test_a_commit_with_no_pr_releases(gate, tmp_path):
    """A direct push to main, or a commit the API knows no PR for."""
    fx = make_fixture(gate, tmp_path)
    fx.run()
    assert_dispatched(gate, fx, "a commit with no merged PR must dispatch")
    gate.assert_contains(fx.out, "no merged PR contains", "and say so")
    gate.log_pass("FAIL OPEN: a commit with no merged PR releases as before")


def test_the_label_is_declared_and_managed(gate):
    """The script keys on a literal label name, so the name has to exist and be appliable."""
    source = UNDER_TEST.read_text(encoding="utf-8")
    match = re.search(r"^SKIP_LABEL='(.*)'$", source, re.MULTILINE)
    skip_label = match.group(1) if match else ""
    gate.assert_eq(skip_label, "bump-none", "the skip label is parseable out of the script")
    labels = LABELS_FILE.read_text(encoding="utf-8")
    if not re.search(r"^- name: %s$" % re.escape(skip_label), labels, re.MULTILINE):
        gate.log_fail(
            "the script skips on '%s', which .github/labels.yml does not declare" % skip_label
        )
    if skip_label not in REVIEW_APPLIER.read_text(encoding="utf-8"):
        gate.log_fail(
            "nothing in the review applier can apply '%s', so the skip could never fire"
            % skip_label
        )
    gate.log_pass("the skip label is declared in labels.yml and appliable by the review")


# --- modes -----------------------------------------------------------------


def test_decide_only_signals_the_skip(gate, tmp_path):
    """THE FIX. CI has to know the answer BEFORE it seals the version."""
    fx = make_fixture(gate, tmp_path)
    fx.pulls_for(SHA, merged_pr(570, "bump-none"))
    fx.run("--decide-only")
    gate.assert_exit_code(0, fx.rc, "the decide step must never fail the sentinel job")
    assert_not_dispatched(gate, fx, "--decide-only must not dispatch, ever")
    gate.assert_contains(
        fx.step_output(),
        "skip_release=true",
        "a bump-none merge must set the output the seal and dispatch steps are guarded on",
    )
    gate.assert_contains(fx.out, "decision: skip", "and say so on stdout")
    gate.assert_contains(
        fx.out,
        "::notice title=Release skipped::",
        "the skip is still announced -- this is now the ONLY step that runs the decision",
    )
    gate.log_pass("FIRE: --decide-only + bump-none => skip_release=true, nothing dispatched")


def test_decide_only_stays_silent_for_a_release(gate, tmp_path):
    """CONTROL. If the output carried skip_release here too, every release would stop."""
    fx = make_fixture(gate, tmp_path)
    fx.pulls_for(SHA, merged_pr(570, ""))
    fx.run("--decide-only")
    gate.assert_exit_code(0, fx.rc, "the decide step exits clean on the release path too")
    gate.assert_not_contains(
        fx.step_output(),
        "skip_release",
        "an unlabelled PR must leave the output EMPTY so the != 'true' guards let both steps run",
    )
    gate.assert_contains(fx.out, "decision: release", "and say release on stdout")
    gate.log_pass("CONTROL: --decide-only on an unlabelled PR emits no skip signal at all")


def test_decide_only_fail_open_paths_never_signal_skip(gate, tmp_path):
    """THE DANGEROUS DIRECTION, three ways, each a path taken when the script could
    NOT answer confidently. A leaked skip_release=true would make the guarded seal and
    dispatch both skip, and the release would vanish on a green job."""
    fx = make_fixture(gate, tmp_path)

    fx.run("--decide-only", env={"GH_FAIL_ALL": "1"})
    gate.assert_exit_code(0, fx.rc, "a lookup failure must not fail the decide step")
    gate.assert_not_contains(
        fx.step_output(), "skip_release", "a failed PR lookup must not withhold the release"
    )
    gate.assert_contains(fx.out, "decision: release", "it decides to release")
    gate.assert_contains(fx.out, "PR lookup failed", "and still says the lookup failed")

    fx.setup()
    fx.run("--decide-only")
    gate.assert_not_contains(
        fx.step_output(), "skip_release", "a commit with no merged PR must not withhold the release"
    )
    gate.assert_contains(fx.out, "decision: release", "it decides to release")

    fx.setup()
    fx.pulls_for(SHA, merged_pr(570, "bump-none"), merged_pr(571, ""))
    fx.run("--decide-only")
    gate.assert_not_contains(
        fx.step_output(), "skip_release", "a mixed PR set must not withhold the release"
    )
    gate.assert_contains(fx.out, "decision: release", "it decides to release")

    # CONTROL, in this same function: the recorder and the output file DO work. Without it, all three assertions above would also pass against a script that never wrote $GITHUB_OUTPUT under any circumstances.
    fx.setup()
    fx.pulls_for(SHA, merged_pr(570, "bump-none"))
    fx.run("--decide-only")
    gate.assert_contains(
        fx.step_output(),
        "skip_release=true",
        "CONTROL: the same harness DOES capture a skip signal when one is owed",
    )
    gate.log_pass(
        "FAIL OPEN: all three unconfident paths emit no skip signal (control: bump-none does)"
    )


def test_dispatch_only_asks_nothing_and_dispatches(gate, tmp_path):
    """Asking again would double the API calls and could answer differently."""
    fx = make_fixture(gate, tmp_path)
    fx.pulls_for(SHA, merged_pr(570, "bump-none"))
    fx.run("--dispatch-only")
    gate.assert_exit_code(0, fx.rc, "--dispatch-only exits clean")
    assert_dispatched(gate, fx, "--dispatch-only dispatches unconditionally")
    gate.assert_not_contains(
        fx.gh_calls(),
        "commits/",
        "and makes NO commits/<sha>/pulls lookup, even with a bump-none fixture sitting right there",
    )
    gate.assert_not_contains(fx.step_output(), "skip_release", "it writes no step output")

    # CONTROL: the recorder is not simply always empty.
    fx.setup()
    fx.pulls_for(SHA, merged_pr(570, "bump-none"))
    fx.run("--decide-only")
    gate.assert_contains(
        fx.gh_calls(),
        "commits/%s/pulls" % SHA,
        "CONTROL: --decide-only DOES record the lookup, so the absence above is real",
    )
    gate.log_pass(
        "--dispatch-only dispatches with zero API lookups (control: --decide-only records one)"
    )


def test_dispatch_only_survives_a_dead_api(gate, tmp_path):
    """If --dispatch-only ever grew a lookup, a dead API would show up as a non-dispatch."""
    fx = make_fixture(gate, tmp_path)
    fx.run("--dispatch-only", env={"GH_FAIL_ALL": "1"})
    gate.assert_exit_code(0, fx.rc, "a dead API cannot fail the dispatch step")
    assert_dispatched(gate, fx, "--dispatch-only dispatches even when every gh call would fail")
    gate.log_pass("CONTROL: --dispatch-only with GH_FAIL_ALL=1 still dispatches")


def test_an_unknown_flag_is_a_wiring_bug(gate, tmp_path):
    """A typo'd flag must not silently restore the old lookup-and-dispatch behaviour."""
    fx = make_fixture(gate, tmp_path)
    fx.run("--decide-onlyy")
    gate.assert_exit_code(2, fx.rc, "an unknown mode flag fails loudly rather than defaulting")
    assert_not_dispatched(gate, fx, "and dispatches nothing")
    gate.log_pass("an unrecognised flag exits 2 instead of falling through to the legacy path")


# --- ci.yml wiring ---------------------------------------------------------
#
# The two predicates below take JOB TEXT rather than reading ci.yml themselves, which is the whole reason a control is possible.


def ordering_violations(job: str) -> list[str]:
    """One entry per ordering violation; empty means clean."""
    lines = job.splitlines()
    decide_line = next((i + 1 for i, ln in enumerate(lines) if "--decide-only" in ln), None)
    seal_line = next(
        (i + 1 for i, ln in enumerate(lines) if "write-release-sentinel.sh" in ln), None
    )
    if decide_line is None:
        # NO DECIDE STEP HERE IS NOW CORRECT, and that is the 2026-08-26 fix rather than a regression: the decision moved to initialize.sh (step 6b) because this job `needs: ci-complete` and is therefore DOWNSTREAM of stage-artifacts, the job that writes R2. Deciding here arrived after the uploader had already advanced the channel pointer. "Absent" must not be confused with
        # "unguarded", so absence is acceptable only when the job demonstrably READS the decision.
        if "needs.initialize.outputs.skip_release" in job:
            return []
        return [
            (
                "no --decide-only step AND no read of "
                "needs.initialize.outputs.skip_release: nothing decides"
            )
        ]
    if seal_line is None:
        return ["no write-release-sentinel.sh step in the job at all"]
    if decide_line >= seal_line:
        return [
            "the release decision (line %d) does not precede the seal (line %d)"
            % (decide_line, seal_line)
        ]
    return []


def polarity_violations(job: str) -> list[str]:
    """One entry per polarity violation; empty means clean."""
    lines = job.splitlines()
    inverted = len([ln for ln in lines if "skip_release != 'true'" in ln])
    wrong = len([ln for ln in lines if "skip_release == 'true'" in ln])
    found = []
    if wrong:
        found.append(
            "%d guard(s) use == 'true'; a cancelled or OOM-killed decide step would then "
            "skip BOTH the seal and the dispatch on a green job" % wrong
        )
    if inverted != 2:
        found.append(
            "expected exactly 2 steps guarded with != 'true' (the seal and the dispatch), "
            "found %d" % inverted
        )
    return found


def finalize_job_text() -> str:
    """The twin's awk: from `  finalize-release-sentinel:` to the next top-level job key."""
    out = []
    inside = False
    for line in CI_WORKFLOW.read_text(encoding="utf-8").splitlines():
        if line.startswith("  finalize-release-sentinel:"):
            inside = True
        elif inside and re.match(r"^  [a-z][a-z0-9-]*:$", line):
            break
        if inside:
            out.append(line)
    return "\n".join(out)


def test_ci_yml_wires_the_script(gate):
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    gate.assert_contains(workflow, "dispatch_release", "ci.yml calls the script")
    job = finalize_job_text()
    gate.assert_contains(
        job, "rediacc_ci.ci.dispatch_release", "from the finalize-release-sentinel job"
    )
    gate.assert_not_contains(
        job,
        "gh workflow run cd-v2.yml",
        "and the inline dispatch is gone, so there is only ONE place the decision can be made",
    )
    gate.assert_contains(job, "GH_TOKEN", "the script still gets its token")
    # THE DECISION MOVED OUT OF THIS JOB (2026-08-26). The invariant that replaces "the decide step exists" is strictly stronger: this job must NOT decide and must read the one shared output. One evaluation, five readers.
    gate.assert_not_contains(
        job,
        "--decide-only",
        "finalize no longer re-decides; asking twice can answer differently if a label moves",
    )
    gate.assert_contains(
        job,
        "needs.initialize.outputs.skip_release",
        "and it reads the ONE decision made in initialize",
    )
    gate.log_pass("ci.yml dispatches through the script, with no second inline path")


def test_ci_yml_decides_before_it_seals(gate):
    """THE ROOT CAUSE, asserted structurally. Sealing before deciding is what put cli/v1.2.27/.released in R2 with no v1.2.27 tag."""
    found = ordering_violations(finalize_job_text())
    if found:
        gate.log_fail("finalize-release-sentinel orders its steps wrongly: %s" % "; ".join(found))

    broken = (
        "      - name: Write release sentinels\n"
        "        run: .ci/scripts/deploy/write-release-sentinel.sh --version v1.2.27\n"
        "      - name: Dispatch cd-v2 release\n"
        "        run: .ci/scripts/ci/dispatch-release.sh --decide-only"
    )
    found = ordering_violations(broken)
    if not found:
        gate.log_fail(
            "CONTROL FAILED: ordering_violations passed a block that seals before it "
            "decides, so it cannot detect the bug it exists for"
        )
    gate.assert_contains(
        "\n".join(found), "does not precede the seal", "and the control names the defect"
    )
    gate.log_pass("ci.yml decides before it seals (control: the pre-fix order IS reported)")


def test_ci_yml_guards_fail_toward_releasing(gate):
    """POLARITY. `!= 'true'` releases on every degenerate state; `== 'true'` would
    withhold on every degenerate state, green and silent."""
    found = polarity_violations(finalize_job_text())
    if found:
        gate.log_fail("finalize-release-sentinel's step guards are wrong: %s" % "; ".join(found))

    broken = (
        "      - name: Write release sentinels\n"
        "        if: steps.release-decision.outputs.skip_release == 'true'\n"
        "      - name: Dispatch cd-v2 release\n"
        "        if: steps.release-decision.outputs.skip_release == 'true'"
    )
    found = polarity_violations(broken)
    if not found:
        gate.log_fail("CONTROL FAILED: polarity_violations accepted == 'true' on both steps")
    gate.assert_contains(
        "\n".join(found), "== 'true'", "and the control names the inverted comparison"
    )

    # CONTROL 2: a guarded dispatch with an unguarded seal is the original bug exactly.
    broken = (
        "      - name: Write release sentinels\n"
        "        run: .ci/scripts/deploy/write-release-sentinel.sh\n"
        "      - name: Dispatch cd-v2 release\n"
        "        if: steps.release-decision.outputs.skip_release != 'true'"
    )
    found = polarity_violations(broken)
    if not found:
        gate.log_fail(
            "CONTROL FAILED: polarity_violations accepted a block where only the dispatch "
            "is guarded"
        )
    gate.assert_contains("\n".join(found), "found 1", "and the control counts the guards")
    gate.log_pass(
        "both steps carry != 'true' (controls: == 'true' rejected, single-guard rejected)"
    )
