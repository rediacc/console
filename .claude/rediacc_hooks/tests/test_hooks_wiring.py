"""WIRING: what is on disk and what settings.json registers must match.

Every other case in the suite drives a hook by literal path, which proves the program behaves and says NOTHING about whether Claude ever invokes it. Two failures are invisible to all of them: a hook file nobody registered (dead code that tests green and never guards anything), and a registration pointing at a file that no longer exists (a hook that silently never fires).
settings.json is READ here, never written.
"""

import json
import re

from rediacc_hooks.tests import hookblocks, hookcases

HOOKS = hookcases.HOOKS
SETTINGS = HOOKS.parent / "settings.json"

# The chains a registration may name, plus a hook at the hooks ROOT such as require-jq.sh, which belongs to no single chain because it is registered first in several.
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


def hook_registrations(settings: dict) -> list[str]:
    """The same relative paths, as named by the command strings in settings.json."""
    found = set()
    for entries in (settings.get("hooks") or {}).values():
        for entry in entries or []:
            for hook in entry.get("hooks") or []:
                command = hook.get("command") or ""
                _, sep, tail = command.rpartition("/.claude/hooks/")
                rel = (tail if sep else command).split('"')[0]
                if REG_RE.match(rel):
                    found.add(rel)
    return sorted(found)


def check_wiring(settings: dict, root) -> tuple[int, list[str]]:
    """`(0, [])` when the two sets agree, `(1, offenders)` otherwise."""
    files, regs = set(hook_files(root)), set(hook_registrations(settings))
    said = ["UNWIRED (on disk, not in settings): %s" % f for f in sorted(files - regs)]
    said += ["DANGLING (in settings, not on disk): %s" % f for f in sorted(regs - files)]
    return (1 if said else 0), said


def wiring_case(block, expected: int, settings: dict, root, label: str, *needles: str) -> None:
    code, said = check_wiring(settings, root)
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
    wiring_case(
        block,
        0,
        settings,
        HOOKS,
        "wiring: every hook on disk is registered, every registration exists",
    )

    # CONTROL, so the green above is agreement and not a check that cannot fire: one fixture drops a real registration, the other invents one. Each must fail AND name the offender -- a bare non-zero would pass either fixture.
    #
    # THE SUBJECT OF THE DROP CONTROL HAD TO MOVE at the W5 P7 cutover, and the reason is worth stating because it is how a control quietly stops firing. It dropped
    # block-worktree-add.sh's registration; that guard is a Python module now and
    # settings.json does not name it, so the filter would have matched nothing, the fixture would have been identical to the real file, and the control would have reported the tree's own green as its own. A control that plants nothing proves nothing. block-pathspecless-git-commit.sh is the pre-bash guard still registered as a file, so it is the one that can be dropped.
    dropped = json.loads(SETTINGS.read_text(encoding="utf-8"))
    for entries in (dropped.get("hooks") or {}).values():
        for entry in entries or []:
            entry["hooks"] = [
                h
                for h in (entry.get("hooks") or [])
                if "block-pathspecless-git-commit.sh" not in (h.get("command") or "")
            ]
    # THE PLANT MUST BE PROVEN TO HAVE LANDED. Comparing the fixture to the original is one line and it is the difference between "the control fired" and "the filter matched nothing and the fixture is the tree".
    block.note(
        0,
        "wiring CONTROL: the unwired fixture really differs from settings.json",
        ok=dropped != settings,
        detail="the fixture is IDENTICAL to settings.json, so nothing was planted",
    )
    wiring_case(
        block,
        1,
        dropped,
        HOOKS,
        "wiring CONTROL: a dropped registration is caught as UNWIRED",
        "UNWIRED (on disk, not in settings): pre-bash/block-pathspecless-git-commit.sh",
    )

    invented = json.loads(SETTINGS.read_text(encoding="utf-8"))
    ghost = {
        "type": "command",
        "command": 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/pre-bash/block-nonexistent-ghost.sh"',
    }
    for entries in (invented.get("hooks") or {}).values():
        for entry in entries or []:
            entry["hooks"] = (entry.get("hooks") or []) + [ghost]
    wiring_case(
        block,
        1,
        invented,
        HOOKS,
        "wiring CONTROL: a registration with no file is caught as DANGLING",
        "DANGLING (in settings, not on disk): pre-bash/block-nonexistent-ghost.sh",
    )
    block.done()
