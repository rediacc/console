"""`rediacc_ci.infra.renet_embed_cache`: which staged embed-assets trees may be saved under the immutable `renet-embed-assets-<lock hash>` key.

The incident (PR #591, run 36724524175 job 109920400971): a failed earlier step skipped the restore, `cache-hit` came back empty, and `if: always() && cache-hit != 'true'` saved the checkout's `.gitkeep` skeleton under the real key. Every later job restored it as a HIT and restaged for ~11 min. The cases below pin each way a tree can look staged without being so.

The receipt check is also driven against build.sh's own `_embed_receipt_is_current` / `_embed_write_receipt` when the renet submodule and jq are present, so the Python mirror cannot drift from the contract it mirrors.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import subprocess
import time

import pytest

from rediacc_ci.infra import renet_embed_cache as rec

ROOT = pathlib.Path(__file__).resolve().parents[3]
BUILD_SH = ROOT / "private" / "renet" / "build.sh"

LOCK = {
    "components": {
        "criu": {
            "assetBase": "criu",
            "imageDir": "/build",
            "class": "base",
            "arches": {"amd64": {}, "arm64": {}},
        },
        "rsync": {
            "assetBase": "rsync",
            "imageDir": "/build",
            "class": "base",
            "arches": {"amd64": {}},
        },
    }
}
ASSETS = (
    "amd64/base/criu-linux-amd64.zst",
    "arm64/base/criu-linux-arm64.zst",
    "amd64/base/rsync-linux-amd64.zst",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _skeleton(tmp_path: pathlib.Path) -> pathlib.Path:
    """The checkout as it ships: lockfile plus `.gitkeep` placeholders, i.e. the 1.15 KiB entry that poisoned the key."""
    src = tmp_path / "renet"
    lock_bytes = json.dumps(LOCK).encode()
    src.mkdir(parents=True)
    (src / "embed-assets.lock.json").write_bytes(lock_bytes)
    (src / "Dockerfile").write_text("FROM ubuntu:26.10 AS rsync-builder-amd64\n", encoding="utf-8")
    assets = rec.assets_dir(src)
    for d in ("", "amd64", "amd64/base", "amd64/cluster", "arm64", "arm64/base", "arm64/cluster"):
        (assets / d).mkdir(parents=True, exist_ok=True)
        (assets / d / ".gitkeep").write_text("", encoding="utf-8")
    return src


def _staged(tmp_path: pathlib.Path) -> pathlib.Path:
    """A complete staging with a receipt written the way build.sh writes it."""
    src = _skeleton(tmp_path)
    assets = rec.assets_dir(src)
    entries = {}
    for rel in ASSETS:
        payload = ("payload:%s" % rel).encode()
        (assets / rel).write_bytes(payload)
        entries[rel] = {"sha256": _sha(payload)}
    receipt = {
        "lockfileSha256": _sha((src / "embed-assets.lock.json").read_bytes()),
        "dockerfileSha256": _sha((src / "Dockerfile").read_bytes()),
        "assets": entries,
    }
    (assets / ".staged.json").write_text(json.dumps(receipt), encoding="utf-8")
    return src


def test_a_complete_staging_is_current(tmp_path):
    assert rec.receipt_is_current(_staged(tmp_path))


def test_the_checkout_skeleton_is_not_current(tmp_path):
    assert not rec.receipt_is_current(_skeleton(tmp_path))


def test_a_lockfile_change_invalidates_the_receipt(tmp_path):
    src = _staged(tmp_path)
    (src / "embed-assets.lock.json").write_text(json.dumps({**LOCK, "bump": 1}), encoding="utf-8")
    assert not rec.receipt_is_current(src)


def test_a_dockerfile_change_invalidates_the_receipt(tmp_path):
    """A base image or configure flag changes the compiled bytes; the lockfile alone missed renet 5e0987c6."""
    src = _staged(tmp_path)
    assert rec.receipt_is_current(src)
    (src / "Dockerfile").write_text("FROM ubuntu:24.04 AS rsync-builder-amd64\n", encoding="utf-8")
    assert not rec.receipt_is_current(src)


def test_a_receipt_without_the_dockerfile_digest_is_not_current(tmp_path):
    src = _staged(tmp_path)
    path = rec.assets_dir(src) / ".staged.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    del receipt["dockerfileSha256"]
    path.write_text(json.dumps(receipt), encoding="utf-8")
    assert not rec.receipt_is_current(src)


def test_a_tampered_asset_invalidates_the_receipt(tmp_path):
    src = _staged(tmp_path)
    (rec.assets_dir(src) / ASSETS[0]).write_bytes(b"other bytes")
    assert not rec.receipt_is_current(src)


def test_a_missing_asset_invalidates_the_receipt(tmp_path):
    src = _staged(tmp_path)
    (rec.assets_dir(src) / ASSETS[1]).unlink()
    assert not rec.receipt_is_current(src)


def test_an_unlisted_extra_asset_invalidates_the_receipt(tmp_path):
    src = _staged(tmp_path)
    (rec.assets_dir(src) / "amd64" / "cluster" / "rclone-linux-amd64.zst").write_bytes(b"x")
    assert not rec.receipt_is_current(src)


def test_an_empty_receipt_never_satisfies(tmp_path):
    src = _skeleton(tmp_path)
    receipt = {
        "lockfileSha256": _sha((src / "embed-assets.lock.json").read_bytes()),
        "dockerfileSha256": _sha((src / "Dockerfile").read_bytes()),
        "assets": {},
    }
    (rec.assets_dir(src) / ".staged.json").write_text(json.dumps(receipt), encoding="utf-8")
    assert not rec.receipt_is_current(src)


def test_a_corrupt_receipt_is_not_current(tmp_path):
    src = _staged(tmp_path)
    (rec.assets_dir(src) / ".staged.json").write_text("{not json", encoding="utf-8")
    assert not rec.receipt_is_current(src)


@pytest.mark.parametrize(
    ("hit", "staged", "want"),
    [
        pytest.param("false", True, True, id="miss-then-staged-saves"),
        pytest.param("", True, True, id="empty-hit-output-then-staged-saves"),
        pytest.param("true", True, False, id="hit-never-saves"),
        pytest.param(None, True, False, id="unwired-step-never-saves"),
        pytest.param("false", False, False, id="miss-but-staging-incomplete-refused"),
        pytest.param("", False, False, id="skipped-restore-skeleton-refused"),
    ],
)
def test_cacheable(tmp_path, monkeypatch, hit, staged, want):
    src = _staged(tmp_path) if staged else _skeleton(tmp_path)
    if hit is None:
        monkeypatch.delenv(rec.HIT_ENV, raising=False)
    else:
        monkeypatch.setenv(rec.HIT_ENV, hit)
    assert rec.cacheable(src) is want


def test_write_verdict_appends_the_output(tmp_path, monkeypatch):
    out = tmp_path / "gh-output"
    out.write_text("earlier=1\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv(rec.HIT_ENV, "false")
    assert rec.write_verdict(_staged(tmp_path)) is True
    assert out.read_text(encoding="utf-8") == "earlier=1\nembed-cacheable=true\n"


def test_write_verdict_without_github_output_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setenv(rec.HIT_ENV, "false")
    assert rec.write_verdict(_staged(tmp_path)) is None


def test_a_stale_hit_warns_and_a_good_hit_does_not(tmp_path, monkeypatch):
    monkeypatch.setenv(rec.HIT_ENV, "true")
    warning = rec.stale_hit_warning(_skeleton(tmp_path / "bad"))
    assert warning is not None
    assert warning.startswith("::warning ")
    assert "gh cache delete" in warning
    assert rec.stale_hit_warning(_staged(tmp_path / "good")) is None
    monkeypatch.setenv(rec.HIT_ENV, "false")
    assert rec.stale_hit_warning(_skeleton(tmp_path / "miss")) is None


def test_cli_rejects_unknown_arguments():
    assert rec.main([]) == 2
    assert rec.main(["verdict", "extra"]) == 2


# ---------------------------------------------------------------------------
# Differential against build.sh's own receipt functions.
# ---------------------------------------------------------------------------

needs_build_sh = pytest.mark.skipif(
    not BUILD_SH.is_file() or shutil.which("jq") is None,
    reason="needs the private/renet submodule and jq",
)


def _bash(src: pathlib.Path, body: str) -> subprocess.CompletedProcess[str]:
    # build.sh ends with `[[ BASH_SOURCE == $0 ]] && "$@"`, which is false when sourced; under its own `set -e` that makes `source` itself return 1, so the status is absorbed and `set -e` dropped before the function runs.
    script = 'source "$1" || true; set +e; EMBED_LOCKFILE="$2/embed-assets.lock.json"; ' + body
    return subprocess.run(
        ["bash", "-c", script, "bash", str(BUILD_SH), str(src)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _shell_says_current(src: pathlib.Path) -> bool:
    assets = rec.assets_dir(src)
    proc = _bash(src, '_embed_receipt_is_current "%s" "%s/.staged.json"' % (assets, assets))
    return proc.returncode == 0


@needs_build_sh
def test_a_receipt_written_by_build_sh_is_accepted_by_both(tmp_path):
    src = _skeleton(tmp_path)
    assets = rec.assets_dir(src)
    for rel in ASSETS:
        (assets / rel).write_bytes(("payload:%s" % rel).encode())
    proc = _bash(src, '_embed_write_receipt "%s" "%s/.staged.json"' % (assets, assets))
    assert proc.returncode == 0, proc.stderr
    assert _shell_says_current(src)
    assert rec.receipt_is_current(src)


@needs_build_sh
def test_a_missing_dockerfile_fails_the_digest_instead_of_hashing_nothing(tmp_path):
    """`sha256sum | cut` exits 0 with an empty hash; an empty receipt field would then match an unlabelled image (review f21afb43.1)."""
    src = _staged(tmp_path)
    (src / "Dockerfile").unlink()
    assets = rec.assets_dir(src)
    digest = _bash(src, "_embed_dockerfile_sha")
    assert digest.returncode != 0
    assert digest.stdout == ""
    written = _bash(src, '_embed_write_receipt "%s" "%s/.staged.json"' % (assets, assets))
    assert written.returncode != 0
    assert not _shell_says_current(src)
    assert not rec.receipt_is_current(src)


@needs_build_sh
@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda _s: None, id="intact"),
        pytest.param(lambda s: (rec.assets_dir(s) / ".staged.json").unlink(), id="no-receipt"),
        pytest.param(lambda s: (rec.assets_dir(s) / ASSETS[0]).write_bytes(b"x"), id="tampered"),
        pytest.param(lambda s: (rec.assets_dir(s) / ASSETS[2]).unlink(), id="missing"),
        pytest.param(
            lambda s: (
                rec.assets_dir(s) / "arm64" / "cluster" / "extra-linux-arm64.zst"
            ).write_bytes(b"x"),
            id="extra",
        ),
        pytest.param(
            lambda s: (s / "embed-assets.lock.json").write_text("{}", encoding="utf-8"),
            id="lock-changed",
        ),
        pytest.param(
            lambda s: (s / "Dockerfile").write_text("FROM ubuntu:24.04\n", encoding="utf-8"),
            id="dockerfile-changed",
        ),
    ],
)
def test_python_and_build_sh_agree(tmp_path, mutate):
    src = _staged(tmp_path)
    mutate(src)
    assert rec.receipt_is_current(src) is _shell_says_current(src)


# ---------------------------------------------------------------------------
# embed_assets itself, driven against a fake `docker` on a fake assets tree.
# Origin: the 2026-11-14 restage printed `zstd: can't stat ... -- ignored` four
# times and still ended "Embedded assets ready" with a current receipt.
# ---------------------------------------------------------------------------

FAKE_DOCKER = """#!/bin/bash
case "$1" in
  image) cat "$FAKE_RECIPE_FILE" ;;
  create) echo fakecontainer ;;
  rm) ;;
  cp)
    dest="$3"
    case "$FAKE_CP:$(basename "$dest")" in
      *:"$FAKE_CP_FAIL") exit 1 ;;
      *:"$FAKE_CP_NOOP") exit 0 ;;
    esac
    printf 'fresh:%s' "$(basename "$dest")" > "$dest"
    ;;
