#!/usr/bin/env python3
"""Written-message control harness for block_commit_meta (#c56b63bd).

The guard's differential golden covers its ordinary verdicts; this suite covers one shape the golden cannot hold, because it needs files on disk and a mutant: a `git commit -F <file>` whose file an earlier clause of the SAME command writes. The guard runs once, before that clause, so the bytes on disk are an earlier command's. Before #c56b63bd the guard skipped such a file and judged only a footer spelled out in the command itself, so a trailer that reached the file any other way (a `%s` argument, a `tee` from another file, a heredoc expanding a variable) was committed unjudged.

Each fire case writes a trailer into a stale CLEAN file and must be REFUSED naming the write (`commit_policy.written_message_refusal`). THE MUTANT answers `written_message_files` with [] everywhere and must flip every fire case to allowed; the CONTROLs (an unwritten `-F` file read both ways, and a `gh pr create --body-file` the helper does not govern) must not move.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER, and the mutant through the same guard source with `.claude` on `PYTHONPATH`, so no hand-written path hop is needed.
"""

import ast
import atexit
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
CLAUDE_DIR = HERE.parents[1]
DISPATCH = str(HERE.parent / "dispatch.py")
STEM = "block_commit_meta"
GUARD = HERE / ("%s.py" % STEM)

# The claude-code product URL, read from .ci/config/well-known.env by the CI reader, loaded by file (check:ci-literal-sources forbids spelling it).
_WK = importlib.util.spec_from_file_location(
    "well_known_for_commit_meta", CLAUDE_DIR.parent / ".ci" / "rediacc_ci" / "well_known.py"
)
if _WK is None or _WK.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/well_known.py is missing" % __file__)
_WK_MOD = importlib.util.module_from_spec(_WK)
_WK.loader.exec_module(_WK_MOD)
CLAUDE_CODE_URL = _WK_MOD.CLAUDE_CODE_URL

# Assembled, so no source line here is itself a trailer or a footer.
TRAILER = "Co-" + "Authored-By: Bot <bot@example.invalid>"
COMMIT = "git " + "commit"

WORK = pathlib.Path(tempfile.mkdtemp(prefix="commit-meta-written-"))
atexit.register(shutil.rmtree, WORK, ignore_errors=True)
(WORK / "clean.txt").write_text("fix: x\n", encoding="utf-8")
(WORK / "trailer.txt").write_text("fix: x\n\n%s\n" % TRAILER, encoding="utf-8")
(WORK / "src.txt").write_text("fix: x\n\n%s\n" % TRAILER, encoding="utf-8")

NEEDLE = "nothing in this command ran, including"
REFUSED = "Do not add Co-Authored-By"

# (name, command, expect_blocked, stderr needle)
CASES = [
    (
        "printf spells the trailer through a %s argument",
        "printf 'fix: x\\n\\n%%s-Authored-By: b <b@c>\\n' Co > clean.txt && %s -F clean.txt -- a"
        % COMMIT,
        True,
        NEEDLE,
    ),
    (
        "tee copies a trailer from another file, read by --file=",
        "cat src.txt | tee clean.txt && %s --file=clean.txt -- a" % COMMIT,
        True,
        NEEDLE,
    ),
    (
        "a heredoc expands a variable into the trailer",
        "P=Co-; cat > clean.txt <<EOF\nfix: x\n\n${P}Authored-By: b <b@c>\nEOF\n%s -F clean.txt -- a"
        % COMMIT,
        True,
        NEEDLE,
    ),
    (
        "the redirect by absolute path, the -F relative",
        "cat src.txt > %s/clean.txt; %s -F clean.txt -- a" % (WORK, COMMIT),
        True,
        NEEDLE,
    ),
    ("CONTROL: an unwritten clean -F file is read", "%s -F clean.txt -- a" % COMMIT, False, ""),
    (
        "CONTROL: another file written, the unwritten -F file still read",
        "printf x > other.txt && %s -F trailer.txt -- a" % COMMIT,
        True,
        REFUSED,
    ),
    (
        "CONTROL: a gh body file this command writes is not a commit",
        "printf 'prose\\n' > body.md; gh pr create --title t --body-file body.md",
        False,
        "",
    ),
]

