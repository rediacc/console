"""Port of `.ci/scripts/test/gates/test-release-state-consistency.sh`, retired in W7 P5.

Unit-tests `rsv_assert_bijection` and `rsv_assert_channel_pointer_tagged` in `.ci/scripts/lib/release-state-validator.sh` against synthetic version lists. The live R2 and git probes are exercised end to end by the quality gate itself during CI; this pins the pure assertion logic so drift detection stays correct even if callers refactor.

HOW A PYTHON FILE DRIVES A BASH LIBRARY, and why the two sides agree. The twin
`source`s the library into its own shell ONCE and calls the functions directly;
this module spawns one fresh `bash -c` per call that sources the same file and calls the same function with the same arguments. The library reads both of its knobs (`RSV_GRANDFATHER_BEFORE`, `RSV_FLOOR_FILE`) at CALL time rather than at source time -- checked in the file, at the two reads inside `rsv_pre_contract_floor` -- so a per-call source and a once-per-file source answer
identically, and the per-call form additionally guarantees no case can leak state into the next one. Arguments are `shlex.quote`d, which is the same protection the twin gets from its `"$1"` quoting.

THE TWO ENVIRONMENT PREPARATIONS THE TWIN DOES AT LOAD TIME ARE DONE PER CALL
HERE, in the script text rather than in the process environment:
  * `unset RSV_GRANDFATHER_BEFORE`, so a value inherited from the operator's
    shell cannot silence the drift cases;
  * `RSV_FLOOR_FILE=/nonexistent/release-contract-floor.txt`, which keeps the
    unit cases independent of the production
    `.ci/config/release-contract-floor.txt` value.
Doing it in the script rather than through `env=` is deliberate: `harness.run`
OVERLAYS `os.environ`, so it can set a variable but cannot unset one, and an inherited `RSV_GRANDFATHER_BEFORE` would then suppress exactly the findings these cases exist to see.

OUTPUT IS READ MERGED (`.combined`), because the twin captures `2>&1` and every assertion below is written against that merged text.

NO `xdist_group`. The ratchet cases write a single file inside pytest's own `tmp_path`; nothing else is written anywhere, no port is bound and no module global is mutated.
"""

import pathlib
import shlex

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

LIB = paths.from_root(".ci", "scripts", "lib", "release-state-validator.sh")

# The twin's load-time value: a path that does not exist, so the ratchet is inert unless a case names its own file.
NO_FLOOR_FILE = "/nonexistent/release-contract-floor.txt"

POINTER_TAGS = "v1.2.9\nv1.3.0\nv1.3.1"


def rsv(
    gate,
    function: str,
    *args: str,
    floor_file: str = NO_FLOOR_FILE,
    grandfather: str | None = None,
) -> harness.RunResult:
    """`run_assert` / `run_pointer`: one call into the library, streams merged."""
    if not LIB.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(LIB))
    prelude = [
        "set -uo pipefail",
        "unset RSV_GRANDFATHER_BEFORE",
        "export RSV_FLOOR_FILE=%s" % shlex.quote(floor_file),
    ]
    if grandfather is not None:
        prelude.append("export RSV_GRANDFATHER_BEFORE=%s" % shlex.quote(grandfather))
    prelude.append("source %s" % shlex.quote(str(LIB)))
    prelude.append("rc=0")
    prelude.append("%s %s 2>&1 || rc=$?" % (function, " ".join(shlex.quote(a) for a in args)))
    prelude.append("exit $rc")
    return harness.run(["bash", "-c", "\n".join(prelude)])


def run_assert(gate, cli: str, tags: str, in_flight: str = "") -> harness.RunResult:
    return rsv(gate, "rsv_assert_bijection", cli, tags, in_flight)


def versions(*names: str) -> str:
    """The twin's `printf 'v1.0.0\\nv1.0.1\\n'`: newline separated, trailing newline."""
    return "".join(name + "\n" for name in names)


def test_all_committed_passes(gate):
    gate.log_test("all-committed -> OK")
    result = run_assert(
        gate, versions("v1.0.0", "v1.0.1", "v1.0.2"), versions("v1.0.0", "v1.0.1", "v1.0.2")
    )
    gate.assert_exit(0, result, "bijection should hold")
    gate.assert_contains(result.combined, "OK:", "positive confirmation emitted")
    gate.assert_not_contains(result.combined, "DRIFT", "no drift lines")
    gate.log_pass("all-committed")


