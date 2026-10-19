"""Differential: `rediacc_ci.release.assert_r2_sentinel` against the bytes its twin `.ci/scripts/test/assert-r2-sentinel.sh` printed.

THE TWIN HAD NO DIFFERENTIAL, ONLY A K=5 SHADOW LEDGER, so this module is the golden-then-delete step for it (operator ruling D5, 2026-10-08, plan PLAN-retire-bash-oracles section 10, unit W7). Every case below ran the bash script under a recording fake `aws`; its exit code, both streams and the `aws` call sequence are in `goldens/twins/test.assert-r2-sentinel.jsonl`, and the port is held to them. The `.sh` is read only by a
`regolden --source bash` run.

THE BRANCHES. The skips (an empty channel, a non-release channel), the usage refusal (no version), the four environment refusals (`aws` missing, each of the three credentials), the healthy prefix, and the three unhealthy ones: sealed-but-empty, empty with no sentinel, and a probe that could not answer. The unanswerable COUNT is the case that matters most and is the quietest: the twin's `set -e` aborts inside the command substitution before it can print its own verdict, so the exit code is 1 and the `Versioned release prefix is not in a healthy sealed state.` line never appears. That is recorded, and the port reproduces it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import pathmask

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/test/assert-r2-sentinel.sh"
TWIN = ROOT / TWIN_REL

FAKE_AWS = """#!/bin/bash
printf '%s\\n' "$*" >>"$FAKE_AWS_LOG"
case "$1 $2" in
    "s3api head-object")
        if [[ -n "${HEAD_ERR:-}" ]]; then printf '%s\\n' "$HEAD_ERR" >&2; fi
        exit "${HEAD_RC:-0}"
        ;;
    "s3api list-objects-v2")
        if [[ -n "${LIST_ERR:-}" ]]; then printf '%s\\n' "$LIST_ERR" >&2; fi
        if [[ "${LIST_RC:-0}" == "0" ]]; then printf '%s\\n' "${LIST_OUT-0}"; fi
        exit "${LIST_RC:-0}"
        ;;
    *)
        exit 0
        ;;
