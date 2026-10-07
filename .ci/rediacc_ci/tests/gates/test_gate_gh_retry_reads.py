"""check:ci-gh-retry-reads (PLAN-gh-retry G9): every non-test GitHub read through `gh` retries a transient fault.

WHAT IS PROVED HERE, AND AGAINST WHAT. The gate's own `--selftest` proves its helpers on fixture text. These tests drive the REAL entry point, by path, against (a) the real tree and (b) a scratch COPY of the real `.ci` and `.claude` Python trees (every SCAN_ROOT, G13 widened it to `.claude/hooks` and `.claude/rediacc_hooks`) and the baseline under `tmp_path`, where a one-shot read can be planted into a real module's text without ever writing a tracked file (the hazard `check:ci-gate-test-real-file-plants` exists for). The gate is pointed at the copy with
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
ROOTS_RE = re.compile(r"(\S+) (\d+) module\(s\) (\d+) site\(s\) (\d+) new")
SHAPE_RE = re.compile(
    r"(\d+) module\(s\), (\d+) gh call site\(s\): (\d+) read\(s\).*?(\d+) write\(s\).*?(\d+) new"
)

# A real module with a routed read, and the plant that demotes it. Chosen because it is one of the G0-G8 modules the gate exists to protect.
PLANT_REL = ".ci/rediacc_ci/release/assert_edge_tag_exists.py"
# A real `.claude` hook whose reads G13 routed through retry_transient: the post-bash body refresh, where a single 5xx used to skip the refresh silently.
CLAUDE_REL = ".claude/hooks/post-bash/refresh_pr_body.py"
CLAUDE_HOOK = "retry.retry_transient(\n        once,"
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
    # Every negative below RAISES. `gate.no` only records a failure, and the fixture's teardown refuses a test with zero passes but not one with a recorded failure, so a `gate.no` without `tally_finish` is a green test (measured 2026-10-07: this file's baseline test passed against an EMPTY baseline that way).
    result = _run()
    gate.assert_exit(0, result, "the real tree")
    m = SHAPE_RE.search(result.out)
    assert m is not None, "no shape line in the gate's output: %r" % result.out[-400:]
    modules, sites, reads, writes, new = (int(x) for x in m.groups())
    gate.assert_eq(new, 0, "new findings on the real tree")
    collapsed = (
        "counts collapsed (%d modules, %d sites, %d reads, %d writes): the detector is not seeing the tree"
        % (modules, sites, reads, writes)
    )
    assert modules > 100, collapsed
    assert sites > 50, collapsed
    assert reads > 20, collapsed
    assert writes > 5, collapsed
    gate.ok(
        "the walk saw %d modules, %d gh sites, %d reads, %d writes"
        % (modules, sites, reads, writes)
    )
    roots = {r: (int(mods), int(n)) for r, mods, n, _new in ROOTS_RE.findall(result.out)}
    gate.assert_eq(sorted(roots), sorted(g.SCAN_ROOTS), "the per-root line names every scan root")
    empty = [r for r, (mods, _n) in roots.items() if mods == 0]
    assert not empty, "scan root(s) with zero modules: %s" % empty
    blind = [r for r in g.CLAUDE_ROOTS if roots[r][1] == 0]
    assert not blind, "a .claude root with zero gh sites: %s" % blind
    gate.ok(
        "every scan root contributes modules, and both .claude roots contribute gh sites: %s"
        % roots
    )
    # The in-run plants into REAL module text must have fired, or the green above means nothing.
    gate.assert_eq(result.out.count("plant fired:"), 3, "all three real-tree plants fired")
    gate.assert_contains(
        result.out, "plant fired: a one-shot gh read appended to a .claude module in .claude/"
    )
    gate.ok(
        "the real tree is green with 0 new findings, and all three in-run real-tree plants fired, one into a real .claude module"
    )


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


def test_a_claude_one_shot_read_reds_and_routing_it_greens(gate, tmp_path):
    """G13: the widened root is SEEN, in a real hook, through the real entry point."""
    root = _copy_tree(tmp_path / "tree")
    target = root / CLAUDE_REL
    clean = target.read_text(encoding="utf-8")

    target.write_text(clean + ONE_SHOT, encoding="utf-8")
    red = _run(root=root)
    gate.assert_exit(1, red, "a one-shot `gh api` read planted into a real .claude hook")
    gate.assert_contains(red.err, "%s:" % CLAUDE_REL)
    gate.assert_contains(red.err, "_planted_one_shot_read: a one-shot gh api GET (no retry)")
    gate.ok("a one-shot read planted into %s reds, naming the hook and the function" % CLAUDE_REL)

    routed = ONE_SHOT.replace(
        'return subprocess.run(["gh", ',
        'return retry.retry_transient(lambda: subprocess.run(["gh", ',
    ).replace("check=False)", "check=False), lambda r: None)")
    target.write_text(clean + routed, encoding="utf-8")
    gate.assert_exit(0, _run(root=root), "the same read inside a retry_transient lambda")
    gate.ok("the same read inside retry_transient(lambda: ...) in the hook is green")


def test_unhooking_a_claude_hooks_retry_reds_exactly_its_reads(gate, tmp_path):
    """The .claude green is EARNED by the routing: take refresh_pr_body's retry_transient away and its three reads come back as findings, its PATCH (a write) does not."""
    root = _copy_tree(tmp_path / "tree")
    target = root / CLAUDE_REL
    clean = target.read_text(encoding="utf-8")
    assert clean.count(CLAUDE_HOOK) == 1, "%s no longer has the routed shape %r" % (
        CLAUDE_REL,
        CLAUDE_HOOK,
    )
    target.write_text(clean.replace(CLAUDE_HOOK, "run_once(\n        once,"), encoding="utf-8")
    red = _run(root=root)
    gate.assert_exit(1, red, "refresh_pr_body with its retry unhooked")
    found = [line for line in red.err.splitlines() if line.startswith(CLAUDE_REL + ":")]
    verbs = sorted(line.split(": a one-shot gh ", 1)[1].split(" (", 1)[0] for line in found)
    gate.assert_eq(verbs, ["pr list", "pr view", "repo view"], "the unhooked hook's findings")
    gate.ok("unhooking refresh_pr_body's retry reds exactly its three reads, not its PATCH")


