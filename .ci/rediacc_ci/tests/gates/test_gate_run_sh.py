"""Port of `.ci/scripts/test/gates/test-run-sh.sh`.

Controls for `./run.sh`, the entry point every other command goes through.

WHY IT EXISTS. The twin was written after two defects had already lived in that
file precisely because it had no test:

  1. `quality all` logged a warning and returned SUCCESS when shfmt was missing,
     so on any machine without shfmt the command reported green having run no
     shell gate at all.
  2. `fix shell` formatted with whatever shfmt was on PATH while the gate verified
     with the pinned one, so the fixer could produce a state the checker rejects.

HERMETIC BY CONSTRUCTION, and the port keeps that: no docker, no network, no
submodules. Every control is either a DISPATCH assertion (a real `./run.sh <verb>`
whose exit code is read) or a SOURCE-LEVEL invariant. Nothing here runs a real
gate; that is what the gates themselves are for.

TWO FILES, AND THE DISTINCTION IS LOAD BEARING IN BOTH DIRECTIONS. Since the
2026-09-06 split `./run.sh` is a router and the body it used to hold is
`.ci/legacy/run-legacy.sh`:

    RUN  the router, and the thing a person or a workflow actually types. Every
         dispatch control drives this, because dispatch is what the split must not
         change.
    SRC  the legacy body, and the thing the source-level controls read.
         `quality_all` and `fix_shell` live there now; grepping the router for
         them would find nothing and three controls would PASS on nothing found,
         which is the vacuous green this file exists to prevent.

WHAT THE PORT RESPELLS, AND WHAT IT DOES NOT. The twin's five extractors are awk
and sed programs (`arms_of`, `documented_in`, `ported_of`, `usage_of`,
`verb_findings`); this module reimplements four of them in Python, rule for rule,
and keeps the fifth in bash on purpose. `ported_of` SOURCES the router and prints
the array bash itself sees, because a regex over the table can be fooled by a
multi-line or commented entry, and the router's `BASH_SOURCE` guard means sourcing
it runs nothing. That is the twin's argument and it survives the port unchanged.

THE REIMPLEMENTED EXTRACTORS THEREFORE OWE A CONTROL OF THEIR OWN, which is the
one case this port ADDS. `test_the_extractors_survive_the_traps_the_awk_documents`
drives `arms_of`, `documented_in` and `usage_of` over a synthetic fixture with a
known answer, including the three shapes the twin's comments name as the reason
each rule is written the way it is: an inner `case` whose numeric arms sit at the
same INDENT as a real subcommand (depth decides the level, never indentation), a
help signature separated from its prose by TWO spaces (splitting on one reads the
first word of the prose as a subcommand), and a `Usage:` line with a NESTED
bracket group (cutting at the first `]` takes the nested three for subcommands and
loses the rest). Those are the rules a Python rewrite is most likely to get subtly
wrong, and a rewrite checked only against today's tree would look right while
being wrong for the next shape that arrives.

IT DOES NOT DRIVE THE TWIN TO CHECK ITSELF, deliberately. Comparing the Python
extractors against the awk ones at runtime would be the strongest possible check
today and a broken test in W7 P5, which deletes the twin. The fixture above makes
the same claim without borrowing the twin's lifetime.

NO `REAL_TREE_TWIN`, AND IT IS CHECKED RATHER THAN ASSUMED. `test-run-sh.sh` is in
neither `gates.lock.json`'s `mutex`/`reads` claims nor `run-all.sh`'s
`WRITER_TESTS_FALLBACK` / `SCANNER_TESTS_FALLBACK` arrays, so the parity driver's
`real_tree_admission` would REFUSE the declaration as an unearned serialisation
slot. What this module does to the real tree is read three files and run
`./run.sh <verb>` four times; the only writes are into a `mktemp -d` holding copies.

TWO PLACES THE PORT SAYS MORE THAN THE TWIN, both narrower than they look and
neither of them a verdict change. Driven against a dozen planted defects the two
sides went red together every time; these are the two states where the MESSAGE
differs, and in both the port names the real cause and the twin does not.

1. `ported_of` REFUSES A NON-ZERO SOURCE. The twin sources the router inside
   `$( ... )` and discards the status, so a router that does not parse yields an
   EMPTY table and the failure surfaces one section later as "an overlapping verb
   was NOT reported" -- a statement about a control, on a tree whose router is
   broken. Reading a table that could not be read is unchecked, not empty, so this
   fails where it happens. The twin's own parse control reds in that same state,
   which is why the verdicts still agree.

2. THE TWIN'S ANTI-VACUITY CONTROL CANNOT FIRE, and the port's can. Section 4
   sources `.ci/lib/local-common.sh`, which sources `.ci/scripts/lib/common.sh:11`
   -- `set -euo pipefail`. Everything after that line in the twin runs under
   errexit it never asked for, so when an extractor returns nothing,
   `n_router=$(arms_of "$RUN" | grep -c '^TOP ')` (test-run-sh.sh:317) exits 1 on
   grep's no-match status and KILLS the script four lines before the control that
   would have said "an extractor returned an EMPTY set". Measured 2026-09-08 with
   `main() {` renamed in the router: the twin stops after "the legacy body is
   executable", prints 12 of its 23 PASS lines and no verdict line at all. The
   port reports `router=0 legacy=16 subs=50 docs=18` and carries on to the rest of
   its controls. Both are red, so parity holds; only the diagnostic differs.

NO `XDIST_GROUP` for the same class of reason: no port is bound, no module global
is mutated, and the environment overlay each lane probe uses is passed to one
short-lived `bash -c` rather than set on this process.
"""

