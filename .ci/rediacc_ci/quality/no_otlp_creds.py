"""No OTLP/Pyroscope credential may be baked into a built artifact.

Ported from `.ci/scripts/quality/check-no-otlp-creds.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live until a differential
ledger row exists over K distinct trees.

WHAT THE TWIN ENFORCES, carried from its own header because the list IS the gate:

    Credentials are resolved at runtime from env vars (renet) or from the
    account server's /telemetry/config endpoint (CLI). Nothing should be
    baked at build time. This check guards against regressions.

    Checks:
      1. renet `.go.buildinfo` contains no `telemetry.otlpUser` or
         `telemetry.otlpPass` ldflags.
      2. `strings <renet>` finds no long base64 sequences adjacent to the
         otlp symbol names (catches any alternative build-time injection).
      3. The CLI bundle contains no literal base64 credential assigned to
         an `Authorization: Basic ...` header at build time.

    Exits 0 on success, 1 on leak, 2 on setup error (e.g. no binaries to check).

THE `|| true` THAT WAS REMOVED, kept here word for word because it is the whole
reason check 1 is written the long way round:

    FAIL LOUDLY. This used to end in `|| true`, so a `go version -m` failure (a
    corrupt binary, a toolchain mismatch, a path that is not a Go binary at all)
    left buildinfo empty, both greps below found nothing, and this SECURITY gate
    reported the binary clean without having read a single byte of it.
    ci-build-renet.yml:130 calls this "the only place the claim is falsifiable",
    so a probe failure here has to be an error, not a pass.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE TWO SKIPS ARE WARNINGS, NOT REFUSALS, AND THAT IS THE TWIN'S DECISION. With
no renet binary and no CLI bundle this gate prints four `log_warn` lines and
exits 0, having inspected nothing. A fresh checkout is exactly that state. The
port does not "improve" it into an anti-vacuity refusal: changing a green into a
red is a different gate, and the shadow differential would score the improvement
as NEW_SIDE_NOISY, correctly. It is reported as a twin finding instead.

`go version -m` IS INVOKED, NOT REIMPLEMENTED. Parsing `.go.buildinfo` in Python
would be a second implementation of a format the Go toolchain owns, and the two
would drift the first time the format moved. The twin shells out; so does this.
A MISSING `go` IS EXIT 2 AND A LOUD MESSAGE, which is the twin's behaviour and
also the house rule: a missing tool is a failure with the fix in the message.

STDERR PASSTHROUGH KEEPS ITS INDENT. On a `go version -m` failure the twin does
`sed 's/^/    /' "$buildinfo_err" >&2` -- four spaces, raw, NOT through log_error.
That matters to `scripts/lib/shadow-gate.ts`: an indented line under a finding is
compared as part of that finding, so re-routing it through the logger would add a
`✗ ` and change the finding text. It is printed the same way here.

THE EMPTY-BUILDINFO CHECK IS `${buildinfo//[[:space:]]/}`, not `-z`. A Go binary
always reports at least its module path, so output that is only whitespace means
the probe returned nothing usable. Reproduced with an explicit POSIX space class
rather than Python's `\\s`, which additionally matches U+00A0 and U+2028 and would
therefore call a slightly different set of outputs "empty".

`strings | grep -B1 -A1 | grep -Eq` IS DECOMPOSED, ON PURPOSE. `strings` is
invoked as a subprocess because reimplementing it would change which byte runs
count as printable; the two greps are done in Python over its output. The context
window is one line either side of every `otlpUser`/`otlpPass` hit, unioned and
de-duplicated the way grep does it, and the `--` group separators grep prints are
irrelevant because they cannot match `^[A-Za-z0-9+/=]{20,}$`.

A MISSING `strings` BINARY IS SILENT IN BOTH. The twin writes `2>/dev/null` and
lets the pipeline produce nothing, so an absent `strings` turns check 2 off
without a word. Reproduced (FileNotFoundError is swallowed to an empty output)
and reported as a twin finding, because a security check that disables itself
when a tool is missing is the "unknown folded into fine" shape.

THE `find` ORDER IS READDIR ORDER IN BOTH, and is not sorted here even though
sorting would be tidier. The twin's `find -print0` hands back directory order and
prints one `inspecting <name>...` line per binary in that order. Those lines are
chatter to the comparator and the findings are compared as a multiset, so the
order is not load-bearing -- but a port that sorted would print a different
sequence to a human diffing the two side by side, which is the cheapest review
this port gets.

CASE 1 OF THE `cd`: the twin does `cd "$REPO_ROOT"` and then uses absolute paths
for everything. There is nothing left for the cd to affect, so it has no analogue
here.
"""