MUTANT_RUNNER = (
    "import sys\n"
    "from rediacc_hooks import commit_policy, hookio\n"
    "commit_policy.written_message_files = lambda *a, **k: []\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "ns = {'__name__': 'mutant', '__file__': %r}\n"
    "exec(compile(src, 'mutant', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)


def run(command, mutant=False):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(WORK))
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    if mutant:
        argv = [sys.executable, "-c", MUTANT_RUNNER % (str(GUARD), str(GUARD))]
        env["PYTHONPATH"] = str(CLAUDE_DIR)
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(
        argv, input=payload, capture_output=True, text=True, check=False, env=env, cwd=str(WORK)
    )
    if mutant and proc.returncode not in (0, 2):
        raise SystemExit("mutant runner crashed: %s" % proc.stderr[-800:])
    return proc.returncode != 0, proc.stderr


fails = 0
blocked = 0
for name, command, want, needle in CASES:
    got, err = run(command)
    mut, _ = run(command, mutant=True)
    blocked += got
    control = name.startswith("CONTROL")
    ok = got == want and needle in err and (mut == got if control else mut != got)
    fails += not ok
    print(
        "%-66s want=%-8s got=%-8s mutant=%-8s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "BLOCKED" if mut else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:3])

# --------------------------------------------------------------------------- the session-link half (incident 2026-10-30, PR-TASK 9f92c43e) ---------------------------------------------------------------------------
#
# EVERY CHANNEL, BOTH DIRECTIONS, AND A MUTANT. Each fire case publishes a session link or a session trailer through one channel (an inline -m, a -F file, `$(cat <file>)`, an inherited variable, a PR body, a PR body file, an issue comment file, a `gh api -f body=`, a `gh api -F body=@`); each CONTROL is an audit shape that must stay legal. THE MUTANT replaces `SESSION_LEAK` with a pattern
# that never matches: every fire case must flip to allowed (else it was refused by something other than the session rule), and no CONTROL may move. All strings are assembled, so no source line here is itself a trailer or a link.
SESSION_HEAD = "Claude-" + "Session"
SESSION_URL = "https://claude" + ".ai/code/session_01AbCdEfGh"
(WORK / "leak.txt").write_text("fix: x\n\n%s: %s\n" % (SESSION_HEAD, SESSION_URL), encoding="utf-8")
LEAK_ENV = {"COMMIT_META_LEAK_MSG": "fix\n\n%s: %s\n" % (SESSION_HEAD, SESSION_URL)}
SESSION_REFUSED = "console is a PUBLIC repository"

# (name, command, expect_blocked)
SESSION_CASES = [
    (
        "an inline -m trailer",
        "%s -m 'fix: x' -m '%s: %s' -- a" % (COMMIT, SESSION_HEAD, SESSION_URL),
        True,
    ),
    (
        "the Claude-Code-Session spelling as a --trailer",
        "%s -m fix --trailer Claude-Code-%s=x -- a" % (COMMIT, "Session"),
        True,
    ),
    ("a lower-case trailer", "%s -m 'fix' -m 'claude-%s: x' -- a" % (COMMIT, "session"), True),
    ("a -F message file", "%s -F leak.txt -- a" % COMMIT, True),
    ("a $(cat <file>) message", '%s -m "$(cat leak.txt)" -- a' % COMMIT, True),
    ("an inherited variable", '%s -m "$COMMIT_META_LEAK_MSG" -- a' % COMMIT, True),
    ("a tag message", "git tag -a v9 -m '%s'" % SESSION_URL, True),
    (
        "a PR body chat link",
        "gh pr create -t t --body 'see https://claude" + ".ai/chat/1a2b-3c4d'",
        True,
    ),
    ("a PR title artifact link", "gh pr edit 5 --title 'x claude" + ".ai/artifact/abc123'", True),
    ("a PR comment body file", "gh pr comment 5 --body-file leak.txt", True),
    ("an issue comment -F file", "gh issue comment 5 -F leak.txt", True),
    ("a review body share link", "gh pr review 5 --comment -b 'claude" + ".ai/share/abc'", True),
    (
        "a gh api -f body= comment",
        "gh api repos/o/r/issues/5/comments -f body='%s'" % SESSION_URL,
        True,
    ),
    ("a gh api -F body=@ PATCH", "gh api repos/o/r/pulls/5 -X PATCH -F body=@leak.txt", True),
    (
        "a claude.com session link",
        "gh pr comment 5 -b 'https://claude" + ".com/code/session_abc1'",
        True,
    ),
    (
        "a PR comment body piped on stdin (--body-file -)",
        "cat leak.txt | gh pr comment 5 --body-file -",
        True,
    ),
    (
        "a PR comment body redirected on stdin",
        "gh pr comment 5 --body-file - < leak.txt",
        True,
    ),
    ("a commit message piped on stdin (-F -)", "cat leak.txt | %s -F - -- a" % COMMIT, True),
    (
        "CONTROL: a clean file piped on stdin",
        "cat clean.txt | gh pr comment 5 --body-file -",
        False,
    ),
    (
        "CONTROL: a public claude.com blog slug is not a session link",
        "gh pr comment 5 -b 'see https://claude" + ".com/blog/share-your-work'",
        False,
    ),
    (
        "a hyphen-form session link (review 28139d6b.2)",
        "gh pr comment 5 -b 'https://claude" + ".ai/code/session-abc1'",
        True,
    ),
    (
        "an underscore-form session link (review 28139d6b.2)",
        "gh pr comment 5 -b 'https://claude" + ".ai/code/session_abc1'",
        True,
    ),
    (
        "CONTROL: a claude.ai blog slug naming session state",
        "gh pr comment 5 -b 'see https://claude" + ".ai/blog/session-state'",
        False,
    ),
    (
        "a hyphen-form code session id with no digit (review 801f5209.3)",
        "gh pr comment 5 -b 'https://claude" + ".ai/code/session-abcdef'",
        True,
    ),
    (
        "CONTROL: a blog slug with chat, a hyphen and a digit (review 801f5209.2)",
        "gh pr comment 5 -b 'see https://claude" + ".com/blog/chat-with-claude-4'",
        False,
    ),
    ("CONTROL: git log --grep claude.ai", "git log --grep claude" + ".ai", False),
    ("CONTROL: grep for the trailer", "grep -rn '%s:' ." % SESSION_HEAD, False),
    (
        "CONTROL: prose naming the rule",
        "echo 'never add a %s: line or a %s link'" % (SESSION_HEAD, SESSION_URL),
        False,
    ),
    (
        "CONTROL: a commit naming the rule",
        "%s -m 'fix(hooks): refuse the %s trailer and claude.ai/code/session_<id> links' -- a"
        % (COMMIT, SESSION_HEAD),
        False,
    ),
    (
        "CONTROL: reading a PR body and grepping it",
        "gh api repos/o/r/pulls/5 --jq .body | grep '%s'" % SESSION_URL,
        False,
    ),
    (
        "CONTROL: echoing the leaking variable publishes nothing",
        'echo "$COMMIT_META_LEAK_MSG"',
        False,
    ),
    (
        "CONTROL: the claude-code product link is not a session",
        "gh pr comment 5 -b 'see %s'" % CLAUDE_CODE_URL,
        False,
    ),
    ("CONTROL: a clean -F file", "%s -F clean.txt -- a" % COMMIT, False),
]

SESSION_MUTANT = (
    "import re, sys\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "ns = {'__name__': 'mutant', '__file__': %r}\n"
    "exec(compile(src, 'mutant', 'exec'), ns)\n"
    "ns['SESSION_LEAK'] = re.compile(r'(?!x)x')\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)


def run_session(command, mutant=False):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(WORK), **LEAK_ENV)
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    if mutant:
        argv = [sys.executable, "-c", SESSION_MUTANT % (str(GUARD), str(GUARD))]
        env["PYTHONPATH"] = str(CLAUDE_DIR)
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(
        argv, input=payload, capture_output=True, text=True, check=False, env=env, cwd=str(WORK)
    )
    if mutant and proc.returncode not in (0, 2):
        raise SystemExit("session mutant crashed: %s" % proc.stderr[-800:])
    return proc.returncode != 0, proc.stderr


print()
s_blocked = 0
for name, command, want in SESSION_CASES:
    got, err = run_session(command)
    mut, _ = run_session(command, mutant=True)
    s_blocked += got
    control = name.startswith("CONTROL")
    ok = (
        got == want
        and (SESSION_REFUSED in err if want else True)
        and (mut == got if control else not mut)
    )
    fails += not ok
    print(
        "%-66s want=%-8s got=%-8s mutant=%-8s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "BLOCKED" if mut else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:3])
if s_blocked == 0 or s_blocked == len(SESSION_CASES):
    print("*** FAIL *** the session half answered the same way on every case", file=sys.stderr)
    fails += 1
print(
    "%d session case(s), %d blocked, %d allowed"
    % (len(SESSION_CASES), s_blocked, len(SESSION_CASES) - s_blocked)
)

# THE GIT LAYER CARRIES A COPY OF THE TWO PATTERNS (githooks.py is loaded by file and cannot import the guard). A copy that drifts is a layer that checks something else.
_spec = importlib.util.spec_from_file_location(
    "githooks_commit_meta_under_test", CLAUDE_DIR / "rediacc_hooks" / "git" / "githooks.py"
)
if _spec is None or _spec.loader is None:
    raise SystemExit("%s: cannot load githooks.py" % __file__)
GH = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = GH
_spec.loader.exec_module(GH)


def _constants(path):
    """The module-level string constants `SESSION_TRAILER` and `SESSION_LINK` of `path`, read with `ast` so a reformatted (parenthesised, wrapped) assignment reads the same."""
    found = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in ("SESSION_TRAILER", "SESSION_LINK"):
                found[target.id] = ast.literal_eval(node.value)
    return found


_guard_ns = _constants(GUARD)
# The CI gate's copy (`check_claude_attribution.py`'s module), read as text for the same reason: it imports the `.ci` package, which this script does not put on its path.
_ci_ns = _constants(CLAUDE_DIR.parent / ".ci" / "rediacc_ci" / "quality" / "claude_attribution.py")
for attr in ("SESSION_TRAILER", "SESSION_LINK"):
    for where, value in (("githooks", getattr(GH, attr)), ("claude_attribution", _ci_ns.get(attr))):
        same = attr in _guard_ns and _guard_ns[attr] == value
        fails += not same
        print(
            "%-66s %s"
            % (
                "%s.%s matches the guard's" % (where, attr),
                "ok" if same else "*** FAIL *** the copies differ",
            )
        )

# --------------------------------------------------------------------------- the git layer, on a REAL repository with core.hooksPath at the real hooks ---------------------------------------------------------------------------
#
# commit-msg: a leaking commit is refused, a commit naming the rule is not. pre-push: a real `git push` to a bare remote with a leaking commit in the outgoing range is refused naming its sha; once that commit is on the remote (pushed past the hook, the shape of the four commits that reached GitHub first), a later clean push is NOT blocked by it.
# The fixture pushes past the hook with `core.hooksPath=/dev/null` on the one call that plants, never with the operator's variable, and `COMMIT_POLICY_OK` is removed from the environment so an inherited one cannot make every refusal below vacuous.
GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="t",
    GIT_AUTHOR_EMAIL="t@example.invalid",
    GIT_COMMITTER_NAME="t",
    GIT_COMMITTER_EMAIL="t@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)
GIT_ENV.pop("COMMIT_POLICY_OK", None)
# The pre-push backup-receipt check judges a scratch repository with no console tree as an unverified backup push; its own well-formed escape keeps that unrelated rule out of these verdicts, so each refusal below is the session rule's (the refusal is asserted to name the sha) and each admission is not a backup verdict.
GIT_ENV["BACKUP_CHECK_PUSH_REASON"] = (
    "not-runtime: scratch repository in the block_commit_meta git-layer fixture, no backup code "
    "ASKED:2026-10-30T00:00Z"
)
REPO = WORK / "gitlayer"
BARE = WORK / "gitlayer-remote.git"
HOOKS_DIR = str(CLAUDE_DIR / "rediacc_hooks" / "git")


def git(*args, check=True):
    proc = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, env=GIT_ENV, check=False
    )
    if check and proc.returncode != 0:
        raise SystemExit("git %s failed: %s" % (" ".join(args), proc.stderr[-600:]))
    return proc


def layer(name, ok, detail=""):
    """Print one git-layer verdict; 1 when it failed, for the caller to add to `fails`."""
    print("%-66s %s" % (name, "ok" if ok else "*** FAIL *** " + detail[-400:]))
    return int(not ok)


subprocess.run(["git", "init", "-q", "--bare", str(BARE)], check=True, env=GIT_ENV)
# The repository shape the branch rules expect, laid down with the hooks off: a `main` root commit, then the one live `0101-1` cut from it. Every judged call below runs with the real hooks on.
subprocess.run(["git", "init", "-q", "-b", "main", str(REPO)], check=True, env=GIT_ENV)
git("remote", "add", "origin", str(BARE))
(REPO / "root").write_text("root\n", encoding="utf-8")
git("add", "root")
git("-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "chore: root")
git("-c", "core.hooksPath=/dev/null", "switch", "-q", "-c", "0101-1")
git("config", "core.hooksPath", HOOKS_DIR)
(REPO / "a").write_text("a\n", encoding="utf-8")
git("add", "a")
(WORK / "leak-commit.txt").write_text(
    "fix: x\n\n%s: %s\n" % (SESSION_HEAD, SESSION_URL), encoding="utf-8"
)
(WORK / "footer-commit.txt").write_text(
    "fix: x\n\n\U0001f916 " + "Generated" + " with [Claude Code](%s)\n" % CLAUDE_CODE_URL,
    encoding="utf-8",
)
p = git("commit", "-q", "-F", str(WORK / "leak-commit.txt"), check=False)
fails += layer(
    "commit-msg refuses a session trailer and link",
    p.returncode != 0 and "PUBLIC" in p.stderr,
    p.stderr,
)
p = git("commit", "-q", "-F", str(WORK / "footer-commit.txt"), check=False)
fails += layer(
    "commit-msg refuses the Claude Code footer",
    p.returncode != 0 and "PUBLIC" in p.stderr,
    p.stderr,
)
p = git(
    "commit",
    "-q",
    "-m",
    "fix(hooks): refuse the %s trailer and claude.ai/code/session_<id> links" % SESSION_HEAD,
    check=False,
)
fails += layer("CONTROL commit-msg admits a message naming the rule", p.returncode == 0, p.stderr)
p = git("push", "-q", "origin", "0101-1", check=False)
fails += layer("CONTROL pre-push admits a clean outgoing range", p.returncode == 0, p.stderr)
(REPO / "b").write_text("b\n", encoding="utf-8")
git("add", "b")
git("-c", "core.hooksPath=/dev/null", "commit", "-q", "-F", str(WORK / "leak-commit.txt"))
leak_sha = git("rev-parse", "HEAD").stdout.strip()
p = git("push", "-q", "origin", "0101-1", check=False)
fails += layer(
    "pre-push refuses an outgoing leaking commit, naming its sha",
    p.returncode != 0 and leak_sha[:12] in p.stderr,
    p.stderr,
)
git("-c", "core.hooksPath=/dev/null", "push", "-q", "origin", "0101-1")
(REPO / "c").write_text("c\n", encoding="utf-8")
git("add", "c")
git("commit", "-q", "-m", "fix: y")
p = git("push", "-q", "origin", "0101-1", check=False)
fails += layer(
    "CONTROL pre-push does not re-block a commit a remote already has", p.returncode == 0, p.stderr
)

print()
if blocked == 0 or blocked == len(CASES):
    print("*** FAIL *** the guard answered the same way on every case", file=sys.stderr)
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
