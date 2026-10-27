"""The release-run admission of the git-level `pre-push` (box W1-D of agent/plans/PLAN-local-release.md): `release_run.py` and `githooks._release_admitted`.

A REAL PROCESS CHAIN. Each case runs a fake `python3 -m rediacc_ci.release.local` (a stand-in package on PYTHONPATH, so the argv is the real entry's shape), which writes its record through `release_run.write_release_run` for its own pid and then starts the hook as its child. So the pid, the `/proc` start time and the argv the hook checks are a live process's, never planted values. The hook either runs in a driver that points `githooks.CONSOLE_ROOT` at a fixture console, or, for the end-to-end pair, under a real `git push` with `core.hooksPath` at the real hooks and the real console.

BOTH DIRECTIONS. A listed push to `main`, which the hook refuses without a release run, is admitted; the same push with the variable unset, a forged record (the pid of a live release entry that is not this hook's ancestor, or a wrong start time), a wrong tree, an unlisted ref, an unlisted oid, and a record outside `.ci/cache/release/` are each refused with today's `main` refusal.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import time
import uuid

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
HOOKS = REPO_ROOT / ".claude" / "rediacc_hooks" / "git"
ZERO = "0" * 40
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}
STRIP = ("COMMIT_POLICY_OK", "REDIACC_RELEASE_RUN", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None, path
    assert spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RR = _load("release_run_under_test", HOOKS / "release_run.py")

# The fake entry: `python3 -m rediacc_ci.release.local <cfg.json>`. Mode "sleep" only lives (the forged-pid sibling); mode "push" writes the record and runs the hook as its child.
ENTRY = r"""
import importlib.util, json, os, subprocess, sys, time
cfg = json.load(open(sys.argv[1]))
if cfg["mode"] == "sleep":
    time.sleep(120)
    sys.exit(0)
spec = importlib.util.spec_from_file_location("rr", cfg["release_run"])
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)
path = rr.write_release_run(cfg["console"], cfg["run_id"], tree=cfg["tree"], version="9.9.9",
                            channel="edge", pushes=cfg["pushes"], pid=cfg.get("record_pid") or os.getpid())
rec = json.loads(open(path).read())
for key, value in cfg.get("tamper", {}).items():
    rec[key] = rec[key] + value if isinstance(value, int) else value
open(path, "w").write(json.dumps(rec))
named = cfg.get("named") or str(path)
if cfg.get("copy_to"):
    open(cfg["copy_to"], "w").write(open(path).read())
    named = cfg["copy_to"]
env = dict(os.environ)
if cfg["set_env"]:
    env["REDIACC_RELEASE_RUN"] = named
