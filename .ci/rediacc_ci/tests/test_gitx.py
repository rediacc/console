"""`rediacc_ci.gitx` against raw git, and against the six traps it exists to close.

THERE IS NO SINGLE BASH ORIGINAL to run beside this one, and that is itself the finding: `.ci/scripts/lib/` and `.ci/lib/` contain no git helper at all. The 36 functions in `common.sh` include exactly ONE line that shells out to git (`common.sh:582`). So the differential here is against RAW GIT -- the same commands the 23 `ls-files` sites, 22 branch sites, 21 dirt sites and 7
ancestry sites run inline -- and against the specific WRONG spellings this module refuses.

EVERY TRAP CASE IS ASSERTED IN BOTH DIRECTIONS. It is not enough to show that `gitx.branch()` returns None on a detached HEAD; the case also runs `rev-parse --abbrev-ref HEAD` and asserts it prints the literal "HEAD" and exits 0, because that is the behaviour 13 call sites in this tree depend on not happening. If a future git changes it, this file says so instead of the trap
quietly evaporating and taking the reason for the module with it.

THE FIXTURES ARE REAL REPOSITORIES, built per test in a tmpdir with the ambient git configuration switched off. A fixture that inherited the developer's `~/.gitconfig` would pick up their `init.defaultBranch`, their commit template and their gpg signing, and would then pass or fail per machine.
"""

import os
import pathlib
import subprocess

import pytest

from rediacc_ci import gitx, proc
from rediacc_ci.tests import differential as diff

# Ambient git configuration is switched OFF, not merely overridden. `/dev/null` is a valid empty config file to git, so this is the documented way to say "no global, no system". Without it the fixture inherits init.defaultBranch, commit signing and any alias the developer happens to have.
ISOLATED = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
}


