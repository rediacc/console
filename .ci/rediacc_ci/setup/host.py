"""The seven `setup_*` machine-bootstrap phases, ported from `.ci/lib/setup.sh`.

WHAT THIS IS. `.ci/lib/setup.sh` is 845 lines answering one question: what does a
bare machine need before this repository can build? Nine functions are defined
there and this module carries all nine, keeping the split the bash drew
(`node_pick_lts` and `go_pick_sha` are separate because they are the parts that
can be unit-tested without a machine, and that reason survives the port).

THE CONTRACT THE BASH STATES AND THIS KEEPS, verbatim from `.ci/lib/setup.sh:17`:
"EVERY FUNCTION HERE IS IDEMPOTENT and returns 0 early when its condition is
already met. That is the contract: `./run.sh setup` is expected to be run
repeatedly, and a second run must do no work." Each function below therefore has
an early-return guard as its FIRST branch, and `shadow_driver.py` drives every
one of them twice against a fixture where the tool is present and requires the
second run to be byte-identical to the first.

AND THE SECOND CONTRACT, `.ci/lib/setup.sh:21-23`: each "refuses rather than
hanging on a non-TTY, printing the command it would have run as PLAIN stdout so
it can be pasted (log_* prefixes every line with a coloured marker, which breaks
a paste)". `ctx.say` is that plain stdout and `ctx.warn` is the marked stderr;
the two are never swapped, because swapping them is invisible in a terminal and
fatal to the paste.

ONE FUNCTION HERE IS REACHED BY NOTHING, AND THAT IS A FINDING ABOUT THE BASH,
NOT A DECISION OF THE PORT. `setup_docker_probe` is defined at
`.ci/lib/setup.sh:575` and called from NO file in the repository: `setup()` runs
`ensure_docker_installed` (`.ci/lib/local-common.sh:669`) instead, and the only
other occurrence of the name in the tree is a prose list in
`docs/ci-overhaul/06-progress.md:5109`. Measured 2026-09-09 with
`grep -rn setup_docker_probe`. It is carried here rather than dropped, because a
port is not the place to delete something: `docker_probe` below is a faithful
port, `PHASES` in `phases.py` does NOT list it, and the discrepancy is now
visible from two files instead of hidden in one. `scripts/gates/check-dead-bash.ts`
could never have found it: that gate asks whether a FILE's basename is mentioned,
and a dead function inside a live file is invisible to it.

WHAT IS DELIBERATELY NOT PORTED. Nothing in this module ever runs `sudo` or a
package manager on its own initiative. Every such path is behind
`ctx.stdin_tty and ctx.confirm(...)`, exactly as the bash is, and the
differential drives the closed-stdin side, which is the branch that prints.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil as _shutil
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

from rediacc_ci.core import platform as platform_
from rediacc_ci.core import toolchain

if TYPE_CHECKING:  # pragma: no cover - both names are only ever annotations here
    from rediacc_ci.setup.ctx import Ctx, Result

# The version managers `.ci/lib/setup.sh:70` probes, IN ITS ORDER, and the command each one wants. Order is observable: a machine with both fnm and mise is told about fnm, and a set would have made that arbitrary.
NODE_MANAGERS: tuple[tuple[str, str], ...] = (
    ("fnm", "fnm install {major} && fnm use {major}"),
    ("nvm", "nvm install {major} && nvm use {major}"),
    ("volta", "volta install node@{major}"),
    ("asdf", "asdf install nodejs latest:{major} && asdf global nodejs latest:{major}"),
    ("mise", "mise use -g node@{major}"),
)

# `.ci/lib/setup.sh:270-283`. The manager is probed in this order and the FIRST hit wins, so this is a tuple and not a dict literal read at random.
SYSTEM_TOOL_INSTALLS: tuple[tuple[str, str], ...] = (
    ("apt-get", "sudo apt-get update && sudo apt-get install -y build-essential python3 jq"),
    ("dnf", "sudo dnf groupinstall -y 'Development Tools' && sudo dnf install -y python3 jq"),
    ("pacman", "sudo pacman -S --noconfirm base-devel python jq"),
    ("apk", "sudo apk add build-base python3 jq"),
)

# `ARG GO_VERSION=` in `.devcontainer/Dockerfile`. The pin lives there and is
# read, never restated: `.ci/lib/setup.sh:332-335` records why (a floating `go` directive once resolved the never-published go1.26.5 and 404'd the image
# build). `grep -oP '^ARG GO_VERSION=\K[0-9.]+'` in the bash; the same anchor,
# the same character class, here.
GO_ARG_RE = re.compile(r"^ARG GO_VERSION=([0-9.]+)", re.MULTILINE)

# `go version 2>/dev/null | grep -oP 'go\K[0-9.]+' | head -1`.
GO_VERSION_RE = re.compile(r"go([0-9.]+)")

GH_INSTALL_DOCS = "https://github.com/cli/cli/blob/trunk/docs/install_linux.md"

# THE OFFICIAL apt RECIPE, VERBATIM. `.ci/lib/setup.sh:481-484` argues for keeping it that way: "kept verbatim rather than paraphrased: they add a signed keyring and an apt source, and getting either subtly wrong is a supply-chain problem, not a typo". A constant rather than a list built at the call site, so nothing can interpolate into it.
GH_APT_SCRIPT = """set -e
(type -p wget >/dev/null || (sudo apt-get update && sudo apt-get install wget -y))
sudo mkdir -p -m 755 /etc/apt/keyrings
out=$(mktemp)
wget -nv -O"$out" https://cli.github.com/packages/githubcli-archive-keyring.gpg
sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null <"$out"
rm -f "$out"
sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
sudo mkdir -p -m 755 /etc/apt/sources.list.d
echo "deb [arch=$(dpkg --print-architecture) \
signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] \
https://cli.github.com/packages stable main" \
  | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
