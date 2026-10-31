"""The release-run admission of the git-level `pre-push` (box W1-D of agent/plans/PLAN-local-release.md): `release_run.py` and `githooks._release_admitted`.

A REAL PROCESS CHAIN. Each case runs a fake entry, `python3 -P -s -m rediacc_ci.release.local` with `PYTHONPATH=<console>/.ci` and `PYTHONPYCACHEPREFIX=/dev/null` (the one invocation `release_run.entry_refusal` admits), whose `local.py` is a TRACKED file of a fixture console. It writes its record through `release_run.write_release_run` for its own pid and then starts the hook as its child, so the pid, the `/proc` start time, argv and environment the hook checks are a live process's, never planted values. The hook runs in a driver that points `githooks.CONSOLE_ROOT` at the fixture console, or, end to end, under a real `git push` with `core.hooksPath` at a copy of the real hooks inside the fixture console (or at the real hooks, against the real console, for the planted-module exploit).

FORGED RECORDS. A refused entry cannot get its record past the writer, so for the planted cases the fake entry, like an attacker, writes the record itself (`forge`) after printing the writer's refusal; the reader must then refuse it on its own.

THE SETTLE WAIT. The reader refuses a package changed less than `SETTLE_S` before the entry started, so every fixture console sleeps that long once after it is built.

BOTH DIRECTIONS. A listed push to `main`, which the hook refuses without a release run, is admitted; the same push with the variable unset, a forged record (a live entry that is not this hook's ancestor, a wrong start time), a wrong tree, an unlisted ref, oid or remote, a record outside `.ci/cache/release/`, and every way of running something other than the console's committed entry (a planted module in the cwd or ahead on PYTHONPATH, a script or `-c` ahead of `-m`, no `-P`, no `-s`, no pycache prefix, a denied variable, a dirty, shadowed or swapped-and-restored package) are each refused with today's `main` refusal.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
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
# BASH_ENV: this host's profiler re-execs a bash by its `$0`, which the argv-spoof case sets to the interpreter path.
STRIP = (
    "COMMIT_POLICY_OK",
    "REDIACC_RELEASE_RUN",
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "BASH_ENV",
)


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None, path
    assert spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RR = _load("release_run_under_test", HOOKS / "release_run.py")
MODULE = RR.ENTRY_MODULE


def _system_python() -> str | None:
    """A root-installed interpreter by an absolute path, the only kind `interpreter_refusal` admits; the runner's own `sys.executable` is often a user-owned venv link."""
    for candidate in (os.path.realpath(sys.executable), "/usr/bin/python3"):
        if (
            os.path.isabs(candidate)
            and os.path.exists(candidate)
            and RR.interpreter_refusal(candidate, os.path.realpath(candidate)) == ""
        ):
            return candidate
    return None


PY = _system_python()
ENTRY_ARGV = [PY or "/usr/bin/python3", "-P", "-s", "-m", MODULE]


def _need_py() -> str:
    """PY, or a failed test: the interpreter cases have no meaning without a root-installed python3."""
    if PY is None:
        raise AssertionError("no root-installed python3 here")
    return PY


# The fake entry; its config is the LAST argument, so it runs the same as a module, a script or `-c` code. Mode "sleep" only lives (the forged-pid sibling); mode "push" writes the record and runs the hook as its child.
ENTRY = r"""
import importlib.util, json, os, subprocess, sys, time
cfg = json.load(open(sys.argv[-1]))
for target, text in cfg.get("restore", {}).items():
    open(target, "w").write(text)
if cfg["mode"] == "sleep":
    time.sleep(120)
    sys.exit(0)
spec = importlib.util.spec_from_file_location("rr", cfg["release_run"])
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)
pid = cfg.get("record_pid") or int(os.environ.get("FORGE_PID") or 0) or os.getpid()
try:
    path = rr.write_release_run(cfg["console"], cfg["run_id"], tree=cfg["tree"], version="9.9.9",
                                channel="edge", pushes=cfg["pushes"], pid=pid)
except rr.RecordError as exc:
    if not cfg.get("forge"):
        raise
    sys.stderr.write("writer refused: %s\n" % exc)
    path = os.path.join(cfg["console"], ".ci", "cache", "release", "run-%s.json" % cfg["run_id"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rec = {"pid": pid, "pid_start": rr.proc_start(pid), "cmdline": rr.proc_cmdline(pid), "tree": cfg["tree"],
           "version": "9.9.9", "channel": "edge", "pushes": cfg["pushes"]}
    open(path, "w").write(json.dumps(rec))
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
sys.exit(gh.pre_push([sys.argv[3], sys.argv[4]], sys.argv[5]))
"""


