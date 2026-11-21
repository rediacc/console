"""`rediacc_ci.infra.vm_bake_image`: publish and fetch of the pre-baked E2E VM images.

Every case drives the module through a fake `run` (or a fake download), so nothing touches a registry, libvirt or the network. The verdicts that carry the design, each with its control:

  * fetch: a registry "not found" and any other pull failure are both a MISS that exports nothing, while a pull that lands one image is a HIT that exports REDIACC_OPS_DISKS_PATH, BAKED_IMAGE_KEY and RENET_SETUP_OFFLINE (the stock fallback depends on the first, the baked leg on the second);
  * probe: "not found" is a miss, but an auth failure raises, so a broken login cannot pass for a missing image;
  * install-oras: a download whose sha256 differs from the pin is refused;
  * tag namespaces: a main run reads and writes `<key>` only and never resolves a `pr-<n>-<key>` tag, a pull_request run publishes only under its own `pr-<n>-` prefix, and a run on neither publishes nowhere.
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


PR_ENV = {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_REF": "refs/pull/605/merge"}
MAIN_ENV = {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main"}


@pytest.fixture(autouse=True)
def _main_run_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every CLI case runs as a main push unless it says otherwise: CI itself runs these tests on pull_request."""
    for name, value in MAIN_ENV.items():
        monkeypatch.setenv(name, value)


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


# --- plan --------------------------------------------------------------------


def _key_for(distro: str) -> str:
    return "vm-bake-v1-%s-2026-11-08e81f4c97c76189" % distro


def test_plan_lists_only_the_distros_without_a_tag() -> None:
    present = {vbi.image_ref(_key_for("debian-13"))}
    missing = vbi.missing_distros(
        ["ubuntu-24.04", "debian-13", "fedora-43"], _key_for, lambda ref: ref in present
    )
    assert missing == ["ubuntu-24.04", "fedora-43"]


def test_plan_probe_error_propagates_rather_than_reading_as_a_miss() -> None:
    def broken(_ref: str) -> bool:
        raise vbi.BakeImageError("oras manifest fetch failed (rc=1): unauthorized")

    with pytest.raises(vbi.BakeImageError, match="unauthorized"):
        vbi.missing_distros(["debian-13"], _key_for, broken)


@pytest.mark.parametrize(
    ("present", "missing", "bake"),
    [
        ({"debian-13", "fedora-43"}, "[]", "false"),
        ({"debian-13"}, '["fedora-43"]', "true"),
    ],
)
def test_cli_plan_emits_the_bake_matrix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    present: set[str],
    missing: str,
    bake: str,
) -> None:
    out = tmp_path / "out"
    out.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(vbi, "_key", _key_for)
    refs = {vbi.image_ref(_key_for(d)) for d in present}
    monkeypatch.setattr(vbi, "tag_exists", lambda ref: ref in refs)
    assert vbi.main(["plan", "--distro", "debian-13", "--distro", "fedora-43"]) == 0
    assert out.read_text() == "missing=%s\nbake=%s\n" % (missing, bake)


def test_cli_plan_fails_on_a_probe_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(_ref: str) -> bool:
        raise vbi.BakeImageError("unauthorized")

    monkeypatch.setattr(vbi, "_key", _key_for)
    monkeypatch.setattr(vbi, "tag_exists", broken)
    assert vbi.main(["plan", "--distro", "debian-13"]) == 1
    assert "unauthorized" in capsys.readouterr().err


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


# --- tag namespaces: a main run never reads a tag a pull request can write ----

PR_REF = (IMAGE_REGISTRY + "/ci-vm-bake:pr-605-") + KEY
MAIN_IMAGE_REF = (IMAGE_REGISTRY + "/ci-vm-bake:") + KEY