sudo apt-get update
sudo apt-get install gh -y"""

NODE_DIST_INDEX = "https://nodejs.org/dist/index.json"
GO_DL_INDEX = "https://go.dev/dl/?mode=json&include=all"


# --------------------------------------------------------------------------- helpers the bash spells inline ---------------------------------------------------------------------------


def _at_least(have: str, want: str) -> bool:
    """`printf '%s\\n%s\\n' "$want" "$have" | sort -V -C`, without coreutils.

    UNPARSEABLE IS FALSE, NOT AN EXCEPTION. `sort -V -C` never raises; it ranks.
    A probe that threw here would turn "this node is too old" into a traceback,
    and the caller's whole point is to report the old node and carry on.
    `rediacc_ci.core.toolchain.at_least` is the shared implementation and its
    agreement with `sort -V` is what the w6p2-toolchain shadow ledger records.
    """
    try:
        return toolchain.at_least(have, want)
    except toolchain.VersionError:
        return False


def _uname(ctx: Ctx) -> tuple[str, str]:
    """`uname -s` and `uname -m`, as the bash asks them.

    THROUGH THE CHILD, not through `platform.uname()`. The differential points
    both sides at one fixture, and a fixture that puts a fake `uname` on PATH is
    the only way to drive the Darwin arms from a Linux box. `platform.uname()`
    reads the kernel and cannot be steered, so a Python side using it would be
    answering a question the bash side was never asked.
    """
    system = ctx.run(["uname", "-s"], timeout=10).out.strip()
    machine = ctx.run(["uname", "-m"], timeout=10).out.strip()
    return system, machine


def _sha256_file(path: pathlib.Path) -> str:
    """`_sha256sum <file> | awk '{print $1}'` (.ci/lib/local-common.sh:37).

    IN PROCESS, which removes the whole reason that bash helper exists. Its own
    header records the defect: "bare `sha256sum` does not exist on macOS, so the
    two checksum verifications below would report a MISMATCH that never happened,
    which is a verifier that CANNOT RUN reading as a verifier that FAILED."
    `hashlib` has no such platform hole, so the shim has no Python twin.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch(url: str, timeout: int) -> bytes | None:
    """`curl -fsS --max-time N <url>`. None on any failure, exactly as `|| ver=""`.

    `-f` is the flag that matters and the reason this returns None on an HTTP
    error rather than the body: without it curl writes a 404 page to the output
    file and exits 0, which is how "a documented `curl` of a 404 baked an HTML
    error page into a signing key" (`.ci/lib/setup.sh:41-42`). `urlopen` raises
    on 4xx/5xx, which is `-f` by default.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return response.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None


# --------------------------------------------------------------------------- the two pure pickers ---------------------------------------------------------------------------


def node_pick_lts(index_text: str, major: str) -> str | None:
    """Newest LTS for a major off nodejs.org's dist index. `.ci/lib/setup.sh:215`.

    The bash shells out to `python3 -c` for this, so the port is the same code
    with the interpolation removed. Two passes and the fallback matters: an LTS
    release is preferred, but a major with no LTS line yet still answers with its
    newest release rather than with nothing.
    """
    try:
        index = json.loads(index_text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(index, list):
        return None
    prefix = "v%s." % major
    releases = [
        r for r in index if isinstance(r, dict) and str(r.get("version", "")).startswith(prefix)
    ]
    lts = [r for r in releases if r.get("lts")]
    chosen = lts or releases
    if not chosen:
        return None
    version = chosen[0].get("version")
    return str(version) if version else None


def go_pick_sha(index_text: str, filename: str) -> str | None:
    """sha256 for one Go release filename off go.dev's json index. `:448`.

    Same shape as `node_pick_lts`: the bash is a `python3 -c` heredoc with the
    filename interpolated into it, which is also a quoting hazard the port
    removes for free (a filename with a quote in it would have broken the bash
    program rather than failing to match).
    """
    try:
        index = json.loads(index_text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(index, list):
        return None
    for release in index:
        if not isinstance(release, dict):
            continue
        for entry in release.get("files", []) or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("filename") == filename and entry.get("sha256"):
                return str(entry["sha256"])
    return None


# --------------------------------------------------------------------------- 1. node ---------------------------------------------------------------------------


def node_toolchain(ctx: Ctx) -> int:
    """`setup_node_toolchain`, .ci/lib/setup.sh:43. 0 ok, 1 the caller must stop.

    THE FLOOR IS REQUIRED, NOT DEFAULTED, and the bash's own comment
    (`:44-51`) is the reason: `${NODE_VERSION_MIN:-22.0.0}` "applied exactly when
    .ci/config/constants.sh had not been sourced, and 22.0.0 is LOOSER than the
    repo's real floor", so the unsourced path "silently accepted a Node this repo
    does not support and reported 'already present' for it". Here the missing
    variable is a refusal with the variable named, which is what `:?` does there.
    """
    minimum = ctx.env.get("NODE_VERSION_MIN", "")
    if not minimum:
        ctx.error("constants.sh was not sourced, so the Node floor is unknown")
        return 1
    major = ctx.env.get("NODE_VERSION_REQUIRED") or "22"

    current = ""
    if ctx.which("node"):
        # `node -v | cut -d'v' -f2`. cut on a DELIMITER, so `v22.13.0` yields
        # `22.13.0`; carried as a strip of the leading `v` because that is the
        # only `v` the string ever has.
        raw = ctx.run(["node", "-v"], timeout=10).out.strip()
        current = raw.removeprefix("v")
        if current and _at_least(current, minimum):
            if ctx.which("npm"):
                npm = ctx.run(["npm", "-v"], timeout=30).out.strip()
                ctx.info("Node.js %s and npm %s already present" % (current, npm))
                return 0
            ctx.warn("node %s is present but npm is NOT on PATH." % current)
        else:
            ctx.warn("Node.js %s is older than the required %s." % (current or "unknown", minimum))
    else:
        ctx.warn("Node.js is not installed; nothing in this repo can build or test without it.")

    # Their manager, their call. Print the command; do not drive it.
    manager = ""
    command = ""
    for name, template in NODE_MANAGERS:
        if ctx.which(name):
            manager, command = name, template
            break
    if not manager:
        nvm_sh = pathlib.Path(ctx.env.get("HOME", "")) / ".nvm" / "nvm.sh"
        # `-s`: exists AND is non-empty. An empty nvm.sh is not an nvm install.
        if nvm_sh.is_file() and nvm_sh.stat().st_size > 0:
            manager, command = "nvm", dict(NODE_MANAGERS)["nvm"]
    if manager:
        ctx.warn("You already use '%s'; install node with it rather than letting setup" % manager)
        ctx.warn("put a second toolchain on this machine:")
        ctx.say()
        ctx.say(command.format(major=major))
        ctx.say()
        ctx.say("Then re-run: ./run.sh setup")
        ctx.say()
        return 1

    system, machine = _uname(ctx)
    try:
        os_name = platform_.os_for("asset", system)
        arch = platform_.arch_for("node", machine)
    except platform_.PlatformError:
        # The bash writes two arms, one per unsupported axis, and only the OS one can fire first. `platform_` folds both into one exception, so the arm is chosen back by asking which half failed.
        if _os_unsupported(system):
            ctx.error("Unsupported OS %s; install Node.js >= %s yourself." % (system, minimum))
        else:
            ctx.error("Unsupported arch %s; install Node.js >= %s yourself." % (machine, minimum))
        return 1
    if os_name not in platform_.NATIVE_OSES:
        ctx.error("Unsupported OS %s; install Node.js >= %s yourself." % (system, minimum))
        return 1

    if not ctx.stdin_tty:
        ctx.warn("Non-interactive run; not installing. Install Node.js >= %s, or run" % minimum)
        ctx.warn("./run.sh setup from a terminal to be offered an automatic install.")
        return 1

    ctx.info(
        "Setup can install Node.js %s into ~/.local/share (no sudo, no system changes)." % major
    )
    if not ctx.confirm("Install a private Node.js %s for this machine?" % major):
        ctx.warn("Skipped. Install Node.js >= %s yourself, then re-run ./run.sh setup." % minimum)
        return 1

    return _node_install(ctx, major=major, os_name=os_name, arch=arch, minimum=minimum)


def _os_unsupported(system: str) -> bool:
    """Is `uname -s` outside the two the bash's `case` accepts?"""
    try:
        return platform_.os_name(system) not in platform_.NATIVE_OSES
    except platform_.PlatformError:
        return True


