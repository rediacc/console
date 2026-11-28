"""`private/renet/build.sh model-key-ldflags`: where renet's detector model public key comes from.

The key is `WK_MODEL_ED25519_PUBLIC_KEY` in `.ci/config/well-known.env`; `MODEL_ED25519_PUBLIC_KEY` in the environment overrides it and, set to the empty string, selects a keyless build (the committed detect.wasm rebuild, `rediacc_ci.quality.detect_wasm.rebuild`). The registry value must be a raw 32-byte Ed25519 public key in base64, the form `pkg/models/keys` parses.
"""

from __future__ import annotations

import base64
import os
import pathlib
import subprocess

from rediacc_ci import well_known

REPO = pathlib.Path(__file__).resolve().parents[3]
BUILD_SH = REPO / "private" / "renet" / "build.sh"
SYMBOL = " -X github.com/rediacc/renet/pkg/models/keys.ModelPublicKey="


def _ldflags(**env: str) -> str:
    base = {k: v for k, v in os.environ.items() if k != "MODEL_ED25519_PUBLIC_KEY"}
    base.update(env)
    proc = subprocess.run(
        ["bash", str(BUILD_SH), "model-key-ldflags"],
        cwd=BUILD_SH.parent,
        env=base,
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_registry_value_is_a_raw_ed25519_public_key() -> None:
    assert len(base64.b64decode(well_known.MODEL_ED25519_PUBLIC_KEY, validate=True)) == 32


def test_unset_env_stamps_the_registry_key() -> None:
    assert _ldflags() == SYMBOL + well_known.MODEL_ED25519_PUBLIC_KEY


def test_env_overrides_the_registry_key() -> None:
    assert _ldflags(MODEL_ED25519_PUBLIC_KEY="b3ZlcnJpZGU=") == SYMBOL + "b3ZlcnJpZGU="


def test_empty_env_is_keyless() -> None:
    assert _ldflags(MODEL_ED25519_PUBLIC_KEY="") == ""
