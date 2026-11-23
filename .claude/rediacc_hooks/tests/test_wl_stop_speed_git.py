"""Git answers keyed on HEAD, and the resprofile fold off the stop path (agent/plans/PLAN-tooling-speed.md SP2, designs D2 and D3).

HOW THE PROCESSES ARE COUNTED. The hook runs in a real subprocess under a launcher that installs a `sys.addaudithook` probe before `runpy` starts worklist.py. CPython raises `subprocess.Popen` for every child the hook starts, so the probe records each one with its argv and the innermost hook frame that started it.

WHAT IS COUNTED AGAINST THE BUDGET. A child started by a module this box owns (wl_core's git_run and the git helpers of wl_review, wl_schedred, wl_loopspeed, wl_uncommitted and wl_histfirst). A child started by a module outside PLAN-tooling-speed.md's Owns is named in UNOWNED_GIT_SITES or UNOWNED_PROCESS_SITES with a BLOCKER reason, and each entry must still fire on the fixture stop, so the lists can only shrink.

EVERY POSITIVE HAS ITS CONTROL: a new commit refreshes the cache (it cannot serve a stale HEAD), a working-tree query is never cached, and the first stop on a cold cache does start git (the probe is not blind).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time

import pytest
import wl_core as C
import wl_resprofile
import wl_ressample

from rediacc_hooks.tests import wlfix

PROBE = textwrap.dedent(
    """
    import json, os, runpy, sys
    hook, out = sys.argv[1], sys.argv[2]
    def audit(ev, args):
        if ev != "subprocess.Popen":
            return
        argv = args[1]
        if isinstance(argv, (str, bytes, os.PathLike)):
            argv = [argv]
        argv = [os.fsdecode(a) if isinstance(a, (bytes, os.PathLike)) else str(a) for a in argv]
        f, site = sys._getframe(1), ""
        while f is not None:
            base = os.path.basename(f.f_code.co_filename)
            if base.startswith(("wl_", "worklist")):
                site = "%s:%s" % (base, f.f_code.co_name)
                break
            f = f.f_back
        fd = os.open(out, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        os.write(fd, (json.dumps({"argv": argv[:8], "site": site}) + "\\n").encode())
        os.close(fd)
    sys.addaudithook(audit)
    sys.argv = [hook]
    sys.path.insert(0, os.path.dirname(hook))
    runpy.run_path(hook, run_name="__main__")
    """
)

OWNED_MODULES = (
    "wl_core.py",
    "wl_review.py",
    "wl_schedred.py",
    "wl_loopspeed.py",
    "wl_uncommitted.py",
    "wl_histfirst.py",
    "wl_resprofile.py",
    "wl_ressample.py",
    "wl_reggate.py",
)

# GIT CALL SITES OUTSIDE THIS PLAN'S OWNS, each with the reason it still starts git on a warm stop. Every entry must still fire (test_every_named_site_still_fires); a site moved onto wl_core.git_run is served, and its entry must go.
UNOWNED_GIT_SITES = {
    "wl_prscope.py": "BLOCKER: wl_prscope.py is outside PLAN-tooling-speed.md's Owns; its rev-parse, symbolic-ref and for-each-ref calls run their own subprocess",
    "wl_boxaudit.py": "BLOCKER: wl_boxaudit.py is outside PLAN-tooling-speed.md's Owns; its _git runs its own subprocess",
    "wl_worktrees.py": "BLOCKER: wl_worktrees.py is outside PLAN-tooling-speed.md's Owns; its _git runs its own subprocess",
    "wl_planqueue.py": "BLOCKER: wl_planqueue.py is outside PLAN-tooling-speed.md's Owns; landing_trees runs its own rev-parse",
    "wl_git.py": "BLOCKER: wl_git.py is outside PLAN-tooling-speed.md's Owns; run_git runs its own subprocess",
    "wl_stack.py": "BLOCKER: wl_stack.py is outside PLAN-tooling-speed.md's Owns; stack_state runs its own rev-parse",
    "wl_outcomes.py": "BLOCKER: wl_outcomes.py is outside PLAN-tooling-speed.md's Owns; commits_since runs its own git log",
}

# NON-GIT CHILDREN of run_stop that this box cannot remove, by the module that starts them.
UNOWNED_PROCESS_SITES = {
    "wl_checks.py:backup_lag": "BLOCKER: backup_lag lives in wl_checks.py, which this plan's SP3 and other live plans edit; its `python3 -m rediacc_ci.dev.backup_ref` child leaves the stop path only by an edit there",
}

# Owned git starts allowed on a warm stop: wl_uncommitted's `git status --porcelain` reads the working tree, which no HEAD key can answer, and the rest come from the cache.
WARM_OWNED_GIT_BUDGET = 3


def counted_stop(fix: wlfix.Fixture, tmp, name: str) -> list[dict]:
    probe = tmp / "probe.py"
    probe.write_text(PROBE, encoding="utf-8")
    out = tmp / ("%s.jsonl" % name)
    if out.exists():
        out.unlink()
    before = fix._lastevents()
    proc = subprocess.run(
        [sys.executable, str(probe), str(fix.hook), str(out)],
        input=fix.event(),
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert fix._lastevents() != before, "the Stop battery did not run: %s" % proc.stderr[-800:]
    if not out.is_file():
        return []
    return [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]


def is_git(row: dict) -> bool:
    return os.path.basename(row["argv"][0]) == "git"


def module_of(row: dict) -> str:
    return row["site"].split(":", 1)[0]


def owned_git(rows: list[dict]) -> list[dict]:
    return [r for r in rows if is_git(r) and module_of(r) in OWNED_MODULES]


def world(fix: wlfix.Fixture) -> None:
    fix.reg_repo()
    got = fix.cli("--add", wlfix.ME, "probe the git cache")
    assert got.rc == 0, got.err[-800:]
    fix.say("done\n\n## Remaining\n- the probe item")
    fix.brief_now()
    fix.hand_now()


@pytest.fixture
def stops(wl, tmp_path):
    """Three counted stops: a cold one, a warm one on the same HEAD, and one after a new commit."""
    world(wl)
    cold = counted_stop(wl, tmp_path, "cold")
    warm = counted_stop(wl, tmp_path, "warm")
    wl.fixcommit("next.txt", "chore: move HEAD")
    moved = counted_stop(wl, tmp_path, "moved")
    return cold, warm, moved


def test_a_warm_stop_starts_at_most_three_owned_git_processes(stops):
    cold, warm, _moved = stops
    # NOT BLIND: the cold stop has to ask git, or a count of zero below proves nothing.
    assert len(owned_git(cold)) > WARM_OWNED_GIT_BUDGET, [r["argv"][3:6] for r in owned_git(cold)]
    got = owned_git(warm)
    assert len(got) <= WARM_OWNED_GIT_BUDGET, [(r["site"], r["argv"][3:6]) for r in got]


def test_a_new_commit_refreshes_the_cache(stops):
    """CONTROL: the stop after a commit asks git again for the HEAD-keyed answers."""
    _cold, warm, moved = stops

    def asks_head(rows):
        return [r for r in owned_git(rows) if r["argv"][-2:] == ["rev-parse", "HEAD"]]

    assert not asks_head(warm), "a warm stop asked git for HEAD: %s" % asks_head(warm)
    assert asks_head(moved), "the stop after a commit served HEAD from the cache"


def test_no_unowned_git_site_is_new(stops):
    """Every git start on a warm stop comes from an owned module or from a named unowned site."""
    _cold, warm, _moved = stops
    stray = sorted(
        {
            module_of(r)
            for r in warm
            if is_git(r)
            and module_of(r) not in OWNED_MODULES
            and module_of(r) not in UNOWNED_GIT_SITES
        }
    )
    assert not stray, "git started from a module neither owned nor named: %s" % stray


def test_no_npm_or_python_module_child_starts_from_run_stop(stops):
    _cold, warm, _moved = stops
    bad = [
        r
        for r in warm
        if (os.path.basename(r["argv"][0]) == "npm" or r["argv"][1:2] == ["-m"])
        and r["site"] not in UNOWNED_PROCESS_SITES
    ]
    assert not bad, bad


def test_every_named_site_still_fires(stops):
    """The exemption lists are live: an entry whose site no longer starts its child is served, and must be deleted."""
    _cold, warm, _moved = stops
    git_sites = {module_of(r) for r in warm if is_git(r)}
    stale = sorted(set(UNOWNED_GIT_SITES) - git_sites)
    assert not stale, "no longer starts git on a warm stop; delete its entry: %s" % stale
    proc_sites = {r["site"] for r in warm if not is_git(r)}
    stale = sorted(set(UNOWNED_PROCESS_SITES) - proc_sites)
    assert not stale, "no longer starts its child; delete its entry: %s" % stale


# ---- the cache itself, in-process -------------------------------------------


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key)
    monkeypatch.delenv("WORKLIST_READ_MEMO", raising=False)
    root = tmp_path / "r"
    root.mkdir()
    for args in (
        ["init", "-q"],
        ["config", "user.email", "t@t"],
        ["config", "user.name", "t"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "a"], check=True)
    C._GIT_CACHE.clear()
    C._GIT_DIRS.clear()
    C.GIT_CACHE_STATS.update(hit=0, miss=0)
    return root


def sh(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def test_an_unchanged_head_is_answered_from_the_cache(repo):
    first = C._git(repo, "rev-parse", "HEAD")
    assert first == sh(repo, "rev-parse", "HEAD")
    assert C._git(repo, "rev-parse", "HEAD") == first
    assert C.GIT_CACHE_STATS == {"hit": 1, "miss": 1}


def test_a_commit_moves_the_key_and_the_answer(repo):
    """CONTROL: the cache never serves the sha of a HEAD that has moved."""
    before = C._git(repo, "rev-parse", "HEAD")
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-qm", "b")
    after = C._git(repo, "rev-parse", "HEAD")
    assert after != before
    assert after == sh(repo, "rev-parse", "HEAD")
    assert C.GIT_CACHE_STATS["miss"] == 2


def test_a_lease_tree_resolves_to_its_own_git_dir_and_the_shared_common_dir(tmp_path):
    """The cache's repository lookup reuses wl_core._git_dirs (a lease's `.git` file and its `commondir`), and leaves that function's own contract alone: lease_main still answers a fake lease with its main checkout."""
    main = tmp_path / "main"
    admin = main / ".git" / "worktrees" / "lease1"
    admin.mkdir(parents=True)
    (admin / "commondir").write_text("../..\n", encoding="utf-8")
    (admin / "HEAD").write_text("ref: refs/heads/x\n", encoding="utf-8")
    (main / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    lease = main / ".claude" / "worktrees" / "lease1"
    lease.mkdir(parents=True)
    (lease / ".git").write_text("gitdir: %s\n" % admin, encoding="utf-8")
    (lease / "sub").mkdir()
    C._GIT_DIRS.clear()
    assert C._repo_git_dirs(lease / "sub") == (
        admin.resolve(),
        (main / ".git").resolve(),
    )
    assert C.lease_main(lease) == main


@pytest.mark.parametrize(
    "move",
    [
        ["update-ref", "refs/remotes/origin/main", "HEAD"],
        ["config", "remote.origin.url", "https://example.invalid/x.git"],
        ["checkout", "-q", "-b", "other"],
    ],
)
def test_a_ref_config_or_branch_move_changes_the_key(repo, move):
    before = C.git_state_key(repo)
    sh(repo, *move)
    assert C.git_state_key(repo) != before, move


def test_the_index_moves_only_an_index_reading_key(repo):
    """An index write expires `:path` answers and leaves the ref answers alone: `git status` rewrites a racy index on most stops."""
    refs, idx = C.git_state_key(repo), C.git_state_key(repo, index=True)
    time.sleep(0.01)
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    sh(repo, "add", "a.txt")
    assert C.git_state_key(repo, index=True) != idx
    assert C.git_state_key(repo) == refs
    assert C.git_reads_index(["show", ":a.txt"])
    assert not C.git_reads_index(["rev-parse", "HEAD"])


def test_the_answers_persist_across_processes(repo):
    C._git(repo, "rev-parse", "HEAD")
    C.flush_git_cache()
    C._GIT_CACHE.clear()
    C.GIT_CACHE_STATS.update(hit=0, miss=0)
    C._git(repo, "rev-parse", "HEAD")
    assert C.GIT_CACHE_STATS == {"hit": 1, "miss": 0}


def test_a_repository_shaping_git_variable_turns_the_cache_off(repo, monkeypatch):
    monkeypatch.setenv("GIT_DIR", str(repo / ".git"))
    assert C.git_state_key(repo) is None


def test_an_editor_variable_leaves_the_cache_on(repo, monkeypatch):
    """CONTROL: GIT_EDITOR is set in ordinary sessions and changes nothing git answers; refusing every GIT_* variable turned the cache off everywhere."""
    monkeypatch.setenv("GIT_EDITOR", "true")
    monkeypatch.setenv("GIT_PAGER", "cat")
    assert C.git_state_key(repo) is not None


def test_a_config_variable_joins_the_key(repo, monkeypatch, tmp_path):
    """GIT_CONFIG_GLOBAL changes what `config --get` answers: the key moves with its value and with the file it names."""
    before = C.git_state_key(repo)
    glob = tmp_path / "g.cfg"
    glob.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(glob))
    named = C.git_state_key(repo)
    assert named is not None
    assert named != before
    time.sleep(0.01)
    glob.write_text("[user]\n\tname = x\n", encoding="utf-8")
    assert C.git_state_key(repo) != named


