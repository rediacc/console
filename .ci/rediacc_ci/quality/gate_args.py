"""Refuse an argument a gate does not take, by name, with exit 2.

Called from a gate module's own entry, the one `python3 -m rediacc_ci.quality.<x>` runs:

    if __name__ == "__main__":
        from rediacc_ci.quality import gate_args

        gate_args.parse("check_npmrc.py", sys.argv[1:], switches=("--selftest",))
        raise SystemExit(main(sys.argv[1:]))

and, through `.ci/scripts/quality/_gate_args.py`, from the entry points in that directory that still run a module by path.

WHY THIS EXISTS. 138 of the 146 entry points here read `sys.argv` by hand: `"--selftest" in args`, `args.index("--root")`, and nothing that looks at what is LEFT. So `npm run check:ci-record-paths -- --update` exited 0 having done nothing, because the gate has no `--update` and the probe only asked about the flags it knew. A typo for a real flag (`--write-basline`) does the same: the gate runs its plain check, prints green, and the author believes the baseline was written. That is a gate that passes without doing what the caller asked.

THE CONTRACT, the one `check_record_paths.py` carries in its own `parse_args`:

  * a SWITCH is a bare flag (`--selftest`);
  * a VALUED flag takes the next argument (`--root <dir>`), and a missing value, or a value that itself starts with `--`, is refused rather than swallowing the next flag;
  * a VARIADIC flag takes every bare argument after it up to the next `--flag` (`--paths a b/ c/*.sh`) and needs at least one;
  * `equals` names the valued flags that ALSO accept the `--flag=value` spelling, because a module that only reads `--flag value` would otherwise ignore `--flag=value` silently, which is the failure this file exists to end;
  * `positional` is a label (`"<path>"`) when bare arguments are taken, and None when they are not;
  * anything else exits 2 on stderr as `<prog>: unknown argument '<arg>' (accepted: ...)`, naming the whole accepted set so the fix is one read away.

THE PARSE HAPPENS BEFORE ANY WORK, in the entry point and not in the module's `main`, so a refused argument costs no gate run and the library `main(argv)` that tests drive in-process keeps its signature. The accepted set is declared per entry point and must match what the module reads: a flag the module handles but the entry point does not declare is now refused, so declare it; a flag declared but never read would be accepted and ignored, so read the module's `main` before declaring one.

`problem` is the pure half, returning the message or "" so a test can drive it without catching `SystemExit`.
"""

from __future__ import annotations

import sys
from typing import NamedTuple


class Parsed(NamedTuple):
    """What parsed: the argv exactly as given, plus the switches, valued flags (last wins) and bare arguments seen."""

    argv: list[str]
    switches: frozenset[str]
    values: dict[str, str]
    positionals: list[str]


def accepted_text(
    switches: tuple[str, ...],
    valued: tuple[str, ...],
    equals: tuple[str, ...],
    positional: str | None,
    variadic: tuple[str, ...] = (),
) -> str:
    """The `accepted: ...` clause of a refusal, in declaration order."""
    parts = list(switches)
    parts += ["%s <value>" % flag for flag in valued]
    parts += ["%s <value>..." % flag for flag in variadic]
    parts += ["%s=<value>" % flag for flag in equals]
    if positional:
        parts.append(positional)
    return "accepted: %s" % (", ".join(parts) if parts else "no arguments")


def scan(
    argv: list[str],
    switches: tuple[str, ...],
    valued: tuple[str, ...],
    equals: tuple[str, ...],
    positional: str | None,
    variadic: tuple[str, ...] = (),
) -> tuple[frozenset[str], dict[str, str], list[str], str]:
    """`(switches, values, positionals, problem)`; `problem` is "" when every argument parses."""
    hint = accepted_text(switches, valued, equals, positional, variadic)
    seen: set[str] = set()
    values: dict[str, str] = {}
    rest: list[str] = []
    k = 0
    while k < len(argv):
        arg = argv[k]
        flag, eq, inline = arg.partition("=")
        if arg in switches:
            seen.add(arg)
        elif arg in variadic:
            taken = []
            while k + 1 < len(argv) and not argv[k + 1].startswith("--"):
                k += 1
                taken.append(argv[k])
            if not taken:
                return frozenset(seen), values, rest, "%s needs a value (%s)" % (arg, hint)
            values[arg] = " ".join(taken)
        elif arg in valued:
            if k + 1 >= len(argv) or argv[k + 1].startswith("--"):
                return frozenset(seen), values, rest, "%s needs a value (%s)" % (arg, hint)
            k += 1
            values[arg] = argv[k]
        elif eq and flag in equals:
            values[flag] = inline
        elif positional and not arg.startswith("-"):
            rest.append(arg)
        else:
            return frozenset(seen), values, rest, "unknown argument %r (%s)" % (arg, hint)
        k += 1
    return frozenset(seen), values, rest, ""


def problem(
    argv: list[str],
    *,
    switches: tuple[str, ...] = (),
    valued: tuple[str, ...] = (),
    equals: tuple[str, ...] = (),
    positional: str | None = None,
    variadic: tuple[str, ...] = (),
) -> str:
    """The first problem with `argv` against the declared set, or "" when it parses."""
    return scan(argv, switches, valued, equals, positional, variadic)[3]


def parse(
    prog: str,
    argv: list[str],
    *,
    switches: tuple[str, ...] = (),
    valued: tuple[str, ...] = (),
    equals: tuple[str, ...] = (),
    positional: str | None = None,
    variadic: tuple[str, ...] = (),
) -> Parsed:
    """Parse `argv` against the declared set, or print the refusal on stderr and exit 2."""
    seen, values, rest, issue = scan(argv, switches, valued, equals, positional, variadic)
    if issue:
        print("%s: %s" % (prog, issue), file=sys.stderr)
        raise SystemExit(2)
    return Parsed(list(argv), seen, values, rest)
