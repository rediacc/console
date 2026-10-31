"""`build.sh dev` has one flavor: licence-enforcing, key baked, written to `bin/`.

The nolicense build and its `bin/enforce/` split are gone (operator 2026-10-30, agent/plans/PLAN-production-key-only.md N2). The real `build.sh` is copied beside a stub `scripts/pull-with-retry.sh` and sourced; a fake `go` on PATH writes its argv into the `-o` file, so the only "build" is the fake.
"""

from __future__ import annotations

import os
import pathlib
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
BUILD_SH = REPO / "private" / "renet" / "build.sh"
# An arbitrary value, never a real key.
KEY = "dGVzdC1vbmx5LW5vdC1hLWtleQ=="

FAKE_GO = """#!/bin/bash
out=""
argv="$*"
while [[ $# -gt 0 ]]; do
    if [[ "$1" == "-o" ]]; then out="$2"; fi
    shift
done
[[ -n "$out" ]] || exit 2
printf '%s\\n' "$FAKE_GO_LABEL" "$argv" >"$out"
"""

NAMES = ("renet", "renet-linux-amd64", "renet-linux-arm64")


def _tree(root: pathlib.Path, script: str) -> pathlib.Path:
    renet = root / "renet"
    (renet / "scripts").mkdir(parents=True)
    (renet / "scripts" / "pull-with-retry.sh").write_text("", encoding="utf-8")
    (renet / "build.sh").write_text(script, encoding="utf-8")
    fake = root / "fakebin"
    fake.mkdir()
    (fake / "go").write_text(FAKE_GO, encoding="utf-8")
    (fake / "go").chmod(0o755)
    return renet


def _dev(renet: pathlib.Path, root: pathlib.Path, *args: str, **extra: str):
    env = {k: v for k, v in os.environ.items() if k not in ("RDC_RENET_LICENSE", "RENET_KEYLESS")}
    env["PATH"] = f"{root / 'fakebin'}{os.pathsep}{env['PATH']}"
    env["FAKE_GO_LABEL"] = "new"
    env["ACCOUNT_ED25519_PUBLIC_KEY"] = KEY
    env.update(extra)
    script = (
        'source "$1" || true; '
        "_embed_assets_or_die() { :; }; embed_proxy() { :; }; ebpf_generate() { :; }; "
        'shift; dev "$@"'
    )
    return subprocess.run(
        ["bash", "-c", script, "dev-flavor", str(renet / "build.sh"), *args],
        cwd=renet,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _seed(directory: pathlib.Path) -> dict[str, bytes]:
    directory.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        (directory / name).write_bytes(b"old " + name.encode())
    return {name: (directory / name).read_bytes() for name in NAMES}


def _assert_fresh_and_keyed(directory: pathlib.Path) -> None:
    for name in NAMES:
        body = (directory / name).read_text(encoding="utf-8")
        assert body.startswith("new\n"), f"{directory / name} was not rewritten"
        assert "-tags" not in body, body
        assert f"keys.ProductionPublicKey={KEY}" in body, body
    assert not [p for p in directory.iterdir() if ".tmp." in p.name]


@pytest.fixture
def tree(tmp_path: pathlib.Path) -> pathlib.Path:
    return _tree(tmp_path, BUILD_SH.read_text(encoding="utf-8"))


def test_dev_writes_bin_keyed_with_no_build_tag(tmp_path: pathlib.Path, tree: pathlib.Path) -> None:
    _seed(tree / "bin")
    res = _dev(tree, tmp_path)
    assert res.returncode == 0, res.stderr
    _assert_fresh_and_keyed(tree / "bin")
    assert not (tree / "bin" / "enforce").exists()


def test_rdc_renet_license_changes_nothing(tmp_path: pathlib.Path, tree: pathlib.Path) -> None:
    res = _dev(tree, tmp_path, RDC_RENET_LICENSE="1")
    assert res.returncode == 0, res.stderr
    _assert_fresh_and_keyed(tree / "bin")
    assert not (tree / "bin" / "enforce").exists()


@pytest.mark.parametrize("flag", ["--nolicense", "--license"])
def test_retired_flavor_flags_are_refused(
    tmp_path: pathlib.Path, tree: pathlib.Path, flag: str
) -> None:
    res = _dev(tree, tmp_path, flag)
    assert res.returncode == 2
    assert "takes no arguments" in res.stderr
    assert not (tree / "bin").exists(), "a refused build wrote binaries"


def test_build_sh_names_no_nolicense_flavor() -> None:
    text = BUILD_SH.read_text(encoding="utf-8")
    for word in ("nolicense", "RDC_RENET_LICENSE", "_dev_out_dir", "bin/enforce"):
        assert word not in text, word


def test_control_a_planted_tag_is_caught(tmp_path: pathlib.Path) -> None:
    """Re-plant the retired tag in dev's link line; the freshness assertion must refuse it."""
    source = BUILD_SH.read_text(encoding="utf-8")
    anchor = '-ldflags="-X main.Version=$dev_version $key_ldflags" \\\n'
    assert source.count(anchor) == 1
    planted = source.replace(anchor, anchor + "        -tags nolicense \\\n")
    renet = _tree(tmp_path, planted)
    res = _dev(renet, tmp_path)
    assert res.returncode == 0, res.stderr
    with pytest.raises(AssertionError):
        _assert_fresh_and_keyed(renet / "bin")
