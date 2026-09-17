"""Every pinned gate tool must have a RUNTIME guard, not just a definition.

Ported from `.ci/scripts/quality/check-host-toolchain-coverage.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__` for why both copies live side by side
until a committed differential ledger says otherwise.

WHY THE TWIN EXISTS, carried over from its header because the archaeology is the
half of a gate that cannot be recovered from the code:

  check-toolchain-pins.sh's A6 rule guarantees a GATE that invokes a pinned tool
  acquires it at the pin rather than trusting PATH -- but that is definition-time
  coverage of the tools GATED_TOOLS already names. It says nothing about whether
  the SEPARATE runtime guard that routes a session away from a host lacking one
  of those tools (.claude/hooks/pre-bash/block-host-toolchain-run.sh's
  BARE_TOOLS/NPX_TOOLS arrays) actually knows about all of them. Those two lists
  are maintained independently as literal bash arrays in two different files,
  with nothing keeping them in sync.

  Measured 2026-08-28: exactly this drift was live and undetected. The runtime
  guard's arrays existed only because a session found the gap by hand
  (`npx --yes ruff format` failing was misdiagnosed as "ruff is missing", when
  ruff was on PATH the whole time and the bug was routing/detection, not
  pinning) -- nothing would have caught GATED_TOOLS growing a fifth entry that
  the runtime guard never learns about. That is the class this gate closes: an
  assertion checked only at DEFINITION (GATED_TOOLS), with no check that the
  runtime guard's CALL SITES (BARE_TOOLS, NPX_TOOLS) still cover every member.

  SCOPE. `go` is deliberately allowed to be a BARE_TOOLS/NPX_TOOLS member with
  no GATED_TOOLS counterpart: go is not part of the toolchain-pins convention
  (its own go.mod/GOTOOLCHAIN resolves versions), so the runtime guard covering
  it is a superset, not a gap. The direction that matters is GATED_TOOLS ->
  BARE_TOOLS/NPX_TOOLS, checked here; the reverse is not required.

The twin's gate header carries a BLOCKER about WIRING rather than about
toolchains, so it stays with the bash file: the step "runs before this lane's
`- id: setup` step, and its subject IS the setup path. Emitting it into the
region would gate it on setup succeeding, so the gate that explains a broken
setup would be the one silenced by it." A port inherits no registration, so
nothing here re-states that as a live suppression.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE TWO EXTRACTORS ARE LINE-ORIENTED AND ANCHORED, and both properties are load
bearing. `grep -oE "^GATED_TOOLS='[^']*'"` and `grep -oE "^NAME=\\([^)]*\\)"`
cannot cross a newline, because grep matches within a line. So a GATED_TOOLS
literal wrapped over two lines, or a `NPX_TOOLS=(` array written one tool per
line -- both perfectly ordinary bash -- are INVISIBLE to this gate, and the
invisibility reads as "nothing is missing" rather than as an error. The
`^` anchor means an indented or `local`-prefixed declaration is invisible too.
That is a real blind spot in the twin. It is preserved rather than quietly
widened, because widening it would change the verdict, and it is reported.

The gate does defend the near half of that hole: an unreadable GATED_TOOLS, or
an unreadable pair of arrays, is a FAILURE with its own message rather than an
empty set that silently covers everything. Read those two branches as the twin's
own acknowledgement that the extractors can come back empty.

`tr ' ' '\\n'` SPLITS ON SPACE ONLY. A tab between two array members leaves them
glued into one pseudo-tool (`ruff\\tgo`), which then appears as missing. Carried
exactly, because a port that split on whitespace generally would DISAGREE with
the twin on a file nobody has written yet but somebody eventually will.

`sort -u` IS RUN UNDER LC_ALL=C by the differential harness, and `comm -23`
requires both inputs sorted in the same collation. Python's `sorted()` on `str`
compares code points, which is C collation for the ASCII these tool names are.
Stated because a locale with a different collation would make `comm` and
`sorted()` disagree, and that would be a difference in the HARNESS rather than
in the subject.

TWO STREAM DIVERGENCES, both deliberate, neither changing a verdict:

  1. The twin's `fail()` prints `✗␣␣␣<msg>` (three spaces); `rediacc_ci.log`
     prints `✗␣<msg>`. `scripts/lib/shadow-gate.ts` strips the marker and
     collapses whitespace runs before comparing, so the two normalize to the
     same finding. The port uses the house logger rather than reproducing an
     ad-hoc one.
  2. The twin decides colour with `[ -t 1 ] && [ -z "${NO_COLOR:-}" ]` and then
     writes the coloured line to STDERR. That is the 11-file variant
     `rediacc_ci.log` was written to end (see its docstring): it tests the wrong
     stream, so redirecting stdout to a file while watching stderr in a terminal
     produces uncoloured output and the reverse writes escapes into the file.
     The port tests the stream it writes to. Reported, not reproduced.

THE INDENTED ADVICE LINES ARE PRINTED RAW, not through the logger, because they
are the twin's continuation lines under a finding header and
`scripts/lib/shadow-gate.ts` folds an indented unmarked line into the finding
above it. Sending them through `log.error` would give each its own `✗`, which is
the same finding text after normalization but a noisier thing for a human to
read next to the twin's output.

WHAT THIS GATE STILL CANNOT SEE, unchanged by the port: it compares two literal
lists. A guard that names a tool in its arrays but never reaches the branch that
uses them still passes, because presence in an array is all that is checked.
That is the same class of blindness `check-toolchain-pins.sh` has at definition
time, one layer further out.
"""

