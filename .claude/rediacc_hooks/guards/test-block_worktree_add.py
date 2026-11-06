#!/usr/bin/env python3
"""Control harness for block_worktree_add's lease half, driven through the dispatcher (agent/plans/PLAN-worktree-lease.md W6).

Each row is one Bash command with the answer it must get. The chain must carry the guard, and two planted copies must flip their own rows: the declared DEFECT for the wrapper arm and a local plant for the remove arm, so a guard that stopped running cannot leave this green. The suffix spelling is driven two ways: on the helper with a name passed in, so it holds with no tree on disk, and through the dispatcher for every tree on disk.

This file names the phrase the guard refuses in a script, so the guard refuses to run it while it is untracked or differs from HEAD. That is the documented cost (`block_worktree_add.py`, A SCRIPT RUN BY PATH THAT NAMES THE PHRASE): commit it, then run it.
"""

import ast
import atexit
import importlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
HOOKS = HERE.parent
DISPATCH = str(HOOKS / "dispatch.py")
STEM = "block_worktree_add"
GUARD = HERE / ("%s.py" % STEM)
REPO_ROOT = HERE.parents[2]
ROOT = str(REPO_ROOT)

_SYSPATH = importlib.util.spec_from_file_location("_rediacc_syspath", HOOKS / "syspath.py")
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: .claude/rediacc_hooks/syspath.py is missing" % __file__)
syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(syspath)
syspath.on_sys_path(syspath.CLAUDE_DIR)
guard = importlib.import_module("rediacc_hooks.guards.%s" % STEM)

failures: list[str] = []

REFUSED = [
    # The lease arm, every way of naming the tree.
    ("remove, relative", "git worktree remove .claude/worktrees/x"),
    ("remove, force", "git worktree remove --force .claude/worktrees/x"),
    ("remove, double force", "git worktree remove -f -f .claude/worktrees/x"),
    ("remove, absolute", "git worktree remove %s/.claude/worktrees/x" % ROOT),
    ("remove, a variable root", 'git worktree remove "$ROOT/.claude/worktrees/x"'),
    ("remove, a dot segment", "git worktree remove .claude/./worktrees/x"),
    ("remove, through a parent", "git worktree remove docs/../.claude/worktrees/x"),
    ("move", "git worktree move .claude/worktrees/x /tmp/x"),
    ("move into the root", "git worktree move /tmp/x .claude/worktrees/x"),
    ("lock", "git worktree lock .claude/worktrees/x"),
    ("unlock", "git worktree unlock .claude/worktrees/x"),
    ("prune inside a lease", "git -C .claude/worktrees/x worktree prune"),
    ("joined to -C", "git -C .claude worktree remove worktrees/x"),
    ("the run's own directory", "git -C .claude/worktrees/x worktree remove ."),
    ("joined to cd", "cd .claude/worktrees && git worktree remove x"),
    ("after a separator", "true; git worktree remove .claude/worktrees/x"),
    ("behind sudo", "sudo git worktree remove .claude/worktrees/x"),
    ("behind env", "env A=1 git worktree remove .claude/worktrees/x"),
    ("inside sh -c", "sh -c 'git worktree remove .claude/worktrees/x'"),
    ("inside a substitution", "x=$(git worktree remove .claude/worktrees/x)"),
    ("launched by find", r"find . -maxdepth 0 -exec git worktree unlock .claude/worktrees/x \;"),
    (
        "python argv",
        (
            "python3 -c \"import subprocess; subprocess.run(['git','worktree','remove',"
            "'.claude/worktrees/x'])\""
        ),
    ),
    (
        "python os.system",
        "python3 -c \"import os; os.system('git worktree remove .claude/worktrees/x')\"",
    ),
    (
        "python heredoc",
        "python3 - <<'EOF'\nimport os\nos.system('git worktree unlock .claude/worktrees/x')\nEOF",
    ),
    (
        "node",
        'node -e \'require("child_process").execSync("git worktree remove .claude/worktrees/x")\'',
    ),
    ("perl argv", 'perl -e \'system("git","worktree","unlock",".claude/worktrees/x")\''),
    # The arms that were already here, still answering after the widening.
    ("the plain add", "git worktree add /tmp/wt main"),
    ("add under the lease root", "git worktree add .claude/worktrees/x"),
    ("the wrapper's create", "./run.sh worktree create 0901-1"),
    ("the wrapper by path", "%s/run.sh worktree create x" % ROOT),
    ("the port's create", "python3 -m rediacc_ci.dev.worktree create x"),
]

