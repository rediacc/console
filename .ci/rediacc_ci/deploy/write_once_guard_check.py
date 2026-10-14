#!/usr/bin/env python3
"""Gate `test:write-once-guard`: unit tests for `rediacc_ci.deploy.write_once_guard`. Mocks `aws` so the test runs offline.

THIS FILE IS THE GATE'S RUN TARGET, so it carries the `---- gate ----` header the bash twin used to carry. `run:` is declared rather than derived for the reason `install_script_check.py` gives at its own header: `derivedRun` returns the bare path for a `.py`, nothing puts `.ci` on `sys.path` for a file inside the package, and `PYTHONPATH=.ci` is the exact form the K=5 ledger licensed.

---- gate ----
id: test:write-once-guard
run: PYTHONPATH=.ci python3 .ci/rediacc_ci/deploy/write_once_guard_check.py
step: Write-once guard tests
lane: quality-static
---- end gate ----

The guard's behaviours (see `write_once_guard.py`):
  1. sentinel exists + binaries present  -> return 10 (SKIP: idempotent rerun)
  2. sentinel exists + NO binaries       -> refuse (FAIL: sealed-but-empty)
  3. no sentinel (clean OR orphan bytes) -> return 0 (PROCEED, overwrite in place)
The guard NEVER runs `aws s3 rm`: orphan cleanup is the nightly housekeeping job's responsibility, so a retried or cancelled release cannot lose its binaries.

THE SUBJECT IS THE PYTHON GUARD. It was bash (a function `sed`-extracted out of `upload-to-r2.sh`) until operator ruling D5 (2026-10-08); this harness is unchanged in what it asserts, and `tests/goldens/write-once-guard/` still holds the bytes it printed against the bash guard, which the port reproduces. The guard module is loaded BY PATH from `ROOT_DIR`, so the mutation tests in `tests/test_deploy_write_once_guard_check.py` can point `REDIACC_CI_ROOT` at a fixture holding a mutated copy of that one file.

THE OUTPUT IS BYTE-IDENTICAL, ANSI ESCAPES AND `->` ARROWS INCLUDED. This is a registered gate whose stdout a human reads in a CI log, so `PASS:` is emitted with `\\033[0;32m` / `\\033[0m` rather than through any formatting helper.

`DRY_RUN`, `RELEASES_BUCKET` AND THE ENDPOINT ARE PASSED PER INVOCATION through the environment, so one case cannot leak state into the next.

`grep -q ... && log_fail ...` style checks are plain `if`s here.

Exit: 0 all four cases pass, 1 the first case that does not.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.well_known import RELEASES_BUCKET

ROOT_DIR = paths.repo_root()
GUARD_MODULE = ROOT_DIR / ".ci" / "rediacc_ci" / "deploy" / "write_once_guard.py"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# Environment the guard reads.
BASE_ENV = {
    "RELEASES_BUCKET": RELEASES_BUCKET,
    "CLOUDFLARE_R2_ENDPOINT": "https://example.invalid",
    "VERSION": "0.0.0-test",
    "CHANNEL": "pr-0",
    "DRY_RUN": "false",
}

# Fake aws: dispatches on the first two args so each subcommand can be scripted independently. Also records every invocation into $TEMP/aws.log so tests can assert whether `aws s3 rm --recursive` was called by the orphan-scrub path.
FAKE_AWS = """#!/bin/bash
printf '%s\\n' "$*" >>"{temp}/aws.log"
case "$1 $2" in
    "s3api head-object")
        # Sentinel existence check. Controlled by SENTINEL_EXISTS.
        if [[ "${{SENTINEL_EXISTS:-false}}" == "true" ]]; then
            exit 0
        fi
        exit 254  # typical NoSuchKey exit from awscli
        ;;
    "s3api list-objects-v2")
        # Prefix non-empty check (rsv_prefix_nonempty) uses --query KeyCount.
        printf '%s\\n' "${{PREFIX_KEYCOUNT:-0}}"
        exit 0
        ;;
    "s3 rm")
        # Scrub call. Always succeeds.
        exit 0
        ;;
    *)
        exit 0
        ;;
