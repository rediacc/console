"""`rediacc_ci.quality.command_tree` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-command-tree.sh` over a
fixture whose `npm` and `npx` are shims, with stdout and stderr captured
SEPARATELY, and its bytes are compared against the port's. The committed ledger
(`.ci/shadow/w7p2-cmdtree.observations.jsonl`) records the same comparison over
K distinct trees, one of which exceeds the `head -40` cap.

THE SHIMS ARE THE POINT, NOT A SHORTCUT. The subject of this gate is the
COMPARISON, not the exporter: `npm run build:packages` and `npx tsx
export-command-tree.ts` are how the live tree is obtained, and both
implementations must obtain it the same way, through PATH. Driving the real
exporter here would make a unit test take a minute and would test the CLI rather
than the gate.

WHAT IS NOT COMPARED, and why: the prose block on stdout. The twin's line reads
"fails OPEN <em dash> they keep passing while checking nothing" and the port's
reads "fails OPEN, they keep passing while checking nothing", because this
repository forbids em dashes in authored text. Both are indented continuation
prose on stdout, which `shadow-gate.ts` classifies as chatter, so the difference
changes no finding. The DIFF BODY, which is the part a reader acts on, is
compared line for line below.
"""

import json
import pathlib
import shutil

import pytest

from rediacc_ci.quality import command_tree as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-command-tree.sh"


def tree(names: list[str]) -> str:
    return json.dumps({"name": "rdc", "subcommands": [{"name": n} for n in names]}, indent=2) + "\n"


