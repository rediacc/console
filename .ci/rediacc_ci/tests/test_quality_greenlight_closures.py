"""`rediacc_ci.quality.greenlight_closures` against the shell it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. The two decisions this gate makes are made by git and by the shell, not by the gate: `[[ -e $root/$p ]]` and `git ls-files --error-unmatch -- "$p"`. The second one is the interesting one, because its answer for a DIRECTORY is not what a reader guesses -- it succeeds when the directory contains tracked files, which is why the
obvious "read the index once and test membership" optimisation is wrong. Running the real command and comparing is the only form of this test that can fail for the right reason.

The real closure list is 78 paths long and comes out of a CommonJS program, so this file drives `scan` on hand-built path lists instead. The whole gate over real closures is what the committed shadow ledger `.ci/shadow/w7p2-greenlight.observations.jsonl` compares over five distinct
trees; this file covers the seams that ledger cannot isolate.
"""

import pathlib
import subprocess
import tempfile

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import greenlight_closures as glc
from rediacc_ci.tests import differential as diff


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """A tiny repository with one tracked file, one tracked directory, one
    ignored file, one untracked file and one untracked directory.

    Five states, because the gate distinguishes three of them and a fixture with fewer cannot show that the third is distinguished at all.
    """
    subprocess.run(["git", "init", "-q", "."], cwd=str(tmp_path), check=True, capture_output=True)
    (tmp_path / "tracked.txt").write_text("t\n", encoding="utf-8")
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "inside.txt").write_text("i\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("g\n", encoding="utf-8")
    (tmp_path / "untracked.txt").write_text("u\n", encoding="utf-8")
    (tmp_path / "newdir").mkdir()
    (tmp_path / "newdir" / "action.yml").write_text("a\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "tracked.txt", "dir/inside.txt", ".gitignore"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    return tmp_path


PATHS = [
    "tracked.txt",  # tracked file
    "dir",  # tracked DIRECTORY: succeeds, which a set lookup would get wrong
    "dir/inside.txt",  # tracked file inside it
    "ignored.txt",  # on disk, gitignored, therefore NOT tracked
    "untracked.txt",  # on disk, untracked
    "newdir",  # untracked DIRECTORY: the 2026-09-02 bws-secrets shape
    "no-such-file.txt",  # not on disk at all
    ".gitignore",  # tracked, and easy to forget
]


@pytest.mark.parametrize("rel", PATHS)
def test_tracked_check_matches_git(repo: pathlib.Path, rel: str) -> None:
    script = 'git -C "$PWD" ls-files --error-unmatch -- %s >/dev/null 2>&1' % rel
    code, _out, _err = diff.bash_streams(script, cwd=str(repo))
    assert glc.is_tracked(repo, rel) == (code == 0)


@pytest.mark.parametrize("rel", PATHS)
def test_on_disk_check_matches_the_shell(repo: pathlib.Path, rel: str) -> None:
    """`[[ -e "$root/$p" ]]`, which FOLLOWS symlinks. So does `Path.exists()`."""
    code, _out, _err = diff.bash_streams('[[ -e "%s" ]]' % rel, cwd=str(repo))
    assert (repo / rel).exists() == (code == 0)


def test_a_symlink_to_a_deleted_target_is_absent_on_both_sides(repo: pathlib.Path) -> None:
    """The `-e` test follows symlinks, so a dangling one reads as ABSENT.

    Stated as a test rather than as prose because it is the one place where "on disk" and "the name exists in the directory" disagree, and a port using `lstat` would report NOT ON DISK where the twin reports NOT TRACKED.
    """
    (repo / "dangling").symlink_to("gone-target")
    code, _out, _err = diff.bash_streams('[[ -e "dangling" ]]', cwd=str(repo))
    assert code != 0
    assert (repo / "dangling").exists() is False
    rc, lines, _n = glc.scan(repo, ["dangling"])
    assert rc == 1
    assert "NOT ON DISK" in lines[0]


def test_the_tracked_directory_is_why_the_batched_lookup_is_wrong(repo: pathlib.Path) -> None:
    """A directory is NOT in `git ls-files` output, yet `--error-unmatch` accepts it.

    Eighteen closures name `.github/actions/bws-secrets`, a directory, so this is the shape of the very incident this gate exists for. A port that read the index into a set would report every one of them as untracked.
    """
    listing = subprocess.run(
        ["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=True
    ).stdout.split("\n")
    assert "dir" not in listing
    assert glc.is_tracked(repo, "dir") is True
    assert glc.scan(repo, ["dir"]) == (0, [], 1)


def test_zero_paths_is_a_refusal_not_a_pass(repo: pathlib.Path) -> None:
    """THE VACUITY CASE, both spellings.

    An empty list and a list of empty strings must both refuse. The second is the
    one that slips through: `while IFS= read -r p` over an empty string yields one
    iteration with `p` empty, which `[[ -n "$p" ]] || continue` skips, leaving `n` at zero.
    """
    assert glc.scan(repo, []) == (1, ["  no closure paths found -- this check is blind"], 0)
    assert glc.scan(repo, ["", ""]) == (1, ["  no closure paths found -- this check is blind"], 0)


def test_the_untracked_case_prints_two_lines_and_the_missing_case_one(repo: pathlib.Path) -> None:
    """The output SHAPE is the contract, not an internal detail.

    `scripts/lib/shadow-gate.ts` folds an indented line into the finding above it, so the second explanation line is part of the finding. A port that dropped it would change the finding set on every untracked path.
    """
    _rc, missing_lines, _n = glc.scan(repo, ["no-such-file.txt"])
    assert len(missing_lines) == 1
    _rc, untracked_lines, _n = glc.scan(repo, ["untracked.txt"])
    assert len(untracked_lines) == 2
    assert untracked_lines[1].startswith("      commit, so it resolves to nothing there")


def test_a_mixed_list_counts_every_path_including_the_offenders(repo: pathlib.Path) -> None:
    """The count in the success message must be the total, not the clean subset.

    A count that silently excluded offenders would make the number shrink as the tree got worse, which is the opposite of what a shape line is for.
    """
    rc, lines, n = glc.scan(repo, ["tracked.txt", "untracked.txt", "no-such-file.txt"])
    assert (rc, n) == (1, 3)
    assert len(lines) == 3


def test_the_node_extractor_reads_the_real_closure_file() -> None:
    """The list really does come out of `.ci/scripts/ci/greenlight.cjs`.

    A control on the INPUT, not on the verdict: without it every case above could be passing while the extractor returned nothing on the real file, which is the shape of a gate that has stopped seeing its subject.
    """
    root = paths.repo_root()
    if not (root / glc.GREENLIGHT_CJS).is_file():
        pytest.skip("greenlight.cjs is absent from this checkout")
    found = glc.closure_paths(root)
    assert len(found) > 20, "the closure list collapsed; a green here would mean nothing"
    assert found == sorted(found)


def test_a_missing_closure_source_raises_rather_than_returning_empty() -> None:
    """UNKNOWN IS A FAILURE. An empty list would read as "no paths to check"."""
    with tempfile.TemporaryDirectory() as tmp, pytest.raises(glc.ScanError):
        glc.closure_paths(pathlib.Path(tmp))


def test_selftest_is_green() -> None:
    """The gate's own controls, driven in-process. Exit 0 or the port is broken."""
    assert glc.selftest() == 0
