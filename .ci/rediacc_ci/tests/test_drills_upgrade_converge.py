"""`rediacc_ci.drills.upgrade_converge`: the CLI-free helpers of the U1 step, pinned without a machine. The live `run(ctx)` orchestration is exercised by `npm run vm:check` (its U1 rows) and is wired into vm_check by an injected `u1_fn` the vm_check tests stub; here only the pure pieces -- the layout path strings, the build and status command text, and the parsers that read the stamp and the converge report -- are checked."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.drills import upgrade_converge as u
from rediacc_ci.drills import vm_check
from rediacc_ci.well_known import RUNTIME_DIR

if TYPE_CHECKING:
    import pathlib

SHA = "16538095dbbae2202b2d00bd9ff0a1b8a086ed11168ae3ecf1b2a195f4cdc4c0"
# The stamp exactly as renet wrote it on ops-worker, 2026-10-24 (pretty-printed over several lines).
LIVE_STAMP = (
    '{\n  "epoch": 1,\n  "renet_sha256": "%s",\n  "pid": 69811,\n  "started_at": "2026-10-24T08:16:20.724692721Z"\n}\n'
    % SHA
)


def test_layout_paths_match_the_per_network_and_flat_forms() -> None:
    assert u.old_docker_socket(8512) == f"{RUNTIME_DIR}/docker-8512.sock"
    assert u.new_docker_socket(8512) == f"{RUNTIME_DIR}/net-8512/docker-8512.sock"
    assert u.runtime_stamp_path(8512) == "/var/lib/rediacc/runtime/net-8512.json"
    assert u.new_docker_socket("8512") == u.new_docker_socket(8512)


def test_pre_isolation_commit_is_the_parent_of_the_layout_change() -> None:
    assert u.PRE_ISOLATION_COMMIT == "0c3a88a^"


def test_build_script_clones_and_builds_without_touching_bin() -> None:
    script = u.build_old_renet_script("/w/src", "/w/old", "7070d286")
    # A checkout, not `git archive`: renet's `.gitattributes` marks `* export-ignore`, so archive would export only LICENSE.
    assert "git clone --quiet --shared --no-checkout private/renet /w/src" in script
    assert "checkout --quiet 7070d286" in script
    assert "archive" not in script
    assert "go build -tags nolicense -o /w/old ./cmd/renet" in script
    assert "private/renet/bin" not in script
    assert script.startswith("set -eu")


def test_build_script_quotes_a_hostile_path() -> None:
    script = u.build_old_renet_script("/w/a b; rm -rf /", "/w/out", "7070d28")
    assert "'/w/a b; rm -rf /'" in script
    assert "; rm -rf / &&" not in script


def _envelope(report: dict[str, object], success: bool = True) -> str:
    return json.dumps({"success": success, "command": "machine converge", "data": report})


@pytest.mark.parametrize(
    ("payload", "clean"),
    [
        ('{"summary": {"would_converge": 0}, "plan": []}', True),
        ('{"summary": {"would_converge": 0}, "plan": [{"name": "a"}]}', True),
        ('{"summary": {"would_converge": 2}, "plan": []}', False),
        ('{"summary": {"would_converge": 0}, "plan": [{"stale_reasons": ["epoch"]}]}', False),
        ("not json", False),
        ('{"plan": []}', False),
        # The CLI's `--json` envelope, as the 2026-10-24 live run printed it.
        (
            _envelope(
                {"summary": {"would_converge": 0}, "plan": [{"name": "a", "action": "current"}]}
            ),
            True,
        ),
        (
            _envelope(
                {"summary": {"would_converge": 1}, "plan": [{"stale_reasons": ["no_stamp"]}]}
            ),
            False,
        ),
        (_envelope({"summary": {"would_converge": 0}, "plan": []}, success=False), False),
        ('{"summary": {}, "plan": []}', False),
        ('{"summary": {"would_converge_renamed": 0}, "plan": []}', False),
    ],
)
def test_dry_run_reports_zero_stale(payload: str, clean: bool) -> None:
    assert u.dry_run_reports_zero_stale(payload) is clean


def test_config_name_is_run_scoped() -> None:
    assert u.config_name("vmc-10240427-94d613") == "u1-vmc-10240427-94d613"


def test_parse_stamp_reads_the_live_multi_line_file() -> None:
    stamp = u.parse_stamp("NEWSOCK\n" + LIVE_STAMP)
    assert stamp is not None
    assert stamp["epoch"] == 1
    assert stamp["pid"] == 69811
    assert stamp["renet_sha256"] == SHA


@pytest.mark.parametrize("text", ["", "not json", "NEWSOCK\n", "{broken"])
def test_parse_stamp_rejects_what_is_not_a_stamp(text: str) -> None:
    assert u.parse_stamp(text) is None


@pytest.mark.parametrize(
    ("stamp", "deployed", "current"),
    [
        ({"epoch": 1, "pid": 42, "renet_sha256": SHA}, SHA, True),
        ({"epoch": 2, "pid": 42, "renet_sha256": SHA}, SHA, True),
        # A stamp left by a daemon the old binary started: the converge pass did not restart it.
        ({"epoch": 1, "pid": 42, "renet_sha256": "0" * 64}, SHA, False),
        ({"epoch": 0, "pid": 42, "renet_sha256": SHA}, SHA, False),
        ({"epoch": 1, "pid": 0, "renet_sha256": SHA}, SHA, False),
        ({"epoch": 1, "renet_sha256": SHA}, SHA, False),
        ({"epoch": 1, "pid": 42, "renet_sha256": SHA}, "", False),
        (None, SHA, False),
    ],
)
def test_stamp_is_current(stamp: dict[str, object] | None, deployed: str, current: bool) -> None:
    assert u.stamp_is_current(stamp, deployed) is current


def test_file_sha256(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "bin"
    path.write_bytes(b"renet")
    assert u.file_sha256(path) == hashlib.sha256(b"renet").hexdigest()
    assert u.file_sha256(tmp_path / "absent") == ""


def test_run_is_the_default_u1_step() -> None:
    # vm_check wires this function as the default u1_fn; a rename here would silently drop the live step, so pin the attribute.
    sig = inspect.signature(vm_check.VmCheck.__init__)
    assert sig.parameters["u1_fn"].default is u.run


OLD_LISTING = "docker-8512.sock\ndocker-8513.sock\ncontainerd-8512\nsecrets\n"
NEW_LISTING = "net-8512\n"


def test_runtime_view_verdict_reads_the_old_layout_breach_and_the_converged_isolation() -> None:
    assert u.runtime_view_verdict(OLD_LISTING, 8512, 8513, expect_peer_visible=True)[0]
    assert u.runtime_view_verdict(NEW_LISTING, 8512, 8513, expect_peer_visible=False)[0]
    # The converged layout is not ok while the peer is still listed, and the old one is not a breach when it is not.
    assert not u.runtime_view_verdict(OLD_LISTING, 8512, 8513, expect_peer_visible=False)[0]
    assert not u.runtime_view_verdict(NEW_LISTING, 8512, 8513, expect_peer_visible=True)[0]
    assert not u.runtime_view_verdict("net-8513\n", 8512, 8513, expect_peer_visible=False)[0]


@pytest.mark.parametrize("text", ["", "NOPID\n", "  \n"])
@pytest.mark.parametrize("expect", [True, False])
def test_a_probe_that_listed_nothing_is_never_ok(text: str, expect: bool) -> None:
    ok, evidence = u.runtime_view_verdict(text, 8512, 8513, expect_peer_visible=expect)
    assert not ok
    assert "no runtime listing" in evidence


def test_pid_file_paths_follow_each_layout() -> None:
    assert u.old_docker_pid_file(8512) == f"{RUNTIME_DIR}/docker-8512.pid"
    assert u.new_docker_pid_file("8512") == f"{RUNTIME_DIR}/net-8512/docker-8512.pid"


def test_runtime_view_script_reads_the_pid_file_and_is_valid_shell() -> None:
    script = u.runtime_view_script(u.new_docker_pid_file(8512))
    assert "nsenter -t $pid -m ls -1" in script
    assert "net-8512/docker-8512.pid" in script
    assert "pgrep" not in script
    assert "HOSTNS" in script
    assert subprocess.run(["bash", "-n", "-c", script], check=False).returncode == 0
    # The before-upgrade row opts out of the host-namespace refusal.
    assert "HOSTNS" not in u.runtime_view_script("/x.pid", allow_host_ns=True)


def _run_script(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)


def test_no_dockerd_prints_nopid(tmp_path: pathlib.Path) -> None:
    missing = _run_script(u.runtime_view_script(str(tmp_path / "absent.pid")))
    assert (missing.returncode, missing.stdout.strip()) == (3, "NOPID")
    # A live pid that is not a dockerd (this very test process) is NOPID too.
    pid_file = tmp_path / "docker.pid"
    pid_file.write_text("%d\n" % os.getpid())
    other = _run_script(u.runtime_view_script(str(pid_file)))
    assert (other.returncode, other.stdout.strip()) == (3, "NOPID")
    pid_file.write_text("not-a-pid")
    assert _run_script(u.runtime_view_script(str(pid_file))).stdout.strip() == "NOPID"


@pytest.mark.skipif(
    not os.access("/proc/1/ns/mnt", os.R_OK), reason="needs readable /proc/1/ns/mnt"
)
def test_a_dockerd_in_the_host_namespace_is_refused(tmp_path: pathlib.Path) -> None:
    fake = tmp_path / "dockerd"
    shutil.copy(shutil.which("sleep") or "/bin/sleep", fake)
    proc = subprocess.Popen([str(fake), "30"])
    try:
        pid_file = tmp_path / "docker.pid"
        pid_file.write_text("%d\n" % proc.pid)
        res = _run_script(u.runtime_view_script(str(pid_file)))
        assert (res.returncode, res.stdout.strip()) == (4, "HOSTNS")
    finally:
        proc.kill()
        proc.wait()


def test_a_host_namespace_listing_is_not_checkable() -> None:
    ok, evidence = u.runtime_view_verdict("HOSTNS\n", 8512, 8513, expect_peer_visible=True)
    assert not ok
    assert "NOT ISOLATED-CHECKABLE" in evidence


def test_sees_peer_on_a_sample_listing() -> None:
    _, evidence = u.runtime_view_verdict(OLD_LISTING, 8512, 8513, expect_peer_visible=True)
    assert "sees_own=True sees_peer=True" in evidence
    _, evidence = u.runtime_view_verdict(NEW_LISTING, 8512, 8513, expect_peer_visible=False)
    assert "sees_own=True sees_peer=False" in evidence


def test_host_namespace_guard_fails_closed_on_an_unreadable_namespace() -> None:
    # Review d7cb08f1.1: an empty readlink on either side must refuse, not compare unequal and pass.
    script = u.runtime_view_script(u.new_docker_pid_file(7))
    assert '[ -n "$own" ] && [ -n "$host" ] && [ "$own" != "$host" ]' in script
    assert "echo HOSTNS; exit 4" in script