import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The two files whose literal lists must agree. Absolute paths in the twin's messages, so they are joined to the root rather than kept relative.
PINS_REL = ".ci/scripts/quality/check-toolchain-pins.sh"
GUARD_REL = ".claude/rediacc_hooks/guards/block_host_toolchain_run.py"

# `grep -oE "^GATED_TOOLS='[^']*'"`. Anchored, single-line; see the port notes.
_GATED_RE = re.compile(r"^GATED_TOOLS='([^']*)'")

# The two arrays inside the runtime guard, in the order the twin reads them.
ARRAYS = ("NPX_TOOLS", "BARE_TOOLS")


def extract_gated_tools(text: str) -> list[str]:
    """`GATED_TOOLS='a|b|c'` -> ["a", "b", "c"], sorted and de-duplicated.

    THE TWIN'S PIPELINE, STAGE BY STAGE, because each stage has an edge a
    "sensible" rewrite loses:

        grep -oE "^GATED_TOOLS='[^']*'"   every matching LINE, anchored at column 1
        sed -E "s/...'([^']*)'$/\\1/"      the inside of the quotes
        tr '|' '\\n'                       split on the pipe, and nothing else
        sed '/^$/d'                       drop empties, so `a||b` yields two
        sort -u                           sorted, de-duplicated

    Multiple GATED_TOOLS lines all contribute, which is `grep` finding every
    match rather than the first. `[^']*` cannot cross a quote, so the match ends
    at the FIRST closing quote and trailing text on the line never reaches sed.
    """
    tools: set[str] = set()
    for line in text.split("\n"):
        match = _GATED_RE.match(line)
        if not match:
            continue
        # `grep -o` PRINTS THE MATCH, NOT THE LINE, and that is why the `$`
        # anchor in the twin's sed always fires: sed is fed `GATED_TOOLS='a|b'`
        # and nothing else, so trailing text on the source line (` # note`) has already been discarded upstream. A port that ran the sed against the whole line would find the anchor failing and would split the comment too. Verified against the real pipeline in the pytest twin.
        tools.update(part for part in match.group(1).split("|") if part)
    return sorted(tools)


def extract_array(text: str, name: str) -> list[str]:
    """`NAME=(a b c)` or `NAME = ("a", "b", "c")` -> ["a", "b", "c"], sorted, unique.

    BOTH SPELLINGS, and the second one is not optional. W5 P7 made the runtime
    guard a PYTHON module, so `NPX_TOOLS = ("ruff", "go", ...)` is what this now
    reads; the bash form is still here because this gate's own control fixtures
    write it. Reading only the bash form made the port report "NPX_TOOLS or
    BARE_TOOLS could not be read" against a guard that plainly declares them,
    while the twin read them fine -- a MISMATCH_FINDINGS the shadow differential
    caught on the first re-record after the cutover, and which no amount of
    reading the diff would have shown, because the path constant had been
    updated and only the READER had not.

    Space-separated or comma-separated; quotes are stripped. Anchored at column 1
    and confined to one line, which is the blind spot the notes describe.
    """
    pattern = re.compile(r"^%s ?=[ ]?\(([^)]*)\)" % re.escape(name))
    tools: set[str] = set()
    for line in text.split("\n"):
        match = pattern.match(line)
        if not match:
            continue
        # See extract_gated_tools: `grep -o` feeds sed the match alone, so the `$` anchor in the twin's substitution always fires.
        raw = match.group(1).replace('"', "").replace("'", "").replace(",", " ")
        tools.update(part for part in raw.split(" ") if part)
    return sorted(tools)


