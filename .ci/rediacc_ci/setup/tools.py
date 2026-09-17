#!/usr/bin/env python3
"""THE INSTALL TABLE: every tool this repository needs, in one place, as data.

WHAT IT REPLACES. Today the answer to "what does a machine need before the gates can run" is spread across six files that agree with none of the others, and each of them enumerates a DIFFERENT subset. Read on 2026-09-06, with the line each row below cites as its provenance:

  .ci/lib/setup.sh:249            setup_system_tools   cc, make, jq
  .ci/lib/local-common.sh:587     ensure_host_tools    jq, zstd, curl, git, cc
  .ci/bootstrap.sh                the Python pair      uv, pytest
  .ci/scripts/lib/toolchain.sh    toolchain_acquire    shfmt, shellcheck
  .ci/lib/setup.sh:40, :330       node and go          node, go
  .devcontainer/Dockerfile        the image            the union, in apt syntax

None of those six is wrong. The problem is that a tool can be REQUIRED by a gate and named in none of them, which is invisible by construction: nothing compares the list of things that get installed against the list of things that get used. The gate half of this module (`audit`, below) is that comparison, and it is why this is a Python module with a verdict rather than a Markdown
table.

--------------------------------------------------------------------------
WHY THE pytest ROW IS THE POINT OF THIS FILE
--------------------------------------------------------------------------
`docs/ci-overhaul/08-driver-contract.md` section 5d records the gap in the programme's own words: the drafted enumeration for this table covered

    cc make jq python3 git curl zstd tmux xz node go gh docker
    ruff shfmt shellcheck actionlint uv gitleaks bws PyYAML

and carried NO pytest row, while W1, W5 and W7 each make a Python test runner the PRIMARY local proof of their port. A table that installs everything except the thing the ports are judged by describes an environment that cannot run the test gate. pytest is provisioned by the uv shim (`.ci/bootstrap.sh install`), it is pinned at `PYTEST_VERSION` in `.devcontainer/toolchain.env`, and
`.ci/rediacc_ci/check_pytest.py` is the gate that runs on it.

So the pytest row is here, and assertion A6 below names it EXPLICITLY rather than letting it be covered by the general "every pinned tool has a row" rule. A6 is redundant with A2 the day it is written, and that is deliberate: A2 would go quiet if `pytest` ever left `toolchain.TOOL_KEYS`, and the gap the contract recorded would reopen with no gate noticing. A named control cannot go
quiet.

--------------------------------------------------------------------------
WHY EVERY ROW MUST HAVE A DARWIN ANSWER (assertion A4)
--------------------------------------------------------------------------
This module ships in the same wave as four macOS defects found in `.ci/scripts/lib/`, all four of which had the same root: a file that a developer is told to run locally, written as though Linux were the only host. A4 refuses a row that names an apt package and nothing a Mac can act on, because a table with a hole on one platform is how the next one of those gets written.

`repo` is a legitimate darwin answer: it means "a script in this repository installs it at the pin, on every platform it supports" (that is what `.ci/bootstrap.sh` does for uv and pytest and what `toolchain_acquire` does for shfmt and shellcheck). It is not an excuse arm -- `.ci/scripts/lib/toolchain.sh` refuses on a Mac today for shfmt, loudly, because only the LINUX checksum
constants exist, and that refusal is recorded in the row's own note.

--------------------------------------------------------------------------
WHAT THIS MODULE DELIBERATELY DOES NOT DO
--------------------------------------------------------------------------
IT NEVER RUNS AN INSTALLER. It prints one. Every install line here needs root or mutates a developer's machine, and a gate that can `sudo apt-get install` as a side effect of being run is a gate nobody can run. `./run.sh setup` remains the
thing that acts; this is the thing that KNOWS, and the separation is the same one
`.ci/scripts/lib/toolchain.sh` already draws between `toolchain_check` (answers) and `toolchain_acquire` (gets).

IT DOES NOT OWN A VERSION. Every pin lives in `.devcontainer/toolchain.env` and is reached through `rediacc_ci.core.toolchain`. A row names a KEY, never a value, so this file cannot become a second place a version is written down. A3 asserts every key a row names actually exists in the pins file, which is what makes the indirection checkable rather than decorative.

--------------------------------------------------------------------------
COMMAND LINE
--------------------------------------------------------------------------
    .ci/rediacc_ci/setup/tools.py --selftest
        the both-direction controls over the audit, on synthetic tables, printed
        one line each. Exits non-zero if any control cannot fire.

    .ci/rediacc_ci/setup/tools.py
        the audit. Exit 0 clean, 1 with findings, 77 cannot-run. THE SAME
        CONTROLS RUN FIRST, quietly, on this path too -- see `main` for why that
        is not optional here.

    .ci/rediacc_ci/setup/tools.py --report
        what THIS host has, next to what the table says it needs. Reports; it is
        not a verdict and it does not gate.

    .ci/rediacc_ci/setup/tools.py --install-plan [<manager>]
        the paste-able install commands for one package manager, defaulting to
        the one detected on this host.

EXIT 77 IS CANNOT-RUN AND IS NEVER A VERDICT. It is returned for exactly one condition: the repository root could not be resolved, so the pins corpus that every corpus-derived floor here is keyed on cannot be read at all. That is a harness fault, not a finding about the tree, and reporting it as 1 would put a green-able number on a run that scanned nothing.

---- gate ---- id: check:ci-install-table step: Install table needs: none selftest: true why: six bash enumerations answered "what a machine needs" and none compared the set installed against the set used, so a pinned tool could be required by a gate and named nowhere -- which is how the drafted table came to carry no pytest row
     (Only the FIRST line of `why:` reaches the parser, measured against
     check_allowlist_key_matching.py which behaves the same way, so the line
     above is written to stand alone. The rest is for a reader of this file.
     driver contract section 5d records the pytest omission; assertion A6 below
     is the control that stops it reopening quietly.)
---- end gate ----
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import platform as _platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

# THE HOP, WRITTEN BY HAND EXACTLY ONCE, and copied deliberately from `.ci/rediacc_ci/check_pytest.py:88` rather than invented: this file is both a module and a SCRIPT, and as a script it cannot import the module that would put its own package on sys.path until its package is on sys.path. `parents[2]` is `.ci`, one level deeper than check_pytest's `parents[1]` because this file
# sits in a subpackage. Everything after this line goes through rediacc_ci.paths.
#
# The alternative is registering the gate as `python3 -m rediacc_ci.setup.tools` in package.json, and `scripts/lib/gate-header.ts` records why that is wrong: a `python3` prefix makes check:ci-parity resolve the entry's leaves to `[python3]`, so the manifest would then claim the interpreter as the gate's file and a change to this one would select nothing.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rediacc_ci import paths
from rediacc_ci.controls import Controls
from rediacc_ci.core import toolchain

# The twin's exit statuses. 77 is CANNOT RUN and is never a verdict; see the
# module docstring for the single condition that returns it.
EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_CANNOT_RUN = 77

# The package managers a row may name, in the order `detect_manager` prefers them. `repo` is last because it is not a system manager at all: it means a script in THIS repository installs the tool at the pin, which is the strongest answer available and therefore the one that must not shadow a host's own.
LINUX_MANAGERS = ("apt", "dnf", "pacman", "apk")
DARWIN_MANAGERS = ("brew",)
REPO_MANAGER = "repo"
ALL_MANAGERS = (*LINUX_MANAGERS, *DARWIN_MANAGERS, REPO_MANAGER)


@dataclass(frozen=True)
class Tool:
    """One row of the install table.

    `pin_key` NAMES A KEY, NEVER A VALUE. See the module docstring: a value here would make this the second place a version is written down, and the whole reason `.devcontainer/toolchain.env` exists is that there used to be three.

    `install` maps a manager name to the command a human pastes. It is prose, not something this module executes, so it may carry a `sudo` and a `&&`.

    `provenance` is `file:line` for where this row's knowledge lived before this table existed, or the file that owns it now. It is checked for shape by A7
    rather than for truth, which is the honest limit of a mechanical check; a
    reviewer confirms the lines, and the audit's job is to stop a row appearing
    with no citation at all.
    """

    name: str
    purpose: str
    pin_key: str | None
    install: dict[str, str]
    provenance: str
    probe: tuple[str, ...] | None = None
    note: str = ""
    # A python DISTRIBUTION rather than an executable on PATH. PyYAML is the only
    # one today; it is pinned, it is needed by gates that parse workflow YAML, and
    # `shutil.which("PyYAML")` will never find it. Flagged so `--report` asks the interpreter instead of PATH, and so A4/A5 still apply to it.
    python_dist: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


# --------------------------------------------------------------------------- THE TABLE ---------------------------------------------------------------------------
#
# ORDER IS THE DEPENDENCY ORDER a fresh machine needs, not alphabetical: the compiler and jq come before node, node comes before anything reached through npm, and the Python pair comes last because uv provisions pytest. A reader following it top to bottom is following `./run.sh setup`.
TOOLS: tuple[Tool, ...] = (
    Tool(
        name="cc",
        purpose=(
            "npm run install:natives runs node-gyp for cpu-features; without a "
            "compiler it dies with 'Unable to detect compiler type', which names "
            "neither the package nor the command that needed it"
        ),
        pin_key=None,
        install={
            "apt": "sudo apt-get update && sudo apt-get install -y build-essential",
            "dnf": "sudo dnf groupinstall -y 'Development Tools'",
            "pacman": "sudo pacman -S --noconfirm base-devel",
            "apk": "sudo apk add build-base",
            "brew": "xcode-select --install",
        },
        provenance=".ci/lib/setup.sh:249 setup_system_tools",
        probe=("cc", "--version"),
        aliases=("gcc", "clang"),
        note=(
            "xcode-select, not brew: Apple ships the compiler in the Command Line "
            "Tools and brew has no formula for it. setup.sh:266 already prints "
            "exactly this line on Darwin."
        ),
    ),
    Tool(
        name="make",
        purpose="node-gyp drives it for every native rebuild",
        pin_key=None,
        install={
            "apt": "sudo apt-get update && sudo apt-get install -y build-essential",
            "dnf": "sudo dnf groupinstall -y 'Development Tools'",
            "pacman": "sudo pacman -S --noconfirm base-devel",
            "apk": "sudo apk add build-base",
            "brew": "xcode-select --install",
        },
        provenance=".ci/lib/setup.sh:251 setup_system_tools",
        probe=("make", "--version"),
    ),
    Tool(
        name="jq",
        purpose="EVERY PreToolUse hook in .claude/hooks parses its input with it",
        pin_key=None,
        install={
            "apt": "sudo apt-get update && sudo apt-get install -y jq",
            "dnf": "sudo dnf install -y jq",
            "pacman": "sudo pacman -S --noconfirm jq",
            "apk": "sudo apk add jq",
            "brew": "brew install jq",
        },
        provenance=".ci/lib/setup.sh:252 setup_system_tools",
        probe=("jq", "--version"),
        note=(
            "setup.sh:267 spells out why this is a SEPARATE brew line on Darwin: "
            "xcode-select does NOT provide jq, and a reader who runs only the "
            "compiler line is left with hooks that cannot parse their own input."
        ),
    ),
    Tool(
        name="python3",
        purpose=(
            "the language half the gates are being ported into; also node-gyp's "
            "own runtime dependency"
        ),
        pin_key=None,
        install={
            "apt": "sudo apt-get update && sudo apt-get install -y python3",
            "dnf": "sudo dnf install -y python3",
            "pacman": "sudo pacman -S --noconfirm python",
            "apk": "sudo apk add python3",
            "brew": "brew install python@3.13",
        },
        provenance=".ci/lib/setup.sh:273 install_cmd, and .ci/bootstrap.sh's own probe",
        probe=("python3", "--version"),
        note=(
            "NOT PINNED, on purpose. Every other language runtime here carries a "
            "pin because CI installs it; python3 is taken from the host and the "
            "package targets py312 (pyproject.toml target-version). A pin would "
            "have to be enforced by something, and nothing installs python3."
        ),
    ),
    Tool(
        name="git",
        purpose=(
            "the enumeration substrate: most gates find their subjects with "
            "git ls-files, and the shadow ledger keys a tree by HEAD^{tree}"
        ),
        pin_key=None,
        install={
            "apt": "sudo apt-get update && sudo apt-get install -y git",
            "dnf": "sudo dnf install -y git",
            "pacman": "sudo pacman -S --noconfirm git",
            "apk": "sudo apk add git",
            "brew": "brew install git",
        },
        provenance=".ci/lib/local-common.sh:590 ensure_host_tools",
        probe=("git", "--version"),
    ),
    Tool(
        name="curl",
        purpose="every pinned-tool download and every R2 probe goes through it",
        pin_key=None,
        install={
            "apt": "sudo apt-get update && sudo apt-get install -y curl",
            "dnf": "sudo dnf install -y curl",
            "pacman": "sudo pacman -S --noconfirm curl",
            "apk": "sudo apk add curl",
            "brew": "brew install curl",
        },
        provenance=".ci/lib/local-common.sh:590 ensure_host_tools",
        probe=("curl", "--version"),
        note="macOS ships curl, so the brew line is an upgrade rather than an install.",
    ),
    Tool(
        name="zstd",
        purpose=(
            "the renet embed-asset cache is zstd-compressed; "
            "extract-renet-from-image.sh:95 require_cmd zstd"
        ),
        pin_key=None,
        install={
            "apt": "sudo apt-get update && sudo apt-get install -y zstd",
            "dnf": "sudo dnf install -y zstd",
            "pacman": "sudo pacman -S --noconfirm zstd",
            "apk": "sudo apk add zstd",
            "brew": "brew install zstd",
        },
        provenance=".ci/lib/local-common.sh:590 ensure_host_tools",
        probe=("zstd", "--version"),
    ),
    Tool(
        name="tmux",
        purpose="the devbox browser terminal is ttyd attached to a tmux session",
        pin_key=None,
        install={
            "apt": "sudo apt-get update && sudo apt-get install -y tmux",
            "dnf": "sudo dnf install -y tmux",
            "pacman": "sudo pacman -S --noconfirm tmux",
            "apk": "sudo apk add tmux",
            "brew": "brew install tmux",
        },
        provenance=".ci/lib/devbox.sh:608",
        probe=("tmux", "-V"),
        note=(
            "Needed INSIDE the devbox container, not on the host. Kept in the "
            "table because the same table describes both, and a row that is "
            "container-only is still a row somebody has to be able to find."
        ),
    ),
    Tool(
        name="xz",
        purpose=(
            "shellcheck publishes its Linux builds as .tar.xz only, and nothing "
            "else in this repo depends on xz -- so its absence surfaces as "
            "'tar: unrecognized option J', which names neither xz nor shellcheck"
        ),
        pin_key=None,
        install={
            "apt": "sudo apt-get update && sudo apt-get install -y xz-utils",
            "dnf": "sudo dnf install -y xz",
            "pacman": "sudo pacman -S --noconfirm xz",
            "apk": "sudo apk add xz",
            "brew": "brew install xz",
        },
        provenance=".ci/scripts/lib/toolchain.sh:415 _toolchain_acquire_shellcheck",
        probe=("xz", "--version"),
    ),
    Tool(
        name="node",
        purpose="the runtime for every TypeScript gate and the whole npm surface",
        pin_key="NODE_VERSION",
        install={
            "apt": "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs",
            "dnf": "sudo dnf module install -y nodejs:22",
            "pacman": "sudo pacman -S --noconfirm nodejs npm",
            "apk": "sudo apk add nodejs npm",
            "brew": "brew install node@22",
            "repo": "./run.sh setup   # setup_node_toolchain installs the pinned tarball",
        },
        provenance=".ci/lib/setup.sh:40 setup_node_toolchain",
        probe=("node", "--version"),
        note=(
            "TWO NUMBERS, ONE TOOL. NODE_VERSION is the bare major CI installs; "
            "NODE_VERSION_MIN is the floor every consumer COMPARES against and "
            "nothing installs. This row names the installed one. The floor is W0's "
            "and is not restated here -- toolchain.node_floor() is how a caller "
            "asks for it."
        ),
    ),
    Tool(
        name="go",
        purpose="renet is Go, and shfmt is acquired through `go install` when Go is present",
        pin_key="GO_VERSION",
        install={
            "apt": "sudo apt-get update && sudo apt-get install -y golang-go",
            "dnf": "sudo dnf install -y golang",
            "pacman": "sudo pacman -S --noconfirm go",
            "apk": "sudo apk add go",
            "brew": "brew install go",
            "repo": "./run.sh setup   # setup_go_toolchain installs the pinned tarball",
        },
        provenance=".ci/lib/setup.sh:330 setup_go_toolchain",
        probe=("go", "version"),
        note=(
            "renet keeps its own go.mod, under private/renet, and it carries a "
            "toolchain directive of its own. These are "
            "deliberately separate numbers: go.mod pins what renet is COMPILED "
            "WITH, GO_VERSION pins what the image SHIPS."
        ),
    ),
    Tool(
        name="gh",
        purpose="CI triage, workflow dispatch, and every PR-shaped gate",
        pin_key=None,
        install={
            "apt": "sudo apt-get update && sudo apt-get install -y gh",
            "dnf": "sudo dnf install -y gh",
            "pacman": "sudo pacman -S --noconfirm github-cli",
            "apk": "sudo apk add github-cli",
            "brew": "brew install gh",
        },
        provenance=".ci/lib/setup.sh:497 and :543",
        probe=("gh", "--version"),
    ),
    Tool(
        name="docker",
        purpose="the devbox, the traefik router, and every repository deployment",
        pin_key=None,
        install={
            "apt": "curl -fsSL https://get.docker.com | sudo sh",
            "dnf": "curl -fsSL https://get.docker.com | sudo sh",
            "pacman": "sudo pacman -S --noconfirm docker",
            "apk": "sudo apk add docker",
            "brew": "brew install --cask docker",
        },
        provenance="./run.sh setup, docker step",
        probe=("docker", "--version"),
        note=(
            "The docker GROUP gap closes itself; see "
            "docs/agent-reference/local-env.md rather than adding a usermod line "
            "here. This row is about the binary."
        ),
    ),
    Tool(
        name="ruff",
        purpose="the Python lint and format gate",
        pin_key="RUFF_VERSION",
        install={
            "apt": "uv tool install ruff==$(rediacc_ci.core.toolchain pin ruff)",
            "dnf": "uv tool install ruff==$(rediacc_ci.core.toolchain pin ruff)",
            "pacman": "sudo pacman -S --noconfirm ruff",
            "apk": "uv tool install ruff==$(rediacc_ci.core.toolchain pin ruff)",
            "brew": "brew install ruff",
            "repo": "check-python-lint.sh's npx-at-the-pin fallback",
        },
        provenance=".devcontainer/toolchain.env RUFF_VERSION, check-python-lint.sh",
        probe=("ruff", "--version"),
        note=(
            "A PATH ruff is used ONLY if its version equals the pin; that rule is "
            "toolchain_check's and is the reason a stale 0.9 on a developer's host "
            "cannot silently decide a verdict."
        ),
    ),
    Tool(
        name="shfmt",
        purpose="the shell format gate",
        pin_key="SHFMT_VERSION",
        install={
            "apt": "sudo apt-get update && sudo apt-get install -y shfmt",
            "dnf": "sudo dnf install -y shfmt",
            "pacman": "sudo pacman -S --noconfirm shfmt",
            "apk": "sudo apk add shfmt",
            "brew": "brew install shfmt",
            "repo": "toolchain_acquire shfmt   # go install at the pin, or a checksummed download",
        },
        provenance=".ci/scripts/lib/toolchain.sh:355 _toolchain_acquire_shfmt",
        probe=("shfmt", "--version"),
        note=(
            "THE repo ARM REFUSES ON DARWIN TODAY, loudly, and that refusal is "
            "correct rather than a gap in this row: only SHFMT_SHA256_LINUX_* "
            "exists in .ci/config/constants.sh, and toolchain.sh:334 names the "
            "constant to add instead of downloading unverified. The brew arm is "
            "what a Mac uses until those two constants land."
        ),
    ),
    Tool(
        name="shellcheck",
        purpose="the shell lint gate",
        pin_key="SHELLCHECK_VERSION",
        install={
            "apt": "sudo apt-get update && sudo apt-get install -y shellcheck",
            "dnf": "sudo dnf install -y ShellCheck",
            "pacman": "sudo pacman -S --noconfirm shellcheck",
            "apk": "sudo apk add shellcheck",
            "brew": "brew install shellcheck",
            "repo": "toolchain_acquire shellcheck   # checksummed .tar.xz download at the pin",
        },
        provenance=".ci/scripts/lib/toolchain.sh:382 _toolchain_acquire_shellcheck",
        probe=("shellcheck", "--version"),
        note=(
            "shellcheck DOES publish darwin builds, so the repo arm needs only the "
            "two SHELLCHECK_SHA256_DARWIN_* constants to work on a Mac; the URL at "
            "toolchain.sh:422 already asks for the right asset."
        ),
    ),
    Tool(
        name="actionlint",
        purpose="the workflow lint gate",
        pin_key="ACTIONLINT_VERSION",
        install={
            "apt": "go install github.com/rhysd/actionlint/cmd/actionlint@v$(...)",
            "dnf": "go install github.com/rhysd/actionlint/cmd/actionlint@v$(...)",
            "pacman": "sudo pacman -S --noconfirm actionlint",
            "apk": "go install github.com/rhysd/actionlint/cmd/actionlint@v$(...)",
            "brew": "brew install actionlint",
            "repo": ".ci/scripts/security/actionlint.sh   # the original per-tool acquirer",
        },
        provenance=".ci/scripts/security/actionlint.sh, which toolchain.sh generalises",
        probe=("actionlint", "--version"),
    ),
    Tool(
        name="uv",
        purpose="the Python package manager, and the only thing that can provision pytest here",
        pin_key="UV_VERSION",
        install={
            "apt": ".ci/bootstrap.sh install",
            "dnf": ".ci/bootstrap.sh install",
            "pacman": ".ci/bootstrap.sh install",
            "apk": ".ci/bootstrap.sh install",
            "brew": ".ci/bootstrap.sh install   # or: brew install uv",
            "repo": ".ci/bootstrap.sh install   # checksummed download into .ci/cache/toolchain",
        },
        provenance=".ci/bootstrap.sh install_uv, and .devcontainer/toolchain.env UV_VERSION",
        probe=("uv", "--version"),
        note=(
            "ALL FOUR PLATFORM CHECKSUMS ARE RECORDED (UV_SHA256_{LINUX,DARWIN}_"
            "{X86_64,AARCH64}), so the repo arm genuinely works on a Mac. That is "
            "the difference between this row and the shfmt one, and it is why the "
            "shfmt row says so out loud instead of implying parity."
        ),
    ),
    Tool(
        name="pytest",
        purpose=(
            "THE test runner. check_pytest.py is the gate that runs the rediacc_ci "
            "suite, and W1, W5 and W7 each make it the primary local proof of "
            "their port"
        ),
        pin_key="PYTEST_VERSION",
        install={
            "apt": ".ci/bootstrap.sh install",
            "dnf": ".ci/bootstrap.sh install",
            "pacman": ".ci/bootstrap.sh install",
            "apk": ".ci/bootstrap.sh install",
            "brew": ".ci/bootstrap.sh install",
            "repo": ".ci/bootstrap.sh install   # uv tool install pytest==<pin>",
        },
        provenance=".ci/bootstrap.sh install_pytest, and .devcontainer/toolchain.env PYTEST_VERSION",
        probe=("pytest", "--version"),
        note=(
            "THE ROW THE DRAFTED ENUMERATION OMITTED. driver contract 5d records "
            "the gap; assertion A6 names this row explicitly so the gap cannot "
            "reopen quietly. There is deliberately no pip or pipx arm: measured on "
            "the host these gates run on, pip AND pipx are both absent, so every "
            "'just pip install it' instruction is a dead end here and writing one "
            "down would be worse than writing nothing."
        ),
    ),
    Tool(
        name="pytest-xdist",
        purpose=(
            "the parallel scheduler check:ci-pytest runs the suite under. Without "
            "it `-n` is an unknown option, the gate exits 4, and the whole suite "
            "reports as a usage error rather than as a missing plugin"
        ),
        pin_key="PYTEST_XDIST_VERSION",
        install={
            "apt": ".ci/bootstrap.sh install",
            "dnf": ".ci/bootstrap.sh install",
            "pacman": ".ci/bootstrap.sh install",
            "apk": ".ci/bootstrap.sh install",
            "brew": ".ci/bootstrap.sh install",
            "repo": ".ci/bootstrap.sh install   # uv tool install --with pytest-xdist==<pin>",
        },
        provenance=(
            ".ci/bootstrap.sh install_xdist, and .devcontainer/toolchain.env PYTEST_XDIST_VERSION"
        ),
        probe=None,
        python_dist="xdist",
        note=(
            "DELIBERATELY ABSENT FROM toolchain.TOOL_KEYS, and A2's second loop is "
            "what permits that: a row may name a pin_key that is in the pins file "
            "without being in TOOL_KEYS. TOOL_KEYS is compared arm-for-arm against "
            "the bash `toolchain_pin_for` case, and every arm there resolves a "
            "BINARY; xdist is a plugin living inside pytest's own environment with "
            "nothing on PATH, so an arm for it would pin a tool no lane can exec. "
            "A DISTRIBUTION, like PyYAML, so --report asks the interpreter -- and "
            "it will read ABSENT on this host, correctly: it is importable from "
            "the uv tool venv .ci/bootstrap.sh built, not from the system python3. "
            "`.ci/bootstrap.sh --check` is the thing that owns that resolution and "
            "it carries its own xdist row."
        ),
    ),
    Tool(
        name="gitleaks",
        purpose="the tracked-credentials scan",
        pin_key=None,
        install={
            "apt": "go install github.com/gitleaks/gitleaks/v8@latest",
            "dnf": "go install github.com/gitleaks/gitleaks/v8@latest",
            "pacman": "sudo pacman -S --noconfirm gitleaks",
            "apk": "go install github.com/gitleaks/gitleaks/v8@latest",
            "brew": "brew install gitleaks",
        },
        provenance="the secret-scanning lane; not pinned in toolchain.env today",
        probe=("gitleaks", "version"),
        note=(
            "NOT PINNED, AND THAT IS A REPORTED GAP RATHER THAN A DECISION. Every "
            "other scanner a gate shells out to carries a key in toolchain.env; "
            "this one does not, so two lanes can disagree about what a leak is. "
            "Adding GITLEAKS_VERSION is a toolchain.env write, which the driver "
            "contract sequences to W0 and W6, not to this row."
        ),
    ),
    Tool(
        name="bws",
        purpose="the Bitwarden Secrets CLI, used to seed and rotate CI secrets",
        pin_key=None,
        install={
            "apt": "cargo install bws   # or the release tarball from bitwarden/sdk",
            "dnf": "cargo install bws",
            "pacman": "cargo install bws",
            "apk": "cargo install bws",
            "brew": "brew install bitwarden/tap/bws",
        },
        provenance=".ci/config/bws-secret-map.json and the bws-secrets composite action",
        probe=("bws", "--version"),
        note=(
            "OPERATOR-ONLY IN PRACTICE: it needs a machine token, so it is absent "
            "on every ordinary developer host and is not a setup failure there. "
            "--report prints it as ABSENT and that is not a finding."
        ),
    ),
    Tool(
        name="PyYAML",
        purpose="the workflow-parsing gates read .github/workflows/*.yml with it",
        pin_key="PYYAML_VERSION",
        install={
            "apt": "uv pip install PyYAML==<pin>",
            "dnf": "uv pip install PyYAML==<pin>",
            "pacman": "sudo pacman -S --noconfirm python-yaml",
            "apk": "uv pip install PyYAML==<pin>",
            "brew": "uv pip install PyYAML==<pin>",
            "repo": ".ci/bootstrap.sh install   # arrives with the uv environment",
        },
        provenance=".devcontainer/toolchain.env PYYAML_VERSION",
        probe=None,
        python_dist="yaml",
        note=(
            "A DISTRIBUTION, NOT A COMMAND. shutil.which('PyYAML') can never "
            "succeed, so --report asks the interpreter for the `yaml` module "
            "instead. Flagged in the row rather than special-cased by name in the "
            "reporter, so a second Python dependency needs no new code."
        ),
    ),
)


# --------------------------------------------------------------------------- Host questions ---------------------------------------------------------------------------


def detect_manager() -> str:
    """The package manager THIS host offers, or "" when none is recognised.

    Darwin is answered before the Linux managers because a Mac with Homebrew's coreutils on PATH can satisfy neither test cleanly, and the OS is the more reliable signal than the presence of a binary.
    """
    if _platform.system() == "Darwin":
        return "brew" if shutil.which("brew") else ""
    for manager in LINUX_MANAGERS:
        probe = "apt-get" if manager == "apt" else manager
        if shutil.which(probe):
            return manager
    return ""


def _python_dist_present(module: str) -> bool:
    """Is an importable module present, without importing it into this process?

    A subprocess rather than `importlib.util.find_spec`, because the question is about the interpreter a GATE will run under, and this process may have been started with a different sys.path by a harness.
    """
    try:
        completed = subprocess.run(
            [sys.executable, "-c", "import %s" % module],
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def present(tool: Tool) -> str | None:
    """Where `tool` is on this host, or None. Never raises.

    Returns a PATH for an executable and the literal "(importable)" for a Python distribution, because a distribution has no single path a reader can act on and printing site-packages would be noise.
    """
    if tool.python_dist:
        return "(importable)" if _python_dist_present(tool.python_dist) else None
    found = shutil.which(tool.name)
    if found:
        return found
    for alias in tool.aliases:
        found = shutil.which(alias)
        if found:
            return found
    return None


def probe_version(tool: Tool) -> str | None:
    """The normalised version string `tool` reports, or None.

    None covers three DIFFERENT situations on purpose -- no probe defined, the binary is absent, the binary printed nothing a version could be read from -- because this function feeds a REPORT and not a verdict. `toolchain_check` is the thing that rules on a version, and it distinguishes all three.
    """
    if tool.probe is None:
        return None
    if shutil.which(tool.probe[0]) is None:
        return None
    try:
        completed = subprocess.run(
            list(tool.probe),
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in (completed.stdout + "\n" + completed.stderr).splitlines():
        for word in line.split():
            # TWO ATTEMPTS PER WORD, and the second is not padding. The ported `normalize_version` strips exactly the prefixes the bash strips (`v` then `go`), because it is a differential twin and must not invent a third. But `jq --version` prints `jq-1.8.1`, so a name-dash-version word yields nothing from it. Splitting on the LAST dash and retrying keeps this reporter useful
            # without widening the twin's contract, which is the thing that must stay pinned.
            for candidate in (word, word.rsplit("-", 1)[-1]):
                try:
                    return toolchain.normalize_version(candidate)
                except toolchain.VersionError:
                    continue
    return None


# --------------------------------------------------------------------------- The audit: the part that has a verdict ---------------------------------------------------------------------------


def audit(
    table: tuple[Tool, ...] = TOOLS,
    pins: dict[str, str] | None = None,
    tool_keys: dict[str, str] | None = None,
) -> list[str]:
    """Every finding about the TABLE, as actionable lines. Empty means clean.

    `table`, `pins` and `tool_keys` are parameters rather than globals so the selftest can drive both directions on synthetic inputs without touching the tree. That is the whole reason this function takes arguments.

    THE FLOORS ARE CORPUS-DERIVED, never hand-typed (driver contract section 6). There are two corpora and neither is a number in this file:

      * `tool_keys` -- `toolchain.TOOL_KEYS`, the tool-to-pin mapping the bash
        `toolchain_pin_for` case is checked against. A2 requires a row for each.
      * `pins` -- the parsed `.devcontainer/toolchain.env`. A3 requires every
        `pin_key` a row names to exist in it.

    A ZERO-ROW TABLE IS A FINDING AND NOT A PASS. A0 says so first, before any other assertion runs, because every rule below is a `for row in table` and an empty table satisfies all of them at once.
    """
    pin_table = toolchain.load_pins() if pins is None else pins
    keys = dict(toolchain.TOOL_KEYS) if tool_keys is None else tool_keys
    findings: list[str] = []

    # -- A0. Anti-vacuity, first, on both corpora. ---------------------------
    if not table:
        findings.append(
            "A0. the install table is EMPTY. Every assertion below iterates it, so "
            "an empty table would satisfy all of them and this gate's green would "
            "mean nothing."
        )
        return findings
    if not keys:
        findings.append(
            "A0. the pinned-tool corpus (toolchain.TOOL_KEYS) is EMPTY, so A2 "
            "cannot compare anything. Fix rediacc_ci.core.toolchain before reading "
            "any verdict from here."
        )
        return findings
    if not pin_table:
        findings.append(
            "A0. the pins file parsed to ZERO pairs, so A3 cannot check a single "
            "key. See .devcontainer/toolchain.env."
        )
        return findings

    by_name = {row.name: row for row in table}

    # -- A1. One row per tool. ----------------------------------------------- A duplicate name is not cosmetic: `by_name` silently keeps the LAST, so the earlier row's installers become unreachable while still reading as present.
    seen: set[str] = set()
    for row in table:
        if row.name in seen:
            findings.append(
                "A1. %s appears twice in the table. The later row wins silently, "
                "so the earlier one's install lines are dead text." % row.name
            )
        seen.add(row.name)

    # -- A2. Every PINNED tool has a row, in both directions. ----------------
    for tool_name, key in sorted(keys.items()):
        row = by_name.get(tool_name)
        if row is None:
            findings.append(
                "A2. %s is pinned at %s but has NO row in the install table, so "
                "nothing here says how a machine gets it. Add a row; do not drop "
                "the pin." % (tool_name, key)
            )
        elif row.pin_key != key:
            findings.append(
                "A2. %s names pin_key %r but toolchain.TOOL_KEYS says %r. One of "
                "the two is reading a version nobody sets." % (tool_name, row.pin_key, key)
            )
    for row in table:
        if row.pin_key is not None and row.name in keys and keys[row.name] != row.pin_key:
            continue
        if row.pin_key is not None and row.name not in keys and row.pin_key not in pin_table:
            findings.append(
                "A2. %s names pin_key %s, which is neither in toolchain.TOOL_KEYS "
                "nor in the pins file. A row cannot pin a key that does not exist."
                % (row.name, row.pin_key)
            )

    # -- A3. Every named key really exists in the pins file. -----------------
    findings.extend(
        "A3. %s names pin_key %s, which .devcontainer/toolchain.env does not "
        "define. The indirection is the point of pin_key; a key that resolves to "
        "nothing makes it decorative." % (row.name, row.pin_key)
        for row in table
        if row.pin_key is not None and row.pin_key not in pin_table
    )

    # -- A4. Every row has a DARWIN answer. ----------------------------------
    findings.extend(
        "A4. %s has no darwin answer (needs a `brew` or `repo` entry). A table "
        "with a hole on one platform is how the macOS defects this wave fixed got "
        "written." % row.name
        for row in table
        if not any(m in row.install for m in (*DARWIN_MANAGERS, REPO_MANAGER))
    )

    # -- A5. Every row has a LINUX answer. -----------------------------------
    findings.extend(
        "A5. %s names no Linux package manager and no repo script, so on the "
        "platform CI actually runs there is no way to obtain it." % row.name
        for row in table
        if not any(m in row.install for m in (*LINUX_MANAGERS, REPO_MANAGER))
    )

    # -- A6. THE pytest ROW, BY NAME. ---------------------------------------- Redundant with A2 today, and deliberately so: see the module docstring. A2
    # goes quiet if pytest ever leaves TOOL_KEYS; this does not.
    pytest_row = by_name.get("pytest")
    if pytest_row is None:
        findings.append(
            "A6. THERE IS NO pytest ROW. driver contract 5d records this exact "
            "omission: the table's drafted enumeration listed twenty-one tools and "
            "no test runner, while three workstreams make pytest the primary local "
            "proof of their port. A table without it describes an environment that "
            "cannot run check:ci-pytest."
        )
    else:
        if pytest_row.pin_key != "PYTEST_VERSION":
            findings.append(
                "A6. the pytest row names pin_key %r, not PYTEST_VERSION. W1 phase "
                "1 already pinned it; W6 adopts that pin rather than inventing one."
                % pytest_row.pin_key
            )
        if REPO_MANAGER not in pytest_row.install:
            findings.append(
                "A6. the pytest row has no `repo` install arm. pytest comes from "
                "the uv shim (.ci/bootstrap.sh install); a host-manager-only answer "
                "is a dead end on the machine measured 2026-09-06, where pip and "
                "pipx are both absent."
            )

    # -- A7. Every row cites where its knowledge came from. ------------------ Shape only, and the limit is stated rather than hidden: this cannot tell a true citation from a plausible one. It exists to stop a row appearing with no citation at all, which is the difference between prose a reviewer can check and prose nobody can.
    for row in table:
        if not row.provenance.strip():
            findings.append(
                "A7. %s carries no provenance. Name the file (and line, where "
                "there is one) this row's knowledge was read from, so the next "
                "reader can confirm it rather than trust it." % row.name
            )
        if not row.purpose.strip():
            findings.append(
                "A7. %s carries no purpose. A row that does not say what needs the "
                "tool is a row nobody can ever delete." % row.name
            )

    # -- A8. Every manager named is one of the known ones. -------------------
    findings.extend(
        "A8. %s names manager %r, which is not in ALL_MANAGERS. A typo'd key is "
        "silently unreachable by --install-plan." % (row.name, manager)
        for row in table
        for manager in sorted(row.install)
        if manager not in ALL_MANAGERS
    )

    return findings


# --------------------------------------------------------------------------- Reporting ---------------------------------------------------------------------------


def report(table: tuple[Tool, ...] = TOOLS) -> int:
    """Print what this host has beside what the table says it needs. Always 0.

    NOT A VERDICT, and it returns 0 even when everything is missing. A developer
    on a fresh machine runs this to find out what to do; making it red would give
    a number to a question that has not been asked yet. `audit` is the verdict.
    """
    manager = detect_manager()
    print(
        "host: %s %s   manager: %s"
        % (_platform.system(), _platform.machine(), manager or "(none detected)")
    )
    print()
    print("  %-12s %-9s %-12s %s" % ("tool", "pinned", "found", "where"))
    missing = 0
    for row in table:
        pinned = "-"
        if row.pin_key is not None:
            try:
                pinned = toolchain.pin(row.pin_key)
            except toolchain.PinError:
                pinned = "UNPINNED"
        where = present(row)
        version = probe_version(row) or "-"
        if where is None:
            missing += 1
        print("  %-12s %-9s %-12s %s" % (row.name, pinned, version, where or "ABSENT"))
    print()
    print("%d row(s), %d absent on this host" % (len(table), missing))
    # ABSENT HERE MEANS "NOT ON PATH", AND FOR THE repo ROWS THAT IS NOT THE SAME AS UNAVAILABLE. `.ci/bootstrap.sh` installs uv and pytest into `.ci/cache/toolchain/`, and `toolchain_acquire` puts shfmt and shellcheck in a cache directory too, so all four can be ABSENT above while `npm run check:ci-pytest` runs perfectly. This module deliberately does not reimplement those
    # resolvers to find out: a second copy of the resolution logic is exactly the drift this table exists to end. It names the thing that DOES know instead.
    repo_rows = [row.name for row in table if REPO_MANAGER in row.install]
    print(
        "note: %d row(s) are repo-provisioned (%s) and resolve from a cache "
        "rather than PATH. Ask `.ci/bootstrap.sh --check` and "
        "`.ci/scripts/lib/toolchain.sh --report`, which own that resolution."
        % (len(repo_rows), ", ".join(repo_rows))
    )
    return 0


def install_plan(manager: str, table: tuple[Tool, ...] = TOOLS) -> int:
    """Print the paste-able commands for one manager. Non-zero on an unknown one.

    ONLY THE ABSENT ROWS, because a plan that re-installs what is already at the pin is a plan nobody runs twice.
    """
    if manager not in ALL_MANAGERS:
        print(
            "tools: %r is not a known manager. Known: %s" % (manager, ", ".join(ALL_MANAGERS)),
            file=sys.stderr,
        )
        return EXIT_FINDINGS
    printed = 0
    for row in table:
        if present(row) is not None:
            continue
        command = row.install.get(manager) or row.install.get(REPO_MANAGER)
        if command is None:
            print("# %s: no %s arm and no repo arm -- see the row's note" % (row.name, manager))
            continue
        print("%s   # %s" % (command, row.name))
        printed += 1
    if printed == 0:
        print("# nothing to install: every row in the table is already present")
    return EXIT_OK


# --------------------------------------------------------------------------- Selftest: both directions, before any real scan ---------------------------------------------------------------------------


def _row(**kwargs: object) -> Tool:
    """A minimal valid row, so a control can break exactly one field.

    Written as a helper rather than repeated per control because a control that accidentally breaks TWO fields at once still fires, and then proves nothing about the assertion it was named after.
    """
    base: dict[str, object] = {
        "name": "widget",
        "purpose": "a purpose",
        "pin_key": None,
        "install": {"apt": "apt install widget", "brew": "brew install widget"},
        "provenance": "somewhere.sh:1",
    }
    base.update(kwargs)
    return Tool(**base)  # type: ignore[arg-type]


def selftest(*, verbose: bool = True) -> int:
    """Both-direction controls over `audit`, on synthetic tables only.

    THE FLOOR IS NOT A HAND-TYPED COUNT OF ASSERTIONS. It is `len(cases)` plus the three controls declared after the loop, so adding a case raises the floor in the same edit. A hand-typed number is one nobody re-derives, and the driver contract's section 6 refuses those for exactly that reason.

    `verbose` is False on the leg `main` runs BEFORE every real scan, where 16
    `ok` lines would bury the verdict. The controls still run; only their
    per-control chatter is suppressed, and a failure still prints every FAIL.
    """
    fake_pins = {"WIDGET_VERSION": "1.0", "PYTEST_VERSION": "9.1.1"}
    fake_keys = {"widget": "WIDGET_VERSION", "pytest": "PYTEST_VERSION"}
    good_pytest = _row(
        name="pytest",
        pin_key="PYTEST_VERSION",
        install={"apt": "x", "brew": "y", "repo": ".ci/bootstrap.sh install"},
    )
    good_widget = _row(name="widget", pin_key="WIDGET_VERSION")
    clean = (good_widget, good_pytest)

    # The floor: the number of controls below, expressed as the length of the list they are declared in, so adding one cannot leave the floor behind.
    cases: list[tuple[str, tuple[Tool, ...], str | None]] = [
        # (label, table, a substring that MUST appear in the findings; None = clean)
        ("MUST NOT FIRE: a complete table is clean", clean, None),
        ("MUST FIRE: an EMPTY table is a finding, never a pass", (), "A0."),
        (
            "MUST FIRE: a duplicate row name",
            (good_widget, good_widget, good_pytest),
            "A1.",
        ),
        (
            "MUST FIRE: a pinned tool with no row",
            (good_pytest,),
            "A2.",
        ),
        (
            "MUST FIRE: a row whose pin_key disagrees with TOOL_KEYS",
            (_row(name="widget", pin_key="PYTEST_VERSION"), good_pytest),
            "A2.",
        ),
        (
            "MUST FIRE: a pin_key the pins file does not define",
            (
                _row(name="widget", pin_key="WIDGET_VERSION"),
                good_pytest,
                _row(name="extra", pin_key="NO_SUCH_KEY"),
            ),
            "A3.",
        ),
        (
            "MUST FIRE: a row with no darwin answer",
            (_row(name="widget", pin_key="WIDGET_VERSION", install={"apt": "x"}), good_pytest),
            "A4.",
        ),
        (
            "MUST FIRE: a row with no linux answer",
            (_row(name="widget", pin_key="WIDGET_VERSION", install={"brew": "x"}), good_pytest),
            "A5.",
        ),
        (
            "MUST FIRE: the pytest row is missing entirely",
            (good_widget,),
            "A6.",
        ),
        (
            "MUST FIRE: the pytest row exists but names the wrong pin",
            (
                good_widget,
                _row(
                    name="pytest",
                    pin_key="WIDGET_VERSION",
                    install={"apt": "x", "brew": "y", "repo": "z"},
                ),
            ),
            "A6.",
        ),
        (
            "MUST FIRE: the pytest row has no repo arm, so pytest has no uv shim",
            (
                good_widget,
                _row(name="pytest", pin_key="PYTEST_VERSION", install={"apt": "x", "brew": "y"}),
            ),
            "A6.",
        ),
        (
            "MUST FIRE: a row with no provenance",
            (_row(name="widget", pin_key="WIDGET_VERSION", provenance="  "), good_pytest),
            "A7.",
        ),
        (
            "MUST FIRE: a row naming an unknown package manager",
            (
                _row(
                    name="widget",
                    pin_key="WIDGET_VERSION",
                    install={"apt": "x", "brew": "y", "yum": "z"},
                ),
                good_pytest,
            ),
            "A8.",
        ),
    ]

    ctl = Controls("setup.tools", floor=len(cases) + 3, verbose=verbose)
    for label, table, want in cases:
        found = audit(table, pins=fake_pins, tool_keys=fake_keys)
        if want is None:
            ctl.check(label, found, [])
        else:
            ctl.check(label, any(f.startswith(want) for f in found), True)

    # THE SHIPPED TABLE IS DELIBERATELY NOT A CONTROL HERE, and it was one until a plant showed why it must not be. A control asking "does the real table audit clean" makes the instrument's health and the TREE's health the same question, so a genuine finding in the table came back as "the controls did not pass, so this gate has NOT judged the tree" -- which is false, and sends the
    # reader to the harness instead of to the row. The
    # controls below are synthetic only; the shipped table is judged by the audit
    # leg in `main`, which runs immediately after them, and by `test_the_shipped_table_audits_clean` in the pytest suite.

    # Two host-shape controls that do not depend on what is installed here.
    ctl.check(
        "MUST NOT FIRE: detect_manager returns a known name or the empty string",
        detect_manager() in (*ALL_MANAGERS, ""),
        True,
    )
    # STDERR IS CAPTURED, not left to leak. This control makes install_plan print a refusal, and on the leg `main` runs before every real scan that refusal would land on stderr in the middle of a PASSING run -- a line that reads as a failure during a green. Capturing it also strengthens the control: the message itself is asserted, not just the exit code, so a refusal that returned
    # the right number and said nothing would still fire.
    captured = io.StringIO()
    with contextlib.redirect_stderr(captured):
        refusal_rc = install_plan("yum", clean)
    ctl.check("MUST FIRE: install_plan refuses a manager nobody knows", refusal_rc, EXIT_FINDINGS)
    ctl.check(
        "MUST FIRE: and the refusal NAMES the known managers",
        all(m in captured.getvalue() for m in ALL_MANAGERS),
        True,
    )

    return EXIT_OK if ctl.report() else EXIT_FINDINGS


# --------------------------------------------------------------------------- argv dispatch ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    """The gate. The controls run FIRST, always, then the real audit.

    NOT ONLY UNDER `--selftest`. A gate whose controls run only when someone asks
    for them is a gate whose instrument is unproven on every run that matters:
    the wiring convention here is `<gate> --selftest && <gate>`, and for a `.py` gate `scripts/lib/gate-header.ts` derives the run as the BARE PATH, so the `--selftest` leg is never actually invoked by CI. Running the controls inline is what makes `selftest: true` in the header true rather than decorative.

    A CONTROL THAT CANNOT FIRE STOPS THE RUN. If the controls fail, this refuses WITHOUT judging the tree, because a verdict from an instrument that cannot fail is worse than no verdict.
    """
    if "--selftest" in argv:
        return selftest()

    # THE ONLY 77. See the module docstring: an unresolvable root means the pins corpus cannot be read, so every corpus-derived floor here is undefined and a 1 would put a green-able number on a run that scanned nothing.
    try:
        root = paths.repo_root()
    except paths.RootError as exc:
        print("tools: CANNOT RUN: %s" % exc, file=sys.stderr)
        return EXIT_CANNOT_RUN

    if "--report" in argv:
        return report()

    if "--install-plan" in argv:
        index = argv.index("--install-plan")
        chosen = argv[index + 1] if index + 1 < len(argv) else detect_manager()
        if not chosen:
            print(
                "tools: no package manager detected on this host; name one of %s"
                % ", ".join(ALL_MANAGERS),
                file=sys.stderr,
            )
            return EXIT_FINDINGS
        return install_plan(chosen)

    controls = selftest(verbose=False)
    if controls != EXIT_OK:
        print(
            "✗ the controls did not pass, so this gate has NOT judged the tree. "
            "Run `%s --selftest` to see which one." % paths.relative_to_root(__file__, root),
            file=sys.stderr,
        )
        return controls

    try:
        findings = audit()
    except toolchain.PinError as exc:
        print("✗ %s" % exc, file=sys.stderr)
        return EXIT_FINDINGS

    pinned_rows = [row for row in TOOLS if row.pin_key is not None]
    if findings:
        for finding in findings:
            print("✗ %s" % finding, file=sys.stderr)
        print(
            "✗ install table: %d finding(s) across %d row(s)." % (len(findings), len(TOOLS)),
            file=sys.stderr,
        )
        return EXIT_FINDINGS

    # PRINT THE SHAPE, NOT JUST THE VERDICT. A reader who sees these four numbers
    # can notice one of them collapsing; "ok" cannot be noticed at all.
    print(
        "ok   install table: %d row(s), %d pinned, %d pinned tool(s) in the "
        "toolchain corpus, %d pin(s) in %s, controls passed"
        % (
            len(TOOLS),
            len(pinned_rows),
            len(toolchain.TOOL_KEYS),
            len(toolchain.load_pins()),
            paths.relative_to_root(toolchain.pins_file(), root),
        )
    )
    return EXIT_OK


__all__ = [
    "ALL_MANAGERS",
    "DARWIN_MANAGERS",
    "EXIT_CANNOT_RUN",
    "EXIT_FINDINGS",
    "EXIT_OK",
    "LINUX_MANAGERS",
    "REPO_MANAGER",
    "TOOLS",
    "Tool",
    "audit",
    "detect_manager",
    "install_plan",
    "present",
    "probe_version",
    "report",
    "selftest",
]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
