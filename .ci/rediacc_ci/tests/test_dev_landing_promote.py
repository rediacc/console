"""Leases and promotion across the two trees (PLAN-two-track-merge-dev LT16), in throwaway repositories.

The promotion fixture is a bare origin, a main clone holding the development branch stacked on the landing branch, one submodule with a bare origin of its own, a linked landing tree on the landing branch bound by the landing record with that submodule checked out, and a rebase-merge simulated by a second clone that cherry-picks the landing commits onto origin/main after one unrelated commit. The development branch's submodule commit sits on the development name in the main checkout's submodule tree only, so the landing tree has to fetch it from there. The lease fixture is `test_dev_worktree_lease`'s, with a landing tree beside it.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from rediacc_ci.dev import landing_promote as promote_mod
from rediacc_ci.dev import worktree_lease as lease
from rediacc_ci.dev import worktree_spike as spike
from rediacc_ci.tests import test_dev_worktree_lease as base

LANDING = "1120-1"
DEV = "1120-2"
NEXT = "1120-3"
TODAY = "1120"
SUB = "sub"


@pytest.fixture(scope="module", autouse=True)
def hermetic_git(tmp_path_factory):
    patch = pytest.MonkeyPatch()
    for key, value in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.test",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.test",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "HOME": str(tmp_path_factory.mktemp("home")),
        "WORKLIST_SESSION_ID": "feedface99",
    }.items():
        patch.setenv(key, value)
    patch.delenv("COMMIT_POLICY_OK", raising=False)
    yield
    patch.undo()


def policy():
    return spike.load_commit_policy()


def commit(tree, name, content=None, subject=None):
    spike.write(tree / name, content or "%s\n" % name)
    spike.must(tree, "add", "--", name)
    spike.must(tree, "commit", "--no-gpg-sign", "-q", "-m", subject or name)
    return spike.must(tree, "rev-parse", "HEAD")


def tip(tree, ref="HEAD"):
    return spike.must(tree, "rev-parse", ref)


def branch_of(tree):
    return spike.out(tree, "symbolic-ref", "-q", "--short", "HEAD")


# ---- promotion ---------------------------------------------------------------


class Two:
    def __init__(self, root, main, landing, merger, landing_shas, dev_tip, sub_link):
        self.root, self.main, self.landing, self.merger = root, main, landing, merger
        self.landing_shas, self.dev_tip, self.sub_link = landing_shas, dev_tip, sub_link
        self.landing_sub = landing / SUB
        self.landing_sub_head = tip(self.landing_sub)


def build_two(base_dir, *, picks=2, dev_conflict=False, absorb_dev=False, dev_work=True):
    """The two-tree promotion fixture. `picks` landing commits reach origin/main; `dev_conflict` makes the first development commit collide with main's unrelated commit; `absorb_dev` puts the first development commit's change on main inside a larger commit, so the rebase drops it as empty; `dev_work=False` leaves the development branch at the landing tip, with no commit of its own."""
    sub_origin = base_dir / "sub.git"
    spike.must(base_dir, "init", "-q", "--bare", "-b", "main", str(sub_origin))
    seed = base_dir / "sub-seed"
    spike.must(base_dir, "clone", "-q", str(sub_origin), str(seed))
    commit(seed, "s0.txt")
    spike.must(seed, "push", "-q", "origin", "HEAD:main")
    origin = base_dir / "origin.git"
    spike.must(base_dir, "init", "-q", "--bare", "-b", "main", str(origin))
    main = base_dir / "console"
    spike.must(base_dir, "clone", "-q", str(origin), str(main))
    spike.must(
        main, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub_origin), SUB
    )
    commit(main, "base.txt")
    spike.must(main, "push", "-q", "-u", "origin", "main")
    spike.must(main, "switch", "-q", "-c", LANDING)
    landing_shas = [commit(main, "l1.txt"), commit(main, "l2.txt")]
    spike.must(main, "push", "-q", "origin", LANDING)
    spike.must(main, "switch", "-q", "-c", DEV)
    sub_link = None
    if dev_work:
        commit(main, "other.txt" if dev_conflict else "d1.txt", "dev side\n", "D1")
        # The development branch's submodule commit sits on the development name in the main checkout's submodule tree, pushed nowhere.
        spike.must(main / SUB, "switch", "-q", "-c", DEV)
        sub_link = commit(main / SUB, "s1.txt")
        spike.must(main, "add", "--", SUB)
        commit(main, "d2.txt", None, "D2")
    landing = base_dir / "console-landing"
    spike.must(main, "worktree", "add", "-q", str(landing), LANDING)
    spike.must(landing, "-c", "protocol.file.allow=always", "submodule", "update", "-q", "--init")
    policy().write_landing_record(str(main), str(landing), LANDING)

    merger = base_dir / "merger"
    spike.must(base_dir, "clone", "-q", str(origin), str(merger))
    commit(merger, "other.txt", "main side\n", "unrelated")
    if absorb_dev:
        spike.write(merger / "d1.txt", "dev side\n")
        spike.must(merger, "add", "--", "d1.txt")
        commit(merger, "extra.txt", None, "carries d1 and more")
    spike.must(merger, "fetch", "-q", "origin", LANDING)
    for sha in landing_shas[:picks]:
        spike.must(merger, "cherry-pick", sha)
    spike.must(merger, "push", "-q", "origin", "main")
    return Two(base_dir, main, landing, merger, landing_shas, tip(main), sub_link)


@pytest.fixture
def two(tmp_path):
    return build_two(tmp_path.resolve())


MERGED_SHA = "f" * 40
GREEN = {"status": "completed", "conclusion": "success"}


def fake_gh(state="MERGED", pr=None, fail=False, runs=None, merged=MERGED_SHA):
    """gh answers for promotion. `runs` maps a workflow file to the run list gh prints for it at the merged sha (newest first); both release workflows default to one green run."""
    pr = {"number": 42, "isDraft": True} if pr is None else pr
    lists = {"ci.yml": [GREEN], "cd-release-edge.yml": [GREEN], **(runs or {})}

    def gh(args, _cwd):
        if fail:
            return 1, ""
        if args[:2] == ["run", "list"]:
            workflow = args[args.index("--workflow") + 1]
            assert args[args.index("--commit") + 1] == merged
            rows = lists.get(workflow)
            if rows is None:
                return 1, ""
            return 0, json.dumps(
                [{"databaseId": 900 + i, "headSha": merged, **r} for i, r in enumerate(rows)]
            )
        if args[:2] != ["pr", "view"]:
            return 1, ""
        if args[2] == LANDING and args[4] == "state,mergeCommit":
            return 0, json.dumps({"state": state, "mergeCommit": {"oid": merged}})
        if args[2] == DEV and args[4] == "number,isDraft":
            return 0, json.dumps(pr)
        return 1, ""

    return gh


def next_name(root, today):
    return policy().next_branch_name(str(root), today, gh=False)


def run_promote(root, **extra):
    kwargs = {"gh": fake_gh(), "today": TODAY, "next_name": next_name, **extra}
    return promote_mod.promote(root, **kwargs)


def record_of(main):
    return json.loads((main / ".git" / policy().LANDING_RECORD_NAME).read_text(encoding="utf-8"))


def untouched(two):
    """Nothing moved: the development branch, the record and both checkouts are where the fixture left them."""
    assert tip(two.main, "refs/heads/%s" % DEV) == two.dev_tip
    assert record_of(two.main) == {"path": str(two.landing), "branch": LANDING}
    assert spike.out(two.main, "symbolic-ref", "--short", "HEAD") == DEV
    assert spike.out(two.landing, "symbolic-ref", "--short", "HEAD") == LANDING
    assert not (two.main / ".git" / "rebase-merge").exists()
    assert tip(two.landing_sub) == two.landing_sub_head
    assert branch_of(two.landing_sub) == ""


def subjects(tree, rng):
    return spike.must(tree, "log", "--format=%s", rng).splitlines()


def test_promote_happy_path_moves_the_branch_and_cuts_the_next(two, capfd):
    line = run_promote(two.main)
    assert line == "gh pr ready 42"
    assert spike.out(two.landing, "symbolic-ref", "--short", "HEAD") == DEV
    assert spike.out(two.main, "symbolic-ref", "--short", "HEAD") == NEXT
    assert record_of(two.main) == {"path": str(two.landing), "branch": DEV}
    # The landing copies dropped as absorbed: only the development commits sit above origin/main.
    assert subjects(two.main, "origin/main..%s" % DEV) == ["D2", "D1"]
    assert "2 carried, 2 absorbed" in capfd.readouterr().err


def test_promote_cuts_the_next_branch_stacked_on_the_new_landing_tip(two):
    run_promote(two.main)
    assert tip(two.main) == tip(two.main, "refs/heads/%s" % DEV)
    assert tip(two.main) != tip(two.main, "refs/remotes/origin/main")
    # wl_stack is the reader: right after promotion the development tree is current against the new landing branch.
    st = lease._hook_module("wl_stack").stack_state(
        two.main, fetch=False, pr_merged=lambda _root, _branch: False
    )
    assert (st.state, st.landing, st.development) == ("current", DEV, NEXT), st


def test_promote_moves_the_landing_submodule_tree_to_the_promoted_name(two):
    run_promote(two.main)
    assert branch_of(two.landing_sub) == DEV
    assert tip(two.landing_sub) == two.sub_link
    assert tip(two.landing, "HEAD:%s" % SUB) == two.sub_link
    assert spike.out(two.landing, "status", "--porcelain") == ""


def test_promote_control_a_landing_submodule_branch_behind_the_gitlink_moves_forward(two):
    spike.must(two.landing_sub, "branch", "-q", DEV, two.landing_sub_head)
    assert run_promote(two.main) == "gh pr ready 42"
    assert branch_of(two.landing_sub) == DEV
    assert tip(two.landing_sub) == two.sub_link


def test_promote_refuses_a_landing_submodule_branch_the_gitlink_lacks(two):
    spike.must(two.landing_sub, "switch", "-q", "-c", DEV)
    stray = commit(two.landing_sub, "stray.txt")
    spike.must(two.landing_sub, "switch", "-q", "--detach", two.landing_sub_head)
    with pytest.raises(promote_mod.PromoteRefusedError, match="does not contain"):
        run_promote(two.main)
    untouched(two)
    assert tip(two.landing_sub, "refs/heads/%s" % DEV) == stray


def test_promote_refuses_a_dirty_landing_submodule_tree(two):
    # A modified tracked file in the submodule tree refuses; untracked files no longer count (ASKED:2026-11-22T18:55Z).
    tracked = spike.must(two.landing_sub, "ls-files").splitlines()[0]
    spike.write(two.landing_sub / tracked, "changed\n")
    with pytest.raises(promote_mod.PromoteRefusedError, match="submodule tree sub of the landing"):
        run_promote(two.main)
    untouched(two)


def dev_sha(two, subject):
    return spike.must(two.main, "log", "-1", "--format=%H", "--grep=^%s$" % subject, DEV)


def test_promote_names_the_commits_the_rebase_left_unreviewed(two, capfd):
    run_promote(two.main)
    err = capfd.readouterr().err
    for subject in ("D1", "D2"):
        assert "%s: UNREVIEWED %s" % (DEV, dev_sha(two, subject)[:12]) in err, err
    assert "2 unreviewed" in err


def test_promote_control_a_review_record_carried_by_patch_id_is_not_named(two, capfd):
    d1 = tip(two.main, "%s~1" % DEV)
    pid = lease._hook_module("wl_review").patch_id(str(two.main), d1)
    assert pid
    rel = "agent/reviews/%s/%s.md" % (DEV, d1)
    spike.write(two.main / rel, "# review\nPatch-Id: %s\n" % pid)
    spike.must(two.main, "add", "--", rel)
    spike.must(two.main, "commit", "--no-gpg-sign", "-q", "-m", "review of D1")
    two.dev_tip = tip(two.main)
    run_promote(two.main)
    err = capfd.readouterr().err
    assert "UNREVIEWED %s" % dev_sha(two, "D2")[:12] in err, err
    assert "UNREVIEWED %s" % dev_sha(two, "D1")[:12] not in err, err
    assert "1 unreviewed" in err


def test_promote_from_the_landing_root_resolves_the_main_checkout(two):
    assert run_promote(two.landing) == "gh pr ready 42"
    assert spike.out(two.main, "symbolic-ref", "--short", "HEAD") == NEXT
    assert spike.out(two.landing, "symbolic-ref", "--short", "HEAD") == DEV


def test_promote_without_a_pr_number_names_the_branch(two):
    assert run_promote(two.main, gh=fake_gh(pr={})) == "gh pr ready %s" % DEV


@pytest.mark.parametrize("where", ["main", "landing"])
def test_promote_refuses_a_dirty_tree_in_either_checkout(two, where):
    # A modified TRACKED file refuses; untracked files no longer count (operator ruling ASKED:2026-11-22T18:55Z).
    tree = getattr(two, where)
    tracked = spike.must(tree, "ls-files").splitlines()[0]
    spike.write(tree / tracked, "changed\n")
    with pytest.raises(promote_mod.PromoteRefusedError, match="is dirty"):
        run_promote(two.main)
    untouched(two)


def test_an_untracked_file_of_other_work_does_not_block_promotion(two):
    spike.write(two.main / "agent" / "other-session" / "notes.md", "theirs\n")
    assert run_promote(two.main) == "gh pr ready 42"
    assert (two.main / "agent" / "other-session" / "notes.md").read_text() == "theirs\n"


def test_promote_ignores_the_machine_local_settings_file(two):
    """.claude/settings.local.json is never committed, so it alone does not make the main checkout dirty."""
    spike.write(two.main / ".claude" / "settings.local.json", "{}\n")
    assert run_promote(two.main) == "gh pr ready 42"


def test_the_settings_file_is_ignored_when_it_is_the_first_dirty_row(two):
    """A tracked, modified settings.local.json sorts first; the stripped porcelain output must not defeat the exemption."""
    target = two.main / ".claude" / "settings.local.json"
    spike.write(target, "{}\n")
    spike.must(two.main, "add", "-f", "--", ".claude/settings.local.json")
    spike.must(
        two.main, "commit", "-qm", "track local settings", "--", ".claude/settings.local.json"
    )
    spike.write(target, '{"changed": true}\n')
    assert run_promote(two.main) == "gh pr ready 42"


@pytest.mark.parametrize(
    ("gh", "why"),
    [(fake_gh(state="OPEN"), "is OPEN, not MERGED"), (fake_gh(fail=True), "gh could not say")],
)
def test_promote_refuses_a_landing_pr_that_is_not_merged(two, gh, why):
    with pytest.raises(promote_mod.PromoteRefusedError, match=why):
        run_promote(two.main, gh=gh)
    untouched(two)


def test_promote_refuses_with_no_landing_record(two):
    (two.main / ".git" / policy().LANDING_RECORD_NAME).unlink()
    with pytest.raises(promote_mod.PromoteRefusedError, match="no landing tree"):
        run_promote(two.main)
    assert tip(two.main, "refs/heads/%s" % DEV) == two.dev_tip


def test_promote_refuses_a_main_checkout_off_the_development_branch(two):
    spike.must(two.main, "switch", "-q", "--detach")
    with pytest.raises(promote_mod.PromoteRefusedError, match="holds no development branch"):
        run_promote(two.main)


def test_promote_refuses_a_landing_commit_missing_from_main(tmp_path):
    two = build_two(tmp_path.resolve(), picks=1)
    with pytest.raises(promote_mod.PromoteRefusedError, match="1 landing commit"):
        run_promote(two.main)
    untouched(two)


def test_promote_aborts_a_conflicted_rebase(tmp_path):
    two = build_two(tmp_path.resolve(), dev_conflict=True)
    with pytest.raises(promote_mod.PromoteRefusedError, match="aborted"):
        run_promote(two.main)
    untouched(two)


def test_promote_refuses_a_rebase_that_loses_a_development_commit(tmp_path):
    two = build_two(tmp_path.resolve(), absorb_dev=True)
    with pytest.raises(promote_mod.PromoteRefusedError, match="lost development commits"):
        run_promote(two.main)
    untouched(two)


def test_promote_refuses_a_gitlink_no_source_holds(two):
    # The main checkout's submodule tree loses the gitlink commit (its status told to ignore the submodule, so the tree reads clean) and the submodule origin never had it.
    sub = two.main / SUB
    spike.must(two.main, "config", "submodule.%s.ignore" % SUB, "all")
    spike.must(sub, "switch", "-q", "--detach", two.landing_sub_head)
    spike.must(sub, "branch", "-q", "-D", DEV)
    spike.must(sub, "reflog", "expire", "--expire=now", "--all")
    spike.must(sub, "gc", "-q", "--prune=now")
    with pytest.raises(promote_mod.PromoteRefusedError, match="cannot reach %s's gitlink" % DEV):
        run_promote(two.main)
    untouched(two)


def test_promote_a_failed_cut_names_what_moved_and_the_command_left(two):
    # The next name is taken (the old landing branch still exists), so the cut fails after the landing tree took the development branch (review 37d8950c.1).
    with pytest.raises(promote_mod.PromoteRefusedError) as raised:
        run_promote(two.main, next_name=lambda _root, _today: LANDING)
    text = str(raised.value)
    assert "already holds %s and the landing record binds it" % DEV in text, text
    assert "git -C %s switch --no-track -c %s %s" % (two.main, LANDING, DEV) in text, text
    assert record_of(two.main) == {"path": str(two.landing), "branch": DEV}
    assert branch_of(two.landing) == DEV
    assert branch_of(two.landing_sub) == DEV


def test_promote_a_failed_submodule_switch_names_what_is_left(two, monkeypatch):
    real_git = promote_mod.spike.git

    def git(cwd, *args, **kwargs):
        if pathlib.Path(cwd) == two.landing_sub and args[:1] == ("switch",):
            return subprocess.CompletedProcess(["git", *args], 1, "", "fatal: refused here")
        return real_git(cwd, *args, **kwargs)

    monkeypatch.setattr(promote_mod.spike, "git", git)
    with pytest.raises(promote_mod.PromoteRefusedError) as raised:
        run_promote(two.main)
    text = str(raised.value)
    assert "the submodule tree sub could not take %s" % DEV in text, text
    assert "fatal: refused here" in text, text
    assert "git -C %s switch --no-track -C %s %s" % (two.landing_sub, DEV, two.sub_link) in text
    assert "git -C %s switch --no-track -c %s %s" % (two.main, NEXT, DEV) in text, text
    assert record_of(two.main) == {"path": str(two.landing), "branch": DEV}


# ---- the D3 premises (PLAN-simple-two-tree-loop B3) ---------------------------


RED = {"status": "completed", "conclusion": "failure"}
PENDING = {"status": "in_progress", "conclusion": ""}


@pytest.mark.parametrize(
    ("runs", "why"),
    [
        ({"ci.yml": [RED]}, "Console CI on main .* is failure"),
        ({"cd-release-edge.yml": [PENDING]}, "the edge release .* is in_progress"),
        ({"cd-release-edge.yml": []}, "has no cd-release-edge.yml run"),
        # The newest run decides: an older green run under a newer red one is still red.
        ({"ci.yml": [RED, GREEN]}, "Console CI on main .* is failure"),
        ({"ci.yml": None}, "gh could not list the ci.yml runs"),
    ],
)
def test_promote_refuses_a_release_that_is_not_fully_green(two, runs, why):
    with pytest.raises(promote_mod.PromoteRefusedError, match=why):
        run_promote(two.main, gh=fake_gh(runs=runs))
    untouched(two)


def test_promote_control_a_rerun_turned_green_is_admitted(two):
    assert run_promote(two.main, gh=fake_gh(runs={"ci.yml": [GREEN, RED]})) == "gh pr ready 42"


def test_promote_refuses_a_merged_pr_gh_names_no_merge_commit_for(two):
    with pytest.raises(promote_mod.PromoteRefusedError, match="no merge commit"):
        run_promote(two.main, gh=fake_gh(merged=""))
    untouched(two)


PLAN = "PLAN-fixture.md"
WRITER_SIG = "aaaa1111"


def plan_commit(two, boxes):
    """A development commit adding agent/plans/PLAN-fixture.md with `boxes` and a Plan-Box trailer naming it; the fixture's tip moves with it."""
    rel = "agent/plans/%s" % PLAN
    body = "# PLAN: fixture\nStatus: approved\n\n## Tasks\n\n%s\n" % "\n".join(boxes)
    spike.write(two.main / rel, body)
    spike.must(two.main, "add", "--", rel)
    message = "feat: plan work\n\nPlan-Box: %s#%s clauses=all" % (PLAN, WRITER_SIG)
    spike.must(two.main, "commit", "--no-gpg-sign", "-q", "-m", message)
    two.dev_tip = tip(two.main)


