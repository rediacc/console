#!/usr/bin/env python3
"""Port of `.ci/scripts/build/build-renet.sh` (256 lines).

THE FULL renet BUILD: stage the embedded third-party assets, export the raw native binaries the runtime image COPYs, cross-compile six `renet` binaries, checksum them, and report whether each one is stripped.

NOT THE SAME SCRIPT AS `.ci/scripts/infra/build-renet.sh`, which shares this basename and nothing else. That one is 131 lines, builds ONE binary from Go source for the local machine, and is ported at `.ci/rediacc_ci/infra/build_renet.py`. The two live in different packages, so the module names do not collide either. Anyone editing one of them should check which twin they are
reading.

WHAT IT DOES, IN THE TWIN'S ORDER

  1. `:22-52` parse `--version` (required), `--output`, `--skip-embed`, `-h`.
  2. `:64` `readlink -f` the output directory, `:66` `mkdir -p` it.
  3. `:83` `private/renet/build.sh embed_assets`, THE single source of truth for
     asset acquisition and per-arch staging. This script deliberately does not
     re-encode any of it; the twin's own comment at `:76-82` says why.
  4. `:86` `ls -la` the staged tree, onto STDOUT.
  5. `:95` `build.sh embed_proxy`, the proxy compose for `go:embed`.
  6. `:107-185` export the RAW native binaries into the output directory, from
     one of two sources: `docker cp` out of the builder image when this run
     built one, or `zstd -d` out of the staged `.zst` tree when the CI cache hit
     and `embed_assets` skipped. Then refuse if any declared asset is missing.
  7. `:196-226` six `go build` invocations: linux/darwin x amd64/arm64, then
     windows x amd64/arm64 with a `.exe` suffix.
  8. `:229-235` `sha256sum renet-*` into `checksums.sha256`, then `ls -la` and
     `cat` that file, both onto STDOUT.
  9. `:238-256` `file(1)` each binary and report stripped / may-contain-debug.

THE LOCKFILE IS THE SOURCE OF TRUTH for step 6. `private/renet/embed-assets.lock.json` supplies the component list, its per-arch coverage and the image directory each asset lives in. The twin's comment at `:115-118` records what it replaced: a hardcoded `<subdir>:<base>` table that had to be kept in step with `build.sh`'s four lists and `extract-renet-from-image.sh`'s own split, by
hand.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHAT IS NOT
-----------------------------------------------------------------------------
SHELLED OUT, because each one is the twin's contract with the machine and its stdout, stderr, argv or exit status is observable:

  * `private/renet/build.sh embed_assets` / `embed_proxy` (`:83`, `:95`), each
    from `private/renet` as its cwd.
  * `jq` (`:132-140`), one filter emitting `<imageDir>\\t<assetBase>\\t<arch>`.
    Kept as `jq` rather than `json.load` so the ROW ORDER and the `keys[]` sort
    stay in one place, and because that filter text is shared vocabulary with
    `build.sh` and `extract-renet-from-image.sh`.
  * `docker image inspect` / `docker create` / `docker cp` / `docker rm`
    (`:143`, `:145`, `:148`, `:151`).
  * `zstd -d -f -q` (`:171`) and `chmod +x` (`:172`). `chmod` is a subprocess
    rather than `os.chmod` on purpose: `chmod +x` means "add x where the umask
    allows", and reimplementing that from `os.umask` is a second spelling of a
    rule the coreutils binary already owns.
  * `readlink -f` (`:64`), whose FAILURE is load-bearing; see DEFECT 2.
  * `ls -la` (`:86`, `:234`), `sha256sum` (`:231`) and `cat` (`:235`). Their
    stdout IS this script's stdout, so they are run rather than reimplemented.
  * `go build` (`:214-216`, `:223-225`), six times, from `private/renet`.
  * `file` (`:242`, `:254`), and the `grep -q` / `head -c 80` that each one
    is PIPED into. Both halves of both pipelines are real processes here,
    because `set -o pipefail` makes the RIGHT half's absence change the
    left half's verdict. `file`'s absence is load-bearing too; see DEFECT 1.

NOT SHELLED OUT: `mkdir -p` (`:66`, `:109`), the `[[ -f ]]` tests, the glob expansions and `command -v`. A `mkdir -p` that cannot create its target dies
with a bash message here and a Python traceback there; the differential runs in
a writable tree, so that divergence is named rather than driven.

-----------------------------------------------------------------------------
DEFECTS CARRIED, NOT FIXED
-----------------------------------------------------------------------------
Every one of these was DRIVEN against the twin on the differential's fixture, and each has a test in `tests/test_build_build_renet.py` pinning the twin's answer next to this port's identical one. None is repaired here: the twin is the live registered gate and repairing it is a separate cutover decision.

DEFECT 1, A MISSING `file` REPORTS EVERY BINARY AS STRIPPED. `:242` is `if ! file "$binary" | grep -q "not stripped"`. With no `file` on PATH the pipeline is `command not found` (127) piped into a `grep` that matches nothing (1), the negation makes that TRUE, and the script prints `renet-linux-amd64: stripped (release build)` for all four. The verification step exists to catch a
binary that shipped with debug symbols, and with the tool absent it reports the answer it was built to disprove. Driven:

    (file present, debug binary)  ! renet-darwin-arm64: may contain debug symbols
    (file absent,  debug binary)  <script>: line 242: file: command not found
                                  + renet-darwin-arm64: stripped (release build)

Both runs exit 0. `file` is never `require_cmd`ed while `jq`, `zstd` and `go` all are. The same absence makes `:254` print `renet-windows-amd64.exe: ` with an empty description.

DEFECT 2, `--output` WITH A NON-EXISTENT PARENT DIES SILENTLY, EXIT 1, NO
MESSAGE. `:64` is `OUTPUT_DIR="$(readlink -f "$OUTPUT_DIR")"`, and GNU
`readlink -f` requires every component but the last to exist: given `--output /tmp/absent/deep` it prints nothing and exits 1, `set -e` takes the assignment's status, and the script is gone before `mkdir -p` on the very next
line would have created the directory. Driven: rc=1, stdout empty, stderr empty.
An operator sees a build that failed for no stated reason.

DEFECT 3, A MALFORMED OR EMPTY LOCKFILE MAKES THE COMPLETENESS CHECK VACUOUS AND
THE BUILD PASS. `:132-140` feeds `jq` through a PROCESS SUBSTITUTION, whose exit status no `set -e` can see. On a parse error `jq` writes to stderr, the array
stays empty, and the three loops over `"${_native_assets[@]}"` at `:146`, `:158`
and `:179` each run zero times. The last of those is the "fail fast" check whose own comment (`:176-178`) says a missing asset "must break HERE, not later as a cryptic COPY error ... on an artifact that looked complete". Driven with
`{ this is not json` as the lockfile:

    jq: parse error: Invalid literal at line 1, column 7
    ... build continues ...
    rc=0, private/bin/ holds the six renet binaries and ZERO assets

That is the exact artifact the check exists to prevent, produced with a clean
exit code. `{"components":{}}` reaches the same end without even a jq message.

DEFECT 4, NO STAGED ASSETS AT ALL IS A RAW `ls` ERROR, EXIT 2. `:86` is a bare `ls -la "$RENET_DIR"/pkg/embed/assets/*/*/`, and with nothing staged the unmatched glob is passed through literally, `ls` exits 2 and `set -e` ends the run with `ls: cannot access '...*/*/': No such file or directory` as the only diagnosis. This is the failure mode of an `embed_assets` that returned 0
without staging anything, and it is reported as a listing problem.

DEFECT 5, `:107` `if [[ -n "$OUTPUT_DIR" ]]` CANNOT BE FALSE. `OUTPUT_DIR` is non-empty by `:60` and is the output of a `readlink -f` that the script would not have survived failing (DEFECT 2). The whole export block is therefore unconditional, and the condition reads as though a caller could opt out of it.

-----------------------------------------------------------------------------
ENVIRONMENT
-----------------------------------------------------------------------------
ONE variable is READ: `ACCOUNT_ED25519_PUBLIC_KEY` (`:200-202`), the account server public key baked into the binaries through `-ldflags`. It is read with a literal `os.environ.get` at its single call site, never through a loop or an alias, because the env-registry gate resolves the NAME and an alias makes the input invisible to it.

`CGO_ENABLED`, `GOOS` and `GOARCH` (`:214`, `:223`) are SET for the `go build` children and never read, so they are passed in the child's env dict and are deliberately not `os.environ.get` call sites.
"""

