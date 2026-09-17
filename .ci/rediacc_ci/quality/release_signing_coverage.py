"""Every release package format is SIGNED, or is declared unsigned on purpose.

Ported from `.ci/scripts/quality/check-release-signing-coverage.sh`, which is not deleted; see `rediacc_ci.quality.__init__` for why both copies live.

WHY THE TWIN EXISTS, carried over from its own header because the incident IS the specification. On 2026-09-05 a deb shipped UNSIGNED and green: the signing
setup was guarded by `[[ -n "${RELEASE_GPG_PRIVATE_KEY:-}" ]]`, the org secret
behind it had been deleted, and an empty value is indistinguishable from "no signing wanted". That was fixed for deb and rpm. A class sweep the next day found the SAME shape one branch over in apk, which had shipped unsigned for the same reason and was fixed reactively too.

Fixing formats one at a time as they are noticed is the actual defect. This gate asks the structural question instead: `build-linux-pkg.sh` accepts N formats, and EACH one must either refuse to ship unsigned when the caller demands signing, or appear in `UNSIGNED_ON_PURPOSE` below as a deliberate, reasoned exception. A fifth format added tomorrow fails here before it can ship
unsigned.

WHAT IT CANNOT DO, unchanged by the port: it does not verify a real signature on a real artifact. That needs the release key, which is a secret and is deliberately not available to a quality job. It checks that the REFUSAL exists. `check:ci-release-key-canonical` covers the key's usability, and `test-linux-packages.sh` signs real packages in CI.

EVERY EXEMPTION STATES A TESTED CONSTRAINT, not a guess, because the first archlinux reason was a guess and it was WRONG: it said "no signature block in nfpm.yaml", which reads as an omission someone could fix by adding one. Adding one fails at config load. The two constraints are different in kind and the difference was measured, not reasoned:

    archlinux  nfpm CANNOT sign it, `field signature not found in type
               nfpm.ArchLinux`
    apk        nfpm CAN sign it; only the key is absent (built both ways to
               check)

A reason that has not been run is a reason that can be wrong for months.

AND THE OBVIOUS FIX FOR archlinux IS A BREAKING CHANGE, which no amount of local testing would have shown. pacman.conf(5) defines SigLevel Optional, what Arch ships as LocalFileSigLevel, as "Signatures are checked if present; absence of a signature is not an error. An invalid signature is a fatal error, as is a signature from a key not in the keyring." So publishing a detached .sig
signed by a key no user holds converts a working `pacman -U` into a hard failure. The keyring rollout has to land BEFORE the first signed artifact, which is how Arch Linux ARM and Chaotic-AUR both do it. apk has no such trap: an unsigned .apk already needs --allow-untrusted, so signing it is strictly an improvement.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE EXEMPTION ORDER IS BASH'S HASH ORDER, MEASURED, NOT INVENTED. The twin
iterates `"${!UNSIGNED_ON_PURPOSE[@]}"` over an associative array, and bash
returns those keys in the order its hash table happens to hold them, which on GNU bash 5.3.9 is `archlinux`, then `apk` -- NOT the order the literal is written in. `UNSIGNED_ON_PURPOSE` below is a tuple in that measured order, so a human diffing the two implementations' stdout side by side sees the same four control lines in the same four places. The shadow comparator would score
either order EQUIVALENT; a reviewer would stop reading.

THE TALLY IS A LOCAL COPY OF `gate-controls.sh`, AND THAT IS DELIBERATE. `rediacc_ci.controls.Controls` counts the same things but prints a DIFFERENT contract: no two-space indent, no `✓ <subject>:` prefix on the verdict, and a different floor message ("the file is not being executed as written" versus "the battery is not being executed as written"). Those strings are the twin's
observable output, and the differential compares output, so the port reproduces `gate-controls.sh` rather than reusing the class. `GateTally` below is the wanted helper: it belongs in the package next to `Controls`, and this port is not allowed to put it there.

THE ROOT IS RESOLVED THE TWIN'S WAY, AND `$REDIACC_CI_ROOT` IS NOT CONSULTED. The twin reads `$SIGNING_COVERAGE_ROOT`, then `git rev-parse --show-toplevel`, then the literal `.`. Honouring the package-wide override as well would let one environment point the two implementations at two different trees while a reviewer read one verdict, which is the exact failure
`paths.repo_root()`'s docstring warns about from the other direction. One name, the twin's.

THE PARSE IS THE GATE'S BLIND SPOT, AND IT IS PRESERVED. `formats_of` reads the FIRST line in the builder that looks like `<lowercase names>) ;;` and treats it as the validation case. That is a positional assumption: a builder that grew an earlier one-line case arm would have its format list read from the wrong place. The twin's floor (`MIN_FORMATS`) catches the collapse-to-nothing
case and not this one. Carried unchanged, because widening it would change the verdict.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci.controls import Controls, plant

# The POSIX space class, written out. `\s` on a Python str additionally matches U+00A0, U+2028 and friends, so a builder line indented with a non-breaking space would be seen by the port and not by sed or awk. See the same note in `rediacc_ci.quality.npmrc`, where it was written first.
SPACE = r"[ \t\n\v\f\r]"

# The builder, relative to the root. `$SIGNING_COVERAGE_BUILDER` overrides it, which is how the twin's own controls point it at a scratch copy.
BUILDER_REL = ".ci/scripts/build/build-linux-pkg.sh"

# Formats that ship UNSIGNED on purpose, in bash's measured hash order. Each needs a reason, and the gate refuses an entry whose format IS guarded, so an exemption cannot outlive its cause.
#
# The reasons are carried BYTE FOR BYTE from the twin. They are long, they name an upstream issue and a manual page, and shortening them is how the archlinux reason became wrong the first time.
UNSIGNED_ON_PURPOSE: tuple[tuple[str, str], ...] = (
    (
        "archlinux",
        (
            "TWO reasons, and the second is the one that matters. (1) nfpm CANNOT sign archlinux: "
            "a signature block fails at config load with 'field signature not found in type "
            "nfpm.ArchLinux'; upstream goreleaser/nfpm#628 is open and PR #1065 unmerged. "
            "(2) Publishing a .sig would BREAK existing users: pacman.conf(5) says under SigLevel "
            "Optional -- what Arch ships as LocalFileSigLevel -- that 'a signature from a key not "
            "in the keyring' is a FATAL error, so a sidecar .sig signed by a key nobody has turns "
            "a working pacman -U into a hard failure. Signing archlinux needs a keyring rollout "
            "FIRST"
        ),
    ),
    (
        "apk",
        (
            "the KEY is missing, not the capability -- VERIFIED 2026-09-06 by building both ways: "
            "with an RSA key the apk carries a .SIGN.RSA.*.rsa.pub entry, without one it carries "
            "none. APK_RSA_PRIVATE_KEY is set by nothing here and is absent from "
            ".ci/config/bws-secret-map.json, so nfpm.yaml's apk signature block reads an env var "
            "never populated. Mint an RSA key and this exemption goes"
        ),
    ),
)

# ANTI-VACUITY FLOOR. A sed that stopped matching would yield an empty format list, and a loop over nothing passes. The builder documents four formats; a floor at four catches a broken parse without firing on an addition.
MIN_FORMATS = 4

# The control floor handed to `gate_finish`. Four formats plus two exemptions times two controls each, plus the parse control, is nine today; six is the twin's number and is carried unchanged rather than tightened, because a floor that tracks the current count fires on every legitimate addition.
MIN_CONTROLS = 6

# The subject line the verdict names.
SUBJECT = "release signing coverage"

# A reason shorter than this is not a reason. The twin's `-gt 30`.
MIN_REASON_LEN = 30

# The validation case arm: ` deb | rpm | apk | archlinux) ;;`. BRE `^[[:space:]]*\([a-z |]*\))[[:space:]]*;;[[:space:]]*$` with the class spelled out. Only lowercase letters, spaces and pipes are inside the group, which is what stops it matching an arm whose pattern contains a glob or a variable.
_CASE_ONELINE = re.compile(r"^%s*([a-z |]*)\)%s*;;%s*$" % (SPACE, SPACE, SPACE))

# A multi-line case arm header: ` rpm | deb)` with nothing after it. The awk program requires a leading `[a-z]`, so `) ;;`-style continuations and the `*)` default arm are both excluded.
_ARM_HEADER = re.compile(r"^%s*[a-z][a-z |]*\)%s*$" % (SPACE, SPACE))

# The end of a case arm body.
_ARM_END = re.compile(r"^%s*;;%s*$" % (SPACE, SPACE))

# `sub(/\)[[:space:]]*$/, "", arm)` -- the trailing paren and any space after it.
_ARM_TAIL = re.compile(r"\)%s*$" % SPACE)


def formats_of(text: str) -> list[str]:
    """The formats the builder ACCEPTS, read from its own validation case.

    Read from the builder rather than duplicated here: a list that can drift is a list that will. The pipeline is four shell stages and is reproduced stage by stage, because each one has an edge a "sensible" rewrite loses:

        sed -n 's/^\\s*\\([a-z |]*\\))\\s*;;\\s*$/\\1/p'  every matching line
        head -1                                         the FIRST one only
        tr -d ' '                                       delete SPACES, not tabs
        tr '|' '\\n'                                     split on the pipe
        grep -v '^$'                                    drop empties

    `tr -d ' '` is the stage worth naming: it deletes the space character and nothing else, so a tab between two format names would survive into the format name itself and the gate would look for a format called `deb\\trpm`. That is the twin's behaviour and it is preserved rather than tidied.
    """
    for line in text.split("\n"):
        match = _CASE_ONELINE.match(line)
        if match is None:
            continue
        # head -1: the FIRST matching line wins and the rest are never read.
        body = match.group(1).replace(" ", "")
        return [part for part in body.split("|") if part != ""]
    return []


def guarded_in(fmt: str, text: str) -> str:
    """Does `fmt`'s OWN case arm contain the signing guard? "yes" or "no".

    Returned as the twin's two strings rather than as a bool, because those strings are what the control compares and what a failure prints.

    READING "IS RELEASE_SIGNING_REQUIRED ANYWHERE AFTER THE ARM" IS WHAT THE FIRST DRAFT DID, and it was wrong in BOTH directions: the guard sits INSIDE the arm, so the arm line is read before anything arms, and a later arm inherits an earlier arm's guard. The scan is scoped to the arm body, `<formats>)` through `;;`.
    """
    inarm = False
    found = False
    for line in text.split("\n"):
        if _ARM_HEADER.match(line):
            arm = _ARM_TAIL.sub("", line, count=1)
            arm = re.sub(SPACE, "", arm)
            inarm = fmt in arm.split("|")
            continue
        if _ARM_END.match(line):
            inarm = False
            continue
        if inarm and "RELEASE_SIGNING_REQUIRED" in line:
            found = True
    return "yes" if found else "no"


class GateTally:
    """`.ci/scripts/lib/gate-controls.sh`, reproduced byte for byte.

    Extracted in bash on 2026-09-06 after `check:ci-shape-duplication` caught the same five lines at three copies (check-release-key-canonical, check-release-signing-coverage, check-staging-tag-guard) and was right to. This class is the fourth copy and it is here under protest: see the port notes for why `rediacc_ci.controls.Controls` cannot be used instead, and treat this as the
    request for a `GateTally` beside it.

    THE OUTPUT CONTRACT, which is the whole reason it is a copy:

        stdout per pass       "  ok    <label>"
        stderr per failure    "  FAIL  <label> (got '<got>' want '<want>')"
        stderr under floor    "FAIL  only <N> control(s) ran; the battery is
                               not being executed as written"
        stderr on failure     "✗ <subject>: <F> of <N> control(s) failed"
        stdout on success     "✓ <subject>: <N> control(s) passed"

    The floor message is deliberately NOT the one in `controls.py`. "the battery is not being executed as written" is the phrase the shadow comparator's refusal vocabulary matches, so changing a word here changes how a differential classifies the run.
    """

    def __init__(self) -> None:
        self.fails = 0
        self.count = 0

    def check(self, label: str, got: object, want: object) -> None:
        """`gate_check`. Compares STRINGS, as `[[ "$2" == "$3" ]]` does."""
        self.count += 1
        if str(got) == str(want):
            print("  ok    %s" % label)
        else:
            self.fails += 1
            print("  FAIL  %s (got '%s' want '%s')" % (label, got, want), file=sys.stderr)

    def finish(self, minimum: int, subject: str) -> bool:
        """`gate_finish`. True when green.

        A battery that did not run is not a green one, which is why the floor is here and not left to each caller to remember.
        """
        if self.count < minimum:
            print(
                "FAIL  only %d control(s) ran; the battery is not being executed as written"
                % self.count,
                file=sys.stderr,
            )
            self.fails += 1
        if self.fails:
            print(
                "✗ %s: %d of %d control(s) failed" % (subject, self.fails, self.count),
                file=sys.stderr,
            )
            return False
        print("✓ %s: %d control(s) passed" % (subject, self.count))
        return True


def resolve_root() -> str:
    """`${SIGNING_COVERAGE_ROOT:-$(git rev-parse --show-toplevel || echo .)}`.

    Three rungs, the twin's, and `$REDIACC_CI_ROOT` is not one of them. See the port notes: an environment that pointed the two implementations at two different trees would produce a differential nobody could interpret.
    """
    override = os.environ.get("SIGNING_COVERAGE_ROOT")
    if override:
        return override
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        # `git` absent behaves as `git` failing: the twin's `2>/dev/null ||` swallows both, and a port that raised here would turn a fallback into a stack trace.
        return "."
    top = proc.stdout.strip()
    return top if proc.returncode == 0 and top else "."


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 violation.

    `--selftest` is intercepted BEFORE any real scan. The twin takes no arguments at all, so no caller can be passing this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = resolve_root()
    builder = os.environ.get("SIGNING_COVERAGE_BUILDER") or os.path.join(root, BUILDER_REL)

    # THE ABSENT BUILDER IS A REFUSAL, NOT AN ABSTENTION. A gate whose subject is missing has verified nothing, and the twin says so in one line that is deliberately not a log_error: plain `echo ... >&2`, no colour helper, so the port prints it the same way.
    if not os.path.isfile(builder):
        print("✗ %s not found -- nothing was verified" % builder, file=sys.stderr)
        return 1

    text = pathlib.Path(builder).read_text(encoding="utf-8", errors="replace")
    formats = formats_of(text)

    tally = GateTally()
    exempt = dict(UNSIGNED_ON_PURPOSE)

    # ANTI-VACUITY, recorded as a CONTROL first and then acted on. Recording it as a control matters: a run that dies at the floor still prints a tally line, so the reader can see the gate reached this point.
    tally.check("the builder's format list parses", 1 if len(formats) >= MIN_FORMATS else 0, 1)
    if len(formats) < MIN_FORMATS:
        print(
            "✗ VACUOUS: parsed %d format(s) from %s, floor is %d."
            % (len(formats), builder, MIN_FORMATS),
            file=sys.stderr,
        )
        print(
            "  The validation case did not parse, so this gate verified nothing.", file=sys.stderr
        )
        return 1

    for fmt in formats:
        guard = guarded_in(fmt, text)
        if exempt.get(fmt):
            # A stale exemption is worse than none: it hides a format that got fixed, and it does it while looking like coverage.
            tally.check(
                "CONTROL: exemption for '%s' still describes an UNguarded format" % fmt,
                guard,
                "no",
            )
        else:
            tally.check(
                "'%s' refuses to ship unsigned when signing is required" % fmt, guard, "yes"
            )

    # Every exemption must name a format the builder actually accepts, or it excuses nothing and sits forever looking like coverage.
    for fmt, reason in UNSIGNED_ON_PURPOSE:
        hit = "yes" if fmt in formats else "no"
        tally.check("exemption '%s' names a real format" % fmt, hit, "yes")
        tally.check(
            "exemption '%s' carries a reason" % fmt,
            "yes" if len(reason) > MIN_REASON_LEN else "no",
            "yes",
        )

    if not tally.finish(MIN_CONTROLS, SUBJECT):
        print(
            "  A format that neither refuses nor is declared unsigned ships unverified.",
            file=sys.stderr,
        )
        return 1

    # PRINT THE SHAPE, NOT JUST THE VERDICT. Two numbers that a reader can watch collapse; "OK" cannot be watched.
    print("  (%d format(s), %d declared unsigned)" % (len(formats), len(UNSIGNED_ON_PURPOSE)))
    return 0


# A builder whose validation case lists the four real formats and whose deb/rpm arm carries the guard. The base every plant below mutates, and asserted CLEAN first: without that, each plant would "fire" against a fixture that was already failing and the suite would be green while testing nothing.
_CLEAN_BUILDER = """#!/usr/bin/env bash
case "$FORMAT" in
    deb | rpm | apk | archlinux) ;;
    *)
        echo "unknown format" >&2
        exit 1
        ;;