def _node_install(ctx: Ctx, *, major: str, os_name: str, arch: str, minimum: str) -> int:
    """The consented install half of `setup_node_toolchain`. `.ci/lib/setup.sh:126`.

    NEVER REACHED BY THE DIFFERENTIAL, and that is stated rather than hidden: it
    needs a tty, a network and a writable home. It is a faithful port of the
    bash's ordering, which is the part that carries the security property --
    download, then VERIFY, then extract, and never the other way round.
    """
    index = _fetch(NODE_DIST_INDEX, 30)
    version = node_pick_lts(index.decode("utf-8", "replace"), major) if index else None
    if not version:
        ctx.error("Could not resolve the latest Node.js %s LTS from nodejs.org." % major)
        ctx.error("Check network access, or install Node.js >= %s yourself." % minimum)
        return 1

    base = "node-%s-%s-%s" % (version, os_name, arch)
    url = "https://nodejs.org/dist/%s/%s.tar.xz" % (version, base)
    dest = pathlib.Path(ctx.env.get("HOME", "")) / ".local" / "share" / "node" / version
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        ctx.step("Downloading %s.tar.xz" % base)
        payload = _fetch(url, 300)
        if payload is None:
            ctx.error("Download failed: %s" % url)
            return 1
        archive = tmp / ("%s.tar.xz" % base)
        archive.write_bytes(payload)

        # Verify BEFORE extracting. An unverified tarball is the whole attack.
        ctx.step("Verifying checksum against the official SHASUMS256.txt")
        sums = _fetch("https://nodejs.org/dist/%s/SHASUMS256.txt" % version, 60)
        if sums is None:
            ctx.error("Could not fetch SHASUMS256.txt; refusing to install an unverified tarball.")
            return 1
        want = ""
        needle = " %s.tar.xz" % base
        for line in sums.decode("utf-8", "replace").split("\n"):
            if line.endswith(needle):
                want = line.split()[0]
                break
        got = _sha256_file(archive)
        if not want or want != got:
            ctx.error("Checksum MISMATCH for %s.tar.xz" % base)
            ctx.error("  expected: %s" % (want or "<not listed in SHASUMS256.txt>"))
            ctx.error("  got:      %s" % got)
            return 1
        ctx.info("Checksum verified")

        ctx.step("Installing to %s" % dest)
        dest.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(archive, "r:xz") as tar:
                _extract_strip1(tar, dest)
        except (tarfile.TarError, OSError):
            ctx.error("Extraction failed.")
            return 1
    finally:
        _shutil.rmtree(tmp, ignore_errors=True)

    bindir = pathlib.Path(ctx.env.get("HOME", "")) / ".local" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    linked = 0
    for name in ("node", "npm", "npx"):
        source = dest / "bin" / name
        if source.exists() or source.is_symlink():
            link = bindir / name
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(source)
            linked += 1
    if linked == 0:
        ctx.error("Extracted %s but found no bin/node; the archive layout was unexpected." % dest)
        return 1

    # `export PATH=...` on the ctx's env, not the process's. See ctx.py.
    ctx.env["PATH"] = "%s:%s" % (bindir, ctx.env.get("PATH", ""))
    if not ctx.which("node"):
        ctx.error("node still not resolvable after install.")
        return 1
    node_v = ctx.run(["node", "-v"], timeout=10).out.strip()
    npm_v = ctx.run(["npm", "-v"], timeout=30).out.strip()
    ctx.info("Node.js %s and npm %s installed" % (node_v, npm_v))

    if ":%s:" % bindir not in ":%s:" % ctx.env.get("PATH", ""):
        ctx.say()
        ctx.say("Add ~/.local/bin to your PATH so future shells find it:")
        ctx.say()
        ctx.say("echo 'export PATH=\"%s:%s\"' >> ~/.bashrc" % (bindir, ctx.env.get("PATH", "")))
        ctx.say()
    return 0