from __future__ import annotations

import glob as globmod
import os
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `:143`, `:145`. The builder image `build.sh embed_assets` leaves behind when it really built one. Its ABSENCE selects the cache-hit path, not a failure.
BUILDER_IMAGE = "rediacc/renet:latest"

# `:132-140`, verbatim. One row per (component, arch), as `<imageDir>\t<assetBase>\t<arch>`. The field ORDER differs from the filter in `extract_renet_from_image.py`, which is the twin's doing and is preserved: the two scripts read the same lockfile with two different column orders.
MATRIX_FILTER = """
            .components
            | to_entries[]
            | .value as $c
            | $c.arches
            | keys[]
            | [$c.imageDir, $c.assetBase, .]
            | @tsv
        """

# `:161`. The two staged classes, searched in this order, first hit wins.
ASSET_CLASSES = ("base", "cluster")

# `:211-226`. The six targets in the twin's order, with the suffix each one's output carries. windows is a separate loop in the twin only because of `.exe`.
GO_TARGETS = (
    ("linux", "amd64", ""),
    ("linux", "arm64", ""),
    ("darwin", "amd64", ""),
    ("darwin", "arm64", ""),
    ("windows", "amd64", ".exe"),
    ("windows", "arm64", ".exe"),
)

# `:239-248`. Only the ELF targets are asked the stripped question; windows is PE and `file(1)` answers differently, which `:250` says out loud.
VERIFY_TARGETS = (
    ("linux", "amd64"),
    ("linux", "arm64"),
    ("darwin", "amd64"),
    ("darwin", "arm64"),
)

