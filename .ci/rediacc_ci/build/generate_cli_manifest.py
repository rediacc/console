#!/usr/bin/env python3
"""Port of `.ci/scripts/build/generate-cli-manifest.sh` (139 lines).

Builds `manifest.json` -- the file `rdc update` reads to learn what the latest
release is and where to download it -- from the `rdc-<platform>-<arch>.sha256`
files a CLI build leaves in a directory.

LIVE CALLERS, neither repointed by this port:
  * `.github/workflows/cd-stage.yml:168-173`  `--version <next> --channel <ch>
    --input dist/cli/ --output dist/cli/manifest.json`, the release path.
  * `.ci/legacy/run-legacy.sh:210-211`  `--version <describe> --input dist/cli/`,
    the PR-preview path, which takes the `<input>/manifest.json` default.

It is also DRIVEN AS A SUBJECT by `.ci/scripts/test/proxies/proxy-cli-manifest.sh`
and its own port `rediacc_ci.proxies.cli_manifest`, which run the BASH twin over
a fixture. Nothing there is repointed either.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHY
-----------------------------------------------------------------------------
`jq`, `date`, `awk`, `dirname` and `mkdir` are all spawned exactly as the twin
spawns them.

`jq` is not negotiable: THE MANIFEST IS jq'S BYTES. `:137` writes `jq .`'s
pretty-printer straight to the output file, and that file is uploaded to R2 and
served to every `rdc update`. Two-space indent, key order, `/` left unescaped,
one trailing newline -- a second pretty-printer that agreed today could stop
agreeing on a jq bump, and the twin's `:89` refusal proves jq is a hard
requirement of this script rather than an implementation detail.

`date` and `awk` are spawned for a sharper reason than fidelity of output:
FIDELITY OF FAILURE. Both sit inside `VAR="$(...)"` assignments, whose status
under `set -e` is the substitution's, so a host without them does not degrade --
it stops. Driven 2026-09-14 on a PATH holding neither: a missing `awk` exits
**127** at `:116` with `generate-cli-manifest.sh: line 116: awk: command not
found`, three log lines in and with no manifest written. `datetime.now()` and
`str.split()` would both have quietly succeeded there, turning a stop into a
silent pass, which is the one direction a port of a release-path script must
not move.

`dirname` is spawned because it is the one substitution here whose failure does
NOT stop the script; see `capture_lax`.

-----------------------------------------------------------------------------
FIVE DEFECTS IN THE TWIN, ALL REPRODUCED RATHER THAN REPAIRED
-----------------------------------------------------------------------------
1. A MANIFEST WITH ZERO BINARIES IS A SUCCESS. With an input directory holding
   no `.sha256` files at all, every platform takes the `continue` at `:112`,
   `:137` writes `"binaries": {}` and `:139` prints `✓ Manifest generated`.
   Exit 0. A release published from that manifest offers no downloads and
   nothing on the release path notices. This one is already WRITTEN DOWN as a
   known hazard by `proxy-cli-manifest.sh:160-166`, reported and not enforced;
   it is restated here because a reader of the port should not have to find the
   proxy to learn it. Driven: `--version 9.9.9 --input <empty dir>` exits 0.

2. AN UNREADABLE OR MALFORMED CHECKSUM IS A `log_warn` AND A `continue`.
   `:117-120` folds three different situations into one line -- an empty file,
   a truncated hash, and a file with several lines -- and none of them changes
   the exit code. A partial manifest that silently omits `mac-arm64` looks
   exactly like a build that never produced it.

3. `--input` RESOLVES AGAINST TWO DIFFERENT DIRECTORIES DEPENDING ON WHETHER
   YOU NAME IT. There is no `cd "$(get_repo_root)"` here, unlike every sibling
   in `.ci/scripts/build/`. `:63-66` defaults `INPUT_DIR` to the ABSOLUTE
   `$REPO_ROOT/dist/cli`, but an explicit `--input dist/cli/` is left relative
   and resolves against the CALLER's cwd. The two invocations that look
   equivalent are not. It works in CI only because both live callers happen to
   run from the repo root.

4. `--version` WITH NO VALUE IS BASH'S OWN `$2: unbound variable`. Each of the
   five value-taking arms reads `$2` under `set -u` with no arity check, so
   `--version` as the last token dies with
   `generate-cli-manifest.sh: line 28: $2: unbound variable` and exit 1 --
   a diagnostic naming an interpreter line number rather than the flag.

5. THE FILE-HEADER USAGE BLOCK OMITS `--channel`. `:5-12` documents
   `--version`, `--input`, `--output` and `--repo`; `--channel` exists (`:43`),
   is what `cd-stage.yml:171` passes, and decides whether the download URLs
   point at `cli/v<version>/` or `cli/<channel>/` (`:77-81`). Only the `--help`
   text at `:48` mentions it.

-----------------------------------------------------------------------------
DIVERGENCES, ALL IN TEXT ONLY A HUMAN READS
-----------------------------------------------------------------------------
 * `$0` in the `--help` line and in bash's `command not found` / `unbound
   variable` diagnostics is the program's own name, so the twin prints a `.sh`
   path and this prints a `.py` one. The differential normalises that one token
   and nothing else.
 * common.sh's `echo -e` interprets backslash escapes in the message;
   `rediacc_ci.log` formats the message as data.

K=5 LEDGER: `.ci/shadow/w7p6-generate-cli-manifest.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import log

# `.ci/scripts/lib/common.sh:205-210` resolves the root as `<lib>/../../..`;
# this module sits at `.ci/rediacc_ci/build/`, which is the same depth.
_ROOT_PARENT_INDEX = 3

# `:22`.
DEFAULT_REPO = "rediacc/console"

# `:65`, appended to the repo root. Defect 3 lives in the asymmetry between this
# absolute default and a caller-relative `--input`.
DEFAULT_INPUT_SUBDIR = ("dist", "cli")

# `:76`. The fallback when `RELEASES_BASE_URL` is unset or empty.
DEFAULT_RELEASES_BASE = "https://releases.rediacc.com"

# `:99`. `${GITHUB_SHA:-unknown}`.
DEFAULT_COMMIT = "unknown"

# `:82`, the exact format string handed to `date`.
DATE_FORMAT = "+%Y-%m-%dT%H:%M:%SZ"

# `:102-107`. The six binaries looked for, in the twin's iteration order.
PLATFORMS = ("linux", "mac", "win")
ARCHES = ("x64", "arm64")

# `:77`. A channel in this set (or an empty channel) gets the immutable
# versioned URL; anything else gets its own channel path.
VERSIONED_URL_CHANNELS = ("stable", "edge")

# `:100`, verbatim: the shape of the empty manifest before any binary is added.
MANIFEST_SEED_PROGRAM = (
    "{version: $version, releaseDate: $releaseDate, "
    "releaseNotesUrl: $releaseNotesUrl, commit: $commit, binaries: {}}"
)

# `:129`, verbatim.
ADD_BINARY_PROGRAM = ".binaries[$key] = {url: $url, sha256: $sha256}"

# `:116`, verbatim. The whole awk program.
FIRST_FIELD_PROGRAM = "{print $1}"

# `:117`. A sha256 is 64 hex characters; anything else is discarded with a warning.
SHA256_LENGTH = 64

# `:131`. How much of the hash the log line shows.
SHA256_LOG_PREFIX = 16

# The twin's line numbers. Bash names the line in `$2: unbound variable` and in
# `command not found`, so a reader diffs on them.
FLAG_LINES = {
    "--version": 28,
    "--input": 32,
    "--output": 36,
    "--repo": 40,
    "--channel": 44,
}
DATE_LINE = 82
JQ_SEED_LINE = 95
AWK_LINE = 116
JQ_ADD_LINE = 125
MKDIR_LINE = 136
WRITE_LINE = 137

# `:90`, verbatim.
NO_JQ_MESSAGE = "jq is required for manifest generation"

# `:59`, verbatim.
NO_VERSION_MESSAGE = "--version is required"

# `:52`, the lead of the one refusal this parser has (it DOES have a `*)` arm,
# unlike its `build-pages.sh` sibling).
UNKNOWN_OPTION_LEAD = "Unknown option: "


class Stop(Exception):  # noqa: N818 - a bash `exit`, not a Python error condition
    """One `exit <n>` from the twin, with the status it exits with."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def repo_root() -> pathlib.Path:
    """The twin's `get_repo_root` (`:63`). See `build_www` on why not `paths`."""
    return pathlib.Path(__file__).resolve().parents[_ROOT_PARENT_INDEX]


