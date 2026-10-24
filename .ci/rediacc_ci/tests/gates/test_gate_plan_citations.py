"""`check:ci-plan-citations`, driven as a process against real git trees.

WHY A REAL GIT FIXTURE. The gate's own defect (2026-09-21) was in `carried_lines()`, which shells `git show <base>:<origin>` and `git log --format=%H -- <origin>`; a fixture built from plain files on disk would prove nothing about that path. Each case commits a small history, points `PLAN_CITATIONS_BASE` at one of those commits, and reads the gate's real exit code.

THE REGRESSION THIS FILE PINS. Before the fix, `carried_lines` read only the blob at `base`. On a branch where a plan was reflowed AFTER `base` and THEN moved with a stub, no line in the moved file matched the base blob verbatim, so every line of the document read as newly added and its citations were judged for the first time -- 337 findings from zero new citations, measured on
the real branch. `_origin_last_content` closes this by walking the origin's own history for its last non-stub content, unioned with the base-blob read so the cheap path is never removed.
"""

import importlib.util
import json
import os
import pathlib
import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness
from rediacc_ci.tests.gates.test_gate_plan_folders import _force_digit_prefix

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


# A COMMIT ON origin/main (2026-10-08). CD pushes release-state and tap-pointer commits straight to main, and a plan written on a branch cut before them cites them. main is never rewritten, so such a commit survives every rebase-merge; the gate refused it with "names neither a blob nor a commit in this clone", which was also false: the "exists but not an ancestor" branch had become unreachable once the commit resolver began demanding ancestry of HEAD.


def _side_commit(root: pathlib.Path, branch: str) -> str:
    """A commit on `branch`, off the base and NOT an ancestor of the checked-out branch."""
    head = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    _git(root, "checkout", "-qb", branch)
    _write(root, "side-%s.txt" % branch, "side\n")
    sha = _commit(root, "chore: on %s" % branch)
    _git(root, "checkout", "-q", head)
    return sha


def _spelled(sha: str, *, forced: bool = False) -> str:
    """How a plan cites `sha`: its nine-character abbreviation, or `commit:<abbrev>` when the abbreviation is all digits or `forced`.

    The extractor reads a bare all-digit token as a number, not a citation (check_plan_citations.py:29-35). About 1 in 69 abbreviations is all digits and the fixture's sha moves with the clock, so a draw that lands there needs the `commit:` spelling (PR 600 run on 078a550ad drew one and the gate answered VACUOUS INPUT).
    """
    short = sha[:9]
    return "commit:%s" % short if forced or short.isdigit() else short


def test_the_spelling_helper_prefixes_an_all_digit_abbreviation():
    assert _spelled("123456789abcdef") == "commit:123456789"
    assert _spelled("12345678a0000000") == "12345678a"
    assert _spelled("12345678a0000000", forced=True) == "commit:12345678a"


def _cited_plan(tmp_path, cite_from, *, forced=False) -> tuple[pathlib.Path, str, str]:
    root = _init(tmp_path)
    _write(root, "agent/PLAN-main.md", "# PLAN: main\nStatus: in-progress\n\n- [ ] T1 a box\n")
    base = _commit(root, "base")
    sha = cite_from(root)
    cited = _spelled(sha, forced=forced)
    _write(
        root,
        "agent/PLAN-main.md",
        "# PLAN: main\nStatus: in-progress\n\n- [ ] T1 a box\n\nThe release ran (%s).\n" % cited,
    )
    _commit(root, "cite")
    return root, base, sha


def test_a_commit_on_origin_main_resolves(gate, tmp_path):
    def on_main(root):
        sha = _side_commit(root, "mainline")
        _git(root, "update-ref", "refs/remotes/origin/main", sha)
        return sha

    root, base, _ = _cited_plan(tmp_path, on_main)
    result = _gate(root, base)
    gate.assert_exit(0, result, "a commit reachable from origin/main is a live citation")
    gate.log_pass("a commit on origin/main, not yet in the branch, resolves")