# `:201`. The linker symbol the account server public key is injected into.
KEY_SYMBOL = "-X github.com/rediacc/renet/pkg/license/keys.ProductionPublicKey="

# `:37-44`. `$0` is substituted at print time.
USAGE = (
    "Usage: %s --version VERSION [--output DIR] [--skip-embed]",
    "",
    "Build full renet binaries with embedded CRIU/rsync assets",
    "",
    "Options:",
    "  --version VERSION    Version to embed in binary (required)",
    "  --output DIR         Output directory for renet binaries",
    "  --skip-embed         Build without embedded assets",
)

# The lines bash names in a `set -u` death when an option's VALUE is missing.
# These are the lines of the ASSIGNMENTS, `VERSION="$2"` (`:25`) and
# `OUTPUT_DIR="$2"` (`:29`), not of the `case` labels above them. Both are
# established by DRIVING the twin, not by counting lines in a reading.
UNBOUND_LINES = {"--version": 25, "--output": 29}

# The lines whose external command bash names when it cannot run it. Used to reproduce bash's own `command not found` / `No such file or directory` text, which is the only diagnosis the twin emits for these.
LINE_EMBED_SUBSHELL = 83
LINE_PROXY_SUBSHELL = 95
LINE_CD_RENET = 196
LINE_FILE_ELF = 242
LINE_FILE_WINDOWS = 254


def console_root() -> pathlib.Path:
    """The repository root, from this file's own location.

    `get_repo_root` (common.sh:205-210) resolves from common.sh's own directory and has no environment override, so `paths.repo_root()` -- which honours `$REDIACC_CI_ROOT` -- is deliberately NOT used: it would make the port answerable to a variable the twin has never heard of, and the differential would then be comparing two different trees.
    """
    # This file: <root>/.ci/rediacc_ci/build/build_renet.py
    return pathlib.Path(__file__).resolve().parents[3]