def test_promote_refuses_a_plan_with_an_open_writer_box(two):
    plan_commit(
        two,
        [
            "- [x] W1 [writer] The first writer box, done.",
            "- [ ] W2 [writer] The second writer box, still open.",
            "- [ ] V1 [live] The live run, open.",
        ],
    )
    with pytest.raises(promote_mod.PromoteRefusedError, match="not code-complete: 1 open"):
        run_promote(two.main)
    untouched(two)


def test_promote_control_a_plan_with_only_a_live_box_open_is_admitted(two):
    plan_commit(
        two,
        [
            "- [x] W1 [writer] The first writer box, done.",
            "- [x] W2 [writer] The second writer box, done.",
            "- [ ] V1 [live] The live run, open for the landing tree.",
            "- [ ] L1 [lead] The lead's measurement, open.",
        ],
    )
    assert run_promote(two.main) == "gh pr ready 42"
    assert spike.out(two.landing, "symbolic-ref", "--short", "HEAD") == DEV


def test_promote_refuses_a_named_plan_the_checkout_lacks(two):
    commit(two.main, "d3.txt", None, "feat: d3\n\nPlan-Box: PLAN-absent.md#bbbb2222 clauses=all")
    two.dev_tip = tip(two.main)
    with pytest.raises(promote_mod.PromoteRefusedError, match=r"PLAN-absent\.md"):
        run_promote(two.main)
    untouched(two)


