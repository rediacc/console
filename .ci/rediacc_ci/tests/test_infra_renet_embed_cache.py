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
    receipt = {"lockfileSha256": _sha((src / "embed-assets.lock.json").read_bytes()), "assets": {}}
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
    ],
)
def test_python_and_build_sh_agree(tmp_path, mutate):
    src = _staged(tmp_path)
    mutate(src)
    assert rec.receipt_is_current(src) is _shell_says_current(src)
