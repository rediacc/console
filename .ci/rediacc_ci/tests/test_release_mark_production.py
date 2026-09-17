"""Differential: `rediacc_ci.release.mark_production` against its twin `.ci/scripts/release/mark-production.sh`.

A RECORDING FAKE `gh` ON PATH, the seam `test_housekeeping_cleanup_github_deployments.py` established this wave. Nothing here reaches GitHub, and the real `gh` is never on the PATH handed to either side. That matters more here than anywhere else in this box: the real script MOVES the `production` tag and re-points the "Latest release" badge on whatever repository
`$GITHUB_REPOSITORY` names, and this machine has a logged-in
`gh`. Every case pins `GITHUB_REPOSITORY=acme/widget` as well, so even a leak
would not name the real repository.

THE CALL LOG IS COMPARED, NOT JUST THE STREAMS. The observable effect of this script is four possible mutations (`PATCH` a ref, `POST` a ref, `release edit --latest`, and nothing at all), and two implementations can print identical text while making different requests. The dereference step is the sharpest example: a port that skipped it would print the same two lines and point
`production` at a tag ANNOTATION instead of a commit.

BOTH LOGGING WORLDS ARE DRIVEN. `source common.sh 2>/dev/null || { ... }` gives
the script a second, private logger whose `log_info` writes to STDOUT with no glyph. `test_the_fallback_logger_world_...` copies each subject into a fixture tree that has no `.ci/scripts/lib/`, which is the only way to reach that branch, and compares the streams there too.

THE ONE DELIBERATE DIVERGENCE IS ASSERTED, NOT HIDDEN.
`test_divergence_common_sh_interprets_backslash_escapes_in_gh_error_text` drives a `gh` failure whose text contains a literal backslash-n and asserts that the twin (via `echo -e`) renders a newline while the port renders two characters. `rediacc_ci.log`'s module docstring already rules on this class; this pins it on the one script in the box that interpolates API text into a log
message.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.release import mark_production as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "release" / "mark-production.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "release" / "mark_production.py"
BASH = shutil.which("bash") or "/bin/bash"

FAKE_GH = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write("\\t".join(argv) + "\\n")


def fail(text, code):
    sys.stderr.write(text)
    sys.exit(code)


joined = "\\t".join(argv)

if argv[:2] == ["release", "view"]:
    rc = int(os.environ.get("FAKE_GH_VIEW_RC", "0"))
    if rc:
        fail(os.environ.get("FAKE_GH_VIEW_ERR", "release not found\\n"), rc)
    sys.stdout.write('{"tagName":"%s"}\\n' % argv[2])
    sys.exit(0)

if argv[:2] == ["release", "edit"]:
    rc = int(os.environ.get("FAKE_GH_EDIT_RC", "0"))
    sys.stdout.write("https://github.com/acme/widget/releases/tag/%s\\n" % argv[2])
    if rc:
        fail("gh: fake release edit failure\\n", rc)
    sys.exit(0)

if "/git/ref/tags/" in joined:
    which = argv[-1]
    if which == ".object.sha":
        rc = int(os.environ.get("FAKE_GH_REF_RC", "0"))
        if rc:
            fail("gh: fake ref lookup failure\\n", rc)
        sys.stdout.write(os.environ.get("FAKE_GH_REF_SHA", "a" * 40) + "\\n")
        sys.exit(0)
    rc = int(os.environ.get("FAKE_GH_TYPE_RC", "0"))
    if rc:
        fail("gh: fake type lookup failure\\n", rc)
    sys.stdout.write(os.environ.get("FAKE_GH_REF_TYPE", "commit") + "\\n")
    sys.exit(0)

if "/git/tags/" in joined:
    rc = int(os.environ.get("FAKE_GH_DEREF_RC", "0"))
    if rc:
        fail("gh: fake deref failure\\n", rc)
    sys.stdout.write(os.environ.get("FAKE_GH_DEREF_SHA", "b" * 40) + "\\n")
    sys.exit(0)

if "/git/refs/tags/production" in joined and "--method" not in argv:
    sys.stdout.write("probe stdout that must never be seen\\n")
    sys.stderr.write("probe stderr that must never be seen\\n")
    sys.exit(int(os.environ.get("FAKE_GH_PROD_REF_RC", "0")))

if "--method" in argv:
    sys.stdout.write("mutation stdout that must never be seen\\n")
    rc = int(os.environ.get("FAKE_GH_MUTATE_RC", "0"))
    if rc:
        fail("gh: fake mutation failure\\n", rc)
    sys.exit(0)

fail("fake gh: unrouted call: %s\\n" % joined, 90)
"""

