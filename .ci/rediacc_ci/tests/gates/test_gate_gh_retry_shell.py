"""check:ci-gh-retry-reads, shell half: every GitHub read made from shell (a `curl` to the GitHub API, or `gh` in a live script or a workflow `run:` block) retries a transient fault.

WHAT IS PROVED HERE, AND AGAINST WHAT. The gate's `--selftest` proves the lexer, the classifiers and the liveness walk on fixture text. These tests drive the REAL entry points by path: the driver `.ci/scripts/quality/check_gh_retry_reads.py` (both halves) against the real tree, and against a scratch COPY of exactly the files the shell half reads, written under `tmp_path` from the real tree's corpus, where a defect can be planted without touching a tracked file. The driver reaches the copy through `--shell-root`; the faster per-case runs call the shell module's own entry, `python3 -m rediacc_ci.quality.gh_retry_shell --root <copy>`.

Both directions every time: each plant must red, and the copy without it must be green, so a gate that reds everything and a gate that reds nothing both fail here.
"""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.quality import gh_retry_shell as sh
from rediacc_ci.tests.gates import harness

if TYPE_CHECKING:
    import pathlib

DRIVER = str(paths.from_root(".ci/scripts/quality/check_gh_retry_reads.py"))
SHAPE_RE = re.compile(
    r"shell: (\d+) script\(s\) \[(\d+) live, (\d+) dead\], (\d+) workflow file\(s\) with (\d+) run: block\(s\); "
    r"(\d+) GitHub call\(s\): (\d+) curl, (\d+) gh; .*?(\d+) debt, (\d+) new"
)
REAPER = sh.REAPER_REL
REAPER_CURL = 'resp="$(curl -sS -w'
DISPATCH = ".ci/scripts/ci/dispatch-release.sh"
DISPATCH_READ = 'rows=$(gh api "repos/${GITHUB_REPOSITORY}/commits/${GITHUB_SHA}/pulls"'
TWIN = ".ci/scripts/release/resolve-ci-run.sh"


def _shell(root: pathlib.Path) -> harness.RunResult:
    argv = [
        sys.executable,
        "-m",
        "rediacc_ci.quality.gh_retry_shell",
        "--quiet-writes",
        "--root",
        str(root),
    ]
    return harness.run(argv, cwd=str(paths.from_root(".ci")), timeout=180)


def _copy(dst: pathlib.Path) -> pathlib.Path:
    """Every file the shell half reads, at its relative path, from the real tree's corpus (so the copy cannot drift from what the gate enumerates)."""
    real = paths.repo_root()
    corpus = sh.load_corpus(real)
    texts = {
        **corpus.scripts,
        **corpus.workflows,
        **{k: t for k, (_kind, t) in corpus.executors.items()},
    }
    texts[sh.WELL_KNOWN_REL] = (real / sh.WELL_KNOWN_REL).read_text(encoding="utf-8")
    for rel, text in texts.items():
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return dst


def _line_of(path: pathlib.Path, needle: str) -> int:
    lines = path.read_text(encoding="utf-8").split("\n")
    hits = [i + 1 for i, ln in enumerate(lines) if needle in ln]
    assert len(hits) == 1, "%s: %r found %d times, wanted once" % (path, needle, len(hits))
    return hits[0]


def test_selftest_controls_pass(gate):
    result = harness.run([sys.executable, DRIVER, "--selftest"], timeout=180)
    gate.assert_exit(0, result, "both halves' controls")
    gate.assert_contains(result.out, "shell selftest: every control passed")
    gate.assert_not_contains(result.out + result.err, "FAIL")
    gate.ok("--selftest runs the shell controls beside the Python ones, every one passing")


