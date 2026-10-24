"""The I1 tenant-isolation drill (agent/plans/PLAN-sandbox-tenant-separation.md, DR): its CLI-free helpers, its registration in vm_check through EXTRA_RENET_STEPS, and the live step's row and teardown sequence against a scripted context. The live rows themselves run on the ops VMs through `npm run vm:check -- --only I1`."""

from __future__ import annotations

import io
import json
import os
import pathlib
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.drills import tenant_isolation as ti
from rediacc_ci.drills import vm_check, vm_ssh
from rediacc_ci.drills import vm_check_receipt as receipt_mod
from rediacc_ci.tests import test_drills_vm_check as harness
from rediacc_ci.well_known import DATASTORE_PATH, RUNTIME_DIR

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

GUID_A = "11111111-2222-4333-8444-555555555555"
GUID_B = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
GUID_C = "99999999-8888-4777-8666-555555555555"

# --------------------------------------------------------------------------- pure helpers


@pytest.mark.parametrize(
    ("nid", "offset", "want"),
    [
        (2816, 0, "127.0.11.0"),
        (2816, 2, "127.0.11.2"),
        (2816, 60, "127.0.11.60"),
        # The third octet carries: 65472 + 62 = 65534 = 0.255.254.
        (65472, 62, "127.0.255.254"),
        # The second octet: 65536 = 1.0.0.
        (65536, 5, "127.1.0.5"),
    ],
)
def test_ip_at_offset_is_the_gates_inverse(nid: int, offset: int, want: str) -> None:
    assert ti.ip_at_offset(nid, offset) == want
    assert ti.subnet_base(nid) == ti.ip_at_offset(nid, 0)


def test_names_and_paths() -> None:
    assert ti.net_group(2816) == "rediacc-net-2816"
    assert ti.exec_cgroup(2816) == "/sys/fs/cgroup/rediacc.slice/renet-exec-2816"
    assert ti.repo_cgroup_rel(2816) == "rediacc.slice/rediacc-2816"
    assert ti.repo_cgroup_rel(2816, "web") == "rediacc.slice/rediacc-2816/web"


def test_service_name_fits_the_gates_service_dir_pattern() -> None:
    name = ti.service_name("vmc-10241200-abcdef")
    assert name == "vmc-i1-10241200-abcdef"
    assert ti.service_name("vmc-10241200-abcdef", "c") == "vmc-i1c-10241200-abcdef"
    assert len(name) <= 63
    assert name[0].isalnum()


def test_fork_c_tag_keeps_the_sweep_pattern() -> None:
    tags = vm_check.fork_tags("10241200", "abcdef")
    c = ti.fork_c_tag(tags)
    assert c == "vmc-10241200-abcdef-c"
    assert vm_check.FORK_TAG.match(c), "the stale-fork sweep must recognise fork C"
    assert c not in tags


def test_sleep_seconds_is_unique_per_row_and_stable() -> None:
    a = ti.sleep_seconds("vmc-1-x", 1)
    assert a == ti.sleep_seconds("vmc-1-x", 1)
    assert a != ti.sleep_seconds("vmc-1-x", 2)
    assert 600000 <= a < 900000


def test_compose_body_names_the_service_and_image() -> None:
    body = ti.compose_body("vmc-i1-x")
    assert "  vmc-i1-x:\n" in body
    assert "image: %s" % ti.IMAGE in body


@pytest.mark.parametrize(
    ("text", "ok", "fragment"),
    [
        ("rediacc rediacc-net-7\n", True, "groups: rediacc rediacc-net-7"),
        ("rediacc docker rediacc-net-7", False, "holds docker"),
        ("rediacc rediacc-net-7 rediacc-net-9", False, "holds rediacc-net-9"),
        ("rediacc", False, "no rediacc-net-7"),
        ("", False, "<none>"),
    ],
)
def test_groups_verdict(text: str, ok: bool, fragment: str) -> None:
    got, why = ti.groups_verdict(text, 7, 9)
    assert got is ok
    assert fragment in why


def test_denied_and_eperm() -> None:
    assert ti.denied(
        "permission denied while trying to connect to the Docker daemon socket at unix:///x"
    )
    assert not ti.denied("Cannot connect to the Docker daemon")
    assert ti.eperm("nc: can't connect to remote host (127.0.11.60): Operation not permitted")
    assert not ti.eperm("nc: can't connect to remote host (127.0.11.60): Connection refused")


@pytest.mark.parametrize(
    ("text", "want"),
    [("403\n", 403), ("curl: noise\n200", 200), ("NOCG\n", None), ("", None), ("4031", None)],
)
def test_http_status(text: str, want: int | None) -> None:
    assert ti.http_status(text) == want


def _inspection(nid: int, entries: list[dict[str, Any]], orphans: int = 0) -> str:
    doc = {
        "network_id": nid,
        "map_pinned": True,
        "gate_seeding": "active",
        "entries": entries,
        "orphans": [{"cgroup": ""}] * orphans,
        "count": len(entries) + orphans,
    }
    return "renet: log line\n" + json.dumps(doc, indent=2) + "\n"


def _entry(cgroup: str, nid: int, service_ip: str = "") -> dict[str, Any]:
    return {
        "cgroup": cgroup,
        "cgroup_id": 1,
        "service_ip": service_ip,
        "subnet_base": ti.subnet_base(nid),
    }


