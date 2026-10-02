#!/usr/bin/env python3
"""Assert the sanctioned-command registry still says something true.

A registry row is a rule agents are held to, so a row that has quietly stopped matching is worse than no row: it reads as an active guard while guarding nothing. Three things are checked per row, and all three are about the row being HONEST rather than about its content:

  * its own `example` must still match its `pattern` -- otherwise the rule is
    dead and nobody can tell by reading it;
  * its `counter` (a legitimately different command) must NOT match -- an
    over-broad pattern blocks real work, gets disabled, and takes the rule with
    it;
  * any tool named in `use` must exist on disk -- pointing an agent at a
    replacement that is not there turns a block into a dead end.

The `CI_READ_VERBS` rows (raw CI reads, refused by `block_raw_ci_read`) get the same three checks through the same classifier the guard uses (`ci_read_match`), held one notch tighter: the example must be refused by THAT row rather than by any row, since rows are ordered and a broader row above it would otherwise shadow it unnoticed; the counter must be refused by NO row; and every
`--flag` in `use` must appear in `ci-trace.py --help`, because a refusal that names a flag the tracer does not have sends the reader to an argparse error instead of an answer.

Called by `rediacc_ci.quality.ci_watch_recipe` as `python3 <path> <registry> <root>`; kept as its own file, which is how the retired bash twin invoked it too.
"""

import importlib.util
import pathlib
import re
import subprocess
import sys

TRACE_REL = ".ci/scripts/ci/ci-trace.py"
FLAG = re.compile(r"(?<![\w-])--[a-z][a-z-]*")


def _trace_flags(root):
    """Every `--flag` the tracer's own --help prints, or None when the help cannot be read."""
    try:
        proc = subprocess.run(
            [sys.executable, str(root / TRACE_REL), "--help"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return set(FLAG.findall(proc.stdout))


def check_read_verbs(mod, root, flags):
    """The problems with the `CI_READ_VERBS` rows; empty when every row is honest."""
    bad: list[str] = []
    rows = getattr(mod, "CI_READ_VERBS", None)
    if not rows:
        return ["CI_READ_VERBS: missing or empty, so block_raw_ci_read refuses nothing"]
    # A malformed row is a finding that names it, not a KeyError that crashes the gate (per-commit review d7ccc9d7.1).
    required = ("name", "match", "use", "why", "example", "counter")
    malformed = [
        "CI_READ_VERBS row %d (%s): missing %s"
        % (
            i,
            row.get("name", "?") if isinstance(row, dict) else "?",
            ", ".join(k for k in required if not isinstance(row, dict) or k not in row),
        )
        for i, row in enumerate(rows)
        if not isinstance(row, dict) or any(k not in row for k in required)
    ]
    if malformed:
        return malformed
    names = [row["name"] for row in rows]
    bad.extend(
        "%s: the name is used by more than one row" % n
        for n in sorted(set(names))
        if names.count(n) > 1
    )
    for row in rows:
        name = row["name"]
        try:
            re.compile(row["match"])
        except re.error as err:
            bad.append("%s: the match pattern does not compile: %s" % (name, err))
            continue
        hit, _ident = mod.ci_read_match(row["example"])
        if hit is None:
            bad.append(
                "%s: its own example is not refused -- a dead rule reading as a live one" % name
            )
        elif hit["name"] != name:
            bad.append("%s: its example is refused by %s, which shadows it" % (name, hit["name"]))
        miss, _ident = mod.ci_read_match(row["counter"])
        if miss is not None:
            bad.append(
                "%s: its counter-example is refused (by %s), so the carve-out is gone"
                % (name, miss["name"])
            )
        if "ci-trace.py" not in row["use"]:
            bad.append("%s: its use line does not name %s" % (name, TRACE_REL))
        bad.extend(
            "%s: names a replacement that does not exist: %s" % (name, tok)
            for tok in row["use"].split()
            if tok.endswith((".py", ".sh")) and not (root / tok).exists()
        )
        if flags is None:
            continue
        bad.extend(
            "%s: its use line names %s, which %s --help does not list" % (name, flag, TRACE_REL)
            for flag in FLAG.findall(row["use"])
            if flag not in flags
        )
    if flags is None:
        bad.append("%s --help could not be read, so no use flag was verified" % TRACE_REL)
    return bad


def main(argv):
    if len(argv) != 3:
        print("usage: check_sanctioned_registry.py <registry.py> <repo-root>")
        return 2
    spec = importlib.util.spec_from_file_location("sanctioned", argv[1])
    if spec is None or spec.loader is None:
        print("could not load the registry module")
        return 1
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    root = pathlib.Path(argv[2])

    bad = []
    for row, rx in mod.compiled():
        name = row["name"]
        if not rx.search(row["example"]):
            bad.append(
                "%s: its own example no longer matches its pattern -- a dead rule "
                "reading as a live one" % name
            )
        if rx.search(row["counter"]):
            bad.append("%s: its counter-example matches, so the pattern is over-broad" % name)
        bad.extend(
            "%s: names a replacement that does not exist: %s" % (name, tok)
            for tok in row["use"].split()
            if tok.endswith((".py", ".sh")) and not (root / tok).exists()
        )
    bad.extend(check_read_verbs(mod, root, _trace_flags(root)))
    if bad:
        print("\n".join(bad))
        return 1
    print(
        "%d row(s) self-consistent, %d CI read verb(s) self-consistent"
        % (len(mod.REGISTRY), len(mod.CI_READ_VERBS))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
