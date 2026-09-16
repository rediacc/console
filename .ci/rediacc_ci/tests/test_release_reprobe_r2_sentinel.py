"""Differential: `rediacc_ci.release.reprobe_r2_sentinel` against its twin
`.ci/scripts/release/reprobe-r2-sentinel.sh`.

BOTH SIDES RUN IN THE REAL CHECKOUT, unlike the fixture-tree siblings in this
directory, and that is safe here for one reason: this script resolves nothing
relative to the repo root and writes nothing. Its entire observable is one
`aws s3api head-object` call, and the only thing that has to be faked is `aws`.
It is faked on a scratch PATH whose shadowing is PROVEN by
`test_the_fake_aws_shadows_any_real_one` rather than assumed, because the whole
point of the fake is that no real R2 endpoint is ever contacted.

THE FAKE ECHOES ITS OWN ARGV into a call log, and the call log is compared as
strictly as the streams are. Two implementations can print identical text while
probing different buckets, keys or endpoints, and stdout here is one line long,
so the streams alone are a weak claim. The same log is what the K=5 shadow
ledger (`.ci/shadow/w7p6-reprobe-r2-sentinel.observations.jsonl`) turns into
comparable findings: `shadow-gate.ts` classifies `✓ `-led lines as CHATTER
before any `--finding-re` sees them, and the success path prints nothing else,
so without a `call: ` line on stdout every row would read VACUOUS_BOTH_EMPTY.

THE THREE PROBE OUTCOMES ARE ALL DRIVEN, because the twin's two-way `if` folds
three of them: sealed (`aws` exits 0), genuinely absent (a 404 in stderr) and
COULD-NOT-TELL (any other failure, e.g. bad credentials). The last one is the
interesting case and the one place the two sides are not byte-identical, for a
reason that belongs to neither: see `test_unknown_probe_diverges_only_by_the_
log_error_marker` below.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.release import reprobe_r2_sentinel as port
from rediacc_ci.tests import pathmask

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "release" / "reprobe-r2-sentinel.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "release" / "reprobe_r2_sentinel.py"
BASH = shutil.which("bash") or "/bin/bash"

# `FAKE_AWS_MODE` selects which of the three probe outcomes the fake produces.
# The 404 wording is the real one an S3-compatible endpoint returns for a
# missing key, because the library decides "absent" by TEXT MATCH on stderr
# (`404|Not Found|NoSuchKey`) -- the aws CLI returns 254 for a 404 and for an
# auth failure alike, so the exit code cannot separate them.
FAKE_AWS = """#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write("call: aws " + " ".join(sys.argv[1:]) + "\\n")

mode = os.environ.get("FAKE_AWS_MODE", "present")
if mode == "present":
    sys.stdout.write('{"ContentLength": 42}\\n')
    sys.exit(0)
if mode == "absent":
    sys.stderr.write(
        "An error occurred (404) when calling the HeadObject operation: Not Found\\n"
    )
    sys.exit(254)
