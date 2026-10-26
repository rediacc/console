"""`rediacc_ci.drills.backup_renet` (legs b-d with real renet, `--renet`) against a scripted worker VM and a scripted control plane.

The VM keeps a repository image per guid as a digest, mutates it on the planted rewrite, and restores a snapshot into a target by copying the digest recorded when that snapshot was cut. The live run on the ops worker is the acceptance and belongs to the lead; these cases pin the legs' own logic and that each goes red on the defect it names.
"""

from __future__ import annotations

import json
import re
import types
import typing

import pytest

from rediacc_ci.drills import backup, backup_renet, lib
from rediacc_ci.drills import backup_roundtrip as rt
from rediacc_ci.well_known import ACCOUNT_DEV_PORT

if typing.TYPE_CHECKING:
    import pathlib

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
