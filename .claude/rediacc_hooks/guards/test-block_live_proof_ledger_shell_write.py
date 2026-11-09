#!/usr/bin/env python3
"""Control harness for block_live_proof_ledger_shell_write: the shell half of "the live-proof ledger is written only by the recorder" (agent/plans/PLAN-tested-on-bench.md box V10).

The cases, the scratch world and the runner live in `test-block_live_proof_ledger_write.py` beside this file, so the two halves are judged by one set of rules; this file runs the shell cases through dispatch.py in both directions (a planted hand-appended row refused, the recorder's append allowed), then plants the guard's DEFECT and requires the run to fail.

    test-block_live_proof_ledger_shell_write.py
"""

import importlib.util
import pathlib
import sys

SHARED = pathlib.Path(__file__).resolve().with_name("test-block_live_proof_ledger_write.py")


def _py(body):
    return "python3 - <<'PY'\n%s\nPY" % body


def searched_text_cases(ledger):
    """#4e20f8c5: the ledger's path as TEXT searched for inside another file's content is not a write to the ledger; the same path as a write target, however it is reached, still is. `(name, command, refused?)`, the shared file's shape."""
    plan = "agent/plans/PLAN-backup-program.md"
    owns = "Owns: x, %s" % ledger
    return [
        # The refused command of 2026-10-28, and its spellings.
        (
            "python edits a PLAN line naming the ledger",
            _py(
                "import pathlib\np = pathlib.Path('%s')\ns = p.read_text()\n"
                "s = s.replace('%s', 'Owns: x')\np.write_text(s)" % (plan, owns)
            ),
            False,
        ),
        (
            "python edits a PLAN through a bound old string",
            _py(
                "p = '%s'\ns = open(p).read()\nold = '%s'\ns = s.replace(old, 'Owns: y')\n"
                "open(p, 'w').write(s)" % (plan, owns)
            ),
            False,
        ),
        (
            "python -c edits a PLAN line naming the ledger",
            "python3 -c \"import pathlib; p=pathlib.Path('%s'); s=p.read_text(); "
            "s=s.replace('%s', 'x'); p.write_text(s)\"" % (plan, owns),
            False,
        ),
        (
            "python keeps the ledger in the replacement text",
            _py(
                "import pathlib\np = pathlib.Path('%s')\ns = p.read_text()\n"
                "s = s.replace('Owns: x', '%s')\np.write_text(s)" % (plan, owns)
            ),
            False,
        ),
        (
            "python strips a suffix naming the ledger",
            _py(
                "import pathlib\np = pathlib.Path('%s')\ns = p.read_text().rstrip()\n"
                "s = s.removesuffix(', %s')\np.write_text(s)" % (plan, ledger)
            ),
            False,
        ),
        (
            "python re.sub of a pattern naming the ledger",
            _py(
                "import pathlib, re\np = pathlib.Path('%s')\ns = p.read_text()\n"
                "s = re.sub(r'%s', 'x', s)\np.write_text(s)" % (plan, ledger)
            ),
            False,
        ),
        # A function's first argument is judged as its destination (`json.dump(obj, fh)` included), so the searched text inside it must not count as the ledger.
        (
            "python dumps text with the ledger replaced out",
            _py(
                "import json\ns = open('%s').read()\n"
                "json.dump(s.replace('%s', 'x'), open('/tmp/plan.json', 'w'))" % (plan, owns)
            ),
            False,
        ),
        # The other direction: every shape where the ledger IS the target stays refused.
        (
            "python writes the ledger path it also searched with",
            _py(
                "p = '%s'\ns = open('/tmp/x').read().replace(p, 'y')\nopen(p, 'w').write(s)"
                % ledger
            ),
            True,
        ),
        (
            "python builds the ledger path from a replacement and writes it",
            _py(
                "import pathlib\nt = 'agent/ledgers/X'.replace('X', 'live-proof.jsonl')\n"
                "pathlib.Path(t).write_text('{}')"
            ),
            True,
        ),
        (
            "python os.replace onto the ledger through an alias",
            _py("import os as o\no.replace('/tmp/forged.jsonl', '%s')" % ledger),
            True,
        ),
        (
            "python Path.replace moves a forgery onto the ledger",
            _py("import pathlib\npathlib.Path('/tmp/forged.jsonl').replace('%s')" % ledger),
            True,
        ),
        (
            "python appends to the ledger after editing a PLAN",
            _py(
                "import pathlib\np = pathlib.Path('%s')\np.write_text(p.read_text().replace('%s', 'x'))\n"
                "open('%s', 'a').write('{}')" % (plan, owns, ledger)
            ),
            True,
        ),
    ]


