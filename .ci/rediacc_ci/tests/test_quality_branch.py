"""`rediacc_ci.quality.branch` against the shell it reproduces.

WHAT IS WORTH TESTING HERE. The shadow ledger `.ci/shadow/w7p2-branch.observations.jsonl` drives the whole gate over five distinct trees: one commit behind, three behind, eight behind, behind AND conflicting, and unrelated histories. What a ledger row cannot isolate is the three pieces that decide whether the gate is even answering the question:

  * the fetch REFSPEC, which the twin spells out because a bare
    `git fetch origin <branch>` does not promise to write
    `refs/remotes/origin/<branch>` at all;
  * `indent`, which stands in for `sed 's/^/    /'` on two different streams;
  * the printed recipe, sixteen lines of instructions a human is expected to
    follow, which is the entire value of the gate exiting 1 rather than rebasing.

The recipe is compared against the TWIN'S OWN TEXT rather than against a copy kept here, so a line deleted from either side is a red instead of a slow drift.
"""

import pathlib
import subprocess

from rediacc_ci import paths
from rediacc_ci.quality import branch as B
from rediacc_ci.tests import differential as diff

TWIN = paths.from_root(".ci", "scripts", "quality", "check-branch.sh")


def _sed_indent(text: str) -> list[str]:
    """The real `sed 's/^/    /'`, so `indent` is compared and not described."""
    proc = subprocess.run(
        ["sed", "s/^/    /"],
        input=text.encode("utf-8"),
        stdout=subprocess.PIPE,
        check=True,
    )
    out = proc.stdout.decode("utf-8").removesuffix("\n")
    return out.split("\n") if out else []


def test_indent_matches_sed_on_a_multi_line_stream() -> None:
    assert B.indent("a\nb\nc") == _sed_indent("a\nb\nc")


def test_indent_matches_sed_on_a_stream_ending_in_a_newline() -> None:
    """The case that produces a stray four-space line if it is got wrong."""
    assert B.indent("a\nb\n") == _sed_indent("a\nb\n") == ["    a", "    b"]


def test_indent_of_an_empty_stream_produces_nothing() -> None:
    """`sed` over an empty input writes nothing at all, not one indented blank."""
    assert B.indent("") == _sed_indent("") == []


def test_indent_preserves_an_already_indented_line() -> None:
    """`s/^/    /` anchors at the start, so it stacks rather than normalising."""
    assert B.indent("    deep") == _sed_indent("    deep") == ["        deep"]


def test_the_refspec_is_the_explicit_form_the_twin_carries() -> None:
    """The literal appears in the twin, so a change there reds here.

    This is the line the twin's longest comment defends. A port that shortened it would still pass every fixture in the ledger, because those fixtures use a remote whose default refspec happens to cover the branch.
    """
    body = TWIN.read_text(encoding="utf-8")
    assert '"+refs/heads/${BASE_BRANCH}:refs/remotes/origin/${BASE_BRANCH}"' in body
    assert B.fetch_refspec("main") == "+refs/heads/main:refs/remotes/origin/main"
    assert B.fetch_refspec("release/1") == ("+refs/heads/release/1:refs/remotes/origin/release/1")


def test_every_fixed_recipe_line_still_exists_in_the_twin() -> None:
    """Byte-for-byte, for every recipe line the twin does not interpolate into.

    Both directions matter and only one of them is cheap: a line the port invented would not be in the twin (caught here), and a line the port dropped is caught by the ledger, where the whole block is stdout the comparator counts as chatter but the gate's exit code depends on.
    """
    body = TWIN.read_text(encoding="utf-8")
    fixed = [
        line
        for line in B.recipe("main", "")
        if line.strip() != "" and "main" not in line and "REBASE LOCALLY" not in line
    ]
    assert len(fixed) >= 12, fixed
    for line in fixed:
        assert line in body, line


def test_the_head_branch_suffix_is_bashs_plus_expansion() -> None:
    """`${HEAD_BRANCH:+ (branch: X)}` prints nothing at all when unset.

    Compared against bash rather than asserted from memory, because `:+` and `:-` are one character apart and mean opposite things.
    """
    for head, want in (("feat-1", "REBASE LOCALLY (branch: feat-1)"), ("", "REBASE LOCALLY")):
        code, out, _err = diff.bash_streams(
            'HEAD_BRANCH=%s; printf %%s "REBASE LOCALLY${HEAD_BRANCH:+ (branch: ${HEAD_BRANCH})}"'
            % (head or '""')
        )
        assert code == 0
        assert out == want, (head, out)
        assert B.recipe("main", head)[2] == want


def test_merge_tree_three_arms_are_distinguishable(tmp_path: pathlib.Path) -> None:
    """0 clean, 1 conflicts, 128 unknown. The gate branches on exactly this.

    Reported as unknown rather than as clean is the load-bearing half: a probe that could not run must never read as "a plain rebase should apply cleanly".
    """
    clean = B._fixture(tmp_path / "clean", behind=1, conflict=False)
    clash = B._fixture(tmp_path / "clash", behind=1, conflict=True)
    for root, want in ((clean, 0), (clash, 1)):
        subprocess.run(
            ["git", "fetch", "origin", B.fetch_refspec("main"), "--quiet"],
            cwd=str(root),
            check=True,
        )
        probe = subprocess.run(
            ["git", "merge-tree", "--write-tree", "origin/main", "HEAD"],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert probe.returncode == want


def test_selftest_runs_and_meets_its_floor() -> None:
    """The gate's own both-direction controls, over repositories built here."""
    assert B.selftest() == 0
