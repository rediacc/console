#!/usr/bin/env python3
"""Control harness for block_user_only_command and block_user_only_command_shell_write, the two write-time halves of "no command or skill is user-only" (operator ruling 2026-10-09).

This file runs the Edit half; `test-block_user_only_command_shell_write.py` beside it runs the shell half through the same code, so each guard has the dedicated `test-<stem>.py` check-hook-integrity credits. Both directions for each half, because a one-sided control is satisfiable by a broken hook: one that always refuses passes the refusal cases, one that never refuses passes the allowed ones. Then each guard's declared DEFECT is planted in-process and the run MUST fail, which is the proof the cases can.

The Edit, MultiEdit and copy cases need a file on disk, so every case runs against a scratch tree (`world()`) holding a clean command, a command that still carries the key, and copy sources with and without it; the payload's `cwd` points there.

    test-block_user_only_command.py        run every Edit case through dispatch.py, then the DEFECT run
"""

import ast
import importlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import typing

HERE = pathlib.Path(__file__).resolve()
_SYSPATH = importlib.util.spec_from_file_location(
    "rediacc_hooks_syspath", HERE.parent.parent / "syspath.py"
)
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: rediacc_hooks/syspath.py is missing" % __file__)
_syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(_syspath)
DISPATCH = str(HERE.parents[1] / "dispatch.py")
NEEDLE = "a user-only command is an operator decision: the operator edits it with !"

K = "disable-model-invocation"
CLEAN = "---\ndescription: a command\nallowed-tools: Bash(ls:*)\n---\n\nBody.\n"
FLAGGED = "---\ndescription: a command\n%s: true\n---\n\nBody.\n" % K
C = ".claude/commands/clean.md"
F = ".claude/commands/flagged.md"
S = ".claude/skills/s/SKILL.md"
# The scratch tree's own exception list: one LISTED command keeps the key as `true`.
LISTED = ".claude/commands/listed.md"
LIST = ".ci/config/model-invocation-exceptions.json"
LIST_TEXT = json.dumps(
    {
        "exceptions": [
            {
                "path": LISTED,
                "value": "true",
                "ruling": {
                    "date": "2026-10-09",
                    "quote": "a scratch ruling, quoted verbatim for the harness",
                },
            }
        ]
    }
)


def world(root: pathlib.Path) -> None:
    """The scratch tree every case runs in."""
    for rel, text in (
        (C, CLEAN),
        (F, FLAGGED),
        (S, CLEAN),
        ("src/flagged.md", FLAGGED),
        ("src/clean.md", CLEAN),
        ("srcdir/a.md", FLAGGED),
        (LISTED, FLAGGED),
        (LIST, LIST_TEXT),
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _w(path, content):
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}


def _e(path, old, new, **extra):
    tin = {"file_path": path, "old_string": old, "new_string": new}
    tin.update(extra)
    return {"tool_name": "Edit", "tool_input": tin}


EDIT_CASES = [
    # (name, payload, refused?)
    ("Write adding the key", _w(C, FLAGGED), True),
    ("Write setting it false", _w(C, FLAGGED.replace("true", "false")), True),
    ("Write with an empty value", _w(C, FLAGGED.replace(": true", ":")), True),
    (
        "Write with underscores and caps",
        _w(C, FLAGGED.replace(K, "Disable_Model_Invocation")),
        True,
    ),
    ("Write with camelCase", _w(C, FLAGGED.replace(K, "disableModelInvocation")), True),
    (
        "Write with spaces and a quoted YES",
        _w(C, FLAGGED.replace(K + ": true", 'disable model invocation :  "YES"')),
        True,
    ),
    ("Write with a quoted key", _w(C, FLAGGED.replace(K, "'%s'" % K)), True),
    ("Write into a skill", _w(S, FLAGGED), True),
    (
        "Write into a nested command tree",
        _w("private/account/.claude/commands/t.md", FLAGGED),
        True,
    ),
    ("Write into a namespaced command", _w(".claude/commands/ns/t.md", FLAGGED), True),
    ("Write with an unclosed frontmatter", _w(C, "---\n%s: on\n" % K), True),
    ("Edit adding the key", _e(C, "allowed-tools:", "%s: true\nallowed-tools:" % K), True),
    ("Edit flipping true to false keeps the key", _e(F, "%s: true" % K, "%s: false" % K), True),
    ("Edit elsewhere in a file that keeps the key", _e(F, "Body.", "Body two."), True),
    (
        "MultiEdit adding the key in its second edit",
        {
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": C,
                "edits": [
                    {"old_string": "Body.", "new_string": "Body two."},
                    {"old_string": "allowed-tools:", "new_string": "%s: yes\nallowed-tools:" % K},
                ],
            },
        },
        True,
    ),
    (
        "NotebookEdit naming a command path",
        {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": C, "new_source": FLAGGED}},
        True,
    ),
    # allowed
    ("Edit removing the key", _e(F, "%s: true\n" % K, ""), False),
    (
        "MultiEdit removing the key",
        {
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": F,
                "edits": [{"old_string": "%s: true\n" % K, "new_string": ""}],
            },
        },
        False,
    ),
    ("Write of a clean command", _w(C, CLEAN), False),
    (
        "Write whose body only mentions the key",
        _w(C, CLEAN + "\nNever set `%s: true`.\n" % K),
        False,
    ),
    (
        "Write with a commented-out key",
        _w(C, CLEAN.replace("---\n\n", "# %s: true\n---\n\n" % K)),
        False,
    ),
    (
        "Write of a skill's user-invocable key",
        _w(S, CLEAN.replace("---\n\n", "user-invocable: false\n---\n\n")),
        False,
    ),
    ("Write outside the command directories", _w("docs/x.md", FLAGGED), False),
    ("Write to a sub-agent definition", _w(".claude/agents/x.md", FLAGGED), False),
    (
        "Write to a non-Markdown file in the directory",
        _w(".claude/commands/notes.txt", FLAGGED),
        False,
    ),
    ("Edit whose old_string is absent", _e(C, "no such text", "%s: true" % K), False),
    ("no path", {"tool_name": "Write", "tool_input": {"content": FLAGGED}}, False),
    # The exception list.
    ("Edit removing the key from a LISTED file", _e(LISTED, "%s: true\n" % K, ""), True),
    ("Edit flipping a LISTED file to false", _e(LISTED, "%s: true" % K, "%s: false" % K), True),
    ("Write of the exception list", _w(LIST, LIST_TEXT), True),
    ("Edit of the exception list", _e(LIST, "listed.md", "clean.md"), True),
    ("Edit elsewhere in a LISTED file", _e(LISTED, "Body.", "Body two."), False),
    (
        "Write of a LISTED file keeping its key",
        _w(LISTED, FLAGGED.replace("Body.", "New body.")),
        False,
    ),
]