def test_empty_state_passes(gate):
    gate.log_test("no sentinels + no tags -> OK")
    result = run_assert(gate, "", "")
    gate.assert_exit(0, result, "empty state is a bijection")
    gate.assert_contains(result.combined, "OK:", "positive confirmation emitted")
    gate.log_pass("empty-state")


def test_orphan_prefix_not_flagged(gate):
    # The library flags sentinel/tag drift, not the presence of orphan bytes without a sentinel. Orphans are handled upstream by the pre-upload scrub.
    gate.log_test("orphan prefix (no sentinel, no tag) -> OK (not this gate's concern)")
    result = run_assert(gate, versions("v1.0.0"), versions("v1.0.0"))
    gate.assert_exit(0, result, "orphan is not sentinel-vs-tag drift")
    gate.log_pass("orphan-prefix")


def test_sentinel_without_tag_fails(gate):
    gate.log_test("cli sentinel present, tag missing -> DRIFT (this is the #458 bug)")
    result = run_assert(gate, versions("v1.0.0", "v1.0.5"), versions("v1.0.0"))
    gate.assert_exit(1, result, "sentinel-without-tag must fail")
    gate.assert_contains(result.combined, "DRIFT v1.0.5", "names the drifted version")
    gate.assert_contains(
        result.combined, "cli sentinel present, git tag missing", "identifies direction"
    )
    gate.assert_contains(result.combined, "re-run CD to tag", "remediation present")
    gate.log_pass("sentinel-without-tag")


def test_tag_without_sentinel_fails(gate):
    gate.log_test("git tag present, cli sentinel missing -> DRIFT")
    result = run_assert(gate, versions("v1.0.0"), versions("v1.0.0", "v1.0.5"))
    gate.assert_exit(1, result, "tag-without-sentinel must fail")
    gate.assert_contains(result.combined, "DRIFT v1.0.5", "names the drifted version")
    gate.assert_contains(
        result.combined, "git tag present, cli sentinel missing", "identifies direction"
    )
    gate.assert_contains(result.combined, "re-run CI to produce artifacts", "remediation present")
    gate.log_pass("tag-without-sentinel")


def test_in_flight_excluded(gate):
    gate.log_test("in-flight version with no sentinel yet -> excluded, gate passes")
    result = run_assert(gate, versions("v1.0.0"), versions("v1.0.0"), "v1.0.5")
    gate.assert_exit(0, result, "in-flight exclusion prevents self-flag")
    gate.log_pass("in-flight-excluded")


def test_in_flight_does_not_mask_other_drift(gate):
    gate.log_test("in-flight exclusion does not hide unrelated drift")
    result = run_assert(gate, versions("v1.0.0", "v1.0.3"), versions("v1.0.0"), "v1.0.5")
    gate.assert_exit(1, result, "v1.0.3 drift must still fire")
    gate.assert_contains(result.combined, "DRIFT v1.0.3", "unrelated drift still caught")
    gate.assert_not_contains(result.combined, "DRIFT v1.0.5", "in-flight remains excluded")
    gate.log_pass("in-flight-targeted-exclusion")


def test_prerelease_tags_ignored(gate):
    gate.log_test("pre-release tags (v1.0.0-beta.1) are not part of the bijection")
    # rsv_list_git_tags filters these out in live use; assert the assertion
    # function also ignores them when they happen to appear in inputs.
    result = run_assert(gate, versions("v1.0.0"), versions("v1.0.0", "v1.0.1-beta.1"))
    gate.assert_exit(0, result, "pre-release tag must not trigger drift")
    gate.log_pass("prerelease-filtered")


def test_floor_excludes_pre_contract_tags(gate):
    gate.log_test("tags older than the oldest cli sentinel are excluded (data-derived floor)")
    # Mirrors the live shape: pre-contract tags exist (v0.9.5..v1.0.4) but have no sentinel; the contract first wrote a sentinel at v1.0.5.
    result = run_assert(
        gate,
        versions("v1.0.5", "v1.0.6"),
        versions("v0.9.5", "v1.0.0", "v1.0.4", "v1.0.5", "v1.0.6"),
    )
    gate.assert_exit(0, result, "pre-contract tags must not trigger drift")
    gate.assert_not_contains(result.combined, "DRIFT v0.9.5", "v0.9.5 is below floor")
    gate.assert_not_contains(result.combined, "DRIFT v1.0.0", "v1.0.0 is below floor")
    gate.assert_not_contains(result.combined, "DRIFT v1.0.4", "v1.0.4 is below floor")
    gate.assert_contains(result.combined, "floor: v1.0.5", "OK line surfaces derived floor")
    gate.log_pass("floor-excludes-pre-contract")