def parse_args(argv: list[str]) -> tuple[str, str, bool, str | None, str]:
    """`:22-52`. Returns `(version, output_dir, skip_embed, kind, detail)`.

    `kind` is None to proceed, or one of:

      "help"     print `USAGE` on STDOUT and exit 0 (`:36-46`)
      "unknown"  `log_error "Unknown option: <detail>"`, exit 1 (`:47-50`)
      "unbound"  bash's own `set -u` death, `detail` is the line number

    Exercised directly by the differential in both directions, so the arms that must NOT fire (a bare `--skip-embed`, an empty argv) are pinned too.
    """
    version = ""
    output_dir = ""
    skip_embed = False
    i = 0
    while i < len(argv):
        opt = argv[i]
        if opt in UNBOUND_LINES:
            if i + 1 >= len(argv):
                return version, output_dir, skip_embed, "unbound", str(UNBOUND_LINES[opt])
            if opt == "--version":
                version = argv[i + 1]
            else:
                output_dir = argv[i + 1]
            i += 2
        elif opt == "--skip-embed":
            skip_embed = True
            i += 1
        elif opt in ("-h", "--help"):
            return version, output_dir, skip_embed, "help", ""
        else:
            return version, output_dir, skip_embed, "unknown", opt
    return version, output_dir, skip_embed, None, ""


def bash_glob(pattern: str, cwd: pathlib.Path | None = None) -> list[str]:
    """A bash glob, producing the exact STRINGS bash would hand the command.

    Two properties, both observable in this script's output:

      * With no `nullglob`, a pattern that matches nothing is passed through
        LITERALLY. That is what turns `:86` into DEFECT 4: `ls` is handed a path
        containing `*` and fails.
      * A pattern ending in `/` matches DIRECTORIES ONLY and keeps the trailing
        slash, which is why `ls -la .../assets/*/*/` prints a `dir:` header per
        arch/class rather than one flat listing. `glob.glob` has exactly that
        behaviour.

    Results are sorted, which under `LC_ALL=C` is byte order.
    """
    root_dir = None if cwd is None else str(cwd)
    matches = sorted(globmod.glob(pattern, root_dir=root_dir))
    return matches or [pattern]


def matrix_rows(text: str) -> list[tuple[str, str, str]]:
    """`:129-131`, `:147`. The lockfile matrix as `(image_dir, base, arch)`.

    `[ -n "$_line" ] || continue` drops blank lines, and
    `IFS=$'\\t' read -r _dir _base _na` folds any fourth field into the third
    and reads absent ones as empty. Both are reproduced, so a short or long row behaves here exactly as it does there rather than raising.
    """
    rows: list[tuple[str, str, str]] = []
    for line in text.split("\n"):
        if not line:
            continue
        fields = line.split("\t", 2)
        while len(fields) < 3:
            fields.append("")
        rows.append((fields[0], fields[1], fields[2]))
    return rows


def ldflags(version: str, key: str) -> str:
    """`:215`, `:224`. The `-ldflags` value, including its TRAILING SPACE.

    `-ldflags="-s -w -X main.Version=$VERSION $KEY_LDFLAGS"` is one QUOTED word,
    so an empty `KEY_LDFLAGS` leaves a trailing space inside it rather than disappearing. `go` does not care; the differential compares argv byte for byte, and a port that stripped it would diverge on all six calls.
    """
    suffix = "" if not key else KEY_SYMBOL + key
    return "-ldflags=-s -w -X main.Version=%s %s" % (version, suffix)


def _flush() -> None:
    sys.stdout.flush()
    sys.stderr.flush()


def _run(command: list[str], **kw) -> int:
    """A child whose streams the caller inherits unless told otherwise."""
    _flush()
    try:
        return subprocess.run(command, check=False, **kw).returncode
    except PermissionError:
        return 126
    except OSError:
        return 127


def _capture(command: list[str], **kw) -> tuple[int, str]:
    """`$(cmd)`: stdout consumed, stderr inherited, trailing newlines stripped."""
    _flush()
    try:
        proc = subprocess.run(command, check=False, stdout=subprocess.PIPE, text=True, **kw)
    except PermissionError:
        return 126, ""
    except OSError:
        return 127, ""
    return proc.returncode, proc.stdout.rstrip("\n")


def _bash_cannot_run(line: int, name: str, code: int) -> None:
    """bash's own message for a command it could not execute.

    Two spellings, and which one bash uses depends on the NAME: a word with a slash was a path that did not resolve (`./build.sh: No such file or directory`), a bare word was a PATH lookup that found nothing (`file: command not found`). Both were driven against the twin.
    """
    if code == 126:
        detail = "Permission denied"
    elif "/" in name:
        detail = "No such file or directory"
    else:
        detail = "command not found"
    print("%s: line %d: %s: %s" % (sys.argv[0], line, name, detail), file=sys.stderr, flush=True)