def missing_from(gated: list[str], covered: list[str]) -> list[str]:
    """`comm -23 gated covered`: the members of `gated` that `covered` lacks.

    A plain set difference, returned sorted so the printed order is the twin's.
    `comm` would also require both inputs sorted; they are, by construction.
    """
    return sorted(set(gated) - set(covered))


def _read(path: pathlib.Path) -> str:
    """File text, or "" when it cannot be read.

    The twin's `grep ... "$1" 2>/dev/null` swallows a read error into an empty
    match set, and the callers then treat empty as "could not be read" and FAIL.
    Same shape here: an unreadable file must not look like a covered one.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 violation or control failure.

    `--selftest` is intercepted BEFORE any real scan. The twin takes no arguments
    at all, so no caller can be passing this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    failures = 0

    def fail(message: str) -> None:
        nonlocal failures
        log.error(message)
        failures += 1

    def ok(message: str) -> None:
        # STDOUT, matching the twin's `pass()`. `scripts/lib/shadow-gate.ts` classifies `ok␣␣` as chatter, which is what a progress line is.
        print("ok   %s" % message)

    # --- controls first: a gate nobody has watched fail is not a gate --------
    #
    # INLINE, on every invocation, exactly as the twin runs them. Moving them behind `--selftest` would change what a plain run proves, and what a plain run proves is the only thing CI ever sees.
    bad_pins = "GATED_TOOLS='shfmt|shellcheck|ruff|actionlint|newlypinned'\n"
    guard_missing = "NPX_TOOLS=(ruff go shfmt shellcheck actionlint)\nBARE_TOOLS=(ruff go shfmt shellcheck actionlint)\n"
    missing = missing_from(extract_gated_tools(bad_pins), extract_array(guard_missing, "NPX_TOOLS"))
    if not missing:
        fail(
            "CONTROL FAILED: a pinned tool absent from the runtime guard's NPX_TOOLS was NOT detected."
        )
        return 1
    if missing != ["newlypinned"]:
        fail(
            "CONTROL FAILED: the wrong tool was flagged (got '%s', wanted 'newlypinned')."
            % "\n".join(missing)
        )
        return 1

    good_pins = "GATED_TOOLS='shfmt|shellcheck|ruff|actionlint'\n"
    guard_full = "NPX_TOOLS=(ruff go shfmt shellcheck actionlint)\nBARE_TOOLS=(ruff go shfmt shellcheck actionlint)\n"
    still_missing = missing_from(
        extract_gated_tools(good_pins), extract_array(guard_full, "NPX_TOOLS")
    )
    if still_missing:
        fail(
            "CONTROL FAILED: full coverage was reported as missing ('%s')."
            % "\n".join(still_missing)
        )
        return 1
    ok("control: a pinned tool absent from the runtime guard is detected")
    ok("control: full coverage reports nothing missing")

    # --- the real scan ------------------------------------------------------
    pins = root / PINS_REL
    guard = root / GUARD_REL

    # A MISSING SUBJECT IS A FAILURE, NOT AN ABSTENTION. Both of these read as "the thing this gate compares has moved", which is exactly when a green would mean nothing.
    if not pins.is_file():
        fail("the pinned-tools source is gone: %s" % pins)
        return 1
    if not guard.is_file():
        fail("the runtime guard is gone: %s" % guard)
        return 1

    gated = extract_gated_tools(_read(pins))
    if not gated:
        fail(
            "GATED_TOOLS could not be read from %s -- this gate is not seeing its input, "
            "so its green would mean nothing." % pins
        )
        return 1
    n_gated = len(gated)

    npx_tools = extract_array(_read(guard), "NPX_TOOLS")
    bare_tools = extract_array(_read(guard), "BARE_TOOLS")
    if not npx_tools or not bare_tools:
        fail(
            "NPX_TOOLS or BARE_TOOLS could not be read from %s -- the runtime guard's "
            "arrays moved or were renamed." % guard
        )
        return 1

    missing_npx = missing_from(gated, npx_tools)
    missing_bare = missing_from(gated, bare_tools)

    if missing_npx:
        fail("pinned tool(s) missing from NPX_TOOLS in %s: %s" % (guard, " ".join(missing_npx)))
        # RAW, indented, on stderr: the twin's continuation line. See the port notes for why it does not go through the logger.
        print(
            "     A bare 'npx <tool>' for these will fail with a confusing npm error "
            "instead of the actionable npx-cannot-run-this message.",
            file=sys.stderr,
        )
    if missing_bare:
        fail("pinned tool(s) missing from BARE_TOOLS in %s: %s" % (guard, " ".join(missing_bare)))
        print(
            "     A direct invocation of these on a host that lacks them will not be "
            "routed to the devbox.",
            file=sys.stderr,
        )

    if failures == 0:
        ok(
            "%d pinned tool(s) all covered by the runtime guard's NPX_TOOLS and BARE_TOOLS"
            % n_gated
        )
        # THE SHAPE, NOT JUST THE VERDICT. The count is printed on the success line so a reader can notice when it collapses.
        print("✓ host-toolchain runtime guard covers every pinned tool (%d)." % n_gated)
        return 0

    log.error("the pinned-tools definition and the runtime guard have drifted.")
    print(
        "  Fix: add the missing tool(s) to NPX_TOOLS and BARE_TOOLS in %s." % guard, file=sys.stderr
    )
    return 1


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    BOTH DIRECTIONS FOR EVERY CONTROL. A gate with only positive plants will
    happily flag a correct pair of files, and the mirrors below are the half that
    proves it does not.
    """
    ctl = Controls("host-toolchain-coverage", floor=26, verbose=True)

    pins_ok = "GATED_TOOLS='shfmt|shellcheck|ruff|actionlint'\n"
    guard_ok = "NPX_TOOLS=(ruff go shfmt shellcheck actionlint)\nBARE_TOOLS=(ruff go shfmt shellcheck actionlint)\n"

    # -- the extractors ------------------------------------------------------
    ctl.check(
        "gated: the literal splits on the pipe and sorts",
        extract_gated_tools(pins_ok),
        ["actionlint", "ruff", "shellcheck", "shfmt"],
    )
    ctl.check(
        "gated: an empty alternation member is dropped",
        extract_gated_tools("GATED_TOOLS='a||b'\n"),
        ["a", "b"],
    )
    ctl.check(
        "gated: duplicates collapse", extract_gated_tools("GATED_TOOLS='a|a|b'\n"), ["a", "b"]
    )
    # MIRRORS: the anchor and the single-line confinement, both blind spots the port notes name. Pinned so a later reader sees they are DECISIONS.
    ctl.check(
        "gated: MIRROR an indented declaration is invisible",
        extract_gated_tools("  GATED_TOOLS='a'\n"),
        [],
    )
    ctl.check(
        "gated: MIRROR a file with no literal yields nothing", extract_gated_tools("echo hi\n"), []
    )
    ctl.check(
        "gated: MIRROR a differently named variable is not it",
        extract_gated_tools("OTHER_TOOLS='a|b'\n"),
        [],
    )

    ctl.check(
        "array: NPX_TOOLS splits on spaces and sorts",
        extract_array(guard_ok, "NPX_TOOLS"),
        ["actionlint", "go", "ruff", "shellcheck", "shfmt"],
    )
    ctl.check(
        "array: BARE_TOOLS is read independently",
        extract_array(guard_ok, "BARE_TOOLS"),
        ["actionlint", "go", "ruff", "shellcheck", "shfmt"],
    )
    ctl.check(
        "array: an empty array yields nothing", extract_array("NPX_TOOLS=()\n", "NPX_TOOLS"), []
    )
    ctl.check(
        "array: MIRROR an absent array yields nothing", extract_array(guard_ok, "NOPE_TOOLS"), []
    )
    # THE TAB DEFECT, PINNED. `tr ' '` does not split on a tab, so two members separated by one become a single pseudo-tool. If someone "fixes" the twin, this control fails and points at the sentence that explains why.
    ctl.check(
        "array: a TAB does not separate members (the twin's tr ' ')",
        extract_array("NPX_TOOLS=(ruff\tgo)\n", "NPX_TOOLS"),
        ["ruff\tgo"],
    )

    ctl.check(
        "diff: a tool absent from the guard is reported", missing_from(["a", "b"], ["a"]), ["b"]
    )
    ctl.check("diff: MIRROR full coverage reports nothing", missing_from(["a"], ["a", "b"]), [])
    ctl.check(
        "diff: MIRROR a guard SUPERSET is fine (the `go` case)",
        missing_from(["ruff"], ["ruff", "go"]),
        [],
    )

    # -- the whole gate, over real files -------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        pins = root / PINS_REL
        guard = root / GUARD_REL
        pins.parent.mkdir(parents=True)
        guard.parent.mkdir(parents=True)

        def write(pins_text: str | None, guard_text: str | None) -> int:
            for target, text in ((pins, pins_text), (guard, guard_text)):
                if text is None:
                    if target.exists():
                        target.unlink()
                else:
                    target.write_text(text, encoding="utf-8")
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved

        ctl.check("CONTROL: a covered pair passes", write(pins_ok, guard_ok), 0)

        # THE VACUITY CASES. Each of these is a state in which the gate has compared nothing, and each must refuse rather than report coverage.
        ctl.check("VACUITY: an absent pins file is refused", write(None, guard_ok), 1)
        ctl.check("VACUITY: an absent guard file is refused", write(pins_ok, None), 1)
        ctl.check("VACUITY: an unreadable GATED_TOOLS is refused", write("echo hi\n", guard_ok), 1)
        ctl.check(
            "VACUITY: an empty GATED_TOOLS literal is refused",
            write("GATED_TOOLS=''\n", guard_ok),
            1,
        )
        ctl.check("VACUITY: absent guard arrays are refused", write(pins_ok, "echo hi\n"), 1)
        ctl.check(
            "VACUITY: NPX_TOOLS present but BARE_TOOLS absent is refused",
            write(pins_ok, "NPX_TOOLS=(ruff)\n"),
            1,
        )

        # PLANTS: a fifth pinned tool the guard never learns about, which is the 2026-08-28 drift this gate was built for.
        ctl.check(
            "PLANT: a tool missing from BOTH arrays is caught",
            write("GATED_TOOLS='shfmt|shellcheck|ruff|actionlint|newlypinned'\n", guard_ok),
            1,
        )
        ctl.check(
            "PLANT: a tool missing from NPX_TOOLS only is caught",
            write(
                "GATED_TOOLS='ruff|newlypinned'\n",
                "NPX_TOOLS=(ruff)\nBARE_TOOLS=(ruff newlypinned)\n",
            ),
            1,
        )
        ctl.check(
            "PLANT: a tool missing from BARE_TOOLS only is caught",
            write(
                "GATED_TOOLS='ruff|newlypinned'\n",
                "NPX_TOOLS=(ruff newlypinned)\nBARE_TOOLS=(ruff)\n",
            ),
            1,
        )
        # ITS MIRROR: the guard covering MORE than GATED_TOOLS is fine. The
        # direction is one-way on purpose; see SCOPE in the module docstring.
        ctl.check(
            "MIRROR: a guard superset passes (the documented `go` case)",
            write(
                "GATED_TOOLS='ruff'\n", "NPX_TOOLS=(ruff go extra)\nBARE_TOOLS=(ruff go extra)\n"
            ),
            0,
        )
        # ITS MIRROR: the blind spot is a PASS, and that is the honest record of what this gate does not see. A multi-line array reads as absent, which this gate reports as a refusal rather than as coverage.
        ctl.check(
            "BLIND SPOT: a multi-line array reads as ABSENT, so it refuses",
            write(pins_ok, "NPX_TOOLS=(\n  ruff\n)\nBARE_TOOLS=(ruff)\n"),
            1,
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