def review_cases():
    """Review 22b7a40c: a copy relative to the run's own `cd` (.1), a ledger name built from pieces (.2), and a read-only call on the ledger's name that only sounds like a write (.3)."""
    lt = "PYTHONPATH=.ci python3 - <<'PY'\nfrom rediacc_ci.proof import live_tier as LT\n%s\nPY"
    return [
        (
            "cp onto the ledger relative to a cd",
            "cd agent/ledgers && cp /tmp/forged.jsonl live-proof.jsonl",
            True,
        ),
        (
            "cp onto the ledger through a partial cd",
            "cd agent && cp /tmp/forged.jsonl ledgers/live-proof.jsonl",
            True,
        ),
        (
            "python concatenates the ledger name",
            _py("open('agent/ledgers/live-proof' + '.jsonl', 'a').write('x')"),
            True,
        ),
        (
            "python concatenates the ledger name mid-word",
            _py("open('agent/ledgers/live-' + 'proof.jsonl', 'a').write('x')"),
            True,
        ),
        (
            "python builds the ledger name in an f-string",
            _py("d = 'agent/ledgers'\nopen(f'{d}/live-proof' '.jsonl', 'a').write('x')"),
            True,
        ),
        (
            "python binds a ledger piece and appends",
            _py("ext = '.jsonl'\np = 'agent/ledgers/live-proof' + ext\nopen(p, 'a').write('x')"),
            True,
        ),
        (
            "python concatenates another file's name",
            _py("open('agent/ledgers/effort' + '-outcomes.jsonl', 'a').write('x')"),
            False,
        ),
        (
            "python dumps the ledger's name to text",
            lt % "import json\nprint(json.dumps(LT.LEDGER))",
            False,
        ),
        (
            "python edits the ledger's name as text",
            lt % "print(str(LT.LEDGER).replace('a', 'b'))",
            False,
        ),
    ]


# The shape of `check_plan_citations._ledger_receipt_ids` that was refused while the script was changed in the main checkout (#9efac135): the ledger's rows read into `out` in one function, and `out.append(...)` growing a list of the same name in another, since bindings are read without scope.
CITES_SCRIPT = (
    "import json, pathlib\n"
    "def ids():\n"
    "    lines = (pathlib.Path('.') / 'agent' / 'ledgers' / 'live-proof.jsonl').read_text(encoding='utf-8')\n"
    "    out = [json.loads(line)['id'] for line in lines.splitlines()]\n"
    "    return out\n"
    "def plan_lines(rel):\n"
    "    out = []\n"
    "    for lineno, text in enumerate(pathlib.Path(rel).read_text().splitlines(), 1):\n"
    "        out.append((rel, lineno, text))\n"
    "    return out\n"
    "print(len(ids()))\n"
)


