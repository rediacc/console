"""Leg o of `rediacc_ci.drills.backup` (a twin tenant cannot reach another tenant's lineage) against an in-memory model of the control plane and a shared object store.

The model holds two tenants. Licenses name a (lineage, subscription) pair; sessions carry it; presigned URLs sign their own object key; the store is one dict shared by both tenants. The live run against `./run.sh account dev` and RustFS is the acceptance; these cases pin the leg's own logic, and that it goes red for each isolation defect planted into the model.
"""

from __future__ import annotations

import hashlib
import json
import typing
import urllib.parse

import pytest

from rediacc_ci.drills import backup
from rediacc_ci.well_known import ACCOUNT_DEV_PORT

if typing.TYPE_CHECKING:
    import pathlib

A_SUB, TWIN_SUB = "sub-a", "sub-twin"
A_LINEAGE = "lineage-a"
A_SNAP = "snap-seed-1"
BEARERS = {"tok-a": A_SUB, "tok-twin": TWIN_SUB}


def sign(key: str) -> str:
    return hashlib.sha256(("secret|" + key).encode()).hexdigest()


class Plane:
    """Control plane and store for two tenants. `bug` plants one isolation defect by name."""

    def __init__(self, bug: str = "") -> None:
        self.bug = bug
        self.store: dict[str, bytes] = {}  # object key -> bytes
        self.owner: dict[str, str] = {A_LINEAGE: A_SUB}  # lineage -> subscription
        self.sessions: dict[str, tuple[str, str, str]] = {}  # token -> (sub, lineage, intent)
        self.manifests: list[dict] = []

    # ---- object store (path-signed URLs)
    def url(self, key: str) -> str:
        return "http://store/bucket/%s?X-Amz-Signature=%s" % (key, sign(key))

    def chunk_url_in(self, sub: str, lineage: str, digest: str) -> str:
        return self.url("t/%s/l/%s/c/%s" % (sub, lineage, digest))

    @staticmethod
    def key_of(url: str) -> str:
        return urllib.parse.urlsplit(url).path.split("/", 2)[2]

    def signature_ok(self, url: str) -> bool:
        if self.bug == "path-unsigned":
            return True
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        return (query.get("X-Amz-Signature") or [""])[0] == sign(self.key_of(url))

    def put(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        if not self.signature_ok(url):
            return 403
        key = self.key_of(url)
        if headers.get("If-None-Match") == "*" and key in self.store:
            return 412
        self.store[key] = body
        return 200

    def get(self, method: str, url: str) -> tuple[int, bytes]:
        assert method == "GET"
        if not self.signature_ok(url):
            return 403, b""
        data = self.store.get(self.key_of(url))
        return (200, data) if data is not None else (404, b"")

    def s3_put(self, url: str, payload: bytes = b"") -> str:
        self.store[self.key_of(url)] = payload
        return "200"

    def s3_delete(self, url: str) -> str:
        self.store.pop(self.key_of(url), None)
        return "204"

    # ---- control plane
    def principal(self, headers: dict[str, str]) -> tuple[str, str, str]:
        return self.sessions[headers.get("X-Backup-Session", "")]

    def mismatch(self, lineage: str, principal: tuple[str, str, str]) -> bool:
        return self.bug != "lineage-unbound" and lineage != principal[1]

    @staticmethod
    def refused(code: str) -> tuple[int, dict]:
        return 403, {"code": code}

    def call(
        self, method: str, url: str, body: object, headers: dict[str, str] | None
    ) -> tuple[int, dict]:
        del method
        data = body if isinstance(body, dict) else {}
        headers = headers or {}
        if url.endswith("/licenses/activate-repo"):
            sub = BEARERS[headers["Authorization"].removeprefix("Bearer ")]
            guid = str(data["repositoryGuid"])
            if self.owner.setdefault(guid, sub) != sub and self.bug != "guid-shared":
                return self.refused("REPO_GUID_OWNERSHIP_CONFLICT")
            return 200, {"license": {"payload": "%s|%s" % (guid, sub)}}
        if url.endswith("/backups/session"):
            guid, sub = str(data["license"]["payload"]).split("|")
            token = "rbs_%d" % len(self.sessions)
            self.sessions[token] = (sub, guid, str(data.get("intent") or "backup"))
            return 200, {"token": token}
        if url.endswith("/streams"):
            return 200, {"streamId": "stream-1"}
        if "/manifests" in url:
            sub = BEARERS[headers["Authorization"].removeprefix("Bearer ")]
            lineage = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["lineage"][0]
            return 200, {
                "manifests": [
                    m
                    for m in self.manifests
                    if m["lineageGuid"] == lineage
                    and (m["sub"] == sub or self.bug == "manifests-cross-tenant")
                ]
            }
        principal = self.principal(headers)
        sub = principal[0]
        asked = str(data.get("lineageGuid") or "")
        if url.endswith("/exists"):
            if self.mismatch(asked, principal):
                return self.refused("BACKUP_LINEAGE_MISMATCH")
            found = []
            for h in data["hashes"]:
                if self.bug == "exists-cross-tenant":
                    hit = any(k.endswith("/l/%s/c/%s" % (asked, h)) for k in self.store)
                else:
                    hit = "t/%s/l/%s/c/%s" % (sub, asked, h) in self.store
                if hit:
                    found.append(h)
            return 200, {"existing": found}
        if url.endswith("/read-grants"):
            if self.mismatch(asked, principal):
                return self.refused("BACKUP_LINEAGE_MISMATCH")
            snap = str(data["snapshotId"])
            return 200, {
                "manifestChain": [snap],
                "manifestGetUrls": {snap: self.url("t/%s/l/%s/m/%s" % (sub, asked, snap))},
                "getUrls": {h: self.chunk_url_in(sub, asked, h) for h in data.get("hashes", [])},
            }
        if url.endswith("/grants"):
            if self.mismatch(asked, principal):
                return self.refused("BACKUP_LINEAGE_MISMATCH")
            return 200, {
                "grant": {
                    "putUrls": {h: self.chunk_url_in(sub, asked, h) for h in data["hashes"]},
                    "manifestPutUrl": self.url("t/%s/l/%s/m/%s" % (sub, asked, data["snapshotId"])),
                }
            }
        if url.endswith("/commit"):
            self.manifests.append(
                {"sub": sub, "lineageGuid": asked, "snapshotId": str(data["snapshotId"])}
            )
            return 200, {"idempotent": False}
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
    sub.subscription_id = A_SUB
    sub.api_token = "tok-a"
    sub.session_mint_url = "http://gw/account/api/v1/backups/session"
    return sub


def _wire(subject: backup.Backup, plane: Plane, monkeypatch: pytest.MonkeyPatch) -> None:
    """Seed tenant A (what legs a and b leave behind) and route every call into `plane`."""
    image = subject.work / "image-v1.bin"
    backup.make_image(image, "1")
    seed_plan = backup.plan_of(image)
    for index, digest in enumerate(seed_plan["cells"]):
        if digest:
            plane.store["t/%s/l/%s/c/%s" % (A_SUB, A_LINEAGE, digest)] = backup.slice_cell(
                image, index
            )
    plane.store["t/%s/l/%s/m/%s" % (A_SUB, A_LINEAGE, A_SNAP)] = json.dumps(
        {"snapshotId": A_SNAP, "cells": seed_plan["cells"]}
    ).encode()
    plane.manifests.append({"sub": A_SUB, "lineageGuid": A_LINEAGE, "snapshotId": A_SNAP})
    subject.stored_lineage = A_LINEAGE
    subject.snap_seed = A_SNAP
    subject.seed_sha = backup.sha256_hex(image.read_bytes())
    subject.license_blob = {"payload": "%s|%s" % (A_LINEAGE, A_SUB)}
    subject.machine_id = "machine-a"

    def api(method: str, url: str, body: object = None, headers: object = None) -> str:
        code, reply = plane.call(method, url, body, headers if isinstance(headers, dict) else None)
        subject.status = str(code)
        return json.dumps(reply)

    def upload_cells(plan: dict, image: pathlib.Path, missing: list[str]) -> int:
        urls = subject.grant["grant"]["putUrls"]
        for digest in missing:
            plane.put(urls[digest], backup.slice_cell(image, plan["cells"].index(digest)), {})
        return 0

    def put_manifest(_snapshot: str, text: str) -> str:
        return str(plane.put(subject.grant["grant"]["manifestPutUrl"], text.encode(), {}))

    d = subject.d
    monkeypatch.setattr(subject, "api", api)
    monkeypatch.setattr(subject, "upload_cells", upload_cells)
    monkeypatch.setattr(subject, "put_manifest", put_manifest)
    monkeypatch.setattr(subject, "presigned_put", plane.put)
    monkeypatch.setattr(subject, "s3_put", plane.s3_put)
    monkeypatch.setattr(subject, "s3_delete", plane.s3_delete)
    monkeypatch.setattr(subject, "chunk_url_in", plane.chunk_url_in)
    monkeypatch.setattr(
        backup.wire, "http_bytes", lambda method, url, *_a, **_k: plane.get(method, url)
    )
    monkeypatch.setattr(d, "account_ensure_login", lambda *_a: None)
    monkeypatch.setattr(d, "account_ensure_subscription", lambda *_a, **_k: None)
    monkeypatch.setattr(d, "account_session", lambda *_a: True)
    monkeypatch.setattr(d, "account_subscription_id", lambda _jar: TWIN_SUB)
    monkeypatch.setattr(d, "account_mint_token", lambda *_a: "tok-twin")


def test_leg_o_is_registered_and_needs_the_plane() -> None:
    assert "o" in backup.KNOWN_LEGS
    assert "o" in backup.DEFAULT_LEGS.split(",")
    opts = backup.Options()
    opts.legs = "o"
    assert opts.needs_plane()


def test_leg_o_passes_against_a_plane_that_isolates_the_tenants(
    subject: backup.Backup, monkeypatch: pytest.MonkeyPatch
) -> None:
    plane = Plane()
    _wire(subject, plane, monkeypatch)
    try:
        subject.leg_o_twin_tenant_isolation()
        assert subject.d.failures == 0
        # Both plants were removed again.
        assert not [k for k in plane.store if k.startswith("t/%s/l/%s/" % (TWIN_SUB, A_LINEAGE))]
    finally:
        subject.d.teardown()


@pytest.mark.parametrize(
    "bug",
    [
        "guid-shared",
        "lineage-unbound",
        "exists-cross-tenant",
        "path-unsigned",
        "manifests-cross-tenant",
    ],
)
def test_leg_o_goes_red_for_each_planted_isolation_bug(
    subject: backup.Backup, monkeypatch: pytest.MonkeyPatch, bug: str
) -> None:
    plane = Plane(bug)
    _wire(subject, plane, monkeypatch)
    try:
        subject.leg_o_twin_tenant_isolation()
        assert subject.d.failures > 0
    finally:
        subject.d.teardown()


def test_run_all_refuses_leg_o_without_leg_b() -> None:
    """Without leg b there is no stored lineage to protect, and the leg would test an empty tenant."""
    assert any(
        isinstance(c, str) and "Include leg b" in c
        for c in backup.Backup.run_all.__code__.co_consts
    )
