"""`rediacc_ci.quality.no_app_admin_perm` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-no-app-admin-perm.sh` over
a fixture, with stdout and stderr captured SEPARATELY, and its bytes are compared
against the port's over the same fixture. The committed ledger
(`.ci/shadow/w7p2-appadmin.observations.jsonl`) records the same comparison over
K distinct trees; these cases are what catch a regression on the day someone
edits either file.

ORDER IS COMPARED AS A SET, DELIBERATELY. GNU grep walks with fts in readdir
order and this module walks sorted, so the two agree about WHICH lines and not
about the order of them. `shadow-gate.ts` compares a multiset for the same
reason. Comparing the sequence would fail on a machine whose directory happened
to be laid out differently, which is a difference in the filesystem rather than
in either implementation.
"""

import pathlib
import shutil

import pytest

from rediacc_ci.quality import no_app_admin_perm as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-no-app-admin-perm.sh"

CLEAN_WORKFLOW = "name: ci\njobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n"
REQUEST = "        permission-administration: write\n"


def build(tmp_path: pathlib.Path, extra: dict[str, str]) -> pathlib.Path:
    """A fixture repo holding the twin, its logger, and a .github tree."""
    root = tmp_path / "fixture"
    (root / ".ci/scripts/quality").mkdir(parents=True)
    (root / ".ci/scripts/lib").mkdir(parents=True)
    repo = pathlib.Path(diff.repo())
    shutil.copy(repo / TWIN, root / TWIN)
    shutil.copy(repo / ".ci/scripts/lib/common.sh", root / ".ci/scripts/lib/common.sh")
    files = {
        ".github/workflows/ci.yml": CLEAN_WORKFLOW,
        ".github/actions/app-token/action.yml": "name: app token\n",
    }
    files.update(extra)
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    env = diff.env_for(
        REDIACC_CI_ROOT=str(root),
        PYTHONPATH=str(pathlib.Path(diff.repo()) / ".ci"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams("bash %s/%s" % (root, TWIN), env=env, cwd=str(root))
    new = diff.bash_streams(
        "python3 -m rediacc_ci.quality.no_app_admin_perm", env=env, cwd=str(root)
    )
    return old, new


@pytest.mark.parametrize(
    ("extra", "want_exit", "want_hits"),
    [
        pytest.param({}, 0, 0, id="clean"),
        pytest.param({".github/workflows/ci.yml": CLEAN_WORKFLOW + REQUEST}, 1, 1, id="workflow"),
        pytest.param(
            {".github/actions/app-token/action.yml": "name: x\n" + REQUEST}, 1, 1, id="action"
        ),
        pytest.param({".github/workflows/deep/inner.yml": REQUEST}, 1, 1, id="nested"),
        pytest.param(
            {
                ".github/workflows/ci.yml": CLEAN_WORKFLOW + REQUEST,
                ".github/actions/app-token/action.yml": "name: x\n" + REQUEST,
            },
            1,
            2,
            id="both-trees",
        ),
    ],
)
def test_port_and_twin_agree(
    tmp_path: pathlib.Path, extra: dict[str, str], want_exit: int, want_hits: int
) -> None:
    root = build(tmp_path, extra)
    (old_exit, old_out, _), (new_exit, new_out, _) = run_both(root)
    assert old_exit == want_exit
    assert new_exit == old_exit
    old_hits = sorted(x for x in old_out.split("\n") if gate.NEEDLE in x)
    new_hits = sorted(x for x in new_out.split("\n") if gate.NEEDLE in x)
    assert new_hits == old_hits
    assert len(old_hits) == want_hits, "the fixture must actually contain the planted hits"


def test_a_hit_outside_the_two_dirs_fires_on_neither(tmp_path: pathlib.Path) -> None:
    """The mirror. A gate that fires on everything is as useless as one that never does."""
    root = build(tmp_path, {".github/README.md": "%s: write\n" % gate.NEEDLE})
    (old_exit, _, _), (new_exit, _, _) = run_both(root)
    assert (old_exit, new_exit) == (0, 0)


def test_no_workflows_at_all_is_the_declared_divergence(tmp_path: pathlib.Path) -> None:
    """Both halves of the one place the port is stronger, so it stays a decision.

    The twin's `grep ... 2>/dev/null` cannot tell "no workflow asks for it" from
    "there are no workflows", and reports the clean tree. The port refuses.
    """
    root = tmp_path / "bare"
    (root / ".ci/scripts/quality").mkdir(parents=True)
    (root / ".ci/scripts/lib").mkdir(parents=True)
    repo = pathlib.Path(diff.repo())
    shutil.copy(repo / TWIN, root / TWIN)
    shutil.copy(repo / ".ci/scripts/lib/common.sh", root / ".ci/scripts/lib/common.sh")
    (old_exit, _, _), (new_exit, _, new_err) = run_both(root)
    assert old_exit == 0, "the twin reports a clean tree with no .github at all"
    assert new_exit == 1
    assert "scanned nothing" in new_err


def test_scan_returns_grep_rn_shape(tmp_path: pathlib.Path) -> None:
    """The byte shape `shadow-gate.ts` classifies as a finding, pinned."""
    root = build(tmp_path, {".github/workflows/ci.yml": CLEAN_WORKFLOW + REQUEST})
    hits, files_read = gate.scan(root)
    assert hits == [".github/workflows/ci.yml:6:        permission-administration: write"]
    assert files_read == 2


def test_scan_counts_every_file_it_read(tmp_path: pathlib.Path) -> None:
    """The anti-vacuity evidence is a COUNT, and it must move with the tree."""
    root = build(tmp_path, {".github/workflows/extra.yml": "name: extra\n"})
    assert gate.scan(root)[1] == 3
    assert gate.scan(tmp_path / "nowhere") == ([], 0)


def test_selftest_passes() -> None:
    assert gate.selftest() == 0
