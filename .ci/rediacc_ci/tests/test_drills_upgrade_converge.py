"""`rediacc_ci.drills.upgrade_converge`: the CLI-free helpers of the U1 step, pinned without a machine. The live `run(ctx)` orchestration is exercised by `npm run vm:check` (its U1 rows) and is wired into vm_check by an injected `u1_fn` the vm_check tests stub; here only the pure pieces -- the layout path strings, the build and status command text, and the parsers that read the stamp and the converge report -- are checked."""

from __future__ import annotations

import hashlib
import inspect
import json
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.drills import upgrade_converge as u
from rediacc_ci.drills import vm_check

if TYPE_CHECKING:
    import pathlib

SHA = "16538095dbbae2202b2d00bd9ff0a1b8a086ed11168ae3ecf1b2a195f4cdc4c0"
# The stamp exactly as renet wrote it on ops-worker, 2026-10-24 (pretty-printed over several lines).
LIVE_STAMP = (
    '{\n  "epoch": 1,\n  "renet_sha256": "%s",\n  "pid": 69811,\n  "started_at": "2026-10-24T08:16:20.724692721Z"\n}\n'
    % SHA
)


def test_layout_paths_match_the_per_network_and_flat_forms() -> None:
    assert u.old_docker_socket(8512) == "/var/run/rediacc/docker-8512.sock"
    assert u.new_docker_socket(8512) == "/var/run/rediacc/net-8512/docker-8512.sock"
    assert u.net_dir(8512) == "/var/run/rediacc/net-8512"
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


def test_runtime_status_command() -> None:
    cmd = u.runtime_status_command("/usr/bin/renet", "/mnt/rediacc")
    assert cmd == "sudo /usr/bin/renet runtime status --json --datastore /mnt/rediacc"


@pytest.mark.parametrize(
    ("payload", "want"),
    [
        ('{"stale": 3, "repos": []}', 3),
        ('{"stale": 0, "repos": []}', 0),
        ("not json", None),
        ('{"repos": []}', None),
        ("[1,2]", None),
    ],
)
def test_parse_stale_count(payload: str, want: int | None) -> None:
    assert u.parse_stale_count(payload) == want


def _envelope(report: dict[str, object], success: bool = True) -> str:
    return json.dumps({"success": success, "command": "machine converge", "data": report})


@pytest.mark.parametrize(
    ("payload", "clean"),
    [
        ('{"summary": {"would_converge": 0}, "plan": []}', True),
        ('{"summary": {"would_converge": 0}, "plan": [{"name": "a"}]}', True),
        ('{"summary": {"would_converge": 2}, "plan": []}', False),
        ('{"summary": {"would_converge": 0}, "plan": [{"stale_reasons": ["epoch"]}]}', False),
        ('{"summary": {}, "plan": []}', True),
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
