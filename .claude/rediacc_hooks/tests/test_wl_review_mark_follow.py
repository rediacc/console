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
        _commit(
            repo, "noise %d" % n, config_dot_py="def run():\n    return reconcile()\n# %d\n" % n
        )
    fix = _commit(repo, "fix: elsewhere", other_dot_py="x = 1\n")
    with pytest.raises(ValueError, match=r"does not touch config\.py") as plain:
        R.mark(repo, BRANCH, fid, "fixed", [fix], ME)
    assert "move search" not in str(plain.value)
    monkeypatch.setattr(R, "MOVE_MAX_COMMITS", 2)
    with pytest.raises(ValueError, match=r"the move search read only the newest 2 of the") as cut:
        R.mark(repo, BRANCH, fid, "fixed", [fix], ME)
    assert "move search" in str(cut.value)


def test_a_move_older_than_the_cap_is_found_past_commits_that_never_touch_the_file(
    tmp_path, monkeypatch
):
    """bf0bded8.2: the move sat behind more unrelated commits than the search reads, so a fix in the file the code moved to was refused. Commits that never touch a source are skipped, so the cap counts only commits that could move code. CONTROL: an unrelated fix past the same noise is still refused, with no cut-short sentence (only one commit in the range touches config.py)."""
    monkeypatch.setattr(R, "MOVE_MAX_COMMITS", 2)
    repo, reviewed = _moved_world(tmp_path)
    fid = _record(repo, reviewed, "config.py", "the late record lands in a dropped group")
    for n in range(3):
        _commit(repo, "noise %d" % n, **{"noise%d_dot_py" % n: "x = %d\n" % n})
    other = _commit(repo, "fix: elsewhere", other_dot_py="x = 1\n")
    with pytest.raises(ValueError, match=r"does not touch config\.py") as refused:
        R.mark(repo, BRANCH, fid, "fixed", [other], ME)
    assert "move search" not in str(refused.value)
    fix = _commit(
        repo, "fix: reconcile", config_reconcile_dot_py="def reconcile():\n%s# fixed\n" % BODY
    )
    R.mark(repo, BRANCH, fid, "fixed", [fix], ME)
    assert (
        "fixed %s" % fix
        in R.read_review(R.review_path(repo, BRANCH, reviewed))[0].findings[0].resolution
    )


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


def test_a_python_from_import_of_the_stem_is_a_module_even_with_a_quoted_comment(tmp_path):
    """Review 2e26138f.2/.3: `from index import add # "note"` imports the module `index`; a quote elsewhere on the line does not disable the unquoted rule, while `import index from '../other/thing'` (a JS default-import identifier) stays refused."""
    anchored = "src/foo/index.py"
    repo, fid = _import_world(tmp_path, anchored)
    test = "tests/test_other_thing.py"
    key = test.replace("/", "__").replace(".", "_dot_")
    fix = _commit(repo, "test: other", **{key: "import index from '../other/thing'\n"})
    with pytest.raises(ValueError, match="does not touch"):
        R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", test], ME)
    (tmp_path / "ok").mkdir()
    repo, fid = _import_world(tmp_path / "ok", anchored)
    fix = _commit(repo, "test: foo", **{key: 'from index import add  # "note"\n'})
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


def test_a_source_named_with_glob_characters_is_matched_literally(tmp_path, monkeypatch):
    """Review ab7e9e28.2: a bare pathspec is a glob, so a source `[id].py` also matched `i.py` and `d.py` (git tries the literal path first, so it still matched itself) and their commits were read and counted as the source's own. CONTROL: the source itself is still found and traced."""
    repo = _repo(tmp_path)
    reviewed = _commit(repo, "feat", **{"[id].py": "def run():\n%s" % BODY})
    _commit(
        repo,
        "refactor: extract",
        **{
            "[id].py": "def run():\n    return reconcile()\n",
            "moved.py": "def reconcile():\n%s" % BODY,
        },
    )
    assert R.moved_successors(repo, "[id].py", reviewed, "HEAD") == {"moved.py"}
    monkeypatch.setattr(R, "MOVE_MAX_COMMITS", 2)
    for n in range(3):
        _commit(repo, "neighbour %d" % n, **{"i.py": "x = %d\n" % n})
    assert R.move_search_note(str(repo), reviewed, "HEAD", "[id].py") == ""
    # bf83ba68.1: with the cap at 2, a glob read of `[id].py` fills the log with the 3 newer `i.py` commits and loses the move.
    assert R.moved_successors(repo, "[id].py", reviewed, "HEAD") == {"moved.py"}


