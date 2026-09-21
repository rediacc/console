#!/usr/bin/env python3
"""Every hook script .claude/settings.json references must exist and be runnable.

WHY THIS EXISTS. This repo's guard layer is largely hooks: they block a non-draft PR create, a premature `gh pr ready`, an admin merge, a force push, a `git worktree add`, a long sleep, a push onto a rebased branch. Each one is a check, and a hook whose script has been renamed, moved or deleted **does not error: it simply stops firing.** The guard disappears and every subsequent
run looks clean, which is the exact failure this session spent a night eliminating everywhere else: a check that reports success while doing nothing.

Nothing verified this. `git mv` on a hook, or a settings edit with a typo, was silent.

WHAT IT CHECKS, for every command in settings.json's hook blocks:
  - the script it names exists on disk
  - it is a regular file, not a directory
  - it is non-empty
  - a `.py` script carrying a shebang is executable IN GIT, because ruff's
    EXE001 reads the git mode and not the filesystem, and that mismatch has
    already cost two CI rounds this session
  - .claude/hooks/chain-head.sh is the FIRST command of every PreToolUse block
    and of the PostToolUse Bash block, and it still CONTAINS both toolchain
    checks, because ORDER is load-bearing for those two and order is invisible
    to every other check here (added 2026-09-06, see first_guard_verdicts and
    head_verdicts)

EVERY COMMAND MEANS THE FLATTENED ONE, since the 2026-09-21 collapse. settings.json names one command per (event, matcher) pattern and the commands that pattern used to name live in `.claude/rediacc_hooks/lifecycle.py`, so reading the file literally would resolve two scripts and stop checking the other twenty-eight. `expand_commands` walks through that table, which is also what
keeps the ordering predicate below about the run order rather than about a wrapper's name.

WHAT IT DOES NOT DO. It does not execute the hooks or judge their logic -- `.ci/scripts/test/gates/` owns behaviour. This asserts only that the wiring resolves, which is the part that fails silently.

---- gate ----
step: Hooks resolvable
needs: none
selftest: true
---- end gate ----
"""

import argparse
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

import _cipath  # noqa: F401
from rediacc_ci.controls import plant

# Vacuity floor. This repo wires dozens of hook commands; a handful means the parse broke, and every check below would be over an empty set -- which reads exactly like "every hook resolves".
MIN_COMMANDS = 10

SETTINGS = ".claude/settings.json"

# A command line may be a bare script path or a wrapper such as `bash "$CLAUDE_PROJECT_DIR/.claude/hooks/x.sh"`. Pull out anything that looks like a repo-relative hook path rather than trying to tokenise a shell string (shlex chokes on the real content: one command contains a bare backslash).
PATH_RE = re.compile(r"(?:\$CLAUDE_PROJECT_DIR/)?(\.claude/[A-Za-z0-9_./-]+\.(?:sh|py|cjs|js|ts))")


LIFECYCLE = ".claude/rediacc_hooks/lifecycle.py"


def lifecycle(root):
    """The pattern table, loaded by path because `.claude` is on no import path.

    A hard failure rather than a fallback. Silently treating the file as absent would flatten nothing, resolve the two wrapper scripts and report every other hook as checked, which is the shape this whole gate exists to refuse.
    """
    spec = importlib.util.spec_from_file_location("hook_lifecycle", root / LIFECYCLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def raw_commands(settings):
    """Every command string under every hook block, as the file spells it."""
    out = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "command" and isinstance(v, str):
                    out.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(settings.get("hooks", {}))
    return out


def expand_commands(cmds, table):
    """The same commands with every collapsed entry replaced by the members it runs."""
    if table is None:
        return list(cmds)
    out = []
    for cmd in cmds:
        out.extend(m["command"] for m in table.expand(cmd))
    return out


def commands(settings, table=None):
    """Every command a hook block really runs, wrappers expanded."""
    return expand_commands(raw_commands(settings), table)


def routing_verdicts(settings, table):
    """A collapsed entry naming a pattern the table does not know runs NOTHING.

    `lifecycle.expand` leaves such a command alone, so `PATH_RE` finds the wrapper, the wrapper exists, and the gate would report it as resolving while the whole pattern it stands for is inert.
    """
    if table is None:
        return []
    wrappers = (table.HEAD_SCRIPT.rsplit("/", 1)[-1], table.RUNNER_SCRIPT.rsplit("/", 1)[-1])
    return [
        f"{cmd.strip()} runs a collapsed hook pattern, but names no key that "
        f"{LIFECYCLE} declares, so every hook that pattern carries is inert."
        for cmd in raw_commands(settings)
        if any(w in cmd for w in wrappers) and table.routed_key(cmd) is None
    ]


def git_mode(root, rel):
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-s", "--", rel],
        capture_output=True,
        text=True,
        check=False,
    )
    parts = out.stdout.split()
    return parts[0] if parts else None