def test_promote_with_no_development_commits_idles(tmp_path, capfd):
    two = build_two(tmp_path.resolve(), dev_work=False)
    # The release premise is never read: a red main would refuse if it were.
    assert run_promote(two.main, gh=fake_gh(runs={"ci.yml": [RED]})) is None
    assert "the landing tree idles and no PR is opened" in capfd.readouterr().err
    untouched(two)


def test_promote_cmd_idle_exits_zero_with_nothing_on_stdout(monkeypatch, capfd):
    monkeypatch.setattr(promote_mod, "promote", lambda _root: None)
    assert promote_mod.cmd_promote([]) == 0
    assert capfd.readouterr().out == ""


def test_promote_cmd_rejects_an_argument(capfd):
    assert promote_mod.cmd_promote(["--bogus"]) == 1
    assert "Unknown option" in capfd.readouterr().err


# ---- leases across trees -----------------------------------------------------

BRANCH = base.BRANCH  # 0101-1, the landing branch here
DEV_BRANCH = "0101-2"


class Pair:
    def __init__(self, repo, landing):
        self.repo, self.landing = repo, landing
        self.root = repo.root


def make_pair(tmp_path, *, record=True):
    """`make_repo`'s console moved onto a development branch stacked on 0101-1, with a landing tree on 0101-1."""
    repo = base.make_repo(tmp_path.resolve())
    root = repo.root
    spike.must(root, "switch", "-q", "-c", DEV_BRANCH)
    commit(root, "dev.txt", None, "dev: on the development branch")
    landing = root.parent / "console-landing"
    spike.must(root, "worktree", "add", "-q", str(landing), BRANCH)
    if record:
        policy().write_landing_record(str(root), str(landing), BRANCH)
    return Pair(repo, landing)


