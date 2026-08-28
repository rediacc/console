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


REAL = os.environ.get("PATH", "")
WITH_SHIM = f"{shim}:{REAL}"

# Does a devbox exist? The refusal arm requires one; without it the guard
# correctly downgrades to a note, and asserting exit 2 would be asserting the
# wrong thing on a machine with no container.
have_box = (
    subprocess.run(
        ["docker", "ps", "--filter", "label=com.rediacc.devbox.worktree", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    != ""
)

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

shutil.rmtree(shim, ignore_errors=True)

bad = 0
for want, got, label in cases:
    if want != got:
        bad += 1
        print(f"  FAIL [{want}] {label} (got {got})")
print(f"FAILURES: {bad}  ({len(cases)} case(s), devbox_present={have_box})")
sys.exit(1 if bad else 0)
