"""Port of `.ci/scripts/test/gates/test-mark-production.sh`.

The production marker must refuse to lie about what is live.

WHY THIS EXISTS. `production` is a moving tag and `--latest` is the badge a human
reads as "what is in production". Both are claims about reality, so the script that
writes them has exactly one job beyond writing: refusing when it cannot confirm the
claim.

The failure this guards is not "it wrote the wrong sha". It is the softer one this
repo keeps paying for: a probe that could not run being read as a pass. `gh`
returning 403, or the network dropping, must NOT mark a version as production --
"could not tell" is a failure, exactly as in assert-edge-tag-exists.sh.

HERMETIC: `gh` is shimmed, so this never touches GitHub and cannot move a real tag.
A gate that needs the network is a gate that gets skipped on somebody else's outage.

WHAT THIS CANNOT SEE: it does not prove promote-stable.yml actually RUNS the script,
nor that it runs AFTER endpoint verification. That wiring is
check-ci-workflow-invariants.sh's kind of subject, not this file's.
"""

import os
import pathlib
import stat

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-mark-production.sh"

SUT = paths.from_root(".ci", "scripts", "release", "mark-production.sh")

# The two anchors the CONTROL cuts between. Named at module level because the control's whole value is that it fails LOUDLY when they move, rather than performing a no-op excision and reporting that the guard is not what refuses.
GUARD_START = 'if ! out="$(gh release view'
GUARD_END = 'log_info "mark-production: $VERSION is a published release"'

MALFORMED = ("", "1.3", "v1.3.1-rc1", "latest", "v1.3.1; rm -rf /")


def make_gh(workdir: pathlib.Path, mode: str) -> pathlib.Path:
    """A `gh` whose RELEASE VIEW behaves per `mode`; everything else succeeds
    quietly so only the property under test can decide the outcome.

    `.object.sha` is asked twice: once on the ref (always succeeds here,
    already jq-filtered to the bare sha), once on the tag object itself when
    `.object.type` was "tag" (the deref, which `deref-fails` breaks)."""
    bindir = workdir / ("bin-" + mode)
    bindir.mkdir(parents=True, exist_ok=True)
    script = bindir / "gh"
    script.write_text(
        "#!/bin/bash\n"
        'mode="%s"\n'
        'case "$*" in\n'
        '  "release view"*)\n'
        '      case "$mode" in\n'
        '        ok)      echo \'{"tagName":"v1.3.1"}\' ;;\n'
        '        missing) echo "release not found" >&2; exit 1 ;;\n'
        '        cannot)  echo "HTTP 403: Resource not accessible" >&2; exit 1 ;;\n'
        "      esac\n"
        "      ;;\n"
        '  *"object.sha"*)\n'
        '      case "$mode" in\n'
        "        deref-fails)\n"
        '            case "$*" in\n'
        '              *"git/tags/"*) echo "HTTP 403: Resource not accessible" >&2; exit 1 ;;\n'
        '              *)             echo "deadbeef" ;;\n'
        "            esac\n"
        "            ;;\n"
        '        *) echo "deadbeef" ;;\n'
        "      esac\n"
        "      ;;\n"
        '  *"object.type"*)\n'
        '      case "$mode" in\n'
        '        type-fails)  echo "HTTP 403: Resource not accessible" >&2; exit 1 ;;\n'
        '        deref-fails) echo "tag" ;;\n'
        '        *)           echo "commit" ;;\n'
        "      esac\n"
        "      ;;\n"
        '  *"git/ref/tags/v"*) echo \'{"object":{"sha":"deadbeef","type":"commit"}}\' ;;\n'
        "  *\"git/refs\"*)       echo '{}' ;;\n"
        '  *"release edit"*)   echo "edited" ;;\n'
        "  *)                  echo '{}' ;;\n"
        "esac\n" % mode,
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def run_sut(workdir: pathlib.Path, mode: str, version: str, script: pathlib.Path = SUT) -> int:
    bindir = make_gh(workdir, mode)
    return harness.run(
        ["bash", str(script), version],
        env={
            "PATH": "%s:%s" % (bindir, os.environ.get("PATH", "")),
            "GITHUB_REPOSITORY": "rediacc/console",
        },
    ).rc


def test_a_published_release_is_marked(gate, tmp_path):
    gate.log_test("a genuinely published version is marked")
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % SUT)
    # The anti-vacuity half: if this cannot pass, every refusal below is satisfied trivially by a script that always fails.
    if run_sut(tmp_path, "ok", "v1.3.1") != 0:
        gate.log_fail("a published release was refused; the refusals below would prove nothing")
    gate.log_pass("a published release is marked")


