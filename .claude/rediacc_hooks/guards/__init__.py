"""The guard registry. A guard declares itself by BEING here.

WHY A SCAN AND NOT A LIST. Section 7 of `docs/ci-overhaul/08-driver-contract.md` gives "modular and dynamic" its only checkable meaning: "Adding a gate, an allowlist entry, or a hook guard requires no edit to any workflow file, any runner file, or any dispatcher file... the guard declares itself as a module in the hook registry." A hand-written tuple in this file would be exactly
the second edit that rule forbids, and it would rot the same way the hook-coverage baseline rotted (`check-hook-integrity.sh` records five `gh_case` cases sitting in a gap list they had not been in for months).

So `modules()` reads the directory. A file named `block_x.py` or `warn_x.py` that defines `run` IS a guard; nothing else has to be told.

WHAT A GUARD MODULE DECLARES, and why each one is needed rather than derivable:

    CHAIN      "pre-bash", "pre-edit", "pre-ask", "pre-agent", "post-bash". NOT
               derivable from the filename: `block-roundlog-truncate.sh` is
               pre-bash and `block-roundlog-write.sh` is pre-edit, and their
               stems differ by one word. It is also the key
               `check-hook-integrity.sh` uses, which chain-qualifies names
               precisely so "two chains can never collide on one basename".
    OWN_SUITE  `True` for a guard that was never bash and therefore has no
               frozen golden to be judged against; absent (equivalently
               `False`) for every other guard, which is judged against
               `tests/goldens/<stem>.jsonl` instead. See OWN_SUITE below.
               PLAN-retire-bash-oracles A3 deleted `.claude/oracles/` and every
               `TWIN` constant that pointed into it, once every twinned guard
               had a golden frozen from its bash original (A1); this field is
               what is left of that distinction, for the handful of guards a
               golden was never possible for.
    ORDER      the guard's position in its chain, counting COMMANDS and not
               guards. The chain head's jq and python3 checks hold positions 1
               and 2 of every chain, so a chain's first ported guard is at 3
               (pre-edit at 4, behind why-on-edit.py). The collapse preserved every
               position rather than renumbering: the dispatcher entry occupies the
               span its guards used to fill one command each. Hook order is
               load-bearing (`check_hooks_resolvable.py` has a whole predicate
               about the chain head leading), so it is recorded rather than left to
               a directory listing's alphabet.

THIS REGISTRY IS WHAT `.claude/settings.json` RUNS, since the P7 cutover on 2026-09-06. One command per chain invokes `dispatch.py --chain <name>`, and the chain it runs is `by_chain(<name>)` -- this directory scan, in ORDER. Two consequences worth stating in the file that owns them:

  * A guard added here is registered by EXISTING. That is section 7 of the
    driver contract satisfied rather than claimed: no workflow file, no runner
    file and no dispatcher file has to be edited.
  * An EMPTY chain is now a catastrophe rather than a curiosity, so
    `dispatch.run_chain` refuses one outright instead of exiting 0 over nothing.
    Before the cutover a broken glob here cost nothing, because settings.json
    named 38 bash files directly.

The bash originals are gone. `.claude/oracles/` held them, byte for byte, only until every twinned guard had a frozen golden to be judged against instead (PLAN-retire-bash-oracles A1); A3 deleted the tree once that freeze was proven complete. `tests/test_guards_differential.py` now compares every port against `tests/goldens/<stem>.jsonl`, not against a live bash process.
"""

import importlib
import pathlib

PACKAGE = "rediacc_hooks.guards"
HERE = pathlib.Path(__file__).resolve().parent

# The chains, in the order `.claude/settings.json` declares them. `post-bash` is here because `check-hook-integrity.sh` added it on 2026-08-28 after finding a whole registered chain outside its inventory: "that was a filename prefix escaping the net, this was a whole chain".
CHAINS = ("pre-bash", "pre-edit", "pre-ask", "pre-agent", "post-bash")


def stems():
    """Every guard module name in this package, sorted.

    `block_`, `warn_` and `require_`, the first two being the same predicate
    `check_hooks_resolvable.py` uses (`GUARD_PREFIXES = ("block-", "warn-")`)
    and for the same reason it states: "a test script is not a hook". `require_` is admitted for a port that does not exist yet and may never: the two toolchain checks are inlined in `.claude/hooks/chain-head.sh` and deliberately still bash, because one of them checks for the interpreter it would otherwise need to run in.

    THE PREFIX RULE IS ALSO WHAT KEEPS THE HARNESSES OUT. Four `test-block_*.py` files sit in this directory, beside the guards they drive, because that is where `check-hook-integrity.sh` looks for a dedicated per-guard suite. They are not guards and this glob does not admit them.
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

    Imported rather than parsed: a module that cannot be imported is a guard that would not run, and a registry that reported it anyway would be reporting coverage that does not exist.
    """
    return [load(stem) for stem in stems()]


def by_chain(chain):
    """The guards of one chain, in the order settings.json runs them."""
    mods = [m for m in modules() if chain == m.CHAIN]
    return sorted(mods, key=lambda m: (m.ORDER, m.__name__))


def has_own_suite(module):
    """Whether this module opts out of golden evidence and stands on its own suite.

    `OWN_SUITE = True` IS A SENTINEL AND NOT AN OVERSIGHT, added 2026-09-16 for
    `block_prose_style_edit` and `block_prose_style_commit`, the first two guards in this package that were never bash (then spelled `TWIN = None`; PLAN-retire-bash-oracles A3 retired the `TWIN` name along with the oracle tree it pointed into, once every OTHER guard had a golden frozen from its bash original instead).

    WHY THE FIELD COULD NOT SIMPLY BE LEFT OFF. All 46 guards that existed before them landed on ONE day, 2026-09-06, the P7 cutover, because every one of them is a PORT. The harness encoded that as an invariant -- `test_dispatch` asserted `isinstance(module.TWIN, str)`, and the differential read `ORACLES / module.TWIN` in four places -- so a genuinely new guard could not be added
    at all without either this sentinel or a fake bash file. The fake was not available either: `.ci/scripts/quality/check_language_policy.py` freezes the SET of shell files under `.ci` and `.claude` and refuses a new one, "the surface may shrink and may never grow". Inventing one to satisfy an assertion would also have been a lie to the assertion, whose whole point is that "the
    port is judged against the file it was made from".

    HAVING NO GOLDEN IS NOT A FREE PASS OUT OF HAVING EVIDENCE, and the harness
    says so in one place rather than leaving it to authors: `test_every_port_has_goldens` REQUIRES a guard declaring `OWN_SUITE = True` to carry a dedicated `test-<stem>.py` beside it. A golden-backed guard is judged against its frozen record; an OWN_SUITE one is judged against a suite written for it. Both are still judged.
    """
    return getattr(module, "OWN_SUITE", False)


def golden_backed():
    """Guard modules judged against a frozen golden: the differential's subject."""
    return [m for m in modules() if not has_own_suite(m)]


def suite_only():
    """Guard modules with no golden, which are tested against their own suites.

    Counted and named rather than silently excluded. A helper that filtered them out of `modules()` would make this set invisible, which is exactly the shape `check-hook-integrity.sh` records rotting once already: "five `gh_case` cases sitting in a gap list they had not been in for months".
    """
    return [m for m in modules() if has_own_suite(m)]
