"""`rediacc_ci.drills.backup_renet` (legs b-d with real renet, `--renet`) against a scripted worker VM and a scripted control plane.

The VM keeps a repository image per guid as a digest, mutates it on the planted rewrite, and restores a snapshot into a target by copying the digest recorded when that snapshot was cut. The live run on the ops worker is the acceptance and belongs to the lead; these cases pin the legs' own logic and that each goes red on the defect it names.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import types
import typing

import pytest

from rediacc_ci.drills import backup, backup_renet, lib
from rediacc_ci.drills import backup_roundtrip as rt
from rediacc_ci.well_known import ACCOUNT_DEV_PORT, DATASTORE_PATH

CELL = backup.CELL_BYTES


class Worker:
    """A scripted worker: `bug` plants one defect by name."""

    def __init__(self, bug: str = "") -> None:
        self.bug = bug
        self.images: dict[str, str] = {}
        self.snaps: list[dict] = []
        self.digest_of_snap: dict[str, str] = {}
        self.commands: list[str] = []
        self.generation = 0

    def __call__(self, command: str, stdin_data: str | None = None) -> rt.VmResult:
        del stdin_data
        self.commands.append(command)
        if "renet machine-id" in command:
            return rt.VmResult(0, "mid-1\n")
        made = re.search(r"repository create --name (\S+)", command)
        if made:
            self.images[made.group(1)] = "digest-0"
        if "license-status" in command:
            return rt.VmResult(
                0, json.dumps([{"repositoryGuid": g, "status": "valid"} for g in self.images])
            )
        if "dd of=" in command:
            guid = re.search(r"/repositories/(\S+) bs=1", command)
            assert guid
            self.generation += 1
            if self.bug != "no-change":
                self.images[guid.group(1)] = "digest-%d" % self.generation
            assert "seek=%d" % (backup_renet.MUTATION_CELL * CELL + 4096) in command
            return rt.VmResult(0)
        if "sha256sum" in command:
            guid = re.search(r"/repositories/(\S+?)'?$", command.strip())
            assert guid
            return rt.VmResult(0, "%s  x\n" % self.images[guid.group(1)])
        if "backup snapshot" in command:
            guid = re.search(r"--repo (\S+)", command)
            assert guid
            first = not self.snaps
            snap = "snap-%d" % len(self.snaps)
            self.snaps.append({"id": snap})
            self.digest_of_snap[snap] = self.images[guid.group(1)]
            size = 8 * CELL if first else (2 * CELL if self.bug == "two-cells" else CELL)
            return rt.VmResult(
                0, json.dumps({"status": "stored", "snapshotId": snap, "bytesUploaded": size})
            )
        if "backup restore" in command:
            target = re.search(r"--repo (\S+)", command)
            at = re.search(r"--at (\S+)", command)
            assert target
            assert at
            wrong = self.bug == "restore-differs"
            self.images[target.group(1)] = "corrupt" if wrong else self.digest_of_snap[at.group(1)]
            return rt.VmResult(0, '{"status":"restored"}')
        return rt.VmResult(0)


class Plane:
    def __init__(self, worker: Worker) -> None:
        self.worker = worker

    def stored(self) -> int:
        total = 0
        for index, _ in enumerate(self.worker.snaps):
            total += 8 * CELL if index == 0 else CELL
        return total


class FakeApi(rt.Api):
    def __init__(self) -> None:
        super().__init__("http://127.0.0.1:1")

    def call(self, method: str, path: str, body: dict | None = None, *_a: object) -> dict:
        del method, body
        if path == "/licenses/activate-repo":
            return {"license": {"publicKeyId": "kid", "payload": "p"}}
        return {}


@pytest.fixture
def make(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    ident = tmp_path / "machine-id"
    ident.write_text("client-1\n", encoding="utf-8")
    monkeypatch.setattr(rt, "CLIENT_MACHINE_ID", ident)

    def go(worker: Worker, ledger_extra: int = 0) -> tuple[lib.Drill, backup_renet.RenetLegs]:
        drill = lib.Drill("backup", selftest=False, keep_work=False)
        drill.init()
        plane = Plane(worker)
        fake = types.SimpleNamespace(
            d=drill,
            api_token="tok",
            lineage_snapshots=lambda _lineage: [s["id"] for s in reversed(worker.snaps)],
            stored_bytes=lambda: plane.stored() + ledger_extra,
        )
        assert drill.work is not None
        roundtrip = rt.Roundtrip(worker, FakeApi(), drill.work, say=drill.note)
        return drill, backup_renet.RenetLegs(fake, roundtrip)

    return go


def _run(legs: backup_renet.RenetLegs) -> None:
    legs.leg_b()
    legs.leg_c()
    legs.leg_d()


def test_the_three_legs_pass_against_a_worker_that_behaves(make: typing.Callable) -> None:
    worker = Worker()
    drill, legs = make(worker)
    try:
        _run(legs)
        assert drill.failures == 0
        b = legs.b
        assert b.snap_seed == "snap-0"
        assert b.snap_incr == "snap-1"
        assert b.stored_lineage == legs.src
        assert b.seed_stored_bytes == 8 * CELL
        assert b.seed_sha == "digest-0"
        assert b.incr_sha == "digest-1"
        assert b.machine_id == "mid-1"
        assert b.license_blob["publicKeyId"] == "kid"
        # Source plus the two restore targets, each with its own licence and no host-built cell anywhere.
        assert len(legs.rt.created) == 3
        assert not any("backup snapshot" in c and "--cell-bytes 1" in c for c in worker.commands)
    finally:
        drill.teardown()


@pytest.mark.parametrize("bug", ["no-change", "two-cells", "restore-differs"])
def test_each_leg_goes_red_on_the_defect_it_names(make: typing.Callable, bug: str) -> None:
    drill, legs = make(Worker(bug))
    try:
        _run(legs)
        assert drill.failures >= 1
    finally:
        drill.teardown()


def test_a_ledger_that_did_not_move_by_the_uploaded_bytes_is_red(make: typing.Callable) -> None:
    drill, legs = make(Worker(), ledger_extra=CELL)
    try:
        legs.leg_b()
        assert drill.failures == 1
    finally:
        drill.teardown()


def test_the_mutation_rewrites_one_cell_in_place_on_the_unmounted_image() -> None:
    cmd = backup_renet.mutation_command("/ds", "g-1", CELL)
    assert "of=/ds/repositories/g-1" in cmd
    assert "conv=notrunc" in cmd
    assert "seek=%d" % (3 * CELL + 4096) in cmd
    assert "head -c 32 /dev/urandom" in cmd


def test_snapshot_documents_are_read_defensively() -> None:
    assert backup_renet.snapshot_ok({"status": "stored", "snapshotId": "s"})
    assert not backup_renet.snapshot_ok({"status": "stored"})
    assert backup_renet.uploaded({"bytesUploaded": "65536"}) == CELL
    assert backup_renet.uploaded({"bytesUploaded": True}) == 0
    assert backup_renet.uploaded({}) == 0


def test_the_options_carry_the_renet_flag_and_the_default_legs_do_not_need_it() -> None:
    opts = backup.Options()
    assert opts.renet is False
    assert backup.parse_args(["--renet", "--vm", "10.0.0.5"], opts) is None
    assert opts.renet is True
    assert opts.vm_ip == "10.0.0.5"


@pytest.fixture
def host(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> backup.Backup:
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    (root / ".account-state").write_text(f"gateway_port={ACCOUNT_DEV_PORT}\nstarted=1\n")
    drill = lib.Drill("backup", selftest=False, keep_work=False)
    drill.init()
    return backup.Backup(typing.cast("backup.BackupDrill", drill), backup.Options())


def test_setup_renet_is_a_no_op_without_the_flag(host: backup.Backup) -> None:
    host.setup_renet()
    assert host.renet_legs is None


def test_setup_renet_refuses_a_host_off_the_vm_network(
    host: backup.Backup, monkeypatch: pytest.MonkeyPatch
) -> None:
    host.o.renet = True
    monkeypatch.setattr(backup.wire, "bridge_host", lambda _base: None)
    with pytest.raises(SystemExit):
        host.setup_renet()
    assert host.renet_legs is None


def test_setup_renet_refuses_a_worker_that_does_not_answer(
    host: backup.Backup, monkeypatch: pytest.MonkeyPatch
) -> None:
    host.o.renet = True
    monkeypatch.setattr(backup.wire, "bridge_host", lambda _base: "192.168.111.254")
    monkeypatch.setattr(
        backup.backup_roundtrip, "ssh_vm", lambda *_a, **_k: rt.VmResult(255, "", "denied")
    )
    with pytest.raises(SystemExit):
        host.setup_renet()
    assert host.renet_legs is None


def test_setup_renet_wires_the_legs_when_the_worker_answers(
    host: backup.Backup, monkeypatch: pytest.MonkeyPatch
) -> None:
    host.o.renet = True
    monkeypatch.setattr(backup.wire, "bridge_host", lambda _base: "192.168.111.254")
    monkeypatch.setattr(backup.backup_roundtrip, "ssh_vm", lambda *_a, **_k: rt.VmResult(0))
    host.setup_renet()
    assert host.renet_legs is not None
    assert host.renet_legs.rt.api.host == "192.168.111.254"
    assert host.renet_legs.rt.api.port == 4800
    # The legs b-d entry points hand over to renet instead of building host cells.
    called: list[str] = []
    monkeypatch.setattr(host.renet_legs, "leg_b", lambda: called.append("b"))
    host.leg_b_seed_upload()
    assert called == ["b"]


# --------------------------------------------------------------------------- legs v, w and x (box T4 of PLAN-backup-critical-tier): the CLI-free builders; the live legs need --renet --vm <worker>


def _run_functions(text: str, calls: str, docker_log: str) -> subprocess.CompletedProcess[str]:
    """Source the Rediaccfile with `docker` stubbed to append its arguments to `docker_log`, then run `calls`."""
    with tempfile.TemporaryDirectory() as work:
        runner = (
            "source /dev/stdin <<'EOF'\n%sEOF\ndocker() { echo \"$*\" >> %s; }\n"
            'sleep() { echo "sleep $*" >> %s; }\n%s\n' % (text, docker_log, docker_log, calls)
        )
        env = {**os.environ, "REDIACC_WORKING_DIR": work}
        return subprocess.run(
            ["bash", "-c", runner], env=env, capture_output=True, text=True, check=False
        )


def test_hook_rediaccfile_is_valid_bash_and_orders_the_hooks() -> None:
    for hang in (False, True):
        proc = subprocess.run(
            ["bash", "-n"],
            input=backup_renet.hook_rediaccfile(hang),
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
    with tempfile.TemporaryDirectory() as work:
        log = work + "/docker.log"
        proc = _run_functions(
            backup_renet.hook_rediaccfile(False), "backup_prepare; backup_finish", log
        )
        assert proc.returncode == 0, proc.stderr
        lines = pathlib.Path(log).read_text().splitlines()
    assert lines == [
        "exec db touch /data/frozen",
        "exec db rm -f /data/frozen",
    ]


def test_hang_variant_sleeps_inside_prepare_only() -> None:
    with tempfile.TemporaryDirectory() as work:
        log = work + "/docker.log"
        _run_functions(backup_renet.hook_rediaccfile(True), "backup_prepare", log)
        prepare = pathlib.Path(log).read_text().splitlines()
        log2 = work + "/docker2.log"
        _run_functions(backup_renet.hook_rediaccfile(True), "backup_finish", log2)
        finish = pathlib.Path(log2).read_text().splitlines()
    assert "sleep %d" % backup_renet.HOOK_HANG_SECONDS in prepare
    assert not any(line.startswith("sleep") for line in finish)
    plain = backup_renet.hook_rediaccfile(False)
    assert "sleep" not in plain


def test_hookless_variant_has_no_hook_functions() -> None:
    text = backup_renet.hook_rediaccfile(False, hooks=False)
    assert "backup_prepare" not in text
    assert "backup_finish" not in text
    assert "up()" in text
    assert "down()" in text


def test_compose_stops_writing_under_the_frozen_file() -> None:
    text = backup_renet.hook_compose()
    assert "container_name: %s" % backup_renet.HOOK_CONTAINER in text
    assert "[ -f /data/frozen ] ||" in text


def test_install_command_writes_both_files_and_a_writable_log() -> None:
    cmd = backup_renet.install_hook_files_command(
        DATASTORE_PATH, "g1", backup_renet.hook_rediaccfile(False), backup_renet.hook_compose()
    )
    blobs = re.findall(r"printf %s ([A-Za-z0-9+/=]+) \| base64 -d", cmd)
    assert [base64.b64decode(b).decode() for b in blobs] == [
        backup_renet.hook_rediaccfile(False),
        backup_renet.hook_compose(),
    ]
    assert f"{DATASTORE_PATH}/mounts/g1/Rediaccfile" in cmd
    assert f"chmod 666 {DATASTORE_PATH}/mounts/g1/%s" % backup_renet.HOOK_LOG in cmd


def test_hook_log_events_and_count_of() -> None:
    assert backup_renet.hook_log_events("prepare 1\nfinish 2\n") == ["prepare", "finish"]
    assert backup_renet.hook_log_events("") == []
    assert backup_renet.hook_log_events("finish 2\nprepare 1\n") != ["prepare", "finish"]
    assert backup_renet.count_of("  42 /data/rows\n") == 42
    assert backup_renet.count_of("") == -1
    assert backup_renet.count_of("wc: no such file") == -1


def test_deadman_bound_follows_the_documented_formula() -> None:
    assert backup_renet.HOOK_DEADMAN_SECONDS == 2 * backup_renet.HOOK_TIMEOUT_SECONDS + 30


def test_marker_wait_and_kill_commands() -> None:
    present = backup_renet.wait_marker_command("g1", True, 60)
    gone = backup_renet.wait_marker_command("g1", False, 60)
    assert "[ -e /run/rediacc/backup-hook/g1 ]" in present
    assert "[ ! -e /run/rediacc/backup-hook/g1 ]" in gone
    assert "kill -9" in backup_renet.kill_pid_command()
    start = backup_renet.killed_hook_command(DATASTORE_PATH, "g1", "65536")
    assert "--hook-timeout %ds" % backup_renet.HOOK_TIMEOUT_SECONDS in start
    assert "nohup renet backup snapshot" in start


def test_cleanup_pattern_cannot_match_its_own_shell() -> None:
    cmd = backup_renet.hook_cleanup_command(DATASTORE_PATH, "g1")
    assert '"[s]leep %d"' % backup_renet.HOOK_HANG_SECONDS in cmd
    assert 'pkill -f "sleep %d"' % backup_renet.HOOK_HANG_SECONDS not in cmd


def test_docker_exec_uses_the_repository_socket() -> None:
    cmd = backup_renet.docker_exec_command("2944", "exec db true")
    assert "DOCKER_HOST=unix://" in cmd
    assert "net-2944/docker-2944.sock" in cmd


def test_sample_found_missing_control_and_failures() -> None:
    assert backup_renet.sample_found_missing({"chunksSampleMissing": 1})
    assert not backup_renet.sample_found_missing({"chunksSampleMissing": 0})
    assert not backup_renet.sample_found_missing({})
    assert not backup_renet.sample_found_missing({"chunksSampleMissing": True})
    assert not backup_renet.sample_found_missing({"chunksSampleMissing": "1"})


def test_target_run_names_the_tier_cadence() -> None:
    cmd = backup_renet.snapshot_target_command(DATASTORE_PATH, "g1", "65536")
    assert "--target %s" % backup_renet.HEAL_TARGET in cmd


def test_reflink_commands_copy_cheaply_and_name_each_run() -> None:
    cmd = backup_renet.reflink_command(DATASTORE_PATH, "g1", 2)
    assert (
        f"cp --reflink=always {DATASTORE_PATH}/repositories/g1 {DATASTORE_PATH}/repositories/g1%s2"
        % backup_renet.REFLINK_SUFFIX
        in cmd
    )
    assert backup_renet.reflink_digest_command(DATASTORE_PATH, "g1", 3).endswith(
        "g1%s3" % backup_renet.REFLINK_SUFFIX
    )
    assert "rm -f" in backup_renet.reflink_remove_command(DATASTORE_PATH, "g1")


def test_chosen_run_is_inside_the_chain_and_not_the_last() -> None:
    assert 1 <= backup_renet.RUN_RESTORED < backup_renet.RUN_CHAIN


def test_legs_are_known_opt_in_and_dispatched() -> None:
    for leg in ("v", "w", "x"):
        assert leg in backup.KNOWN_LEGS
        assert leg not in backup.DEFAULT_LEGS.split(",")
    assert backup.KNOWN_LEGS[-3:] == ["v", "w", "x"]
    assert "t,u,v,w,x]" in backup.USAGE
    for name in ("leg_v_hook_order", "leg_w_sample_heals", "leg_x_restore_at_run"):
        assert hasattr(backup.Backup, name)
    for name in ("leg_v", "leg_w", "leg_x"):
        assert hasattr(backup_renet.RenetLegs, name)


# ---------------------------------------------------------------------------
# Legs v, w and x driven end to end against a scripted worker, each with the planted control that must fire.
# The live run (`./run.sh drill backup --renet --vm <worker> --legs v,w,x`) is the lead's.
# ---------------------------------------------------------------------------


def _decoded_rediaccfile(command: str) -> str:
    blob = re.search(r"printf %s (\S+) \| base64 -d > \S+/Rediaccfile", command)
    assert blob
    return base64.b64decode(blob.group(1)).decode()


class HookWorker:
    """A worker for leg v: an application that stops writing while held, a hook log, and a deadman that thaws a killed run. `bug` plants one defect."""

    def __init__(self, bug: str = "") -> None:
        self.bug = bug
        self.hooks = False
        self.hang = False
        self.frozen = False
        self.marker = False
        self.rows = 10
        self.log: list[str] = []
        self.cleaned = False

    def __call__(self, command: str, stdin_data: str | None = None) -> rt.VmResult:
        del stdin_data
        if "renet machine-id" in command:
            return rt.VmResult(0, "mid-1\n")
        if "base64 -d > " in command and "Rediaccfile" in command:
            text = _decoded_rediaccfile(command)
            self.hooks = "backup_prepare()" in text
            self.hang = "sleep %d" % backup_renet.HOOK_HANG_SECONDS in text
            return rt.VmResult(0)
        if "wc -l /data/rows" in command:
            self.rows += 0 if self.frozen else 7
            return rt.VmResult(0, "%d /data/rows\n" % self.rows)
        if "test -f /data/frozen" in command:
            return rt.VmResult(0 if self.frozen else 1)
        if "test ! -f /data/frozen" in command:
            return rt.VmResult(1 if self.frozen else 0)
        if "cat " in command and backup_renet.HOOK_LOG in command:
            return rt.VmResult(0, "".join("%s 1\n" % e for e in self.log))
        if "nohup renet backup snapshot" in command:
            self.frozen = self.marker = self.hang and self.bug != "never-held"
            if self.frozen:
                self.log.append("prepare")
            return rt.VmResult(0)
        if "i=0; while [ $i -lt" in command:
            if "[ -e " in command:
                return rt.VmResult(0 if self.marker else 1)
            if self.bug == "no-deadman":
                return rt.VmResult(1)
            if self.bug == "late-deadman":
                # the hold ends only after the bound: a wait window of exactly the bound sees nothing
                seconds = int(re.search(r"-lt (\d+)", command).group(1))
                if seconds <= backup_renet.HOOK_DEADMAN_SECONDS:
                    return rt.VmResult(1)
            self.frozen = self.marker = False
            self.log.append("finish")
            return rt.VmResult(0)
        if "backup snapshot" in command and "--hook-timeout" in command:
            if self.bug == "control-fails" and not self.hooks:
                return rt.VmResult(1, "")
            claim = "app-quiesced" if self.hooks or self.bug == "claims-without-hook" else "crash"
            if self.hooks:
                order = (
                    ["finish", "prepare"] if self.bug == "wrong-order" else ["prepare", "finish"]
                )
                self.log.extend(order)
            doc = {
                "status": "stored",
                "snapshotId": "s",
                "consistency": claim,
                "hook": {"prepare": "ok", "finish": "ok"} if self.hooks else {},
            }
            return rt.VmResult(0, json.dumps(doc))
        if "repository down" in command and "pkill" in command:
            self.cleaned = True
        return rt.VmResult(0)


def _legs_for_v(
    make: typing.Callable, worker: HookWorker
) -> tuple[lib.Drill, backup_renet.RenetLegs]:
    drill, legs = make(Worker())
    legs.rt.vm = worker
    legs.b.av = lambda value, expected, desc: drill.assert_equal(
        str(bool(expected)), str(bool(value)), desc
    )
    return drill, legs


def test_leg_v_passes_and_its_controls_run(make: typing.Callable) -> None:
    worker = HookWorker()
    drill, legs = _legs_for_v(make, worker)
    try:
        legs.leg_v()
        assert drill.failures == 0
        assert worker.cleaned
        # The deadman, not the run, wrote the last event.
        assert worker.log[-1] == "finish"
        assert not worker.frozen
    finally:
        drill.teardown()


@pytest.mark.parametrize(
    ("bug", "desc"),
    [
        ("claims-without-hook", "CONTROL: a repository with no hook is not claimed app-quiesced"),
        ("wrong-order", "the hooks ran once each, prepare first"),
        ("never-held", "the run held the application (marker stands)"),
        ("no-deadman", "the deadman ended the hold within its bound"),
        ("late-deadman", "the deadman ended the hold within its bound"),
        ("control-fails", "CONTROL: a repository with no hook is not claimed app-quiesced"),
    ],
)
def test_leg_v_goes_red_on_the_defect_each_check_names(
    make: typing.Callable, capsys: pytest.CaptureFixture[str], bug: str, desc: str
) -> None:
    drill, legs = _legs_for_v(make, HookWorker(bug))
    try:
        legs.leg_v()
        assert drill.failures >= 1
        out = capsys.readouterr()
        assert desc in out.out + out.err
    finally:
        drill.teardown()


def test_leg_v_cleans_up_even_when_a_step_raises(make: typing.Callable) -> None:
    worker = HookWorker()
    drill, legs = _legs_for_v(make, worker)

    def broken(command: str, stdin_data: str | None = None) -> rt.VmResult:
        if "nohup renet backup snapshot" in command:
            raise rt.StepError("boom")
        return worker(command, stdin_data)

    legs.rt.vm = broken
    try:
        with pytest.raises(rt.StepError):
            legs.leg_v()
        assert worker.cleaned
    finally:
        drill.teardown()


LOST_CELL = b"the cell the store lost"


class HealWorker:
    """A worker for leg w: an idle image whose target runs sample the store and reach the lost chunk on the `finds_on`-th target run after the first idle one, so the run count is `finds_on + 1` at the find (0: never)."""

    def __init__(self, store: dict[str, bytes], digest: str, bug: str, finds_on: int) -> None:
        self.store = store
        self.digest = digest
        self.bug = bug
        self.finds_on = finds_on
        self.runs = 0

    def __call__(self, command: str, stdin_data: str | None = None) -> rt.VmResult:
        del stdin_data
        if "--target" not in command:
            return rt.VmResult(0)
        self.runs += 1
        idle = {"status": "unchanged", "chunksSampled": 16, "bytesUploaded": 0}
        doc = idle
        if self.bug == "dirty-before-find" and self.runs == 2:
            doc = {"status": "stored", "bytesUploaded": CELL, "chunksSampled": 16}
        elif self.digest not in self.store and 0 < self.finds_on <= self.runs - 1:
            if self.bug != "no-heal":
                self.store[self.digest] = b"corrupt" if self.bug == "wrong-bytes" else LOST_CELL
            doc = {
                "status": "stored",
                "bytesUploaded": CELL,
                "chunksSampled": 16,
                "chunksSampleMissing": 1,
            }
        return rt.VmResult(0, json.dumps(doc))


def _legs_for_w(
    make: typing.Callable, bug: str = "", finds_on: int = 3, digest_known: bool = True
) -> tuple[lib.Drill, backup_renet.RenetLegs]:
    digest = hashlib.sha256(LOST_CELL).hexdigest()
    store = {digest: LOST_CELL}
    drill, legs = make(Worker())
    legs.src = "lineage-1"
    legs.rt.vm = HealWorker(store, digest, bug, finds_on)
    token = {"value": ""}

    def mint() -> bool:
        token["value"] = "tok"
        return True

    def s3_get(url: str) -> tuple[int, bytes]:
        body = store.get(url.rsplit("/", 1)[1])
        return (200, body) if body is not None else (404, b"")

    def s3_delete(url: str) -> str:
        return "204" if store.pop(url.rsplit("/", 1)[1], None) is not None else "404"

    legs.b.restore_session_token = ""
    legs.b.release_probe_leases = lambda: None
    legs.b.mint_restore_session = mint
    legs.b.a_seed_digest = lambda tok: digest if tok and digest_known else ""
    legs.b.chunk_url = lambda lineage, name: "http://store/%s/%s" % (lineage, name)
    legs.b.s3_get = s3_get
    legs.b.s3_delete = s3_delete
    legs.b.av = lambda value, expected, desc: drill.assert_equal(str(expected), str(value), desc)
    legs.b.restore_session_token = "tok"
    # The target halves have their own worker (TargetWorker below); here only that the heal hands over to them.
    reached: list[bool] = []
    legs.target_halves = lambda: reached.append(True)
    legs.reached_target_halves = reached
    return drill, legs


def test_leg_w_heals_a_deleted_chunk_after_idle_runs_that_upload_nothing(
    make: typing.Callable,
) -> None:
    drill, legs = _legs_for_w(make)
    try:
        legs.leg_w()
        assert drill.failures == 0
        # The idle first run, two idle runs before the find, and the finding run.
        assert typing.cast("HealWorker", legs.rt.vm).runs == 4
        assert legs.reached_target_halves == [True]
    finally:
        drill.teardown()


@pytest.mark.parametrize(
    ("bug", "kwargs", "desc"),
    [
        ("", {"finds_on": 0}, "the rolling sample reached the lost chunk within"),
        ("no-heal", {}, "the chunk is back in the store"),
        ("wrong-bytes", {}, "and its bytes hash to the name it was lost under"),
        ("dirty-before-find", {}, "before the find is idle and uploads nothing"),
        ("", {"digest_known": False}, "the seed snapshot names a chunk"),
    ],
)
def test_leg_w_goes_red_on_the_defect_each_check_names(
    make: typing.Callable,
    capsys: pytest.CaptureFixture[str],
    bug: str,
    kwargs: dict,
    desc: str,
) -> None:
    drill, legs = _legs_for_w(make, bug, **kwargs)
    try:
        legs.leg_w()
        assert drill.failures >= 1
        out = capsys.readouterr()
        assert desc in out.out + out.err
    finally:
        drill.teardown()


class ChainWorker:
    """A worker for leg x: an image that changes per rewrite, a reflink per run, and a restore at a run. `bug` plants one defect."""

    def __init__(self, bug: str = "") -> None:
        self.bug = bug
        self.images: dict[str, str] = {}
        self.reflinks: dict[int, str] = {}
        self.snap_digest: dict[str, str] = {}
        self.gen = 0
        self.removed = False

    def __call__(self, command: str, stdin_data: str | None = None) -> rt.VmResult:
        del stdin_data
        suffix = re.escape(backup_renet.REFLINK_SUFFIX)
        if "dd of=" in command:
            guid = re.search(r"/repositories/(\S+) bs=1", command)
            assert guid
            self.gen += 1
            if self.bug != "no-rewrite":
                self.images[guid.group(1)] = "img-%d" % self.gen
            return rt.VmResult(0)
        if "backup snapshot" in command:
            guid = re.search(r"--repo (\S+)", command)
            assert guid
            snap = "snap-%d" % len(self.snap_digest)
            self.snap_digest[snap] = self.images.setdefault(guid.group(1), "img-0")
            return rt.VmResult(0, json.dumps({"status": "stored", "snapshotId": snap}))
        if "cp --reflink=always" in command:
            guid = re.search(r"cp --reflink=always \S+/repositories/(\S+?) ", command)
            run = re.search(r"%s(\d+)'" % suffix, command)
            assert guid
            assert run
            self.reflinks[int(run.group(1))] = self.images[guid.group(1)]
            return rt.VmResult(0)
        if "sha256sum" in command:
            run = re.search(r"%s(\d+)$" % suffix, command.strip())
            if run:
                return rt.VmResult(0, "%s  x\n" % self.reflinks[int(run.group(1))])
            guid = re.search(r"/repositories/(\S+?)'?$", command.strip())
            assert guid
            return rt.VmResult(0, "%s  x\n" % self.images[guid.group(1)])
        if "backup restore" in command:
            target = re.search(r"--repo (\S+)", command)
            at = re.search(r"--at (\S+)", command)
            assert target
            assert at
            latest = "snap-%d" % (len(self.snap_digest) - 1)
            chosen = latest if self.bug == "restores-latest" else at.group(1)
            self.images[target.group(1)] = self.snap_digest[chosen]
            return rt.VmResult(0, '{"status":"restored"}')
        if "rm -f" in command and backup_renet.REFLINK_SUFFIX in command:
            self.removed = True
        return rt.VmResult(0)


def _legs_for_x(
    make: typing.Callable, bug: str = ""
) -> tuple[lib.Drill, backup_renet.RenetLegs, ChainWorker]:
    worker = ChainWorker(bug)
    drill, legs = make(Worker())
    legs.src = "src-1"
    legs.rt.vm = worker
    return drill, legs, worker


def test_leg_x_passes_when_the_restore_equals_the_chosen_runs_reflink(
    make: typing.Callable,
) -> None:
    drill, legs, worker = _legs_for_x(make)
    try:
        legs.leg_x()
        assert drill.failures == 0
        assert worker.removed
        assert len(worker.reflinks) == backup_renet.RUN_CHAIN
    finally:
        drill.teardown()


@pytest.mark.parametrize(
    ("bug", "desc"),
    [
        ("restores-latest", "and the restored image equals that run's reflink"),
        ("no-rewrite", "CONTROL: every run's image differs from the others"),
    ],
)
def test_leg_x_goes_red_on_the_defect_each_check_names(
    make: typing.Callable, capsys: pytest.CaptureFixture[str], bug: str, desc: str
) -> None:
    drill, legs, worker = _legs_for_x(make, bug)
    try:
        legs.leg_x()
        assert drill.failures >= 1
        out = capsys.readouterr()
        assert desc in out.out + out.err
        assert worker.removed
    finally:
        drill.teardown()


# ------------------------------------------------------------------ leg u and leg v helpers


def test_the_hook_network_id_is_one_renet_accepts() -> None:
    """renet refuses a network id that is not 2816 + n * 64 (measured 2026-11-05 on the worker: 2881 was refused), and the id must differ from leg b's."""
    ident = int(backup_renet.HOOK_NET_ID)
    assert (ident - 2816) % 64 == 0
    assert ident > 2816
    assert backup_renet.HOOK_NET_ID != "2880"
    # CONTROL: the id the drill used to name fails the same rule.
    assert (2881 - 2816) % 64 != 0


