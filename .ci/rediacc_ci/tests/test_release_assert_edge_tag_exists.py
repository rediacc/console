"""Differential: `rediacc_ci.release.assert_edge_tag_exists` against its twin
`.ci/scripts/release/assert-edge-tag-exists.sh`.

RECORDING FAKE `gh` AND `aws` ON A SCRATCH PATH, the seam every port in this box uses. Nothing here reaches GitHub or R2. That matters more than usual: this machine has a logged-in `gh`, and the twin's very first probe is `gh api repos/<repo>/git/ref/tags/<tag>` against whatever `$GITHUB_REPOSITORY`
names. Every case pins `GITHUB_REPOSITORY=acme/widget` and a fake endpoint as
well, so even a leak would not name the real repository or a real bucket.

THE CALL LOG IS COMPARED, NOT JUST THE STREAMS, because the observable question is WHICH oracles were consulted. Three independent probes that all run even after one has failed is the design (`judge ... || true`), and a port that short-circuited on the first failure would print a plausible subset of the same lines. Only the call log shows it.

BOTH ANTI-VACUITY DIRECTIONS ARE DRIVEN. `absent` (a real 404) and `unknown:` (a 403, a 5xx, `NoCredentials`) exit 1 with DIFFERENT advice, and the whole script exists to keep them apart -- `test_a_403_...` and `test_a_404_...` assert that the two remediation blocks are not interchangeable.

THE SILENT-EXIT DEFECT IS PINNED, NOT PAPERED OVER.
`test_defect_bare_version_flag_exits_1_in_total_silence` drives the twin with a bare `--version` and asserts zero bytes on both streams with exit 1, then asserts the port agrees. If someone repairs the twin, this test goes red and names the port that must follow.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.release import assert_edge_tag_exists as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "release" / "assert-edge-tag-exists.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "release" / "assert_edge_tag_exists.py"
BASH = shutil.which("bash") or "/bin/bash"

FAKE_GH = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("gh\\t" + "\\t".join(argv) + "\\n")

if argv[:1] == ["api"]:
    rc = int(os.environ.get("FAKE_GH_API_RC", "0"))
    if rc:
        sys.stderr.write(os.environ.get("FAKE_GH_API_ERR", "gh: Not Found (HTTP 404)\\n"))
        sys.exit(rc)
    sys.stdout.write('{"ref":"refs/tags/x"}\\n')
    sys.exit(0)

if argv[:2] == ["release", "view"]:
    rc = int(os.environ.get("FAKE_GH_REL_RC", "0"))
    if rc:
        sys.stderr.write(os.environ.get("FAKE_GH_REL_ERR", "release not found\\n"))
        sys.exit(rc)
    sys.stdout.write('{"tagName":"%s"}\\n' % argv[2])
    sys.exit(0)

sys.stderr.write("fake gh: unrouted call\\n")
sys.exit(90)
"""

FAKE_AWS = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("aws\\t" + "\\t".join(argv) + "\\n")

rc = int(os.environ.get("FAKE_AWS_RC", "0"))
if rc:
    sys.stderr.write(
        os.environ.get(
            "FAKE_AWS_ERR",
            "An error occurred (404) when calling the HeadObject operation: Not Found\\n",
        )
    )
    sys.exit(rc)