# A script path the shell expands, with the words in the command's text. The second row is the hole itself: the fixture names the phrase and is untracked, so the literal path is refused and the variable must be too.
FIXTURE_DIR = tempfile.mkdtemp(prefix="guard-lease-variable-")
atexit.register(shutil.rmtree, FIXTURE_DIR, ignore_errors=True)
pathlib.Path(FIXTURE_DIR, "fixture.py").write_text("# git worktree add /tmp/x\n", encoding="utf-8")
REFUSED += [
    ("a variable script path naming the words", "python3 $G/test-block_worktree_add.py"),
    ("the fixture, literal", "python3 %s/fixture.py" % FIXTURE_DIR),
    ("the fixture, through an assignment", "G=%s; python3 $G/fixture.py" % FIXTURE_DIR),
    (
        "written and run through a variable",
        "G=%s; printf 'git worktree add x' > $G/w.py; python3 $G/w.py" % FIXTURE_DIR,
    ),
]

# #a904d9f4: the INVOCATION is judged, not two words anywhere. An untracked script that runs the argv is refused; one whose comment says `worktree` while its code runs `git add`, and a sanctioned `./run.sh worktree` verb beside a `$`-path script, are not.
pathlib.Path(FIXTURE_DIR, "invoke.py").write_text(
    "import subprocess\nsubprocess.run(['git', 'worktree', 'add', '/tmp/x', 'HEAD'])\n",
    encoding="utf-8",
)
pathlib.Path(FIXTURE_DIR, "selftest.py").write_text(
    "import subprocess\n\n"
    "# A scratch repository stands in for the lease worktree.\n\n\n"
    "def g(root, *args):\n"
    "    return subprocess.run(['git', *args], cwd=root, check=True)\n\n\n"
    "def selftest(root):\n"
    "    g(root, 'add', '-A')\n",
    encoding="utf-8",
)
REFUSED += [("an untracked script running the argv", "python3 %s/invoke.py" % FIXTURE_DIR)]

# The design review of dd6898eb0: adjacency alone let a script keep the two words apart and still run the verb. Each of these names the phrase in CODE (not a comment), so it is refused.
APART = {
    "helper.js": (
        "node",
        (
            'const { execSync } = require("child_process");\n'
            "// a helper per verb\n"
            'const tree = (verb, p) => execSync("git worktree " + verb + " " + p);\n'
            'tree("add", "/tmp/x");\n'
        ),
    ),
    "wrapper.sh": ("bash", 'wt(){ git worktree "$@"; }\nwt add /tmp/x\n'),
    "alias.sh": ("bash", "git -c alias.wt=worktree wt add /tmp/x\n"),
    "config.sh": (
        "bash",
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.wt GIT_CONFIG_VALUE_0=worktree git wt add /x\n",
    ),
}
for apart_name, (_runner, apart_text) in APART.items():
    pathlib.Path(FIXTURE_DIR, apart_name).write_text(apart_text, encoding="utf-8")
APART_ROWS = [
    ("apart: %s" % name, "%s %s/%s" % (runner, FIXTURE_DIR, name))
    for name, (runner, _text) in APART.items()
]
PRINTF_ROW = (
    "apart: printf into a $-path script",
    "G=%s; printf 'git %%s add %%s\\n' worktree /p > $G/a.sh; bash $G/a.sh" % FIXTURE_DIR,
)
REFUSED += [*APART_ROWS, PRINTF_ROW]

