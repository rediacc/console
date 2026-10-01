"""Port of `.ci/scripts/test/gates/test-shell-counter-increment.sh`, retired in W7 P5.

Regression test for a bash defect that was silently disarming four gates.

WHAT BROKE. Under `set -e`, the arithmetic COMMAND `((x++))` exits NON-ZERO when the value it evaluates to is zero. Post-increment evaluates to the OLD value, so the very first `((x++))` on a counter starting at 0 evaluates to 0, exits 1, and `set -e` kills the script on the spot:

    $ bash -c 'set -euo pipefail; w=0; echo before; ((w++)); echo after'
    before
    $                       # "after" never prints, exit status 1

Every affected script begins `set -euo pipefail` and counts findings from 0, so each one died at its FIRST finding. Twelve occurrences across four gates: `check-workflows.sh` (3), `check-submodule-branches.sh` (7), `check-compose-env.sh` (1), `check-commands.sh` (1).

WHY IT HID. The scripts still EXITED NON-ZERO, so the gates still went red and nobody saw a false green. What was lost is everything after the first finding: the remaining findings, the counts, and the summary line.

THE SEVERE ONE is `check-submodule-branches.sh`'s unreplied-review-comment counter. That increment sat in a bare counting loop with no log line before it, inside a
function whose ONLY output is `echo "$unreplied_count"` at the end. So the first
unreplied comment killed the subshell before it echoed anything: the function could report 0, and it could die, but it could never report a real count.

WHAT THIS MODULE DOES NOW. The gate whose counter this was, `check-submodule-branches.sh`, was retired under PLAN-retire-bash-oracles B3: CI runs its port, `.ci/rediacc_ci/quality/submodule_branches.py`, which counts in Python and cannot carry the defect. Its twin's text was extracted and driven here, together with a pre-fix copy recovered from git as the control; a deleted file can
be neither, and freezing its functions to keep running them would test code nothing executes. So the subject moves to the port: the same two-unreplied fixture through a PATH-shimmed `gh` must yield 2, and a PLANT that stops counting at the first comment must not. What stays bash is what is still about bash: the semantics claim the whole fix rests on, and the structural sweep,
widened from the two gate directories (which no longer hold a gate script) to every tracked `.sh` under `.ci/` so a reintroduction anywhere a script runs under `set -e` is caught.

ONE CASE READS THE WORKING TREE: the sweep reads every tracked `.ci/**/*.sh`. It is a read, and no `XDIST_GROUP` is declared: this module has no `BASH_TWIN`, so `real_tree_admission` in `test_twin_parity.py` never looks at it. A pure reader needs no group.
"""

import json
import os
import pathlib
import re
import subprocess

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

# Reads every tracked `.ci/**/*.sh` off the real working tree; reads need no group. See the module docstring.

GATE_REL = ".ci/rediacc_ci/quality/submodule_branches.py"
GATE = paths.from_root(*GATE_REL.split("/"))

# Two review comments, NEITHER of them replied to. A correct counter says 2.
FIXTURE = """[
  {"id": 101, "in_reply_to_id": null, "body": "first finding"},
  {"id": 102, "in_reply_to_id": null, "body": "second finding"}
]"""

# `grep -qE '^\s*\(\(\s*[a-zA-Z_][a-zA-Z0-9_]*\+\+\s*\)\)\s*$'` from the twin's structural sweep, character for character.
STANDALONE_INCREMENT_RE = re.compile(r"^\s*\(\(\s*[a-zA-Z_][a-zA-Z0-9_]*\+\+\s*\)\)\s*$")

# `grep -q '^set -e\|^set -[a-z]*e'` -- the twin's own two-alternative BRE.
SET_E_RE = re.compile(r"^set -e|^set -[a-z]*e", re.MULTILINE)


def gh_shim(bindir: pathlib.Path) -> pathlib.Path:
    """`mk_gh_shim`. A `gh` answering the one call the function makes, no network."""
    bindir.mkdir(parents=True, exist_ok=True)
    shim = bindir / "gh"
    shim.write_text("#!/bin/bash\ncat <<'JSON'\n%s\nJSON\n" % FIXTURE, encoding="utf-8")
    shim.chmod(0o755)
    return bindir


COUNT_PROGRAM = """import sys
sys.path.insert(0, sys.argv[1])
import importlib.util
spec = importlib.util.spec_from_file_location("subject", sys.argv[2])
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)
readable, count = subject.unreplied_review_comments("some/repo", "1")
print("%s %d" % ("readable" if readable else "UNREADABLE", count))
"""