import os
import re
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-run-sh.sh"

ROOT = paths.repo_root()
RUN = paths.from_root("run.sh")
SRC = paths.from_root(".ci", "legacy", "run-legacy.sh")
LOCAL_COMMON = paths.from_root(".ci", "lib", "local-common.sh")
PY_PACKAGE_INIT = paths.from_root(".ci", "rediacc_ci", "__init__.py")

# A CEILING, NOT A STYLE RULE. The whole point of the split is that porting a verb
# touches one line in the router; a router that starts absorbing logic re-creates
# the file the split was undoing, one reasonable special case at a time.
ROUTER_LINE_CEILING = 120

# The lane decision, taken in a fresh shell that sources exactly what a real gate
# sources. Byte-for-byte the twin's, including the order of the three sources.
LANE_SNIPPET = (
    ". .ci/config/constants.sh; . .ci/scripts/lib/toolchain.sh; "
    ". .ci/lib/local-common.sh; gate_lane_decide"
)

# READ THE TABLE, NEVER A REGEX OVER IT. See the module docstring.
PORTED_TABLE_SNIPPET = r"""
. "$1" >/dev/null 2>&1
printf '%s\n' ${PORTED_VERBS[@]+"${PORTED_VERBS[@]}"}
"""

BASH_FIX = "install bash; the subject is a bash router and a bash legacy body"

# `arms_of`'s two shapes, transcribed from the awk. The first says a line looks
# like a case arm at all; the second says a line OPENS a case. Both are matched
# against the line with its leading indentation already removed, because
# case-nesting DEPTH decides the level and indentation is not allowed to.
ARM_LINE_RE = re.compile(r'^[a-zA-Z0-9_"*-][a-zA-Z0-9_"*|. -]*\)')
CASE_OPEN_RE = re.compile(r"(^|[ \t;])case[ \t].*[ \t]in([ \t]|$)")
VERB_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def bash_bin() -> str:
    """The interpreter, probed once so a missing one is a LOUD failure with a fix."""
    return harness.require_tool("bash", BASH_FIX)


def read(path) -> str:
    return path.read_text(encoding="utf-8")


def run_verb(gate, *args: str) -> int:
    """`./run.sh <args...>` from the repo root; its exit code and nothing else.

    A FILE THAT CANNOT BE EXECUTED IS A VERDICT, NOT A TRACEBACK. `subprocess`
    raises `PermissionError` when the router has lost its `+x` bit, which arrives
    as an ERROR inside a helper and reads as harness flake; the bash twin gets a
    plain 126 from its shell. This turns the exception back into the statement the
    twin makes, and names the file, because the executable-bit control one section
    down is exactly the state that produces it.
    """
    try:
        return harness.run([str(RUN), *args], cwd=ROOT).rc
    except OSError as exc:
        gate.log_fail(
            "could not execute %s at all (%s). Every dispatch control below would be "
            "unchecked, which is a FAILURE and not a pass." % (paths.relative_to_root(RUN), exc)
        )
        raise  # unreachable; log_fail raises. Kept so the return type cannot lie.


