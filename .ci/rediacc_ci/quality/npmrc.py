"""`.npmrc` supply-chain hardening, enforced in BOTH directions.

Ported from `.ci/scripts/quality/check-npmrc.sh`, which W7 P5 batch C1 retired once `.ci/shadow/w7p2-npmrc.observations.jsonl` asserted equivalence over five distinct trees.

WHAT THE TWIN ENFORCES, carried over from its own header verbatim because the list IS the gate and a summary of it would be a different gate:

  Forbidden  -- settings that hide dependency problems
      legacy-peer-deps : silently ignores peer dependency conflicts
      force            : forces installation despite errors
  Required   -- supply-chain defenses (see /workspace/console/.npmrc for rationale)
      ignore-scripts=true           : blocks dependency lifecycle scripts
      allow-git=none                : rejects git+/github:/tarball deps (PackageGate)
      minimum-release-age=1440      : 24h cooldown (Axios-style smash-and-grab)

The live `.npmrc` header expands each of those: `ignore-scripts` blocks every lifecycle script at install time and the natives are rebuilt by an explicit
`npm rebuild` afterwards; `allow-git=none` defends against PackageGate-style
git-dep RCE (Koi Security, Jan 2026) where a hijacked `.npmrc` inside a git
dependency redirects the git binary; `minimum-release-age=1440` is a 24h
freshness window motivated by smash-and-grab supply-chain attacks (the Axios 1.14.1 RAT, live roughly 4h, March 2026), read by this repo's own dependency gates and NOT by npm, whose real key is `min-release-age` in DAYS.

THE GATE HEADER CARRIES A BLOCKER, and it is about WIRING rather than about .npmrc, so it stays with the bash file rather than moving here: the step "runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails." That reason is still true, and
it is the reason `emit: false` sits in the twin's gate block. A port does not inherit a registration, so nothing here re-states it as a live suppression.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE REQUIRED-KEY ORDER IS BASH'S HASH ORDER, MEASURED, NOT INVENTED. The twin
iterates `"${!required[@]}"` over an associative array, and bash returns those
keys in the order its hash table happens to hold them, which on GNU bash 5.3.9 is `allow-git`, `minimum-release-age`, `ignore-scripts` -- NOT the order they are written in the literal. `REQUIRED` below is a tuple in that measured order.

Why bother, when `scripts/lib/shadow-gate.ts` compares findings as an unordered multiset and would score either order EQUIVALENT: because a human diffing the two implementations' stderr side by side is the cheapest review this port will ever get, and an ordering difference is the kind of noise that makes a reviewer stop reading. It costs one tuple and a comment.

THE VALUE PIPELINE IS FOUR SHELL STAGES AND IS REPRODUCED STAGE BY STAGE, since each one has an edge that a "sensible" rewrite loses:

    grep -E "^[[:space:]]*KEY[[:space:]]*="   every matching line, CASE SENSITIVE
    tail -n1                                  the LAST wins, so a later line overrides
    sed -E "s/^...=[[:space:]]*//; s/[[:space:]]*#.*//"   strip key, then a trailing comment
    tr -d '[:space:]'                         delete ALL remaining whitespace, inner included

The twin's own comment explains stage three: "Strip optional trailing comments (everything from the first # onward) before trimming whitespace so a line like
'ignore-scripts=true # hardening' parses cleanly to 'true' instead of
'true#hardening'."

TWO CONSEQUENCES WORTH NAMING because they look like bugs and are behaviour:

  * `ignore-scripts=` (present, empty) is reported as MISSING, not as a wrong
    value, because the empty string is what "no matching line" also produces.
    A port that distinguished them would emit a finding the twin never emits.
  * `ignore-scripts=#x` also reduces to empty and is therefore MISSING.

CASE SENSITIVITY DIFFERS BETWEEN THE TWO HALVES OF THIS GATE, and that is the twin's behaviour, not a slip in the port: the forbidden scan is `grep -qiE`
(case INsensitive, so `Force=true` is caught) and the required scan is `grep -E`
(case sensitive, so `Ignore-Scripts=true` does NOT satisfy `ignore-scripts`).
npm's own config keys are case sensitive, so the required half is right and the forbidden half is merely generous. Both are carried unchanged.

`[[:space:]]` IS NOT `\\s`. POSIX space is exactly [ \\t\\n\\v\\f\\r]; Python's `\\s` on a str pattern additionally matches U+00A0, U+2028 and friends, so a `.npmrc` line indented with a non-breaking space would be seen by the port and not by grep. The character class is written out rather than abbreviated.

WHAT THIS GATE STILL CANNOT SEE, unchanged by the port: it reads the repo-root `.npmrc` only. A per-workspace `.npmrc`, a `~/.npmrc`, or an `NPM_CONFIG_*` environment variable overrides these settings at install time and this gate never looks. That is a real blind spot in the twin and it is preserved rather than quietly widened, because widening it would change the verdict.
"""

import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls, plant