import os
import pathlib
import re
import shutil
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The dev build produced by `build.sh dev`, and the CI release builds produced by
# `.ci/scripts/build/build-renet.sh`. The twin checks whichever exists and says
# "it's fine to have just one".
DEV_RENET = ("private", "renet", "bin", "renet")
RELEASE_BIN_DIR = ("private", "bin")
RELEASE_PREFIX = "renet-"

# The CLI bundle. The only valid `Basic` header in it is built at runtime from
# `this.authToken` after `setRuntimeOtlpCredentials()` has been called.
CLI_BUNDLE = ("packages", "cli", "dist", "cli-bundle.cjs")

# POSIX [[:space:]], written out. `\s` on a Python str also matches U+00A0 and
# friends, which would make "is this output only whitespace" a different question.
SPACE_RE = re.compile(r"[ \t\n\v\f\r]")

# The two ldflag names, matched as `grep -q 'telemetry\.otlpUser'` does: a plain
# substring with the dot escaped, anywhere in the buildinfo.
OTLP_USER_RE = re.compile(r"telemetry\.otlpUser")
OTLP_PASS_RE = re.compile(r"telemetry\.otlpPass")

# `grep -B1 -A1 'otlpUser\|otlpPass'` -- a BRE alternation, so a plain substring
# test on either name.
OTLP_SYMBOL_RE = re.compile(r"otlpUser|otlpPass")

# `grep -Eq '^[A-Za-z0-9+/=]{20,}$'` -- a whole line of base64 alphabet, 20 or
# more characters. Anchored at both ends, so a token embedded in a longer line
# does not count; that is the twin's rule and it is what keeps this check from
# firing on ordinary Go symbol tables.
BASE64_LINE_RE = re.compile(r"^[A-Za-z0-9+/=]{20,}$")

# `grep -qE '["\x27]Basic [A-Za-z0-9+/=]{20,}["\x27]'`. `\x27` is ugrep's spelling
# of a literal apostrophe inside a single-quoted shell pattern.
BASIC_LITERAL_RE = re.compile(r"[\"']Basic [A-Za-z0-9+/=]{20,}[\"']")

# The em dash in these two lines is the TWIN'S BYTE, not authored prose, and both
# strings are compared against the twin's stdout by the shadow differential. It is
# written as an escape so this source file carries none.
NO_RENET_WARN = (
    "no renet binaries found at private/renet/bin or private/bin \u2014 skipping renet checks"
)
NO_RENET_HINT = (
    "build with ./build.sh dev or .ci/scripts/build/build-renet.sh before running this check"
)


def renet_binaries(root: pathlib.Path) -> list[pathlib.Path]:
    """Every renet binary the twin would inspect, in the twin's order.

    `private/renet/bin/renet` first when it is a regular file, then
    `find private/bin -maxdepth 1 -type f -name 'renet-*'` in readdir order. Not
    sorted; see the port notes.
    """
    found: list[pathlib.Path] = []
    dev = root.joinpath(*DEV_RENET)
    if dev.is_file():
        found.append(dev)
    release_dir = root.joinpath(*RELEASE_BIN_DIR)
    if release_dir.is_dir():
        with os.scandir(release_dir) as entries:
            # `-type f` follows the symlink and asks about the target, and
            # `-name 'renet-*'` is a glob on the BASENAME only.
            found.extend(
                pathlib.Path(entry.path)
                for entry in entries
                if entry.name.startswith(RELEASE_PREFIX) and entry.is_file()
            )
    return found


def buildinfo_findings(binary: str, buildinfo: str) -> list[str]:
    """Check 1 over one binary's `go version -m` output. Empty means clean.

    Returned as a list rather than logged in place so a test can assert on the
    decision without capturing a stream.
    """
    findings: list[str] = []
    if OTLP_USER_RE.search(buildinfo):
        findings.append("%s: .go.buildinfo contains telemetry.otlpUser ldflag" % binary)
    if OTLP_PASS_RE.search(buildinfo):
        findings.append("%s: .go.buildinfo contains telemetry.otlpPass ldflag" % binary)
    return findings


def base64_near_symbol(text: str) -> bool:
    """Check 2's decision: `grep -B1 -A1 <symbol> | grep -Eq <base64 line>`.

    `text` is `strings <binary>` output. The context window is one line either
    side of each hit, unioned and de-duplicated exactly as grep does, because
    grep merges overlapping context rather than repeating a line.
    """
    lines = text.split("\n")
    window: set[int] = set()
    for index, line in enumerate(lines):
        if OTLP_SYMBOL_RE.search(line):
            window.update((index - 1, index, index + 1))
    return any(
        0 <= index < len(lines) and BASE64_LINE_RE.match(lines[index]) for index in sorted(window)
    )