def test_parse_inspection_reads_indented_json_after_noise() -> None:
    doc = ti.parse_inspection(_inspection(64, [_entry("/rediacc.slice/rediacc-64", 64)], 1))
    assert doc is not None
    assert ti.inspection_count(doc) == 2
    assert ti.parse_inspection("not json") is None
    assert ti.parse_inspection('{"other": 1}') is None
    assert ti.inspection_count(None) is None


def test_service_entry_verdict_wants_default_and_labelled_service() -> None:
    nid = 2816
    ip = ti.ip_at_offset(nid, 2)
    good = ti.parse_inspection(
        _inspection(
            nid,
            [
                _entry("/rediacc.slice/rediacc-%d" % nid, nid),
                _entry("rediacc.slice/rediacc-%d/svc" % nid, nid, ip),
            ],
        )
    )
    ok, why = ti.service_entry_verdict(good, nid, "svc", ip)
    assert ok, why
    # No default entry.
    only_service = ti.parse_inspection(
        _inspection(nid, [_entry("/rediacc.slice/rediacc-%d/svc" % nid, nid, ip)])
    )
    ok, why = ti.service_entry_verdict(only_service, nid, "svc", ip)
    assert not ok
    assert "no default entry" in why
    # The service entry carries another address than the label.
    ok, why = ti.service_entry_verdict(good, nid, "svc", ti.ip_at_offset(nid, 3))
    assert not ok
    assert "service_ip" in why
    # A label the container never got.
    ok, _why = ti.service_entry_verdict(good, nid, "svc", "")
    assert not ok
    # Another network's subnet.
    foreign = ti.parse_inspection(
        _inspection(
            nid,
            [
                _entry("/rediacc.slice/rediacc-%d" % nid, nid),
                {
                    **_entry("/rediacc.slice/rediacc-%d/svc" % nid, nid, ip),
                    "subnet_base": "127.0.0.64",
                },
            ],
        )
    )
    ok, why = ti.service_entry_verdict(foreign, nid, "svc", ip)
    assert not ok
    assert "service subnet" in why
    assert ti.service_entry_verdict(None, nid, "svc", ip) == (False, "no inspection JSON")


MOUNTINFO = f"""\
22 1 0:21 / / rw,relatime - btrfs /dev/sda1 rw
40 22 0:33 / {DATASTORE_PATH}/mounts/%(a)s rw,relatime - ext4 /dev/mapper/a rw
41 40 0:34 / {DATASTORE_PATH}/mounts/%(a)s/sub rw,relatime - ext4 /dev/mapper/a2 rw
50 22 0:35 /mounts/%(b)s /srv/elsewhere rw - btrfs /dev/sda1 rw
"""


def test_mount_guids_reads_mount_points_only() -> None:
    text = MOUNTINFO % {"a": GUID_A, "b": GUID_B}
    # B's guid appears only in field 4 (the root inside its filesystem), never as a mount point.
    assert ti.mount_guids(text) == [GUID_A]
    leaked = text + f"60 22 0:36 / {DATASTORE_PATH}/mounts/%s rw - ext4 /dev/mapper/b rw\n" % GUID_B
    assert ti.mount_guids(leaked) == [GUID_A, GUID_B]
    assert ti.mount_guids("") == []


def test_split_sections() -> None:
    assert ti.split_sections("pid:[1]\n===\nmounts\n") == ["pid:[1]\n", "mounts\n"]
    assert ti.split_sections("") == [""]


GO_PASS = """=== RUN   TestEBPF_DeepestEntryWins
--- PASS: TestEBPF_DeepestEntryWins (0.10s)
=== RUN   TestEBPF_RepoDefaultBlocksCrossRepo
--- PASS: TestEBPF_RepoDefaultBlocksCrossRepo (0.20s)
PASS
"""


def test_go_test_verdict_needs_every_named_pass() -> None:
    ok, why = ti.go_test_verdict(
        GO_PASS, ("TestEBPF_DeepestEntryWins", "TestEBPF_RepoDefaultBlocksCrossRepo")
    )
    assert ok, why
    ok, why = ti.go_test_verdict(GO_PASS, ("TestEBPF_DeepestEntryWins", "TestEBPF_Bind4"))
    assert not ok
    assert "TestEBPF_Bind4 did not run" in why
    # A prefix of another test's name is not that test.
    ok, _ = ti.go_test_verdict(GO_PASS, ("TestEBPF_Deepest",))
    assert not ok


def test_go_test_verdict_a_skip_is_a_failure_with_its_reason() -> None:
    out = (
        "=== RUN   TestPrivateRepoViewLinux\n"
        "--- SKIP: TestPrivateRepoViewLinux (0.00s)\n"
        "    sandbox_repo_view_linux_test.go:274: the private repository view needs root or passwordless sudo\n"
        "PASS\n"
    )
    ok, why = ti.go_test_verdict(out, ("TestPrivateRepoViewLinux",))
    assert not ok
    assert "skipped" in why
    assert "needs root" in why
    ok, why = ti.go_test_verdict(
        "--- FAIL: TestPrivateRepoViewLinux (1s)\nFAIL\n", ("TestPrivateRepoViewLinux",)
    )
    assert not ok
    assert "failed" in why