def exits(gate, label: str, want: int, *args: str) -> None:
    """The twin's `exits`: drive a verb, tally the exit code against `want`."""
    got = run_verb(gate, *args)
    if got == want:
        gate.ok("%s (exit %d)" % (label, got))
    else:
        gate.no("%s (exit %s, want %d)" % (label, harness.describe_exit(got), want))


def body(source: str, name: str) -> str:
    """`body <file> <function-name>`: the function's body, comment lines emptied.

    CODE ONLY, and the twin's header says why in a sentence worth keeping: an
    earlier draft grepped a fixed window and matched the word `log_warn` inside the
    COMMENT that explains the old behaviour, so the test failed on correct code --
    the wrong direction for a control to fail in.
    """
    out = []
    opening = re.compile(r"^%s\(\) \{" % re.escape(name))
    inside = False
    for line in source.splitlines():
        if not inside:
            if opening.match(line):
                inside = True
            continue
        if line.startswith("}"):
            break
        out.append(re.sub(r"^\s*#.*$", "", line))
    return "\n".join(out)


def lines_after(source: str, pattern: str, count: int) -> str:
    """`grep -A <count> <pattern>`: every matching line plus the `count` after it.

    Overlapping windows are concatenated rather than de-duplicated, which grep does
    de-duplicate. It cannot matter for either call site here (one match each, proved
    by the anti-vacuity refusal in the caller), and the difference is only ever
    duplicated text in a haystack that is then searched for a substring.
    """
    lines = source.splitlines()
    matcher = re.compile(pattern)
    window: list[str] = []
    for index, line in enumerate(lines):
        if matcher.search(line):
            window.extend(lines[index : index + count + 1])
    return "\n".join(window)


def arms_of(source: str) -> set[str]:
    """`main()`'s case arms as `"TOP <verb>"` / `"SUB <top>/<sub>"`.

    CASE-NESTING DEPTH DECIDES THE LEVEL, NEVER INDENTATION. The docker-group route
    code in the legacy dispatcher contains an inner `case` whose arms sit at the
    same indent as a real subcommand, and an indentation rule reports its numeric
    arms as verbs.
    """
    found: set[str] = set()
    inmain = False
    depth = 0
    top = ""
    for raw in source.splitlines():
        if not inmain:
            if re.match(r"^main\(\) \{", raw):
                inmain = True
            continue
        if raw.startswith("}"):
            break
        line = re.sub(r"^[ \t]+", "", raw)
        if line.startswith("#"):
            continue
        if line.startswith("esac"):
            depth -= 1
            continue
        if CASE_OPEN_RE.search(line):
            depth += 1
            continue
        if depth < 1 or not ARM_LINE_RE.match(line):
            continue
        for part in re.sub(r"\).*$", "", line, count=1).split("|"):
            verb = part.strip(" \t").replace('"', "")
            # `*` is the fallback, `""` the bare-verb default, a leading `-` a flag
            # alias of the verb beside it, a bare number an inner arm.
            if verb in ("", "*") or verb.startswith("-") or verb.isdigit():
                continue
            if depth == 1:
                top = verb
                found.add("TOP " + verb)
            elif depth == 2 and top:
                found.add("SUB %s/%s" % (top, verb))
    return found


def documented_in(source: str) -> set[str]:
    """`show_help`'s inventory as `"TOP <verb>"` / `"SUB <top>/<sub>"`.

    THE SIGNATURE IS THE PART BEFORE THE FIRST RUN OF TWO SPACES. Splitting on a
    single space reads the first word of the prose as a subcommand.
    """
    found: set[str] = set()
    inhelp = False
    for raw in source.splitlines():
        if not inhelp:
            if re.match(r"^show_help\(\) \{", raw):
                inhelp = True
            continue
        if raw == "EOF" or raw.startswith("}"):
            break
        if not re.match(r"^  [a-z]", raw):
            continue
        line = raw[2:]
        gap = re.search(r"[ \t][ \t]+", line)
        signature = line[: gap.start()] if gap else line
        description = line[len(signature) :]
        words = re.split(r"[ \t]+", signature)
        top = words[0]
        if not VERB_RE.match(top):
            continue
        found.add("TOP " + top)
        if len(words) < 2:
            continue
        # `<cmd>` means "the subcommands are enumerated in the description", which
        # is how devbox and worktree are written. Anything else in brackets is a
        # PARAMETER (`<slug>`, `[opts]`), not a subcommand.
        if words[1] == "<cmd>":
            parts = description.split("|")
            if len(parts) < 2:
                continue
            for part in parts:
                verb = part.strip(" \t")
                if VERB_RE.match(verb):
                    found.add("SUB %s/%s" % (top, verb))
            continue
        if VERB_RE.match(words[1]):
            found.add("SUB %s/%s" % (top, words[1]))
    return found


