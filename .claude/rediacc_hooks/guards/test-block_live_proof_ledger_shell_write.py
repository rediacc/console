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


def main():
    spec = importlib.util.spec_from_file_location("test_live_proof_ledger_shared", SHARED)
    if spec is None or spec.loader is None:
        raise SystemExit("%s is missing" % SHARED)
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)
    shared.SHELL_CASES.extend(searched_text_cases(shared.L))
    shared.SHELL_CASES.extend(review_cases())
    return shared.main(("block_live_proof_ledger_shell_write",))


if __name__ == "__main__":
    sys.exit(main())
