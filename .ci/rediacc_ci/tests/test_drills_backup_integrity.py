"""The pure parts of legs p to s, the harness guard, and the on-premise fake. The legs' live behaviour is the drill itself."""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import pathlib
import subprocess
import threading
import urllib.error

import pytest

from rediacc_ci.drills import backup
from rediacc_ci.drills import backup_onprem as onprem
from rediacc_ci.drills import backup_renet as renet

ROOT = pathlib.Path(__file__).resolve()
VECTORS = pathlib.Path(
    "/home/developer/console/private/renet/pkg/chunkstore/testdata/cells_root_vectors.json"
)


def test_the_drill_root_gives_every_known_answer() -> None:
    vectors = json.loads(VECTORS.read_text())["vectors"]
    assert vectors
    for v in vectors:
        assert backup.cells_root(v["cells"], v["cellBytes"], v["imageBytes"]) == v["root"], v[
            "name"
        ]


def test_a_delta_manifest_commits_to_the_whole_image_and_the_declared_identity(
    tmp_path: pathlib.Path,
) -> None:
    seed, incr = tmp_path / "1", tmp_path / "2"
    backup.make_image(seed, "1")
    backup.make_image(incr, "2")
    a, b = backup.plan_of(seed), backup.plan_of(incr)
    doc = json.loads(backup.wire_manifest("s2", b, "l", "s1", a, ("u", "k")))
    assert doc["changedCells"] == {"3": b["cells"][3]}
    assert doc["cellsRoot"] == backup.plan_root(b) != backup.plan_root(a)
    assert (doc["luksUuid"], doc["luksKeyDigest"]) == ("u", "k")
    assert "luksUuid" not in json.loads(backup.wire_manifest("s1", a, "l"))


def make_backup(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> backup.Backup:
    monkeypatch.setenv("REDIACC_CI_ROOT", str(tmp_path))
    drill = backup.BackupDrill("backup", selftest=False, keep_work=False)
    drill.init()
    return backup.Backup(drill, backup.Options())


def test_an_empty_presigned_url_stops_the_leg_before_any_request(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = make_backup(tmp_path, monkeypatch)
    monkeypatch.setattr(backup.wire, "http_bytes", lambda *_a, **_k: pytest.fail("opened a URL"))
    monkeypatch.setattr(backup.wire, "http_call", lambda *_a, **_k: pytest.fail("opened a URL"))
    with pytest.raises(backup.LegStoppedError, match="presigned GET"):
        subject.presigned_get("")
    with pytest.raises(backup.LegStoppedError, match="presigned PUT"):
        subject.presigned_put("", b"", {})


@pytest.mark.parametrize(
    "boom",
    [
        urllib.error.URLError("refusing a URL this call may not open: "),
        backup.LegStoppedError("nothing to read"),
        SystemExit(1),
        KeyError("cells"),
        backup.backup_roundtrip.StepError("VM command failed"),
    ],
)
def test_a_crashing_leg_is_one_named_failure_and_the_next_leg_still_runs(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, boom: BaseException
) -> None:
    subject = make_backup(tmp_path, monkeypatch)
    ran: list[str] = []

    def crash() -> None:
        raise boom

    subject.run_leg("o", crash)
    subject.run_leg("k", lambda: ran.append("k"))
    assert ran == ["k"]
    assert subject.d.failures == 1
    assert subject.d.rows[-1][2] == "leg o stopped early"
    assert subject.d.summary() == 1


@pytest.mark.parametrize(
    ("line", "verdict"),
    [
        ("Backup store preflight: passed (duplicate PUT 412, wrong checksum 400).", "passed"),
        ("Backup store preflight: FAILED. The store accepted", "failed"),
        ("Backup store preflight: warning. A duplicate", "warning"),
        ("Backup store preflight: could not check (x); asked again", "could-not-check"),
        ("Backup store preflight: not applicable (no presigned grant path).", "none"),
        ("", "none"),
    ],
)
def test_preflight_verdict(line: str, verdict: str) -> None:
    assert onprem.preflight_verdict(line) == verdict


@pytest.mark.parametrize(("enforce", "wrong_status"), [(False, 200), (True, 400)])
def test_the_fake_store_is_non_conforming_in_the_way_each_row_needs(
    enforce: bool, wrong_status: int
) -> None:
    fake = onprem.FakeStore(enforce)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    try:

        def put(body: bytes, signed: bytes) -> int:
            digest = base64.b64encode(hashlib.sha256(signed).digest()).decode()
            connection = http.client.HTTPConnection("127.0.0.1", fake.server_address[1], timeout=5)
            try:
                connection.request(
                    "PUT", "/b/k", body, {"x-amz-checksum-sha256": digest, "If-None-Match": "*"}
                )
                return connection.getresponse().status
            finally:
                connection.close()

        assert put(b"a", b"a") == 200
        assert put(b"a", b"a") == 200, (
            "a duplicate must not be refused: that is the defect it plants"
        )
        assert put(b"b", b"a") == wrong_status
    finally:
        fake.shutdown()
        fake.server_close()


def test_the_journal_commands_move_it_aside_and_back(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(renet, "JOURNAL_DIR", str(tmp_path))
    journal = tmp_path / "ds-guid.json"
    other = tmp_path / "ds-other.json"
    journal.write_text("{}")
    other.write_text("{}")

    def run(command: str) -> None:
        subprocess.run(["/bin/sh", "-c", command.replace("sudo -n ", "")], check=True)

    run(renet.journal_aside_command("guid"))
    assert not journal.exists()
    assert other.exists()
    assert (tmp_path / ("ds-guid.json" + renet.JOURNAL_ASIDE)).exists()
    run(renet.journal_back_command("guid"))
    assert journal.exists()


def test_the_swap_commands_replace_the_image_and_put_it_back(tmp_path: pathlib.Path) -> None:
    ds = tmp_path
    (ds / "repositories").mkdir()
    image = ds / "repositories" / "guid"
    image.write_bytes(b"original")
    swap = renet.swap_image_command(str(ds), "guid")
    assert "luksFormat" in swap
    assert (
        subprocess.run(["sh", "-n", "-c", swap.replace("sudo -n ", "")], check=False).returncode
        == 0
    )
    subprocess.run(
        ["/bin/sh", "-c", renet.unswap_image_command(str(ds), "guid").replace("sudo -n ", "")],
        check=False,
    )
    assert image.read_bytes() == b"original"


def test_the_new_legs_are_registered_and_need_the_plane() -> None:
    for leg in "pqrs":
        assert leg in backup.KNOWN_LEGS
        assert leg in backup.DEFAULT_LEGS.split(",")
        opts = backup.Options()
        opts.legs = leg
        assert opts.needs_plane()
