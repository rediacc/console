"""Gate test for `check:ci-scope-mirrors` (`.ci/scripts/quality/check_scope_mirrors.py`), plan SM6 of agent/plans/PLAN-scope-mirrors.md.

WHAT IT GUARDS. CLAUDE.md's PR-scope clauses are anchored and pinned; seven other files restate them by hand. The gate's own selftest proves its checks fire on a toy fixture. This file proves the same checks fire on the REAL corpus: the real CLAUDE.md, the real mirrors, the real registry and baseline, with the entry point driven by path exactly as CI drives it.

EVERY PLANT GOES INTO A COPY under a temp root, passed with `--root`; no tracked file is written (`check:ci-gate-test-real-file-plants`). The copy carries what the gate reads: the canonical file, the C9 corpus directories, the oracle and quote-source modules and the two `.ci/config` files. Each plant is built with `rediacc_ci.controls.plant`, which raises when the needle is absent, so a drifted anchor reads as a broken CONTROL rather than as a gate that stayed green.

BOTH DIRECTIONS. T1 is the untouched copy and must be green with counts at or above the floors the success line prints. T2 replays the 8ed69711c miss and asserts the UNTOUCHED mirrors stay silent; T3 asserts a changed canonical reports C2 and no C5/C6; T5 asserts a correctly marked cut is silent; T8 asserts an anchored restatement is C10 and not C9; T9 and T10 assert the write paths refuse and then admit.

THE FLOORS ARE READ, NEVER TYPED: T1 parses `N clauses (floor F)` and `M mirror checks (floor G)` from the one success line, so the floors live in the registry and nowhere else, and requires N == F and M == G, so a floor can be neither lowered nor left behind a new clause.
"""

import json
import os
import pathlib
import re
import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.controls import plant
from rediacc_ci.tests.gates import harness

GATE_REL = ".ci/scripts/quality/check_scope_mirrors.py"
GATE = paths.from_root(*GATE_REL.split("/"))
REPO = paths.repo_root()
REGISTRY_REL = ".ci/config/scope-mirrors.json"
BASELINE_REL = ".ci/config/scope-mirrors-baseline.json"

# What the gate reads, copied into every temp root.
COPY = (
    "CLAUDE.md",
    ".claude/commands",
    ".claude/agents",
    ".claude/output-styles",
    ".claude/skills",
    "agent/plans/QUEUE.md",
    ".claude/rediacc_hooks/guards/block_settled_questions.py",
    ".claude/rediacc_hooks/guards/block_turbo_early_push.py",
    ".claude/hooks/stop/wl_planqueue.py",
    REGISTRY_REL,
    BASELINE_REL,
)

TRAILERS = ".claude/skills/pr-epics/trailers.md"
STANDING = ".claude/output-styles/standing-orders.md"
BABYSITTER = ".claude/agents/pr-babysitter.md"
PR_MERGE = ".claude/commands/pr-merge.md"
SKILL = ".claude/skills/pr-epics/SKILL.md"
GUARD = ".claude/rediacc_hooks/guards/block_settled_questions.py"
KINDS_SRC = ".claude/rediacc_hooks/guards/block_turbo_early_push.py"
HANDOFF = ".claude/commands/handoff.md"

SHAPE_RE = re.compile(r"(\d+) clauses \(floor (\d+)\), (\d+) mirror checks \(floor (\d+)\)")
TURBO_ANCHOR = "<!-- scope: pr.turbo-batch-end -->"

# The gate runs its 65 selftest controls first, then the real tree; well under a minute measured 2026-10-08.
GATE_TIMEOUT = 300


class Proving:
    """The harness with every `assert_*` also recorded as a proof.

    The `gate` fixture's teardown counts `log_pass` lines, not assertions, so a test made only of `assert_eq` calls reads as one that proved nothing. Each assertion here names what it proves in its message, and that message becomes its PASS line.
    """

    def __init__(self, gate) -> None:
        self._gate = gate

    def __getattr__(self, name: str):
        attr = getattr(self._gate, name)
        if not name.startswith("assert_") or name == "assert_vacuous_tree_fails":
            return attr

        def proved(*args, **kwargs):
            attr(*args, **kwargs)
            label = kwargs.get("msg") or (args[-1] if args and isinstance(args[-1], str) else name)
            self._gate.log_pass(label)

        return proved


