#!/usr/bin/env python3
"""Port of `.ci/scripts/release/update-homebrew-tap.sh`.

Rewrites `Formula/rediacc-cli.rb` in the `private/homebrew-tap` submodule with a
new version and the four platform SHA256 checksums, then optionally commits and
pushes it and moves the parent repository's submodule pointer.

Usage: update_homebrew_tap.py --version X.Y.Z [--push | --stage-only]
       [--local-checksums <dir>] [--dry-run]

THIS SCRIPT MUTATES ANOTHER REPOSITORY, WHICH IS WHY THE DIFFERENTIAL NEVER
RUNS EITHER SIDE AGAINST THE REAL TREE. `get_repo_root` (common.sh:205-210)
derives the root from common.sh's OWN location and takes no override, so the
twin always resolves `<root>/private/homebrew-tap` and will `sed` the live
formula, `git commit` inside the submodule and `git push origin HEAD:main`.
`test_release_update_homebrew_tap.py` therefore copies BOTH subjects into a
fixture tree at their real relative depths and stubs `git`, `curl` and `gh` as
recording fakes, so the only thing either side can reach is the fixture.

FOUR EXTERNAL PROGRAMS ARE STILL INVOKED, DELIBERATELY, and each for the same
reason `verify_release_assets.py` still invokes `jq`: the twin's behaviour on
awkward input IS that program's behaviour, and re-implementing it in Python
would be a second implementation of sed rather than a port of this script.

  * `sed`, through `rediacc_ci.core.common.sed_in_place` -- the already-ported
    twin of `sed_in_place` (common.sh:88-94), so the GNU/BSD branch comes free.
    The version string is interpolated into the sed REPLACEMENT, so a version
    containing `/`, `&` or `\\` is sed's problem in both implementations and
    means the same thing in both.
  * `awk`, with FORMULA_AWK below carried verbatim from the twin. The state
    machine decides WHICH of four `sha256 "..."` lines gets which checksum;
    a port that got it subtly wrong would publish a formula whose mac-arm64
    build installs the linux-x64 binary, and nothing downstream would notice
    until a user did.
  * `find` and `sha256sum` in the local-checksum path. `find ... | head -1`
    makes readdir ORDER load-bearing, and `sha256sum`'s `<hash>  <path>` line is
    written to a file the next step parses.
  * `curl` for the R2 download, and `git` for every repository mutation.

`extract_checksum` IS ALSO `awk`, and that is not laziness: the twin's
`awk '{print $1}' "$file"` on a MISSING file writes an implementation-specific
diagnostic to stderr and exits 2, which `set -e` turns into the script's exit
code. gawk, mawk and busybox awk word that diagnostic differently, so the only
way both sides say the same thing on the same machine is for both to ask the
same awk.

THREE `set -u` DEATHS ARE REPRODUCED IN SHAPE, NOT IN COORDINATES, and the
differential pins the difference rather than hiding it. `--version` and
`--local-checksums` read `"$2"` unguarded, and `commit_and_push` /
`update_submodule_pointer` read `"$GIT_BOT_NAME"` / `"$GIT_BOT_EMAIL"`, which
`.ci/config/constants.sh:164-166` deliberately does NOT declare. Each is a live
crash path a caller can reach, so the port exits 1 and writes bash's own
`<script>: line <n>: <name>: unbound variable`. The script name and the line
number are the port's own, because they are true of the port; every other byte
and the exit code agree.

CONSTANTS ARE LITERALS WITH A DRIFT TEST, not a bash parser. Two scalars are
read out of `.ci/config/constants.sh` by the twin -- `HOMEBREW_FORMULA_PATH`
(:288) and `RELEASES_BASE_URL` (:200) -- and both are reproduced below with
their line references. `test_constants_have_not_drifted` reads constants.sh and
asserts the pair still matches, so a change there turns the test RED instead of
being silently followed.

WHAT SOURCING constants.sh COSTS, reproduced because it fires before any
argument is read. `.ci/config/constants.sh:20-33` refuses when
`<root>/.devcontainer/toolchain.env` is not readable, and `set -e` on the
`source` line kills the caller. So `update-homebrew-tap.sh --help` exits 1 on a
checkout with no toolchain.env, and so does this. The two `${VAR:?}` refusals
further down constants.sh are NOT reproduced: they need a toolchain.env that
exists but is incomplete, which nothing in this repository can produce, and a
divergence nobody can reach is worse documented than implemented.

K=5 LEDGER: `.ci/shadow/w7p6-update-homebrew-tap.observations.jsonl`.
"""

