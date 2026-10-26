#!/usr/bin/env python3
"""Control harness for block_backup_unverified_push (OWN_SUITE: never bash, so no golden), box J4 of agent/plans/PLAN-backup-program.md.

REAL REPOSITORIES, one per world, built under a `rediacc_ci.runtmp` run directory by the guard's own `world()` and `plant_receipt()` (the builders its differential `FIXTURES` use): a console-shaped checkout on `1008-1` with real `private/renet` and `private/account` gitlinks, `origin/main` at the seed and unpushed work, and schema 1 backup receipts written through `backup_check_trigger.write`, so a receipt shape the module would refuse can never be planted here.

THE BOX'S THREE CLAIMS, each with its twin: no receipt is refused (a console backup file, a renet chunk-store file, an account backup service), a receipt admits (the same worlds with a VERIFIED receipt), and a stale gitlink is refused (a VERIFIED receipt whose console inputs match but whose renet gitlink is the seed's).

BOTH DIRECTIONS. Every refusal has an allow twin that differs by one planted fact: a docs-only range, a test-only renet range, a renet range outside the backup paths, a VERIFIED receipt, a valid escape of each kind against a transcript holding one AskUserQuestion answer. Every escape kind is refused in its invalid case.

THE LEDGER. An admitted escape appends exactly one line to agent/ledgers/backup-check-push-reasons.jsonl in the world; a refused command and a push a VERIFIED receipt admits append nothing.

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
STEM = "block_backup_unverified_push"
GUARD = HERE / ("%s.py" % STEM)
LEDGER = "agent/ledgers/backup-check-push-reasons.jsonl"
REASON_ENV = "BACKUP_CHECK_PUSH_REASON"

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", HERE.parents[2] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/runtmp.py is missing" % __file__)
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-backup-unverified-push-")

_SYSPATH = importlib.util.spec_from_file_location(
    "_rediacc_syspath", HERE.parents[1] / "rediacc_hooks" / "syspath.py"
)
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: .claude/rediacc_hooks/syspath.py is missing" % __file__)
syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(syspath)
syspath.on_sys_path(syspath.CLAUDE_DIR)
_SPEC = importlib.util.spec_from_file_location("backup_push_guard_under_test", GUARD)
if _SPEC is None or _SPEC.loader is None:
    raise SystemExit("cannot load %s" % GUARD)
G = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(G)


def new_dir(prefix):
    return pathlib.Path(tempfile.mkdtemp(prefix=prefix, dir=RUN_TMP)) / "repo"


def built(name):
    return G.FIXTURES[name](new_dir(name + "-"))


DOCS = built("bck-docs-only")
CONSOLE_NONE = built("bck-console-none")
CONSOLE_VERIFIED = built("bck-console-verified")
CONSOLE_NOT_VERIFIED = built("bck-console-not-verified")
CONSOLE_FAILED = built("bck-console-failed")
CHUNKSTORE = built("bck-renet-chunkstore")
RENET_TESTS = built("bck-renet-tests-only")
RENET_OTHER = built("bck-renet-other")
RENET_VERIFIED = built("bck-renet-verified")
STALE_GITLINK = built("bck-stale-gitlink")
ACCOUNT_SRC = built("bck-account-src")
ACCOUNT_VERIFIED = G.plant_receipt(built("bck-account-src"))
MISSING_OLD = built("bck-missing-old")
STALE_NV = built("bck-stale-not-verified")
# A VERIFIED receipt for the pushed tree whose drill ran renet at another commit, and one with uncommitted edits.
CHECKOUT_MISMATCH = G.plant_receipt(
    G.world(new_dir("checkout-mismatch-"), renet_files=(G.RENET_FILE,)),
    checkout="0" * 40,
)
MODIFIED = G.plant_receipt(
    G.world(new_dir("modified-"), renet_files=(G.RENET_FILE,)), modified=True
)
# Worlds the escape cases write ledger lines into, one per kind, so each count is exact.
ESC_NR = built("bck-console-none")
ESC_DL = built("bck-console-none")
ESC_NV = built("bck-console-not-verified")
ESC_MIRROR = built("bck-docs-only")
# A second repository the scope cases push from with `git -C`.
OUTSIDE = built("bck-docs-only")


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
CONSOLE_HIT = G.CONSOLE_FILE
NR = (R % ("not-runtime: " + G._FILES + ASK)) + PUSH
RENET_HIT = "private/renet/%s" % G.RENET_FILE
ACCOUNT_HIT = "private/account/%s" % G.ACCOUNT_FILE

CASES = [
    # (name, command, root, transcript, expect_blocked, stderr needle) ---- the trigger
    ("docs only", PUSH, DOCS, None, False, ""),
    ("renet range, tests only", PUSH, RENET_TESTS, None, False, ""),
    ("renet range outside the backup paths", PUSH, RENET_OTHER, None, False, ""),
    ("console backup file, no receipt", PUSH, CONSOLE_NONE, None, True, CONSOLE_HIT),
    ("console backup file: names no-receipt", PUSH, CONSOLE_NONE, None, True, "[no-receipt]"),
    (
        "console backup file: names the drill",
        PUSH,
        CONSOLE_NONE,
        None,
        True,
        "./run.sh drill backup",
    ),
    ("console backup file: an implicit push", "git push", CONSOLE_NONE, None, True, ""),
    ("console backup file: a -C push", "git -C . push origin 1008-1", CONSOLE_NONE, None, True, ""),
    (
        "console backup file: the push to main",
        "git push origin 1008-1:main",
        CONSOLE_NONE,
        None,
        True,
        "",
    ),
    ("renet chunk store, no receipt", PUSH, CHUNKSTORE, None, True, RENET_HIT),
    ("account backup service, no receipt", PUSH, ACCOUNT_SRC, None, True, ACCOUNT_HIT),
    ("the old renet object missing", PUSH, MISSING_OLD, None, True, "(unknown) private/renet"),
    # ---- the receipt
    ("console backup file, VERIFIED", PUSH, CONSOLE_VERIFIED, None, False, ""),
    ("renet chunk store, VERIFIED", PUSH, RENET_VERIFIED, None, False, ""),
    ("account backup service, VERIFIED", PUSH, ACCOUNT_VERIFIED, None, False, ""),
    ("console backup file, NOT_VERIFIED", PUSH, CONSOLE_NOT_VERIFIED, None, True, "[not-verified]"),
    ("console backup file, FAILED", PUSH, CONSOLE_FAILED, None, True, "[failed]"),
    ("renet chunk store, a stale gitlink", PUSH, STALE_GITLINK, None, True, "[stale-gitlink]"),
    (
        "renet chunk store, checkout not the pointer",
        PUSH,
        CHECKOUT_MISMATCH,
        None,
        True,
        "[checkout-mismatch]",
    ),
    ("renet chunk store, modified checkout", PUSH, MODIFIED, None, True, "[modified-checkout]"),
    ("a dry run", "git push --dry-run origin 1008-1", CONSOLE_NONE, None, False, ""),
    ("a delete push", "git push origin --delete 1007-1", CONSOLE_NONE, None, False, ""),
    ("prose naming a push", "echo 'git push origin 1008-1'", CONSOLE_NONE, None, False, ""),
    # ---- the scope, the vm-check guard's own cases
    ("cd into the submodule", "cd private/renet && git push", CONSOLE_NONE, None, False, ""),
    ("cwd inside the submodule", PUSH, CONSOLE_NONE, None, False, ""),
    ("a heredoc body", "cat > n.md <<'EOF'\ngit push\nEOF", CONSOLE_NONE, None, False, ""),
    (
        "a repository outside",
        "git -C %s push origin 1008-1" % OUTSIDE,
        CONSOLE_NONE,
        None,
        False,
        "",
    ),
    ("an empty command", "", CONSOLE_NONE, None, False, ""),
    ("console backup file: an sh -c payload", "sh -c 'git push'", CONSOLE_NONE, None, True, ""),
    (
        "a mirror push",
        "git push --mirror origin",
        DOCS,
        None,
        True,
        "no backup receipt can describe",
    ),
    # ---- the escape
    (
        "not-runtime, answered",
        (R % ("not-runtime: " + G._FILES + ASK)) + PUSH,
        ESC_NR,
        ANSWERED,
        False,
        "",
    ),
    (
        "deadline, answered",
        (R % ("deadline: " + G._DEADLINE + ASK)) + PUSH,
        ESC_DL,
        ANSWERED,
        False,
        "",
    ),
    (
        "drill-unavailable over its own NOT_VERIFIED",
        (R % ("drill-unavailable: " + G._UNAVAIL + ASK)) + PUSH,
        ESC_NV,
        ANSWERED,
        False,
        "",
    ),
    (
        "drill-unavailable over another tree's NOT_VERIFIED",
        (R % ("drill-unavailable: " + G._UNAVAIL + ASK)) + PUSH,
        STALE_NV,
        ANSWERED,
        True,
        "escape-no-attempt",
    ),
    (
        "drill-unavailable with no receipt at all",
        (R % ("drill-unavailable: " + G._UNAVAIL + ASK)) + PUSH,
        CONSOLE_NONE,
        ANSWERED,
        True,
        "escape-no-attempt",
    ),
    (
        "an ASKED matching no answer",
        (R % ("not-runtime: " + G._FILES + ASK_ELSEWHERE)) + PUSH,
        CONSOLE_NONE,
        ANSWERED,
        True,
        "escape-unproven",
    ),
    (
        "no transcript",
        (R % ("not-runtime: " + G._FILES + ASK)) + PUSH,
        CONSOLE_NONE,
        None,
        True,
        "escape-unproven",
    ),
    (
        "an unknown kind",
        (R % ("because: " + G._FILES + ASK)) + PUSH,
        CONSOLE_NONE,
        ANSWERED,
        True,
        "escape-kind",
    ),
    (
        "a short why",
        (R % ("deadline: soon" + ASK)) + PUSH,
        CONSOLE_NONE,
        ANSWERED,
        True,
        "escape-why",
    ),
    (
        "no ASKED",
        (R % ("not-runtime: " + G._FILES)) + PUSH,
        CONSOLE_NONE,
        ANSWERED,
        True,
        "escape-asked",
    ),
    (
        "the vm-check variable is not this escape",
        ("VM_CHECK_PUSH_REASON='not-runtime: " + G._FILES + ASK + "' ") + PUSH,
        CONSOLE_NONE,
        ANSWERED,
        True,
        "escape-missing",
    ),
    # ---- the escape spellings and refusals the vm-check guard's suite carries
    (
        "an exported reason",
        "export %s='not-runtime: %s%s'; %s" % (REASON_ENV, G._FILES, ASK, PUSH),
        ESC_NR,
        ANSWERED,
        False,
        "",
    ),
    (
        "env NAME=value",
        "env %s='not-runtime: %s%s' %s" % (REASON_ENV, G._FILES, ASK, PUSH),
        ESC_NR,
        ANSWERED,
        False,
        "",
    ),
    (
        "a malformed ASKED",
        (R % ("not-runtime: " + G._FILES + " ASKED:today")) + PUSH,
        CONSOLE_NONE,
        ANSWERED,
        True,
        "escape-asked: `",
    ),
    (
        "the reason in prose only",
        "echo \"%s='not-runtime: %s%s'\"; %s" % (REASON_ENV, G._FILES, ASK, PUSH),
        CONSOLE_NONE,
        ANSWERED,
        True,
        "no `%s=` on it" % REASON_ENV,
    ),
    (
        "a second push with no reason",
        "%s; git push origin HEAD:1008-1" % NR,
        CONSOLE_NONE,
        ANSWERED,
        True,
        "no `%s=` on it" % REASON_ENV,
    ),
    (
        "the same push twice, the second with no reason",
        "%s; %s" % (NR, PUSH),
        CONSOLE_NONE,
        ANSWERED,
        True,
        "no `%s=` on it" % REASON_ENV,
    ),
    (
        "a mirror push, an ASKED matching no answer",
        (R % ("deadline: " + G._DEADLINE + ASK_ELSEWHERE)) + "git push --mirror origin",
        DOCS,
        ANSWERED,
        True,
        "escape-unproven: its ASKED: minute matches no AskUserQuestion answer",
    ),
    (
        "a mirror push, escaped",
        (R % ("deadline: " + G._DEADLINE + ASK)) + "git push --mirror origin",
        ESC_MIRROR,
        ANSWERED,
        False,
        "",
    ),
    (
        "a mirror push, drill-unavailable",
        (R % ("drill-unavailable: " + G._UNAVAIL + ASK)) + "git push --mirror origin",
        DOCS,
        ANSWERED,
        True,
        "escape-blind",
    ),
]

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
    path = pathlib.Path(root) / LEDGER
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


# The cases that run with the payload's cwd somewhere other than the world's root.
CWD = {"cwd inside the submodule": "private/renet"}


def run(command, root, transcript_path, broken=None, cwd=None):
    """(blocked, stderr) of one payload through the dispatcher, or through a copy of the guard with `broken` (an (old, new) mutant) planted."""
    env = dict(
        os.environ,
        CLAUDE_PROJECT_DIR=str(root),
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
        print("    needle %r; stderr: %s" % (needle, err.strip().splitlines()[:8]))

# The shape of the ledger lines, read back.
want_keys = {
    "ts",
    "branch",
    "head",
    "tree",
    "renet",
    "account",
    "kind",
    "why",
    "asked",
    "hits",
    "receipt",
}
checks = (
    (ESC_NR, "not-runtime", None),
    (ESC_DL, "deadline", None),
    (ESC_NV, "drill-unavailable", {"status": "NOT_VERIFIED", "class": "store-unavailable"}),
)
for root, kind, receipt in checks:
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
            ("branch", last.get("branch") == "1008-1"),
            ("head", len(last.get("head", "")) == 40),
            ("tree", len(last.get("tree", "")) == 40),
            ("renet", len(last.get("renet", "")) == 40),
            ("account", len(last.get("account", "")) == 40),
            ("asked", last.get("asked") == "2026-01-01T00:00Z"),
            ("hits", last.get("hits") == [CONSOLE_HIT]),
            ("receipt", last.get("receipt") == receipt),
            ("why", "ASKED" not in last.get("why", "") and len(last.get("why", "")) >= G.MIN_WHY),
        )
        if not cond
    ]
    if bad:
        print("*** FAIL *** ledger line %r is wrong in: %s" % (last, ", ".join(bad)))
        fails += 1
    else:
        print("ledger: %d line(s) for kind %s, receipt %r" % (len(rows), kind, last["receipt"]))
for quiet in (CONSOLE_NONE, CONSOLE_VERIFIED, RENET_VERIFIED, STALE_GITLINK, DOCS, STALE_NV):
    if ledger_lines(quiet):
        print("*** FAIL *** a world with no admitted escape wrote %r" % ledger_lines(quiet))
        fails += 1

print()
CONTROLS = [("DEFECT", G.DEFECT), *sorted(G.MUTANTS.items())]
# The case each control must flip, so a control cannot pass on some unrelated refusal.
MUST_FLIP = {
    "DEFECT": "console backup file, no receipt",
    "gitlinks-ignored": "renet chunk store, a stale gitlink",
    "inputs-always-equal": "drill-unavailable over another tree's NOT_VERIFIED",
    "asked-always-true": "an ASKED matching no answer",
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
