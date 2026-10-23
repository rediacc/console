#!/usr/bin/env python3
"""block_roundlog_truncate: a redirect onto a variable the command assigned is read as bash expands it (#7b3f34ae).

The guard's broad differential is `hookcases.py`; this file pins the redirect-target rows only, in both directions through dispatch.py, then plants the typed-only read in-process and requires it to turn a row. Rows measured at 0600a4642: each refusal was allowed (rc 0), because the redirect target was read as typed (`$L`).

    test-block_roundlog_truncate.py
"""

import importlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import typing

HERE = pathlib.Path(__file__).resolve()
HOOKS = HERE.parents[1]
DISPATCH = str(HOOKS / "dispatch.py")
STEM = "block_roundlog_truncate"
LOG = "agent/pr-babysit-1008-1.md"

CASES = [
    ("truncate through an assigned name", "L=%s; echo x > $L" % LOG, True),
    ("truncate through a braced name", "L=%s; echo x > ${L}" % LOG, True),
    ("truncate through a directory and a name", "D=agent; echo x > $D/pr-babysit-1008-1.md", True),
    (
        "truncate through a name assigned in an if",
        "L=/tmp/x.md; if true; then L=%s; fi; echo x > $L" % LOG,
        True,
    ),
    ("append through an assigned name", "L=%s; echo x >> $L" % LOG, False),
    ("truncate through a name holding another file", "L=/tmp/notes.md; echo x > $L", False),
    ("truncate through an unset variable", "echo x > $UNSET_L", False),
    ("redirect bash refuses as ambiguous", 'L="%s %s"; echo x > $L' % (LOG, LOG), False),
    # #63109cf2: a glob literal puts a log in play only where it can reach a log directory. The first two were refused (rc 2) at 8ef785864, a regex read as a glob meeting the log name while the program writes another file or none; the last three still reach `agent/` and stay refused.
    (
        "a regex in a program that slices an unrelated file",
        "python3 - <<'PY'\nimport pathlib, re, tempfile\np = pathlib.Path(tempfile.mkdtemp()) / 'out.txt'\ns = 'abc def'\nm = re.search(r'[A-Za-z_][A-Za-z0-9_]*', s)\np.write_text(s[:m.end()])\nPY",
        False,
    ),
    (
        "a program that imports the guard and prints",
        "python3 -c \"import sys; sys.path.insert(0, '.claude'); from rediacc_hooks.guards import block_roundlog_truncate as g; print(g._glob_meets_log('[a-z]*'))\"",
        False,
    ),
    (
        "a bare glob under cd agent",
        "cd agent && python3 - <<'PY'\nimport glob\nfor p in glob.glob('[a-z]*'):\n    open(p, 'w').write('')\nPY",
        True,
    ),
    (
        "a bare glob after chdir into agent",
        "python3 - <<'PY'\nimport glob, os\nos.chdir('agent')\nfor p in glob.glob('[a-z]*'):\n    open(p, 'w').write('')\nPY",
        True,
    ),
    (
        "a recursive glob",
        "python3 - <<'PY'\nimport glob\nfor p in glob.glob('**/[a-z]*', recursive=True):\n    open(p, 'w').write('')\nPY",
        True,
    ),
    # #3df07b02: a `**` under a fixed directory that is not a log directory walks only that tree. The first was refused (rc 2) at b9674ed79 (the live heredoc, minimised: it imports a module the reader cannot follow and only prints); the rest reach `agent/` and stay refused.
    (
        "a recursive glob under a fixed non-log directory, printed",
        "python3 -I - <<'EOF2'\nimport sys; sys.path.insert(0,'.claude/hooks/stop')\nimport wl_planconc as X\nprint(X.spawn_verdict({'a.md'}, {}, None, declared=('workers/account/src/telemetry/**',)))\nEOF2",
        False,
    ),
    (
        "a recursive glob under a fixed non-log directory, written through",
        "python3 - <<'PY'\nimport glob\nfor p in glob.glob('workers/src/**', recursive=True):\n    open(p, 'w').write('')\nPY",
        False,
    ),
    (
        "a recursive glob under agent",
        "python3 - <<'PY'\nimport glob\nfor p in glob.glob('agent/**', recursive=True):\n    open(p, 'w').write('')\nPY",
        True,
    ),
    (
        "a recursive glob under a parent directory",
        "python3 - <<'PY'\nimport glob\nfor p in glob.glob('workers/../**', recursive=True):\n    open(p, 'w').write('')\nPY",
        True,
    ),
    (
        "a recursive glob that climbs out after the stars (3800cd21.1)",
        "python3 - <<'PY'\nimport glob\nfor p in glob.glob('workers/**/../../agent/pr-*.md', recursive=True):\n    open(p, 'w').write('')\nPY",
        True,
    ),
    (
        "a recursive glob under a fixed directory after chdir",
        "python3 - <<'PY'\nimport glob, os\nos.chdir('/')\nfor p in glob.glob('home/u/console/**', recursive=True):\n    open(p, 'w').write('')\nPY",
        True,
    ),
    (
        "a recursive glob from the root",
        "python3 - <<'PY'\nimport glob\nfor p in glob.glob('/home/u/console/**', recursive=True):\n    open(p, 'w').write('')\nPY",
        True,
    ),
]

