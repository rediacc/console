"""Port of `.ci/scripts/test/gates/test-run-sh.sh`.

Controls for `./run.sh`, the entry point every other command goes through.

WHY IT EXISTS. The twin was written after two defects had already lived in that file precisely because it had no test:

  1. `quality all` logged a warning and returned SUCCESS when shfmt was missing, so on any machine without shfmt the command reported green having run no shell gate at all.
  2. `fix shell` formatted with whatever shfmt was on PATH while the gate verified with the pinned one, so the fixer could produce a state the checker rejects.

HERMETIC BY CONSTRUCTION, and the port keeps that: no docker, no network, no submodules. Every control is either a DISPATCH assertion (a real `./run.sh <verb>` whose exit code is read) or a SOURCE-LEVEL invariant. Nothing here runs a real gate; that is what the gates themselves are for.

TWO FILES, AND THE DISTINCTION IS LOAD BEARING IN BOTH DIRECTIONS. Since 2026-10-01 `./run.sh` is a router with two exits, the media entry point (`provision`, `www`) and `python3 -m rediacc_ci` (every other verb), and the bash dispatcher `.ci/legacy/run-legacy.sh` is deleted. The verbs it served are the entry functions in `.ci/rediacc_ci/core/run_verbs.py`:

    RUN  the router, and the thing a person or a workflow actually types. Every dispatch control drives this.
    SRC  the Python verb module, and the thing the source-level controls read. `quality_all` and `fix_shell` live there; grepping the router for them would find nothing and three controls would PASS on nothing found, which is the vacuous green this file exists to prevent.

THE PARTITION IS ROUTER ARMS PLUS THE VERBS TABLE, against `help`. The verbs the package dispatches are read from the code that dispatches them (`python3 -m rediacc_ci.core.run_verbs arms`: every row of `__main__.VERBS`, every key of a dispatch table), and the documented ones from `./run.sh help`. The per-verb `Usage:` lines are generated from the dispatch tables, so the third inventory the bash dispatcher kept by hand (and let drift) no longer exists to be checked.

THE REIMPLEMENTED EXTRACTORS OWE A CONTROL OF THEIR OWN. `arms_of` and `documented_in` are awk in the twin and Python here, so `test_the_extractors_survive_the_traps_the_awk_documents` drives them over a synthetic fixture with a known answer, including the shapes the twin's comments name as the reason each rule is written the way it is: an inner `case` whose numeric arms sit at the same INDENT as a real subcommand (depth decides the level, never indentation) and a help signature separated from its prose by TWO spaces (splitting on one reads the first word of the prose as a subcommand).

NO `REAL_TREE_TWIN`, AND IT IS CHECKED RATHER THAN ASSUMED. `test-run-sh.sh` makes no `mutex`/`reads` claim in `gates.lock.json`; what this module does to the real tree is read three files and run `./run.sh <verb>` four times and `./run.sh help` once; the only writes are into a temporary directory holding copies.

NO `XDIST_GROUP` for the same class of reason: no port is bound, no module global is mutated, and the environment overlay each lane probe uses is passed to one short-lived `bash -c` rather than set on this process.
"""

import os
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-run-sh.sh"

ROOT = paths.repo_root()
RUN = paths.from_root("run.sh")
SRC = paths.from_root(".ci", "rediacc_ci", "core", "run_verbs.py")
LEGACY = paths.from_root(".ci", "legacy", "run-legacy.sh")
LOCAL_COMMON = paths.from_root(".ci", "lib", "local-common.sh")
PY_PACKAGE_INIT = paths.from_root(".ci", "rediacc_ci", "__init__.py")

# A CEILING, NOT A STYLE RULE. A router that starts absorbing logic re-creates the file the split was undoing, one reasonable special case at a time.
ROUTER_LINE_CEILING = 120

# The lane decision, taken in a fresh shell that sources exactly what a real gate sources. Byte-for-byte the twin's, including the order of the three sources.
LANE_SNIPPET = (
    ". .ci/config/constants.sh; . .ci/scripts/lib/toolchain.sh; "
    ". .ci/lib/local-common.sh; gate_lane_decide"
)

