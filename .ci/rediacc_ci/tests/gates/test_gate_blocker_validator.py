"""Port of `.ci/scripts/test/gates/test-blocker-validator.sh`, retired in W7 P5.

Unit tests for the BLOCKER library: the parser that reads a `BLOCKER:`-annotated suppression list, and the quality rule that decides whether a stated reason is a reason at all.

THE SUBJECT IS THE PORT. The twin tested `.ci/scripts/lib/blocker-validator.sh`, which was deleted in PLAN-retire-bash-oracles section 12 U1; every case below now drives its port, `rediacc_ci.core.blocker_validator`, through the port's own CLI (`pairs`, `reason`, `verify`: one verb per bash function the twin called). A PROCESS, not an import, for the reason the bash version gave
for its subprocess: the test observes what a caller observes, exit code included, rather than a function's return value. The bash library's byte-level answers stay frozen in `goldens/twins/lib.blocker-validator.jsonl`.

THE BANNED PHRASES ARE READ OUT OF THE CANONICAL at runtime (`python3 -m rediacc_ci.core.allowlist contract`) rather than retyped here; the bash version read its `LOW_EFFORT_BLOCKER_PATTERNS` mirror of the same list. That keeps `test_validate_rejects_every_low_effort_phrase` a CORPUS-DERIVED floor: adding a banned phrase adds a case here on its own, and a contract whose list emptied would fail the
anti-vacuity refusal below instead of passing over nothing.

WHY `test_validate_accepts_all_current_audit_entries` READS THE REAL POLICY FILES. It is the one case that is not fixture-driven, and deliberately: it asserts that every BLOCKER reason SHIPPING TODAY still passes the rule, which is what stops a tightened `BLOCKER_MIN_LENGTH` or a new banned phrase from reddening a gate somewhere else in the estate. It only READS them, so it
declares no `tree:` claim.
"""

import json
import os

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

LIB = paths.from_root(".ci", "rediacc_ci", "core", "blocker_validator.py")

# The allowlists the twin walks. Relative, and resolved against the repo root.
POLICY_FILES = (
    ".ci/policy/.audit-prod-allowlist",
    ".ci/policy/.audit-allowlist",
    ".ci/policy/.deps-upgrade-blocklist",
)


def run_module(gate, module: str, *argv: str) -> harness.RunResult:
    """`python3 -m <module> <argv...>` from the repo root, with `rediacc_ci` importable and nothing in the cwd shadowing it."""
    if not LIB.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(LIB))
    python3 = harness.require_tool("python3", "install python3; the subject IS a python module")
    return harness.run(
        [python3, "-m", module, *argv],
        cwd=paths.repo_root(),
        env={"PYTHONPATH": os.fspath(paths.ci_dir()), "PYTHONSAFEPATH": "1"},
    )


def parse(gate, list_path) -> tuple[dict[str, str], dict[str, str]]:
    """(ALLOWED, BLOCKER) as Python dicts, produced BY the port's `pairs` verb: one `allowed<TAB>key<TAB>1` or `blocker<TAB>key<TAB>reason` line per cell, the two tables the bash function filled through its namerefs."""
    result = run_module(gate, "rediacc_ci.core.blocker_validator", "pairs", os.fspath(list_path))
    if result.rc != 0:
        gate.log_fail("parse_blockered_list exited %d" % result.rc, result)
    allowed: dict[str, str] = {}
    blocker: dict[str, str] = {}
    for line in result.out.splitlines():
        kind, _, rest = line.partition("\t")
        key, _, value = rest.partition("\t")
        if kind == "allowed":
            allowed[key] = value
        elif kind == "blocker":
            blocker[key] = value
    return allowed, blocker


def verdict(gate, result: harness.RunResult) -> int:
    if result.rc not in (0, 1) or "Traceback (most recent call last)" in result.err:
        gate.log_fail("the validator crashed instead of giving a verdict", result)
    return result.rc


def validate(gate, ident: str, reason: str, source: str = "testfile") -> int:
    """The port's verdict: 0 accepted, 1 rejected. A crash (a traceback also exits 1) or a usage error is neither, so it fails the case instead of passing as a rejection."""
    return verdict(
        gate, run_module(gate, "rediacc_ci.core.blocker_validator", "reason", ident, reason, source)
    )


def verify(gate, list_path) -> int:
    return verdict(
        gate, run_module(gate, "rediacc_ci.core.blocker_validator", "verify", os.fspath(list_path))
    )


