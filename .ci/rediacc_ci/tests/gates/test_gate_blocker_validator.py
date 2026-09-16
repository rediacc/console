"""Port of `.ci/scripts/test/gates/test-blocker-validator.sh`.

Unit tests for `.ci/scripts/lib/blocker-validator.sh`: the parser that reads a
`BLOCKER:`-annotated suppression list, and the quality rule that decides whether a
stated reason is a reason at all.

WHY THE SUBJECT CANNOT BE REACHED WITHOUT BASH, and why that is not a shortcoming
of the port. `parse_blockered_list` takes two NAMEREF arguments -- the caller
declares `ALLOWED` and `BLOCKER` as associative arrays and passes their NAMES, and
the function writes through `declare -n`. There is no stdout form of that result
and no file it lands in. So the only honest way to observe it is from inside a
bash process, which is exactly what every case below does: a snippet that sources
the real library, calls the real function, and PRINTS what landed in the arrays.
Re-implementing the parser in Python to avoid the subprocess would be testing a
copy.

`LOW_EFFORT_BLOCKER_PATTERNS` is READ OUT OF THE LIBRARY at runtime rather than
retyped here. That keeps `test_validate_rejects_every_low_effort_phrase` a
CORPUS-DERIVED floor: adding a banned phrase to the library adds a case here on
its own, and a library whose array emptied would fail the anti-vacuity refusal
below instead of passing over nothing.

WHY `test_validate_accepts_all_current_audit_entries` READS THE REAL POLICY FILES.
It is the one case that is not fixture-driven, and deliberately: it asserts that
every BLOCKER reason SHIPPING TODAY still passes the rule, which is what stops a
tightened `BLOCKER_MIN_LENGTH` or a new banned phrase from reddening a gate
somewhere else in the estate. It only READS them, so it declares no `tree:` claim.
"""

import os
import shlex

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-blocker-validator.sh"

LIB = paths.from_root(".ci", "scripts", "lib", "blocker-validator.sh")

# The allowlists the twin walks. Relative, and resolved against the repo root.
POLICY_FILES = (
    ".ci/policy/.audit-prod-allowlist",
    ".ci/policy/.audit-allowlist",
    ".ci/policy/.deps-upgrade-blocklist",
)


def bash_lib(gate, snippet: str) -> harness.RunResult:
    """Source the real library in a fresh shell and run `snippet`."""
    if not LIB.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(LIB))
    bash = harness.require_tool("bash", "install bash; the subject IS a bash library")
    return harness.run(
        [bash, "-c", 'set -uo pipefail\nsource "%s"\n%s' % (os.fspath(LIB), snippet)],
        cwd=paths.repo_root(),
    )


def parse(gate, list_path) -> tuple[dict[str, str], dict[str, str]]:
    """(ALLOWED, BLOCKER) as Python dicts, produced BY the real bash parser.

    The two arrays are printed with a NUL-free but unambiguous separator and read
    back here. `declare -p` would have been shorter and is not used on purpose: it
    would need re-parsing bash's own quoting, and a subtly wrong unquoter is a
    second implementation of the thing under test.
    """
    snippet = (
        "declare -A ALLOWED=() BLOCKER=()\n"
        "parse_blockered_list %s ALLOWED BLOCKER\n"
        'for k in "${!ALLOWED[@]}"; do printf "A\\t%%s\\t%%s\\n" "$k" "${ALLOWED[$k]}"; done\n'
        'for k in "${!BLOCKER[@]}"; do printf "B\\t%%s\\t%%s\\n" "$k" "${BLOCKER[$k]}"; done\n'
    ) % shlex.quote(str(list_path))
    result = bash_lib(gate, snippet)
    if result.rc != 0:
        gate.log_fail("parse_blockered_list exited %d: %s" % (result.rc, result.combined))
    allowed: dict[str, str] = {}
    blocker: dict[str, str] = {}
    for line in result.out.splitlines():
        kind, _, rest = line.partition("\t")
        key, _, value = rest.partition("\t")
        if kind == "A":
            allowed[key] = value
        elif kind == "B":
            blocker[key] = value
    return allowed, blocker