# common.sh needs `dirname` and `uname` at source time and `tr` in parse_args;
# this script does not call parse_args, but `dirname` is used by the twin itself and `uname` by the library, so both must be reachable.
PATH_MINIMUM = ("dirname", "uname", "tr")


def _bin(tmp_path: pathlib.Path, name: str, *, with_gh: bool = True) -> str:
    stub = tmp_path / name
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    if with_gh:
        fake = stub / "gh"
        fake.write_text(FAKE_GH, encoding="utf-8")
        fake.chmod(0o755)
    else:
        assert shutil.which("gh", path=str(stub)) is None, "gh leaked into the stub PATH"
    return str(stub)


def _run(
    subject: pathlib.Path,
    tmp_path: pathlib.Path,
    args: list[str],
    *,
    with_gh: bool = True,
    **gh_env: str,
):
    side = "old" if subject.suffix == ".sh" else "new"
    call_log = tmp_path / f"{side}-gh-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tmp_path, f"{side}-bin", with_gh=with_gh),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GH_LOG": str(call_log),
        # NEVER the real repository, even if the fake were somehow bypassed.
        "GITHUB_REPOSITORY": "acme/widget",
    }
    env.update(gh_env)
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    return proc, calls


def run_both(tmp_path: pathlib.Path, args: list[str], *, with_gh: bool = True, **gh_env: str):
    old, old_calls = _run(TWIN, tmp_path, args, with_gh=with_gh, **gh_env)
    new, new_calls = _run(PORT, tmp_path, args, with_gh=with_gh, **gh_env)
    return old, new, old_calls, new_calls


def _assert_agree(old, new, label: str, old_calls=None, new_calls=None) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    assert new.stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new.stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )
    if old_calls is not None:
        assert new_calls == old_calls, (
            f"{label}: gh call sequence diverged:\nold: {old_calls}\nnew: {new_calls}"
        )


VIEW = "release\tview\tv1.3.1\t--json\ttagName"
REF_SHA = "api\trepos/acme/widget/git/ref/tags/v1.3.1\t--jq\t.object.sha"
REF_TYPE = "api\trepos/acme/widget/git/ref/tags/v1.3.1\t--jq\t.object.type"
PROD_PROBE = "api\trepos/acme/widget/git/refs/tags/production"
EDIT = "release\tedit\tv1.3.1\t--latest"
A40 = "a" * 40
B40 = "b" * 40


def test_no_version_is_refused(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, [])
    assert old.returncode == 1
    assert old.stderr == "✗ mark-production: no version given (argv[1] or $VERSION)\n"
    assert old.stdout == ""
    assert old_calls == [], "gh was called before the version was validated"
    _assert_agree(old, new, "no-version", old_calls, new_calls)


def test_the_version_environment_variable_is_the_fallback(tmp_path: pathlib.Path) -> None:
    """`${1:-${VERSION:-}}`: argv wins, the environment is the fallback, and an
    EMPTY argv[1] falls through to the environment rather than being refused."""
    old, new, old_calls, new_calls = run_both(tmp_path, [""], VERSION="1.3.1")
    assert old.returncode == 0
    assert "mark-production: v1.3.1 is a published release" in old.stderr
    _assert_agree(old, new, "version-env", old_calls, new_calls)


