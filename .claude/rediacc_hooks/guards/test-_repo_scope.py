#!/usr/bin/env python3
"""Control harness for `_repo_scope`, the shared repository scope of the pre-bash guards whose rule is about this checkout and its submodules (#381462dc), driven through the dispatcher.

Each guard that calls `_repo_scope.elsewhere` gets four row families from one table, each row carrying the event `cwd` it is judged from:

  - ADMITTED: a throwaway `git init` under the system temp directory, reached by `-C`, by the event `cwd`, by `cd`, and as a repository the same command creates. Before #381462dc the `cwd` row was refused by every guard here but block_git_empty_commit, and these rows are what the plants below flip.
  - DOUBT: the same scratch repository, with something the resolver cannot know (a `GIT_DIR` on the run, a global option but `-C`/`-c`, an alias anywhere on the line, a relative event `cwd`, a `-C` directory in a variable). Each is still refused, so a doubt never reads as "elsewhere".
  - OURS: this checkout by `cwd` and by `-C`, a symlink to it, and a submodule. Still refused.
  - WALK: the spellings a text pattern anchored on `git commit` does not read past (`git -C <this checkout> commit ...`, `git -c k=v commit ...`, an alias for `commit`) for block_git_empty_commit and block_git_amend, and `--git-dir=<dir>` before the verb for block_unlinked_commit_author: the three guards that now ask the walk too. Before #381462dc each was admitted.

Then the plants. Taking the scope call out of a guard flips its ADMITTED rows to refused, so they are admitted BY the scope; taking the walk call out flips the WALK rows to admitted; and taking the common-dir comparison out of `_repo_scope.elsewhere` flips the `-C` rows of this checkout and the submodule to admitted, so those are refused BY that comparison and not by a parse doubt on the way. The helper rows drive `git_targets` and `elsewhere` in process, both directions.
"""

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
SCOPE = HERE / "_repo_scope.py"
ROOT = str(HERE.parents[2])

_SYSPATH = importlib.util.spec_from_file_location("_rediacc_syspath", HOOKS / "syspath.py")
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: .claude/rediacc_hooks/syspath.py is missing" % __file__)
syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(syspath)
syspath.on_sys_path(syspath.CLAUDE_DIR)
scope = importlib.import_module("rediacc_hooks.guards._repo_scope")

failures: list[str] = []
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
ENV["CLAUDE_PROJECT_DIR"] = ROOT

SCRATCH = tempfile.mkdtemp(prefix="repo-scope-")
atexit.register(shutil.rmtree, SCRATCH, True)
WORK = os.path.join(SCRATCH, "work")
NEW = os.path.join(SCRATCH, "new")
LINK = os.path.join(SCRATCH, "link")
SUB = os.path.join(ROOT, "private", "renet")
# A tree holding an independent repository of its own (as a gitignored sibling under private/ does): built in the scratch dir, never in this checkout.
NEST_ROOT = os.path.join(SCRATCH, "nest-root")
NESTED = os.path.join(NEST_ROOT, "private", "sibling")


def _git(*args):
    subprocess.run(["git", *args], check=True, capture_output=True, env=ENV)


_git("init", "-q", "--bare", os.path.join(SCRATCH, "remote.git"))
_git("init", "-q", WORK)
_git("init", "-q", NEST_ROOT)
_git("init", "-q", NESTED)
_git("-C", WORK, "remote", "add", "origin", os.path.join(SCRATCH, "remote.git"))
for i in range(30):
    pathlib.Path(WORK, "f%d.txt" % i).write_text("a\n", encoding="utf-8")
# Committed, then changed and staged: block_unproven_bulk_transform judging this repository (its scope planted out) counts only paths with a change against HEAD, and needs 30 of them.
_git("-C", WORK, "add", "-A")
_git("-C", WORK, "-c", "user.email=s@s", "-c", "user.name=s", "commit", "-q", "-m", "seed")
for i in range(30):
    pathlib.Path(WORK, "f%d.txt" % i).write_text("b\n", encoding="utf-8")
_git("-C", WORK, "add", "-A")
os.symlink(ROOT, LINK)
if not os.path.exists(os.path.join(SUB, ".git")):
    failures.append("setup: private/renet is not checked out")
    print("*** FAIL *** %s is not a checked-out submodule; the submodule rows judge nothing" % SUB)

MANY = " ".join("f%d.txt" % i for i in range(30))

# stem -> (global options before the verb, the verb and its words, row families it takes). block_unproven_bulk_transform judges this checkout's index, whose size is the live tree's state, so its OURS rows would assert nothing stable; its own suite carries them.
GUARDS = {
    "block_git_empty_commit": ("", "commit --allow-empty -m x", "ADOWX"),
    "block_unlinked_commit_author": ("-c user.email=t@t ", "commit -m x -- f0.txt", "ADOGX"),
    "block_blanket_git_add": ("", "add -A", "ADO"),
    "block_pathspecless_git_commit": ("", "commit -m x", "ADO"),
    "block_unproven_bulk_transform": ("", "commit -m x -- " + MANY, "A"),
    "block_git_amend": ("", "commit --amend -m x -- f0.txt", "W"),
}


