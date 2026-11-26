"""A profile with `token_file` fetches with that file's token and never with the default one.

The rotation tool's admin credentials live in their own Bitwarden project, read through `bws-rotation-token`. `hydrate` must therefore (1) read the named file beside the default token file, (2) ignore `BWS_ACCESS_TOKEN` for that profile, and (3) refuse with a message naming the missing file. `bws` is a fake on `BWS_BIN` that answers by the token it was handed, so the test sees which token reached the store without any real credential.
"""

import json
import os
import stat

import pytest

from rediacc_ci.core import bws_env
from rediacc_ci.quality import secret_supply

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


def _tree(tmp_path, *, rotation_mode: int | None = 0o600, spec=None):
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    (tmp_path / bws_env.SUPPLY_REL).write_text(json.dumps(spec or SPEC), encoding="utf-8")
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


def test_an_earlier_default_profile_does_not_take_a_name_from_a_token_file_profile(
    tmp_path,
) -> None:
    """Review 8989f955.1: `claimed` was keyed by local name only, so the first profile named took ADMIN_ONE from the shared store whatever its source."""
    spec = {
        "consumers": {
            "early": {"why": "fixture", "required": ["ADMIN_ONE"]},
            "adm": SPEC["consumers"]["adm"],
        }
    }
    out, done = _hydrate(["early", "adm"], _tree(tmp_path, spec=spec))
    assert out["ADMIN_ONE"] == "admin-v"
    assert done == ["early", "adm"]


def test_a_required_name_is_not_taken_by_an_earlier_profiles_optional_spec(tmp_path) -> None:
    """Review 8989f955.1: the optional spec of an earlier profile never shadows a required one of the same local name."""
    spec = {
        "consumers": {
            "early": {"why": "fixture", "optional": ["ADMIN_ONE"]},
            "adm": SPEC["consumers"]["adm"],
        }
    }
    out, _ = _hydrate(["early", "adm"], _tree(tmp_path, spec=spec))
    assert out["ADMIN_ONE"] == "admin-v"


def test_a_missing_token_file_with_only_optional_names_warns_and_binds_nothing(tmp_path) -> None:
    """Review 8989f955.2: the default-token path only warns for optional names, and a token file now does the same."""
    spec = {
        "consumers": {
            "adm-opt": {
                "why": "fixture",
                "optional": ["ADMIN_ONE"],
                "token_file": "bws-rotation-token",
            }
        }
    }
    env = _tree(tmp_path, rotation_mode=None, spec=spec)
    messages = tmp_path / "err.txt"
    with open(messages, "w", encoding="utf-8") as sink:
        out, done = bws_env.hydrate(["adm-opt"], env, stderr=sink)
    assert "ADMIN_ONE" not in out
    assert done == ["adm-opt"]
    text = messages.read_text(encoding="utf-8")
    assert "bws-rotation-token" in text
    assert "ADMIN_ONE" in text


def _supply_findings(token_file) -> list[str]:
    """Review 8989f955.6: the `token_file` of a profile is a bare file name in the token directory."""
    spec = {"consumers": {"p": {"why": "fixture", "token_file": token_file}}}
    return secret_supply.evaluate_consumers(spec, set())


@pytest.mark.parametrize("bad", ["../escape", "sub/token", "/abs/token", ".hidden", 7])
def test_a_token_file_that_is_not_a_bare_name_is_malformed(bad) -> None:
    assert any(f.startswith("MALFORMED PROFILE p: `token_file`") for f in _supply_findings(bad))


@pytest.mark.parametrize("good", ["", "bws-rotation-token"])
def test_a_bare_token_file_name_is_accepted(good) -> None:
    assert not any("token_file" in f for f in _supply_findings(good))