def test_the_commit_spelling_is_judged_like_a_bare_sha(gate, tmp_path):
    """The `commit:` spelling is otherwise drawn only by an all-digit sha, about 1 run in 69, so it is forced here."""

    def on_main(root):
        sha = _side_commit(root, "mainline")
        _git(root, "update-ref", "refs/remotes/origin/main", sha)
        return sha

    (tmp_path / "live").mkdir()
    (tmp_path / "orphan").mkdir()
    root, base, _ = _cited_plan(tmp_path / "live", on_main, forced=True)
    gate.assert_exit(
        0, _gate(root, base), "a `commit:` citation reachable from origin/main resolves"
    )
    root, base, _ = _cited_plan(
        tmp_path / "orphan", lambda root: _side_commit(root, "orphan"), forced=True
    )
    result = _gate(root, base)
    gate.assert_exit(1, result, "a `commit:` citation of an orphan commit is a finding")
    gate.assert_contains(result.err, "EXISTS in this clone", "named as an orphan")
    gate.log_pass("the commit: spelling resolves and refuses like a bare sha")


def test_an_orphan_commit_is_named_as_one(gate, tmp_path):
    root, base, _ = _cited_plan(tmp_path, lambda root: _side_commit(root, "orphan"))
    result = _gate(root, base)
    gate.assert_exit(1, result, "a commit reachable from neither HEAD nor origin/main is a finding")
    gate.assert_contains(result.err, "EXISTS in this clone", "and the message says it exists")
    gate.log_pass("an orphan commit gets the orphan message, not 'names neither'")


# THE `commit` KIND (eb3bcb68.1). `check_plan_record` hands `unresolved` a `commit` kind directly, so it is driven in-process here: the citation text never produces that kind.


