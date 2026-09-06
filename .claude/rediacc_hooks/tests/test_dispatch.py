"""The registry's own invariants, and the entry point that reads it.

WHY THIS IS SEPARATE FROM THE DIFFERENTIAL. That file asks "does this port
answer as its twin does", one guard at a time. Nothing in it asks whether the
SET of ports is coherent: two modules can each pass their own differential
while claiming the same position in a chain, naming the same twin, or declaring
a chain that does not exist. Those are properties of the collection, and the
collection is what `.claude/settings.json` becomes at the P6 cutover.

`dispatch.run_chain` is tested here rather than left for that cutover, because
the fork saving this whole workstream is measured by is the difference between
38 processes and one. A chain runner that is written but never driven is the
shape of thing that is discovered to be wrong on the day it is wired in.
"""

import json
import re
import subprocess
import sys

import pytest

from rediacc_hooks import dispatch, guards
from rediacc_hooks.tests import guardcorpus

ROOT = guardcorpus.repo_root()

# A floor, not a count. The port lands over several phases, so an exact number
# would be wrong the day after it was written; a floor still catches the case
# this exists for, which is the glob in `guards.stems()` collapsing to nothing
# and every assertion below passing over an empty set.
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
    assert isinstance(module.TWIN, str)
    assert module.TWIN.startswith(module.CHAIN + "/"), (
        "%s's TWIN (%r) must be chain-qualified relative to .claude/hooks, so that it is "
        "the same key check-hook-integrity.sh and the suite use" % (stem, module.TWIN)
    )
    assert isinstance(module.ORDER, int)
    assert module.ORDER > 0
    assert callable(module.run)
    assert isinstance(module.DEFECT, tuple)
    assert len(module.DEFECT) == 2


def test_no_two_modules_share_a_twin():
    """Two ports of one bash file would each pass their own differential.

    They would also both run at the cutover, so the guard would refuse twice and
    print its message twice. Nothing else in this package would notice.
    """
    seen = {}
    for stem in guards.stems():
        twin = guards.load(stem).TWIN
        assert twin not in seen, "%s and %s both claim %s as their twin" % (
            seen[twin],
            stem,
            twin,
        )
        seen[twin] = stem


def settings_order():
    """The position of every guard in `.claude/settings.json`, chain-qualified.

    DERIVED, NOT TYPED. Driver contract section 6: "a floor must be set-based or
    corpus-derived, never a hand-typed count." ORDER is exactly such a number,
    and on its first run this check found 27 of 35 declarations wrong by one --
    every module whose author counted the GUARDS in a chain and not its
    commands, since `require-jq.sh` holds position 1 of all four. A uniqueness
    test would have caught only the four that happened to collide.
    """
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    order = {}
    pattern = re.compile(
        r"\.claude/hooks/((?:pre-bash|pre-edit|pre-ask|post-bash)/[A-Za-z0-9_.-]+\.sh)"
    )
    for event in ("PreToolUse", "PostToolUse"):
        for block in settings.get("hooks", {}).get(event, []) or []:
            commands = [h.get("command", "") for h in block.get("hooks", []) or []]
            for position, command in enumerate(commands, start=1):
                found = pattern.search(command)
                if found:
                    order[found.group(1)] = position
    return order


def test_declared_order_matches_settings_json():
    """ORDER is what the cutover will emit, so it has to be what runs today.

    A wrong ORDER is invisible until P6 rewrites `.claude/settings.json` from
    this registry, at which point the chain runs in an order nobody chose and
    every guard still passes its own differential.
    """
    order = settings_order()
    assert order, "no hook paths parsed out of .claude/settings.json"
    wrong = []
    for stem in guards.stems():
        module = guards.load(stem)
        real = order.get(module.TWIN)
        if real is None:
            wrong.append("%s: %s is not registered in settings.json at all" % (stem, module.TWIN))
        elif real != module.ORDER:
            wrong.append("%s: ORDER = %d (declared %d)" % (stem, real, module.ORDER))
    assert not wrong, "\n".join(wrong)


def test_chain_order_is_unique_per_chain():
    """ORDER is the position settings.json runs the guard at.

    Two guards claiming one position is not a tie to be broken quietly: it means
    at least one of them was read off the wrong chain, and the cutover would then
    emit them in an order nobody chose. `by_chain` falls back to the module name
    so the sort is stable, which is exactly what would hide this.
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


# ---------------------------------------------------------------------------
# The entry point
# ---------------------------------------------------------------------------

# A payload nothing refuses, and one that at least one pre-bash guard does. The
# second is `git push --force`, which block-git-force-push.sh exists for; the
# assertion below does not name that guard, only that SOMETHING in the chain
# says no, so it stays true as the port set grows.
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

    STOPPING IS THE HARNESS'S BEHAVIOUR, not a shortcut: a non-zero exit refuses
    the tool call and the rest of the block does not run, which is why
    require-jq.sh's whole contract is about being FIRST. If this ever stops being
    true the chain runner and 38 separate registrations would disagree about what
    a session sees.
    """
    rc, _out, err = dispatch.run_chain("pre-bash", REFUSED)
    if rc == 0:
        pytest.skip("no ported pre-bash guard refuses a force push yet")
    assert rc == 2
    assert err != "", "a chain refused with an empty stderr, so the session is told nothing"


def test_the_entry_point_runs_as_a_process():
    """`python3 .claude/rediacc_hooks/dispatch.py <stem>` with an event on stdin.

    Driven as a PROCESS, because that is how `.claude/settings.json` invokes a
    hook and because the `sys.path` hop at the top of that file only exists on
    that path. An import-only test would pass with the hop deleted.
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
