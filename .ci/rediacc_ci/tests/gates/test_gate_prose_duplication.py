"""Gate test for `check:ci-prose-duplication` (`.ci/scripts/quality/check_prose_duplication.py`), box W1 of agent/plans/PLAN-pr-loop-single-source.md.

WHAT IT GUARDS. The gate's own selftest proves its controls fire on a toy fixture. This file proves the gate fires on the REAL loop docs: the real CLAUDE.md, launcher, agent file and /pr-merge, with the real scope registry, the entry point driven by path exactly as CI drives it.

EVERY PLANT GOES INTO A COPY under a temp root, passed with `--root`; no tracked file is written (`check:ci-gate-test-real-file-plants`). Each plant is built with `rediacc_ci.controls.plant` or reads its passage from the copy by anchor, so a moved anchor reads as a broken CONTROL rather than as a gate that stayed green.

BOTH DIRECTIONS (plan D6, live-tree red control). T1 is the untouched copy and must be green with a non-trivial shape. T2 appends the agent file's `pr.sibling-repos` paragraph, anchor removed, to the launcher copy and requires rc 1 naming both files: the paragraph is excluded where it is registered, and red the moment it is copied out unregistered. T5 is T2's silent twin: the same paragraph planted inside /pr-merge's registered `pr.sibling-repos` ref span (a declared mirror of the same clause) must stay green, because scope-mirrors judges that copy. Together they pin the rule: a registered span is exempt only from its own clause's registered copies, never from unregistered text. T3 and T4 are the refusals: an empty root and a missing family file are rc 2, never a pass.
"""

import os
import pathlib
import re
import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.controls import plant
from rediacc_ci.tests.gates import harness

GATE_REL = ".ci/scripts/quality/check_prose_duplication.py"
GATE = paths.from_root(*GATE_REL.split("/"))
REPO = paths.repo_root()

LAUNCHER = ".claude/commands/pr-babysit.md"
AGENT = ".claude/agents/pr-babysitter.md"
PR_MERGE = ".claude/commands/landing.md"
REGISTRY_REL = ".ci/config/scope-mirrors.json"

# What the gate reads, copied into every temp root.
COPY = ("CLAUDE.md", LAUNCHER, AGENT, PR_MERGE, REGISTRY_REL)

SIBLING_OPEN = "<!-- scope: pr.sibling-repos -->"
SHAPE_RE = re.compile(r"(\d+) files \(.*\), (\d+) pairs, (\d+) words")
FINDING_RE = re.compile(r"^\S+ (\S+):\d+ ~ (\S+):\d+ (\d+) words: ")

# The gate runs its selftest controls first, then the four files; a few seconds measured 2026-11-21.
GATE_TIMEOUT = 300


def build_root(gate, base: pathlib.Path) -> pathlib.Path:
    """A fresh copy of what the gate reads, proved present before any plant lands on it."""
    if not GATE.is_file():
        gate.log_fail("gate not found: %s" % GATE_REL)
    if not os.access(GATE, os.X_OK):
        gate.log_fail("gate not executable: %s" % GATE_REL)
    root = base / "tree"
    for rel in COPY:
        src = REPO / rel
        if not src.is_file():
            gate.log_fail("%s is missing from the repository; the copy would be vacuous" % rel)
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return root


def run_gate(root: pathlib.Path) -> harness.RunResult:
    return harness.run(
        [sys.executable, os.fspath(GATE), "--root", os.fspath(root)],
        cwd=REPO,
        timeout=GATE_TIMEOUT,
    )


def findings(result: harness.RunResult) -> list[tuple[str, str, int]]:
    out = []
    for line in result.err.splitlines():
        m = FINDING_RE.match(line)
        if m:
            out.append((m.group(1), m.group(2), int(m.group(3))))
    return out


