"""`rediacc_ci.drills.gpu_grants`: the CLI-free helpers of the G1 step (box T1 of PLAN-gpu-device-grants), pinned without a machine. The live `run(ctx)` is exercised by `npm run vm:check` (its G1 rows); here the spec text, the root scripts and the parsers and verdicts of `/dev` listings, cgroup readouts, grant files and refusals are checked against outputs shaped like the real ones."""

from __future__ import annotations

import base64
import json
import re

from rediacc_ci.drills import gpu_grants as g
from rediacc_ci.drills import vm_check
from rediacc_ci.well_known import DATASTORE_PATH, INFRA_DOMAIN, RUNTIME_DIR

FAKE_KIND = INFRA_DOMAIN + "/fake"
FAKE_DEV = FAKE_KIND + "=one"

DENIAL = (
    "docker: Error response from daemon: refused by this repository's Docker API gate "
    f'(containers/create): device "{FAKE_DEV}" is not granted to this repository; '
    "grant it with rdc repo gpu grant\n"
)

BASE_DEV = ["console", "core", "fd", "full", "mqueue", "null", "ptmx", "pts", "random", "shm"]


def probe_out(entries: list[str], open_line: str, rc: int = 0) -> str:
    lines = ["N:%s" % e for e in entries]
    lines += ["O:%s" % open_line, "O:done", "DOCKER_RC=%d" % rc]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- registration


def test_step_registration_tuple() -> None:
    assert ("G1", ("P5",), g.run) == g.STEP
    assert g.STEP in vm_check.EXTRA_RENET_STEPS
    assert "G1" in vm_check.PHASE_STEPS[vm_check.SIDE_RENET]


def test_g1_runs_after_u2_and_only_drags_in_p5() -> None:
    ids = [step_id for step_id, _deps, _fn in vm_check.EXTRA_RENET_STEPS]
    assert ids.index("G1") > ids.index("U2")
    assert vm_check.VmCheck._ONLY_DEPS["G1"] == ("P5",)


def test_fork_tags_are_swept_as_stale_vmc_forks() -> None:
    tags = vm_check.fork_tags("10251200", "abc123")
    d, e = g.fork_tags(tags)
    assert (d, e) == ("vmc-10251200-abc123-d", "vmc-10251200-abc123-e")
    for tag in (d, e, *tags):
        assert vm_check.FORK_TAG.match(tag)
    assert not vm_check.FORK_TAG.match("vmc-10251200-abc123-f")


# --------------------------------------------------------------------------- spec and setup


def test_spec_text_defines_the_fake_device_with_its_numbers() -> None:
    spec = g.spec_text()
    assert 'cdiVersion: "0.6.0"' in spec
    assert f"kind: {FAKE_KIND}\n" in spec
    assert "  - name: one\n" in spec
    assert "        - path: /dev/rediacc-fake\n" in spec
    assert "type: c\n" in spec
    assert "major: 60\n" in spec
    assert "minor: 0\n" in spec
    assert g.CDI_NAME == FAKE_DEV


def test_fake_node_is_not_a_default_container_device() -> None:
    # 1:3 (/dev/null) is in every container's default rules, so a cgroup row on it could never fail.
    assert (g.NODE_MAJOR, g.NODE_MINOR) != (1, 3)
    assert g.NODE_MAJOR in range(60, 64)
    assert g.NODE_RULE == "c 60:0 rwm"


def test_setup_script_mknods_and_writes_the_spec_through_base64() -> None:
    script = g.setup_script()
    assert "mknod -m 0666 /dev/rediacc-fake c 60 0" in script
    b64 = re.search(r"printf %s (\S+) \| base64 -d > /etc/cdi/fake\.yaml", script)
    assert b64
    assert base64.b64decode(b64.group(1)).decode() == g.spec_text()
    assert script.startswith("set -e;")


def test_teardown_script_removes_both_and_proves_it() -> None:
    script = g.teardown_script()
    assert "rm -f /etc/cdi/fake.yaml /dev/rediacc-fake" in script
    assert "test ! -e /etc/cdi/fake.yaml && test ! -e /dev/rediacc-fake" in script


