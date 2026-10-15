#!/usr/bin/env python3
"""Control harness for block_cli_bundle.

Both directions, because a one-sided control is satisfiable by a broken guard: one that always refuses passes every refuse row, one that never refuses passes every allow row.

THE PROGRAM IS THE WORD BASH HANDS THE INTERPRETER, NOT THE WORD AS TYPED (#e13fb555). `B=packages/cli/dist/cli-bundle.cjs; node $B config field set ...` ran on 2026-10-15 because the guard matched the typed `$B`. Every refuse row below past the first block was rc 0 on the unfixed guard; the allow rows pin that the expansion did not turn the guard onto prose or onto a word bash never expands.

THE GUARD IS DRIVEN THROUGH dispatch.py, the path every hook event takes, and the paths are derived from this file so another worktree tests its own copy.
"""

import ast
import importlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import Any

HOOKS = pathlib.Path(__file__).resolve().parents[1]
ROOT = HOOKS.parents[1]
DISPATCH = str(HOOKS / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_cli_bundle"]
# Assembled so this file is not itself a tripwire for a guard scanning the harness's own command line.
BUNDLE = "packages/cli/dist/" + "cli-bundle.cjs"
SET = "B=" + BUNDLE + "; "

LINKS = tempfile.mkdtemp(prefix="entry-link-harness-")
# A link to the bundle under another name and directory: the typed word names neither `cli-bundle` nor `packages/cli/dist`. The target need not exist; the kernel resolves the link to its path either way.
LINK = os.path.join(LINKS, "rdc-entry.cjs")
os.symlink(str(ROOT / BUNDLE), LINK)
OTHER_LINK = os.path.join(LINKS, "tool.mjs")
os.symlink(str(ROOT / "scripts" / "dev" / "x.mjs"), OTHER_LINK)

CASES = [
    # (name, command, expect_blocked)
    # Typed forms the guard refused before the fix, kept as the floor.
    ("typed bundle path", "node " + BUNDLE + " --version", True),
    ("typed bundle after &&", "cd . && node " + BUNDLE, True),
    # The live escape and its spellings: the program reaches node through a variable.
    ("assigned then $B (the live 2026-10-15 run)", SET + "node $B config field set x y", True),
    ('assigned then "$B"', SET + 'node "$B" --version', True),
    ("assigned then ${B}", SET + "node ${B} --version", True),
    ("assignment joined by &&", "B=" + BUNDLE + " && node $B", True),
    ("export B=... then $B", "export " + SET + "node $B", True),
    ("assigned, exported, then $B", SET + "export B; node $B", True),
    ("-- before the program", SET + "node -- $B", True),
    ("a flag before the program", SET + "node --enable-source-maps $B", True),
    ("the directory from a variable", "P=packages/cli/dist; node $P/" + "cli-bundle.cjs", True),
    ("the directory from a braced variable", "P=packages/cli/dist; node ${P}/index.js", True),
    # The program word names neither marker; the directory the run executes in does.
    ("relative path after cd", "cd packages/cli && node dist/index.js", True),
    ("relative path after cd ;", "cd packages/cli/dist; node ./index.js", True),
    ("cd through a variable", "D=packages/cli; cd $D && node dist/index.js", True),
    ("a symlink to the bundle", "node " + LINK + " --version", True),
    ("a symlink through a variable", "L=" + LINK + "; node $L", True),
    # The other runtimes that run a JavaScript file run the bundle just the same, around ./rdc.sh.
    ("bun runs the bundle", "bun " + BUNDLE, True),
    ("bun run runs the bundle", "bun run " + BUNDLE, True),
    ("deno run runs the bundle", "deno run -A " + BUNDLE, True),
    ("tsx runs the bundle", "tsx " + BUNDLE, True),
    ("bun through a variable", SET + "bun $B", True),
    ("npx node through a variable", SET + "npx node $B", True),
    ("find -exec node through a variable", SET + r"find . -maxdepth 0 -exec node $B \;", True),
    # The outer shell expands a double-quoted payload before the inner shell parses it.
    ("bash -c with a double-quoted payload", SET + 'bash -c "node $B"', True),
    ("the runner's name from a variable", "N=node; " + SET + "$N $B", True),
    # The shell's name from a variable is a shell too (review 06ac1c92.1).
    (
        "the shell's name from a variable, double-quoted payload",
        "N=bash; " + SET + '$N -c "node $B"',
        True,
    ),
    (
        "the shell's name from a variable, typed payload",
        "N=bash; $N -c 'node " + BUNDLE + "'",
        True,
    ),
    # The whole build output is the CLI (review 06ac1c92.3): dist/index.js is the package's `main` and `npm start`.
    ("the package main under dist", "node packages/cli/dist/index.js --version", True),
    (
        "a nested module under dist after cd",
        "cd packages/cli && node dist/commands/config.js",
        True,
    ),
    # xargs appends what it reads when the runner names no program of its own.
    ("xargs node fed a here-string", SET + "xargs node <<< $B", True),
    ("xargs node fed by echo", "echo " + BUNDLE + " | xargs node", True),
    ("xargs -I node fed by echo", "echo " + BUNDLE + " | xargs -I{} node {} --version", True),
    # Controls: each must stay allowed.
    ("the wrapper", "./rdc.sh config field set x y", False),
    ("node of another file through a variable", "B=scripts/dev/x.mjs; node $B", False),
    ("node of the build entry after cd", "cd packages/cli && node bundle.mjs", False),
    # The two typed shapes the declared DEFECT turns back into refusals.
    ("the build entry, typed", "node packages/cli/bundle.mjs", False),
    (
        "the dist directory as a typed output flag",
        "node scripts/x.mjs --outdir packages/cli/dist/out.js",
        False,
    ),
    ("a symlink to another file", "node " + OTHER_LINK, False),
    (
        "a sentence naming the bundle",
        "echo the bundle is " + BUNDLE + ", run it with ./rdc.sh",
        False,
    ),
    ("echo of the expanded command", SET + "echo node $B", False),
    ("the bundle as a non-program operand", SET + "ls -la $B", False),
    (
        "the dist directory as an output value",
        "B=packages/cli/dist; node scripts/x.mjs --outdir $B",
        False,
    ),
    # bash expands $B before env sets it, so node is handed no program at all (measured: `env B=x echo $B` prints an empty line).
    ("env B=... node $B gives node nothing", "env B=" + BUNDLE + " node $B", False),
    # A word whose value cannot be known stays as before the fix: unjudged.
    ("an unset variable", "node $UNSET_BUNDLE_VAR", False),
    ("a command substitution", "node $(cat entry.txt)", False),
    (
        "xargs feeding an argument to another program",
        "echo " + BUNDLE + " | xargs node scripts/dev/x.mjs",
        False,
    ),
    # A single-quoted payload is the inner shell's, where an unexported B is empty.
    ("bash -c with a single-quoted payload, B not exported", SET + "bash -c 'node $B'", False),
    (
        "the shell's name from a variable, payload echoes",
        "N=bash; $N -c 'echo node " + BUNDLE + "'",
        False,
    ),
    # Not the CLI's build output: another package's dist, and a sibling directory whose name only starts with `dist`.
    ("another package's dist", "node packages/www/dist/server.js", False),
    ("a sibling of the CLI's dist", "node packages/cli/dist-old/index.js", False),
    ("bun install", "bun install", False),
    ("deno fmt", "deno fmt", False),
]


def payload(cmd):
    return {"tool_input": {"command": cmd}, "cwd": str(ROOT)}


def run(cmd):
    p = subprocess.run(
        GUARD_ARGV,
        input=json.dumps(payload(cmd)),
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )
    return p.returncode


# THE CONTROLS ARE PLANTED, AND EACH MUST TURN AT LEAST ONE ROW. The declared DEFECT (the `.*` back between the program slot and the bundle name) and the defect #e13fb555 fixed (the program read from the words as typed): a harness neither one turns red proves nothing about the code it names.
_SYSPATH = importlib.util.spec_from_file_location("rediacc_hooks_syspath", HOOKS / "syspath.py")
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: rediacc_hooks/syspath.py is missing" % __file__)
_syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(_syspath)
_syspath.on_sys_path(str(HOOKS.parent))
hookio = importlib.import_module("rediacc_hooks.hookio")
GUARD = importlib.import_module("rediacc_hooks.guards.block_cli_bundle")
GUARD_SRC = (HOOKS / "guards" / "block_cli_bundle.py").read_text(encoding="utf-8")
# The mutant for review 06ac1c92.1 (the shell's name read as typed) is retired: shellscan resolves a variable shell name itself since #156caed2, and the guard's own name lookup, launch re-parse and `-c` payload re-walk are gone with it (#d6d000ad); the rows they guarded stay, refused through shellscan.
MUTANTS = [
    (
        "the program read as typed (#e13fb555)",
        ("run.xargv if run.xargv is not None else run.argv", "run.argv"),
    ),
]


def _outside_declarations(src):
    """`src` without its top-level `DEFECT` assignment, so a plant cannot be found inside the line that declares it."""
    cut = [
        n
        for n in ast.parse(src).body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "DEFECT" for t in n.targets)
    ]
    return "\n".join(
        line
        for i, line in enumerate(src.split("\n"), 1)
        if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut)
    )