def usage_line() -> str:
    """`:48`, with `$0` as this program's own name."""
    return (
        "Usage: %s --version VERSION [--input DIR] [--output PATH] "
        "[--repo REPO] [--channel CHANNEL]" % sys.argv[0]
    )


def bash_diagnostic(line: int, message: str) -> str:
    """`<script>: line <N>: <message>`, bash's own prefix."""
    return "%s: line %d: %s" % (sys.argv[0], line, message)


def _strip_trailing_newlines(text: str) -> str:
    """What `$( )` does to a command's stdout: every trailing newline goes."""
    return text.rstrip("\n")


def capture_strict(argv: list[str], line: int, stdin: str | None = None) -> str:
    """`VAR="$(cmd)"`, whose own status IS the substitution's under `set -e`.

    stderr is INHERITED, exactly as the twin's is: a `jq: error` or an awk
    diagnostic still reaches the caller's terminal, it is only stdout that is
    captured. A non-zero status raises `Stop`, which is `set -e` firing.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        proc = subprocess.run(
            argv,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            check=False,
        )
    except PermissionError:
        print(bash_diagnostic(line, "%s: Permission denied" % argv[0]), file=sys.stderr, flush=True)
        raise Stop(126) from None
    except FileNotFoundError:
        print(bash_diagnostic(line, "%s: command not found" % argv[0]), file=sys.stderr, flush=True)
        raise Stop(127) from None
    if proc.returncode != 0:
        raise Stop(proc.returncode)
    return _strip_trailing_newlines(proc.stdout)


def capture_lax(argv: list[str], line: int) -> str:
    """`cmd "$(other)"`: a substitution used as an ARGUMENT, not as the command.

    `set -e` does not fire here, because the status that counts is the OUTER
    command's. `:136` is the one place in this script where that matters: with
    `dirname` absent, bash prints its `command not found`, substitutes the empty
    string, and hands `mkdir -p ''` to the next process, which is the thing that
    then fails. Reproducing the outer failure means reproducing the empty string.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=None, text=True, check=False)
    except PermissionError:
        print(bash_diagnostic(line, "%s: Permission denied" % argv[0]), file=sys.stderr, flush=True)
        return ""
    except FileNotFoundError:
        print(bash_diagnostic(line, "%s: command not found" % argv[0]), file=sys.stderr, flush=True)
        return ""
    return _strip_trailing_newlines(proc.stdout)


