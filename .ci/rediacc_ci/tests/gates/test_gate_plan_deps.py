"""`check:ci-plan-deps`, driven as a process against planted plan trees.

WHAT THIS ADDS TO THE GATE'S OWN `--selftest`. Those controls plant into fixture TEXT and call `evaluate` on a graph built in memory; they prove the detector and nothing else. This file proves the rest of the path from disk to exit code: the directory walk (`Graph.load`), the INDEX.md tombstone read, `--root`, the exit codes, and the two verbs that touch files (`--set` writes one line and only with `--write`; `--draft` never writes).

THE FIXTURE IS A PLAIN DIRECTORY, not a git repository: the gate reads plan files from disk and never asks git, so a repository would be a precondition this gate does not have.
"""

import pathlib
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import plan_lifecycle as PL
from rediacc_ci.tests.gates import harness

paths.on_sys_path(paths.hooks_stop_dir())
import wl_plandeps as D  # noqa: E402

GATE = paths.from_root(".ci", "scripts", "quality", "check_plan_deps.py")

#: The gate's MIN_REQUIRED, so the clean fixture sits exactly on the floor and one removal trips D8.
FLOOR = 10
INDEX = (
    "## Expired plans\n\n| Plan | Title | First seen | Expired | Full-Text-Blob |\n|---|---|---|---|---|\n"
    "| `agent/plans/_done/PLAN-gone.md` | t | 2026-01-01 | 2026-03-01 | `%s` |\n"
    "| `agent/plans/PLAN-expired.md` | t | 2026-01-01 | 2026-03-01 | `%s` |\n"
    % ("a" * 40, "b" * 40)
)


def _plan(status="in-progress", dep=None):
    text = "# PLAN: sample\n\nStatus: %s\nOwner: cafe0000\n" % status
    if dep is not None:
        text += "Depends-On: %s\n" % dep
    return text + "\n## Tasks\n\n- [ ] T1 a box\n"


def _seed(tmp_path: pathlib.Path, **plans: str | None) -> pathlib.Path:
    """A clean tree of FLOOR required plans; `name=text` replaces or adds `agent/plans/PLAN-<name>.md`, `name=None` removes it."""
    root = tmp_path / "tree"
    files = {
        "PLAN-p%02d.md" % i: _plan(dep="no-dep -- fixture plan %02d stands alone" % i)
        for i in range(7)
    }
    files["PLAN-x.md"] = _plan(dep="PLAN-y.md")
    files["PLAN-y.md"] = _plan(dep="PLAN-z.md, PLAN-fin.md")
    files["PLAN-z.md"] = _plan(status="draft", dep="PLAN-gone.md")
    files["PLAN-rec.md"] = _plan(status="compacted")
    files["PLAN-fin.md"] = "# stub\n\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-fin.md\n"
    for name, text in plans.items():
        key = "PLAN-%s.md" % name
        if text is None:
            files.pop(key, None)
        else:
            files[key] = text
    for name, text in files.items():
        _write(root, "agent/plans/%s" % name, text)
    _write(root, "agent/plans/_done/PLAN-fin.md", _plan(status="done"))
    _write(root, "agent/plans/_removed/PLAN-rm.md", _plan(status="removed"))
    _write(root, "agent/INDEX.md", INDEX)
    return root


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _gate(root: pathlib.Path, *argv: str) -> harness.RunResult:
    return harness.run(
        [sys.executable, str(GATE), "--root", str(root), *argv], cwd=paths.repo_root()
    )


# --------------------------------------------------------------------------- Preconditions and the real tree.


def test_the_subject_exists(gate):
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    gate.log_pass("subject under test is present")


def test_selftest_alone_is_green(gate):
    result = harness.run([sys.executable, str(GATE), "--selftest"], cwd=paths.repo_root())
    gate.assert_exit(0, result, "the planted controls must pass")
    gate.assert_contains(result.out, "control(s) passed", "the tally is printed")
    gate.log_pass("--selftest is green")