def test_journal_upload_snapshot_reads_the_in_flight_upload() -> None:
    doc = json.dumps(
        {"version": 1, "upload": {"snapshotId": "20261105T1-aa", "manifestCommitted": False}}
    )
    assert backup_renet.journal_upload_snapshot(doc) == "20261105T1-aa"


@pytest.mark.parametrize(
    "text",
    ["", "not json", "[]", '{"anchor": {}}', '{"upload": null}', '{"upload": {"snapshotId": 3}}'],
)
def test_journal_upload_snapshot_is_empty_without_an_upload(text: str) -> None:
    assert backup_renet.journal_upload_snapshot(text) == ""


def test_lineage_rows_never_counts_a_skipped_row_as_judged() -> None:
    skipped = {"lineageGuid": "g", "skipped": "leased", "observedBytes": 0, "ledgerBytesBefore": 9}
    judged = {"lineageGuid": "h", "skipped": None, "observedBytes": 9, "ledgerBytesBefore": 9}
    assert backup_renet.lineage_rows([skipped, judged]) == ([judged], [skipped])
    # CONTROL: the skipped row alone leaves nothing judged, which is what leg u's assertion reads.
    assert backup_renet.lineage_rows([skipped]) == ([], [skipped])
    assert backup_renet.lineage_rows(None) == ([], [])