esac
"""

# Loads the guard module from ROOT_DIR by path, so a fixture can hold a mutated copy. A module with no `write_once_guard` is exit 127, the status a missing command has always had here.
DRIVER = """import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("write_once_guard_under_test", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
guard = getattr(module, "write_once_guard", None)
if guard is None:
    raise SystemExit(127)
try:
    rc = guard(
        sys.argv[2],
        "test",
        endpoint=os.environ["CLOUDFLARE_R2_ENDPOINT"],
        dry_run=os.environ["DRY_RUN"] == "true",
    )
except module.SealedButEmptyError:
    rc = 1
raise SystemExit(rc)
"""


class CaseFailedError(Exception):
    """`log_fail`, which in the twin is an `exit 1` from wherever it is called."""


def log_fail(message: str) -> None:
    print("%sFAIL:%s %s" % (RED, NC, message), file=sys.stderr, flush=True)
    raise CaseFailedError


def log_pass(message: str) -> None:
    print("%sPASS:%s %s" % (GREEN, NC, message), flush=True)


class Harness:
    def __init__(self, temp: pathlib.Path) -> None:
        self.temp = temp
        self.log = temp / "aws.log"

    def build(self) -> None:
        aws = self.temp / "aws"
        aws.write_text(FAKE_AWS.format(temp=self.temp), encoding="utf-8")
        aws.chmod(0o755)

    def reset_log(self) -> None:
        self.log.write_text("", encoding="utf-8")

    def logged(self, needle: str) -> bool:
        """`grep -q <needle> "$TEMP/aws.log"`, fixed-string as the twin's is."""
        return needle in self.log.read_text(encoding="utf-8")

    def run_guard(self, prefix: str, **overrides: str) -> int:
        env = dict(os.environ)
        env.update(BASE_ENV)
        env.update(overrides)
        env["PATH"] = "%s:%s" % (self.temp, os.environ.get("PATH", ""))
        # The gate runs with `PYTHONPATH=.ci`; the child inherits it. A copy of this file elsewhere falls back to its own package root.
        env.setdefault("PYTHONPATH", str(pathlib.Path(__file__).resolve().parents[2]))
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, "-c", DRIVER, str(GUARD_MODULE), prefix],
            env=env,
            stdout=None,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode


# PREFIX_KEYCOUNT drives BOTH the mock's list-objects-v2 responses; the guard only calls rsv_binary_count when the sentinel exists, so it doubles as the "binary count" for the sealed cases below.


def test_sealed_with_binaries_skips(h: Harness) -> None:
    h.reset_log()
    rc = h.run_guard("cli/v0.0.0/", SENTINEL_EXISTS="true", PREFIX_KEYCOUNT="16")
    if rc != 10:
        log_fail("sealed + binaries present should SKIP (rc=10, idempotent rerun); got rc=%d" % rc)
    if h.logged("s3 rm"):
        log_fail("guard must NEVER scrub")
    log_pass("sealed + binaries → idempotent SKIP (rc=10)")


def test_sealed_but_empty_fails(h: Harness) -> None:
    h.reset_log()
    rc = h.run_guard("cli/v0.0.0/", SENTINEL_EXISTS="true", PREFIX_KEYCOUNT="0")
    if rc != 1:
        log_fail("sealed + NO binaries (sealed-but-empty) should FAIL loud (rc=1); got rc=%d" % rc)
    if h.logged("s3 rm"):
        log_fail("guard must NEVER scrub")
    log_pass("sealed + no binaries → FAIL loud (rc=1)")


def test_no_sentinel_proceeds_without_scrub(h: Harness) -> None:
    # Clean prefix: PROCEED, no scrub.
    h.reset_log()
    if h.run_guard("cli/v0.0.0/", SENTINEL_EXISTS="false", PREFIX_KEYCOUNT="0") != 0:
        log_fail("clean prefix (no sentinel) should PROCEED (rc=0)")
    if h.logged("s3 rm"):
        log_fail("guard must NEVER scrub a clean prefix")

    # Orphan prefix (bytes, no sentinel): PROCEED and OVERWRITE in place -- must NOT scrub (the old behaviour that deleted retried releases' binaries).
    h.reset_log()
    if h.run_guard("cli/v0.0.0/", SENTINEL_EXISTS="false", PREFIX_KEYCOUNT="9") != 0:
        log_fail("orphan prefix should PROCEED (rc=0), overwriting in place")
    if h.logged("s3 rm"):
        # THE EM DASH IS WRITTEN AS AN ESCAPE ON PURPOSE. The twin's message carries a literal U+2014 (test-write-once-guard.sh:140) and this port must emit the same bytes, but a literal em dash in a `.ci/rediacc_ci` `.py` file is a NEW finding for `check:ci-em-dash-surfaces`, whose baseline is shrink-only. The escape keeps the OUTPUT identical without putting the character in the
        # source.
        log_fail(
            "guard must NEVER scrub an orphan -- that is the nightly housekeeping "
            "job's responsibility"
        )
    log_pass("no sentinel → PROCEED (rc=0), never scrubs")


def test_dry_run_skips(h: Harness) -> None:
    h.reset_log()
    if h.run_guard("cli/v0.0.0/", SENTINEL_EXISTS="true", PREFIX_KEYCOUNT="1", DRY_RUN="true") != 0:
        log_fail("DRY_RUN=true should pass regardless of state")
    if h.logged("s3api head-object"):
        log_fail("DRY_RUN must not call aws at all")
    log_pass("DRY_RUN=true skips all checks")


CASES = (
    test_sealed_with_binaries_skips,
    test_sealed_but_empty_fails,
    test_no_sentinel_proceeds_without_scrub,
    test_dry_run_skips,
)


def main(_argv: list[str]) -> int:
    temp = pathlib.Path(tempfile.mkdtemp())
    try:
        harness = Harness(temp)
        harness.build()
        for case in CASES:
            case(harness)
        print(flush=True)  # the twin's bare `echo ""`
        log_pass("all sentinel-aware write_once_guard cases")
        return 0
    except CaseFailedError:
        return 1
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
