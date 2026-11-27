"""check:ci-windows-image-expiry: every verdict of the Windows evaluation image expiry gate, on fixture records and a planted clock."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.core import gate_clock
from rediacc_ci.quality import windows_image_expiry as gate

if TYPE_CHECKING:
    import pathlib

NOW = dt.datetime(2026, 11, 27, 12, 0, tzinfo=dt.UTC)
ISO, VIRTIO = "a" * 64, "b" * 64
REBAKE = "PYTHONPATH=.ci python3 -m rediacc_ci.ops.windows_image rebake"


def record(tmp: pathlib.Path, *, days: float | None = 30.0, iso: str = ISO, **over) -> pathlib.Path:
    doc: dict = {
        "schema": 1,
        "bucket": "windows-ci-images",
        "warn_days": 14,
        "rebake": REBAKE,
        "inputs": {"iso": {"sha256": ISO}, "virtio": {"sha256": VIRTIO}},
        "image": None,
    }
    if days is not None:
        doc["image"] = {
            "key": "images/win11/26300.9457-2026-11-01/golden.tar.zst",
            "iso_sha256": iso,
            "virtio_iso_sha256": VIRTIO,
            "installed_at": "2026-11-01T00:00:00Z",
            "expires_at": (NOW + dt.timedelta(days=days)).isoformat().replace("+00:00", "Z"),
        }
    doc.update(over)
    path = tmp / "windows-image.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_null_image_is_green(tmp_path: pathlib.Path) -> None:
    rc, lines = gate.evaluate(record(tmp_path, days=None), NOW)
    assert rc == 0
    assert "NO WINDOWS IMAGE RECORDED" in lines[0]


def test_fifteen_days_is_green(tmp_path: pathlib.Path) -> None:
    rc, lines = gate.evaluate(record(tmp_path, days=15), NOW)
    assert rc == 0, lines
    assert "15 day(s) left" in lines[0]


def test_fourteen_days_is_red_naming_rebake(tmp_path: pathlib.Path) -> None:
    rc, lines = gate.evaluate(record(tmp_path, days=14), NOW)
    assert rc == 1
    text = "\n".join(lines)
    assert "14 day(s) left" in text
    assert REBAKE in text
    assert "expires at" in text


def test_expired_is_red(tmp_path: pathlib.Path) -> None:
    rc, lines = gate.evaluate(record(tmp_path, days=-3), NOW)
    assert rc == 1
    assert "EXPIRED 3 day(s) ago" in "\n".join(lines)


def test_missing_file_is_red(tmp_path: pathlib.Path) -> None:
    rc, lines = gate.evaluate(tmp_path / "absent.json", NOW)
    assert rc == 1
    assert "cannot read" in lines[0]


@pytest.mark.parametrize("body", ["{not json", "[]", '{"schema": 2}'])
def test_unparseable_file_is_red(tmp_path: pathlib.Path, body: str) -> None:
    path = tmp_path / "windows-image.json"
    path.write_text(body, encoding="utf-8")
    assert gate.evaluate(path, NOW)[0] == 1


def test_bad_expiry_is_red(tmp_path: pathlib.Path) -> None:
    path = record(tmp_path)
    doc = json.loads(path.read_text())
    doc["image"]["expires_at"] = "soon"
    path.write_text(json.dumps(doc))
    assert gate.evaluate(path, NOW)[0] == 1


def test_input_hash_mismatch_is_red(tmp_path: pathlib.Path) -> None:
    rc, lines = gate.evaluate(record(tmp_path, days=60, iso="c" * 64), NOW)
    assert rc == 1
    assert "differs from inputs.iso.sha256" in "\n".join(lines)


def test_image_without_inputs_is_red(tmp_path: pathlib.Path) -> None:
    assert gate.evaluate(record(tmp_path, days=60, inputs=None), NOW)[0] == 1


def _run(path: pathlib.Path, clock: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "CI"}
    env.update(
        {"PYTHONPATH": str(paths.from_root(".ci")), gate_clock.TEST_ENV: "1", gate_clock.ENV: clock}
    )
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.quality.windows_image_expiry", str(path)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_module_reads_the_planted_clock(tmp_path: pathlib.Path) -> None:
    """The same record is green at NOW and red once the clock is planted past the warning window."""
    path = record(tmp_path, days=30)
    assert _run(path, NOW.isoformat()).returncode == 0
    late = _run(path, (NOW + dt.timedelta(days=20)).isoformat())
    assert late.returncode == 1
    assert REBAKE in late.stderr


def test_committed_record_is_judged() -> None:
    rc, lines = gate.evaluate(paths.repo_root() / gate.RECORD_REL, NOW)
    doc = json.loads((paths.repo_root() / gate.RECORD_REL).read_text())
    if doc["image"] is None:
        assert rc == 0
        assert "NO WINDOWS IMAGE RECORDED" in lines[0]
    else:
        assert lines