@pytest.fixture
def pair(tmp_path):
    return make_pair(tmp_path)


def lease_record(root, name):
    return json.loads((root / ".git" / lease.RECORD_DIR / ("%s.json" % name)).read_text())


def test_lease_hook_from_the_landing_root_cuts_at_the_landing_tip(pair):
    done = base.run_worktree_hook(
        pair.landing, "lease-hook", {"name": "agent-l1", "session_id": "abcd1234ffff"}
    )
    assert done.returncode == 0, done.stderr
    tree = pathlib.Path(done.stdout.strip().splitlines()[-1])
    assert tree == pair.root / spike.HOLDER / "agent-l1"
    assert tip(tree) == tip(pair.root, "refs/heads/%s" % BRANCH)
    record = lease_record(pair.root, "agent-l1")
    assert (record["tree"], record["cut_from"]) == ("landing", BRANCH)


def test_lease_hook_control_with_no_record_the_landing_root_is_refused(tmp_path):
    pair = make_pair(tmp_path, record=False)
    done = base.run_worktree_hook(pair.landing, "lease-hook", {"name": "agent-l2"})
    assert done.returncode != 0
    assert "not a main checkout" in done.stderr


def test_gc_hook_from_the_landing_root_removes_a_clean_lease(pair):
    made = base.run_lease(pair.root, "--name", "gone-l", "--owner", "cli")
    assert made.returncode == 0, made.stderr
    tree = pathlib.Path(made.stdout.strip())
    done = base.run_worktree_hook(pair.landing, "gc-hook", {"worktree_path": str(tree)})
    assert done.returncode == 0, done.stderr
    assert not tree.exists()


