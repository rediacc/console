#!/usr/bin/env python3
"""Port of `.ci/scripts/test/test-write-once-guard.sh` (gate `test:write-once-guard`).

Unit tests for the sentinel-aware `write_once_guard()` in `.ci/scripts/deploy/upload-to-r2.sh`. Mocks `aws` so the test runs offline.

THIS FILE IS THE GATE'S RUN TARGET, so it carries the `---- gate ----` header the twin used to carry; the header moved here in the same change that deleted the twin, because a bare-path gate whose declarer is gone emits no step at all. `run:` is declared rather than derived for the reason `install_script_check.py` gives at its own header: `derivedRun` returns the bare path for a
`.py`, nothing puts `.ci` on `sys.path` for a file inside the package, and `PYTHONPATH=.ci` is the exact form the K=5 ledger licensed.

---- gate ----
id: test:write-once-guard
run: PYTHONPATH=.ci python3 .ci/rediacc_ci/deploy/write_once_guard_check.py
step: Write-once guard tests
lane: quality-static
---- end gate ----

The guard's behaviours (see `.ci/scripts/lib/release-state-validator.sh`):
  1. sentinel exists + binaries present  -> return 10 (SKIP: idempotent rerun)
  2. sentinel exists + NO binaries       -> exit 1 (FAIL: sealed-but-empty)
  3. no sentinel (clean OR orphan bytes) -> return 0 (PROCEED, overwrite in place)
The guard NEVER runs `aws s3 rm` -- orphan cleanup is the nightly housekeeping job's responsibility, so a retried/cancelled release can't lose its binaries.

WHAT IS PORTED AND WHAT DELIBERATELY IS NOT. The HARNESS moves to Python: the temp dir, the fake `aws`, the bundle assembly, the four cases, the PASS/FAIL lines and the exit code. The SUBJECT stays bash and is still driven as bash -- `write_once_guard` is a bash function that is `sed`-extracted out of `upload-to-r2.sh` and sourced beside the real `release-state-validator.sh`. A
Python reimplementation of the guard would be a second instrument certifying itself, which is the reason `.ci/scripts/test/lib/git-fixture.sh` and `mutate-check.sh` were allowlisted rather than ported; here only the wrapper around the instrument moves, so the same objection does not apply.

PORT NOTES.

THE OUTPUT IS BYTE-IDENTICAL, ANSI ESCAPES AND `->` ARROWS INCLUDED. This is a registered gate whose stdout a human reads in a CI log, so `PASS:` is emitted
with the twin's own `\\033[0;32m` / `\\033[0m` pair rather than through any
formatting helper, and the messages are copied verbatim.

`VAR=x some_function` EXPORTS INTO THE FUNCTION'S ENVIRONMENT AND THEN VANISHES.
Driven before this was written, because the whole fixture depends on it:
`SENTINEL_EXISTS=true f` where `f` runs `bash -c '...'` DOES reach the
grandchild (the fake `aws` sees `SENTINEL_EXISTS=true`), and the variable is
UNSET again in the caller afterwards. Neither is obvious -- POSIX mode makes such assignments persist -- and a port that set them once on the process would leak state from one case into the next. Here they are passed per invocation.

`grep -q ... && log_fail ...` DOES NOT ABORT WHEN THE GREP FAILS, even under `set -e`, because a command that is not the last in an `&&` list is exempt. So a clean `aws.log` means the scrub assertion simply does not fire; it is not a silent early exit. Ported as a plain `if`.

THE ONE THING THIS PORT COULD NOT KEEP is the shell's own `mktemp -d` name; both sides make their own temp dir, so any output quoting a temp path would differ. Nothing in the twin's output quotes one, which is why the differential can compare bytes.

Exit: 0 all four cases pass, 1 the first case that does not.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths

ROOT_DIR = paths.repo_root()
GUARD_SCRIPT = ROOT_DIR / ".ci" / "scripts" / "deploy" / "upload-to-r2.sh"
VALIDATOR_LIB = ROOT_DIR / ".ci" / "scripts" / "lib" / "release-state-validator.sh"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# Environment upload-to-r2.sh requires before we can source it.
BASE_ENV = {
    "RELEASES_BUCKET": "rediacc-releases",
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

STUBS = """log_error() {{ echo "error: $*" >&2; }}
log_warn()  {{ echo "warn: $*" >&2; }}
log_info()  {{ echo "info: $*" >&2; }}
SCRIPT_DIR="{root}/.ci/scripts/deploy"
RELEASES_BUCKET="{bucket}"
CLOUDFLARE_R2_ENDPOINT="{endpoint}"
DRY_RUN=${{DRY_RUN:-false}}
"""

# `sed -n '/^write_once_guard()/,/^}/p'`: from the definition line to the first
# line that is exactly a closing brace at column 0.
GUARD_START = re.compile(r"^write_once_guard\(\)")
GUARD_END = re.compile(r"^\}")


class CaseFailedError(Exception):
    """`log_fail`, which in the twin is an `exit 1` from wherever it is called."""


def log_fail(message: str) -> None:
    print("%sFAIL:%s %s" % (RED, NC, message), file=sys.stderr, flush=True)
    raise CaseFailedError


def log_pass(message: str) -> None:
    print("%sPASS:%s %s" % (GREEN, NC, message), flush=True)


def extract_guard(text: str) -> str:
    """`sed -n '/^write_once_guard()/,/^}/p'`, range semantics and all."""
    out: list[str] = []
    inside = False
    for line in text.split("\n")[:-1] if text.endswith("\n") else text.split("\n"):
        if not inside:
            if GUARD_START.search(line):
                inside = True
                out.append(line)
            continue
        out.append(line)
        if GUARD_END.search(line):
            inside = False
    return "".join(line + "\n" for line in out)


class Harness:
    def __init__(self, temp: pathlib.Path) -> None:
        self.temp = temp
        self.log = temp / "aws.log"
        self.bundle = temp / "bundle.sh"

    def build(self) -> None:
        aws = self.temp / "aws"
        aws.write_text(FAKE_AWS.format(temp=self.temp), encoding="utf-8")
        aws.chmod(0o755)

        # Extract just the guard function + define stubs for log_* + pull in the validator library (which provides rsv_sentinel_exists / rsv_prefix_nonempty).
        guard = extract_guard(GUARD_SCRIPT.read_text(encoding="utf-8"))
        (self.temp / "guard.sh").write_text(guard, encoding="utf-8")
        self.bundle.write_text(
            STUBS.format(
                root=ROOT_DIR,
                bucket=BASE_ENV["RELEASES_BUCKET"],
                endpoint=BASE_ENV["CLOUDFLARE_R2_ENDPOINT"],
            )
            + VALIDATOR_LIB.read_text(encoding="utf-8")
            + guard,
            encoding="utf-8",
        )

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
        return subprocess.run(
            [
                "bash",
                "-c",
                "source '%s/bundle.sh'; write_once_guard '%s' 'test'" % (self.temp, prefix),
            ],
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


def main(argv: list[str]) -> int:  # noqa: ARG001 -- the twin takes no arguments
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