def test_build_tests_script_builds_every_root_test_outside_bin() -> None:
    script = ti.build_tests_script("/r/private/renet", "/w/tests")
    assert script.startswith("set -eu\ncd /r/private/renet\n")
    for _label, binary, package, tags, _names in ti.ROOT_TESTS:
        assert "go test -c -tags '%s' -o /w/tests/%s %s" % (tags, binary, package) in script or (
            "go test -c -tags %s -o /w/tests/%s %s" % (tags, binary, package) in script
        )
    assert "/bin/renet" not in script
    tag_set = {t for _l, _b, _p, t, _n in ti.ROOT_TESTS}
    assert "nolicense ebpf_e2e" in tag_set


def test_root_test_script_stages_privately_and_cleans_up() -> None:
    script = ti.root_test_script(
        f"{DATASTORE_PATH}/mounts/g/vmc-i1-tests/x.test", "x.test", ("TestA", "TestB"), 600
    )
    assert f"test -f {DATASTORE_PATH}/mounts/g/vmc-i1-tests/x.test" in script
    assert "mktemp -d /var/tmp/vmc-i1-XXXXXX" in script
    assert "trap 'rm -rf \"$stage\"' EXIT" in script
    assert "-test.run '^(TestA|TestB)$'" in script
    assert "-test.count=1 -test.v -test.timeout=600s" in script
    # Never installed where the renet binary lives.
    assert "/usr/local/bin" not in script


def test_process_scripts_anchor_the_pattern() -> None:
    for script in (ti.alive_script(612345), ti.job_view_script(612345), ti.absent_script(612345)):
        assert "pgrep -f '^sleep 612345$'" in script
    assert "pkill -f '^sleep 612345$'" in ti.ns_gone_script(612345, "pid:[4026532800]")
    assert "pgrep -f '^sleep 612346$'" in ti.absent_script(612345)
    assert "echo PGREP_RC=$r" in ti.absent_script(612345)


def test_absent_verdict_needs_the_control_and_a_not_found_search() -> None:
    assert ti.absent_verdict("CONTROL_SEEN\nPGREP_RC=1\n")[0]
    # Found the job: not absent.
    assert not ti.absent_verdict("CONTROL_SEEN\nPGREP_RC=0\n")[0]
    # pgrep could not look (control unseen): never read as absent (review 55ab6cf1.1).
    assert not ti.absent_verdict("CONTROL_MISSING\nPGREP_RC=1\n")[0]
    # pgrep failed outright (status 2), or the marker never printed.
    assert not ti.absent_verdict("CONTROL_SEEN\nPGREP_RC=2\n")[0]
    assert not ti.absent_verdict("CONTROL_SEEN\n")[0]


def test_job_view_verdict_returns_the_namespace_when_only_the_view_fails() -> None:
    text = (
        "pid:[4026532800]\n===\npid:[4026531836]\n===\n"
        f"60 22 0:36 / {DATASTORE_PATH}/mounts/%s rw - ext4 x rw\n" % GUID_B
    )
    ok, _why, ns = ti.job_view_verdict(text, GUID_B)
    assert not ok
    assert ns == "pid:[4026532800]"
    # The worker's namespace unread: nothing proves the job's differs, so none counts (review 661409e8.2).
    unread = text.replace("pid:[4026531836]", "")
    assert ti.job_view_verdict(unread, GUID_B)[2] == ""


def test_ns_gone_script_waits_for_no_process_in_the_namespace() -> None:
    script = ti.ns_gone_script(612345, "pid:[4026532800]", tries=3)
    assert "for i in $(seq 3)" in script
    # The namespace is quoted: its brackets are a glob otherwise.
    assert "= 'pid:[4026532800]' ]" in script
    assert "/proc/[0-9]*/ns/pid" in script
    assert "echo NSGONE; exit 0" in script
    assert script.rstrip().endswith("exit 1")
    # The kill comes first, so the wait is for the namespace to end with the job.
    assert script.index("pkill") < script.index("for i in")


JOB_NS, HOST_NS = "pid:[4026532800]", "pid:[4026531836]"


def _job_view(job_ns: str = JOB_NS, host_ns: str = HOST_NS, extra: str = "") -> str:
    return "%s\n===\n%s\n===\n%s%s" % (
        job_ns,
        host_ns,
        MOUNTINFO % {"a": GUID_A, "b": GUID_B},
        extra,
    )


def test_job_view_script_reads_the_jobs_namespace_and_mounts() -> None:
    script = ti.job_view_script(612345)
    assert 'readlink "/proc/$p/ns/pid"' in script
    assert "readlink /proc/self/ns/pid" in script
    assert 'cat "/proc/$p/mountinfo"' in script
    assert "echo NOJOB; exit 3" in script


