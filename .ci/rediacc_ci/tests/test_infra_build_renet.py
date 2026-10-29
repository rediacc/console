"""`.ci/rediacc_ci/infra/build_renet.py`, the thin CI wrapper over `local_common.ensure_renet_built`.

The retired shell twin's differential cases pinned the shared-path identity stamp (`bin/.renet-build-identity`), which no longer exists: each flavor now has its own directory and its own stamp (`core.renet_flavor`, PLAN-per-flavor-renet-binary-paths P3). What is pinned here instead is what a CI step reads: the flavor chosen with build.sh's precedence, the `RENET_BINARY=<path>` line, the per-flavor skip, and that a build of one flavor never touches the other's binary.

Every case runs the COPY of the wrapper inside a fixture tree, with a recording fake `build.sh` that writes into the flavor directory the explicit flag names, and a PATH rebuilt from named tools. `test_the_fake_build_is_actually_reached` is the anti-vacuity control.
"""

import hashlib
import json
import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.infra import build_renet

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "infra" / "build_renet.py"
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/infra/build_renet.py")

# The recording `./build.sh`: logs its argv and cwd, then writes the three binaries of the flavor its flag names (`--license` is `bin/enforce/`, anything else `bin/`), each holding the flavor's name.
FAKE_BUILD_SH = """#!/usr/bin/env python3
import os, pathlib, sys
LOG = %(log)r
ROOT = %(root)r
RC = %(rc)d
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("\\t".join(["build.sh", os.path.relpath(os.getcwd(), ROOT), *sys.argv[1:]]) + "\\n")
flavor = "enforce" if "--license" in sys.argv[1:] else "nolicense"
out = pathlib.Path(os.getcwd()) / "bin"
if flavor == "enforce":
    out = out / "enforce"
out.mkdir(parents=True, exist_ok=True)
for name in ("renet", "renet-linux-amd64", "renet-linux-arm64"):
    (out / name).write_text("fake-renet-" + flavor + "\\n", encoding="utf-8")
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

FAKE_GO = """#!/usr/bin/env python3
import sys
sys.exit(97)
"""

NEEDED = ("python3", "git", "sha256sum", "env", "sh", "bash", "cat", "mkdir", "ls")


def _fixture(
    where: pathlib.Path, *, build_rc: int = 0, go: bool = True, submodule: bool = True
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
            % {"log": str(root.parent / "buildlog.txt"), "root": str(root), "rc": build_rc},
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
        (binder / "go").write_text(FAKE_GO, encoding="utf-8")
        (binder / "go").chmod(0o755)
    return root


def _run(root: pathlib.Path, *argv: str, env_extra: dict[str, str] | None = None) -> dict:
    env = {
        "PATH": str(root.parent / "pathbin"),
        "HOME": str(root.parent),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(ROOT / ".ci"),
        # The CI keyless test build (agent/plans/PLAN-production-key-only.md K3): no account key, admitted only under GITHUB_ACTIONS.
        "RENET_KEYLESS": "1",
        "GITHUB_ACTIONS": "true",
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
    out = _run(root, "--nolicense")
    assert out["exit"] == 0, out
    assert out["calls"], "the recording build.sh was never invoked"
    fields = out["calls"][0].split("\t")
    assert fields[1] == "private/renet", "build.sh ran in %r" % fields[1]
    assert fields[2:] == ["dev", "--nolicense"], "build.sh got %r" % fields[2:]
    assert out["stdout"] == "RENET_BINARY=<root>/private/renet/bin/renet\n"


def test_a_license_build_then_a_nolicense_build_leaves_the_enforcing_binary_alone(tmp_path):
    root = _fixture(tmp_path)
    first = _run(root, "--license")
    assert first["exit"] == 0, first
    assert first["stdout"] == "RENET_BINARY=<root>/private/renet/bin/enforce/renet\n"
    enforcing = {n: _bytes(root, "bin/enforce/" + n) for n in ("renet", "renet-linux-amd64")}
    assert enforcing["renet"] == b"fake-renet-enforce\n"
    second = _run(root, "--nolicense")
    assert second["exit"] == 0, second
    for name, content in enforcing.items():
        assert _bytes(root, "bin/enforce/" + name) == content, "%s changed" % name
    assert _bytes(root, "bin/renet") == b"fake-renet-nolicense\n"


def test_an_explicit_nolicense_beats_the_license_env(tmp_path):
    """build.sh's precedence, the opposite of the retired identity stamp: the flag wins over `RDC_RENET_LICENSE=1`."""
    root = _fixture(tmp_path)
    out = _run(root, "--nolicense", env_extra={"RDC_RENET_LICENSE": "1"})
    assert out["exit"] == 0, out
    assert out["stdout"] == "RENET_BINARY=<root>/private/renet/bin/renet\n"
    assert out["calls"][0].split("\t")[2:] == ["dev", "--nolicense"]
    assert not (root / "private" / "renet" / "bin" / "enforce").exists()