def build_root(gate, base: pathlib.Path) -> pathlib.Path:
    """A fresh copy of what the gate reads, proved non-empty before any plant lands on it."""
    if not GATE.is_file():
        gate.log_fail("gate not found: %s" % GATE_REL)
    if not os.access(GATE, os.X_OK):
        gate.log_fail("gate not executable: %s" % GATE_REL)
    root = base / "tree"
    for rel in COPY:
        src = REPO / rel
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        elif src.is_file():
            shutil.copy2(src, dst)
        else:
            gate.log_fail("%s is missing from the repository; the copy would be vacuous" % rel)
    return root


def mutate(root: pathlib.Path, rel: str, old: str, new: str, count: int = -1) -> None:
    path = root / rel
    path.write_text(plant(path.read_text(encoding="utf-8"), old, new, count), encoding="utf-8")


def run_gate(root: pathlib.Path, *extra: str) -> harness.RunResult:
    return harness.run(
        [sys.executable, os.fspath(GATE), "--root", os.fspath(root), *extra],
        cwd=REPO,
        timeout=GATE_TIMEOUT,
    )


def findings(result: harness.RunResult) -> list[str]:
    """The red finding lines on stderr, one per finding (the indented id lines are not findings)."""
    return [line for line in result.err.splitlines() if re.match(r"^\S+ C\d+ ", line)]


def line_of(root: pathlib.Path, rel: str, starts: str) -> str:
    for line in (root / rel).read_text(encoding="utf-8").split("\n"):
        if line.startswith(starts):
            return line
    return ""


def turbo_sentence(root: pathlib.Path) -> str:
    """The anchored turbo sentence of the trailers mirror, anchor excluded, to the end of its list item."""
    line = line_of(root, TRAILERS, "- **Pushing is separate**")
    at = line.find(TURBO_ANCHOR)
    return line[at + len(TURBO_ANCHOR) :] if at >= 0 else ""


def test_t1_untouched_copy_is_green_at_or_above_the_floors(gate):
    gate = Proving(gate)
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        result = run_gate(root)
        gate.assert_exit(0, result, "T1: the untouched copy of the real tree is green")
        gate.assert_eq(result.err.strip(), "", "T1: a green run writes nothing to stderr")
        shape = SHAPE_RE.search(result.out)
        if shape is None:
            gate.log_fail("T1: the success line carries no shape: %r" % result.out[-400:])
            return
        clauses, floor_c, mirrors, floor_m = (int(x) for x in shape.groups())
        # A RATCHET, NOT A MINIMUM: each floor must EQUAL its measured count, so a floor lowered in the registry reds here, and a clause or mirror added without raising its floor reds too (review 169ccbe2.1).
        gate.assert_eq(
            (clauses, floor_c >= 9),
            (floor_c, True),
            "T1: %d clauses, floor %d (plan C0: >= 9)" % (clauses, floor_c),
        )
        gate.assert_eq(
            (mirrors, floor_m >= 25),
            (floor_m, True),
            "T1: %d mirror checks, floor %d (plan C0: >= 25)" % (mirrors, floor_m),
        )


def test_t1_an_empty_tree_fails_loudly(gate):
    gate = Proving(gate)
    with harness.temp_dir() as tmp:
        gate.assert_vacuous_tree_fails(
            run_gate, tmp, "the gate has nothing to check", "T1b: an empty --root is red"
        )


def test_t2_the_8ed69711c_miss_names_only_the_drifted_mirror(gate):
    gate = Proving(gate)
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        sentence = turbo_sentence(root)
        if "TURBO_PUSH_REASON" not in sentence:
            gate.log_fail(
                "T2: the trailers mirror no longer carries the anchored turbo sentence: %r"
                % sentence
            )
        mutate(root, TRAILERS, TURBO_ANCHOR + sentence, TURBO_ANCHOR, 1)
        result = run_gate(root)
        gate.assert_exit(1, result, "T2: a mirror missing the turbo sentence is red")
        found = findings(result)
        hits = [f for f in found if TRAILERS in f and "pr.turbo-batch-end" in f]
        gate.assert_eq(
            bool(hits),
            True,
            "T2: a finding names %s and pr.turbo-batch-end; got %r" % (TRAILERS, found),
        )
        for quiet in (STANDING, BABYSITTER, PR_MERGE):
            gate.assert_eq(
                [f for f in found if quiet in f],
                [],
                "T2: the untouched mirror %s stays silent" % quiet,
            )


