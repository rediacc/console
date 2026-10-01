"""`rediacc_ci.dev.worktree` against `scripts/dev/worktree.sh`, in throwaway repositories.

NOTHING HERE TOUCHES A REAL CHECKOUT. Each case builds its own fixture under pytest's `tmp_path`: a bare `origin.git`, a bare `sub.git` for a submodule, and a clone of origin that carries copies of `worktree.sh` and `common.sh`. The bash derives its root from where its copy sits and the port from `$REDIACC_CI_ROOT`, so both act on the fixture and on nothing else. `tmux`, `gh`, `docker`, `sudo` and `git` are shims first on PATH: the first four so no real session, PR lookup, container or privilege is ever reached, `git` so every call is recorded (and passed through to the real binary) and "never stashed, never checked out" is asserted from the log and not from the end state alone.

Two kinds of case:

  DIFFERENTIAL (`test_same_*`). The bash and the port run over identically built fixtures; exit code, stdout, stderr (fixture path masked) and the resulting repository state must match. These are the behaviours the bash gets right.

  DELTA (`test_delta_*`). One per deliberate difference listed in the port's module docstring (D1 to D12), and the INCIDENT case of 2026-10-01 (`./run.sh worktree prune --help` ran a real prune). Each asserts what the port does and, while `worktree.sh` exists, that the bash does the opposite, so the case provably fails on the bash behaviour. When the bash is deleted (PLAN-retire-bash-oracles B3) the `bash_*` halves go with it.

`git worktree add` is what the create cases run, inside the fixtures only. The guard that blocks it (`block_worktree_add.py`) matches the text of an agent's Bash command, and these cases are test code run by pytest in CI.
"""

from __future__ import annotations

import re
import shutil
import stat
import subprocess
import sys
import time
from typing import TYPE_CHECKING, NamedTuple

import pytest

from rediacc_ci import paths

if TYPE_CHECKING:
    from pathlib import Path

REPO = paths.repo_root()
BASH_SCRIPT = REPO / "scripts" / "dev" / "worktree.sh"
COMMON_SH = REPO / ".ci" / "scripts" / "lib" / "common.sh"
CI_DIR = REPO / ".ci"
REAL_GIT = shutil.which("git") or "/usr/bin/git"
SYSTEM_PATH = "/usr/bin:/bin"
TODAY = time.strftime("%m%d")

needs_bash = pytest.mark.skipif(not BASH_SCRIPT.is_file(), reason="worktree.sh is retired")

GIT_SHIM = (
    f'#!/bin/bash\necho "git TP=${{GIT_TERMINAL_PROMPT-}} $*" >>"$CALLS"\nexec {REAL_GIT} "$@"\n'
)
TMUX_SHIM = """#!/bin/bash
echo "tmux $*" >>"$CALLS"
case "$1" in
  has-session) [ -e "$TMUXDIR/$3" ] ;;
  new-session) touch "$TMUXDIR/$4" ;;
  kill-session) rm -f "$TMUXDIR/$3" ;;
  *) exit 0 ;;
esac
"""
GH_SHIM = """#!/bin/bash
echo "gh $*" >>"$CALLS"
branch="" json=""
while [ $# -gt 0 ]; do
  case "$1" in --head) branch="$2"; shift ;; --json) json="$2"; shift ;; esac
  shift
done
merged=false stale=false
grep -qx "$branch" "$GH_MERGED" 2>/dev/null && merged=true
grep -qx "$branch" "$GH_STALE" 2>/dev/null && stale=true
if [ "$json" = state ]; then
  { $merged || $stale; } && echo MERGED
elif [ "$json" = headRefOid ]; then
  $merged && /usr/bin/git -C "$FX_ROOT" rev-parse "refs/heads/$branch"
  $stale && echo deadbeefdeadbeefdeadbeefdeadbeefdeadbeef
fi
exit 0
"""
DOCKER_SHIM = (
    '#!/bin/bash\necho "docker $*" >>"$CALLS"\n[ "$1" = info ] && exit "${DOCKER_RC:-1}"\nexit 0\n'
)
SUDO_SHIM = '#!/bin/bash\necho "sudo $*" >>"$CALLS"\nexit 0\n'
RUN_SH = """#!/bin/bash
echo "run.sh CONSOLE_ROOT_DIR=${CONSOLE_ROOT_DIR-} $*" >>"$CALLS"
[ "$1 $2" = "devbox url" ] && echo "https://devbox.test/x"
[ "$1 $2" = "devbox remove" ] && exit "${DEVBOX_REMOVE_RC:-0}"
exit 0
"""


class Result(NamedTuple):
    rc: int
    out: str
    err: str