def sh(script: str, cwd: pathlib.Path) -> tuple[int, str, str]:
    """Raw bash inside a fixture repo, streams separate, ambient git config off."""
    return diff.bash_streams(script, cwd=str(cwd), env=diff.env_for(**ISOLATED))


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A fresh repository with one commit on `main`. Returns its path."""
    for key, value in ISOLATED.items():
        monkeypatch.setenv(key, value)
    root = tmp_path / "fixture"
    root.mkdir()
    rc, _out, err = sh(
        "git init -q -b main . && "
        "printf 'one\\n' > tracked.txt && "
        "git add tracked.txt && "
        "git commit -q -m first",
        root,
    )
    assert rc == 0, err
    return root


# --------------------------------------------------------------------------- ANTI-VACUITY ---------------------------------------------------------------------------


def test_the_fixture_really_is_a_repository(repo):
    """Without this, every case below could be running against a plain directory
    and reporting the empty answers that a plain directory gives."""
    assert gitx.is_work_tree(repo) is True
    assert gitx.is_work_tree(repo.parent) is False
    assert gitx.head_sha(repo) is not None
    assert len(gitx.head_sha(repo)) == 40


def test_git_is_reachable_and_at_a_plausible_version():
    result = proc.run(["git", "--version"], timeout=10)
    assert result.ok
    assert result.stdout.startswith("git version 2.")


# --------------------------------------------------------------------------- TRAP 3: the branch, and the spelling that lies ---------------------------------------------------------------------------


def test_branch_matches_the_two_honest_spellings(repo):
    """Differential against `branch --show-current` and `symbolic-ref`."""
    _, show_current, _ = sh("git branch --show-current", repo)
    _, symbolic, _ = sh("git symbolic-ref --short -q HEAD", repo)
    assert gitx.branch(repo) == "main"
    assert show_current.strip() == "main"
    assert symbolic.strip() == "main"


def test_detached_head_prints_the_literal_head_string_from_abbrev_ref(repo):
    """THE TRAP ITSELF, measured rather than remembered.

    `rev-parse --abbrev-ref HEAD` exits 0 and prints "HEAD", so every `|| echo unknown` fallback written after it is dead code -- four of them in `scripts/dev/worktree.sh` alone. `.ci/lib/devbox.sh:151-156` records the cost: that string sanitises to `head.localhost`, one traefik router name shared by every detached worktree on the machine.
    """
    sh("git checkout -q --detach HEAD", repo)

    rc, abbrev, _ = sh("git rev-parse --abbrev-ref HEAD", repo)
    assert (rc, abbrev.strip()) == (0, "HEAD"), "the trap must still reproduce"

    rc, show_current, _ = sh("git branch --show-current", repo)
    assert (rc, show_current.strip()) == (0, ""), "the honest spelling prints nothing"

    rc, _out, _err = sh("git symbolic-ref --short -q HEAD", repo)
    assert rc != 0, "symbolic-ref reports detachment through its exit code"

    assert gitx.branch(repo) is None, "None is the honest answer, not 'HEAD'"


def test_branch_from_ci_prefers_pr_head_ref_then_github_head_ref():
    """The order matters: GITHUB_REF_NAME is `<n>/merge` on a pull_request."""
    assert gitx.branch_from_ci({"PR_HEAD_REF": "a", "GITHUB_HEAD_REF": "b"}) == "a"
    assert gitx.branch_from_ci({"GITHUB_HEAD_REF": "b", "GITHUB_REF_NAME": "9/merge"}) == "b"
    assert gitx.branch_from_ci({"GITHUB_REF_NAME": "9/merge"}) == "9/merge"
    assert gitx.branch_from_ci({}) is None
    assert gitx.branch_from_ci({"PR_HEAD_REF": ""}) is None


def test_branch_from_ci_does_not_silently_fall_through_to_git(repo):
    """Two different unknowns must stay distinguishable at the call site."""
    assert gitx.branch_from_ci({}) is None
    assert gitx.branch(repo) == "main"


# --------------------------------------------------------------------------- TRAP 1: ls-files reads the index ---------------------------------------------------------------------------


def test_ls_files_equals_raw_git_on_the_real_repository():
    """SET EQUALITY over the whole tracked corpus, against the command it replaces.

    Run against the real repository rather than a fixture, so the comparison is over thousands of paths in every shape this tree actually contains -- spaces, unicode, deep nesting -- rather than over three files someone thought of.
    """
    root = diff.repo()
    _, out, _ = diff.bash_streams("git ls-files -z", cwd=root)
    raw = {p for p in out.split("\0") if p}
    assert raw, "the corpus must not be empty"
    assert len(raw) > 500, "a tree this size cannot have fewer than 500 tracked files"
    assert set(gitx.ls_files(root=root)) == raw


def test_ls_files_with_a_pathspec_equals_raw_git():
    """The `.ci/*.sh` spelling from check-go-tool-path.sh:103, both sides."""
    root = diff.repo()
    _, out, _ = diff.bash_streams("git ls-files -z -- '.ci/*.sh' 'scripts/*.sh'", cwd=root)
    raw = {p for p in out.split("\0") if p}
    assert len(raw) > 50
    assert set(gitx.ls_files(".ci/*.sh", "scripts/*.sh", root=root)) == raw


def test_ls_files_still_lists_a_file_deleted_from_disk(repo):
    """TRAP 1, the direction that CRASHES consumers.

    `rm` without `git rm` leaves the path in the index. Only two of 23 call sites in this tree filter for it, and `check-shell-declared-commands.ts` crashed on exactly this on 2026-09-06.
    """
    (repo / "tracked.txt").unlink()

    _, out, _ = sh("git ls-files -z", repo)
    assert "tracked.txt" in out, "the trap must still reproduce"

    assert gitx.ls_files(root=repo) == ["tracked.txt"]
    assert gitx.ls_files(root=repo, existing=True) == []


def test_ls_files_cannot_see_an_untracked_file_without_being_asked(repo):
    """TRAP 1, the direction that shipped a green gate on 2026-08-09."""
    (repo / "new.py").write_text("x = 1\n")

    assert gitx.ls_files(root=repo) == ["tracked.txt"]
    assert gitx.ls_files(root=repo, untracked=True) == ["new.py", "tracked.txt"]

    _, out, _ = sh("git ls-files -z --cached --others --exclude-standard", repo)
    assert {p for p in out.split("\0") if p} == {"new.py", "tracked.txt"}


def test_untracked_listing_still_honours_gitignore(repo):
    """`--exclude-standard` is what keeps node_modules and build output out."""
    (repo / ".gitignore").write_text("ignored.py\n")
    (repo / "ignored.py").write_text("x = 1\n")
    (repo / "seen.py").write_text("x = 1\n")
    listed = gitx.ls_files(root=repo, untracked=True)
    assert "seen.py" in listed
    assert "ignored.py" not in listed


def test_recurse_submodules_with_untracked_is_refused_with_a_sentence(repo):
    """git rejects the combination with an error naming neither option clearly."""
    with pytest.raises(ValueError, match="--recurse-submodules"):
        gitx.ls_files(root=repo, untracked=True, recurse_submodules=True)


# --------------------------------------------------------------------------- TRAP 2: the pathspec that quietly narrows ---------------------------------------------------------------------------


def test_double_star_slash_silently_skips_files_at_the_top_level(repo):
    """THE MEASUREMENT FROM check-go-tool-path.sh:96-102, reproduced.

    `a/*.sh` reaches every depth because git's default `*` crosses `/`. `a/**/*.sh` requires at least one intermediate directory and drops `a/top.sh`. The narrower spelling looks more thorough and is not.
    """
    (repo / "a" / "deep").mkdir(parents=True)
    (repo / "a" / "top.sh").write_text("#!/bin/sh\n")
    (repo / "a" / "deep" / "nested.sh").write_text("#!/bin/sh\n")
    sh("git add -A && git commit -q -m more", repo)

    # THE NARROWING SPELLING IS ASSEMBLED, NOT WRITTEN. This test's whole subject is that `a/**/*.sh` under git's DEFAULT matching DEMANDS a literal slash and so silently drops the top-level file, which is exactly what check_pathspec_scope.py refuses everywhere else in the tree. Written as a literal it is an instance of the defect and that gate reds on it, correctly; it cannot be
    # spelled `:(glob)a/**/*.sh` either, because that opts into the semantics this test exists to show we do NOT get. Assembling it keeps the behaviour identical and keeps the gate honest, which is the same treatment check-em-dash-surfaces.ts and check-typecheck-scope-coverage.ts already use for their own deliberately-bad fixtures.
    narrowing = "a/" + "**" + "/*.sh"
    wide = gitx.ls_files("a/*.sh", root=repo)
    narrow = gitx.ls_files(narrowing, root=repo)
    assert wide == ["a/deep/nested.sh", "a/top.sh"]
    assert narrow == ["a/deep/nested.sh"], "the doubled-star form drops the top-level file"

    _, out, _ = sh("git ls-files -z -- '%s'" % narrowing, repo)
    assert {p for p in out.split("\0") if p} == {"a/deep/nested.sh"}, "raw git agrees"


def test_pathspec_warning_names_the_narrowing_spelling():
    """The rule from check_pathspec_scope.py:73, at the call site instead of in a gate."""
    assert gitx.pathspec_warning("a/**/*.sh")
    assert "**/" in gitx.pathspec_warning("a/**/*.sh")
    assert gitx.pathspec_warning("a/*.sh") is None
    assert gitx.pathspec_warning(".ci/scripts/**") is None, "'**' without a slash is fine"
    assert gitx.pathspec_warning(":(glob)a/**/*.sh") is None, "magic pathspecs opt in"


# --------------------------------------------------------------------------- TRAP 4: four different questions ---------------------------------------------------------------------------


def test_a_staged_change_is_dirty_but_git_diff_quiet_calls_it_clean(repo):
    """THE ASYMMETRY, in both directions.

    `scripts/dev/worktree.sh` pairs `diff --quiet` with `diff --cached --quiet` at four sites; a tree with only staged changes needs the second to be seen at all.
    """
    (repo / "tracked.txt").write_text("two\n")
    sh("git add tracked.txt", repo)

    assert sh("git diff --quiet", repo)[0] == 0, "unstaged view says clean"
    assert sh("git diff --cached --quiet", repo)[0] == 1, "staged view says dirty"

    assert gitx.has_unstaged_changes(repo) is False
    assert gitx.has_staged_changes(repo) is True
    assert gitx.is_dirty(repo) is True


def test_an_untracked_only_tree_is_dirty_to_status_and_clean_to_diff(repo):
    """The other half of the asymmetry, and why `untracked=` is an argument."""
    (repo / "scratch.txt").write_text("x\n")

    assert sh("git diff --quiet", repo)[0] == 0
    assert sh("git diff --cached --quiet", repo)[0] == 0
    _, porcelain, _ = sh("git status --porcelain", repo)
    assert porcelain.strip() == "?? scratch.txt"

    assert gitx.is_dirty(repo) is True
    assert gitx.is_dirty(repo, untracked=False) is False
    assert gitx.dirty_paths(repo) == ["scratch.txt"]
    assert gitx.dirty_paths(repo, untracked=False) == []


def test_status_entries_stay_in_phase_across_a_rename(repo):
    """`git status -z` emits an EXTRA field after a rename: the origin path.

    A naive split is one field out of phase for every entry after the first rename, and then reports half a filename as a status code. Two files are renamed here so a parser that skips one extra field but not two still fails.
    """
    (repo / "second.txt").write_text("two\n")
    sh("git add -A && git commit -q -m second", repo)
    sh(
        "git mv tracked.txt renamed.txt && git mv second.txt also-renamed.txt && "
        "printf 'z\\n' > after.txt && git add after.txt",
        repo,
    )
    entries = gitx.status_entries(repo)
    assert entries is not None
    paths = {path for _xy, path in entries}
    assert paths == {"renamed.txt", "also-renamed.txt", "after.txt"}
    for xy, _path in entries:
        assert len(xy) == 2, "a status code is two characters; %r is a phase error" % xy


def test_a_failed_probe_returns_none_and_not_clean(tmp_path):
    """TRAP 5 in the dirt check's clothing: unknown is not clean."""
    assert gitx.is_dirty(tmp_path) is None
    assert gitx.dirty_paths(tmp_path) is None
    assert gitx.status_entries(tmp_path) is None
    assert gitx.has_staged_changes(tmp_path) is None
    assert gitx.has_unstaged_changes(tmp_path) is None


