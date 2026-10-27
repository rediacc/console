"""Leg m of `rediacc_ci.drills.backup` (the scheduled verify against a real store) against an in-memory model of the control plane and the object store.

The model keeps what the leg reads: one lineage's referenced chunks, an object store keyed by chunk URL, and a maintenance pass that HEADs and samples them. The live run against `./run.sh account dev` and RustFS is the acceptance; these cases pin the leg's own logic, and that it goes red when the verify misses a tampered chunk.
"""

from __future__ import annotations

import datetime
import json
import typing

import pytest

from rediacc_ci.drills import backup
from rediacc_ci.well_known import ACCOUNT_DEV_PORT

if typing.TYPE_CHECKING:
    import pathlib

CELL = backup.CELL_BYTES


class Plane:
    """The control plane and store as the leg sees them. `bug` plants one verify defect by name."""

    def __init__(self, bug: str = "") -> None:
        self.bug = bug
        self.lineage = ""
        self.referenced: list[str] = []
        self.objects: dict[str, bytes] = {}  # digest -> bytes
        self.maintenance_days: list[int] = []

    def verify(self) -> list[dict]:
        missing = [h for h in self.referenced if h not in self.objects]
        corrupt = [
            h
            for h in self.referenced
            if h in self.objects and backup.sha256_hex(self.objects[h]) != h
        ]
        if self.bug == "blind-head":
            missing = []
        if self.bug == "blind-sample":
            corrupt = []
        return [
            {
                "subscriptionId": "sub-1",
                "lineageGuid": self.lineage,
                "level": "head",
                "checked": len(self.referenced),
                "missing": missing,
                "corrupt": [],
                "passComplete": True,
            },
            {
                "subscriptionId": "sub-1",
                "lineageGuid": self.lineage,
                "level": "sample",
                "checked": len(self.referenced),
                "missing": missing,
                "corrupt": corrupt,
                "passComplete": True,
            },
            # Another lineage's entry must be ignored by the leg.
            {
                "subscriptionId": "sub-1",
                "lineageGuid": "other",
                "level": "head",
                "checked": 9,
                "missing": ["x"],
                "corrupt": [],
                "passComplete": True,
            },
        ]

    def call(self, url: str, body: object) -> tuple[int, dict]:
        data = body if isinstance(body, dict) else {}
        if url.endswith("/licenses/activate-repo"):
            self.lineage = str(data["repositoryGuid"])
            return 200, {"license": {"payload": "p"}}
        if url.endswith("/backups/session"):
            return 200, {"token": "rbs_t"}
        if url.endswith("/streams"):
            return 200, {"streamId": "stream-1"}
        if url.endswith("/exists"):
            return 200, {"existing": [h for h in data["hashes"] if h in self.objects]}
        if url.endswith("/grants"):
            return 200, {"grant": {"putUrls": dict.fromkeys(data["hashes"], "u")}}
        if url.endswith("/commit"):
            return 200, {"idempotent": False}
        if url.endswith("/test/backup/maintenance"):
            now = datetime.datetime.fromisoformat(str(data["now"]))
            self.maintenance_days.append(
                round((now - datetime.datetime.now(datetime.UTC)).total_seconds() / 86400)
            )
            return 200, {"report": {"verify": self.verify(), "failures": []}}
        raise AssertionError("unmodelled call %s" % url)


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
    return sub


def _wire(subject: backup.Backup, plane: Plane, monkeypatch: pytest.MonkeyPatch) -> None:
    def api(method: str, url: str, body: object = None, headers: object = None) -> str:
        del method, headers
        code, reply = plane.call(url, body)
        subject.status = str(code)
        return json.dumps(reply)

    def upload_cells(plan: dict, image: pathlib.Path, missing: list[str]) -> int:
        for digest in missing:
            plane.objects[digest] = backup.slice_cell(image, plan["cells"].index(digest))
        plane.referenced = list(plan["unique"])
        return 0

    def digest_of(url: str) -> str:
        assert "/t/sub-1/l/%s/c/" % plane.lineage in url
        return url.rsplit("/", 1)[1]

    def s3_delete(url: str) -> str:
        plane.objects.pop(digest_of(url), None)
        return "204"

    def s3_put(url: str, payload: bytes = b"") -> str:
        plane.objects[digest_of(url)] = payload
        return "200"

    monkeypatch.setattr(subject, "api", api)
    monkeypatch.setattr(subject, "put_manifest", lambda _snap, _body: "200")
    monkeypatch.setattr(subject, "upload_cells", upload_cells)
    monkeypatch.setattr(subject, "s3_delete", s3_delete)
    monkeypatch.setattr(subject, "s3_put", s3_put)


def test_leg_m_is_registered_and_needs_the_plane() -> None:
    assert "m" in backup.KNOWN_LEGS
    assert "m" in backup.DEFAULT_LEGS.split(",")
    opts = backup.Options()
    opts.legs = "m"
    assert opts.needs_plane()


def test_the_leg_m_fixture_has_exactly_two_non_zero_cells(tmp_path: pathlib.Path) -> None:
    plan = backup.make_two_cell_image(tmp_path / "m.bin")
    assert [i for i, h in enumerate(plan["cells"]) if h] == list(backup.M_CELLS)
    assert len(plan["unique"]) == 2
    image = (tmp_path / "m.bin").read_bytes()
    for index in range(backup.CELLS):
        cell = image[index * CELL : (index + 1) * CELL]
        assert (backup.sha256_hex(cell) == plan["cells"][index]) == (index in backup.M_CELLS)
        assert any(cell) == (index in backup.M_CELLS)


def test_leg_m_passes_against_a_verify_that_sees_the_deleted_and_the_overwritten_chunk(
    subject: backup.Backup, monkeypatch: pytest.MonkeyPatch
) -> None:
    plane = Plane()
    _wire(subject, plane, monkeypatch)
    try:
        subject.leg_m_scheduled_verify()
        assert subject.d.failures == 0
        assert plane.maintenance_days == [backup.M_CONTROL_DAYS, backup.M_TAMPER_DAYS]
        assert len(plane.objects) == 1
    finally:
        subject.d.teardown()


@pytest.mark.parametrize("bug", ["blind-head", "blind-sample"])
def test_leg_m_goes_red_when_the_verify_misses_the_tampering(
    subject: backup.Backup, monkeypatch: pytest.MonkeyPatch, bug: str
) -> None:
    plane = Plane(bug)
    _wire(subject, plane, monkeypatch)
    try:
        subject.leg_m_scheduled_verify()
        assert subject.d.failures > 0
    finally:
        subject.d.teardown()
