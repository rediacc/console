"""check:ci-gh-retry-reads (PLAN-gh-retry G9): every non-test GitHub read through `gh` retries a transient fault.

WHAT IS PROVED HERE, AND AGAINST WHAT. The gate's own `--selftest` proves its helpers on fixture text. These tests drive the REAL entry point, by path, against (a) the real tree and (b) a scratch COPY of the real `.ci` Python trees and baseline under `tmp_path`, where a one-shot read can be planted into a real module's text without ever writing a tracked file (the hazard `check:ci-gate-test-real-file-plants` exists for). The gate is pointed at the copy with
`--root`.

Both directions every time: the plant must red, and the same tree without it must be green, so a gate that reds everything and a gate that reds nothing both fail here.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.quality import gh_retry_reads as g
from rediacc_ci.tests.gates import harness

if TYPE_CHECKING:
    import pathlib

SCRIPT = str(paths.from_root(".ci/scripts/quality/check_gh_retry_reads.py"))
SHAPE_RE = re.compile(
    r"(\d+) module\(s\), (\d+) gh call site\(s\): (\d+) read\(s\).*?(\d+) write\(s\).*?(\d+) new"
)

# A real module with a routed read, and the plant that demotes it. Chosen because it is one of the G0-G8 modules the gate exists to protect.
PLANT_REL = ".ci/rediacc_ci/release/assert_edge_tag_exists.py"
ONE_SHOT = """

def _planted_one_shot_read(tag):
    return subprocess.run(["gh", "api", "repos/o/r/git/ref/tags/%s" % tag], capture_output=True, check=False)
"""


def _run(*args: str, root: pathlib.Path | None = None) -> harness.RunResult:
    argv = [sys.executable, SCRIPT, "--quiet-writes", *args]
    if root is not None:
        argv += ["--root", str(root)]
    return harness.run(argv, timeout=180)


def _copy_tree(dst: pathlib.Path) -> pathlib.Path:
    """The real `.ci/rediacc_ci` and `.ci/scripts` Python files plus the baseline, at the same relative paths."""
    real = paths.repo_root()
    for rel in g.SCAN_ROOTS:
        for src in (real / rel).rglob("*.py"):
            if "__pycache__" in src.parts:
                continue
            out = dst / src.relative_to(real)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, out)
    base = dst / g.BASELINE_REL
    base.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(real / g.BASELINE_REL, base)
    return dst


def test_selftest_controls_pass(gate):
    result = _run("--selftest")
    gate.assert_exit(0, result, "the gate's own controls")
    gate.assert_contains(result.out, "selftest: every control passed")
    gate.assert_not_contains(result.out + result.err, "FAIL")
    gate.ok("--selftest exits 0 with every control passing")


def test_real_tree_is_green_and_not_vacuous(gate):
    result = _run()
    gate.assert_exit(0, result, "the real tree")
    m = SHAPE_RE.search(result.out)
    if m is None:
        gate.no("no shape line in the gate's output: %r" % result.out[-400:])
        return
    modules, sites, reads, writes, new = (int(x) for x in m.groups())
    gate.assert_eq(new, 0, "new findings on the real tree")
    if modules > 100 and sites > 50 and reads > 20 and writes > 5:
        gate.ok(
            "the walk saw %d modules, %d gh sites, %d reads, %d writes"
            % (modules, sites, reads, writes)
        )
    else:
        gate.no(
            "counts collapsed (%d modules, %d sites, %d reads, %d writes): the detector is not seeing the tree"
            % (modules, sites, reads, writes)
        )
    # The in-run plants into REAL module text must have fired, or the green above means nothing.
    gate.assert_eq(result.out.count("plant fired:"), 2, "both real-tree plants fired")
    gate.ok("the real tree is green with 0 new findings, and both in-run real-tree plants fired")


def test_planted_one_shot_read_reds_and_its_removal_greens(gate, tmp_path):
    root = _copy_tree(tmp_path / "tree")
    target = root / PLANT_REL
    clean = target.read_text(encoding="utf-8")

    green = _run(root=root)
    gate.assert_exit(0, green, "the unplanted copy")
    gate.ok("the unplanted copy of the real tree is green")

    target.write_text(clean + ONE_SHOT, encoding="utf-8")
    red = _run(root=root)
    gate.assert_exit(1, red, "a one-shot `gh api` read planted into a real module")
    gate.assert_contains(red.err, "%s:" % PLANT_REL)
    gate.assert_contains(red.err, "_planted_one_shot_read: a one-shot gh api GET (no retry)")
    gate.assert_contains(red.err, "Do not add it to the baseline")
    gate.ok("a one-shot read planted into %s reds, naming the function and the fix" % PLANT_REL)

    target.write_text(
        clean + ONE_SHOT.replace('subprocess.run(["gh", ', "gh_retry.gh(["), encoding="utf-8"
    )
    routed = _run(root=root)
    gate.assert_exit(0, routed, "the SAME read routed through gh_retry.gh")
    gate.ok("the same read through gh_retry.gh is green")

    write = ONE_SHOT.replace('"gh", "api", ', '"gh", "api", "-X", "DELETE", ')
    target.write_text(clean + write, encoding="utf-8")
    gate.assert_exit(0, _run(root=root), "the same call as a DELETE is a write, never a finding")
    gate.ok("the same call as a DELETE (a write) is green")


def test_baseline_is_shrink_only(gate, tmp_path):
    root = _copy_tree(tmp_path / "tree")
    base = root / g.BASELINE_REL
    data = json.loads(base.read_text(encoding="utf-8"))
    if data["entries"]:
        gate.ok("the copied baseline carries %d row(s)" % len(data["entries"]))
    else:
        gate.no("the copied baseline is empty, so the drain below would prove nothing")

    # A row the tree no longer fills is DRAINED: red until --write-baseline removes it.
    data["entries"].append({"id": "000000000000", "site": "a fixed read", "count": 1})
    base.write_text(json.dumps(data), encoding="utf-8")
    drained = _run(root=root)
    gate.assert_exit(1, drained, "an unfilled baseline row")
    gate.assert_contains(drained.err, "DRAINED baseline row")
    gate.ok("a baseline row the tree no longer fills reds as DRAINED")
    drain = _run("--write-baseline", root=root)
    gate.assert_exit(0, drain, "the drain")
    gate.assert_contains(drain.out, "ADDED 0")
    gate.assert_exit(0, _run(root=root), "the drained copy")
    gate.ok("--write-baseline drains it with ADDED 0, and the tree is green again")

    # A NEW read must never be absorbed by a drain, however the totals move.
    target = root / PLANT_REL
    target.write_text(target.read_text(encoding="utf-8") + ONE_SHOT, encoding="utf-8")
    refused = _run("--write-baseline", root=root)
    gate.assert_exit(1, refused, "--write-baseline over a new one-shot read")
    gate.assert_contains(refused.err, "ADDED ")
    gate.assert_contains(refused.err, "do not add them to the baseline")
    gate.ok("--write-baseline refuses to absorb a new one-shot read")


def test_missing_baseline_is_refused_not_read_as_empty(gate, tmp_path):
    root = _copy_tree(tmp_path / "tree")
    (root / g.BASELINE_REL).unlink()
    result = _run(root=root)
    gate.assert_exit(1, result, "no baseline file")
    gate.assert_contains(result.err, "cannot read the baseline")
    gate.ok("a missing baseline is refused, never read as empty")


def test_shapes_seen_on_the_real_tree(gate):
    """Detector shapes that each misfired once while the gate was written, pinned on fixture text."""
    rel = ".ci/rediacc_ci/x.py"
    # publish_ci_verdict: the verb comes from a tuple unpack, and `out.write(...)` must not bind to `GitHub.write`.
    src = """import subprocess
