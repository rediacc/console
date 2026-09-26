"""`rediacc_ci.quality.no_app_admin_perm`, driven directly against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-no-app-admin-perm.sh` over each fixture below, with stdout and stderr captured SEPARATELY, and its bytes were compared against the port's over the same tree. The K=5 ledger `.ci/shadow/w7p2-appadmin.observations.jsonl` recorded that verdict over five distinct trees and licensed the port. The twin has now
been deleted, and every case that executed it compares against `goldens/app-admin-perm/`, which holds the twin's OWN recorded output for that fixture, captured from the tracked script on its last day in the tree. The provenance header of each golden carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed those bytes. Nothing here is a hand-written
expectation.

WHAT IS COMPARED IS WHAT THE DIFFERENTIAL COMPARED. That comparison was never byte-for-byte on both streams: it asserted the exit code and the SET of `permission-administration` lines on stdout, because two things were known to differ. Order is one -- GNU grep walks with fts in readdir order and the port walks sorted, so the two agree about WHICH lines and not about the order of
them, exactly as `shadow-gate.ts` compares a multiset. The port's success line is the other, and it is a DECLARED divergence rather than a normalization: the port appends the count of files it read, because a green that carries no evidence of having seen the tree is the failure this gate is named after. `test_the_success_line_divergence_is_still_declared` pins it so that it stays a
decision and not a drift.

The full twin render is recorded all the same, both streams verbatim, so a reader can see everything the twin printed and not only the projection the suite compares.
"""

from __future__ import annotations

import pathlib

import pytest

from rediacc_ci.quality import no_app_admin_perm as gate
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

SLUG = "app-admin-perm"
PORT = pathlib.Path(diff.repo()) / ".ci" / "rediacc_ci" / "quality" / "no_app_admin_perm.py"

CLEAN_WORKFLOW = "name: ci\njobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n"
REQUEST = "        permission-administration: write\n"

BASE_FILES = {
    ".github/workflows/ci.yml": CLEAN_WORKFLOW,
    ".github/actions/app-token/action.yml": "name: app token\n",
}


def build(tmp_path: pathlib.Path, extra: dict[str, str], bare: bool = False) -> pathlib.Path:
    """A fixture repo holding a `.github` tree. `bare` leaves the tree out entirely.

    The twin used to be copied in beside its logger, because it resolved its root from its own location. The port reads `REDIACC_CI_ROOT`, so nothing but the subject has to be in here any more.
    """
    root = tmp_path / "fixture"
    root.mkdir(parents=True)
    files = dict({} if bare else BASE_FILES)
    files.update(extra)
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def run_port(root: pathlib.Path) -> tuple[int, str, str]:
    env = diff.env_for(
        REDIACC_CI_ROOT=str(root),
        PYTHONPATH=str(pathlib.Path(diff.repo()) / ".ci"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    return diff.bash_streams(
        "python3 -m rediacc_ci.quality.no_app_admin_perm", env=env, cwd=str(root)
    )


def project(returncode: int, stdout: str) -> str:
    """Exit code and the SET of findings: the one thing the differential compared."""
    hits = sorted(line for line in stdout.split("\n") if gate.NEEDLE in line)
    return "exit: %d\n%s" % (returncode, "".join("%s\n" % h for h in hits))


def project_golden(text: str) -> str:
    """The same projection, read back out of a recorded twin render."""
    exit_line, rest = text.split("\n", 1)
    stdout = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)[0]
    return project(int(exit_line.removeprefix("exit: ")), stdout)


CASES: list[tuple[str, dict[str, object]]] = [
    ("clean", {"extra": {}}),
    ("workflow", {"extra": {".github/workflows/ci.yml": CLEAN_WORKFLOW + REQUEST}}),
    ("action", {"extra": {".github/actions/app-token/action.yml": "name: x\n" + REQUEST}}),
    ("nested", {"extra": {".github/workflows/deep/inner.yml": REQUEST}}),
    (
        "both-trees",
        {
            "extra": {
                ".github/workflows/ci.yml": CLEAN_WORKFLOW + REQUEST,
                ".github/actions/app-token/action.yml": "name: x\n" + REQUEST,
            }
        },
    ),
    # THE MIRROR. A gate that fires on everything is as useless as one that never does.
    ("hit-outside-the-two-dirs", {"extra": {".github/README.md": "%s: write\n" % gate.NEEDLE}}),
    # THE DIVERGENCE THAT CLOSED. The twin's `grep ... 2>/dev/null` could not tell
    # "no workflow asks for it" from "there are no workflows", so it printed the violation and then declared the tree clean; `grep` exits 2 on a missing operand WHILE PRINTING its hits. The hardened twin checks its scan dirs first, and the bytes recorded for this case are its refusal.
    ("no-github-tree-at-all", {"extra": {}, "bare": True}),
]

EXPECTED_HITS = {
    "clean": 0,
    "workflow": 1,
    "action": 1,
    "nested": 1,
    "both-trees": 2,
    "hit-outside-the-two-dirs": 0,
    "no-github-tree-at-all": 0,
}


@pytest.mark.parametrize(("name", "kwargs"), CASES, ids=[c[0] for c in CASES])
def test_port_matches_the_twins_recorded_output(
    tmp_path: pathlib.Path, name: str, kwargs: dict[str, object]
) -> None:
    root = build(tmp_path, **kwargs)  # type: ignore[arg-type]
    returncode, stdout, _ = run_port(root)
    actual = project(returncode, stdout)
    expected = project_golden(frozen.read(SLUG, name))
    assert actual == expected, "%s diverged from the twin's recorded bytes:\n%s\n%s" % (
        name,
        expected,
        actual,
    )
    planted = len([line for line in stdout.split("\n") if gate.NEEDLE in line])
    assert planted == EXPECTED_HITS[name], "the fixture must actually contain the planted hits"


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, {name for name, _ in CASES})