def _unresolved_fn():
    spec = importlib.util.spec_from_file_location("_plan_citations_under_test", GATE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    already = str(GATE.parent.resolve()) in sys.path
    added = paths.on_sys_path(GATE.parent)
    try:
        spec.loader.exec_module(module)
    finally:
        if not already:
            sys.path.remove(added)
    return module.unresolved


def test_a_commit_kind_on_origin_main_but_not_head_passes(gate, tmp_path):
    def on_main(root):
        sha = _side_commit(root, "mainline")
        _git(root, "update-ref", "refs/remotes/origin/main", sha)
        return sha

    root, _base, sha = _cited_plan(tmp_path, on_main)
    bad, why = _unresolved_fn()(root, "commit", sha)
    if bad:
        gate.log_fail("a commit-kind citation reachable from origin/main must pass: %s" % why)
    gate.log_pass("commit kind: reachable from origin/main only, passes")


def test_an_orphan_commit_kind_gets_the_orphan_message_naming_only_existing_refs(gate, tmp_path):
    root, _base, sha = _cited_plan(tmp_path, lambda root: _side_commit(root, "orphan"))
    unresolved = _unresolved_fn()
    bad, why = unresolved(root, "commit", sha)
    if not bad:
        gate.log_fail("an orphan commit-kind citation must be a finding")
    gate.assert_contains(why, "EXISTS in this clone", "and the message says it exists")
    gate.assert_contains(why, "ancestor of HEAD,", "no origin/main ref here, so only HEAD is named")
    if "origin/main" in why:
        gate.log_fail("the missing ref must not be named: %s" % why)
    _git(root, "update-ref", "refs/remotes/origin/main", _git(root, "rev-parse", "HEAD").strip())
    _bad2, why2 = unresolved(root, "commit", sha)
    gate.assert_contains(why2, "HEAD or origin/main", "with the ref present both are named")
    gate.log_pass("commit kind: orphan message, refs named only when they exist")


def test_a_cited_tree_only_this_clone_holds_reds_and_a_committed_one_passes(gate, tmp_path):
    """PR #601: a tree a tool wrote while hashing an uncommitted state existed locally, so the gate passed, and CI refused it as naming nothing. A cited blob or tree must be reachable from HEAD."""
    root = _init(tmp_path)
    _write(root, "agent/PLAN-trees.md", "# PLAN: trees\nStatus: in-progress\n")
    _write(root, "src/kept.txt", "kept\n")
    base_sha = _commit(root, "base")
    committed_tree = _git(root, "rev-parse", "HEAD^{tree}").strip()
    _write(root, "src/scratch.txt", "never committed\n")
    _git(root, "add", "src/scratch.txt")
    loose_tree = _git(root, "write-tree").strip()
    _git(root, "rm", "-q", "--cached", "src/scratch.txt")
    (root / "src" / "scratch.txt").unlink()
    _write(
        root,
        "agent/PLAN-trees.md",
        "# PLAN: trees\nStatus: in-progress\n\nThe receipt ran on `%s`.\n" % loose_tree[:12],
    )
    _commit(root, "cite a tree only this clone holds")
    result = _gate(root, base_sha)
    gate.assert_exit(1, result, "a loose tree citation reds locally, as it does in CI")
    gate.assert_contains(
        result.out + result.err, "exists only in this clone", "the refusal names why"
    )
    _write(
        root,
        "agent/PLAN-trees.md",
        "# PLAN: trees\nStatus: in-progress\n\nThe base tree is `%s`.\n" % committed_tree[:12],
    )
    _commit(root, "cite the committed tree instead")
    ok = _gate(root, base_sha)
    gate.assert_exit(0, ok, "a committed tree citation still passes")
    gate.log_pass("a cited tree is judged by reachability, not presence")


# WHOLE-PLAN MODE (PLAN-plan-preflight PF2). `--plan <rel> --json` judges every line of one plan, classes each line as blocking or history, and reports a fileline citation whose cited text changed since the commit that last wrote the citing plan line. PF3 parses the JSON, so its shape is pinned here as well as its verdicts.

_CONTRACT_KEYS = ["plan", "unresolved", "drifted"]
_UNRESOLVED_KEYS = ["line", "kind", "token", "why", "blocking"]
_DRIFTED_KEYS = ["line", "token", "relocate_to", "blocking"]


def _plan_gate(root: pathlib.Path, rel: str, *extra: str) -> harness.RunResult:
    env = {"PLAN_CITATIONS_ROOT": str(root)}
    return harness.run(
        [sys.executable, str(GATE), "--plan", rel, *extra], cwd=paths.repo_root(), env=env
    )


def _plan_json(gate, result: harness.RunResult) -> dict:
    try:
        data = json.loads(result.out)
    except ValueError:
        gate.log_fail(
            "stdout is not one JSON object: %r / stderr %r" % (result.out[:400], result.err[-400:])
        )
    if list(data) != _CONTRACT_KEYS:
        gate.log_fail("top-level keys drifted from the frozen contract: %s" % list(data))
    for u in data["unresolved"]:
        if list(u) != _UNRESOLVED_KEYS:
            gate.log_fail("an unresolved row's keys drifted from the contract: %s" % list(u))
    for d in data["drifted"]:
        if list(d) != _DRIFTED_KEYS:
            gate.log_fail("a drifted row's keys drifted from the contract: %s" % list(d))
    return data


_PLAN = "agent/plans/PLAN-drift.md"


def _drift_fixture(tmp_path, body: str, after: str) -> pathlib.Path:
    """`lib/a.txt` committed as alpha..delta, a plan citing it committed, then `lib/a.txt` rewritten to `after` and committed."""
    root = _init(tmp_path)
    _write(root, "lib/a.txt", "alpha\nbravo\ncharlie\ndelta\n")
    _write(root, _PLAN, "# PLAN: drift\nStatus: in-progress\n\n" + body)
    _commit(root, "base")
    _write(root, "lib/a.txt", after)
    _commit(root, "the cited file changes under the plan")
    return root


def test_plan_mode_a_blocking_rewritten_line_reds_with_the_contract(gate, tmp_path):
    root = _drift_fixture(
        tmp_path, "- [ ] T1 see `lib/a.txt:3`\n", "alpha\nbravo\nCHARLIE-rewritten\ndelta\n"
    )
    result = _plan_gate(root, _PLAN, "--json")
    gate.assert_exit(1, result, "a blocking drift with nowhere to relocate is a finding")
    data = _plan_json(gate, result)
    want = [{"line": 4, "token": "lib/a.txt:3", "relocate_to": None, "blocking": True}]
    if data["drifted"] != want or data["unresolved"] or data["plan"] != _PLAN:
        gate.log_fail("unexpected report: %s" % data)
    gate.log_pass("a rewritten cited line on an open box is blocking drift, relocate_to null")


def test_plan_mode_a_moved_line_is_relocatable_and_does_not_red(gate, tmp_path):
    root = _drift_fixture(
        tmp_path, "- [ ] T1 see `lib/a.txt:2`\n", "alpha\nINSERTED\nbravo\ncharlie\ndelta\n"
    )
    result = _plan_gate(root, _PLAN, "--json")
    gate.assert_exit(0, result, "a uniquely relocatable drift is repairable, not a refusal")
    data = _plan_json(gate, result)
    want = [{"line": 4, "token": "lib/a.txt:2", "relocate_to": 3, "blocking": True}]
    if data["drifted"] != want:
        gate.log_fail("expected one relocatable drift to :3, got %s" % data["drifted"])
    gate.log_pass("a moved cited line carries relocate_to with its new line")


def test_plan_mode_an_unchanged_citation_is_silent(gate, tmp_path):
    """CONTROL for both drift cases: the same history, citing a line that did not change."""
    root = _drift_fixture(
        tmp_path, "- [ ] T1 see `lib/a.txt:4`\n", "alpha\nbravo\nCHARLIE-rewritten\ndelta\n"
    )
    result = _plan_gate(root, _PLAN, "--json")
    gate.assert_exit(0, result, "an unchanged cited line is clean")
    data = _plan_json(gate, result)
    if data["drifted"] or data["unresolved"]:
        gate.log_fail("expected an empty report, got %s" % data)
    gate.assert_contains(result.err, "1 fileline(s) drift-checked", "and it really was checked")
    gate.log_pass("an unchanged citation is silent, and the shape line proves it was read")


def test_plan_mode_history_lines_are_reported_not_judged(gate, tmp_path):
    body = "- [x] T1 done, see `lib/a.txt:3`\n    (ticked) evidence `lib/nope.txt:1`\n"
    root = _drift_fixture(tmp_path, body, "alpha\nbravo\nCHARLIE-rewritten\ndelta\n")
    result = _plan_gate(root, _PLAN, "--json")
    gate.assert_exit(0, result, "drift and a dead pointer on history lines do not block")
    data = _plan_json(gate, result)
    if [d["blocking"] for d in data["drifted"]] != [False] or [
        u["blocking"] for u in data["unresolved"]
    ] != [False]:
        gate.log_fail("expected one non-blocking drift and one non-blocking unresolved: %s" % data)
    gate.log_pass("a done box and a (ticked) line are reported as history")


def test_plan_mode_a_blocking_dead_pointer_reds(gate, tmp_path):
    """CONTROL for the history case: the same dead pointer in prose blocks."""
    root = _drift_fixture(
        tmp_path, "Prose cites `lib/nope.txt:1`.\n", "alpha\nbravo\ncharlie\ndelta\nepsilon\n"
    )
    result = _plan_gate(root, _PLAN, "--json")
    gate.assert_exit(1, result, "a dead pointer in prose blocks")
    data = _plan_json(gate, result)
    if [(u["kind"], u["token"], u["blocking"]) for u in data["unresolved"]] != [
        ("fileline", "lib/nope.txt:1", True)
    ]:
        gate.log_fail("expected one blocking unresolved fileline: %s" % data)
    gate.log_pass("a blocking unresolved citation reds")


def test_plan_mode_an_uncommitted_line_cannot_have_drifted(gate, tmp_path):
    root = _drift_fixture(tmp_path, "", "alpha\nINSERTED\nbravo\ncharlie\ndelta\n")
    (root / _PLAN).write_text(
        (root / _PLAN).read_text(encoding="utf-8") + "Today `lib/a.txt:3` reads bravo.\n",
        encoding="utf-8",
    )
    result = _plan_gate(root, _PLAN, "--json")
    gate.assert_exit(0, result, "a line written against today's tree has not drifted")
    data = _plan_json(gate, result)
    if data["drifted"]:
        gate.log_fail("an uncommitted line was reported as drifted: %s" % data)
    gate.assert_contains(result.err, "1 on uncommitted line(s)", "and the shape line says why")
    gate.log_pass("an uncommitted citing line is compared with the tree it was written against")


def test_plan_mode_a_non_utf8_cited_blob_does_not_crash(gate, tmp_path):
    """A cited file in a legacy encoding is decoded leniently; strict decoding raised UnicodeDecodeError and printed no verdict."""
    root = _init(tmp_path)
    (root / "lib").mkdir()
    (root / "lib/a.txt").write_bytes(b"caf\xe9\nbravo\n")
    _write(root, _PLAN, "# PLAN: enc\nStatus: in-progress\n\n- [ ] T1 see `lib/a.txt:2`\n")
    _commit(root, "base")
    (root / "lib/a.txt").write_bytes(b"caf\xe9\nBRAVO-rewritten\n")
    _commit(root, "the cited file changes")
    result = _plan_gate(root, _PLAN, "--json")
    gate.assert_exit(1, result, "the drift is judged, not a traceback")
    data = _plan_json(gate, result)
    if len(data["drifted"]) != 1:
        gate.log_fail("expected one drifted row: %s" % data)
    gate.log_pass("non-UTF-8 cited blobs are decoded leniently")


def test_plan_mode_an_unreadable_blob_fails_closed(gate, tmp_path):
    """The partial-clone shape: the tree names the old blob and the blob is not in the clone. The mode must refuse (rc 2), never report "no drift"."""
    root = _drift_fixture(
        tmp_path, "- [ ] T1 see `lib/a.txt:4`\n", "alpha\nbravo\nCHARLIE-rewritten\ndelta\n"
    )
    old = _git(root, "rev-parse", "HEAD~1:lib/a.txt").strip()
    obj = root / ".git" / "objects" / old[:2] / old[2:]
    if not obj.is_file():
        gate.log_fail(
            "the fixture blob is not a loose object, so the plant cannot be made: %s" % obj
        )
    obj.chmod(0o644)
    obj.unlink()
    result = _plan_gate(root, _PLAN, "--json")
    gate.assert_exit(2, result, "an unreadable history blob is a refusal")
    gate.assert_contains(
        result.err, "cannot read the history", "and it says what it could not read"
    )
    if result.out.strip():
        gate.log_fail("no JSON may be printed when the answer is unknown: %r" % result.out[:200])
    gate.log_pass("a missing history blob fails closed, it does not read as clean")


def test_plan_mode_refuses_a_plan_it_cannot_see(gate, tmp_path):
    root = _drift_fixture(tmp_path, "", "alpha\n")
    for rel in ("agent/plans/PLAN-absent.md", "docs/not-a-plan.md"):
        result = _plan_gate(root, rel, "--json")
        gate.assert_exit(2, result, "%s is not a judgeable plan" % rel)
    gate.log_pass("a missing or out-of-scope plan is a refusal, not an empty report")


def test_plan_mode_on_the_real_tree_prints_valid_json(gate):
    """The box's acceptance, on this repository: the command prints one JSON object in the contract's shape."""
    rel = "agent/plans/PLAN-plan-per-pr-loop.md"
    if not (paths.repo_root() / rel).is_file():
        gate.log_fail("%s is gone; pick another in-scope plan for this acceptance" % rel)
    result = harness.run(
        [sys.executable, str(GATE), "--plan", rel, "--json"], cwd=paths.repo_root()
    )
    if result.rc not in (0, 1):
        gate.log_fail("rc %d: %s" % (result.rc, result.err[-600:]))
    data = _plan_json(gate, result)
    if data["plan"] != rel:
        gate.log_fail("plan key %r" % data["plan"])
    gate.log_pass("the real plan yields contract-shaped JSON (rc %d)" % result.rc)


def test_plan_mode_a_ticked_line_is_history_even_under_an_open_box(gate, tmp_path):
    """A partially worked open box carries `(ticked)` evidence for its finished half; that line is history by its own marker, while the open box's plain continuation still blocks."""
    body = (
        "- [ ] T1 open box\n"
        "    (ticked) half done, see `lib/nope.txt:1`\n"
        "    still open, see `lib/gone.txt:1`\n"
    )
    root = _drift_fixture(tmp_path, body, "alpha\nbravo\ncharlie\ndelta\nepsilon\n")
    result = _plan_gate(root, _PLAN, "--json")
    gate.assert_exit(1, result, "the plain continuation's dead pointer still blocks")
    data = _plan_json(gate, result)
    got = [(u["token"], u["blocking"]) for u in data["unresolved"]]
    if got != [("lib/nope.txt:1", False), ("lib/gone.txt:1", True)]:
        gate.log_fail(
            "expected the (ticked) line as history and the continuation as blocking: %s" % got
        )
    gate.log_pass("(ticked) marks history on its own; an open box's continuation blocks")


def test_unimportable_resolvers_exit_2_in_plan_mode_and_1_in_the_diff_gate(tmp_path) -> None:
    """`--plan` documents 2 for "the instrument could not answer"; the diff-scoped gate keeps 1 (worklist #d8634506)."""
    env = {**os.environ, "PLAN_CITATIONS_ROOT": str(tmp_path)}
    plan_mode = harness.run(
        [sys.executable, str(GATE), "--plan", "agent/plans/PLAN-p.md", "--json"],
        cwd=paths.repo_root(),
        env=env,
    )
    diff_mode = harness.run([sys.executable, str(GATE)], cwd=paths.repo_root(), env=env)
    assert "VACUOUS INPUT" in plan_mode.err
    assert plan_mode.rc == 2, plan_mode
    assert diff_mode.rc == 1, diff_mode