def test_an_unpublished_version_is_refused(gate, tmp_path):
    gate.log_test("a version with no GitHub Release must be REFUSED")
    if run_sut(tmp_path, "missing", "v9.9.9") == 0:
        gate.log_fail(
            "marked a version that was never published -- 'production' would name a "
            "release that does not exist"
        )
    gate.log_pass("an unpublished version is refused")


def test_could_not_tell_is_a_failure(gate, tmp_path):
    gate.log_test("a 403 must FAIL, not pass -- a probe that did not run is not a pass")
    if run_sut(tmp_path, "cannot", "v1.3.1") == 0:
        gate.log_fail(
            "a 403 was read as permission to mark production; 'could not tell' must never be a pass"
        )
    gate.log_pass("an unreadable probe fails rather than marking production")


def test_object_type_lookup_failure_is_a_refusal(gate, tmp_path):
    gate.log_test(
        "FIXED 2026-09-10: a failed .object.type lookup must refuse, not proceed as if "
        "the tag were a plain commit"
    )
    if run_sut(tmp_path, "type-fails", "v1.3.1") == 0:
        gate.log_fail(
            "marked production despite an unreadable .object.type -- a swallowed failure "
            "here used to silently skip dereferencing an annotated tag"
        )
    gate.log_pass("an unreadable .object.type lookup refuses rather than silently proceeding")


def test_annotated_tag_deref_failure_is_a_refusal(gate, tmp_path):
    gate.log_test(
        "FIXED 2026-09-10: a failed annotated-tag dereference must refuse, not move "
        "production to the tag object"
    )
    if run_sut(tmp_path, "deref-fails", "v1.3.1") == 0:
        gate.log_fail(
            "marked production despite a failed annotated-tag dereference -- production "
            "would have been moved to point at a tag object instead of a commit"
        )
    gate.log_pass(
        "a failed annotated-tag dereference refuses rather than moving production to the "
        "wrong object"
    )


def test_malformed_versions_never_become_tags(gate, tmp_path):
    gate.log_test("a malformed version must never become the production tag")
    for bad in MALFORMED:
        if run_sut(tmp_path, "ok", bad) == 0:
            gate.log_fail(
                "accepted '%s' as a version; the production tag is the thing humans trust" % bad
            )
    gate.log_pass("%d malformed versions rejected" % len(MALFORMED))


def test_control_the_guard_can_be_removed(gate, tmp_path):
    gate.log_test("CONTROL: delete the release check and the refusals MUST stop firing")
    # By CONSTRUCTION: copy the script and cut the block that verifies the release exists, then require the unpublished case to flip to success. If it does not flip, the assertions above are not reaching the guard.
    body = SUT.read_text(encoding="utf-8")
    for anchor in (GUARD_START, GUARD_END):
        if anchor not in body:
            gate.log_fail(
                "CONTROL could not plant its defect: the anchor %r is gone from "
                "mark-production.sh, so nothing would be excised and the refusals "
                "above would not be shown to depend on the release check" % anchor
            )
    mutant = tmp_path / "mut.sh"
    mutant.write_text(
        body[: body.index(GUARD_START)] + body[body.index(GUARD_END) :], encoding="utf-8"
    )
    rc = run_sut(tmp_path, "missing", "v9.9.9", script=mutant)
    if rc != 0:
        gate.log_fail(
            "CONTROL DID NOT FIRE: the unpublished case still failed (rc=%d) with the "
            "guard removed, so it is not what refuses" % rc
        )
    gate.log_pass("control fires: without the release check, an unpublished version gets marked")