def test_the_leading_v_is_added_exactly_once(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["1.3.1"])
    assert old.returncode == 0
    assert VIEW in old_calls, "the bare version was not normalised to v1.3.1"
    _assert_agree(old, new, "normalise", old_calls, new_calls)


def test_a_double_v_is_not_stripped_twice_and_is_refused(tmp_path: pathlib.Path) -> None:
    """`v${VERSION#v}` strips ONE `v`, so `vv1.3.1` stays malformed and is
    rejected by the semver test. Reproduced rather than tidied: this is the rule that decides which strings can ever become the `production` tag."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["vv1.3.1"])
    assert old.returncode == 1
    assert old.stderr == "✗ mark-production: 'vv1.3.1' is not strict semver (expected vX.Y.Z)\n"
    assert old_calls == []
    _assert_agree(old, new, "double-v", old_calls, new_calls)


def test_a_non_semver_version_is_refused(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["1.3"])
    assert old.returncode == 1
    assert "'v1.3' is not strict semver" in old.stderr
    assert old_calls == []
    _assert_agree(old, new, "non-semver", old_calls, new_calls)


def test_a_prerelease_suffix_is_refused(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["v1.3.1-rc.1"])
    assert old.returncode == 1
    assert old_calls == []
    _assert_agree(old, new, "prerelease", old_calls, new_calls)


def test_missing_gh_is_refused_first(tmp_path: pathlib.Path) -> None:
    """`require_cmd gh` runs BEFORE the version is even read, so a machine without gh says so even with no arguments at all."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], with_gh=False)
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'gh' is not available\n"
    _assert_agree(old, new, "missing-gh", old_calls, new_calls)


def test_an_unpublished_version_takes_the_never_published_branch(
    tmp_path: pathlib.Path,
) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["v1.3.1"],
        FAKE_GH_VIEW_RC="1",
        FAKE_GH_VIEW_ERR="release not found\n",
    )
    assert old.returncode == 1
    assert old.stderr == (
        "✗ mark-production: no GitHub Release for v1.3.1; refusing to mark a version "
        "that was never published\n"
    )
    assert old_calls == [VIEW], "a refused version still reached the tag API"
    _assert_agree(old, new, "never-published", old_calls, new_calls)


def test_a_403_is_could_not_tell_and_is_a_different_message(tmp_path: pathlib.Path) -> None:
    """THE POINT OF THE WHOLE SCRIPT. A lookup that could not run must not be filed as "no such release": the first is an unknown, the second is a fact. Both exit 1, and the operator has to be able to tell them apart."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["v1.3.1"],
        FAKE_GH_VIEW_RC="1",
        FAKE_GH_VIEW_ERR="HTTP 403: Resource not accessible by integration\n",
    )
    assert old.returncode == 1
    assert "so the check did NOT run" in old.stderr
    assert "HTTP 403" in old.stderr, "gh's own text is not carried into the message"
    assert "never published" not in old.stderr
    assert old_calls == [VIEW]
    _assert_agree(old, new, "could-not-tell", old_calls, new_calls)


def test_a_lightweight_tag_is_not_dereferenced(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["v1.3.1"], FAKE_GH_REF_TYPE="commit")
    assert old.returncode == 0
    assert old_calls == [
        VIEW,
        REF_SHA,
        REF_TYPE,
        PROD_PROBE,
        (
            "api\t--method\tPATCH\trepos/acme/widget/git/refs/tags/production"
            f"\t-f\tsha={A40}\t-F\tforce=true"
        ),
        EDIT,
    ]
    assert f"moved the 'production' tag to v1.3.1 ({A40})" in old.stderr
    _assert_agree(old, new, "lightweight-tag", old_calls, new_calls)


def test_an_annotated_tag_is_dereferenced_to_its_commit(tmp_path: pathlib.Path) -> None:
    """THE STEP A PORT WOULD SILENTLY DROP. An annotated tag's ref names a TAG object; without the extra lookup `production` would point at the annotation and `git show production` would print the message instead of the code. The only evidence is the call log and the sha in the message."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["v1.3.1"], FAKE_GH_REF_TYPE="tag")
    assert old.returncode == 0
    assert f"api\trepos/acme/widget/git/tags/{A40}\t--jq\t.object.sha" in old_calls
    assert f"-f\tsha={B40}" in "\n".join(old_calls), "the PATCH used the tag object's own sha"
    assert f"moved the 'production' tag to v1.3.1 ({B40})" in old.stderr
    _assert_agree(old, new, "annotated-tag", old_calls, new_calls)