esac
"""

NOT_FOUND = "An error occurred (404) when calling the HeadObject operation: Not Found"
CREDS = {
    "CLOUDFLARE_R2_ACCESS_KEY_ID": "key-fixture",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "secret-fixture",
    "CLOUDFLARE_R2_ENDPOINT": "https://r2.example.invalid",
}
# Everything the twin and the port reach for on PATH besides `aws`.
TOOLS = ("bash", "python3", "dirname", "uname", "mktemp", "rm", "sed", "grep", "cat", "env")

# name -> (argv, env overrides, drop env names, hide aws)
CASES: dict[str, tuple[list[str], dict[str, str], tuple[str, ...], bool]] = {
    "empty-channel": ([], {}, (), False),
    "empty-channel-with-a-version": (["", "1.2.3"], {}, (), False),
    "pr-channel-is-skipped": (["pr-5", "1.2.3"], {}, (), False),
    "no-version": (["edge"], {}, (), False),
    "no-aws": (["edge", "1.2.3"], {}, (), True),
    "no-access-key": (["edge", "1.2.3"], {}, ("CLOUDFLARE_R2_ACCESS_KEY_ID",), False),
    "no-secret-key": (["edge", "1.2.3"], {}, ("CLOUDFLARE_R2_SECRET_ACCESS_KEY",), False),
    "no-endpoint": (["edge", "1.2.3"], {}, ("CLOUDFLARE_R2_ENDPOINT",), False),
    "healthy-edge": (["edge", "1.2.3"], {"HEAD_RC": "0", "LIST_OUT": "16"}, (), False),
    "healthy-stable-without-a-sentinel": (
        ["stable", "1.2.3"],
        {"HEAD_RC": "254", "HEAD_ERR": NOT_FOUND, "LIST_OUT": "2"},
        (),
        False,
    ),
    "healthy-custom-bucket": (
        ["edge", "1.2.3"],
        {"RELEASES_BUCKET": "bucket-under-test", "HEAD_RC": "0", "LIST_OUT": "3"},
        (),
        False,
    ),
    "sealed-but-empty": (["edge", "1.2.3"], {"HEAD_RC": "0", "LIST_OUT": "0"}, (), False),
    "empty-and-no-sentinel": (
        ["edge", "1.2.3"],
        {"HEAD_RC": "254", "HEAD_ERR": NOT_FOUND, "LIST_OUT": "0"},
        (),
        False,
    ),
    "empty-and-the-sentinel-probe-cannot-answer": (
        ["edge", "1.2.3"],
        {"HEAD_RC": "255", "HEAD_ERR": "An error occurred (ExpiredToken)", "LIST_OUT": "None"},
        (),
        False,
    ),
    "count-cannot-be-obtained": (
        ["edge", "1.2.3"],
        {
            "HEAD_RC": "0",
            "LIST_RC": "255",
            "LIST_ERR": "An error occurred (AccessDenied) when calling the ListObjectsV2 operation",
        },
        (),
        False,
    ),
    "count-is-unparseable": (["edge", "1.2.3"], {"HEAD_RC": "0", "LIST_OUT": "abc"}, (), False),
}


def _env(scratch: pathlib.Path, extra: dict[str, str], drop: tuple[str, ...], hide_aws: bool):
    bindir = scratch / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    for tool in TOOLS:
        found = shutil.which(tool)
        assert found, "%s is missing from this machine" % tool
        if not (bindir / tool).exists():
            (bindir / tool).symlink_to(found)
    if not hide_aws:
        aws = bindir / "aws"
        aws.write_text(FAKE_AWS, encoding="utf-8")
        aws.chmod(0o755)
    log = scratch / "aws.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": str(bindir),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "TMPDIR": str(scratch),
        "FAKE_AWS_LOG": str(log),
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        **CREDS,
        **extra,
    }
    if hide_aws:
        env.update(pathmask.no_aws(scratch))
    for name in drop:
        env.pop(name, None)
    return env, log


def _run(command: list[str], env: dict[str, str]):
    return subprocess.run(
        command, capture_output=True, text=True, env=env, cwd=str(ROOT), check=False, timeout=60
    )


def _bash(scratch: pathlib.Path, argv, extra, drop, hide):
    env, log = _env(scratch, extra, drop, hide)
    proc = _run(["bash", str(TWIN), *argv], env)
    return proc.returncode, proc.stdout, proc.stderr, log


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_port_answers_what_the_bash_script_answered(tmp_path: pathlib.Path, name: str) -> None:
    argv, extra, drop, hide = CASES[name]
    held: dict[str, pathlib.Path] = {}

    def bash():
        rc, out, err, log = _bash(tmp_path / "bash", argv, extra, drop, hide)
        held["log"] = log
        return rc, out, err

    rc, out, err, frozen = diff.twin_run(
        TWIN_REL,
        [name, repr(argv), repr(sorted(extra.items())), repr(drop), repr(hide)],
        bash,
        extras={"calls": lambda: held["log"].read_text(encoding="utf-8")},
        work=(tmp_path,),
        label="assert-" + name,
    )
    env, log = _env(tmp_path / "port", extra, drop, hide)
    proc = _run(
        [sys.executable, "-m", "rediacc_ci.release.assert_r2_sentinel", *argv],
        env,
    )
    assert proc.returncode == rc, "exit: bash %d, port %d\n%s" % (rc, proc.returncode, proc.stderr)
    assert proc.stdout == out
    assert proc.stderr == err
    assert log.read_text(encoding="utf-8") == frozen["calls"]


def test_the_corpus_holds_both_verdicts_and_the_usage_exit() -> None:
    """ANTI-VACUITY: a corpus that only succeeds would agree with a port that never fails."""
    if diff.regolden_mode(TWIN_REL) is not None:
        pytest.skip("a regolden run is recording the golden this reads")
    codes = set()
    for name, (argv, extra, drop, hide) in CASES.items():
        key = diff.case_key(
            [name, repr(argv), repr(sorted(extra.items())), repr(drop), repr(hide)],
            work=(),
            label="assert-" + name,
        )
        codes.add(diff.golden_answer(TWIN_REL, key, ())[0])
    assert codes == {0, 1, 2}, codes