# Review ba934aef.1: a comment marker INSIDE A STRING hid the code after it from a quote-blind strip. Each of these keeps the phrase apart, so only the script arm's comment-stripped reading can refuse it.
QUOTED = {
    "quoted.sh": ("bash", 'echo " #"; git -c alias.wt=worktree wt add /p\n'),
    "quoted.js": (
        "node",
        (
            'const { execSync } = require("child_process");\n'
            'execSync("echo //"); execSync("git -c alias.wt=worktree wt add /p");\n'
        ),
    ),
    "quoted.pl": ("perl", 'system("echo #"); system("git -c alias.wt=worktree wt add /p");\n'),
}
# A whole-line comment is the only `worktree` beside a `git add`: allowed in every family the scanners read.
COMMENTED = {
    "commented.sh": ("bash", "# a note on the worktree\ngit add -A\n"),
    "commented.js": (
        "node",
        (
            "// a note on the worktree\n"
            "/* the worktree again */\n"
            'require("child_process").execSync("git add -A");\n'
        ),
    ),
}
for fixture_name, (_runner, fixture_text) in {**QUOTED, **COMMENTED}.items():
    pathlib.Path(FIXTURE_DIR, fixture_name).write_text(fixture_text, encoding="utf-8")
QUOTED_ROWS = {
    name: ("in a string: %s" % name, "%s %s/%s" % (runner, FIXTURE_DIR, name))
    for name, (runner, _text) in QUOTED.items()
}
COMMENTED_ROWS = [
    ("whole-line comment: %s" % name, "%s %s/%s" % (runner, FIXTURE_DIR, name))
    for name, (runner, _text) in COMMENTED.items()
]
REFUSED += list(QUOTED_ROWS.values())
# The JS helper is also caught by the text reading (`_text_verdict` folds the concatenation), so only the shell rows depend on the script arm alone.
SCRIPT_ARM_ROWS = [row for row in APART_ROWS if row[1].startswith("bash ")]
FALSE_POSITIVES = [
    (
        "a comment naming the tree beside git add",
        "python3 %s/selftest.py --selftest" % FIXTURE_DIR,
    ),
    (
        "gc beside a $-path worklist --add",
        (
            "./run.sh worktree gc --write --id x && "
            'python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/stop/worklist.py --add abcd1234 a note'
        ),
    ),
    (
        "gc beside a $-path worklist tick",
        (
            "./run.sh worktree gc --write --id x; "
            "python3 $CLAUDE_PROJECT_DIR/.claude/hooks/stop/worklist.py --tick abcd1234 1f2e removed"
        ),
    ),
]

ALLOWED = [
    # A variable script path with none of the words is out of reach, and must stay allowed: every session runs these.
    ("a variable script path, no words", "python3 $G/unrelated.py"),
    # A bare name aimed at another checkout says nothing about this checkout's trees.
    ("a bare name in another checkout", "git -C /other/repo worktree remove w2-proof"),
    # The lease tool is the sanctioned road.
    ("the lease tool", "./run.sh worktree lease"),
    ("the lease tool, named", "./run.sh worktree lease --name w6 --owner abcd1234"),
    ("the lease tool by path", "%s/run.sh worktree lease" % ROOT),
    ("the lease tool via bash", "bash run.sh worktree lease"),
    ("the lease listing", "./run.sh worktree leases --json"),
    ("the landing verb", "./run.sh worktree land x"),
    ("the gc verb", "./run.sh worktree gc --write --id x"),
    # The same verbs on any other tree are not this guard's business.
    ("remove elsewhere", "git worktree remove /tmp/wt"),
    ("remove in the operator's tree dir", "git worktree remove .worktrees/0101-1"),
    ("a look-alike directory", "git worktree remove .claude/worktrees-old/x"),
    ("a look-alike parent", "git worktree remove x.claude/worktrees/y"),
    ("a bare prune", "git worktree prune"),
    ("a list", "git worktree list --porcelain"),
    # A mention is not a run.
    ("an echo", "echo git worktree remove .claude/worktrees/x"),
    ("a commit message", "git commit -m 'git worktree remove .claude/worktrees/x' -- a"),
    ("a grep", "grep -rn 'git worktree remove .claude/worktrees' docs"),
    ("a heredoc body", "cat > n.md <<'EOF'\ngit worktree remove .claude/worktrees/x\nEOF"),
    ("a python print", "python3 -c 'print(\"never git worktree remove .claude/worktrees/x\")'"),
    ("reading the lease root", "ls .claude/worktrees"),
    ("a git status inside", "git -C .claude/worktrees/x status"),
    *FALSE_POSITIVES,
    *COMMENTED_ROWS,
]