sys.stderr.write(
    "An error occurred (InvalidAccessKeyId) when calling the HeadObject "
    "operation: The Access Key Id you provided does not exist in our records.\\n"
)
sys.exit(254)
"""

# Credentials that cannot work anywhere. Spelled out here rather than reused
# from another module so a reader can see at a glance that nothing real is in
# play; the endpoint is an RFC 6761 name that can never resolve.
FAKE_R2 = {
    "CLOUDFLARE_R2_ACCESS_KEY_ID": "fake-access-key-id",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "fake-secret-access-key",
    "CLOUDFLARE_R2_ENDPOINT": "https://r2.example.invalid",
}


def _stub_path(tmp_path: pathlib.Path, side: str) -> str:
    """A PATH whose FIRST entry holds the fake `aws`, ahead of the real one."""
    stub = tmp_path / ("%s-bin" % side)
    stub.mkdir(parents=True, exist_ok=True)
    fake = stub / "aws"
    fake.write_text(FAKE_AWS, encoding="utf-8")
    fake.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def _run(
    tmp_path: pathlib.Path,
    side: str,
    *,
    mode: str = "present",
    **extra: str,
) -> tuple[int, str, str, list[str]]:
    call_log = tmp_path / ("%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    path = _stub_path(tmp_path, side)
    env = {
        "PATH": path,
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "LC_ALL": "C",
        "LANG": "C",
        # Both sides decide colour from the stream and from NO_COLOR; pinning it
        # removes a pty from the comparison without removing the marker
        # difference the UNKNOWN case exists to record.
        "NO_COLOR": "1",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_LOG": str(call_log),
        "FAKE_AWS_MODE": mode,
        **FAKE_R2,
    }
    env.update(extra)
    for key, value in list(env.items()):
        if value is None:
            del env[key]

    subject = TWIN if side == "old" else PORT
    runner = [BASH] if side == "old" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    return proc.returncode, proc.stdout, proc.stderr, calls


def run_both(tmp_path: pathlib.Path, **kw) -> tuple[tuple, tuple]:
    return _run(tmp_path, "old", **kw), _run(tmp_path, "new", **kw)


def _demark(text: str) -> str:
    """Drop `common.sh`'s `✗ ` error marker. See the UNKNOWN case for why."""
    return "\n".join(line.removeprefix("✗ ") for line in text.split("\n"))


def assert_agree(old: tuple, new: tuple, label: str) -> None:
    o_rc, o_out, o_err, o_calls = old
    n_rc, n_out, n_err, n_calls = new
    assert n_rc == o_rc, "%s: exit diverged: %d vs %d (old stderr %r, new stderr %r)" % (
        label,
        o_rc,
        n_rc,
        o_err,
        n_err,
    )
    assert n_out == o_out, "%s: stdout diverged:\nold: %r\nnew: %r" % (label, o_out, n_out)
    assert _demark(n_err) == _demark(o_err), "%s: stderr diverged:\nold: %r\nnew: %r" % (
        label,
        o_err,
        n_err,
    )
    assert n_calls == o_calls, "%s: call sequence diverged:\nold: %s\nnew: %s" % (
        label,
        o_calls,
        n_calls,
    )


# ---------------------------------------------------------------------------
# The controls on the harness
# ---------------------------------------------------------------------------


def test_the_fake_aws_shadows_any_real_one(tmp_path: pathlib.Path) -> None:
    """The control on the control: prove the stub SHADOWS, never merely exists."""
    path = _stub_path(tmp_path, "control")
    found = shutil.which("aws", path=path)
    assert found is not None, "the fake aws vanished from the stub PATH"
    assert found.startswith(str(tmp_path)), (
        "aws resolved to %s, which is outside the scratch stub; a real R2 call is reachable" % found
    )


def test_both_subjects_exist() -> None:
    assert TWIN.is_file(), "the bash twin moved: %s" % TWIN
    assert PORT.is_file(), "the port moved: %s" % PORT


# ---------------------------------------------------------------------------
# The three probe outcomes
# ---------------------------------------------------------------------------


def test_sealed_sentinel_reports_present_and_exits_zero(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, mode="present", VERSION="v1.1.2")
    assert old[0] == 0
    assert old[1] == "✓ cli/v1.1.2/.released present in R2\n"
    assert old[2] == ""
    assert old[3] == [
        (
            "call: aws s3api head-object --bucket rediacc-releases "
            "--key cli/v1.1.2/.released --endpoint-url https://r2.example.invalid"
        )
    ]
    assert_agree(old, new, "present")


def test_absent_sentinel_annotates_and_exits_one(tmp_path: pathlib.Path) -> None:
    """`::error::` lands on STDOUT, not stderr: the twin uses a plain `echo`."""
    old, new = run_both(tmp_path, mode="absent", VERSION="v1.1.2")
    assert old[0] == 1
    assert old[1] == "::error::cli/v1.1.2/.released NOT present after write\n"
    assert old[2] == ""
    assert_agree(old, new, "absent")