def test_the_real_tree_gets_a_verdict_not_a_crash(gate):
    """0 or 1, never 2 or 77. The live tree is red until PLAN-plan-dependencies T10 backfills the field, so this pins that a VERDICT is reached and the controls ran first, not which one."""
    result = harness.run([sys.executable, str(GATE)], cwd=paths.repo_root())
    gate.assert_eq(result.rc in (0, 1), True, "the real tree is judged: %r" % result)
    gate.assert_contains(
        result.out, "controls first, then the verdict", "controls are not optional"
    )
    gate.assert_contains(result.combined, "plan deps:", "the summary line names the corpus")
    gate.log_pass("the real tree reaches a verdict after the controls")


def test_the_tombstone_grammar_mirrors_plan_lifecycle(gate):
    """wl_plandeps restates plan_lifecycle's tombstone row regex because it must import with `.claude` alone. A mirror nobody compares is just a second regex."""
    gate.assert_eq(D.TOMBSTONE_ROW_RE.pattern, PL.TOMBSTONE_ROW_RE.pattern, "tombstone row regex")
    gate.assert_eq(D.TOMBSTONE_ROW_RE.flags, PL.TOMBSTONE_ROW_RE.flags, "tombstone row flags")
    gate.assert_eq(D.STUB_STATUS, PL.STUB_STATUS, "the stub word")
    gate.assert_eq(D.REMOVED_STATUS, PL.REMOVED_STATUS, "the removed word")
    gate.assert_eq(
        (D.PLANS_DIR, D.DONE_DIR, D.REMOVED_DIR),
        (PL.PLANS_DIR, PL.DONE_DIR, PL.REMOVED_DIR),
        "folders",
    )
    gate.log_pass("the mirrored grammar matches plan_lifecycle")


# --------------------------------------------------------------------------- Planted trees: the clean twin, then one finding each.


def test_the_clean_tree_is_green(gate, tmp_path):
    result = _gate(_seed(tmp_path))
    gate.assert_exit(0, result, "a tree where every required plan carries a valid field")
    gate.assert_contains(
        result.out, "✓ plan deps: %d required plan(s)" % FLOOR, "counts the floor exactly"
    )
    gate.assert_contains(result.out, "Blind spot:", "a green says what it did not check")
    gate.log_pass("the clean fixture is green")


@pytest.mark.parametrize(
    ("code", "plants"),
    [
        ("D1", {"p00": _plan()}),
        ("D2", {"x": _plan(dep="agent/plans/PLAN-y.md")}),
        ("D2", {"x": _plan(dep="no-dep -- n/a")}),
        ("D3", {"x": _plan(dep="PLAN-nowhere.md")}),
        ("D4", {"x": _plan(dep="PLAN-rm.md")}),
        ("D4", {"x": _plan(dep="PLAN-expired.md")}),
        ("D5", {"x": _plan(dep="PLAN-x.md")}),
        ("D6", {"z": _plan(dep="PLAN-x.md")}),
        ("D8", {"p00": None}),
    ],
)
def test_each_finding_reds_the_tree(gate, tmp_path, code, plants):
    result = _gate(_seed(tmp_path, **plants))
    gate.assert_exit(1, result, "%s planted" % code)
    gate.assert_contains(result.err, "    %s  " % code, "the finding is named by its code")
    gate.log_pass("%s planted into a clean tree reds it" % code)


def test_an_ambiguous_basename_reds_the_tree(gate, tmp_path):
    root = _seed(tmp_path)
    _write(root, "agent/plans/_done/PLAN-z.md", _plan(status="done"))
    result = _gate(root)
    gate.assert_exit(1, result, "two real files named PLAN-z.md")
    gate.assert_contains(result.err, "    D7  ", "D7 is named")
    gate.log_pass("D7 planted reds the tree")


def test_the_cycle_is_reported_as_a_path(gate, tmp_path):
    result = _gate(_seed(tmp_path, z=_plan(dep="PLAN-x.md")))
    gate.assert_contains(result.err, "PLAN-x.md -> PLAN-y.md -> PLAN-z.md -> PLAN-x.md", "the path")
    gate.log_pass("D6 prints the cycle path")