def test_lease_tree_landing_cuts_at_the_landing_tip(pair):
    made = base.run_lease(pair.root, "--name", "tl", "--tree", "landing")
    assert made.returncode == 0, made.stderr
    tree = pathlib.Path(made.stdout.strip())
    assert tip(tree) == tip(pair.root, "refs/heads/%s" % BRANCH)
    record = lease_record(pair.root, "tl")
    assert (record["tree"], record["cut_from"]) == ("landing", BRANCH)


def test_lease_control_without_tree_cuts_at_the_development_tip(pair):
    made = base.run_lease(pair.root, "--name", "td")
    assert made.returncode == 0, made.stderr
    tree = pathlib.Path(made.stdout.strip())
    assert tip(tree) == tip(pair.root, "refs/heads/%s" % DEV_BRANCH)
    record = lease_record(pair.root, "td")
    assert (record["tree"], record["cut_from"]) == ("development", DEV_BRANCH)


def test_lease_tree_landing_with_no_record_is_refused(tmp_path):
    pair = make_pair(tmp_path, record=False)
    made = base.run_lease(pair.root, "--name", "tn", "--tree", "landing")
    assert made.returncode == 1
    assert "no landing tree" in made.stderr
    assert made.stdout == ""


def test_lease_tree_rejects_an_unknown_value(pair):
    made = base.run_lease(pair.root, "--name", "tx", "--tree", "elsewhere")
    assert made.returncode == 1
    assert "--tree needs one of" in made.stderr


