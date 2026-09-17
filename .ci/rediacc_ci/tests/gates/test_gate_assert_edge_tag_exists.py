"""Port of `.ci/scripts/test/gates/test-assert-edge-tag-exists.sh`.

`promote-stable` must refuse to promote a version that does not fully exist -- and
must refuse just as loudly when it CANNOT TELL whether it exists.

WHY THIS EXISTS. `cli/edge/manifest.json` advertised 1.3.1 with no v1.3.1 tag, no
GitHub Release and no `cli/v1.3.1/.released`. `promote-stable.yml` would have copied
those bytes to stable and retagged Docker `:stable` FIRST and only then failed on
`ref: v1.3.1` while checking out for the three regional deploys -- a half-applied
production release. This drives the precondition that turns that ordering into a
loud no-op.

WHAT IT ASSERTS, with a fake `gh` and a fake `aws` (no network, no promotion):
  1. no tag ref                 -> exit 1
  2. tag, no GitHub Release     -> exit 1
  3. tag + release, no sentinel -> exit 1
  4. all three present          -> exit 0   (proves it is not always-red)
  5. gh answers 403             -> exit 1, NOT 0. A 404 confirms absence; a 403,
                                   5xx or network error means the check DID NOT RUN,
                                   and a check that did not run must not read as a pass.
  6. aws cannot authenticate    -> exit 1, same reason on the R2 probe.
  7. ANTI-VACUITY: the passing case must have actually CALLED all three probes. A
     script returning 0 without probing would satisfy 4 alone.

CONTROL-FIRST. The mutant is assembled BY CONSTRUCTION -- head, a literal
replacement arm written here, tail, split on the subject's own
`COULD_NOT_TELL_ARM_BEGIN` / `_END` anchors -- in which "could not tell" returns 0
instead of failing. Case 5 must go GREEN against it; if it does not, this module
declares itself broken. The mutant is also proven LIVE (case 4 still 0, case 1 still
1) so a mutant that merely crashes cannot masquerade as a firing control.

NO PATTERN SUBSTITUTION OF A LIVE LINE, and that is the point of the anchors: a
reworded arm cannot silently yield a "mutant" identical to the source. The port
keeps both refusals the twin has -- anchors missing, and mutant identical to source
-- because either one turns the control into decoration.

WHY THE MUTANT NEEDS A SANDBOX. The subject resolves its library with
`"$SCRIPT_DIR/../lib/common.sh"`, so a mutant dropped in a bare temp directory dies
at its source line, and the liveness probe below would (correctly) refuse to accept
that as a firing control. The sandbox mirrors the real layout with the library
symlinked in.

STATED BLIND SPOT, carried over verbatim: this cannot see whether
`promote-stable.yml` actually RUNS the script, nor whether it runs BEFORE the first
promotion write. A precondition wired after the promotion is worth nothing. That
step-order assertion belongs to the workflow-invariant gate (plan T2), not here.

NO `xdist_group`. Every case builds its own fixture tree under pytest's `tmp_path`
and passes PATH per invocation as an ENV OVERLAY rather than mutating this process's
own PATH, so two of these in one worker cannot see each other's fakes.
"""

import os
import stat

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-assert-edge-tag-exists.sh"

TARGET = paths.from_root(".ci", "scripts", "release", "assert-edge-tag-exists.sh")
LIB_DIR = paths.from_root(".ci", "scripts", "lib")

BEGIN_ANCHOR = "COULD_NOT_TELL_ARM_BEGIN"
END_ANCHOR = "COULD_NOT_TELL_ARM_END"

# The arm the mutant carries INSTEAD of the real one: an unprovable probe read as a pass. Written here as a literal, never derived from the live text.
MUTANT_ARM = """        unknown:*)
            log_warn "MUTANT: treating an unprovable probe as a pass -- ${what}"
            return 0
            ;;
"""

# TAG_STATE / REL_STATE drive the two gh probes independently:
#   present -> exit 0; absent -> the real 404 wording, exit 1; forbid -> a 403.
FAKE_GH = """#!/bin/bash
printf '%s\\n' "$*" >>"{log}"
state=""
case "$1 $2" in
    "api repos"*) state="${{TAG_STATE:-present}}" ;;
    "release view") state="${{REL_STATE:-present}}" ;;
    *)
        case "$*" in
            api*) state="${{TAG_STATE:-present}}" ;;
            *) state="${{REL_STATE:-present}}" ;;
        esac
        ;;
esac
case "$state" in
    present) echo '{{"ok":true}}'; exit 0 ;;
    absent)  echo 'gh: Not Found (HTTP 404)' >&2; exit 1 ;;
    forbid)  echo 'gh: Resource not accessible by integration (HTTP 403)' >&2; exit 1 ;;
esac
echo "fake gh: unknown state '$state'" >&2
exit 9
"""