def test_setup_verdict() -> None:
    ok = f"crw-rw-rw-    1 0        0          60,   0 Oct 25 12:00 /dev/rediacc-fake\nkind: {FAKE_KIND}\n"
    assert g.setup_verdict(ok)
    assert not g.setup_verdict(ok.replace("60,   0", "1,   3"))
    assert not g.setup_verdict(ok.replace("crw", "brw"))
    assert not g.setup_verdict(ok.replace(f"kind: {FAKE_KIND}", ""))
    assert not g.setup_verdict("")


# --------------------------------------------------------------------------- docker run probes


def test_docker_run_prints_its_status() -> None:
    cmd = g.docker_run(g.device_flag())
    assert cmd == f"docker run --rm --device {FAKE_DEV} busybox:1.36 true 2>&1; echo DOCKER_RC=$?"
    assert g.docker_rc("x\nDOCKER_RC=125\n") == 125
    assert g.docker_rc("DOCKER_RC=1\nDOCKER_RC=0\n") == 0
    assert g.docker_rc("no marker") is None


def test_probe_commands_never_meet_the_cli_write_guard() -> None:
    # The CLI's redirect pattern (vm_check tests' FILE_WRITE): a term connect command matching it is refused.
    file_write = re.compile(r"\b(cat|echo|printf|base64)\b[^|;&]*>>?\s*(?!/dev/null\b)(?!&)\S")
    for cmd in (
        g.docker_run(g.device_flag(), g.probe_command()),
        g.docker_run("", g.probe_command()),
        g.docker_run(g.device_flag()),
        "docker exec x %s" % g.open_command(),
    ):
        assert not file_write.search(cmd), cmd


def test_not_granted_verdict() -> None:
    ok, why = g.not_granted_verdict(DENIAL + "DOCKER_RC=125\n")
    assert ok
    assert "rc=125" in why
    assert not g.not_granted_verdict(DENIAL + "DOCKER_RC=0\n")[0]
    assert not g.not_granted_verdict(DENIAL)[0]
    other = "docker: Error response from daemon: could not select device driver\nDOCKER_RC=125\n"
    assert not g.not_granted_verdict(other)[0]
    wrong_dev = DENIAL.replace(FAKE_DEV, "nvidia.com/gpu=all") + "DOCKER_RC=125\n"
    assert not g.not_granted_verdict(wrong_dev)[0]


def test_added_nodes_verdict() -> None:
    base = probe_out(BASE_DEV, "head: /dev/rediacc-fake: No such file or directory")
    granted = probe_out(
        [*BASE_DEV, "rediacc-fake"], "head: /dev/rediacc-fake: No such device or address"
    )
    ok, why = g.added_nodes_verdict(granted, base)
    assert ok
    assert "['rediacc-fake']" in why
    extra = probe_out([*BASE_DEV, "rediacc-fake", "kmsg"], "x")
    assert not g.added_nodes_verdict(extra, base)[0]
    assert not g.added_nodes_verdict(base, base)[0]
    assert not g.added_nodes_verdict(probe_out([*BASE_DEV, "rediacc-fake"], "x", rc=125), base)[0]
    assert not g.added_nodes_verdict(granted, "DOCKER_RC=0\n")[0]


def test_open_verdict() -> None:
    assert g.open_verdict("O:head: /dev/rediacc-fake: No such device or address\nO:done\n")[0]
    refused = "O:head: /dev/rediacc-fake: Operation not permitted\nO:done\n"
    assert not g.open_verdict(refused)[0]
    assert not g.open_verdict("O:done\n")[0]
    assert not g.open_verdict("")[0]


# --------------------------------------------------------------------------- cgroup readout


def test_cgroup_script_reads_both_versions_through_the_repo_socket() -> None:
    script = g.cgroup_script(f"{RUNTIME_DIR}/net-9/docker-9.sock", ("dev", "base"))
    assert f"docker -H unix://{RUNTIME_DIR}/net-9/docker-9.sock inspect" in script
    assert "devices.list" in script
    assert "bpftool cgroup list" in script
    assert "bpftool prog dump xlated id" in script
    assert "NOBPFTOOL" in script
    assert script.endswith("rd dev; rd base")


V1_BASE = """CGV=1
RULE:c 1:3 rwm
RULE:c 1:5 rwm
RULE:c 136:* rwm
RULE:c *:* m
"""