from __future__ import annotations

import inspect
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import log
from rediacc_ci.core import common

# `.ci/config/constants.sh:288`, verbatim. Relative to the tap submodule root.
HOMEBREW_FORMULA_PATH = "Formula/rediacc-cli.rb"

# `.ci/config/constants.sh:200`: `${RELEASES_BASE_URL:-https://releases.rediacc.com}`,
# so the environment still wins.
RELEASES_BASE_URL_DEFAULT = "https://releases.rediacc.com"

# The submodule path, spelled the way the twin spells it in three places.
TAP_SUBMODULE = "private/homebrew-tap"

# `local required_files=(...)` (:101) and `local names=(...)` (:123). The two
# lists are the same four platforms in the same order, and they are separate in
# the twin because one names `.sha256` sidecars on R2 and the other names local
# binaries. Kept separate here for the same reason.
CHECKSUM_FILES = (
    "rdc-mac-arm64.sha256",
    "rdc-mac-x64.sha256",
    "rdc-linux-arm64.sha256",
    "rdc-linux-x64.sha256",
)
BINARY_NAMES = ("rdc-mac-arm64", "rdc-mac-x64", "rdc-linux-arm64", "rdc-linux-x64")

# The four files `update_formula` reads, in the order it reads them, paired with
# the awk variable each one feeds.
FORMULA_SLOTS = (
    ("mac_arm64", "rdc-mac-arm64.sha256", "mac-arm64:  "),
    ("mac_x64", "rdc-mac-x64.sha256", "mac-x64:    "),
    ("linux_arm64", "rdc-linux-arm64.sha256", "linux-arm64:"),
    ("linux_x64", "rdc-linux-x64.sha256", "linux-x64:  "),
)

# `.ci/scripts/release/update-homebrew-tap.sh:190-218`, verbatim.
#
# CARRIED AS DATA RATHER THAN RE-EXPRESSED. Four `sha256 "..."` lines live in one
# file and the only thing telling them apart is which `on_macos do` / `on_linux
# do` / `if Hardware::CPU.arm?` / `else` line was seen most recently. A Python
# re-implementation would be a second copy of that reasoning, and the failure it
# would produce is silent: a formula that installs the wrong binary on one
# platform, which passes every syntax check there is.
FORMULA_AWK = r"""
    BEGIN {
        in_macos = 0
        in_linux = 0
        in_arm = 0
        mac_arm_done = 0
        mac_x64_done = 0
        linux_arm_done = 0
        linux_x64_done = 0
    }
    /on_macos do/ { in_macos = 1; in_linux = 0 }
    /on_linux do/ { in_linux = 1; in_macos = 0 }
    /if Hardware::CPU.arm\?/ { in_arm = 1 }
    /^[[:space:]]*else/ { in_arm = 0 }
    /sha256/ {
        if (in_macos && in_arm && !mac_arm_done) {
            gsub(/sha256 "[^"]*"/, "sha256 \"" mac_arm64 "\"")
            mac_arm_done = 1
        } else if (in_macos && !in_arm && !mac_x64_done) {
            gsub(/sha256 "[^"]*"/, "sha256 \"" mac_x64 "\"")
            mac_x64_done = 1
        } else if (in_linux && in_arm && !linux_arm_done) {
            gsub(/sha256 "[^"]*"/, "sha256 \"" linux_arm64 "\"")
            linux_arm_done = 1
        } else if (in_linux && !in_arm && !linux_x64_done) {
            gsub(/sha256 "[^"]*"/, "sha256 \"" linux_x64 "\"")
            linux_x64_done = 1
        }
    }
    { print }
    """


class HelpRequestedError(Exception):
    """`-h | --help` (:56-59): the usage line on STDOUT, exit 0."""


class UnboundVariableError(Exception):
    """One `set -u` death, carrying bash's own wording.

    `line` is where it happens in THIS file, which is what makes the message
    true of the program that printed it. See the module docstring.
    """

    def __init__(self, name: str, line: int) -> None:
        super().__init__("%s: line %d: %s: unbound variable" % (sys.argv[0], line, name))


