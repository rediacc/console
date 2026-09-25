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


#: Every fixture plan carries a valid X triple (agent/plans/PLAN-plan-priority-concurrency.md), so each tree below means the same before and after `wl_plandeps.X_FIELDS_REQUIRED` flips at the T11 migration.
X_TRIPLE = "Priority: P2 -- a fixture plan\nConcurrency: parallel\nOwns: docs/fixture/**\n"


def _plan(status="in-progress", dep=None):
    text = "# PLAN: sample\n\nStatus: %s\nOwner: cafe0000\n" % status
    if dep is not None:
        text += "Depends-On: %s\n" % dep
    return text + X_TRIPLE + "\n## Tasks\n\n- [ ] T1 a box\n"


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


# --------------------------------------------------------------------------- The X fields (agent/plans/PLAN-plan-priority-concurrency.md T3).


def _xplan(pri="P2 -- a fixture plan", dep="no-dep -- a fixture plan with X lines"):
    return _plan(dep=dep).replace("Priority: P2 -- a fixture plan\n", "Priority: %s\n" % pri)


def test_x_fields_are_pending_not_red_before_the_migration(gate, tmp_path):
    """While `X_FIELDS_REQUIRED` is False a tree without the X lines stays green, and says what is pending."""
    if D.X_FIELDS_REQUIRED:
        pytest.skip("the migration has landed; the strict half is the gate's --selftest")
    malformed = _xplan(pri="P0. an operator ruling", dep="PLAN-y.md")
    result = _gate(_seed(tmp_path, x=malformed))
    gate.assert_exit(0, result, "missing and malformed X lines are reported, not failed")
    gate.assert_contains(result.out, "X fields pending migration", "the pending block is printed")
    gate.assert_contains(
        result.out, "D11  agent/plans/PLAN-x.md", "a malformed line present is named"
    )
    gate.assert_contains(
        result.out, "enforcement OFF until the T11 migration", "the green says it is lax"
    )
    gate.log_pass("X findings are visible and not enforced before the migration")


def test_d17_an_operator_demotion_reds_the_tree(gate, tmp_path):
    root = _seed(tmp_path, x=_xplan(pri="P1", dep="PLAN-y.md"))
    base = tmp_path / "base"
    _write(base, "agent/plans/PLAN-x.md", _xplan(pri="P1 (operator) -- ruled", dep="PLAN-y.md"))
    result = _gate(root, "--base-tree", str(base))
    gate.assert_exit(1, result, "an operator Priority demoted to an AI value")
    gate.assert_contains(result.err, "    D17  ", "D17 is named")
    gate.log_pass("D17 planted through --base-tree reds the tree")


def test_d17_a_kept_marker_is_info_not_red(gate, tmp_path):
    root = _seed(tmp_path, x=_xplan(pri="P0 (operator) -- ruled", dep="PLAN-y.md"))
    base = tmp_path / "base"
    _write(base, "agent/plans/PLAN-x.md", _xplan(pri="P1 (operator) -- ruled", dep="PLAN-y.md"))
    result = _gate(root, "--base-tree", str(base))
    gate.assert_exit(0, result, "the operator's own level change")
    gate.assert_contains(result.out, "INFO D17 agent/plans/PLAN-x.md", "shown as INFO")
    gate.log_pass("a level change that keeps the marker is INFO only")


def test_d17_reads_the_merge_base_from_git(gate, tmp_path):
    """The real path: `git merge-base HEAD main`, then one `git grep` at the base. A plan on main carries an operator value; the branch demotes it."""
    import subprocess  # noqa: PLC0415

    root = _seed(tmp_path, x=_xplan(pri="P1 (operator) -- ruled", dep="PLAN-y.md"))

    def git(*args):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)

    git("init", "-q", "-b", "main")
    git("-c", "user.name=f", "-c", "user.email=f@example.com", "add", "-A")
    git("-c", "user.name=f", "-c", "user.email=f@example.com", "commit", "-qm", "base")
    git("checkout", "-q", "-b", "0925-1")
    path = root / "agent/plans/PLAN-x.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("P1 (operator) -- ruled", "P1 -- ruled"),
        encoding="utf-8",
    )
    result = _gate(root)
    gate.assert_exit(1, result, "demoted on the branch")
    gate.assert_contains(result.err, "    D17  ", "D17 from git")
    path.write_text(
        path.read_text(encoding="utf-8").replace("P1 -- ruled", "P1 (operator) -- ruled"),
        encoding="utf-8",
    )
    result = _gate(root)
    gate.assert_exit(0, result, "restored")
    gate.assert_contains(
        result.out, "1 operator-set Priority line(s) there", "the base was really read"
    )
    gate.log_pass("D17 reads the base from git and clears when the value is restored")