class Fixture:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.root = base / "console"
        self.origin = base / "origin.git"
        self.sub = base / "sub.git"
        self.calls = base / "calls"
        self.tmuxdir = base / "tmuxstate"
        self.shim = base / "shim"
        self.merged = base / "merged"
        self.stale = base / "stale"
        self.home = base / "home"

    def env(self, **extra: str) -> dict[str, str]:
        env = {
            "PATH": f"{self.shim}:{SYSTEM_PATH}",
            "HOME": str(self.home),
            "CALLS": str(self.calls),
            "TMUXDIR": str(self.tmuxdir),
            "GH_MERGED": str(self.merged),
            "GH_STALE": str(self.stale),
            "FX_ROOT": str(self.root),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "protocol.file.allow",
            "GIT_CONFIG_VALUE_0": "always",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.test",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.test",
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
            "NO_COLOR": "1",
            "LC_ALL": "C",
        }
        env.update(extra)
        return env

    def git(self, *args: str, cwd: Path | None = None, check: bool = True) -> str:
        proc = subprocess.run(
            [REAL_GIT, *args],
            cwd=str(cwd or self.root),
            env=self.env(),
            capture_output=True,
            text=True,
            check=False,
        )
        if check and proc.returncode != 0:
            raise AssertionError("git %s failed: %s" % (" ".join(args), proc.stderr))
        return proc.stdout

    def commit(
        self, name: str, text: str = "x\n", cwd: Path | None = None, message: str | None = None
    ) -> None:
        where = cwd or self.root
        (where / name).write_text(text, encoding="utf-8")
        self.git("add", "--", name, cwd=where)
        self.git("commit", "-q", "-m", message or name, cwd=where)

    def run_bash(self, args: list[str], *, cwd: Path | str | None = None, **extra: str) -> Result:
        return self._run(
            ["bash", str(self.root / "scripts" / "dev" / "worktree.sh"), *args], cwd, extra
        )

    def run_port(self, args: list[str], *, cwd: Path | str | None = None, **extra: str) -> Result:
        code = (
            "import sys; from rediacc_ci.dev import worktree; sys.exit(worktree.main(sys.argv[1:]))"
        )
        return self._run(
            [sys.executable, "-c", code, *args],
            cwd,
            {"PYTHONPATH": str(CI_DIR), "REDIACC_CI_ROOT": str(self.root), **extra},
        )

    def _run(self, argv: list[str], cwd: Path | str | None, extra: dict[str, str]) -> Result:
        proc = subprocess.run(
            argv,
            cwd=str(cwd or self.root),
            env=self.env(**extra),
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
            stdin=subprocess.DEVNULL,
        )
        return Result(proc.returncode, self.mask(proc.stdout), self.mask(proc.stderr))

    def mask(self, text: str) -> str:
        """Paths and abbreviated shas: the two fixtures hold different `.gitmodules` URLs, so their commit ids differ though everything observable is the same."""
        text = text.replace(str(self.root), "<ROOT>").replace(str(self.base), "<BASE>")
        return re.sub(r"\b[0-9a-f]{7,40}\b", "<sha>", text)

    def call_log(self, *tools: str) -> list[str]:
        if not self.calls.exists():
            return []
        lines = self.calls.read_text(encoding="utf-8").splitlines()
        return [self.mask(line) for line in lines if line.split(" ", 1)[0] in tools]

    def forget_calls(self) -> None:
        self.calls.write_text("", encoding="utf-8")

    def branches(self) -> list[str]:
        return sorted(self.git("branch", "--format=%(refname:short)").split())

    def state(self) -> dict[str, object]:
        wts = [
            self.mask(w)
            for w in self.git("worktree", "list", "--porcelain").splitlines()
            if w.startswith("worktree ")
        ]
        wtdir = self.root / ".worktrees"
        return {
            "branch": self.git("rev-parse", "--abbrev-ref", "HEAD").strip(),
            "branches": sorted(self.git("branch", "--format=%(refname:short)").split()),
            "worktrees": wts,
            "stash": self.git("stash", "list").splitlines(),
            "status": self.git("status", "--porcelain").splitlines(),
            "dirs": sorted(p.name for p in wtdir.iterdir()) if wtdir.is_dir() else [],
        }


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _noop(_fx: Fixture) -> None:
    """No setup: the fixture as built."""


