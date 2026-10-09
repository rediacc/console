"""`private/renet/.ci/scripts/quality/security.sh` prints one `::finding::` key per govulncheck red.

WHY. The console push guard carries a known red by its finding keys and refuses a new key (`.ci/config/carried-reds.json`). check:ci-renet runs this script, so if its keys stop printing, a carried renet red turns into a push refusal with no other signal. This file pins the keys against a fake govulncheck.

HOW. The script finds its repo root three directories above its own `lib/`, so the two script directories are copied into a temp root with that root's own `.govulncheck-allowlist`. A fake `go` on PATH answers `go run ...govulncheck... -format json` with fixed findings. `jq` and `bash` are real.
"""

import json
import os
import pathlib
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

RENET_CI = paths.from_root("private", "renet", ".ci", "scripts")


def run_security(
    tmp_path: pathlib.Path, findings: list[tuple[str, str]], allowlist: str = ""
) -> harness.RunResult:
    """Run security.sh in a temp root whose fake govulncheck reports `findings` as (osv, fixed_version) pairs."""
    root = tmp_path / "root"
    for sub in ("lib", "quality"):
        shutil.copytree(RENET_CI / sub, root / ".ci" / "scripts" / sub)
    (root / ".govulncheck-allowlist").write_text(allowlist, encoding="utf-8")
    payload = "\n".join(
        json.dumps({"finding": {"osv": osv, "fixed_version": fixed}}) for osv, fixed in findings
    )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake_go = bindir / "go"
    fake_go.write_text("#!/usr/bin/env bash\ncat <<'JSON'\n%s\nJSON\n" % payload, encoding="utf-8")
    fake_go.chmod(0o755)
    bash = harness.require_tool("bash", "install bash; the subject is a bash script")
    harness.require_tool("jq", "install jq; the subject parses govulncheck's JSON with it")
    env = dict(os.environ, PATH="%s:%s" % (bindir, os.environ.get("PATH", "")))
    return harness.run([bash, str(root / ".ci" / "scripts" / "quality" / "security.sh")], env=env)


def keys(result: harness.RunResult) -> list[str]:
    return sorted(
        {
            line.removeprefix("::finding::")
            for line in result.combined.splitlines()
            if line.startswith("::finding::")
        }
    )


def test_each_actionable_advisory_prints_its_key(gate, tmp_path):
    if not RENET_CI.is_dir():
        gate.log_fail(
            "private/renet is not checked out, so the subject is missing; run git submodule update --init private/renet"
        )
    result = run_security(tmp_path, [("GO-2026-0001", "v1.2.3"), ("GO-2026-0002", "")])
    gate.assert_eq(result.rc != 0, True, "an actionable advisory fails the script")
    gate.assert_eq(
        keys(result),
        ["govuln:GO-2026-0001", "govuln:GO-2026-0002"],
        "one govuln key per actionable advisory",
    )
    gate.log_pass("each actionable advisory prints its govuln key and the script fails")


def test_a_suppressed_advisory_with_a_fix_prints_a_stale_key_and_one_without_prints_none(
    gate, tmp_path
):
    if not RENET_CI.is_dir():
        gate.log_fail("private/renet is not checked out, so the subject is missing")
    result = run_security(
        tmp_path,
        [("GO-2026-0003", "v2.0.0"), ("GO-2026-0004", "")],
        allowlist="GO-2026-0003 # BLOCKER: test\nGO-2026-0004 # BLOCKER: test\n",
    )
    gate.assert_eq(
        keys(result),
        ["govuln-stale:GO-2026-0003"],
        "only the suppression that now has a fix is keyed",
    )
    gate.log_pass("a fixable suppression prints its stale key, an unfixable one prints none")


def test_control_a_clean_report_prints_no_key(gate, tmp_path):
    if not RENET_CI.is_dir():
        gate.log_fail("private/renet is not checked out, so the subject is missing")
    result = run_security(tmp_path, [])
    gate.assert_eq(keys(result), [], "CONTROL: no finding, no key")
    gate.log_pass("CONTROL: a clean report prints no key")
