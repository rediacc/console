"""The license drill reads and pins the one licensed renet by its own path (agent/plans/PLAN-production-key-only.md Design 6).

There is one build in `bin/`, always licensed. `verify_renet_key` judges the three `bin/` binaries (the host one and both Linux ones `machine setup` may upload) and refuses one that bakes no account key, and `setup_config` hands `config init` the host path through `--renet-path`.
"""

from __future__ import annotations

import pathlib
import types

import pytest

from rediacc_ci.drills import license as lic
from rediacc_ci.well_known import RENET_REPO

KEYED = "build\t-ldflags=-X github.com/%s/pkg/license/keys.ProductionPublicKey=abc\n" % RENET_REPO
KEYLESS = "build\t-ldflags=-s -w\n"
EMPTY_KEY = "build\t-ldflags=-X github.com/%s/pkg/license/keys.ProductionPublicKey=\n" % RENET_REPO
ROOT = pathlib.Path("/work/console")
BIN_DIR = ROOT / "private" / "renet" / "bin"


def _fake():
    fake = types.SimpleNamespace(
        d=types.SimpleNamespace(root=ROOT, step=lambda *_a: None, note=lambda *_a: None),
        server_url="http://127.0.0.1:1",
        o=types.SimpleNamespace(
            enabled=lambda _leg: False,
            ssh_key="k",
            vm_ip="1.2.3.4",
            ssh_user="u",
            vm_renet="renet",
            vm2_ip="1.2.3.5",
        ),
        rdc="rdc",
    )
    fake.renet_binary = types.MethodType(lic.License.renet_binary, fake)
    return fake


def _verify(monkeypatch, infos):
    """Run verify_renet_key with the go reader answering `infos(path)`; returns the paths read."""
    read: list[str] = []

    def reader(path: str) -> str:
        read.append(path)
        return infos(path)

    monkeypatch.setattr(lic, "_go_buildinfo", reader)
    lic.License.verify_renet_key(_fake())
    return read


def test_the_three_bin_binaries_are_read(monkeypatch) -> None:
    read = _verify(monkeypatch, lambda _p: KEYED)
    assert read == [
        str(BIN_DIR / "renet"),
        str(BIN_DIR / "renet-linux-amd64"),
        str(BIN_DIR / "renet-linux-arm64"),
    ]


@pytest.mark.parametrize(
    "info", [KEYLESS, EMPTY_KEY, ""], ids=["no-key", "empty-key", "unreadable"]
)
def test_a_binary_without_a_baked_key_is_refused(monkeypatch, info) -> None:
    with pytest.raises(SystemExit) as stop:
        _verify(monkeypatch, lambda _p: info)
    assert stop.value.code == 1


def test_one_wrong_linux_binary_is_enough_to_refuse(monkeypatch) -> None:
    def infos(path: str) -> str:
        return KEYLESS if path.endswith("renet-linux-arm64") else KEYED

    with pytest.raises(SystemExit) as stop:
        _verify(monkeypatch, infos)
    assert stop.value.code == 1


def test_config_init_pins_the_bin_binary(monkeypatch) -> None:
    monkeypatch.setattr(lic, "_go_buildinfo", lambda _p: KEYED)
    calls: list[tuple[str, ...]] = []
    fake = _fake()
    fake.cli = lambda *args: calls.append(args)
    fake.verify_renet_key = lambda: None
    fake.d.setup_run = lambda *_a, **_k: None
    fake.ssh_argv = lambda *_a: []
    fake.api_token = "t"
    lic.License.setup_config(fake)
    init = next(c for c in calls if c[:2] == ("config", "init"))
    assert init[init.index("--renet-path") + 1] == str(BIN_DIR / "renet")
