#!/usr/bin/env python3
"""Control harness for block_origin_clone, driven through the dispatcher.

Each row is one Bash command with the answer it must get. Real fixture repositories stand in for "a source with no origin of ours" and "a local tree whose origin is ours", because the guard reads their config. The declared DEFECT planted in a copy must flip fire rows, and the chain must carry the guard, so a guard that stopped running cannot leave this green.

Commands sit in tables and reach `subprocess` through a variable: the guard reads a script run by path, and judges only what a call is handed directly.
"""

import ast
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
HOOKS = HERE.parent
DISPATCH = str(HOOKS / "dispatch.py")
STEM = "block_origin_clone"
GUARD = HERE / ("%s.py" % STEM)
REPO_ROOT = HERE.parents[2]
ROOT = str(REPO_ROOT)
HOME = os.path.expanduser("~")
MESSAGE_MARK = "ASKED:2026-11-04T10:15Z"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("%s: %s is missing" % (__file__, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtmp = _load("runtmp", REPO_ROOT / ".ci" / "rediacc_ci" / "runtmp.py")
wellknown = _load("wellknown_for_origin_clone", HOOKS / "wellknown.py")


def _wk(command):
    """A table row's command with each `<NAME>` token spelled from the registry, so no owned value is typed here."""
    for token, value in (
        ("<GHO_TOKEN>", wellknown.GH_ORIGIN.replace("://", "://x-access-token:t0k@")),
        ("<GHO_HTTP>", wellknown.GH_ORIGIN.replace("https", "http")),
        ("<GHO>", wellknown.GH_ORIGIN),
        ("<GH>", wellknown.GH_REPO),
        ("<RENET>", wellknown.RENET_REPO),
        ("<ACCOUNT>", wellknown.ACCOUNT_REPO),
        ("<ELITE>", wellknown.ELITE_REPO),
        ("<TAP>", wellknown.HOMEBREW_TAP_REPO),
        ("<MIRROR>", wellknown.GITLAB_MIRROR_HOST),
    ):
        command = command.replace(token, value)
    return command


TMP = pathlib.Path(runtmp.run_dir("guard-origin-clone-"))

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)

failures: list[str] = []


def _git(*argv, cwd=None):
    subprocess.run(["git", *argv], cwd=cwd, check=True, capture_output=True, env=GIT_ENV)


def _repo(name, origin=None):
    path = TMP / name
    path.mkdir(parents=True)
    _git("init", "-q", "--initial-branch=main", cwd=path)
    _git("commit", "-q", "--allow-empty", "-m", "seed", cwd=path)
    if origin:
        _git("remote", "add", "origin", origin, cwd=path)
    return str(path)


CONSOLE = "%s/%s.git" % (wellknown.GH_ORIGIN, wellknown.GH_REPO)
RENET = "%s/%s.git" % (wellknown.GH_ORIGIN, wellknown.RENET_REPO)
FIXTURE = _repo("fixture")
FIXTURE_FOREIGN = _repo("fixture-foreign", origin="https://example.invalid/other/app.git")
OLD_CLONE = _repo("old-clone", origin=CONSOLE)
OLD_LOCAL = _repo("old-local", origin=ROOT)
# git reads an existing directory as a path before a colon as a host.
_repo("github.com:%s" % wellknown.GH_REPO)
EMPTY_DIR = TMP / "scripts"
EMPTY_DIR.mkdir()
X = str(TMP / "x")

# A script run by path: its text is the program unless it is tracked and unchanged.
SH_CLONE = EMPTY_DIR / "clone.sh"
SH_CLONE.write_text("#!/bin/sh\ngit clone %s %s\n" % (CONSOLE, X), encoding="utf-8")
PY_CLONE = EMPTY_DIR / "clone.py"
PY_CLONE.write_text(
    "import subprocess\nsubprocess.run(['git', 'clone', %r, %r])\n" % (CONSOLE, X),
    encoding="utf-8",
)
PY_SHELL = EMPTY_DIR / "shell.py"
PY_SHELL.write_text(
    "import os\nos.system('git clone %s %s')\n" % (CONSOLE, X),
    encoding="utf-8",
)
PY_TABLE = EMPTY_DIR / "table.py"
PY_TABLE.write_text(
    "ROWS = [('plain', 'git clone %s %s', True)]\nprint(len(ROWS))\n" % (CONSOLE, X),
    encoding="utf-8",
)
SH_FIXTURE = EMPTY_DIR / "fixture.sh"
SH_FIXTURE.write_text("#!/bin/sh\ngit clone %s %s\n" % (FIXTURE, X), encoding="utf-8")

REFUSED = [
    # Every spelling of the console's origin.
    ("https", "git clone <GHO>/<GH>.git /tmp/x"),
    ("https, no .git", "git clone <GHO>/<GH> /tmp/x"),
    ("https, a trailing slash", "git clone <GHO>/<GH>/ /tmp/x"),
    ("http", "git clone <GHO_HTTP>/<GH>.git /tmp/x"),
    ("git protocol", "git clone git://github.com/<GH>.git /tmp/x"),
    ("ssh url", "git clone ssh://git@github.com/<GH>.git /tmp/x"),
    ("ssh url with a port", "git clone ssh://git@ssh.github.com:443/<GH>.git /tmp/x"),
    ("scp form", "git clone git@github.com:<GH>.git /tmp/x"),
    ("scp form, no user or .git", "git clone github.com:<GH> /tmp/x"),
    (
        "a token in the url",
        "git clone <GHO_TOKEN>/<GH> /tmp/x",
    ),
    ("case folded", "git clone https://GitHub.com/Rediacc/Console.git /tmp/x"),
    ("percent encoded", "git clone <GHO>/rediacc/c%6Fnsole.git /tmp/x"),
    ("no target", "git clone <GHO>/<GH>.git"),
    ("target under home", "git clone <GHO>/<GH>.git ~/x"),
    ("target in the cache", "git clone <GHO>/<GH>.git ~/.cache/x"),
    # Each submodule, https and ssh.
    ("renet", "git clone <GHO>/<RENET>.git /tmp/x"),
    ("account", "git clone <GHO>/<ACCOUNT>.git /tmp/x"),
    ("elite", "git clone <GHO>/<ELITE>.git /tmp/x"),
    ("homebrew-tap", "git clone <GHO>/<TAP>.git /tmp/x"),
    ("renet ssh", "git clone git@github.com:<RENET>.git /tmp/x"),
    ("account ssh", "git clone ssh://git@github.com/<ACCOUNT>.git /tmp/x"),
    ("elite ssh", "git clone git@github.com:<ELITE>.git /tmp/x"),
    ("homebrew-tap ssh", "git clone git@github.com:<TAP>.git /tmp/x"),
    # The mirror.
    ("gitlab mirror", "git clone https://<MIRROR>/rediacc-org/github/console.git /tmp/x"),
    ("gitlab mirror ssh", "git clone git@<MIRROR>:rediacc-org/github/renet.git /tmp/x"),
    # A local path in this checkout or its git directory.
    ("--shared of the checkout", "git clone --shared %s /tmp/x" % ROOT),
    ("--local of the checkout", "git clone --local %s /tmp/x" % ROOT),
    ("the submodule by absolute path", "git clone %s/private/renet /tmp/y" % ROOT),
    ("the submodule by relative path", "git clone private/renet /tmp/y"),
    ("the module store", "git clone .git/modules/private/renet ~/x"),
    ("the module store, absolute", "git clone %s/.git/modules/private/account /tmp/x" % ROOT),
    ("the git directory", "git clone .git /tmp/x"),
    ("dot", "git clone . /tmp/x"),
    ("a file url", "git clone file://%s /tmp/x" % ROOT),
    ("a localhost ssh url", "git clone ssh://localhost%s /tmp/x" % ROOT),
    ("a localhost scp form", "git clone localhost:%s /tmp/x" % ROOT),
    ("from a subdirectory", "cd %s/packages && git clone .. /tmp/x" % ROOT),
    ("a -C prefix", "git -C %s clone . /tmp/x" % ROOT),
    ("$PWD", 'cd %s && git clone "$PWD" /tmp/x' % ROOT),
    ("$(pwd)", 'git clone "$(pwd)" /tmp/x'),
    ("$CLAUDE_PROJECT_DIR", 'git clone "$CLAUDE_PROJECT_DIR" /tmp/x'),
    ("$(rev-parse)", 'git clone "$(git rev-parse --show-toplevel)" /tmp/x'),
    ("a variable from rev-parse", 'R=$(git rev-parse --show-toplevel); git clone "$R" /tmp/x'),
    ("a variable holding the path", 'R=%s; git clone "$R" /tmp/x' % ROOT),
    ("a variable holding the url", 'U=%s; git clone "$U" /tmp/x' % CONSOLE),
    ("a loop over the url", "for u in %s; do git clone $u /tmp/x; done" % CONSOLE),
    # Options before and after the source.
    ("--depth value", "git clone --depth 1 %s /tmp/x" % CONSOLE),
    ("--depth=value", "git clone --depth=1 %s /tmp/x" % CONSOLE),
    ("-b value", "git clone -b main %s /tmp/x" % CONSOLE),
    ("a bundle ending in a value letter", "git clone -qb main %s /tmp/x" % CONSOLE),
    ("-bvalue", "git clone -bmain %s /tmp/x" % CONSOLE),
    ("a unique long prefix", "git clone --dep 1 %s /tmp/x" % CONSOLE),
    ("--bare", "git clone --bare %s /tmp/x" % CONSOLE),
    ("--mirror", "git clone --mirror %s /tmp/x" % CONSOLE),
    ("-c value", "git clone -c a=b %s /tmp/x" % CONSOLE),
    ("--filter", "git clone --filter=blob:none %s /tmp/x" % CONSOLE),
    ("-- ends the options", "git clone -- %s /tmp/x" % CONSOLE),
    ("options after the source", "git clone %s /tmp/x --depth 1" % CONSOLE),
    ("--reference beside our source", "git clone --reference %s %s /tmp/x" % (FIXTURE, CONSOLE)),
    # gh.
    ("gh owner/repo", "gh repo clone <GH>"),
    ("gh owner/repo with a target", "gh repo clone <RENET> /tmp/x"),
    ("gh with a url", "gh repo clone %s /tmp/x" % CONSOLE),
    ("gh with host/owner/repo", "gh repo clone github.com/<ACCOUNT>"),
    ("gh with git flags", "gh repo clone <GH> /tmp/x -- --depth 1"),
    ("gh with its own flag", "gh repo clone -u up <GH> /tmp/x"),
    ("gh fork --clone", "gh repo fork <GH> --clone"),
    # Wrappers.
    ("sh -c", 'sh -c "git clone %s /tmp/x"' % CONSOLE),
    ("bash -c", "bash -c 'git clone --shared %s /tmp/x'" % ROOT),
    ("bash heredoc", "bash <<'EOF'\ngit clone %s /tmp/x\nEOF" % CONSOLE),
    ("a piped shell", "echo 'git clone %s /tmp/x' | sh" % CONSOLE),
    ("eval", 'eval "git clone %s /tmp/x"' % CONSOLE),
    ("a substitution", "echo $(git clone %s /tmp/x)" % CONSOLE),
    ("env", "env A=1 git clone %s /tmp/x" % CONSOLE),
    ("timeout", "timeout 60 git clone %s /tmp/x" % CONSOLE),
    ("sudo", "sudo git clone %s /tmp/x" % CONSOLE),
    ("command", "command git clone %s /tmp/x" % CONSOLE),
    ("a path to git", "/usr/bin/git clone %s /tmp/x" % CONSOLE),
    ("a global -c", "git -c a=b clone %s /tmp/x" % CONSOLE),
    ("a verb in a variable", "V=clone; git $V %s /tmp/x" % CONSOLE),
    ("a rewrite by -c", "git -c url.<GHO>/.insteadOf=gh: clone gh:<GH> /x"),
    ("xargs", "echo %s | xargs git clone" % CONSOLE),
    ("xargs -I", "echo %s | xargs -I{} git clone {} /tmp/x" % CONSOLE),
    ("find -exec", r"find . -maxdepth 0 -exec git clone %s /tmp/x \;" % CONSOLE),
    ("npx -c", 'npx -c "git clone %s /tmp/x"' % CONSOLE),
    # Program text.
    (
        "python -c with an argv list",
        "python3 -c \"import subprocess; subprocess.run(['git','clone','%s','/tmp/x'])\"" % CONSOLE,
    ),
    (
        "python -c with a shell string",
        "python3 -c \"import os; os.system('git clone --shared %s /tmp/x')\"" % ROOT,
    ),
    (
        "python -c with a helper's argv",
        "python3 -c \"sh('git', ['clone', '-q', '%s', '/tmp/x'])\"" % CONSOLE,
    ),
    (
        "python -c, a joined string",
        "python3 -c \"import os; os.system('git clone ' + '%s /tmp/x')\"" % CONSOLE,
    ),
    (
        "python heredoc",
        "python3 - <<'EOF'\nimport subprocess\nsubprocess.run(['git', 'clone', '%s', 'y'])\nEOF"
        % RENET,
    ),
    (
        "python here-string",
        "python3 - <<< 'import os; os.system(\"git clone %s /tmp/x\")'" % CONSOLE,
    ),
    (
        "sh -c around python",
        'sh -c "python3 -c \\"import os; os.system(\'git clone %s /x\')\\""' % CONSOLE,
    ),
    ("node -e", 'node -e \'require("child_process").execSync("git clone %s /x")\'' % CONSOLE),
    (
        "node -e with an argv",
        'node -e \'require("child_process").spawnSync("git",["clone","%s","/x"])\'' % CONSOLE,
    ),
    ("perl -e with an argv", 'perl -e \'system("git", "clone", "%s", "/x")\'' % CONSOLE),
    ("a perl qw list", "perl -e 'system qw(git clone %s /x)'" % CONSOLE),
    # A script run by path.
    (
        "a script the command writes",
        "cat > %s/w.sh <<'E'\ngit clone %s /x\nE\nbash %s/w.sh" % (TMP, CONSOLE, TMP),
    ),
    ("a shell script on disk", "bash %s" % SH_CLONE),
    ("a python script's argv on disk", "python3 %s" % PY_CLONE),
    ("a python script's call on disk", "python3 %s" % PY_SHELL),
    ("python reading a file on stdin", "python3 < %s" % PY_CLONE),
    ("a shell reading a file on stdin", "sh < %s" % SH_CLONE),
    # `git init` plus a fetch is the same act.
    ("init, fetch -C", "git init /tmp/x && git -C /tmp/x fetch %s" % CONSOLE),
    ("init, fetch the path", "git init /tmp/x && git -C /tmp/x fetch %s" % ROOT),
    (
        "init, fetch the module store",
        "git init /tmp/x; git -C /tmp/x fetch %s/.git/modules/private/renet" % ROOT,
    ),
    ("init, cd, fetch", "git init /tmp/x && cd /tmp/x && git fetch %s" % RENET),
    ("init, cd, pull", "git init /tmp/x && cd /tmp/x && git pull %s main" % CONSOLE),
    ("init, remote add", "git init /tmp/x && git -C /tmp/x remote add o %s" % CONSOLE),
    ("init, submodule add", "git init /tmp/x && git -C /tmp/x submodule add %s s" % CONSOLE),
    ("--git-dir fetch", "git --git-dir=/tmp/x/.git fetch %s" % CONSOLE),
    ("GIT_DIR fetch", "GIT_DIR=/tmp/x/.git git fetch %s" % CONSOLE),
    ("a fetch with a value option", "git -C /tmp/x fetch --depth 1 %s" % CONSOLE),
    (
        "init inside the checkout",
        "git init .claude/zz-probe && git -C .claude/zz-probe fetch %s" % CONSOLE,
    ),
    ("a fetch in sh -c", "sh -c 'git init /tmp/x && git -C /tmp/x fetch %s'" % CONSOLE),
    # A local tree whose origin is ours is the same second tree one hop away.
    ("a local tree with our origin", "git clone %s /tmp/y" % OLD_CLONE),
    ("a local tree cloned from the checkout", "git clone %s /tmp/y" % OLD_LOCAL),
    ("a fetch of a named remote that is ours", "git -C %s fetch origin" % OLD_CLONE),
]

ALLOWED = [
    # Sources with no origin of ours.
    ("a missing fixture path", "git clone /tmp/fixture /tmp/y"),
    ("a real fixture", "git clone %s /tmp/y" % FIXTURE),
    ("a real fixture with a foreign origin", "git clone %s /tmp/y" % FIXTURE_FOREIGN),
    ("a fixture into this checkout", "git clone %s private/zz-probe" % FIXTURE),
    ("an unrelated url", "git clone <GHO>/torvalds/linux.git /tmp/y"),
    ("the same name under another owner", "git clone <GHO>/acme/console.git /tmp/y"),
    ("another repo of the owner", "git clone <GHO>/rediacc/website.git /tmp/y"),
    ("a name extending ours", "git clone <GHO>/rediacc/console-docs.git /tmp/y"),
    ("another mirror group", "git clone https://<MIRROR>/other/console.git /tmp/y"),
    ("a foreign host", "git clone https://example.invalid/<GH>.git /tmp/y"),
    ("a scp form elsewhere", "git clone git@example.invalid:<GH>.git /tmp/y"),
    (
        "--reference to ours for a foreign source",
        "git clone --reference %s https://example.invalid/a.git /tmp/y" % ROOT,
    ),
    ("a value equal to our url", "git clone -o %s %s /tmp/y" % (CONSOLE, FIXTURE)),
    ("an unknown scratch variable", 'T=$(mktemp -d); git init -q "$T/a"; git clone "$T/a" "$T/b"'),
    ("gh elsewhere", "gh repo clone torvalds/linux /tmp/y"),
    ("gh with a bare name", "gh repo clone console"),
    ("gh repo view of ours", "gh repo view <GH>"),
    ("gh fork with no clone", "gh repo fork <GH>"),
    # Mentions.
    ("echo", "echo git clone %s /tmp/x" % CONSOLE),
    ("echo of a local path", "echo git clone --shared %s /tmp/x" % ROOT),
    ("printf", "printf '%%s\\n' 'git clone %s'" % CONSOLE),
    ("a heredoc body", "cat > n.md <<'EOF'\ngit clone %s /tmp/x\nEOF" % CONSOLE),
    ("an unquoted heredoc body", "cat > n.md <<EOF\ngit clone %s /tmp/x\nEOF" % CONSOLE),
    ("grep", 'grep -rn "git clone %s" docs' % CONSOLE),
    ("a log grep", 'git log --grep="git clone %s"' % CONSOLE),
    ("a commit message", 'git commit -m "refuse git clone %s" -- x' % CONSOLE),
    ("a python sentence", "python3 -c 'print(\"never run git clone %s here\")'" % CONSOLE),
    ("a shell comment", "true # git clone %s /tmp/x" % CONSOLE),
    # Clones elsewhere than this machine.
    ("ssh to a machine", 'ssh vm "git clone %s /x"' % CONSOLE),
    ("ssh with words", "ssh -i k vm git clone %s /x" % CONSOLE),
    ("docker exec", "docker exec c git clone %s /x" % CONSOLE),
    ("rdc term", 'rdc term m -c "git clone %s /x"' % CONSOLE),
    # Reads and the usual work in this checkout.
    ("clone help", "git clone --help"),
    ("clone -h", "git clone -h"),
    ("a bare clone word", "git clone"),
    ("a fetch here", "git fetch origin"),
    ("a fetch of a submodule", "git -C private/renet fetch origin"),
    ("a fetch of our url here", "git fetch %s main" % CONSOLE),
    ("a pull here", "git pull origin main"),
    ("a remote add here", "git remote add mirror %s" % CONSOLE),
    ("a remote set-url here", "git remote set-url origin %s" % CONSOLE),
    ("a submodule update", "git submodule update --init private/renet"),
    ("a fetch in a fixture", "git -C %s fetch origin" % FIXTURE_FOREIGN),
    ("a fixture fetching a fixture", "git -C %s fetch %s" % (FIXTURE, FIXTURE_FOREIGN)),
    ("init alone", "git init /tmp/x"),
    ("init, fetch a fixture", "git init /tmp/x && git -C /tmp/x fetch %s" % FIXTURE),
    ("git status", "git status"),
    # The structural route: tools that clone in a subprocess this hook never sees.
    ("ci:quick", "npm run ci:quick"),
    ("the quick-clone selftest", "npx tsx scripts/ci-runner/run.ts --selftest"),
    ("the release entry", "npm run release:local -- --channel edge --dry-run"),
    (
        "a harness suite",
        "PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_release_local_gates.py",
    ),
    ("a tracked gate model by path", "python3 .ci/rediacc_ci/ci/gate_model.py"),
    ("a tracked release gate by path", "python3 .ci/rediacc_ci/release/local_gates.py"),
    ("setup", "./run.sh setup"),
    # A script run by path that clones a fixture, or only lists a command.
    ("a shell script cloning a fixture", "bash %s" % SH_FIXTURE),
    ("a python table of commands", "python3 %s" % PY_TABLE),
    # Program text with no source of ours.
    (
        "python with a computed source",
        "python3 -c \"import subprocess as s,sys; s.run(['git','clone',sys.argv[1],'/y'])\"",
    ),
    (
        "python -c on a fixture",
        "python3 -c \"import os; os.system('git clone %s /tmp/y')\"" % FIXTURE,
    ),
    (
        "a scratch variable behind a cd here",
        'cd %s && T=$(mktemp -d) && git init -q "$T/a" && git clone "$T/a" "$T/b"' % ROOT,
    ),
    (
        "a python string naming a script that clones",
        "python3 -c 'print(open(\"%s\").read())'" % SH_CLONE,
    ),
    ("cat of a script that clones", "cat %s" % SH_CLONE),
    ("grep of a script that clones", "grep -n clone %s" % PY_CLONE),
    ("an empty command", ""),
]

# The checkout spelled through the home directory, on a machine where it sits under it.
if ROOT.startswith(HOME + os.sep):
    UNDER_HOME = ROOT[len(HOME) + 1 :]
    REFUSED += [
        ("a tilde path", "git clone ~/%s /tmp/x" % UNDER_HOME),
        ("a $HOME path", 'git clone "$HOME/%s" /tmp/x' % UNDER_HOME),
        ("a ${HOME} path", "git clone ${HOME}/%s /tmp/x" % UNDER_HOME),
    ]

SUBMODULE_DIR = "%s/private/renet" % ROOT
RELATIVE = [
    ("dot from a fixture is the fixture", False, "git clone . /tmp/y", FIXTURE),
    ("a relative fixture beside it", False, "git clone fixture /tmp/y", str(TMP)),
    ("dot from a submodule is ours", True, "git clone . /tmp/y", SUBMODULE_DIR),
    (
        "a directory shaped like a host form",
        False,
        "git clone github.com:<GH> /tmp/y",
        str(TMP),
    ),
    ("a -C into a fixture leaves the checkout", False, "git -C %s clone . /tmp/y" % FIXTURE, ROOT),
    ("a fetch from a submodule stays inside", False, "git fetch %s" % RENET, SUBMODULE_DIR),
    ("a bare fetch of a tree with our origin", True, "git fetch", OLD_CLONE),
    ("a bare fetch of a foreign tree", False, "git fetch", FIXTURE_FOREIGN),
]

REFUSED = [(name, _wk(command)) for name, command in REFUSED]
ALLOWED = [(name, _wk(command)) for name, command in ALLOWED]
RELATIVE = [(name, ours, _wk(command), cwd) for name, ours, command, cwd in RELATIVE]


def _payload(command, cwd):
    return json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd},
    )