def test_job_view_verdict() -> None:
    ok, why, ns = ti.job_view_verdict(_job_view(), GUID_B)
    assert ok, why
    assert ns == JOB_NS
    # The job in the worker's own namespace: the view was never built.
    ok, why, ns = ti.job_view_verdict(_job_view(job_ns=HOST_NS), GUID_B)
    assert not ok
    assert ns == ""
    assert "worker's PID namespace" in why
    # B's mount in the job's view.
    leaked = f"60 22 0:36 / {DATASTORE_PATH}/mounts/%s rw - ext4 x rw\n" % GUID_B
    ok, why, ns = ti.job_view_verdict(_job_view(extra=leaked), GUID_B)
    assert not ok
    assert ns == JOB_NS
    assert GUID_B in why
    # Nothing read (a failed probe, NOJOB) proves nothing.
    for text in ("", "NOJOB\n"):
        ok, why, ns = ti.job_view_verdict(text, GUID_B)
        assert not ok
        assert ns == ""
        assert "no namespaces read" in why


def test_peer_curl_script_moves_into_the_cgroup_first() -> None:
    script = ti.peer_curl_script(
        "/sys/fs/cgroup/rediacc.slice/renet-exec-7", f"{RUNTIME_DIR}/net-9/docker-9.sock"
    )
    assert script.index("cgroup.procs") < script.index("curl")
    assert f"--unix-socket {RUNTIME_DIR}/net-9/docker-9.sock http://localhost/_ping" in script
    assert "echo NOCG; exit 3" in script


def test_tcp_connect_script() -> None:
    script = ti.tcp_connect_script("127.0.11.60", 47123)
    assert "/dev/tcp/127.0.11.60/47123" in script
    assert "echo CONNECTED" in script


# --------------------------------------------------------------------------- registration


def test_step_shape() -> None:
    step_id, deps, fn = ti.STEP
    assert step_id == "I1"
    assert deps == ("V1.2",)
    assert fn is ti.run


def test_vm_check_registers_i1_once() -> None:
    assert ti.STEP in vm_check.EXTRA_RENET_STEPS
    assert [s[0] for s in vm_check.EXTRA_RENET_STEPS].count("I1") == 1
    renet = vm_check.PHASE_STEPS[vm_check.SIDE_RENET]
    assert renet.count("I1") == 1
    # After U1: the order the run calls the steps in.
    assert renet.index("I1") > renet.index("U1")


def test_only_i1_drags_in_v12_and_its_own_dependencies() -> None:
    assert set(vm_check.VmCheck._ONLY_DEPS["I1"]) == {"V1.2", "P5", "V1.1"}


def test_only_deps_closes_transitively_and_terminates_on_cycles() -> None:
    base = {"V1.1": ("P5",), "V1.2": ("P5", "V1.1"), "X": ("Y",), "Y": ("X",)}
    got = vm_check.only_deps(base, [("I9", ("V1.2",), None), ("Z", ("X",), None)])
    assert got["I9"] == ("V1.2", "P5", "V1.1")
    assert set(got["Z"]) == {"X", "Y"}
    assert got["V1.1"] == ("P5",), "the base entries are untouched"


def _main(
    tmp_path: pathlib.Path,
    world: Any,
    argv: Sequence[str],
    extra_fns: Mapping[str, Any],
    u1: Any = harness.stub_u1,
) -> tuple[int, str, dict[str, Any]]:
    out = io.StringIO()
    environ = {
        "HOME": str(tmp_path / "home"),
        "PATH": os.environ.get("PATH", ""),
        "VM_NET_BASE": harness.NET,
    }
    rc = vm_check.main(
        [*argv, "--keep-work", "--wait", "0"],
        root=world.root,
        host=world,
        account=harness.FakeAccount(),
        lock=vm_check.Lock(tmp_path / "vm-check.lock"),
        out=out,
        environ=environ,
        inputs_fn=lambda _root: harness.DIGEST,
        account_modified_fn=lambda _root: False,
        account_digest_fn=lambda _root: harness.ADIGEST,
        u1_fn=u1,
        extra_fns=extra_fns,
    )
    latest = world.root / receipt_mod.CACHE_DIR / receipt_mod.LATEST
    receipt = json.loads(latest.read_text()) if latest.exists() else {}
    return rc, out.getvalue(), receipt


def test_only_i1_runs_v12_then_i1(tmp_path: pathlib.Path) -> None:
    world = harness.make_world(tmp_path, stored_ok=True)
    seen: list[str] = []

    def stub(check: Any) -> None:
        # The forks V1.1 made are in hand when I1 starts.
        seen.append("I1 forks=%d" % len(check.guids))
        check.check("I1", "stub I1", True)

    _rc, out, receipt = _main(tmp_path, world, ["--only", "I1"], {"I1": stub})
    assert receipt == {}, "a --only run writes no receipt.json"
    assert seen == ["I1 forks=2"]
    ids = [ln.split()[0] for ln in out.splitlines() if ln.startswith("  ")]
    assert "V1.2" in ids
    assert "I1" in ids
    assert ids.index("V1.2") < ids.index("I1")
    assert "V1.3" not in ids
    assert "U1" not in ids


def test_a_full_run_calls_i1_after_u1_and_needs_its_row(tmp_path: pathlib.Path) -> None:
    order: list[str] = []

    def u1(check: Any) -> None:
        order.append("U1")
        check.check("U1", "stub U1", True)

    def i1(check: Any) -> None:
        order.append("I1")
        check.check("I1", "stub I1", True)

    world = harness.make_world(tmp_path)
    rc, out, receipt = _main(tmp_path, world, [], {**harness.STUB_EXTRA, "I1": i1}, u1=u1)
    assert order == ["U1", "I1"]
    assert rc == vm_check.EXIT_VERIFIED, out
    assert receipt["status"] == receipt_mod.VERIFIED