def test_v1_rules_verdict() -> None:
    granted = V1_BASE + "RULE:c 60:0 rwm\n"
    ok, why = g.cgroup_rules_verdict(granted, V1_BASE)
    assert ok
    assert "c 60:0 rwm" in why
    assert g.v1_rules("RULE:c  1:3   rwm\n") == {"c 1:3 rwm"}
    assert not g.cgroup_rules_verdict(V1_BASE, V1_BASE)[0]
    assert not g.cgroup_rules_verdict(granted + "RULE:a *:* rwm\n", V1_BASE)[0]
    assert not g.cgroup_rules_verdict(granted, "CGV=1\n")[0]


def xlated(*majors: int) -> str:
    lines = ["CGV=2 CG=/rediacc.slice/x", "PROG=42"]
    pc = 0
    for major in majors:
        lines.append("XL:  %d: (55) if r2 != 0x2 goto pc+4" % pc)
        lines.append("XL:  %d: (55) if r4 != 0x%x goto pc+3" % (pc + 1, major))
        lines.append("XL:  %d: (55) if r5 != 0x0 goto pc+2" % (pc + 2))
        lines.append("XL:  %d: (b7) r0 = 1" % (pc + 3))
        pc += 4
    return "\n".join(lines) + "\n"


def test_v2_compare_immediates() -> None:
    assert g.v2_compare_immediates(xlated(1, 136)) == {2, 1, 136, 0}
    assert g.v2_compare_immediates("XL: 3: (56) if w4 != 0x3c goto pc+1\n") == {60}
    assert g.v2_compare_immediates("if r4 != 0x3c goto pc+1\n") == set()


def test_v2_rules_verdict() -> None:
    base = xlated(1, 5, 136)
    ok, why = g.cgroup_rules_verdict(xlated(1, 5, 136, 60), base)
    assert ok
    assert "[60]" in why
    assert not g.cgroup_rules_verdict(base, base)[0]
    assert not g.cgroup_rules_verdict(xlated(1, 5, 136, 60, 10), xlated(1, 5, 136))[0]
    nobpf = "CGV=2 CG=/x\nNOBPFTOOL\n"
    ok, why = g.cgroup_rules_verdict(nobpf, nobpf)
    assert not ok
    assert "bpftool" in why


def test_cgroup_verdict_refuses_mixed_or_missing_versions() -> None:
    assert not g.cgroup_rules_verdict(V1_BASE, xlated(1))[0]
    assert not g.cgroup_rules_verdict("NOPID: no such container\n", V1_BASE)[0]


def test_split_cgroup_sections() -> None:
    text = "== dev\nCGV=1\nRULE:c 60:0 rwm\n== base\nCGV=1\n"
    sections = g.split_cgroup_sections(text)
    assert set(sections) == {"dev", "base"}
    assert "c 60:0" in sections["dev"]
    assert "c 60:0" not in sections["base"]


# --------------------------------------------------------------------------- grants


def test_grant_scripts() -> None:
    assert g.grant_show_script(9) == "renet daemon grant --network-id 9 --show"
    assert g.revoke_script("9") == f"renet daemon grant --network-id 9 --revoke-device {FAKE_DEV}"


def test_parse_grant_devices() -> None:
    doc = {
        "version": 1,
        "repo_mount_path": f"{DATASTORE_PATH}/mounts/x",
        "devices": [
            {
                "name": FAKE_DEV,
                "exclusive": True,
                "granted_at": "2026-10-25T00:00:00Z",
            },
            {"name": "nvidia.com/gpu=all", "granted_at": "2026-10-25T00:00:00Z"},
        ],
    }
    text = "level=info msg={noise}\n" + json.dumps(doc, indent=2) + "\n"
    assert g.parse_grant_devices(text) == {FAKE_DEV: True, "nvidia.com/gpu=all": False}
    assert g.parse_grant_devices(json.dumps({"version": 1, "repo_mount_path": ""})) == {}
    assert g.parse_grant_devices("no json") is None
    assert g.parse_grant_devices('{"other": 1}') is None


def test_exclusive_refusal_verdict() -> None:
    text = f"Error: device {FAKE_DEV} is granted exclusively to network 2816\n"
    ok, why = g.exclusive_refusal_verdict(1, text, 2816)
    assert ok
    assert "holder named=True" in why
    assert not g.exclusive_refusal_verdict(0, text, 2816)[0]
    assert not g.exclusive_refusal_verdict(1, text, 3072)[0]
    assert not g.exclusive_refusal_verdict(1, "Error: connection reset", 2816)[0]