# The declared DEFECT applied to a copy, the whole guard otherwise unchanged.
BROKEN_RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "old, new = %r\n"
    "import ast\n"
    "cut = [n for n in ast.parse(src).body if isinstance(n, ast.Assign)"
    " and any(isinstance(t, ast.Name) and t.id == 'DEFECT' for t in n.targets)]\n"
    "outside = '\\n'.join(l for i, l in enumerate(src.split('\\n'), 1)"
    " if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut))\n"
    "assert cut and old in outside, 'DEFECT no longer applies outside its own declaration'\n"
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


ENV = dict(os.environ, CLAUDE_PROJECT_DIR=ROOT, HOME=HOME)


def run_guard(command, cwd=ROOT, defect=None):
    payload = _payload(command, cwd)
    if defect is not None:
        code = BROKEN_RUNNER % (str(HOOKS.parent), str(GUARD), defect, str(GUARD))
        argv = [sys.executable, "-c", code]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(
        argv, input=payload, capture_output=True, text=True, check=False, env=ENV, cwd=ROOT
    )
    if proc.returncode not in (0, 2):
        print("*** CRASH *** rc=%d %r\n%s" % (proc.returncode, command, proc.stderr[-800:]))
        failures.append("crash: %s" % command)
    return proc.returncode, proc.stderr