def test_a_full_run_whose_i1_records_nothing_is_not_verified(tmp_path: pathlib.Path) -> None:
    world = harness.make_world(tmp_path)
    rc, out, receipt = _main(tmp_path, world, [], {**harness.STUB_EXTRA, "I1": lambda _check: None})
    assert rc != vm_check.EXIT_VERIFIED, out
    assert receipt.get("status") != receipt_mod.VERIFIED


# --------------------------------------------------------------------------- the live step, scripted


class Res:
    def __init__(self, rc: int = 0, out: str = "", err: str = "") -> None:
        self.rc, self.out, self.err, self.ms = rc, out, err, 0

    def text(self) -> str:
        return (self.out + "\n" + self.err).strip()


class Opts:
    parent = "vmcheck-base"


class FakeCtx:
    """The slice of VmCheck the I1 step drives, answering each command from the fixed behaviour (or from `broken`, a set of row keys that answer the defect)."""

    def __init__(self, work: pathlib.Path, broken: frozenset[str] = frozenset()) -> None:
        self.run_id = "vmc-10241200-abcdef"
        self.tags = vm_check.fork_tags("10241200", "abcdef")
        self.network_ids = {self.tags[0]: "2816", self.tags[1]: "2880"}
        self.guids = {self.tags[0]: GUID_A, self.tags[1]: GUID_B}
        self.work = work
        self.root = work / "repo"
        self.environ: dict[str, str] = {}
        self.ssh_user, self.ssh_key, self.worker_ip = "u", "/k", "192.168.111.11"
        self.opts = Opts()
        self.forks: list[dict[str, Any]] = [
            {"tag": t, "guid": g, "created": True, "deleted": False}
            for t, g in ((self.tags[0], GUID_A), (self.tags[1], GUID_B))
        ]
        self.sweep_leftovers: list[str] = []
        self.connection = ""
        self.rows: list[tuple[str, str, bool | None]] = []
        self.calls: list[str] = []
        self.broken = broken
        self.c_deleted = False
        self.label_ip = ti.ip_at_offset(2880, 2)

    # VmCheck's ledger
    def check(self, step_id: str, desc: str, ok: bool, *_a: Any, **_kw: Any) -> bool:
        self.rows.append((step_id, desc, bool(ok)))
        return bool(ok)

    def record(self, step_id: str, desc: str, ok: bool | None, *_a: Any, **_kw: Any) -> bool:
        self.rows.append((step_id, desc, ok))
        return bool(ok)

    def scrub(self, text: str) -> str:
        return text

    def remote_evidence(self, res: Any) -> str:
        return "rc=%d" % res.rc

    def purge_licences(self, guids: Sequence[str], what: str) -> str:
        self.calls.append("purge %s %s" % (",".join(guids), what))
        return ""

    def keep_log(self, *_a: Any) -> str:
        return ""

    def ref(self, tag: str) -> str:
        return "%s:%s" % (self.opts.parent, tag)

    def repo_list(self) -> tuple[Res, list[dict[str, Any]]]:
        entries = [
            {"name": self.ref(t), "guid": self.guids[t], "networkId": int(n)}
            for t, n in self.network_ids.items()
        ]
        if not self.c_deleted:
            entries.append(
                {"name": self.ref(ti.fork_c_tag(self.tags)), "guid": GUID_C, "networkId": 2944}
            )
        return Res(0, json.dumps({"data": entries})), entries

    # Commands
    def shell(self, ref: str, command: str, *_a: Any, **_kw: Any) -> Res:
        return self.rdc("term", "connect", ref, "-c", command)

    def rdc(self, *args: str, **_kw: Any) -> Res:
        line = " ".join(args)
        self.calls.append("rdc " + line)
        b = self.broken
        if args[:2] == ("repo", "delete"):
            # `undeleted`: the delete answers rc 0 and the fork stays listed.
            self.c_deleted = "undeleted" not in b
            return Res()
        if args[:1] == ("vscode",):
            return Res(0, ti.URI_PREFIX + "alias-a/mnt\n")
        if "id -Gn" in line:
            return Res(
                0,
                "rediacc rediacc-net-2816 docker\n"
                if "groups" in b
                else "rediacc rediacc-net-2816\n",
            )
        if "version" in line and "net-2880" in line:
            return Res(1, "", "permission denied while trying to connect")
        if "--format" in line:
            return Res(0, self.label_ip + "\n")
        if "nc -vv -w 3" in line:
            if "connect" in b:
                self.received = line.split("echo ", 1)[1].split(" ", 1)[0]
                return Res(0, "NC_RC=0\n")
            return Res(
                0,
                "nc: 127.0.42.60 (127.0.42.60:47123): Operation not permitted\nsent 0, rcvd 0\nNC_RC=1\n",
            )
        if "docker logs" in line:
            return Res(0, getattr(self, "received", "") + "\n")
        if "/dev/tcp" in line:
            return Res(0, "CONNECTED\n")
        if "mountinfo" in line:
            extra = (
                f"60 22 0:36 / {DATASTORE_PATH}/mounts/%s rw - ext4 x rw\n" % GUID_B
                if "mounts" in b
                else ""
            )
            return Res(
                0, "pid:[4026532999]\n===\n" + MOUNTINFO % {"a": GUID_A, "b": GUID_B} + extra
            )
        if "echo PGREP_RC=" in line:
            # `visible`: a session sees another session's lingering job.
            return Res(0, "CONTROL_SEEN\nPGREP_RC=%d\n" % (0 if "visible" in b else 1))
        if "nohup sleep" in line:
            return Res(0, "STARTED\n")
        if "test -f" in line and ".vscode-server/.vmc-i1-" in line:
            # `wipe`: the second connect removed what the first prepared.
            return Res(1) if "wipe" in b else Res()
        return Res()

    def host_run(self, argv: Sequence[str], **_kw: Any) -> Res:
        command = argv[-1]
        self.calls.append("host " + command)
        if argv[:2] == ["bash", "-c"]:
            out_dir = pathlib.Path(command.split(" -o ")[1].split()[0]).parent
            out_dir.mkdir(parents=True, exist_ok=True)
            for _l, binary, _p, _t, _n in ti.ROOT_TESTS:
                (out_dir / binary).write_bytes(b"\x7fELF")
            return Res()
        if "renet-exec-2816" in command:
            return Res(0, "200\n" if "peer" in self.broken else "403\n")
        if "/_ping" in command:
            return Res(0, "200\n")
        if "ebpf inspect" in command:
            if "2944" in command:
                entries = [] if self.c_deleted else [_entry("/rediacc.slice/rediacc-2944", 2944)]
                return Res(0, _inspection(2944, entries))
            return Res(
                0,
                _inspection(
                    2880,
                    [
                        _entry("/rediacc.slice/rediacc-2880", 2880),
                        _entry(
                            "/rediacc.slice/rediacc-2880/" + ti.service_name(self.run_id),
                            2880,
                            self.label_ip,
                        ),
                    ],
                ),
            )
        if argv[:2] == ["ssh", "-F"] and argv[2] != "/dev/null":
            # The VS Code alias channel; `slowalias`: it returns only when its job ends.
            res = Res()
            res.ms = 40000 if "slowalias" in self.broken else 1200
            return res
        if "NOJOB" in command:
            # `nsview`: the job runs in the worker's own PID namespace.
            return Res(0, _job_view(job_ns=HOST_NS if "nsview" in self.broken else JOB_NS))
        if "NSGONE" in command:
            # `nslingers`: a process still holds the job's namespace.
            if "nslingers" in self.broken:
                return Res(1, "NSLINGERS /proc/77/ns/pid\n")
            return Res(0, "NSGONE\n")
        if "echo ALIVE" in command:
            # `lingerdies`: the job died with its session (the defect of vmc-10241051-440c3f I1.8).
            if "lingerdies" in self.broken:
                return Res(1, "GONE\n")
            return Res(0, "ALIVE\n")
        if "readlink /proc/self/ns/pid" in command:
            return Res(0, "pid:[4026531836]\n")
        if "pkill" in command and "! pgrep" in command and "ssh-cleanup" in self.broken:
            return Res(vm_ssh.SSH_FAILED, "", "ssh: connect to host: Connection timed out")
        if "test -d /sys/fs/cgroup" in command:
            return Res(0, "ABSENT\n")
        if "getent group" in command:
            return Res(0, "rc=2\n")
        if "-test.run" in command:
            names = [n for _l, b, _p, _t, ns in ti.ROOT_TESTS for n in ns if b in command]
            return Res(0, "".join("--- PASS: %s (0.1s)\n" % n for n in names) + "PASS\n")
        return Res()

    def say(self, text: str = "") -> None:
        pass


