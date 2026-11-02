"""Leg n of `rediacc_ci.drills.backup` (a presigned chunk PUT is bound to its declared size and checksum) against an in-memory model of the control plane and a store.

The model signs the URLs it hands out: `X-Amz-SignedHeaders` names what the store will enforce, and the store checks exactly that. The live run against RustFS (and, under tier B, R2) is the acceptance; these cases pin the leg's own logic, and that it goes red when the store accepts what the signature should have refused.
"""

from __future__ import annotations

import base64
import json
import typing
import urllib.parse

import pytest

from rediacc_ci.drills import backup
from rediacc_ci.well_known import ACCOUNT_DEV_PORT

if typing.TYPE_CHECKING:
    import pathlib

CELL = backup.CELL_BYTES
SIGNED_BOTH = "content-length;host;if-none-match;x-amz-checksum-sha256"


class Plane:
    """The control plane and the store as the leg sees them. `bug` plants one defect by name."""

    def __init__(self, bug: str = "") -> None:
        self.bug = bug
        self.objects: dict[str, bytes] = {}  # hash -> bytes
        self.puts: list[tuple[int, int]] = []  # (body length, status)

    def signed(self) -> str:
        if self.bug == "length-unsigned":
            return "host;if-none-match;x-amz-checksum-sha256"
        if self.bug == "checksum-unsigned":
            return "content-length;host;if-none-match"
        return SIGNED_BOTH

    def url(self, digest: str) -> str:
        base = "http://store/bucket/t/sub-1/l/lin/c/%s" % digest
        return base + "?X-Amz-SignedHeaders=" + urllib.parse.quote(self.signed(), safe="")

    def put(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        digest = urllib.parse.urlsplit(url).path.rsplit("/", 1)[1]
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        signed = set((query.get("X-Amz-SignedHeaders") or [""])[0].split(";"))
        status = self.decide(digest, signed, body, headers)
        if status == 200:
            self.objects[digest] = body
        self.puts.append((len(body), status))
        return status

    def decide(self, digest: str, signed: set[str], body: bytes, headers: dict[str, str]) -> int:
        if self.bug == "store-refuses-all":
            return 403
        if "content-length" in signed and len(body) != CELL and self.bug != "store-ignores-length":
            return 403
        if "x-amz-checksum-sha256" in signed:
            sent = headers.get("x-amz-checksum-sha256", "")
            actual = base64.b64encode(bytes.fromhex(backup.sha256_hex(body))).decode()
            if sent != actual:
                return 400
        if digest in self.objects:
            return 412
        return 200

    def call(self, url: str, body: object) -> tuple[int, dict]:
        data = body if isinstance(body, dict) else {}
        if url.endswith("/licenses/activate-repo"):
            return 200, {"license": {"payload": "p"}}
        if url.endswith("/backups/session"):
            return 200, {"token": "rbs_t"}
        if url.endswith("/streams"):
            return 200, {"streamId": "stream-1"}
        if url.endswith("/exists"):
            return 200, {"existing": [h for h in data["hashes"] if h in self.objects]}
        if url.endswith("/grants"):
            # The account refuses a grant without its sizes (private/account 4da3475): every call carries manifestBytes, and a call naming hashes carries chunkBytes.
            if "manifestBytes" not in data or (data.get("hashes") and "chunkBytes" not in data):
                return 400, {"error": "chunkBytes and manifestBytes are required"}
            return 200, {"grant": {"putUrls": {h: self.url(h) for h in data["hashes"]}}}
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

    def s3_delete(url: str) -> str:
        plane.objects.pop(url.rsplit("/", 1)[1], None)
        return "204"

    monkeypatch.setattr(subject, "api", api)
    monkeypatch.setattr(subject, "presigned_put", plane.put)
    monkeypatch.setattr(subject, "s3_delete", s3_delete)


def test_leg_n_is_registered_and_needs_the_plane() -> None:
    assert "n" in backup.KNOWN_LEGS
    assert "n" in backup.DEFAULT_LEGS.split(",")
    opts = backup.Options()
    opts.legs = "n"
    assert opts.needs_plane()


def test_leg_n_passes_against_a_store_that_enforces_the_signed_bound(
    subject: backup.Backup, monkeypatch: pytest.MonkeyPatch
) -> None:
    plane = Plane()
    _wire(subject, plane, monkeypatch)
    try:
        subject.leg_n_bounded_put()
        assert subject.d.failures == 0
        # Oversize refused, wrong content refused, the exact body accepted; the unsized grant is refused with 400 (failures == 0 covers that assertion).
        assert plane.puts[:3] == [(CELL + 1, 403), (CELL, 400), (CELL, 200)]
    finally:
        subject.d.teardown()


@pytest.mark.parametrize("bug", ["length-unsigned", "checksum-unsigned", "store-refuses-all"])
def test_leg_n_goes_red_for_each_planted_bug(
    subject: backup.Backup, monkeypatch: pytest.MonkeyPatch, bug: str
) -> None:
    plane = Plane(bug)
    _wire(subject, plane, monkeypatch)
    try:
        subject.leg_n_bounded_put()
        assert subject.d.failures > 0
    finally:
        subject.d.teardown()


def test_the_leg_n_fixture_cells_are_distinct_and_full_size(tmp_path: pathlib.Path) -> None:
    plan = backup.make_two_cell_image(tmp_path / "n.bin")
    first, second = (backup.slice_cell(tmp_path / "n.bin", i) for i in backup.M_CELLS)
    assert len(first) == len(second) == CELL
    assert first != second
    assert len(plan["unique"]) == 2


def test_a_store_that_ignores_the_length_is_still_caught_by_the_checksum(
    subject: backup.Backup, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Size and content are redundant guards on one PUT: a longer body cannot hash to the signed checksum, so a store that enforces only the checksum still refuses the oversize body. The leg pins the size half through the signed-header assertion, not through the store's status."""
    plane = Plane("store-ignores-length")
    _wire(subject, plane, monkeypatch)
    try:
        subject.leg_n_bounded_put()
        assert subject.d.failures == 0
        assert plane.puts[0] == (CELL + 1, 400)
    finally:
        subject.d.teardown()
