#!/usr/bin/env python3
"""Assert the sanctioned-command registry still says something true.

A registry row is a rule agents are held to, so a row that has quietly stopped
matching is worse than no row: it reads as an active guard while guarding
nothing. Three things are checked per row, and all three are about the row
being HONEST rather than about its content:

  * its own `example` must still match its `pattern` -- otherwise the rule is
    dead and nobody can tell by reading it;
  * its `counter` (a legitimately different command) must NOT match -- an
    over-broad pattern blocks real work, gets disabled, and takes the rule with
    it;
  * any tool named in `use` must exist on disk -- pointing an agent at a
    replacement that is not there turns a block into a dead end.

Called by check-ci-watch-recipe.sh; kept as a file rather than an inline
heredoc so shfmt and shellcheck see plain shell in the caller.
"""

import importlib.util
import pathlib
import sys


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
            bad.append(
                "%s: its counter-example matches, so the pattern is over-broad" % name
            )
        for tok in row["use"].split():
            if tok.endswith((".py", ".sh")) and not (root / tok).exists():
                bad.append("%s: names a replacement that does not exist: %s" % (name, tok))
    if bad:
        print("\n".join(bad))
        return 1
    print("%d row(s) self-consistent" % len(mod.REGISTRY))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