class MissingSourceError(Exception):
    """`source <path>` on a path that is not there (:25-26).

    bash writes `<script>: line <n>: <path>: No such file or directory` and
    `set -e` exits 1. Reproduced because a checkout missing common.sh or
    constants.sh must refuse, not run this script's logic with different
    defaults.
    """

    def __init__(self, path: pathlib.Path, line: int) -> None:
        super().__init__("%s: line %d: %s: No such file or directory" % (sys.argv[0], line, path))


class Options:
    """The five variables the twin's `while` loop sets (:28-65)."""

    def __init__(self) -> None:
        self.version = ""
        self.push = False
        self.stage_only = False
        self.local_checksums_dir = ""
        self.dry_run = False


def console_root() -> pathlib.Path:
    """`get_repo_root` (common.sh:205-210), from this file's own location.

    This module sits at `<root>/.ci/rediacc_ci/release/`, so `parents[3]` is the
    root, the same place `.ci/scripts/lib/../../..` lands. `paths.repo_root()`
    is deliberately not used: it honours `$REDIACC_CI_ROOT`, the twin has no
    such override, and a fixture that moved one and not the other would diverge
    for a reason that has nothing to do with this script.
    """
    return pathlib.Path(__file__).resolve().parents[3]


def usage(prog: str) -> str:
    """`:57`, with `$0` substituted the way bash substitutes it."""
    return (
        "Usage: %s --version X.Y.Z [--push | --stage-only] "
        "[--local-checksums <dir>] [--dry-run]" % prog
    )


def checksum_url(base: str, version: str, filename: str) -> str:
    """`${RELEASES_BASE_URL}/cli/v${VERSION}/${file}` (:103)."""
    return "%s/cli/v%s/%s" % (base, version, filename)


def commit_message(version: str) -> str:
    """`:239`. `[skip ci]` is load-bearing: without it the tap runs its own CI."""
    return "chore(release): bump rediacc-cli to %s [skip ci]" % version


POINTER_COMMIT_MESSAGE = "chore(release): update homebrew-tap submodule pointer [skip ci]"


def releases_base_url(env: dict[str, str] | None = None) -> str:
    """`.ci/config/constants.sh:200`."""
    e = dict(os.environ) if env is None else env
    return e.get("RELEASES_BASE_URL") or RELEASES_BASE_URL_DEFAULT


def parse_argv(argv: list[str]) -> Options:
    """The twin's hand-rolled loop (:34-65), including both ways it can die.

    NOT `common.parse_args`. This script does not call the shared parser: it
    matches five exact flags, treats anything else as an error rather than
    ignoring it, and reads `"$2"` with no `$# > 1` guard, which is precisely
    the crash path a shared parser would have removed.
    """
    opts = Options()
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag == "--version":
            if i + 1 >= len(argv):
                frame = inspect.currentframe()
                raise UnboundVariableError("$2", frame.f_lineno if frame else 0)
            opts.version = argv[i + 1]
            i += 2
        elif flag == "--push":
            opts.push = True
            i += 1
        elif flag == "--stage-only":
            opts.stage_only = True
            i += 1
        elif flag == "--local-checksums":
            if i + 1 >= len(argv):
                frame = inspect.currentframe()
                raise UnboundVariableError("$2", frame.f_lineno if frame else 0)
            opts.local_checksums_dir = argv[i + 1]
            i += 2
        elif flag == "--dry-run":
            opts.dry_run = True
            i += 1
        elif flag in ("-h", "--help"):
            raise HelpRequestedError(usage(sys.argv[0]))
        else:
            raise common.RefusalError("Unknown option: %s" % flag)
    return opts


def require_env(name: str, line: int, env: dict[str, str] | None = None) -> str:
    """`"$GIT_BOT_NAME"` under `set -u`: present or the shell dies."""
    e = dict(os.environ) if env is None else env
    if name not in e:
        raise UnboundVariableError(name, line)
    return e[name]