def strings_output(binary: pathlib.Path) -> str:
    """`strings <binary> 2>/dev/null`, with an absent `strings` reduced to "".

    THE SWALLOW IS THE TWIN'S, not a convenience. See the port notes: check 2
    turns itself off when the binary is missing, and that is reported as a twin
    finding rather than repaired here.
    """
    try:
        completed = subprocess.run(
            ["strings", str(binary)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="replace",
            check=False,
        )
    except (FileNotFoundError, OSError):
        return ""
    return completed.stdout or ""


def bundle_has_literal(path: pathlib.Path) -> bool:
    """Check 3's decision, streamed line by line rather than read whole.

    The bundle is 16 MB in this tree. `grep -q` reads it a buffer at a time and
    stops at the first hit; reading it into one string would work and would make
    the gate's memory footprint a function of the artifact's size.
    """
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return any(BASIC_LITERAL_RE.search(line) for line in handle)


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 clean, 1 leak, 2 setup error (no `go` to probe with).

    `--selftest` is intercepted BEFORE any real scan, which is the addition the
    twin does not have. The twin takes no arguments, so no caller passes it.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()

    log.step("Checking for leaked OTLP credentials in built artifacts...")

    errors = 0

    binaries = renet_binaries(root)
    if not binaries:
        log.warn(NO_RENET_WARN)
        log.warn(NO_RENET_HINT)
    else:
        # A MISSING TOOL IS A LOUD FAILURE WITH THE FIX IN THE MESSAGE. Exit 2 is
        # the twin's "setup error", distinct from 1 (a leak) so a caller can tell
        # "this gate could not run" from "this gate found something".
        if not _have_go():
            log.error("go is required to inspect renet binaries via 'go version -m'")
            return 2

        for binary in binaries:
            log.info("inspecting %s..." % binary.name)

            completed = subprocess.run(
                ["go", "version", "-m", str(binary)],
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
            )
            if completed.returncode != 0:
                log.error(
                    "%s: 'go version -m' failed (exit %d); cannot inspect for baked credentials"
                    % (binary, completed.returncode)
                )
                # `sed 's/^/    /' "$buildinfo_err" >&2`: raw, four spaces, NOT
                # through the logger. See the port notes.
                stderr_text = completed.stderr or ""
                # `[[ -s "$buildinfo_err" ]] && sed ... >&2`: only when the file
                # has bytes. `splitlines()` rather than `split("\n")` because sed
                # does not invent a final empty line for a trailing newline, and a
                # spurious "    " line would be an extra compared finding.
                if stderr_text:
                    for line in stderr_text.splitlines():
                        print("    %s" % line, file=sys.stderr)
                errors += 1
                continue

            buildinfo = completed.stdout or ""
            if SPACE_RE.sub("", buildinfo) == "":
                log.error(
                    "%s: 'go version -m' returned no build info; the binary was not inspected"
                    % binary
                )
                errors += 1
                continue

            for finding in buildinfo_findings(str(binary), buildinfo):
                log.error(finding)
                errors += 1

            if base64_near_symbol(strings_output(binary)):
                log.error("%s: strings shows a base64-looking token near otlp symbols" % binary)
                errors += 1

        if errors == 0:
            # The double glyph is the TWIN'S: log_info already prefixes `✓` and
            # the message text starts with another one. Carried, and reported as
            # a twin finding rather than tidied, because tidying it would change
            # a compared line.
            log.info("✓ renet binaries: no OTLP credentials in build info")

    bundle = root.joinpath(*CLI_BUNDLE)
    if not bundle.is_file():
        log.warn("CLI bundle not found at %s \u2014 skipping CLI check" % bundle)
        log.warn("build with npm run build -w @rediacc/cli first")
    else:
        log.info("inspecting %s..." % bundle.name)
        if bundle_has_literal(bundle):
            log.error("%s: bundle contains a literal 'Basic <token>' header" % bundle)
            errors += 1
        if errors == 0:
            log.info("✓ CLI bundle: no literal credentials")

    if errors > 0:
        # `log_error ""` prints a bare glyph with no message. Carried; the
        # comparator drops an empty finding, so it costs nothing and removing it
        # would change the bytes a human diffs.
        log.error("")
        log.error("%d credential leak(s) detected. Do NOT ship these artifacts." % errors)
        log.error("Check for accidentally-reintroduced build-time injection in")
        log.error("private/renet/build.sh, .ci/scripts/build/build-renet.sh, or")
        log.error("packages/cli/bundle.mjs.")
        return 1

    log.info("✓ no OTLP credentials leaked in built artifacts")
    return 0


def _have_go() -> bool:
    """`command -v go >/dev/null 2>&1`."""
    return shutil.which("go") is not None


def selftest() -> int:
    """Plant each violation, prove it fires; remove it, prove it does not.

    BOTH DIRECTIONS FOR EVERY CONTROL. The decision functions are exercised
    directly rather than through a subprocess, because the parts worth pinning
    are the three matchers and the grep-context union, and driving them through
    `go version -m` would test the Go toolchain instead.
    """
    ctl = Controls("no-otlp-creds", floor=16, verbose=True)

    clean_buildinfo = "\tpath\tgithub.com/rediacc/renet\n\tbuild\t-ldflags=-X main.Version=1.2.3\n"
    ctl.check(
        "CONTROL: an ordinary buildinfo is clean", buildinfo_findings("b", clean_buildinfo), []
    )
    ctl.check(
        "PLANT: an otlpUser ldflag is caught",
        buildinfo_findings("b", clean_buildinfo + "\t-X telemetry.otlpUser=admin\n"),
        ["b: .go.buildinfo contains telemetry.otlpUser ldflag"],
    )
    ctl.check(
        "PLANT: an otlpPass ldflag is caught",
        buildinfo_findings("b", clean_buildinfo + "\t-X telemetry.otlpPass=hunter2\n"),
        ["b: .go.buildinfo contains telemetry.otlpPass ldflag"],
    )
    ctl.check(
        "PLANT: both ldflags produce two findings, not one",
        len(buildinfo_findings("b", "telemetry.otlpUser telemetry.otlpPass")),
        2,
    )
    # MIRROR: the dot is escaped in the twin's pattern, so `telemetryXotlpUser`
    # is not a match. A port that dropped the escape would flag more.
    ctl.check(
        "MIRROR: an unrelated symbol with the same tail is not a finding",
        buildinfo_findings("b", "telemetryXotlpUser=1"),
        [],
    )

    # -- check 2: the base64-near-symbol window ------------------------------
    ctl.check(
        "PLANT: a base64 line directly after the symbol fires",
        base64_near_symbol("otlpUser\nQUJDREVGR0hJSktMTU5PUFFSUw==\n"),
        True,
    )
    ctl.check(
        "PLANT: a base64 line directly BEFORE the symbol fires (-B1)",
        base64_near_symbol("QUJDREVGR0hJSktMTU5PUFFSUw==\notlpPass\n"),
        True,
    )
    ctl.check(
        "MIRROR: two lines away is outside the window",
        base64_near_symbol("otlpUser\nfiller\nQUJDREVGR0hJSktMTU5PUFFSUw==\n"),
        False,
    )
    ctl.check(
        "MIRROR: a SHORT token next to the symbol is not base64 enough",
        base64_near_symbol("otlpUser\nQUJDREVG\n"),
        False,
    )
    ctl.check(
        "MIRROR: a base64 run inside a longer line is not an anchored match",
        base64_near_symbol("otlpUser\nkey=QUJDREVGR0hJSktMTU5PUFFSUw== trailing\n"),
        False,
    )
    ctl.check(
        "MIRROR: base64 with no otlp symbol anywhere is not a finding",
        base64_near_symbol("harmless\nQUJDREVGR0hJSktMTU5PUFFSUw==\n"),
        False,
    )
    ctl.check("VACUITY: empty strings output finds nothing", base64_near_symbol(""), False)

    # -- check 3: the bundle literal -----------------------------------------
    ctl.check(
        "PLANT: a literal Basic header in double quotes is caught",
        bool(BASIC_LITERAL_RE.search('h["Authorization"] = "Basic QUJDREVGR0hJSktMTU5PUFFSUw==";')),
        True,
    )
    ctl.check(
        "PLANT: the same in single quotes is caught",
        bool(
            BASIC_LITERAL_RE.search("h.set('Authorization', 'Basic QUJDREVGR0hJSktMTU5PUFFSUw==')")
        ),
        True,
    )
    ctl.check(
        "MIRROR: the runtime form is NOT flagged",
        bool(BASIC_LITERAL_RE.search("`Basic ${this.authToken}`")),
        False,
    )
    ctl.check(
        "MIRROR: a short token after Basic is not flagged",
        bool(BASIC_LITERAL_RE.search('"Basic QUJD"')),
        False,
    )

    # -- the whitespace-only buildinfo rule ----------------------------------
    ctl.check("VACUITY: whitespace-only buildinfo reduces to empty", SPACE_RE.sub("", " \t\n"), "")
    ctl.check("MIRROR: real buildinfo does not", SPACE_RE.sub("", " \tpath x\n") != "", True)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