def test_floor_does_not_mask_post_contract_drift(gate):
    gate.log_test("tags at-or-above the derived floor still subject to bijection")
    result = run_assert(gate, versions("v1.0.5", "v1.0.6"), versions("v1.0.5", "v1.0.6", "v1.0.7"))
    gate.assert_exit(1, result, "post-contract drift must still fire")
    gate.assert_contains(
        result.combined, "DRIFT v1.0.7", "v1.0.7 is at-or-above floor; drift fires"
    )
    gate.assert_not_contains(
        result.combined, "DRIFT v1.0.5", "v1.0.5 (== floor) is committed, no drift"
    )
    gate.log_pass("floor-does-not-mask")


def test_no_sentinels_short_circuits(gate):
    gate.log_test("no cli sentinels (and no override) -> bijection short-circuits to OK")
    # Fresh dev bucket / pre-rollout state: contract not in effect for any tag we have. Asserting drift on every tag would be useless noise.
    result = run_assert(gate, "", versions("v0.9.5", "v1.0.0", "v1.0.4"))
    gate.assert_exit(0, result, "no-sentinels state is a no-op")
    gate.assert_contains(result.combined, "contract not in effect", "diagnostic message present")
    gate.log_pass("no-sentinels-short-circuits")


def test_explicit_override_still_works(gate):
    gate.log_test("RSV_GRANDFATHER_BEFORE overrides the data-derived floor")
    # Operators can pin a synthetic floor for emergency dry-runs or tests. A cli
    # sentinel at v1.0.5 would normally derive floor=v1.0.5; the override pushes
    # it to v1.5.0 and every drift below that must then be silenced.
    result = rsv(
        gate,
        "rsv_assert_bijection",
        versions("v1.0.5"),
        versions("v1.0.5", "v1.0.6"),
        "",
        grandfather="v1.5.0",
    )
    gate.assert_exit(0, result, "override pushes floor up; drift below it suppressed")
    gate.assert_not_contains(result.combined, "DRIFT v1.0.6", "v1.0.6 < override; not flagged")
    gate.assert_contains(result.combined, "floor: v1.5.0", "OK line reflects overridden floor")
    gate.log_pass("explicit-override")


def test_ratchet_lifts_floor_above_observed(gate, tmp_path: pathlib.Path):
    gate.log_test("ratchet file value lifts floor above observed CLI sentinels")
    # If an operator scrubs a recent cli sentinel, the observed oldest shifts up silently. The ratchet's role is to remember where the floor used to be.
    ratchet = tmp_path / "floor.txt"

    # Case 1: ratchet below observed -> observed wins.
    ratchet.write_text("v1.0.6\n", encoding="utf-8")
    result = rsv(
        gate,
        "rsv_assert_bijection",
        versions("v1.0.8", "v1.0.9"),
        versions("v1.0.6", "v1.0.7", "v1.0.8", "v1.0.9"),
        "",
        floor_file=str(ratchet),
    )
    gate.assert_exit(0, result, "ratchet < observed: observed v1.0.8 floor used")
    gate.assert_contains(result.combined, "floor: v1.0.8", "floor message names v1.0.8")
    gate.assert_not_contains(result.combined, "DRIFT v1.0.6", "v1.0.6 below floor; suppressed")

    # Case 2: ratchet above observed -> ratchet wins, drift still suppressed below floor.
    ratchet.write_text("v1.0.10\n", encoding="utf-8")
    result = rsv(
        gate,
        "rsv_assert_bijection",
        versions("v1.0.8", "v1.0.10"),
        versions("v1.0.8", "v1.0.9", "v1.0.10"),
        "",
        floor_file=str(ratchet),
    )
    gate.assert_exit(0, result, "ratchet > observed: ratchet floor used, no drift below")
    gate.assert_contains(result.combined, "floor: v1.0.10", "ratchet pulls floor up to v1.0.10")
    gate.assert_not_contains(
        result.combined, "DRIFT v1.0.8", "observed v1.0.8 below ratchet floor; suppressed"
    )
    gate.assert_not_contains(
        result.combined, "DRIFT v1.0.9", "v1.0.9 below ratchet floor; suppressed"
    )
    gate.log_pass("ratchet-lifts-floor")