def usage_of(source: str, verb: str) -> set[str]:
    """A verb's own `Usage:` line, NESTED GROUPS REMOVED FIRST.

    `devbox` writes `url [term|account|db]` inside its own list, so cutting at the
    first `]` would take those three for subcommands and lose the seven that follow.
    """
    matcher = re.compile(r"Usage: \./run\.sh %s \[.*" % re.escape(verb))
    for line in source.splitlines():
        hit = matcher.search(line)
        if not hit:
            continue
        text = re.sub(r"^[^\[]*\[", "", hit.group(0), count=1)
        text = re.sub(r"\[[^\]]*\]", "", text)
        text = re.sub(r"\].*$", "", text, count=1)
        return {part.strip(" \t") for part in text.split("|") if part.strip(" \t")}
    return set()


def ported_of(gate, router) -> set[str]:
    """`PORTED_VERBS` as BASH sees it, by sourcing the router.

    Not a regex: a multi-line or commented entry cannot fool the parser this way,
    and the `BASH_SOURCE` guard at the end of the router means sourcing runs nothing.
    """
    result = harness.run([bash_bin(), "-c", PORTED_TABLE_SNIPPET, "_", str(router)])
    if result.rc != 0:
        gate.log_fail(
            "sourcing %s to read PORTED_VERBS exited %d (stderr: %s); the overlap half "
            "of the partition would be computed against an empty table"
            % (router, result.rc, result.err.strip())
        )
    return {line.strip() for line in result.out.splitlines() if line.strip()}


def level(entries: set[str], prefix: str) -> set[str]:
    """The `TOP `/`SUB ` slice of an extractor's output, with the tag removed."""
    return {e[len(prefix) :] for e in entries if e.startswith(prefix)}


def subs_of(entries: set[str], top: str) -> set[str]:
    return {e.split("/", 1)[1] for e in entries if e.startswith("SUB %s/" % top)}


def verb_findings(gate, router, legacy) -> list[str]:
    """One line per problem, EMPTY when the split is a partition.

    A findings FUNCTION rather than inline assertions, so the controls below can
    drive the same code against a deliberately broken COPY: an assertion that has
    never been seen to fire is not yet evidence of anything.

    NO EMPTY-STRING GUARD IS NEEDED HERE, and its absence is the one place the port
    is structurally safer than the twin. The twin pipes each half through
    `printf '%s\\n'`, where an EMPTY set is one blank line rather than zero lines,
    so without `sed '/^$/d'` on every side an empty half is reported as a finding
    about a verb whose name is the empty string -- an instrument inventing a defect.
    A Python set of zero elements has no such spelling.
    """
    router_text, legacy_text = read(router), read(legacy)
    router_arms = arms_of(router_text)
    legacy_arms = arms_of(legacy_text)
    documented = documented_in(legacy_text)

    dispatched_router = level(router_arms, "TOP ") | ported_of(gate, router)
    dispatched_legacy = level(legacy_arms, "TOP ")
    dispatched = dispatched_router | dispatched_legacy
    documented_top = level(documented, "TOP ")

    findings = ["overlap %s" % v for v in sorted(dispatched_router & dispatched_legacy)]
    findings += ["dispatched-but-undocumented %s" % v for v in sorted(dispatched - documented_top)]
    findings += ["documented-but-unreachable %s" % v for v in sorted(documented_top - dispatched)]

    # SECOND LEVEL, only for the verbs that OWN a nested case. `provision`, `www`,
    # `rotation` and `worktree` delegate their whole subcommand tree to another
    # program, so their documented subcommands are that program's inventory and not
    # this file's; demanding they appear as arms here would be wrong.
    for top in sorted(
        {e[len("SUB ") :].split("/", 1)[0] for e in legacy_arms if e.startswith("SUB ")}
    ):
        armed = subs_of(legacy_arms, top)
        described = subs_of(documented, top)
        findings += [
            "dispatched-but-undocumented %s/%s" % (top, s) for s in sorted(armed - described)
        ]
        findings += [
            "documented-but-unreachable %s/%s" % (top, s) for s in sorted(described - armed)
        ]
        # THE THIRD INVENTORY. A verb's own `Usage:` line is what a user sees after a
        # typo, and it drifted from both of the others unnoticed for months.
        usage = usage_of(legacy_text, top)
        if usage:
            findings += ["usage-line-drift %s/%s" % (top, s) for s in sorted(armed ^ usage)]
    return findings


