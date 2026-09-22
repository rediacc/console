"""`python3 -m rediacc_ci` -- this package's command line, and the router's other half.

WHAT THIS IS FOR. `./run.sh` is a router with three destinations (the media entry point, this package, the legacy bash body). Its Python arm is one line:

    PYTHONPATH="$ROOT_DIR/.ci" exec python3 -m rediacc_ci "$@"

so `run.sh` hands this file the WHOLE argv, verb included, and every ported verb arrives here. Until this file existed that arm named a module that was not on disk: `run.sh` said so out loud in its own header rather than letting the first port discover it as a ModuleNotFoundError.

THE TABLE HOLDS TWO VERBS TODAY, AND THAT IS THE HONEST STATE. `setup` and `dev` have moved: they are the rows below and the two names in run.sh's `PORTED_VERBS`, and `.ci/legacy/run-legacy.sh` has neither a `setup` arm nor a `dev` one, nor either function body. Every other top-level verb is still the legacy dispatcher's. Registering a name here that the legacy dispatcher also
serves would create exactly the overlap the whole split exists to prevent -- the port looks like it works while the code it replaced is what actually ran -- so a name arrives here only when the verb genuinely moves, in the same change that deletes its legacy arm and adds it to `PORTED_VERBS`.

That invariant is checked rather than trusted: .ci/scripts/test/gates/test-run-sh.sh section 6 fails an orphan (a name here with no legacy arm removed) and an overlap (a name served twice) alike. `--help`, the no-verb path and the unknown-verb path are the parts a person meets first and the parts a stub would fake, and they are real here and tested against the real command.

WHY A TABLE AND NOT A CHAIN OF `if verb == ...`. The verb set has to be
INTROSPECTABLE. `--help` derives its listing from the table rather than from a second hand-maintained string (the legacy body's three inventories -- arms, `show_help`, per-verb `Usage:` -- disagreed with each other for months, which is what .ci/scripts/test/gates/test-run-sh.sh section 6 now refuses), and the next workstream's boxes read the set programmatically. `names()` is the
accessor; a dispatch written as control flow has no such thing.

THE HANDLER IS RESOLVED LAZILY, by dotted name, at the moment its verb is dispatched. `rediacc_ci/__init__.py` refuses to re-export its submodules for a stated reason -- it is imported by a vacuity fixture whose whole point is that most of the tree is absent -- and a table that imported every handler at module scope would undo that decision one row at a time. `--help` therefore
imports nothing at all.
"""

import dataclasses
import importlib
import sys

# How this program is spelled in its own messages. `./run.sh <verb>` is what a person actually types for a ported verb, but a message naming run.sh would be wrong for the verbs reached directly (and for `run.sh`'s own error paths), so the module form is used and run.sh is named in the help text instead.
PROGRAM = "python3 -m rediacc_ci"

# Usage errors -- no verb, an unknown verb -- exit 2, matching every other argv dispatcher in this package (core/env.py:398, core/ports.py:271). 1 stays what it has always been: a real verdict from a handler that ran.
EXIT_USAGE = 2


@dataclasses.dataclass(frozen=True)
class Verb:
    """One top-level verb served by this package.

    `module` and `entry` are STRINGS, not a callable: a callable in the table would be imported when the table is built, which is what the lazy-resolution paragraph in the module docstring exists to avoid. `entry` names a function taking the verb's remaining argv and returning an exit code.
    """

    name: str
    summary: str
    module: str
    entry: str = "main"


# THE VERB TABLE. One row per top-level verb `./run.sh` forwards here, and the row must land in the SAME change that adds the name to `PORTED_VERBS` in run.sh and deletes its arm from .ci/legacy/run-legacy.sh -- test-run-sh.sh section 6 fails an orphan and an overlap alike, so a half-done port is red rather than ambiguous.
#
# THE NEXT LINE IS MATCHED LITERALLY BY tests/test_main.py, which builds a throwaway package around a copy of this file with one probe verb planted in place of the empty tuple -- the only way to exercise dispatch while the real table is empty. Keep it on one line, in this spelling; the fixture refuses to run rather than testing nothing if the replacement stops matching.
VERBS: tuple[Verb, ...] = (
    Verb(
        name="setup",
        summary="prepare this machine and hand back a URL",
        module="rediacc_ci.setup.machine",
    ),
    Verb(
        name="dev",
        summary="start the www (marketing site) development server",
        module="rediacc_ci.dev.www",
    ),
)


