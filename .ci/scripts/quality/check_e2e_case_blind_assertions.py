#!/usr/bin/env python3
"""An e2e assertion must not compare an uppercase literal against lowercased output.

WHY THIS EXISTS. `TestHelpers.getCombinedOutput()` returns
`(result.stdout + result.stderr).toLowerCase()`. Any matcher fed from it that
expects a capital letter can NEVER match, whatever the machine did. That is not
a flaky test, it is a test with a dead arm: it reports the product broken while
the product is fine, and no amount of re-running changes it.

WHAT IT COST. Four of these shipped in one wave and each one burned a full CI
round on a matrix of five distros:
    /No such file|total 0/    the "No such file" arm was dead; an absent
                              anchor directory -- the CORRECT outcome -- read
                              as a failure
    toContain('ABSENT')       compared against `echo ABSENT`, lowercased
    toContain('2026-01-01T00:00:00Z')
                              RFC3339 carries a capital T and Z; the engine
                              quoted the timestamp back correctly and the
                              assertion failed anyway

WHY A GATE RATHER THAN A SWEEP, which is the whole point. The first three were
found by a hand-written grep that reported the population as "exactly 3". It was
wrong: the grep only examined the FIRST matcher after each getCombinedOutput()
call, so the ordinary idiom

    const text = runner.getCombinedOutput(result);
    expect(text).toContain('...');     <- seen
    expect(text).toContain('...');     <- invisible

hid every assertion after the first, and the fourth instance was found by CI
instead. A confident wrong number from a hand sweep is exactly the failure this
repo keeps paying for, so the sweep is an instrument now.

WHAT IT DOES NOT COVER, stated plainly. It resolves subjects one hop: an inline
getCombinedOutput() call, or a local const bound directly to one. A subject
passed through a helper, or reassigned, is not tracked. It also cannot know that
some OTHER helper lowercases; it is specifically about this one.
"""

import pathlib
import re
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[3]
TESTS = REPO / "packages" / "e2e-tests" / "tests"
HELPER = REPO / "packages" / "e2e-tests" / "src" / "utils" / "bridge" / "helpers" / "TestHelpers.ts"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

