"""Hooks stand down while a rebase, merge, cherry-pick, revert or am is halted (worklist #b07162cf, PR-TASK 79b7e92e).

THE INCIDENT, 2026-11-23. Rebasing 1121-1 (273 steps) onto origin/main halted at step 26 on a conflict. The conflict was resolved and staged, `git ls-files -u` was empty, and `git rebase --continue` still exited 1 asking for the conflicts to be resolved with `git add`. Meanwhile the Stop hook had rewritten agent/plans/QUEUE.md and agent/ledgers/effort-outcomes.jsonl, and the post-bash reviewer had appended to agent/reviews/1121-1/clean.jsonl, all unstaged.

THE ROOT CAUSE, reproduced here with real git and the real commit-policy hooks installed (`test_root_cause_*`): `git rebase --continue` refuses while ANY tracked path holds an unstaged change, whatever the index says, and its message blames merge conflicts. It runs no `pre-commit` and no `commit-msg` for the resumed step, so the commit-policy hook cannot be what refused it. The hooks' writes were the cause.

THE FIX, one case per behaviour, each with its silent control (no operation in progress, the hook writes as before):

  wl_git.operation_in_progress   the one answer, over every real halted state and a linked worktree
  wl_git rebase-continue         refuses BEFORE `git rebase --continue`, naming the unstaged paths
  the Stop hook                  blocks once and writes no tracked byte; allows on `stop_hook_active`
  wl_review.trigger / run_review starts no reviewer, and a running one records nothing
  githooks pre-commit            mid-rebase, judges the commit's index, not an unstaged input
  block_rebase_over_foreign_dirt refuses to START a main-checkout rebase onto a base whose wl_git.py lacks the stand-down (box R20261123.3)
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_review_commit_hook import World
from rediacc_hooks.tests.test_wl_retro import boundary, compact, ledger_rows

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
HOOKS = REPO_ROOT / ".claude" / "rediacc_hooks" / "git"
WL_GIT = REPO_ROOT / ".claude" / "hooks" / "stop" / "wl_git.py"
G = wlfix.import_wl("wl_git")
R = wlfix.import_wl("wl_review")

# The words git prints on stdout when `--continue` meets an unstaged tracked change (git 2.53.0).
GIT_REFUSAL = "mark them as resolved using git add"
BRANCH = "0101-1"


def _env(**extra: str) -> dict[str, str]:
    env = wlfix.scrubbed_environ()
    for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "COMMIT_POLICY_OK"):
        env.pop(k, None)
    env.update(
        {
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_EDITOR": "true",
        }
    )
    env.update(extra)
    return env


def git(repo, *args, check=True, **extra):
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=_env(**extra),
        check=False,
        timeout=120,
    )
    if check and proc.returncode != 0:
        raise AssertionError(
            "git %s: rc=%d\n%s%s" % (args, proc.returncode, proc.stdout, proc.stderr)
        )
    return proc


def write(repo, rel, text):
    path = pathlib.Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit_all(repo, msg, **extra):
    git(repo, "add", "-A", **extra)
    git(repo, "commit", "-q", "-m", msg, **extra)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def base_repo(repo, records=True):
    """`repo` on BRANCH with a base commit: f.txt (the file the conflicts land in) and, with `records`, a hook record and a QUEUE.md like the console's."""
    git(repo.parent, "init", "-q", "-b", BRANCH, str(repo))
    write(repo, "f.txt", "base\n")
    write(repo, "other.txt", "unrelated\n")
    if records:
        write(repo, "agent/ledgers/effort-outcomes.jsonl", '{"id": "eo-1"}\n')
        write(repo, "agent/plans/QUEUE.md", "# Plan queue\n")
    return commit_all(repo, "chore: base")


def halt_rebase(repo):
    """A real `git rebase` halted on a conflict in f.txt: BRANCH carries one commit, `upstream` another, both editing f.txt."""
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    write(repo, "f.txt", "topic\n")
    commit_all(repo, "feat: topic")
    git(repo, "checkout", "-q", "--detach", base)
    write(repo, "f.txt", "upstream\n")
    upstream = commit_all(repo, "feat: upstream")
    git(repo, "checkout", "-q", BRANCH)
    proc = git(repo, "rebase", upstream, check=False)
    assert proc.returncode != 0, "the fixture rebase did not halt: %s" % proc.stdout
    return upstream