@pytest.mark.parametrize(
    ("args", "want"),
    [
        (["rev-parse", "HEAD"], True),
        (["symbolic-ref", "--short", "-q", "HEAD"], True),
        (["config", "--get", "remote.origin.url"], True),
        (["log", "--format=%ct", "origin/x..HEAD"], True),
        # `submodule status --cached` describes from the SUBMODULE's refs, which no key here covers.
        (["submodule", "status", "--cached"], False),
        # The other direction: working-tree, writing and clock-relative queries are never cached.
        (["status", "--porcelain"], False),
        (["diff", "--name-only"], False),
        (["submodule", "status"], False),
        (["config", "remote.origin.url", "x"], False),
        (["log", "--since=2.hours.ago"], False),
        (["log", "--format=%cr"], False),
        (["log", "-g"], False),
        (["rev-parse", "HEAD@{1}"], False),
        ([], False),
    ],
)
def test_only_read_only_state_queries_are_cacheable(args, want):
    assert C.git_cacheable(args) is want


# ---- the resprofile fold off the stop path ----------------------------------


@pytest.fixture
def prof(tmp_path, monkeypatch):
    monkeypatch.setenv("RESPROFILE_ROOT", str(tmp_path / "rp"))
    monkeypatch.delenv("WORKLIST_PROFILE", raising=False)
    paths = wl_resprofile.store_paths()
    assert paths is not None
    return paths