BASH_FIX = "install bash; the subject is a bash router and a bash lane library"

# `arms_of`'s two shapes, transcribed from the awk. The first says a line looks like a case arm at all; the second says a line OPENS a case. Both are matched against the line with its leading indentation already removed, because case-nesting DEPTH decides the level and indentation is not allowed to.
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

    A FILE THAT CANNOT BE EXECUTED IS A VERDICT, NOT A TRACEBACK. `subprocess` raises `PermissionError` when the router has lost its `+x` bit, which arrives as an ERROR inside a helper and reads as harness flake; the bash twin gets a plain 126 from its shell. This turns the exception back into the statement the twin makes, and names the file, because the executable-bit control one
    section down is exactly the state that produces it.
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
    """`body <file> <function-name>`: the Python function's body, comment lines emptied.

    CODE ONLY, and the twin's header says why in a sentence worth keeping: an earlier draft grepped a fixed window and matched the word `log_warn` inside the COMMENT that explains the old behaviour, so the test failed on correct code -- the wrong direction for a control to fail in. The body ends at the first line that starts in column zero.
    """
    out = []
    opening = re.compile(r"^def %s\(" % re.escape(name))
    inside = False
    for line in source.splitlines():
        if not inside:
            if opening.match(line):
                inside = True
            continue
        if re.match(r"^[^ \t#]", line):
            break
        out.append(re.sub(r"^\s*#.*$", "", line))
    return "\n".join(out)


def bash_body(source: str, name: str) -> str:
    """The same extraction for a BASH function (`name() {` to the closing brace), comment lines emptied."""
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


def arms_of(source: str) -> set[str]:
    """The router's `main()` case arms as `"TOP <verb>"`.

    CASE-NESTING DEPTH DECIDES THE LEVEL, NEVER INDENTATION. The router has no inner `case` today; the rule is kept because a router that grows one must not report its numeric arms as verbs.
    """
    found: set[str] = set()
    inmain = False
    depth = 0
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
            # `*` is the fallback, `""` the bare-verb default, a leading `-` a flag alias of the verb beside it, a bare number an inner arm.
            if verb in ("", "*") or verb.startswith("-") or verb.isdigit():
                continue
            if depth == 1:
                found.add("TOP " + verb)
    return found


def documented_in(text: str) -> set[str]:
    """The help text's inventory as `"TOP <verb>"` / `"SUB <top>/<sub>"`.

    THE SIGNATURE IS THE PART BEFORE THE FIRST RUN OF TWO SPACES. Splitting on a single space reads the first word of the prose as a subcommand.
    """
    found: set[str] = set()
    for raw in text.splitlines():
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
        # `<cmd>` means "the subcommands are enumerated in the description", which is how devbox and worktree are written. Anything else in brackets is a PARAMETER (`<slug>`, `[opts]`), not a subcommand.
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


def package_arms(gate) -> set[str]:
    """What the package dispatches, read from the code that dispatches it: `python3 -m rediacc_ci.core.run_verbs arms`."""
    env = {"PYTHONPATH": str(paths.ci_dir())}
    result = harness.run(["python3", "-m", "rediacc_ci.core.run_verbs", "arms"], cwd=ROOT, env=env)
    if result.rc != 0:
        gate.log_fail(
            "reading the package's dispatch tables exited %d (stderr: %s); the partition "
            "would be computed against an empty set" % (result.rc, result.err.strip())
        )
    return {line.strip() for line in result.out.splitlines() if line.strip()}


def help_text(gate) -> str:
    """`./run.sh help`, the one inventory a person reads."""
    result = harness.run([str(RUN), "help"], cwd=ROOT)
    if result.rc != 0:
        gate.log_fail("./run.sh help exited %d; the documented set would be empty" % result.rc)
    return result.out


def level(entries: set[str], prefix: str) -> set[str]:
    """The `TOP `/`SUB ` slice of an extractor's output, with the tag removed."""
    return {e[len(prefix) :] for e in entries if e.startswith(prefix)}


def subs_of(entries: set[str], top: str) -> set[str]:
    return {e.split("/", 1)[1] for e in entries if e.startswith("SUB %s/" % top)}