def test_set_x_writes_only_with_write_and_refuses_the_freeze(gate, tmp_path):
    root = _seed(tmp_path, x=_xplan(pri="P1 (operator) -- ruled", dep="PLAN-y.md"))
    path = root / "agent/plans/PLAN-x.md"
    before = path.read_bytes()
    dry = _gate(root, "--set-x", "agent/plans/PLAN-x.md", "Owns: docs/new/**")
    gate.assert_exit(0, dry, "a valid Owns")
    gate.assert_eq(path.read_bytes(), before, "a dry run writes nothing")
    frozen = _gate(
        root, "--set-x", "agent/plans/PLAN-x.md", "Priority: P0 (operator) -- ruled", "--write"
    )
    gate.assert_exit(1, frozen, "an operator value")
    gate.assert_contains(frozen.err, "operator-set", "the refusal says why")
    gate.assert_eq(path.read_bytes(), before, "the refusal writes nothing")
    wrote = _gate(root, "--set-x", "agent/plans/PLAN-x.md", "Owns: docs/new/**", "--write")
    gate.assert_exit(0, wrote, "written")
    gate.assert_contains(
        path.read_text(encoding="utf-8"), "Owns: docs/new/**\n", "the line is in the file"
    )
    gate.log_pass("--set-x is a dry run by default and never touches an operator value")


def test_overlaps_names_the_pair_and_a_shared_file(gate, tmp_path):
    root = _seed(
        tmp_path,
        x=_xplan(dep="PLAN-y.md").replace(
            "Owns: docs/fixture/**", "Owns: src/shared.py, docs/x/**"
        ),
    )
    y = root / "agent/plans/PLAN-y.md"
    y.write_text(
        y.read_text(encoding="utf-8").replace("Owns: docs/fixture/**", "Owns: src/*.py"),
        encoding="utf-8",
    )
    _write(root, "src/shared.py", "")
    result = _gate(root, "--overlaps")
    gate.assert_exit(0, result, "advisory")
    gate.assert_contains(result.out, "PLAN-x.md  x  PLAN-y.md", "the pair")
    gate.assert_contains(result.out, "shared files (1): src/shared.py", "the materialised file")
    gate.log_pass("--overlaps names the pair, the witness and the real shared file")


# ---- the migration dry run (section 8): five plans, two of them required.

MIG_GOLDEN = (
    "--- a/agent/plans/PLAN-live.md\n"
    "+++ b/agent/plans/PLAN-live.md\n"
    "@@ -5,2 +5,5 @@\n"
    " Depends-On: no-dep -- a fixture plan stands alone\n"
    "+Priority: P1 -- seed: Status executing, 1 open box(es)\n"
    "+Concurrency: parallel\n"
    "+Owns: src/a.py, src/b.py\n"
    " \n"
    "--- a/agent/plans/PLAN-rec.md\n"
    "+++ b/agent/plans/PLAN-rec.md\n"
    "@@ -8,2 +8,5 @@\n"
    " Record-Sig: 823c73dd\n"
    "+Priority: P3 -- seed: Status parked, 0 open box(es)\n"
    "+Concurrency: parallel\n"
    "+Owns: none -- seed: the plan cites no repo path to edit\n"
    " \n"
    "migrate-x --diff: 2 of 2 required plan(s) would change; nothing was written.\n"
)