# ---------------------------------------------------------------------------
# Critical-tier box Y1 (leg w's target halves) and integrity box P1 (leg p's TOC half, leg r's scope half), each against a scripted worker with the planted defect each check names.
# The live run (`./run.sh drill backup --renet --vm <worker> --legs a,b,c,d,p,r,w`) is the lead's.
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _equal_av(drill: lib.Drill) -> typing.Callable[[object, object, str], None]:
    return lambda value, expected, desc: drill.assert_equal(str(expected), str(value), desc)


def _flag(command: str, name: str) -> str:
    found = re.search(r"--%s (\S+)" % name, command)
    return found.group(1).rstrip("';") if found else ""


def _sh(command: str, **kwargs: typing.Any) -> subprocess.CompletedProcess[str]:
    """A worker command run by this host's shell, root's `sudo -n` dropped."""
    return subprocess.run(
        ["/bin/sh", "-c", command.replace("sudo -n ", "")], text=True, check=False, **kwargs
    )


class TargetWorker:
    """A worker for leg w's target halves: a trickled run against a deadline, two repositories on one slot, and a timer unit. `bug` plants one defect."""

    def __init__(self, src: str, bug: str = "") -> None:
        self.src = src
        self.bug = bug
        self.installed = False
        self.unit_cleaned = False
        self.tier_cleaned = 0
        self.holder = False

    def record(self, doc: dict, rc: int = 0, elapsed: int = 1) -> rt.VmResult:
        return rt.VmResult(rc, json.dumps(doc) + "\n", "elapsed %d\n" % elapsed)

    def timed(self, command: str) -> rt.VmResult:
        repo, deadline = _flag(command, "repo"), _flag(command, "deadline")
        if repo == self.src and deadline == "%ds" % backup_renet.DEADLINE_SECONDS:
            if self.bug == "deadline-ignored":
                return self.record({"status": "stored", "targetMet": True}, 0, 40)
            elapsed = 70 if self.bug == "slow-kill" else backup_renet.DEADLINE_SECONDS
            return self.record({"status": "deadline-exceeded", "targetMet": False}, 1, elapsed)
        if repo == self.src:
            if self.bug == "slot-kept":
                return self.record({"status": "stored", "slotWaitMs": 5000})
            return self.record({"status": "stored"})
        if deadline == "%ds" % backup_renet.SLOT_REFUSE_DEADLINE_SECONDS:
            assert self.holder
            if self.bug == "unbounded-slot":
                return self.record({"status": "stored"}, 0, 1)
            return self.record({"status": "skipped", "slotWaitMs": 3001}, 0, 3)
        if self.bug == "no-wait":
            return self.record({"status": "stored"})
        return self.record({"status": "stored", "slotWaitMs": 9000})

    def journal(self) -> rt.VmResult:
        lines = []
        stamps: list[int] = []
        if self.installed and self.bug != "never-fires":
            gap = 5 if self.bug == "wrong-gap" else 60
            stamps = [1_000_000_000, 1_000_000_000 + gap * 1_000_000]
        elif self.bug == "early-run":
            stamps = [999_000_000]
        for stamp in stamps:
            rec = {"guid": self.src, "status": "unchanged", "targetSeconds": 60, "targetMet": True}
            lines.append(
                json.dumps({"MESSAGE": json.dumps(rec), "__REALTIME_TIMESTAMP": str(stamp)})
            )
            lines.append(
                json.dumps({"MESSAGE": "Starting unit", "__REALTIME_TIMESTAMP": str(stamp)})
            )
        return rt.VmResult(0, "\n".join(lines) + "\n")

    def __call__(self, command: str, stdin_data: str | None = None) -> rt.VmResult:
        del stdin_data
        if "renet machine-id" in command:
            return rt.VmResult(0, "mid-1\n")
        if "s=$(date" in command and "--target" in command:
            return self.timed(command)
        if "pgrep -f" in command:
            if self.bug == "sudo-refused":
                return rt.VmResult(3)
            return rt.VmResult(0 if self.bug == "left-alive" else 1)
        if "nohup renet backup snapshot" in command or "kill -0" in command:
            return rt.VmResult(0)
        if "cat /tmp/tier-a.out" in command:
            return self.record({"status": "stored"})
        if "flock -n" in command:
            return rt.VmResult(0)
        if "nohup flock -o" in command:
            self.holder = True
            return rt.VmResult(0)
        if "pkill -f" in command and "/tmp/tier-" in command:
            self.holder = False
            self.tier_cleaned += 1
            return rt.VmResult(0)
        if "systemctl start" in command:
            self.installed = True
            return rt.VmResult(0)
        if "journalctl" in command and "while" in command:
            return rt.VmResult(1 if self.bug == "never-fires" or not self.installed else 0)
        if "journalctl" in command:
            return self.journal()
        if "systemctl stop" in command:
            self.unit_cleaned = True
            return rt.VmResult(0)
        if "backup snapshot" in command:
            return rt.VmResult(0, json.dumps({"status": "stored", "snapshotId": "seed-2"}))
        return rt.VmResult(0)


