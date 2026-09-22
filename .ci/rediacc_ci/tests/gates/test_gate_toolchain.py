r"""Port of `.ci/scripts/test/gates/test-toolchain.sh`, retired in W7 P5.

Controls for `.ci/scripts/lib/toolchain.sh`.

THE SUBJECT STAYS BASH. Nothing ported it: three real readers source the file directly (`bash`'s `set -a; . toolchain.env`, a Dockerfile `COPY` + `ARG`, and GitHub Actions' `cat >> $GITHUB_ENV`), so this port changes the harness language and not the subject, exactly as `test_gate_review_status.py` keeps driving bash `review-status.sh` for the same reason.

The hazard this file exists for: every tool prints its version differently, so the normaliser is per-tool and fragile. A normaliser that silently returns "" would make `toolchain_check` compare "" against "" and PASS -- vacuity inside the check whose whole job is preventing it. So every probe assertion is paired with a garbage-output control, and every match assertion with a
mismatch.

Fake binaries are built by CONSTRUCTION in a per-test `tmp_path`, never by mutating a real tool, so a reworded real `--version` cannot void these.

EACH CALL IS ITS OWN SUBPROCESS, sourcing the library fresh -- the same choice `test_gate_review_status.py`'s `source_common` makes, for the identical reason: a shell library cannot be sourced in-process from Python, and `toolchain_load`'s own idempotence guard (`REDIACC_TOOLCHAIN_LOADED`) means nothing is lost by not sharing one shell across calls.

A FLAT TWIN. The bash original declares no `test_*()` functions -- it is a straight-line script ending in `tally_finish "toolchain"` -- so `test_twin_parity.py`'s case-set comparison would have fallen back to its runtime `PASS:` line count anyway. This port keeps the same shape: one `gate.ok()`/`gate.log_pass()` per twin assertion, grouped into a handful of pytest functions rather
than the twin's single run, which is a Python-side convenience and not a case the twin declared.
"""

import os

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

LIB = paths.from_root(".ci", "scripts", "lib", "toolchain.sh")


def fake(bindir, name, stdout) -> None:
    """`fake <name> <stdout>` -- a binary that just cats fixed text to stdout."""
    path = bindir / name
    path.write_text("#!/usr/bin/env bash\ncat <<'OUT'\n%s\nOUT\n" % stdout, encoding="utf-8")
    path.chmod(0o755)


def source_run(snippet, env=None) -> harness.RunResult:
    """`source toolchain.sh; toolchain_load || refuse; <snippet>`, one subprocess."""
    return harness.run(
        [
            "bash",
            "-c",
            'source "$1"; toolchain_load >/dev/null 2>&1 || '
            '{ echo "cannot load pins" >&2; exit 9; }; %s' % snippet,
            "_",
            str(LIB),
        ],
        env=env,
    )


def with_path(bindir) -> dict:
    """PATH with `bindir` prepended to the REAL PATH, resolved now, not `$PATH` left literal."""
    return {"PATH": "%s%s%s" % (bindir, os.pathsep, os.environ.get("PATH", ""))}


def probe(tmp_path, tool, stdout) -> str:
    """Write a fake `tool` printing `stdout`, and return `toolchain_probe_version`'s output."""
    fake(tmp_path, tool, stdout)
    result = source_run('toolchain_probe_version %s "%s/%s"' % (tool, tmp_path, tool))
    return result.out.strip()


def check(gate, label, actual, want) -> None:
    """`check <label> <actual> <want>` -- one recorded control per real-world shape, matching the twin's own per-assertion `ok`/`no` granularity rather than folding six shapes into one."""
    if actual == want:
        gate.ok(label)
    else:
        gate.no("%s (got %r, want %r)" % (label, actual, want))


def test_every_real_world_version_shape_parses_to_a_bare_version(gate, tmp_path):
    check(gate, "shfmt: a leading v is stripped", probe(tmp_path, "shfmt", "v3.13.1"), "3.13.1")
    check(
        gate,
        "shellcheck: read from a multi-line banner",
        probe(
            tmp_path,
            "shellcheck",
            "ShellCheck - shell script analysis tool\nversion: 0.10.0\n"
            "license: GNU General Public License, version 3",
        ),
        "0.10.0",
    )
    check(gate, "ruff: second field", probe(tmp_path, "ruff", "ruff 0.16.1"), "0.16.1")
    check(gate, "actionlint: bare version", probe(tmp_path, "actionlint", "1.7.12"), "1.7.12")
    check(
        gate,
        "go: 'go' prefix stripped, arch dropped",
        probe(tmp_path, "go", "go version go1.26.4 linux/arm64"),
        "1.26.4",
    )
    check(gate, "node: leading v stripped", probe(tmp_path, "node", "v22.23.2"), "22.23.2")
    gate.tally_finish("real-world version shapes")