SHELL_CASES = [
    ("heredoc writing the key", "cat > %s <<'EOF'\n%sEOF" % (C, FLAGGED), True),
    (
        "heredoc writing the key with an EMPTY value",
        "cat > %s <<'EOF'\n---\n%s:\n---\nEOF" % (C, K),
        True,
    ),
    ("append of another spelling", "echo 'Disable_Model_Invocation: yes' >> %s" % C, True),
    ("printf false through tee", "printf -- '---\\n%s: false\\n---\\n' | tee %s" % (K, S), True),
    (
        "sed -i adding the key",
        "sed -i 's/^description:/%s: true\\ndescription:/' %s" % (K, C),
        True,
    ),
    ("sed -i appending the key", "sed -i '1a %s: true' %s" % (K, C), True),
    ("cp of a flagged source", "cp src/flagged.md %s" % C, True),
    ("cp of a flagged source onto the directory", "cp src/flagged.md .claude/commands/", True),
    ("cp -r of a directory with a flagged file", "cp -r srcdir .claude/skills/", True),
    ("mv of a flagged source", "mv src/flagged.md .claude/commands/new.md", True),
    # The target-directory option names the destination and makes every operand a source (review cac47d16.1): each was allowed (rc 0) before.
    ("cp -t into the command directory", "cp -t .claude/commands src/flagged.md", True),
    ("cp --target-directory=", "cp --target-directory=.claude/commands src/flagged.md", True),
    (
        "an abbreviated --target with its own word",
        "cp --target .claude/commands src/flagged.md",
        True,
    ),
    ("a bundle ending in t", "cp -rt .claude/skills srcdir", True),
    ("mv -t", "mv -t .claude/commands src/flagged.md", True),
    ("install -m then -t", "install -m 644 -t .claude/commands src/flagged.md", True),
    ("ln -t", "ln -t .claude/commands src/flagged.md", True),
    ("a value option after the operands", "cp src/flagged.md .claude/commands/ -S .bak", True),
    (
        "rsync with an option after the operands",
        "rsync src/flagged.md .claude/commands/ --exclude x",
        True,
    ),
    ("xargs appends the destination", "echo .claude/commands/ | xargs cp src/flagged.md", True),
    (
        "python heredoc writing the key",
        "python3 - <<'EOF'\nimport pathlib\npathlib.Path('%s').write_text('---\\n%s: true\\n---\\n')\nEOF"
        % (C, K),
        True,
    ),
    ("python -c writing the key", "python3 -c \"open('%s','w').write('%s: on')\"" % (C, K), True),
    ("after cd", "cd .claude/commands && echo '%s: 1' >> x.md" % K, True),
    ("inside sh -c", "sh -c \"echo '%s: true' >> %s\"" % (K, C), True),
    # allowed
    ("sed -i deleting the key line", "sed -i '/^%s:/d' %s" % (K, F), False),
    ("sed -i substituting the key away", "sed -i 's/^%s: true$//' %s" % (K, F), False),
    ("cp of a clean source", "cp src/clean.md %s" % C, False),
    ("cp of a command OUT of the directory", "cp %s /tmp/x.md" % F, False),
    ("cp -t of a command OUT of the directory", "cp -t /tmp %s" % F, False),
    ("cp -t of a clean source", "cp -t .claude/commands src/clean.md", False),
    ("rsync -t keeps times; the last operand is the destination", "rsync -t %s /tmp/" % F, False),
    ("echo to the terminal", "echo '%s: true is banned'" % K, False),
    ("grep for the key", "grep -rn '%s' .claude/commands" % K, False),
    ("heredoc into a doc", "cat > docs/x.md <<'EOF'\n%sEOF" % FLAGGED, False),
    (
        "commit message heredoc naming the key",
        "git commit -F - <<'EOF'\nfix: drop %s: true\nEOF" % K,
        False,
    ),
    ("a clean command written", "printf -- '---\\ndescription: x\\n---\\n' > %s" % C, False),
    ("unrelated redirect", "echo x > /tmp/out.txt", False),
    # The exception list.
    ("sed -i deleting the key of a LISTED file", "sed -i '/^%s:/d' %s" % (K, LISTED), True),
    ("append to the exception list", "echo '{}' >> %s" % LIST, True),
    ("sed -i on the exception list", "sed -i 's/listed/clean/' %s" % LIST, True),
    ("cp onto the exception list", "cp /tmp/x.json %s" % LIST, True),
    (
        "cp -t into the exception list's directory",
        "cp -t .ci/config /tmp/model-invocation-exceptions.json",
        True,
    ),
    (
        "cp into the exception list's directory",
        "cp /tmp/model-invocation-exceptions.json .ci/config/",
        True,
    ),
    (
        "python writing the exception list",
        "python3 -c \"open('%s','w').write('{}')\"" % LIST,
        True,
    ),
    (
        "heredoc overwriting a LISTED file, key kept",
        "cat > %s <<'EOF'\n%sEOF" % (LISTED, FLAGGED),
        False,
    ),
    ("cp of a flagged source onto a LISTED file", "cp src/flagged.md %s" % LISTED, False),
    ("sed -i elsewhere in a LISTED file", "sed -i 's/Body/Text/' %s" % LISTED, False),
    ("reading the exception list", "cat %s" % LIST, False),
]


