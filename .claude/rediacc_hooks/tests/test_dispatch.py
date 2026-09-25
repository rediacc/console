"""The registry's own invariants, and the entry point that reads it.

WHY THIS IS SEPARATE FROM THE DIFFERENTIAL. That file asks "does this port answer as its twin does", one guard at a time. Nothing in it asks whether the SET of ports is coherent: two modules can each pass their own differential
while claiming the same position in a chain, naming the same twin, or declaring
a chain that does not exist. Those are properties of the collection, and the collection is what `.claude/settings.json` becomes at the P6 cutover.

`dispatch.run_chain` is tested here rather than left for that cutover, because the fork saving this whole workstream is measured by is the difference between 38 processes and one. A chain runner that is written but never driven is the shape of thing that is discovered to be wrong on the day it is wired in.
"""

import json
import re
import subprocess
import sys

import pytest

from rediacc_hooks import dispatch, guards, lifecycle
from rediacc_hooks.tests import guardcorpus

ROOT = guardcorpus.repo_root()

# A floor, not a count. The port lands over several phases, so an exact number would be wrong the day after it was written; a floor still catches the case this exists for, which is the glob in `guards.stems()` collapsing to nothing and every assertion below passing over an empty set.
MIN_PORTS = 5


def test_the_registry_is_not_empty():
    assert len(guards.stems()) >= MIN_PORTS, (
        "only %d guard module(s) found in %s; below %d every assertion in this file "
        "runs over an empty set and passes for that reason"
        % (len(guards.stems()), guards.HERE, MIN_PORTS)
    )


@pytest.mark.parametrize("stem", guards.stems())
def test_every_module_declares_the_contract(stem):
    module = guards.load(stem)
    assert module.CHAIN in guards.CHAINS, "%s declares chain %r" % (stem, module.CHAIN)
    # OWN_SUITE = True IS ADMITTED, for a guard that was never bash and so has
    # no golden. See `guards.has_own_suite` for why the sentinel exists and what replaces the missing golden.
    assert isinstance(guards.has_own_suite(module), bool)
    assert isinstance(module.ORDER, int)
    assert module.ORDER > 0
    assert callable(module.run)
    assert isinstance(module.DEFECT, tuple)
    assert len(module.DEFECT) == 2


DISPATCH_RE = re.compile(r"rediacc_hooks/dispatch\.py\"?\s+--chain\s+([a-z-]+)")


def block_commands(block):
    """One block's commands as they really run, with any collapsed entry expanded."""
    out = []
    for hook in block.get("hooks", []) or []:
        out.extend(m["command"] for m in lifecycle.expand(hook.get("command", "")))
    return out


def effective_order():
    """The position every guard REALLY runs at, keyed by module name.

    HOW THIS CHANGED AT THE P7 CUTOVER, said out loud because the test below no longer means quite what it used to and a name that outlives its meaning is the trap this package exists to avoid.

    Before the cutover `.claude/settings.json` named all 38 pre-bash guards as their own commands, so it was an INDEPENDENT oracle: a module could declare
    ORDER = 12 and the file said 13, and the mismatch was a fact about two
    separate records disagreeing. On its first run that caught 27 of 35 declarations wrong by one, every module whose author counted the GUARDS in a chain rather than its COMMANDS, since the head's jq check holds position 1 of all four.

    Settings.json now names ONE command per chain. It still fixes the BASE -- how many commands run before the dispatcher, and therefore what position the chain's first guard occupies -- but the order WITHIN the dispatcher is `by_chain`, which sorts on ORDER itself. So the remaining independent facts are: the base, the length, and that the declared numbers form a contiguous run
    with no gap and no duplicate. Those are exactly what changes when someone adds, removes or reorders a COMMAND entry, which is the mistake the original check was built for and the one the brief calls out. What is no longer checkable from outside is two guards SWAPPING ORDER values, because after the collapse ORDER is the definition of the run order rather than a claim about
    another file. That is stated here rather than papered over.

    AND SINCE THE 2026-09-21 COLLAPSE the commands are read through `lifecycle.expand`, because settings.json names one command per (event, matcher) PATTERN rather than per chain. The base is unchanged -- the same commands run in the same order -- but the file no longer spells them, so a reader that took it literally would find no dispatcher entry at all and every ORDER would
    be reported as a guard that never runs.
    """
    settings = json.loads(lifecycle.settings_path().read_text(encoding="utf-8"))
    order = {}
    for event in ("PreToolUse", "PostToolUse"):
        for block in settings.get("hooks", {}).get(event, []) or []:
            position = 0
            for command in block_commands(block):
                found = DISPATCH_RE.search(command)
                if not found:
                    position += 1
                    continue
                for module in guards.by_chain(found.group(1)):
                    position += 1
                    order[module.__name__] = position
    return order


def dispatched_chains():
    """Every chain `.claude/settings.json` routes to the dispatcher."""
    settings = json.loads(lifecycle.settings_path().read_text(encoding="utf-8"))
    chains = []
    for event in ("PreToolUse", "PostToolUse"):
        for block in settings.get("hooks", {}).get(event, []) or []:
            for command in block_commands(block):
                found = DISPATCH_RE.search(command)
                if found:
                    chains.append(found.group(1))
    return chains


