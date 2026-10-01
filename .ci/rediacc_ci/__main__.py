"""`python3 -m rediacc_ci` -- this package's command line, and the only destination of `./run.sh` besides the media entry point.

WHAT THIS IS FOR. `./run.sh` is a router with two destinations: `.ci/media/media-entry.sh` for `provision` and `www`, and this package for every other verb. Its Python arm is one line:

    PYTHONPATH="$ROOT_DIR/.ci" exec python3 -m rediacc_ci "$@"

so `run.sh` hands this file the WHOLE argv, verb included. The legacy bash dispatcher (`.ci/legacy/run-legacy.sh`) is gone: its last verbs moved here when its verb table emptied, and `rediacc_ci/core/run_verbs.py` holds the entry functions for service, account, rotation, worktree, devbox, drill, quality, fix, clean and help.

THE TABLE IS DATA, NOT CONTROL FLOW. The verb set has to be INTROSPECTABLE: `names()` is the accessor the gate test reads to prove every verb the help documents is served and every served verb is documented, in both directions. A dispatch written as a chain of `if verb == ...` has no such accessor.

THE `help` VERB IS THE FRONT DOOR. No verb at all, `-h` and `--help` run it when the table registers one, which prints the full command reference (`./run.sh help` before the legacy file was deleted), and an unknown verb runs its `unknown_main` (the error, the reference, exit 1). A table without a `help` row falls back to a listing DERIVED from the table, with usage errors on stderr and exit 2; that fallback is what the
fixture package in tests/test_main.py exercises, because it carries one probe verb and nothing else.

THE HANDLER IS RESOLVED LAZILY, by dotted name, at the moment its verb is dispatched. `rediacc_ci/__init__.py` refuses to re-export its submodules for a stated reason -- it is imported by a vacuity fixture whose whole point is that most of the tree is absent -- and a table that imported every handler at module scope would undo that decision one row at a time.
"""

import dataclasses
import importlib
import sys

from rediacc_ci.well_known import WEB_IMAGE_REPO

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


# THE VERB TABLE. One row per top-level verb `./run.sh` forwards here. `provision` and `www` are not rows: the router sends both to `.ci/media/media-entry.sh`, which stays bash by design.
#
# THE NEXT LINE IS MATCHED LITERALLY BY tests/test_main.py, which builds a throwaway package around a copy of this file with one probe verb planted in place of the table. Keep it on one line, in this spelling; the fixture refuses to run rather than testing nothing if the replacement stops matching.
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
    Verb(
        name="service",
        summary=("start | stop | status | logs for " + WEB_IMAGE_REPO + " and RustFS"),
        module="rediacc_ci.core.run_verbs",
        entry="service_main",
    ),
    Verb(
        name="account",
        summary="dev | db | test | stop | reset | seed-demo | totp for the account server",
        module="rediacc_ci.core.run_verbs",
        entry="account_main",
    ),
    Verb(
        name="rotation",
        summary="credential rotation (private/account/scripts/rotation)",
        module="rediacc_ci.core.run_verbs",
        entry="rotation_main",
    ),
    Verb(
        name="worktree",
        summary="manage git worktrees (create, switch, prune, list)",
        module="rediacc_ci.core.run_verbs",
        entry="worktree_main",
    ),
    Verb(
        name="devbox",
        summary="up | status | url | stop | proxy | remove | shell | exec | doctor | logs",
        module="rediacc_ci.core.run_verbs",
        entry="devbox_main",
    ),
    Verb(
        name="drill",
        summary="scripted walkthroughs: universe | transfer | license | backup",
        module="rediacc_ci.core.run_verbs",
        entry="drill_main",
    ),
    Verb(
        name="quality",
        summary="run the quality checks (lint, format, types, ..., all)",
        module="rediacc_ci.core.run_verbs",
        entry="quality_main",
    ),
    Verb(
        name="fix",
        summary="auto-fix formatting, lint and shell formatting",
        module="rediacc_ci.core.run_verbs",
        entry="fix_main",
    ),
    Verb(
        name="clean",
        summary="clean build artifacts",
        module="rediacc_ci.core.run_verbs",
        entry="clean_main",
    ),
    Verb(
        name="help",
        summary="print the full command reference",
        module="rediacc_ci.core.run_verbs",
        entry="help_main",
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

    `table` is a test seam and nothing else: a seam that injects the real production code path is a better answer than a fake verb registered to make the tests pass, and it is how the dispatch cases run against a table holding one probe verb.
    """
    registry = VERBS if table is None else table
    front_door = next((verb for verb in registry if verb.name == "help"), None)

    if not argv and front_door is not None:
        return _finish(front_door, _resolve(front_door)([]))

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
        if front_door is not None:
            return _finish(front_door, _resolve(front_door)([]))
        print(format_help(registry))
        return 0

    match = next((verb for verb in registry if verb.name == verb_name), None)
    if match is None and front_door is not None:
        # The legacy dispatcher's answer: the error, the full reference, exit 1.
        unknown = _resolve(dataclasses.replace(front_door, entry="unknown_main"))
        return _finish(front_door, unknown([verb_name]))

    if match is None:
        print("%s: unknown verb: %s" % (PROGRAM, verb_name), file=sys.stderr)
        known = names(registry)
        if known:
            print("%s: known verbs: %s" % (PROGRAM, " ".join(known)), file=sys.stderr)
        else:
            print(
                "%s: no verbs are registered." % PROGRAM,
                file=sys.stderr,
            )
        return EXIT_USAGE

    # THE ONE `--` THIS PROGRAM CONSUMES, and only when it sits immediately after the verb. `./run.sh <verb> -- --flag "a b"` is how a person stops an outer
    # tool from claiming `--flag`, so the separator is this dispatcher's to eat;
    # stripping it once here is one line, and leaving it for every handler to strip is the same line written once per verb, differently each time. Everything else passes through byte for byte, INCLUDING a second `--`, which belongs to the handler's own argument grammar.
    if rest and rest[0] == "--":
        rest = rest[1:]

    return _finish(match, _resolve(match)(rest))


def _finish(verb: Verb, code) -> int:
    """A handler's return value as an exit status."""
    if code is None:
        # A handler that falls off its end succeeded. Spelled out because the alternative -- `return code` -- makes `None` an exit status of 0 by accident of SystemExit's coercion rather than by decision.
        return 0
    if not isinstance(code, int):
        print(
            "%s: %s returned %r, which is not an exit code" % (PROGRAM, verb.name, code),
            file=sys.stderr,
        )
        return 1
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
