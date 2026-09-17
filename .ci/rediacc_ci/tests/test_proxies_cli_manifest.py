"""`rediacc_ci.proxies.cli_manifest` against its bash twin.

TWIN is the PROXY itself (`proxy-cli-manifest.sh`), not the subject it drives (`.ci/scripts/build/generate-cli-manifest.sh`, which stays bash on both sides of this comparison -- it now also has its own separate W7P6 port, `rediacc_ci.build.generate_cli_manifest`, but that port is not what this proxy invokes). Both the bash and the Python proxy build their own fixture dist directory
in a fresh tmpdir and invoke the SAME bash subject, so this differential is really asking one question: does the ported harness assert the same things, in the same order, with the same exit code?

BOTH INVOCATIONS ARE BYTE-IDENTICAL ON PURPOSE, same technique as `test_version_resolve_version.py`: no timestamps, no tmp paths and no PIDs appear in this proxy's own output (the one literal `$(mktemp -d)` in the
hazard message is prose, not a real path), so `old == new` on the full
`(exit, stdout, stderr)` tuple is the right assertion rather than a weaker finding-set comparison.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-cli-manifest.observations.jsonl`, recorded
against a disposable scratch git repo built OUTSIDE this checkout (this repo's own working tree is not clean; `shadow-gate.ts --record` refuses a dirty tree). See that file's own header for the exact recording commands.
"""

from __future__ import annotations

from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/test/proxies/proxy-cli-manifest.sh"
MODULE = "cli_manifest"


def run_both(*args: str) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    old_env = diff.env_for()
    new_env = diff.env_for(PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    arg_str = (" " + " ".join(args)) if args else ""
    old = diff.bash_streams(f"bash {TWIN}{arg_str}", env=old_env, timeout=60)
    new = diff.bash_streams(
        f"python3 -m rediacc_ci.proxies.{MODULE}{arg_str}", env=new_env, timeout=60
    )
    return old, new


def test_selftest_is_byte_identical() -> None:
    old, new = run_both("--selftest")
    assert old[0] == 0
    assert new == old


def test_full_run_is_byte_identical() -> None:
    old, new = run_both()
    assert old[0] == 0
    assert "11 check(s) passed, 3 requirement(s) present" in old[1]
    assert new == old


def test_full_run_reports_the_known_hazard_every_time() -> None:
    # Not ruled on -- see the module docstring -- but it must never go quiet.
    old, new = run_both()
    assert "KNOWN HAZARD in the subject, reported not enforced" in old[1]
    assert new == old
