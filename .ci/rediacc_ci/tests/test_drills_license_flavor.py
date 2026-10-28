"""The license drill reads and pins the ENFORCING renet by its own path (PLAN-per-flavor-renet-binary-paths P5).

`bin/enforce/` holds the enforcing build and `bin/renet` the nolicense one, so a plain `./rdc.sh` elsewhere cannot flip what the drill deploys. `verify_renet_flavor` therefore judges the three `bin/enforce/` binaries and never reads `bin/renet`, and `setup_config` hands `config init` the enforcing path through `--renet-path`.
"""

from __future__ import annotations

import pathlib
import types

import pytest

from rediacc_ci.drills import license as lic

ENFORCING = "build  -tags=\nbuild\t-ldflags=-X keys.ProductionPublicKey=abc\n"
KEYLESS = "build\t-ldflags=-s -w\n"
NOLICENSE = "build\t-tags=nolicense\nbuild\t-ldflags=-X keys.ProductionPublicKey=abc\n"
ROOT = pathlib.Path("/work/console")
ENFORCE_DIR = ROOT / "private" / "renet" / "bin" / "enforce"


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
    fake.enforce_binary = types.MethodType(lic.License.enforce_binary, fake)
    return fake


def _verify(monkeypatch, infos):
    """Run verify_renet_flavor with the go reader answering `infos(path)`; returns the paths read."""
    read: list[str] = []

    def reader(path: str) -> str:
        read.append(path)
        return infos(path)

    monkeypatch.setattr(lic, "_go_buildinfo", reader)
    lic.License.verify_renet_flavor(_fake())
    return read


def test_the_three_enforce_binaries_are_read_and_bin_renet_never(monkeypatch) -> None:
    read = _verify(monkeypatch, lambda _p: ENFORCING)
    assert read == [
        str(ENFORCE_DIR / "renet"),
        str(ENFORCE_DIR / "renet-linux-amd64"),
        str(ENFORCE_DIR / "renet-linux-arm64"),
    ]
    assert str(ROOT / "private" / "renet" / "bin" / "renet") not in read


def test_a_nolicense_build_at_the_enforcing_path_is_refused(monkeypatch) -> None:
    with pytest.raises(SystemExit) as stop:
        _verify(monkeypatch, lambda _p: NOLICENSE)
    assert stop.value.code == 1


def test_a_keyless_enforcing_build_is_refused(monkeypatch) -> None:
    with pytest.raises(SystemExit) as stop:
        _verify(monkeypatch, lambda _p: KEYLESS)
    assert stop.value.code == 1


def test_one_wrong_linux_binary_is_enough_to_refuse(monkeypatch) -> None:
    def infos(path: str) -> str:
        return NOLICENSE if path.endswith("renet-linux-arm64") else ENFORCING

    with pytest.raises(SystemExit) as stop:
        _verify(monkeypatch, infos)
    assert stop.value.code == 1


def test_an_unreadable_binary_is_refused(monkeypatch) -> None:
    with pytest.raises(SystemExit) as stop:
        _verify(monkeypatch, lambda _p: "")
    assert stop.value.code == 1


def test_config_init_pins_the_enforcing_binary(monkeypatch) -> None:
    monkeypatch.setattr(lic, "_go_buildinfo", lambda _p: ENFORCING)
    calls: list[tuple[str, ...]] = []
    fake = _fake()
    fake.cli = lambda *args: calls.append(args)
    fake.verify_renet_flavor = lambda: None
    fake.d.setup_run = lambda *_a, **_k: None
    fake.ssh_argv = lambda *_a: []
    fake.api_token = "t"
    lic.License.setup_config(fake)
    init = next(c for c in calls if c[:2] == ("config", "init"))
    assert init[init.index("--renet-path") + 1] == str(ENFORCE_DIR / "renet")