def _env(**extra: str) -> dict:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in STRIP and not k.startswith("PYTHON") and not k.startswith("LD_")
    }
    env.update(GIT_ENV)
    env.update(extra)
    return env


def _git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True, env=_env()
    ).stdout.strip()


def _plant(folder: pathlib.Path) -> pathlib.Path:
    """`rediacc_ci/release/local.py` (the fake entry) as a package under `folder`; returns `folder`."""
    pkg = folder / "rediacc_ci" / "release"
    pkg.mkdir(parents=True)
    (pkg.parent / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "local.py").write_text(ENTRY, encoding="utf-8")
    return folder


def _make_console(
    root: pathlib.Path,
    *,
    with_hooks: bool = False,
    symlink_entry: bool = False,
    outside_link: pathlib.Path | None = None,
) -> pathlib.Path:
    """A console checkout whose committed `.ci/rediacc_ci/release/local.py` is the fake entry; `with_hooks` also commits a copy of the real git hooks, so a `core.hooksPath` there makes this the hooks' CONSOLE_ROOT; `symlink_entry` commits `local.py` as a symlink to the entry beside it; `outside_link` commits `release/tag.py` as a symlink to that file outside the tree. Sleeps out `SETTLE_S`."""
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n.ci/cache/\n", encoding="utf-8")
    _plant(root / ".ci")
    if symlink_entry:
        local = root / ".ci/rediacc_ci/release/local.py"
        local.rename(local.with_name("real_local.py"))
        local.symlink_to("real_local.py")
    if outside_link is not None:
        (root / ".ci/rediacc_ci/release/tag.py").symlink_to(outside_link)
    if with_hooks:
        hooks = root / ".claude" / "rediacc_hooks"
        shutil.copytree(HOOKS, hooks / "git", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(HOOKS.parent / "commit_policy.py", hooks / "commit_policy.py")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")
    time.sleep(RR.SETTLE_S + 0.3)
    return root


class World:
    def __init__(self, tmp: pathlib.Path, console: pathlib.Path) -> None:
        self.tmp = tmp
        self.console = console
        self.tree = _git(console, "rev-parse", "HEAD^{tree}")
        self.bare = tmp / "tap.git"
        _git(tmp, "init", "-q", "--bare", "-b", "main", str(self.bare))
        self.pusher = tmp / "tap"
        self.pusher.mkdir()
        _git(self.pusher, "init", "-q", "-b", "main")
        _git(self.pusher, "commit", "-q", "--allow-empty", "-m", "formula")
        _git(self.pusher, "remote", "add", "origin", str(self.bare))
        self.oid = _git(self.pusher, "rev-parse", "HEAD")
        self.toplevel = _git(self.pusher, "rev-parse", "--show-toplevel")
        self.driver = tmp / "driver.py"
        self.driver.write_text(DRIVER, encoding="utf-8")
        self.n = 0

    def triple(
        self, ref: str = "refs/heads/main", oid: str | None = None, remote: str = "origin"
    ) -> dict:
        return {
            "toplevel": self.toplevel,
            "remote": remote,
            "remote_ref": ref,
            "oid": oid or self.oid,
        }

    def entry_env(self, console: pathlib.Path | None = None) -> dict:
        return _env(
            PYTHONPATH=str((console or self.console) / ".ci"),
            PYTHONPYCACHEPREFIX=RR.PYCACHE_PREFIX,
        )

    def run(
        self,
        *,
        pushes=None,
        set_env=True,
        console=None,
        tree=None,
        child=None,
        remote="origin",
        argv=None,
        cwd=None,
        env=None,
        release_run=None,
        executable=None,
        script=None,
        stdin=None,
        **cfg,
    ) -> subprocess.CompletedProcess:
        self.n += 1
        console = console or self.console
        _settle(console)
        stdin = stdin or "refs/heads/main %s refs/heads/main %s\n" % (self.oid, ZERO)
        conf = {
            "mode": "push",
            "release_run": str(release_run or HOOKS / "release_run.py"),
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
                remote,
                str(self.bare),
                stdin,
            ],
            **cfg,
        }
        path = self.tmp / ("cfg-%d.json" % self.n)
        path.write_text(json.dumps(conf), encoding="utf-8")
        return subprocess.run(
            [*(argv or ENTRY_ARGV), str(path)],
            executable=executable,
            input=script,
            cwd=str(cwd or self.tmp),
            capture_output=True,
            text=True,
            env=env or self.entry_env(console),
            check=False,
            timeout=120,
        )