def test_a_missing_production_ref_is_created_with_post(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["v1.3.1"], FAKE_GH_PROD_REF_RC="1")
    assert old.returncode == 0
    assert (
        "api\t--method\tPOST\trepos/acme/widget/git/refs\t-f\tref=refs/tags/production"
        f"\t-f\tsha={A40}" in old_calls
    )
    assert not any("PATCH" in c for c in old_calls)
    _assert_agree(old, new, "post-new-ref", old_calls, new_calls)


def test_the_existence_probes_output_is_swallowed(tmp_path: pathlib.Path) -> None:
    """`>/dev/null 2>&1` on the probe. The fake writes to both streams so a port that forgot one would be caught here rather than in production logs."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["v1.3.1"])
    assert "must never be seen" not in old.stdout + old.stderr
    assert "must never be seen" not in new.stdout + new.stderr
    _assert_agree(old, new, "probe-swallowed", old_calls, new_calls)


def test_a_failed_mutation_kills_the_run_before_the_moved_line(
    tmp_path: pathlib.Path,
) -> None:
    """`set -e` on an unguarded `gh api --method PATCH`: the script exits with gh's own status, gh's stderr reaches the caller because only stdout was redirected, and neither the "moved" line nor the `--latest` edit happens. A port that reported success here would leave the badge lying."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["v1.3.1"], FAKE_GH_MUTATE_RC="6")
    assert old.returncode == 6
    assert "gh: fake mutation failure" in old.stderr
    assert "moved the 'production' tag" not in old.stderr
    assert EDIT not in old_calls, "the badge was edited after the tag move failed"
    assert "mutation stdout that must never be seen" not in old.stdout
    _assert_agree(old, new, "mutation-fails", old_calls, new_calls)