def test_the_recorded_refusal_and_the_ports_refusal_are_both_real(
    tmp_path: pathlib.Path,
) -> None:
    """A tree with no `.github` at all is refused on both sides, and said so in both.

    The assertion used to be `old_exit == 0`, back when the twin failed open. It was inverted rather than deleted when the twin was hardened, because a test that asserted a divergence must assert its ABSENCE once it closes or nothing notices if it returns.
    """
    recorded = frozen.read(SLUG, "no-github-tree-at-all")
    assert recorded.startswith("exit: 1\n"), "the hardened twin refused a tree with no .github"
    assert "cannot scan" in recorded, "and named the directory it could not scan"
    root = build(tmp_path, {}, bare=True)
    returncode, _, stderr = run_port(root)
    assert returncode == 1, "and so does the port, which never did anything else"
    assert "scanned nothing" in stderr


def test_the_success_line_divergence_is_still_declared(tmp_path: pathlib.Path) -> None:
    """The one place the port is stronger, pinned as a decision rather than left to drift.

    The twin said "OK: no permission-administration requests found." and had no idea how many files it had read. The port says the same words and appends the count, which is the evidence its green carries and the twin's did not.
    """
    recorded = frozen.read(SLUG, "clean")
    assert "OK: no permission-administration requests found.\n" in recorded
    assert "file(s) read" not in recorded
    root = build(tmp_path, {})
    returncode, _, stderr = run_port(root)
    assert returncode == 0
    assert "OK: no permission-administration requests found. (2 file(s) read)" in stderr


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


def test_planted_defect_is_caught_by_the_goldens(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Drop the composite-action tree from the scan.

    Scanning only `.github/workflows` is exactly the narrowing a reader would make on sight -- workflows are where the token is minted -- and it is a real divergence from what the twin printed. The mutation is written to a throwaway file; the tracked port is never touched.
    """
    source = PORT.read_text(encoding="utf-8")
    anchor = 'SCAN_DIRS = (".github/workflows/", ".github/actions/")\n'
    assert source.count(anchor) == 1, "the plant's anchor moved"
    broken_src = source.replace(anchor, 'SCAN_DIRS = (".github/workflows/",)\n')
    assert broken_src != source

    root = build(
        tmp_path,
        {
            ".github/workflows/ci.yml": CLEAN_WORKFLOW + REQUEST,
            ".github/actions/app-token/action.yml": "name: x\n" + REQUEST,
        },
    )
    expected = project_golden(frozen.read(SLUG, "both-trees"))
    broken = tmp_path / "no_app_admin_perm_broken.py"
    broken.write_text(broken_src, encoding="utf-8")
    env = diff.env_for(
        REDIACC_CI_ROOT=str(root),
        PYTHONPATH=str(pathlib.Path(diff.repo()) / ".ci"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    returncode, stdout, _ = diff.bash_streams("python3 %s" % broken, env=env, cwd=str(root))
    assert project(returncode, stdout) != expected, (
        "PLANT DID NOT FIRE: the goldens cannot see the composite-action tree going unscanned"
    )
    # And the real, unmutated file still agrees against the same fixture.
    assert project(*run_port(root)[:2]) == expected
    assert PORT.read_text(encoding="utf-8") == source


def test_selftest_passes() -> None:
    assert gate.selftest() == 0