def _cd_or_report(target: pathlib.Path, line: int) -> str | None:
    """bash's `cd` failure text, or None when the directory is usable.

    `(cd "$RENET_DIR" && ...)` (`:83`, `:95`) and `cd "$RENET_DIR"` (`:196`) all die this way. Only the two reachable spellings are reproduced; a directory that exists but is unreadable prints `Permission denied` in bash and is not covered here, which is named rather than silently approximated.
    """
    if target.is_dir():
        return None
    detail = "Not a directory" if target.exists() else "No such file or directory"
    return "%s: line %d: cd: %s: %s" % (sys.argv[0], line, target, detail)


def _build_sh(renet_dir: pathlib.Path, step: str, line: int) -> int:
    """`(cd "$RENET_DIR" && ./build.sh <step>)`, one subshell.

    The `cd` and the exec are separate failures with separate messages, and both end the run under `set -e`: the subshell's status is 1 for a failed `cd`, 127 for a missing `./build.sh`, 126 for a non-executable one.
    """
    message = _cd_or_report(renet_dir, line)
    if message is not None:
        print(message, file=sys.stderr, flush=True)
        return 1
    code = _run(["./build.sh", step], cwd=str(renet_dir))
    if code in (126, 127) and not os.access(renet_dir / "build.sh", os.X_OK):
        _bash_cannot_run(line, "./build.sh", code)
    return code


def _export_native(
    root: pathlib.Path, output: pathlib.Path, rows: list[tuple[str, str, str]]
) -> int:
    """`:107-185`. The two sources, then the completeness check.

    DEFECT 5 lives on the first line of the twin's version of this: the `[[ -n "$OUTPUT_DIR" ]]` guard cannot be false, so the block is unconditional and is written as such here.
    """
    renet_dir = root / "private" / "renet"

    # `:142-143`. `command -v docker` and then an image lookup whose output and error are both discarded: absence is a route, not a failure.
    have_builder = False
    if shutil.which("docker") is not None:
        with open(os.devnull, "wb") as sink:
            have_builder = (
                _run(
                    ["docker", "image", "inspect", BUILDER_IMAGE],
                    stdout=sink,
                    stderr=sink,
                )
                == 0
            )

    if have_builder:
        # Source A `:144-151`.
        code, container_id = _capture(["docker", "create", BUILDER_IMAGE])
        if code != 0:
            # `set -e` on a failing command substitution in an assignment.
            return code
        for image_dir, base, arch in rows:
            asset = "%s-linux-%s" % (base, arch)
            with open(os.devnull, "wb") as sink:
                copied = _run(
                    ["docker", "cp", "%s:%s/%s" % (container_id, image_dir, asset), "%s/" % output],
                    stderr=sink,
                )
            if copied != 0:
                log.warn("native binary %s not found in builder image" % asset)
        with open(os.devnull, "wb") as sink:
            _run(["docker", "rm", container_id], stdout=sink, stderr=sink)
    else:
        # Source B `:152-174`.
        log.info("Builder image absent (cached staged tree); reconstructing via zstd -d")
        try:
            common.require_cmd("zstd")
        except common.RefusalError as exc:
            exc.report()
            return exc.code
        for _image_dir, base, arch in rows:
            asset = "%s-linux-%s" % (base, arch)
            staged = ""
            for klass in ASSET_CLASSES:
                candidate = renet_dir / "pkg" / "embed" / "assets" / arch / klass / (asset + ".zst")
                if candidate.is_file():
                    staged = str(candidate)
                    break
            if not staged:
                log.warn("no staged .zst for %s" % asset)
                # `:169`: the completeness check below fails loudly.
                continue
            code = _run(["zstd", "-d", "-f", "-q", staged, "-o", str(output / asset)])
            if code != 0:
                return code
            code = _run(["chmod", "+x", str(output / asset)])
            if code != 0:
                return code

    # `:176-185`. Vacuous when `rows` is empty; that is DEFECT 3, and it is the whole reason this loop cannot be trusted on its own.
    for _image_dir, base, arch in rows:
        asset = "%s-linux-%s" % (base, arch)
        if not (output / asset).is_file():
            log.error(
                "native binary %s missing after export (builder image or staged tree incomplete)"
                % asset
            )
            return 1
    return 0


