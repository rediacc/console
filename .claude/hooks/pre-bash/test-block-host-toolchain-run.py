#!/usr/bin/env python3
"""block-host-toolchain-run.sh: both directions.

The interesting half is the ALLOW half. A guard that pushes every `npm run` into
a container would be routed around within a day: most gates are node and
TypeScript, run identically on the host, and are faster there. This one fires
only when the named gate needs a binary THIS host lacks.

PATH is manipulated per case rather than mocked, so "the host lacks it" is a
fact the guard establishes with `command -v`, exactly as it does in the wild.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "block-host-toolchain-run.sh")
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

# A PATH with the real tools plus a shim dir we control.
shim = tempfile.mkdtemp()


def fake(name):
    p = os.path.join(shim, name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("#!/bin/sh\nexit 0\n")
    # 0o700, not 0o755: the shim only has to be executable by THIS process,
    # and mkdtemp() already made the parent owner-only, so the group/other
    # bits were unreachable decoration.
    os.chmod(p, 0o700)


def run(cmd, path=None):
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        ["bash", GUARD],
        input=json.dumps({"tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    ).returncode


def run_full(cmd, path=None):
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        ["bash", GUARD],
        input=json.dumps({"tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


REAL = os.environ.get("PATH", "")
WITH_SHIM = f"{shim}:{REAL}"

# Does a devbox exist? The refusal arm requires one; without it the guard
# correctly downgrades to a note, and asserting exit 2 would be asserting the
# wrong thing on a machine with no container.
box_name = subprocess.run(
    ["docker", "ps", "--filter", "label=com.rediacc.devbox.worktree", "--format", "{{.Names}}"],
    capture_output=True,
    text=True,
    check=False,
).stdout.strip()
have_box = box_name != ""

cases = []

# --- ALLOW: the half that decides whether this guard survives ---------------
cases.append(
    (0, run("npm run check:ci-parity"), "CONTROL: a gate needing no extra toolchain is untouched")
)
cases.append((0, run("npm run build:packages"), "CONTROL: an ordinary npm script is untouched"))
cases.append((0, run("git status"), "CONTROL: a non-npm command is out of scope"))
cases.append(
    (
        0,
        run("./run.sh devbox exec -- npm run check:ci-python-lint"),
        "CONTROL: already routed through the devbox is out of scope",
    )
)
cases.append(
    (
        0,
        run("echo 'run npm run check:ci-renet in the box'"),
        "CONTROL: prose about the command is not the command",
    )
)

# The host HAS the tool -> never route. Proven by shimming one onto PATH.
fake("ruff")
cases.append(
    (
        0,
        run("npm run check:ci-python-lint", WITH_SHIM),
        "CONTROL: host HAS ruff, so the guard leaves it alone",
    )
)

# A GATE THAT PROVISIONS ITS OWN PINNED TOOL MUST NEVER BE ROUTED.
# Three of the table's original six entries were this mistake, so it is pinned
# rather than remembered. These run with the REAL host PATH: if either tool is
# absent here (it is, on this host) the old table refused the command outright,
# while the gate itself acquires its pin and passes.
cases.extend(
    (
        0,
        run(f"npm run {gate}", REAL),
        f"CONTROL: {gate} self-provisions its pin, so it is never routed",
    )
    for gate in ("check:ci-shell-lint", "check:ci-shell-format", "check:ci-actionlint")
)

# --- REFUSE: only when the host lacks it and the box has it -----------------
if have_box:
    # Strip the shim so ruff is absent again; the real host has no ruff.
    if shutil.which("ruff", path=REAL) is None:
        cases.append(
            (
                2,
                run("npm run check:ci-python-lint", REAL),
                "host lacks ruff and the devbox has it -> REFUSED with the devbox form",
            )
        )
    else:
        cases.append(
            (
                0,
                run("npm run check:ci-python-lint", REAL),
                "CONTROL: this host actually has ruff, so no routing is correct",
            )
        )
else:
    cases.append(
        (
            0,
            run("npm run check:ci-python-lint", REAL),
            "CONTROL: no devbox running, so the guard notes rather than blocks",
        )
    )

# --- BARE TOOL: the same class, for a directly-typed command ----------------
# The NEEDS table above matches a GATE KEY string in the command
# (`check:ci-python-lint`); it is blind to `go build ./...`, which names no gate
# at all. BARE_TOOLS exists to catch exactly that shape.
# Constructed rather than ambient: whether THIS host happens to have `go` on PATH
# must not decide which branch of the guard gets exercised. Strip every PATH entry
# that actually resolves `go`, so the REFUSE branch runs deterministically instead
# of silently degrading to a no-op CONTROL assertion on a host that has go (which
# is exactly what happened the first time this case was written: it passed while
# testing nothing, because `go` was on this host's PATH the whole time).
NOGO = os.pathsep.join(
    d for d in REAL.split(os.pathsep) if not os.path.isfile(os.path.join(d, "go"))
)
if have_box:
    r = run_full("go build ./...", NOGO)
    cases.append((2, r.returncode, "bare 'go', host lacks it, devbox has it -> REFUSED"))
    cases.append(
        (
            True,
            "this command needs 'go'" in r.stderr and "gate 'go' needs" not in r.stderr,
            "bare-tool message reads 'this command needs', not 'gate <tool> needs'",
        )
    )
    cases.append(
        (
            True,
            "npm run go" not in r.stderr,
            "bare-tool routing never suggests the nonsensical 'npm run go'",
        )
    )
    cases.append((0, run("go build ./...", REAL), "CONTROL: with go restored to PATH, no routing"))
else:
    cases.append(
        (0, run("go build ./...", NOGO), "CONTROL: no devbox running, bare tool notes not blocks")
    )

# Prose mentioning a tracked tool name must never be mistaken for running it.
cases.append(
    (
        0,
        run('git commit -m "install ruff and go before running this"', REAL),
        "CONTROL: prose naming tool words is not a command",
    )
)

# --- NPX MISUSE: fires on shape, independent of host tool state -------------
# npx resolves its argument as an npm package name; none of ruff/go/shfmt/
# shellcheck/actionlint are npm packages, so this fails whether or not the
# tool is on PATH. Measured 2026-08-28: this exact shape, with ruff genuinely
# present on PATH the whole time.
cases.append(
    (2, run("npx --yes ruff format file.py", REAL), "npx cannot run a pinned non-npm tool")
)
cases.append((2, run("npx -y shfmt -l .", REAL), "npx misuse, short flag form"))
cases.append(
    (0, run("npx --yes tsx scripts/foo.ts", REAL), "CONTROL: npx running a real npm package")
)

# ---------------------------------------------------------------------------
# Submodule / non-submodule split, and the credential file. Both added 2026-08-28
# after each failed for real.
#
# The property that decides routing is NOT "is this a submodule". It is whether the
# target owns a HOST-BUILT toolchain. private/renet is a submodule with neither a
# .venv nor node_modules, so it routes like the root repo. private/account is a
# submodule WITH node_modules, and private/growth/video_pipeline is not a submodule
# at all but carries its own .venv; neither can run in the container. Routing
# video_pipeline into the devbox produced ModuleNotFoundError: anyio.
# THE ROOT-REPO EXPECTATION IS DERIVED, NEVER HARDCODED. This case asserted a
# literal 2 for private/renet and went red on 2026-08-28 the moment `ruff` was
# installed on this host -- the guard then correctly declined to route, exactly
# as its own comment says it should ("THE HOST IS ASKED, NOT ASSUMED").
#
# The property under test is the one the section header states: a submodule with
# no host toolchain routes LIKE THE ROOT REPO. So compare it to the root repo's
# verdict rather than to a constant, which holds in both worlds and keeps the
# case meaningful on a machine that has ruff and on one that does not.
#
# SAME CLASS AS wl_git.py's force-push probe trio, found the same day: a control
# whose expectation was pinned to ambient machine state (there, a branch name
# from an earlier wave). Neither went green and lied -- both went RED for a
# reason unrelated to what they assert, which is worse, because a red nobody can
# explain is a red everybody learns to ignore.
_root_like = 2 if (have_box and shutil.which("ruff", path=REAL) is None) else 0
if have_box:
    for path, want, why in (
        ("private/growth/video_pipeline", 0, "a pipeline with its own .venv must NOT be routed"),
        ("private/account", 0, "a submodule with host-built node_modules must NOT be routed"),
        (
            "private/renet",
            _root_like,
            "a submodule with no host toolchain routes like the root repo (expected %d here)"
            % _root_like,
        ),
    ):
        if not os.path.exists(os.path.join(REPO, path)):
            continue
        cases.append((want, run(f"npm run check:ci-python-lint --prefix {path}", REAL), why))

# A command that uploads to R2 without sourcing private/account/.env does not fail,
# it half-succeeds: 52 files copied locally, 0 uploaded, exit 0, and a closing warning
# that named the wrong cause. Only assert this when the credential file is present,
# since the guard is deliberately silent without it.
if os.path.exists(os.path.join(REPO, "private/account/.env")):
    cases.append(
        (
            2,
            run("./run.sh --publish-www --langs en", REAL),
            "publish-www without sourcing private/account/.env is refused",
        )
    )
    cases.append(
        (
            0,
            run("set -a; . private/account/.env; set +a; ./run.sh --publish-www --langs en", REAL),
            "CONTROL: sourcing it in the same command is accepted",
        )
    )
    cases.append(
        (
            0,
            run("R2_MEDIA_ACCESS_KEY_ID=x ./run.sh --publish-www --langs en", REAL),
            "CONTROL: setting the credential inline states the intent, so it is accepted",
        )
    )

# ---------------------------------------------------------------------------
# EVERY TOOL IN THE ARRAY, NOT JUST TWO OF FIVE. check-host-toolchain-coverage.sh
# proves NPX_TOOLS/BARE_TOOLS LIST the same tools GATED_TOOLS pins; it says
# nothing about whether the ROUTING REGEX actually FIRES for each of them at
# runtime. A tool could sit in the array and still be unreachable -- a name
# containing a regex metacharacter, a word-boundary edge case on a two-letter
# name like `go` -- and list-membership coverage would not catch it. Before
# this, npx-misuse was exercised for ruff and shfmt only, and bare-tool routing
# for ruff and go only: 2 of 5 tools on each path, with shellcheck, actionlint
# (both paths) and go/shfmt (npx path) never actually invoked.
#
# PATH is constructed per tool, never trusted to ambient host state: this host
# happens to lack shfmt/shellcheck/actionlint and have ruff/go, and a case
# written against today's ambient mix silently stops testing the branch it
# names the moment the host's toolset changes.
ALL_TOOLS = ["ruff", "go", "shfmt", "shellcheck", "actionlint"]


def _path_without(tool, base):
    """base's PATH entries, minus any that resolve `tool`."""
    return os.pathsep.join(
        d for d in base.split(os.pathsep) if not os.path.isfile(os.path.join(d, tool))
    )


