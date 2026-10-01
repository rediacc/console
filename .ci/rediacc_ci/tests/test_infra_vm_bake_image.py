"""`rediacc_ci.infra.vm_bake_image`: publish and fetch of the pre-baked E2E VM images.

Every case drives the module through a fake `run` (or a fake download), so nothing touches a registry, libvirt or the network. The verdicts that carry the design, each with its control:

  * fetch: a registry "not found" and any other pull failure are both a MISS that exports nothing, while a pull that lands one image is a HIT that exports REDIACC_OPS_DISKS_PATH, BAKED_IMAGE_KEY and RENET_SETUP_OFFLINE (the stock fallback depends on the first, the baked leg on the second);
  * probe: "not found" is a miss, but an auth failure raises, so a broken login cannot pass for a missing image;
  * install-oras: a download whose sha256 differs from the pin is refused.
"""

from __future__ import annotations

import hashlib
import io
import pathlib
import subprocess
import tarfile
from typing import Any

import pytest

from rediacc_ci.infra import vm_bake_image as vbi
from rediacc_ci.well_known import IMAGE_REGISTRY

KEY = "vm-bake-v1-debian-13-2026-09-08e81f4c97c76189"
IMAGE_NAME = "debian-13-genericcloud-amd64.qcow2"


class FakeRun:
    """Records each argv and answers from a queue of (returncode, stdout, stderr, side_effect)."""

    def __init__(self, *answers: tuple[int, str, str] | tuple[int, str, str, Any]) -> None:
        self.answers = list(answers)
        self.calls: list[list[str]] = []
        self.kwargs: list[dict[str, Any]] = []

    def __call__(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(argv))
        self.kwargs.append(kw)
        rc, out, err, *effect = self.answers.pop(0)
        if effect:
            effect[0](argv)
        return subprocess.CompletedProcess(argv, rc, out, err)


def _pulls_one_image(argv: list[str]) -> None:
    dest = argv[argv.index("--output") + 1]
    (pathlib.Path(dest) / IMAGE_NAME).write_bytes(b"qcow2")


def test_image_ref_names_the_one_package_and_refuses_a_non_key() -> None:
    assert vbi.image_ref(KEY) == (IMAGE_REGISTRY + "/ci-vm-bake:") + KEY
    with pytest.raises(vbi.BakeImageError):
        vbi.image_ref("latest")


# --- probe -------------------------------------------------------------------


def test_probe_hit() -> None:
    assert vbi.tag_exists(vbi.image_ref(KEY), FakeRun((0, "{}", "")))


def test_probe_not_found_is_a_miss() -> None:
    err = 'Error response from registry: failed to fetch the content of "x": x: not found'
    assert not vbi.tag_exists(vbi.image_ref(KEY), FakeRun((1, "", err)))


def test_probe_auth_failure_raises_rather_than_reading_as_a_miss() -> None:
    with pytest.raises(vbi.BakeImageError, match="unauthorized"):
        vbi.tag_exists(
            vbi.image_ref(KEY), FakeRun((1, "", "Error: unauthorized: authentication required"))
        )


# --- fetch -------------------------------------------------------------------


def test_fetch_hit_returns_the_single_image(tmp_path: pathlib.Path) -> None:
    dest = tmp_path / "disks-baked"
    run = FakeRun((0, "", "", _pulls_one_image))
    image, reason = vbi.fetch(KEY, dest, run)
    assert reason == ""
    assert image == dest / IMAGE_NAME
    assert run.calls[0][:3] == ["oras", "pull", vbi.image_ref(KEY)]


def test_fetch_not_found_is_a_miss_and_leaves_no_directory(tmp_path: pathlib.Path) -> None:
    dest = tmp_path / "disks-baked"
    image, reason = vbi.fetch(KEY, dest, FakeRun((1, "", "x: not found")))
    assert image is None
    assert reason.startswith("no baked image")
    assert not dest.exists()


def test_fetch_other_failure_is_also_a_miss(tmp_path: pathlib.Path) -> None:
    image, reason = vbi.fetch(KEY, tmp_path / "d", FakeRun((1, "", "connection reset by peer")))
    assert image is None
    assert "connection reset" in reason


def test_fetch_missing_oras_is_a_miss(tmp_path: pathlib.Path) -> None:
    def no_oras(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(argv[0])

    image, reason = vbi.fetch(KEY, tmp_path / "d", no_oras)
    assert image is None
    assert "did not complete" in reason


def test_fetch_empty_pull_is_a_miss(tmp_path: pathlib.Path) -> None:
    image, reason = vbi.fetch(KEY, tmp_path / "d", FakeRun((0, "", "")))
    assert image is None
    assert "0 file(s)" in reason


def _drive_fetch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, run: FakeRun, oras_on_path: bool = True
) -> tuple[str, str]:
    out, env = tmp_path / "out", tmp_path / "env"
    out.touch()
    env.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_ENV", str(env))
    monkeypatch.setattr(vbi, "_key", lambda _distro: KEY)
    monkeypatch.setattr(vbi.fetch, "__defaults__", (run,))
    monkeypatch.setattr(
        vbi.shutil, "which", lambda _name: "/usr/bin/oras" if oras_on_path else None
    )
    argv = [
        "fetch",
        "--distro",
        "debian-13",
        "--dest",
        str(tmp_path / "disks-baked"),
        "--oras-dir",
        str(tmp_path / "oras-bin"),
    ]
    assert vbi.main(argv) == 0
    return out.read_text(), env.read_text()


