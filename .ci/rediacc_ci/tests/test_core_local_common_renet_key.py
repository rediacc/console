"""The account key a `./rdc.sh` renet build bakes (agent/plans/PLAN-production-key-only.md K3, Design 1).

`ensure_renet_built` resolves `ACCOUNT_ED25519_PUBLIC_KEY` in order: the environment, the public-key cache, Bitwarden through `bws_env cache-to` (which rewrites the cache), and otherwise refuses naming `./run.sh setup`. The resolved key reaches build.sh through its environment, because build.sh reads it from there only. Bitwarden is never reached here: `bws_env.load` is stubbed in every case, and a stub that must not be called raises.
"""

from __future__ import annotations

import os
import stat

import pytest

from rediacc_ci.core import bws_env, local_common
from rediacc_ci.release import renet_key_gate
from rediacc_ci.well_known import RENET_REPO

KEY = "ACCOUNT_ED25519_PUBLIC_KEY"
X_KEY = "ACCOUNT_X25519_PUBLIC_KEY"


def _root(tmp_path):
    root = tmp_path / "root"
    renet = root / "private" / "renet"
    renet.mkdir(parents=True)
    (root / "private" / "account").mkdir(parents=True)
    return root, renet


def _cache(root):
    return root / "private" / "account" / ".cache" / "public-keys.env"


def _load_answering(calls, answer, envs=None):
    def fake_load(names=None, *, env=None, stderr=None):
        del stderr
        if envs is not None:
            envs.append(env)
        calls.append(list(names or []))
        resolved = {name: answer[name] for name in names or [] if name in answer}
        missing = [name for name in names or [] if name not in answer]
        return resolved, missing, 1 if missing else 0

    return fake_load


def _load_forbidden(*_args, **_kwargs):
    raise AssertionError("bws_env.load was called although a key was already at hand")


@pytest.fixture
def build(monkeypatch):
    """`ensure_renet_built` with every machine-touching step stubbed; `_run` records the environment build.sh would get and writes the binary."""
    seen: list[dict[str, str]] = []

    def fake_run(argv, *, cwd=None, env=None, **_kwargs):
        seen.append(dict(env or {}))
        assert argv == ["./build.sh", "dev"]
        binary = os.path.join(cwd, "bin", "renet")
        os.makedirs(os.path.dirname(binary), exist_ok=True)
        with open(binary, "w", encoding="utf-8") as handle:
            handle.write("renet\n")
        return 0

    monkeypatch.setattr(local_common, "check_go_installed", lambda: None)
    monkeypatch.setattr(local_common, "_uname", lambda _flag: "Linux")
    monkeypatch.setattr(local_common, "git_tree_fingerprint", lambda *_a, **_k: "fp")
    monkeypatch.setattr(local_common, "renet_head", lambda _d: "")
    monkeypatch.setattr(local_common, "_run", fake_run)
    # The key gate is driven for real in the renet_key_refusal cases below; here the fake binary has no build info to read.
    monkeypatch.setattr(local_common, "renet_key_refusal", lambda _binary, _key: None)
    return seen


def _env(root, **extra):
    env = {k: v for k, v in os.environ.items() if k not in (KEY, "RENET_KEYLESS", "GITHUB_ACTIONS")}
    env.update({"LOCAL_ROOT_DIR": str(root), **extra})
    return env