def planted_runner(old, new):
    """The guard with `old` replaced by `new`, run in-process; None when `old` is not in the guard outside its DEFECT declaration."""
    if old not in _outside_declarations(GUARD_SRC):
        return None
    ns: dict[str, Any] = {
        "__name__": "planted_block_cli_bundle",
        "__file__": str(HOOKS / "guards" / "block_cli_bundle.py"),
    }
    exec(compile(GUARD_SRC.replace(old, new), ns["__file__"], "exec"), ns)

    def judged(cmd):
        event = hookio.Event(json.dumps(payload(cmd)))
        return ns["run"](event)

    return judged


fails = 0
try:
    for name, cmd, want in CASES:
        rc = run(cmd)
        got = rc == 2
        ok = got == want and rc in (0, 2)
        fails += not ok
        print(
            "%-46s want=%-9s got=%-9s rc=%d %s"
            % (
                name,
                "BLOCKED" if want else "allowed",
                "BLOCKED" if got else "allowed",
                rc,
                "ok" if ok else "*** FAIL ***",
            )
        )
    print()
    for label, (old, new) in [("DEFECT", GUARD.DEFECT), *MUTANTS]:
        judged = planted_runner(old, new)
        if judged is None:
            fails += 1
            print("plant %-40s *** FAIL *** it no longer applies to the guard" % label)
            continue
        turned = [name for name, cmd, want in CASES if (judged(cmd) == 2) != want]
        fails += not turned
        print(
            "plant %-40s turns %d row(s) %s"
            % (label, len(turned), "ok" if turned else "*** FAIL *** the harness cannot see it")
        )
finally:
    for path in (LINK, OTHER_LINK):
        os.unlink(path)
    os.rmdir(LINKS)

print()
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
