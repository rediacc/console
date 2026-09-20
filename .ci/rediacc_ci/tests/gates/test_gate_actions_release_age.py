"""Port of `.ci/scripts/test/gates/test-actions-release-age.sh`.

Test for the release-age deferral and the anti-vacuity guard in `scripts/gates/check-actions.ts`.

TWO DEFECTS THIS COVERS.

1. NO NOTION OF RELEASE AGE. The gate demanded an upgrade the instant upstream
   published one. Measured 2026-07-28: docker/login-action v4.5.2 was published at
   07:04:43Z and had reddened the build by 07:21Z, seventeen minutes later, leaving
   only two bad options -- pin a barely-vetted SHA, or blocklist a version that is
   not actually blocked. It now defers through the SAME shared window as check-deps
   and check-embed-asset-freshness.

2. A VACUOUS PASS, the worse of the two. With every GitHub API lookup rate-limited
   the gate printed "All GitHub Actions are up-to-date (14 unknown)" and exited 0.
   Fourteen unknown means fourteen UNCHECKED, so it reported freshness it had
   verified for nothing, and an offline run would have done that indefinitely.

WHY THIS TEST IS OFFLINE. Its first version drove the real gate four times, which needed a GitHub token, spent ~56 API calls per run, and FAILED in CI's quality-gate harness where no token exists. Worse, when the anonymous limit tripped it passed for the wrong reason: it read "nothing fresh upstream" from output that actually said "nothing could be checked", which is the very
defect it exists to catch. Pure logic gets tested purely.

WHY NOT IMPORT check-actions.ts DIRECTLY. It invokes checkActions() at module scope, so importing it would run the gate. Adding a main-module guard to make it importable was rejected deliberately: a guard that is subtly wrong makes `npm run check:actions` exit 0 while doing nothing, which is a far worse vacuous pass than the one being fixed. The deferral logic is exercised through
the shared lib it delegates to, and the wiring is pinned against the source.

WHAT THE PORT CHANGES. The twin spawns one `npx tsx --eval` per window question, three times, at roughly a second each. The port asks all three in ONE process and reads the answers back as JSON, so the behavioural cases still drive the REAL `isWithinFreshnessWindow` -- not a Python re-implementation of it -- at a third of the process cost. The source-pinning cases are unchanged:
they read the file.
"""

import json

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-actions-release-age.sh"

GATE = paths.from_root("scripts/gates", "check-actions.ts")
LIB = paths.from_root("scripts", "lib", "release-age.ts")
NPMRC = paths.from_root(".npmrc")

DAY_MS = 86400000

# (published, now, min_age_ms) -> asked of the REAL helper, once per process.
QUESTIONS = {
    "fresh": ("2026-07-28T07:04:43Z", "2026-07-28T07:21:00Z", DAY_MS),
    "aged": ("2026-07-20T07:04:43Z", "2026-07-28T07:21:00Z", DAY_MS),
    "zero-window": ("2026-07-28T07:04:43Z", "2026-07-28T07:04:44Z", 0),
}

DRIVER = """
import { isWithinFreshnessWindow } from %(lib)s;
const Q = JSON.parse(process.env.RELEASE_AGE_QUESTIONS);
const out = {};
for (const [name, [published, now, minAge]] of Object.entries(Q)) {
  out[name] = isWithinFreshnessWindow(Date.parse(published), Date.parse(now), minAge)
    ? 'deferred'
    : 'eligible';
}
process.stdout.write('\\n@@RESULT@@' + JSON.stringify(out));
"""

# A ONE-SLOT DICT rather than a rebound module global: the answers are memoised, not reassigned, so no `global` statement is needed to write them.
_ANSWERS: dict[str, dict[str, str]] = {}


def gate_source(gate) -> str:
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    return GATE.read_text(encoding="utf-8")


def windows(gate) -> dict[str, str]:
    """Every question asked of the REAL shared helper, in one tsx process.

    This is behaviour and not a re-implementation: the same module `check-actions.ts` imports is the one answering.
    """
    if "value" in _ANSWERS:
        return _ANSWERS["value"]
    if not LIB.is_file():
        gate.log_fail("shared lib under test is missing: %s" % paths.relative_to_root(LIB))
    npx = harness.require_tool(
        "npx", "install node; the shared window lib is TypeScript driven through tsx"
    )
    result = harness.run(
        [npx, "tsx", "--eval", DRIVER % {"lib": json.dumps(str(LIB))}],
        cwd=paths.repo_root(),
        env={"RELEASE_AGE_QUESTIONS": json.dumps(QUESTIONS)},
    )
    marker = "@@RESULT@@"
    if result.rc != 0 or marker not in result.out:
        gate.log_fail(
            "the release-age driver did not report (rc=%d).\n--- stdout ---\n%s\n"
            "--- stderr ---\n%s" % (result.rc, result.out, result.err)
        )
    answers = json.loads(result.out.split(marker, 1)[1].strip())
    missing = sorted(set(QUESTIONS) - set(answers))
    if missing:
        gate.log_fail(
            "the driver answered %d of %d question(s); missing: %s"
            % (len(answers), len(QUESTIONS), ", ".join(missing))
        )
    _ANSWERS["value"] = answers
    return answers