def _legs_for_target(
    make: typing.Callable, bug: str = ""
) -> tuple[lib.Drill, backup_renet.RenetLegs, TargetWorker]:
    drill, legs = make(Worker())
    legs.src = "src-guid-0001"
    worker = TargetWorker(legs.src, bug)
    legs.rt.vm = worker
    legs.b.av = _equal_av(drill)
    legs.b.lineage_snapshots = lambda _lineage: ["s2", "s1"]
    return drill, legs, worker


def test_target_halves_pass_and_clean_up(make: typing.Callable) -> None:
    drill, legs, worker = _legs_for_target(make)
    try:
        legs.target_halves()
        assert drill.failures == 0
        assert worker.unit_cleaned
        # Once after the slot control (before the unit takes the slot), once at the end.
        assert worker.tier_cleaned == 2
        assert not worker.holder
    finally:
        drill.teardown()


@pytest.mark.parametrize(
    ("bug", "desc"),
    [
        ("deadline-ignored", "the run ends deadline-exceeded"),
        ("slow-kill", "it ended at its deadline, not before and not long after"),
        ("left-alive", "no part of the run is left alive"),
        ("sudo-refused", "no part of the run is left alive"),
        ("slot-kept", "and the killed run left the slot free"),
        ("no-wait", "after waiting for the slot"),
        ("unbounded-slot", "CONTROL: a run the slot never frees for is skipped"),
        ("never-fires", "the timer fired 2 runs within"),
        ("early-run", "CONTROL: the unit has run nothing before its timer"),
        ("wrong-gap", "the two runs fired a target apart"),
    ],
)
def test_target_halves_go_red_on_the_defect_each_check_names(
    make: typing.Callable, capsys: pytest.CaptureFixture[str], bug: str, desc: str
) -> None:
    drill, legs, worker = _legs_for_target(make, bug)
    try:
        legs.target_halves()
        assert drill.failures >= 1
        out = capsys.readouterr()
        assert desc in out.out + out.err
        assert worker.unit_cleaned
    finally:
        drill.teardown()