def build(
    tmp_path: pathlib.Path, committed: str | None, live: str | None, build_status: int = 0
) -> pathlib.Path:
    """A fixture repo holding the twin, its logger, the shims and the two trees."""
    root = tmp_path / "fixture"
    (root / ".ci/scripts/quality").mkdir(parents=True)
    (root / ".ci/scripts/lib").mkdir(parents=True)
    (root / "packages/cli/scripts").mkdir(parents=True)
    (root / "bin").mkdir(parents=True)
    repo = pathlib.Path(diff.repo())
    shutil.copy(repo / TWIN, root / TWIN)
    shutil.copy(repo / ".ci/scripts/lib/common.sh", root / ".ci/scripts/lib/common.sh")
    if committed is not None:
        (root / gate.COMMITTED_REL).write_text(committed, encoding="utf-8")
    npm = root / "bin/npm"
    npm.write_text("#!/bin/bash\nexit %d\n" % build_status, encoding="utf-8")
    npm.chmod(0o755)
    if live is None:
        body = "true"
    else:
        (root / "live.json").write_text(live, encoding="utf-8")
        body = 'cat "$(dirname "$0")/../live.json" > "${@: -1}"'
    npx = root / "bin/npx"
    npx.write_text("#!/bin/bash\n%s\n" % body, encoding="utf-8")
    npx.chmod(0o755)
    return root


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    env = diff.env_for(
        PATH="%s:%s" % (root / "bin", diff.BASE_ENV["PATH"]),
        REDIACC_CI_ROOT=str(root),
        PYTHONPATH=str(pathlib.Path(diff.repo()) / ".ci"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams("bash %s/%s" % (root, TWIN), env=env, cwd=str(root))
    new = diff.bash_streams("python3 -m rediacc_ci.quality.command_tree", env=env, cwd=str(root))
    return old, new


def diff_body(stdout: str) -> list[str]:
    """The `diff` lines the gate printed, which is what a reader acts on."""
    return [x for x in stdout.split("\n") if x.startswith("    ") and x[4:5] in "<>-0123456789"]


@pytest.mark.parametrize(
    ("committed", "live", "want_exit", "want_diff"),
    [
        pytest.param(tree(["repo"]), tree(["repo"]), 0, False, id="fresh"),
        pytest.param(tree(["repo"]), tree(["repo", "machine"]), 1, True, id="stale-missing-cmd"),
        pytest.param(tree(["repo", "machine"]), tree(["repo"]), 1, True, id="stale-extra-cmd"),
        pytest.param(None, tree(["repo"]), 1, False, id="committed-file-missing"),
    ],
)
def test_port_and_twin_agree(
    tmp_path: pathlib.Path, committed: str | None, live: str, want_exit: int, want_diff: bool
) -> None:
    root = build(tmp_path, committed, live)
    (old_exit, old_out, old_err), (new_exit, new_out, new_err) = run_both(root)
    assert old_exit == want_exit
    assert new_exit == old_exit
    assert diff_body(new_out) == diff_body(old_out)
    assert bool(diff_body(old_out)) == want_diff
    # The verdict line is the one finding on stderr, and its text is what the
    # shadow comparator compares. Both sides must say STALE, or missing, or
    # neither.
    assert ("STALE" in new_err) == ("STALE" in old_err)
    assert ("missing" in new_err) == ("missing" in old_err)


def test_the_diff_is_capped_the_same_way_on_both_sides(tmp_path: pathlib.Path) -> None:
    """`head -40`. A cap that only one side applies is a finding-set difference."""
    root = build(
        tmp_path,
        tree(["old%02d" % i for i in range(30)]),
        tree(["new%02d" % i for i in range(30)]),
    )
    (_, old_out, _), (_, new_out, _) = run_both(root)
    assert len(diff_body(old_out)) == gate.DIFF_CAP
    assert diff_body(new_out) == diff_body(old_out)


def test_a_reformat_is_stale_on_both_sides(tmp_path: pathlib.Path) -> None:
    """The BYTE comparison, asserted rather than assumed.

    The sibling port `regions_sync` compares parsed JSON; this one must not, and
    a control that never reformats anything could not tell the two apart.
    """
    same = {"name": "rdc", "subcommands": [{"name": "repo"}]}
    root = build(
        tmp_path,
        json.dumps(same, indent=4) + "\n",
        json.dumps(same, indent=2) + "\n",
    )
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(root)
    assert old_exit == 1
    assert new_exit == 1
    assert "STALE" in old_err
    assert "STALE" in new_err


def test_an_exporter_that_writes_nothing_is_the_declared_divergence(
    tmp_path: pathlib.Path,
) -> None:
    """Both halves of the divergence, so it stays a pinned decision.

    MEASURED, NOT ASSUMED, and worse than the port notes first claimed. The twin
    declares the committed tree STALE -- blaming the file the exporter failed to
    produce a rival for -- and then DIES at its own diff pipeline: `diff` exits 2
    on the missing operand, `set -euo pipefail` carries that out, and the gate
    exits 2 having printed "Diff (committed vs live):" and nothing under it. The
    author is told to run `npm run export:command-tree`, which would commit the
    empty tree. The port refuses before any of that.
    """
    root = build(tmp_path, tree(["repo"]), None)
    (old_exit, old_out, old_err), (new_exit, _, new_err) = run_both(root)
    assert old_exit == 2, "the twin dies at the diff pipeline under pipefail"
    assert "STALE" in old_err
    assert "No such file or directory" in old_err
    assert old_out.rstrip().endswith("Diff (committed vs live):"), "the report is cut off"
    assert new_exit == 1
    assert "STALE" not in new_err
    assert "wrote no tree" in new_err


def test_two_empty_trees_are_refused_not_called_equal(tmp_path: pathlib.Path) -> None:
    """The vacuity the twin scores GREEN: two empty files compare equal."""
    root = build(tmp_path, "", "")
    (old_exit, _, _), (new_exit, _, new_err) = run_both(root)
    assert old_exit == 0, "the twin calls two empty trees up to date"
    assert new_exit == 1
    assert "meaningless" in new_err


def test_node_count_counts_the_whole_tree() -> None:
    assert gate.node_count_of(tree(["a", "b"])) == 3
    assert gate.node_count_of('{"name":"rdc"}') == 1
    assert gate.node_count_of("[]") == 0
    assert gate.node_count_of("not json") == 0


def test_selftest_passes() -> None:
    assert gate.selftest() == 0