sys.stdout.write('{"ContentLength": 0}\\n')
sys.exit(0)
"""

# common.sh needs `dirname` and `uname` at source time; the twin itself uses
# `dirname`, `tr` and `sed` (in `one_line`) and `grep` in every probe. All five must be reachable from the stub PATH or the twin fails for a reason that has nothing to do with the subject.
PATH_MINIMUM = ("dirname", "uname", "tr", "sed", "grep")


def _bin(tmp_path: pathlib.Path, name: str, *, tools: bool = True) -> str:
    stub = tmp_path / name
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    for tool, body in (("gh", FAKE_GH), ("aws", FAKE_AWS)):
        target = stub / tool
        if tools:
            target.write_text(body, encoding="utf-8")
            target.chmod(0o755)
        else:
            assert shutil.which(tool, path=str(stub)) is None, f"{tool} leaked into the stub PATH"
    return str(stub)


def _run(
    subject: pathlib.Path,
    tmp_path: pathlib.Path,
    args: list[str],
    *,
    tools: bool = True,
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    side = "old" if subject.suffix == ".sh" else "new"
    call_log = tmp_path / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tmp_path, f"{side}-bin", tools=tools),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        # NEVER the real repository or a real bucket, even if a fake were bypassed.
        "GITHUB_REPOSITORY": "acme/widget",
        "RELEASES_BUCKET": "widget-releases",
        "CLOUDFLARE_R2_ENDPOINT": "https://r2.invalid",
        "CLOUDFLARE_R2_ACCESS_KEY_ID": "AKIAFIXTURE",
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "SECRETFIXTURE",
    }
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)
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


def run_both(tmp_path: pathlib.Path, args: list[str], **kw):
    old, old_calls = _run(TWIN, tmp_path, args, **kw)
    new, new_calls = _run(PORT, tmp_path, args, **kw)
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
            f"{label}: call sequence diverged:\nold: {old_calls}\nnew: {new_calls}"
        )


TAG_PROBE = "gh\tapi\trepos/acme/widget/git/ref/tags/v1.3.0"
REL_PROBE = "gh\trelease\tview\tv1.3.0\t--json\ttagName"
R2_PROBE = (
    "aws\ts3api\thead-object\t--bucket\twidget-releases"
    "\t--key\tcli/v1.3.0/.released\t--endpoint-url\thttps://r2.invalid"
)
ALL_THREE = [TAG_PROBE, REL_PROBE, R2_PROBE]


def test_the_happy_path_consults_all_three_oracles(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--version", "1.3.0"])
    assert old.returncode == 0
    assert old_calls == ALL_THREE, "an oracle was skipped on the happy path"
    assert old.stderr == (
        "→ Asserting v1.3.0 really exists before any promotion write\n"
        "✓ OK      git tag v1.3.0 (acme/widget)\n"
        "✓ OK      GitHub Release v1.3.0\n"
        "✓ OK      R2 sentinel s3://widget-releases/cli/v1.3.0/.released\n"
        "✓ All three exist: git tag, GitHub Release, and R2 sentinel for v1.3.0.\n"
    )
    assert old.stdout == "", "this script must never put anything on stdout"
    _assert_agree(old, new, "happy-path", old_calls, new_calls)


def test_a_bare_positional_version_works_and_the_v_is_stripped(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["v1.3.0"])
    assert old.returncode == 0
    assert old_calls == ALL_THREE
    _assert_agree(old, new, "positional-v", old_calls, new_calls)


def test_a_prerelease_suffix_is_accepted_here_unlike_its_siblings(
    tmp_path: pathlib.Path,
) -> None:
    """The pattern is `[0-9]+\\.[0-9]+\\.[0-9]+([-+][0-9A-Za-z.-]+)?`, LOOSER than
    the strict semver `mark-production.sh` demands. The question this script asks
    is whether the version EXISTS, not whether it is promotable."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--version", "1.3.0-rc.1"])
    assert old.returncode == 0
    assert any("v1.3.0-rc.1" in c for c in old_calls)
    _assert_agree(old, new, "prerelease", old_calls, new_calls)


def test_a_double_v_is_not_stripped_twice_and_is_refused(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["vv1.3.0"])
    assert old.returncode == 1
    assert old.stderr == ("✗ assert-edge-tag-exists.sh: 'v1.3.0' is not a semver version\n")
    assert old_calls == [], "a malformed version still reached an oracle"
    _assert_agree(old, new, "double-v", old_calls, new_calls)


