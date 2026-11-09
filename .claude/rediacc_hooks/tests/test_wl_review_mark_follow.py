"""`wl_review.mark`: a fix is followed across a file move, a test is related by what it tests, and a not-a-bug citation reaches the whole project (worklist #ef4120ad); the reviewer's git calls take no index lock (worklist #65b47fef).

Every world is a real repository. Each refusal has a control that differs by the one fact the rule reads, so a pass is evidence of the rule and not of a loose check.
"""

from __future__ import annotations

import os
import pathlib
import subprocess

import pytest

from rediacc_hooks.tests import wlfix

R = wlfix.import_wl("wl_review")

BRANCH = "1104-1"
ME = "deadbeef"
GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "protocol.file.allow=always", *args],
        capture_output=True,
        text=True,
        env=GIT_ENV,
        check=True,
    ).stdout.strip()


def _commit(repo, message, **files):
    for name, body in files.items():
        path = pathlib.Path(repo) / name.replace("__", "/").replace("_dot_", ".")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        _git(repo, "add", "--", str(path.relative_to(repo)))
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _record(root, sha, file, claim, repo_label="console", fid=None):
    fid = fid or "%s.1" % sha[:8]
    finding = R.Finding(
        id=fid,
        severity="medium",
        file=file,
        line=1,
        anchor="in-diff",
        claim=claim,
        resolution="open",
    )
    review = R.Review(
        sha=sha,
        subject="s",
        repo=repo_label,
        branch=BRANCH,
        reviewed_at="2026-11-04T00:00:00Z",
        model="m",
        verdict="findings",
        findings=[finding],
    )
    R.write_atomic(R.review_path(root, BRANCH, sha), R.render(review))
    return fid


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "--initial-branch=%s" % BRANCH)
    _commit(repo, "seed", seed_dot_txt="seed\n")
    return repo


BODY = "".join("    result_%d = compute_value(%d) + offset_%d\n" % (i, i, i) for i in range(12))


def _moved_world(tmp_path):
    """C1 adds config.py (the reviewed commit), C2 extracts most of it into config_reconcile.py."""
    repo = _repo(tmp_path)
    reviewed = _commit(repo, "feat: config", config_dot_py="def run():\n%s" % BODY)
    _commit(
        repo,
        "refactor: extract",
        config_dot_py="def run():\n    return reconcile()\n",
        config_reconcile_dot_py="def reconcile():\n%s" % BODY,
    )
    return repo, reviewed


def test_a_fix_in_the_file_the_code_moved_to_closes_the_finding(tmp_path):
    repo, reviewed = _moved_world(tmp_path)
    fid = _record(repo, reviewed, "config.py", "the late record lands in a dropped group")
    fix = _commit(
        repo, "fix: reconcile", config_reconcile_dot_py="def reconcile():\n%s# fixed\n" % BODY
    )
    R.mark(repo, BRANCH, fid, "fixed", [fix], ME)
    assert (
        "fixed %s" % fix
        in R.read_review(R.review_path(repo, BRANCH, reviewed))[0].findings[0].resolution
    )


def test_control_a_fix_of_an_unrelated_file_is_refused(tmp_path):
    repo, reviewed = _moved_world(tmp_path)
    fid = _record(repo, reviewed, "config.py", "the late record lands in a dropped group")
    fix = _commit(repo, "fix: elsewhere", other_dot_py="x = 1\n")
    with pytest.raises(ValueError, match=r"does not touch config\.py"):
        R.mark(repo, BRANCH, fid, "fixed", [fix], ME)


def test_a_refusal_without_the_test_flag_names_it_and_a_red_suite_claim_closes_with_it(tmp_path):
    """#634a1e11: a claim about a red suite matches no missing-test wording, so a test-only fix of config.py's test was refused with no word of `--test`. The refusal now names the flag, and the flag closes the finding through the test's name. CONTROL: a refusal that already carries --test does not repeat the hint."""
    repo, reviewed = _moved_world(tmp_path)
    fid = _record(repo, reviewed, "config.py", "the commit lands with the integration suite red")
    fix = _commit(repo, "test: fix the fixture", tests__test_config_pins_dot_py="x = 1\n")
    with pytest.raises(ValueError, match=r"does not touch config\.py") as plain:
        R.mark(repo, BRANCH, fid, "fixed", [fix], ME)
    assert "--test <repo-relative test path>" in str(plain.value)
    R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", "tests/test_config_pins.py"], ME)
    assert (
        "fixed %s" % fix
        in R.read_review(R.review_path(repo, BRANCH, reviewed))[0].findings[0].resolution
    )