# (family, text, does the comment-stripped text still name the phrase): the scanners on their own, both directions, and the raw-text fallback for a construct they do not read.
CODE_TEXT = [
    ("shell", 'echo " #"; git -c alias.wt=worktree wt add /p\n', True),
    ("shell", "echo ' #'; git -c alias.wt=worktree wt add /p\n", True),
    ("shell", "echo a\\ #b; git -c alias.wt=worktree wt add /p\n", True),
    ("shell", "echo a # x; git -c alias.wt=worktree wt add /p\n", True),
    ("shell", 'x="\n# "; git -c alias.wt=worktree wt add /p\n', True),
    ("shell", "x=${y:-\n#}; git -c alias.wt=worktree wt add /p\n", True),
    ("shell", "cat <<E\n'\nE\nx='\n# '; git -c alias.wt=worktree wt add /p\n", True),
    ("shell", "# a worktree note\ngit add -A  # stage\n", False),
    ("shell", 'echo "it\'s" # the worktree\ngit add -A\n', False),
    ("node", 'f("echo //"); f("git -c alias.wt=worktree wt add /p");\n', True),
    ("node", 'f("/* x"); f("git -c alias.wt=worktree wt add /p"); g("*/");\n', True),
    ("node", "f(`\n// `); f(`git -c alias.wt=worktree wt add /p`);\n", True),
    ("tsx", "<p>don't</p>; f(' // '); f('git -c alias.wt=worktree wt add /p');\n", True),
    ("node", '// a worktree note\nf("git add -A"); /* worktree */ f("http://a")\n', False),
    ("perl", "# a worktree note\nsystem('git add -A');\n", True),
    ("ruby", 'puts "a #{1} #"; system("git -c alias.wt=worktree wt add /p")\n', True),
    ("python", "# a worktree note\ng('add', '-A')\n", False),
]

# (operand, directory, trees on disk, does it name a lease)
HELPER = [
    ("w2", "", ["w2", "w9"], True),
    ("worktrees/w2", "", ["w2"], True),
    (".claude/worktrees/w2", "", [], True),
    ("x", ".claude/worktrees", [], True),
    ("w3", "", ["w2", "w9"], False),
    ("rktrees/w2", "", ["w2"], False),
    ("/tmp/w2", "", ["w2"], False),
    (".", "", ["w2"], False),
    ("w2", "/tmp", [], False),
]


def _payload(command, cwd=ROOT):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd})


# A planted copy, the whole guard otherwise unchanged, through the guard's own `run`.
BROKEN_RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "old, new = %r\n"
    "assert old in src, 'the plant no longer applies'\n"
    "ns = {'__name__': 'broken', '__file__': %r}\n"
    "exec(compile(src.replace(old, new), 'broken', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)