def test_release_edit_writes_to_stdout_and_its_failure_is_fatal(
    tmp_path: pathlib.Path,
) -> None:
    """The ONE call with no redirection at all, so gh's confirmation URL is the only thing this script ever puts on stdout -- and a failure there exits
    with gh's status, without the final line."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["v1.3.1"], FAKE_GH_EDIT_RC="4")
    assert old.returncode == 4
    assert old.stdout == "https://github.com/acme/widget/releases/tag/v1.3.1\n"
    assert "marked v1.3.1 as the latest" not in old.stderr
    _assert_agree(old, new, "edit-fails", old_calls, new_calls)


def test_the_happy_path_prints_three_lines_and_makes_five_calls(
    tmp_path: pathlib.Path,
) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["v1.3.1"])
    assert old.returncode == 0
    assert old.stderr == (
        "✓ mark-production: v1.3.1 is a published release\n"
        f"✓ mark-production: moved the 'production' tag to v1.3.1 ({A40})\n"
        "✓ mark-production: marked v1.3.1 as the latest GitHub Release\n"
    )
    assert old.stdout == "https://github.com/acme/widget/releases/tag/v1.3.1\n"
    assert len(old_calls) == 6
    _assert_agree(old, new, "happy-path", old_calls, new_calls)


def test_a_failed_ref_lookup_is_reported_with_ghs_text(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["v1.3.1"], FAKE_GH_REF_RC="1")
    assert old.returncode == 1
    assert "could not resolve v1.3.1 to a commit: gh: fake ref lookup failure" in old.stderr
    _assert_agree(old, new, "ref-lookup-fails", old_calls, new_calls)


def test_a_failed_object_type_lookup_is_its_own_message(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["v1.3.1"], FAKE_GH_TYPE_RC="1")
    assert old.returncode == 1
    assert "could not resolve v1.3.1's object type" in old.stderr
    _assert_agree(old, new, "type-lookup-fails", old_calls, new_calls)


def test_a_failed_dereference_is_its_own_message(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["v1.3.1"], FAKE_GH_REF_TYPE="tag", FAKE_GH_DEREF_RC="1"
    )
    assert old.returncode == 1
    assert "could not dereference the annotated tag object for v1.3.1" in old.stderr
    assert not any("--method" in c for c in old_calls), "a ref was written from an unknown sha"
    _assert_agree(old, new, "deref-fails", old_calls, new_calls)


def _fixture_tree(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """Both subjects, copied into a tree with NO `.ci/scripts/lib/common.sh`.

    Each keeps its own depth from the root it derives (`../../..` for the twin's `.ci/scripts/release/`, `parents[3]` for the port's `.ci/rediacc_ci/release/`), so both compute the same missing library path.
    """
    fix = tmp_path / "fixture"
    twin_dir = fix / ".ci" / "scripts" / "release"
    port_dir = fix / ".ci" / "rediacc_ci" / "release"
    twin_dir.mkdir(parents=True, exist_ok=True)
    port_dir.mkdir(parents=True, exist_ok=True)
    twin_copy = twin_dir / TWIN.name
    port_copy = port_dir / PORT.name
    shutil.copy2(TWIN, twin_copy)
    shutil.copy2(PORT, port_copy)
    assert not (fix / ".ci" / "scripts" / "lib" / "common.sh").exists()
    return twin_copy, port_copy


def test_the_fallback_logger_world_puts_info_on_stdout_without_a_glyph(
    tmp_path: pathlib.Path,
) -> None:
    """THE BRANCH THAT ONLY EXISTS WHEN common.sh IS MISSING. `source ... ||
    { log_info() { echo "$*"; }; ... }` moves every info line to STDOUT and
    drops the glyph, and `log_error` keeps stderr but loses its `✗`. A port that implemented only the library path would be byte-identical in CI and wrong on exactly the machine the fallback was written for."""
    twin_copy, port_copy = _fixture_tree(tmp_path)
    old, old_calls = _run(twin_copy, tmp_path, ["v1.3.1"])
    new, new_calls = _run(port_copy, tmp_path, ["v1.3.1"])
    assert old.returncode == 0
    assert old.stdout == (
        "mark-production: v1.3.1 is a published release\n"
        f"mark-production: moved the 'production' tag to v1.3.1 ({A40})\n"
        "https://github.com/acme/widget/releases/tag/v1.3.1\n"
        "mark-production: marked v1.3.1 as the latest GitHub Release\n"
    )
    assert old.stderr == "", f"the fallback world wrote to stderr: {old.stderr!r}"
    assert "✓" not in old.stdout
    _assert_agree(old, new, "fallback-logger", old_calls, new_calls)


def test_the_fallback_world_error_path_also_agrees(tmp_path: pathlib.Path) -> None:
    twin_copy, port_copy = _fixture_tree(tmp_path)
    old, old_calls = _run(twin_copy, tmp_path, ["nope"])
    new, new_calls = _run(port_copy, tmp_path, ["nope"])
    assert old.returncode == 1
    assert old.stderr == "mark-production: 'vnope' is not strict semver (expected vX.Y.Z)\n"
    assert old.stdout == ""
    _assert_agree(old, new, "fallback-error", old_calls, new_calls)


def test_divergence_common_sh_interprets_backslash_escapes_in_gh_error_text(
    tmp_path: pathlib.Path,
) -> None:
    """A DELIBERATE DIVERGENCE, ASSERTED IN BOTH DIRECTIONS SO IT CANNOT BE
    "FIXED" BY ACCIDENT. common.sh's loggers use `echo -e`, which interprets backslash escapes IN THE MESSAGE, and this script interpolates gh's own output into that message. `rediacc_ci.log` formats the message as data (see its module docstring), so the twin turns a literal backslash-n in an API error into a newline and the port keeps the two characters. The FALLBACK world
    uses a bare `echo` and does NOT interpret, which is asserted here too: the divergence belongs to common.sh, not to the script."""
    err = "HTTP 500: boom\\nline two\n"
    old, new, _old_calls, _new_calls = run_both(
        tmp_path, ["v1.3.1"], FAKE_GH_VIEW_RC="1", FAKE_GH_VIEW_ERR=err
    )
    assert old.returncode == new.returncode == 1
    assert "boom\nline two" in old.stderr, "the twin no longer interprets escapes"
    assert "boom\\nline two" in new.stderr, "the port started interpreting escapes"
    assert old.stderr != new.stderr

    twin_copy, port_copy = _fixture_tree(tmp_path)
    f_old, _ = _run(twin_copy, tmp_path, ["v1.3.1"], FAKE_GH_VIEW_RC="1", FAKE_GH_VIEW_ERR=err)
    f_new, _ = _run(port_copy, tmp_path, ["v1.3.1"], FAKE_GH_VIEW_RC="1", FAKE_GH_VIEW_ERR=err)
    assert f_old.stderr == f_new.stderr, "the fallback world must NOT diverge"
    assert "boom\\nline two" in f_old.stderr


def test_pure_helpers() -> None:
    assert port.normalise_version("1.3.1") == "v1.3.1"
    assert port.normalise_version("v1.3.1") == "v1.3.1"
    assert port.normalise_version("vv1.3.1") == "vv1.3.1"
    assert port.is_semver("v1.3.1")
    assert not port.is_semver("vv1.3.1")
    assert not port.is_semver("v1.3.1-rc.1")
    assert not port.is_semver("v1.3")
    assert port.looks_missing("release not found")
    assert port.looks_missing("HTTP 404: Not Found (https://api.github.com/...)")
    assert not port.looks_missing("HTTP 403: Resource not accessible by integration")
    assert port.ref_path("a/b", "v1.0.0") == "repos/a/b/git/ref/tags/v1.0.0"
    assert port.tag_object_path("a/b", "abc") == "repos/a/b/git/tags/abc"
    assert port.production_ref_path("a/b") == "repos/a/b/git/refs/tags/production"
    assert port.refs_path("a/b") == "repos/a/b/git/refs"


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the annotated-tag dereference -- the one step whose omission changes nothing a reader would notice. The mutant skips it, so `production` would point at the tag ANNOTATION; the message text is the same shape, only the sha differs, and the call log loses one entry. Driven red, then the source is confirmed byte-identical and green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace('    if obj_type == "tag":', "    if False:")
    assert mutated != original, "the line this plant targets is no longer present verbatim"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")

    kw = {"FAKE_GH_REF_TYPE": "tag"}
    old, old_calls = _run(TWIN, tmp_path, ["v1.3.1"], **kw)
    bad, bad_calls = _run(mutant, tmp_path, ["v1.3.1"], **kw)
    assert any("/git/tags/" in c for c in old_calls), "the TWIN skipped the deref; plant untested"
    assert not any("/git/tags/" in c for c in bad_calls), "the mutant still dereferenced"
    assert bad.returncode == old.returncode, (
        "the plant is invisible in the exit code, which is why the call log is compared"
    )
    assert f"sha={A40}" in "\n".join(bad_calls), "the mutant wrote the annotation's own sha"

    good, good_calls = _run(PORT, tmp_path, ["v1.3.1"], **kw)
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert good.stderr == old.stderr
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