def verdicts(root, refs):
    """Every complaint. Pure, so the controls can drive it."""
    out = []
    for rel in sorted(set(refs)):
        p = root / rel
        if not p.exists():
            out.append(
                f"{rel} is referenced by a hook but DOES NOT EXIST. The hook does not error -- "
                f"it silently stops firing, and every run afterwards looks clean."
            )
            continue
        if not p.is_file():
            out.append(f"{rel} is referenced by a hook but is not a regular file.")
            continue
        if p.stat().st_size == 0:
            out.append(f"{rel} is referenced by a hook but is EMPTY, so it guards nothing.")
            continue
        if rel.endswith(".py"):
            first = p.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
            if first.startswith("#!"):
                mode = git_mode(root, rel)
                if mode is not None and mode != "100755":
                    out.append(
                        f"{rel} has a shebang but its GIT mode is {mode}, not 100755. ruff's "
                        f"EXE001 reads the git mode, not the filesystem, so this passes locally "
                        f"and fails in CI. Fix with: git update-index --chmod=+x {rel}"
                    )
    return out


# The one hook whose POSITION is part of its contract, and the blocks it has to lead. Everything else in settings.json may sit in any order. It was two scripts (require-jq.sh then require-python.sh) until 2026-09-21; both checks are inlined in the head now, so leading is necessary and no longer sufficient, and `head_verdicts` carries the other half.
FIRST_GUARD = "chain-head.sh"


def guarded_blocks(settings, table=None):
    """(label, commands) for every chain the head must lead.

    Every PreToolUse block -- Bash, the Edit family, AskUserQuestion -- plus the PostToolUse block matched on Bash. The other PostToolUse blocks are matcher- less and fire for every tool; they are not jq-parsing Bash chains, so they are deliberately out of scope.

    The commands are FLATTENED. Since the collapse each of those blocks holds one entry naming `chain-head.sh`, and a predicate about that name would be a predicate about a wrapper rather than about the position the hook actually runs at.
    """
    hooks = settings.get("hooks", {}) or {}
    blocks = []
    for i, block in enumerate(hooks.get("PreToolUse", []) or []):
        if isinstance(block, dict):
            blocks.append((f"PreToolUse[{block.get('matcher') or i}]", block))
    blocks.extend(
        ("PostToolUse[Bash]", block)
        for block in hooks.get("PostToolUse", []) or []
        if isinstance(block, dict) and block.get("matcher") == "Bash"
    )
    out = []
    for label, block in blocks:
        cmds = [
            h.get("command", "")
            for h in (block.get("hooks", []) or [])
            if isinstance(h, dict) and isinstance(h.get("command"), str)
        ]
        out.append((label, expand_commands(cmds, table)))
    return out