def plant(gate, path, pattern: str, replacement: str, why: str) -> None:
    """Rewrite one line of a COPY, and REFUSE if the rewrite matched nothing.

    THE CONTROL'S OWN CONTROL, and it is the half the twin leaves implicit. Each of
    the three plants below is a `sed -i` whose pattern is anchored to a literal line
    of the real file; when such a line is reworded the substitution silently becomes
    a no-op, the finding it was supposed to provoke never appears, and what reads as
    "the assertion does not fire" is really "the plant was never planted". The twin
    still goes red in that state, so the verdicts agree, but it goes red naming the
    wrong thing. Counting the substitution says which one happened.
    """
    text = read(path)
    planted, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count != 1:
        gate.log_fail(
            "THE PLANT DID NOT LAND: %r matched %d line(s) of %s, so %s would be tested "
            "against an UNMODIFIED copy. Re-anchor the pattern; do not weaken the "
            "assertion." % (pattern, count, path.name, why)
        )
    path.write_text(planted, encoding="utf-8")


def test_an_unknown_verb_does_not_look_like_success(gate):
    """Dispatch. What the split must not change: the same argv reaches the same code."""
    exits(gate, "an unknown verb fails", 1, "definitely-not-a-verb")
    exits(gate, "an unknown devbox subcommand fails", 1, "devbox", "not-a-real-subcommand")
    exits(gate, "help succeeds", 0, "help")
    exits(gate, "devbox exec with no command fails", 1, "devbox", "exec", "--")
    gate.tally_finish("run.sh dispatch")


def test_quality_all_refuses_when_the_shell_gates_cannot_run(gate):
    """THE VACUOUS GREEN. A gate that cannot run must not report success.

    Both directions, which is what makes the pair a control rather than a wish: the
    warn-and-continue spelling must be ABSENT, and a failure path must be PRESENT.
    Either one alone is satisfied by a `quality_all` that does nothing at all.
    """
    quality_all = body(read(SRC), "quality_all")
    if not quality_all.strip():
        gate.log_fail(
            "quality_all was not extracted from %s, so both controls below would ask "
            "their question of an EMPTY string and both would answer whatever the empty "
            "string answers." % paths.relative_to_root(SRC)
        )
    if "log_warn" in quality_all:
        gate.no(
            "CONTROL: quality_all warns and falls through when shfmt is absent "
            "(the vacuous green is back)"
        )
    else:
        gate.ok("quality_all does not warn-and-continue when shfmt is unusable")
    if "return 1" in quality_all:
        gate.ok("quality_all returns non-zero when the shell gates cannot run")
    else:
        gate.no("quality_all has no failure path when the shell gates cannot run")
    gate.tally_finish("quality_all")


def test_fix_and_check_use_the_same_binary(gate):
    """`fix shell` must format with the binary the gate verifies with.

    The nastiest shape of a version split is the one where the tool that is supposed
    to fix the problem creates it.
    """
    source = read(SRC)
    window = lines_after(source, r"^fix_shell\(\)", 12)
    if not window:
        gate.log_fail(
            "fix_shell was not found in %s; both controls below would search an empty "
            "window and the second one PASSES on nothing found." % paths.relative_to_root(SRC)
        )
    if "toolchain_acquire shfmt" in window:
        gate.ok("fix shell formats with the pinned binary, the one the gate verifies with")
    else:
        gate.no("fix shell takes shfmt from PATH; it can format into a state the gate rejects")
    bare = re.search(
        r'^\s+(find [^|]*-exec |")shfmt', lines_after(source, r"^fix_shell\(\)", 20), re.MULTILINE
    )
    if bare:
        gate.no("CONTROL: fix_shell still calls a bare shfmt somewhere")
    else:
        gate.ok("CONTROL: no bare shfmt invocation survives in fix_shell")
    gate.tally_finish("fix_shell")