def markers(repo):
    """The operation markers present in `repo`'s own git dir, read WITHOUT the helper under test, so a fixture's setup cannot fail for the reason a case asserts."""
    gd = pathlib.Path(git(repo, "rev-parse", "--absolute-git-dir").stdout.strip())
    names = (
        "rebase-merge",
        "rebase-apply",
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "sequencer",
    )
    return {n for n in names if (gd / n).exists()}


def resolve(repo):
    write(repo, "f.txt", "resolved\n")
    git(repo, "add", "--", "f.txt")
    assert git(repo, "ls-files", "-u").stdout == "", "a conflict is still unmerged"


# --------------------------------------------------------------------------- the helper


def _side(repo, text):
    """A commit off HEAD editing f.txt to `text`, left dangling; HEAD returns to BRANCH."""
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-q", "--detach", head)
    write(repo, "f.txt", text)
    sha = commit_all(repo, "side %s" % text.strip())
    git(repo, "checkout", "-q", BRANCH)
    return sha


def halted(kind, repo):
    """`repo` with a real `kind` operation halted on a conflict."""
    base_repo(repo, records=False)
    if kind == "rebase":
        halt_rebase(repo)
    elif kind == "merge":
        side = _side(repo, "side\n")
        write(repo, "f.txt", "ours\n")
        commit_all(repo, "ours")
        assert git(repo, "merge", side, check=False).returncode != 0
    elif kind == "cherry-pick":
        side = _side(repo, "side\n")
        write(repo, "f.txt", "ours\n")
        commit_all(repo, "ours")
        assert git(repo, "cherry-pick", side, check=False).returncode != 0
    elif kind == "revert":
        write(repo, "f.txt", "a\n")
        first = commit_all(repo, "a")
        write(repo, "f.txt", "b\n")
        commit_all(repo, "b")
        assert git(repo, "revert", "--no-edit", first, check=False).returncode != 0
    elif kind == "am":
        side = _side(repo, "side\n")
        patch = git(repo, "format-patch", "-1", "--stdout", side).stdout
        write(repo, "f.txt", "ours\n")
        commit_all(repo, "ours")
        (repo.parent / "p.patch").write_text(patch, encoding="utf-8")
        assert git(repo, "am", str(repo.parent / "p.patch"), check=False).returncode != 0
    else:
        raise AssertionError(kind)


@pytest.mark.parametrize("kind", ["rebase", "merge", "cherry-pick", "revert", "am"])
def test_operation_in_progress_names_each_real_halt(tmp_path, kind):
    repo = tmp_path / "r"
    halted(kind, repo)
    assert G.operation_in_progress(repo) == kind


def test_operation_in_progress_control_a_clean_repo_and_a_non_repo_are_empty(tmp_path):
    repo = tmp_path / "r"
    base_repo(repo)
    assert G.operation_in_progress(repo) == ""
    lone = tmp_path / "lone"
    lone.mkdir()
    # GIT_CEILING_DIRECTORIES is not needed: tmp_path is outside every repository.
    assert G.operation_in_progress(lone) == ""
    assert G.operation_in_progress(tmp_path / "missing") == ""


def test_operation_in_progress_reads_a_linked_worktree_s_own_git_dir(tmp_path):
    """`.git` is a FILE in a linked worktree; the halt lives in its own git dir, and the main checkout is not halted."""
    repo = tmp_path / "r"
    base_repo(repo, records=False)
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "-q", "--detach", str(linked))
    git(linked, "checkout", "-q", "-b", "0101-2")
    write(linked, "f.txt", "linked\n")
    commit_all(linked, "linked")
    side = _side(repo, "side\n")
    assert git(linked, "rebase", side, check=False).returncode != 0
    assert (linked / ".git").is_file()
    assert G.operation_in_progress(linked) == "rebase"
    assert G.operation_in_progress(repo) == ""


def test_operation_in_progress_names_a_bare_sequencer(tmp_path):
    """Between the picks of a multi-commit cherry-pick only `sequencer/` is left, and it is the marker that goes stale."""
    repo = tmp_path / "r"
    base_repo(repo)
    gd = git(repo, "rev-parse", "--absolute-git-dir").stdout.strip()
    (pathlib.Path(gd) / "sequencer").mkdir()
    assert G.operation_in_progress(repo) == "sequencer"
    assert "--quit" in G.operation_finish_hint("sequencer")