# The file, relative to the repository root. The twin `cd`s to the root and writes a bare `.npmrc`; this is the same fact with the cd removed.
NPMRC = ".npmrc"

# POSIX [[:space:]], written out. See the port notes for why `\s` is wrong here.
SPACE = r"[ \t\n\v\f\r]"

# The forbidden settings, as ONE alternation so the compiled pattern matches the twin's `(legacy-peer-deps|force)` exactly. Case insensitive, matching `-i`.
FORBIDDEN_RE = re.compile(r"^%s*(legacy-peer-deps|force)%s*=" % (SPACE, SPACE), re.IGNORECASE)

# The required settings and their exact expected values. A TUPLE in bash's measured hash order, not a dict in source order; see the port notes.
REQUIRED: tuple[tuple[str, str], ...] = (
    ("allow-git", "none"),
    ("minimum-release-age", "1440"),
    ("ignore-scripts", "true"),
)

# The rationale pointer the twin prints on the missing-settings path. It names an absolute path from a DIFFERENT checkout (`/workspace/console`), which does not exist on this machine or in CI. Carried byte for byte because the port's job is to keep the verdict, and reported as a finding instead of quietly repaired.
RATIONALE_LINE = "See /workspace/console/.npmrc header for the rationale behind each setting."


def forbidden_matches(text: str) -> list[tuple[int, str]]:
    """Every `legacy-peer-deps=` / `force=` line, as (1-based line number, text).

    This is `grep -niE` over the file: the number and the line, with no filename prefix because grep is given exactly one file argument. The twin prints this list verbatim under a "Problematic lines:" header, so the shape is the output contract and not an internal detail.
    """
    out: list[tuple[int, str]] = []
    for index, line in enumerate(text.split("\n"), start=1):
        if FORBIDDEN_RE.match(line):
            out.append((index, line))
    # grep's last "line" after a trailing newline is not a line. `split` produces a final empty string for a file ending in \n, and the empty string cannot
    # match a pattern that requires `=`, so no guard is needed -- stated because
    # the absence of one looks like an oversight.
    return out


def setting_value(text: str, key: str) -> str:
    """The effective value of `key`, through the twin's four-stage pipeline.

    Returns "" for both "no such line" and "the line reduces to nothing", which the twin treats identically as MISSING. See the port notes.
    """
    pattern = re.compile(r"^%s*%s%s*=" % (SPACE, re.escape(key), SPACE))
    matches = [line for line in text.split("\n") if pattern.match(line)]
    if not matches:
        return ""
    # tail -n1: a later line wins, which is npm's own last-one-wins semantics.
    last = matches[-1]
    # sed stage 1: strip the key and the `=` and any space after it.
    stripped = re.sub(r"^%s*%s%s*=%s*" % (SPACE, re.escape(key), SPACE, SPACE), "", last)
    # sed stage 2: strip a trailing comment, from optional space before the `#`.
    stripped = re.sub(r"%s*#.*" % SPACE, "", stripped)
    # tr -d: delete EVERY remaining space character, inner ones included, so `true false` becomes `truefalse` and is reported as a wrong value.
    return re.sub(SPACE, "", stripped)


def audit(text: str) -> list[str]:
    """The required-settings findings for `.npmrc` content. Empty means clean.

    Returned as a list rather than printed so a test can assert on the decision without capturing a stream, which is the whole reason the ports expose their helpers (see `rediacc_ci.quality.__init__`).
    """
    findings: list[str] = []
    for key, expected in REQUIRED:
        actual = setting_value(text, key)
        if actual == "":
            findings.append(".npmrc is missing required setting: %s=%s" % (key, expected))
        elif actual != expected:
            findings.append(".npmrc has %s=%s, expected %s=%s" % (key, actual, key, expected))
    return findings


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 violation.

    `--selftest` is intercepted BEFORE any real scan, which is the addition the twin does not have. The twin takes no arguments at all, so no caller can be passing this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    npmrc = root / NPMRC

    log.step("Checking .npmrc for supply-chain hardening settings...")

    # THE ABSENT FILE IS A FAILURE, NOT AN ABSTENTION. A gate whose subject is missing has verified nothing, and the twin says so in four lines that double as the fix, so they are carried as four lines rather than folded into one paragraph.
    if not npmrc.is_file():
        log.error(".npmrc is missing")
        log.error("Supply-chain hardening requires .npmrc at the repo root with:")
        log.error("  ignore-scripts=true")
        log.error("  allow-git=none")
        log.error("  minimum-release-age=1440")
        return 1

    text = npmrc.read_text(encoding="utf-8", errors="replace")

    problems = forbidden_matches(text)
    if problems:
        log.error(".npmrc contains legacy-peer-deps or force=true")
        log.error("These settings hide dependency problems that should be fixed properly.")
        # STDOUT, deliberately. The twin uses bare `echo` for these three, not log_error, so they land on stdout while the two lines above land on stderr. `rediacc_ci.log` refuses to write messages to stdout, which is correct for messages; this is DATA the twin prints for copy-paste, so it goes through print() and the split is preserved.
        print()
        print("Problematic lines:")
        for number, line in problems:
            print("%d:%s" % (number, line))
        return 1

    findings = audit(text)
    if findings:
        for finding in findings:
            log.error(finding)
        print()
        print(RATIONALE_LINE)
        return 1

    log.info(".npmrc is clean and hardened")
    return 0


