"""`build.sh dev` writes each license flavor into its own directory.

A nolicense build owns `bin/`, an enforcing one owns `bin/enforce/`, so one never overwrites the other's binaries. The real `build.sh` is copied beside a stub `scripts/pull-with-retry.sh` and sourced; a fake `go` on PATH writes its argv into the `-o` file, so the only "build" is the fake.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
BUILD_SH = REPO / "private" / "renet" / "build.sh"

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


def _dev(renet: pathlib.Path, root: pathlib.Path, *args: str, license_env: bool = False):
    env = {k: v for k, v in os.environ.items() if k != "RDC_RENET_LICENSE"}
    env["PATH"] = f"{root / 'fakebin'}{os.pathsep}{env['PATH']}"
    env["FAKE_GO_LABEL"] = "new"
    if license_env:
        env["RDC_RENET_LICENSE"] = "1"
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


def _read(directory: pathlib.Path) -> dict[str, bytes]:
    return {name: (directory / name).read_bytes() for name in NAMES}


def _assert_fresh(directory: pathlib.Path, nolicense: bool) -> None:
    for name in NAMES:
        body = (directory / name).read_text(encoding="utf-8")
        assert body.startswith("new\n"), f"{directory / name} was not rewritten"
        assert ("-tags nolicense" in body) is nolicense, body
    assert not [p for p in directory.iterdir() if ".tmp." in p.name]


@pytest.fixture
def tree(tmp_path: pathlib.Path) -> pathlib.Path:
    return _tree(tmp_path, BUILD_SH.read_text(encoding="utf-8"))


def test_plain_dev_writes_bin_and_leaves_enforce_alone(
    tmp_path: pathlib.Path, tree: pathlib.Path
) -> None:
    enforce = _seed(tree / "bin" / "enforce")
    res = _dev(tree, tmp_path)
    assert res.returncode == 0, res.stderr
    _assert_fresh(tree / "bin", nolicense=True)
    assert _read(tree / "bin" / "enforce") == enforce


def _license_scenario(renet: pathlib.Path, root: pathlib.Path, how: str) -> None:
    plain = _seed(renet / "bin")
    res = _dev(renet, root, *(["--license"] if how == "flag" else []), license_env=how == "env")
    assert res.returncode == 0, res.stderr
    _assert_fresh(renet / "bin" / "enforce", nolicense=False)
    assert _read(renet / "bin") == plain, "plain bin/ untouched"


@pytest.mark.parametrize("how", ["env", "flag"])
def test_license_dev_writes_only_enforce(
    tmp_path: pathlib.Path, tree: pathlib.Path, how: str
) -> None:
    _license_scenario(tree, tmp_path, how)


def test_env_license_with_nolicense_flag_writes_bin(
    tmp_path: pathlib.Path, tree: pathlib.Path
) -> None:
    enforce = _seed(tree / "bin" / "enforce")
    res = _dev(tree, tmp_path, "--nolicense", license_env=True)
    assert res.returncode == 0, res.stderr
    _assert_fresh(tree / "bin", nolicense=True)
    assert _read(tree / "bin" / "enforce") == enforce


def test_control_collapsed_out_dir_is_caught(tmp_path: pathlib.Path) -> None:
    source = BUILD_SH.read_text(encoding="utf-8")
    planted, count = re.subn(
        r"(_dev_out_dir\(\) \{\n).*?(\n\})",
        r'\1    echo "$SCRIPT_DIR/bin"\2',
        source,
        count=1,
        flags=re.DOTALL,
    )
    assert count == 1
    renet = _tree(tmp_path, planted)
    # With one shared directory, an enforcing build lands in bin/ and bin/enforce/ stays empty.
    with pytest.raises((AssertionError, FileNotFoundError)):
        _license_scenario(renet, tmp_path, "flag")