def read_is_not_write_cases(world, ledger):
    """#9efac135: a READ of the ledger binds its rows, never its path, and a PLAN heredoc beside another heredoc is judged by its own tree. `(name, command, refused?)`."""
    script = world / "check_cites.py"
    script.write_text(CITES_SCRIPT, encoding="utf-8")
    plan = "agent/plans/PLAN-x.md"
    msg = "cat > /tmp/msg <<'EOF'\nchore(plans): it's the receipt in %s\nEOF\n" % ledger
    return [
        # The false positives of 2026-11-08: each must be ALLOWED.
        ("python runs a changed script that reads the ledger", "python3 check_cites.py", False),
        (
            "sed -i a PLAN, then run that script",
            "sed -i 's|- \\[ \\] V1|- [x] V1|' %s && python3 check_cites.py" % plan,
            False,
        ),
        (
            "python heredoc reads receipt ids and edits a PLAN",
            _py(
                "import json, pathlib\nrows = open('%s').read().splitlines()\n"
                "out = [json.loads(r)['id'] for r in rows]\nout.append('lp-x')\n"
                "p = pathlib.Path('%s')\np.write_text(p.read_text() + ' '.join(out))"
                % (ledger, plan)
            ),
            False,
        ),
        (
            "python heredoc iterates a read-only handle on the ledger",
            _py(
                "import pathlib\nfh = open('%s')\nseen = list(fh)\nseen.append('end')\n"
                "pathlib.Path('%s').write_text(str(len(seen)))" % (ledger, plan)
            ),
            False,
        ),
        (
            "review 634e1ef5.1: Path.open('rb', -1) is a read, its negative buffering is not a mode",
            _py(
                "import pathlib\nfh = pathlib.Path('%s').open('rb', -1)\nseen = list(fh)\nseen.append('end')\n"
                "pathlib.Path('%s').write_text(str(len(seen)))" % (ledger, plan)
            ),
            False,
        ),
        (
            "review 68fffbc7.1: Path.open('rb', +1) is a read, its positive buffering is not a mode",
            _py(
                "import pathlib\nfh = pathlib.Path('%s').open('rb', +1)\nseen = list(fh)\nseen.append('end')\n"
                "pathlib.Path('%s').write_text(str(len(seen)))" % (ledger, plan)
            ),
            False,
        ),
        (
            "a message heredoc beside a PLAN heredoc naming the ledger",
            msg
            + _py(
                "import pathlib\np = pathlib.Path('%s')\n"
                "p.write_text(p.read_text() + 'rows land in %s\\n')" % (plan, ledger)
            ),
            False,
        ),
        # The writes stay refused, read first or not, beside another heredoc or not.
        (
            "python reads the ledger then rewrites it",
            _py("s = open('%s').read()\nopen('%s', 'w').write(s + '{}')" % (ledger, ledger)),
            True,
        ),
        (
            "python appends through a with-handle",
            _py("with open('%s', 'a') as fh:\n    fh.write('{}')" % ledger),
            True,
        ),
        (
            "python opens the ledger with a mode in a variable",
            _py("m = input()\nfh = open('%s', m)\nfh.write('{}')" % ledger),
            True,
        ),
        (
            "python Path.open in append mode",
            _py("import pathlib\npathlib.Path('%s').open('a').write('{}')" % ledger),
            True,
        ),
        (
            "review 9d3a7308.1: a write-mode open nested under a read call",
            _py("open('%s', 'a').read()" % ledger),
            True,
        ),
        (
            "review 9d3a7308.1: a write-mode open as the argument of a read call",
            _py("import json\njson.load(open('%s', 'a+'))" % ledger),
            True,
        ),
        (
            "review 9d3a7308.1: a named ledger path truncated through a nested open",
            _py("p = '%s'\ndata = open(p, 'w+').read()" % ledger),
            True,
        ),
        (
            "review 9d3a7308.1: a named ledger path truncated inside json.load",
            _py("import json\np = '%s'\nrows = json.load(open(p, 'w'))" % ledger),
            True,
        ),
        (
            "review 9d3a7308.2: the mode passed through a dict unpacking",
            _py("fh = open('%s', **{'mode': 'a'})\nfh.write('{}')" % ledger),
            True,
        ),
        (
            "review 9d3a7308.2: the mode passed through **kwargs",
            _py("kw = {'mode': 'a'}\nopen('%s', **kw).write('{}')" % ledger),
            True,
        ),
        (
            "review 9d3a7308.1: gzip.open with the path first and a write mode second",
            _py("import gzip\ngzip.open('%s', 'wt').write('{}')" % ledger),
            True,
        ),
        (
            "review 634e1ef5.1 control: Path.open('w', -1) is still a write",
            _py("import pathlib\npathlib.Path('%s').open('w', -1).write('{}')" % ledger),
            True,
        ),
        (
            "review 68fffbc7.1 control: Path.open('w', +1) is still a write",
            _py("import pathlib\npathlib.Path('%s').open('w', +1).write('{}')" % ledger),
            True,
        ),
        (
            "review 9d3a7308.4: the mode passed by keyword",
            _py("open('%s', mode='a').write('{}')" % ledger),
            True,
        ),
        (
            "review 9d3a7308.4: Path.open with a keyword write mode",
            _py("import pathlib\npathlib.Path('%s').open(mode='w').write('{}')" % ledger),
            True,
        ),
        (
            "review b326762a.1: any ** call is refused, mode in the mapping or not",
            _py("fh = open('%s', **{'encoding': 'utf-8'})\nfh.write('{}')" % ledger),
            True,
        ),
        (
            "a message heredoc beside a heredoc appending to the ledger",
            msg + _py("open('%s', 'a').write('{}')" % ledger),
            True,
        ),
        (
            "a message heredoc beside a heredoc that reads then rewrites the ledger",
            msg
            + _py(
                "import pathlib\np = pathlib.Path('%s')\np.write_text(p.read_text() + '{}')"
                % ledger
            ),
            True,
        ),
    ]