def validate(gate, ident: str, reason: str, source: str = "testfile") -> int:
    result = bash_lib(
        gate,
        "validate_blocker_quality %s %s %s >/dev/null 2>&1"
        % (shlex.quote(ident), shlex.quote(reason), shlex.quote(source)),
    )
    return result.rc


def low_effort_patterns(gate) -> list[str]:
    """`LOW_EFFORT_BLOCKER_PATTERNS`, read out of the library at runtime."""
    result = bash_lib(gate, 'printf "%s\\n" "${LOW_EFFORT_BLOCKER_PATTERNS[@]}"')
    if result.rc != 0:
        gate.log_fail("could not read LOW_EFFORT_BLOCKER_PATTERNS: %s" % result.combined)
    return [line for line in result.out.splitlines() if line]


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
    # Pattern used by .deps-upgrade-blocklist: "package-name  # BLOCKER: reason"
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
    # ANTI-VACUITY, and it is the whole case: a library whose banned-phrase array
    # emptied would make the loop below prove nothing while still exiting green.
    if not patterns:
        gate.log_fail(
            "LOW_EFFORT_BLOCKER_PATTERNS came back EMPTY, so the loop below checked "
            "nothing. Either the array was renamed or the library did not source; "
            "either way this case's green would mean nothing."
        )
    for pattern in patterns:
        if validate(gate, "testid", pattern) == 0:
            gate.log_fail("LOW_EFFORT_BLOCKER_PATTERNS[%s] should be rejected but passed" % pattern)
    gate.log_pass(
        "every LOW_EFFORT_BLOCKER_PATTERNS entry is rejected (%d phrase(s) read from the "
        "library)" % len(patterns)
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
    """Routine-deferral phrasing is substring-matched, so it is rejected even when
    the reason is long and not an exact low-effort phrase. This is the guardrail
    against blocklisting installable routine bumps "to keep this merge focused".
    """
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
    # Legitimate major-migration holds that mention a dedicated PR must STILL pass --
    # they read "dedicated lint-tooling PR" / "dedicated PR that exercises the email
    # flows", not "dedicated dependency-bump PR".
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
    """Sanity check: every BLOCKER reason in the currently-shipped allowlists must
    pass the quality gate. This catches regressions in BLOCKER_MIN_LENGTH or new
    banned phrases that collide with legitimate reasons.
    """
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
    # ANTI-VACUITY. The twin's loop `continue`s past a missing file, so on a tree
    # where all three vanished it would report a pass having validated nothing.
    # PORT-ONLY strengthening, and it is the difference between "they all pass"
    # and "there were none".
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
    snippet = (
        "declare -A ALLOWED=() BLOCKER=()\n"
        "parse_blockered_list %s ALLOWED BLOCKER\n"
        "verify_all_blockers %s BLOCKER >/dev/null 2>&1\n"
    ) % (shlex.quote(str(tmp_path / "list")), shlex.quote(str(tmp_path / "list")))
    if bash_lib(gate, snippet).rc == 0:
        gate.log_fail("verify_all_blockers should fail when BLOCKER missing")
    gate.log_pass("verify_all_blockers rejects missing BLOCKER")


def test_verify_all_blockers_passes_when_good(gate, tmp_path):
    (tmp_path / "list").write_text(
        "# BLOCKER: upstream package-X pins transitive package-Y <2; fix requires major "
        "migration\n4000001\n",
        encoding="utf-8",
    )
    snippet = (
        "declare -A ALLOWED=() BLOCKER=()\n"
        "parse_blockered_list %s ALLOWED BLOCKER\n"
        "verify_all_blockers %s BLOCKER >/dev/null 2>&1\n"
    ) % (shlex.quote(str(tmp_path / "list")), shlex.quote(str(tmp_path / "list")))
    if bash_lib(gate, snippet).rc != 0:
        gate.log_fail("verify_all_blockers should pass when BLOCKER good")
    gate.log_pass("verify_all_blockers accepts good BLOCKER")