# --------------------------------------------------------------------------- the root cause


def test_root_cause_continue_refuses_over_one_unstaged_tracked_file_with_no_conflict_left(tmp_path):
    """The real commit-policy hooks are installed, as in the console. With every conflict staged, one unstaged tracked record is enough for git to refuse, and git blames merge conflicts."""
    repo = tmp_path / "r"
    base_repo(repo)
    git(repo, "config", "core.hooksPath", str(HOOKS))
    halt_rebase(repo)
    resolve(repo)
    write(repo, "agent/ledgers/effort-outcomes.jsonl", '{"id": "eo-1"}\n{"id": "eo-2"}\n')
    proc = git(repo, "rebase", "--continue", check=False)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert GIT_REFUSAL in proc.stdout
    assert git(repo, "ls-files", "-u").stdout == ""
    assert "rebase-merge" in markers(repo)


def test_root_cause_control_the_same_halt_continues_once_the_tracked_file_is_clean(tmp_path):
    repo = tmp_path / "r"
    base_repo(repo)
    git(repo, "config", "core.hooksPath", str(HOOKS))
    halt_rebase(repo)
    resolve(repo)
    write(repo, "untracked.txt", "untracked files do not count\n")
    proc = git(repo, "rebase", "--continue", check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert markers(repo) == set()
    assert git(repo, "show", "HEAD:f.txt").stdout == "resolved\n"


def test_root_cause_continue_runs_no_pre_commit_or_commit_msg_hook(tmp_path):
    """Why the commit-policy hook is not the refuser: git resumes the step with neither hook (only post-commit and post-rewrite run)."""
    repo = tmp_path / "r"
    base_repo(repo)
    hooks = tmp_path / "probe-hooks"
    hooks.mkdir()
    log = tmp_path / "hooks.log"
    for name in ("pre-commit", "commit-msg", "post-commit"):
        p = hooks / name
        p.write_text("#!/bin/sh\necho %s >> '%s'\n" % (name, log), encoding="utf-8")
        p.chmod(0o755)
    halt_rebase(repo)
    git(repo, "config", "core.hooksPath", str(hooks))
    resolve(repo)
    assert git(repo, "rebase", "--continue", check=False).returncode == 0
    ran = log.read_text(encoding="utf-8").split()
    assert "post-commit" in ran, (
        "the probe hooks did not run at all, so their absence proves nothing"
    )
    assert "pre-commit" not in ran, ran
    assert "commit-msg" not in ran, ran


# --------------------------------------------------------------------------- the executor


def run_executor(repo):
    return subprocess.run(
        [sys.executable, str(WL_GIT), "rebase-continue", "--execute"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
        timeout=300,
    )


def test_executor_refuses_before_continue_and_names_the_unstaged_record(tmp_path):
    repo = tmp_path / "r"
    base_repo(repo)
    halt_rebase(repo)
    resolve(repo)
    write(repo, "agent/plans/QUEUE.md", "# Plan queue\n\nrewritten by a hook\n")
    proc = run_executor(repo)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "REFUSED" in proc.stderr
    assert "agent/plans/QUEUE.md" in proc.stderr
    assert "hook records" in proc.stderr
    assert GIT_REFUSAL not in proc.stdout + proc.stderr, (
        "git's own refusal ran, so the check came too late"
    )
    assert "rebase-merge" in markers(repo)


def test_executor_control_a_clean_halt_continues_to_the_end(tmp_path):
    repo = tmp_path / "r"
    base_repo(repo)
    halt_rebase(repo)
    resolve(repo)
    proc = run_executor(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert markers(repo) == set()


def test_continue_dirt_refusal_skips_staged_settings_local_and_the_paths_it_stages(tmp_path):
    repo = tmp_path / "r"
    base_repo(repo)
    write(repo, G.SETTINGS_LOCAL, "{}\n")
    # Forced: the default ~/.config/git/ignore may exclude it, as the console's own tracked copy predates any such rule.
    git(repo, "add", "-f", "--", G.SETTINGS_LOCAL)
    git(repo, "commit", "-q", "-m", "settings")
    write(repo, G.SETTINGS_LOCAL, '{"a": 1}\n')
    write(repo, "f.txt", "to be staged by the verb\n")
    write(repo, "other.txt", "staged already\n")
    git(repo, "add", "--", "other.txt")
    assert G.continue_dirt_refusal(repo, staging=("f.txt",)) is None
    write(repo, "agent/ledgers/effort-outcomes.jsonl", "x\n")
    said = G.continue_dirt_refusal(repo, staging=("f.txt",))
    assert said
    assert "agent/ledgers/effort-outcomes.jsonl" in said
    assert "f.txt," not in said


# --------------------------------------------------------------------------- the Stop hook


def tracked_snapshot(repo):
    """Every tracked path's work-tree bytes, hashed, plus `git status --porcelain`: a stop that wrote a tracked byte changes one of them."""
    files = git(repo, "ls-files", "-z").stdout.split("\0")
    digests = {}
    for rel in filter(None, files):
        path = pathlib.Path(repo) / rel
        digests[rel] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return digests, git(repo, "status", "--porcelain", "--untracked-files=no").stdout


@pytest.fixture
def stopworld(wl):
    """The Stop-hook sandbox with a real repository at proj/ whose tracked files include agent/plans/QUEUE.md, as in the console."""
    wl.reg_repo()
    wl.git("add", "-A")
    wl.git("commit", "-qm", "chore: queue", "--allow-empty")
    assert "agent/plans/QUEUE.md" in wl.git("ls-files").stdout
    return wl


def halt_merge_in(wl):
    env = _env()
    proj = wl.proj
    base = git(proj, "rev-parse", "HEAD").stdout.strip()
    write(proj, "base.txt", "ours\n")
    git(proj, "commit", "-qam", "ours")
    git(proj, "checkout", "-q", "--detach", base)
    write(proj, "base.txt", "theirs\n")
    git(proj, "commit", "-qam", "theirs")
    theirs = git(proj, "rev-parse", "HEAD").stdout.strip()
    branch = git(proj, "rev-parse", "--abbrev-ref", "@{-1}").stdout.strip()
    git(proj, "checkout", "-q", branch)
    merged = subprocess.run(
        ["git", "-C", str(proj), "merge", theirs], capture_output=True, env=env, check=False
    )
    assert merged.returncode != 0
    assert "MERGE_HEAD" in markers(proj)


def test_stop_hook_blocks_once_and_writes_no_tracked_byte_mid_merge(stopworld):
    wl = stopworld
    halt_merge_in(wl)
    before = tracked_snapshot(wl.proj)
    store_before = wl.wl_events()
    got = wl.run()
    assert got.rc == 0, got.err
    assert got.decision == "block", got.out
    reason = json.loads(got.out)["reason"]
    assert "merge is in progress" in reason
    assert "NONE of this stop's checks ran" in reason
    assert "git merge --continue" in reason
    assert tracked_snapshot(wl.proj) == before
    assert wl.wl_events() == store_before
    assert not got.battery_ran


def test_stop_hook_allows_on_stop_hook_active_and_still_writes_nothing(stopworld):
    wl = stopworld
    halt_merge_in(wl)
    before = tracked_snapshot(wl.proj)
    event = json.loads(wl.event())
    event["stop_hook_active"] = True
    got = wl.run(event=json.dumps(event))
    assert got.rc == 0, got.err
    assert got.decision != "block", got.out
    assert "UNCHECKED" in json.loads(got.out)["systemMessage"]
    assert tracked_snapshot(wl.proj) == before


def test_stop_hook_control_without_an_operation_the_battery_runs(stopworld):
    wl = stopworld
    before = tracked_snapshot(wl.proj)
    got = wl.run()
    assert got.rc == 0, got.err
    assert "standing down" not in got.out
    assert "in progress in" not in got.out
    assert got.battery_ran, "the battery did not run, so the stand-down cases prove nothing"
    # THE HAZARD ITSELF: a normal stop rewrites the tracked QUEUE.md (its in-flight block), which is what makes the no-write assertions above able to fail.
    assert " M agent/plans/QUEUE.md" in tracked_snapshot(wl.proj)[1], before[1]


def test_post_compact_orders_no_retro_row_mid_merge_and_says_so(stopworld):
    """PostCompact appends the retro order to the TRACKED retro ledger; mid-operation it writes nothing and the briefing names why."""
    wl = stopworld
    halt_merge_in(wl)
    wl.plant_state("## Next action\n\nkeep going")
    wl.append_transcript(boundary(False))
    text = compact(wl)
    assert "Post-compact retro NOT ordered" in text, text[-600:]
    assert "merge is in progress" in text
    assert "STOP-HOOK RETRO" not in text
    assert ledger_rows(wl) == []


def test_post_compact_control_orders_the_retro_row_without_an_operation(stopworld):
    wl = stopworld
    wl.plant_state("## Next action\n\nkeep going")
    wl.append_transcript(boundary(False))
    text = compact(wl)
    assert "STOP-HOOK RETRO" in text, text[-600:]
    assert "Post-compact retro NOT ordered" not in text
    assert len(ledger_rows(wl)) == 1


# --------------------------------------------------------------------------- the reviewer


@pytest.fixture
def reviewworld(tmp_path, monkeypatch):
    w = World(tmp_path)
    monkeypatch.setenv("TMPDIR", str(w.tmpdir))
    return w


def halt_cherry_pick_in(w):
    w.commit(name="f.txt", body="ours\n", msg="fix(x): ours")
    head = w.git("rev-parse", "HEAD").stdout.strip()
    w.git("checkout", "-q", "--detach", "origin/main")
    side = w.commit(name="f.txt", body="theirs\n", msg="fix(x): theirs")
    w.git("checkout", "-q", BRANCH_R)
    assert w.git("cherry-pick", side, check=False).returncode != 0
    assert "CHERRY_PICK_HEAD" in markers(w.repo)
    return head


BRANCH_R = "0930-1"


def _recording_spawn(spawned: list[tuple[object, ...]]):
    """A spawn stand-in that records each call and answers a fake pid."""

    def spawn(*a: object) -> int:
        spawned.append(a)
        return 4242

    return spawn


def test_trigger_starts_no_reviewer_mid_operation(reviewworld):
    w = reviewworld
    halt_cherry_pick_in(w)
    spawned: list[tuple[object, ...]] = []
    assert R.trigger(w.repo, w.repo, spawn=_recording_spawn(spawned)) == []
    assert spawned == []


def test_trigger_control_the_same_commit_gets_a_reviewer_once_the_operation_ends(reviewworld):
    w = reviewworld
    halt_cherry_pick_in(w)
    w.git("cherry-pick", "--abort")
    spawned: list[tuple[object, ...]] = []
    started = R.trigger(w.repo, w.repo, spawn=_recording_spawn(spawned))
    assert spawned, "nothing was uncovered, so the stand-down case proves nothing"
    assert started


def test_post_bash_names_the_deferral_instead_of_calling_it_covered(reviewworld):
    w = reviewworld
    halt_cherry_pick_in(w)
    rc, out, _err, _t = w.hook("git cherry-pick --continue")
    assert rc == 0
    assert "per-commit review deferred" in out
    assert "cherry-pick is in progress" in out
    assert "none due" not in out


def _clean_reviewer(_prompt, _cfg, _log):
    return {
        "verdict": "clean",
        "findings": [],
        "labels": {"bump": "none", "kind": ["chore"], "why": "x"},
    }, ""


def test_a_running_reviewer_records_nothing_once_an_operation_began(reviewworld):
    w = reviewworld
    head = halt_cherry_pick_in(w)
    before = tracked_snapshot(w.repo)
    said: list[str] = []
    path = R.run_review(
        w.repo, "console", head, BRANCH_R, reviewer=_clean_reviewer, log=said.append
    )
    assert path is None
    assert any("not recorded" in s for s in said), said
    assert not w.ledger().exists()
    assert not w.review_file(head).exists()
    assert tracked_snapshot(w.repo) == before


def test_a_running_reviewer_control_records_without_an_operation(reviewworld):
    w = reviewworld
    head = w.commit(name="f.txt", body="ours\n", msg="fix(x): ours")
    path = R.run_review(
        w.repo, "console", head, BRANCH_R, reviewer=_clean_reviewer, log=lambda _m: None
    )
    assert path is not None
    assert pathlib.Path(path).exists()


# --------------------------------------------------------------------------- the commit-policy hook mid-rebase


def _tiny():
    spec = importlib.util.spec_from_file_location(
        "githook_artifacts_tests_for_standdown", HERE / "test_githook_generated_artifacts.py"
    )
    assert spec is not None, "cannot load test_githook_generated_artifacts.py"
    assert spec.loader is not None, "test_githook_generated_artifacts.py has no loader"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _tiny_halted(tmp_path):
    """The generated-artifacts tiny repository, halted mid-rebase on other/z.txt (no artifact reads it), with the real hooks installed."""
    tmod = _tiny()
    t = tmod.Tiny(tmp_path)
    t.build()
    ok = {"COMMIT_POLICY_OK": "1"}
    repo = t.repo
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    write(repo, "other/z.txt", "topic\n")
    commit_all(repo, "topic", **ok)
    git(repo, "checkout", "-q", "--detach", base, **ok)
    write(repo, "other/z.txt", "upstream\n")
    upstream = commit_all(repo, "upstream", **ok)
    git(repo, "checkout", "-q", tmod.GD.BRANCH, **ok)
    assert git(repo, "rebase", upstream, check=False, **ok).returncode != 0
    write(repo, "other/z.txt", "resolved\n")
    git(repo, "add", "--", "other/z.txt")
    assert "rebase-merge" in markers(repo)
    return tmod, t


def _hand_commit(t):
    msg = t.base / "msg"
    msg.write_text("test(fixture): resolved step\n", encoding="utf-8")
    t.marker.unlink(missing_ok=True)
    return git(t.repo, "commit", "-F", str(msg), check=False)


def test_pre_commit_mid_rebase_judges_the_index_not_an_unstaged_input(tmp_path):
    """A consistent input and output are staged; a hook then rewrites the input in the work tree. The commit's own tree is clean, so it passes, and the checker really ran."""
    _tmod, t = _tiny_halted(tmp_path)
    t.write("src/a.txt", "beta\n")
    t.generate()
    git(t.repo, "add", "--", "src/a.txt", "out/gen.txt")
    t.write("src/a.txt", "gamma, unstaged\n")
    proc = _hand_commit(t)
    assert proc.returncode == 0, proc.stderr
    assert t.marker.is_file(), "the checker never ran, so the pass proves nothing"
    assert "verified clean" in proc.stderr
    assert git(t.repo, "show", "HEAD:src/a.txt").stdout == "beta\n"


def test_pre_commit_mid_rebase_control_the_same_edit_staged_is_refused(tmp_path):
    tmod, t = _tiny_halted(tmp_path)
    t.write("src/a.txt", "beta\n")
    t.generate()
    t.write("src/a.txt", "gamma, staged\n")
    git(t.repo, "add", "--", "src/a.txt", "out/gen.txt")
    proc = _hand_commit(t)
    assert proc.returncode != 0
    assert tmod.STALE in proc.stderr


# --------------------------------------------------------------------------- the guard on a base without the stand-down (box R20261123.3)

DISPATCH = REPO_ROOT / ".claude" / "rediacc_hooks" / "dispatch.py"
STANDDOWN_MARK = "would rebase the main checkout onto"
WL_GIT_REL = ".claude/hooks/stop/wl_git.py"


def standdown_repo(tmp_path):
    """A clean main checkout on BRANCH whose own wl_git.py lacks the stand-down, with `refs/remotes/origin/old` (a base without it) and `refs/remotes/origin/main` (a base with it)."""
    repo = tmp_path / "console"
    git(tmp_path, "init", "-q", "-b", BRANCH, str(repo))
    write(repo, WL_GIT_REL, "def rebase_state(root):\n    return None\n")
    write(repo, "f.txt", "base\n")
    old = commit_all(repo, "chore: base without the stand-down")
    write(repo, WL_GIT_REL, "def operation_in_progress(root):\n    return ''\n")
    fixed = commit_all(repo, "fix: the stand-down")
    git(repo, "update-ref", "refs/remotes/origin/old", old)
    git(repo, "update-ref", "refs/remotes/origin/main", fixed)
    git(repo, "reset", "-q", "--hard", old)
    write(repo, "f.txt", "topic\n")
    commit_all(repo, "feat: topic")
    assert git(repo, "status", "--porcelain").stdout == "", "the fixture tree is not clean"
    return repo


def guard(cmd, project, cwd=None):
    """The live guard through the real dispatcher process: `(rc, stderr)`."""
    env = _env()
    env["CLAUDE_PROJECT_DIR"] = str(project)
    proc = subprocess.run(
        [sys.executable, str(DISPATCH), "block_rebase_over_foreign_dirt"],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        cwd=str(cwd or project),
        env=env,
        check=False,
        timeout=120,
    )
    return proc.returncode, proc.stderr


@pytest.mark.parametrize(
    "cmd",
    [
        "git rebase origin/old",
        "git rebase -i origin/old",
        "git rebase --onto origin/old origin/main",
        "git rebase --keep-base origin/old",
        "sh -c 'git rebase origin/old'",
    ],
)
def test_guard_refuses_a_main_checkout_rebase_onto_a_base_without_the_standdown(tmp_path, cmd):
    repo = standdown_repo(tmp_path)
    rc, err = guard(cmd, repo)
    assert rc == 2, (cmd, err)
    assert STANDDOWN_MARK in err, err
    assert "landing tree" in err
    assert "git branch -f" in err
    assert "git submodule update --init" in err
    assert "def operation_in_progress" in err


def test_guard_judges_an_unreadable_onto_against_origin_main(tmp_path):
    """`"origin/${BASE:-main}"` (branch-rebase.md step 3) is judged against origin/main, the base the refusal expires against: allowed while it carries the stand-down, refused once it does not."""
    repo = standdown_repo(tmp_path)
    cmd = 'git rebase "origin/${BASE:-main}"'
    rc, err = guard(cmd, repo)
    assert rc == 0, err
    old = git(repo, "rev-parse", "refs/remotes/origin/old").stdout.strip()
    git(repo, "update-ref", "refs/remotes/origin/main", old)
    rc, err = guard(cmd, repo)
    assert rc == 2, err
    assert STANDDOWN_MARK in err


@pytest.mark.parametrize(
    "cmd",
    [
        "git rebase origin/main",
        "git rebase --onto origin/main origin/old",
        "git rebase --continue",
        "git rebase --abort",
        "git rebase --quit",
        "git rebase no-such-ref",
        "git rebase",
        "git pull --ff-only",
    ],
)
def test_guard_control_a_base_with_the_standdown_or_a_control_verb_is_allowed(tmp_path, cmd):
    """The base carries `def operation_in_progress`, or the command starts no rebase onto a base git can resolve: allowed. An unknown ref and `git rebase` with no upstream configured are git's to refuse."""
    repo = standdown_repo(tmp_path)
    rc, err = guard(cmd, repo)
    assert rc == 0, (cmd, err)


def test_guard_control_continue_and_abort_pass_mid_rebase_onto_the_old_base(tmp_path):
    """Halted mid-rebase onto a base without the stand-down, finishing or undoing it is never refused."""
    repo = standdown_repo(tmp_path)
    git(repo, "checkout", "-q", "--detach", "refs/remotes/origin/old")
    write(repo, "f.txt", "upstream\n")
    upstream = commit_all(repo, "feat: upstream")
    git(repo, "checkout", "-q", BRANCH)
    assert git(repo, "rebase", upstream, check=False).returncode != 0
    assert "rebase-merge" in markers(repo)
    for cmd in ("git rebase --continue", "git rebase --abort"):
        rc, err = guard(cmd, repo)
        assert rc == 0, (cmd, err)


def test_guard_control_a_linked_tree_is_not_probed(tmp_path):
    """The landing tree is the route the refusal names: a rebase there onto the old base is allowed, while the same command in the main checkout is refused."""
    repo = standdown_repo(tmp_path)
    linked = tmp_path / "landing"
    git(repo, "worktree", "add", "-q", "--detach", str(linked))
    rc, err = guard("git rebase origin/old", linked)
    assert rc == 0, err
    rc, err = guard("git rebase origin/old", repo)
    assert rc == 2, err


def test_guard_dirt_is_still_named_first(tmp_path):
    """A peer's modified file refuses with the dirt message, whatever the base holds."""
    repo = standdown_repo(tmp_path)
    write(repo, "f.txt", "peer edit\n")
    rc, err = guard("git rebase origin/main", repo)
    assert rc == 2, err
    assert "would start over uncommitted tracked work" in err
    assert STANDDOWN_MARK not in err