def test_unknown_probe_diverges_only_by_the_log_error_marker(tmp_path: pathlib.Path) -> None:
    """A credential failure is NOT a 404, and both sides say so before failing.

    THE ONE BYTE-LEVEL DIVERGENCE IN THIS PAIR, and it belongs to neither
    subject. The twin sources `common.sh`, whose `log_error` prefixes `✗ `;
    `rediacc_ci.core.release_state_validator._log_error` deliberately drops that
    marker (its own docstring says so, because it is a colour-conditional
    decoration the shared library has no stream to decide against). The finding
    TEXT, the indented aws stderr, the exit code and the call log are identical;
    only the two-byte marker differs, which `shadow-gate.ts` strips as a
    severity MARKER before comparing anyway.

    Asserted explicitly here rather than normalised away silently, so that the
    day someone gives the library its marker back this case says which half
    changed.
    """
    old, new = run_both(tmp_path, mode="unknown", VERSION="v1.1.2")
    assert old[0] == 1
    assert old[1] == "::error::cli/v1.1.2/.released NOT present after write\n"
    assert old[2].startswith(
        "✗ rsv_sentinel_exists: could not determine whether cli/v1.1.2/.released exists"
    )
    assert new[2].startswith(
        "rsv_sentinel_exists: could not determine whether cli/v1.1.2/.released exists"
    )
    assert not new[2].startswith("✗"), (
        "the library grew the ✗ marker; delete the _demark() normalisation and this case"
    )
    # The aws stderr is indented four spaces and echoed by both, which is the
    # half that tells an operator the probe failed on credentials.
    assert "    An error occurred (InvalidAccessKeyId)" in old[2]
    assert_agree(old, new, "unknown")


def test_the_version_reaches_the_probe_key(tmp_path: pathlib.Path) -> None:
    """A second version, so a hard-coded key in either side is visible."""
    old, new = run_both(tmp_path, mode="present", VERSION="v9.9.9")
    assert "--key cli/v9.9.9/.released" in old[3][0]
    assert_agree(old, new, "version-9.9.9")


def test_a_custom_bucket_is_honoured_by_both(tmp_path: pathlib.Path) -> None:
    """`RELEASES_BUCKET` is read at call time by both sides."""
    old, new = run_both(
        tmp_path, mode="present", VERSION="v1.1.2", RELEASES_BUCKET="scratch-bucket"
    )
    assert "--bucket scratch-bucket " in old[3][0]
    assert_agree(old, new, "custom-bucket")


# ---------------------------------------------------------------------------
# Refusals, before any probe
# ---------------------------------------------------------------------------


def test_missing_aws_refuses_identically(tmp_path: pathlib.Path) -> None:
    """`require_cmd aws` runs FIRST, before any variable is read.

    Byte-identical on both sides, marker included, because this message comes
    from `common.sh:log_error` on one side and `rediacc_ci.log.error` on the
    other and those two DO agree.

    THE REAL PATH, WITH THE STUB DIRECTORY REMOVED, rather than an empty one.
    An empty PATH does not test `require_cmd`: it kills the twin four lines
    earlier at `$(dirname "${BASH_SOURCE[0]}")` with `dirname: command not
    found`, which is what this case asserted on its first run and is a defect in
    the HARNESS rather than in either subject.

    AND WITH `aws` MASKED OUT OF IT. This used to read "`aws` genuinely is not
    installed here, which the premise below proves, so the real PATH is already
    the without-aws case" -- true of this tree's machines, false of a GitHub
    runner, which ships the CLI at /usr/local/bin/aws. On such a host the case
    was not exercising the `require_cmd` refusal it documents; it was running a
    real aws. Measured in CI run 34970782616. `pathmask` removes exactly that
    one command and keeps everything else the directory provided, so `dirname`
    and friends still resolve and the harness defect above stays fixed.
    """
    masked = pathmask.path_without("aws", tmp_path, base=os.environ.get("PATH", "/usr/bin:/bin"))
    pathmask.assert_absent("aws", masked)
    old, new = run_both(tmp_path, mode="present", VERSION="v1.1.2", PATH=masked)
    assert old[0] == 1
    assert old[2] == "✗ Required command 'aws' is not available\n"
    assert old[1] == ""
    assert new[0] == 1
    assert new[2] == old[2]
    assert new[1] == ""
    assert old[3] == []
    assert new[3] == []