def low_effort_patterns(gate) -> list[str]:
    """`LOW_EFFORT_PHRASES`, read out of the canonical's published contract at runtime."""
    result = run_module(gate, "rediacc_ci.core.allowlist", "contract")
    if result.rc != 0:
        gate.log_fail("could not read the canonical contract", result)
    return list(json.loads(result.out).get("phrases", []))


def test_parse_empty_file(gate, tmp_path):
    (tmp_path / "list").write_text("", encoding="utf-8")
    allowed, blocker = parse(gate, tmp_path / "list")
    gate.assert_eq(len(allowed), 0, "empty file yields no entries")
    gate.assert_eq(len(blocker), 0, "empty file yields no blockers")
    gate.log_pass("parse empty file")


def test_parse_happy_path(gate, tmp_path):
    (tmp_path / "list").write_text(
        "# Some prose\n# BLOCKER: upstream X pins version Y; build-time only\n1234567\n",
        encoding="utf-8",
    )
    allowed, blocker = parse(gate, tmp_path / "list")
    gate.assert_eq(allowed.get("1234567", ""), "1", "ID registered")
    gate.assert_contains(blocker.get("1234567", ""), "upstream X pins", "BLOCKER captured")
    gate.log_pass("parse happy path")


def test_parse_grouped_ids_share_blocker(gate, tmp_path):
    (tmp_path / "list").write_text(
        "# BLOCKER: family of xmldom advisories; same transitive chain blocked by "
        "electron-builder major\n1000001\n1000002\n1000003\n",
        encoding="utf-8",
    )
    allowed, blocker = parse(gate, tmp_path / "list")
    gate.assert_eq(len(allowed), 3, "three IDs registered")
    for ident in ("1000001", "1000002", "1000003"):
        gate.assert_contains(blocker.get(ident, ""), "xmldom", "ID %s shares BLOCKER" % ident)
    gate.log_pass("parse grouped IDs share BLOCKER")


def test_parse_blank_line_resets_blocker(gate, tmp_path):
    (tmp_path / "list").write_text(
        "# BLOCKER: group A blocker reason with enough length to pass validation\n"
        "2000001\n\n2000002\n",
        encoding="utf-8",
    )
    _allowed, blocker = parse(gate, tmp_path / "list")
    gate.assert_contains(blocker.get("2000001", ""), "group A", "first ID got BLOCKER")
    gate.assert_eq(blocker.get("2000002", ""), "", "second ID (after blank) has no BLOCKER")
    gate.log_pass("blank line resets BLOCKER")


def test_parse_inline_form_with_blocker(gate, tmp_path):
    # Pattern used by .deps-upgrade-blocklist: "package-name # BLOCKER: reason"
    (tmp_path / "list").write_text(
        "antd  # BLOCKER: v6.x requires CSS-in-JS removal and component API changes\n"
        "electron  # BLOCKER: v40.x breaks native module rebuild with nan library errors\n",
        encoding="utf-8",
    )
    allowed, blocker = parse(gate, tmp_path / "list")
    gate.assert_eq(allowed.get("antd", ""), "1", "antd registered")
    gate.assert_contains(blocker.get("antd", ""), "CSS-in-JS", "antd BLOCKER captured from inline")
    gate.assert_contains(blocker.get("electron", ""), "native module", "electron BLOCKER captured")
    gate.log_pass("parse inline form with BLOCKER")


def test_validate_rejects_every_low_effort_phrase(gate):
    patterns = low_effort_patterns(gate)
    # ANTI-VACUITY, and it is the whole case: a library whose banned-phrase array emptied would make the loop below prove nothing while still exiting green.
    if not patterns:
        gate.log_fail(
            "the canonical's phrase list came back EMPTY, so the loop below checked "
            "nothing. Either the contract changed shape or the module did not import; "
            "either way this case's green would mean nothing."
        )
    for pattern in patterns:
        if validate(gate, "testid", pattern) == 0:
            gate.log_fail("LOW_EFFORT_PHRASES[%s] should be rejected but passed" % pattern)
    gate.log_pass(
        "every LOW_EFFORT_PHRASES entry is rejected (%d phrase(s) read from the canonical)"
        % len(patterns)
    )