ASSERT = re.compile(
    r"expect\(\s*([^,)]+(?:\([^()]*\))?[^,)]*)\s*(?:,[\s\S]*?)?\)\s*\.\s*"
    r"(?:not\s*\.\s*)?(?:toContain|toMatch|toEqual)\(\s*([\s\S]*?)\)\s*;",
    re.MULTILINE,
)
BIND = re.compile(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*[^;]*getCombinedOutput\s*\(")


def uppercase_in_literal(expected: str) -> bool:
    """True when the EXPECTED value carries a capital that can never be matched.

    Only string literals and case-SENSITIVE regex bodies count. An identifier is
    not inspected (its value is unknown here), a regex carrying /i is fine by
    construction, and escapes like \\D are character classes rather than letters
    -- treating those as findings made the first draft cry wolf on four healthy
    assertions.
    """
    for lit in re.findall(r"'([^']*)'|\"([^\"]*)\"|`([^`]*)`", expected):
        if re.search(r"[A-Z]", "".join(lit)):
            return True
    m = re.search(r"/((?:[^/\\\n]|\\.)+)/([gimsuy]*)", expected)
    return bool(
        m
        and "i" not in m.group(2)
        and re.search(r"[A-Z]", re.sub(r"\\[dDwWsSbBnrtAZ]", "", m.group(1)))
    )


def scan(files):
    """Returns (findings, assertions_examined)."""
    findings = []
    examined = 0
    for path in files:
        try:
            src = path.read_text(errors="replace")
        except OSError:
            continue
        bound = set(BIND.findall(src))
        for m in ASSERT.finditer(src):
            subject, expected = m.group(1).strip(), m.group(2)
            root = subject.split(".")[0].split("(")[0].strip()
            if "getCombinedOutput" not in subject and root not in bound:
                continue
            examined += 1
            if uppercase_in_literal(expected):
                findings.append(
                    (path, src[: m.start()].count("\n") + 1, " ".join(expected.split())[:70])
                )
    return findings, examined


def run_controls():
    """Prove the rule fires on each dead shape and stays quiet on each live one."""
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        planted = pathlib.Path(tmp) / "planted.test.ts"
        planted.write_text(
            "const a = runner.getCombinedOutput(r);\n"
            "expect(a).toContain('FIRE_bound_literal');\n"
            "expect(a).toMatch(/FireBoundRegex/);\n"
            "expect(a, 'msg').toContain('FIRE_with_message');\n"
            "expect(runner.getCombinedOutput(r)).toContain('FIRE_inline');\n"
            "expect(a).toMatch(/quiet_flagged/i);\n"
            "expect(a).toContain('quiet_lower');\n"
            "expect(a).toMatch(/(^|\\D)0(\\D|$)/);\n"
            "expect(other).toContain('QUIET_NOT_LOWERCASED_SUBJECT');\n"
        )
        found, examined = scan([planted])
        got = {f[2] for f in found}
        wanted = (
            "'FIRE_bound_literal'",
            "/FireBoundRegex/",
            "'FIRE_with_message'",
            "'FIRE_inline'",
        )
        failures.extend(f"a dead assertion was not flagged: {w}" for w in wanted if w not in got)
        never = ("quiet_flagged", "quiet_lower", "\\D", "QUIET_NOT_LOWERCASED")
        failures.extend(
            f"a healthy assertion was flagged: {n}" for n in never if any(n in g for g in got)
        )
        # 7, not 8: the QUIET_NOT_LOWERCASED_SUBJECT line is deliberately bound
        # to a subject this rule does not track, so it must NOT be resolved.
        if examined != 7:
            failures.append(
                f"resolved {examined} lowercased-subject assertions, expected exactly 7"
            )

    # The rule is a claim ABOUT a helper. If that helper stops lowercasing, this
    # gate is enforcing a rule that no longer exists, and every finding it
    # produces is noise. Fail loudly rather than police a vanished contract.
    try:
        if ".toLowerCase()" not in HELPER.read_text(errors="replace"):
            failures.append(
                f"{HELPER.name} no longer lowercases; this gate's premise is gone -- delete it"
            )
    except OSError:
        failures.append(f"cannot read {HELPER}; the gate's premise is unverifiable")
    return failures


def main() -> int:
    print("e2e assertions: can each one actually match the lowercased output?")
    print("=" * 66)

    control_failures = run_controls()
    if control_failures:
        for f in control_failures:
            print(f"{RED}x{NC} control: {f}")
        print(f"{RED}x{NC} the rule itself is broken, so no verdict it produces means anything.")
        return 1
    print(f"{GREEN}v{NC} control fired: 4 dead shapes caught, 4 healthy ones left alone")

    files = sorted(TESTS.rglob("*.ts"))
    if not files:
        print(
            f"{RED}x{NC} no e2e test files found; checking nothing exits 0 exactly like checking everything"
        )
        return 1

    findings, examined = scan(files)

    # A rule that resolved no assertion passes forever.
    if examined < 20:
        print(
            f"{RED}x{NC} only {examined} assertion(s) resolved across {len(files)} file(s); the rule has been unhooked"
        )
        return 1

    if findings:
        for path, line, expected in findings:
            rel = path.relative_to(REPO) if path.is_relative_to(REPO) else path
            print(f"{RED}x{NC} {rel}:{line}: expects {expected}")
        print()
        print(
            f"{RED}x{NC} {len(findings)} assertion(s) compare an uppercase literal against lowercased output."
        )
        print("  getCombinedOutput() returns (stdout + stderr).toLowerCase(), so these can never")
        print("  match and will report the product broken while it is behaving correctly. Add an")
        print("  /i flag, lowercase the expected literal, or assert on result.stdout directly.")
        return 1

    print(
        f"{GREEN}v{NC} {examined} assertion(s) across {len(files)} file(s): every expected value is reachable"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