def rec(n):
    return {"v": 1, "shape": "py:x", "cpu_ms": n, "rss_kb": n}


def test_the_fold_reads_from_its_byte_cursor(prof):
    t0, _t1 = prof
    for n in range(3):
        wl_resprofile.append(rec(n), prof)
    roll = wl_resprofile.fold(prof)
    assert roll["shapes"]["py:x"]["n"] == 3
    assert roll["cursor_bytes"][str(t0)] == t0.stat().st_size
    wl_resprofile.append(rec(9), prof)
    roll = wl_resprofile.fold(prof)
    assert roll["shapes"]["py:x"]["n"] == 4
    assert roll["folded_lines"] == 1


def test_a_torn_last_line_waits_for_the_next_fold(prof):
    t0, _t1 = prof
    wl_resprofile.append(rec(1), prof)
    with t0.open("ab") as fh:
        fh.write(b'{"v":1,"shape":"py:x"')
    roll = wl_resprofile.fold(prof)
    assert roll["shapes"]["py:x"]["n"] == 1
    with t0.open("ab") as fh:
        fh.write(b',"cpu_ms":2,"rss_kb":2}\n')
    assert wl_resprofile.fold(prof)["shapes"]["py:x"]["n"] == 2


def test_a_line_cursor_converts_without_folding_twice(prof):
    t0, t1 = prof
    for n in range(4):
        wl_resprofile.append(rec(n), prof)
    t1.write_text(
        json.dumps({"format": 1, "shapes": {"py:x": {"n": 2}}, "cursor": {str(t0): 2}}),
        encoding="utf-8",
    )
    roll = wl_resprofile.fold(prof)
    assert roll["shapes"]["py:x"]["n"] == 4
    assert "cursor" not in roll