def test_the_live_step_passes_on_the_fixed_behaviour_and_tears_down(tmp_path: pathlib.Path) -> None:
    ctx = FakeCtx(tmp_path)
    ti.run(ctx)
    failed = [d for s, d, ok in ctx.rows if ok is False]
    assert not failed, failed
    assert {s for s, _d, _ok in ctx.rows} == {"I1"}
    descs = " | ".join(d for _s, d, _ok in ctx.rows)
    for row in (
        "I1.1",
        "I1.2",
        "I1.3",
        "I1.4",
        "I1.5",
        "I1.6",
        "I1.7",
        "I1.8",
        "I1.R RB",
        "I1.R RC",
    ):
        assert row in descs, row
    # Fork C, deleted and confirmed gone by I1.7, left the run's forks, so teardown never deletes it twice; I1 purged its licence state instead.
    assert ti.fork_c_tag(ctx.tags) not in [f["tag"] for f in ctx.forks]
    assert [c for c in ctx.calls if c.startswith("purge %s " % GUID_C)]
    assert len([c for c in ctx.calls if c.startswith("rdc repo delete ")]) == 1
    # The VS Code rows: two connects, the marker placed after the first and found after the second.
    assert len([c for c in ctx.calls if c.startswith("rdc vscode connect")]) == 2
    assert any("a second rdc vscode connect keeps" in d and ok for _s, d, ok in ctx.rows)
    # The cleanup removed the listener and B's compose service and killed the sleeps; nothing was left.
    assert any("docker rm -f vmc-i1-listen-" in c for c in ctx.calls)
    assert any("renet compose -- down" in c for c in ctx.calls)
    assert any("pkill -f" in c for c in ctx.calls)
    assert ctx.sweep_leftovers == []
    assert not (tmp_path / ("i1-%s" % ctx.run_id)).exists()
    # The test binaries reached the worker through rdc's sync, never scp.
    uploads = [
        c
        for c in ctx.calls
        if c.startswith("rdc repo sync upload " + ctx.ref(ti.fork_c_tag(ctx.tags)))
    ]
    assert uploads
    assert not [c for c in ctx.calls if "scp " in c]
    # The VS Code lifetime row is a skip without V1.6/V1.7's alias config, never a silent pass.
    assert any(ok is None and "VS Code server lifetime not run" in d for _s, d, ok in ctx.rows)


