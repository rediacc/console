"""`.ci/rediacc_ci/infra/build_renet.py`, the thin CI wrapper over `local_common.ensure_renet_built`.

What is pinned here is what a CI step reads: the one licensed build in `bin/` (agent/plans/PLAN-production-key-only.md Design 6), the `RENET_BINARY=<path>` line, the stamp skip, and the key gate that refuses a build which does not bake the account key.

Every case runs the COPY of the wrapper inside a fixture tree, with a recording fake `build.sh` that writes `bin/`, a fake `go` whose `version -m` reports the key the fake binary was built with, and a PATH rebuilt from named tools. `test_the_fake_build_is_actually_reached` is the anti-vacuity control.
"""

import hashlib
import json
import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.well_known import RENET_REPO

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "infra" / "build_renet.py"
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/infra/build_renet.py")

# A syntactically valid ED25519 public key (32 bytes 0x00..0x1f, base64), fixture only.
KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
OTHER_KEY = "HxwdHhscGhkYFxYVFBMSERAPDg0MCwoJCAcGBQQDAgE="

# The recording `./build.sh`: logs its argv and cwd, then writes the three binaries into `bin/`, each holding the key it was built with (or `unkeyed` when BAKE is false), which the fake `go version -m` reports back.
FAKE_BUILD_SH = """#!/usr/bin/env python3
import os, pathlib, sys
LOG = %(log)r
ROOT = %(root)r
RC = %(rc)d
BAKE = %(bake)r
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("\\t".join(["build.sh", os.path.relpath(os.getcwd(), ROOT), *sys.argv[1:]]) + "\\n")
out = pathlib.Path(os.getcwd()) / "bin"
out.mkdir(parents=True, exist_ok=True)
baked = os.environ.get("ACCOUNT_ED25519_PUBLIC_KEY", "") if BAKE else "unkeyed"
for name in ("renet", "renet-linux-amd64", "renet-linux-arm64"):
    (out / name).write_text("fake-renet " + baked + "\\n", encoding="utf-8")
if RC < 0:
    os.kill(os.getpid(), -RC)
sys.exit(RC)
"""

FAKE_UNAME = """#!/usr/bin/env python3
import sys
if sys.argv[1:] == ["-s"]:
    sys.stdout.write("Linux\\n")
else:
    sys.exit(1)
"""

# `go version -m <bin>` prints a build line carrying the key ldflag the fake build wrote into the binary; anything else exits 97.
FAKE_GO = """#!/usr/bin/env python3
import pathlib, sys
if sys.argv[1:3] != ["version", "-m"]:
    sys.exit(97)
baked = pathlib.Path(sys.argv[3]).read_text(encoding="utf-8").split()[-1]
flag = "" if baked == "unkeyed" else " -X github.com/%(repo)s/pkg/license/keys.ProductionPublicKey=" + baked
sys.stdout.write(sys.argv[3] + ": go1.25\\n\\tbuild\\t-ldflags=\\"-X main.Version=0.0.0-dev" + flag + "\\"\\n")
"""

NEEDED = ("python3", "git", "sha256sum", "env", "sh", "bash", "cat", "mkdir", "ls")


def _fixture(
    where: pathlib.Path,
    *,
    build_rc: int = 0,
    go: bool = True,
    submodule: bool = True,
    bake: bool = True,
) -> pathlib.Path:
    """A tree shaped like the repository, holding a COPY of the wrapper: it derives the console root from its own location, so the tracked file driven in place would build in the real checkout."""
    root = where.resolve() / "tree"
    (root / ".ci" / "rediacc_ci" / "infra").mkdir(parents=True)
    shutil.copy2(PORT, root / PORT_REL)
    if submodule:
        src = root / "private" / "renet"
        src.mkdir(parents=True)
        script = src / "build.sh"
        script.write_text(
            FAKE_BUILD_SH
            % {
                "log": str(root.parent / "buildlog.txt"),
                "root": str(root),
                "rc": build_rc,
                "bake": bake,
            },
            encoding="utf-8",
        )
        script.chmod(0o755)
    binder = where.resolve() / "pathbin"
    binder.mkdir()
    for tool in NEEDED:
        target = shutil.which(tool)
        if target is not None:
            (binder / tool).symlink_to(target)
    (binder / "uname").write_text(FAKE_UNAME, encoding="utf-8")
    (binder / "uname").chmod(0o755)
    if go:
        (binder / "go").write_text(FAKE_GO % {"repo": RENET_REPO}, encoding="utf-8")
        (binder / "go").chmod(0o755)
    return root