def verb_findings(router_text: str, arms: set[str], documented_text: str) -> list[str]:
    """One line per problem, EMPTY when the router and the package partition the documented verbs.

    A findings FUNCTION rather than inline assertions, so the controls below can drive the same code against a deliberately broken COPY: an assertion that has never been seen to fire is not yet evidence of anything.

    NO EMPTY-STRING GUARD IS NEEDED HERE, and its absence is the one place the port is structurally safer than the twin. The twin pipes each half through `printf '%s\\n'`, where an EMPTY set is one blank line rather than zero lines, so without `sed '/^$/d'` on every side an empty half is reported as a finding about a verb whose name is the empty string. A Python set of zero
    elements has no such spelling.
    """
    router = level(arms_of(router_text), "TOP ")
    package = level(arms, "TOP ")
    documented = documented_in(documented_text)
    documented_top = level(documented, "TOP ")
    dispatched = router | package

    findings = ["overlap %s" % v for v in sorted(router & package)]
    findings += ["dispatched-but-undocumented %s" % v for v in sorted(dispatched - documented_top)]
    findings += ["documented-but-unreachable %s" % v for v in sorted(documented_top - dispatched)]

    # SECOND LEVEL, only for the verbs whose dispatch table lives in the package. `provision`, `www`, `rotation` and `worktree` delegate their whole subcommand tree to another program, so their documented subcommands are that program's inventory; demanding they appear as arms here would be wrong.
    for top in sorted({e[len("SUB ") :].split("/", 1)[0] for e in arms if e.startswith("SUB ")}):
        armed = subs_of(arms, top)
        described = subs_of(documented, top)
        findings += [
            "dispatched-but-undocumented %s/%s" % (top, s) for s in sorted(armed - described)
        ]
        findings += [
            "documented-but-unreachable %s/%s" % (top, s) for s in sorted(described - armed)
        ]
    return findings


def vacuity_findings(router: int, package: int, docs: int, subs: int, doc_subs: int) -> list[str]:
    """One line per way the extractors could be measuring NOTHING. Empty is the good case.

    ANTI-VACUITY BEFORE THE ASSERTION, because every claim `verb_findings` makes is "this set is empty" and an extractor that matched nothing satisfies all of them at once. A findings FUNCTION for the same reason `verb_findings` is one: the controls drive it against numbers they choose, so each clause is SEEN to fire rather than assumed to. Arguments in the order the messages print them.
    """
    findings: list[str] = []
    if docs <= 0:
        findings.append("help documents no verb, so both set comparisons are against an empty set")
    if router + package <= 0:
        findings.append(
            "nothing dispatches anything (router=%d package=%d); the partition is "
            "between two empty sets" % (router, package)
        )
    if not (doc_subs == 0 or subs > 0):
        findings.append(
            "help documents %d subcommand(s), but the package dispatch tables hold %d; "
            "the second level is checking nothing" % (doc_subs, subs)
        )
    return findings


def counts_of(gate) -> tuple[int, int, int, int, int]:
    """The five numbers `vacuity_findings` judges, read off the REAL tree.

    One function rather than two copies: the partition case asks whether today's tree is vacuous, and the control case asks the same question again as its negative half. Two transcriptions of the same extractor calls would be two chances to read a different tree.
    """
    arms = package_arms(gate)
    documented = documented_in(help_text(gate))
    return (
        len(level(arms_of(read(RUN)), "TOP ")),
        len(level(arms, "TOP ")),
        len(level(documented, "TOP ")),
        len({e for e in arms if e.startswith("SUB ")}),
        len({e for e in documented if e.startswith("SUB ")}),
    )


def test_an_unknown_verb_does_not_look_like_success(gate):
    """Dispatch. What the split must not change: the same argv reaches the same code."""
    exits(gate, "an unknown verb fails", 1, "definitely-not-a-verb")
    exits(gate, "an unknown devbox subcommand fails", 1, "devbox", "not-a-real-subcommand")
    exits(gate, "help succeeds", 0, "help")
    exits(gate, "devbox exec with no command fails", 1, "devbox", "exec", "--")
    gate.tally_finish("run.sh dispatch")