def test_the_cut_short_note_counts_the_commits_of_a_found_successor(tmp_path, monkeypatch):
    """Review ab7e9e28.1: from round 2 the log reads the commits touching every found successor, so a successor with more commits than the cap cut the search short while the anchored file's own count stayed under it and the refusal read as complete. CONTROL: a successor within the cap leaves the note empty."""
    repo, reviewed = _moved_world(tmp_path)
    monkeypatch.setattr(R, "MOVE_MAX_COMMITS", 3)
    successors = {"config_reconcile.py"}
    assert R.move_search_note(str(repo), reviewed, "HEAD", "config.py", successors) == ""
    for n in range(3):
        _commit(
            repo,
            "noise %d" % n,
            config_reconcile_dot_py="def reconcile():\n%s# %d\n" % (BODY, n),
        )
    assert R.move_search_note(str(repo), reviewed, "HEAD", "config.py") == ""
    note = R.move_search_note(str(repo), reviewed, "HEAD", "config.py", successors)
    assert "read only the newest 3 of the 4 commits" in note


# --------------------------------------------------------------------------- a reviewed commit's copy on the branch (finding #48c72397)
# Measured 2026-11-24 on 1121-1: after a rebase onto main, a reviewed commit's copy sat 730 commits below the fix, past the old 400-commit walk, and 45 genuine fixes were refused as "does not descend". The copy is now searched over `merge-base(origin/main, HEAD)..HEAD` by stable patch-id and by the `(cherry picked from commit <sha>)` line, in the repository the record names; a reviewed commit with no copy on the branch closes as `not-a-bug` with a verdict the tool computes.


@pytest.fixture
def _branch_wide_search():
    # The old lookup walked a fixed depth below the fix (`REBASED_COPY_DEPTH`); it is gone, so there is no depth left to shrink (cd54ad27.2). The fixture states that, and clears the patch-id cache so each test computes its own copies.
    assert not hasattr(R, "REBASED_COPY_DEPTH"), "a fixed-depth walk is back in wl_review"
    R.__dict__.get("_COPY_PATCH_IDS", {}).clear()


def _fillers(repo, n=3):
    for i in range(n):
        _commit(repo, "chore: filler %d" % i, **{"filler_%d_dot_txt" % i: "%d\n" % i})


def _copy_record(root, sha, pid, repo_label="console"):
    fid = "%s.1" % sha[:8]
    finding = R.Finding(
        id=fid,
        severity="medium",
        file="f.py",
        line=1,
        anchor="in-diff",
        claim="the value is computed from the wrong offset",
        resolution="open",
    )
    review = R.Review(
        sha=sha,
        subject="s",
        repo=repo_label,
        branch=BRANCH,
        patch_id=pid or "(none)",
        reviewed_at="2026-11-24T00:00:00Z",
        model="m",
        verdict="findings",
        findings=[finding],
    )
    R.write_atomic(R.review_path(root, BRANCH, sha), R.render(review))
    return fid


def _copy_resolution(root, sha):
    return R.read_review(R.review_path(root, BRANCH, sha))[0].findings[0].resolution


def _copy_init(repo):
    repo.mkdir()
    _git(repo, "init", "-q", "--initial-branch=main")
    _commit(repo, "seed", seed_dot_txt="seed\n")


def _publish_main(repo):
    _git(repo, "update-ref", "refs/remotes/origin/main", "main")


def _rebased_world(tmp_path):
    """BRANCH carries the reviewed commit, main moves, BRANCH is rebased onto it: the record names a sha the branch no longer holds."""
    repo = tmp_path / "repo"
    _copy_init(repo)
    _publish_main(repo)
    _git(repo, "checkout", "-q", "-b", BRANCH)
    reviewed = _commit(repo, "feat: f", f_dot_py="a = 1\nb = 2\n")
    pid = R.patch_id(repo, reviewed)
    _git(repo, "checkout", "-q", "main")
    moved = _commit(repo, "chore(main): move main", main_dot_txt="m\n")
    _publish_main(repo)
    _git(repo, "checkout", "-q", BRANCH)
    _git(repo, "rebase", "-q", "main")
    copy = _git(repo, "rev-parse", "HEAD")
    assert copy != reviewed
    return repo, reviewed, pid, copy, moved


