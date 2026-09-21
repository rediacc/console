"""Port of `.ci/scripts/test/gates/test-knip-blockers.sh`, retired in W7 P5.

Behavioural test for `scripts/gates/check-knip-blockers.ts`, the validator that holds knip's suppression arrays to the repo-wide BLOCKER convention.

WHAT IT GUARDS. `knip.jsonc`'s `ignore`, `ignoreDependencies`, `ignoreBinaries` and `ignoreUnresolved` arrays are the one place in the tree where a name can be made invisible to dead-code analysis by typing it. The convention is that every such entry carries a substantive `// BLOCKER:` reason, so a suppression cannot become permanent by being quiet. `entry` / `project` globs are
CONFIGURATION and are exempt; the exemption is a case here rather than a comment, because an exemption nothing tests is an exemption that will silently widen.

STALENESS IS NOT THIS GATE'S JOB, and the twin says so out loud: an ignore entry that no longer suppresses anything is reported by knip itself under `--treat-config-hints-as-errors`. Two gates asking different questions.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. `test_accepts_real_config` drives the validator seam-free over the REAL `knip.jsonc` at the repo root, and the validator additionally shells out to `git grep` across the working tree and the `private/account` submodule to collect `@public` tags. A battery step rewriting either mid-read is a divergence that would be blamed on this
port.
`REAL_TREE_TWIN = True` buys the serialisation, and it is honoured only because
this module declares no `XDIST_GROUP` of its own; see `real_tree_admission` in `test_twin_parity.py`.

THE SUBJECT IS NEVER REIMPLEMENTED. Every verdict comes from a real `npx tsx scripts/gates/check-knip-blockers.ts` run. The fixtures are the twin's, string
for string.

ADDED BY THE PORT: `test_the_real_config_declares_a_non_trivial_corpus`. The twin's real-config case asserts only that the validator exits 0, which a validator that parsed ZERO entries would also do -- and a line-based JSONC walk over four hand-written regexes is exactly the kind of reader that can stop matching after a reformat. The added case reads the count the validator prints
and refuses a corpus that has collapsed, so the shape is visible on every run instead of the verdict alone.
"""

import os
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

# test_accepts_real_config runs the validator over the real knip.jsonc, and the validator git-greps the whole working tree for @public tags. See the docstring.
REAL_TREE_TWIN = True

SUBJECT_REL = "scripts/gates/check-knip-blockers.ts"
SUBJECT = paths.from_root(*SUBJECT_REL.split("/"))
REAL_CONFIG_REL = "knip.jsonc"
REAL_CONFIG = paths.from_root(REAL_CONFIG_REL)

# `check-knip-blockers: 53 suppression entries validated in knip.jsonc`
VALIDATED_RE = re.compile(r"(\d+) suppression entries validated")

# The validator's own floor for a corpus that has not collapsed. Deliberately far under the live count (53 on 2026-09-08): this is a "the reader still reads" assertion, not a ratchet, and a ratchet here would be a second source of truth
# for a number knip.jsonc already owns.
CORPUS_FLOOR = 10


def require_subject(gate) -> str:
    """The subject and its interpreter, proved present before anything is claimed.

    A missing `npx` is a LOUD failure carrying the fix, never a skip: a case that could not run has not been checked, and unchecked folded into fine is the shape this directory refuses.
    """
    if not SUBJECT.is_file():
        gate.log_fail("subject under test is missing: %s" % SUBJECT_REL)
    return harness.require_tool(
        "npx", "install Node.js; the subject is a TypeScript program driven through tsx"
    )


def run_validator(gate, *args: str) -> harness.RunResult:
    """`npx tsx scripts/gates/check-knip-blockers.ts [...]`, from the repo root.

    The twin captures `2>&1` and asserts on the merged text, so callers read `.combined` for the same reason. It matters here beyond fidelity: npm prints an `Unknown project config "minimum-release-age"` warning to stderr on every `npx` invocation in this repo, so a port reading only `.out` would be fine and a port reading only `.err` would be matching npm's noise.
    """
    npx = require_subject(gate)
    return harness.run([npx, "tsx", SUBJECT_REL, *args], cwd=paths.repo_root())


def run_validator_with_config(gate, config_content: str) -> harness.RunResult:
    """`run_validator_with_config` from the twin: a temp knip.jsonc, then the gate.

    The twin binds its `mktemp -d` into a RETURN trap because a shell function has no other way to clean up after itself. `harness.temp_dir()` has that property natively, so the context manager is the whole difference.
    """
    with harness.temp_dir() as d:
        config = d / "knip.jsonc"
        config.write_text(config_content, encoding="utf-8")
        return run_validator(gate, "--config", os.fspath(config))


def validated_count(gate, output: str) -> int:
    """The number of suppression entries the validator says it read.

    ANTI-VACUITY: an output with no count at all is a FAILURE. "exit 0" from a validator that printed nothing recognisable is not evidence that it validated anything, and treating it as such is exactly how a gate passes without running.
    """
    match = VALIDATED_RE.search(output)
    if not match:
        gate.log_fail(
            "the validator exited without stating how many suppression entries it "
            'validated, so its green says nothing about what it read. Output: "%s"' % output
        )
    return int(match.group(1))