def test_quality_all_refuses_when_the_shell_gates_cannot_run(gate):
    """THE VACUOUS GREEN. A gate that cannot run must not report success.

    Both directions, which is what makes the pair a control rather than a wish: the warn-and-continue spelling must be ABSENT, and a failure path must be PRESENT. Either one alone is satisfied by a `quality_all` that does nothing at all.
    """
    quality_all = body(read(SRC), "quality_all")
    if not quality_all.strip():
        gate.log_fail(
            "quality_all was not extracted from %s, so both controls below would ask "
            "their question of an EMPTY string and both would answer whatever the empty "
            "string answers." % paths.relative_to_root(SRC)
        )
    if "log.warn" in quality_all:
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

    The nastiest shape of a version split is the one where the tool that is supposed to fix the problem creates it.
    """
    fix_shell = body(read(SRC), "fix_shell")
    if not fix_shell.strip():
        gate.log_fail(
            "fix_shell was not found in %s; the control below would search an empty "
            "body and PASSES on nothing found." % paths.relative_to_root(SRC)
        )
    if 'toolchain.acquire("shfmt")' in fix_shell:
        gate.ok("fix shell formats with the pinned binary, the one the gate verifies with")
    else:
        gate.no("fix shell takes shfmt from PATH; it can format into a state the gate rejects")
    if re.search(r'\[\s*"shfmt"', fix_shell):
        gate.no("CONTROL: fix_shell still calls a bare shfmt somewhere")
    else:
        gate.ok("CONTROL: no bare shfmt invocation survives in fix_shell")
    gate.tally_finish("fix_shell")


def lane(**overrides: str) -> str:
    """`gate_lane_decide` under an environment overlay, stdout only.

    THE OVERLAY IS ONE VARIABLE, exactly as `env VAR=1 bash -c ...` gives the twin.
    Clearing the others would be tidier and would let this module report a lane the twin does not see on a machine where one of them is already exported, which is a divergence invented by the port.
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
    should_route = bash_body(read(LOCAL_COMMON), "gate_lane_should_route")
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
    """Parse and permission bits on the router, the package imports, and the legacy dispatcher stays deleted.

    The router `exec`s the Python package, so a package that does not import fails on the FIRST verb anybody types, with the router named in the error and not the module at fault. A `run-legacy.sh` that reappeared would be a second, unrouted implementation of every verb.
    """
    if harness.run([bash_bin(), "-n", str(RUN)]).rc == 0:
        gate.ok("run.sh parses")
    else:
        gate.no("run.sh does not parse")
    if os.access(RUN, os.X_OK):
        gate.ok("run.sh is executable")
    else:
        gate.no("run.sh is not executable")
    imports = harness.run(
        ["python3", "-c", "import rediacc_ci.__main__, rediacc_ci.core.run_verbs"],
        cwd=ROOT,
        env={"PYTHONPATH": str(paths.ci_dir())},
    )
    if imports.rc == 0:
        gate.ok("the verb module imports")
    else:
        gate.no("the verb module does not import: %s" % imports.err.strip())
    if not LEGACY.exists():
        gate.ok("the legacy dispatcher stays deleted")
    else:
        gate.no(
            "the legacy dispatcher is back; the router does not reach it, so it is dead "
            "code beside the real verbs"
        )
    gate.tally_finish("both halves runnable")


