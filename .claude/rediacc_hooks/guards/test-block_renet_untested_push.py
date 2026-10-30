#!/usr/bin/env python3
"""Control harness for block_renet_untested_push (OWN_SUITE: never bash, so no golden), box M3 of agent/plans/PLAN-renet-change-test-triggers.md.

REAL REPOSITORIES, one per world, built under a `rediacc_ci.runtmp` run directory by the guard's own `world()` and `plant_receipt()` (the builders its differential `FIXTURES` use): a console checkout on `1008-1` with a real private/renet gitlink, the guard's map, and a renet `origin/main` at the seed commit so the renet push form has a base. Receipts are written in the gate's shape into a per-world directory named by `RENET_TEST_RECEIPT_DIR`.

BOTH PUSH FORMS FIRE: a console push whose gitlink moves a renet Go file, and a renet push (`git -C private/renet push`, `cd private/renet && git push`, a payload `cwd` inside private/renet) of the same commit. Each has silent twins differing by one planted fact: a docs-only range, a renet range touching no Go path, a receipt covering the tree, an all-package receipt over an unmapped path, a dry run, a delete push, prose naming a push.

THE RECEIPT IS JUDGED, not just found: a receipt missing one selected package refuses, a receipt for the seed's tree refuses, a partial receipt over an unmapped path (which selects every package) refuses, and a missing old gitlink (an unknown range) refuses.

THE ESCAPE is the repo's ASKED convention: each kind admits with a transcript answer at the minute and writes one ledger line; an unknown kind, a short why, no ASKED and an ASKED matching no answer refuse and write nothing.

THE MUTANTS ARE PROVEN HERE TOO. The guard's `DEFECT` and each of its `MUTANTS` are planted in a copy run through the same payloads, and each must flip its named refusal to allowed.
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
DISPATCH = str(HERE.parent / "dispatch.py")
STEM = "block_renet_untested_push"
GUARD = HERE / ("%s.py" % STEM)
REASON_LEDGER = "agent/ledgers/renet-test-push-reasons.jsonl"
REASON_ENV = "RENET_TEST_PUSH_REASON"

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", HERE.parents[2] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/runtmp.py is missing" % __file__)
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-renet-untested-push-")

_SYSPATH = importlib.util.spec_from_file_location(
    "_rediacc_syspath", HERE.parents[1] / "rediacc_hooks" / "syspath.py"
)
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: .claude/rediacc_hooks/syspath.py is missing" % __file__)
syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(syspath)
syspath.on_sys_path(syspath.CLAUDE_DIR)
_SPEC = importlib.util.spec_from_file_location("renet_push_guard_under_test", GUARD)
if _SPEC is None or _SPEC.loader is None:
    raise SystemExit("cannot load %s" % GUARD)
G = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(G)


def new_dir(prefix):
    return pathlib.Path(tempfile.mkdtemp(prefix=prefix, dir=RUN_TMP)) / "repo"


def built(name):
    return G.FIXTURES[name](new_dir(name + "-"))


DOCS = built("rnt-docs")
RENET_DOCS = built("rnt-renet-docs")
LICENSE = built("rnt-license")
LICENSE_OK = built("rnt-license-receipt")
LICENSE_PARTIAL = built("rnt-license-partial")
LICENSE_SEED = built("rnt-license-seed-receipt")
UNMAPPED_PARTIAL = built("rnt-unmapped-partial")
UNMAPPED_ALL = built("rnt-unmapped-all")
MISSING_OLD = built("rnt-missing-old")
NEW_MISSING = built("rnt-new-missing")
RENET_B = G.VM._git(LICENSE / "private/renet", "rev-parse", "HEAD")[:12]
# Worlds the escape cases write ledger lines into, one per kind, so each count is exact.
ESC_ENV = built("rnt-license")
ESC_DL = built("rnt-license")
ESC_RENET = built("rnt-license")


def transcript(answer_ts):
    """A lead transcript holding one AskUserQuestion and its answer at `answer_ts`."""
    path = pathlib.Path(tempfile.mkdtemp(prefix="transcript-", dir=RUN_TMP)) / "lead.jsonl"
    records = [
        {
            "type": "assistant",
            "timestamp": "2026-01-01T00:00:10Z",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "AskUserQuestion", "id": "toolu_fixture_ask"}
                ]
            },
        },
        {
            "type": "user",
            "timestamp": answer_ts,
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_fixture_ask", "content": "a"}
                ]
            },
        },
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return str(path)


ANSWERED = transcript("2026-01-01T00:00:30Z")
ASK = " ASKED:2026-01-01T00:00Z"
ASK_ELSEWHERE = " ASKED:2026-01-01T00:10Z"
R = REASON_ENV + "='%s' "
PUSH = "git push origin 1008-1"
RPUSH = "git -C private/renet push origin main"
ENVW = "environment: " + G._ENVIRONMENT
DL = "deadline: " + G._DEADLINE

CASES = [
    # (name, command, root, transcript, expect_blocked, stderr needle) ---- console form
    ("console: docs only", PUSH, DOCS, None, False, ""),
    ("console: renet README only", PUSH, RENET_DOCS, None, False, ""),
    ("console: renet licence file, no receipt", PUSH, LICENSE, None, True, "[no-receipt]"),
    ("console: names the command", PUSH, LICENSE, None, True, G.COMMAND),
    ("console: names the dependents", PUSH, LICENSE, None, True, "  cmd/renet\n"),
    ("console: an implicit push", "git push", LICENSE, None, True, "console push"),
    ("console: licence file, covering receipt", PUSH, LICENSE_OK, None, False, ""),
    ("console: receipt missing a dependent", PUSH, LICENSE_PARTIAL, None, True, "[partial]"),
    ("console: receipt for the seed tree", PUSH, LICENSE_SEED, None, True, "[no-receipt]"),
    (
        "console: unmapped Go path, partial receipt",
        PUSH,
        UNMAPPED_PARTIAL,
        None,
        True,
        "every package",
    ),
    ("console: unmapped Go path, all receipt", PUSH, UNMAPPED_ALL, None, False, ""),
    (
        "console: old gitlink missing (unknown range)",
        PUSH,
        MISSING_OLD,
        None,
        True,
        "every package",
    ),
    ("console: new gitlink not fetched", PUSH, NEW_MISSING, None, True, "[no-tree]"),
    (
        "console: names the renet commit to check out",
        PUSH,
        LICENSE,
        None,
        True,
        "checked out at %s " % RENET_B,
    ),
    ("console: a dry run", "git push --dry-run origin 1008-1", LICENSE, None, False, ""),
    ("console: a delete push", "git push origin --delete 1007-1", LICENSE, None, False, ""),
    ("console: prose naming a push", "echo 'git push origin 1008-1'", LICENSE, None, False, ""),
    # ---- renet form
    ("renet -C: licence file, no receipt", RPUSH, LICENSE, None, True, "renet push"),
    ("renet -C: covering receipt", RPUSH, LICENSE_OK, None, False, ""),
    ("renet -C: receipt missing a dependent", RPUSH, LICENSE_PARTIAL, None, True, "[partial]"),
    (
        "renet cd: licence file, no receipt",
        "cd private/renet && git push origin main",
        LICENSE,
        None,
        True,
        "renet push",
    ),
    (
        "renet cwd: licence file, no receipt",
        "git push origin main",
        LICENSE,
        None,
        True,
        "renet push",
    ),
    ("renet cwd: covering receipt", "git push origin main", LICENSE_OK, None, False, ""),
    ("renet -C: README only", RPUSH, RENET_DOCS, None, False, ""),
    (
        "renet -C: a dry run",
        "git -C private/renet push --dry-run origin main",
        LICENSE,
        None,
        False,
        "",
    ),
    ("renet -C: prose naming a push", "echo '%s'" % RPUSH, LICENSE, None, False, ""),
    # ---- the escape
    ("escape: environment", (R % (ENVW + ASK)) + PUSH, ESC_ENV, ANSWERED, False, ""),
    ("escape: deadline", (R % (DL + ASK)) + PUSH, ESC_DL, ANSWERED, False, ""),
    ("escape: deadline on a renet push", (R % (DL + ASK)) + RPUSH, ESC_RENET, ANSWERED, False, ""),
    (
        "escape: an unknown kind",
        (R % ("because: " + G._DEADLINE + ASK)) + PUSH,
        LICENSE,
        ANSWERED,
        True,
        "escape-kind",
    ),
    (
        "escape: a short why",
        (R % ("deadline: soon" + ASK)) + PUSH,
        LICENSE,
        ANSWERED,
        True,
        "escape-why",
    ),
    ("escape: no ASKED", (R % DL) + PUSH, LICENSE, ANSWERED, True, "escape-asked"),
    (
        "escape: an ASKED matching no answer",
        (R % (DL + ASK_ELSEWHERE)) + PUSH,
        LICENSE,
        ANSWERED,
        True,
        "escape-unproven",
    ),
    ("escape: no transcript", (R % (DL + ASK)) + PUSH, LICENSE, None, True, "escape-unproven"),
    (
        "escape: prose naming the variable",
        "echo %s=%s && %s" % (REASON_ENV, G._DEADLINE.split()[0], PUSH),
        LICENSE,
        ANSWERED,
        True,
        "escape-missing",
    ),
]

# The cases that run with the payload's cwd somewhere other than the world's root.
CWD = {
    "renet cwd: licence file, no receipt": "private/renet",
    "renet cwd: covering receipt": "private/renet",
}

BROKEN_RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "old, new = %r\n"
    "import ast\n"
    "cut = [n for n in ast.parse(src).body if isinstance(n, ast.Assign)"
    " and any(isinstance(t, ast.Name) and t.id in ('DEFECT', 'MUTANTS') for t in n.targets)]\n"
    "outside = '\\n'.join(l for i, l in enumerate(src.split('\\n'), 1)"
    " if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut))\n"
    "assert outside.count(old) == 1, 'the mutant must name exactly one line outside its declaration'\n"
    "ns = {'__name__': 'broken', '__file__': %r}\n"
    "exec(compile(src.replace(old, new), 'broken', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)


def ledger_lines(root):
    path = pathlib.Path(root) / REASON_LEDGER
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def run(command, root, transcript_path, broken=None, cwd=None):
    """(blocked, stderr) of one payload through the dispatcher, or through a copy of the guard with `broken` (an (old, new) mutant) planted."""
    env = dict(
        os.environ,
        CLAUDE_PROJECT_DIR=str(root),
        RENET_TEST_RECEIPT_DIR=str(pathlib.Path(root) / G.RECEIPTS_REL),
        TMPDIR=tempfile.mkdtemp(prefix="tmp-", dir=RUN_TMP),
    )
    env.pop(REASON_ENV, None)
    doc = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(pathlib.Path(root) / cwd) if cwd else str(root),
    }
    if transcript_path:
        doc["transcript_path"] = transcript_path
    if broken:
        argv = [
            sys.executable,
            "-c",
            BROKEN_RUNNER % (str(HERE.parents[1]), str(GUARD), broken, str(GUARD)),
        ]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(
        argv, input=json.dumps(doc), capture_output=True, text=True, check=False, env=env
    )
    if proc.returncode not in (0, 2):
        raise SystemExit(
            "%s runner crashed (rc %d): %s"
            % ("broken" if broken else "guard", proc.returncode, proc.stderr[-800:])
        )
    return proc.returncode == 2, proc.stderr


fails = 0
blocked = 0
for name, command, root, tr, want, needle in CASES:
    before = len(ledger_lines(root))
    got, err = run(command, root, tr, cwd=CWD.get(name))
    grew = len(ledger_lines(root)) - before
    blocked += got
    ok = got == want and (not needle or needle in err)
    escaped = REASON_ENV + "='" in command
    if got and grew:
        ok = False
        print("    a refused command wrote %d ledger line(s)" % grew)
    if not got and escaped and grew != 1:
        ok = False
        print("    an admitted escape wrote %d ledger line(s), want 1" % grew)
    if not got and not escaped and grew:
        ok = False
        print("    a push admitted without an escape wrote %d ledger line(s)" % grew)
    fails += not ok
    print(
        "%-52s want=%-8s got=%-8s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok:
        print("    needle %r; stderr: %s" % (needle, err.strip().splitlines()[:12]))

# The shape of the ledger lines, read back.
want_keys = {"ts", "branch", "form", "head", "renetTree", "kind", "why", "asked", "packages"}
for root, kind, form in (
    (ESC_ENV, "environment", "console"),
    (ESC_DL, "deadline", "console"),
    (ESC_RENET, "deadline", "renet"),
):
    rows = [json.loads(line) for line in ledger_lines(root)]
    if not rows:
        print("*** FAIL *** no ledger line was written for kind %s" % kind)
        fails += 1
        continue
    last = rows[-1]
    bad = [
        what
        for what, cond in (
            ("keys", set(last) == want_keys),
            ("kind", last.get("kind") == kind),
            ("form", last.get("form") == form),
            ("head", len(last.get("head", "")) == 40),
            ("renetTree", len(last.get("renetTree", "")) == 40),
            ("asked", last.get("asked") == "2026-01-01T00:00Z"),
            ("packages", last.get("packages") == ["cmd/renet", "pkg/license"]),
            ("why", "ASKED" not in last.get("why", "") and len(last.get("why", "")) >= G.MIN_WHY),
        )
        if not cond
    ]
    if bad:
        print("*** FAIL *** ledger line %r is wrong in: %s" % (last, ", ".join(bad)))
        fails += 1
    else:
        print("ledger: %d line(s) for kind %s, form %s" % (len(rows), kind, form))
for quiet in (DOCS, LICENSE, LICENSE_OK, LICENSE_PARTIAL, UNMAPPED_ALL):
    if ledger_lines(quiet):
        print("*** FAIL *** a world with no admitted escape wrote %r" % ledger_lines(quiet))
        fails += 1

print()
CONTROLS = [("DEFECT", G.DEFECT), *sorted(G.MUTANTS.items())]
# The case each control must flip, so a control cannot pass on some unrelated refusal.
MUST_FLIP = {
    "DEFECT": "console: renet licence file, no receipt",
    "partial-receipt-admits": "console: receipt missing a dependent",
    "renet-form-ignored": "renet -C: licence file, no receipt",
    "asked-always-true": "escape: an ASKED matching no answer",
}
for label, mutant in CONTROLS:
    flipped = [
        n
        for n, c, r, tr, w, _ in CASES
        if w and not run(c, r, tr, broken=mutant, cwd=CWD.get(n))[0]
    ]
    must = MUST_FLIP[label]
    if must in flipped:
        print(
            "%s control: planted %r; %d refusal(s) flipped to allowed, including %r"
            % (label, mutant[1], len(flipped), must)
        )
    else:
        print(
            "*** FAIL *** %s control: with %r planted, %r did not flip (flipped: %r)"
            % (label, mutant, must, flipped)
        )
        fails += 1

if blocked in (0, len(CASES)):
    print("*** FAIL *** the guard answered the same way on every case")
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