def first_guard_verdicts(settings, table=None):
    """The chain head must lead every jq-parsing chain. Pure, so controls drive it.

    WHY POSITION, AND WHY NOTHING ELSE HERE CAN SEE IT. Every other verdict in this file is about a command in isolation: does the file exist, is it a file, is it non-empty, is its git mode right. `commands()` flattens the whole hooks tree precisely because that is all those checks need. Order survives none of that flattening, and order is the entire contract of the two toolchain
    checks the head carries: they fail closed when jq or python3 is missing, so the hooks BEHIND them never get to parse an empty string and exit 0. Registered second, the hook they were meant to cover has already run and already returned ALLOW.

    Measured 2026-09-06: the jq check led all three PreToolUse chains and was absent from PostToolUse entirely, so both post-bash hooks (cancel-old-ci.sh and refresh-pr-body.sh, each parsing stdin with `jq -r ... 2>/dev/null`) failed OPEN on a machine without jq -- they ran, found nothing, said nothing. Registering it there is one line; keeping it FIRST there is this predicate.

    On PostToolUse it prevents nothing, the tool having already run. It converts a silent no-op into a visible one, which is the whole difference.
    """
    out = []
    blocks = guarded_blocks(settings, table)
    if not blocks:
        vacuous = (
            "no PreToolUse block and no PostToolUse Bash block was found at all, so this "
            "ordering check ran over an empty set -- which reads exactly like every chain "
            "being led correctly."
        )
        return [vacuous]
    for label, cmds in blocks:
        if not cmds:
            out.append(f"{label} has no hook commands at all, so {FIRST_GUARD} cannot lead it.")
            continue
        if FIRST_GUARD in cmds[0]:
            continue
        at = next((i for i, c in enumerate(cmds) if FIRST_GUARD in c), None)
        if at is None:
            out.append(
                f"{label} does not register {FIRST_GUARD} at all, so neither toolchain check "
                f"runs for it. Every hook in that chain parses its stdin with jq, and with no "
                f"jq each one gets an empty string and exits 0 -- which means ALLOW on "
                f"PreToolUse and a silent no-op on PostToolUse."
            )
        else:
            out.append(
                f"{label} registers {FIRST_GUARD} at position {at + 1}, not first. The "
                f"{at} command(s) ahead of it run BEFORE the toolchain is checked, so on a "
                f"machine without jq they have already parsed an empty string and already "
                f"returned 0 by the time the guard fires."
            )
    return out


def head_verdicts(text, checks):
    """The head must still CONTAIN every check it leads with. Pure, so controls drive it.

    LEADING IS NO LONGER SUFFICIENT, which is the half of this contract the predicate above cannot see. Until 2026-09-21 the two checks were scripts of their own, so `verdicts` resolved them by path and their absence was a missing file. Inlined, they are lines inside one script that already exists, is a regular file, is non-empty and leads every guarded chain: a head with the jq
    arm deleted satisfies every other verdict in this gate while the entire guard set is back to failing OPEN on a machine without jq. Nothing else in CI reads the head's body.
    """
    return [
        f"{LIFECYCLE} says the chain head checks for {tool}, but the head does not run "
        f"`command -v {tool}` at all. Every hook behind it then runs on a machine missing "
        f"{tool}, where each one gets an empty parse and exits 0 -- which means ALLOW."
        for tool in checks
        if not re.search(r"command -v %s\b" % re.escape(tool), text)
    ]