def test_every_ported_chain_is_dispatched():
    """A chain with ports but no dispatcher entry is 37 guards that stopped running.

    This is the assertion the cutover turns on. Nothing else in the tree notices a chain that quietly left settings.json: `check_hooks_resolvable.py` checks that the paths it names RESOLVE, not that the chains it used to run are still there.
    """
    routed = set(dispatched_chains())
    ported = {guards.load(stem).CHAIN for stem in guards.stems()}
    assert ported <= routed, (
        "these chains have ported guards but nothing in .claude/settings.json runs "
        "them, so every guard they carry is inert: %s" % sorted(ported - routed)
    )


def test_declared_order_is_the_chain_settings_json_runs():
    """ORDER is what the dispatcher emits, so it has to be based where the chain is.

    Contiguity AND base, both derived (driver contract section 6). A command entry added ahead of the dispatcher moves every guard behind it, which is exactly the re-key the port brief warns about: "any entry you add, remove or reorder re-keys every ORDER after it, in the same change".
    """
    order = effective_order()
    assert order, "no chain in .claude/settings.json routes to the dispatcher at all"
    wrong = []
    for stem in guards.stems():
        module = guards.load(stem)
        real = order.get(module.__name__)
        if real is None:
            wrong.append(
                "%s: chain %r is not dispatched by settings.json, so this guard never runs"
                % (stem, module.CHAIN)
            )
        elif real != module.ORDER:
            wrong.append(
                "%s: runs at position %d, declares ORDER = %d" % (stem, real, module.ORDER)
            )
    assert not wrong, "\n".join(wrong)

    # And the shape, so a chain whose numbers are individually right but jointly broken (a gap, a repeat, a base of zero) is a failure rather than a shrug.
    for chain in sorted({guards.load(s).CHAIN for s in guards.stems()}):
        declared = [m.ORDER for m in guards.by_chain(chain)]
        assert declared == list(range(declared[0], declared[0] + len(declared))), (
            "%s declares a non-contiguous chain: %s" % (chain, declared)
        )
        assert declared[0] >= 2, (
            "%s starts at position %d, so the head's jq and python3 checks are not "
            "both ahead of it" % (chain, declared[0])
        )


def test_chain_order_is_unique_per_chain():
    """ORDER is the position settings.json runs the guard at.

    Two guards claiming one position is not a tie to be broken quietly: it means at least one of them was read off the wrong chain, and the cutover would then emit them in an order nobody chose. `by_chain` falls back to the module name so the sort is stable, which is exactly what would hide this.
    """
    collisions = []
    for chain in guards.CHAINS:
        seen = {}
        for module in guards.by_chain(chain):
            if module.ORDER in seen:
                collisions.append(
                    "%s: %s and %s both claim position %d"
                    % (chain, seen[module.ORDER], module.__name__, module.ORDER)
                )
            seen[module.ORDER] = module.__name__
    assert not collisions, "\n".join(collisions)


def test_by_chain_covers_every_module():
    covered = {m.__name__ for chain in guards.CHAINS for m in guards.by_chain(chain)}
    assert covered == {guards.load(s).__name__ for s in guards.stems()}


# --------------------------------------------------------------------------- The entry point ---------------------------------------------------------------------------

# A payload nothing refuses, and one that at least one pre-bash guard does. The second is `git push --force`, which block-git-force-push.sh exists for; the assertion below does not name that guard, only that SOMETHING in the chain says no, so it stays true as the port set grows.
BENIGN = '{"tool_input":{"command":"echo hello"}}'
REFUSED = '{"tool_input":{"command":"git push --force origin main"}}'


def test_run_one_returns_the_three_fields():
    stem = guards.stems()[0]
    rc, out, err = dispatch.run_one(stem, BENIGN)
    assert rc in (0, 2)
    assert isinstance(out, str)
    assert isinstance(err, str)


def test_run_chain_allows_a_benign_command():
    rc, _out, err = dispatch.run_chain("pre-bash", BENIGN)
    assert rc == 0, "a plain echo was refused by the pre-bash chain: %r" % (err,)


def test_run_chain_stops_at_the_first_refusal():
    """The refusal, and the guards behind it never speaking.

    STOPPING IS THE HARNESS'S BEHAVIOUR, not a shortcut: a non-zero exit refuses the tool call and the rest of the block does not run, which is why the chain head's whole contract is about being FIRST. If this ever stops being true the chain runner and 38 separate registrations would disagree about what a session sees.
    """
    rc, _out, err = dispatch.run_chain("pre-bash", REFUSED)
    if rc == 0:
        pytest.skip("no ported pre-bash guard refuses a force push yet")
    assert rc == 2
    assert err != "", "a chain refused with an empty stderr, so the session is told nothing"


def test_the_entry_point_runs_as_a_process():
    """`python3 .claude/rediacc_hooks/dispatch.py <stem>` with an event on stdin.

    Driven as a PROCESS, because that is how `.claude/settings.json` invokes a hook and because the `sys.path` hop at the top of that file only exists on that path. An import-only test would pass with the hop deleted.
    """
    stem = guards.stems()[0]
    proc = subprocess.run(
        [sys.executable, str(ROOT / ".claude" / "rediacc_hooks" / "dispatch.py"), stem],
        input=BENIGN.encode("utf-8"),
        capture_output=True,
        check=False,
        cwd=str(ROOT),
    )
    assert proc.returncode in (0, 2), proc.stderr.decode("utf-8", "replace")


def test_list_names_every_port():
    proc = subprocess.run(
        [sys.executable, str(ROOT / ".claude" / "rediacc_hooks" / "dispatch.py"), "--list"],
        capture_output=True,
        check=False,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    out = proc.stdout.decode("utf-8", "replace")
    for stem in guards.stems():
        assert stem in out, "--list omitted %s" % stem