def test_the_split_is_a_partition_of_the_documented_verb_set(gate):
    """SET EQUALITY PLUS DISJOINTNESS, in both directions, against `help`.

    `./run.sh <verb>` has two destinations -- the media entry point (the router's own arms) and the `rediacc_ci` package (its VERBS table) -- and the two ways a verb goes wrong are silent in OPPOSITE directions:

      AN ORPHAN. A verb documented in `help` and served by neither falls through to the package's "Unknown command" and is indistinguishable from a typo.
      AN OVERLAP. A verb served by BOTH is answered by whichever the router reaches first, so the second implementation is dead code that reads as live.

    SECOND LEVEL, NOT JUST TOP LEVEL. A check over top-level verbs alone would have missed the seven subcommands the dispatcher once served without documenting.
    """
    # ANTI-VACUITY BEFORE THE ASSERTION, because every claim here is "this set is empty" and an extractor that matched nothing satisfies all of them at once.
    router, package, docs, subs, doc_subs = counts_of(gate)
    vacuity = vacuity_findings(router, package, docs, subs, doc_subs)
    if vacuity:
        gate.no(
            "an extractor returned an EMPTY set; every assertion below would pass on "
            "nothing:\n%s" % "\n".join("    " + line for line in vacuity)
        )
    else:
        gate.ok(
            "the extractors see a real tree: %d router arm(s) + %d package verb(s) = "
            "%d dispatched, %d subcommand(s), %d documented verb(s)"
            % (router, package, router + package, subs, docs)
        )

    router_text, arms, documented = read(RUN), package_arms(gate), help_text(gate)
    findings = verb_findings(router_text, arms, documented)
    if findings:
        gate.no(
            "the verb sets do not partition:\n%s" % "\n".join("    " + line for line in findings)
        )
    else:
        gate.ok("router arms + package verbs == the verbs help documents, with no overlap")

    # CONTROL, three ways, on COPIES of the three inputs so no tracked file is ever mutated. Each plants one of the three failure shapes and requires the report to name it, and each plant is asserted to have LANDED: a substitution whose pattern stopped matching leaves the copy identical to the source, and the control would report PASS having planted nothing.

    # (a) a verb served by both halves.
    planted = plant_text(
        gate,
        router_text,
        r"^(        www\) exec )",
        r"        quality) exec elsewhere ;;\n\1",
        "the overlap half",
    )
    if "overlap quality" in verb_findings(planted, arms, documented):
        gate.ok("CONTROL: a verb in both the router and the package is reported as an overlap")
    else:
        gate.no(
            "CONTROL: an overlapping verb was NOT reported; the disjointness half proves nothing"
        )

    # (b) a documented verb nothing dispatches.
    if "TOP clean" not in arms:
        gate.log_fail(
            "THE PLANT DID NOT LAND: the package no longer dispatches `clean`, so the "
            "unreachable-verb control would plant nothing and pass for free"
        )
    if "documented-but-unreachable clean" in verb_findings(
        router_text, arms - {"TOP clean"}, documented
    ):
        gate.ok("CONTROL: deleting a dispatch row for a documented verb is reported as unreachable")
    else:
        gate.no("CONTROL: an orphaned verb was NOT reported; the set equality proves nothing")

    # (c) a subcommand that exists but is undocumented.
    undocumented = plant_text(
        gate, documented, r"^  fix shell           .*$", "", "the second-level half"
    )
    if "dispatched-but-undocumented fix/shell" in verb_findings(router_text, arms, undocumented):
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


def plant_text(gate, text: str, pattern: str, replacement: str, why: str) -> str:
    """Rewrite one line of a COPY, and REFUSE if the rewrite matched nothing.

    THE CONTROL'S OWN CONTROL, and it is the half the twin leaves implicit. Each plant is anchored to a literal line of the real input; when such a line is reworded the substitution silently becomes a no-op, the finding it was supposed to provoke never appears, and what reads as "the assertion does not fire" is really "the plant was never planted". Counting the substitution says which one happened.
    """
    planted, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count != 1:
        gate.log_fail(
            "THE PLANT DID NOT LAND: %r matched %d line(s), so %s would be tested against "
            "an UNMODIFIED copy. Re-anchor the pattern; do not weaken the assertion."
            % (pattern, count, why)
        )
    return planted


