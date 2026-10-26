"""Leg l of `rediacc_ci.drills.backup` (GC and retention through the maintenance seam) against an in-memory model of the control plane.

The model keeps what the leg reads: a chain of snapshots per lineage, a chunk ledger, a keep-last policy, the per-stream floor of 3 and the 7-day grace counted from the prune. The live run against `./run.sh account dev` and RustFS is the acceptance and belongs to the lead; these cases pin the leg's own logic, and that it goes red when the server misbehaves.
"""

from __future__ import annotations

import datetime
import itertools
import json
import typing
from urllib.parse import parse_qs, urlsplit

import pytest

from rediacc_ci.drills import backup
from rediacc_ci.well_known import ACCOUNT_DEV_PORT

if typing.TYPE_CHECKING:
    import pathlib

FLOOR = 3
GRACE_DAYS = 7
CELL = backup.CELL_BYTES


class Plane:
    """The control plane as the leg sees it. `bug` plants one server defect by name."""

    def __init__(self, bug: str = "") -> None:
        self.bug = bug
        self.lineage = ""
        self.snapshots: list[dict] = []  # oldest first: {id, cells}
        self.chunks: dict[str, int | None] = {}  # hash -> day it was orphaned, or None
        self.keep_last: int | None = None
        self.manifest_cells: dict[str, list[str]] = {}
        self.pending: list[str] = []
        self.maintenance_days: list[int] = []

    def referenced(self) -> set[str]:
        return {h for s in self.snapshots for h in s["cells"] if h}

    def doomed(self) -> list[str]:
        if self.keep_last is None:
            return []
        keep = max(self.keep_last, 1 if self.bug == "no-floor" else FLOOR)
        return [s["id"] for s in self.snapshots[: max(0, len(self.snapshots) - keep)]]

    def stored(self) -> int:
        return len(self.chunks) * CELL

    def sweep(self, days: int) -> dict:
        report: dict = {"retentionPolicy": [], "gc": [], "failures": []}
        doomed = self.doomed()
        if doomed:
            report["retentionPolicy"].append(
                {"lineageGuid": self.lineage, "deletedSnapshots": doomed, "keptSnapshots": FLOOR}
            )
            self.snapshots = [s for s in self.snapshots if s["id"] not in doomed]
            live = self.referenced()
            for digest, orphaned in self.chunks.items():
                if digest not in live and orphaned is None:
                    self.chunks[digest] = days
        freed = 0
        grace = 0 if self.bug == "no-grace" else GRACE_DAYS
        for digest, orphaned in list(self.chunks.items()):
            if orphaned is not None and days >= orphaned + grace:
                del self.chunks[digest]
                freed += CELL
        if freed and self.bug != "no-gc-accounting":
            report["gc"].append({"subscriptionId": "sub-1", "freedBytes": freed})
        return report

    def call(self, method: str, url: str, body: object) -> tuple[int, dict]:
        parts = urlsplit(url)
        path = parts.path
        data = body if isinstance(body, dict) else {}
        if path.endswith("/licenses/activate-repo"):
            self.lineage = str(data["repositoryGuid"])
            return 200, {"license": {"payload": "p"}}
        if path.endswith("/backups/session"):
            return 200, {"token": "rbs_t"}
        if path.endswith("/streams"):
            return 200, {"streamId": "stream-1"}
        if path.endswith("/exists"):
            return 200, {"existing": [h for h in data["hashes"] if h in self.chunks]}
        if path.endswith("/grants"):
            return 200, {"grant": {"putUrls": dict.fromkeys(data["hashes"], "u")}}
        if path.endswith("/commit"):
            self.snapshots.append({"id": data["snapshotId"], "cells": list(self.pending)})
            return 200, {"idempotent": False}
        if path.endswith("/manifests"):
            assert parse_qs(parts.query)["lineage"] == [self.lineage]
            return 200, {"manifests": [{"snapshotId": s["id"]} for s in reversed(self.snapshots)]}
        if path.endswith("/usage"):
            return 200, {"storedBytes": self.stored()}
        if path.endswith("/retention/preview"):
            doomed = self.doomed()
            return 200, {
                "deleted": [{"snapshotId": s} for s in doomed],
                "keptSnapshots": len(self.snapshots) - len(doomed),
            }
        if path.endswith("/retention") and method == "PUT":
            self.keep_last = int(data["keepLast"])
            return 200, {"policies": []}
        if path.endswith("/test/backup/maintenance"):
            now = datetime.datetime.fromisoformat(str(data["now"]))
            days = round((now - datetime.datetime.now(datetime.UTC)).total_seconds() / 86400)
            self.maintenance_days.append(days)
            return 200, {"report": self.sweep(days)}
        raise AssertionError("unmodelled call %s %s" % (method, path))