def test_control_a_refusal_that_names_a_test_does_not_repeat_the_hint(tmp_path):
    repo, reviewed = _moved_world(tmp_path)
    fid = _record(repo, reviewed, "config.py", "the commit lands with the integration suite red")
    fix = _commit(repo, "test: unrelated", tests__test_other_dot_py="x = 1\n")
    with pytest.raises(ValueError, match="does not") as named:
        R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", "tests/test_other.py"], ME)
    assert "--test <repo-relative test path>" not in str(named.value)


def test_a_refusal_says_when_the_move_search_was_cut_short(tmp_path, monkeypatch):
    """Review 4bcec972.2: with more commits in base..fix than the search reads, the refusal names the cut. CONTROL: a range inside the cap carries no such sentence."""
    repo, reviewed = _moved_world(tmp_path)
    fid = _record(repo, reviewed, "config.py", "the late record lands in a dropped group")
    for n in range(3):
        _commit(repo, "noise %d" % n, **{"noise%d_dot_py" % n: "x = %d\n" % n})
    fix = _commit(repo, "fix: elsewhere", other_dot_py="x = 1\n")
    with pytest.raises(ValueError, match=r"does not touch config\.py") as plain:
        R.mark(repo, BRANCH, fid, "fixed", [fix], ME)
    assert "move search" not in str(plain.value)
    monkeypatch.setattr(R, "MOVE_MAX_COMMITS", 2)
    with pytest.raises(ValueError, match=r"the move search read only the newest 2 of the") as cut:
        R.mark(repo, BRANCH, fid, "fixed", [fix], ME)
    assert "move search" in str(cut.value)


def test_a_two_line_overlap_is_no_move(tmp_path):
    """Three shared meaningful lines is the floor: a neighbour that shares two lines with the anchored file did not receive its code."""
    repo = _repo(tmp_path)
    reviewed = _commit(repo, "feat", a_dot_py="alpha_value = 1\nbeta_value = 2\ngamma_value = 3\n")
    _commit(
        repo,
        "touch",
        a_dot_py="gamma_value = 3\n",
        b_dot_py="alpha_value = 1\nbeta_value = 2\nnew_one = 9\n",
    )
    assert R.moved_successors(repo, "a.py", reviewed, "HEAD") == set()


def test_a_move_is_followed_through_a_second_move(tmp_path):
    repo, reviewed = _moved_world(tmp_path)
    _commit(
        repo,
        "refactor: again",
        config_reconcile_dot_py="def reconcile():\n    return deeper()\n",
        config_deeper_dot_py="def deeper():\n%s" % BODY,
    )
    assert R.moved_successors(repo, "config.py", reviewed, "HEAD") == {
        "config_reconcile.py",
        "config_deeper.py",
    }


TEST_BODY = "def test_follow():\n    assert followByPolls(budget) == 600\n"


def _test_world(tmp_path):
    repo = _repo(tmp_path)
    reviewed = _commit(
        repo,
        "feat: route",
        tests__test_route_dot_py="def test_const():\n    assert BUDGET == 600\n",
    )
    fid = _record(
        repo,
        reviewed,
        "tests/test_route.py",
        "The budget is pinned only by a constant; no test drives followByPolls, so the follow would still give up early.",
    )
    return repo, fid


def test_a_named_test_that_exercises_what_the_claim_names_closes_a_missing_test_finding(tmp_path):
    repo, fid = _test_world(tmp_path)
    fix = _commit(repo, "fix: drive it", tests__test_harness_dot_py=TEST_BODY)
    R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", "tests/test_harness.py"], ME)


def test_control_without_the_test_flag_the_unrelated_name_is_refused(tmp_path):
    repo, fid = _test_world(tmp_path)
    fix = _commit(repo, "fix: drive it", tests__test_harness_dot_py=TEST_BODY)
    with pytest.raises(ValueError, match="does not touch"):
        R.mark(repo, BRANCH, fid, "fixed", [fix], ME)