def lane(**overrides: str) -> str:
    """`gate_lane_decide` under an environment overlay, stdout only.

    THE OVERLAY IS ONE VARIABLE, exactly as `env VAR=1 bash -c ...` gives the twin.
    Clearing the others would be tidier and would let this module report a lane the
    twin does not see on a machine where one of them is already exported, which is a
    divergence invented by the port.
    """
    result = harness.run([bash_bin(), "-c", LANE_SNIPPET], cwd=ROOT, env=dict(overrides))
    return result.out.strip()


def test_the_gate_lane_is_decided_and_never_degrades_silently(gate):
    """The lane, including the one answer that breaks the re-exec recursion."""
    rows = (
        (
            {"REDIACC_IN_DEVBOX": "1"},
            "host",
            "inside the container the lane is 'host' (breaks the re-exec recursion)",
            "REDIACC_IN_DEVBOX did not force the host lane -- routing would recurse",
        ),
        (
            {"REDIACC_LANE": "host"},
            "host",
            "REDIACC_LANE=host is honoured (the documented opt-out)",
            "the host opt-out is not honoured",
        ),
        (
            {"REDIACC_LANE": "devbox"},
            "devbox",
            "REDIACC_LANE=devbox is honoured",
            "an explicit devbox lane is not honoured",
        ),
    )
    for overrides, want, good, bad in rows:
        got = lane(**overrides)
        if got == want:
            gate.ok(good)
        else:
            gate.no("%s (decided %r, want %r)" % (bad, got, want))

    # A routed verb must not silently degrade: if it cannot route, it says so.
    should_route = body(read(LOCAL_COMMON), "gate_lane_should_route")
    if not should_route.strip():
        gate.log_fail(
            "gate_lane_should_route was not extracted from %s; the control below would "
            "search an empty body and report silent degradation on correct code."
            % paths.relative_to_root(LOCAL_COMMON)
        )
    if re.search(r"log_warn|log_error", should_route):
        gate.ok("a lane that cannot route reports it rather than degrading silently")
    else:
        gate.no(
            "CONTROL: routing can fail silently, which is the failure this design exists to prevent"
        )
    gate.tally_finish("gate lane")


def test_both_halves_are_runnable_at_all(gate):
    """Parse and permission bits, on the router AND on the legacy body.

    The legacy file is checked too, and not as symmetry: the router `exec`s it, so a
    legacy file that does not parse or has lost its `+x` bit fails on the FIRST verb
    anybody types, with the router named in the error and not the file at fault.
    """
    for path, label in ((RUN, "run.sh"), (SRC, "the legacy body")):
        if harness.run([bash_bin(), "-n", str(path)]).rc == 0:
            gate.ok("%s parses" % label)
        else:
            gate.no("%s does not parse" % label)
        if os.access(path, os.X_OK):
            gate.ok("%s is executable" % label)
        else:
            gate.no("%s is not executable" % label)
    gate.tally_finish("both halves runnable")