def count_with(gate, module: pathlib.Path, work: pathlib.Path) -> str:
    """The port's unreplied count for the two-comment FIXTURE, through a PATH-shimmed `gh`."""
    shim = gh_shim(work / "bin")
    program = work / "count.py"
    program.write_text(COUNT_PROGRAM, encoding="utf-8")
    python3 = harness.require_tool("python3", "install python3")
    result = harness.run(
        [python3, os.fspath(program), os.fspath(paths.from_root(".ci")), os.fspath(module)],
        cwd=paths.repo_root(),
        env={"PATH": "%s%s%s" % (shim, os.pathsep, os.environ.get("PATH", ""))},
    )
    if result.rc != 0:
        gate.log_fail("the counting program did not run", result)
    return result.out.strip()


def test_extraction_is_not_vacuous(gate):
    """Anti-vacuity on the subject: the port must still expose the counter this file drives, or every case below would be exercising nothing."""
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE_REL)
    text = GATE.read_text(encoding="utf-8")
    gate.assert_contains(
        text, "def unreplied_review_comments(", "the port carries the fetch-and-count"
    )
    gate.assert_contains(text, "def count_unreplied(", "the port carries the counter under test")
    gate.log_pass("the counter under test is the port's own, not a stub")


def test_fixed_version_counts_every_unreplied_comment(gate):
    with harness.temp_dir() as work:
        got = count_with(gate, GATE, work)
    gate.assert_eq(
        got,
        "readable 2",
        "both unreplied comments are counted, so the gate can state a real number",
    )
    gate.log_pass("the port reports 2 of 2 unreplied comments")


def test_prefix_version_could_not_count_at_all(gate):
    """THE CONTROL, on the port: a counter that gives up after the first unreplied comment -- the shape the bash defect produced, one finding and then nothing -- must NOT satisfy the case above. If it did, that case could not fail."""
    source = GATE.read_text(encoding="utf-8")
    anchor = "def count_unreplied(comments: list[dict]) -> int:\n"
    if source.count(anchor) != 1:
        gate.log_fail("the plant's anchor moved; this control is planting nothing")
    planted = source.replace(anchor, anchor + "    comments = comments[:1]\n", 1)
    with harness.temp_dir() as work:
        mutant = work / "submodule_branches_mutant.py"
        mutant.write_text(planted, encoding="utf-8")
        got = count_with(gate, mutant, work)
    gate.assert_eq(
        got, "readable 1", "the planted early stop counts one, so the real case can tell"
    )
    gate.log_pass("control: a counter that stops at the first finding is caught")


def test_bash_semantics_are_what_we_think(gate):
    """The claim underneath the whole fix, asserted directly rather than assumed: `((x++))` at zero is fatal under set -e, and the replacement form is not."""
    bash = harness.require_tool("bash", "install bash; the claim is about bash itself")
    before = harness.run([bash, "-c", "set -euo pipefail; w=0; ((w++)); echo reached"])
    after = harness.run([bash, "-c", "set -euo pipefail; w=0; w=$((w + 1)); echo reached"])
    gate.assert_eq(before.out.strip(), "", "((x++)) at zero aborts the script under set -e")
    gate.assert_eq(after.out.strip(), "reached", "x=$((x + 1)) at zero does not")
    gate.log_pass("the bash semantics behind the fix hold on this shell")


def test_no_standalone_increments_remain(gate):
    """Structural sweep, so a future edit cannot quietly reintroduce the class into any gate that runs under set -e."""
    root = paths.repo_root()
    tracked = subprocess.run(
        ["git", "-C", os.fspath(root), "ls-files", "--", ".ci/*.sh"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    files = sorted(root / rel for rel in tracked)
    # ANTI-VACUITY, and the twin had no equivalent: its `for f in <glob>` would iterate the unexpanded pattern once, `[[ -f ]]` would drop it, and the sweep would report zero findings having read nothing.
    if not files:
        gate.log_fail(
            "the sweep matched no tracked shell file under .ci/, so its clean verdict would "
            "mean nothing"
        )
    found = 0
    scanned = 0
    for path in files:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not SET_E_RE.search(text):
            continue
        scanned += 1
        for line in text.splitlines():
            if STANDALONE_INCREMENT_RE.match(line):
                gate.log_error(
                    "standalone ((x++)) under set -e in %s" % paths.relative_to_root(path)
                )
                found += 1
                break
    gate.assert_eq(found, 0, "no gate under set -e still uses a standalone ((x++))")
    gate.log_pass(
        "no gate reintroduces the fatal-increment pattern (%d of %d file(s) run under set -e)"
        % (scanned, len(files))
    )
    # Print the shape, so a collapse in either number is visible rather than silent.
    gate.log_info(
        "sweep: %s" % json.dumps({"matched": len(files), "under_set_e": scanned, "findings": found})
    )