@pytest.mark.parametrize(
    "env",
    [
        MAIN_ENV,
        {"GITHUB_EVENT_NAME": "schedule", "GITHUB_REF": "refs/heads/main"},
        {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main"},
    ],
)
def test_main_scope_reads_and_writes_only_mains_namespace(env: dict[str, str]) -> None:
    scope = vbi.scope_from_env(env)
    assert scope.read_refs(KEY) == [MAIN_IMAGE_REF]
    assert scope.write_ref(KEY) == MAIN_IMAGE_REF


def test_pr_scope_writes_only_its_own_namespace_and_reads_it_before_mains() -> None:
    scope = vbi.scope_from_env(PR_ENV)
    assert scope.write_ref(KEY) == PR_REF
    assert scope.read_refs(KEY) == [PR_REF, MAIN_IMAGE_REF]
    other = vbi.scope_from_env({**PR_ENV, "GITHUB_REF": "refs/pull/606/merge"})
    assert PR_REF not in other.read_refs(KEY)


@pytest.mark.parametrize(
    "env",
    [
        {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/1104-1"},
        {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/1104-1"},
        {},
    ],
)
def test_a_run_off_main_and_off_a_pr_reads_main_and_publishes_nowhere(
    env: dict[str, str],
) -> None:
    scope = vbi.scope_from_env(env)
    assert scope.read_refs(KEY) == [MAIN_IMAGE_REF]
    with pytest.raises(vbi.BakeImageError, match="may not publish"):
        scope.write_ref(KEY)


def test_a_pull_request_without_its_merge_ref_is_refused() -> None:
    with pytest.raises(vbi.BakeImageError, match="refs/pull/<number>/merge"):
        vbi.scope_from_env({"GITHUB_EVENT_NAME": "pull_request", "GITHUB_REF": "refs/heads/main"})


def test_image_ref_refuses_a_namespace_that_is_not_a_pr_prefix() -> None:
    for prefix in ("pr--", "pr-0-", "main-", "pr-1"):
        with pytest.raises(vbi.BakeImageError, match="not a tag namespace"):
            vbi.image_ref(KEY, prefix)


def test_main_fetch_never_resolves_a_pr_namespace_tag(tmp_path: pathlib.Path) -> None:
    """The registry holds only the PR's tag: a main run pulls main's ref alone and misses."""

    def registry(argv: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        pulled.append(argv[2])
        if argv[2] == PR_REF:
            _pulls_one_image(argv)
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.CompletedProcess(argv, 1, "", "x: not found")

    pulled: list[str] = []
    image, reason = vbi.fetch(KEY, tmp_path / "d", registry, scope=vbi.scope_from_env(MAIN_ENV))
    assert image is None
    assert pulled == [MAIN_IMAGE_REF]
    assert reason == "no baked image published for %s" % KEY
    # Control: the same registry serves a PR run from its own namespace.
    pulled.clear()
    image, _ = vbi.fetch(KEY, tmp_path / "d", registry, scope=vbi.scope_from_env(PR_ENV))
    assert image is not None
    assert pulled == [PR_REF]


def test_pr_fetch_falls_back_to_mains_image_on_not_found(tmp_path: pathlib.Path) -> None:
    run = FakeRun((1, "", "x: not found"), (0, "", "", _pulls_one_image))
    image, reason = vbi.fetch(KEY, tmp_path / "d", run, scope=vbi.scope_from_env(PR_ENV))
    assert (image, reason) == (tmp_path / "d" / IMAGE_NAME, "")
    assert [c[2] for c in run.calls] == [PR_REF, MAIN_IMAGE_REF]


def test_pr_fetch_does_not_fall_back_past_a_registry_error(tmp_path: pathlib.Path) -> None:
    run = FakeRun((1, "", "connection reset by peer"))
    image, reason = vbi.fetch(KEY, tmp_path / "d", run, scope=vbi.scope_from_env(PR_ENV))
    assert image is None
    assert "connection reset" in reason
    assert len(run.calls) == 1


def test_cli_publish_in_a_pr_run_pushes_only_to_the_pr_namespace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    for name, value in PR_ENV.items():
        monkeypatch.setenv(name, value)
    image = tmp_path / IMAGE_NAME
    image.write_bytes(b"qcow2")
    run = FakeRun((0, "", ""), (0, "{}", ""))
    monkeypatch.setattr(vbi.publish, "__defaults__", (run,))
    monkeypatch.setattr(vbi.tag_exists, "__defaults__", (run,))
    argv = ["publish", "--distro", "debian-13", "--key", KEY, "--image", str(image)]
    assert vbi.main(argv) == 0
    touched = [arg for call in run.calls for arg in call if arg.startswith(IMAGE_REGISTRY)]
    assert [c[:2] for c in run.calls] == [["oras", "push"], ["oras", "manifest"]]
    assert touched == [PR_REF, PR_REF]


def test_cli_plan_in_a_pr_run_counts_mains_tag_as_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    for name, value in PR_ENV.items():
        monkeypatch.setenv(name, value)
    out = tmp_path / "out"
    out.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(vbi, "_key", _key_for)
    present = {
        vbi.image_ref(_key_for("debian-13")),
        vbi.image_ref(_key_for("fedora-43"), "pr-605-"),
    }
    monkeypatch.setattr(vbi, "tag_exists", lambda ref: ref in present)
    argv = ["plan", "--distro", "debian-13", "--distro", "fedora-43", "--distro", "oracle-10"]
    assert vbi.main(argv) == 0
    assert out.read_text() == 'missing=["oracle-10"]\nbake=true\n'


def test_cli_plan_off_main_and_off_a_pr_fails_before_any_probe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GITHUB_REF", "refs/heads/1104-1")
    monkeypatch.setattr(vbi, "_key", _key_for)
    probed: list[str] = []

    def probe(ref: str) -> bool:
        probed.append(ref)
        return False

    monkeypatch.setattr(vbi, "tag_exists", probe)
    assert vbi.main(["plan", "--distro", "debian-13"]) == 1
    assert "may not publish" in capsys.readouterr().err
    assert probed == []


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
