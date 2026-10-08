"""Differential: `rediacc_ci.deploy.write_once_guard` against the bash `write_once_guard` it replaced.

THE GUARD'S TWIN IS `.ci/scripts/deploy/upload-to-r2.sh`, whose `write_once_guard` function was sourced (with the real `common.sh` and `release-state-validator.sh`) by the Python uploader and by `write_once_guard_check`. Operator ruling D5 (2026-10-08) ported it BEHIND GOLDENS FROZEN FROM THE BASH FIRST. Every case below ran the bash function under a recording fake `aws`; the answer (exit code, both streams, and the `aws` call sequence) is in
`goldens/twins/deploy.upload-to-r2.jsonl`, and this module holds the Python guard to it. The bash side is only read in a `regolden --source bash` run, which needs the `.sh` on disk.

WHY THE BRANCHES ARE THESE. The guard has five outcomes, and the v1.1.16/17 incident is the reason each is pinned separately:

  * SEALED with binaries (one, many) answers 10 and logs two lines.
  * SEALED and EMPTY answers `exit 1` with the five-line remediation. "Empty" is reached three ways that look alike and are not: a count of 0, the `None` spelling of an absent prefix, and a count that could not be obtained at all (an `aws` failure, an unparseable or blank answer). The last one is carried, not repaired; see the guard module's docstring.
  * NO SENTINEL (clean prefix, byte-only orphan) answers 0 and makes no further call. NEVER an `s3 rm`: the calls are compared, so a scrub shows.
  * A SENTINEL PROBE THAT CANNOT ANSWER (no message, an expired token) answers 0 after the validator's own error lines.
  * DRY RUN answers 0 whatever the state would be and makes no call at all.

Run in compare mode the `.sh` is never read: deleting it changes nothing.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import differential as diff

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/deploy/upload-to-r2.sh"
COMMON_REL = ".ci/scripts/lib/common.sh"
VALIDATOR_REL = ".ci/scripts/lib/release-state-validator.sh"

ENDPOINT = "https://r2.example.invalid"
SEALED_404 = "An error occurred (404) when calling the HeadObject operation: Not Found"

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

# name -> (prefix, context, extra env). HEAD_RC=0 is a sentinel that exists; 254 with a 404 message is one that is absent.
CASES: dict[str, tuple[str, str, dict[str, str]]] = {
    "sealed-with-binaries": ("cli/v1.2.3/", "cli v1.2.3", {"HEAD_RC": "0", "LIST_OUT": "16"}),
    "sealed-one-binary": ("cli/v1.2.3/", "cli v1.2.3", {"HEAD_RC": "0", "LIST_OUT": "1"}),
    "sealed-empty": ("cli/v1.2.3/", "cli v1.2.3", {"HEAD_RC": "0", "LIST_OUT": "0"}),
    "sealed-none-spelling": ("cli/v1.2.3/", "cli v1.2.3", {"HEAD_RC": "0", "LIST_OUT": "None"}),
    "sealed-count-unparseable": (
        "cli/v1.2.3/",
        "cli v1.2.3",
        {"HEAD_RC": "0", "LIST_OUT": "abc"},
    ),
    "sealed-count-blank": ("cli/v1.2.3/", "cli v1.2.3", {"HEAD_RC": "0", "LIST_OUT": ""}),
    "sealed-count-aws-failure": (
        "cli/v1.2.3/",
        "cli v1.2.3",
        {
            "HEAD_RC": "0",
            "LIST_RC": "255",
            "LIST_ERR": "An error occurred (AccessDenied) when calling the ListObjectsV2 operation",
        },
    ),
    "missing-clean": ("cli/v1.2.3/", "cli v1.2.3", {"HEAD_RC": "254", "HEAD_ERR": SEALED_404}),
    "missing-orphan-with-bytes": (
        "cli/v1.2.3/",
        "cli v1.2.3",
        {"HEAD_RC": "254", "HEAD_ERR": SEALED_404, "LIST_OUT": "9"},
    ),
    "missing-nosuchkey-lowercase": (
        "cli/v1.2.3/",
        "cli v1.2.3",
        {"HEAD_RC": "254", "HEAD_ERR": "an error occurred (nosuchkey): the key does not exist"},
    ),
    "probe-silent-failure": ("cli/v1.2.3/", "cli v1.2.3", {"HEAD_RC": "254"}),
    "probe-expired-token": (
        "cli/v1.2.3/",
        "cli v1.2.3",
        {
            "HEAD_RC": "255",
            "HEAD_ERR": "An error occurred (ExpiredToken) when calling the HeadObject operation:\nThe provided token has expired.",
        },
    ),
    "dry-run-clean": ("cli/v1.2.3/", "cli v1.2.3", {"DRY_RUN": "true", "HEAD_RC": "254"}),
    "dry-run-ignores-a-sealed-empty-prefix": (
        "cli/v1.2.3/",
        "cli v1.2.3",
        {"DRY_RUN": "true", "HEAD_RC": "0", "LIST_OUT": "0"},
    ),
    "custom-bucket-sealed": (
        "cli/v1.2.3/",
        "cli v1.2.3",
        {"RELEASES_BUCKET": "bucket-under-test", "HEAD_RC": "0", "LIST_OUT": "3"},
    ),
    "custom-bucket-sealed-empty": (
        "cli/v1.2.3/",
        "cli v1.2.3",
        {"RELEASES_BUCKET": "bucket-under-test", "HEAD_RC": "0", "LIST_OUT": "0"},
    ),
    "other-product-prefix": ("npm/v2.0.0/", "npm v2.0.0", {"HEAD_RC": "0", "LIST_OUT": "2"}),
    "prefix-without-trailing-slash": (
        "cli/v1.0.5",
        "cli v1.0.5",
        {"HEAD_RC": "254", "HEAD_ERR": SEALED_404},
    ),
    "prefix-without-any-slash": ("cli", "bare", {"HEAD_RC": "254", "HEAD_ERR": SEALED_404}),
}

BASE_ENV = {
    "RELEASES_BUCKET": "rediacc-releases",
    "CLOUDFLARE_R2_ENDPOINT": ENDPOINT,
    "DRY_RUN": "false",
    "LC_ALL": "C.UTF-8",
    "PYTHONDONTWRITEBYTECODE": "1",
}

PORT_DRIVER = (
    "import os, sys\n"
    "from rediacc_ci.deploy import write_once_guard as g\n"
    "try:\n"
    "    rc = g.write_once_guard(sys.argv[1], sys.argv[2], endpoint=os.environ['CLOUDFLARE_R2_ENDPOINT'],"
    " dry_run=os.environ['DRY_RUN'] == 'true')\n"
    "except g.SealedButEmptyError:\n"
    "    rc = 1\n"
    "raise SystemExit(rc)\n"
)

# `sed -n '/^write_once_guard()/,/^}/p'`: the definition line to the first column-zero brace.
_GUARD_RE = re.compile(r"^write_once_guard\(\).*?^\}\n", re.MULTILINE | re.DOTALL)


def _scene(scratch: pathlib.Path, extra: dict[str, str]) -> tuple[dict[str, str], pathlib.Path]:
    """A scratch dir holding the fake `aws` and a call log, and the environment for one run."""
    scratch.mkdir(parents=True, exist_ok=True)
    aws = scratch / "aws"
    aws.write_text(FAKE_AWS, encoding="utf-8")
    aws.chmod(0o755)
    log = scratch / "aws.log"
    log.write_text("", encoding="utf-8")
    env = {
        **BASE_ENV,
        "PATH": "%s:/usr/local/bin:/usr/bin:/bin" % scratch,
        "HOME": os.environ.get("HOME", "/tmp"),
        "TMPDIR": str(scratch),
        "FAKE_AWS_LOG": str(log),
        "PYTHONPATH": str(ROOT / ".ci"),
        **extra,
    }
    return env, log


def _run_bash(scratch: pathlib.Path, prefix: str, context: str, extra: dict[str, str]):
    """The bash function, sourced exactly as the uploader sourced it (`|| rc=$?`, so errexit is suppressed inside its body)."""
    env, log = _scene(scratch, extra)
    text = (ROOT / TWIN_REL).read_text(encoding="utf-8")
    match = _GUARD_RE.search(text)
    assert match, "write_once_guard() is no longer in %s" % TWIN_REL
    script = (
        "source '%s'\nsource '%s'\n%s\nrc=0\nwrite_once_guard \"$1\" \"$2\" || rc=$?\nexit $rc\n"
        % (
            ROOT / COMMON_REL,
            ROOT / VALIDATOR_REL,
            match.group(0),
        )
    )
    proc = subprocess.run(
        ["bash", "-c", script, "guard", prefix, context],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr, log


def _run_port(scratch: pathlib.Path, prefix: str, context: str, extra: dict[str, str]):
    env, log = _scene(scratch, extra)
    proc = subprocess.run(
        [sys.executable, "-c", PORT_DRIVER, prefix, context],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr, log


def _frozen(tmp_path: pathlib.Path, name: str):
    """The bash guard's answer for case `name`: from the golden, or from the live bash in a `regolden --source bash` run."""
    prefix, context, extra = CASES[name]
    holder: dict[str, pathlib.Path] = {}

    def bash():
        rc, out, err, log = _run_bash(tmp_path / "bash", prefix, context, extra)
        holder["log"] = log
        return rc, out, err

    rc, out, err, frozen = diff.twin_run(
        TWIN_REL,
        ["guard", name, prefix, context, repr(sorted(extra.items()))],
        bash,
        extras={"calls": lambda: holder["log"].read_text(encoding="utf-8")},
        work=(tmp_path,),
        label="guard-" + name,
    )
    return rc, out, err, frozen["calls"]


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_port_answers_what_the_bash_guard_answered(tmp_path: pathlib.Path, name: str) -> None:
    prefix, context, extra = CASES[name]
    rc, out, err, calls = _frozen(tmp_path, name)
    new_rc, new_out, new_err, log = _run_port(tmp_path / "port", prefix, context, extra)
    assert new_rc == rc, "exit: bash %d, port %d\n%s" % (rc, new_rc, new_err)
    assert new_out == out
    assert new_err == err
    assert log.read_text(encoding="utf-8") == calls


def _reading_goldens() -> None:
    """These two read the frozen file directly, which a recording run is still writing."""
    if diff.regolden_mode(TWIN_REL) is not None:
        pytest.skip("a regolden run is recording the golden these read")


def test_the_corpus_holds_every_outcome() -> None:
    """ANTI-VACUITY: a corpus of one outcome would agree with a guard that always answers it."""
    _reading_goldens()
    rcs = {
        name: diff.golden_answer(TWIN_REL, key, ())[0]
        for name, key in ((n, _key_for(n)) for n in CASES)
    }
    assert set(rcs.values()) == {0, 1, 10}, rcs


def _key_for(name: str) -> str:
    prefix, context, extra = CASES[name]
    return diff.case_key(
        ["guard", name, prefix, context, repr(sorted(extra.items()))],
        work=(),
        label="guard-" + name,
    )


def test_no_case_ever_scrubs() -> None:
    """The guard NEVER runs `aws s3 rm`, and the frozen call logs are where that is checked on every branch at once."""
    _reading_goldens()
    for name in CASES:
        calls = diff.golden_answer(TWIN_REL, _key_for(name) + "|calls", ())[1]
        assert "s3 rm" not in calls, name