def test_t3_a_changed_canonical_is_c2_and_judges_no_mirror(gate):
    gate = Proving(gate)
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        mutate(
            root,
            "CLAUDE.md",
            "and their unfinished prerequisites)<!-- /scope -->",
            "and their unfinished prerequisites, and one clause more)<!-- /scope -->",
            1,
        )
        result = run_gate(root)
        gate.assert_exit(1, result, "T3: an edited canonical span is red")
        found = findings(result)
        gate.assert_eq(
            bool([f for f in found if " C2 " in f and "pr.plan-set" in f]),
            True,
            "T3: C2 names pr.plan-set; got %r" % found,
        )
        gate.assert_contains(
            result.err, "--repin pr.plan-set", "T3: the C2 line names the repin command"
        )
        gate.assert_eq(
            [f for f in found if " C5 " in f or " C6 " in f],
            [],
            "T3: no C5/C6 while the pin is red",
        )


def test_t4_terms_drift_names_that_file_only(gate):
    gate = Proving(gate)
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        bullet = line_of(root, BABYSITTER, "- <!-- scope: pr.one-plan-per-pr -->")
        if "`Operational-Reason:`" not in bullet:
            gate.log_fail(
                "T4: the pr-babysitter plan-set bullet carries no `Operational-Reason:` to remove"
            )
        mutate(
            root, BABYSITTER, bullet, bullet.replace("`Operational-Reason:`", "a reason line"), 1
        )
        result = run_gate(root)
        gate.assert_exit(1, result, "T4: a terms mirror missing an atom is red")
        found = findings(result)
        gate.assert_eq(
            bool([f for f in found if " C6 " in f and BABYSITTER in f and "pr.plan-set" in f]),
            True,
            "T4: C6 names %s [pr.plan-set]; got %r" % (BABYSITTER, found),
        )
        gate.assert_eq([f for f in found if BABYSITTER not in f], [], "T4: no other file is named")


def test_t5_quote_drift_is_c7_and_a_marked_cut_is_silent(gate):
    gate = Proving(gate)
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        mutate(root, GUARD, "Ask for the big-bang, not for", "Ask for the big-change, not for", 1)
        result = run_gate(root)
        gate.assert_exit(1, result, "T5: a changed word inside a quote is red")
        gate.assert_eq(
            bool([f for f in findings(result) if " C7 " in f and GUARD in f]),
            True,
            "T5: C7 names the guard; got %r" % findings(result),
        )
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        mutate(
            root,
            GUARD,
            "Ask for the big-bang, not for permission to patch one thing...",
            "Ask for the big-bang, ...",
            1,
        )
        result = run_gate(root)
        gate.assert_exit(0, result, "T5: the same cut written as '...' is a true quote")


def test_t6_a_deleted_anchor_is_c4_not_silence(gate):
    gate = Proving(gate)
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        mutate(root, SKILL, "<!-- scope: pr.epic-carries-plan -->", "", 1)
        result = run_gate(root)
        gate.assert_exit(1, result, "T6: a mirror whose anchor is gone is red")
        gate.assert_eq(
            bool(
                [
                    f
                    for f in findings(result)
                    if " C4 " in f and SKILL in f and "pr.epic-carries-plan" in f
                ]
            ),
            True,
            "T6: C4 names %s; got %r" % (SKILL, findings(result)),
        )


def test_t7_a_new_oracle_value_is_c8(gate):
    gate = Proving(gate)
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        mutate(root, KINDS_SRC, '"deadline", "backup")', '"deadline", "backup", "late")', 1)
        result = run_gate(root)
        gate.assert_exit(1, result, "T7: a KINDS value the canonical lacks is red")
        gate.assert_eq(
            bool(
                [
                    f
                    for f in findings(result)
                    if " C8 " in f and "pr.turbo-batch-end" in f and "late" in f
                ]
            ),
            True,
            "T7: C8 names the missing value; got %r" % findings(result),
        )