# The two readers overlap (each alone refuses the same rows), so the plant takes both.
MUTANTS = [
    (
        "both redirect readers take the typed target",
        [
            (
                "    words = [target for _op, target in _redirects(shellscan._analyse(cmd))]\n",
                "    words = [target for _op, target in shellscan._analyse(cmd).writes]\n",
            ),
            (
                "        for op, target in _redirects(shellscan._analyse(cmd))\n",
                "        for op, target in shellscan._analyse(cmd).writes\n",
            ),
        ],
    ),
    (
        "any recursive glob reaches a log directory (#3df07b02)",
        [
            (
                "                if _recursive_reaches_log_dir(alt, context):\n",
                "                if True:\n",
            ),
        ],
    ),
    (
        "any glob literal puts a log in play (#63109cf2)",
        [
            (
                '        and _glob_reaches_log_dir(m.group(0)[1:-1], code + "\\n" + (context or ""))\n',
                "",
            ),
        ],
    ),
]


def via_dispatch(command, cwd):
    proc = subprocess.run(
        [sys.executable, DISPATCH, STEM],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def planted(scratch, pairs):
    """The guard with each `(old, new)` pair of `pairs` applied, imported in-process from a copy under `scratch`; None when an `old` is not in the guard."""
    src = HERE.with_name(STEM + ".py").read_text(encoding="utf-8")
    if any(old not in src for old, _new in pairs):
        return None
    for old, new in pairs:
        src = src.replace(old, new)
    # The canonical, idempotent hop (rediacc_hooks/syspath.py), as test-block_cli_bundle.py takes it; a bare insert run per mutant left one copy per call.
    syspath_spec = importlib.util.spec_from_file_location(
        "rediacc_hooks_syspath", HOOKS / "syspath.py"
    )
    if syspath_spec is None or syspath_spec.loader is None:
        raise SystemExit("%s: rediacc_hooks/syspath.py is missing" % __file__)
    syspath = importlib.util.module_from_spec(syspath_spec)
    syspath_spec.loader.exec_module(syspath)
    syspath.on_sys_path(str(HOOKS.parent))
    hookio = importlib.import_module("rediacc_hooks.hookio")
    copy = scratch / ("mutant_%s.py" % STEM)
    copy.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("mutant_" + STEM, copy)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load the planted copy of %s" % STEM)
    broken: typing.Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(broken)

    def run(command, cwd):
        event = hookio.Event(
            json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd})
        )
        rc = broken.run(event)
        _rc, out, err = event.result(rc)
        return rc, out + err

    return run


def main():
    cwd = str(HOOKS.parents[1])
    fails = 0
    for name, command, refused in CASES:
        rc, text = via_dispatch(command, cwd)
        ok = (rc != 0) == refused
        fails += not ok
        print(
            "%-48s want=%-8s %s"
            % (
                name,
                "BLOCKED" if refused else "allowed",
                "ok" if ok else "*** FAIL *** " + text[:200],
            )
        )
    refusals = sum(1 for c in CASES if c[2])
    if refusals < 3 or len(CASES) - refusals < 3:
        print("FLOOR: at least 3 cases of each direction")
        fails += 1
    print("FAILURES: %d" % fails)
    mutant_fails = 0
    with tempfile.TemporaryDirectory(prefix="roundlog-mutants-") as tmp:
        for label, pairs in MUTANTS:
            run = planted(pathlib.Path(tmp), pairs)
            if run is None:
                mutant_fails += 1
                print("plant %-52s *** FAIL *** it no longer applies to the guard" % label)
                continue
            turned = sum(1 for _n, c, refused in CASES if (run(c, cwd)[0] != 0) != refused)
            mutant_fails += not turned
            print(
                "plant %-52s turns %d row(s) %s"
                % (label, turned, "ok" if turned else "*** FAIL *** the harness cannot see it")
            )
    print("MUTANT FAILURES: %d" % mutant_fails)
    return 1 if fails or mutant_fails else 0


if __name__ == "__main__":
    sys.exit(main())