def rows_for(stem):
    pre, verb, families = GUARDS[stem]
    out: list[tuple[str, str, str, str | None]] = []
    if "A" in families:
        out += [
            ("ADMITTED", "scratch by -C", "git -C %s %s%s" % (WORK, pre, verb), ROOT),
            ("ADMITTED", "scratch by the event cwd", "git %s%s" % (pre, verb), WORK),
            ("ADMITTED", "scratch by cd", "cd %s && git %s%s" % (WORK, pre, verb), ROOT),
            (
                "ADMITTED",
                "scratch the command creates",
                "git init -q %s && cd %s && git %s%s" % (NEW, NEW, pre, verb),
                ROOT,
            ),
        ]
    if "D" in families:
        out += [
            ("DOUBT", "GIT_DIR on the run", "GIT_DIR=%s/.git git %s%s" % (WORK, pre, verb), WORK),
            ("DOUBT", "a global option but -C/-c", "git --no-pager %s%s" % (pre, verb), WORK),
            (
                "DOUBT",
                "an alias elsewhere on the line",
                "git -c alias.st=status st; git %s%s" % (pre, verb),
                WORK,
            ),
            ("DOUBT", "a relative event cwd", "git %s%s" % (pre, verb), "work"),
            ("DOUBT", "no event cwd", "git %s%s" % (pre, verb), None),
            ("DOUBT", "a -C directory in a variable", 'git -C "$D" %s%s' % (pre, verb), ROOT),
            ("DOUBT", "a -C directory under ~", "git -C ~/nowhere %s%s" % (pre, verb), ROOT),
        ]
    if "O" in families:
        out += [
            ("OURS", "this checkout by the event cwd", "git %s%s" % (pre, verb), ROOT),
            ("OURS", "this checkout by -C", "git -C %s %s%s" % (ROOT, pre, verb), "/"),
            ("OURS", "a submodule by -C", "git -C %s %s%s" % (SUB, pre, verb), "/"),
        ]
        # block_pathspecless_git_commit admits any `git -C /tmp/...` by its text marker, a limit its header states; the symlink sits under the temp directory.
        if stem != "block_pathspecless_git_commit":
            out.append(
                (
                    "OURS",
                    "this checkout through a symlink",
                    "git -C %s %s%s" % (LINK, pre, verb),
                    "/",
                )
            )
    if "W" in families:
        out += [
            ("WALK", "-C this checkout", "git -C %s %s%s" % (ROOT, pre, verb), "/"),
            ("WALK", "-c before the verb", "git -c a.b=c %s%s" % (pre, verb), ROOT),
            (
                "WALK",
                "an alias for commit",
                "git -c alias.ci=commit %s%s" % (pre, verb.replace("commit", "ci", 1)),
                ROOT,
            ),
        ]
    if "X" in families:
        # Admitted before #381462dc: block_git_empty_commit's text match never saw the `-C` spelling, and block_unlinked_commit_author let a `-C` outside the root through by its path. block_blanket_git_add still admits these by `target_root`'s path arm, which is outside this change.
        out += [
            (
                "DOUBT",
                "GIT_DIR naming this checkout, -C scratch",
                "GIT_DIR=%s/.git git -C %s %s%s" % (ROOT, WORK, pre, verb),
                "/",
            ),
            (
                "DOUBT",
                "--git-dir naming this checkout",
                "git -C %s --git-dir=%s/.git %s%s" % (WORK, ROOT, pre, verb),
                "/",
            ),
        ]
    if "G" in families:
        # COMMIT_AT_COMMAND_POS read a global option as `-x [value]`, so `--git-dir=<dir>` ended the match and the commit was not a commit at all; the walk placed it, and since #f2e3507a the pattern also takes an attached `=value`. Two lines hold the row, so its plant (WALK_OFF) takes out both.
        out.append(
            (
                "WALK",
                "--git-dir= before the verb",
                "git -C %s --git-dir=%s/.git %s%s" % (WORK, ROOT, pre, verb),
                "/",
            )
        )
    return out


def _payload(command, cwd):
    event = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        event["cwd"] = cwd
    return json.dumps(event)