@pytest.mark.usefixtures("_branch_wide_search")
def test_a_fix_far_above_a_rebased_copy_is_admitted_by_patch_id(tmp_path):
    repo, reviewed, pid, _copy, _moved = _rebased_world(tmp_path)
    fid = _copy_record(repo, reviewed, pid)
    _fillers(repo)
    fix = _commit(repo, "fix: offset", f_dot_py="a = 1\nb = 3\n")
    R.mark(repo, BRANCH, fid, "fixed", [fix], ME)
    assert _copy_resolution(repo, reviewed).startswith("fixed %s | %s " % (fix, ME))


@pytest.mark.usefixtures("_branch_wide_search")
def test_control_a_fix_that_does_not_descend_from_the_copy_is_refused(tmp_path):
    repo, reviewed, pid, copy, moved = _rebased_world(tmp_path)
    fid = _copy_record(repo, reviewed, pid)
    with pytest.raises(
        ValueError, match=r"does not descend from the reviewed commit .*%s" % copy[:12]
    ):
        R.mark(repo, BRANCH, fid, "fixed", [moved], ME)
    assert _copy_resolution(repo, reviewed) == "open"


def _cherry_world(tmp_path, with_line):
    """The reviewed commit lives on a lease's detached line; BRANCH carries a copy whose content (so patch-id) differs, as a conflict-resolved `cherry-pick -x` leaves it."""
    repo = tmp_path / "repo"
    _copy_init(repo)
    _publish_main(repo)
    _git(repo, "checkout", "-q", "-b", BRANCH)
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "--detach", base)
    reviewed = _commit(repo, "feat: f", f_dot_py="a = 1\nb = 2\n")
    pid = R.patch_id(repo, reviewed)
    _git(repo, "checkout", "-q", BRANCH)
    message = "feat: f"
    if with_line:
        message += "\n\n(cherry picked from commit %s)" % reviewed
    copy = _commit(repo, message, f_dot_py="a = 1\nb = 2\nc = 0\n")
    assert R.patch_id(repo, copy) != pid
    return repo, reviewed, pid, copy


@pytest.mark.usefixtures("_branch_wide_search")
def test_a_cherry_picked_copy_is_found_by_its_x_line(tmp_path):
    repo, reviewed, pid, _copy = _cherry_world(tmp_path, with_line=True)
    fid = _copy_record(repo, reviewed, pid)
    _fillers(repo)
    fix = _commit(repo, "fix: offset", f_dot_py="a = 1\nb = 3\nc = 0\n")
    R.mark(repo, BRANCH, fid, "fixed", [fix], ME)
    assert _copy_resolution(repo, reviewed).startswith("fixed %s" % fix)


@pytest.mark.usefixtures("_branch_wide_search")
def test_control_without_the_x_line_the_commit_is_not_on_the_branch(tmp_path):
    repo, reviewed, pid, _copy = _cherry_world(tmp_path, with_line=False)
    fid = _copy_record(repo, reviewed, pid)
    fix = _commit(repo, "fix: offset", f_dot_py="a = 1\nb = 3\nc = 0\n")
    with pytest.raises(ValueError, match="is not on this branch"):
        R.mark(repo, BRANCH, fid, "fixed", [fix], ME)


