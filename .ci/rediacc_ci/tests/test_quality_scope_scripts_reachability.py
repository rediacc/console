"""`rediacc_ci.quality.scope_scripts_reachability`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-scope-scripts-reachability.sh` over a git fixture with stdout and stderr captured SEPARATELY, and its bytes were compared against the port's. Same recipe as the committed ledger, `.ci/shadow/w7p2-scope-scripts-reachability.observations.jsonl`. The twin has now been deleted and every case that
executed it compares against `goldens/scope-scripts-reachability/`, which holds the twin's OWN recorded output, captured from the tracked script on its last day in the tree. The provenance header of each golden carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed those bytes.

THE FIXTURE CARRIES THE REAL `scope-map.cjs`, and it has to. The gate's verdict is whatever `classify()` says, and that file's rule ORDER is semantics (first match wins, driver contract section 3). A stubbed classifier would make these cases assert that the port agrees with the stub.

TWO CASES HERE ARE NOT IN THE LEDGER, and both are the interesting ones.

  * THE DISPATCH-FLOOR REFUSAL EXITS 127, not 1, because the twin called
    `log_fail` and never sourced the library that defines it. Both sides printed a
    single shell diagnostic and no finding, so `scripts/lib/shadow-gate.ts` scored
    the pair VACUOUS_BOTH_EMPTY and refused to record it. Byte equality can rule
    on it, so it lives here, and it is now the one recorded case whose LINE NUMBER
    had to be frozen into the port: `dispatch_floor_refusal` used to read the twin
    to find it. See `TWIN_LOG_FAIL_LINE`.
  * THE `\\x27` BLIND SPOT is a property of the twin's extractor rather than of any
    one tree: an invocation whose only lead character is a single quote was
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
from rediacc_ci.tests import frozen

SLUG = "scope-scripts-reachability"
MODULE = "scope_scripts_reachability"

RUNSH = """#!/bin/bash
case "$1" in
        drill)
            bash scripts/drills/lib.sh
            ;;
esac
"""


def build(tmp_path: pathlib.Path, extra: dict[str, str], *, runsh: bool = True) -> pathlib.Path:
    """A sealed git specimen with the port, scope-map.cjs and a run.sh.

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


def run_port(root: pathlib.Path) -> tuple[int, str, str]:
    return diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s" % MODULE,
        cwd=str(root),
    )


def split_golden(text: str) -> tuple[int, str, str]:
    """A recorded twin render, back into its three parts."""
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr


def compare(root: pathlib.Path, name: str) -> tuple[int, str, str]:
    """Byte equality on BOTH streams against the twin's recorded bytes."""
    want_exit, want_out, want_err = split_golden(frozen.read(SLUG, name))
    returncode, stdout, stderr = run_port(root)
    stdout = frozen.mask_root(stdout, root)
    stderr = frozen.mask_root(stderr, root)
    assert returncode == want_exit, "%s: the twin exited %d, the port %d" % (
        name,
        want_exit,
        returncode,
    )
    assert stdout == want_out, "%s: stdout diverged from the twin's recorded bytes" % name
    assert stderr == want_err, "%s: stderr diverged from the twin's recorded bytes" % name
    return returncode, stdout, stderr


MENTION = {
    ".ci/scripts/deploy/publish.sh": (
        'log_error "run scripts/gates/check-embed-credits.ts to fix this"\n'
    )
}

CASES = [
    (
        # THE NEGATIVE HALF. The baseline alone references only paths that classify `full`, so the gate must be silent. Without it, a port that called everything a violation would pass every red case below.
        "a-tree-whose-reachable-paths-all-force-full-is-silent",
        {},
        True,
        0,
    ),
    (
        "a-narrowable-path-referenced-from-a-workflow-is-a-violation",
        {".github/workflows/ci.yml": "npx tsx scripts/gates/check-embed-credits.ts\n"},
        True,
        1,
    ),
    (
        "a-narrowable-path-referenced-from-a-deploy-script-is-a-violation",
        {".ci/scripts/deploy/publish.sh": "npx tsx scripts/gates/check-embed-credits.ts\n"},
        True,
        1,
    ),
    (
        "a-narrowable-path-reached-only-through-the-run-sh-dispatch-is-a-violation",
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
        # DOCUMENTATION IS NOT A DEPENDENCY. This is the 2026-08-06 false positive that would have forced full CI on every scripts/dev edit forever, and it is what the planted control below re-breaks.
        "a-log-error-mention-of-a-narrowable-path-is-not-a-violation",
        MENTION,
        True,
        0,
    ),
    (
        "a-collapsed-ci-scan-refuses-rather-than-reporting-clean",
        {".github/workflows/ci.yml": "", ".ci/scripts/build/driver.sh": ""},
        True,
        1,
    ),
    (
        # THE `log_fail` DEFECT. Its own case rather than a parametrized one, because its verdict is 127 and its reason has a docstring of its own below.
        "the-dispatch-floor-refusal-exits-127",
        {},
        False,
        127,
    ),
]


