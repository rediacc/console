"""leg_p never loses the original image: the swap runs inside the try that restores it."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from rediacc_ci.drills import backup_renet as renet

if TYPE_CHECKING:
    import pathlib


def test_a_swap_that_fails_still_puts_the_original_back() -> None:
    commands: list[str] = []

    def run_vm(cmd: str, *_args: object, **_kw: object) -> str:
        commands.append(cmd)
        if "luksFormat" in cmd:
            raise RuntimeError("swap failed after the mv")
        return ""

    backup = SimpleNamespace(d=SimpleNamespace(step=lambda *_a: None))
    legs = renet.RenetLegs(backup, cast("Any", SimpleNamespace(run_vm=run_vm, datastore="/ds")))
    legs.src = "guid"
    with pytest.raises(RuntimeError, match="swap failed"):
        legs.leg_p()
    assert commands[-1] == renet.unswap_image_command("/ds", "guid")


def test_unswap_without_an_aside_leaves_the_image_alone(tmp_path: pathlib.Path) -> None:
    image = tmp_path / "repositories" / "guid"
    image.parent.mkdir()
    image.write_bytes(b"original")
    cmd = renet.unswap_image_command(str(tmp_path), "guid").replace("sudo -n ", "")
    subprocess.run(["/bin/sh", "-c", cmd], check=True)
    assert image.read_bytes() == b"original"