def test_validate_rejects_short_reason(gate):
    # "upstream transitive" is 19 chars -- below the 30-char floor
    if validate(gate, "testid", "upstream transitive") == 0:
        gate.log_fail("short reason should be rejected")
    gate.log_pass("short reason is rejected")


def test_validate_accepts_substantive_reason(gate):
    good = (
        "electron-builder 26.x pins plist > xmldom 0.8.x; build-time only, requires "
        "electron major migration"
    )
    if validate(gate, "testid", good) != 0:
        gate.log_fail("substantive reason should pass")
    gate.log_pass("substantive reason passes")


def test_validate_rejects_deferral_phrasing(gate):
    """Routine-deferral phrasing is substring-matched, so it is rejected even when the reason is long and not an exact low-effort phrase. This is the guardrail against blocklisting installable routine bumps "to keep this merge focused"."""
    kick = (
        (
            "routine 5.9.0 minor bump, not security-relevant and not needed by this change; "
            "deferred to a dedicated dependency-bump PR"
        ),
        "routine patch deferred to a dedicated dependency-bump PR to keep this merge focused",
        "minor bump deferred to a dedicated dependency-bump PR once the guard admits the version",
    )
    for reason in kick:
        if validate(gate, "testid", reason) == 0:
            gate.log_fail(
                'can-kicking deferral reason should be rejected but passed: "%s"' % reason
            )
    # Legitimate major-migration holds that mention a dedicated PR must STILL pass -- they read "dedicated lint-tooling PR" / "dedicated PR that exercises the email flows", not "dedicated dependency-bump PR".
    legit = (
        (
            "v66 is a major release that adds and renames lint rules; adoption deferred to a "
            "dedicated lint-tooling PR that audits the rule-set"
        ),
        (
            "v9 is a major release with breaking transport changes; deferred to a dedicated PR "
            "that exercises the email flows before bumping"
        ),
    )
    for reason in legit:
        if validate(gate, "testid", reason) != 0:
            gate.log_fail(
                'legitimate major-migration reason should pass but was rejected: "%s"' % reason
            )
    gate.log_pass("routine-deferral phrasing rejected; legitimate major-migration holds accepted")


def test_validate_accepts_all_current_audit_entries(gate):
    """Sanity check: every BLOCKER reason in the currently-shipped allowlists must pass the quality gate. This catches regressions in BLOCKER_MIN_LENGTH or new banned phrases that collide with legitimate reasons."""
    checked = 0
    seen_files = 0
    for name in POLICY_FILES:
        path = paths.from_root(*name.split("/"))
        if not path.is_file():
            continue
        seen_files += 1
        _allowed, blocker = parse(gate, path)
        for ident, reason in blocker.items():
            if not reason:
                continue
            checked += 1
            if validate(gate, ident, reason, name) != 0:
                gate.log_fail(
                    "current allowlist entry %s in %s has a BLOCKER that fails validation: "
                    '"%s"' % (ident, name, reason)
                )
    # ANTI-VACUITY. The twin's loop `continue`s past a missing file, so on a tree where all three vanished it would report a pass having validated nothing. PORT-ONLY strengthening, and it is the difference between "they all pass" and "there were none".
    if seen_files == 0 or checked == 0:
        gate.log_fail(
            "read %d of the %d policy file(s) and found %d reason(s) to validate. Zero "
            "means this case asserted nothing, which is not a pass."
            % (seen_files, len(POLICY_FILES), checked)
        )
    gate.log_pass(
        "every current allowlist BLOCKER passes validation (%d reason(s) across %d file(s))"
        % (checked, seen_files)
    )


def test_verify_all_blockers_fails_on_missing(gate, tmp_path):
    (tmp_path / "list").write_text("# no BLOCKER here\n3000001\n", encoding="utf-8")
    if verify(gate, tmp_path / "list") == 0:
        gate.log_fail("verify_all_blockers should fail when BLOCKER missing")
    gate.log_pass("verify_all_blockers rejects missing BLOCKER")


def test_verify_all_blockers_passes_when_good(gate, tmp_path):
    (tmp_path / "list").write_text(
        "# BLOCKER: upstream package-X pins transitive package-Y <2; fix requires major "
        "migration\n4000001\n",
        encoding="utf-8",
    )
    if verify(gate, tmp_path / "list") != 0:
        gate.log_fail("verify_all_blockers should pass when BLOCKER good")
    gate.log_pass("verify_all_blockers accepts good BLOCKER")