def test_control_a_named_test_that_names_nothing_of_the_claim_is_refused(tmp_path):
    repo, fid = _test_world(tmp_path)
    fix = _commit(
        repo,
        "fix: unrelated",
        tests__test_harness_dot_py="def test_x():\n    assert other_thing() == 1\n",
    )
    with pytest.raises(ValueError, match="does not touch"):
        R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", "tests/test_harness.py"], ME)


def test_control_the_claim_name_in_a_test_the_fix_did_not_add_is_refused(tmp_path):
    """The name must be on a line the fix ADDED to the test: an old line that already carried it answers nothing."""
    repo, fid = _test_world(tmp_path)
    _commit(repo, "test: old", tests__test_harness_dot_py=TEST_BODY)
    fix = _commit(
        repo, "fix: other", tests__test_harness_dot_py=TEST_BODY + "\ndef test_y():\n    assert 1\n"
    )
    with pytest.raises(ValueError, match="does not touch"):
        R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", "tests/test_harness.py"], ME)


def test_a_claim_that_is_not_about_a_missing_test_gets_no_content_relation(tmp_path):
    """The by-content relation serves a missing-test claim only: a code finding is not closed by a test that happens to name its identifier."""
    repo = _repo(tmp_path)
    reviewed = _commit(repo, "feat", route_dot_py="x = 1\n")
    fid = _record(repo, reviewed, "route.py", "followByPolls gives up after the wrong budget")
    fix = _commit(repo, "fix: test only", tests__test_harness_dot_py=TEST_BODY)
    with pytest.raises(ValueError, match="does not touch"):
        R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", "tests/test_harness.py"], ME)


def _submodule_world(tmp_path):
    sub_src = tmp_path / "sub_src"
    sub_src.mkdir()
    _git(sub_src, "init", "-q", "--initial-branch=%s" % BRANCH)
    sub_sha = _commit(sub_src, "feat: renet", pkg__precondition_dot_go="package pkg\n")
    sup = _repo(tmp_path)
    _git(sup, "submodule", "add", "-q", str(sub_src), "private/sub")
    _commit(
        sup,
        "chore: plan",
        agent__plans__PLAN_dot_md="one\ntwo\nthree\n",
        packages__cli__t_dot_ts="a\nb\n",
    )
    return sup, sup / "private" / "sub", sub_sha


def _evidence(text):
    return "read against the current tree: %s and the rest holds" % text


@pytest.mark.parametrize(
    "cite",
    [
        "agent/plans/PLAN.md:2",
        "packages/cli/t.ts:1",
        "agent/plans/PLAN.md:3-3.",
        "(packages/cli/t.ts:2)",
    ],
)
def test_a_submodule_finding_may_cite_a_console_path(tmp_path, cite):
    sup, _sub, sub_sha = _submodule_world(tmp_path)
    fid = _record(sup, sub_sha, "pkg/precondition.go", "claim", repo_label="private/sub")
    R.mark(sup, BRANCH, fid, "not-a-bug", [_evidence(cite)], ME)


@pytest.mark.parametrize(
    "cite",
    [
        "agent/plans/PLAN.md:99",
        "agent/plans/MISSING.md:1",
        "../outside.md:1",
        "agent/plans/PLAN.md",
    ],
)
def test_control_a_console_citation_that_does_not_exist_still_refuses(tmp_path, cite):
    sup, _sub, sub_sha = _submodule_world(tmp_path)
    fid = _record(sup, sub_sha, "pkg/precondition.go", "claim", repo_label="private/sub")
    with pytest.raises(ValueError, match="must cite a path:line"):
        R.mark(sup, BRANCH, fid, "not-a-bug", [_evidence(cite)], ME)


def test_a_console_finding_may_cite_a_submodule_sha(tmp_path):
    sup, _sub, sub_sha = _submodule_world(tmp_path)
    review_sha = _git(sup, "rev-parse", "HEAD")
    fid = _record(sup, review_sha, "packages/cli/t.ts", "claim")
    R.mark(
        sup, BRANCH, fid, "not-a-bug", [_evidence("the gitlink holds it, sha %s" % sub_sha[:8])], ME
    )


def test_control_a_sha_in_no_project_checkout_still_refuses(tmp_path):
    sup, _sub, _sub_sha = _submodule_world(tmp_path)
    review_sha = _git(sup, "rev-parse", "HEAD")
    fid = _record(sup, review_sha, "packages/cli/t.ts", "claim")
    with pytest.raises(ValueError, match="must cite a path:line"):
        R.mark(sup, BRANCH, fid, "not-a-bug", [_evidence("the gitlink holds it, sha 5dead49d")], ME)