def test_land_of_a_landing_lease_picks_into_the_landing_tree(pair, tmp_path):
    made = base.run_lease(pair.root, "--name", "ll", "--tree", "landing")
    assert made.returncode == 0, made.stderr
    tree = pathlib.Path(made.stdout.strip())
    sha = base.committed(tree, "land-me.txt")
    result = base.run_land(pair.root, "ll")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines == ["git -C %s cherry-pick -x %s" % (pair.landing, sha)]
    dev_before = tip(pair.root)
    for finished in base.run_printed(pair.root, lines, tmp_path):
        assert finished.returncode == 0, finished.stderr
    assert (pair.landing / "land-me.txt").is_file()
    assert tip(pair.root) == dev_before
    rows = {row["id"]: row for row in lease.lease_rows(pair.root)}
    assert rows["ll"]["unlanded"] == {}


def test_leases_judge_a_landing_lease_against_the_landing_tip(pair):
    # The landing branch moves past what the development branch holds, so the development tip would read the landing commit as the lease's own.
    commit(pair.landing, "landing-only.txt", None, "landing: ahead of development")
    made = base.run_lease(pair.root, "--name", "la", "--tree", "landing")
    assert made.returncode == 0, made.stderr
    rows = {row["id"]: row for row in lease.lease_rows(pair.root)}
    assert rows["la"]["unlanded"] == {}