# The shape of `test-block_vm_unverified_push.py` that was refused on 2026-11-09 (#b4bb4a4e): `transcript()` writes its own local `path`, and an unrelated function binds `path = ... / LEDGER` (a different ledger, but the guard reads the bare name `LEDGER` as this one) and only reads it.
SCOPED_SCRIPT = (
    "import json, pathlib\n"
    'LEDGER = "agent/ledgers/vm-check-push-reasons.jsonl"\n'
    "def transcript(records):\n"
    "    path = pathlib.Path('/tmp') / 'transcript.jsonl'\n"
    "    path.write_text(''.join(json.dumps(r) + '\\n' for r in records), encoding='utf-8')\n"
    "    return path\n"
    "def ledger_lines(root):\n"
    "    path = pathlib.Path(root) / LEDGER\n"
    "    return path.read_text(encoding='utf-8').splitlines() if path.is_file() else []\n"
    "transcript([{}])\n"
)


def scope_cases(world, ledger):
    """#b4bb4a4e: a name resolves to the binding of its own scope (module, function, lambda, comprehension), so a ledger path bound in one function never taints a same-named local in another; a write through the same scope's binding, a module binding, a closure's or a `global`'s still does. `(name, command, refused?)`."""
    script = world / "check_scoped.py"
    script.write_text(SCOPED_SCRIPT, encoding="utf-8")
    return [
        # The false positives: each must be ALLOWED.
        ("python runs a script whose same-named locals differ", "python3 check_scoped.py", False),
        (
            "python heredoc: ledger bound in one function, same name written in another",
            _py(
                "import pathlib\n"
                "def rows():\n    path = pathlib.Path('.') / '%s'\n    return path.read_text()\n"
                "def save(text):\n    path = pathlib.Path('/tmp/out.txt')\n    path.write_text(text)\n"
                "save(rows())" % ledger
            ),
            False,
        ),
        (
            "python: a parameter shadows a module ledger binding",
            _py(
                "import pathlib\npath = '%s'\n"
                "def save(path):\n    pathlib.Path(path).write_text('x')\n"
                "save('/tmp/out.txt')" % ledger
            ),
            False,
        ),
        (
            "python: a lambda parameter shadows a function's ledger binding",
            _py(
                "import pathlib\n"
                "def go():\n    p = '%s'\n    n = len(open(p).read())\n"
                "    w = lambda p: pathlib.Path(p).write_text(str(n))\n    w('/tmp/out.txt')\n"
                "go()" % ledger
            ),
            False,
        ),
        # The writes stay refused.
        (
            "python writes through the same function's ledger binding",
            _py(
                "import pathlib\n"
                "def go():\n    path = pathlib.Path('.') / '%s'\n    path.write_text('{}')\n"
                "go()" % ledger
            ),
            True,
        ),
        (
            "python writes a module ledger binding inside a function",
            _py("path = '%s'\ndef go():\n    open(path, 'a').write('{}')\ngo()" % ledger),
            True,
        ),
        (
            "python closure writes the enclosing function's ledger binding",
            _py(
                "def outer():\n    path = '%s'\n"
                "    def inner():\n        with open(path, 'a') as fh:\n            fh.write('{}')\n"
                "    inner()\nouter()" % ledger
            ),
            True,
        ),
        (
            "python lambda writes the enclosing function's ledger binding",
            _py(
                "def outer():\n    p = '%s'\n    w = lambda: open(p, 'a').write('{}')\n    w()\n"
                "outer()" % ledger
            ),
            True,
        ),
        (
            "python binds the ledger through a global declaration",
            _py(
                "def setup():\n    global path\n    path = '%s'\n"
                "def go():\n    open(path, 'a').write('{}')\nsetup()\ngo()" % ledger
            ),
            True,
        ),
        (
            "python binds the ledger through a nonlocal declaration",
            _py(
                "def outer():\n    path = '/tmp/x'\n"
                "    def setup():\n        nonlocal path\n        path = '%s'\n"
                "    setup()\n    open(path, 'a').write('{}')\nouter()" % ledger
            ),
            True,
        ),
        (
            "python a parameter default names the ledger",
            _py("def go(path='%s'):\n    open(path, 'a').write('{}')\ngo()" % ledger),
            True,
        ),
    ]