@pytest.mark.usefixtures("_branch_wide_search")
def test_a_submodule_record_finds_the_copy_in_the_submodule(tmp_path):
    sub_src = tmp_path / "sub_src"
    _copy_init(sub_src)
    _git(sub_src, "checkout", "-q", "-b", BRANCH)
    reviewed = _commit(sub_src, "feat: f", f_dot_py="a = 1\nb = 2\n")
    pid = R.patch_id(sub_src, reviewed)
    _git(sub_src, "checkout", "-q", "main")
    _commit(sub_src, "chore(main): move main", main_dot_txt="m\n")
    sup = tmp_path / "sup"
    _copy_init(sup)
    _git(sup, "checkout", "-q", "-b", BRANCH)
    _git(sup, "submodule", "add", "-q", str(sub_src), "private/sub")
    sub = sup / "private" / "sub"
    _git(sub, "checkout", "-q", "-B", BRANCH, "origin/%s" % BRANCH)
    _git(sub, "rebase", "-q", "origin/main")
    assert _git(sub, "rev-parse", "HEAD") != reviewed
    fid = _copy_record(sup, reviewed, pid, repo_label="private/sub")
    _fillers(sub)
    fix = _commit(sub, "fix: offset", f_dot_py="a = 1\nb = 3\n")
    R.mark(sup, BRANCH, fid, "fixed", [fix], ME)
    assert _copy_resolution(sup, reviewed).startswith("fixed %s" % fix)


def _dropped_world(tmp_path):
    repo = tmp_path / "repo"
    _copy_init(repo)
    _publish_main(repo)
    _git(repo, "checkout", "-q", "-b", BRANCH)
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "--detach", base)
    reviewed = _commit(repo, "feat: f", f_dot_py="a = 1\nb = 2\n")
    pid = R.patch_id(repo, reviewed)
    _git(repo, "checkout", "-q", BRANCH)
    _commit(repo, "feat: other work", g_dot_py="x = 1\n")
    return repo, reviewed, pid


@pytest.mark.usefixtures("_branch_wide_search")
def test_a_dropped_commit_closes_as_not_a_bug_with_a_computed_verdict(tmp_path):
    repo, reviewed, pid = _dropped_world(tmp_path)
    fid = _copy_record(repo, reviewed, pid)
    fix = _commit(repo, "fix: offset", f_dot_py="a = 1\nb = 3\n")
    with pytest.raises(ValueError, match=r"is not on this branch.*not-a-bug"):
        R.mark(repo, BRANCH, fid, "fixed", [fix], ME)
    R.mark(repo, BRANCH, fid, "not-a-bug", [], ME)
    resolution = _copy_resolution(repo, reviewed)
    assert resolution.startswith(
        "not-a-bug | reviewed commit %s is not on this branch" % reviewed[:8]
    ), resolution
    assert R.RESOLUTION_BY_KIND["not-a-bug"].match(resolution)


@pytest.mark.usefixtures("_branch_wide_search")
def test_control_a_commit_on_the_branch_still_needs_not_a_bug_evidence(tmp_path):
    repo, reviewed, pid, _copy, _moved = _rebased_world(tmp_path)
    fid = _copy_record(repo, reviewed, pid)
    with pytest.raises(ValueError, match="20 characters"):
        R.mark(repo, BRANCH, fid, "not-a-bug", [], ME)


def test_branch_copies_refuses_a_sha_missing_from_the_repo(tmp_path):
    """Review cd54ad27.1: a reviewed sha the repo does not hold makes merge-base exit 128, a failed read that must raise rather than read as "not on the branch"."""
    repo = _repo(tmp_path)
    with pytest.raises(ValueError, match="exit 128"):
        R.branch_copies(str(repo), "0123456789abcdef0123456789abcdef01234567", None)


def test_branch_copies_answers_an_ancestor_without_raising(tmp_path):
    """Silent control: an ancestor sha answers itself."""
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert R.branch_copies(str(repo), head, None) == [head]


# ---- #ee9de1f9: a move spread across commits, and a named test of the code's new home ----------

TS_BODY = "".join(
    "  const budget_%d = windowMs - (Date.now() - startedAt) + %d;\n" % (i, i) for i in range(12)
)
OLD_CALL = "workers/mcp/src/call.ts"
NEW_CALL = "packages/shared/src/mcp-host/call.ts"
RELOCATE = "packages/shared/src/mcp-host/__tests__/relocate.test.ts"