esac

case "$FORMAT" in
    rpm | deb)
        if [[ "${RELEASE_SIGNING_REQUIRED:-0}" == "1" ]]; then
            echo "refusing to ship an UNSIGNED $FORMAT" >&2
            exit 1
        fi
        ;;
    apk)
        echo "APK_RSA_PRIVATE_KEY not set, skipping APK signing"
        ;;
    archlinux)
        echo "nfpm cannot sign archlinux"
        ;;
esac
"""


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    BOTH DIRECTIONS FOR EVERY CONTROL. A gate with only positive plants will happily flag a correct builder, and the mirrors below are the half that proves it does not.
    """
    ctl = Controls("release-signing-coverage", floor=20, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        builder = root / "build-linux-pkg.sh"

        def run(content: str | None) -> int:
            """Point the gate at a builder holding `content`, or at nothing."""
            if content is None:
                if builder.exists():
                    builder.unlink()
            else:
                builder.write_text(content, encoding="utf-8")
            saved = os.environ.get("SIGNING_COVERAGE_BUILDER")
            os.environ["SIGNING_COVERAGE_BUILDER"] = str(builder)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ["SIGNING_COVERAGE_BUILDER"]
                else:
                    os.environ["SIGNING_COVERAGE_BUILDER"] = saved

        ctl.check("CONTROL: the reference builder passes", run(_CLEAN_BUILDER), 0)

        # THE VACUITY CASES. A missing subject and an empty subject are both refusals, never clean verdicts.
        ctl.check("VACUITY: an absent builder is refused", run(None), 1)
        ctl.check("VACUITY: an EMPTY builder is refused", run(""), 1)
        ctl.check(
            "VACUITY: a builder with no validation case is refused",
            run("#!/usr/bin/env bash\necho hi\n"),
            1,
        )
        ctl.check(
            "VACUITY: three formats is below the floor of %d" % MIN_FORMATS,
            run(plant(_CLEAN_BUILDER, "deb | rpm | apk | archlinux)", "deb | rpm | apk)")),
            1,
        )

        # PLANT 1: a format that neither refuses nor is exempt. This is the 2026-09-05 shape itself, one format over.
        ctl.check(
            "PLANT: an unguarded, unexempt format is caught",
            run(plant(_CLEAN_BUILDER, "rpm | deb)", "rpm)")),
            1,
        )
        # PLANT 2: a fifth format added with no guard and no exemption.
        ctl.check(
            "PLANT: a NEW format added with no guard is caught",
            run(
                plant(
                    _CLEAN_BUILDER,
                    "deb | rpm | apk | archlinux)",
                    "deb | rpm | apk | archlinux | snap)",
                )
            ),
            1,
        )
        # PLANT 3: a stale exemption. archlinux grows the guard, so the exemption now describes a format that got fixed, and the CONTROL line must fire rather than quietly bless it.
        ctl.check(
            "PLANT: an exemption that outlived its cause is caught",
            run(
                plant(
                    _CLEAN_BUILDER,
                    '        echo "nfpm cannot sign archlinux"',
                    '        if [[ "${RELEASE_SIGNING_REQUIRED:-0}" == "1" ]]; then exit 1; fi',
                )
            ),
            1,
        )
        # PLANT 4: the exemption names a format the builder does not accept.
        ctl.check(
            "PLANT: an exemption naming no real format is caught",
            run(
                plant(
                    _CLEAN_BUILDER, "deb | rpm | apk | archlinux)", "deb | rpm | apk | rpmv4 | msi)"
                )
            ),
            1,
        )

        # MIRRORS. Each is a shape that must stay GREEN, and each is a direction a "tidier" rewrite of the parser would invert.
        ctl.check(
            "MIRROR: extra spacing in the validation case still parses",
            run(plant(_CLEAN_BUILDER, "deb | rpm | apk | archlinux)", "deb|rpm|apk|archlinux)")),
            0,
        )
        ctl.check(
            "MIRROR: an unrelated later one-line arm does not steal the parse",
            run(_CLEAN_BUILDER + '\ncase "$X" in\n    zip | tar) ;;\nesac\n'),
            0,
        )

    # -- the pure helpers, driven directly ---------------------------------
    #
    # The end-to-end cases above cannot distinguish "the parser is right" from "the parser is wrong in a way the controls happen not to see", so the two functions that decide everything are exercised on their own.

    ctl.check(
        "formats_of: the reference builder",
        formats_of(_CLEAN_BUILDER),
        ["deb", "rpm", "apk", "archlinux"],
    )
    ctl.check("formats_of: no case at all is EMPTY, not a guess", formats_of("echo hi\n"), [])
    ctl.check(
        "formats_of: head -1 -- the FIRST matching arm wins",
        formats_of("    a | b) ;;\n    c | d) ;;\n"),
        ["a", "b"],
    )
    ctl.check(
        "formats_of: an empty group yields no formats, not one empty name",
        formats_of("    ) ;;\n"),
        [],
    )
    ctl.check(
        "guarded_in: the guard inside deb's own arm counts",
        guarded_in("deb", _CLEAN_BUILDER),
        "yes",
    )
    ctl.check(
        "guarded_in: apk's arm has no guard",
        guarded_in("apk", _CLEAN_BUILDER),
        "no",
    )
    ctl.check(
        "guarded_in: a format the builder never mentions is not guarded",
        guarded_in("snap", _CLEAN_BUILDER),
        "no",
    )
    # THE TWO DIRECTIONS THE FIRST DRAFT GOT WRONG, both pinned here.
    ctl.check(
        "guarded_in: a LATER arm does not inherit an earlier arm's guard",
        guarded_in(
            "apk",
            "    deb)\n        RELEASE_SIGNING_REQUIRED=1\n        ;;\n    apk)\n        :\n        ;;\n",
        ),
        "no",
    )
    ctl.check(
        "guarded_in: the guard AFTER the esac belongs to nobody",
        guarded_in("apk", "    apk)\n        :\n        ;;\nesac\nRELEASE_SIGNING_REQUIRED=1\n"),
        "no",
    )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