def test_target_halves_clean_up_when_a_step_raises(make: typing.Callable) -> None:
    drill, legs, worker = _legs_for_target(make)

    def broken(command: str, stdin_data: str | None = None) -> rt.VmResult:
        if "systemctl start" in command:
            raise rt.StepError("boom")
        return worker(command, stdin_data)

    legs.rt.vm = broken
    try:
        with pytest.raises(rt.StepError):
            legs.target_halves()
        assert worker.unit_cleaned
        assert worker.tier_cleaned == 2
    finally:
        drill.teardown()


def test_the_slot_repository_keeps_the_source_passphrase_and_its_own_network(
    make: typing.Callable,
) -> None:
    drill, legs, worker = _legs_for_target(make)
    seen: list[str] = []

    def spy(command: str, stdin_data: str | None = None) -> rt.VmResult:
        seen.append(command)
        return worker(command, stdin_data)

    legs.rt.vm = spy
    luks = legs.rt.work / "luks.txt"
    luks.write_text("source-pass\n", encoding="utf-8")
    try:
        guid, passphrase = legs.own_repo(backup_renet.SLOT_NET_ID)
        assert passphrase != "source-pass"
        assert luks.read_text(encoding="utf-8") == "source-pass\n"
        assert legs.rt.net_src == "2880"
        assert guid in legs.rt.created
        assert any("--network-id %s" % backup_renet.SLOT_NET_ID in c for c in seen)
    finally:
        drill.teardown()