# A `.npmrc` that satisfies every rule. The base every plant below mutates, and asserted to be CLEAN first: without that, each plant would "fire" against a fixture that was already failing and the suite would be green while testing nothing.
_CLEAN = "ignore-scripts=true\nallow-git=none\nminimum-release-age=1440\n"


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    BOTH DIRECTIONS FOR EVERY CONTROL. A gate with only positive plants will happily flag a correct file, and the mirrors below (a trailing comment, a later line overriding an earlier one, exactly the three required keys) are the half that proves it does not.
    """
    ctl = Controls("npmrc", floor=18, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        def run(content: str | None) -> int:
            """Point the gate at a fixture root holding `content`, or nothing."""
            target = root / NPMRC
            if content is None:
                if target.exists():
                    target.unlink()
            else:
                target.write_text(content, encoding="utf-8")
            # REDIACC_CI_ROOT is the package-wide override named once in rediacc_ci.paths. Set through the mapping the module reads rather than through a private seam invented for the test.
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved

        ctl.check("CONTROL: a hardened .npmrc passes", run(_CLEAN), 0)

        # THE VACUITY CASE. No file at all must be a refusal, never a clean verdict: a gate whose subject is absent has checked nothing.
        ctl.check("VACUITY: an absent .npmrc is refused", run(None), 1)
        ctl.check("VACUITY: an EMPTY .npmrc is refused", run(""), 1)

        # PLANT 1: the forbidden half, in both spellings and both cases.
        ctl.check("PLANT: legacy-peer-deps is caught", run(_CLEAN + "legacy-peer-deps=true\n"), 1)
        ctl.check("PLANT: force is caught", run(_CLEAN + "force=true\n"), 1)
        ctl.check(
            "PLANT: the forbidden scan is case INsensitive",
            run(_CLEAN + "Legacy-Peer-Deps=true\n"),
            1,
        )
        ctl.check(
            "PLANT: a leading-space forbidden line is caught",
            run(_CLEAN + "   force = 1\n"),
            1,
        )
        # ITS MIRROR: `force` inside a longer key is not `force`, and a commented-out line is not a setting. A gate that fired on these would be unusable.
        ctl.check("MIRROR: force-something is not force", run(_CLEAN + "force-cache=true\n"), 0)
        ctl.check("MIRROR: a commented force is not force", run(_CLEAN + "#force=true\n"), 0)

        # PLANT 2: each required key removed in turn. Three plants, because a loop that stopped checking one key looks identical to a clean file.
        for key, _expected in REQUIRED:
            without = "".join(
                line + "\n" for line in _CLEAN.strip().split("\n") if not line.startswith(key)
            )
            ctl.check("PLANT: a missing %s is caught" % key, run(without), 1)

        # PLANT 3: present but WRONG. The distinction the twin draws between "missing" and "has X, expected Y" is the whole reason it re-reads the
        # value instead of grepping for the literal `ignore-scripts=true`.
        ctl.check(
            "PLANT: a wrong value is caught",
            run(plant(_CLEAN, "minimum-release-age=1440", "minimum-release-age=60")),
            1,
        )
        # PLANT 4: present, empty. Reported as MISSING; see the port notes.
        ctl.check(
            "PLANT: an empty value is caught",
            run(plant(_CLEAN, "allow-git=none", "allow-git=")),
            1,
        )
        # PLANT 5: last-one-wins. An earlier good line does not rescue a later bad one, which is npm's own semantics and the reason for `tail -n1`.
        ctl.check(
            "PLANT: a later line overriding a good one is caught",
            run(_CLEAN + "allow-git=always\n"),
            1,
        )
        # ITS MIRROR: a later line repairing an earlier bad one passes.
        ctl.check(
            "MIRROR: a later line repairing a bad one passes",
            run("allow-git=always\n" + _CLEAN),
            0,
        )

        # PLANT 6: case. The required half is case SENSITIVE, so a capitalised key does not satisfy it. This is the direction that would silently invert if someone "unified" the two greps onto `-i`.
        ctl.check(
            "PLANT: a capitalised required key does not satisfy it",
            run(plant(_CLEAN, "ignore-scripts=true", "Ignore-Scripts=true")),
            1,
        )

        # MIRRORS on the parser itself, all of which must stay GREEN. Each one
        # is a shape the four-stage pipeline handles and a naive `split("=")`
        # would not.
        ctl.check(
            "MIRROR: a trailing comment still parses",
            run("ignore-scripts=true # hardening\nallow-git=none\nminimum-release-age=1440\n"),
            0,
        )
        ctl.check(
            "MIRROR: spaces around the = still parse",
            run("  ignore-scripts = true \nallow-git=none\nminimum-release-age=1440\n"),
            0,
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