def _git(args: list[str], *, quiet: bool = False, capture: bool = False, cwd=None):
    """One `git` call, with the twin's redirection for that call site.

    `quiet` is `>/dev/null 2>&1`; `capture` is `$(...)`, which takes stdout and
    leaves stderr on the caller's own stderr.
    """
    if quiet:
        return subprocess.run(
            ["git", *args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=cwd,
            check=False,
        )
    if capture:
        return subprocess.run(
            ["git", *args], stdout=subprocess.PIPE, text=True, cwd=cwd, check=False
        )
    return subprocess.run(["git", *args], cwd=cwd, check=False)


def sync_to_origin_main(directory: pathlib.Path, *, dry_run: bool) -> int:
    """`:81-90`.

    THE FETCH IS ALLOWED TO FAIL AND THE REV-PARSE IS NOT. `|| true` on the
    fetch means an offline machine still proceeds against whatever `origin/main`
    it already has; the `rev-parse` that follows is a bare assignment, so `set
    -e` kills the script when there is no `origin/main` at all. Both halves are
    reproduced, including the fact that DRY-RUN still runs both of them and only
    skips the checkout.
    """
    _git(["-C", str(directory), "fetch", "origin", "main"], quiet=True)
    proc = _git(["-C", str(directory), "rev-parse", "origin/main"], capture=True)
    if proc.returncode != 0:
        return proc.returncode
    origin = proc.stdout.rstrip("\n")
    if not dry_run:
        rc = _git(
            ["-C", str(directory), "checkout", "-B", "main", origin, "--force"], quiet=True
        ).returncode
        if rc != 0:
            return rc
    log.info("Synced %s to origin/main (%s)" % (directory, origin))
    return 0


def download_checksums(tmpdir: pathlib.Path, version: str, *, dry_run: bool) -> int:
    """`:92-110`. Four `curl -fsSL`, and the FIRST failure ends the run."""
    log.step("Downloading SHA256 checksums from R2 for v%s..." % version)
    if dry_run:
        log.info("[DRY-RUN] Would download checksums for v%s" % version)
        return 0
    base = releases_base_url()
    for filename in CHECKSUM_FILES:
        rc = subprocess.run(
            [
                "curl",
                "-fsSL",
                checksum_url(base, version, filename),
                "-o",
                str(tmpdir / filename),
            ],
            check=False,
        ).returncode
        if rc != 0:
            log.error("Failed to download checksum: %s" % filename)
            return 1
    log.info("Downloaded all checksum files")
    return 0


def _find_first(directory: str, name: str) -> str:
    """`find "$dir" -name "${name}*" ! -name "*.sha256" -type f | head -1 || true`.

    SHELLED OUT BECAUSE THE ORDER IS THE ANSWER. `head -1` takes whatever
    readdir handed `find` first, so a directory holding both `rdc-mac-arm64` and
    `rdc-mac-arm64.old` resolves differently depending on the filesystem. An
    `os.walk` re-implementation would agree on every tidy directory and disagree
    on exactly the untidy one somebody would then have to debug. `find`'s own
    stderr is inherited here, as it is in the twin, so a missing directory still
    says so.
    """
    proc = subprocess.run(
        ["find", directory, "-name", "%s*" % name, "!", "-name", "*.sha256", "-type", "f"],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    lines = proc.stdout.split("\n")
    return lines[0] if lines and lines[0] else ""


def calculate_local_checksums(directory: str, outdir: pathlib.Path, *, dry_run: bool) -> int:
    """`:112-140`.

    A VACUOUS RUN IS ALREADY FATAL, PER ARTIFACT. The twin's own comment
    (:125-127) says so and it is worth keeping in the port: three of four
    binaries present still exits 1, because the test is inside the loop rather
    than on the aggregate.
    """
    log.step("Computing SHA256 checksums from local binaries in %s..." % directory)
    if dry_run:
        log.info("[DRY-RUN] Would compute checksums from %s" % directory)
        return 0

    for name in BINARY_NAMES:
        found = _find_first(directory, name)
        if not found:
            log.error("Missing local binary matching %s* in %s" % (name, directory))
            return 1
        sidecar = outdir / ("%s.sha256" % name)
        with sidecar.open("wb") as handle:
            rc = subprocess.run(["sha256sum", found], stdout=handle, check=False).returncode
        if rc != 0:
            return rc
        digest = extract_checksum(sidecar)
        if digest is None:
            return 2
        log.info("  %s: %s" % (name, digest))

    log.info("Computed all checksums from local binaries")
    return 0


def extract_checksum(path: pathlib.Path) -> str | None:
    """`awk '{print $1}' "$file"` (:142-146), inside `$( )`.

    Returns None when awk itself failed, which is how `set -e` sees it. See the
    module docstring for why this is awk and not `text.split()[0]`.
    """
    proc = subprocess.run(
        ["awk", "{print $1}", str(path)], stdout=subprocess.PIPE, text=True, check=False
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.rstrip("\n")


def update_formula(
    tmpdir: pathlib.Path, formula: pathlib.Path, version: str, *, dry_run: bool
) -> int:
    """`:148-224`. Version by `sed`, then the four checksums by `awk`."""
    log.step("Updating formula with version %s..." % version)
    if dry_run:
        log.info("[DRY-RUN] Would update formula to version %s" % version)
        return 0

    shas: dict[str, str] = {}
    for var, filename, _label in FORMULA_SLOTS:
        value = extract_checksum(tmpdir / filename)
        if value is None:
            # `set -e` on the failing command substitution: awk's own status,
            # which is 2 for a file it cannot open.
            return 2
        shas[var] = value

    log.info("Checksums extracted:")
    for var, _filename, label in FORMULA_SLOTS:
        log.info("  %s %s" % (label, shas[var]))

    rc = common.sed_in_place(["-E", 's/version "[^"]*"/version "%s"/' % version, str(formula)])
    if rc != 0:
        return rc

    fd, tmpname = tempfile.mkstemp()
    with os.fdopen(fd, "wb") as handle:
        rc = subprocess.run(
            [
                "awk",
                "-v",
                "mac_arm64=%s" % shas["mac_arm64"],
                "-v",
                "mac_x64=%s" % shas["mac_x64"],
                "-v",
                "linux_arm64=%s" % shas["linux_arm64"],
                "-v",
                "linux_x64=%s" % shas["linux_x64"],
                FORMULA_AWK,
                str(formula),
            ],
            stdout=handle,
            check=False,
        ).returncode
    if rc != 0:
        # `set -e` on the awk pipeline: the twin dies with the temp file still
        # on disk and the formula untouched. Only the leak is repaired here,
        # because a leaked temp file is not observable behaviour.
        pathlib.Path(tmpname).unlink(missing_ok=True)
        return rc
    shutil.move(tmpname, str(formula))

    log.info("Formula updated successfully")
    return 0


def commit_and_push(tap_dir: pathlib.Path, version: str, *, dry_run: bool) -> int:
    """`:226-244`.

    `git diff --quiet <path>` IS THE IDEMPOTENCE TEST, and it is asked inside an
    `if`, so its exit 1 is data rather than a failure. Re-running this script
    for a version already in the formula prints one line and pushes nothing.
    """
    if dry_run:
        log.info("[DRY-RUN] Would commit and push formula update")
        return 0

    if _git(["-C", str(tap_dir), "diff", "--quiet", HOMEBREW_FORMULA_PATH]).returncode == 0:
        log.info("Formula already at version %s" % version)
        return 0

    rc = _git(["-C", str(tap_dir), "add", HOMEBREW_FORMULA_PATH]).returncode
    if rc != 0:
        return rc

    frame = inspect.currentframe()
    line = frame.f_lineno if frame else 0
    bot_name = require_env("GIT_BOT_NAME", line)
    bot_email = require_env("GIT_BOT_EMAIL", line)

    rc = _git(
        [
            "-C",
            str(tap_dir),
            "-c",
            "user.name=%s" % bot_name,
            "-c",
            "user.email=%s" % bot_email,
            "commit",
            "-m",
            commit_message(version),
        ]
    ).returncode
    if rc != 0:
        return rc
    log.info("Committed formula update")

    rc = _git(["-C", str(tap_dir), "push", "origin", "HEAD:main"]).returncode
    if rc != 0:
        return rc
    log.info("Pushed to homebrew-tap")
    return 0


def stage_submodule_pointer(repo_root: pathlib.Path, *, dry_run: bool) -> int:
    """`:246-257`. Stages the pointer and stops, for `commit.sh` to pick up."""
    if dry_run:
        log.info("[DRY-RUN] Would stage submodule pointer for %s" % TAP_SUBMODULE)
        return 0
    rc = _git(["add", TAP_SUBMODULE], cwd=str(repo_root)).returncode
    if rc != 0:
        return rc
    log.info("Staged %s submodule pointer in parent repo" % TAP_SUBMODULE)
    return 0


def update_submodule_pointer(repo_root: pathlib.Path, *, dry_run: bool) -> int:
    """`:259-278`. Stages, and pushes the parent repo when the pointer moved."""
    if dry_run:
        log.info("[DRY-RUN] Would update submodule pointer")
        return 0

    rc = _git(["add", TAP_SUBMODULE], cwd=str(repo_root)).returncode
    if rc != 0:
        return rc

    if _git(["diff", "--cached", "--quiet"], cwd=str(repo_root)).returncode == 0:
        log.info("No submodule pointer changes")
        return 0

    frame = inspect.currentframe()
    line = frame.f_lineno if frame else 0
    bot_name = require_env("GIT_BOT_NAME", line)
    bot_email = require_env("GIT_BOT_EMAIL", line)

    rc = _git(
        [
            "-c",
            "user.name=%s" % bot_name,
            "-c",
            "user.email=%s" % bot_email,
            "commit",
            "-m",
            POINTER_COMMIT_MESSAGE,
        ],
        cwd=str(repo_root),
    ).returncode
    if rc != 0:
        return rc
    rc = _git(["push", "origin", "HEAD:main"], cwd=str(repo_root)).returncode
    if rc != 0:
        return rc
    log.info("Committed and pushed homebrew-tap submodule pointer update")
    return 0


def require_sources(root: pathlib.Path) -> None:
    """`source common.sh` (:25) and `source constants.sh` (:26), plus what the
    second one refuses on.

    Ordered exactly as the twin sources them, because the message a broken
    checkout gets names the FIRST missing file and no other.
    """
    frame = inspect.currentframe()
    line = frame.f_lineno if frame else 0
    for rel in (".ci/scripts/lib/common.sh", ".ci/config/constants.sh"):
        path = root / rel
        if not path.is_file():
            raise MissingSourceError(path, line)
    pins = root / ".devcontainer" / "toolchain.env"
    if not os.access(pins, os.R_OK):
        # `.ci/config/constants.sh:31-32`, verbatim, then `return 1` which
        # `set -e` turns into the caller's exit 1.
        print("constants.sh: gate toolchain pins missing: %s" % pins, file=sys.stderr)
        raise SystemExit(1)


def main(argv: list[str]) -> int:
    root = console_root()

    try:
        require_sources(root)
        opts = parse_argv(argv)
    except MissingSourceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except HelpRequestedError as exc:
        print(str(exc))
        return 0
    except UnboundVariableError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    if not opts.version:
        log.error("--version is required")
        return 1

    tap_dir = root / TAP_SUBMODULE
    formula = tap_dir / HOMEBREW_FORMULA_PATH

    pat = os.environ.get("GITHUB_PAT", "")
    if pat:
        rc = _git(
            [
                "config",
                "--global",
                "url.https://x-access-token:%s@github.com/.insteadOf" % pat,
                "https://github.com/",
            ]
        ).returncode
        if rc != 0:
            return rc

    log.step("Updating Homebrew tap for version %s..." % opts.version)

    try:
        common.require_file(formula)
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    checksum_dir = pathlib.Path(tempfile.mkdtemp())
    try:
        return _run(root, tap_dir, formula, checksum_dir, opts)
    except UnboundVariableError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        # `trap 'rm -rf "$CHECKSUM_DIR"' EXIT` (:287).
        shutil.rmtree(checksum_dir, ignore_errors=True)


def _run(
    root: pathlib.Path,
    tap_dir: pathlib.Path,
    formula: pathlib.Path,
    checksum_dir: pathlib.Path,
    opts: Options,
) -> int:
    """`:289-311`, the part that runs with the temp directory alive."""
    rc = sync_to_origin_main(tap_dir, dry_run=opts.dry_run)
    if rc != 0:
        return rc

    if opts.local_checksums_dir:
        rc = calculate_local_checksums(opts.local_checksums_dir, checksum_dir, dry_run=opts.dry_run)
    else:
        rc = download_checksums(checksum_dir, opts.version, dry_run=opts.dry_run)
    if rc != 0:
        return rc

    rc = update_formula(checksum_dir, formula, opts.version, dry_run=opts.dry_run)
    if rc != 0:
        return rc

    # `--stage-only` WINS over `--push` (:303-309). Both flags together is not
    # refused, it is silently resolved, and the port resolves it the same way.
    if opts.stage_only:
        rc = commit_and_push(tap_dir, opts.version, dry_run=opts.dry_run)
        if rc != 0:
            return rc
        rc = stage_submodule_pointer(root, dry_run=opts.dry_run)
    elif opts.push:
        rc = commit_and_push(tap_dir, opts.version, dry_run=opts.dry_run)
        if rc != 0:
            return rc
        rc = update_submodule_pointer(root, dry_run=opts.dry_run)
    if rc != 0:
        return rc

    log.info("Homebrew tap update complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