def make_fixture(tmp_path: Path, name: str = "fx") -> Fixture:
    fx = Fixture((tmp_path / name).resolve())
    fx.base.mkdir(parents=True)
    fx.home.mkdir()
    fx.tmuxdir.mkdir()
    fx.shim.mkdir()
    fx.calls.write_text("", encoding="utf-8")
    fx.merged.write_text("", encoding="utf-8")
    fx.stale.write_text("", encoding="utf-8")
    for tool, body in (
        ("git", GIT_SHIM),
        ("tmux", TMUX_SHIM),
        ("gh", GH_SHIM),
        ("docker", DOCKER_SHIM),
        ("sudo", SUDO_SHIM),
    ):
        _write_exec(fx.shim / tool, body)

    for bare in (fx.origin, fx.sub):
        fx.git("init", "-q", "--bare", "-b", "main", str(bare), cwd=fx.base)
    seed = fx.base / "subseed"
    fx.git("clone", "-q", str(fx.sub), str(seed), cwd=fx.base)
    fx.commit("lib.txt", cwd=seed)
    fx.git("branch", "-M", "main", cwd=seed)
    fx.git("push", "-q", "origin", "main", cwd=seed)

    fx.git("clone", "-q", str(fx.origin), str(fx.root), cwd=fx.base)
    fx.git("checkout", "-q", "-b", "main")
    (fx.root / "scripts" / "dev").mkdir(parents=True)
    (fx.root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    if BASH_SCRIPT.is_file():
        shutil.copy(BASH_SCRIPT, fx.root / "scripts" / "dev" / "worktree.sh")
    shutil.copy(COMMON_SH, fx.root / ".ci" / "scripts" / "lib" / "common.sh")
    (fx.root / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        REPO / ".ci" / "config" / "well-known.env", fx.root / ".ci" / "config" / "well-known.env"
    )
    fx.git("submodule", "add", "-q", str(fx.sub), "private/sub")
    (fx.root / ".gitignore").write_text(".worktrees/\n", encoding="utf-8")
    fx.git("add", "--", ".gitignore", "scripts", ".ci")
    fx.git("commit", "-q", "-m", "seed")
    fx.git("push", "-q", "origin", "main")
    fx.git("branch", "-q", "--set-upstream-to=origin/main", "main")
    fx.forget_calls()
    return fx


def add_worktree(fx: Fixture, name: str, branch: str | None = None) -> Path:
    path = fx.root / ".worktrees" / name
    fx.git("worktree", "add", "-q", "-b", branch or name, str(path), "origin/main")
    fx.forget_calls()
    return path


def commit_run_sh(fx: Fixture) -> None:
    """A tracked `run.sh` stub, so the checkout stays clean and the sync still runs."""
    _write_exec(fx.root / "run.sh", RUN_SH)
    fx.git("add", "--", "run.sh")
    fx.git("commit", "-q", "-m", "run.sh stub")
    fx.git("push", "-q", "origin", "main")


def dirty_checkout(fx: Fixture, branch: str = "0930-1") -> None:
    """The shared-checkout shape of the incident: another session's branch, tracked edits and untracked files."""
    fx.git("checkout", "-q", "-b", branch)
    (fx.root / ".gitignore").write_text(".worktrees/\nedited\n", encoding="utf-8")
    for i in range(3):
        (fx.root / f"untracked-{i}.txt").write_text("live work\n", encoding="utf-8")


def diff_pair(
    tmp_path: Path,
    setup,
    args: list[str],
    tools: tuple[str, ...] = ("tmux", "sudo", "run.sh", "docker"),
    **extra: str,
):
    """Run the bash on one fixture and the port on an identically built one."""
    a, b = make_fixture(tmp_path, "bash"), make_fixture(tmp_path, "port")
    for fx in (a, b):
        setup(fx)
        fx.forget_calls()
    ra = a.run_bash(args, **extra)
    rb = b.run_port(args, **extra)
    return a, b, ra, rb, (a.call_log(*tools), b.call_log(*tools))


def assert_same(a: Fixture, b: Fixture, ra: Result, rb: Result, calls) -> None:
    assert rb.rc == ra.rc
    assert rb.err == ra.err
    assert rb.out == ra.out
    sa, sb = a.state(), b.state()
    assert sa == sb
    assert calls[0] == calls[1]


def git_mutations(fx: Fixture) -> list[str]:
    """Every recorded git call that stashes, checks out, resets, pulls or merges the checkout the command runs from (`-C <ROOT>` or no `-C`)."""
    bad = ("stash", "checkout", "reset", "pull", "merge", "switch", "clean", "restore")
    found = []
    for line in fx.call_log("git"):
        rest = line.split()[2:]
        target, command = (rest[1], rest[2:]) if rest[:1] == ["-C"] else ("<ROOT>", rest)
        if target == "<ROOT>" and command and command[0] in bad:
            found.append(line)
    return found


# --------------------------------------------------------------------------- differential: behaviour the bash gets right ---------------------------------------------------------------------------


@needs_bash
@pytest.mark.parametrize("sub", ["create", "switch"])
def test_same_help_of_the_commands_the_bash_already_honoured(tmp_path: Path, sub: str) -> None:
    fx = make_fixture(tmp_path)
    b, p = fx.run_bash([sub, "--help"]), fx.run_port([sub, "--help"])
    assert (p.rc, p.err) == (b.rc, b.err) == (0, "")
    if sub == "create":
        assert p.out == b.out
    else:
        assert p.out.startswith(b.out.rstrip("\n").split("Options:")[0])


@needs_bash
def test_same_unknown_command_is_refused_with_the_same_message_and_code(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    b, p = fx.run_bash(["frobnicate"]), fx.run_port(["frobnicate"])
    assert (p.rc, p.err) == (b.rc, b.err) == (1, "✗ Unknown command: frobnicate\n")
    assert p.out.startswith("\nUsage: ./run.sh worktree <command> [options]")


@needs_bash
def test_same_no_worktrees_and_list_with_one(tmp_path: Path) -> None:
    a, b, ra, rb, calls = diff_pair(tmp_path, _noop, ["list"])
    assert_same(a, b, ra, rb, calls)
    assert "No worktrees found" in rb.err

    def setup(fx: Fixture) -> None:
        add_worktree(fx, "0101-1")

    a, b, ra, rb, calls = diff_pair(tmp_path / "second", setup, ["list"])
    assert_same(a, b, ra, rb, calls)
    assert "0101-1" in rb.out


@needs_bash
@pytest.mark.parametrize("flags", [[], ["--teams"], ["--no-devbox"]])
def test_same_create_on_a_clean_main_checkout(tmp_path: Path, flags: list[str]) -> None:
    a, b, ra, rb, calls = diff_pair(tmp_path, _noop, ["create", *flags], tools=("tmux",))
    assert rb.rc == 0, rb.err
    assert_same(a, b, ra, rb, calls)
    assert f"{TODAY}-1" in b.branches()
    assert (b.root / ".worktrees" / f"{TODAY}-1" / "private" / "sub").is_dir()
    sub_branch = b.git(
        "rev-parse",
        "--abbrev-ref",
        "HEAD",
        cwd=b.root / ".worktrees" / f"{TODAY}-1" / "private" / "sub",
    ).strip()
    assert sub_branch == f"{TODAY}-1"


@needs_bash
def test_same_create_sequence_number_and_existing_branch_refusal(tmp_path: Path) -> None:
    def setup(fx: Fixture) -> None:
        add_worktree(fx, f"{TODAY}-3")

    a, b, ra, rb, calls = diff_pair(tmp_path, setup, ["create", "--no-devbox"], tools=("tmux",))
    assert_same(a, b, ra, rb, calls)
    assert f"{TODAY}-4" in b.branches()

    def clash(fx: Fixture) -> None:
        fx.git("branch", f"{TODAY}-1")

    a, b, ra, rb, calls = diff_pair(tmp_path / "clash", clash, ["create"], tools=("tmux",))
    assert rb.rc == 1
    assert_same(a, b, ra, rb, calls)


@needs_bash
def test_same_create_brings_the_devbox_up_and_prints_its_url(tmp_path: Path) -> None:
    def setup(fx: Fixture) -> None:
        commit_run_sh(fx)

    a, b, ra, rb, calls = diff_pair(
        tmp_path, setup, ["create"], tools=("docker", "run.sh"), DOCKER_RC="0"
    )
    assert "Devbox:  https://devbox.test/x" in rb.out
    assert any("devbox up" in line for line in calls[1])
    assert_same(a, b, ra, rb, calls)


@needs_bash
def test_same_remove_a_clean_worktree_and_the_not_found_refusal(tmp_path: Path) -> None:
    def setup(fx: Fixture) -> None:
        add_worktree(fx, "0101-1")

    a, b, ra, rb, calls = diff_pair(tmp_path, setup, ["remove", "0101-1"])
    assert rb.rc == 0
    assert_same(a, b, ra, rb, calls)
    assert "0101-1" not in b.branches()
    a, b, ra, rb, calls = diff_pair(tmp_path / "gone", setup, ["remove", "9999-9"])
    assert rb.rc == 1
    assert_same(a, b, ra, rb, calls)
    a, b, ra, rb, calls = diff_pair(tmp_path / "noarg", setup, ["remove"])
    assert rb.rc == 1
    assert_same(a, b, ra, rb, calls)


@needs_bash
@pytest.mark.parametrize(("docker_rc", "remove_rc"), [("0", "0"), ("0", "1"), ("1", "1")])
def test_same_devbox_teardown_runs_first_and_a_failed_one_aborts(
    tmp_path: Path, docker_rc: str, remove_rc: str
) -> None:
    def setup(fx: Fixture) -> None:
        add_worktree(fx, "0101-1")
        commit_run_sh(fx)

    a, b, ra, rb, calls = diff_pair(
        tmp_path,
        setup,
        ["remove", "0101-1"],
        tools=("docker", "run.sh", "git"),
        DOCKER_RC=docker_rc,
        DEVBOX_REMOVE_RC=remove_rc,
    )
    log = [line for line in calls[1] if line.startswith("run.sh") or "worktree remove" in line]
    if docker_rc == "0":
        assert log[0].startswith("run.sh CONSOLE_ROOT_DIR=<ROOT>/.worktrees/0101-1 devbox remove")
    if remove_rc == "1" and docker_rc == "0":
        assert rb.rc == 1
        assert not any("worktree remove" in line for line in log)
        assert "0101-1" in b.state()["dirs"]
    keep = [lambda ln: not ln.startswith("git ")]
    assert [x for x in calls[0] if keep[0](x)] == [x for x in calls[1] if keep[0](x)]
    assert (ra.rc, ra.err) == (rb.rc, rb.err)
    assert a.state() == b.state()
    # ORDER: the devbox is stopped before the directory goes, in the port as in the bash.
    for side in calls:
        order = [ln for ln in side if ln.startswith("run.sh") or "worktree remove" in ln]
        if docker_rc == "0":
            assert order[0].startswith("run.sh")


@needs_bash
def test_same_prune_removes_a_merged_pr_worktree_and_an_empty_one(tmp_path: Path) -> None:
    def setup(fx: Fixture) -> None:
        path = add_worktree(fx, "0101-1")
        fx.commit("work.txt", cwd=path)
        fx.merged.write_text("0101-1\n", encoding="utf-8")
        add_worktree(fx, "0101-2")
        keep = add_worktree(fx, "0101-3")
        fx.commit("keep.txt", cwd=keep)

    a, b, ra, rb, calls = diff_pair(tmp_path, setup, ["prune"])
    assert rb.rc == 0, rb.err
    assert_same(a, b, ra, rb, calls)
    assert b.state()["dirs"] == ["0101-3"]


@needs_bash
def test_same_switch_to_a_remote_branch_and_the_refusals(tmp_path: Path) -> None:
    def setup(fx: Fixture) -> None:
        fx.git("checkout", "-q", "-b", "feat")
        fx.commit("feat.txt")
        fx.git("push", "-q", "origin", "feat")
        fx.git("checkout", "-q", "main")
        fx.git("branch", "-q", "-D", "feat")

    a, b, ra, rb, calls = diff_pair(tmp_path, setup, ["switch", "feat"])
    assert rb.rc == 0, rb.err
    assert_same(a, b, ra, rb, calls)
    assert b.state()["branch"] == "feat"
    assert (b.root / "private" / "sub" / ".git").exists()
    for case, args in (
        ("missing", ["switch", "nope"]),
        ("noarg", ["switch"]),
        ("extra", ["switch", "a", "b"]),
        ("opt", ["switch", "--x"]),
    ):
        a, b, ra, rb, calls = diff_pair(tmp_path / case, setup, args)
        assert rb.rc == 1, case
        assert_same(a, b, ra, rb, calls)


@needs_bash
def test_same_switch_refuses_a_tracked_change(tmp_path: Path) -> None:
    def setup(fx: Fixture) -> None:
        fx.git("branch", "other")
        (fx.root / ".gitignore").write_text("changed\n", encoding="utf-8")

    _a, b, _ra, rb, _calls = diff_pair(tmp_path, setup, ["switch", "other"])
    assert rb.rc == 1
    assert "uncommitted" in rb.err
    assert b.state()["branch"] == "main"


@needs_bash
def test_same_switch_fast_forwards_a_branch_that_is_behind_its_remote(tmp_path: Path) -> None:
    def setup(fx: Fixture) -> None:
        fx.git("checkout", "-q", "-b", "feat")
        fx.git("push", "-q", "origin", "feat")
        fx.commit("ahead.txt")
        fx.git("push", "-q", "origin", "feat")
        fx.git("reset", "-q", "--hard", "HEAD~1")
        fx.git("checkout", "-q", "main")

    a, b, ra, rb, calls = diff_pair(tmp_path, setup, ["switch", "feat"])
    assert (b.root / "ahead.txt").exists()
    assert_same(a, b, ra, rb, calls)


# --------------------------------------------------------------------------- the incident ---------------------------------------------------------------------------


@pytest.mark.parametrize("sub", ["prune", "list", "remove", "create", "switch"])
def test_delta_d1_help_is_side_effect_free_for_every_subcommand(tmp_path: Path, sub: str) -> None:
    """INCIDENT 2026-10-01 11:19Z: `prune --help` ran a real prune. The port reads no repository for help: the git shim sees no call at all."""
    fx = make_fixture(tmp_path)
    dirty_checkout(fx)
    before, tracked = fx.state(), fx.root.joinpath(".gitignore").read_text(encoding="utf-8")
    fx.forget_calls()
    for flag in ("--help", "-h"):
        result = fx.run_port([sub, flag])
        assert result.rc == 0
        assert result.out.startswith("Usage: ./run.sh worktree %s" % sub)
        assert result.err == ""
    assert fx.call_log("git", "tmux", "gh", "docker", "sudo", "run.sh") == []
    assert fx.state() == before
    assert fx.root.joinpath(".gitignore").read_text(encoding="utf-8") == tracked


@needs_bash
def test_delta_d1_bash_prune_help_really_ran_the_prune(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    dirty_checkout(fx)
    result = fx.run_bash(["prune", "--help"])
    assert result.rc == 0
    assert "Syncing main repo" in result.err
    assert any("stash" in line for line in fx.call_log("git"))
    assert fx.git("rev-parse", "--abbrev-ref", "HEAD").strip() == "main"


@pytest.mark.parametrize("sub", ["prune", "create"])
def test_delta_d2_d3_a_dirty_shared_checkout_is_left_alone(tmp_path: Path, sub: str) -> None:
    fx = make_fixture(tmp_path)
    dirty_checkout(fx)
    before = fx.state()
    fx.forget_calls()
    result = fx.run_port([sub] + (["--no-devbox"] if sub == "create" else []))
    assert (
        "4 uncommitted or untracked path(s): refusing to stash, check out or pull it" in result.err
    )
    assert git_mutations(fx) == []
    assert fx.state()["status"] == before["status"]
    assert fx.state()["stash"] == []
    assert fx.state()["branch"] == "0930-1"
    if sub == "prune":
        assert result.rc == 0
    else:
        # create branches from the fetched origin/main without touching the checkout.
        assert result.rc == 0, result.err
        assert f"{TODAY}-1" in fx.branches()


@needs_bash
@pytest.mark.parametrize("sub", ["prune", "create"])
def test_delta_d2_d3_bash_stashed_and_switched_the_dirty_checkout(tmp_path: Path, sub: str) -> None:
    fx = make_fixture(tmp_path)
    dirty_checkout(fx)
    fx.run_bash([sub] + (["--no-devbox"] if sub == "create" else []))
    assert any("stash" in line for line in fx.call_log("git"))
    assert any("checkout main" in line for line in fx.call_log("git"))


def test_delta_d2_untracked_only_is_dirty_too(tmp_path: Path) -> None:
    """`git diff --quiet` cannot see an untracked file; the bash would have gone on to check out `main`."""
    fx = make_fixture(tmp_path)
    fx.git("checkout", "-q", "-b", "0930-1")
    (fx.root / "only-untracked.txt").write_text("x\n", encoding="utf-8")
    fx.forget_calls()
    result = fx.run_port(["prune"])
    assert "1 uncommitted or untracked path(s)" in result.err
    assert git_mutations(fx) == []
    assert fx.git("rev-parse", "--abbrev-ref", "HEAD").strip() == "0930-1"


def test_delta_d3_a_clean_checkout_on_its_branch_is_not_moved_to_main(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    fx.git("checkout", "-q", "-b", "0930-1")
    fx.forget_calls()
    result = fx.run_port(["prune"])
    assert result.rc == 0
    assert fx.git("rev-parse", "--abbrev-ref", "HEAD").strip() == "0930-1"
    assert git_mutations(fx) == []
    assert any(" fetch origin main" in line for line in fx.call_log("git"))


@needs_bash
def test_delta_d3_bash_moved_a_clean_checkout_to_main(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    fx.git("checkout", "-q", "-b", "0930-1")
    fx.run_bash(["prune"])
    assert fx.git("rev-parse", "--abbrev-ref", "HEAD").strip() == "main"


def test_delta_d3_a_clean_main_checkout_is_fast_forwarded(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    other = fx.base / "other"
    fx.git("clone", "-q", str(fx.origin), str(other), cwd=fx.base)
    fx.commit("later.txt", cwd=other)
    fx.git("push", "-q", "origin", "main", cwd=other)
    result = fx.run_port(["prune"])
    assert result.rc == 0
    assert (fx.root / "later.txt").exists()
    assert "Pulled latest origin/main" in result.err


# --------------------------------------------------------------------------- D4 to D12 ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ["list", "x"],
        ["prune", "x"],
        ["remove", "a", "b"],
        ["create", "x"],
        ["create", "--bogus"],
        ["switch", "a", "b"],
    ],
)
def test_delta_d4_surplus_arguments_and_options_are_refused(
    tmp_path: Path, args: list[str]
) -> None:
    fx = make_fixture(tmp_path)
    fx.forget_calls()
    result = fx.run_port(args)
    assert result.rc == 1
    assert result.err.startswith("✗ ")
    assert git_mutations(fx) == []


@needs_bash
@pytest.mark.parametrize("args", [["list", "x"], ["remove", "a", "b"]])
def test_delta_d4_bash_accepted_them(tmp_path: Path, args: list[str]) -> None:
    fx = make_fixture(tmp_path)
    assert fx.run_bash(args).err.startswith("✗ ") is (
        args[0] == "remove"
    )  # `remove a b` only failed because `a` does not exist
    assert fx.run_bash(["list", "x"]).rc == 0


@pytest.mark.parametrize("name", ["../victim", "..", ".", "a/b", "/etc", "-rf", ".hidden", ""])
def test_delta_d5_remove_takes_a_name_never_a_path(tmp_path: Path, name: str) -> None:
    fx = make_fixture(tmp_path)
    (fx.root / ".worktrees").mkdir()
    victim = fx.root / "victim"
    victim.mkdir()
    (victim / "keep").write_text("x\n", encoding="utf-8")
    fx.forget_calls()
    result = fx.run_port(["remove", name])
    assert result.rc == 1
    assert (victim / "keep").exists()
    assert fx.call_log("sudo") == []
    assert not any("worktree remove" in line or " branch -D" in line for line in fx.call_log("git"))


@needs_bash
def test_delta_d5_bash_reached_sudo_rm_on_a_path_outside_the_base(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    (fx.root / ".worktrees").mkdir()
    (fx.root / "victim").mkdir()
    fx.run_bash(["remove", "../victim"])
    assert any(
        line.startswith("sudo rm -rf") and line.endswith("/.worktrees/../victim")
        for line in fx.call_log("sudo")
    )


def test_delta_d5_a_symlink_named_like_a_worktree_is_not_followed(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    target = fx.base / "elsewhere"
    target.mkdir()
    (fx.root / ".worktrees").mkdir()
    (fx.root / ".worktrees" / "0101-1").symlink_to(target)
    result = fx.run_port(["remove", "0101-1"])
    assert result.rc == 1
    assert target.exists()


def test_delta_d6_prune_keeps_an_untracked_only_worktree_and_a_dirty_merged_one(
    tmp_path: Path,
) -> None:
    fx = make_fixture(tmp_path)
    untracked = add_worktree(fx, "0101-1")
    (untracked / "notes.txt").write_text("unsaved thought\n", encoding="utf-8")
    merged = add_worktree(fx, "0101-2")
    fx.commit("w.txt", cwd=merged)
    (merged / "w.txt").write_text("edited after commit\n", encoding="utf-8")
    fx.merged.write_text("0101-2\n", encoding="utf-8")
    result = fx.run_port(["prune"])
    assert result.rc == 0, result.err
    assert (untracked / "notes.txt").exists()
    assert merged.is_dir()
    assert "0101-1 (branch: 0101-1) - kept, 1 uncommitted or untracked path(s)" in result.out
    assert "0101-2 (branch: 0101-2) - kept, 1 uncommitted or untracked path(s)" in result.out
    assert {"0101-1", "0101-2"} <= set(fx.branches())


@needs_bash
def test_delta_d6_bash_deleted_the_untracked_only_worktree(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    untracked = add_worktree(fx, "0101-1")
    (untracked / "notes.txt").write_text("unsaved thought\n", encoding="utf-8")
    fx.run_bash(["prune"])
    assert not untracked.exists()


def test_delta_d6_prune_never_removes_the_worktree_it_runs_from(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    here = add_worktree(fx, "0101-1")
    result = fx.run_port(["prune"], cwd=here)
    assert here.is_dir()
    assert "kept, this command runs from it" in result.out


def test_delta_d7_a_merged_pr_does_not_cover_commits_made_after_it(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    path = add_worktree(fx, "0101-1")
    fx.commit("after-merge.txt", cwd=path)
    fx.stale.write_text("0101-1\n", encoding="utf-8")
    result = fx.run_port(["prune"])
    assert result.rc == 0
    assert path.is_dir()
    assert "0101-1" in fx.branches()


@needs_bash
def test_delta_d7_bash_deleted_the_branch_with_its_later_commits(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    path = add_worktree(fx, "0101-1")
    fx.commit("after-merge.txt", cwd=path)
    fx.stale.write_text("0101-1\n", encoding="utf-8")
    fx.run_bash(["prune"])
    assert "0101-1" not in fx.branches()


def test_delta_d8_a_detached_worktree_is_not_pruned_and_head_is_never_a_branch_to_delete(
    tmp_path: Path,
) -> None:
    fx = make_fixture(tmp_path)
    path = fx.root / ".worktrees" / "0101-1"
    fx.git("worktree", "add", "-q", "--detach", str(path), "origin/main")
    fx.forget_calls()
    result = fx.run_port(["prune"])
    assert result.rc == 0
    assert path.is_dir()
    assert not any(" branch -D" in line for line in fx.call_log("git"))


@needs_bash
def test_delta_d8_bash_removed_the_detached_worktree_and_reported_deleting_a_branch_called_head(
    tmp_path: Path,
) -> None:
    fx = make_fixture(tmp_path)
    path = fx.root / ".worktrees" / "0101-1"
    fx.git("worktree", "add", "-q", "--detach", str(path), "origin/main")
    result = fx.run_bash(["prune"])
    assert not path.exists()
    assert "Deleted branch: HEAD" in result.err


def test_delta_d8_remove_never_deletes_main(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    fx.git("checkout", "-q", "-b", "0930-1")
    path = fx.root / ".worktrees" / "0101-1"
    fx.git("worktree", "add", "-q", str(path), "main")
    result = fx.run_port(["remove", "0101-1"])
    assert result.rc == 0, result.err
    assert "main" in fx.branches()


def _local_ahead_of_remote(fx: Fixture) -> str:
    fx.git("checkout", "-q", "-b", "feat")
    fx.commit("on-remote.txt")
    fx.git("push", "-q", "origin", "feat")
    fx.commit("local-only.txt")
    fx.git("checkout", "-q", "main")
    return fx.git("rev-parse", "feat").strip()


def test_delta_d9_switch_keeps_local_commits_the_remote_lacks(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    tip = _local_ahead_of_remote(fx)
    result = fx.run_port(["switch", "feat"])
    assert result.rc == 0, result.err
    assert fx.git("rev-parse", "HEAD").strip() == tip
    assert "has commits origin/feat lacks" in result.err


@needs_bash
def test_delta_d9_bash_reset_the_local_branch_to_the_remote(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    tip = _local_ahead_of_remote(fx)
    fx.run_bash(["switch", "feat"])
    assert fx.git("rev-parse", "HEAD").strip() != tip


def test_delta_d9_a_submodule_branch_ahead_of_its_remote_is_kept(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    sub = fx.root / "private" / "sub"
    recorded = fx.git("rev-parse", "HEAD", cwd=sub).strip()
    fx.git("checkout", "-q", "-b", "feat", cwd=sub)
    fx.commit("sub-remote.txt", cwd=sub)
    fx.git("push", "-q", "origin", "feat", cwd=sub)
    fx.commit("sub-local.txt", cwd=sub)
    tip = fx.git("rev-parse", "HEAD", cwd=sub).strip()
    fx.git("checkout", "-q", "--detach", recorded, cwd=sub)
    fx.git("checkout", "-q", "-b", "feat", cwd=fx.root)
    fx.git("checkout", "-q", "main", cwd=fx.root)
    result = fx.run_port(["switch", "feat"])
    assert result.rc == 0, result.err
    assert fx.git("rev-parse", "feat", cwd=sub).strip() == tip


def test_delta_d9_switch_refuses_untracked_paths_and_a_bad_branch_name(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    fx.git("branch", "other")
    (fx.root / "scratch.txt").write_text("x\n", encoding="utf-8")
    (fx.root / "scratch2.txt").write_text("x\n", encoding="utf-8")
    fx.forget_calls()
    result = fx.run_port(["switch", "other"])
    assert result.rc == 1
    assert "has 2 uncommitted or untracked path(s)" in result.err
    assert git_mutations(fx) == []
    bad = fx.run_port(["switch", "a..b"])
    assert bad.rc == 1
    assert "Invalid branch name" in bad.err


@needs_bash
def test_delta_d9_bash_switched_over_untracked_paths(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    fx.git("branch", "other")
    (fx.root / "scratch.txt").write_text("x\n", encoding="utf-8")
    assert fx.run_bash(["switch", "other"]).rc == 0


def test_delta_d10_the_sudo_fallback_never_waits_for_a_password(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    path = add_worktree(fx, "0101-1")
    fx.git("worktree", "lock", str(path))
    fx.forget_calls()
    result = fx.run_port(["remove", "0101-1"])
    assert "trying sudo removal" in result.err
    assert fx.call_log("sudo") == ["sudo -n rm -rf -- <ROOT>/.worktrees/0101-1"]


@needs_bash
def test_delta_d10_bash_called_sudo_without_n(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    path = add_worktree(fx, "0101-1")
    fx.git("worktree", "lock", str(path))
    fx.forget_calls()
    fx.run_bash(["remove", "0101-1"])
    assert fx.call_log("sudo") == ["sudo rm -rf <ROOT>/.worktrees/0101-1"]


def test_delta_d11_list_matches_the_base_directory_not_a_string_prefix(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    add_worktree(fx, "0101-1")
    outside = fx.root / ".worktrees-old" / "0202-2"
    fx.git("worktree", "add", "-q", "-b", "0202-2", str(outside), "origin/main")
    result = fx.run_port(["list"])
    assert "0101-1" in result.out
    assert "0202-2" not in result.out


@needs_bash
def test_delta_d11_bash_listed_the_sibling_directory(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    add_worktree(fx, "0101-1")
    outside = fx.root / ".worktrees-old" / "0202-2"
    fx.git("worktree", "add", "-q", "-b", "0202-2", str(outside), "origin/main")
    assert "0202-2" in fx.run_bash(["list"]).out


def test_delta_d12_git_never_waits_for_a_credential_prompt(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    fx.forget_calls()
    fx.run_port(["prune"])
    lines = fx.call_log("git")
    assert lines
    assert all(line.startswith("git TP=0 ") for line in lines)


@needs_bash
def test_delta_d12_bash_left_the_prompt_on(tmp_path: Path) -> None:
    fx = make_fixture(tmp_path)
    fx.forget_calls()
    fx.run_bash(["prune"])
    assert all(line.startswith("git TP= ") for line in fx.call_log("git"))


def test_the_port_runs_as_a_module_file(tmp_path: Path) -> None:
    """`python worktree.py --help` is the same help, with no repository needed."""
    proc = subprocess.run(
        [sys.executable, str(CI_DIR / "rediacc_ci" / "dev" / "worktree.py"), "prune", "--help"],
        env={"PATH": SYSTEM_PATH, "PYTHONPATH": str(CI_DIR)},
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout.startswith("Usage: ./run.sh worktree prune")