def test_a_scan_root_missing_from_the_tree_is_vacuous(gate, tmp_path):
    root = _copy_tree(tmp_path / "tree")
    for p in sorted((root / ".claude/hooks").rglob("*.py")):
        p.unlink()
    red = _run(root=root)
    gate.assert_exit(1, red, "a copy with no .claude/hooks modules")
    gate.assert_contains(red.err, "VACUOUS: scan root .claude/hooks contributed zero modules")
    gate.ok("a scan root with zero modules reds as VACUOUS by name, whatever the other roots total")


def test_baseline_is_shrink_only(gate, tmp_path):
    """Self-seeded: the real baseline was drained to zero rows on 2026-10-07, so the copy SEEDS its own debt from a planted read rather than relying on the real one carrying any."""
    root = _copy_tree(tmp_path / "tree")
    base = root / g.BASELINE_REL
    target = root / PLANT_REL
    clean = target.read_text(encoding="utf-8")
    debt = ONE_SHOT.replace("_planted_one_shot_read", "_seeded_debt_read")
    target.write_text(clean + debt, encoding="utf-8")
    base.unlink()
    seeded = _run("--init-baseline", root=root)
    gate.assert_exit(0, seeded, "seeding the copy's baseline over one planted read")
    data = json.loads(base.read_text(encoding="utf-8"))
    gate.assert_eq(len(data["entries"]), 1, "rows in the seeded baseline")
    gate.assert_exit(0, _run(root=root), "the seeded copy, its one read frozen as debt")
    gate.ok("a copy seeded with one frozen read is green, the read counted as debt")

    # Fixing the frozen read DRAINS its row: red until --write-baseline removes it.
    target.write_text(clean, encoding="utf-8")

    drained = _run(root=root)
    gate.assert_exit(1, drained, "an unfilled baseline row")
    gate.assert_contains(drained.err, "DRAINED baseline row")
    gate.ok("a baseline row the tree no longer fills reds as DRAINED")
    drain = _run("--write-baseline", root=root)
    gate.assert_exit(0, drain, "the drain")
    gate.assert_contains(drain.out, "ADDED 0")
    gate.assert_eq(
        json.loads(base.read_text(encoding="utf-8"))["entries"], [], "rows after the drain"
    )
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