def controls(root):
    """Prove the detector fires in BOTH directions before any real read."""
    if not verdicts(root, [".claude/hooks/__a_hook_that_does_not_exist__.sh"]):
        return "planted a nonexistent hook path and the detector stayed silent"
    # A .sh, deliberately: the control must not collide with the .py mode check below. Using a Python hook here made mutating ANY python hook trip the control instead of the finding, which refuses a verdict correctly but tests nothing. A GUARD THAT STILL EXISTS AS A .sh, RE-KEYED 2026-09-07. This was `block-admin-merge.sh`, which the W5 cutover moved to `.claude/oracles/`, and the
    # `is_file()` guard then made this control SKIP SILENTLY: the gate stayed green while the case that proves a real hook is not reported broken stopped running at all. `block-pathspecless-git-commit.sh` is the one pre-bash guard with no Python port, so it is a .sh that is still wired.
    real = ".claude/hooks/pre-bash/block-pathspecless-git-commit.sh"
    if not (root / real).is_file():
        return f"the control's subject {real} is gone; re-key it rather than skipping"
    if verdicts(root, [real]):
        return f"a real, present, executable hook ({real}) was reported as broken"

    # The ordering predicate, driven in BOTH directions off in-memory fixtures. In memory, deliberately: these must not touch the real settings.json, and they must not be routed through main(), whose MIN_COMMANDS vacuity floor would reject a two-command fixture as a broken parse. first_guard_verdicts is pure, so it can be handed a settings-shaped dict directly.
    def _fixture(order):
        chain = {"hooks": [{"type": "command", "command": c} for c in order]}
        return {
            "hooks": {
                "PreToolUse": [dict(chain, matcher="Bash")],
                "PostToolUse": [dict(chain, matcher="Bash")],
            }
        }

    lead = 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/chain-head.sh" --check jq'
    other = 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/pre-bash/block-pathspecless-git-commit.sh"'
    if first_guard_verdicts(_fixture([lead, other])):
        return f"a fixture with {FIRST_GUARD} FIRST in both chains was reported as misordered"
    if not first_guard_verdicts(_fixture([other, lead])):
        return f"a fixture with {FIRST_GUARD} SECOND in both chains was accepted"

    # The flattening, driven in both directions off the real table. Without these the collapse would be certified by a gate that had quietly gone back to reading two wrapper scripts and calling it thirty.
    table = lifecycle(root)
    collapsed = [k for k, p in table.PATTERNS.items() if p["collapsed"]]
    if not collapsed:
        return f"{LIFECYCLE} declares no collapsed pattern, so the flattening checks nothing"
    key = collapsed[0]
    entry = table.entry_command(key)
    if len(expand_commands([entry], table)) <= 1:
        return f"the {key} entry expanded to itself, so the member commands are not being read"
    ghost = plant(entry, " " + key, " __a_pattern_that_does_not_exist__")
    if not routing_verdicts({"hooks": {"Stop": [{"hooks": [{"command": ghost}]}]}}, table):
        return "planted an entry naming an unknown hook pattern and the detector stayed silent"
    if routing_verdicts({"hooks": {"Stop": [{"hooks": [{"command": entry}]}]}}, table):
        return f"a real collapsed entry ({key}) was reported as naming no pattern"

    # The head's BODY, one plant per check. A single plant would certify whichever arm it did not touch, and dropping one of two inlined checks is exactly the edit this half of the contract exists to catch.
    checks = table.head_checks()
    if len(checks) < 2:
        return f"{LIFECYCLE} declares {len(checks)} toolchain check(s); the head carries two"
    head_text = (root / table.HEAD_SCRIPT).read_text(encoding="utf-8")
    if head_verdicts(head_text, checks):
        return f"the real {table.HEAD_SCRIPT} was reported as missing a check it runs"
    for tool in checks:
        # A suffix rather than a deletion: `command -v jqq` still CONTAINS `command -v jq`, so a substring detector would read the mutant as clean and the control would pass without asserting anything.
        dropped = plant(head_text, "command -v %s" % tool, "command -v %s_gone" % tool)
        if not head_verdicts(dropped, checks):
            return f"dropped the {tool} check from the head and the detector stayed silent"
    return None


# Guard directories, and the naming convention that separates a guard from its own test. `block-*`/`warn-*` are hooks; `test-*` are the suites that drive them.
GUARD_DIRS = ("pre-bash", "pre-edit", "post-bash")
GUARD_PREFIXES = ("block-", "warn-")