def test_the_extra_network_ids_are_ones_renet_accepts_and_all_differ() -> None:
    ids = [backup_renet.HOOK_NET_ID, backup_renet.SLOT_NET_ID, backup_renet.TOC_NET_ID, "2880"]
    assert len(set(ids)) == len(ids)
    for ident in (backup_renet.SLOT_NET_ID, backup_renet.TOC_NET_ID):
        assert (int(ident) - 2816) % 64 == 0


def test_the_unit_renders_the_cli_figures_for_a_60_second_target() -> None:
    """The CLI's arithmetic for T = 60 s (backup-schedule-unit-generator.ts), recomputed, and the generator's constants read from source so a change there breaks this pin."""
    target = backup_renet.TIER_TARGET_SECONDS
    deadline = min(max(3 * target, 600), 7200)
    assert "%dm" % (deadline // 60) == backup_renet.UNIT_DEADLINE
    assert 2 * deadline + 600 == backup_renet.UNIT_START_TIMEOUT_SECONDS
    assert min(target // 5, 60) == backup_renet.UNIT_JITTER_SECONDS
    generator = REPO_ROOT / "packages/cli/src/services/backup/backup-schedule-unit-generator.ts"
    source = generator.read_text(encoding="utf-8")
    for pin in (
        "START_TIMEOUT_SLACK_SECONDS = 600",
        "JITTER_CAP_SECONDS = 60",
        "DEADLINE_CAP_SECONDS = 7200",
        "return `00/${value.slice(2)}`",
    ):
        assert pin in source
    service = backup_renet.tier_service_unit("/ds", "g", "65536")
    timer = backup_renet.tier_timer_unit()
    assert "--target 1m --deadline 10m" in service
    assert "TimeoutStartSec=1800" in service
    assert "RuntimeMaxSec" not in service
    assert "OnCalendar=*-*-* *:00/1:00" in timer
    assert "RandomizedDelaySec=12s\nFixedRandomDelay=true\nAccuracySec=1s" in timer


def test_install_unit_command_writes_both_files_and_starts_the_timer() -> None:
    cmd = backup_renet.install_unit_command("rediacc-drill-tier-x", "SERVICE", "TIMER")
    blobs = re.findall(r"printf %s (\S+) \| base64 -d > (\S+)", cmd)
    assert [(base64.b64decode(b).decode(), p) for b, p in blobs] == [
        ("SERVICE", "/etc/systemd/system/rediacc-drill-tier-x.service"),
        ("TIMER", "/etc/systemd/system/rediacc-drill-tier-x.timer"),
    ]
    assert cmd.endswith("systemctl start rediacc-drill-tier-x.timer'")


def test_unit_records_reads_only_this_repositorys_records() -> None:
    mine = {"guid": "g", "status": "stored"}
    other = {"guid": "h", "status": "stored"}
    text = "\n".join(
        [
            json.dumps({"MESSAGE": json.dumps(mine), "__REALTIME_TIMESTAMP": "5"}),
            json.dumps({"MESSAGE": json.dumps(other), "__REALTIME_TIMESTAMP": "6"}),
            json.dumps({"MESSAGE": "Started a unit", "__REALTIME_TIMESTAMP": "7"}),
            json.dumps({"MESSAGE": [1, 2], "__REALTIME_TIMESTAMP": "8"}),
            "not json",
        ]
    )
    assert backup_renet.unit_records(text, "g") == [(5, mine)]
    assert backup_renet.unit_records("", "g") == []


def _fake_bin(tmp_path: pathlib.Path, name: str, body: str) -> dict[str, str]:
    """An environment whose PATH finds a stand-in `name` first."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    tool = bindir / name
    tool.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    tool.chmod(0o755)
    return {**os.environ, "PATH": "%s:%s" % (bindir, os.environ["PATH"])}


def test_wait_unit_runs_counts_this_repositorys_records_through_the_real_shell(
    tmp_path: pathlib.Path,
) -> None:
    record = json.dumps({"guid": "g-1", "status": "stored"}, separators=(",", ":"))
    env = _fake_bin(tmp_path, "journalctl", "printf '%%s\\n%%s\\n' '%s' '%s'\n" % (record, record))
    assert _sh(backup_renet.wait_unit_runs_command("u", "g-1", 2, 2), env=env).returncode == 0
    # CONTROL: three runs are not there, and another guid has none.
    assert _sh(backup_renet.wait_unit_runs_command("u", "g-1", 3, 1), env=env).returncode == 1
    assert _sh(backup_renet.wait_unit_runs_command("u", "g-2", 1, 1), env=env).returncode == 1


def test_timed_command_keeps_stdout_and_exit_and_reports_elapsed_on_stderr() -> None:
    done = _sh(backup_renet.timed_command('echo out; sh -c "exit 3"'), capture_output=True)
    assert done.returncode == 3
    assert done.stdout == "out\n"
    assert backup_renet.elapsed_of(done.stderr) == 0
    assert backup_renet.elapsed_of("noise\nelapsed 12\n") == 12
    assert backup_renet.elapsed_of("") == -1


@pytest.mark.skipif(not shutil.which("flock"), reason="needs util-linux flock")
def test_slot_busy_sees_a_held_flock_and_not_a_free_one(tmp_path: pathlib.Path) -> None:
    lock = str(tmp_path / "slot.lock")
    busy = backup_renet.slot_busy_command(1).replace(backup_renet.TIER_SLOT, lock)
    assert _sh(busy).returncode == 1
    holder = subprocess.Popen(["flock", "-o", lock, "sleep", "5"])
    try:
        # Give flock a moment to take the lock before the probe looks.
        assert (
            _sh(
                "i=0; while flock -n %s true; do i=$((i+1)); [ $i -gt 50 ] && exit 1; sleep 0.05; done"
                % lock
            ).returncode
            == 0
        )
        assert _sh(busy).returncode == 0
    finally:
        holder.kill()
        holder.wait()


def test_tier_cleanup_cannot_match_its_own_shell() -> None:
    cmd = backup_renet.tier_cleanup_command()
    assert '"[f]lock -o %s"' % backup_renet.TIER_SLOT in cmd
    assert '"[s]leep %d"' % backup_renet.SLOT_HOLDER_SECONDS in cmd
    assert backup_renet.SLOT_HOLDER_SECONDS != backup_renet.HOOK_HANG_SECONDS


def test_target_args_name_the_target_the_deadline_and_the_cap() -> None:
    args = backup_renet.target_args("/ds", "g", "65536", "8s", 1638)
    assert args == (
        "renet backup snapshot --datastore /ds --repo g --cell-bytes 65536 "
        "--target 1m --deadline 8s --bwlimit 1638"
    )
    assert "--bwlimit" not in backup_renet.target_args("/ds", "g", "65536", "10m")
    # The trickle outlasts the deadline by far, and the slot's holder outlasts the refused run's deadline.
    assert backup_renet.DEADLINE_TRICKLE_SECONDS >= 3 * backup_renet.DEADLINE_SECONDS
    assert backup_renet.SLOT_HOLDER_SECONDS > backup_renet.SLOT_REFUSE_DEADLINE_SECONDS + 10


class TocWorker:
    """A worker for leg p's TOC half: a mounted repository whose TOC key a password mount may install. `bug` plants one defect."""

    def __init__(self, bug: str = "") -> None:
        self.bug = bug
        self.key: str | None = None
        self.back = False

    def __call__(self, command: str, stdin_data: str | None = None) -> rt.VmResult:
        if "renet machine-id" in command:
            return rt.VmResult(0, "mid-1\n")
        if "repository create" in command:
            self.key = None if self.bug == "none-at-create" else "rediacc-toc-x25519 RIGHT"
            return rt.VmResult(0)
        if "toc-key status" in command:
            if self.key is None:
                return rt.VmResult(0, '{"outcome":"absent"}\n')
            return rt.VmResult(0, json.dumps({"outcome": "present", "publicKey": self.key}) + "\n")
        if "repository mount" in command:
            assert stdin_data
            wrong = stdin_data.startswith("not-")
            if (wrong and self.key is not None and self.bug == "wrong-replaces") or (
                wrong and self.key is None and self.bug == "installs-unproven"
            ):
                self.key = "rediacc-toc-x25519 WRONG"
            elif not wrong and self.key is None:
                self.key = "rediacc-toc-x25519 RIGHT"
            return rt.VmResult(0)
        if "sudo -n mv " in command and ".credentials/toc/" in command:
            self.key = None
            return rt.VmResult(0)
        if ".credentials/toc/" in command and "if [ -e" in command:
            self.back = True
        return rt.VmResult(0)


def _legs_for_toc(
    make: typing.Callable, bug: str = ""
) -> tuple[lib.Drill, backup_renet.RenetLegs, TocWorker]:
    drill, legs = make(Worker())
    worker = TocWorker(bug)
    legs.rt.vm = worker
    legs.b.av = _equal_av(drill)
    return drill, legs, worker


def test_toc_half_passes_and_puts_the_key_back(make: typing.Callable) -> None:
    drill, legs, worker = _legs_for_toc(make)
    try:
        legs.toc_key_on_mount()
        assert drill.failures == 0
        assert worker.back
    finally:
        drill.teardown()


@pytest.mark.parametrize(
    ("bug", "desc"),
    [
        ("wrong-replaces", "and it is the same key"),
        ("installs-unproven", "CONTROL: with the key gone a wrong password installs nothing"),
        ("none-at-create", "creating the repository installed its TOC key"),
    ],
)
def test_toc_half_goes_red_on_the_defect_each_check_names(
    make: typing.Callable, capsys: pytest.CaptureFixture[str], bug: str, desc: str
) -> None:
    drill, legs, worker = _legs_for_toc(make, bug)
    try:
        legs.toc_key_on_mount()
        assert drill.failures >= 1
        out = capsys.readouterr()
        assert desc in out.out + out.err
        assert worker.back
    finally:
        drill.teardown()


def test_toc_commands_name_renets_key_path_and_put_back_only_what_is_missing(
    tmp_path: pathlib.Path,
) -> None:
    assert backup_renet.toc_key_path("/ds", "g") == "/ds/.credentials/toc/g.pub"
    assert "--password-stdin" in backup_renet.mount_password_command("/ds", "g")
    ds = str(tmp_path)
    key = pathlib.Path(backup_renet.toc_key_path(ds, "g"))
    key.parent.mkdir(parents=True)
    key.write_text("K\n")
    assert _sh(backup_renet.toc_aside_command(ds, "g")).returncode == 0
    assert not key.exists()
    assert _sh(backup_renet.toc_back_command(ds, "g")).returncode == 0
    assert key.read_text() == "K\n"
    # A key that stands again is kept, and the aside copy goes.
    assert _sh(backup_renet.toc_aside_command(ds, "g")).returncode == 0
    key.write_text("NEW\n")
    assert _sh(backup_renet.toc_back_command(ds, "g")).returncode == 0
    assert key.read_text() == "NEW\n"
    assert list(key.parent.iterdir()) == [key]
    # Nothing aside: nothing happens.
    assert _sh(backup_renet.toc_back_command(ds, "g")).returncode == 0
    assert key.read_text() == "NEW\n"


class ScopeWorker:
    """A worker for leg r's scope half: a verify probe answering the cgroup the run landed in. `bug` plants one defect."""

    def __init__(self, bug: str = "") -> None:
        self.bug = bug
        self.levels: list[tuple[str, bool]] = []

    def __call__(self, command: str, stdin_data: str | None = None) -> rt.VmResult:
        del stdin_data
        if "renet backup verify" not in command:
            return rt.VmResult(0)
        level = _flag(command, "level")
        scoped = "systemd-run --scope" in command
        self.levels.append((level, scoped))
        session = "/user.slice/user-1000.slice/session-3.scope"
        if scoped:
            cgroup = session if self.bug == "no-scope" else "/system.slice/run-r1a2.scope"
            cpumax = "max 100000" if self.bug == "no-quota" else backup_renet.ONE_CORE_CPU_MAX
        else:
            cgroup = "/system.slice/run-r9.scope" if self.bug == "control-in-scope" else session
            cpumax = "max 100000"
        cells = 8 if level == "spot" or self.bug == "shallow-deep" else 140
        rec = {"guid": "src", "status": "verified", "level": level, "checkedCells": cells}
        return rt.VmResult(
            0, "cgroup %s\ncpumax %s\nrc 0\n%s\n" % (cgroup, cpumax, json.dumps(rec))
        )


def _legs_for_scope(
    make: typing.Callable, bug: str = ""
) -> tuple[lib.Drill, backup_renet.RenetLegs, ScopeWorker]:
    drill, legs = make(Worker())
    legs.src = "src"
    worker = ScopeWorker(bug)
    legs.rt.vm = worker
    legs.b.av = _equal_av(drill)
    return drill, legs, worker


def test_scope_half_passes_with_spot_deep_and_the_unscoped_control(make: typing.Callable) -> None:
    drill, legs, worker = _legs_for_scope(make)
    try:
        legs.verify_in_scope()
        assert drill.failures == 0
        assert worker.levels == [("spot", True), ("full", True), ("full", False)]
    finally:
        drill.teardown()


@pytest.mark.parametrize(
    ("bug", "desc"),
    [
        ("no-scope", "the spot verify ran inside a transient scope"),
        ("no-quota", "held to one core"),
        ("control-in-scope", "CONTROL: without the prefix the same run is in no transient scope"),
        ("shallow-deep", "the deep pass checked more cells than the spot pass"),
    ],
)
def test_scope_half_goes_red_on_the_defect_each_check_names(
    make: typing.Callable, capsys: pytest.CaptureFixture[str], bug: str, desc: str
) -> None:
    drill, legs, _ = _legs_for_scope(make, bug)
    try:
        legs.verify_in_scope()
        assert drill.failures >= 1
        out = capsys.readouterr()
        assert desc in out.out + out.err
    finally:
        drill.teardown()


def test_probe_fields_and_transient_scope() -> None:
    text = (
        "cgroup /system.slice/run-r1.scope\ncpumax 100000 100000\nrc 0\n"
        '{"status":"verified"}\n{"x":1}\n'
    )
    assert backup_renet.probe_fields(text) == {
        "cgroup": "/system.slice/run-r1.scope",
        "cpumax": "100000 100000",
        "rc": 0,
        "record": {"status": "verified"},
    }
    assert backup_renet.probe_fields("cgroup \nrc x\n{broken\n") == {
        "cgroup": "",
        "cpumax": "",
        "rc": -1,
        "record": {},
    }
    assert backup_renet.transient_scope("/system.slice/run-r1.scope")
    for other in (
        "/user.slice/user-1000.slice/session-3.scope",
        "/system.slice/run-r1.service",
        "",
        "/",
    ):
        assert not backup_renet.transient_scope(other)


def test_the_scope_prefix_is_the_one_the_verify_function_builds() -> None:
    """A tripwire on private/renet/pkg/functions/commands/backup.go: the prefix the drill puts in front of verify is backgroundReadPrefix's on a systemd machine."""
    source = (REPO_ROOT / "private/renet/pkg/functions/commands/backup.go").read_text(
        encoding="utf-8"
    )
    for pin in (
        '"systemd-run", "--scope", "--quiet", "-p", "CPUQuota=" + quota',
        '"nice", "-n", "10"',
        '"ionice", "-c", "2", "-n", "7"',
        'return "100%"',
    ):
        assert pin in source
    assert backup_renet.VERIFY_SCOPE_PREFIX == (
        "nice -n 10 ionice -c 2 -n 7 systemd-run --scope --quiet -p CPUQuota=100%"
    )


def test_verify_probe_reads_the_running_verbs_cgroup_through_the_real_shell(
    tmp_path: pathlib.Path,
) -> None:
    """The unscoped probe on this host with a stand-in `renet` (a script, so its comm is renet): the cgroup and rc lines and the record come back, in one shell."""
    if not pathlib.Path("/proc/self/cgroup").exists():
        pytest.skip("no /proc on this host")
    env = _fake_bin(tmp_path, "renet", 'sleep 0.3; echo \'{"status":"verified","level":"full"}\'\n')
    cmd = backup_renet.verify_probe_command(str(tmp_path), "g", "full", False)
    assert "--read-bwlimit %d" % backup_renet.DEEP_READ_BWLIMIT in cmd
    scoped_spot = backup_renet.verify_probe_command("/ds", "g", "spot", True)
    assert "--read-bwlimit" not in scoped_spot
    assert scoped_spot.startswith(
        "sudo -n sh -c '" + backup_renet.VERIFY_SCOPE_PREFIX + " renet backup verify"
    )
    done = _sh(cmd, capture_output=True, env=env, cwd=tmp_path)
    fields = backup_renet.probe_fields(done.stdout)
    assert fields["cgroup"].startswith("/"), done.stdout + done.stderr
    assert fields["rc"] == 0
    assert fields["record"] == {"status": "verified", "level": "full"}


class _KilledRunWorker:
    """Leg u's worker: the killed run exits 137, the journal names an upload, the rerun stores."""

    def __call__(self, command: str, stdin_data: str | None = None) -> rt.VmResult:
        del stdin_data
        if "renet machine-id" in command:
            return rt.VmResult(0, "mid-1\n")
        if "timeout -s KILL" in command:
            return rt.VmResult(137)
        if "journal" in command:
            return rt.VmResult(0, json.dumps({"upload": {"snapshotId": "killed-1"}}))
        if "backup snapshot" in command:
            return rt.VmResult(0, json.dumps({"status": "stored", "snapshotId": "rerun-1"}))
        return rt.VmResult(0)


@pytest.mark.parametrize(("lease_live", "failures"), [(True, 0), (False, 1)])
def test_leg_u_requires_the_killed_runs_lease_to_be_live_before_the_rerun(
    make: typing.Callable, lease_live: bool, failures: int
) -> None:
    """CONTROL: a killed run that never leased would also read clean after the rerun."""
    drill, legs = make(Worker())
    legs.rt.vm = _KilledRunWorker()
    legs.src = "src-guid-0001"
    legs.b.av = _equal_av(drill)
    legs.b.release_probe_leases = lambda: None
    clean_row = {"lineageGuid": "l", "observedBytes": 1, "ledgerBytesBefore": 1}
    clean_row.update({"observedChunks": 1, "ledgerChunksBefore": 1})
    answers = iter([([], [{"skipped": "leased"}] if lease_live else []), ([clean_row], [])])
    legs.reconcile_dry_run = lambda: next(answers)
    try:
        legs.leg_u()
        assert drill.failures == failures
    finally:
        drill.teardown()