def test_gh_api_is_classified_by_the_hooks_own_gh_parser(gate):
    """The `gh api` read/write split reads the argv through `shellscan.gh_args`, the pflag reader the `.claude` guards share (#9de9a8e9), not a fourth hand-written flag table. Each spelling below is one gh accepts; the long form beside it is the control."""
    cases: list[tuple[list[g.Token], str]] = [
        # (argv after "gh", kind)
        (["api", "x", "-f", "a=b"], "write"),
        (["api", "x", "-fa=b"], "write"),
        (["api", "x", "--raw-field=a=b"], "write"),
        (["api", "x", "-F", "a=b"], "write"),
        (["api", "x", "-Fa=b"], "write"),
        (["api", "x", "--input=f"], "write"),
        (["api", "-X", "POST", "x"], "write"),
        (["api", "-iXPOST", "x"], "write"),
        (["api", "-iX", "POST", "x"], "write"),
        (["api", "-X=POST", "x"], "write"),
        (["api", "-X", "GET", "x", "-f", "a=b"], "read"),
        (["api", "-X=GET", "x", "-fa=b"], "read"),
        (["api", "--method=get", "x", "-f", "a=b"], "read"),
        # A value-taking flag's value is never the endpoint: the header names no `graphql`, the query is a read.
        (["api", "-H", "Accept: x", "graphql", "-f", "query=query{a}"], "read"),
        (["api", "-X", "POST", "graphql", "-f", "query=mutation{a}"], "write"),
        # A `-f` that is the VALUE of `-q` is no body field.
        (["api", "-q", "-f", "x"], "read"),
        (["api", "-X", g.DYN, "x"], "unresolved"),
        (["api", "-X", g.Choice(frozenset({"PATCH", "POST"})), "x"], "write"),
        (["api", "-X", g.Choice(frozenset({"GET", "HEAD"})), "x", "-f", "a=b"], "read"),
    ]
    for tail, kind in cases:
        gate.assert_eq(g.classify(["gh", *tail])[0], kind, "gh %r" % (tail,))
    gate.ok("%d gh api spellings classified as gh reads them" % len(cases))


def test_every_gh_api_body_and_method_flag_of_the_shared_table_is_honoured(gate):
    """Parity with the table itself: every spelling of every `gh api` flag that implies a POST, and of `--method`, changes the verdict, so a flag added to `shellscan.GH_FLAGS` reaches this gate with no second edit."""
    shellscan = g._shellscan()
    table = shellscan.GH_FLAGS[("api",)]
    implied = ("field", "raw-field", "input")
    seen = 0
    for name in (*implied, "method"):
        short, _takes = table[name]
        value = "POST" if name == "method" else "a=b"
        spellings = [["--" + name, value], ["--%s=%s" % (name, value)]]
        if short:
            spellings += [["-" + short, value], ["-%s%s" % (short, value)], ["-i" + short, value]]
        for spelling in spellings:
            gate.assert_eq(g.classify(["gh", "api", "x", *spelling])[0], "write", repr(spelling))
            seen += 1
    gate.assert_eq(seen > 0, True, "the shared table offered no spelling at all")
    gate.ok("%d spellings of %d flags from shellscan.GH_FLAGS each make a write" % (seen, 4))