def test_the_stop_process_reads_the_rollup_and_never_folds(prof, tmp_path):
    """A Stop process (worklist.py with `_RUN["stop"]`) gets the rollup as it stands; the same call outside a Stop folds. CONTROL first."""
    t0, t1 = prof
    wl_resprofile.append(rec(1), prof)
    script = tmp_path / "s.py"
    script.write_text(
        textwrap.dedent(
            """
            import json, pathlib, sys
            sys.path.insert(0, sys.argv[1])
            if sys.argv[2] == "stop":
                _RUN = {"stop": True}
            import wl_resprofile
            roll = wl_resprofile.fold((pathlib.Path(sys.argv[3]), pathlib.Path(sys.argv[4])))
            print(json.dumps(roll.get("folded_lines")))
            """
        ),
        encoding="utf-8",
    )

    def run(mode):
        return subprocess.run(
            [sys.executable, str(script), str(wlfix.STOP_DIR), mode, str(t0), str(t1)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    assert run("stop") == "null"
    assert not t1.exists(), "the Stop process wrote the rollup"
    assert run("cli") == "1"
    assert t1.exists()


def test_the_sampler_folds_after_its_watch(prof, tmp_path, monkeypatch):
    t0, t1 = prof
    wl_resprofile.append(rec(5), prof)
    monkeypatch.setattr(wl_resprofile, "store_paths", lambda: prof)
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    rc = wl_ressample.main(
        ["--watch", str(child.pid), "--out", str(tmp_path / "cap.jsonl"), "--interval-ms", "50"]
    )
    assert rc == 0
    assert json.loads(t1.read_text(encoding="utf-8"))["shapes"]["py:x"]["n"] == 1
    assert t0.is_file()