def _need_proc() -> None:
    if not os.path.exists(RR.PROCFS_ROOT + "/self/stat"):
        pytest.skip("the release-run admission reads /proc; without it nothing is admitted")
    if PY is None:
        pytest.fail(
            "no root-installed python3 here (tried the runner's %s and /usr/bin/python3), so the admitted direction cannot be exercised; install the system python3"
            % sys.executable
        )


def _settle(console: pathlib.Path) -> None:
    """Sleep until nothing under the console's `.ci/rediacc_ci` changed within `SETTLE_S`, by the ctime the reader judges. The shared console outlives one test, and under a loaded full run a directory there changed 0.27 s before the next entry started (ci:quick 2026-10-31, three times)."""
    pkg = console / ".ci" / "rediacc_ci"
    if not pkg.is_dir():
        return
    newest = 0.0
    for folder, dirs, files in os.walk(pkg):
        for name in [".", *dirs, *files]:
            try:
                newest = max(newest, os.lstat(os.path.join(folder, name)).st_ctime)
            except FileNotFoundError:
                continue
    wait = newest + RR.SETTLE_S + 0.2 - time.time()
    if wait > 0:
        time.sleep(wait)


@pytest.fixture(scope="module")
def shared_console(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    _need_proc()
    return _make_console(tmp_path_factory.mktemp("shared") / "console")


@pytest.fixture
def world(tmp_path: pathlib.Path, shared_console: pathlib.Path) -> World:
    return World(tmp_path, shared_console)


@pytest.fixture
def fresh_world(tmp_path: pathlib.Path) -> World:
    """A world with its own console, for the cases that dirty the package."""
    _need_proc()
    return World(tmp_path, _make_console(tmp_path / "console"))


MAIN_REFUSAL = "this pushes to `main` and is not the fast-forward fallback"
NOT_ENTRY = "is not the console's release entry"


def _refused(proc: subprocess.CompletedProcess, reason: str) -> None:
    assert proc.returncode == 1, (proc.returncode, proc.stderr)
    assert reason in proc.stderr, proc.stderr
    assert MAIN_REFUSAL in proc.stderr, proc.stderr


def test_a_listed_key_is_admitted(world: World) -> None:
    proc = world.run()
    assert proc.returncode == 0, proc.stderr
    assert "admits nothing" not in proc.stderr
    assert "does not list" not in proc.stderr


def test_the_same_push_without_the_variable_is_refused(world: World) -> None:
    proc = world.run(set_env=False)
    _refused(proc, MAIN_REFUSAL)
    assert "admits nothing" not in proc.stderr
    assert "does not list" not in proc.stderr


def test_a_forged_record_naming_a_live_entry_outside_the_chain_is_refused(world: World) -> None:
    sleeper_cfg = world.tmp / "sleep.json"
    sleeper_cfg.write_text(json.dumps({"mode": "sleep"}), encoding="utf-8")
    sleeper = subprocess.Popen(
        [*ENTRY_ARGV, str(sleeper_cfg)], cwd=str(world.tmp), env=world.entry_env()
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
    _refused(proc, "not in this hook's parent chain")


def test_a_wrong_start_time_is_refused(world: World) -> None:
    _refused(world.run(tamper={"pid_start": 1}), "started at")


def test_a_wrong_tree_is_refused(world: World) -> None:
    _refused(world.run(tree="1" * 40), "HEAD^{tree}")


def test_an_unlisted_ref_is_refused_and_named(world: World) -> None:
    proc = world.run(pushes=[world.triple(ref="refs/heads/release")])
    _refused(proc, "does not list (%s, origin, refs/heads/main, %s)" % (world.toplevel, world.oid))


def test_an_unlisted_oid_is_refused_and_named(world: World) -> None:
    proc = world.run(pushes=[world.triple(oid="2" * 40)])
    _refused(proc, "does not list (%s, origin, refs/heads/main, %s)" % (world.toplevel, world.oid))


def test_a_listed_oid_pushed_to_another_remote_is_refused(world: World) -> None:
    proc = world.run(remote="elsewhere")
    _refused(
        proc, "does not list (%s, elsewhere, refs/heads/main, %s)" % (world.toplevel, world.oid)
    )


def test_a_record_outside_the_release_cache_is_refused(world: World) -> None:
    _refused(world.run(copy_to=str(world.tmp / "elsewhere.json")), "is not under")


def test_a_missing_record_file_is_refused(world: World) -> None:
    proc = world.run(named=str(world.console / ".ci/cache/release/run-absent.json"))
    _refused(proc, "cannot be read")


# Review finding 875b0384.1: the module that ran must be the console's tracked file.


def test_a_planted_module_in_the_cwd_is_refused(world: World) -> None:
    plant = _plant(world.tmp / "plant")
    proc = world.run(argv=[ENTRY_ARGV[0], "-s", "-m", MODULE], cwd=plant, forge=True)
    assert "writer refused" in proc.stderr
    _refused(proc, "runs without -P")


def test_a_planted_module_ahead_on_pythonpath_is_refused(world: World) -> None:
    plant = _plant(world.tmp / "plant")
    env = world.entry_env()
    env["PYTHONPATH"] = "%s%s%s" % (plant, os.pathsep, env["PYTHONPATH"])
    proc = world.run(env=env, forge=True)
    assert "writer refused" in proc.stderr
    _refused(proc, "first PYTHONPATH entry")


def test_a_script_ahead_of_the_module_words_is_refused(world: World) -> None:
    script = world.tmp / "evil.py"
    script.write_text(ENTRY, encoding="utf-8")
    proc = world.run(argv=[ENTRY_ARGV[0], "-P", "-s", str(script), "-m", MODULE], forge=True)
    _refused(proc, "is not `python3")


def test_code_ahead_of_the_module_words_is_refused(world: World) -> None:
    proc = world.run(argv=[ENTRY_ARGV[0], "-c", ENTRY, "-m", MODULE], forge=True)
    _refused(proc, "is not `python3")


def test_no_user_site_guard_is_refused(world: World) -> None:
    proc = world.run(argv=[ENTRY_ARGV[0], "-P", "-m", MODULE], forge=True)
    _refused(proc, "runs without -s")


def test_a_readable_pycache_is_refused(world: World) -> None:
    env = world.entry_env()
    del env["PYTHONPYCACHEPREFIX"]
    _refused(world.run(env=env, forge=True), "PYTHONPYCACHEPREFIX")


def test_a_denied_python_variable_is_refused(world: World) -> None:
    env = world.entry_env()
    env["PYTHONWARNINGS"] = "default"
    _refused(world.run(env=env, forge=True), "PYTHONWARNINGS set")


def test_a_dirty_entry_file_is_refused(fresh_world: World) -> None:
    local = fresh_world.console / ".ci/rediacc_ci/release/local.py"
    local.write_text(ENTRY + "\n# planted\n", encoding="utf-8")
    proc = fresh_world.run(forge=True)
    assert "writer refused" in proc.stderr
    _refused(proc, "is not HEAD's")


def test_an_untracked_module_in_the_package_is_refused(fresh_world: World) -> None:
    (fresh_world.console / ".ci/rediacc_ci/release/tag.py").write_text("", encoding="utf-8")
    _refused(fresh_world.run(forge=True), "is not HEAD's")


def test_a_package_swapped_for_the_start_and_restored_is_refused(fresh_world: World) -> None:
    local = fresh_world.console / ".ci/rediacc_ci/release/local.py"
    local.write_text(ENTRY + "\n# planted\n", encoding="utf-8")
    proc = fresh_world.run(forge=True, restore={str(local): ENTRY})
    assert local.read_text(encoding="utf-8") == ENTRY
    _refused(proc, "after the entry started")


def test_a_committed_symlink_entry_is_refused(tmp_path: pathlib.Path) -> None:
    _need_proc()
    world = World(tmp_path, _make_console(tmp_path / "console", symlink_entry=True))
    _refused(world.run(forge=True), "is not a tracked regular file")


def test_a_committed_symlink_to_outside_the_tree_is_refused(tmp_path: pathlib.Path) -> None:
    """Review finding a6188f8e.2: git sees the link text, never the target, so a rewritten target is invisible to the status check."""
    _need_proc()
    outside = tmp_path / "outside.py"
    outside.write_text("", encoding="utf-8")
    world = World(tmp_path, _make_console(tmp_path / "console", outside_link=outside))
    _refused(world.run(forge=True), "release/tag.py is a symlink")


# Review finding a6188f8e.1: argv is the caller's to choose, the executable is not.


def test_an_entry_shaped_argv_on_another_binary_is_refused(world: World) -> None:
    """`bash` (root-owned) started with argv `python3 -P -s -m rediacc_ci.release.local <cfg>`, the `exec -a` trick, reading its script from stdin: it has a child write a record naming the bash pid by hand and run the hook. Only the executable gives it away."""
    script = world.tmp / "evil.py"
    script.write_text(ENTRY, encoding="utf-8")
    bash = os.path.realpath(shutil.which("bash") or "/bin/bash")
    proc = world.run(
        executable=bash,
        script='FORGE_PID=$$ "%s" "%s" "${@: -1}"\n' % (sys.executable, script),
        forge=True,
    )
    _refused(proc, "is not a Python interpreter")


def test_a_copied_interpreter_is_refused(world: World) -> None:
    copy = world.tmp / "bin" / "python3"
    copy.parent.mkdir()
    shutil.copy2(os.path.realpath(ENTRY_ARGV[0]), copy)
    proc = world.run(argv=[str(copy), *ENTRY_ARGV[1:]], forge=True)
    assert "writer refused" in proc.stderr, proc.stderr
    _refused(proc, "is not root-owned")


def test_a_user_writable_venv_is_refused(world: World) -> None:
    """The venv's `python` links to the root-owned interpreter, so `/proc/<pid>/exe` is clean; its own directory is not, and its site-packages run `.pth` files whatever `-s` says."""
    venv = world.tmp / "venv"
    subprocess.run(
        [ENTRY_ARGV[0], "-m", "venv", "--without-pip", str(venv)], check=True, env=_env()
    )
    python = venv / "bin" / "python3"
    proc = world.run(argv=[str(python), *ENTRY_ARGV[1:]], forge=True)
    _refused(proc, "is not root-owned")


def test_a_symlinked_directory_into_a_writable_dir_is_refused(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review 120e8ea7.1: `argv0` passes through a symlink into a writable directory, and a second link there leads back to the interpreter's root-owned directory. Python reads `pyvenv.cfg` one level above the typed path, inside the writable directory.

    `/proc/self/cwd` is the root-owned-looking symlink: `/proc` is root's, `self` and `cwd` are links, so the typed path crosses no unlinked user directory and the old check, which skipped every link and resolved only `dirname(argv0)`, admitted it."""
    py = _need_py()
    real = os.path.realpath(py)
    writable = tmp_path / "w"
    writable.mkdir()
    writable.chmod(0o777)
    (writable / "d").symlink_to(os.path.dirname(real))
    monkeypatch.chdir(writable)
    argv0 = "%s/self/cwd/d/%s" % (RR.PROCFS_ROOT, os.path.basename(real))
    assert os.path.realpath(argv0) == real, "the planted path must resolve to the interpreter"
    got = RR.interpreter_refusal(argv0, real)
    assert "is not root-owned" in got, got
    assert str(writable) in got, got
    assert "the target of %s/self/cwd" % RR.PROCFS_ROOT in got, got


def test_an_interpreter_found_on_path_is_refused(world: World) -> None:
    proc = world.run(argv=["python3", *ENTRY_ARGV[1:]], executable=ENTRY_ARGV[0], forge=True)
    _refused(proc, "not by an absolute interpreter path")


@pytest.mark.parametrize(
    ("argv0", "exe", "want"),
    [
        ("{py}", "{py}", ""),
        ("python3", "{py}", "not by an absolute interpreter path"),
        ("/bin/bash", "/usr/bin/bash", "is not a Python interpreter"),
        ("{py}", "{py} (deleted)", "is not a file on disk"),
        ("/usr/bin/python3-fake", "{py}", "does not resolve to its executable"),
    ],
)
def test_interpreter_refusal(argv0: str, exe: str, want: str) -> None:
    py = _need_py()
    real = os.path.realpath(py)
    got = RR.interpreter_refusal(argv0.replace("{py}", py), exe.replace("{py}", real))
    if want:
        assert want in got
    else:
        assert got == ""


def test_a_tag_push_beside_a_listed_main_prints_no_release_noise(world: World) -> None:
    """Review finding a6188f8e.3: a tag the rules admit anyway is unlisted, and says nothing about it."""
    stdin = "refs/heads/main %s refs/heads/main %s\nrefs/tags/v9 %s refs/tags/v9 %s\n" % (
        world.oid,
        ZERO,
        world.oid,
        ZERO,
    )
    proc = world.run(stdin=stdin)
    assert proc.returncode == 0, proc.stderr
    assert "release run" not in proc.stderr, proc.stderr


def test_a_tag_only_push_prints_no_release_noise(world: World) -> None:
    stdin = "refs/tags/v9 %s refs/tags/v9 %s\n" % (world.oid, ZERO)
    proc = world.run(stdin=stdin)
    assert proc.returncode == 0, proc.stderr
    assert "release run" not in proc.stderr, proc.stderr


def test_a_real_git_push_through_the_real_hooks(tmp_path: pathlib.Path) -> None:
    """End to end: `git push` with core.hooksPath at a committed copy of the real hooks inside a fixture console, so that console is their CONSOLE_ROOT and its tracked fake entry is the entry."""
    _need_proc()
    console = _make_console(tmp_path / "console", with_hooks=True)
    world = World(tmp_path, console)
    hooks = console / ".claude" / "rediacc_hooks" / "git"
    _git(world.pusher, "config", "core.hooksPath", str(hooks))
    push = ["git", "push", "-q", "origin", "HEAD:refs/heads/main"]
    rr_path = hooks / "release_run.py"
    refused = world.run(child=push, set_env=False, release_run=rr_path)
    assert refused.returncode != 0
    assert MAIN_REFUSAL in refused.stderr
    admitted = world.run(child=push, release_run=rr_path)
    assert admitted.returncode == 0, admitted.stderr
    assert _git(world.bare, "rev-parse", "refs/heads/main") == world.oid


def test_the_planted_module_exploit_against_the_real_console(tmp_path: pathlib.Path) -> None:
    """Review finding 875b0384.1 as written: a planted `rediacc_ci/release/local.py` run by `python3 -m` from its own directory, PYTHONPATH at the real console's `.ci`, the real HEAD tree, a real `git push` through the real hooks. It must not reach `main`."""
    _need_proc()
    world = World(tmp_path, REPO_ROOT)
    _git(world.pusher, "config", "core.hooksPath", str(HOOKS))
    plant = _plant(tmp_path / "plant")
    push = ["git", "push", "-q", "origin", "HEAD:refs/heads/main"]
    proc = world.run(
        argv=[ENTRY_ARGV[0], "-m", MODULE],
        cwd=plant,
        tree=_git(REPO_ROOT, "rev-parse", "HEAD^{tree}"),
        child=push,
        forge=True,
    )
    assert proc.returncode != 0, proc.stderr
    assert NOT_ENTRY in proc.stderr
    assert MAIN_REFUSAL in proc.stderr
    assert (
        subprocess.run(
            ["git", "-C", str(world.bare), "rev-parse", "--verify", "-q", "refs/heads/main"],
            capture_output=True,
            env=_env(),
            check=False,
        ).returncode
        != 0
    ), "the planted entry pushed main"


def test_only_the_entry_can_write_a_record(tmp_path: pathlib.Path) -> None:
    with pytest.raises(RR.RecordError, match=NOT_ENTRY):
        RR.write_release_run(tmp_path, "x", tree="t", version="v", channel="edge", pushes=[])


@pytest.mark.parametrize(
    ("argv", "want"),
    [
        (["python3", "-m", MODULE, "--channel", "edge"], True),
        (["python3", "-P", "-s", "-B", "-u", "-m", MODULE], True),
        (["python3", "-m", "rediacc_ci.release.local_gates"], False),
        (["python3", "-c", "-m rediacc_ci.release.local"], False),
        (["python3", "-c", "code", "-m", MODULE], False),
        (["python3", "evil.py", "-m", MODULE], False),
        (["python3", "-X", "dev", "-m", MODULE], False),
        (["python3", "-Ps", "-m", MODULE], False),
        (["bash", "-c", "python3 -m rediacc_ci.release.local"], False),
    ],
)
def test_entry_argv(argv: list[str], want: bool) -> None:
    assert RR.is_entry_argv(argv) is want


GOOD_ARGV = ["python3", "-P", "-s", "-m", MODULE]


def _good_environ(console: pathlib.Path) -> dict:
    return {
        "PYTHONPATH": str(console / ".ci"),
        "PYTHONPYCACHEPREFIX": RR.PYCACHE_PREFIX,
        "HOME": "/h",
    }


@pytest.mark.parametrize(
    ("argv", "change", "want"),
    [
        (GOOD_ARGV, {}, ""),
        (["python3", "-m", MODULE], {"PYTHONSAFEPATH": "1", "PYTHONNOUSERSITE": "1"}, ""),
        (GOOD_ARGV, {"PYTHONUNBUFFERED": "1", "PYTHONHASHSEED": "0"}, ""),
        (["python3", "-s", "-m", MODULE], {}, "without -P"),
        (["python3", "-P", "-m", MODULE], {}, "without -s"),
        (GOOD_ARGV, {"PYTHONPYCACHEPREFIX": None}, "PYTHONPYCACHEPREFIX"),
        (GOOD_ARGV, {"PYTHONPYCACHEPREFIX": "/tmp/pyc"}, "PYTHONPYCACHEPREFIX"),
        (GOOD_ARGV, {"PYTHONHOME": "/x"}, "PYTHONHOME set"),
        (GOOD_ARGV, {"LD_PRELOAD": "/x.so"}, "LD_PRELOAD set"),
        (GOOD_ARGV, {"PYTHONPATH": None}, "first PYTHONPATH entry"),
        (GOOD_ARGV, {"PYTHONPATH": ":{ci}"}, "first PYTHONPATH entry"),
        (GOOD_ARGV, {"PYTHONPATH": "/elsewhere:{ci}"}, "first PYTHONPATH entry"),
        (GOOD_ARGV, {"PYTHONPATH": ".ci"}, "first PYTHONPATH entry"),
    ],
)
def test_invocation_refusal(
    tmp_path: pathlib.Path, argv: list[str], change: dict, want: str
) -> None:
    (tmp_path / ".ci").mkdir()
    environ = _good_environ(tmp_path)
    for key, value in change.items():
        if value is None:
            environ.pop(key, None)
        else:
            environ[key] = value.replace("{ci}", str(tmp_path / ".ci"))
    got = RR.invocation_refusal(tmp_path, argv, environ)
    if want:
        assert want in got
    else:
        assert got == ""


def test_invocation_refusal_resolves_a_symlinked_ci(tmp_path: pathlib.Path) -> None:
    """A `.ci` that is a symlink resolves elsewhere, so the package that ran is not the console's own."""
    (tmp_path / "other").mkdir()
    (tmp_path / ".ci").symlink_to(tmp_path / "other")
    got = RR.invocation_refusal(tmp_path, GOOD_ARGV, _good_environ(tmp_path))
    assert "first PYTHONPATH entry" in got


def test_a_procfs_override_that_is_not_root_locked_is_ignored(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seam moves the procfs root only to a root-owned, write-closed directory: a caller-chosen one would let it forge the process table the admission trusts, so it is ignored and the default answers. A non-absolute and an empty value are ignored the same way."""
    default = RR._procfs_root({})
    fake = tmp_path / "fakeproc"
    fake.mkdir()
    assert RR._procfs_root({RR.PROCFS_ENV: str(fake)}) == default
    assert RR._procfs_root({RR.PROCFS_ENV: "relative/procfs"}) == default
    assert RR._procfs_root({RR.PROCFS_ENV: ""}) == default
    # the other direction: a directory the lock check accepts is honoured. The check is stubbed for one directory, so this runs on every host (no dependence on /usr being root-owned and closed) and does not reuse the predicate to choose its own input.
    real = RR._locked_refusal
    monkeypatch.setattr(RR, "_locked_refusal", lambda p: "" if p == str(fake) else real(p))
    assert RR._procfs_root({RR.PROCFS_ENV: str(fake) + "/"}) == str(fake)
    assert RR._procfs_root({RR.PROCFS_ENV: str(tmp_path)}) == default
