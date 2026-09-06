"""The guard registry. A guard declares itself by BEING here.

WHY A SCAN AND NOT A LIST. Section 7 of `docs/ci-overhaul/08-driver-contract.md`
gives "modular and dynamic" its only checkable meaning: "Adding a gate, an
allowlist entry, or a hook guard requires no edit to any workflow file, any
runner file, or any dispatcher file... the guard declares itself as a module in
the hook registry." A hand-written tuple in this file would be exactly the
second edit that rule forbids, and it would rot the same way the hook-coverage
baseline rotted (`check-hook-integrity.sh` records five `gh_case` cases sitting
in a gap list they had not been in for months).

So `modules()` reads the directory. A file named `block_x.py` or `warn_x.py`
that defines `run` IS a guard; nothing else has to be told.

WHAT A GUARD MODULE DECLARES, and why each one is needed rather than derivable:

    CHAIN    "pre-bash", "pre-edit", "pre-ask", "post-bash". NOT derivable
             from the filename: `block-roundlog-truncate.sh` is pre-bash and
             `block-roundlog-write.sh` is pre-edit, and their stems differ by
             one word. It is also the key `check-hook-integrity.sh` uses, which
             chain-qualifies names precisely so "two chains can never collide
             on one basename".
    TWIN     the bash original, CHAIN-QUALIFIED relative to `.claude/hooks`
             (`pre-bash/block-git-amend.sh`). That is the same key
             `check-hook-integrity.sh` uses and the same string the suite's
             `check` calls name, so nothing has to translate between the three.
             This is the differential's
             oracle and the reason it exists: while both copies are present,
             the port is judged against the file it was made from, not against
             its author's understanding of it. P6 removes the bash; the field
             stays, because it is also the only pointer back to the comment
             archaeology.
    ORDER    position within the chain in `.claude/settings.json`, so the P6
             cutover emits the chain in the order it runs today. Hook order is
             load-bearing for at least one hook (`check_hooks_resolvable.py`
             has a whole predicate about require-jq.sh leading), so it is
             recorded rather than left to a directory listing's alphabet.

NOTHING HERE IS WIRED INTO `.claude/settings.json`. That is P6, and it is a
single-writer file this workstream's phases 2 to 4 do not open. Until then both
implementations are on disk and only the bash one runs, which is the condition
the differential needs to be evidence at all.
"""

import importlib
import pathlib

PACKAGE = "rediacc_hooks.guards"
HERE = pathlib.Path(__file__).resolve().parent

# The chains, in the order `.claude/settings.json` declares them. `post-bash`
# is here because `check-hook-integrity.sh` added it on 2026-08-28 after
# finding a whole registered chain outside its inventory: "that was a filename
# prefix escaping the net, this was a whole chain".
CHAINS = ("pre-bash", "pre-edit", "pre-ask", "post-bash")


def stems():
    """Every guard module name in this package, sorted.

    `block_` and `warn_` only, which is the same predicate
    `check_hooks_resolvable.py` uses (`GUARD_PREFIXES = ("block-", "warn-")`)
    and for the same reason it states: "a test script is not a hook".
    """
    return [
        path.stem
        for path in sorted(HERE.glob("*.py"))
        if path.name.startswith(("block_", "warn_", "require_"))
    ]


def load(stem):
    return importlib.import_module("%s.%s" % (PACKAGE, stem))


def modules():
    """Every guard module, imported.

    Imported rather than parsed: a module that cannot be imported is a guard
    that would not run, and a registry that reported it anyway would be
    reporting coverage that does not exist.
    """
    return [load(stem) for stem in stems()]


def by_chain(chain):
    """The guards of one chain, in the order settings.json runs them."""
    mods = [m for m in modules() if chain == m.CHAIN]
    return sorted(mods, key=lambda m: (m.ORDER, m.__name__))


def twin_of(module):
    """The bash original this module was ported from, repo-relative."""
    return module.TWIN
