#!/usr/bin/env python3
"""Control harness for block_second_open_pr: WHICH repository's open PRs a `gh pr create` is counted against (worklist #29531257).

THE LIVE CASE, 2026-11-11, console PR 605 open on 1104-1: `for s in renet account elite; do (cd private/$s && gh pr create ...); done`, run from the console, was refused as a second open PR in rediacc/console. The guard read the repository from the SESSION cwd's origin whenever the `cd` did not literally name `private/<submodule>`, so a create in any other directory was counted against the console. The repository is now read as gh reads it: `--repo`/`-R`/`GH_REPO`, else the directory the call really runs in after its `cd`s, else the session cwd; a `cd` target the walk cannot expand is refused as unverifiable, never guessed as the console.

REAL REPOSITORIES under a `rediacc_ci.runtmp` run directory: a console checkout whose origin is rediacc/console, a `private/renet` checkout whose origin is rediacc/renet, and a checkout outside `private/` whose origin is rediacc/elite. `gh` is stubbed on PATH: it answers `gh pr list --repo <r>` with one open PR for rediacc/console, and none (or, in the second stub, one on another branch) for renet and elite.

BOTH DIRECTIONS. The submodule creates are admitted; a second console PR, a submodule that already has an open PR, and a `cd` into a missing directory (the shell stays in the console) are refused.
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
STEM = "block_second_open_pr"

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", HERE.parents[2] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/runtmp.py is missing" % __file__)
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-second-open-pr-")

# The well-known repo slugs and origin, read from .ci/config/well-known.env by the CI reader, loaded by file like runtmp above (check:ci-literal-sources forbids spelling them).
_WK = importlib.util.spec_from_file_location(
    "well_known_for_second_open_pr", HERE.parents[2] / ".ci" / "rediacc_ci" / "well_known.py"
)
if _WK is None or _WK.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/well_known.py is missing" % __file__)
well_known = importlib.util.module_from_spec(_WK)
_WK.loader.exec_module(well_known)
GH_ORIGIN, GH_REPO = well_known.GH_ORIGIN, well_known.GH_REPO
RENET_REPO, ELITE_REPO = well_known.RENET_REPO, well_known.ELITE_REPO

_GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")


def checkout(path, origin):
    path = pathlib.Path(path)
    path.mkdir(parents=True)
    for argv in (
        ["init", "-q", "--initial-branch=main"],
        ["remote", "add", "origin", "%s/%s.git" % (GH_ORIGIN, origin)],
    ):
        subprocess.run(["git", *argv], cwd=path, check=True, capture_output=True, env=_GIT_ENV)
    return path


ROOT = checkout(pathlib.Path(tempfile.mkdtemp(prefix="console-", dir=RUN_TMP)) / "console", GH_REPO)
checkout(ROOT / "private" / "renet", RENET_REPO)
OTHER = checkout(ROOT / "work" / "elite-co", ELITE_REPO)

_OPEN = '[{"number":%d,"title":"t","headRefName":"%s","isDraft":true}]'
_STUB = (
    "#!/bin/sh\n"
    'repo=""\n'
    'while [ $# -gt 0 ]; do [ "$1" = --repo ] && repo="$2"; shift; done\n'
    'case "$repo" in\n'
    "  %s) echo '%s' ;;\n"
    "  %s) echo '%s' ;;\n"
    "  *) echo '[]' ;;\n"
    "esac\n"
)


def stub(body):
    d = pathlib.Path(tempfile.mkdtemp(prefix="stub-", dir=RUN_TMP))
    (d / "gh").write_text(body, encoding="utf-8")
    (d / "gh").chmod(0o755)
    return str(d)


GH_CONSOLE_OPEN = stub(_STUB % (GH_REPO, _OPEN % (605, "1104-1"), RENET_REPO, "[]"))
GH_RENET_OPEN = stub(_STUB % (GH_REPO, _OPEN % (605, "1104-1"), RENET_REPO, _OPEN % (77, "1031-2")))
GH_DOWN = stub("#!/bin/sh\necho 'gh: could not connect'\nexit 1\n")

CREATE = "gh pr create --draft --base main --head 1104-1 -t x -b y"
ALREADY = "already have 1 open PR(s) in %s"
UNVERIFIED = "cannot verify"

CASES = [
    # (name, command, gh, expect_blocked, stderr needle)
    (
        "cd <abs>/private/renet && create",
        "cd %s && %s" % (ROOT / "private" / "renet", CREATE),
        GH_CONSOLE_OPEN,
        False,
        "",
    ),
    ("cd private/renet && create", "cd private/renet && " + CREATE, GH_CONSOLE_OPEN, False, ""),
    (
        "cd into a checkout outside private/ is judged against ITS origin",
        "cd work/elite-co && " + CREATE,
        GH_CONSOLE_OPEN,
        False,
        "",
    ),
    (
        "a subshell cd into that checkout too",
        "(cd %s && %s)" % (OTHER, CREATE),
        GH_CONSOLE_OPEN,
        False,
        "",
    ),
    ("--repo names the submodule", CREATE + " --repo " + RENET_REPO, GH_CONSOLE_OPEN, False, ""),
    ("-R names the submodule", CREATE + " -R " + RENET_REPO, GH_CONSOLE_OPEN, False, ""),
    (
        "--repo beats the cd",
        "cd private/renet && %s --repo %s" % (CREATE, GH_REPO),
        GH_CONSOLE_OPEN,
        True,
        ALREADY % GH_REPO,
    ),
    # The live 2026-11-11 shape: the directory is a loop variable, so the repo is unknown, never the console.
    (
        "the live loop: cd private/$s",
        "for s in renet account elite; do (cd private/$s && %s); done" % CREATE,
        GH_CONSOLE_OPEN,
        True,
        "cd private/$s",
    ),
    # 3e82900b.2: `cd -` returns to a directory the walk never saw, so it is unverifiable, not the session repo.
    (
        "cd - is a directory the hook cannot evaluate",
        "cd -; " + CREATE,
        GH_CONSOLE_OPEN,
        True,
        "cd -",
    ),
    # ---- controls
    (
        "a second console PR from the console",
        CREATE,
        GH_CONSOLE_OPEN,
        True,
        ALREADY % GH_REPO,
    ),
    (
        "a submodule that already has an open PR on another branch",
        "cd private/renet && " + CREATE,
        GH_RENET_OPEN,
        True,
        ALREADY % RENET_REPO,
    ),
    (
        "a cd into a missing directory leaves the shell in the console",
        "cd private/missing; " + CREATE,
        GH_CONSOLE_OPEN,
        True,
        ALREADY % GH_REPO,
    ),
    ("gh down fails closed", "cd private/renet && " + CREATE, GH_DOWN, True, UNVERIFIED),
]


def run(command, gh):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(ROOT), PATH="%s:%s" % (gh, os.environ["PATH"]))
    env.pop("GH_REPO", None)
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(ROOT)}
    )
    proc = subprocess.run(
        [sys.executable, DISPATCH, STEM],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if proc.returncode not in (0, 2):
        raise SystemExit("guard crashed (rc %d): %s" % (proc.returncode, proc.stderr[-800:]))
    return proc.returncode == 2, proc.stderr


fails = 0
blocked = 0
for name, command, gh, want, needle in CASES:
    got, err = run(command, gh)
    blocked += got
    ok = got == want and (not needle or needle in err)
    fails += not ok
    print(
        "%-64s want=%-8s got=%-8s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok:
        print("    needle %r; stderr: %s" % (needle, err.strip().splitlines()[:4]))

if blocked in (0, len(CASES)):
    print("*** FAIL *** the guard answered the same way on every case")
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
