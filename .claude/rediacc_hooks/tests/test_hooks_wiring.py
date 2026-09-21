"""WIRING: what is on disk and what settings.json registers must match.

Every other case in the suite drives a hook by literal path, which proves the program behaves and says NOTHING about whether Claude ever invokes it. Two failures are invisible to all of them: a hook file nobody registered (dead code that tests green and never guards anything), and a registration pointing at a file that no longer exists (a hook that silently never fires).
settings.json is READ here, never written.
"""

import json
import re

from rediacc_hooks import lifecycle
from rediacc_hooks.tests import hookblocks, hookcases

HOOKS = hookcases.HOOKS
# The live file, unless a proposed one is named through `lifecycle.SETTINGS_ENV`.
SETTINGS = lifecycle.settings_path()

# The chains a registration may name, plus a hook at the hooks ROOT such as chain-head.sh, which belongs to no single chain because it is registered first in several.
#
# WIDENED 2026-08-26 to cover two surfaces this was structurally blind to: `pre-ask/` (the AskUserQuestion chain) and the root. Before that, a hook in either place could be added, left unregistered, and reported as neither UNWIRED nor DANGLING -- the set comparison simply never saw it, which is the same cannot-fail shape the guards themselves exist to prevent.
CHAINS = ("pre-bash", "pre-edit", "post-bash", "pre-ask")
FILE_RE = re.compile(r"^(?:%s)/|^[A-Za-z0-9._-]+\.sh$" % "|".join(CHAINS))
REG_RE = re.compile(r"^(?:%s)/[A-Za-z0-9._-]+\.sh$|^[A-Za-z0-9._-]+\.sh$" % "|".join(CHAINS))


def hook_files(root) -> list[str]:
    """Relative path of every hook script under `root`, lib/ excluded.

    `test-*.sh` is excluded at the root because widening this caught the harness ITSELF as UNWIRED on the first run: a test file is not a hook, and the test- prefix is already this tree's convention for one.
    """
    found = set()
    for path in root.rglob("*.sh"):
        if not path.is_file() or "lib" in path.relative_to(root).parts[:-1]:
            continue
        rel = str(path.relative_to(root))
        if FILE_RE.match(rel) and not path.name.startswith("test-"):
            found.add(rel)
    return sorted(found)


def _named(command: str) -> str:
    _, sep, tail = command.rpartition("/.claude/hooks/")
    return (tail if sep else command).split('"')[0]


def hook_registrations(settings: dict) -> set[str]:
    """The same relative paths, as named by the commands settings.json really runs.

    FLATTENED THROUGH `lifecycle.expand` since the 2026-09-21 collapse, because settings.json names one command per (event, matcher) pattern and the commands that pattern used to name moved into `lifecycle.PATTERNS`. Read literally, the file would name two wrapper scripts and every guard behind them would be reported as UNWIRED.

    THE HEAD IS WIRED BY THE TABLE, not by its own line in the file, and that is why it is added here: `chain-head.sh` is what a collapsed guarded pattern registers, and the table is pinned against the file by `test_settings_collapse.test_the_table_is_what_settings_json_runs`, so the union cannot hide a real disagreement between the two.
    """
    found = set()
    for entries in (settings.get("hooks") or {}).values():
        for entry in entries or []:
            for hook in entry.get("hooks") or []:
                for member in lifecycle.expand(hook.get("command") or ""):
                    rel = _named(member["command"])
                    if REG_RE.match(rel):
                        found.add(rel)
    for key, pattern in lifecycle.PATTERNS.items():
        if pattern["head"]:
            found.add(_named(lifecycle.entry_command(key)).split()[0])
    return found


def check_wiring(regs: set[str], root) -> tuple[int, list[str]]:
    """`(0, [])` when the two sets agree, `(1, offenders)` otherwise."""
    files = set(hook_files(root))
    said = ["UNWIRED (on disk, not in settings): %s" % f for f in sorted(files - regs)]
    said += ["DANGLING (in settings, not on disk): %s" % f for f in sorted(regs - files)]
    return (1 if said else 0), said


def wiring_case(block, expected: int, regs: set[str], root, label: str, *needles: str) -> None:
    code, said = check_wiring(regs, root)
    missing = [n for n in needles if not any(n in line for line in said)]
    block.note(
        expected,
        label,
        ok=code == expected and not missing,
        detail="got exit %d, unnamed: %s" % (code, missing or "-"),
    )


def test_wiring_agrees_in_both_directions():
    block = hookblocks.Block("wiring")
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    regs = hook_registrations(settings)
    wiring_case(
        block,
        0,
        regs,
        HOOKS,
        "wiring: every hook on disk is registered, every registration exists",
    )

    # CONTROL, so the green above is agreement and not a check that cannot fire: one fixture drops a real registration, the other invents one. Each must fail AND name the offender -- a bare non-zero would pass either fixture.
    #
    # THE CONTROLS PLANT INTO THE REGISTRATION SET, not into a settings copy, and that is a re-key the collapse forced rather than a convenience. The old drop control filtered a command out of the file, and the command it filtered, `block-pathspecless-git-commit.sh`, is no longer spelled in the file at all -- it is a member of the pre-bash pattern. The filter would have matched
    # nothing, the fixture would have equalled the original, and the control would have reported the tree's own green as its own. Planting into the set the comparator reads keeps the plant landing wherever the wiring happens to live.
    # RE-KEYED AT W7 P6, which ported the last three bash hooks. `chain-head.sh` is the only bash file left on both sides of this comparison, so it is the only subject a drop can actually remove.
    dropped_subject = "chain-head.sh"
    block.note(
        0,
        "wiring CONTROL: the drop fixture's subject is really registered",
        ok=dropped_subject in regs,
        detail="%s is not in the registration set, so nothing would be planted" % dropped_subject,
    )
    wiring_case(
        block,
        1,
        regs - {dropped_subject},
        HOOKS,
        "wiring CONTROL: a dropped registration is caught as UNWIRED",
        "UNWIRED (on disk, not in settings): %s" % dropped_subject,
    )

    ghost = "pre-bash/block-nonexistent-ghost.sh"
    wiring_case(
        block,
        1,
        regs | {ghost},
        HOOKS,
        "wiring CONTROL: a registration with no file is caught as DANGLING",
        "DANGLING (in settings, not on disk): %s" % ghost,
    )

    # AND ONE CONTROL ON THE FLATTENING ITSELF, because every case above would pass with `lifecycle.expand` returning its argument unchanged -- on the live file today it does exactly that for 30 of the 30 commands, and would go on passing after the collapse while reporting 28 guards as UNWIRED only if the expansion had broken. Driving the collapsed entry directly is what makes
    # the difference visible either way.
    collapsed = [k for k, p in lifecycle.PATTERNS.items() if p["collapsed"]]
    block.note(
        0,
        "wiring CONTROL: a collapsed entry expands to more than itself",
        ok=bool(collapsed) and len(lifecycle.expand(lifecycle.entry_command(collapsed[0]))) > 1,
        detail="the %s entry expanded to itself" % (collapsed[0] if collapsed else "<none>"),
    )
    block.done()