def unregistered_guards(root, refs):
    """Guard scripts on disk that settings.json never names.

    THE OTHER HALF OF THIS GATE. Everything above answers "settings.json names a script, does it exist?". This answers the reverse, "a guard exists, is it wired?", and the reverse is the direction an AUTHOR gets wrong: writing a guard, testing it by hand, and never adding it to settings.json. The result is indistinguishable from a guard that works, because a hook that is never
    invoked never complains, and the author's hand-test passed.

    Found by probing rather than reasoning, 2026-08-19: two guards were added that day and nothing in CI would have noticed if either registration line had been skipped.

    Names are compared, not paths, because settings.json interpolates $CLAUDE_PROJECT_DIR and a path comparison would be brittle against that.
    """
    named = {pathlib.Path(r).name for r in refs}
    missing = []
    for d in GUARD_DIRS:
        for f in sorted((root / ".claude" / "hooks" / d).glob("*.sh")):
            if not f.name.startswith(GUARD_PREFIXES):
                continue  # a test script is not a hook
            if f.name not in named:
                missing.append(f"{d}/{f.name}")
    return missing


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    # A proposed settings file can be driven before anybody rewires a shared worktree with it, which is the only way to check a wiring change without a wrong second of it landing on every concurrent session.
    ap.add_argument("--settings", default=None, help=f"path to a settings file ({SETTINGS})")
    args = ap.parse_args(argv)
    root = pathlib.Path(__file__).resolve().parents[3]
    settings_path = pathlib.Path(args.settings) if args.settings else root / SETTINGS

    if not settings_path.is_file():
        print(f"VACUOUS INPUT: {SETTINGS} is missing, so no hook can be checked", file=sys.stderr)
        return 1

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    table = lifecycle(root)
    cmds = commands(settings, table)
    refs = [m for c in cmds for m in PATH_RE.findall(c)]

    if len(cmds) < MIN_COMMANDS or not refs:
        print(
            f"VACUOUS INPUT: parsed {len(cmds)} hook command(s) and {len(refs)} script "
            f"reference(s), expected at least {MIN_COMMANDS} commands. A check over an empty "
            f"set exits 0 and reads exactly like every hook resolving.",
            file=sys.stderr,
        )
        return 1

    broken = controls(root)
    if broken:
        print(
            f"CONTROL FAILED, so nothing below is meaningful: {broken}.\n"
            "  Refusing a verdict, because the defect this gate exists for is a guard that\n"
            "  reports success while doing nothing.",
            file=sys.stderr,
        )
        return 1

    inert = routing_verdicts(settings, table)
    if inert:
        print("A hook pattern is wired to a key nothing runs:", file=sys.stderr)
        for line in inert:
            print(f"  - {line}", file=sys.stderr)
        print(f"  Add the key to PATTERNS in {LIFECYCLE}, or fix the command.", file=sys.stderr)
        return 1

    problems = verdicts(root, refs)
    if problems:
        print("Hooks referenced by settings.json do not resolve:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    hollow = head_verdicts(
        (root / table.HEAD_SCRIPT).read_text(encoding="utf-8"), table.head_checks()
    )
    if hollow:
        print(
            f"{table.HEAD_SCRIPT} no longer runs a check the table says it does:", file=sys.stderr
        )
        for line in hollow:
            print(f"  - {line}", file=sys.stderr)
        print(
            f"  Restore the check in the head, or take it out of HEAD in {LIFECYCLE}. A head "
            "that leads every chain while checking nothing passes every other verdict here.",
            file=sys.stderr,
        )
        return 1

    misordered = first_guard_verdicts(settings, table)
    if misordered:
        print(
            f"{FIRST_GUARD} does not lead every chain that depends on it:",
            file=sys.stderr,
        )
        for m in misordered:
            print(f"  - {m}", file=sys.stderr)
        print(
            f'  Move it to the FIRST entry of that block\'s "hooks" array in {SETTINGS}. A '
            "fail-closed toolchain check that runs after the hooks it protects has already "
            "let them report success while doing nothing.",
            file=sys.stderr,
        )
        return 1

    orphans = unregistered_guards(root, refs)
    if orphans:
        print(
            "Guard hooks exist on disk but settings.json never invokes them, so they "
            "silently do nothing:",
            file=sys.stderr,
        )
        for o in orphans:
            print(f"  - .claude/hooks/{o}", file=sys.stderr)
        print(
            "  Add each to the matching PreToolUse block in .claude/settings.json, or "
            "delete it. A guard nobody calls is worse than no guard: it reads as "
            "coverage.",
            file=sys.stderr,
        )
        return 1

    print(
        f"{len(set(refs))} hook script(s) across {len(cmds)} command(s) all resolve, "
        f"{FIRST_GUARD} leads all {len(guarded_blocks(settings, table))} chain(s) that need it "
        f"and still runs {', '.join(table.head_checks())}, and "
        f"every guard on disk is registered (controls fired in both directions)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