def run_strict(argv: list[str], line: int) -> None:
    """A plain command under `set -e`: both streams inherited, non-zero stops."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        code = subprocess.run(argv, check=False).returncode
    except PermissionError:
        print(bash_diagnostic(line, "%s: Permission denied" % argv[0]), file=sys.stderr, flush=True)
        raise Stop(126) from None
    except FileNotFoundError:
        print(bash_diagnostic(line, "%s: command not found" % argv[0]), file=sys.stderr, flush=True)
        raise Stop(127) from None
    if code != 0:
        raise Stop(code)


class Options:
    """The five variables `:19-23` initialise and `:25-56` fill in."""

    def __init__(self) -> None:
        self.version = ""
        self.input_dir = ""
        self.output_path = ""
        self.repo = DEFAULT_REPO
        self.channel = ""


def parse_argv(argv: list[str]) -> Options:
    """`:25-56`, arm for arm, including defect 4.

    Returns the filled `Options`. Raises `Stop(0)` for `--help` (after printing
    the usage line to STDOUT, as `echo` does) and `Stop(1)` for an unknown
    option or a value-taking flag with no value.
    """
    opts = Options()
    setters = {
        "--version": "version",
        "--input": "input_dir",
        "--output": "output_path",
        "--repo": "repo",
        "--channel": "channel",
    }
    i = 0
    while i < len(argv):
        token = argv[i]
        if token in setters:
            if i + 1 >= len(argv):
                # Defect 4: `$2` under `set -u`, reported with the ARM's line.
                print(
                    bash_diagnostic(FLAG_LINES[token], "$2: unbound variable"),
                    file=sys.stderr,
                    flush=True,
                )
                raise Stop(1)
            setattr(opts, setters[token], argv[i + 1])
            i += 2
        elif token in ("-h", "--help"):
            # `:48` uses `echo`, so this is STDOUT and not the logger.
            print(usage_line(), flush=True)
            raise Stop(0)
        else:
            log.error(UNKNOWN_OPTION_LEAD + token)
            raise Stop(1)
    return opts


def download_base(releases_base: str, channel: str, version: str) -> str:
    """`:77-81`. An empty channel is treated as a release channel."""
    if channel in VERSIONED_URL_CHANNELS or not channel:
        return "%s/cli/v%s" % (releases_base, version)
    return "%s/cli/%s" % (releases_base, channel)


def binary_name(platform: str, arch: str) -> str:
    """`:104-107`. Only `win` carries the `.exe` suffix."""
    name = "rdc-%s-%s" % (platform, arch)
    return name + ".exe" if platform == "win" else name


def _body(argv: list[str]) -> int:
    opts = parse_argv(argv)

    if not opts.version:  # `:58-61`
        log.error(NO_VERSION_MESSAGE)
        return 1

    root = repo_root()  # `:63`
    input_dir = opts.input_dir or str(root.joinpath(*DEFAULT_INPUT_SUBDIR))  # `:64-66`
    output_path = opts.output_path or "%s/manifest.json" % input_dir  # `:67-69`

    release_url = "https://github.com/%s/releases/tag/v%s" % (opts.repo, opts.version)  # `:71`

    # `:76`. Read at the call site, never through an `env = dict(os.environ)`
    # alias: `check:ci-python-env-registry`'s AST scanner cannot see through one.
    releases_base = os.environ.get("RELEASES_BASE_URL", "") or DEFAULT_RELEASES_BASE
    base = download_base(releases_base, opts.channel, opts.version)

    release_date = capture_strict(["date", "-u", DATE_FORMAT], DATE_LINE)  # `:82`

    log.step("Generating CLI manifest v%s" % opts.version)  # `:84`
    log.info("  Input: %s" % input_dir)  # `:85`
    log.info("  Output: %s" % output_path)  # `:86`

    # `:89-92`. `command -v jq &>/dev/null` differs from `shutil.which` only for
    # a shell FUNCTION or alias named jq, which a script bash spawns cannot inherit.
    if shutil.which("jq") is None:
        log.error(NO_JQ_MESSAGE)
        return 1

    # `:99`. Read at the call site, for the reason above.
    commit = os.environ.get("GITHUB_SHA", "") or DEFAULT_COMMIT

    manifest = capture_strict(  # `:95-100`
        [
            "jq",
            "-n",
            "--arg",
            "version",
            opts.version,
            "--arg",
            "releaseDate",
            release_date,
            "--arg",
            "releaseNotesUrl",
            release_url,
            "--arg",
            "commit",
            commit,
            MANIFEST_SEED_PROGRAM,
        ],
        JQ_SEED_LINE,
    )

    for platform in PLATFORMS:  # `:102`
        for arch in ARCHES:  # `:103`
            name = binary_name(platform, arch)
            checksum_file = "%s/%s.sha256" % (input_dir, name)  # `:109`
            if not pathlib.Path(checksum_file).is_file():  # `:110-113`
                log.info("  Skipping %s-%s (no checksum file)" % (platform, arch))
                continue

            sha256 = capture_strict(["awk", FIRST_FIELD_PROGRAM, checksum_file], AWK_LINE)  # `:116`
            if not sha256 or len(sha256) != SHA256_LENGTH:  # `:117-120`
                # Defect 2: empty, truncated and multi-line all land here, and
                # none of them changes the exit code.
                log.warn("  Invalid checksum for %s, skipping" % name)
                continue

            url = "%s/%s" % (base, name)  # `:122`
            key = "%s-%s" % (platform, arch)  # `:123`

            manifest = capture_strict(  # `:125-129`
                [
                    "jq",
                    "--arg",
                    "key",
                    key,
                    "--arg",
                    "url",
                    url,
                    "--arg",
                    "sha256",
                    sha256,
                    ADD_BINARY_PROGRAM,
                ],
                JQ_ADD_LINE,
                stdin=manifest + "\n",
            )

            log.info("  Added %s: %s..." % (key, sha256[:SHA256_LOG_PREFIX]))  # `:131`

    # `:136`. The inner `dirname` is LAX; the outer `mkdir` is strict.
    run_strict(["mkdir", "-p", capture_lax(["dirname", output_path], MKDIR_LINE)], MKDIR_LINE)

    # `:137`. `>` truncates the destination BEFORE jq runs, so a jq failure here
    # leaves a zero-byte manifest behind. Reproduced by opening in "w".
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        handle = open(output_path, "w", encoding="utf-8")  # noqa: SIM115 - closed below
    except OSError as exc:
        # bash's own redirect failure: `<script>: line 137: <path>: <reason>`.
        print(
            bash_diagnostic(WRITE_LINE, "%s: %s" % (output_path, exc.strerror)),
            file=sys.stderr,
            flush=True,
        )
        raise Stop(1) from None
    with handle:
        proc = subprocess.run(
            ["jq", "."],
            input=manifest + "\n",
            stdout=handle,
            stderr=None,
            text=True,
            check=False,
        )
    if proc.returncode != 0:
        # `pipefail`: `echo | jq` takes jq's status, and `set -e` stops on it.
        raise Stop(proc.returncode)

    log.info("Manifest generated: %s" % output_path)  # `:139`
    return 0


def main(argv: list[str]) -> int:
    """The twin's whole body, in its order."""
    try:
        return _body(argv)
    except Stop as stop:
        return stop.code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
