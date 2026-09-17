"""Port of `.ci/scripts/test/gates/test-shell-counter-increment.sh`.

Regression test for a bash defect that was silently disarming four gates.

WHAT BROKE. Under `set -e`, the arithmetic COMMAND `((x++))` exits NON-ZERO when the
value it evaluates to is zero. Post-increment evaluates to the OLD value, so the very
first `((x++))` on a counter starting at 0 evaluates to 0, exits 1, and `set -e` kills
the script on the spot:

    $ bash -c 'set -euo pipefail; w=0; echo before; ((w++)); echo after'
    before
    $                       # "after" never prints, exit status 1

Every affected script begins `set -euo pipefail` and counts findings from 0, so each
one died at its FIRST finding. Twelve occurrences across four gates:
`check-workflows.sh` (3), `check-submodule-branches.sh` (7), `check-compose-env.sh`
(1), `check-commands.sh` (1).

WHY IT HID. The scripts still EXITED NON-ZERO, so the gates still went red and nobody
saw a false green. What was lost is everything after the first finding: the remaining
findings, the counts, and the summary line.

THE SEVERE ONE is `check-submodule-branches.sh`'s unreplied-review-comment counter.
That increment sat in a bare counting loop with no log line before it, inside a
function whose ONLY output is `echo "$unreplied_count"` at the end. So the first
unreplied comment killed the subshell before it echoed anything: the function could
report 0, and it could die, but it could never report a real count.

WHAT THIS MODULE DOES. It does not re-implement the loop. It extracts the REAL
function text out of the REAL gate script and runs it against a PATH-shimmed `gh`, so
the code under test is the code that ships. Then it does the same with the PRE-FIX
text recovered from git, which is the control.

THE CONTROL'S FIRST BRANCH IS UNEXERCISED ON THIS TREE, and that is worth saying
plainly rather than discovering it in CI. `HEAD` no longer contains the buggy
increment, so `test_prefix_version_could_not_count_at_all` takes its second arm on
every run here, exactly as the twin does. The first arm -- recover the old text,
build a harness from it, prove it echoes nothing -- is carried faithfully and has
never run in this checkout. If it ever fires, it is because somebody reintroduced
`((unreplied_count++))` into a commit, which is itself the finding.

ONE DELIBERATE ADDITION over the twin. Where the twin's second arm prints two `INFO`
lines and returns having asserted NOTHING, this port asserts the thing those lines
assume: that `HEAD` really is free of the buggy increment. A bash test may return
without a `PASS:` line; a ported test may not (`conftest.py` here refuses a green
that recorded no control), and inventing a decorative pass to satisfy that refusal
would be exactly the vacuity it exists to catch. So the arm makes a real claim.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. Two of its cases read the working
tree directly: the extraction reads `.ci/scripts/quality/check-submodule-branches.sh`
line by line, and the structural sweep greps every `.sh` under
`.ci/scripts/quality/` and `.ci/scripts/security/`. A battery step rewriting one of
those mid-sweep is a flake that would be blamed on this port. `REAL_TREE_TWIN = True`
is what buys the serialisation, and it is honoured only because this module declares
no `XDIST_GROUP` of its own.
"""

import json
import os
import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-shell-counter-increment.sh"

# Reads `.ci/scripts/quality/*.sh` and `.ci/scripts/security/*.sh` off the real working tree. See the module docstring.
REAL_TREE_TWIN = True

GATE_REL = ".ci/scripts/quality/check-submodule-branches.sh"
GATE = paths.from_root(*GATE_REL.split("/"))

# Two review comments, NEITHER of them replied to. A correct counter says 2.
FIXTURE = """[
  {"id": 101, "in_reply_to_id": null, "body": "first finding"},
  {"id": 102, "in_reply_to_id": null, "body": "second finding"}
]"""

# The pre-fix increment, as the twin greps for it.
BUGGY_INCREMENT_RE = re.compile(r"\(\(\s*unreplied_count\+\+\s*\)\)")

# `grep -qE '^\s*\(\(\s*[a-zA-Z_][a-zA-Z0-9_]*\+\+\s*\)\)\s*$'` from the twin's structural sweep, character for character.
STANDALONE_INCREMENT_RE = re.compile(r"^\s*\(\(\s*[a-zA-Z_][a-zA-Z0-9_]*\+\+\s*\)\)\s*$")