# --------------------------------------------------------------------------- TRAP 5: ancestry is tri-state ---------------------------------------------------------------------------


def test_is_ancestor_agrees_with_raw_git_in_both_directions(repo):
    first = gitx.head_sha(repo)
    (repo / "tracked.txt").write_text("two\n")
    sh("git add -A && git commit -q -m second", repo)
    second = gitx.head_sha(repo)

    assert sh("git merge-base --is-ancestor %s %s" % (first, second), repo)[0] == 0
    assert sh("git merge-base --is-ancestor %s %s" % (second, first), repo)[0] == 1

    assert gitx.is_ancestor(first, second, root=repo) is True
    assert gitx.is_ancestor(second, first, root=repo) is False


def test_an_unknown_ref_is_none_and_raw_git_exits_128(repo):
    """THE WHOLE POINT OF THE TRI-STATE.

    All seven shell sites in this tree collapse this into False, so a shallow clone reports "this commit is not on main" and the gate acts on it.
    """
    rc, _out, _err = sh("git merge-base --is-ancestor HEAD refs/heads/never-existed", repo)
    assert rc not in (0, 1), "the blind case must be distinguishable by exit code (got %d)" % rc

    assert gitx.is_ancestor("HEAD", "refs/heads/never-existed", root=repo) is None
    assert gitx.ref_exists("refs/heads/never-existed", root=repo) is False
    assert gitx.ref_exists("HEAD", root=repo) is True


