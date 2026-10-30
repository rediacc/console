"""`private/renet/build.sh key-ldflags`: renet refuses to build without a licence key (PLAN-production-key-only K4, gate G2).

The seam prints exactly the ldflag every build flavor (`dev`, `build`, `stage_linux`) links with, through the same `_account_key_ldflags`. The key comes from `ACCOUNT_ED25519_PUBLIC_KEY` in the environment only: the public-key cache beside it is never read, and there is no keyless exception: `RENET_KEYLESS` and `GITHUB_ACTIONS` change nothing (operator 2026-10-30, the nolicense removal). The real build.sh is copied into a temp tree beside a planted cache, so the cache-fallback case is driven against the path the old fallback read. Every key here is an arbitrary value, never a real one.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[3]
BUILD_SH = REPO / "private" / "renet" / "build.sh"
SYMBOL = "github.com/rediacc/renet/pkg/license/keys.ProductionPublicKey="
CACHED = "Y2FjaGVkLWtleS1ub3QtcmVhbA=="
ENV_KEY = "ZW52LWtleS1ub3QtcmVhbA=="
STRIPPED = ("ACCOUNT_ED25519_PUBLIC_KEY", "RENET_KEYLESS", "GITHUB_ACTIONS")


def _tree(tmp_path: pathlib.Path) -> pathlib.Path:
    """private/renet/build.sh plus a private/account/.cache/public-keys.env holding a key, where the retired fallback looked."""
    renet = tmp_path / "private" / "renet"
    renet.mkdir(parents=True)
    shutil.copy2(BUILD_SH, renet / "build.sh")
    (renet / "scripts").mkdir()
    (renet / "scripts" / "pull-with-retry.sh").write_text("", encoding="utf-8")
    cache = tmp_path / "private" / "account" / ".cache" / "public-keys.env"
    cache.parent.mkdir(parents=True)
    cache.write_text(
        f"ACCOUNT_ED25519_PUBLIC_KEY={CACHED}\nACCOUNT_X25519_PUBLIC_KEY=x\n", encoding="utf-8"
    )
    return renet / "build.sh"


def _key_ldflags(script: pathlib.Path, **env: str) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if k not in STRIPPED}
    base.update(env)
    return subprocess.run(
        ["bash", str(script), "key-ldflags"],
        cwd=script.parent,
        env=base,
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )


def test_no_env_key_fails_and_the_cache_is_not_read(tmp_path: pathlib.Path) -> None:
    done = _key_ldflags(_tree(tmp_path))
    assert done.returncode == 1
    assert done.stdout == ""
    assert "ACCOUNT_ED25519_PUBLIC_KEY is not set" in done.stderr
    assert "./run.sh setup" in done.stderr
    assert CACHED not in done.stdout + done.stderr


def test_renet_keyless_is_refused_everywhere(tmp_path: pathlib.Path) -> None:
    """The retired CI escape: RENET_KEYLESS=1, even under GITHUB_ACTIONS=true, still fails closed."""
    script = _tree(tmp_path)
    for env in ({"RENET_KEYLESS": "1"}, {"RENET_KEYLESS": "1", "GITHUB_ACTIONS": "true"}, {"GITHUB_ACTIONS": "true"}):
        done = _key_ldflags(script, **env)
        assert done.returncode == 1, env
        assert done.stdout == "", env
        assert "ACCOUNT_ED25519_PUBLIC_KEY is not set" in done.stderr, env


def test_build_sh_names_no_keyless_escape() -> None:
    assert "RENET_KEYLESS" not in BUILD_SH.read_text(encoding="utf-8")


def test_control_an_env_key_is_baked(tmp_path: pathlib.Path) -> None:
    done = _key_ldflags(_tree(tmp_path), ACCOUNT_ED25519_PUBLIC_KEY=ENV_KEY)
    assert done.returncode == 0, done.stderr
    assert done.stdout == f"-X {SYMBOL}{ENV_KEY}"
    assert CACHED not in done.stdout


def test_build_sh_names_no_cache_file() -> None:
    """The retired fallback read private/account/.cache/public-keys.env; nothing in build.sh may name it again."""
    assert "public-keys.env" not in BUILD_SH.read_text(encoding="utf-8")


def test_every_flavor_captures_the_ldflag_before_linking() -> None:
    """A failing `$(...)` inside an argument list does not trip `set -e`; each flavor assigns it first, so the refusal stops the build."""
    text = BUILD_SH.read_text(encoding="utf-8")
    assert ' "$(_account_key_ldflags)"' not in text
    assert text.count('key_ldflags="$(_account_key_ldflags)"') == 3


def _dev(
    script: pathlib.Path, tmp_path: pathlib.Path, **env: str
) -> tuple[subprocess.CompletedProcess[str], pathlib.Path]:
    """`build.sh dev` with the asset steps stubbed and a fake `go` that records each call; returns the run and the record."""
    fake = tmp_path / "fakebin"
    fake.mkdir()
    record = tmp_path / "go-calls"
    (fake / "go").write_text(
        "#!/bin/bash\n"
        f'printf "%s\\n" "$*" >>"{record}"\n'
        'out=""; while [[ $# -gt 0 ]]; do [[ "$1" == "-o" ]] && out="$2"; shift; done\n'
        '[[ -n "$out" ]] && : >"$out"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    (fake / "go").chmod(0o755)
    (script.parent / "scripts").mkdir(exist_ok=True)
    (script.parent / "scripts" / "pull-with-retry.sh").write_text("", encoding="utf-8")
    base = {k: v for k, v in os.environ.items() if k not in STRIPPED}
    base["PATH"] = f"{fake}{os.pathsep}{base['PATH']}"
    base.update(env)
    stub = (
        'source "$1" || true; set -e; '
        "_embed_assets_or_die() { echo ASSETS >&2; }; embed_proxy() { :; }; ebpf_generate() { :; }; "
        "dev"
    )
    done = subprocess.run(
        ["bash", "-c", stub, "dev", str(script)],
        cwd=script.parent,
        env=base,
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    return done, record


def test_dev_without_a_key_exits_1_before_any_step(tmp_path: pathlib.Path) -> None:
    done, record = _dev(_tree(tmp_path), tmp_path)
    assert done.returncode == 1
    assert "ACCOUNT_ED25519_PUBLIC_KEY is not set" in done.stderr
    assert "ASSETS" not in done.stderr
    assert not record.exists()


def test_control_dev_with_a_key_links_it(tmp_path: pathlib.Path) -> None:
    done, record = _dev(_tree(tmp_path), tmp_path, ACCOUNT_ED25519_PUBLIC_KEY=ENV_KEY)
    assert done.returncode == 0, done.stderr
    calls = record.read_text(encoding="utf-8")
    assert f"keys.ProductionPublicKey={ENV_KEY}" in calls
    assert CACHED not in calls