FAKE_AWS = """#!/bin/bash
printf '%s\\n' "$*" >>"{log}"
case "${{SENTINEL_STATE:-present}}" in
    present) echo '{{"ContentLength":42}}'; exit 0 ;;
    absent)  echo 'An error occurred (404) when calling the HeadObject operation: Not Found' >&2; exit 254 ;;
    forbid)  echo 'Unable to locate credentials. You can configure credentials by running "aws configure".' >&2; exit 255 ;;
esac
echo "fake aws: unknown state" >&2
exit 9
"""


class Probe:
    """One invocation's result plus what each fake was actually called with."""

    def __init__(self, result: harness.RunResult, gh_calls: int, aws_calls: int) -> None:
        self.rc = result.rc
        self.out = result.combined
        self.gh_calls = gh_calls
        self.aws_calls = aws_calls


class Fakes:
    """The fake `gh` and `aws` pair, plus the call logs they append to."""

    def __init__(self, directory) -> None:
        self.bindir = directory / "bin"
        self.bindir.mkdir(parents=True, exist_ok=True)
        self.gh_log = directory / "gh.log"
        self.aws_log = directory / "aws.log"
        self._write("gh", FAKE_GH.format(log=self.gh_log))
        self._write("aws", FAKE_AWS.format(log=self.aws_log))

    def _write(self, name: str, body: str) -> None:
        path = self.bindir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def run(self, script, tag: str, rel: str, sent: str) -> Probe:
        """Drive `script` under the fakes, streams MERGED as the twin captures them.

        PATH IS AN ENV OVERLAY, not a mutation of this process. The twin uses
        `env PATH=... bash "$script"`, which is per-invocation for the same reason;
        `harness.run`'s `env=` overlays rather than replaces, so PATH is prefixed
        and HOME and the rest survive.
        """
        self.gh_log.write_text("", encoding="utf-8")
        self.aws_log.write_text("", encoding="utf-8")
        bash = harness.require_tool("bash", "install bash; the subject is a bash script")
        result = harness.run(
            [bash, str(script), "--version", "1.3.0"],
            env={
                "PATH": "%s%s%s" % (self.bindir, os.pathsep, os.environ.get("PATH", "")),
                "TAG_STATE": tag,
                "REL_STATE": rel,
                "SENTINEL_STATE": sent,
                "GITHUB_REPOSITORY": "rediacc/console",
                "CLOUDFLARE_R2_ENDPOINT": "https://example.invalid",
                "RELEASES_BUCKET": "rediacc-releases",
                "CLOUDFLARE_R2_ACCESS_KEY_ID": "test-key-id",
                "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "test-secret",
            },
            stdin="",
        )
        return Probe(
            result,
            len([ln for ln in self.gh_log.read_text(encoding="utf-8").splitlines() if ln]),
            len([ln for ln in self.aws_log.read_text(encoding="utf-8").splitlines() if ln]),
        )


def fakes(gate, tmp_path) -> Fakes:
    if not TARGET.is_file():
        gate.log_fail("assert-edge-tag-exists.sh not found at %s" % paths.relative_to_root(TARGET))
    return Fakes(tmp_path)


# -- the six properties, each 0 when it HOLDS --------------------------------- Written as predicates returning a complaint (or None) so the mutant control can re-run the very same code against the planted copy. That is what makes case 5 and its control the same assertion rather than two similar ones.


def case_no_tag(f: Fakes, script) -> str | None:
    probe = f.run(script, "absent", "present", "present")
    if probe.rc != 1:
        return "exit %d (expected 1) for a version with no tag ref" % probe.rc
    if "MISSING" not in probe.out:
        return "failure did not name the missing thing"
    return None


def case_no_release(f: Fakes, script) -> str | None:
    probe = f.run(script, "present", "absent", "present")
    if probe.rc != 1:
        return "exit %d (expected 1) for a tag with no GitHub Release" % probe.rc
    return None


def case_no_sentinel(f: Fakes, script) -> str | None:
    probe = f.run(script, "present", "present", "absent")
    if probe.rc != 1:
        return "exit %d (expected 1) for a tag+release with no .released sentinel" % probe.rc
    return None


def case_all_present(f: Fakes, script) -> str | None:
    probe = f.run(script, "present", "present", "present")
    if probe.rc != 0:
        return "exit %d (expected 0) with all three present:\n%s" % (probe.rc, probe.out)
    # ANTI-VACUITY: a script returning 0 without probing would pass the line above.
    if probe.gh_calls < 2 or probe.aws_calls < 1:
        return (
            "ANTI-VACUITY: the passing run made %d gh call(s) and %d aws call(s); it did "
            "not probe all three" % (probe.gh_calls, probe.aws_calls)
        )
    return None


def case_gh_cannot_tell(f: Fakes, script) -> str | None:
    probe = f.run(script, "forbid", "present", "present")
    if probe.rc != 1:
        return (
            "exit %d (expected 1) when gh answered 403 -- 'could not tell' was read as a "
            "pass" % probe.rc
        )
    if "COULD NOT TELL" not in probe.out:
        return "exit 1, but the message does not distinguish 'could not tell' from 'missing'"
    return None