def _mig_tree(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "mig"
    _write(
        root,
        "agent/plans/PLAN-live.md",
        "# PLAN: live\n\nStatus: executing\nOwner: cafe0000\nDepends-On: no-dep -- a fixture plan stands alone\n\n## Tasks\n\n- [ ] T1 edit `src/a.py` and `src/b.py`\n- [x] T0 read `src/c.py`\n",
    )
    _write(
        root,
        "agent/plans/PLAN-rec.md",
        "# PLAN: rec\nStatus: parked\nDepends-On: no-dep -- cites no other plan\nFirst-Seen: 2026-09-17\nOwner: housekeeping writer\nFull-Text: f7a5351a9 agent/PLAN-rec.md\nFull-Text-Blob: %s\nRecord-Sig: 823c73dd\n\n## Why\nparked\n"
        % ("0f714f0ac7" * 4),
    )
    _write(
        root,
        "agent/plans/PLAN-stub.md",
        "# stub\n\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-old.md\n",
    )
    _write(
        root, "agent/plans/PLAN-comp.md", "# PLAN: comp\nStatus: compacted\nOwner: x\n\n## Why\nx\n"
    )
    _write(
        root,
        "agent/plans/_done/PLAN-old.md",
        "# PLAN: old\n\nStatus: done\n\n- [ ] T1 `src/a.py`\n",
    )
    for name in ("a", "b", "c"):
        _write(root, "src/%s.py" % name, "")
    return root


def _snapshot(root: pathlib.Path) -> dict:
    import hashlib  # noqa: PLC0415

    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_migrate_x_diff_is_golden_and_writes_nothing(gate, tmp_path):
    root = _mig_tree(tmp_path)
    before = _snapshot(root)
    result = _gate(root, "--migrate-x", "--diff")
    gate.assert_exit(0, result, "a dry run")
    gate.assert_eq(
        result.out,
        MIG_GOLDEN,
        "the diff equals the golden: only the two required plans, three lines each",
    )
    gate.assert_eq(_snapshot(root), before, "the tree is byte-identical afterwards")
    gate.log_pass("--migrate-x --diff is the golden and writes nothing")


def test_migrate_x_apply_needs_write_refuses_drift_and_adds_three_lines(gate, tmp_path):
    root = _mig_tree(tmp_path)
    saved = _gate(root, "--migrate-x", "--save")
    gate.assert_exit(0, saved, "--save")
    proposal = root / ".ci/cache/plan-x-migration/proposal.json"
    gate.assert_eq(proposal.is_file(), True, "the proposal is written under the ignored cache")
    before = _snapshot(root)
    dry = _gate(root, "--migrate-x", "--apply", str(proposal))
    gate.assert_exit(0, dry, "--apply without --write")
    gate.assert_eq(_snapshot(root), before, "--apply without --write writes nothing")
    table = _gate(root, "--migrate-x", "--table")
    gate.assert_contains(table.out, "2 row(s).", "the approval table has the two required plans")
    live = root / "agent/plans/PLAN-live.md"
    original = live.read_text(encoding="utf-8")
    live.write_text(original + "\nedited after --save\n", encoding="utf-8")
    drift = _gate(root, "--migrate-x", "--apply", str(proposal), "--write")
    gate.assert_exit(1, drift, "a file changed since --save")
    gate.assert_contains(drift.err, "changed since --save", "the refusal names the drift")
    gate.assert_contains(
        live.read_text(encoding="utf-8"), "edited after --save", "nothing was written over it"
    )
    live.write_text(original, encoding="utf-8")
    wrote = _gate(root, "--migrate-x", "--apply", str(proposal), "--write")
    gate.assert_exit(0, wrote, "--apply --write")
    gate.assert_contains(wrote.out, "3\t0\tagent/plans/PLAN-live.md", "numstat 3 0")
    gate.assert_contains(wrote.out, "3\t0\tagent/plans/PLAN-rec.md", "numstat 3 0 on the record")
    rec = (root / "agent/plans/PLAN-rec.md").read_text(encoding="utf-8").splitlines()
    gate.assert_eq(
        rec.index("Record-Sig: 823c73dd") + 1 <= 10, True, "the record's spine stays within line 10"
    )
    gate.assert_eq(
        [ln.split(":")[0] for ln in rec[8:11]],
        ["Priority", "Concurrency", "Owns"],
        "the X lines land at 9-11",
    )
    gate.log_pass(
        "--apply writes only with --write, refuses drift, and adds exactly three lines per file"
    )