def _run(root: pathlib.Path, *argv: str, env_extra: dict[str, str] | None = None) -> dict:
    env = {
        "PATH": str(root.parent / "pathbin"),
        "HOME": str(root.parent),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(ROOT / ".ci"),
        # The account key is named in the environment, so neither the cache nor Bitwarden is read.
        "ACCOUNT_ED25519_PUBLIC_KEY": KEY,
        **(env_extra or {}),
    }
    proc = subprocess.run(
        ["python3", str(root / PORT_REL), *argv],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    log = root.parent / "buildlog.txt"
    calls = (
        [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln] if log.exists() else []
    )
    if log.exists():
        log.unlink()
    return {
        "exit": proc.returncode,
        "stdout": proc.stdout.replace(str(root), "<root>"),
        "stderr": proc.stderr.replace(str(root), "<root>"),
        "calls": calls,
    }


def _sub(base: pathlib.Path, name: str) -> pathlib.Path:
    path = base / name
    path.mkdir()
    return path


def _bytes(root: pathlib.Path, rel: str) -> bytes:
    return (root / "private" / "renet" / rel).read_bytes()


def test_the_fake_build_is_actually_reached(tmp_path):
    """ANTI-VACUITY. Every case below is worthless if build.sh never ran."""
    root = _fixture(tmp_path)
    out = _run(root)
    assert out["exit"] == 0, out
    assert out["calls"], "the recording build.sh was never invoked"
    fields = out["calls"][0].split("\t")
    assert fields[1] == "private/renet", "build.sh ran in %r" % fields[1]
    assert fields[2:] == ["dev"], "build.sh got %r" % fields[2:]
    assert out["stdout"] == "RENET_BINARY=<root>/private/renet/bin/renet\n"
    # The key gate's verdict is on stderr, so stdout stays the one RENET_BINARY line.
    assert "ok      <root>/private/renet/bin/renet" in out["stderr"]


def test_a_retired_flavor_flag_is_dropped_and_builds_the_one_binary(tmp_path):
    root = _fixture(tmp_path)
    out = _run(root, "--license", "-v")
    assert out["exit"] == 0, out
    assert out["calls"][0].split("\t")[2:] == ["dev"]
    assert out["stdout"] == "RENET_BINARY=<root>/private/renet/bin/renet\n"
    assert not (root / "private" / "renet" / "bin" / "enforce").exists()


def test_a_build_that_bakes_no_key_is_refused_and_leaves_no_stamp(tmp_path):
    root = _fixture(tmp_path, bake=False)
    out = _run(root)
    assert out["exit"] == 1, out
    assert "renet key gate refused" in out["stderr"]
    assert "RENET_BINARY=" not in out["stdout"]
    assert not (root / "private" / "renet" / "bin" / ".renet-build-stamp").exists()


def test_a_build_that_bakes_another_key_is_refused(tmp_path):
    root = _fixture(tmp_path)
    assert _run(root)["exit"] == 0
    # The binary now bakes KEY; a run expecting OTHER_KEY rebuilds (the stamp carries the key) and the gate compares against OTHER_KEY.
    out = _run(root, env_extra={"ACCOUNT_ED25519_PUBLIC_KEY": OTHER_KEY})
    assert out["calls"], "a key change did not rebuild"
    assert out["exit"] == 0, out
    # CONTROL: a fake build that ignores the key it was handed is refused.
    bad = _fixture(_sub(tmp_path, "bad"), bake=False)
    assert _run(bad, env_extra={"ACCOUNT_ED25519_PUBLIC_KEY": OTHER_KEY})["exit"] == 1


def test_a_second_run_skips_on_the_stamp(tmp_path):
    root = _fixture(tmp_path)
    assert _run(root)["exit"] == 0
    stamp = root / "private" / "renet" / "bin" / ".renet-build-stamp"
    assert stamp.is_file()
    again = _run(root)
    assert again["exit"] == 0, again
    assert again["calls"] == [], "a build ran despite a matching stamp: %r" % again["calls"]
    assert again["stdout"] == "RENET_BINARY=<root>/private/renet/bin/renet\n"


def test_a_swapped_binary_under_an_unchanged_stamp_is_rebuilt(tmp_path):
    root = _fixture(tmp_path)
    assert _run(root)["exit"] == 0
    (root / "private" / "renet" / "bin" / "renet").write_text(
        "swapped-by-hand-xx\n", encoding="utf-8"
    )
    out = _run(root)
    assert out["calls"], "a binary replaced under its stamp was handed back"
    assert _bytes(root, "bin/renet") == ("fake-renet %s\n" % KEY).encode()


def test_the_stamp_is_not_written_when_the_build_fails(tmp_path):
    root = _fixture(tmp_path, build_rc=3)
    out = _run(root)
    # build.sh's own status, not a flat 1 (review 6de769e7.2).
    assert out["exit"] == 3, out
    assert out["calls"]
    assert not (root / "private" / "renet" / "bin" / ".renet-build-stamp").exists()
    assert "RENET_BINARY=" not in out["stdout"]


def test_a_build_killed_by_a_signal_exits_128_plus_the_signal(tmp_path):
    # A negative subprocess code would exit as 256 - signal (247 for SIGKILL); the shell twin reports 128 + signal (review f57d518c.2).
    root = _fixture(tmp_path, build_rc=-9)
    out = _run(root)
    assert out["exit"] == 137, out
    assert "RENET_BINARY=" not in out["stdout"]


def test_a_missing_submodule_names_the_fix(tmp_path):
    root = _fixture(tmp_path, submodule=False)
    out = _run(root)
    assert out["exit"] == 1
    assert "git submodule update --init private/renet" in out["stderr"]
    assert out["calls"] == []


def test_a_missing_go_fails_before_any_build(tmp_path):
    root = _fixture(tmp_path, go=False)
    out = _run(root)
    assert out["exit"] == 1
    assert out["calls"] == []
    assert "Go is not installed" in out["stderr"]


def test_github_env_receives_the_binary(tmp_path):
    root = _fixture(tmp_path)
    gh = tmp_path / "github-env"
    gh.write_text("", encoding="utf-8")
    out = _run(root, env_extra={"GITHUB_ENV": str(gh)})
    assert out["exit"] == 0, out
    assert gh.read_text(encoding="utf-8") == "RENET_BINARY=%s/private/renet/bin/renet\n" % root


# ---------------------------------------------------------------------------
# The embed-assets cache verdict (rediacc_ci.infra.renet_embed_cache): it reads RENET_EMBED_CACHE_HIT and GITHUB_OUTPUT.
# ---------------------------------------------------------------------------


def _stage_receipt(root: pathlib.Path) -> None:
    """One staged asset plus a receipt that vouches for it, in the fixture's renet tree."""
    src = root / "private" / "renet"
    lock = b'{"components": {}}'
    (src / "embed-assets.lock.json").write_bytes(lock)
    asset = src / "pkg" / "embed" / "assets" / "amd64" / "base" / "criu-linux-amd64.zst"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"criu")
    receipt = {
        "lockfileSha256": hashlib.sha256(lock).hexdigest(),
        "assets": {
            "amd64/base/criu-linux-amd64.zst": {"sha256": hashlib.sha256(b"criu").hexdigest()}
        },
    }
    (asset.parents[2] / ".staged.json").write_text(json.dumps(receipt), encoding="utf-8")