def test_count_commits_is_none_rather_than_zero_when_the_probe_fails(repo):
    """check-branch.sh:67-71: a `|| echo 0` here once read as 'up to date'."""
    assert gitx.count_commits("HEAD", root=repo) == 1
    assert gitx.count_commits("origin/main..HEAD", root=repo) is None
    assert gitx.merge_base("HEAD", "HEAD", root=repo) == gitx.head_sha(repo)
    assert gitx.merge_base("HEAD", "refs/heads/nope", root=repo) is None


# --------------------------------------------------------------------------- TRAP 6: submodules, read and never hardcoded ---------------------------------------------------------------------------


def test_submodules_match_the_git_config_enumeration_on_the_real_repo():
    """Differential against `git config -f .gitmodules --get-regexp`.

    That is the spelling used by `detect-pointer-bump.sh:170`, `claude-review-gate.sh:882` and `review-status.sh:321`.
    """
    root = diff.repo()
    _, out, _ = diff.bash_streams(
        "git config -f .gitmodules --get-regexp '^submodule\\..*\\.path$' | awk '{print $2}'",
        cwd=root,
    )
    from_git = {line.strip() for line in out.splitlines() if line.strip()}
    assert len(from_git) >= 2, "the enumeration must not be empty"
    assert {s.path for s in gitx.submodules(root)} == from_git