def _stage_embedded(root: pathlib.Path, output: pathlib.Path) -> int:
    """`:73-186`, the whole `--skip-embed` == false branch."""
    renet_dir = root / "private" / "renet"

    log.step("Staging embedded assets")

    # `:83`.
    code = _build_sh(renet_dir, "embed_assets", LINE_EMBED_SUBSHELL)
    if code != 0:
        return code

    # `:85-86`. DEFECT 4: an unmatched glob reaches `ls` literally.
    log.info("Embedded assets:")
    code = _run(["ls", "-la", *bash_glob("%s/pkg/embed/assets/*/*/" % renet_dir)])
    if code != 0:
        return code

    # `:94-95`.
    log.info("Staging proxy compose doc...")
    code = _build_sh(renet_dir, "embed_proxy", LINE_PROXY_SUBSHELL)
    if code != 0:
        return code

    # `:107-109`. DEFECT 5: the guard is unconditional.
    log.step("Exporting native binaries (all 8 assets) for the runtime image...")
    output.mkdir(parents=True, exist_ok=True)

    # `:119-124`.
    try:
        common.require_cmd("jq")
    except common.RefusalError as exc:
        exc.report()
        return exc.code
    lockfile = root / "private" / "renet" / "embed-assets.lock.json"
    if not lockfile.is_file():
        log.error("embed lockfile not found: %s" % lockfile)
        return 1

    # `:128-140`. The status of a PROCESS SUBSTITUTION is unobservable to `set -e`, so a failing `jq` yields an empty matrix and the run continues. That is DEFECT 3, reproduced by ignoring the return code here.
    _code, matrix = _capture(["jq", "-r", MATRIX_FILTER, str(lockfile)])
    return _export_native(root, output, matrix_rows(matrix))


def _pipeline(left: list[str], right: list[str], line: int) -> tuple[int, int, bytes]:
    """`left | right`, run as two real processes, with bash's own message for either side that cannot be executed.

    THE SECOND HALF IS RUN, NOT REIMPLEMENTED, and that is a decision this port got wrong once. `grep -q "not stripped"` was first written as a Python `in` test, which is the same answer whenever `grep` exists and a DIFFERENT verdict when it does not: bash's pipeline is `command not found` (127) and takes the "stripped" arm, while an `in` test still reads the text and can report
    debug symbols. It was caught by a ledger fixture whose `grep` symlink happened to be broken, having produced four extra `line 242: grep: command not found` lines on the twin's side and none on this one. The same argument covers `head -c 80` on the windows arm.

    `left`'s output is buffered rather than streamed. The only observable difference is SIGPIPE: `grep -q` exits on its first match and a real pipeline could kill `file` with EPIPE. `file`'s output here is one line, written long before `grep` can exit, so the case is unreachable rather than ignored.
    """
    _flush()
    left_out = b""
    left_code = 0
    try:
        done = subprocess.run(left, check=False, stdout=subprocess.PIPE)
        left_out, left_code = done.stdout, done.returncode
    except OSError as exc:
        left_code = 126 if isinstance(exc, PermissionError) else 127
        _bash_cannot_run(line, left[0], left_code)
    try:
        done = subprocess.run(right, check=False, input=left_out, stdout=subprocess.PIPE)
        return left_code, done.returncode, done.stdout
    except OSError as exc:
        code = 126 if isinstance(exc, PermissionError) else 127
        _bash_cannot_run(line, right[0], code)
        return left_code, code, b""