# ---------------------------------------------------------------------------


def test_accepts_real_config(gate):
    """THE REAL-TREE CASE. Real `knip.jsonc`, real `git grep` over the tree and the `private/account` submodule, no seams."""
    if not REAL_CONFIG.is_file():
        gate.log_fail("knip.jsonc missing at repo root")
    result = run_validator(gate)
    gate.assert_exit_code(
        0,
        result.rc,
        "real knip.jsonc should pass BLOCKER validation (output: %s)" % result.combined,
    )
    gate.log_pass("real knip.jsonc passes validation")


def test_accepts_group_blocker(gate):
    """A `// BLOCKER:` line covers every entry after it until a blank line or the end of the array, which is `parse_blockered_list`'s contract in the shared shell validator. One reason for a coherent group beats N copies of it."""
    result = run_validator_with_config(
        gate,
        """{
  "ignoreBinaries": [
    // BLOCKER: platform terminal emulators probed via child_process at runtime, never npm-managed
    "konsole",
    "xterm"
  ]
}""",
    )
    gate.assert_exit_code(0, result.rc, "grouped BLOCKER should cover following entries")
    gate.log_pass("group BLOCKER covers multiple entries")


def test_rejects_missing_blocker(gate):
    """The case the whole gate exists for: a suppression typed in with no reason."""
    result = run_validator_with_config(
        gate,
        """{
  "ignoreDependencies": [
    "some-package"
  ]
}""",
    )
    gate.assert_exit_code(1, result.rc, "entry without BLOCKER should fail")
    gate.assert_contains(result.combined, "missing a", "error message names the problem")
    gate.log_pass("missing BLOCKER is rejected")


def test_rejects_low_effort_blocker(gate):
    """A reason that is not a reason. Requiring the WORD `BLOCKER` and nothing else would industrialise `// BLOCKER: tbd`, which is worse than no convention because it reads as compliance."""
    result = run_validator_with_config(
        gate,
        """{
  "ignoreDependencies": [
    // BLOCKER: tbd
    "some-package"
  ]
}""",
    )
    gate.assert_exit_code(1, result.rc, "low-effort BLOCKER should fail")
    gate.assert_contains(
        result.combined, "low-effort placeholder", "error message identifies the issue"
    )
    gate.log_pass("low-effort BLOCKER is rejected")


def test_blank_line_resets_blocker(gate):
    """THE SCOPE BOUNDARY. Without the reset, one reason at the top of an array would cover everything anybody appended to it afterwards, forever."""
    result = run_validator_with_config(
        gate,
        """{
  "ignoreBinaries": [
    // BLOCKER: platform terminal emulators probed via child_process at runtime, never npm-managed
    "konsole",

    "xterm"
  ]
}""",
    )
    gate.assert_exit_code(1, result.rc, "entry after blank line should not inherit BLOCKER")
    gate.assert_contains(result.combined, "xterm", "the uncovered entry is named")
    gate.log_pass("blank line resets BLOCKER coverage")


def test_entry_project_exempt(gate):
    """THE CONVERSE, and without it every case above is satisfied by a validator
    that rejects everything. `entry` and `project` globs tell knip where to look;
    they suppress nothing, so demanding a reason for them would be noise that teaches readers to ignore the convention."""
    result = run_validator_with_config(
        gate,
        """{
  "workspaces": {
    "packages/foo": {
      "entry": [
        "src/index.ts"
      ],
      "project": [
        "src/**/*.ts"
      ]
    }
  }
}""",
    )
    gate.assert_exit_code(0, result.rc, "entry/project globs are configuration, not suppressions")
    gate.log_pass("entry/project arrays are exempt")


def test_the_real_config_declares_a_non_trivial_corpus(gate):
    """ADDED BY THE PORT: print the shape, so a collapse is visible rather than silent.

    `test_accepts_real_config` asserts exit 0 and nothing else, and exit 0 is also what a validator that parsed ZERO entries returns. The reader is a line-based JSONC walk over four hand-written regexes -- put an array on one line, change the quoting, let a formatter through, and `keyOpenArray` stops matching while the gate keeps reporting green over a corpus of nothing.

    So the count is READ from the validator's own verdict line and required to be non-trivial. Zero is a failure; so is a number that has fallen under the floor.
    """
    if not REAL_CONFIG.is_file():
        gate.log_fail("knip.jsonc missing at repo root")
    result = run_validator(gate)
    gate.assert_exit_code(0, result.rc, "the real config must pass before its shape means anything")
    count = validated_count(gate, result.combined)
    if count < CORPUS_FLOOR:
        gate.log_fail(
            "the validator read only %d suppression entr(ies) from %s, at or under the "
            "floor of %d. Either the JSONC reader stopped matching or the corpus really "
            "did collapse; both make this gate's green meaningless."
            % (count, REAL_CONFIG_REL, CORPUS_FLOOR)
        )
    gate.log_pass(
        "the real %s yields %d suppression entr(ies), comfortably over the floor of %d"
        % (REAL_CONFIG_REL, count, CORPUS_FLOOR)
    )