def test_t8_unregistered_restatement_is_c9_and_an_anchor_makes_it_c10(gate):
    gate = Proving(gate)
    para = "\n\nUnder `turbo_push: batch-end` (the default) the batch is pushed once.\n"
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        path = root / HANDOFF
        path.write_text(path.read_text(encoding="utf-8") + para, encoding="utf-8")
        result = run_gate(root)
        gate.assert_exit(1, result, "T8: an unregistered restatement is red")
        found = findings(result)
        gate.assert_eq(
            bool([f for f in found if " C9 " in f and HANDOFF in f]),
            True,
            "T8: C9 names handoff.md; got %r" % found,
        )
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        path = root / HANDOFF
        path.write_text(
            path.read_text(encoding="utf-8") + para.replace("Under", TURBO_ANCHOR + "Under"),
            encoding="utf-8",
        )
        result = run_gate(root)
        gate.assert_exit(1, result, "T8: an unregistered anchor is red")
        found = findings(result)
        gate.assert_eq(
            bool([f for f in found if " C10 " in f and HANDOFF in f]),
            True,
            "T8: C10 names handoff.md; got %r" % found,
        )
        gate.assert_eq(
            [f for f in found if " C9 " in f and HANDOFF in f],
            [],
            "T8: an anchored restatement is C10, not C9",
        )


def test_t9_repin_refuses_while_a_mirror_drifts_and_admits_after(gate):
    gate = Proving(gate)
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        clean = (root / TRAILERS).read_text(encoding="utf-8")
        mutate(root, TRAILERS, TURBO_ANCHOR + turbo_sentence(root), TURBO_ANCHOR, 1)
        before = (root / REGISTRY_REL).read_bytes()
        result = run_gate(root, "--repin", "pr.turbo-batch-end")
        gate.assert_exit(1, result, "T9: --repin refuses while the trailers mirror drifts")
        gate.assert_contains(result.err, "no --force", "T9: the refusal says there is no override")
        gate.assert_eq(
            (root / REGISTRY_REL).read_bytes() == before, True, "T9: a refused repin writes nothing"
        )
        (root / TRAILERS).write_text(clean, encoding="utf-8")
        result = run_gate(root, "--repin", "pr.turbo-batch-end")
        gate.assert_exit(0, result, "T9: --repin is admitted once the mirror is restored")


def test_t10_baseline_refuses_growth_and_admits_a_drain(gate):
    gate = Proving(gate)
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        baseline = root / BASELINE_REL
        clean = (root / BABYSITTER).read_text(encoding="utf-8")
        bullet = line_of(root, BABYSITTER, "- <!-- scope: pr.one-plan-per-pr -->")
        mutate(
            root, BABYSITTER, bullet, bullet.replace("`Operational-Reason:`", "a reason line"), 1
        )
        before = baseline.read_bytes()
        result = run_gate(root, "--write-baseline")
        gate.assert_exit(1, result, "T10: --write-baseline refuses to grow the set")
        gate.assert_contains(
            result.err, "Do not add it to the baseline", "T10: the refusal says so"
        )
        gate.assert_eq(
            baseline.read_bytes() == before,
            True,
            "T10: a refused write leaves the baseline as it was",
        )
        # The one legal growth: a first seed while no baseline exists. Then the held finding is green, and fixing it is red until drained.
        baseline.unlink()
        gate.assert_exit(
            0,
            run_gate(root, "--write-baseline", "--first-seed"),
            "T10: --first-seed is admitted with no baseline",
        )
        held = json.loads(baseline.read_text(encoding="utf-8"))["findings"]
        gate.assert_eq(len(held), 1, "T10: the seed holds the one finding")
        gate.assert_exit(0, run_gate(root), "T10: a baselined finding is held, not red")
        (root / BABYSITTER).write_text(clean, encoding="utf-8")
        result = run_gate(root)
        gate.assert_exit(1, result, "T10: a fixed baselined finding is red until drained")
        gate.assert_contains(result.err, "baselined finding is fixed", "T10: the stale id is named")
        gate.assert_exit(0, run_gate(root, "--write-baseline"), "T10: the drain is admitted")
        gate.assert_eq(
            json.loads(baseline.read_text(encoding="utf-8"))["findings"],
            [],
            "T10: the drained set is empty",
        )
        gate.assert_exit(0, run_gate(root), "T10: green after the drain")