def names(table: tuple[Verb, ...] | None = None) -> list[str]:
    """The registered verb names, in table order. The introspection seam."""
    return [verb.name for verb in (VERBS if table is None else table)]


def format_help(table: tuple[Verb, ...] | None = None) -> str:
    """The `--help` text, DERIVED from the table rather than written twice."""
    registry = VERBS if table is None else table
    lines = ["usage: %s <verb> [args...]" % PROGRAM, "", "Verbs:"]
    if registry:
        width = max(len(verb.name) for verb in registry)
        lines += ["  %-*s  %s" % (width, verb.name, verb.summary) for verb in registry]
    else:
        # SAY IT, do not print an empty section. An empty list under a heading reads as "the listing broke"; this reads as the state it is.
        lines.append("  (none yet -- no verb has been ported into this package)")
    lines += [
        "",
        "Options:",
        "  -h, --help  print this and exit",
        "",
        "A verb listed above is also reachable as `./run.sh <verb>`: run.sh's",
        "PORTED_VERBS table forwards it here with the rest of its arguments.",
    ]
    return "\n".join(lines)


def _resolve(verb: Verb):
    """Import `verb.module` and return its `verb.entry` callable.

    Both failure modes are a BROKEN REGISTRATION rather than user error, so they raise with the row's own fields in the message: the traceback that follows names this file and the module that would not load, which is what a person fixing the table needs. Catching them here and printing a tidy line would hide the import error underneath it.
    """
    module = importlib.import_module(verb.module)
    return getattr(module, verb.entry)


def main(argv: list[str], table: tuple[Verb, ...] | None = None) -> int:
    """Dispatch `argv` (verb first, exactly as run.sh forwards it).

    `table` is a test seam and nothing else: the real table is empty today, so every dispatch case would otherwise be untestable, and a seam that injects the real production code path is a better answer than a fake verb registered to make the tests pass.
    """
    registry = VERBS if table is None else table

    if not argv:
        # A USAGE ERROR, NOT A TRACEBACK, and not a silent 0 either. stderr, because stdout belongs to whatever the verb would have printed.
        print("%s: no verb given." % PROGRAM, file=sys.stderr)
        print(
            "%s: run `%s --help` for the verbs this package serves." % (PROGRAM, PROGRAM),
            file=sys.stderr,
        )
        return EXIT_USAGE

    verb_name = argv[0]
    rest = list(argv[1:])

    if verb_name in ("-h", "--help"):
        print(format_help(registry))
        return 0

    match = next((verb for verb in registry if verb.name == verb_name), None)
    if match is None:
        print("%s: unknown verb: %s" % (PROGRAM, verb_name), file=sys.stderr)
        known = names(registry)
        if known:
            print("%s: known verbs: %s" % (PROGRAM, " ".join(known)), file=sys.stderr)
        else:
            print(
                "%s: no verbs are registered yet; every verb is still served by "
                ".ci/legacy/run-legacy.sh." % PROGRAM,
                file=sys.stderr,
            )
        return EXIT_USAGE

    # THE ONE `--` THIS PROGRAM CONSUMES, and only when it sits immediately after the verb. `./run.sh <verb> -- --flag "a b"` is how a person stops an outer
    # tool from claiming `--flag`, so the separator is this dispatcher's to eat;
    # stripping it once here is one line, and leaving it for every handler to strip is the same line written once per verb, differently each time. Everything else passes through byte for byte, INCLUDING a second `--`, which belongs to the handler's own argument grammar.
    if rest and rest[0] == "--":
        rest = rest[1:]

    code = _resolve(match)(rest)
    if code is None:
        # A handler that falls off its end succeeded. Spelled out because the alternative -- `return code` -- makes `None` an exit status of 0 by accident of SystemExit's coercion rather than by decision.
        return 0
    if not isinstance(code, int):
        print(
            "%s: %s returned %r, which is not an exit code" % (PROGRAM, verb_name, code),
            file=sys.stderr,
        )
        return 1
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