for tool in ALL_TOOLS:
    # npx-misuse: fires on SHAPE alone, so REAL PATH is the right environment --
    # it must refuse whether or not the tool happens to be installed.
    cases.append(
        (
            2,
            run(f"npx --yes {tool} --version", REAL),
            f"npx-misuse: {tool} refused regardless of host state",
        )
    )

    if not have_box:
        continue
    # Bare-tool routing, host lacks it, devbox has it: constructed absence, not
    # assumed. `fake()` proves the opposite direction: with the tool shimmed
    # onto PATH, the same command must NOT be routed.
    #
    # DEVBOX PRESENCE IS CHECKED, NOT ASSUMED, per tool. actionlint is
    # DELIBERATELY absent from the baked image (its own gate downloads a
    # pinned, checksum-verified release on demand -- see this guard's own
    # comment on why it is not in NEEDS either), so on a host that also lacks
    # it the guard correctly NOTES rather than blocks: there is nowhere to
    # route TO. Hardcoding "devbox has it" for every tool would have made this
    # case assert the wrong exit code for exactly the one tool the image
    # intentionally does not carry.
    tool_in_box = (
        subprocess.run(
            ["docker", "exec", "-u", "vscode", box_name, "bash", "-lc", f"command -v {tool}"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )
    without = _path_without(tool, REAL)
    want = 2 if tool_in_box else 0
    label = (
        f"bare-tool: {tool} routed when constructed-absent from PATH"
        if tool_in_box
        else f"bare-tool: {tool} absent from host AND devbox -> notes, does not route"
    )
    cases.append((want, run(f"{tool} --version", without), label))
    fake(tool)
    with_shim = f"{shim}:{REAL}"
    cases.append(
        (0, run(f"{tool} --version", with_shim), f"CONTROL: {tool} present on PATH is left alone")
    )

shutil.rmtree(shim, ignore_errors=True)

bad = 0
for want, got, label in cases:
    if want != got:
        bad += 1
        print(f"  FAIL [{want}] {label} (got {got})")
print(f"FAILURES: {bad}  ({len(cases)} case(s), devbox_present={have_box})")
sys.exit(1 if bad else 0)
