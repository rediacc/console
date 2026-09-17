"""`rediacc_ci.quality.scope_scripts_reachability` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-scope-scripts-reachability.sh` over a git fixture with stdout and stderr captured SEPARATELY, and its bytes are compared against the port's. Same recipe as the committed ledger, `.ci/shadow/w7p2-scope-scripts-reachability.observations.jsonl`.

THE FIXTURE CARRIES THE REAL `scope-map.cjs`, and it has to. The gate's verdict is whatever `classify()` says, and that file's rule ORDER is semantics (first match wins, driver contract section 3). A stubbed classifier would make these cases assert that the port agrees with the stub.

TWO CASES HERE ARE NOT IN THE LEDGER, and both are the interesting ones.

  * THE DISPATCH-FLOOR REFUSAL EXITS 127, not 1, because the twin calls
    `log_fail` and never sources the library that defines it. Both sides print a
    single shell diagnostic and no finding, so `scripts/lib/shadow-gate.ts` scores
    the pair VACUOUS_BOTH_EMPTY and refuses to record it. Byte equality can rule
    on it, so it lives here.
  * THE `\\x27` BLIND SPOT is a property of the twin's extractor rather than of any
    one tree: an invocation whose only lead character is a single quote is
    invisible, because GNU grep reads `\\x27` as the literal `x27`. Asserted here
    against the port's own extractor, so a future "cleanup" that turns `x27` back
    into `'` is caught as the behaviour change it is.
"""

import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci.quality import scope_scripts_reachability as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-scope-scripts-reachability.sh"
MODULE = "scope_scripts_reachability"

RUNSH = """#!/bin/bash
case "$1" in
        drill)
            bash scripts/drills/lib.sh
            ;;
esac
"""


