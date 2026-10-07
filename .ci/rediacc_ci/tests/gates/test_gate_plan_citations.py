"""`check:ci-plan-citations`, driven as a process against real git trees.

WHY A REAL GIT FIXTURE. The gate's own defect (2026-09-21) was in `carried_lines()`, which shells `git show <base>:<origin>` and `git log --format=%H -- <origin>`; a fixture built from plain files on disk would prove nothing about that path. Each case commits a small history, points `PLAN_CITATIONS_BASE` at one of those commits, and reads the gate's real exit code.

THE REGRESSION THIS FILE PINS. Before the fix, `carried_lines` read only the blob at `base`. On a branch where a plan was reflowed AFTER `base` and THEN moved with a stub, no line in the moved file matched the base blob verbatim, so every line of the document read as newly added and its citations were judged for the first time -- 337 findings from zero new citations, measured on
the real branch. `_origin_last_content` closes this by walking the origin's own history for its last non-stub content, unioned with the base-blob read so the cheap path is never removed.
"""

import pathlib
import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_plan_citations.py")


def _git(repo: pathlib.Path, *args: str) -> str:
    result = harness.run(["git", "-C", str(repo), *args])
    if result.rc != 0:
        raise harness.GateAssertionError(
            "git %s failed in the fixture (rc=%d): %s" % (" ".join(args), result.rc, result.err)
        )
    return result.out


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(root: pathlib.Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", message)
    return _git(root, "rev-parse", "HEAD").strip()


def _init(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "tree"
    root.mkdir()
    # The gate imports its citation resolvers from `.claude/hooks/stop` via `paths.hooks_stop_dir(ROOT)`, so the fixture needs a real hop even though the git history under test is fake; a symlink to the actual repo's copy costs nothing and stays in sync by construction.
    (root / ".claude" / "hooks").mkdir(parents=True)
    (root / ".claude" / "hooks" / "stop").symlink_to(
        paths.hooks_stop_dir(paths.repo_root()), target_is_directory=True
    )
    # The gate's own `--selftest` resolves a REAL gate citation against `package.json`'s `scripts` block, so the fixture carries a copy rather than an invented one -- the selftest is meant to prove the resolver against this repo's own shape, not a shape a test author guessed at.
    shutil.copy(paths.repo_root() / "package.json", root / "package.json")
    _git(root, "init", "-q", ".")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "fixture")
    return root


def _gate(root: pathlib.Path, base: str) -> harness.RunResult:
    env = {"PLAN_CITATIONS_ROOT": str(root), "PLAN_CITATIONS_BASE": base}
    return harness.run([sys.executable, str(GATE)], cwd=paths.repo_root(), env=env)


def test_git_is_available_or_this_file_asserts_nothing(gate):
    if shutil.which("git") is None:
        gate.log_fail("git is absent; every case in this file would assert nothing")
    gate.log_pass("git is available, so the fixtures below are real repositories")


def test_the_subject_exists(gate):
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    gate.log_pass("check_plan_citations.py exists")


def _lived_fixture(tmp_path):
    """A plan citing a live file, reflowed, then moved with a stub, then the cited file deleted.

    Returns (root, base_sha) where `base_sha` is the commit BEFORE the reflow, the exact shape that broke `carried_lines` on the real branch: the moved file's content at `base` shares no verbatim line with the moved file's content at HEAD.
    """
    root = _init(tmp_path)
    _write(root, "lib/thing.py", "def f():\n    return 1\n")
    _write(
        root,
        "agent/PLAN-widget.md",
        "# PLAN: widget\nStatus: in-progress\n\nSee `lib/thing.py:1` for the entry point.\n",
    )
    base_sha = _commit(root, "base")

    # THE REFLOW: same meaning, different exact bytes, so a verbatim-line match against `base_sha` fails for every line of the document.
    _write(
        root,
        "agent/PLAN-widget.md",
        "# PLAN: widget\nStatus: in-progress\n\nSee\n`lib/thing.py:1`\nfor the entry point.\n",
    )
    _commit(root, "reflow")

    # THE MOVE: a stub at the old path, the content (reflowed) at the new one, exactly what `check_plan_folders.py --move` produces.
    (root / "agent" / "plans").mkdir(parents=True)
    shutil.move(root / "agent" / "PLAN-widget.md", root / "agent" / "plans" / "PLAN-widget.md")
    _write(
        root,
        "agent/PLAN-widget.md",
        "# PLAN: widget (moved)\nStatus: moved\nMoved-To: agent/plans/PLAN-widget.md\n\nThis plan moved to `agent/plans/PLAN-widget.md`.\n",
    )
    _commit(root, "move")

    # THE ROT: the cited file is gone, so the citation is now genuinely broken, but it was NOT written by the move.
    (root / "lib" / "thing.py").unlink()
    _commit(root, "delete the cited file")
    return root, base_sha


def test_a_move_carries_no_new_citation_even_after_a_reflow(gate, tmp_path):
    """REGRESSION. Before the fix this exited 1: the reflow defeated the base-blob match and the whole moved document read as added."""
    root, base_sha = _lived_fixture(tmp_path)
    result = _gate(root, base_sha)
    gate.assert_exit(0, result, "a move plus an earlier reflow carries no new citation")
    gate.log_pass("the reflow-then-move sequence no longer manufactures 337 findings from zero")


def test_a_citation_written_after_the_move_is_still_judged(gate, tmp_path):
    """CONTROL. The fix must not swallow real new debt: a line added after the move, in the SAME moved file, still has to resolve."""
    root, base_sha = _lived_fixture(tmp_path)
    plan = root / "agent" / "plans" / "PLAN-widget.md"
    plan.write_text(
        plan.read_text(encoding="utf-8") + "\nAlso see `lib/nonexistent.py:1`.\n", encoding="utf-8"
    )
    _commit(root, "a genuinely new stale citation")
    result = _gate(root, base_sha)
    gate.assert_exit(1, result, "a citation written after the move is not excused by it")
    gate.assert_contains(result.out + result.err, "lib/nonexistent.py", "and it names the new line")
    gate.log_pass("new debt on a moved plan still reds")


def test_a_never_moved_plan_with_a_new_stale_citation_still_reds(gate, tmp_path):
    """CONTROL. The fix touches only the moved-plan path; an ordinary plan is unaffected."""
    root = _init(tmp_path)
    _write(root, "agent/PLAN-static.md", "# PLAN: static\nStatus: in-progress\n")
    base_sha = _commit(root, "base")
    _write(
        root,
        "agent/PLAN-static.md",
        "# PLAN: static\nStatus: in-progress\n\nSee `lib/nope.py:1`.\n",
    )
    _commit(root, "a stale citation, never moved")
    result = _gate(root, base_sha)
    gate.assert_exit(1, result, "an ordinary plan's new stale citation still reds")
    gate.log_pass("the exclusion is not a blanket amnesty")


def test_the_exclusion_is_scoped_to_the_moved_plan(gate, tmp_path):
    """CONTROL. A stale citation added to a DIFFERENT plan in the same commit as an unrelated move is still reported."""
    root, base_sha = _lived_fixture(tmp_path)
    _write(
        root, "agent/PLAN-other.md", "# PLAN: other\nStatus: in-progress\n\nSee `lib/gone.py:1`.\n"
    )
    _commit(root, "a stale citation in a sibling plan")
    result = _gate(root, base_sha)
    gate.assert_exit(1, result, "the sibling plan's new citation is not excused by the move")
    gate.assert_contains(result.out + result.err, "PLAN-other.md", "and it is the one named")
    gate.log_pass("the carried-lines exclusion is per moved plan, not global")


# THE ALL-DIGIT `commit:` CITATION (#0241c97d). About 1 in 69 nine-character abbreviations is all digits, and the extractor skipped every all-digit token as a run id or a date, so a real `commit:<sha9>` tick citation was never judged: a dead one passed, and a plan whose only citation was one read as a blind corpus. The `commit:` form now says "this is a sha"; a bare digit run is still a number.


def _digit_cited_plan(tmp_path, line: str) -> tuple[pathlib.Path, str]:
    """A plan committed at a base, then `line` added under its box. Returns (root, base). `{d9}` in `line` becomes the 9-character, ALL-DIGIT abbreviation of a real commit on this history (re-dated until it is one, the shape #e9852315 drew by chance)."""
    from rediacc_ci.tests.gates.test_gate_plan_folders import _force_digit_prefix  # noqa: PLC0415

    root = _init(tmp_path)
    _write(root, "agent/PLAN-digits.md", "# PLAN: digits\nStatus: in-progress\n\n- [ ] T1 a box\n")
    base = _commit(root, "base")
    _write(root, "src/work.txt", "work\n")
    _commit(root, "feat: the work")
    sha = _force_digit_prefix(root)
    assert sha[:9].isdigit(), sha
    _write(
        root,
        "agent/PLAN-digits.md",
        "# PLAN: digits\nStatus: in-progress\n\n- [x] T1 a box\n%s\n" % line.format(d9=sha[:9]),
    )
    _commit(root, "tick")
    return root, base


def test_an_all_digit_commit_citation_that_resolves_is_read(gate, tmp_path):
    """Red before #0241c97d: the only citation was skipped, so the corpus read as ZERO citations and the gate refused as blind (exit 1)."""
    root, base = _digit_cited_plan(tmp_path, "    (ticked) commit:{d9} rc=0")
    result = _gate(root, base)
    gate.assert_exit(0, result, "a resolving all-digit commit: citation is judged and passes")
    gate.assert_contains(result.out, "carrying 1 citation(s)", "the extractor counted it")
    gate.log_pass("an all-digit commit:<sha9> that resolves is read and verified")


def test_an_all_digit_commit_citation_that_does_not_resolve_is_reported(gate, tmp_path):
    """Red before #0241c97d: the dead pointer was skipped as a run id and the gate passed."""
    root, base = _digit_cited_plan(
        tmp_path, "    (ticked) commit:123456789 rc=0, see `package.json:1`"
    )
    result = _gate(root, base)
    gate.assert_exit(1, result, "a dead all-digit commit: citation is a finding")
    gate.assert_contains(result.err, "123456789", "and the finding names it")
    gate.log_pass("an all-digit commit:<sha9> that resolves to nothing is reported")


def test_a_bare_digit_run_is_still_not_judged(gate, tmp_path):
    """CONTROL, the other direction: without the prefix the same digits are a run id, and judging them would red on every CI run id a plan quotes."""
    root, base = _digit_cited_plan(
        tmp_path, "    (ticked) run 123456789 went red, see `package.json:1`"
    )
    result = _gate(root, base)
    gate.assert_exit(0, result, "an unprefixed digit run is not a citation")
    gate.log_pass("a bare all-digit run id is still skipped")