def test_the_vacuity_clauses_fire_and_the_real_numbers_are_not_a_failure(gate):
    """Both directions on all three clauses of `vacuity_findings`.

    A CLAUSE THAT HAS NEVER BEEN SEEN TO FIRE IS NOT YET A CHECK, so each of the three shapes it names is driven directly with numbers chosen to produce it, and today's real numbers are asserted NOT to fire, because three positives and no negative would be satisfied by a function that always fires.
    """
    for label, needle, counts in (
        ("an empty help is reported", "documents no verb", (2, 12, 0, 40, 40)),
        ("a tree where nothing dispatches is reported", "nothing dispatches", (0, 0, 18, 40, 40)),
        (
            "documented subcommands with no extracted dispatch table are reported",
            "second level is checking nothing",
            (2, 12, 18, 0, 40),
        ),
    ):
        if any(needle in finding for finding in vacuity_findings(*counts)):
            gate.ok("CONTROL: %s" % label)
        else:
            gate.no("CONTROL: %s -- the clause did NOT fire, so its green proves nothing" % label)

    live = vacuity_findings(*counts_of(gate))
    if not live:
        gate.ok("CONTROL: today's real numbers are not reported as vacuous either")
    else:
        gate.no(
            "CONTROL: the clause fires on the live tree, so the cases above prove "
            "nothing about it:\n%s" % "\n".join("    " + line for line in live)
        )
    gate.tally_finish("the vacuity clauses")


def test_the_router_stays_a_router(gate):
    """The ceiling over the router's lines, and the one arm whose target has to exist."""
    # `wc -l`, which counts NEWLINES: a final line with no terminator is not counted by either, so the two numbers cannot drift on a file the formatter has seen.
    router_lines = RUN.read_bytes().count(b"\n")
    if router_lines <= ROUTER_LINE_CEILING:
        gate.ok("run.sh is still a router (%d lines of %d)" % (router_lines, ROUTER_LINE_CEILING))
    else:
        gate.no(
            "run.sh has grown to %d lines; the ceiling is %d and logic belongs on one "
            "side or the other" % (router_lines, ROUTER_LINE_CEILING)
        )
    # The Python arm names a module that has to exist, or the first verb fails with ModuleNotFoundError and nothing is reachable.
    if "python3 -m rediacc_ci" in read(RUN) and PY_PACKAGE_INIT.is_file():
        gate.ok("the router's Python arm names rediacc_ci, and that package is on disk")
    else:
        gate.no(
            "the router's Python arm and .ci/rediacc_ci/__init__.py disagree; the verbs cannot work"
        )
    gate.tally_finish("the router stays a router")


# The fixture for the ADDED case. Every line in it is here because one of the twin's comments says a simpler rule reads it wrong. See the module docstring.
TRAP_ROUTER = """#!/bin/bash

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
        *) exec package "$@" ;;
    esac
}
"""

TRAP_HELP = """Usage: ./run.sh [COMMAND]

  alpha one           Do the first thing
  alpha two           Do the second thing
  beta <cmd>          up | status | doctor
  gamma [--check]     Prepare the thing, whose prose mentions one word per line
  delta               A verb with no subcommand at all
"""


def test_the_extractors_survive_the_traps_the_awk_documents(gate):
    """ADDED BY THE PORT. Two extractors reimplemented from awk owe this.

    THE TREE IS NOT A CONTROL FOR A REWRITE. Checked only against today's `run.sh` the Python and the awk agree by construction, because the Python was written while reading that tree. What has to hold is the RULE, so this drives a fixture whose expected answer is written out in full and whose every line is one of the shapes the twin's comments name as the reason a rule is not simpler.

    BOTH DIRECTIONS. The negative half is the one that matters most here: an extractor that returned everything would satisfy every "is this present" check in the file, so the assertions are EQUALITY against a complete set rather than membership.
    """
    arms = arms_of(TRAP_ROUTER)
    expect_arms = {"TOP www", "TOP provision", "TOP alpha"}
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

    # THE NEGATIVE CONTROL FOR THE READER ITSELF. A file with no `main()` must yield NOTHING, not a partial parse of whatever it holds: an extractor that reads arms outside `main()` would report a helper function's arms as verbs.
    stray = 'helper() {\n    case "$1" in\n        ghost) : ;;\n    esac\n}\n'
    gate.assert_eq(arms_of(stray), set(), "arms_of reads main() and nothing else")
    gate.assert_eq(documented_in("no help here\n"), set(), "documented_in finds no line to read")
    gate.ok("CONTROL: a file with no entry point yields EMPTY sets, not a partial parse")

    gate.tally_finish("the reimplemented extractors")
