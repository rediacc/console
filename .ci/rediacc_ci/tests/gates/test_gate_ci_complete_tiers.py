"""Port of `.ci/scripts/test/gates/test-ci-complete-tiers.sh`.

Both-ways test for the tier logic in `.ci/scripts/ci/assert-ci-complete.sh`, added with the pointer-bump fast path (2026-07-22).

The contract under test:
  - Normally, BUILD_DOCKER / BUILD_DOCKER_FAST / BUILD_CLI are HARD-required: a
    skip means the DAG broke and must read as red.
  - Under POINTER_BUMP_ONLY=true those three are DELIBERATELY skipped by ci.yml
    (content proven identical to a full-CI-green baseline), so their skips must
    read as green -- but a genuine FAILURE of any job must still be red, and
    INITIALIZE must still be hard-required.

Both directions matter: too strict and every fast-path run is red (the fast path is dead on arrival); too lax and a skipped build reads as green on a normal run, which is the exact DAG-breakage the hard tier exists to catch.

THE ONE PLACE THE PORT IS DELIBERATELY NOT A TRANSLATION. The twin hand-types the 21 `RESULT_*` names of its all-green baseline, with a comment on three of them recording that each was added only after a job landed and the fixture caught the omission by accident. That is a hand-typed floor, and the failure it invites is the quiet one: a job added to the subject and NOT to the
fixture is simply never exercised, and the suite stays green having stopped covering it.

So the port DERIVES the baseline from `HARD_REQUIRED` and `SOFT_REQUIRED` in the subject itself, refuses an empty parse, and keeps a case whose whole job is to
assert the two agree. Measured 2026-09-07: 5 hard + 16 soft = 21, exactly the
twin's 21. If they ever disagree the port reds and the twin does not, and the parity driver will say so -- which is the report a reader wants, not a silence.
"""

import os
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-ci-complete-tiers.sh"

SUT = paths.from_root(".ci", "scripts", "ci", "assert-ci-complete.sh")

ARRAY_RE = re.compile(r"^(HARD_REQUIRED|SOFT_REQUIRED)=\((.*?)\)", re.MULTILINE | re.DOTALL)
NAME_RE = re.compile(r"[A-Z][A-Z0-9_]*")

# A fast-path run: builds and their dependents skipped -> must PASS. This is a SCENARIO and not a floor, so it stays written out, exactly as the twin has it.
FASTPATH_SKIPS = {
    "POINTER_BUMP_ONLY": "true",
    "RESULT_BUILD_DOCKER": "skipped",
    "RESULT_BUILD_DOCKER_FAST": "skipped",
    "RESULT_BUILD_CLI": "skipped",
    "RESULT_STAGE_ARTIFACTS": "skipped",
    "RESULT_VALIDATE_INSTALL": "skipped",
    "RESULT_VALIDATE_PROMOTE": "skipped",
    "RESULT_TESTS": "skipped",
    "RESULT_ELITE_RUN_TEST": "skipped",
    "RESULT_OPS_TESTS": "skipped",
    "RESULT_UPDATE_FLOW_TEST": "skipped",
    "RESULT_DEPLOY_PREVIEW": "skipped",
    "RESULT_SMOKE_TEST_PREVIEW": "skipped",
    "RESULT_STRIPE_SANDBOX": "skipped",
    "RESULT_PACKAGE_TESTS": "skipped",
    # label-guide is PR-gated, so a pointer-bump run skips it like the rest.
    "RESULT_LABEL_GUIDE": "skipped",
    # breakpoint-lifecycle's if: excludes pointer_bump_only, so it skips here too
    "RESULT_BREAKPOINT_LIFECYCLE": "skipped",
}

# The twin's hand-typed set, kept ONLY so the derivation can be checked against it. Nothing below is driven from this.
TWIN_BASELINE_NAMES = frozenset(
    {
        "INITIALIZE",
        "BUILD_DOCKER",
        "BUILD_DOCKER_FAST",
        "BUILD_CLI",
        "RUN_SH_TESTS",
        "QUALITY",
        "REVIEW_GATE",
        "STRIPE_SANDBOX",
        "PACKAGE_TESTS",
        "CHECK_RELEASE_STATE",
        "STAGE_ARTIFACTS",
        "LABEL_GUIDE",
        "VALIDATE_INSTALL",
        "VALIDATE_PROMOTE",
        "TESTS",
        "ELITE_RUN_TEST",
        "OPS_TESTS",
        "UPDATE_FLOW_TEST",
        "DEPLOY_PREVIEW",
        "SMOKE_TEST_PREVIEW",
        "BREAKPOINT_LIFECYCLE",
    }
)


def required_jobs() -> dict[str, list[str]]:
    """`{"HARD_REQUIRED": [...], "SOFT_REQUIRED": [...]}` read from the subject.

    The `+=` re-binding inside the POINTER_BUMP_ONLY branch is deliberately NOT
    matched: the regex is anchored on `NAME=(`, and that branch spells it
    `SOFT_REQUIRED+=(`. The baseline this feeds is the NORMAL-path one.
    """
    source = SUT.read_text(encoding="utf-8")
    found: dict[str, list[str]] = {}
    for name, body in ARRAY_RE.findall(source):
        # Comment lines inside the array are prose about individual jobs and are full of the very names being parsed; drop them before extracting.
        cleaned = "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))
        found[name] = NAME_RE.findall(cleaned)
    return found


