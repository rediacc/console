"""`./run.sh setup`'s `account-bws-bootstrap` phase (agent/plans/PLAN-account-env-to-bws.md T15, T20).

BLOCKING on the bootstrap token and on the retired env files, ADVISORY on the public-key cache. Every case builds its own fixture root and environment, so the operator's real token file and real `private/account/.env` are never read: `XDG_CONFIG_HOME` points inside `tmp_path`, and `bws` is a fake on PATH.
"""

from __future__ import annotations

import json
import os
import stat

from rediacc_ci import paths
from rediacc_ci.setup import machine
from rediacc_ci.setup.ctx import Ctx

BOOTSTRAP_ENV = "BWS_ACCESS_TOKEN"


def _root(tmp_path):
    root = tmp_path / "root"
    (root / "private" / "account").mkdir(parents=True)
    (root / "private" / "account" / "package.json").write_text("{}\n", encoding="utf-8")
    (root / ".ci" / "config").mkdir(parents=True)
    (root / ".ci" / "config" / "bws-secret-map.json").write_text(
        '{"project": "p", "secrets": {"ACCOUNT_ED25519_PUBLIC_KEY_DEV": {"id": "1"}}}',
        encoding="utf-8",
    )
    listing = [
        {"key": "ACCOUNT_ED25519_PUBLIC_KEY_DEV", "value": "ed-pub-dev"},
        {"key": "ACCOUNT_X25519_PUBLIC_KEY_DEV", "value": "x-pub-dev"},
    ]
    (root / "listing.json").write_text(json.dumps(listing), encoding="utf-8")
    fake = root / "bin" / "bws"
    fake.parent.mkdir()
    fake.write_text("#!/bin/bash\ncat '%s'\n" % (root / "listing.json"), encoding="utf-8")
    fake.chmod(0o755)
    return root


def _env(root, tmp_path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in (BOOTSTRAP_ENV, "BWS_ACCESS_TOKEN_FILE")}
    env.update(
        {
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
            "BWS_ENV_ROOT": str(root),
            "BWS_BIN": str(root / "bin" / "bws"),
            "PYTHONPATH": str(paths.from_root(".ci")),
        }
    )
    return env


def _token(tmp_path, mode: int = 0o600) -> None:
    target = tmp_path / "xdg" / "rediacc" / "bws-access-token"
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    target.write_text("fixture-token-not-a-credential\n", encoding="utf-8")
    target.chmod(mode)


def _run(root, env) -> int:
    return machine._account_bws_bootstrap(Ctx(root=root, env=env))


def test_no_token_file_blocks_setup(tmp_path, capsys) -> None:
    root = _root(tmp_path)
    assert _run(root, _env(root, tmp_path)) == 1
    assert "no token file was found" in capsys.readouterr().err


def test_a_group_readable_token_file_blocks_setup(tmp_path, capsys) -> None:
    root = _root(tmp_path)
    _token(tmp_path, mode=0o640)
    assert _run(root, _env(root, tmp_path)) == 1
    assert "mode 0640" in capsys.readouterr().err


def test_a_leftover_env_file_blocks_setup_and_names_no_value(tmp_path, capsys) -> None:
    root = _root(tmp_path)
    _token(tmp_path)
    (root / "private" / "account" / ".env").write_text(
        "BWS_ACCESS_TOKEN=x\nACCOUNT_JWT_SECRET=planted-value\n", encoding="utf-8"
    )
    assert _run(root, _env(root, tmp_path)) == 1
    err = capsys.readouterr().err
    assert "private/account/.env still exists and assigns 1 name(s)" in err
    assert "planted-value" not in err


def test_an_env_bench_file_blocks_setup_even_when_empty(tmp_path, capsys) -> None:
    root = _root(tmp_path)
    _token(tmp_path)
    (root / "private" / "account" / ".env.bench").write_text("", encoding="utf-8")
    assert _run(root, _env(root, tmp_path)) == 1
    assert ".env.bench still exists" in capsys.readouterr().err


def test_a_token_only_env_file_is_tolerated_during_the_drain(tmp_path) -> None:
    """T17's window: `.env` holding nothing but the token does not block."""
    root = _root(tmp_path)
    _token(tmp_path)
    (root / "private" / "account" / ".env").write_text("BWS_ACCESS_TOKEN=x\n", encoding="utf-8")
    assert _run(root, _env(root, tmp_path)) == 0


def test_the_public_key_cache_holds_the_dev_keys_under_the_local_names(tmp_path) -> None:
    root = _root(tmp_path)
    _token(tmp_path)
    assert _run(root, _env(root, tmp_path)) == 0
    cache = root / machine.PUBLIC_KEY_CACHE
    assert cache.read_text(encoding="utf-8") == (
        "ACCOUNT_ED25519_PUBLIC_KEY=ed-pub-dev\nACCOUNT_X25519_PUBLIC_KEY=x-pub-dev\n"
    )
    assert stat.S_IMODE(cache.stat().st_mode) == 0o644


def test_an_unreachable_store_leaves_setup_green_and_says_so(tmp_path, capsys) -> None:
    root = _root(tmp_path)
    _token(tmp_path)
    (root / "bin" / "bws").write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
    assert _run(root, _env(root, tmp_path)) == 0
    assert "Could not refresh" in capsys.readouterr().err
    assert not (root / machine.PUBLIC_KEY_CACHE).exists()