def _verify(output: pathlib.Path) -> None:
    """`:237-256`. Reports only; nothing here can fail the run.

    DEFECT 1 is the `file`-shaped hole in both loops: an absent tool makes the first print `stripped (release build)` for everything and the second print an empty description.
    """
    log.step("Verifying release builds...")
    for goos, arch in VERIFY_TARGETS:
        binary = output / ("renet-%s-%s" % (goos, arch))
        # `! file "$binary" | grep -q "not stripped"` under `pipefail`, whose status is 0 only when BOTH sides are 0. A `file` that could not run, a `file` that errored, and a `grep` that found nothing all take the same arm, which is the one that says the binary is clean.
        file_code, grep_code, _ = _pipeline(
            ["file", str(binary)], ["grep", "-q", "not stripped"], LINE_FILE_ELF
        )
        if file_code == 0 and grep_code == 0:
            log.warn("renet-%s-%s: may contain debug symbols" % (goos, arch))
        else:
            log.info("renet-%s-%s: stripped (release build)" % (goos, arch))

    # `:250-256`. `$(file -b "$binary" | head -c 80)`: the first 80 BYTES, with trailing newlines stripped by the command substitution.
    for arch in ("amd64", "arm64"):
        binary = output / ("renet-windows-%s.exe" % arch)
        if not binary.is_file():
            continue
        _file_code, _head_code, head = _pipeline(
            ["file", "-b", str(binary)], ["head", "-c", "80"], LINE_FILE_WINDOWS
        )
        described = head.decode("utf-8", errors="replace").rstrip("\n")
        log.info("renet-windows-%s.exe: %s" % (arch, described))


def main(argv: list[str]) -> int:
    version, output_dir, skip_embed, kind, detail = parse_args(argv)
    if kind == "help":
        for line in USAGE:
            print(line % sys.argv[0] if "%s" in line else line)
        return 0
    if kind == "unknown":
        log.error("Unknown option: %s" % detail)
        return 1
    if kind == "unbound":
        print(
            "%s: line %s: $2: unbound variable" % (sys.argv[0], detail),
            file=sys.stderr,
            flush=True,
        )
        return 1

    # `:54-57`.
    if not version:
        log.error("--version is required")
        return 1

    # `:59-61`.
    root = console_root()
    renet_dir = root / "private" / "renet"
    target = output_dir or str(root / "private" / "bin")

    # `:64`. DEFECT 2: a parent that does not exist ends the run right here, exit 1, nothing printed by anybody.
    code, resolved = _capture(["readlink", "-f", target])
    if code != 0:
        return code
    output = pathlib.Path(resolved)

    # `:66`.
    output.mkdir(parents=True, exist_ok=True)

    # `:68-70`.
    log.step("Building renet binaries (release)")
    log.info("  Version: %s" % version)
    log.info("  Output: %s" % output)

    if not skip_embed:
        code = _stage_embedded(root, output)
        if code != 0:
            return code
    else:
        # `:188`.
        log.info("Skipping asset embedding (--skip-embed)")

    # `:192-196`.
    log.step("Building renet binaries (release)...")
    try:
        common.require_cmd("go")
    except common.RefusalError as exc:
        exc.report()
        return exc.code
    message = _cd_or_report(renet_dir, LINE_CD_RENET)
    if message is not None:
        print(message, file=sys.stderr, flush=True)
        return 1

    # `:199-203`. The ONE environment variable this script reads, at its one call site, spelled as a literal so the env-registry gate can resolve it.
    key = os.environ.get("ACCOUNT_ED25519_PUBLIC_KEY", "")
    if key:
        log.info("Account server public key injected from environment")

    # `:211-226`.
    flags = ldflags(version, key)
    for goos, arch, suffix in GO_TARGETS:
        log.info("Building renet-%s-%s..." % (goos, arch))
        child_env = dict(os.environ)
        child_env["CGO_ENABLED"] = "0"
        child_env["GOOS"] = goos
        child_env["GOARCH"] = arch
        code = _run(
            [
                "go",
                "build",
                flags,
                "-o",
                str(output / ("renet-%s-%s%s" % (goos, arch, suffix))),
                "./cmd/renet",
            ],
            cwd=str(renet_dir),
            env=child_env,
        )
        if code != 0:
            return code

    # `:229-231`. `cd "$OUTPUT_DIR"` for the checksum, so the recorded names are basenames; the redirect truncates `checksums.sha256` whether or not `sha256sum` then succeeds.
    log.step("Generating checksums...")
    with open(output / "checksums.sha256", "wb") as dest:
        code = _run(["sha256sum", *bash_glob("renet-*", output)], stdout=dest, cwd=str(output))
    if code != 0:
        return code

    # `:233-235`. Both of these put real content on STDOUT.
    log.info("Renet binaries built successfully:")
    code = _run(["ls", "-la", *bash_glob("%s/renet-*" % output)])
    if code != 0:
        return code
    code = _run(["cat", str(output / "checksums.sha256")])
    if code != 0:
        return code

    _verify(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