# A planted copy of the guard, and optionally of `_repo_scope`, through the guard's own `run`. The shared module is put in place under its real name before the guard's source runs, so the guard's own `from rediacc_hooks.guards import _repo_scope` picks up the planted copy.
BROKEN_RUNNER = (
    "import sys, types; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "import rediacc_hooks.guards as pkg\n"
    "def planted(path, pairs):\n"
    "    src = open(path, encoding='utf-8').read()\n"
    "    for old, new in pairs:\n"
    "        assert src.count(old) == 1, 'the plant no longer applies: %%r' %% old\n"
    "        src = src.replace(old, new)\n"
    "    return src\n"
    "scope_pairs = %r\n"
    "if scope_pairs:\n"
    "    mod = types.ModuleType('rediacc_hooks.guards._repo_scope')\n"
    "    mod.__file__ = %r\n"
    "    exec(compile(planted(%r, scope_pairs), 'scope', 'exec'), mod.__dict__)\n"
    "    sys.modules['rediacc_hooks.guards._repo_scope'] = mod\n"
    "    pkg._repo_scope = mod\n"
    "ns = {'__name__': 'broken', '__file__': %r}\n"
    "exec(compile(planted(%r, %r), 'broken', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)


def run_guard(stem, command, cwd, guard_pairs=None, scope_pairs=None):
    if guard_pairs is None and scope_pairs is None:
        argv = [sys.executable, DISPATCH, stem]
    else:
        path = str(HERE / ("%s.py" % stem))
        code = BROKEN_RUNNER % (
            str(HOOKS.parent),
            list(scope_pairs or []),
            str(SCOPE),
            str(SCOPE),
            path,
            path,
            list(guard_pairs or []),
        )
        argv = [sys.executable, "-c", code]
    proc = subprocess.run(
        argv,
        input=_payload(command, cwd),
        capture_output=True,
        text=True,
        check=False,
        env=ENV,
        cwd=ROOT,
    )
    if proc.returncode not in (0, 2):
        print("*** CRASH *** rc=%d %r\n%s" % (proc.returncode, command, proc.stderr[-800:]))
        failures.append("crash: %s %s" % (stem, command))
    return proc.returncode, proc.stderr


def show(cwd):
    if cwd is None:
        return "(none)"
    return cwd.replace(SCRATCH, "$S").replace(ROOT, "$ROOT")


WANT_BLOCKED = {"ADMITTED": False, "DOUBT": True, "OURS": True, "WALK": True}
total = 0
for stem in GUARDS:
    rows = rows_for(stem)
    print("== %s (%d rows)" % (stem, len(rows)))
    for family, name, command, cwd in rows:
        total += 1
        want = WANT_BLOCKED[family]
        rc, err = run_guard(stem, command, cwd)
        got = rc == 2
        fine = got == want
        print(
            "  %-8s %-34s cwd=%-7s want=%-7s got=%-7s %s"
            % (
                family,
                name[:34],
                show(cwd)[:7],
                "BLOCKED" if want else "allowed",
                "BLOCKED" if got else "allowed",
                "ok" if fine else "*** FAIL ***",
            )
        )
        if not fine:
            failures.append("%s: %s %s" % (stem, family, name))
            print("    command: %r\n    stderr: %s" % (command, err.strip()[:300]))

# THE PLANTS. Each must flip every row it names, or the rows are not held by the line it plants on.
SCOPE_OFF = [("_repo_scope.elsewhere(", "False and _repo_scope.elsewhere(")]
# Both scope checks come out together: the in-tree check (any target inside this tree is ours) and the common-dir comparison (a repository sharing this checkout's common dir is ours). Either alone still refuses this checkout and the submodule, so the plant must take both to flip those rows.
COMPARE_OFF = [
    (
        "if commit_policy.is_inside(target, root):",
        "if False and commit_policy.is_inside(target, root):",
    ),
    (
        "if common and (not ours or commit_policy.is_inside(common, ours)):",
        "if common and not ours:",
    ),
]
WALK_OFF = {
    "block_git_empty_commit": [
        ('_repo_scope.walked_commit_flag(cmd, "allow-empty")', "False"),
    ],
    "block_git_amend": [('_repo_scope.walked_commit_flag(cmd, "amend", adjacent=False)', "False")],
    "block_unlinked_commit_author": [
        ('or commit_policy.git_runs(cmd, "commit")', "or False"),
        ("(=[^ ;&|]*|[{S}]+[^ ;&|]+)?)*[{S}]+commit", "([{S}]+[^ ;&|]+)?)*[{S}]+commit"),
    ],
}
# The ADMITTED rows each guard admits ONLY through the scope: block_blanket_git_add and block_unproven_bulk_transform still admit a `-C`/`cd` outside this tree by `target_root`, and block_pathspecless_git_commit admits `-C /tmp/...`, `cd /tmp/...` and a line with `git init` by its text markers, so for those three only the event `cwd` row is the scope's alone.
SCOPE_ONLY = {
    "block_blanket_git_add": ("scratch by the event cwd",),
    "block_unproven_bulk_transform": ("scratch by the event cwd",),
    "block_pathspecless_git_commit": ("scratch by the event cwd",),
}
plants = 0
for stem in GUARDS:
    rows = rows_for(stem)
    picks = [
        ("the scope call taken out", SCOPE_OFF, None, "ADMITTED", SCOPE_ONLY.get(stem), 2),
        ("the walk taken out", WALK_OFF.get(stem), None, "WALK", None, 0),
        (
            "the common-dir comparison taken out",
            None,
            COMPARE_OFF,
            "OURS",
            ("this checkout by -C", "a submodule by -C"),
            0,
        ),
    ]
    for label, guard_pairs, scope_pairs, family, names, want_rc in picks:
        chosen = [r for r in rows if r[0] == family and (names is None or r[1] in names)]
        if not chosen or (guard_pairs is None and scope_pairs is None):
            continue
        plants += 1
        flipped = [
            r[1]
            for r in chosen
            if run_guard(stem, r[2], r[3], guard_pairs, scope_pairs)[0] == want_rc
        ]
        if len(flipped) != len(chosen):
            failures.append("plant: %s, %s" % (stem, label))
            print(
                "*** FAIL *** %s with %s: %d of %d rows flipped (unflipped: %s)"
                % (
                    stem,
                    label,
                    len(flipped),
                    len(chosen),
                    ", ".join(r[1] for r in chosen if r[1] not in flipped),
                )
            )
        else:
            print("%s with %s: all %d rows flipped" % (stem, label, len(chosen)))

# THE HELPER, in process, both directions.
everything = scope.verb_is("commit")
helper = [
    (
        "a literal -C resolves",
        scope.git_targets("git -C %s commit -m x" % WORK, None, everything, 0) == [WORK],
    ),
    (
        "the event cwd resolves a bare run",
        scope.git_targets("git commit -m x", WORK, everything, 0) == [WORK],
    ),
    (
        "a relative -C needs an absolute cwd",
        scope.git_targets("git -C work commit -m x", None, everything, 0) is None,
    ),
    (
        "a relative -C composes on the cwd",
        scope.git_targets("git -C work commit -m x", SCRATCH, everything, 0) == [WORK],
    ),
    (
        "more text matches than runs is a doubt",
        scope.git_targets("git -C %s commit -m x" % WORK, None, everything, 2) is None,
    ),
    ("no judged run is a doubt", scope.git_targets("git status", WORK, everything, 0) is None),
    (
        "a missing directory is a doubt",
        scope.git_targets("git -C %s/absent commit" % SCRATCH, None, everything, 0) is None,
    ),
    (
        "an identity variable is no doubt",
        scope.git_targets("GIT_AUTHOR_EMAIL=a@b git commit -m x", WORK, everything, 0) == [WORK],
    ),
    (
        "GIT_INDEX_FILE on the run is a doubt",
        scope.git_targets("GIT_INDEX_FILE=i git commit -m x", WORK, everything, 0) is None,
    ),
    ("a scratch repository is elsewhere", scope.elsewhere("git commit", WORK, ROOT, everything, 0)),
    ("this checkout is not", not scope.elsewhere("git commit", ROOT, ROOT, everything, 0)),
    ("a submodule is not", not scope.elsewhere("git commit", SUB, ROOT, everything, 0)),
    (
        "a non-repository outside this tree is elsewhere",
        scope.elsewhere("git commit", SCRATCH, ROOT, everything, 0),
    ),
    ("no root is never elsewhere", not scope.elsewhere("git commit", WORK, "", everything, 0)),
    (
        "an independent repository nested inside the tree is not elsewhere",
        not scope.elsewhere("git commit", NESTED, NEST_ROOT, everything, 0),
    ),
    (
        "the walk reads -C",
        scope.walked_commit_flag("git -C x commit --allow-empty -m y", "allow-empty"),
    ),
    (
        "the walk reads a message as a value",
        not scope.walked_commit_flag("git commit -m --allow-empty", "allow-empty"),
    ),
    (
        "adjacent=False passes over the adjacent spelling",
        not scope.walked_commit_flag("git commit --amend", "amend", adjacent=False),
    ),
    (
        "adjacent=False still reads -C",
        scope.walked_commit_flag("git -C x commit --amend", "amend", adjacent=False),
    ),
    (
        "allow-empty-message is another option",
        not scope.walked_commit_flag("git commit --allow-empty-message -m ''", "allow-empty"),
    ),
]
for name, held in helper:
    print("  helper   %-50s %s" % (name, "ok" if held else "*** FAIL ***"))
    if not held:
        failures.append("helper: %s" % name)

if failures:
    print("\n%d FAILED: %s" % (len(failures), "; ".join(failures[:25])))
    sys.exit(1)
print(
    "\nOK: %d dispatcher rows over %d guards, %d plants held, %d helper rows"
    % (total, len(GUARDS), plants, len(helper))
)