def via_dispatch(stem, payload):
    p = subprocess.run(
        [sys.executable, DISPATCH, stem],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    return p.returncode, p.stdout + p.stderr


def _outside_defect(src: str) -> str:
    """`src` with the top-level `DEFECT` assignment removed, so a needle search cannot be satisfied by the declaration that names it."""
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


def defect_runner(stem, scratch):
    """The guard with its declared DEFECT planted, imported in-process from a copy under `scratch` (an import, so no `exec` call is needed)."""
    _syspath.on_sys_path(str(HERE.parents[2]))
    hookio = importlib.import_module("rediacc_hooks.hookio")
    good = importlib.import_module("rediacc_hooks.guards.%s" % stem)
    old, new = good.DEFECT
    src = pathlib.Path(str(good.__file__)).read_text(encoding="utf-8")
    if old not in _outside_defect(src):
        raise SystemExit("the DEFECT no longer applies to %s outside its own declaration" % stem)
    planted = scratch / ("broken_%s.py" % stem)
    planted.write_text(src.replace(old, new), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("broken_" + stem, planted)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load the planted copy of %s" % stem)
    broken: typing.Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(broken)

    def run(_stem, payload):
        event = hookio.Event(json.dumps(payload))
        rc = broken.run(event)
        _rc, out, err = event.result(rc)
        return rc, out + err

    return run


def run_cases(stem, cases, runner, root, quiet=False):
    fails = 0
    for name, raw, refused in cases:
        world(root)
        payload = dict(raw, cwd=str(root))
        rc, text = runner(stem, payload)
        blocked = rc != 0
        ok = blocked == refused and (not refused or NEEDLE in text)
        fails += not ok
        if not quiet:
            print(
                "%-50s want=%-8s %s"
                % (
                    name,
                    "BLOCKED" if refused else "allowed",
                    "ok" if ok else "*** FAIL *** " + text[:200],
                )
            )
    return fails


def main(stems=("block_user_only_command",)):
    shell = [(n, {"tool_name": "Bash", "tool_input": {"command": c}}, r) for n, c, r in SHELL_CASES]
    suites = {"block_user_only_command": EDIT_CASES, "block_user_only_command_shell_write": shell}
    total = 0
    with tempfile.TemporaryDirectory(prefix="uo-guard-") as tmp:
        root = pathlib.Path(tmp) / "world"
        scratch = pathlib.Path(tmp) / "planted"
        scratch.mkdir()
        for stem in stems:
            cases = suites[stem]
            print("== %s" % stem)
            total += run_cases(stem, cases, via_dispatch, root)
            refusals = sum(1 for c in cases if c[2])
            if refusals < 4 or len(cases) - refusals < 4:
                print("FLOOR: at least 4 cases of each direction")
                total += 1
            planted = run_cases(stem, cases, defect_runner(stem, scratch), root, quiet=True)
            print(
                "DEFECT planted in %s: %d case(s) fail%s"
                % (stem, planted, "" if planted else "  *** the suite cannot fail ***")
            )
            total += planted == 0
    print("FAILURES: %d" % total)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