@pytest.fixture
def subject(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> backup.Backup:
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    (root / ".account-state").write_text(f"gateway_port={ACCOUNT_DEV_PORT}\nstarted=1\n")
    drill = backup.BackupDrill("backup", selftest=False, keep_work=False)
    drill.init()
    sub = backup.Backup(drill, backup.Options())
    sub.subscription_id = "sub-1"
    sub.api_token = "tok"
    sub.session_mint_url = "http://gw/account/api/v1/backups/session"
    monkeypatch.setattr(sub, "admin_jar", object())
    monkeypatch.setattr(drill, "account_mint_token", lambda *_a, **_k: "manage-token")
    return sub


def _cell_of(digest: str, subject: backup.Backup) -> bytes:
    for path in sorted(subject.work.glob("image-l*.bin")):
        for index in range(backup.CELLS):
            data = backup.slice_cell(path, index)
            if backup.sha256_hex(data) == digest:
                return data
    raise AssertionError("no source cell hashes to %s" % digest)


def _wire(subject: backup.Backup, plane: Plane, monkeypatch: pytest.MonkeyPatch) -> None:
    def api(method: str, url: str, body: object = None, headers: object = None) -> str:
        del headers
        code, reply = plane.call(method, url, body)
        subject.status = str(code)
        return json.dumps(reply)

    def put_manifest(snapshot: str, body: str) -> str:
        doc = json.loads(body)
        if "cells" in doc:
            cells = list(doc["cells"])
        else:
            cells = list(plane.manifest_cells[doc["parent"]])
            for index, digest in doc["changedCells"].items():
                cells[int(index)] = digest
        plane.manifest_cells[snapshot] = cells
        plane.pending = cells
        return "200"

    def upload_cells(plan: dict, image: pathlib.Path, missing: list[str]) -> int:
        del plan, image
        for digest in missing:
            plane.chunks[digest] = None
        return 0

    def restore_snapshot(
        snapshot: str, out: pathlib.Path, lineage: str = "", token: str = ""
    ) -> bool:
        assert lineage == plane.lineage
        assert token == "rbs_t"
        if snapshot not in {s["id"] for s in plane.snapshots}:
            return False
        out.write_bytes(
            b"".join(
                bytes(CELL) if not h else _cell_of(h, subject)
                for h in plane.manifest_cells[snapshot]
            )
        )
        return True

    monkeypatch.setattr(subject, "api", api)
    monkeypatch.setattr(subject, "put_manifest", put_manifest)
    monkeypatch.setattr(subject, "upload_cells", upload_cells)
    monkeypatch.setattr(subject, "restore_snapshot", restore_snapshot)


def test_leg_l_is_registered_and_needs_the_plane() -> None:
    assert "l" in backup.KNOWN_LEGS
    assert "l" in backup.DEFAULT_LEGS.split(",")
    opts = backup.Options()
    opts.legs = "l"
    assert opts.needs_plane()


def test_the_leg_l_fixture_changes_exactly_cell_three_and_collides_with_no_other_fixture(
    tmp_path: pathlib.Path,
) -> None:
    plans = []
    for step in range(3):
        path = tmp_path / ("l%d.bin" % step)
        backup.make_unique_image(path, step)
        plans.append(backup.plan_of(path))
    for earlier, later in itertools.pairwise(plans):
        changed = [
            i
            for i, (a, b) in enumerate(zip(earlier["cells"], later["cells"], strict=True))
            if a != b
        ]
        assert changed == [3]
    for index in backup.HOLES:
        assert plans[0]["cells"][index] == ""
    ours = {h for plan in plans for h in plan["unique"]}
    legacy = tmp_path / "v.bin"
    for version in ("1", "2"):
        backup.make_image(legacy, version)
        assert not set(backup.plan_of(legacy)["unique"]) & ours


def test_leg_l_passes_against_a_server_that_prunes_to_the_floor_and_frees_after_the_grace(
    subject: backup.Backup, monkeypatch: pytest.MonkeyPatch
) -> None:
    plane = Plane()
    _wire(subject, plane, monkeypatch)
    try:
        subject.leg_l_gc_and_retention()
        assert subject.d.failures == 0
        assert plane.maintenance_days == [8, 9, 17]
        assert len(plane.snapshots) == FLOOR
        assert plane.stored() == (6 + 4 - 2) * CELL
    finally:
        subject.d.teardown()


@pytest.mark.parametrize("bug", ["no-floor", "no-grace", "no-gc-accounting"])
def test_leg_l_goes_red_when_the_server_breaks_the_floor_the_grace_or_the_accounting(
    subject: backup.Backup, monkeypatch: pytest.MonkeyPatch, bug: str
) -> None:
    plane = Plane(bug)
    _wire(subject, plane, monkeypatch)
    try:
        subject.leg_l_gc_and_retention()
        assert subject.d.failures > 0
    finally:
        subject.d.teardown()