esac
"""


def _embed(
    src: pathlib.Path,
    tmp_path: pathlib.Path,
    *,
    fail: str = "",
    noop: str = "",
    pre: str = "",
    timeout_s: int | None = None,
):
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    docker = bindir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8")
    docker.chmod(0o755)
    recipe = tmp_path / "recipe"
    recipe.write_text(_sha((src / "Dockerfile").read_bytes()) + "\n", encoding="utf-8")
    script = (
        'source "$1" || true; set +e; SCRIPT_DIR="$2"; EMBED_LOCKFILE="$2/embed-assets.lock.json"; '
        'PATH="$3:$PATH"; export FAKE_RECIPE_FILE="$4" FAKE_CP_FAIL="$5" FAKE_CP_NOOP="$6"; '
        + pre
        + " embed_assets --force"
    )
    cmd = [
        "bash",
        "-c",
        script,
        "bash",
        str(BUILD_SH),
        str(src),
        str(bindir),
        str(recipe),
        fail,
        noop,
    ]
    if timeout_s is not None:
        # `timeout` kills the whole staging; the result is None when it had to.
        proc = subprocess.run(
            ["timeout", "--kill-after=1", str(timeout_s), *cmd],
            capture_output=True,
            text=True,
            check=False,
        )
        return None if proc.returncode in (124, 137) else proc
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=120)


needs_embed_tools = pytest.mark.skipif(
    not BUILD_SH.is_file() or shutil.which("jq") is None or shutil.which("zstd") is None,
    reason="needs the private/renet submodule, jq and zstd",
)


@needs_embed_tools
def test_a_full_staging_compresses_every_asset_and_writes_a_current_receipt(tmp_path):
    src = _skeleton(tmp_path)
    proc = _embed(src, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assets = rec.assets_dir(src)
    for rel in ASSETS:
        assert (assets / rel).is_file(), rel
        assert not (assets / rel[: -len(".zst")]).exists()
    assert rec.receipt_is_current(src)


@needs_embed_tools
def test_a_failed_copy_does_not_leave_the_old_artifact_for_the_receipt(tmp_path):
    src = _skeleton(tmp_path)
    assets = rec.assets_dir(src)
    stale = assets / "arm64/base/criu-linux-arm64.zst"
    stale.write_bytes(b"OLD BYTES")
    proc = _embed(src, tmp_path, fail="criu-linux-arm64")
    assert proc.returncode != 0
    assert not stale.exists(), "the stale .zst survived a failed extraction"
    assert not (assets / ".staged.json").exists()


@needs_embed_tools
def test_a_raw_file_that_vanishes_before_compression_is_a_hard_error(tmp_path):
    """cp exits 0 but nothing is there: the shape a concurrent `zstd --rm` produces."""
    src = _skeleton(tmp_path)
    proc = _embed(src, tmp_path, noop="criu-linux-arm64")
    assert proc.returncode != 0
    assert "missing before compression" in proc.stderr
    assert not (rec.assets_dir(src) / ".staged.json").exists()


@needs_embed_tools
def test_control_a_bare_zstd_loop_under_if_not_context_passes_silently(tmp_path):
    """The old compress loop: zstd exits 1 on a missing input, but errexit is off inside `if ! embed_assets`, so the loop carried on and the function returned 0."""
    script = (
        'old() { set -e; zstd -19 -T0 -q --rm -f "$1"; echo reached-the-receipt; }; '
        'if ! old "$1"; then echo FAILED; else echo PASSED; fi'
    )
    proc = subprocess.run(
        ["bash", "-c", script, "bash", str(tmp_path / "absent-linux-amd64")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "PASSED" in proc.stdout
    assert "reached-the-receipt" in proc.stdout
    assert "ignored" in proc.stderr


@needs_embed_tools
@pytest.mark.skipif(shutil.which("flock") is None, reason="needs flock")
def test_a_second_staging_waits_while_one_holds_the_tree(tmp_path):
    src = _skeleton(tmp_path)
    assets = rec.assets_dir(src)
    holder = subprocess.Popen(["flock", str(assets), "sleep", "30"])
    try:
        for _ in range(50):
            if subprocess.run(["flock", "-n", str(assets), "true"], check=False).returncode != 0:
                break
            time.sleep(0.1)
        assert _embed(src, tmp_path, timeout_s=2) is None, (
            "embed_assets ran while another staging held the tree"
        )
    finally:
        holder.kill()
        holder.wait()
    done = _embed(src, tmp_path)
    assert done is not None
    assert done.returncode == 0