# Review 53e8d8aa.1: a left-nested `+` chain parses (the parser loops over it) while the scope walk recurses about two frames per level, so 2000 terms overflow the walk and not the parse.
DEEP_TERMS = 2000


def _deep(tail):
    return _py("x = " + "+".join(["'a'"] * DEEP_TERMS) + "\n" + tail)


def review_53e8d8aa_cases(ledger):
    """Review 53e8d8aa: a program nested past the scope walk's recursion is judged by its lines, refused when it names the ledger and admitted when it does not (.1); a `match` capture binds in its scope, to the subject, the way an assignment target does (.2). `(name, command, refused?)`."""
    return [
        (
            "53e8d8aa.1: a deeply nested program appends to the ledger",
            _deep("open('%s', 'a').write(x)" % ledger),
            True,
        ),
        (
            "53e8d8aa.1: a deeply nested program writes elsewhere",
            _deep("open('/tmp/out.txt', 'a').write(x)"),
            False,
        ),
        (
            "53e8d8aa.2: a bare match capture of the ledger path is written",
            _py(
                "from pathlib import Path\nroot = '.'\nLEDGER = '%s'\n"
                "match Path(root) / LEDGER:\n    case p:\n        open(p, 'a').write('{}')" % ledger
            ),
            True,
        ),
        (
            "53e8d8aa.2: a star capture in a sequence pattern is written",
            _py(
                "def go():\n    match ['%s']:\n        case [*rest]:\n"
                "            open(rest[0], 'a').write('{}')\ngo()" % ledger
            ),
            True,
        ),
        (
            "53e8d8aa.2: a mapping rest capture is written",
            _py(
                "def go():\n    match {'p': '%s'}:\n        case {**rest}:\n"
                "            open(rest['p'], 'a').write('{}')\ngo()" % ledger
            ),
            True,
        ),
        (
            "53e8d8aa.2: a match capture shadows a module ledger name",
            _py(
                "path = '%s'\ndef go(s):\n    match s:\n        case path:\n"
                "            open(path, 'a').write('{}')\ngo('/tmp/out.txt')" % ledger
            ),
            False,
        ),
        (
            "53e8d8aa.2: a class-pattern capture shadows a module ledger name",
            _py(
                "import types\npath = '%s'\ndef go(s):\n"
                "    match s:\n        case types.SimpleNamespace(dest=path):\n"
                "            open(path, 'a').write('{}')\n"
                "go(types.SimpleNamespace(dest='/tmp/out.txt'))" % ledger
            ),
            False,
        ),
    ]


def no_traceback(shared):
    """Each 53e8d8aa.1 case answers through the guard, never through a traceback the dispatcher caught."""
    fails = 0
    for name, command, _refused in review_53e8d8aa_cases(shared.L)[:2]:
        payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": shared.CWD}
        _rc, text = shared.via_dispatch("block_live_proof_ledger_shell_write", payload)
        if "Traceback" in text or "RecursionError" in text:
            print("*** FAIL *** %s raised: %s" % (name, text[-300:]))
            fails += 1
    print("53e8d8aa.1 tracebacks: %d" % fails)
    return fails


def main():
    spec = importlib.util.spec_from_file_location("test_live_proof_ledger_shared", SHARED)
    if spec is None or spec.loader is None:
        raise SystemExit("%s is missing" % SHARED)
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)
    shared.SHELL_CASES.extend(searched_text_cases(shared.L))
    shared.SHELL_CASES.extend(review_cases())
    shared.SHELL_CASES.extend(read_is_not_write_cases(shared.WORLD, shared.L))
    shared.SHELL_CASES.extend(scope_cases(shared.WORLD, shared.L))
    shared.SHELL_CASES.extend(review_53e8d8aa_cases(shared.L))
    rc = shared.main(("block_live_proof_ledger_shell_write",))
    return 1 if no_traceback(shared) else rc


if __name__ == "__main__":
    sys.exit(main())