def test_the_split_is_a_partition_of_the_documented_verb_set(gate):
    """SET EQUALITY PLUS DISJOINTNESS, in both directions, against `show_help`.

    `./run.sh <verb>` has three possible destinations now -- the media entry point,
    the `rediacc_ci` package, and the legacy body -- and the two ways a move between
    them goes wrong are silent in OPPOSITE directions:

      AN ORPHAN. A verb deleted from the legacy dispatcher and not added to
        PORTED_VERBS falls through to the legacy `*)` arm and reports "Unknown
        command", indistinguishable from a typo, on a verb documented three lines
        above in the same file's own help.
      AN OVERLAP. A verb left in BOTH is served by whichever the router reaches
        first, so the port appears to work while the code it was meant to replace is
        what actually ran.

    SECOND LEVEL, NOT JUST TOP LEVEL. On the day the twin was written the dispatcher
    served SEVEN subcommands `show_help` did not mention, and the per-verb `Usage:`
    strings were a THIRD inventory agreeing with neither. A check over top-level
    verbs alone finds none of that and would have shipped green.
    """
    # ANTI-VACUITY BEFORE THE ASSERTION, because every claim here is "this set is
    # empty" and an extractor that matched nothing satisfies all of them at once.
    router_arms = arms_of(read(RUN))
    legacy_arms = arms_of(read(SRC))
    documented = documented_in(read(SRC))
    shape = (
        len(level(router_arms, "TOP ")),
        len(level(legacy_arms, "TOP ")),
        len({e for e in legacy_arms if e.startswith("SUB ")}),
        len(level(documented, "TOP ")),
    )
    if all(shape):
        gate.ok(
            "the extractors see a real tree: %d router arm(s), %d legacy arm(s), "
            "%d subcommand(s), %d documented verb(s)" % shape
        )
    else:
        gate.no(
            "CONTROL: an extractor returned an EMPTY set (router=%d legacy=%d subs=%d "
            "docs=%d); every assertion below would pass on nothing" % shape
        )

    findings = verb_findings(gate, RUN, SRC)
    if findings:
        gate.no(
            "the verb sets do not partition:\n%s" % "\n".join("    " + line for line in findings)
        )
    else:
        gate.ok("router arms + legacy arms == the verbs show_help documents, with no overlap")

    # CONTROL, three ways, on COPIES so no tracked file is ever mutated. Each plants
    # one of the three failure shapes and requires the report to name it.
    with harness.temp_dir() as ctl:
        router, legacy = ctl / "run.sh", ctl / "legacy.sh"
        shutil.copyfile(RUN, router)
        shutil.copyfile(SRC, legacy)

        # (a) a verb served by both halves.
        plant(gate, router, r"^PORTED_VERBS=\(\)$", "PORTED_VERBS=(quality)", "the overlap half")
        if "overlap quality" in verb_findings(gate, router, legacy):
            gate.ok(
                "CONTROL: a verb in both PORTED_VERBS and the legacy dispatcher is "
                "reported as an overlap"
            )
        else:
            gate.no(
                "CONTROL: an overlapping verb was NOT reported; the disjointness half "
                "proves nothing"
            )
        shutil.copyfile(RUN, router)

        # (b) a documented verb nothing dispatches.
        plant(gate, legacy, r"^        clean\) clean ;;$", "", "the set-equality half")
        if "documented-but-unreachable clean" in verb_findings(gate, router, legacy):
            gate.ok(
                "CONTROL: deleting a dispatch arm for a documented verb is reported as unreachable"
            )
        else:
            gate.no("CONTROL: an orphaned verb was NOT reported; the set equality proves nothing")
        shutil.copyfile(SRC, legacy)

        # (c) a subcommand that exists but is undocumented -- the seven this gate found.
        plant(gate, legacy, r"^  fix shell           .*$", "", "the second-level half")
        if "dispatched-but-undocumented fix/shell" in verb_findings(gate, router, legacy):
            gate.ok(
                "CONTROL: deleting a help line for a live SUBCOMMAND is reported, so the "
                "second level is really checked"
            )
        else:
            gate.no(
                "CONTROL: an undocumented subcommand was NOT reported; the second-level "
                "half proves nothing"
            )
    gate.tally_finish("the verb partition")


def test_the_router_stays_a_router(gate):
    """The ceiling, and the one arm whose target has to exist."""
    # `wc -l`, which counts NEWLINES: a final line with no terminator is not counted
    # by either, so the two numbers cannot drift on a file the formatter has seen.
    router_lines = RUN.read_bytes().count(b"\n")
    if router_lines <= ROUTER_LINE_CEILING:
        gate.ok(
            "run.sh is still a router (%d lines, ceiling %d)" % (router_lines, ROUTER_LINE_CEILING)
        )
    else:
        gate.no(
            "run.sh has grown to %d lines; the ceiling is %d and logic belongs on one "
            "side or the other" % (router_lines, ROUTER_LINE_CEILING)
        )
    # The Python arm names a module that has to exist, or the first port fails with
    # ModuleNotFoundError and a verb nobody can reach.
    if "python3 -m rediacc_ci" in read(RUN) and PY_PACKAGE_INIT.is_file():
        gate.ok("the router's Python arm names rediacc_ci, and that package is on disk")
    else:
        gate.no(
            "the router's Python arm and .ci/rediacc_ci/__init__.py disagree; the ported "
            "half cannot work"
        )
    gate.tally_finish("the router stays a router")