def test_the_license_env_alone_selects_the_enforcing_binary(tmp_path):
    root = _fixture(tmp_path)
    out = _run(root, env_extra={"RDC_RENET_LICENSE": "1"})
    assert out["exit"] == 0, out
    assert out["stdout"] == "RENET_BINARY=<root>/private/renet/bin/enforce/renet\n"
    assert out["calls"][0].split("\t")[2:] == ["dev", "--license"]


def test_a_second_run_skips_on_the_per_flavor_stamp(tmp_path):
    root = _fixture(tmp_path)
    assert _run(root, "--nolicense")["exit"] == 0
    stamp = root / "private" / "renet" / "bin" / ".renet-build-stamp"
    assert stamp.is_file()
    again = _run(root, "--nolicense")
    assert again["exit"] == 0, again
    assert again["calls"] == [], "a build ran despite a matching stamp: %r" % again["calls"]
    assert again["stdout"] == "RENET_BINARY=<root>/private/renet/bin/renet\n"
    # CONTROL: the other flavor has no stamp of its own, so it builds.
    other = _run(root, "--license")
    assert other["calls"], "the enforcing flavor was skipped on the nolicense stamp"
    enforce_stamp = root / "private" / "renet" / "bin" / "enforce" / ".renet-build-stamp"
    assert enforce_stamp.read_text(encoding="utf-8") != stamp.read_text(encoding="utf-8")


def test_a_swapped_binary_under_an_unchanged_stamp_is_rebuilt(tmp_path):
    root = _fixture(tmp_path)
    assert _run(root, "--nolicense")["exit"] == 0
    (root / "private" / "renet" / "bin" / "renet").write_text(
        "swapped-by-hand-xx\n", encoding="utf-8"
    )
    out = _run(root, "--nolicense")
    assert out["calls"], "a binary replaced under its stamp was handed back"
    assert _bytes(root, "bin/renet") == b"fake-renet-nolicense\n"


def test_the_stamp_is_not_written_when_the_build_fails(tmp_path):
    root = _fixture(tmp_path, build_rc=3)
    out = _run(root, "--nolicense")
    # build.sh's own status, not a flat 1 (review 6de769e7.2).
    assert out["exit"] == 3, out
    assert out["calls"]
    assert not (root / "private" / "renet" / "bin" / ".renet-build-stamp").exists()
    assert "RENET_BINARY=" not in out["stdout"]


def test_a_build_killed_by_a_signal_exits_128_plus_the_signal(tmp_path):
    # A negative subprocess code would exit as 256 - signal (247 for SIGKILL); the shell twin reports 128 + signal (review f57d518c.2).
    root = _fixture(tmp_path, build_rc=-9)
    out = _run(root, "--nolicense")
    assert out["exit"] == 137, out
    assert "RENET_BINARY=" not in out["stdout"]


def test_a_missing_submodule_names_the_fix(tmp_path):
    root = _fixture(tmp_path, submodule=False)
    out = _run(root, "--nolicense")
    assert out["exit"] == 1
    assert "git submodule update --init private/renet" in out["stderr"]
    assert out["calls"] == []


def test_a_missing_go_fails_before_any_build(tmp_path):
    root = _fixture(tmp_path, go=False)
    out = _run(root, "--nolicense")
    assert out["exit"] == 1
    assert out["calls"] == []
    assert "Go is not installed" in out["stderr"]


def test_github_env_receives_the_flavor_binary(tmp_path):
    root = _fixture(tmp_path)
    gh = tmp_path / "github-env"
    gh.write_text("", encoding="utf-8")
    out = _run(root, "--license", env_extra={"GITHUB_ENV": str(gh)})
    assert out["exit"] == 0, out
    assert (
        gh.read_text(encoding="utf-8") == "RENET_BINARY=%s/private/renet/bin/enforce/renet\n" % root
    )


def test_build_args_drops_everything_but_the_two_flags():
    assert build_renet.build_args([]) == []
    assert build_renet.build_args(["--nolicence"]) == []
    assert build_renet.build_args(["-v", "--license", "x"]) == ["--license"]
    assert build_renet.build_args(["--nolicense", "--license"]) == ["--nolicense", "--license"]


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
        "--nolicense",
        env_extra={"GITHUB_OUTPUT": str(gh_out), "RENET_EMBED_CACHE_HIT": hit},
    )
    assert (out["exit"] == 0) == (build_rc == 0), out
    assert gh_out.read_text(encoding="utf-8") == "embed-cacheable=%s\n" % want


def test_a_stale_cache_hit_is_announced_before_the_restage(tmp_path):
    """The PR #591 shape: a HIT that restored the checkout skeleton. build.sh restages (~11 min) and nothing else in the log says why."""
    root = _fixture(_sub(tmp_path, "w"))
    out = _run(root, "--nolicense", env_extra={"RENET_EMBED_CACHE_HIT": "true"})
    assert out["stdout"].startswith("::warning title=Stale renet-embed-assets cache entry::")
    # CONTROL: a hit on a real staging says nothing.
    good = _fixture(_sub(tmp_path, "g"))
    _stage_receipt(good)
    quiet = _run(good, "--nolicense", env_extra={"RENET_EMBED_CACHE_HIT": "true"})
    assert "::warning" not in quiet["stdout"]
