"""Port of `.ci/scripts/test/gates/test-claude-hooks.sh`.

CI wrapper for the Claude hook harness at `.claude/hooks/test-hooks.sh`.

WHY THE WRAPPER EXISTS AT ALL. The pre-bash hooks carry live PR policy: draft-only
creation, green-gated `gh pr ready`, the `--admin` merge ban, merge-time review
hygiene. The harness (quote-strip evasion, command-position anchoring, prose
false-positive controls) previously ran only when someone remembered to run it, so a
hook regression could never turn CI red. Discovery by the battery is what put it
inside `npm run ci`.

THE TRANSLATION IS THE GATE, and it is the reason this is not just `bash test-hooks.sh`.
The harness speaks `ok [..]` plus a final `PASS=<n> FAIL=<m>` counter, not the
`PASS:` lines the battery counts, so trusting its exit code alone would let a harness
that silently ran ZERO cases report green. The wrapper requires `FAIL=0` AND a nonzero
case count, and the port keeps both halves plus a third the wrapper had implicitly:
the summary line must be PRESENT and parseable, because a harness whose output shape
changed is unchecked rather than fine.

A FLAT TWIN. It declares no `test_*()` functions, so `test_twin_parity.py` compares
against its runtime `PASS:` count (one line) rather than a case set. The port records
four controls against that floor, each naming a different property of the same run.

TWIN_TIMEOUT, AND WHY IT IS DECLARED HERE FIRST. This subject was UNPORTABLE by
construction until the parity driver gained a declarable timeout: 2 229 offline cases
at roughly 13m31s blow straight through the 600s default, `subprocess.run` RAISES on
timeout, and the driver produced a `TimeoutExpired` traceback instead of a verdict --
which reads as a broken harness rather than as a slow subject, and had this subject
one report away from being recorded as a permanent standing drop. 1000s leaves
headroom over the measured wall time without approaching the 1800s cap. If this ever
needs more than the cap, the answer is to SPLIT the harness, not to raise it.
"""

import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-claude-hooks.sh"

# See the module docstring. Measured at ~811s; the driver caps declarations at 1800.
TWIN_TIMEOUT = 1000

HARNESS = paths.from_root(".claude", "hooks", "test-hooks.sh")

# The wrapper's `grep -E '^PASS=[0-9]+ FAIL=[0-9]+$' | tail -1`, anchored the same way.
SUMMARY_RE = re.compile(r"^PASS=(\d+) FAIL=(\d+)$", re.MULTILINE)


def test_the_claude_hook_harness_is_green_and_not_empty(gate):
    if not HARNESS.is_file():
        gate.log_fail(
            "%s is missing, so the hook policy this gate exists to pin is unchecked. "
            "That is a FAILURE and not a skip." % paths.relative_to_root(HARNESS)
        )
    bash = harness.require_tool("bash", "install bash; the harness is a bash script")
    harness.require_tool("jq", "install jq; .claude/hooks/test-hooks.sh needs it")

    # Streams MERGED, as the wrapper's `2>&1` does: the harness writes its per-case
    # lines to stdout and some guards write diagnostics to stderr, and the summary
    # must be found regardless of which one carried it.
    result = harness.run([bash, str(HARNESS)], timeout=TWIN_TIMEOUT)
    if result.rc != 0:
        gate.log_fail(
            "claude-hook harness exited %d.\n--- stdout ---\n%s\n--- stderr ---\n%s"
            % (result.rc, result.out, result.err)
        )
    gate.log_pass("claude-hook harness exited 0")

    matches = SUMMARY_RE.findall(result.combined)
    if not matches:
        gate.log_fail(
            "no `PASS=<n> FAIL=<m>` summary line in the harness output, so its verdict "
            "could not be read at all -- which is UNCHECKED, not fine. The harness's "
            "output shape changed; re-read it rather than trusting its exit code.\n"
            "--- tail ---\n%s" % "\n".join(result.combined.splitlines()[-20:])
        )
    cases, fails = (int(x) for x in matches[-1])
    gate.log_pass("the harness printed a parseable summary (PASS=%d FAIL=%d)" % (cases, fails))

    gate.assert_eq(fails, 0, "the harness must report zero failing cases")
    gate.log_pass("no failing case in the harness summary")

    # ANTI-VACUITY, and it is the reason the wrapper exists rather than a bare
    # `bash test-hooks.sh`. A harness that dispatched nothing exits 0 with FAIL=0.
    if cases == 0:
        gate.log_fail(
            "the harness reported PASS=0: it ran no case at all, so its green means "
            "nothing. Check that the dispatcher still resolves the guard modules."
        )
    gate.log_pass("claude-hook harness green (%d offline cases)" % cases)