def test_garbage_output_fails_rather_than_yielding_empty(gate, tmp_path):
    fake(tmp_path, "shfmt", "command not found: shfmt")
    result = source_run('toolchain_probe_version shfmt "%s/shfmt" >/dev/null 2>&1' % tmp_path)
    if result.rc == 0:
        gate.log_fail("CONTROL: unparseable output must not yield a version")
    gate.ok("CONTROL: unparseable output fails instead of returning empty")

    fake(tmp_path, "shfmt", "")
    result = source_run('toolchain_probe_version shfmt "%s/shfmt" >/dev/null 2>&1' % tmp_path)
    if result.rc == 0:
        gate.log_fail("CONTROL: empty output must not yield a version")
    gate.ok("CONTROL: empty output fails instead of returning empty")
    gate.tally_finish("garbage-output controls")


def pinned(name) -> str:
    """The REAL current value of pin `name`, read by actually loading the pins -- never hand-copied, so a future pin bump cannot make this assertion stale without also moving what it is compared against."""
    result = source_run('echo "$%s"' % name)
    return result.out.strip()


def test_toolchain_check_match_mismatch_absent(gate, tmp_path):
    fake(tmp_path, "shfmt", "v%s" % pinned("SHFMT_VERSION"))
    result = source_run("toolchain_check shfmt >/dev/null 2>&1", env=with_path(tmp_path))
    if result.rc != 0:
        gate.log_fail("a PATH binary AT the pin was rejected: %s" % result.combined)
    gate.ok("a PATH binary at the pin is accepted")

    fake(tmp_path, "shfmt", "v0.0.1")
    result = source_run("toolchain_check shfmt >/dev/null 2>&1", env=with_path(tmp_path))
    if result.rc == 0:
        gate.log_fail("CONTROL: a WRONG version on PATH was accepted -- the pin is decorative")
    gate.ok("CONTROL: a wrong version on PATH is rejected")

    empty = tmp_path / "empty"
    empty.mkdir()
    result = source_run("toolchain_check shfmt >/dev/null 2>&1", env=with_path(empty))
    if result.rc == 0:
        gate.log_fail("CONTROL: an absent tool was accepted")
    gate.ok("CONTROL: an absent tool is rejected")

    # node compares MAJOR only; both directions.
    fake(tmp_path, "node", "v22.99.0")
    result = source_run("toolchain_check node >/dev/null 2>&1", env=with_path(tmp_path))
    if result.rc != 0:
        gate.log_fail("node: same major was rejected")
    gate.ok("node: a different patch inside the pinned major is accepted")

    fake(tmp_path, "node", "v24.14.0")
    result = source_run("toolchain_check node >/dev/null 2>&1", env=with_path(tmp_path))
    if result.rc == 0:
        gate.log_fail("CONTROL: a different node MAJOR was accepted")
    gate.ok("CONTROL: a different node major is rejected")
    gate.tally_finish("toolchain_check match/mismatch/absent")


def test_the_pins_file_itself(gate):
    result = source_run("toolchain_keys | wc -l | tr -d ' '")
    n = int(result.out.strip() or "0")
    if n < 7:
        gate.log_fail(
            "pins file defines only %d keys -- a shrinking file must not read as clean" % n
        )
    gate.ok("pins file defines %d keys" % n)

    result = source_run(
        "toolchain_pairs | grep -qvE '^[A-Z][A-Z0-9_]*=[^ ]*$' && echo BAD || echo OK"
    )
    if result.out.strip() == "BAD":
        gate.log_fail("CONTROL: --env emitted a line $GITHUB_ENV would reject")
    gate.ok("CONTROL: every --env line is KEY=value, safe for $GITHUB_ENV")
    gate.tally_finish("the pins file")