def sibling_paragraph(gate, root: pathlib.Path) -> str:
    """The agent file's `pr.sibling-repos` span, anchors removed: the passage T2 copies out."""
    text = (root / AGENT).read_text(encoding="utf-8")
    start = text.find(SIBLING_OPEN)
    if start < 0:
        gate.log_fail(
            "%s carries no %s anchor; the T2 control has nothing to plant" % (AGENT, SIBLING_OPEN)
        )
        return ""
    body = text[start + len(SIBLING_OPEN) :]
    close = body.find("<!-- /scope -->")
    blank = body.find("\n\n")
    cut = min(x for x in (close, blank, len(body)) if x >= 0)
    passage = re.sub(r"<!--.*?-->", "", body[:cut], flags=re.DOTALL).strip()
    if len(passage.split()) < 30:
        gate.log_fail(
            "the pr.sibling-repos span holds %d words; a control under 30 proves nothing"
            % len(passage.split())
        )
    return passage


def test_t1_untouched_copy_is_green_with_a_shape(gate):
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        result = run_gate(root)
        gate.assert_exit(0, result, "T1: the untouched copy of the real loop docs is green")
        gate.assert_eq(result.err.strip(), "", "T1: a green run writes nothing to stderr")
        shape = SHAPE_RE.search(result.out)
        if shape is None:
            gate.log_fail("T1: the success line carries no shape: %r" % result.out[-400:])
            return
        files, pairs, words = (int(x) for x in shape.groups())
        gate.assert_eq((files, pairs), (4, 6), "T1: four family files, six pairs")
        gate.assert_eq(words > 5000, True, "T1: %d words compared, not a collapsed scan" % words)
        gate.log_pass("T1: untouched copy green over %d words" % words)


def test_t2_a_copied_sibling_repos_paragraph_is_red_naming_both(gate):
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        passage = sibling_paragraph(gate, root)
        launcher = root / LAUNCHER
        text = launcher.read_text(encoding="utf-8")
        launcher.write_text(plant(text, text, text + "\n" + passage + "\n", 1), encoding="utf-8")
        result = run_gate(root)
        gate.assert_exit(
            1, result, "T2: the agent's sibling-repos paragraph copied into the launcher is red"
        )
        found = findings(result)
        hits = [f for f in found if {f[0], f[1]} == {LAUNCHER, AGENT} and f[2] >= 25]
        gate.assert_eq(
            bool(hits), True, "T2: a finding names %s and %s; got %r" % (LAUNCHER, AGENT, found)
        )
        gate.log_pass("T2: planted duplicate red, %d finding(s)" % len(found))


def test_t3_an_empty_root_is_a_refusal(gate):
    with harness.temp_dir() as tmp:
        empty = tmp / "empty"
        empty.mkdir()
        result = run_gate(empty)
        gate.assert_exit(2, result, "T3: an empty --root is rc 2, never a pass")
        gate.assert_contains(result.err, "is missing", "T3: says what it could not see")
        gate.log_pass("T3: empty tree refused (anti-vacuity), it does not pass silently")


def test_t4_a_missing_family_file_is_a_refusal(gate):
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        (root / PR_MERGE).unlink()
        result = run_gate(root)
        gate.assert_exit(2, result, "T4: a missing family file is rc 2")
        gate.assert_contains(result.err, PR_MERGE, "T4: the refusal names the missing file")
        gate.log_pass("T4: missing family file refused")


def test_t5_the_same_paragraph_inside_the_registered_pr_merge_span_stays_green(gate):
    with harness.temp_dir() as tmp:
        root = build_root(gate, tmp)
        passage = sibling_paragraph(gate, root)
        merge = root / PR_MERGE
        text = merge.read_text(encoding="utf-8")
        if text.count(SIBLING_OPEN) != 1:
            gate.log_fail(
                "%s carries %d %s anchors; the registered pointer copy T5 plants into is gone"
                % (PR_MERGE, text.count(SIBLING_OPEN), SIBLING_OPEN)
            )
        merge.write_text(
            plant(text, SIBLING_OPEN, SIBLING_OPEN + passage + " ", 1), encoding="utf-8"
        )
        result = run_gate(root)
        gate.assert_exit(
            0,
            result,
            "T5: the paragraph inside the registered pr.sibling-repos mirror span of %s is green"
            % PR_MERGE,
        )
        gate.assert_eq(findings(result), [], "T5: no finding names the registered copy")
        gate.log_pass("T5: a registered mirror copy of the same clause stays exempt")