def _declared_defect():
    tree = ast.parse(GUARD.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "DEFECT" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise SystemExit("%s declares no DEFECT" % GUARD)


ENV = dict(os.environ, CLAUDE_PROJECT_DIR=ROOT)


def run_guard(command, defect=None):
    if defect is not None:
        code = BROKEN_RUNNER % (str(HOOKS.parent), str(GUARD), defect, str(GUARD))
        argv = [sys.executable, "-c", code]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(
        argv,
        input=_payload(command),
        capture_output=True,
        text=True,
        check=False,
        env=ENV,
        cwd=ROOT,
    )
    if proc.returncode not in (0, 2):
        print("*** CRASH *** rc=%d %r\n%s" % (proc.returncode, command, proc.stderr[-800:]))
        failures.append("crash: %s" % command)
    return proc.returncode, proc.stderr


def check(name, want_blocked, command):
    rc, err = run_guard(command)
    blocked = rc == 2
    fine = blocked == want_blocked and (want_blocked or not err)
    print(
        "%-40s want=%-8s got=%-8s %s"
        % (
            name[:40],
            "BLOCKED" if want_blocked else "allowed",
            "BLOCKED" if blocked else "allowed",
            "ok" if fine else "*** FAIL ***",
        )
    )
    if not fine:
        failures.append(name)
        print("    command: %r\n    stderr: %s" % (command, err.strip()[:400]))


print("== refused (%d rows)" % len(REFUSED))
for row_name, row_command in REFUSED:
    check(row_name, True, row_command)

print("== allowed (%d rows)" % len(ALLOWED))
for row_name, row_command in ALLOWED:
    check(row_name, False, row_command)

print("== the suffix git resolves, on the helper (%d rows)" % len(HELPER))
for word, here, names, want in HELPER:
    got = guard.names_lease(word, here, names)
    if got != want:
        failures.append("helper: %s" % word)
    print("%-40s want=%-5s got=%-5s %s" % (word, want, got, "ok" if got == want else "*** FAIL"))

print("== the comment scanners, on the helper (%d rows)" % len(CODE_TEXT))
for family, text, want in CODE_TEXT:
    got = guard._names_phrase(guard._code_text(family, text))
    if got != want:
        failures.append("code text: %s %r" % (family, text[:40]))
    print(
        "%-40s want=%-5s got=%-5s %s"
        % ("%s %r" % (family, text[:30]), want, got, "ok" if got == want else "*** FAIL")
    )

on_disk = guard._lease_names()
print("== the suffix git resolves, on the %d tree(s) on disk" % len(on_disk))
for tree_name in on_disk:
    check("the bare name %s" % tree_name, True, "git worktree unlock %s" % tree_name)
check("a name no tree has", False, "git worktree unlock no-such-tree-%d" % os.getpid())

print("== the messages name the road and no clone")
for key, text in (
    ("git", guard.GIT_MESSAGE),
    ("run.sh", guard.RUN_SH_MESSAGE),
    ("port", guard.PORT_MESSAGE),
):
    if "./run.sh worktree lease" not in text or "git clone" in text:
        failures.append("message: %s" % key)
        print("*** FAIL *** the %s message: %s" % (key, text))
    else:
        print("%s: names the lease tool, recommends no clone" % key)
if "./run.sh worktree gc" not in guard.LEASE_MESSAGE:
    failures.append("message: lease")
    print("*** FAIL *** the lease message names no way out: %s" % guard.LEASE_MESSAGE)

print("== the chain carries it")
listing = subprocess.run(
    [sys.executable, DISPATCH, "--list"], capture_output=True, text=True, check=False, env=ENV
)
listed = [line for line in listing.stdout.splitlines() if STEM in line]
if not (listed and listed[0].split()[0] == "pre-bash"):
    failures.append("not on the pre-bash chain")
    print("*** FAIL *** %s is not listed on pre-bash: %r" % (STEM, listed))
else:
    print("listed: %s" % " ".join(listed[0].split()))
chain = subprocess.run(
    [sys.executable, DISPATCH, "--chain", "pre-bash"],
    input=_payload("git worktree remove .claude/worktrees/x"),
    capture_output=True,
    text=True,
    check=False,
    env=ENV,
    cwd=ROOT,
)
if chain.returncode != 2 or guard.LEASE_MESSAGE[:40] not in chain.stderr:
    failures.append("chain did not refuse")
    print("*** FAIL *** the chain answered rc=%d: %s" % (chain.returncode, chain.stderr[-400:]))
else:
    print("chain: refused by this guard, rc=2")

print("== the plants")
LEASE_ROWS = [(n, c) for n, c in REFUSED if "worktrees" in c and " add " not in c]
for label, pair, rows in (
    ("the declared DEFECT", _declared_defect(), [r for r in REFUSED if "run.sh" in r[1]]),
    ("the lease arm", ("if runs_lease_verb(cmd):", "if False:"), LEASE_ROWS),
):
    flipped = [n for n, c in rows if run_guard(c, defect=pair)[0] == 0]
    if not rows or len(flipped) < len(rows) // 2:
        failures.append("plant: %s" % label)
        print("*** FAIL *** %s flipped %d of %d rows" % (label, len(flipped), len(rows)))
    else:
        print("%s: %d of %d flipped, e.g. %r" % (label, len(flipped), len(rows), flipped[0]))
    kept = [n for n, c in ALLOWED if run_guard(c, defect=pair)[0] != 0]
    if kept:
        failures.append("plant refused an allowed row: %s" % label)
        print("*** FAIL *** with %s planted, refused %r" % (label, kept[:3]))

# THE REVERSE PLANTS (#a904d9f4): each puts back one piece of the old two-words-anywhere reading, and the false positive it caused must be refused again, so the allowed rows above cannot be green because the rows stopped reaching the arm.
REVERSE = [
    (
        "the script arm reads two words anywhere",
        (
            "    if _spells_invocation(text) or _names_phrase(_code_text(family, text)):\n",
            "    if _names_phrase(text):\n",
        ),
        FALSE_POSITIVES[0],
    ),
    (
        "a comment licenses the argv fill",
        ("mentions = _code_mentions(code)", 'mentions = "worktree" in code'),
        FALSE_POSITIVES[0],
    ),
    (
        "the unjudgeable arm reads two words anywhere",
        ("_spells_invocation(cmd, lease=True)", "_could_spell(cmd)"),
        FALSE_POSITIVES[1],
    ),
    (
        "the unjudgeable arm reads two words anywhere (tick)",
        ("_spells_invocation(cmd, lease=True)", "_could_spell(cmd)"),
        FALSE_POSITIVES[2],
    ),
    # The scanners always keeping the raw text refuse the whole-line comment rows again, so those rows reach the arm and are allowed BY the scanners.
    (
        "the scanners read nothing",
        ('    return "".join(out)\n', "    return text\n"),
        COMMENTED_ROWS[0],
    ),
    (
        "the scanners read nothing (js)",
        ('    return "".join(out)\n', "    return text\n"),
        COMMENTED_ROWS[1],
    ),
]
for label, pair, (row_name, row_command) in REVERSE:
    if run_guard(row_command, defect=pair)[0] != 2:
        failures.append("reverse plant: %s" % label)
        print("*** FAIL *** with %s planted, %r was not refused" % (label, row_name))
    else:
        print("%s: %r refused again" % (label, row_name))

# THE REWORK'S OWN PLANTS: back to dd6898eb0's adjacency-only script arm, every shell APART script is admitted; without the written-script lookup in the `$` arm, the printf shape is admitted. So the APART rows are refused BY these lines, not by another arm.
for label, pair, rows in (
    (
        "the script arm without the comment-stripped phrase",
        (
            "_spells_invocation(text) or _names_phrase(_code_text(family, text))",
            "_spells_invocation(text)",
        ),
        SCRIPT_ARM_ROWS,
    ),
    (
        "the $ arm without the written-script lookup",
        (
            "            for word in dict.fromkeys((operand, known)):\n",
            "            for word in ():\n",
        ),
        [PRINTF_ROW],
    ),
    # Review ba934aef.1: each family back on the quote-blind regex strip admits its in-a-string row, so those rows are refused BY the quote-aware reading.
    (
        "the quote-blind shell strip",
        (
            "        return _shell_code_text(text)\n",
            '        return re.sub(r"(?:^|(?<=\\s))#.*$", "", text, flags=re.M)\n',
        ),
        [QUOTED_ROWS["quoted.sh"]],
    ),
    (
        "the quote-blind JS strip",
        (
            "        return _slash_code_text(text)\n",
            '        return re.sub(r"(?:^|(?<=\\s))(?:/\\*.*?\\*/|//[^\\n]*)", "", text, flags=re.M | re.S)\n',
        ),
        [QUOTED_ROWS["quoted.js"]],
    ),
    (
        "the quote-blind perl strip",
        (
            '    if family == "shell":\n        return _shell_code_text(text)\n',
            '    if family in ("shell", "perl"):\n        return re.sub(r"(?:^|(?<=\\s))#.*$", "", text, flags=re.M)\n',
        ),
        [QUOTED_ROWS["quoted.pl"]],
    ),
):
    admitted = [n for n, c in rows if run_guard(c, defect=pair)[0] == 0]
    if len(admitted) != len(rows):
        failures.append("rework plant: %s" % label)
        print(
            "*** FAIL *** with %s planted, only %d of %d admitted"
            % (label, len(admitted), len(rows))
        )
    else:
        print("%s: all %d admitted" % (label, len(rows)))

if failures:
    print("\n%d FAILED: %s" % (len(failures), ", ".join(failures[:25])))
    sys.exit(1)
print(
    "\nOK: %d refused, %d allowed, %d helper rows, %d tree(s) on disk, chain and plants held"
    % (len(REFUSED), len(ALLOWED), len(HELPER), len(on_disk))
)