def baseline(gate) -> dict[str, str]:
    """Every job green. ANTI-VACUITY: an empty parse is a refusal, not a pass."""
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % SUT)
    jobs = required_jobs()
    names = jobs.get("HARD_REQUIRED", []) + jobs.get("SOFT_REQUIRED", [])
    if len(jobs) != 2 or not names:
        gate.log_fail(
            "could not read HARD_REQUIRED/SOFT_REQUIRED out of %s (found %r). Every case "
            "below builds its environment from that parse, so an empty one would drive "
            "the subject with NO RESULT_ variables at all -- which it would correctly "
            "fail, for a reason having nothing to do with the tier logic."
            % (paths.relative_to_root(SUT), sorted(jobs))
        )
    return {"RESULT_%s" % job: "success" for job in names}


def run_assert(gate, expected: int, name: str, overrides: dict | None = None, drop=()) -> None:
    """The twin's `run_assert`: green baseline plus overrides, under `env -i`.

    `env -i` IS the point and not tidiness. An unset `RESULT_*` must read as `<unset>` and fail, and this process inherits a real CI environment in CI, where those very names are exported.
    """
    env = baseline(gate)
    for key in drop:
        env.pop(key, None)
    env.update(overrides or {})
    env["PATH"] = os.environ.get("PATH", "")
    env["HOME"] = os.environ.get("HOME", "")
    result = harness.run(["bash", str(SUT)], env=env, env_replace=True)
    gate.assert_exit_code(expected, result.rc, name)
    gate.log_pass(name)


def test_all_green_passes(gate):
    run_assert(gate, 0, "all-green run passes (no fast path)")


def test_fastpath_skips_pass(gate):
    run_assert(gate, 0, "fast path: skipped builds+dependents pass", FASTPATH_SKIPS)


def test_skipped_build_fails_without_flag(gate):
    # The exact fast-path shape, but WITHOUT the flag: hard tier must fire.
    no_flag = {k: v for k, v in FASTPATH_SKIPS.items() if k != "POINTER_BUMP_ONLY"}
    run_assert(gate, 1, "no flag: skipped BUILD_* stays red (DAG breakage)", no_flag)


def test_flag_false_keeps_hard_tier(gate):
    run_assert(
        gate,
        1,
        "POINTER_BUMP_ONLY=false keeps the hard tier",
        {"POINTER_BUMP_ONLY": "false", "RESULT_BUILD_CLI": "skipped"},
    )


def test_failure_still_red_on_fastpath(gate):
    # The soft tier forgives skips, never failures.
    run_assert(
        gate,
        1,
        "fast path: a FAILED build is still red",
        {"POINTER_BUMP_ONLY": "true", "RESULT_BUILD_DOCKER": "failure"},
    )
    run_assert(
        gate,
        1,
        "fast path: a failed soft job (quality) is still red",
        {"POINTER_BUMP_ONLY": "true", "RESULT_QUALITY": "failure"},
    )


def test_initialize_stays_hard_on_fastpath(gate):
    run_assert(
        gate,
        1,
        "fast path: skipped INITIALIZE is still red",
        {"POINTER_BUMP_ONLY": "true", "RESULT_INITIALIZE": "skipped"},
    )


def test_unset_var_still_fails(gate):
    # A renamed job must break loudly, fast path or not.
    run_assert(
        gate,
        1,
        "unset RESULT_ var fails even on fast path",
        {"POINTER_BUMP_ONLY": "true"},
        drop=("RESULT_TESTS",),
    )


def test_the_baseline_is_derived_and_covers_every_required_job(gate):
    """PORT-ONLY, and it is the case the twin's hand-typed fixture cannot have.

    A job added to `SOFT_REQUIRED` and forgotten here is never exercised by any
    case above, and nothing goes red. Deriving the set removes the possibility;
    this asserts the derivation is real and still agrees with the twin.
    """
    jobs = required_jobs()
    derived = set(jobs.get("HARD_REQUIRED", [])) | set(jobs.get("SOFT_REQUIRED", []))
    if not derived:
        gate.log_fail("the derivation read zero required jobs out of %s" % SUT)
    missing = sorted(derived - TWIN_BASELINE_NAMES)
    extra = sorted(TWIN_BASELINE_NAMES - derived)
    if missing or extra:
        gate.log_fail(
            "the subject's required-job set and the twin's hand-typed baseline have "
            "drifted apart: %d in the subject but not the twin (%s), %d in the twin but "
            "not the subject (%s). The port drives the DERIVED set, so it is the twin "
            "that is now exercising the wrong fixture."
            % (len(missing), ", ".join(missing) or "-", len(extra), ", ".join(extra) or "-")
        )
    gate.log_pass(
        "baseline derived from the subject: %d hard + %d soft = %d job(s), matching the "
        "twin's fixture exactly"
        % (len(jobs["HARD_REQUIRED"]), len(jobs["SOFT_REQUIRED"]), len(derived))
    )