def test_the_shared_lib_is_what_the_gate_uses(gate):
    """Anti-vacuity for this file: every behavioural assertion below drives the shared lib, so if the gate stopped delegating to it they would all pass while proving nothing about the gate."""
    src = gate_source(gate)
    gate.assert_contains(
        src,
        "from '../lib/release-age.js'",
        "check-actions.ts delegates to the shared release-age lib",
    )
    gate.assert_contains(
        src,
        "isWithinFreshnessWindow(published, nowMs, minReleaseAgeMs)",
        "and calls it with the publish time it fetched, not a local copy of the rule",
    )
    gate.log_pass(
        "the gate delegates to the shared window, so exercising the lib exercises the gate"
    )


def test_a_fresh_release_is_deferred(gate):
    # Seventeen minutes old, the exact case that reddened the build.
    gate.assert_eq(
        windows(gate)["fresh"], "deferred", "a release minutes old must be deferred, not demanded"
    )
    gate.log_pass("a seventeen-minute-old release is deferred")


def test_an_aged_release_is_eligible(gate):
    """THE CONTROL. Same helper, same shape, older release: it must come back eligible. Without this the deferral could be a mute button and every other assertion here would still pass."""
    gate.assert_eq(
        windows(gate)["aged"], "eligible", "a release well past the window must still be demanded"
    )
    gate.log_pass("control: an aged release remains eligible, so the window is not a mute button")


def test_a_zero_window_defers_nothing(gate):
    """The second control: with the feature disabled, even a release published this instant is eligible. Proves the deferral is driven by the window rather than by something incidental."""
    gate.assert_eq(
        windows(gate)["zero-window"], "eligible", "a zero window disables deferral entirely"
    )
    gate.log_pass("control: a zero window defers nothing")


def test_null_policy_is_fail_closed(gate):
    """A lookup hiccup must never manufacture an "upgrade is required now" failure. Pinned against the source: the lib deliberately leaves null-handling to the caller, and this gate's choice is the fail-closed one."""
    src = gate_source(gate)
    gate.assert_contains(src, "if (!publishedAt) return true", "a missing publish date defers")
    gate.assert_contains(
        src, "if (Number.isNaN(published)) return true", "and so does an unparseable one"
    )
    gate.log_pass("an absent or unparseable timestamp fails closed to deferred")


def test_deferrals_are_reported_not_silent(gate):
    """A silent defer is indistinguishable from a gate that stopped looking, which is the failure mode this repo keeps finding in its own tooling."""
    src = gate_source(gate)
    gate.assert_contains(src, "Deferred upgrades", "held-back upgrades are printed")
    gate.assert_contains(
        src,
        "become normal findings once the window passes",
        "and announced as postponed rather than dismissed",
    )
    gate.log_pass("deferrals are announced and explicitly temporary")


def test_total_lookup_failure_is_a_failure_not_a_pass(gate):
    """THE VACUOUS-PASS FIX. Zero resolved of N is evidence the read failed, never evidence that everything is current."""
    src = gate_source(gate)
    gate.assert_contains(
        src, "unknown.length === actions.size", "a run that resolved NOTHING is detected"
    )
    gate.assert_contains(
        src, "Could not resolve the latest release for ANY", "and says so explicitly"
    )
    gate.assert_contains(
        src, "Nothing was verified", "naming the reason rather than implying an all-green result"
    )
    gate.log_pass("a total lookup failure is reported as a failure, not as up-to-date")


def test_partial_failure_is_deliberately_not_fatal(gate):
    """Scope matters: failing on ONE flaky lookup would make this the flakiest gate in CI. Only a total failure is fatal, and that choice is written down."""
    gate.assert_contains(
        gate_source(gate),
        "only a TOTAL lookup failure is fatal",
        "the narrow scope is stated where the guard lives",
    )
    gate.log_pass("a partial lookup failure stays non-fatal, by design")


def test_window_source_is_the_shared_npmrc_setting(gate):
    """The number is a repo-wide policy, not a local preference."""
    if not LIB.is_file():
        gate.log_fail("shared lib under test is missing: %s" % paths.relative_to_root(LIB))
    if not NPMRC.is_file():
        gate.log_fail("%s is missing, so the policy this case pins has no source" % NPMRC)
    gate.assert_contains(
        LIB.read_text(encoding="utf-8"),
        "minimum-release-age",
        "the shared lib reads the window from .npmrc",
    )
    gate.assert_contains(
        NPMRC.read_text(encoding="utf-8"),
        "minimum-release-age=1440",
        "and .npmrc still sets it",
    )
    gate.log_pass("the window comes from the repo-wide supply-chain setting")
