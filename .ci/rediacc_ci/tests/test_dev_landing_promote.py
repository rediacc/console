"""Leases and promotion across the two trees (PLAN-two-track-merge-dev LT16), in throwaway repositories.

The promotion fixture is a bare origin, a main clone holding the development branch stacked on the landing branch, a linked landing tree on the landing branch bound by the landing record, and a rebase-merge simulated by a second clone that cherry-picks the landing commits onto origin/main after one unrelated commit. The lease fixture is `test_dev_worktree_lease`'s, with a landing tree beside it.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from rediacc_ci.dev import landing_promote as promote_mod
from rediacc_ci.dev import worktree_lease as lease
from rediacc_ci.dev import worktree_spike as spike
from rediacc_ci.tests import test_dev_worktree_lease as base

LANDING = "1120-1"
DEV = "1120-2"
NEXT = "1120-3"
TODAY = "1120"


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


# ---- promotion ---------------------------------------------------------------


class Two:
    def __init__(self, root, main, landing, merger, landing_shas, dev_tip):
        self.root, self.main, self.landing, self.merger = root, main, landing, merger
        self.landing_shas, self.dev_tip = landing_shas, dev_tip


def build_two(base_dir, *, picks=2, dev_conflict=False, absorb_dev=False):
    """The two-tree promotion fixture. `picks` landing commits reach origin/main; `dev_conflict` makes the first development commit collide with main's unrelated commit; `absorb_dev` puts the first development commit's change on main inside a larger commit, so the rebase drops it as empty."""
    origin = base_dir / "origin.git"
    spike.must(base_dir, "init", "-q", "--bare", "-b", "main", str(origin))
    main = base_dir / "console"
    spike.must(base_dir, "clone", "-q", str(origin), str(main))
    commit(main, "base.txt")
    spike.must(main, "push", "-q", "-u", "origin", "main")
    spike.must(main, "switch", "-q", "-c", LANDING)
    landing_shas = [commit(main, "l1.txt"), commit(main, "l2.txt")]
    spike.must(main, "push", "-q", "origin", LANDING)
    spike.must(main, "switch", "-q", "-c", DEV)
    commit(main, "other.txt" if dev_conflict else "d1.txt", "dev side\n", "D1")
    commit(main, "d2.txt", None, "D2")
    landing = base_dir / "console-landing"
    spike.must(main, "worktree", "add", "-q", str(landing), LANDING)
    policy().write_landing_record(str(main), str(landing), LANDING)

    merger = base_dir / "merger"
    spike.must(base_dir, "clone", "-q", str(origin), str(merger))
    commit(merger, "other.txt", "main side\n", "unrelated")
    if absorb_dev:
        spike.write(merger / "d1.txt", "dev side\n")
        commit(merger, "extra.txt", None, "carries d1 and more")
    spike.must(merger, "fetch", "-q", "origin", LANDING)
    for sha in landing_shas[:picks]:
        spike.must(merger, "cherry-pick", sha)
    spike.must(merger, "push", "-q", "origin", "main")
    return Two(base_dir, main, landing, merger, landing_shas, tip(main))


@pytest.fixture
def two(tmp_path):
    return build_two(tmp_path.resolve())


def fake_gh(state="MERGED", pr=None, fail=False):
    pr = {"number": 42, "isDraft": True} if pr is None else pr

    def gh(args, _cwd):
        if fail or args[:2] != ["pr", "view"]:
            return 1, ""
        if args[2] == LANDING and args[4] == "state":
            return 0, json.dumps({"state": state})
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


def subjects(tree, rng):
    return spike.must(tree, "log", "--format=%s", rng).splitlines()


def test_promote_happy_path_moves_the_branch_and_cuts_the_next(two, capfd):
    line = run_promote(two.main)
    assert line == "gh pr ready 42"
    assert spike.out(two.landing, "symbolic-ref", "--short", "HEAD") == DEV
    assert spike.out(two.main, "symbolic-ref", "--short", "HEAD") == NEXT
    assert tip(two.main) == tip(two.main, "refs/remotes/origin/main")
    assert record_of(two.main) == {"path": str(two.landing), "branch": DEV}
    # The landing copies dropped as absorbed: only the development commits sit above origin/main.
    assert subjects(two.main, "origin/main..%s" % DEV) == ["D2", "D1"]
    assert "2 carried, 2 absorbed" in capfd.readouterr().err


def test_promote_from_the_landing_root_resolves_the_main_checkout(two):
    assert run_promote(two.landing) == "gh pr ready 42"
    assert spike.out(two.main, "symbolic-ref", "--short", "HEAD") == NEXT
    assert spike.out(two.landing, "symbolic-ref", "--short", "HEAD") == DEV


def test_promote_without_a_pr_number_names_the_branch(two):
    assert run_promote(two.main, gh=fake_gh(pr={})) == "gh pr ready %s" % DEV


@pytest.mark.parametrize("where", ["main", "landing"])
def test_promote_refuses_a_dirty_tree_in_either_checkout(two, where):
    spike.write(getattr(two, where) / "scratch.txt", "work\n")
    with pytest.raises(promote_mod.PromoteRefusedError, match="is dirty"):
        run_promote(two.main)
    untouched(two)


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


def test_land_control_a_development_lease_prints_the_plain_pick(pair):
    made = base.run_lease(pair.root, "--name", "ld2")
    assert made.returncode == 0, made.stderr
    sha = base.committed(pathlib.Path(made.stdout.strip()), "dev-pick.txt")
    result = base.run_land(pair.root, "ld2")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["git cherry-pick -x %s" % sha]


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