def test_cli_fetch_hit_exports_the_three_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    out, env = _drive_fetch(monkeypatch, tmp_path, FakeRun((0, "", "", _pulls_one_image)))
    assert "hit=true\n" in out
    assert "REDIACC_OPS_DISKS_PATH=%s\n" % (tmp_path / "disks-baked") in env
    assert "BAKED_IMAGE_KEY=%s\n" % KEY in env
    assert "RENET_SETUP_OFFLINE=1\n" in env


def test_cli_fetch_miss_exports_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    out, env = _drive_fetch(monkeypatch, tmp_path, FakeRun((1, "", "x: not found")))
    assert "hit=false\n" in out
    assert env == ""


def test_cli_fetch_failed_oras_install_is_a_miss(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    def broken(_dest: pathlib.Path) -> pathlib.Path:
        raise vbi.BakeImageError("oras 1.3.4 sha256 mismatch")

    monkeypatch.setattr(vbi, "install_oras", broken)
    run = FakeRun()
    out, env = _drive_fetch(monkeypatch, tmp_path, run, oras_on_path=False)
    assert "hit=false\n" in out
    assert env == ""
    assert run.calls == []


# --- build and publish -------------------------------------------------------


def test_build_defines_the_network_once_and_returns_the_printed_image(
    tmp_path: pathlib.Path,
) -> None:
    image = tmp_path / IMAGE_NAME
    image.write_bytes(b"qcow2")
    run = FakeRun((1, "", "network not found"), (0, "", ""), (0, "%s\n" % image, ""))
    assert vbi.build("debian-13", KEY, tmp_path, "renet", run) == image
    assert run.calls[1][:3] == ["sudo", "virsh", "net-define"]
    build_argv = run.calls[2]
    assert build_argv[:4] == ["renet", "ops", "image", "build"]
    assert build_argv[build_argv.index("--bake-key") + 1] == KEY
    assert build_argv[build_argv.index("--network") + 1] == vbi.BAKE_NETWORK


def test_build_skips_define_when_the_network_exists_and_fails_on_no_image(
    tmp_path: pathlib.Path,
) -> None:
    run = FakeRun((0, "Active: yes", ""), (0, "\n", ""))
    with pytest.raises(vbi.BakeImageError, match="no usable image path"):
        vbi.build("debian-13", KEY, tmp_path, "renet", run)
    assert run.calls[0][:3] == ["sudo", "virsh", "net-info"]
    assert len(run.calls) == 2


def test_publish_pushes_relative_and_reads_the_tag_back(tmp_path: pathlib.Path) -> None:
    image = tmp_path / IMAGE_NAME
    image.write_bytes(b"qcow2")
    run = FakeRun((0, "", ""), (0, "{}", ""))
    assert vbi.publish(image, KEY, "debian-13", run) == vbi.image_ref(KEY)
    push = run.calls[0]
    assert push[:3] == ["oras", "push", vbi.image_ref(KEY)]
    assert push[3] == "%s:%s" % (IMAGE_NAME, vbi.LAYER_MEDIA_TYPE)
    assert run.kwargs[0]["cwd"] == str(tmp_path)
    assert run.calls[1][:3] == ["oras", "manifest", "fetch"]


def test_publish_fails_when_the_tag_does_not_resolve_after_push(tmp_path: pathlib.Path) -> None:
    image = tmp_path / IMAGE_NAME
    image.write_bytes(b"qcow2")
    with pytest.raises(vbi.BakeImageError, match="does not resolve"):
        vbi.publish(image, KEY, "debian-13", FakeRun((0, "", ""), (1, "", "x: not found")))


# --- install-oras ------------------------------------------------------------


def _tarball(payload: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("oras")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def test_install_oras_refuses_a_checksum_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr(vbi.platform, "system", lambda: "Linux")
    monkeypatch.setattr(vbi.platform, "machine", lambda: "x86_64")
    blob = _tarball(b"#!/bin/sh\n")

    def download(_url: str, dest: pathlib.Path) -> None:
        dest.write_bytes(blob)

    with pytest.raises(vbi.BakeImageError, match="sha256 mismatch"):
        vbi.install_oras(tmp_path, download)
    assert not (tmp_path / "oras").exists()


def test_install_oras_installs_when_the_checksum_matches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    # Control for the refusal above: the same archive passes once the pin is its own digest.
    monkeypatch.setattr(vbi.platform, "system", lambda: "Linux")
    monkeypatch.setattr(vbi.platform, "machine", lambda: "x86_64")
    blob = _tarball(b"#!/bin/sh\n")
    monkeypatch.setattr(vbi, "ORAS_SHA256_LINUX_AMD64", hashlib.sha256(blob).hexdigest())

    def download(_url: str, dest: pathlib.Path) -> None:
        dest.write_bytes(blob)

    binary = vbi.install_oras(tmp_path, download)
    assert binary.read_bytes() == b"#!/bin/sh\n"
    assert binary.stat().st_mode & 0o111