def test_land_control_a_development_lease_prints_the_plain_pick(pair):
    made = base.run_lease(pair.root, "--name", "ld2")
    assert made.returncode == 0, made.stderr
    sha = base.committed(pathlib.Path(made.stdout.strip()), "dev-pick.txt")
    result = base.run_land(pair.root, "ld2")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["git cherry-pick -x %s" % sha]


def test_land_refuses_a_submodule_commit_the_landing_tree_cannot_hold(pair):
    # The fixture's landing tree leaves the submodule uninitialized, so a submodule commit has nowhere to land; skipping it would drop it silently.
    made = base.run_lease(pair.root, "--name", "ls", "--tree", "landing")
    assert made.returncode == 0, made.stderr
    base.sub_commit(pathlib.Path(made.stdout.strip()), "sub-only.txt")
    result = base.run_land(pair.root, "ls")
    assert result.returncode == 1
    assert "is not checked out in %s" % pair.landing in result.stderr
    assert result.stdout == ""


def test_gc_labels_the_landing_tree_landing(pair):
    done = base.run_gc(pair.root)
    assert done.returncode == 0, done.stderr
    row = base.row_of(done.stdout, "console-landing")
    assert "landing: " in row, done.stdout
    assert "gc never touches" in row, done.stdout
    assert pair.landing.is_dir()


