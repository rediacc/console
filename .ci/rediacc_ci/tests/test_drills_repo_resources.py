"""`rediacc_ci.drills.repo_resources`: the CLI-free pieces of the K2 and K3 steps (box K0b of PLAN-repo-resource-limits). The live rows run against the KVM fleet through `npm run vm:check` (boxes K2 and K3); here the parsers and verdicts are driven both ways. The CONTROL rows are an oom_kill delta that appears in D, and a findmnt listing that still carries `.ram` after the unmount: both must FAIL."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from rediacc_ci.drills import repo_resources as r
from rediacc_ci.drills import vm_check

MOUNT = r.MOUNTS + "/0f0e0d0c-1111-2222-3333-444455556666"
TARGET = r.ram_dir(MOUNT)
LEAF = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

READOUT_C = """== memory.max
1073741824
== memory.high
max
== cpu.max
100000 100000
== memory.events
low 0
high 0
max 4
oom 1
oom_kill 1
oom_group_kill 1
== memory.stat
anon 1000
shmem 220200960
== oom.group keep
1
== oom.group 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
1
"""


def test_fork_tags_stay_in_the_stale_sweep() -> None:
    tags = r.fork_tags(("vmc-11051200-abcdef-a", "vmc-11051200-abcdef-b"))
    assert tags == (
        "vmc-11051200-abcdef-g",
        "vmc-11051200-abcdef-h",
        "vmc-11051200-abcdef-i",
        "vmc-11051200-abcdef-j",
    )
    for tag in tags:
        assert vm_check.FORK_TAG.match(tag), "the stale-fork sweep must recognise %s" % tag


def test_steps_are_registered_after_p5() -> None:
    ids = [step_id for step_id, _deps, _fn in vm_check.EXTRA_RENET_STEPS]
    assert ids[-2:] == ["K2", "K3"]
    assert r.STEP_K2[1] == ("P5",)
    assert r.STEP_K3[1] == ("P5",)
    assert "K2" in vm_check.PHASE_STEPS[vm_check.SIDE_RENET]


def test_cgroup_readout_parsers() -> None:
    assert r.section_value(READOUT_C, "memory.max") == "1073741824"
    assert r.oom_kills(r.sections(READOUT_C)["memory.events"]) == 1
    assert r.shmem(r.sections(READOUT_C)["memory.stat"]) == 220200960
    assert r.oom_groups(READOUT_C) == {"keep": "1", LEAF: "1"}
    assert r.vmstat_oom_kill("oom_kill 7\n") == 7
    assert r.vmstat_oom_kill("pgfault 3\n") is None
    assert "case $n in @*) continue" in r.cgroup_readout_script(3200)


def test_limits_verdicts() -> None:
    ok, why = r.limits_verdict(READOUT_C, r.C_MEMORY_MAX, r.CPU_ONE_CORE)
    assert ok, why
    # A service directory left at oom.group 0 would kill the whole repository's container set wrongly.
    bad = READOUT_C.replace("== oom.group keep\n1", "== oom.group keep\n0")
    assert not r.limits_verdict(bad, r.C_MEMORY_MAX, r.CPU_ONE_CORE)[0]
    assert not r.limits_verdict(
        READOUT_C.replace("1073741824", "max"), r.C_MEMORY_MAX, r.CPU_ONE_CORE
    )[0]
    assert not r.limits_verdict("NO_CGROUP\n", r.C_MEMORY_MAX, r.CPU_ONE_CORE)[0]
    assert r.uncapped_verdict("== memory.max\nmax\n")[0]
    assert not r.uncapped_verdict(READOUT_C)[0]


def test_oom_isolation_verdict_and_control() -> None:
    ok, why = r.oom_isolation_verdict((3, 4), (0, 0), (10, 11))
    assert ok, why
    # CONTROL: a kill that appears in D is a kill outside C.
    assert not r.oom_isolation_verdict((3, 4), (0, 1), (10, 12))[0]
    # A host kill outside both repositories is a FAIL too, and so is no kill at all.
    assert not r.oom_isolation_verdict((3, 4), (0, 0), (10, 12))[0]
    assert not r.oom_isolation_verdict((3, 3), (0, 0), (10, 10))[0]
    assert not r.oom_isolation_verdict((None, 4), (0, 0), (10, 11))[0]


def test_started_at_and_main_pid() -> None:
    text = "/app 2026-11-05T10:00:00Z\n/db 2026-11-05T10:00:01Z\n/alloc 2026-11-05T11:00:00Z\n"
    before = r.started_at(text)
    assert before == {
        "app": "2026-11-05T10:00:00Z",
        "db": "2026-11-05T10:00:01Z",
        "alloc": "2026-11-05T11:00:00Z",
    }
    after = dict(before)
    del after["alloc"]
    assert r.kept_started_verdict(before, after, skip="alloc")[0]
    after["db"] = "2026-11-05T12:00:00Z"
    assert not r.kept_started_verdict(before, after, skip="alloc")[0]
    assert not r.kept_started_verdict({}, {})[0], "an empty listing proves nothing"
    assert r.parse_main_pid("MAINPID=4242\n") == 4242
    assert r.parse_main_pid("MAINPID=0\n") is None


def test_findmnt_and_statfs() -> None:
    line = (
        "%s tmpfs rw,nosuid,nodev,relatime,size=524288k,mode=770,uid=1001,gid=1001,noswap" % TARGET
    )
    assert r.ram_mounted(line, TARGET) == (True, r.RAM_SIZE)
    probe = "findmnt %s|tmpfs|rw,size=524288k,mode=770" % TARGET
    assert r.probe_up_verdict(probe + "\nrestored 209715200\n", TARGET)[0]
    assert not r.probe_up_verdict("findmnt \n", TARGET)[0], "up() saw no tmpfs"
    assert not r.probe_up_verdict(probe.replace("524288k", "1048576k"), TARGET)[0]
    assert r.tmpfs_size("rw,size=1g") == r.GIB
    assert r.parse_statfs("131072 80000 4096") == (536870912, 209190912)
    assert r.parse_statfs("garbage") is None


def test_unmount_verdicts_and_control() -> None:
    assert r.unmounted_verdict("", TARGET)[0]
    # CONTROL: a listing with `.ram` still mounted after the unmount is FAIL.
    still = "%s tmpfs rw,size=524288k" % TARGET
    assert not r.unmounted_verdict(still, TARGET)[0]
    assert r.down_line_verdict("down findmnt %s|tmpfs\n" % TARGET)[0]
    assert not r.down_line_verdict("down findmnt \n")[0], "down() ran after the volume was gone"
    assert not r.down_line_verdict("")[0]


def test_shmem_verdict() -> None:
    assert r.shmem_verdict(220200960, 0, r.RESTORE_BYTES)[0]
    assert not r.shmem_verdict(1000, 220200960, r.RESTORE_BYTES)[0], (
        "charged to renet-exec, not the repository"
    )
    assert not r.shmem_verdict(None, None, r.RESTORE_BYTES)[0]


def test_grant_and_marker_readers() -> None:
    show = 'time="x" level=info msg="y"\n{\n  "version": 1,\n  "limits": {"memory_max": 1610612736}\n}\n'
    assert r.grant_memory_max(show) == r.C_MEMORY_RAISED
    assert r.grant_memory_max("{}") is None
    assert (
        r.marker_mounted_at('{"boot_id":"b","mounted_at":"2026-11-05T12:00:00Z","size":1}')
        == "2026-11-05T12:00:00Z"
    )
    assert r.marker_mounted_at("cat: no such file") is None


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_probe_rediaccfile_and_commands_are_valid_shell() -> None:
    for script in (r.probe_rediaccfile(), r.cgroup_readout_script(3200), r.findmnt_script(MOUNT)):
        assert subprocess.run(["bash", "-n"], input=script, text=True, check=False).returncode == 0
    assert "head -c 2147483648 /dev/zero | tail" in r.alloc_command("vmc-k2-alloc-x")
    assert "%s/data:/data" % TARGET in r.writer_command(MOUNT)


# The rows vm:check run vmc-11060119-8cbbc0 recorded, read back through the verdicts.


def test_limits_verdict_refuses_an_empty_glob_and_a_missing_holder() -> None:
    """K2.1 read `oom.group={'*': ''}`: the glob matched no directory (C ran no container) and echoed itself."""
    empty = READOUT_C.split("== oom.group keep", maxsplit=1)[0] + "== oom.group *\n\n"
    assert not r.limits_verdict(empty, r.C_MEMORY_MAX, r.CPU_ONE_CORE)[0]
    no_leaf = READOUT_C.split("== oom.group %s" % LEAF, maxsplit=1)[0]
    assert not r.limits_verdict(no_leaf, r.C_MEMORY_MAX, r.CPU_ONE_CORE)[0], (
        "the ad-hoc leaf is part of K2.1"
    )
    no_keep = READOUT_C.replace("== oom.group keep\n1\n", "")
    assert not r.limits_verdict(no_keep, r.C_MEMORY_MAX, r.CPU_ONE_CORE)[0]
    assert '[ -d "$s" ] || continue' in r.cgroup_readout_script(3200)


def test_oom_isolation_counts_the_memcg_kill_on_the_host_too() -> None:
    """K2.2 read `C 0->1 D 0->0 host 0->1`: /proc/vmstat oom_kill counts memcg kills, so a host delta equal to C's is the pass, and the row failed on its empty StartedAt baselines instead."""
    assert r.oom_isolation_verdict((0, 1), (0, 0), (0, 1))[0]
    assert not r.oom_isolation_verdict((0, 1), (0, 0), (0, 2))[0], "a kill outside C"
    ok, why = r.kept_started_verdict({}, {})
    assert not ok
    assert why == "moved: none", "an empty baseline reads `moved: none` and still fails"


def test_holder_commands() -> None:
    keep = r.keep_command(
        "vmc-k2-keep-x", r.service_parent(28992, r.KEEP_SERVICE), r.HOLD_SHM_BYTES
    )
    assert "--cgroup-parent /rediacc.slice/rediacc-28992/keep" in keep
    assert "head -c %d /dev/zero > /dev/shm/hold" % r.HOLD_SHM_BYTES in keep
    assert r.HOLD_SHM_BYTES > 16 * r.MIB, "K2.4 needs usage above the refused 16M"
    adhoc = r.keep_command("vmc-k2-adhoc-x")
    assert "--cgroup-parent" not in adhoc
    assert "exec sleep" in adhoc
    for command in (keep, adhoc):
        assert subprocess.run(["sh", "-n"], input=command, text=True, check=False).returncode == 0


def test_k3_compose_body_names_a_service() -> None:
    """K3.0 failed `renet compose up -d: no compose file found`: the probe's up() needs a compose file in the empty fork."""
    body = r.compose_body()
    assert body.startswith("services:\n  keep:\n")
    assert "image: %s" % r.IMAGE in body
    assert r.COMPOSE_FILE == "docker-compose.yml"