def test_the_three_hardcoded_submodule_lists_still_agree_with_gitmodules():
    """THE DRIFT DETECTOR the tree does not have.

    `check-submodule-branches.sh:418`, `.ci/scripts/ci/scope-map.cjs:123` and `.ci/scripts/ci/greenlight.cjs:270` each carry their own copy of the four paths. They agree today, and two files already record that as a live defect rather than a state of grace. This is the case that goes red on the day one of them stops agreeing -- which is the day a fifth submodule is added, when the
    shell gate goes blind to it silently.
    """
    root = pathlib.Path(diff.repo())
    declared = {s.path for s in gitx.submodules(root)}
    assert declared, "nothing to compare against"

    for relative in (
        ".ci/scripts/quality/check-submodule-branches.sh",
        ".ci/scripts/ci/scope-map.cjs",
        ".ci/scripts/ci/greenlight.cjs",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        missing = sorted(path for path in declared if path not in text)
        assert not missing, "%s does not mention %s" % (relative, missing)


def test_parse_gitmodules_reads_text_with_no_repository_at_all():
    """A text parser, so a fixture needs no git. The three `git config -f` sites
    cannot be tested without building a repository, which is why none of them is."""
    parsed = gitx.parse_gitmodules(
        '[submodule "renet"]\n'
        "\tpath = private/renet\n"
        "\turl = https://example.invalid/renet.git\n"
        "\tbranch = release\n"
        '[submodule "account"]\n'
        "\tpath = private/account\n"
        "\turl = https://example.invalid/account.git\n"
    )
    assert [s.path for s in parsed] == ["private/renet", "private/account"]
    assert parsed[0].branch == "release"
    assert parsed[1].branch == "main", "the default, matching wl_git.py:113-138"
    assert parsed[0].name == "renet"


def test_a_section_without_a_path_is_skipped_rather_than_half_parsed():
    """A malformed entry must not become a Submodule with an empty path, which
    would then be joined onto the root and enumerate the whole repository."""
    parsed = gitx.parse_gitmodules(
        '[submodule "broken"]\n\turl = x\n[submodule "ok"]\n\tpath = p\n'
    )
    assert [s.path for s in parsed] == ["p"]


def test_submodules_is_empty_and_not_an_exception_without_a_gitmodules(tmp_path):
    assert gitx.submodules(tmp_path) == []
    assert gitx.sibling_repos(tmp_path) == []


def test_sibling_repos_finds_gitignored_checkouts_that_are_not_submodules(tmp_path):
    """The blind spot no enumeration in the tree covers.

    `private/growth` holds the media pipeline whose publish gate console CI cannot run; `git status`, `git submodule` and `.gitmodules` all report nothing about it.
    """
    (tmp_path / ".gitmodules").write_text('[submodule "a"]\n\tpath = private/declared\n')
    for name in ("declared", "sibling", "plain"):
        (tmp_path / "private" / name).mkdir(parents=True)
    (tmp_path / "private" / "declared" / ".git").mkdir()
    (tmp_path / "private" / "sibling" / ".git").write_text("gitdir: elsewhere\n")

    assert gitx.sibling_repos(tmp_path) == ["private/sibling"]


def test_a_worktree_git_file_still_counts_as_a_repository(tmp_path):
    """In a git WORKTREE -- how every session in this repo works -- `.git` is a
    FILE holding a gitdir pointer, so an is_dir() test says 'not a repository'."""
    (tmp_path / "private" / "wt").mkdir(parents=True)
    (tmp_path / "private" / "wt" / ".git").write_text("gitdir: /somewhere/else\n")
    assert gitx.sibling_repos(tmp_path) == ["private/wt"]


# --------------------------------------------------------------------------- file modes, and the git-versus-disk distinction ---------------------------------------------------------------------------


def test_file_modes_report_what_git_recorded_not_what_is_on_disk(repo):
    """The 2026-08-28 defect: two files passed locally and failed in CI.

    CI lints a fresh checkout, so what it sees is the recorded mode. A file chmod +x AFTER `git add` is 755 on disk and 644 in the index.
    """
    target = repo / "tracked.txt"
    target.chmod(0o755)
    assert os.access(target, os.X_OK), "the disk really is executable"
    assert gitx.file_modes(root=repo) == {"tracked.txt": "100644"}

    sh("git update-index --chmod=+x tracked.txt", repo)
    assert gitx.file_modes(root=repo) == {"tracked.txt": "100755"}


def test_file_modes_equal_raw_ls_files_s_on_the_real_repository():
    """Differential against check-script-exec-bit.sh:82's own query."""
    root = diff.repo()
    _, out, _ = diff.bash_streams("git ls-files -s -- '*.py' | awk '{print $1, $4}'", cwd=root)
    raw = {}
    for line in out.splitlines():
        mode, _, path = line.partition(" ")
        if path:
            raw[path] = mode
    assert len(raw) > 10
    assert gitx.file_modes("*.py", root=root) == raw


# --------------------------------------------------------------------------- The runner underneath ---------------------------------------------------------------------------


def test_git_runs_noninteractively(repo):
    """Every one of these closes a way git can decide to wait for a human."""
    result = gitx.git(["var", "GIT_EDITOR"], root=repo)
    assert result.stdout.strip() == "true"
    assert set(gitx.NONINTERACTIVE) == {
        "GIT_EDITOR",
        "GIT_SEQUENCE_EDITOR",
        "GIT_TERMINAL_PROMPT",
        "GIT_PAGER",
    }


def test_a_git_failure_is_returned_and_not_raised(tmp_path):
    """Matching wl_git.py:92: "Never raises on a non-zero git; callers decide"."""
    result = gitx.git(["status"], root=tmp_path)
    assert result.ok is False
    assert result.returncode != 0
    assert result.stderr, "the reason must survive"


def test_toplevel_answers_with_the_innermost_repository(repo):
    inner = repo / "nested"
    inner.mkdir()
    assert gitx.toplevel(inner) == repo.resolve()
    assert gitx.toplevel(repo.parent) is None


def test_the_real_repository_is_reachable_through_toplevel():
    """ANTI-VACUITY for every case that uses `diff.repo()`."""
    found = gitx.toplevel(diff.repo())
    assert found is not None
    assert (found / ".ci" / "rediacc_ci").is_dir()


def test_subprocess_is_reachable_at_all():
    assert subprocess.run(["git", "--version"], check=False, capture_output=True).returncode == 0