def test_control_a_sha_of_a_commit_off_the_submodule_branch_refuses(tmp_path):
    sup, sub, _sub_sha = _submodule_world(tmp_path)
    _git(sub, "checkout", "-q", "--detach", "HEAD")
    off = _commit(sub, "other", z_dot_txt="z\n")
    _git(sub, "reset", "-q", "--hard", "HEAD^")
    review_sha = _git(sup, "rev-parse", "HEAD")
    fid = _record(sup, review_sha, "packages/cli/t.ts", "claim")
    with pytest.raises(ValueError, match="must cite a path:line"):
        R.mark(
            sup, BRANCH, fid, "not-a-bug", [_evidence("the gitlink holds it, sha %s" % off[:8])], ME
        )


def _index_stamp(repo):
    return (pathlib.Path(repo) / ".git" / "index").stat().st_mtime_ns


def test_the_reads_leave_the_index_untouched_where_a_plain_status_rewrites_it(tmp_path):
    """Control first: a plain `git status` refreshes a stale index (the lock a lead's `git cherry-pick` then collides with); `R.git` does not."""
    repo = _repo(tmp_path)
    target = repo / "seed.txt"

    stamps = iter(range(1_000_000_000_000_000_000, 1_000_000_100_000_000_000, 10**10))

    def stale():
        when = next(stamps)
        os.utime(target, ns=(when, when))

    stale()
    before = _index_stamp(repo)
    os.utime(repo / ".git" / "index", ns=(before - 10**10, before - 10**10))
    before = _index_stamp(repo)
    subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        check=True,
        env=GIT_ENV,
        capture_output=True,
    )
    assert _index_stamp(repo) != before, "control: a plain status must refresh the stale index"
    stale()
    before = _index_stamp(repo)
    os.utime(repo / ".git" / "index", ns=(before - 10**10, before - 10**10))
    before = _index_stamp(repo)
    rc, _out = R.git(repo, "status", "--porcelain", "--untracked-files=all")
    assert rc == 0
    assert _index_stamp(repo) == before