@pytest.mark.parametrize(
    ("broken", "row"),
    [
        ("groups", "I1.1"),
        ("peer", "I1.3 root in renet-exec"),
        ("connect", "I1.5 a plain docker run in B"),
        ("mounts", "I1.6 A's mountinfo"),
        ("lingerdies", "I1.8 a session's nohup background job outlives its session"),
        ("nsview", "I1.8 the lingering job keeps its session's PID namespace"),
        ("visible", "I1.8 B's session does not see A's lingering job"),
        ("nslingers", "I1.8 the job's PID namespace ends with the job"),
    ],
)
def test_each_defect_is_a_fail_row(tmp_path: pathlib.Path, broken: str, row: str) -> None:
    ctx = FakeCtx(tmp_path, frozenset({broken}))
    ti.run(ctx)
    failed = [d for _s, d, ok in ctx.rows if ok is False]
    assert any(d.startswith(row) for d in failed), failed


def test_missing_forks_stop_before_any_vm_command(tmp_path: pathlib.Path) -> None:
    ctx = FakeCtx(tmp_path)
    ctx.network_ids = {}
    ti.run(ctx)
    assert [ok for _s, _d, ok in ctx.rows] == [False]
    assert not [c for c in ctx.calls if c.startswith("rdc ")]
    # No background sleep was started, so the cleanup has nothing to kill and probes nothing.
    assert not [c for c in ctx.calls if "pkill" in c]
    assert ctx.sweep_leftovers == []


def test_a_failed_cleanup_probe_is_a_leftover_not_a_pass(tmp_path: pathlib.Path) -> None:
    """Review 81e15b4f.1: an ssh failure (rc 255) during the sleep cleanup proves nothing was killed, so it must reach sweep_leftovers and keep the run from VERIFIED."""
    ctx = FakeCtx(tmp_path, frozenset({"ssh-cleanup"}))
    ti.run(ctx)
    assert len(ctx.sweep_leftovers) == 1, ctx.sweep_leftovers
    assert "root ssh probe failed (rc=255)" in ctx.sweep_leftovers[0]


def test_a_fork_c_still_listed_stays_for_teardown(tmp_path: pathlib.Path) -> None:
    """Review 81e15b4f.2: only a delete the list confirms hands C over; a C still listed stays in ctx.forks, undeleted, for the run's teardown, and the failed row says so."""
    ctx = FakeCtx(tmp_path, frozenset({"undeleted"}))
    ti.run(ctx)
    c = [f for f in ctx.forks if f["tag"] == ti.fork_c_tag(ctx.tags)]
    assert len(c) == 1
    assert c[0]["deleted"] is False
    assert not [x for x in ctx.calls if x.startswith("purge ")]
    assert any(
        d == "I1.7 fork C no longer listed after the delete" and ok is False
        for _s, d, ok in ctx.rows
    )


def test_a_second_vscode_connect_that_wipes_the_server_fails(tmp_path: pathlib.Path) -> None:
    """Review 81e15b4f.3: the server-directory row is proved across two separate connects with a marker the first left, not by a bare `test -d` after both."""
    ctx = FakeCtx(tmp_path, frozenset({"wipe"}))
    ti.run(ctx)
    failed = [d for _s, d, ok in ctx.rows if ok is False]
    assert failed == [
        "I1.8 a second rdc vscode connect keeps the prepared VS Code server directory"
    ]
    connects = [i for i, c in enumerate(ctx.calls) if c.startswith("rdc vscode connect")]
    touch = next(i for i, c in enumerate(ctx.calls) if "touch " in c and ".vmc-i1-" in c)
    assert connects[0] < touch < connects[1]


def test_dead_helpers_are_gone() -> None:
    """Review 81e15b4f.4: the unused repo-list parser was removed (the live step reads ctx.repo_list). gone_script asserted the defect I1.8 now refutes (a session's job dying with it)."""
    assert not hasattr(ti, "_data_list")
    assert not hasattr(ti, "gone_script")