def check(name, want_blocked, command, cwd=ROOT):
    rc, err = run_guard(command, cwd)
    blocked = rc == 2
    fine = blocked == want_blocked
    if blocked and MESSAGE_MARK not in err:
        fine = False
    if not want_blocked and err:
        fine = False
    print(
        "%-46s want=%-8s got=%-8s %s"
        % (
            name[:46],
            "BLOCKED" if want_blocked else "allowed",
            "BLOCKED" if blocked else "allowed",
            "ok" if fine else "*** FAIL ***",
        )
    )
    if not fine:
        failures.append(name)
        print("    command: %r\n    stderr: %s" % (command, err.strip()[:400]))
    return blocked


print("== refused (%d rows)" % len(REFUSED))
for row_name, row_command in REFUSED:
    check(row_name, True, row_command)

print("== allowed (%d rows)" % len(ALLOWED))
for row_name, row_command in ALLOWED:
    check(row_name, False, row_command)

print("== a source relative to the event's cwd (%d rows)" % len(RELATIVE))
for row_name, row_blocked, row_command, row_cwd in RELATIVE:
    check(row_name, row_blocked, row_command, cwd=row_cwd)

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
    input=_payload("git clone --shared %s /tmp/x" % ROOT, ROOT),
    capture_output=True,
    text=True,
    check=False,
    env=ENV,
    cwd=ROOT,
)
if chain.returncode != 2 or MESSAGE_MARK not in chain.stderr:
    failures.append("chain did not refuse")
    print("*** FAIL *** the chain answered rc=%d: %s" % (chain.returncode, chain.stderr[-400:]))
else:
    print("chain: refused by this guard, rc=2")

print("== the DEFECT control")
defect_pair = _declared_defect()
flipped = [n for n, c in REFUSED if run_guard(c, defect=defect_pair)[0] == 0]
if len(flipped) < len(REFUSED) // 2:
    failures.append("defect control")
    print(
        "*** FAIL *** with %r planted only %d of %d refusals flipped"
        % (defect_pair, len(flipped), len(REFUSED))
    )
else:
    print(
        "planted %r: %d of %d refusals flipped, e.g. %r"
        % (defect_pair[0], len(flipped), len(REFUSED), flipped[0])
    )
kept = [n for n, c in ALLOWED if run_guard(c, defect=defect_pair)[0] != 0]
if kept:
    failures.append("defect refused an allowed row")
    print("*** FAIL *** the planted copy refused %r" % kept[:3])

if failures:
    print("\n%d FAILED: %s" % (len(failures), ", ".join(failures[:25])))
    sys.exit(1)
print("\nOK: %d refused, %d allowed, chain and DEFECT controls held" % (len(REFUSED), len(ALLOWED)))