def case_aws_cannot_tell(f: Fakes, script) -> str | None:
    probe = f.run(script, "present", "present", "forbid")
    if probe.rc != 1:
        return "exit %d (expected 1) when the R2 probe could not authenticate" % probe.rc
    if "COULD NOT TELL" not in probe.out:
        return "exit 1, but the message does not distinguish 'could not tell' from 'missing'"
    return None


def must_hold(gate, predicate, script, f: Fakes, label: str) -> None:
    gate.assertions += 1
    detail = predicate(f, script)
    if detail:
        gate.log_fail("%s\n    %s" % (label, detail))
    gate.log_pass(label)


def test_no_git_tag_ref(gate, tmp_path):
    must_hold(gate, case_no_tag, TARGET, fakes(gate, tmp_path), "1. no git tag ref -> exit 1")


def test_tag_but_no_github_release(gate, tmp_path):
    must_hold(
        gate,
        case_no_release,
        TARGET,
        fakes(gate, tmp_path),
        "2. tag but no GitHub Release -> exit 1",
    )


def test_tag_and_release_but_no_sentinel(gate, tmp_path):
    must_hold(
        gate,
        case_no_sentinel,
        TARGET,
        fakes(gate, tmp_path),
        "3. tag + release but no cli/v1.3.0/.released -> exit 1",
    )


def test_all_three_present_and_all_three_probed(gate, tmp_path):
    must_hold(
        gate,
        case_all_present,
        TARGET,
        fakes(gate, tmp_path),
        "4. all three present -> exit 0, having probed all three",
    )


def test_gh_403_is_not_a_pass(gate, tmp_path):
    must_hold(
        gate,
        case_gh_cannot_tell,
        TARGET,
        fakes(gate, tmp_path),
        "5. gh 403 -> exit 1, NOT 0 (could not tell is a failure)",
    )


def test_r2_credentials_unusable_is_not_a_pass(gate, tmp_path):
    must_hold(
        gate,
        case_aws_cannot_tell,
        TARGET,
        fakes(gate, tmp_path),
        "6. R2 credentials unusable -> exit 1, distinguishably",
    )


def test_the_control_fires_against_a_planted_403_pass(gate, tmp_path):
    """THE CONTROL, built by construction and proven LIVE before it is believed."""
    gate.log_test("CONTROL: a mutant that reads an unprovable probe as a pass")
    source = TARGET.read_text(encoding="utf-8").splitlines(keepends=True)
    begin = end = None
    for index, line in enumerate(source):
        if BEGIN_ANCHOR in line and begin is None:
            begin = index
        if END_ANCHOR in line and end is None:
            end = index
    if begin is None or end is None or end <= begin:
        gate.log_fail(
            "CONTROL COULD NOT PLANT: could-not-tell anchors not found in %s "
            "(begin=%s end=%s)" % (paths.relative_to_root(TARGET), begin, end)
        )

    sandbox = tmp_path / "sb" / ".ci" / "scripts"
    (sandbox / "release").mkdir(parents=True)
    (sandbox / "lib").mkdir(parents=True)
    for item in sorted(LIB_DIR.iterdir()):
        (sandbox / "lib" / item.name).symlink_to(item)
    mutant = sandbox / "release" / "mutant-403-passes.sh"
    mutant.write_text(
        "".join(source[:begin]) + MUTANT_ARM + "".join(source[end + 1 :]), encoding="utf-8"
    )
    mutant.chmod(mutant.stat().st_mode | stat.S_IXUSR)

    text = mutant.read_text(encoding="utf-8")
    if BEGIN_ANCHOR in text:
        gate.log_fail("CONTROL COULD NOT PLANT: anchor survived in the mutant")
    if text == TARGET.read_text(encoding="utf-8"):
        gate.log_fail("CONTROL COULD NOT PLANT: mutant is identical to the source")

    # LIVENESS. A mutant that merely crashes exits non-zero for reasons unrelated to the plant, and case 5 would "still fail" for the wrong reason. Prove the mutant both RUNS (case 4 -> 0) and still detects genuine absence (case 1 -> 1).
    f = fakes(gate, tmp_path)
    gate.assertions += 1
    if case_all_present(f, mutant) is not None or case_no_tag(f, mutant) is not None:
        gate.log_fail("MUTANT IS NOT LIVE: the planted copy no longer runs its unmutated cases")
    gate.log_pass("the mutant is live: it still passes case 4 and still fails case 1")

    gate.assertions += 1
    if case_gh_cannot_tell(f, mutant) is None:
        gate.log_fail(
            "CONTROL DID NOT FIRE: the mutant treats a 403 as a pass and case 5 still went "
            "green -- assertion 5 proves nothing"
        )
    gate.log_pass("control fires: 403-arm-returns-0 mutant is caught by case 5")