def _write(repo, message, files=(), remove=()):
    """One commit writing `files` ({repo-relative path: body}) and removing `remove`; paths are used verbatim (`__tests__` included)."""
    for name, body in dict(files).items():
        path = pathlib.Path(repo) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        _git(repo, "add", "--", name)
    for name in remove:
        _git(repo, "rm", "-q", "--", name)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _spread_world(tmp_path, spread=True):
    """The reviewed commit adds call.ts; one commit copies its code into the shared package without touching the original, and a later one deletes the original, so no single commit holds both halves of the move. With `spread=False` one commit moves it (aaf114bc's shape: the original left as a stub, deleted by a later commit)."""
    repo = _repo(tmp_path)
    body = "export function callTool() {\n%s}\n" % TS_BODY
    reviewed = _write(repo, "feat: call", {OLD_CALL: body})
    first = {NEW_CALL: body, "packages/shared/src/mcp-host/executor.ts": "export const x = 1;\n"}
    if not spread:
        first[OLD_CALL] = "export { callTool } from '@rediacc/shared/mcp-host/call';\n"
    _write(repo, "refactor: copy the handler into shared", first)
    _write(repo, "refactor: drop the worker copy", remove=[OLD_CALL])
    return repo, reviewed


def test_a_move_spread_across_two_commits_is_followed(tmp_path):
    """#ee9de1f9: the copy and the removal sit in two commits, so the per-commit match sees neither; the range's net diff does. CONTROL: executor.ts, added beside the copy with none of its lines, is no successor."""
    repo, reviewed = _spread_world(tmp_path)
    assert R.moved_successors(repo, OLD_CALL, reviewed, "HEAD") == {NEW_CALL}


@pytest.mark.parametrize("spread", [True, False])
def test_a_named_test_that_imports_the_moved_module_closes_the_finding(tmp_path, spread):
    """#ee9de1f9: relocate.test.ts already imported '../call.js' before the fix added its case; its name carries nothing of the old path, yet it tests the module the code moved to. The one-commit move isolates the import relation from the spread-move search."""
    repo, reviewed = _spread_world(tmp_path, spread)
    head = "import { callTool } from '../call.js';\n"
    _write(repo, "test: relocate", {RELOCATE: head + "it('a', () => callTool());\n"})
    fid = _record(repo, reviewed, OLD_CALL, "The lookup budget ignores the start time.")
    fix = _write(
        repo,
        "test: the budget after time has passed",
        {RELOCATE: head + "it('a', () => callTool());\nit('b', () => callTool());\n"},
    )
    R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", RELOCATE], ME)
    assert (
        "fixed %s" % fix
        in R.read_review(R.review_path(repo, BRANCH, reviewed))[0].findings[0].resolution
    )


def test_control_a_named_test_of_another_module_beside_the_new_home_is_refused(tmp_path):
    repo, reviewed = _spread_world(tmp_path)
    head = "import { executor } from '../executor.js';\n"
    _write(repo, "test: relocate", {RELOCATE: head + "it('a', () => executor);\n"})
    fid = _record(repo, reviewed, OLD_CALL, "The lookup budget ignores the start time.")
    fix = _write(
        repo,
        "test: executor",
        {RELOCATE: head + "it('a', () => executor);\nit('b', () => executor);\n"},
    )
    with pytest.raises(ValueError, match=r"does not touch workers/mcp/src/call\.ts"):
        R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", RELOCATE], ME)


CALLER = "packages/cli/src/services/renet/renet-execution.ts"
DEFINER = "packages/cli/src/services/preview/touch.ts"
USER = "packages/cli/src/services/preview/slot-ops.ts"
DEFINER_TEST = "packages/cli/src/services/preview/__tests__/touch.test.ts"
DEFINER_BODY = (
    "export function previewTouchOption(machine?: string) {\n"
    "  if (!machine) throw new ValidationError('machine');\n"
    "  return { previewTouch: { machine } };\n"
    "}\n"
    "export function touch(machine: string) {\n  return machine;\n}\n"
)


def _definer_world(tmp_path):
    """#eff552fc: the finding is anchored on the caller of `previewTouchOption`; the symbol is defined in touch.ts, which the reviewed commit also adds."""
    repo = _repo(tmp_path)
    reviewed = _write(
        repo,
        "feat: pin the renet",
        {
            DEFINER: DEFINER_BODY,
            CALLER: (
                "import { previewTouchOption, touch } from '../preview/touch.js';\n"
                "export function acquireRemoteRenet(machineName?: string) {\n"
                "  touch(machineName ?? '');\n"
                "  return { ...previewTouchOption(machineName) };\n}\n"
            ),
            USER: (
                "import { previewTouchOption } from './touch.js';\n"
                "export const slot = (m: string) => previewTouchOption(m);\n"
            ),
            DEFINER_TEST: "it('a', () => 1);\n",
        },
    )
    return repo, reviewed