# The fixture for the ADDED case. Every line in it is here because one of the
# twin's comments says a simpler rule reads it wrong. See the module docstring.
TRAP_ROUTER = """#!/bin/bash
PORTED_VERBS=()

main() {
    case "${1:-}" in
        # commented) not-an-arm ;;
        www | provision) exec elsewhere "$@" ;;
        -h | --help) show_help ;;
        alpha)
            shift
            # The docker-group route: an INNER case whose arms sit at the same
            # indent as a real subcommand, and whose arms are numbers.
            case "$_route" in
                0) keep_going ;;
                2) exit 2 ;;
            esac
            case "${1:-}" in
                one) alpha_one ;;
                two | "") alpha_two ;;
                *) exit 1 ;;
            esac
            ;;
        *) exec legacy "$@" ;;
    esac
}
"""

TRAP_HELP = """show_help() {
    cat <<EOF
Usage: ./run.sh [COMMAND]

  alpha one           Do the first thing
  alpha two           Do the second thing
  beta <cmd>          up | status | doctor
  gamma [--check]     Prepare the thing, whose prose mentions one word per line
  delta               A verb with no subcommand at all
  Usage: ./run.sh alpha [one|two [nested|group]|three]
EOF
}
"""


def test_the_extractors_survive_the_traps_the_awk_documents(gate):
    """ADDED BY THE PORT. Four extractors reimplemented from awk owe this.

    THE TREE IS NOT A CONTROL FOR A REWRITE. Checked only against today's `run.sh`
    the Python and the awk agree by construction, because the Python was written
    while reading that tree. What has to hold is the RULE, so this drives a fixture
    whose expected answer is written out in full and whose every line is one of the
    shapes the twin's comments name as the reason a rule is not simpler.

    BOTH DIRECTIONS. The negative half is the one that matters most here: an
    extractor that returned everything would satisfy every "is this present" check
    in the file, so the assertions are EQUALITY against a complete set rather than
    membership.
    """
    arms = arms_of(TRAP_ROUTER)
    expect_arms = {
        "TOP www",
        "TOP provision",
        "TOP alpha",
        "SUB alpha/one",
        "SUB alpha/two",
    }
    gate.assert_eq(
        arms,
        expect_arms,
        "arms_of: depth decides the level, `*`/`-h`/numeric arms and comments are not verbs",
    )
    gate.ok(
        "arms_of: the inner numeric case at subcommand indent contributes NO verb, and "
        "`www | provision` splits into two (%d arm(s))" % len(arms)
    )

    documented = documented_in(TRAP_HELP)
    expect_doc = {
        "TOP alpha",
        "SUB alpha/one",
        "SUB alpha/two",
        "TOP beta",
        "SUB beta/up",
        "SUB beta/status",
        "SUB beta/doctor",
        "TOP gamma",
        "TOP delta",
    }
    gate.assert_eq(
        documented,
        expect_doc,
        "documented_in: two spaces end the signature, `<cmd>` enumerates, `[--check]` does not",
    )
    gate.ok(
        "documented_in: `gamma [--check]` yields no subcommand named `Prepare`, and "
        "`beta <cmd>` yields its three (%d entry/entries)" % len(documented)
    )

    usage = usage_of(TRAP_HELP, "alpha")
    gate.assert_eq(
        usage,
        {"one", "two", "three"},
        "usage_of: the NESTED group is removed, and `three` after it survives",
    )
    gate.ok("usage_of: `two [nested|group]|three` keeps three and drops the nested pair")

    # THE NEGATIVE CONTROL FOR THE READER ITSELF. A file with no `main()` and no
    # `show_help()` must yield NOTHING, not a partial parse of whatever it holds --
    # an extractor that reads arms outside `main()` would report the legacy file's
    # helper functions as verbs.
    stray = 'helper() {\n    case "$1" in\n        ghost) : ;;\n    esac\n}\n'
    gate.assert_eq(arms_of(stray), set(), "arms_of reads main() and nothing else")
    gate.assert_eq(documented_in(stray), set(), "documented_in reads show_help() and nothing else")
    gate.assert_eq(usage_of(stray, "alpha"), set(), "usage_of finds no line to read")
    gate.ok("CONTROL: a file with neither entry point yields three EMPTY sets, not a partial parse")

    gate.tally_finish("the reimplemented extractors")