def test_ratchet_protects_against_all_sentinels_scrubbed(gate, tmp_path: pathlib.Path):
    gate.log_test("ratchet pins floor even when every cli sentinel is missing")
    # Without the ratchet an empty cli sentinel list short-circuits to OK ("no contract in effect yet"), which is right for a fresh dev bucket and WRONG for a production bucket where releases have happened.
    ratchet = tmp_path / "floor.txt"
    ratchet.write_text("v1.0.8\n", encoding="utf-8")
    result = rsv(
        gate,
        "rsv_assert_bijection",
        "",
        versions("v1.0.7", "v1.0.8", "v1.0.9"),
        "",
        floor_file=str(ratchet),
    )
    gate.assert_exit(1, result, "tags above ratchet with no cli sentinel must drift")
    gate.assert_contains(
        result.combined,
        "DRIFT v1.0.8",
        "v1.0.8 tag without cli sentinel; ratchet keeps it in scope",
    )
    gate.assert_contains(result.combined, "DRIFT v1.0.9", "v1.0.9 likewise")
    gate.assert_not_contains(
        result.combined, "DRIFT v1.0.7", "v1.0.7 below ratchet; still grandfathered"
    )
    gate.log_pass("ratchet-protects-empty-observed")


# =============================================================================
# rsv_assert_channel_pointer_tagged -- the relation the bijection does NOT cover
# =============================================================================
# The bijection reconciles sentinels against tags, and a bump-none merge correctly skips BOTH. The channel pointer was advanced anyway, so it could name a version with no tag and a 404 notes URL. Measured live: cli/edge advertised 1.3.1 across three bump-none merges (#573, #574, #576) with no v1.3.1 tag.


def run_pointer(gate, channel: str, latest: str, manifest: str, tags: str, in_flight: str = ""):
    return rsv(
        gate, "rsv_assert_channel_pointer_tagged", channel, latest, manifest, tags, in_flight
    )


def test_pointer_naming_a_tagged_version_passes(gate):
    result = run_pointer(gate, "edge", "v1.3.1", "v1.3.1", POINTER_TAGS)
    gate.assert_exit(0, result, "a tagged pointer must pass")
    gate.assert_contains(result.combined, "OK:", "positive confirmation emitted")
    gate.log_pass("a pointer naming a tagged version passes")


def test_pointer_naming_an_untagged_version_is_caught(gate):
    # THE BUG, reproduced exactly.
    result = run_pointer(gate, "edge", "v9.9.9", "v9.9.9", POINTER_TAGS)
    gate.assert_exit(1, result, "an untagged pointer MUST fail")
    gate.assert_contains(result.combined, "NO git tag", "the finding names the cause")
    gate.log_pass("a pointer naming an untagged version is caught")


def test_torn_pointer_write_is_caught(gate):
    # latest.json and manifest.json are written seconds apart; disagreement means install.sh and the auto-updater resolve to different versions.
    result = run_pointer(gate, "edge", "v1.3.1", "v1.3.0", POINTER_TAGS)
    gate.assert_exit(1, result, "a torn write MUST fail")
    gate.assert_contains(result.combined, "torn write", "the finding names the cause")
    gate.log_pass("a torn pointer write is caught")


def test_unreadable_pointer_is_not_a_pass(gate):
    # A pointer nobody could read is never a clean channel.
    result = run_pointer(gate, "edge", "", "v1.3.1", POINTER_TAGS)
    gate.assert_exit(1, result, "an unreadable pointer must NOT pass")
    gate.assert_contains(
        result.combined, "never a pass", "refuses to certify a read it could not make"
    )
    gate.log_pass("an unreadable pointer fails rather than passing blind")


def test_in_flight_version_is_excluded(gate):
    # The pointer for release X is written BEFORE X's tag is pushed. Without this exclusion the relation would redden every release that uses it.
    result = run_pointer(gate, "edge", "v9.9.9", "v9.9.9", POINTER_TAGS, "v9.9.9")
    gate.assert_exit(0, result, "the in-flight version must be excluded")
    gate.assert_contains(result.combined, "in-flight", "says why it was excluded")
    gate.log_pass("the in-flight version is excluded, so the gate is safe on the release path")


def test_control_the_tag_lookup_can_fail(gate):
    # CONTROL, by construction: a version present in the tag list must pass and one absent must fail, using the SAME inputs. If both answered the same the assertions above would be decoration.
    tagged = run_pointer(gate, "edge", "v1.3.0", "v1.3.0", POINTER_TAGS).rc
    untagged = run_pointer(gate, "edge", "v0.0.1", "v0.0.1", POINTER_TAGS).rc
    if not (tagged == 0 and untagged == 1):
        gate.log_fail(
            "CONTROL DID NOT FIRE: tagged=%d untagged=%d; the tag lookup does not "
            "discriminate" % (tagged, untagged)
        )
    gate.log_pass("control fires: the tag lookup distinguishes tagged from untagged")