@pytest.mark.parametrize(
    ("hit", "staged", "build_rc", "want"),
    [
        pytest.param("false", True, 0, "true", id="miss-staged-built"),
        pytest.param("false", True, 3, "true", id="miss-staged-go-build-failed-still-saves"),
        pytest.param("false", False, 3, "false", id="miss-staging-never-finished"),
        pytest.param("true", True, 0, "false", id="hit-never-saves"),
    ],
)
def test_the_wrapper_writes_the_cache_verdict_on_every_exit(tmp_path, hit, staged, build_rc, want):
    root = _fixture(tmp_path, build_rc=build_rc)
    if staged:
        _stage_receipt(root)
    gh_out = tmp_path / "gh-output"
    gh_out.write_text("", encoding="utf-8")
    out = _run(
        root,
        env_extra={"GITHUB_OUTPUT": str(gh_out), "RENET_EMBED_CACHE_HIT": hit},
    )
    assert (out["exit"] == 0) == (build_rc == 0), out
    assert gh_out.read_text(encoding="utf-8") == "embed-cacheable=%s\n" % want


def test_a_stale_cache_hit_is_announced_before_the_restage(tmp_path):
    """The PR #591 shape: a HIT that restored the checkout skeleton. build.sh restages (~11 min) and nothing else in the log says why."""
    root = _fixture(_sub(tmp_path, "w"))
    out = _run(root, env_extra={"RENET_EMBED_CACHE_HIT": "true"})
    assert out["stdout"].startswith("::warning title=Stale renet-embed-assets cache entry::")
    # CONTROL: a hit on a real staging says nothing.
    good = _fixture(_sub(tmp_path, "g"))
    _stage_receipt(good)
    quiet = _run(good, env_extra={"RENET_EMBED_CACHE_HIT": "true"})
    assert "::warning" not in quiet["stdout"]