# `grep -q '^set -e\|^set -[a-z]*e'` -- the twin's own two-alternative BRE.
SET_E_RE = re.compile(r"^set -e|^set -[a-z]*e", re.MULTILINE)

# The three `sed -n '/START/,/END/p'` ranges the twin lifts out of the gate.
EXTRACT_RANGES = (
    (re.compile(r"^LOW_EFFORT_PATTERNS=\("), re.compile(r"^\)")),
    (re.compile(r"^is_low_effort_reply\(\)"), re.compile(r"^\}")),
    (re.compile(r"^check_pr_review_comments\(\)"), re.compile(r"^\}")),
)


def sed_range(source: str, start: re.Pattern[str], end: re.Pattern[str]) -> str:
    """`sed -n '/start/,/end/p'`, semantics included rather than approximated.

    RE-IMPLEMENTED RATHER THAN SHELLED OUT, and the semantics are the part worth
    stating because getting them subtly wrong is how an extraction quietly returns
    less than it should. sed opens a range on the first line matching `start`, keeps
    printing until a LATER line matches `end`, prints that line too, and then becomes
    eligible to open the range again. The `end` pattern is never tested against the
    same line that opened the range, which is why `is_low_effort_reply()` does not
    terminate on its own line. An unterminated range runs to end of input.
    """
    out: list[str] = []
    inside = False
    for line in source.splitlines():
        if not inside:
            if start.search(line):
                inside = True
                out.append(line)
            continue
        out.append(line)
        if end.search(line):
            inside = False
    return "".join(line + "\n" for line in out)


def gh_shim(bindir: pathlib.Path) -> pathlib.Path:
    """`mk_gh_shim`. A `gh` answering the one call the function makes, no network."""
    bindir.mkdir(parents=True, exist_ok=True)
    shim = bindir / "gh"
    shim.write_text("#!/bin/bash\ncat <<'JSON'\n%s\nJSON\n" % FIXTURE, encoding="utf-8")
    shim.chmod(0o755)
    return bindir


def build_harness(source: str, out: pathlib.Path) -> pathlib.Path:
    """`build_harness`. A runnable script around the function text taken from `source`.

    Extracting rather than copying is the point: if somebody rewrites the loop, this
    test follows them.
    """
    parts = [
        "#!/bin/bash",
        "set -euo pipefail",
        # The counting loop is all we exercise; these stubs stand in for the sourced
        # common.sh so the harness has no repo dependencies.
        "log_warn() { :; }",
        "log_error() { :; }",
        # gh_json is the third common.sh helper the gate now uses: the fetch was `gh api ... 2>/dev/null || echo "[]"`, which turned an API failure into a PR with no review comments. The stub keeps this harness about the COUNTING loop by passing the call straight through to the shimmed gh, exactly as the real helper does on its first successful attempt.
        'gh_json() { shift; [[ "${1:-}" == "--" ]] && shift; gh "$@"; }',
    ]
    body = "\n".join(parts) + "\n"
    for start, end in EXTRACT_RANGES:
        body += sed_range(source, start, end)
    body += "check_pr_review_comments some/repo 1\n"
    out.write_text(body, encoding="utf-8")
    out.chmod(0o755)
    return out


def run_harness(script: pathlib.Path, shim: pathlib.Path) -> harness.RunResult:
    """`run_harness`. The shim goes FIRST on PATH; stderr is discarded by the twin,
    so callers here read `.out` only."""
    bash = harness.require_tool("bash", "install bash; the subject IS a bash script")
    return harness.run(
        [bash, os.fspath(script)],
        cwd=paths.repo_root(),
        env={"PATH": "%s%s%s" % (shim, os.pathsep, os.environ.get("PATH", ""))},
    )


def gate_source(gate) -> str:
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE_REL)
    return GATE.read_text(encoding="utf-8")