def test_the_tombstone_is_read_from_disk(gate, tmp_path):
    """The clean tree depends on PLAN-gone.md, which exists only as an INDEX.md row. Removing the row must turn it into D3: proof the gate read the file, not a constant."""
    root = _seed(tmp_path)
    (root / "agent" / "INDEX.md").write_text("", encoding="utf-8")
    result = _gate(root)
    gate.assert_exit(1, result, "no tombstone section")
    gate.assert_contains(result.err, "    D3  PLAN-gone.md", "the tombstoned target dangles")
    gate.log_pass("tombstones come from agent/INDEX.md on disk")


# --------------------------------------------------------------------------- Anti-vacuity: no verdict is never green.


def test_zero_required_plans_cannot_run(gate, tmp_path):
    root = tmp_path / "tree"
    _write(root, "agent/plans/PLAN-rec.md", _plan(status="compacted"))
    result = _gate(root)
    gate.assert_exit(77, result, "a tree with no live plan has nothing to judge")
    gate.assert_contains(result.err, "CANNOT RUN", "and says so")
    gate.log_pass("zero required plans is exit 77, never green")


def test_a_tree_without_plans_dir_cannot_run(gate, tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    result = _gate(bare)
    gate.assert_exit(77, result, "no agent/plans at all")
    gate.assert_contains(result.err, "CANNOT RUN", "and says so")
    gate.log_pass("a tree without agent/plans is exit 77")


# --------------------------------------------------------------------------- The verbs that touch files.


def test_set_is_a_dry_run_without_write(gate, tmp_path):
    root = _seed(tmp_path, p00=_plan())
    before = (root / "agent/plans/PLAN-p00.md").read_bytes()
    result = _gate(root, "--set", "agent/plans/PLAN-p00.md", "no-dep -- fixture plan stands alone")
    gate.assert_exit(0, result, "a valid value")
    gate.assert_contains(result.out, "dry run", "says it did not write")
    gate.assert_eq((root / "agent/plans/PLAN-p00.md").read_bytes(), before, "the file is unchanged")
    gate.log_pass("--set without --write writes nothing")


def test_set_write_adds_exactly_one_line_and_turns_the_tree_green(gate, tmp_path):
    root = _seed(tmp_path, p00=_plan())
    path = root / "agent/plans/PLAN-p00.md"
    before = path.read_text(encoding="utf-8").splitlines()
    result = _gate(root, "--set", str(path), "no-dep -- fixture plan stands alone", "--write")
    gate.assert_exit(0, result, "a valid value, written")
    after = path.read_text(encoding="utf-8").splitlines()
    gate.assert_eq(
        [line for line in after if line not in before],
        ["Depends-On: no-dep -- fixture plan stands alone"],
        "one added line",
    )
    gate.assert_eq([line for line in before if line not in after], [], "nothing removed")
    gate.assert_exit(0, _gate(root), "the tree is green after the one write")
    gate.log_pass("--set --write is a one-line diff that clears D1")


def test_set_refuses_a_cycle_and_writes_nothing(gate, tmp_path):
    root = _seed(tmp_path)
    path = root / "agent/plans/PLAN-z.md"
    before = path.read_bytes()
    result = _gate(root, "--set", "agent/plans/PLAN-z.md", "PLAN-x.md", "--write")
    gate.assert_exit(1, result, "the value closes a cycle")
    gate.assert_contains(result.err, "D6", "the cycle is the reason")
    gate.assert_eq(path.read_bytes(), before, "nothing was written")
    gate.log_pass("--set refuses a cycle even with --write")


def test_draft_proposes_and_never_writes(gate, tmp_path):
    root = _seed(
        tmp_path,
        p00=_plan().replace("## Tasks", "Builds on PLAN-y.md and PLAN-fin.md.\n\n## Tasks"),
    )
    snapshot = {p: p.read_bytes() for p in root.rglob("*.md")}
    result = _gate(root, "--draft", "agent/plans/PLAN-p00.md")
    gate.assert_exit(0, result, "--draft is a report")
    gate.assert_contains(
        result.out, "proposed: Depends-On: PLAN-y.md", "the live citation is the candidate"
    )
    gate.assert_contains(
        result.out, "cites PLAN-fin.md  [complete", "the finished citation is shown as such"
    )
    gate.assert_eq({p: p.read_bytes() for p in root.rglob("*.md")}, snapshot, "no file changed")
    gate.log_pass("--draft proposes from citations and writes nothing")