def _extract_strip1(tar, dest: pathlib.Path) -> None:
    """`tar -x ... --strip-components=1`.

    THE PATH IS CHECKED, which `tar(1)` does not do and which is the difference
    between extracting an archive and letting an archive write anywhere. A member
    whose resolved destination leaves `dest` is skipped rather than written; the
    bash had no equivalent and the port is not obliged to carry that hole.
    """
    root = dest.resolve()
    for member in tar.getmembers():
        parts = pathlib.PurePosixPath(member.name).parts
        if len(parts) <= 1:
            continue
        member.name = str(pathlib.PurePosixPath(*parts[1:]))
        target = (root / member.name).resolve()
        if root != target and root not in target.parents:
            continue
        tar.extract(member, root)


# --------------------------------------------------------------------------- 2. system tools ---------------------------------------------------------------------------


def system_tools(ctx: Ctx) -> int:
    """`setup_system_tools`, .ci/lib/setup.sh:248. The one step that needs root.

    MANDATORY, not best effort, and the bash's measurement is the reason
    (`:234-239`): on a bare Ubuntu box `cpu-features` runs node-gyp and dies with
    "Unable to detect compiler type", which fails `npm run install:natives`, which
    fails setup and every `./rdc.sh` behind it.
    """
    missing: list[str] = []
    if not ctx.which("cc"):
        missing.append("a C compiler")
    if not ctx.which("make"):
        missing.append("make")
    if not ctx.which("jq"):
        missing.append("jq")

    if not missing:
        ctx.info(
            "System tools present: %s, jq %s"
            % (_cc_version(ctx), ctx.run(["jq", "--version"], timeout=10).out.strip())
        )
        return 0

    ctx.warn("Missing required system tools: %s" % " ".join(missing))
    ctx.warn("  a C compiler + make: 'npm run install:natives' runs node-gyp for cpu-features")
    ctx.warn("  jq: EVERY PreToolUse hook in .claude/hooks parses its input with it")

    system, _ = _uname(ctx)
    if system == "Darwin":
        ctx.say()
        ctx.say("xcode-select --install   # compiler + make")
        ctx.say("brew install jq          # xcode-select does NOT provide jq")
        ctx.say()
        ctx.say("Then re-run: ./run.sh setup")
        ctx.say()
        return 1

    install_cmd = ""
    for manager, command in SYSTEM_TOOL_INSTALLS:
        if ctx.which(manager):
            install_cmd = command
            break
    if not install_cmd:
        ctx.error("No known package manager; install a C/C++ toolchain and python3 yourself.")
        return 1

    if not ctx.stdin_tty or not ctx.which("sudo"):
        ctx.warn("Cannot install it from here. Run this yourself:")
        ctx.say()
        ctx.say(install_cmd)
        ctx.say()
        ctx.say("Then re-run: ./run.sh setup")
        ctx.say()
        return 1

    ctx.info("This is the only step in setup that needs root.")
    ctx.say("  %s" % install_cmd)
    if not ctx.confirm("Install the build toolchain now?"):
        ctx.warn("Skipped, but install:natives will fail until it is installed. Run:")
        ctx.say()
        ctx.say(install_cmd)
        ctx.say()
        return 1

    # `eval "$install_cmd"`: the string carries `&&`, so it is a shell program and not an argv. Run through `bash -c` for the same reason, which is also why the string is a constant in this file and never built from input.
    if ctx.run(["bash", "-c", install_cmd], timeout=1800).rc != 0:
        ctx.error("Toolchain install failed. Run it yourself and re-run ./run.sh setup:")
        ctx.say()
        ctx.say(install_cmd)
        ctx.say()
        return 1

    for tool in ("cc", "make", "jq"):
        if not ctx.which(tool):
            ctx.error("'%s' still not resolvable after install." % tool)
            return 1
    ctx.info(
        "System tools installed (%s, jq %s)"
        % (_cc_version(ctx), ctx.run(["jq", "--version"], timeout=10).out.strip())
    )
    return 0