def test_extraction_is_not_vacuous(gate):
    """Anti-vacuity: if the sed ranges stop matching (renamed function, reflowed
    file), both harnesses would be empty and both would "agree", which would look
    like a pass. Assert the real thing was actually extracted."""
    with harness.temp_dir() as work:
        built = build_harness(gate_source(gate), work / "new.sh")
        text = built.read_text(encoding="utf-8")
        gate.assert_contains(
            text, "check_pr_review_comments()", "the harness really contains the extracted function"
        )
        gate.assert_contains(
            text, "unreplied_count", "the harness really contains the counter under test"
        )
        gate.log_pass("the function text was extracted from the real gate, not stubbed")


def test_fixed_version_counts_every_unreplied_comment(gate):
    with harness.temp_dir() as work:
        shim = gh_shim(work / "bin")
        built = build_harness(gate_source(gate), work / "new.sh")
        result = run_harness(built, shim)
        gate.assert_eq(
            result.out.strip(),
            "2",
            "both unreplied comments are counted, so the gate can state a real number",
        )
        gate.log_pass("the fixed counter reports 2 of 2 unreplied comments")


def test_prefix_version_could_not_count_at_all(gate):
    """THE CONTROL. Recover the pre-fix text from git and prove it breaks. If this
    ever starts returning 2, the bug is gone from git history and this whole test is
    measuring nothing, so it fails loudly instead."""
    git = harness.require_tool("git", "install git; the control is recovered from history")
    show = harness.run([git, "-C", os.fspath(paths.repo_root()), "show", "HEAD:" + GATE_REL])
    if show.rc != 0:
        gate.log_fail("could not recover the pre-fix gate from HEAD; control unavailable")
    old_source = show.out

    if not BUGGY_INCREMENT_RE.search(old_source):
        gate.log_info("HEAD no longer contains the buggy increment (the fix has been committed)")
        gate.log_info("control satisfied by the standalone bash semantics assertion below")
        # THE ADDITION over the twin, and the reason is in the module docstring: a bash test may return with no PASS line, a ported one may not. Rather than print a decorative pass, assert what the two INFO lines above assume.
        gate.assert_eq(
            bool(BUGGY_INCREMENT_RE.search(old_source)),
            False,
            "HEAD's copy of the gate is free of ((unreplied_count++))",
        )
        gate.assert_eq(
            bool(BUGGY_INCREMENT_RE.search(gate_source(gate))),
            False,
            "and so is the working-tree copy, which is the one that ships",
        )
        gate.log_pass(
            "the fix is committed: neither HEAD nor the working tree contains ((unreplied_count++))"
        )
        return

    with harness.temp_dir() as work:
        shim = gh_shim(work / "bin")
        built = build_harness(old_source, work / "old.sh")
        result = run_harness(built, shim)
        gate.assert_eq(
            result.out.strip(),
            "",
            "the pre-fix counter died before echoing, so it could report no count at all",
        )
        gate.log_pass(
            "control: the pre-fix version produced NO count, confirming the defect was real"
        )


def test_bash_semantics_are_what_we_think(gate):
    """The claim underneath the whole fix, asserted directly rather than assumed:
    `((x++))` at zero is fatal under set -e, and the replacement form is not."""
    bash = harness.require_tool("bash", "install bash; the claim is about bash itself")
    before = harness.run([bash, "-c", "set -euo pipefail; w=0; ((w++)); echo reached"])
    after = harness.run([bash, "-c", "set -euo pipefail; w=0; w=$((w + 1)); echo reached"])
    gate.assert_eq(before.out.strip(), "", "((x++)) at zero aborts the script under set -e")
    gate.assert_eq(after.out.strip(), "reached", "x=$((x + 1)) at zero does not")
    gate.log_pass("the bash semantics behind the fix hold on this shell")


def test_no_standalone_increments_remain(gate):
    """Structural sweep, so a future edit cannot quietly reintroduce the class into
    any gate that runs under set -e."""
    root = paths.repo_root()
    files = sorted(
        [
            *(root / ".ci" / "scripts" / "quality").glob("*.sh"),
            *(root / ".ci" / "scripts" / "security").glob("*.sh"),
        ]
    )
    # ANTI-VACUITY, and the twin has no equivalent: its `for f in <glob>` would iterate the unexpanded pattern once, `[[ -f ]]` would drop it, and the sweep would report zero findings having read nothing.
    if not files:
        gate.log_fail(
            "the sweep matched no shell files under .ci/scripts/quality or "
            ".ci/scripts/security, so its clean verdict would mean nothing"
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