proc = subprocess.run(cfg["child"], cwd=cfg["pusher"], env=env)
os.unlink(path)
sys.exit(proc.returncode)
"""

# The hook in a driver: the real githooks.py with CONSOLE_ROOT pointed at the fixture console.
DRIVER = r"""
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("githooks_release_driver", sys.argv[1])
gh = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gh
spec.loader.exec_module(gh)
gh.CONSOLE_ROOT = __import__("pathlib").Path(sys.argv[2])
sys.exit(gh.pre_push(["origin", sys.argv[3]], sys.argv[4]))
"""


def _env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in STRIP}
    env.update(GIT_ENV)
    env.update(extra)
    return env


def _git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True, env=_env()
    ).stdout.strip()


class World:
    def __init__(self, tmp: pathlib.Path) -> None:
        self.tmp = tmp
        self.console = tmp / "console"
        self.console.mkdir()
        _git(self.console, "init", "-q", "-b", "main")
        (self.console / "a.txt").write_text("a\n", encoding="utf-8")
        _git(self.console, "add", "a.txt")
        _git(self.console, "commit", "-q", "-m", "seed")
        self.tree = _git(self.console, "rev-parse", "HEAD^{tree}")
        self.bare = tmp / "tap.git"
        _git(tmp, "init", "-q", "--bare", "-b", "main", str(self.bare))
        self.pusher = tmp / "tap"
        self.pusher.mkdir()
        _git(self.pusher, "init", "-q", "-b", "main")
        _git(self.pusher, "commit", "-q", "--allow-empty", "-m", "formula")
        _git(self.pusher, "remote", "add", "origin", str(self.bare))
        self.oid = _git(self.pusher, "rev-parse", "HEAD")
        self.toplevel = _git(self.pusher, "rev-parse", "--show-toplevel")
        pkg = tmp / "pkg" / "rediacc_ci" / "release"
        pkg.mkdir(parents=True)
        (pkg.parent / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "local.py").write_text(ENTRY, encoding="utf-8")
        self.driver = tmp / "driver.py"
        self.driver.write_text(DRIVER, encoding="utf-8")
        self.n = 0

    def triple(self, ref: str = "refs/heads/main", oid: str | None = None) -> dict:
        return {"toplevel": self.toplevel, "remote_ref": ref, "oid": oid or self.oid}

    def entry_env(self) -> dict:
        return _env(PYTHONPATH=str(self.tmp / "pkg"))

    def run(
        self, *, pushes=None, set_env=True, console=None, tree=None, child=None, **cfg
    ) -> subprocess.CompletedProcess:
        self.n += 1
        console = console or self.console
        stdin = "refs/heads/main %s refs/heads/main %s\n" % (self.oid, ZERO)
        conf = {
            "mode": "push",
            "release_run": str(HOOKS / "release_run.py"),
            "console": str(console),
            "run_id": "t%d-%s" % (self.n, uuid.uuid4().hex[:8]),
            "tree": tree or self.tree,
            "pushes": [self.triple()] if pushes is None else pushes,
            "set_env": set_env,
            "pusher": str(self.pusher),
            "child": child
            or [
                sys.executable,
                str(self.driver),
                str(HOOKS / "githooks.py"),
                str(console),
                str(self.bare),
                stdin,
            ],
            **cfg,
        }
        path = self.tmp / ("cfg-%d.json" % self.n)
        path.write_text(json.dumps(conf), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-m", "rediacc_ci.release.local", str(path)],
            cwd=str(self.tmp),
            capture_output=True,
            text=True,
            env=self.entry_env(),
            check=False,
            timeout=120,
        )


@pytest.fixture
def world(tmp_path: pathlib.Path) -> World:
    if not os.path.exists("/proc/self/stat"):
        pytest.skip("the release-run admission reads /proc; without it nothing is admitted")
    return World(tmp_path)


MAIN_REFUSAL = "this pushes to `main` and is not the fast-forward fallback"


def test_a_listed_triple_is_admitted(world: World) -> None:
    proc = world.run()
    assert proc.returncode == 0, proc.stderr
    assert "admits nothing" not in proc.stderr


def test_the_same_push_without_the_variable_is_refused(world: World) -> None:
    proc = world.run(set_env=False)
    assert proc.returncode == 1
    assert MAIN_REFUSAL in proc.stderr
    assert "admits nothing" not in proc.stderr


def test_a_forged_record_naming_a_live_entry_outside_the_chain_is_refused(world: World) -> None:
    sleeper_cfg = world.tmp / "sleep.json"
    sleeper_cfg.write_text(json.dumps({"mode": "sleep"}), encoding="utf-8")
    sleeper = subprocess.Popen(
        [sys.executable, "-m", "rediacc_ci.release.local", str(sleeper_cfg)],
        cwd=str(world.tmp),
        env=world.entry_env(),
    )
    try:
        # The sibling must be an entry by the time its record is written: python fills /proc/<pid>/cmdline at exec, poll until it shows.
        deadline = time.monotonic() + 10
        while not RR.is_entry_argv(RR.proc_cmdline(sleeper.pid) or []):
            assert time.monotonic() < deadline, "the sleeper never became an entry process"
            time.sleep(0.05)
        proc = world.run(record_pid=sleeper.pid)
    finally:
        sleeper.kill()
        sleeper.wait()
    assert proc.returncode == 1
    assert "not in this hook's parent chain" in proc.stderr
    assert MAIN_REFUSAL in proc.stderr


def test_a_wrong_start_time_is_refused(world: World) -> None:
    proc = world.run(tamper={"pid_start": 1})
    assert proc.returncode == 1
    assert "started at" in proc.stderr
    assert MAIN_REFUSAL in proc.stderr


def test_a_wrong_tree_is_refused(world: World) -> None:
    proc = world.run(tree="1" * 40)
    assert proc.returncode == 1
    assert "HEAD^{tree}" in proc.stderr
    assert MAIN_REFUSAL in proc.stderr


def test_an_unlisted_ref_is_refused(world: World) -> None:
    proc = world.run(pushes=[world.triple(ref="refs/heads/release")])
    assert proc.returncode == 1
    assert MAIN_REFUSAL in proc.stderr


def test_an_unlisted_oid_is_refused(world: World) -> None:
    proc = world.run(pushes=[world.triple(oid="2" * 40)])
    assert proc.returncode == 1
    assert MAIN_REFUSAL in proc.stderr


def test_a_record_outside_the_release_cache_is_refused(world: World) -> None:
    proc = world.run(copy_to=str(world.tmp / "elsewhere.json"))
    assert proc.returncode == 1
    assert "is not under" in proc.stderr
    assert MAIN_REFUSAL in proc.stderr


def test_a_missing_record_file_is_refused(world: World) -> None:
    proc = world.run(named=str(world.console / ".ci/cache/release/run-absent.json"))
    assert proc.returncode == 1
    assert "cannot be read" in proc.stderr


def test_a_real_git_push_through_the_real_hooks(world: World) -> None:
    """End to end: `git push` with core.hooksPath at the real hooks, whose CONSOLE_ROOT is this checkout, so the record lives in its `.ci/cache/release/` (gitignored) and names its real tree; the record is removed by the entry."""
    _git(world.pusher, "config", "core.hooksPath", str(HOOKS))
    real_tree = _git(REPO_ROOT, "rev-parse", "HEAD^{tree}")
    push = ["git", "push", "-q", "origin", "HEAD:refs/heads/main"]
    refused = world.run(console=REPO_ROOT, tree=real_tree, child=push, set_env=False)
    assert refused.returncode != 0
    assert MAIN_REFUSAL in refused.stderr
    admitted = world.run(console=REPO_ROOT, tree=real_tree, child=push)
    assert admitted.returncode == 0, admitted.stderr
    assert _git(world.bare, "rev-parse", "refs/heads/main") == world.oid


def test_only_the_entry_can_write_a_record(tmp_path: pathlib.Path) -> None:
    with pytest.raises(RR.RecordError, match="is not `python3 -m"):
        RR.write_release_run(tmp_path, "x", tree="t", version="v", channel="edge", pushes=[])


@pytest.mark.parametrize(
    ("argv", "want"),
    [
        (["python3", "-m", "rediacc_ci.release.local", "--channel", "edge"], True),
        (["python3", "-m", "rediacc_ci.release.local_gates"], False),
        (["python3", "-c", "-m rediacc_ci.release.local"], False),
        (["bash", "-c", "python3 -m rediacc_ci.release.local"], False),
    ],
)
def test_entry_argv(argv: list[str], want: bool) -> None:
    assert RR.is_entry_argv(argv) is want