def test_real_tree_is_green_and_not_vacuous(gate):
    result = harness.run([sys.executable, DRIVER, "--quiet-writes"], timeout=240)
    gate.assert_exit(0, result, "the real tree, both halves")
    gate.assert_contains(result.out, "gh retry reads: python half rc=0, shell half rc=0")
    m = SHAPE_RE.search(result.out)
    assert m is not None, "no shell shape line in the gate's output: %r" % result.out[-600:]
    scripts, live, dead, workflows, blocks, _calls, curl, gh, debt, new = (
        int(x) for x in m.groups()
    )
    gate.assert_eq(new, 0, "new shell findings on the real tree")
    collapsed = "shell counts collapsed (%s): the gate is not seeing the tree" % m.group(0)
    assert scripts > 100, collapsed
    assert live > 40, collapsed
    assert dead > 20, collapsed
    assert workflows > 20, collapsed
    assert blocks > 300, collapsed
    assert curl >= 1, collapsed
    assert gh >= 3, collapsed
    gate.assert_eq(debt, len(sh.SHELL_DEBT), "every SHELL_DEBT row is filled by the tree")
    gate.ok(
        "%d scripts (%d live, %d dead), %d run: blocks, %d curl and %d gh calls, %d debt, 0 new"
        % (scripts, live, dead, blocks, curl, gh, debt)
    )
    gate.assert_eq(
        result.out.count("shell plant red:"), 3, "all three shell real-tree plants fired"
    )
    gate.assert_contains(
        result.out, "shell plant red: the reaper's --retry removed -> %s:" % REAPER
    )
    gate.assert_eq(
        len(
            [
                ln
                for ln in result.out.splitlines()
                if ln.startswith("  DEBT   ") and "SHELL_DEBT (" in ln
            ]
        ),
        len(sh.SHELL_DEBT),
        "one visible DEBT line per frozen read",
    )
    assert "  TWIN   " in result.out, "no TWIN line: the dead-twin exclusion is no longer printed"
    gate.ok(
        "all three in-run shell plants fired, every frozen read and every unjudged twin is printed"
    )


def test_reaper_without_retry_reds_through_the_driver(gate, tmp_path):
    root = _copy(tmp_path / "tree")
    reaper = root / REAPER
    clean = reaper.read_text(encoding="utf-8")
    green = harness.run(
        [sys.executable, DRIVER, "--quiet-writes", "--shell-root", str(root)], timeout=240
    )
    gate.assert_exit(0, green, "the unplanted copy through the driver")
    gate.ok("the unplanted copy is green through the driver")

    hit = sh.REAPER_RETRY.search(clean)
    assert hit is not None, "%s no longer carries a --retry" % REAPER
    reaper.write_text(clean.replace(hit.group(0), "", 1), encoding="utf-8")
    line = _line_of(reaper, REAPER_CURL)
    red = harness.run(
        [sys.executable, DRIVER, "--quiet-writes", "--shell-root", str(root)], timeout=240
    )
    gate.assert_exit(1, red, "the reaper's GitHub curl without --retry")
    gate.assert_contains(
        red.err,
        "%s:%d: gh_run_status: a one-shot curl GET to the GitHub API (no --retry)" % (REAPER, line),
    )
    gate.assert_contains(red.err, "Do not add it to SHELL_DEBT")
    gate.assert_contains(red.err, "python half rc=0, shell half rc=1")
    findings = [ln for ln in red.err.splitlines() if re.match(r"^\S+:\d+: ", ln)]
    gate.assert_eq(len(findings), 1, "findings for the one planted defect")
    gate.ok(
        "the reaper without --retry reds through the driver with exactly one finding, %s:%d, and the fix"
        % (REAPER, line)
    )