def build(tmp_path: pathlib.Path, extra: dict[str, str], *, runsh: bool = True) -> pathlib.Path:
    """A sealed git specimen with both implementations, scope-map.cjs and a run.sh.

    THE BASELINE IS DELIBERATELY ABOVE BOTH FLOORS: twelve `.ci/scripts/deploy` references from a workflow and twelve `.ci/scripts/build` ones from a build script clear the 20-reference `.ci` floor, and the run.sh drill arm clears the dispatch floor of 1. A case that wants a floor to fire removes the baseline rather than lowering the floor, because a floor a test can lower is not a
    floor.
    """
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    for rel in (
        ".ci/scripts/quality",
        ".ci/scripts/ci",
        ".ci/scripts/build",
        ".ci/scripts/deploy",
        ".ci/rediacc_ci/quality",
        ".github/workflows",
        "scripts/drills",
        "scripts/gates",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
    shutil.copytree(src / ".ci" / "scripts" / "lib", root / ".ci" / "scripts" / "lib")
    shutil.copy2(src / TWIN, root / TWIN)
    shutil.copy2(
        src / ".ci" / "scripts" / "ci" / "scope-map.cjs",
        root / ".ci" / "scripts" / "ci" / "scope-map.cjs",
    )
    for name in ("__init__.py", "log.py", "paths.py", "controls.py"):
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    for name in ("__init__.py", "%s.py" % MODULE):
        shutil.copy2(
            src / ".ci" / "rediacc_ci" / "quality" / name,
            root / ".ci" / "rediacc_ci" / "quality" / name,
        )
    # The two paths the classifier controls are asserted against.
    (root / "scripts/gates" / "check-embed-credits.ts").write_text(
        "// gate source\n", encoding="utf-8"
    )
    (root / "scripts" / "drills" / "lib.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    workflow = "".join("bash .ci/scripts/deploy/step-%02d.sh\n" % i for i in range(1, 13))
    workflow += "./run.sh drill transfer\n"
    (root / ".github" / "workflows" / "ci.yml").write_text(workflow, encoding="utf-8")
    (root / ".ci" / "scripts" / "build" / "driver.sh").write_text(
        "".join("bash .ci/scripts/build/b-%02d.sh\n" % i for i in range(1, 13)), encoding="utf-8"
    )
    if runsh:
        (root / "run.sh").write_text(RUNSH, encoding="utf-8")
    for rel, text in extra.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and rel.endswith(".yml"):
            target.write_text(target.read_text(encoding="utf-8") + text, encoding="utf-8")
        else:
            target.write_text(text, encoding="utf-8")
    for args in (
        ["init", "-q", "-b", "main", "."],
        ["config", "user.email", "gate@example.invalid"],
        ["config", "user.name", "test"],
        ["add", "-A"],
        ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "specimen"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    old = diff.bash_streams("bash %s" % TWIN, cwd=str(root))
    new = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s" % MODULE,
        cwd=str(root),
    )
    return old, new


CASES = [
    (
        # THE NEGATIVE HALF. The baseline alone references only paths that classify `full`, so the gate must be silent. Without it, a port that called everything a violation would pass every red case below.
        "a tree whose reachable paths all force full is silent",
        {},
        True,
        0,
    ),
    (
        "a narrowable path referenced from a workflow is a violation",
        {".github/workflows/ci.yml": "npx tsx scripts/gates/check-embed-credits.ts\n"},
        True,
        1,
    ),
    (
        "a narrowable path referenced from a deploy script is a violation",
        {".ci/scripts/deploy/publish.sh": "npx tsx scripts/gates/check-embed-credits.ts\n"},
        True,
        1,
    ),
    (
        "a narrowable path reached only through the run.sh dispatch is a violation",
        {
            "run.sh": RUNSH.replace(
                "bash scripts/drills/lib.sh",
                "bash scripts/drills/lib.sh\n            npx tsx scripts/gates/check-embed-credits.ts",
            )
        },
        True,
        1,
    ),
    (
        # DOCUMENTATION IS NOT A DEPENDENCY. This is the 2026-08-06 false positive that would have forced full CI on every scripts/dev edit forever.
        "a log_error mention of a narrowable path is not a violation",
        {
            ".ci/scripts/deploy/publish.sh": (
                'log_error "run scripts/gates/check-embed-credits.ts to fix this"\n'
            )
        },
        True,
        0,
    ),
    (
        "a collapsed .ci scan refuses rather than reporting clean",
        {".github/workflows/ci.yml": "", ".ci/scripts/build/driver.sh": ""},
        True,
        1,
    ),
]


@pytest.mark.parametrize(
    ("extra", "runsh", "want_exit"),
    [(c[1], c[2], c[3]) for c in CASES],
    ids=[c[0] for c in CASES],
)
def test_differential(tmp_path, extra, runsh, want_exit):
    """Byte equality on BOTH streams, plus the exit code the case expects."""
    root = build(tmp_path, extra, runsh=runsh)
    (old_rc, old_out, old_err), (new_rc, new_out, new_err) = run_both(root)
    assert old_rc == want_exit, "the twin's verdict moved: %s%s" % (old_out, old_err)
    assert new_rc == old_rc
    assert new_out == old_out
    assert new_err == old_err


def test_the_dispatch_floor_refusal_exits_127_on_both_sides(tmp_path):
    """The `log_fail` defect, pinned so a one-sided repair is a disagreement.

    The twin never sources `.ci/scripts/lib/common.sh`, and `log_fail` is defined only in `.ci/scripts/test/lib/test-helpers.sh` and four test scripts. Under `set -euo pipefail` the unknown command exits 127 at that line, so the three explanatory `echo`s and the `exit 1` beneath it never run. The identical defect is already on the record for check-pool-writer-safety.sh at
    `.ci/scripts/test/run-all.sh:215-219`.

    NOT IN THE LEDGER: both sides print one shell diagnostic and no finding, so the comparator scores it VACUOUS_BOTH_EMPTY and refuses to record it. Byte equality can rule on it, which is why the case lives here.
    """
    root = build(tmp_path, {}, runsh=False)
    (old_rc, old_out, old_err), (new_rc, new_out, new_err) = run_both(root)
    assert old_rc == 127, "the twin no longer hits the log_fail defect: %s" % old_err
    assert new_rc == old_rc
    assert new_out == old_out
    assert new_err == old_err
    assert "log_fail: command not found" in old_err
    assert "Refusing to report on the .ci/scripts half alone" not in (old_out + old_err), (
        "the explanatory text became reachable; the twin was repaired and the port must follow"
    )


def test_the_single_quote_lead_is_dead_under_gnu_grep():
    """`\\x27` is the literal `x27`, not a quote, so `require('./x.sh')` is invisible.

    Measured 2026-09-06: `/usr/bin/grep -oE '\\x27'` prints `x27` on a line containing `ax27b` and does not match a line containing `a'b`. The consequence on the real tree is five `.cjs` paths under `.github/workflows` that this gate cannot see. Asserted in BOTH directions so a future edit that "fixes" the escape is caught as the behaviour change it is.
    """
    assert "x27" in gate._LEAD
    assert "'" not in gate._LEAD, "restoring the quote changes which paths are judged"
    probe = "script: return await require('./scripts/hidden.sh')"
    assert gate.ROOT_COMMAND.search(probe) is None
    # The same invocation with a SPACE lead is seen, which is what makes the point above a blind spot rather than a total failure of the extractor.
    assert gate.ROOT_COMMAND.search("bash scripts/hidden.sh") is not None


def test_the_extractor_separates_invocation_from_mention(tmp_path):
    """The 2026-08-06 accuracy question, in both directions, without a subprocess."""
    probe = tmp_path / "p.sh"
    probe.write_text("bash scripts/real.sh\n", encoding="utf-8")
    assert gate.extract_refs(tmp_path) == ["scripts/real.sh"]
    probe.write_text('log_error "see scripts/real.sh"\n', encoding="utf-8")
    assert gate.extract_refs(tmp_path) == []


def test_dispatch_attribution_is_by_nearest_top_level_label():
    """Neither a fixed window nor a block scan; both of those were wrong.

    A window of 12 lines missed scripts/drills/license.sh at run.sh:1995, and a scan to the closing `;;` ran past `account)` because run.sh's arms terminate inline.
    """
    text = (
        "case $1 in\n"
        "        drill)\n"
        "            bash scripts/drills/a.sh\n"
        "            bash scripts/drills/b.sh\n"
        "            bash scripts/drills/c.sh\n"
        "            ;;\n"
        "        account)\n"
        "            bash scripts/dev/worktree.sh\n"
        "            ;;\n"
        "esac\n"
    )
    assert gate.dispatch_targets(text, "drill") == [
        "scripts/drills/a.sh",
        "scripts/drills/b.sh",
        "scripts/drills/c.sh",
    ]
    assert gate.dispatch_targets(text, "account") == ["scripts/dev/worktree.sh"]


def test_the_legacy_router_body_is_still_scanned():
    """Dropping it took this half to zero references, and the gate stayed green."""
    assert ".ci/legacy/run-legacy.sh" in gate.GATED_FILES
    assert "run.sh" in gate.GATED_FILES


def test_selftest_exits_zero_and_prints_a_count():
    """Exit 0 with zero PASS lines is a failure, so the count is asserted too."""
    code, out, err = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s --selftest"
        % MODULE
    )
    assert code == 0, err
    assert "control(s) passed" in out
    assert int(out.split(" control(s)")[0].strip()) >= 16


def test_the_twin_is_still_present():
    """Invariant 5: a twin is never deleted in the change that ports it."""
    assert (pathlib.Path(diff.repo()) / TWIN).is_file()