def test_the_detached_reviewer_runs_with_optional_locks_off(tmp_path, monkeypatch):
    seen = {}

    class Proc:
        pid = 4242

    def fake_popen(_argv, **kw):
        seen.update(kw)
        return Proc()

    repo = _repo(tmp_path)
    monkeypatch.setattr(R.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(R, "acquire_lock", lambda *_a, **_k: True)
    monkeypatch.setattr(R, "set_lock_pid", lambda *_a, **_k: None)
    monkeypatch.setattr(R, "state_dir", lambda: tmp_path)
    (tmp_path / "logs").mkdir()
    assert R.spawn_detached(repo, repo, "a" * 40, BRANCH) == 4242
    assert seen["env"]["GIT_OPTIONAL_LOCKS"] == "0"


def test_diff_lines_files_a_removed_sql_comment_under_its_own_file():
    """Review 4bcec972.1: a removed `-- comment` line is `--- comment` inside a hunk, and read as a file header it renamed the file every later removed line was filed under. CONTROL: the real headers of two files still set each file."""
    text = (
        "diff --git a/q.sql b/q.sql\n"
        "--- a/q.sql\n"
        "+++ b/q.sql\n"
        "@@ -1,2 +0,0 @@\n"
        "--- the old reporting query comment\n"
        "-SELECT name, total FROM orders_by_customer;\n"
        "diff --git a/r.sql b/r.sql\n"
        "--- a/r.sql\n"
        "+++ b/r.sql\n"
        "@@ -0,0 +1 @@\n"
        "+SELECT name, total FROM orders_by_customer;\n"
    )
    removed, added = R._diff_lines(text)
    assert set(removed) == {"q.sql"}, removed
    assert "SELECT name, total FROM orders_by_customer;" in removed["q.sql"]
    assert "-- the old reporting query comment" in removed["q.sql"]
    assert added == {"r.sql": ["SELECT name, total FROM orders_by_customer;"]}


def _import_world(tmp_path, anchored, body="export const x = 1;\n"):
    repo = _repo(tmp_path)
    reviewed = _commit(repo, "feat", **{anchored.replace("/", "__").replace(".", "_dot_"): body})
    fid = _record(repo, reviewed, anchored, "The size limit is read from the wrong header.")
    return repo, fid


@pytest.mark.parametrize(
    ("anchored", "test", "body"),
    [
        (
            "src/blob-storage.service.ts",
            "tests/blob-list.test.ts",
            "import { size } from '../src/blob-storage.service';\ntest('a', () => size());\n",
        ),
        (
            "src/onboarding.py",
            "tests/test_enterprise_add.py",
            "from src.onboarding import add\n\n\ndef test_a():\n    add()\n",
        ),
    ],
)
def test_a_named_test_that_imports_the_anchored_module_closes_the_finding(
    tmp_path, anchored, test, body
):
    """#d8f3ba65: the test's file name does not carry the anchored stem and the claim is no missing-test claim; the import in its added lines relates it."""
    repo, fid = _import_world(tmp_path, anchored)
    fix = _commit(repo, "test: cover it", **{test.replace("/", "__").replace(".", "_dot_"): body})
    R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", test], ME)


@pytest.mark.parametrize(
    ("anchored", "test", "body"),
    [
        (
            "src/blob-storage.service.ts",
            "tests/blob-list.test.ts",
            "import { other } from '../src/other.service';\ntest('a', () => other());\n",
        ),
        (
            "src/onboarding.py",
            "tests/test_enterprise_add.py",
            "from src.billing import add\n\n\ndef test_a():\n    add()  # unlike onboarding\n",
        ),
    ],
)
def test_control_an_unrelated_test_is_still_refused(tmp_path, anchored, test, body):
    """The import must name the anchored module: another import, or a bare mention on a non-import line, relates nothing."""
    repo, fid = _import_world(tmp_path, anchored)
    fix = _commit(repo, "test: other", **{test.replace("/", "__").replace(".", "_dot_"): body})
    with pytest.raises(ValueError, match="does not touch"):
        R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", test], ME)


def test_control_a_same_stem_import_from_another_directory_is_refused(tmp_path):
    """Review fc93df02.1: `../other/index` shares the bare stem `index` with `src/foo/index.ts` and is another module; `../src/foo/index` is the anchored one (control)."""
    anchored = "src/foo/index.ts"
    repo, fid = _import_world(tmp_path, anchored)
    test = "tests/other-thing.test.ts"
    key = test.replace("/", "__").replace(".", "_dot_")
    fix = _commit(repo, "test: other", **{key: "import { x } from '../src/other/index';\n"})
    with pytest.raises(ValueError, match="does not touch"):
        R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", test], ME)
    (tmp_path / "ok").mkdir()
    repo, fid = _import_world(tmp_path / "ok", anchored)
    fix = _commit(repo, "test: foo", **{key: "import { x } from '../src/foo/index';\n"})
    R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", test], ME)


def test_a_bare_identifier_on_an_import_line_is_no_module(tmp_path):
    """Review a27ac34b.1: `import { index } from '../other/thing'` names the identifier `index`, not the module `src/foo/index.ts`; `from index import x` and `'index'` are modules (control)."""
    anchored = "src/foo/index.ts"
    repo, fid = _import_world(tmp_path, anchored)
    test = "tests/other-thing.test.ts"
    key = test.replace("/", "__").replace(".", "_dot_")
    fix = _commit(repo, "test: other", **{key: "import { index } from '../other/thing';\n"})
    with pytest.raises(ValueError, match="does not touch"):
        R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", test], ME)
    (tmp_path / "ok").mkdir()
    repo, fid = _import_world(tmp_path / "ok", anchored)
    fix = _commit(repo, "test: foo", **{key: "vi.mock('index');\n"})
    R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", test], ME)


def test_control_an_importing_test_without_the_test_flag_is_refused(tmp_path):
    """The import relation serves a named test only; a fix that touches an importing test unnamed stays refused."""
    repo, fid = _import_world(tmp_path, "src/onboarding.py")
    fix = _commit(
        repo,
        "test: cover it",
        tests__test_enterprise_add_dot_py="from src.onboarding import add\n\n\ndef test_a():\n    add()\n",
    )
    with pytest.raises(ValueError, match="does not touch"):
        R.mark(repo, BRANCH, fid, "fixed", [fix], ME)