def test_a_one_shot_read_in_a_workflow_run_block_reds(gate, tmp_path):
    root = _copy(tmp_path / "tree")
    wf = root / ".github/workflows/promote-stable.yml"
    clean = wf.read_text(encoding="utf-8")
    needle = '          echo "No rollback labels found"\n'
    assert clean.count(needle) == 1, (
        "promote-stable.yml no longer has the rollback step's last line"
    )
    wf.write_text(
        clean.replace(
            needle, needle + '          gh api "repos/$GITHUB_REPOSITORY/pulls" --jq length\n'
        ),
        encoding="utf-8",
    )
    line = _line_of(wf, 'gh api "repos/$GITHUB_REPOSITORY/pulls"')
    red = _shell(root)
    gate.assert_exit(1, red, "a one-shot gh api read planted into a workflow run: block")
    gate.assert_contains(
        red.err,
        ".github/workflows/promote-stable.yml:%d: promote/Check for rollback labels: a one-shot gh api GET (no retry)"
        % line,
    )
    gate.ok("a one-shot read in a run: block reds on its YAML line, named by job and step")

    routed = clean.replace(
        needle,
        needle + '          curl -fsS --retry 3 "$GITHUB_API_URL/repos/$GITHUB_REPOSITORY/pulls"\n',
    )
    wf.write_text(routed, encoding="utf-8")
    gate.assert_exit(0, _shell(root), "the same read as a curl with --retry 3")
    gate.ok("the same read as `curl --retry 3` against $GITHUB_API_URL is green")


def test_wiring_a_dead_twin_makes_its_reads_findings(gate, tmp_path):
    root = _copy(tmp_path / "tree")
    green = _shell(root)
    gate.assert_exit(0, green, "the unplanted copy")
    gate.assert_contains(green.out, "  TWIN   %s:" % TWIN)
    gate.ok("%s is reported as an unjudged dead twin on the clean copy" % TWIN)

    wf = root / ".github/workflows/promote-stable.yml"
    clean = wf.read_text(encoding="utf-8")
    needle = '          echo "No rollback labels found"\n'
    wf.write_text(
        clean.replace(needle, needle + "          %s --sha abc\n" % TWIN), encoding="utf-8"
    )
    red = _shell(root)
    gate.assert_exit(1, red, "the dead twin named by a workflow run: block")
    found = [ln for ln in red.err.splitlines() if ln.startswith(TWIN + ":")]
    assert len(found) >= 1, "wiring %s left its reads unjudged: %r" % (TWIN, red.err[-600:])
    gate.assert_not_contains(red.out, "  TWIN   %s:" % TWIN)
    gate.ok(
        "naming the twin in a run: block makes it live, and its %d read(s) become findings"
        % len(found)
    )


def test_a_routed_debt_read_drains_its_row(gate, tmp_path):
    root = _copy(tmp_path / "tree")
    script = root / DISPATCH
    clean = script.read_text(encoding="utf-8")
    assert clean.count(DISPATCH_READ) == 1, "%s no longer has the frozen read" % DISPATCH
    script.write_text(
        clean.replace(
            DISPATCH_READ,
            'rows=$(gh_retry "PR lookup" -- api "repos/${GITHUB_REPOSITORY}/commits/${GITHUB_SHA}/pulls"',
        ),
        encoding="utf-8",
    )
    red = _shell(root)
    gate.assert_exit(1, red, "a SHELL_DEBT read routed through gh_retry")
    gate.assert_contains(red.err, "DRAINED SHELL_DEBT row")
    gate.assert_contains(red.err, "dispatch-release.sh :: decide")
    gate.ok(
        "routing a frozen read through common.sh gh_retry reds as DRAINED until its row is deleted"
    )


def test_a_shell_tree_with_no_scripts_is_vacuous(gate, tmp_path):
    root = _copy(tmp_path / "tree")
    for rel in sh.load_corpus(root).scripts:
        (root / rel).unlink()
    red = _shell(root)
    gate.assert_exit(1, red, "a copy with every shell script removed")
    gate.assert_contains(red.err, "VACUOUS: zero shell scripts")
    gate.assert_contains(red.err, "shell: 0 script(s) [0 live, 0 dead]")
    gate.ok("a copy with no shell scripts reds as VACUOUS, never green, and prints the zero")

    # The reaper is the tree's one GitHub curl: without it the curl detector has nothing to see, and that must red too, not pass quietly on the gh sites alone.
    root2 = _copy(tmp_path / "tree2")
    (root2 / REAPER).unlink()
    red2 = _shell(root2)
    gate.assert_exit(1, red2, "a copy with no GitHub curl")
    gate.assert_contains(red2.err, "VACUOUS: zero curl calls to the GitHub API")
    gate.ok("a copy with no GitHub curl reds as VACUOUS for the curl detector")