@pytest.mark.parametrize(
    ("name", "extra", "runsh", "want_exit"),
    CASES,
    ids=[c[0] for c in CASES],
)
def test_port_matches_the_twins_recorded_output(tmp_path, name, extra, runsh, want_exit):
    """Byte equality on BOTH streams, plus the exit code the case expects."""
    root = build(tmp_path, extra, runsh=runsh)
    returncode, _stdout, _stderr = compare(root, name)
    assert returncode == want_exit, "the recorded verdict moved"


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, {name for name, _e, _r, _x in CASES})


def test_the_green_case_is_not_vacuously_equal() -> None:
    """Two implementations that both print nothing agree about nothing.

    The silent case prints a control tally on stdout and nothing on stderr; the violation case prints nothing on stdout and a finding on stderr. A recording in which both were empty would be the both-empty trap with the twin no longer around to blame.
    """
    silent = split_golden(
        frozen.read(SLUG, "a-tree-whose-reachable-paths-all-force-full-is-silent")
    )
    violation = split_golden(
        frozen.read(SLUG, "a-narrowable-path-referenced-from-a-workflow-is-a-violation")
    )
    assert silent[0] == 0
    assert violation[0] == 1
    assert silent[1] != ""
    assert violation[2] != ""
    assert silent[1] != violation[1]


def test_the_dispatch_floor_refusal_exits_127(tmp_path):
    """The `log_fail` defect, pinned so a one-sided repair is a disagreement.

    The twin never sourced `.ci/scripts/lib/common.sh`, and `log_fail` is defined only in `.ci/scripts/test/lib/test-helpers.sh` and four test scripts. Under `set -euo pipefail` the unknown command exited 127 at that line, so the three explanatory `echo`s and the `exit 1` beneath it never ran. The identical defect is already on the record for the pool-writer-safety gate's own
    bash twin, the since-retired shell battery runner.

    NOT IN THE LEDGER: both sides printed one shell diagnostic and no finding, so the comparator scored it VACUOUS_BOTH_EMPTY and refused to record it. Byte equality can rule on it, which is why the case lives here.
    """
    recorded_exit, recorded_out, recorded_err = split_golden(
        frozen.read(SLUG, "the-dispatch-floor-refusal-exits-127")
    )
    assert recorded_exit == 127
    assert "log_fail: command not found" in recorded_err
    assert "Refusing to report on the .ci/scripts half alone" not in (
        recorded_out + recorded_err
    ), "the explanatory text was reachable after all; the recording says otherwise"
    assert ":%d:" % gate.TWIN_LOG_FAIL_LINE not in recorded_err
    assert "line %d:" % gate.TWIN_LOG_FAIL_LINE in recorded_err, (
        "the frozen line number no longer matches the number bash printed"
    )
    compare(build(tmp_path, {}, runsh=False), "the-dispatch-floor-refusal-exits-127")


def test_planted_defect_is_caught_by_the_goldens(tmp_path):
    """THE CONTROL ON THE GOLDENS. Let a documented mention count as an invocation.

    Dropping the output-statement filter is the simplification that revives the 2026-08-06 false positive, and it turns the silent `a-log-error-mention-of-a-narrowable-path-is-not-a-violation` tree into a violation. The mutation is applied to the module COPY inside the throwaway fixture; the tracked port is never touched.
    """
    tracked = pathlib.Path(diff.repo()) / ".ci" / "rediacc_ci" / "quality" / ("%s.py" % MODULE)
    before = tracked.read_text(encoding="utf-8")
    anchor = 'OUTPUT_STATEMENT = re.compile(r"\\b(log_error|log_warn|log_info|log_debug|echo|printf)\\b")'
    assert before.count(anchor) == 1, "the plant's anchor moved"

    root = build(tmp_path, MENTION)
    copy = root / ".ci" / "rediacc_ci" / "quality" / ("%s.py" % MODULE)
    copy.write_text(
        copy.read_text(encoding="utf-8").replace(
            anchor, 'OUTPUT_STATEMENT = re.compile(r"(?!x)x")'
        ),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError):
        compare(root, "a-log-error-mention-of-a-narrowable-path-is-not-a-violation")

    # And the real, unmutated module still agrees against the same fixture.
    clean = build(tmp_path / "clean", MENTION)
    compare(clean, "a-log-error-mention-of-a-narrowable-path-is-not-a-violation")
    assert tracked.read_text(encoding="utf-8") == before


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
