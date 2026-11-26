"""A profile with `token_file` fetches with that file's token and never with the default one.

The rotation tool's admin credentials live in their own Bitwarden project, read through `bws-rotation-token`. `hydrate` must therefore (1) read the named file beside the default token file, (2) ignore `BWS_ACCESS_TOKEN` for that profile, and (3) refuse with a message naming the missing file. `bws` is a fake on `BWS_BIN` that answers by the token it was handed, so the test sees which token reached the store without any real credential.
"""

import json
import os
import stat

import pytest

from rediacc_ci.core import bws_env

DEFAULT_TOKEN = "fixture-default-token-not-a-credential"
ROTATION_TOKEN = "fixture-rotation-token-not-a-credential"

FAKE_BWS = r"""#!/usr/bin/env python3
import json, os, sys
tok = os.environ.get("BWS_ACCESS_TOKEN", "")
rows = {
    "fixture-default-token-not-a-credential": [{"key": "SHARED_ONE", "value": "shared-v"}],
    "fixture-rotation-token-not-a-credential": [{"key": "ADMIN_ONE", "value": "admin-v"}],
}.get(tok, [])
print(json.dumps(rows))
"""

SPEC = {
    "consumers": {
        "adm": {"why": "fixture", "required": ["ADMIN_ONE"], "token_file": "bws-rotation-token"},
        "shared": {"why": "fixture", "required": ["SHARED_ONE"]},
    }
}


def _tree(tmp_path, *, rotation_mode: int | None = 0o600):
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    (tmp_path / bws_env.SUPPLY_REL).write_text(json.dumps(SPEC), encoding="utf-8")
    xdg = tmp_path / "xdg"
    (xdg / "rediacc").mkdir(parents=True)
    (xdg / "rediacc").chmod(0o700)
    if rotation_mode is not None:
        f = xdg / "rediacc" / "bws-rotation-token"
        f.write_text(ROTATION_TOKEN + "\n", encoding="utf-8")
        f.chmod(rotation_mode)
    fake = tmp_path / "bws"
    fake.write_text(FAKE_BWS, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return {
        "PATH": os.environ["PATH"],
        "BWS_ENV_ROOT": str(tmp_path),
        "XDG_CONFIG_HOME": str(xdg),
        "BWS_BIN": str(fake),
        "BWS_ACCESS_TOKEN": DEFAULT_TOKEN,
    }


def _hydrate(names, env):
    with open(os.devnull, "w", encoding="utf-8") as sink:
        return bws_env.hydrate(names, env, stderr=sink)


def test_token_file_profile_fetches_with_its_own_token(tmp_path) -> None:
    out, done = _hydrate(["adm"], _tree(tmp_path))
    assert out["ADMIN_ONE"] == "admin-v"
    assert done == ["adm"]


def test_default_profile_still_uses_the_default_token(tmp_path) -> None:
    out, _ = _hydrate(["shared"], _tree(tmp_path))
    assert out["SHARED_ONE"] == "shared-v"


def test_two_profiles_each_use_their_own_token(tmp_path) -> None:
    out, _ = _hydrate(["adm", "shared"], _tree(tmp_path))
    assert (out["ADMIN_ONE"], out["SHARED_ONE"]) == ("admin-v", "shared-v")


def test_missing_token_file_is_refused_naming_the_file(tmp_path) -> None:
    env = _tree(tmp_path, rotation_mode=None)
    with pytest.raises(bws_env.RefusalError) as exc:
        _hydrate(["adm"], env)
    text = "\n".join(exc.value.lines)
    assert "bws-rotation-token" in text
    assert "bws-rotation-token is missing or empty" in text


def test_wide_mode_token_file_is_refused(tmp_path) -> None:
    env = _tree(tmp_path, rotation_mode=0o644)
    with pytest.raises(bws_env.RefusalError) as exc:
        _hydrate(["adm"], env)
    assert "bws-rotation-token" in "\n".join(exc.value.lines)