def _definer_fix(repo, module=DEFINER, body=None):
    body = body or DEFINER_BODY.replace("if (!machine) throw", "if (!machine && replacing) throw")
    return _write(
        repo,
        "fix: refuse only at a replacement",
        {module: body, DEFINER_TEST: "it('a', () => 1);\nit('b', () => 2);\n"},
    )


def _closed(repo, reviewed, fix):
    resolution = R.read_review(R.review_path(repo, BRANCH, reviewed))[0].findings[0].resolution
    return ("fixed %s" % fix) in resolution


def test_a_fix_of_the_module_defining_a_claimed_symbol_closes_the_callers_finding(tmp_path):
    repo, reviewed = _definer_world(tmp_path)
    fid = _record(
        repo,
        reviewed,
        CALLER,
        "previewTouchOption throws a ValidationError whenever machineName is undefined, on every acquireRemoteRenet call.",
    )
    fix = _definer_fix(repo)
    R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", DEFINER_TEST], ME)
    assert _closed(repo, reviewed, fix)


def test_a_backtick_quoted_symbol_names_the_definition_too(tmp_path):
    """`touch` is too plain for the bare-identifier rule (no case change, under 6 characters); quoted, the claim names it."""
    repo, reviewed = _definer_world(tmp_path)
    fid = _record(repo, reviewed, CALLER, "`touch()` runs with an empty machine name.")
    fix = _definer_fix(repo, body=DEFINER_BODY.replace("return machine;", "return machine || 'x';"))
    R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", DEFINER_TEST], ME)
    assert _closed(repo, reviewed, fix)


def test_control_a_claim_naming_no_symbol_the_fixed_module_defines_is_refused(tmp_path):
    """acquireRemoteRenet is defined in the caller, not in touch.ts, so a fix of touch.ts answers nothing about it."""
    repo, reviewed = _definer_world(tmp_path)
    fid = _record(
        repo, reviewed, CALLER, "acquireRemoteRenet provisions before the replacement is decided."
    )
    fix = _definer_fix(repo)
    with pytest.raises(ValueError, match=r"does not touch packages/cli/src/services/renet"):
        R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", DEFINER_TEST], ME)


def test_control_a_plain_unquoted_word_names_no_definition(tmp_path):
    repo, reviewed = _definer_world(tmp_path)
    fid = _record(repo, reviewed, CALLER, "the touch runs with an empty machine name.")
    fix = _definer_fix(repo, body=DEFINER_BODY.replace("return machine;", "return machine || 'x';"))
    with pytest.raises(ValueError, match=r"does not touch packages/cli/src/services/renet"):
        R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", DEFINER_TEST], ME)


def test_control_a_module_that_only_calls_the_symbol_is_no_definition(tmp_path):
    repo, reviewed = _definer_world(tmp_path)
    fid = _record(
        repo, reviewed, CALLER, "previewTouchOption throws whenever machineName is unset."
    )
    fix = _definer_fix(
        repo,
        module=USER,
        body="import { previewTouchOption } from './touch.js';\n"
        "export const slot = (m: string) => previewTouchOption(m || 'x');\n",
    )
    with pytest.raises(ValueError, match=r"does not touch packages/cli/src/services/renet"):
        R.mark(repo, BRANCH, fid, "fixed", [fix, "--test", DEFINER_TEST], ME)


def test_control_the_definition_rule_needs_a_named_test(tmp_path):
    repo, reviewed = _definer_world(tmp_path)
    fid = _record(
        repo, reviewed, CALLER, "previewTouchOption throws whenever machineName is unset."
    )
    fix = _definer_fix(repo)
    with pytest.raises(ValueError, match=r"does not touch packages/cli/src/services/renet"):
        R.mark(repo, BRANCH, fid, "fixed", [fix], ME)
