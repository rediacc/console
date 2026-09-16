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
    TWIN     the bash original, CHAIN-QUALIFIED (`pre-bash/block-git-amend.sh`),
             or `None` for a guard that was never bash. See TWIN = None below.
             It was a path under `.claude/hooks` until the P7 cutover and is now
             a key into `.claude/oracles/`, where those files were
             moved; the STRING is unchanged, so the differential and the comment
             archaeology both still resolve. This is the differential's oracle
             and the reason it exists: the port is judged against the file it
             was made from, not against its author's understanding of it. The
             field survives the cutover for that reason and because it is the
             only pointer back to the prose.
    ORDER    the guard's position in its chain, counting COMMANDS and not
             guards. require-jq.sh and require-python.sh hold positions 1 and 2
             of every chain, so a chain's first ported guard is at 3 (pre-edit
             at 4, behind why-on-edit.py). The collapse preserved every
             position rather than renumbering: the dispatcher entry occupies the
             span its guards used to fill one command each. Hook order is
             load-bearing (`check_hooks_resolvable.py` has a whole predicate
             about require-jq.sh leading), so it is recorded rather than left to
             a directory listing's alphabet.

THIS REGISTRY IS WHAT `.claude/settings.json` RUNS, since the P7 cutover on
2026-09-06. One command per chain invokes `dispatch.py --chain <name>`, and the
chain it runs is `by_chain(<name>)` -- this directory scan, in ORDER. Two
consequences worth stating in the file that owns them:

  * A guard added here is registered by EXISTING. That is section 7 of the
    driver contract satisfied rather than claimed: no workflow file, no runner
    file and no dispatcher file has to be edited.
  * An EMPTY chain is now a catastrophe rather than a curiosity, so
    `dispatch.run_chain` refuses one outright instead of exiting 0 over nothing.
    Before the cutover a broken glob here cost nothing, because settings.json
    named 38 bash files directly.

The bash originals still exist, at `.claude/oracles/`, and
`tests/test_guards_differential.py` still compares every port against its own
one byte for byte. They are no longer registered anywhere and are no longer
guards; see that directory's README for why they are kept and why they had to
leave `.claude/hooks/`.
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

    `block_`, `warn_` and `require_`, the first two being the same predicate
    `check_hooks_resolvable.py` uses (`GUARD_PREFIXES = ("block-", "warn-")`)
    and for the same reason it states: "a test script is not a hook".
    `require_` is admitted for a port that does not exist yet: require-jq.sh and
    require-python.sh are deliberately still bash, because each one checks for
    the interpreter it would otherwise need to run in.

    THE PREFIX RULE IS ALSO WHAT KEEPS THE HARNESSES OUT. Four `test-block_*.py`
    files sit in this directory, beside the guards they drive, because that is
    where `check-hook-integrity.sh` looks for a dedicated per-guard suite. They
    are not guards and this glob does not admit them.
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
    """The bash original this module was ported from, repo-relative, or None.

    TWIN = None IS A SENTINEL AND NOT AN OVERSIGHT, added 2026-09-16 for
    `block_prose_style_edit` and `block_prose_style_commit`, the first two guards
    in this package that were never bash.

    WHY THE FIELD COULD NOT SIMPLY BE FILLED IN. All 46 guards that existed
    before them landed on ONE day, 2026-09-06, the P7 cutover, because every one
    of them is a PORT. The harness encoded that as an invariant -- `test_dispatch`
    asserted `isinstance(module.TWIN, str)`, and the differential read
    `ORACLES / module.TWIN` in four places -- so a genuinely new guard could not
    be added at all without either this sentinel or a fake bash file. The fake was
    not available either: `.ci/scripts/quality/check_language_policy.py` freezes
    the SET of shell files under `.ci` and `.claude` and refuses a new one, "the
    surface may shrink and may never grow". Inventing one to satisfy an assertion
    would also have been a lie to the assertion, whose whole point is that "the
    port is judged against the file it was made from".

    SKIPPING THE ORACLE IS NOT A FREE PASS OUT OF HAVING EVIDENCE, and the
    harness now says so in one place rather than leaving it to authors:
    `test_every_port_has_a_present_twin` REQUIRES a guard declaring `TWIN = None`
    to carry a dedicated `test-<stem>.py` beside it. A twinned guard is judged
    against bash; an untwinned one is judged against a suite written for it. Both
    are still judged.
    """
    return module.TWIN


def twinned():
    """Guard modules that HAVE a bash oracle: the differential's subject."""
    return [m for m in modules() if m.TWIN is not None]


def untwinned():
    """Guard modules with no oracle, which are tested against their own suites.

    Counted and named rather than silently excluded. A helper that filtered them
    out of `modules()` would make this set invisible, which is exactly the shape
    `check-hook-integrity.sh` records rotting once already: "five `gh_case` cases
    sitting in a gap list they had not been in for months".
    """
    return [m for m in modules() if m.TWIN is None]