def test_no_version_is_refused_before_any_probe(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, [])
    assert old.returncode == 1
    assert old.stderr == ("✗ assert-edge-tag-exists.sh: a version is required (--version 1.3.0)\n")
    assert old_calls == []
    _assert_agree(old, new, "no-version", old_calls, new_calls)


def test_an_unknown_option_is_refused(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["-x"])
    assert old.returncode == 1
    assert old.stderr == "✗ assert-edge-tag-exists.sh: unknown option: -x\n"
    _assert_agree(old, new, "unknown-option", old_calls, new_calls)


def test_the_equals_form_of_version_is_not_supported(tmp_path: pathlib.Path) -> None:
    """`--version=1.3.0` falls through to the `-*` arm. Reproduced rather than
    accepted: a port that "helpfully" understood it would promote on an input
    the live script rejects."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--version=1.3.0"])
    assert old.returncode == 1
    assert "unknown option: --version=1.3.0" in old.stderr
    assert old_calls == []
    _assert_agree(old, new, "equals-form", old_calls, new_calls)


def test_missing_gh_is_refused_before_missing_aws(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["1.3.0"], tools=False)
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'gh' is not available\n"
    assert "aws" not in old.stderr, "the order of the two require_cmd calls changed"
    _assert_agree(old, new, "missing-gh", old_calls, new_calls)


def test_a_404_on_every_oracle_names_all_three_and_gives_release_advice(
    tmp_path: pathlib.Path,
) -> None:
    """PROVABLE ABSENCE. All three probes still run -- the failure of the first
    does not stop the second -- and the remediation block is the "cut the
    release, then seal it" one, NOT the could-not-tell one."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["1.3.0"],
        FAKE_GH_API_RC="1",
        FAKE_GH_REL_RC="1",
        FAKE_AWS_RC="255",
    )
    assert old.returncode == 1
    assert old_calls == ALL_THREE, "a failed probe short-circuited the rest"
    assert old.stderr.count("MISSING ") == 3
    assert "COULD NOT TELL" not in old.stderr
    assert "Remediate first: cut the release for v1.3.0" in old.stderr
    assert "did not run" not in old.stderr
    _assert_agree(old, new, "all-absent", old_calls, new_calls)


def test_a_403_is_could_not_tell_and_gets_the_opposite_advice(
    tmp_path: pathlib.Path,
) -> None:
    """THE POINT OF THE WHOLE SCRIPT. A probe that could not run must not be
    filed as an absence: the advice for an absence is "cut the release and backfill the sentinel", and giving that to an operator whose release is fine
    is what the twin's own comment records as having cost real cycles."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["1.3.0"],
        FAKE_GH_API_RC="1",
        FAKE_GH_API_ERR="gh: HTTP 403: Resource not accessible by integration\n",
    )
    assert old.returncode == 1
    assert "COULD NOT TELL git tag v1.3.0 (acme/widget)" in old.stderr
    assert "At least one probe COULD NOT REACH A VERDICT" in old.stderr
    assert "Remediate first" not in old.stderr
    assert "MISSING " not in old.stderr
    # The other two oracles still answered, and their OK lines are still there.
    assert old.stderr.count("✓ OK      ") == 2
    _assert_agree(old, new, "403-could-not-tell", old_calls, new_calls)


def test_nocredentials_from_aws_gets_the_aws_specific_hint(tmp_path: pathlib.Path) -> None:
    """The line naming CLOUDFLARE_R2_ACCESS_KEY_ID exists because this exact
    failure broke promote-stable for 7 consecutive runs from 2026-08-27."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["1.3.0"],
        FAKE_AWS_RC="253",
        FAKE_AWS_ERR="Unable to locate credentials\n",
    )
    assert old.returncode == 1
    assert "'NoCredentials' means the aws CLI got no AWS_ACCESS_KEY_ID" in old.stderr
    _assert_agree(old, new, "nocredentials", old_calls, new_calls)