def test_gc_control_an_unbound_linked_tree_stays_rule_1(tmp_path):
    pair = make_pair(tmp_path, record=False)
    done = base.run_gc(pair.root)
    row = base.row_of(done.stdout, "console-landing")
    assert "rule 1" in row, done.stdout
    assert "landing: " not in row, done.stdout


def test_the_release_is_judged_at_the_main_tip_when_it_contains_the_merge(two):
    """A hotfix on top of the merge: the merge's own release stays red, main's tip released green with it inside."""
    tip = spike.must(two.main, "rev-parse", "origin/main")
    assert promote_mod._release_sha(two.main, tip) == tip
    # A development commit main does not contain is judged as itself, as is an unknown sha.
    dev_tip = spike.must(two.main, "rev-parse", DEV)
    assert promote_mod._release_sha(two.main, dev_tip) == dev_tip
    # Control: a sha main does not contain is judged as itself.
    assert promote_mod._release_sha(two.main, MERGED_SHA) == MERGED_SHA


def test_record_paths_and_hook_ledgers_are_not_dirt():
    globs = [
        ("agent/reviews/**", ()),
        ("agent/plans/**/*.md", ()),
        ("agent/worklist/*.jsonl", ("agent/worklist/epics.jsonl",)),
    ]
    globs = [*globs, ("agent/ledgers/*.jsonl", ())]
    assert promote_mod._is_record("agent/plans/QUEUE.md", globs)
    assert promote_mod._is_record("agent/reviews/1121-1/clean.jsonl", globs)
    assert promote_mod._is_record("agent/ledgers/ops-health.jsonl", globs)
    # Controls: an excepted record and a code file still count as dirt.
    assert not promote_mod._is_record("agent/worklist/epics.jsonl", globs)
    assert not promote_mod._is_record(".ci/rediacc_ci/dev/landing.py", globs)
