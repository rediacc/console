"""`rediacc_ci.drills.converge_preflight`: the CLI-free helpers of the U2 step (box D1 of PLAN-converge-preflight-and-repo-recovery), pinned without a machine. The live `run(ctx)` is exercised by `npm run vm:check` (its U2 rows); here the compose bodies, the container-id probe and the parsers of the setup summary and of converge-last.json are checked, with fakes standing in for the fields P1, P3 and P4 produce."""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from rediacc_ci.drills import converge_preflight as c
from rediacc_ci.drills import vm_check
from rediacc_ci.well_known import RUNTIME_DIR

GUID_R = "11111111-1111-4111-8111-111111111111"
GUID_C = "22222222-2222-4222-8222-222222222222"
ID_A = "a" * 64
ID_B = "b" * 64

REFUSED = {
    "guid": GUID_R,
    "name": "base:u2r",
    "status": "skipped",
    "reason": "gate_refused",
    "denials": [
        {
            "service": "web",
            "field": "Binds",
            "tier": "bind",
            "message": "bind of /opt/rediacc/proxy",
        },
        "web: cap MKNOD",
    ],
    "extra_future_field": 1,
}
CONTROL = {"guid": GUID_C, "name": "base:u2c", "status": "converged", "network_id": 9}
REPORT = {
    "summary": {"total": 2, "would_converge": 0, "converged": 1, "skipped": 1, "failed": 0},
    "results": [REFUSED, CONTROL],
    "something_new": {"a": 1},
}


def test_step_registration_tuple() -> None:
    assert ("U2", (), c.run) == c.STEP
    assert c.STEP in vm_check.EXTRA_RENET_STEPS
    assert "U2" in vm_check.PHASE_STEPS[vm_check.SIDE_RENET]


def test_refused_compose_has_the_proxy_bind_and_mknod() -> None:
    body = c.refused_compose("web")
    assert f"- {c.PROXY_ROOT}:{c.PROXY_ROOT}" in body
    assert "cap_add:" in body
    assert "- MKNOD" in body
    assert "web:" in body


def test_control_compose_has_nothing_the_gate_refuses() -> None:
    body = c.control_compose("ok")
    assert "ok:" in body
    for word in ("cap_add", "volumes", "MKNOD", c.PROXY_ROOT, "privileged"):
        assert word not in body


def test_container_ids_script_reads_new_socket_before_flat() -> None:
    script = c.container_ids_script(8512)
    new = f"{RUNTIME_DIR}/net-8512/docker-8512.sock"
    old = f"{RUNTIME_DIR}/docker-8512.sock"
    assert script.index(new) < script.index(old)
    assert "ps -q --no-trunc" in script
    assert "NOSOCK" in script


@pytest.mark.parametrize(
    ("text", "want"),
    [
        (f"CID:{ID_B}\nCID:{ID_A}\nSOCK=/s\n", sorted([ID_A, ID_B])),
        ("SOCK=/s\n", []),
        ("NOSOCK\n", None),
        ("", None),
        ("Cannot connect to the Docker daemon\n", None),
    ],
)
def test_parse_container_ids(text: str, want: list[str] | None) -> None:
    assert c.parse_container_ids(text) == want


def test_ids_unchanged() -> None:
    assert c.ids_unchanged([ID_A], [ID_A])
    assert not c.ids_unchanged([ID_A], [ID_B])
    assert not c.ids_unchanged([], [])
    assert not c.ids_unchanged(None, None)
    assert not c.ids_unchanged([ID_A], None)


def test_parse_converge_report_bare_enveloped_and_noisy() -> None:
    bare = json.dumps(REPORT, indent=2)
    assert c.parse_converge_report(bare) == REPORT
    enveloped = json.dumps({"success": True, "command": "machine converge", "data": REPORT})
    assert c.parse_converge_report(enveloped) == REPORT
    assert c.parse_converge_report("log line\n" + bare + "\n") == REPORT
    assert c.parse_converge_report("not json") is None
    assert c.parse_converge_report("{broken") is None
    assert c.parse_converge_report("[1]") is None


def test_result_for_matches_guid_then_name() -> None:
    assert c.result_for(REPORT, GUID_R) is REFUSED
    assert c.result_for(REPORT, "", "base:u2c") is CONTROL
    assert c.result_for(REPORT, "nope") is None
    assert c.result_for(None, GUID_R) is None
    assert c.report_results({"results": "x"}) == []


def test_denials_read_strings_and_objects() -> None:
    lines = c.result_denials(REFUSED)
    assert lines[0] == "web Binds bind bind of /opt/rediacc/proxy"
    assert lines[1] == "web: cap MKNOD"
    assert c.result_denials({"denials": "x"}) == []
    assert c.result_denials(None) == []
    assert c.result_denials({"denials": [{}, ""]}) == ["{}"]


def test_is_gate_refused_needs_status_reason_and_denials() -> None:
    assert c.is_gate_refused(REFUSED)
    assert not c.is_gate_refused({**REFUSED, "denials": []})
    assert not c.is_gate_refused({**REFUSED, "reason": "needs_device_grant"})
    assert not c.is_gate_refused({**REFUSED, "status": "failed"})
    assert not c.is_gate_refused(CONTROL)
    assert not c.is_gate_refused(None)


def test_is_converged() -> None:
    assert c.is_converged(CONTROL)
    assert not c.is_converged(REFUSED)
    assert not c.is_converged(None)


def test_summary_counts_keeps_only_integers() -> None:
    assert c.summary_counts(REPORT) == {
        "total": 2,
        "would_converge": 0,
        "converged": 1,
        "skipped": 1,
        "failed": 0,
    }
    assert c.summary_counts({"summary": {"converged": True, "skipped": "1"}}) == {}
    assert c.summary_counts({}) == {}
    assert c.summary_counts(None) == {}


def test_summary_skips_refused_reads_the_named_line() -> None:
    text = "Converged 1\n  base:u2r  skipped (gate_refused)\n  base:u2c  converged\n"
    assert c.summary_skips_refused(text, "base:u2r", "u2r")
    assert not c.summary_skips_refused(text, "base:u2c")
    assert not c.summary_skips_refused("base:u2r skipped (needs_device_grant)", "base:u2r")
    assert not c.summary_skips_refused(text, "")


def test_config_name_is_run_scoped() -> None:
    assert c.config_name("vmc-10240427-94d613") == "u2-vmc-10240427-94d613"


def test_no_hardcoded_runtime_or_datastore_paths() -> None:
    # Layout paths come from rediacc_ci.well_known through upgrade_converge and the MOUNTS constant, never a literal.
    source = pathlib.Path(c.__file__).read_text()
    assert not re.search(r'"/var/run/rediacc|"/var/lib/rediacc/(?!runtime)', source)