def _refusal(tmp_path: pathlib.Path, missing: str) -> tuple[tuple, tuple]:
    kw = {"VERSION": "v1.1.2", **FAKE_R2, missing: None}
    return run_both(tmp_path, mode="present", **kw)


def test_missing_version_refuses_on_both_sides(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, mode="present", VERSION=None)
    assert old[0] == 1
    assert new[0] == 1
    assert "VERSION" in old[2]
    assert "must be set" in old[2]
    assert "VERSION" in new[2]
    assert "must be set" in new[2]
    assert old[3] == [], "a probe ran before the arguments were validated"
    assert new[3] == [], "a probe ran before the arguments were validated"


def test_missing_access_key_refuses_on_both_sides(tmp_path: pathlib.Path) -> None:
    old, new = _refusal(tmp_path, "CLOUDFLARE_R2_ACCESS_KEY_ID")
    assert old[0] == 1
    assert new[0] == 1
    assert "CLOUDFLARE_R2_ACCESS_KEY_ID" in old[2]
    assert "must be set" in old[2]
    assert "CLOUDFLARE_R2_ACCESS_KEY_ID" in new[2]
    assert "must be set" in new[2]
    assert old[3] == []
    assert new[3] == []


def test_missing_secret_key_refuses_on_both_sides(tmp_path: pathlib.Path) -> None:
    old, new = _refusal(tmp_path, "CLOUDFLARE_R2_SECRET_ACCESS_KEY")
    assert old[0] == 1
    assert new[0] == 1
    assert "CLOUDFLARE_R2_SECRET_ACCESS_KEY" in old[2]
    assert "must be set" in old[2]
    assert "CLOUDFLARE_R2_SECRET_ACCESS_KEY" in new[2]
    assert "must be set" in new[2]
    assert old[3] == []
    assert new[3] == []


def test_missing_endpoint_refuses_on_both_sides(tmp_path: pathlib.Path) -> None:
    old, new = _refusal(tmp_path, "CLOUDFLARE_R2_ENDPOINT")
    assert old[0] == 1
    assert new[0] == 1
    assert "CLOUDFLARE_R2_ENDPOINT" in old[2]
    assert "must be set" in old[2]
    assert "CLOUDFLARE_R2_ENDPOINT" in new[2]
    assert "must be set" in new[2]
    assert old[3] == []
    assert new[3] == []


def test_an_empty_variable_refuses_like_an_unset_one(tmp_path: pathlib.Path) -> None:
    """`${VAR:?}` is the colon form: empty refuses too. Easy to port wrong."""
    old, new = run_both(tmp_path, mode="present", VERSION="")
    assert old[0] == 1
    assert new[0] == 1
    assert "VERSION" in old[2]
    assert "VERSION" in new[2]
    assert old[3] == []
    assert new[3] == []


# ---------------------------------------------------------------------------
# The loop shape, which is the twin's documented BLOCKER
# ---------------------------------------------------------------------------


def test_the_product_list_is_still_one_element_on_both_sides() -> None:
    """`cli` is the only product with `.released` sentinels today.

    Pinned on BOTH sides, so adding a product to one and not the other is a
    red test rather than a silently half-probed release.
    """
    assert port.PRODUCTS == ("cli",)
    text = TWIN.read_text(encoding="utf-8")
    assert "for product in cli; do" in text, (
        "the twin's product loop changed; re-derive PRODUCTS in the port"
    )


def test_the_harness_actually_compared_something(tmp_path: pathlib.Path) -> None:
    """Anti-vacuity: a fake that never ran would make every case above pass."""
    old, new = run_both(tmp_path, mode="present", VERSION="v1.1.2")
    assert len(old[3]) == 1, "the twin made no aws call; the differential is vacuous"
    assert len(new[3]) == 1, "the port made no aws call; the differential is vacuous"