class GitHub:
    def write(self, method, path):
        return subprocess.run(["gh", "api", "-X", method, path], check=False)
def upsert(gh, out, found):
    if found:
        method, path = ("PATCH", "repos/o/r/check-runs/1")
    else:
        method, path = "POST", "repos/o/r/check-runs"
    out.write("would %s" % method)
    return gh.write(method, path)
"""
    sites = g.scan_source(rel, src)
    gate.assert_eq(
        [(s.qualname, s.kind) for s in sites],
        [("upsert", "write")],
        "a PATCH|POST chosen by tuple unpack",
    )
    gate.ok(
        "a PATCH|POST verb chosen by tuple unpack is one write, and out.write does not bind to GitHub.write"
    )
    # review_table: an injected runner threaded through a parameter with no default of its own.
    src = """import subprocess
def _gh(args):
    return subprocess.run(["gh", *args], check=False)
def commits(gh):
    return gh(["api", "repos/o/r/pulls/1/commits"])
def publish(gh=_gh):
    return commits(gh)
"""
    gate.assert_eq(
        [(s.qualname, s.kind, s.route) for s in g.scan_source(rel, src)],
        [("commits", "read", "one-shot")],
        "a threaded injected runner",
    )
    gate.ok("a runner injected as a default and threaded through a parameter is followed")
    # resolved_threads' selftest: a caller overriding a defaulted binary does not spawn gh.
    src = """import subprocess
def gh_json(argv, binary="gh"):
    return subprocess.run([binary, *argv], check=False)
def selftest():
    return gh_json(["irrelevant"], binary="gh-does-not-exist-zzz")
"""
    gate.assert_eq(g.scan_source(rel, src), [], "an overridden binary is not a gh call")
    gate.ok("a caller overriding a defaulted binary is not a gh call")