def test_the_could_not_tell_detail_keeps_its_trailing_space(tmp_path: pathlib.Path) -> None:
    """`one_line`'s here-string appends a newline that becomes a SPACE, and
    nothing later removes it. Asserted on the raw bytes because it is exactly
    the kind of thing a port tidies away without noticing."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["1.3.0"],
        FAKE_GH_API_RC="1",
        FAKE_GH_API_ERR="HTTP 500: boom\n",
    )
    assert "verdict: HTTP 500: boom \n" in old.stderr, "the twin lost its trailing space"
    _assert_agree(old, new, "trailing-space", old_calls, new_calls)


def test_a_multiline_probe_error_is_folded_onto_one_line(tmp_path: pathlib.Path) -> None:
    """`tr '\\n' ' ' | sed 's/  */ /g'`: newlines become spaces and runs of
    spaces collapse, so a multi-line API error cannot break the one-finding-per-
    line shape the caller's log reader depends on."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["1.3.0"],
        FAKE_GH_REL_RC="1",
        FAKE_GH_REL_ERR="gh: something broke\n   indented detail\n\n\ntail\n",
    )
    assert old.returncode == 1
    assert "verdict: gh: something broke indented detail tail \n" in old.stderr
    # One probe line, plus the summary's "see COULD NOT TELL above" back-reference.
    assert old.stderr.count("✗ COULD NOT TELL ") == 1
    _assert_agree(old, new, "multiline-fold", old_calls, new_calls)


def test_an_empty_probe_error_still_takes_the_could_not_tell_arm(
    tmp_path: pathlib.Path,
) -> None:
    """A tool that fails with NOTHING on either stream is the worst input for a
    classifier, and it must still be an unknown rather than an absence."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["1.3.0"], FAKE_AWS_RC="7", FAKE_AWS_ERR="")
    assert old.returncode == 1
    assert "COULD NOT TELL R2 sentinel" in old.stderr
    _assert_agree(old, new, "empty-error", old_calls, new_calls)


def test_a_release_not_found_message_is_an_absence_not_an_unknown(
    tmp_path: pathlib.Path,
) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["1.3.0"], FAKE_GH_REL_RC="1", FAKE_GH_REL_ERR="release not found\n"
    )
    assert old.returncode == 1
    assert "MISSING GitHub Release v1.3.0" in old.stderr
    assert "COULD NOT TELL" not in old.stderr
    _assert_agree(old, new, "release-not-found", old_calls, new_calls)


def test_nosuchkey_from_r2_is_an_absence(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["1.3.0"], FAKE_AWS_RC="255", FAKE_AWS_ERR="NoSuchKey: the key does not exist\n"
    )
    assert old.returncode == 1
    assert "MISSING R2 sentinel" in old.stderr
    _assert_agree(old, new, "nosuchkey", old_calls, new_calls)


def test_a_mixture_of_absent_and_unknown_takes_the_could_not_tell_advice(
    tmp_path: pathlib.Path,
) -> None:
    """When BOTH states are present the could-not-tell block wins, because an
    unknown means nothing can be concluded about the release at all -- so the "cut the release" advice would be unsound even though something really is
    missing."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["1.3.0"],
        FAKE_GH_API_RC="1",
        FAKE_GH_REL_RC="1",
        FAKE_GH_REL_ERR="HTTP 502: bad gateway\n",
    )
    assert old.returncode == 1
    assert "MISSING git tag" in old.stderr
    assert "COULD NOT TELL GitHub Release" in old.stderr
    assert "At least one probe COULD NOT REACH A VERDICT" in old.stderr
    assert "Remediate first" not in old.stderr
    _assert_agree(old, new, "mixed", old_calls, new_calls)