def _cc_version(ctx: Ctx) -> str:
    """`cc --version 2>/dev/null | head -1`. "" when there is no cc."""
    return ctx.run(["cc", "--version"], timeout=10).first_line()


# --------------------------------------------------------------------------- 3. go ---------------------------------------------------------------------------


def go_pin(root: pathlib.Path) -> str:
    """`ARG GO_VERSION` out of `.devcontainer/Dockerfile`. "" when unreadable."""
    try:
        text = (root / ".devcontainer" / "Dockerfile").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    found = GO_ARG_RE.search(text)
    return found.group(1) if found else ""


def go_toolchain(ctx: Ctx) -> int:
    """`setup_go_toolchain`, .ci/lib/setup.sh:339.

    ONE PIN, ONE PLACE. The version is read from `.devcontainer/Dockerfile`
    rather than restated, and the bash says why at `:332-335`. That indirection
    is the reason this function can be driven differentially at all: change the
    Dockerfile in a fixture and both sides move together.
    """
    want = go_pin(ctx.root)
    if not want:
        ctx.error("Could not read ARG GO_VERSION from .devcontainer/Dockerfile.")
        ctx.error("That file is the pin; fix it rather than hardcoding a version here.")
        return 1

    if ctx.which("go"):
        raw = ctx.run(["go", "version"], timeout=30).out
        found = GO_VERSION_RE.search(raw)
        current = found.group(1) if found else ""
        if current and _at_least(current, want):
            ctx.info("Go %s present (pin: %s)" % (current, want))
            return 0
        ctx.warn("Go %s is older than the pinned %s." % (current or "unknown", want))
    else:
        ctx.warn("Go is not installed; ./rdc.sh cannot build renet without it.")

    system, machine = _uname(ctx)
    if _os_unsupported(system):
        ctx.error("Unsupported OS %s; install Go %s yourself." % (system, want))
        return 1
    try:
        os_name = platform_.os_for("asset", system)
        arch = platform_.arch_for("goarch", machine)
    except platform_.PlatformError:
        ctx.error("Unsupported arch %s; install Go %s yourself." % (machine, want))
        return 1

    filename = "go%s.%s-%s.tar.gz" % (want, os_name, arch)
    if not ctx.stdin_tty:
        ctx.warn("Non-interactive run; not installing. Install Go %s, or run" % want)
        ctx.warn("./run.sh setup from a terminal to be offered an automatic install.")
        return 1

    ctx.info("Setup can install Go %s into ~/.local/share (no sudo)." % want)
    if not ctx.confirm("Install Go %s for this machine?" % want):
        ctx.warn("Skipped. Install Go %s yourself, then re-run ./run.sh setup." % want)
        return 1

    return _go_install(ctx, want=want, filename=filename)