def test_the_lingering_job_rows_pass_and_run_in_order(tmp_path: pathlib.Path) -> None:
    ctx = FakeCtx(tmp_path)
    ti.run(ctx)
    descs = [d for _s, d, ok in ctx.rows if ok]
    want = [
        "I1.8 a session's nohup background job outlives its session",
        "I1.8 the lingering job keeps its session's PID namespace and a view without B's mount",
        "I1.8 B's session does not see A's lingering job",
        "I1.8 a fresh A session does not see the job either (each session has its own PID namespace)",
        "I1.8 the job's PID namespace ends with the job",
    ]
    assert [d for d in descs if d in want] == want
    # The namespace probe waits on the namespace the view probe read.
    assert any("NSGONE" in c and JOB_NS in c for c in ctx.calls)
    # B is probed from B's session, the fresh A from A's.
    absent = [c for c in ctx.calls if c.startswith("rdc ") and "echo PGREP_RC=" in c]
    assert len(absent) == 2
    assert ctx.ref(ctx.tags[1]) in absent[0]
    assert ctx.ref(ctx.tags[0]) in absent[1]


def test_a_dead_job_skips_the_lingering_rows(tmp_path: pathlib.Path) -> None:
    ctx = FakeCtx(tmp_path, frozenset({"lingerdies"}))
    ti.run(ctx)
    assert not any("lingering job" in d or "namespace ends" in d for _s, d, _ok in ctx.rows)
    assert not [c for c in ctx.calls if "NOJOB" in c or "NSGONE" in c]


def test_an_unread_namespace_fails_the_namespace_row(tmp_path: pathlib.Path) -> None:
    ctx = FakeCtx(tmp_path, frozenset({"nsview"}))
    ti.run(ctx)
    assert ("I1", "I1.8 the job's PID namespace ends with the job", False) in ctx.rows
    assert not [c for c in ctx.calls if "NSGONE" in c]


ALIAS_ROW = "I1.8 the alias exec channel returned in under 30s, not when its job ends"


def _with_alias(ctx: FakeCtx) -> FakeCtx:
    ctx.connection = "alias-a"
    (ctx.work / "ssh_config").write_text("Host alias-a\n")
    return ctx


def test_the_alias_channel_returns_quickly(tmp_path: pathlib.Path) -> None:
    ctx = _with_alias(FakeCtx(tmp_path))
    ti.run(ctx)
    failed = [d for _s, d, ok in ctx.rows if ok is False]
    assert not failed, failed
    assert ("I1", ALIAS_ROW, True) in ctx.rows
    assert any("outlives its channel" in d and ok for _s, d, ok in ctx.rows)


def test_a_slow_alias_channel_fails(tmp_path: pathlib.Path) -> None:
    ctx = _with_alias(FakeCtx(tmp_path, frozenset({"slowalias"})))
    ti.run(ctx)
    failed = [d for _s, d, ok in ctx.rows if ok is False]
    assert failed == [ALIAS_ROW]


def test_nc_evidence_keeps_the_nc_docker_and_marker_lines() -> None:
    out = (
        '{"durationMs": 9}\n'
        "nc: can't connect to remote host (127.0.40.188): Operation not permitted\n"
        "docker: Error response from daemon: x\n"
        "NC_RC=1\n"
    )
    assert ti.nc_evidence(out) == (
        "nc: can't connect to remote host (127.0.40.188): Operation not permitted"
        " | docker: Error response from daemon: x | NC_RC=1"
    )
    assert ti.nc_evidence('{"x": 1}\n') == ""


EPERM_OUT = "nc: can't connect to remote host (127.0.40.188): Operation not permitted\nNC_RC=1\n"
MARK = "VMC-I1-FROM-B-abc123"


def test_cross_connect_verdict_refused_with_eperm() -> None:
    ok, why = ti.cross_connect_verdict(EPERM_OUT, "", MARK)
    assert ok
    assert "Operation not permitted" in why


def test_cross_connect_verdict_marker_in_listener_log_fails() -> None:
    ok, why = ti.cross_connect_verdict(EPERM_OUT, MARK + "\n", MARK)
    assert not ok
    assert "RECEIVED" in why


def test_cross_connect_verdict_needs_the_marker_and_a_nonzero_rc() -> None:
    eperm_only = "nc: can't connect to remote host (127.0.40.188): Operation not permitted\n"
    assert not ti.cross_connect_verdict(eperm_only, "", MARK)[0]
    assert not ti.cross_connect_verdict(eperm_only + "NC_RC=0\n", "", MARK)[0]


def test_cross_connect_verdict_silent_nc_fails() -> None:
    ok, why = ti.cross_connect_verdict("NC_RC=1\n", "", MARK)
    assert not ok
    assert "not refused" in why


def test_cross_connect_verdict_unreadable_log_fails() -> None:
    assert not ti.cross_connect_verdict(EPERM_OUT, None, MARK)[0]


def test_nc_rc_reads_the_last_marker() -> None:
    assert ti.nc_rc("NC_RC=125\n") == 125
    assert ti.nc_rc("no marker") is None


def test_cross_connect_verdict_reads_busybox_vv_output() -> None:
    out = "nc: 127.0.42.60 (127.0.42.60:47123): Operation not permitted\nsent 0, rcvd 0\nNC_RC=1\n"
    assert ti.cross_connect_verdict(out, "", MARK)[0]
    refused = "nc: 127.0.42.60 (127.0.42.60:47123): Connection refused\nsent 0, rcvd 0\nNC_RC=1\n"
    assert not ti.cross_connect_verdict(refused, "", MARK)[0]