def test_the_defaults_for_repo_and_bucket_are_used_when_unset(
    tmp_path: pathlib.Path,
) -> None:
    """`${GITHUB_REPOSITORY:-rediacc/console}` / `${RELEASES_BUCKET:-rediacc-releases}`.
    Only the call log shows which names were used; the OK lines carry them too."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["1.3.0"], drop_env=("GITHUB_REPOSITORY", "RELEASES_BUCKET")
    )
    assert old.returncode == 0
    assert "gh\tapi\trepos/rediacc/console/git/ref/tags/v1.3.0" in old_calls
    assert any("--bucket\trediacc-releases" in c for c in old_calls)
    _assert_agree(old, new, "defaults", old_calls, new_calls)


def test_an_empty_repo_variable_falls_back_to_the_default(tmp_path: pathlib.Path) -> None:
    """`:-` fires on unset OR EMPTY, which is a different rule from `-` and the
    one an exported-but-blank workflow input actually hits."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["1.3.0"], GITHUB_REPOSITORY="")
    assert "gh\tapi\trepos/rediacc/console/git/ref/tags/v1.3.0" in old_calls
    _assert_agree(old, new, "empty-repo", old_calls, new_calls)


def test_the_r2_credentials_are_bridged_into_the_aws_names(tmp_path: pathlib.Path) -> None:
    """:90-91. The aws CLI reads AWS_*; the workflow passes CLOUDFLARE_R2_*.
    The fake asserts the bridge from inside the child process, which is the only
    place it is observable."""
    probe = tmp_path / "probe-bin"
    probe.mkdir()
    for name in PATH_MINIMUM:
        real = shutil.which(name)
        assert real is not None
        (probe / name).symlink_to(real)
    (probe / "gh").write_text(FAKE_GH, encoding="utf-8")
    (probe / "gh").chmod(0o755)
    (probe / "aws").write_text(
        "#!/usr/bin/python3\n"
        "import os, sys\n"
        "open(os.environ['FAKE_CALL_LOG'], 'a').write(\n"
        "    'aws-creds\\t%s\\t%s\\n' % (os.environ.get('AWS_ACCESS_KEY_ID', '<unset>'),\n"
        "                                os.environ.get('AWS_SECRET_ACCESS_KEY', '<unset>')))\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    (probe / "aws").chmod(0o755)

    def drive(subject):
        log_file = tmp_path / f"{subject.suffix}-creds.log"
        log_file.write_text("", encoding="utf-8")
        env = {
            "PATH": str(probe),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LC_ALL": "C",
            "PYTHONPATH": str(ROOT / ".ci"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "FAKE_CALL_LOG": str(log_file),
            "GITHUB_REPOSITORY": "acme/widget",
            "CLOUDFLARE_R2_ENDPOINT": "https://r2.invalid",
            "CLOUDFLARE_R2_ACCESS_KEY_ID": "AK-BRIDGED",
            "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "SK-BRIDGED",
        }
        runner = BASH if subject.suffix == ".sh" else sys.executable
        subprocess.run(
            [runner, str(subject), "1.3.0"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=60,
        )
        return log_file.read_text(encoding="utf-8")

    assert "aws-creds\tAK-BRIDGED\tSK-BRIDGED\n" in drive(TWIN)
    assert "aws-creds\tAK-BRIDGED\tSK-BRIDGED\n" in drive(PORT)


def test_each_required_credential_is_demanded_in_order(tmp_path: pathlib.Path) -> None:
    """DIVERGENCE 1 IS ASSERTED, NOT ASSUMED. `${VAR:?msg}` is a bash diagnostic
    carrying the twin's path and line number; the port names itself instead.
    What must agree is the STREAM, the EXIT CODE, the ORDER (only the first
    missing variable is named) and the fact that no oracle was consulted."""
    for name in port.REQUIRED_ENV:
        old, old_calls = _run(TWIN, tmp_path, ["1.3.0"], drop_env=(name,))
        new, new_calls = _run(PORT, tmp_path, ["1.3.0"], drop_env=(name,))
        assert old.returncode == 1 == new.returncode, name
        assert old.stdout == "" == new.stdout, name
        assert name in old.stderr, name
        assert name in new.stderr, name
        assert "must be set" in old.stderr, name
        assert "must be set" in new.stderr, name
        assert old_calls == [] == new_calls, f"{name}: an oracle ran without credentials"
        assert new.stderr.startswith("assert-edge-tag-exists.py: "), (
            f"{name}: the port stopped naming itself"
        )
        assert "line 8" in old.stderr, (
            f"{name}: the twin no longer emits a bash line-numbered diagnostic; "
            "divergence 1 in the port's docstring needs re-checking"
        )


def test_help_goes_to_stdout_with_exit_0(tmp_path: pathlib.Path) -> None:
    """DIVERGENCE 2: the line interpolates `$0`, so only the tail can match."""
    tail = " --version VERSION      (VERSION may be 1.3.0 or v1.3.0)\n"
    for flag in ("-h", "--help"):
        old, old_calls = _run(TWIN, tmp_path, [flag])
        new, new_calls = _run(PORT, tmp_path, [flag])
        assert old.returncode == 0 == new.returncode, flag
        assert old.stderr == "" == new.stderr, flag
        assert old.stdout.endswith(tail), flag
        assert new.stdout.endswith(tail), flag
        assert old.stdout.startswith("Usage: "), flag
        assert new.stdout.startswith("Usage: "), flag
        assert old_calls == [] == new_calls, flag


def test_defect_bare_version_flag_exits_1_in_total_silence(tmp_path: pathlib.Path) -> None:
    """THE DEFECT, PINNED IN BOTH DIRECTIONS. `--version` with no value hits
    `shift 2` with one argument left; `set -e` (inherited from common.sh:11,
    which this script sources despite its own `set -uo pipefail`) kills the run before the `if [[ -z "$VERSION" ]]` written to handle exactly this case.

    Zero bytes on both streams with exit 1 is indistinguishable from a probe genuinely refusing to promote, on a script whose whole purpose is to be a LOUD no-op. Reproduced because the acceptance rule for this wave is
    agreement with the live twin; if someone repairs the twin, this test goes
    red and names the port that must follow.
    """
    old, new, old_calls, new_calls = run_both(tmp_path, ["--version"])
    assert old.returncode == 1
    assert old.stdout == "", f"the twin now prints something: {old.stdout!r}"
    assert old.stderr == "", f"the twin now prints something: {old.stderr!r}"
    assert old_calls == []
    assert port.SHIFT2_UNDERFLOW_IS_SILENT_EXIT_1
    _assert_agree(old, new, "shift2-underflow", old_calls, new_calls)


def test_an_empty_version_value_reaches_the_required_message(tmp_path: pathlib.Path) -> None:
    """`--version ''` has TWO tokens, so `shift 2` succeeds and the empty value
    reaches the guard. This is the case the silent branch above should have
    been, and driving both shows they are genuinely different code paths."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--version", ""])
    assert old.returncode == 1
    assert "a version is required" in old.stderr
    _assert_agree(old, new, "empty-version-value", old_calls, new_calls)


def test_the_last_positional_wins(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["1.0.0", "2.0.0"])
    assert old.returncode == 0
    assert any("v2.0.0" in c for c in old_calls)
    assert not any("v1.0.0" in c for c in old_calls)
    _assert_agree(old, new, "last-positional", old_calls, new_calls)


def test_divergence_common_sh_interprets_backslash_escapes_in_probe_text(
    tmp_path: pathlib.Path,
) -> None:
    """A DELIBERATE DIVERGENCE, ASSERTED IN BOTH DIRECTIONS SO IT CANNOT BE
    "FIXED" BY ACCIDENT. common.sh's loggers use `echo -e`, which interprets backslash escapes IN THE MESSAGE, and the COULD NOT TELL line interpolates the probe's own output into that message. `rediacc_ci.log` formats the message as data (see its module docstring), so a literal backslash-n in an API error becomes a newline through the twin and stays two characters here.
    """
    old, new, _oc, _nc = run_both(
        tmp_path,
        ["1.3.0"],
        FAKE_GH_API_RC="1",
        FAKE_GH_API_ERR="HTTP 500: boom\\nline two\n",
    )
    assert old.returncode == new.returncode == 1
    assert "boom\nline two" in old.stderr, "the twin no longer interprets escapes"
    assert "boom\\nline two" in new.stderr, "the port started interpreting escapes"
    assert old.stderr != new.stderr


def test_pure_helpers() -> None:
    # `one_line` always ends in exactly one space, including on empty input.
    assert port.one_line("") == " "
    assert port.one_line("a") == "a "
    assert port.one_line("a\nb") == "a b "
    assert port.one_line("a   b") == "a b "
    assert port.one_line("a\n\n\nb") == "a b "
    assert port.unknown("boom") == "unknown:boom "
    assert port.is_unknown(port.unknown("x"))
    assert not port.is_unknown(port.PRESENT)
    assert not port.is_unknown(port.ABSENT)
    assert port.VERSION_RE.match("1.3.0")
    assert port.VERSION_RE.match("1.3.0-rc.1")
    assert port.VERSION_RE.match("1.3.0+build.7")
    assert not port.VERSION_RE.match("v1.3.0")
    assert not port.VERSION_RE.match("1.3")
    assert port.GH_API_ABSENT.search("gh: Not Found (HTTP 404)")
    assert not port.GH_API_ABSENT.search("HTTP 403: Resource not accessible")
    assert port.R2_ABSENT.search("An error occurred (404) when calling HeadObject")
    assert port.R2_ABSENT.search("NoSuchKey")
    assert not port.R2_ABSENT.search("Unable to locate credentials")


def test_judge_counts_the_two_states_separately() -> None:
    """`FAILED` and `COULD_NOT_TELL` are two counters because they need OPPOSITE
    advice. Driven directly so the branch is provable without a subprocess."""
    v = port.Verdicts()
    assert v.judge("thing", port.PRESENT) is True
    assert not v.failed
    assert not v.could_not_tell

    v = port.Verdicts()
    assert v.judge("thing", port.ABSENT) is False
    assert v.failed
    assert not v.could_not_tell

    v = port.Verdicts()
    assert v.judge("thing", port.unknown("boom")) is False
    assert v.failed
    assert v.could_not_tell

    # The unreachable arm still refuses rather than passing.
    v = port.Verdicts()
    assert v.judge("thing", "nonsense") is False
    assert v.failed
    assert not v.could_not_tell


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the one thing whose omission a reader would not
    notice: the `unknown` arm classified as a pass. That is exactly the "a check that did not run reads as a green" failure this script exists to prevent, and the mutant's exit code changes from 1 to 0 while two of its three OK lines stay identical. Driven red, then the source is confirmed byte-identical and green.
    """
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        "        if is_unknown(state):\n", "        if is_unknown(state) and False:\n"
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")

    kw = {
        "FAKE_GH_API_RC": "1",
        "FAKE_GH_API_ERR": "gh: HTTP 403: Resource not accessible by integration\n",
    }
    old, old_calls = _run(TWIN, tmp_path, ["1.3.0"], **kw)
    bad, _bad_calls = _run(mutant, tmp_path, ["1.3.0"], **kw)
    assert old.returncode == 1, "the TWIN did not refuse; the plant is untested"
    assert "COULD NOT TELL" in old.stderr
    assert bad.stderr != old.stderr, "the mutant is indistinguishable from the port"
    assert "COULD NOT TELL" not in bad.stderr, "the mutant still reached the unknown arm"

    good, good_calls = _run(PORT, tmp_path, ["1.3.0"], **kw)
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert good.stderr == old.stderr
    assert good.returncode == old.returncode
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