def _go_install(ctx: Ctx, *, want: str, filename: str) -> int:
    """The consented install half of `setup_go_toolchain`. `.ci/lib/setup.sh:388`."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        ctx.step("Resolving %s checksum from go.dev" % filename)
        index = _fetch(GO_DL_INDEX, 60)
        want_sha = go_pick_sha(index.decode("utf-8", "replace"), filename) if index else None
        if not want_sha:
            ctx.error("Could not find a published checksum for %s." % filename)
            ctx.error("Check that %s exists on https://go.dev/dl/ (the pin may be wrong)." % want)
            return 1

        ctx.step("Downloading %s" % filename)
        payload = _fetch("https://go.dev/dl/%s" % filename, 600)
        if payload is None:
            ctx.error("Download failed: https://go.dev/dl/%s" % filename)
            return 1
        archive = tmp / filename
        archive.write_bytes(payload)

        got_sha = _sha256_file(archive)
        if want_sha != got_sha:
            ctx.error("Checksum MISMATCH for %s" % filename)
            ctx.error("  expected: %s" % want_sha)
            ctx.error("  got:      %s" % got_sha)
            return 1
        ctx.info("Checksum verified")

        dest = pathlib.Path(ctx.env.get("HOME", "")) / ".local" / "share" / "go" / want
        ctx.step("Installing to %s" % dest)
        _shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(archive, "r:gz") as tar:
                _extract_strip1(tar, dest)
        except (tarfile.TarError, OSError):
            ctx.error("Extraction failed.")
            return 1
    finally:
        _shutil.rmtree(tmp, ignore_errors=True)

    bindir = pathlib.Path(ctx.env.get("HOME", "")) / ".local" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    for name in ("go", "gofmt"):
        source = dest / "bin" / name
        if source.exists() or source.is_symlink():
            link = bindir / name
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(source)
    ctx.env["PATH"] = "%s:%s" % (bindir, ctx.env.get("PATH", ""))
    if not ctx.which("go"):
        ctx.error("go still not resolvable after install.")
        return 1
    ctx.info(ctx.run(["go", "version"], timeout=30).out.strip())
    return 0


# --------------------------------------------------------------------------- 4. gh ---------------------------------------------------------------------------


def gh_cli(ctx: Ctx) -> int:
    """`setup_gh_cli`, .ci/lib/setup.sh:485.

    MANDATORY. The bash's reason (`:466-471`) is that the PR guards run live `gh`
    queries and FAIL CLOSED, so on a machine without gh every `gh pr create` is
    refused. LATEST, NOT PINNED, deliberately: `gh` talks to an API that moves
    under it, so a pin would rot.
    """
    if ctx.which("gh"):
        ctx.info("GitHub CLI present (%s)" % ctx.run(["gh", "--version"], timeout=30).first_line())
        return 0

    ctx.warn("GitHub CLI (gh) is not installed.")
    ctx.warn("  The PR guards run live gh queries and FAIL CLOSED without it,")
    ctx.warn("  so gh pr create is refused on a machine that lacks gh.")

    system, _ = _uname(ctx)
    if system == "Darwin":
        ctx.say()
        ctx.say("brew install gh")
        ctx.say()
        ctx.say("Then re-run: ./run.sh setup")
        ctx.say()
        return 1
    if not ctx.which("apt-get"):
        ctx.error("Only the Debian/Ubuntu apt path is automated here.")
        ctx.error("See %s" % GH_INSTALL_DOCS)
        return 1
    if not ctx.stdin_tty or not ctx.which("sudo"):
        ctx.warn("Cannot install it from here. Official instructions:")
        ctx.say()
        ctx.say(GH_INSTALL_DOCS)
        ctx.say()
        ctx.say("Then re-run: ./run.sh setup")
        ctx.say()
        return 1

    ctx.info("Installing gh from the official GitHub apt repository (needs root).")
    if not ctx.confirm("Install the GitHub CLI now?"):
        ctx.warn("Skipped. PR commands will be refused until gh is installed.")
        return 1
    return _gh_install(ctx)


def _gh_install(ctx: Ctx) -> int:
    """The apt half of `setup_gh_cli`, `.ci/lib/setup.sh:524`.

    KEPT AS ONE SHELL PROGRAM, verbatim from the official docs. The bash's
    comment at `:523` says why the commands are "kept verbatim rather than
    paraphrased: they add a signed keyring and an apt source, and getting either
    subtly wrong is a supply-chain problem, not a typo". Splitting them into
    argv lists here would be exactly that paraphrase, so they stay a script.
    """
    if ctx.run(["bash", "-c", GH_APT_SCRIPT], timeout=1800).rc != 0:
        ctx.error("apt could not install gh. See the official instructions:")
        ctx.error("  %s" % GH_INSTALL_DOCS)
        return 1
    if not ctx.which("gh"):
        ctx.error("gh still not resolvable after install.")
        return 1
    ctx.info("%s installed" % ctx.run(["gh", "--version"], timeout=30).first_line())
    ctx.warn("Not authenticated yet. Run 'gh auth login' when you need PR commands.")
    return 0


# --------------------------------------------------------------------------- 5. docker probe -- DEFINED IN THE BASH, CALLED BY NOTHING. See the header. ---------------------------------------------------------------------------


def docker_probe(ctx: Ctx) -> int:
    """`setup_docker_probe`, .ci/lib/setup.sh:575. ADVISORY, never fatal.

    NOT IN `phases.PHASES`, because the bash `setup()` never calls it either.
    Ported anyway so the discrepancy is visible in two files rather than hidden
    in one; see this module's header for the measurement.
    """
    if not ctx.which("docker"):
        ctx.warn("Docker not found. Fine for CLI, www and test work.")
        ctx.warn("Needed for: ./run.sh service *, and the account dev stack.")
        return 0

    if ctx.run(["docker", "info"], timeout=30).rc == 0:
        version = ctx.run(["docker", "version", "--format", "{{.Server.Version}}"], timeout=15)
        # `|| echo 'version unknown'`: the bash discards the status here, and `.ci/rediacc_ci/core/dockerx.py:538` records that this is the right call in this one place -- an advisory line must not become an error.
        label = (
            version.out.strip() if version.rc == 0 and version.out.strip() else "version unknown"
        )
        ctx.info("Docker engine reachable (%s)" % label)
        return 0

    ctx.warn("Docker CLI is on PATH but no engine answered.")
    if _is_wsl():
        ctx.warn("This is WSL, and the usual cause is Docker Desktop's WSL integration")
        ctx.warn("being off for this distro. Enable it in:")
        ctx.warn("  Docker Desktop > Settings > Resources > WSL Integration > %s" % _pretty_name())
    else:
        ctx.warn("Start Docker Desktop, or: sudo systemctl start docker")
    ctx.warn("Not fatal. CLI, www and test work do not need it; ./run.sh service * does.")
    return 0


def _is_wsl() -> bool:
    """`grep -qi microsoft /proc/version`.

    NOT `platform_.detect_wsl`, which also consults `WSL_DISTRO_NAME` and
    `proc/sys/kernel/osrelease`. The bash asks one narrower question and the
    port answers the same one: a broader probe here would make the two sides
    disagree on a host where only the env var is set, and the differential would
    be right to call that a difference.
    """
    try:
        return (
            "microsoft"
            in pathlib.Path("/proc/version").read_text(encoding="utf-8", errors="replace").lower()
        )
    except OSError:
        return False


def _pretty_name() -> str:
    """`. /etc/os-release && echo "${PRETTY_NAME:-this distro}"`."""
    try:
        text = pathlib.Path("/etc/os-release").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "this distro"
    for line in text.split("\n"):
        if line.startswith("PRETTY_NAME="):
            value = line.split("=", 1)[1].strip().strip('"')
            return value or "this distro"
    return "this distro"


# --------------------------------------------------------------------------- 6. git identity ---------------------------------------------------------------------------

# `git log -200 --format='%an <%ae>' | grep -v '\[bot\]' | sort | uniq -c |
# sort -rn | head -1 | sed 's/^ *[0-9]* //'`. The whole pipeline is here rather than shelled out because `uniq -c | sort -rn` has a tie-break nobody wrote down: `sort -rn` is not stable across implementations, so the bash's answer on a tie is already unspecified. Python's `max` takes the FIRST maximum, which is at least a stated rule.
BOT_MARKER = "[bot]"


def dominant_author(log_text: str) -> str:
    """The most frequent `Name <email>` in a `git log --format` dump, bots out."""
    counts: dict[str, int] = {}
    for line in log_text.split("\n"):
        entry = line.strip()
        if not entry or BOT_MARKER in entry:
            continue
        counts[entry] = counts.get(entry, 0) + 1
    if not counts:
        return ""
    best = max(counts.values())
    for line in log_text.split("\n"):
        entry = line.strip()
        if entry and BOT_MARKER not in entry and counts.get(entry) == best:
            return entry
    return ""


def split_identity(suggested: str) -> tuple[str, str]:
    """`${suggested%% <*}` and `sed 's/.*<//; s/>.*//'`, as one call."""
    name = suggested.split(" <", 1)[0]
    email = suggested
    if "<" in email:
        email = email.rsplit("<", 1)[1]
    if ">" in email:
        email = email.split(">", 1)[0]
    return name, email


def git_identity(ctx: Ctx) -> int:
    """`setup_git_identity`, .ci/lib/setup.sh:609.

    RETURNS 0 IN EVERY BRANCH, exactly as the bash does: `setup()` calls it
    WITHOUT `|| return 1` (`.ci/legacy/run-legacy.sh:650`), so a missing identity
    is reported and setup continues. That asymmetry with `git_credentials`, which
    is fatal, is deliberate on the bash's side and is carried.
    """
    name = _git_global(ctx, "user.name")
    email = _git_global(ctx, "user.email")
    if name and email:
        ctx.info("Git identity: %s <%s>" % (name, email))
        return 0

    ctx.warn("Git identity is not configured; commits from this machine will fail.")
    suggested = dominant_author(
        ctx.run(["git", "log", "-200", "--format=%an <%ae>"], timeout=60).out
    )

    if not ctx.stdin_tty:
        ctx.warn("Non-interactive run; skipping the prompt. Set it yourself with:")
        if suggested:
            want_name, want_email = split_identity(suggested)
            ctx.warn('  git config --global user.name  "%s"' % want_name)
            ctx.warn('  git config --global user.email "%s"' % want_email)
        return 0

    want_name = ""
    want_email = ""
    if suggested:
        ctx.info("This repo's commits are authored by: %s" % suggested)
        if ctx.confirm("Use that identity for this machine?"):
            want_name, want_email = split_identity(suggested)

    if not want_name:
        want_name = ctx.ask("  Full name for git commits (blank to skip): ")
        if not want_name:
            ctx.warn("Skipped; git identity still unset.")
            return 0
        want_email = ctx.ask("  Email for git commits (blank to skip): ")
        if not want_email:
            ctx.warn("Skipped; git identity still unset.")
            return 0

    ctx.run(["git", "config", "--global", "user.name", want_name], timeout=30)
    ctx.run(["git", "config", "--global", "user.email", want_email], timeout=30)
    ctx.info("Git identity set: %s <%s>" % (want_name, want_email))

    # Only ever ADD; an existing operator preference is left alone.
    if not _git_global(ctx, "init.defaultBranch"):
        ctx.run(["git", "config", "--global", "init.defaultBranch", "main"], timeout=30)
        ctx.info("Set init.defaultBranch=main (matches every repo here)")
    if not _git_global(ctx, "pull.ff") and not _git_global(ctx, "pull.rebase"):
        ctx.run(["git", "config", "--global", "pull.ff", "only"], timeout=30)
        ctx.info("Set pull.ff=only (refuses surprise merge commits on pull)")
    return 0


def _git_global(ctx: Ctx, key: str) -> str:
    """`git config --global <key> || true`. "" when unset OR when git fails."""
    result = ctx.run(["git", "config", "--global", key], timeout=30)
    return result.out.strip() if result.rc == 0 else ""


# --------------------------------------------------------------------------- 7. git credentials ---------------------------------------------------------------------------

CREDENTIAL_QUERY = "protocol=https\nhost=github.com\n\n"


def credential_probe(ctx: Ctx) -> Result:
    """`git credential fill` with prompts disabled and a 20s deadline.

    HELPER-AGNOSTIC, which is why it is `git credential fill` and not a read of
    `~/.git-credentials`: store, osxkeychain, manager and gh's helper all answer
    it. `GIT_TERMINAL_PROMPT=0` is what makes it fail fast instead of hanging,
    and it is set on a COPY of the env so it does not leak into later calls.
    """
    saved = ctx.env.get("GIT_TERMINAL_PROMPT")
    ctx.env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        return ctx.run(["git", "credential", "fill"], timeout=20, stdin_text=CREDENTIAL_QUERY)
    finally:
        if saved is None:
            ctx.env.pop("GIT_TERMINAL_PROMPT", None)
        else:
            ctx.env["GIT_TERMINAL_PROMPT"] = saved


def git_credentials(ctx: Ctx) -> int:
    """`setup_git_credentials`, .ci/lib/setup.sh:689. BLOCKING on purpose.

    The bash's reason (`:672-676`): read access to this repo works ANONYMOUSLY,
    so the first sign of a missing credential is normally a failed PUSH long
    after setup said everything was fine.
    """
    if ctx.env.get("SKIP_GIT_CREDENTIAL_CHECK") == "1":
        ctx.warn("SKIP_GIT_CREDENTIAL_CHECK=1; not checking GitHub credentials.")
        return 0

    helper = _git_global(ctx, "credential.helper")

    if not helper and ctx.stdin_tty:
        ctx.warn("No git credential helper configured; git will re-ask for your")
        ctx.warn("GitHub token on every push.")
        if ctx.confirm(
            "Set credential.helper=store (token saved in plaintext at ~/.git-credentials)?"
        ):
            ctx.run(["git", "config", "--global", "credential.helper", "store"], timeout=30)
            helper = "store"
            ctx.info("Set credential.helper=store")

    if credential_probe(ctx).rc == 0:
        ctx.info("GitHub credential available%s" % (" (helper: %s)" % helper if helper else ""))
        return 0

    ctx.warn("No GitHub credential stored yet.")
    ctx.warn("Read access works anonymously here, so this would not bite until your")
    ctx.warn("first push, which is why setup asks now instead.")

    if not ctx.stdin_tty:
        ctx.warn("Non-interactive run; cannot prompt. Store one with:")
        ctx.say()
        ctx.say("git credential approve <<'CRED'")
        ctx.say("protocol=https")
        ctx.say("host=github.com")
        ctx.say("username=YOUR_GITHUB_USERNAME")
        ctx.say("password=YOUR_TOKEN")
        ctx.say("CRED")
        ctx.say()
        ctx.say("Then re-run: ./run.sh setup")
        ctx.say("(or set SKIP_GIT_CREDENTIAL_CHECK=1 if this machine has no push credential)")
        ctx.say()
        return 1

    if ctx.which("gh"):
        outcome = _try_gh_credential(ctx)
        if outcome is not None:
            return outcome

    ctx.say()
    ctx.say("  Falling back to a personal access token.")
    ctx.say("  Create one at: https://github.com/settings/tokens   (scope: repo)")
    ctx.say()
    if not ctx.confirm("Enter a GitHub token now and store it?"):
        ctx.warn("Skipped. Pushes will fail until a credential is stored.")
        return 1

    gh_user = ctx.ask("  GitHub username: ")
    if not gh_user:
        ctx.error("No username given; nothing stored.")
        return 1
    gh_token = ctx.ask("  GitHub token (input hidden): ", hidden=True)
    if not gh_token:
        ctx.error("No token given; nothing stored.")
        return 1
    if gh_token.startswith("<") and gh_token.endswith(">"):
        ctx.error("That looks like a placeholder ('%s'), not a token. Nothing stored." % gh_token)
        return 1

    ctx.run(
        ["git", "credential", "approve"],
        timeout=30,
        stdin_text="protocol=https\nhost=github.com\nusername=%s\npassword=%s\n\n"
        % (gh_user, gh_token),
    )
    del gh_token

    # VERIFY, because approve reports nothing and a silently-empty store is exactly what sent the operator round this loop once already.
    if credential_probe(ctx).rc != 0:
        ctx.error("Stored nothing: the credential helper did not return it back.")
        ctx.error("Check that credential.helper is set (it is: %s)." % (helper or "unset"))
        return 1
    ctx.info("GitHub credential stored and verified (helper: %s)" % (helper or "store"))
    return 0


def _try_gh_credential(ctx: Ctx) -> int | None:
    """The gh arms of `setup_git_credentials`. None means "fall through to a PAT".

    PREFER gh, and only fall back to a hand-pasted token: the bash's reason
    (`:747-755`) is that no token is ever typed, shown, or written in plaintext,
    gh handles renewal, and the scopes come from the flow. IT IS OFFERED, NEVER
    RUN UNASKED, because `gh auth login` opens a browser and authenticates a
    real account.
    """
    if ctx.run(["gh", "auth", "status"], timeout=60).rc == 0:
        ctx.info("gh is already authenticated; wiring it in as git's credential helper.")
        if ctx.run(["gh", "auth", "setup-git"], timeout=60).rc == 0:
            if credential_probe(ctx).rc == 0:
                ctx.info("GitHub credential now served by gh; no token to paste.")
                return 0
            ctx.warn("gh auth setup-git ran but git still cannot get a credential.")
        else:
            ctx.warn("gh auth setup-git failed; falling back to a stored token.")
        return None

    ctx.say()
    ctx.say("  gh is installed but not logged in. Logging in with gh is the better")
    ctx.say("  option: it opens a browser, and afterwards git gets its credential")
    ctx.say("  from gh, so there is no token to create, paste, or keep in a file.")
    ctx.say()
    if ctx.confirm("Run 'gh auth login' now?"):
        # `gh auth login && gh auth setup-git`: the second only runs if the first succeeded, and `gh auth login` is interactive, so it gets the real terminal rather than a captured pipe.
        login = subprocess.run(["gh", "auth", "login"], cwd=str(ctx.root), env=ctx.env, check=False)
        if (
            login.returncode == 0
            and ctx.run(["gh", "auth", "setup-git"], timeout=60).rc == 0
            and credential_probe(ctx).rc == 0
        ):
            ctx.info("Logged in and wired into git; no token to paste.")
            return 0
        ctx.warn("gh login did not produce a usable git credential.")
    return None