def test_no_key_anywhere_refuses_naming_setup(tmp_path, monkeypatch, build, capsys) -> None:
    root, _renet = _root(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(bws_env, "load", _load_answering(calls, {}))
    with pytest.raises(local_common.LocalCommonError):
        local_common.ensure_renet_built(_env(root))
    assert calls == [[KEY, X_KEY]], "Bitwarden was not asked for the production names"
    assert build == [], "build.sh ran without a key"
    assert "./run.sh setup" in capsys.readouterr().err
    assert not _cache(root).exists(), "a partial or empty cache was written"


def test_a_key_from_bitwarden_reaches_the_build_and_the_cache(tmp_path, monkeypatch, build) -> None:
    root, _renet = _root(tmp_path)
    calls: list[list[str]] = []
    answer = {KEY: "prod-ed-pub", X_KEY: "prod-x-pub"}
    monkeypatch.setattr(bws_env, "load", _load_answering(calls, answer))
    assert local_common.ensure_renet_built(_env(root)) is True
    assert calls == [[KEY, X_KEY]]
    assert [env[KEY] for env in build] == ["prod-ed-pub"]
    cache = _cache(root)
    assert cache.read_text(encoding="utf-8") == (
        bws_env.PUBLIC_KEY_CACHE_HEADER
        + "ACCOUNT_ED25519_PUBLIC_KEY=prod-ed-pub\nACCOUNT_X25519_PUBLIC_KEY=prod-x-pub\n"
    )
    assert stat.S_IMODE(cache.stat().st_mode) == 0o644


def test_control_an_environment_key_never_reaches_bitwarden(tmp_path, monkeypatch, build) -> None:
    root, _renet = _root(tmp_path)
    monkeypatch.setattr(bws_env, "load", _load_forbidden)
    assert local_common.ensure_renet_built(_env(root, **{KEY: "shell-key"})) is True
    assert [env[KEY] for env in build] == ["shell-key"]
    assert not _cache(root).exists()


def test_a_cached_key_is_used_offline(tmp_path, monkeypatch, build) -> None:
    root, _renet = _root(tmp_path)
    _cache(root).parent.mkdir(parents=True)
    _cache(root).write_text(
        bws_env.PUBLIC_KEY_CACHE_HEADER + "X=1\nACCOUNT_ED25519_PUBLIC_KEY=cached-key\r\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(bws_env, "load", _load_forbidden)
    assert local_common.ensure_renet_built(_env(root)) is True
    assert [env[KEY] for env in build] == ["cached-key"]


def test_a_cache_from_before_the_one_keypair_store_is_refreshed(
    tmp_path, monkeypatch, build, capsys
) -> None:
    """Review 824f3bd7.2: an older setup aliased the retired DEV entry onto the production name, so a cache without the v2 header may hold the retired DEV key. It is skipped, Bitwarden answers, and the cache is rewritten with the header; the cached-key test above is the CONTROL (the same cache with the header is used offline)."""
    root, _renet = _root(tmp_path)
    _cache(root).parent.mkdir(parents=True)
    _cache(root).write_text("ACCOUNT_ED25519_PUBLIC_KEY=retired-dev-key\n", encoding="utf-8")
    calls: list[list[str]] = []
    answer = {KEY: "prod-ed-pub", X_KEY: "prod-x-pub"}
    monkeypatch.setattr(bws_env, "load", _load_answering(calls, answer))
    assert local_common.ensure_renet_built(_env(root)) is True
    assert calls == [[KEY, X_KEY]]
    assert [env[KEY] for env in build] == ["prod-ed-pub"]
    assert "predates the one-keypair store" in capsys.readouterr().err
    assert bws_env.public_key_cache_current(_cache(root).read_text(encoding="utf-8"))


def test_a_stale_cache_with_no_bitwarden_refuses(tmp_path, monkeypatch, build) -> None:
    root, renet = _root(tmp_path)
    _cache(root).parent.mkdir(parents=True)
    _cache(root).write_text("ACCOUNT_ED25519_PUBLIC_KEY=retired-dev-key\n", encoding="utf-8")
    monkeypatch.setattr(bws_env, "load", _load_answering([], {}))
    with pytest.raises(local_common.LocalCommonError):
        local_common.resolve_renet_account_key(str(renet), _env(root))
    assert build == []


@pytest.mark.parametrize(
    "extra", [{"RENET_KEYLESS": "1", "GITHUB_ACTIONS": "true"}, {"RENET_KEYLESS": "1"}]
)
def test_the_retired_keyless_switch_is_ignored(tmp_path, monkeypatch, build, capsys, extra) -> None:
    """Design 6: there is no keyless path, in CI or anywhere else; RENET_KEYLESS reads as unset and the build is refused naming the fix."""
    root, renet = _root(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(bws_env, "load", _load_answering(calls, {}))
    with pytest.raises(local_common.LocalCommonError):
        local_common.resolve_renet_account_key(str(renet), _env(root, **extra))
    assert calls == [[KEY, X_KEY]]
    assert build == []
    assert "./run.sh setup" in capsys.readouterr().err


# A syntactically valid ED25519 public key and a second one, fixture only.
GOOD = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
OTHER = "HxwdHhscGhkYFxYVFBMSERAPDg0MCwoJCAcGBQQDAgE="


def _build_info(key=None, tags=""):
    flag = (
        ""
        if key is None
        else " -X github.com/%s/pkg/license/keys.ProductionPublicKey=%s" % (RENET_REPO, key)
    )
    text = 'bin/renet: go1.25\n\tbuild\t-ldflags="-X main.Version=0.0.0-dev%s"\n' % flag
    if tags:
        text += "\tbuild\t-tags=%s\n" % tags
    return text


@pytest.mark.parametrize(
    ("info", "passes"),
    [
        pytest.param(_build_info(GOOD), True, id="bakes-the-key"),
        pytest.param(_build_info(OTHER), False, id="another-key"),
        pytest.param(_build_info(None), False, id="no-key"),
        pytest.param(_build_info(GOOD, "nolicense"), False, id="license-checks-compiled-out"),
    ],
)
def test_renet_key_refusal_drives_the_real_gate(monkeypatch, capsys, info, passes) -> None:
    monkeypatch.setattr(renet_key_gate, "go_version_m", lambda _binary, _run=None: info)
    refusal = local_common.renet_key_refusal("bin/renet", GOOD)
    assert (refusal is None) is passes
    out = capsys.readouterr()
    # The verdict line goes to stderr, and a key is never printed, only fingerprints.
    assert out.out == ""
    assert GOOD not in out.err
    assert OTHER not in out.err
    assert ("ok      bin/renet" in out.err) is passes


def test_renet_key_refusal_refuses_a_retired_or_malformed_expected_key(monkeypatch) -> None:
    monkeypatch.setattr(
        renet_key_gate, "go_version_m", lambda _binary, _run=None: _build_info(GOOD)
    )
    assert local_common.renet_key_refusal("bin/renet", "not-a-key") is not None
    assert local_common.renet_key_refusal("bin/renet", "") is not None


@pytest.mark.usefixtures("build")
def test_bitwarden_is_read_under_the_callers_environment(tmp_path, monkeypatch) -> None:
    """The token comes from the environment handed to ensure_renet_built, never this process's: a test or CI wrapper that builds its own environment never reaches the operator's token file."""
    root, _renet = _root(tmp_path)
    calls: list[list[str]] = []
    envs: list = []
    answer = {KEY: "prod-ed-pub", X_KEY: "prod-x-pub"}
    monkeypatch.setattr(bws_env, "load", _load_answering(calls, answer, envs))
    env = _env(root, BWS_ACCESS_TOKEN_FILE=str(tmp_path / "caller-token"))
    assert local_common.ensure_renet_built(env) is True
    assert len(envs) == 1
    assert envs[0]["BWS_ACCESS_TOKEN_FILE"] == str(tmp_path / "caller-token")
    assert envs[0]["LOCAL_ROOT_DIR"] == str(root)
