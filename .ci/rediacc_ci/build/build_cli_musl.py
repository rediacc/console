#!/usr/bin/env python3
"""Port of `.ci/scripts/build/build-cli-musl.sh` (165 lines).

Builds the CLI as a musl-linked SEA binary by running `build-cli-executables.sh` INSIDE a `node:22-alpine` container, then renaming the container's glibc-named output (`dist/cli/rdc-linux-<arch>`) to the musl name (`dist/cli/rdc-linux-musl-<arch>`) and carrying its checksum across.

The whole build lives in a single `docker run ... sh -c '<script>'`. That inline script is the twin's, character for character, including the `'"$ARCH"'` quote-dance that splices the host's `$ARCH` into a single-quoted heredoc-ish string; see `CONTAINER_SCRIPT` below for why it is stored as a plain format string here instead.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHAT IS NOT
-----------------------------------------------------------------------------
SHELLED OUT, because each one is the twin's actual contract with the machine:

  * `docker run` -- the build itself.
  * `.ci/scripts/version/inject-env.sh --version <v> --strict --print` -- the
    publishable-version seam. Its stdout is discarded (`>/dev/null`) and only
    its exit status is read, exactly as at `:82`.
  * `sudo chown -R <uid>:<gid> <repo>/dist/cli/` -- ownership repair for files
    the container created as root. stderr suppressed, failure ignored (`:139`).
  * `sed "s/rdc-linux-<arch>/<binary>/"` -- the checksum-file rewrite (`:148`).
    Kept as a real `sed` call rather than a Python replace because GNU sed's
    handling of a final line WITHOUT a trailing newline is the observable
    detail, and reimplementing it would be a second answer to that question.
  * `sha256sum` / `shasum -a 256` -- the checksum fallback (`:151-155`),
    including the `command -v` probe that decides between them and the third
    outcome nobody writes down: when NEITHER exists the twin writes no checksum
    file at all and still exits 0.

NOT SHELLED OUT: `id -u` / `id -g`, which are `os.getuid()` / `os.getgid()`;
`wc -c`, which is `os.path.getsize`; `mkdir -p`, `mv`, `rm -f` and the `-f` tests. The `id` substitution is the one place a machine could tell the two apart: `$(id -u)` on a box with no `id` yields the empty string and the twin then runs `sudo chown -R : <dir>`, which fails and is swallowed. Python cannot lose the number, so on that machine the port repairs ownership and the twin
does not. Named rather than emulated.

-----------------------------------------------------------------------------
DEFECTS CARRIED, NOT FIXED
-----------------------------------------------------------------------------
DEFECT 1, `--dry-run` PREVIEWS A BUILD THAT COULD NEVER RUN. The architecture `case` that rejects anything other than `x64`/`arm64` sits at `:90-97`, AFTER the dry-run `exit 0` at `:68`. Driven:

    $ bash .ci/scripts/build/build-cli-musl.sh --arch banana --dry-run
    -> Building musl-linked CLI SEA executable: rdc-linux-musl-banana
    ok   Arch: banana
    ok [DRY-RUN] Would build rdc-linux-musl-banana
    ; echo $? -> 0

A preview whose only job is to say what would happen says the wrong thing, with a zero exit, for an input the real run rejects in one line. `require_cmd docker`
(`:71`) is skipped by the same early return, which is defensible for a preview;
validating the argument is not.

DEFECT 2, THE OUTPUT CHECK IS EXISTENCE-ONLY, SO A STALE BINARY SHIPS AS A MUSL
ONE. `:133` asks only whether `dist/cli/rdc-linux-<arch>` is a file. Nothing records when it appeared. A `dist/cli/rdc-linux-x64` left by an earlier GLIBC build satisfies it, gets renamed to `rdc-linux-musl-x64`, gets a freshly computed and entirely valid checksum, and is reported as a completed musl build. Driven against a `docker` stub that produces no output:

    ok Musl binary: <out>/rdc-linux-musl-x64 (0MB)
    ok Checksum: d936b9b8...  rdc-linux-musl-x64
    ok CLI musl build complete: <out>/rdc-linux-musl-x64
    ; echo $? -> 0
    $ cat <out>/rdc-linux-musl-x64
    STALE-GLIBC-BINARY

Both are reproduced here rather than repaired: the twin stays the registered gate and a cutover is a separate box.

DEFECT 3, THE SIZE IS FLOOR-DIVIDED TWICE. `$((BINARY_SIZE / 1024 / 1024))MB` reports `0MB` for anything under a megabyte, which is exactly the size a wrong artifact tends to be. Carried as `//`.

-----------------------------------------------------------------------------
ENVIRONMENT IS READ AT THE CALL SITE
-----------------------------------------------------------------------------
`RELEASE_BUILD`, `CLI_VERSION` and `CI` are each read with a literal `os.environ.get("NAME", "")` where they are used. No dict comprehension, no
`env = dict(os.environ)` alias: `check:ci-python-env-registry` derives a
module's declared inputs from the AST and records a non-literal key as the EXPRESSION, so an alias would leave every real input undeclared while the gate stayed green.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `:60`. The musl artifact name, and the only thing `--arch` really selects.
BINARY_PREFIX = "rdc-linux-musl-"

# `:90-97`. The two accepted architectures and the docker `--platform` each maps to, in the twin's `case` order.
DOCKER_PLATFORMS = {
    "x64": "linux/amd64",
    "arm64": "linux/arm64",
}

# `:82`, relative to the twin's own `$SCRIPT_DIR/..`.
INJECT_ENV_REL = ".ci/scripts/version/inject-env.sh"

# `:111`. The image the build runs in.
CONTAINER_IMAGE = "node:22-alpine"

# `:111-128`, verbatim. The twin writes this inside single quotes and splices the host `$ARCH` in with `'"$ARCH"'`; stored here as a `%s` slot because the quote-dance is a bash-only way of saying "substitute one value", and carrying it would reproduce the workaround rather than the string that reaches `sh -c`. The leading newline is the twin's: its single quote opens at the end of
# `:111`.
CONTAINER_SCRIPT = """
set -e

echo "\u2192 Installing build dependencies..."
apk add --no-cache python3 make g++ binutils bash jq

echo "\u2192 Installing npm dependencies..."
npm ci --ignore-scripts
# Rebuild native addons for musl
npm rebuild

echo "\u2192 Building shared packages..."
cd packages/shared && npx tsc -p tsconfig.json && cd /workspace
cd packages/provisioning && npx tsc -p tsconfig.json && cd /workspace

echo "\u2192 Building CLI bundle and SEA binary..."
.ci/scripts/build/build-cli-executables.sh --platform linux --arch %s
"""

# The lines bash names in a `set -u` death when an option's value is missing. `--arch "$2"` is `:28`; `--output "$2"` is `:32`.
UNBOUND_LINES = {"--arch": 28, "--output": 32}


def console_root() -> pathlib.Path:
    """The repository root, from this file's own location.

    `get_repo_root` (common.sh:205-210) has no environment override, so `rediacc_ci.paths.repo_root()` -- which honours `$REDIACC_CI_ROOT` -- is deliberately not used: a differential in which one side follows an override and the other does not diverges for a reason that says nothing about the port. Same derivation as `build/build_linux_packages.py`.
    """
    # This file: <root>/.ci/rediacc_ci/build/build_cli_musl.py
    return pathlib.Path(__file__).resolve().parents[3]


def container_script(arch: str) -> str:
    """`:111-128` with the host's `$ARCH` spliced in, as `sh -c` receives it."""
    return CONTAINER_SCRIPT % arch


def docker_argv(
    platform: str,
    repo_root: str,
    arch: str,
    ci: str,
    cli_version: str,
    release_build: str,
) -> list[str]:
    """`:104-128`, argument for argument.

    Exported so the differential can compare it against the recording fake's argv rather than inferring it from output. `CLI_VERSION` carries the twin's
    `${CLI_VERSION:-0.0.0-dev}` default; `CI` and `RELEASE_BUILD` are forwarded
    EMPTY when unset (`${VAR:-}`), which is not the same as being absent inside
    the container.
    """
    return [
        "docker",
        "run",
        "--rm",
        "--platform",
        platform,
        "-v",
        "%s:/workspace" % repo_root,
        "-w",
        "/workspace",
        "-e",
        "CI=%s" % ci,
        "-e",
        "CLI_VERSION=%s" % (cli_version or "0.0.0-dev"),
        "-e",
        "RELEASE_BUILD=%s" % release_build,
        CONTAINER_IMAGE,
        "sh",
        "-c",
        container_script(arch),
    ]


def parse_args(argv: list[str]) -> tuple[str, str, bool, int | None, str]:
    """`:25-48`. Returns `(arch, output_dir, dry_run, exit_code, message)`.

    `exit_code` is `None` when parsing succeeded. When it is not, `message` is the line to print and the caller decides the stream: `-h/--help` prints its usage on STDOUT and exits 0, every refusal goes to stderr.

    THE `set -u` DEATHS ARE REPRODUCED. `--arch` as the final argument makes bash expand `"$2"` with nothing behind it, which under `set -u` prints `<script>: line 28: $2: unbound variable` and exits 1 BEFORE `shift 2` runs. Driven on bash 5.3.9. The sentence names the script and the line, so the port forges it with `sys.argv[0]` and the twin's line number; the differential masks
    `$0` on both sides and compares the rest byte for byte.
    """
    arch = ""
    output_dir = ""
    dry_run = False
    i = 0
    while i < len(argv):
        opt = argv[i]
        if opt in ("--arch", "--output"):
            if i + 1 >= len(argv):
                return (
                    arch,
                    output_dir,
                    dry_run,
                    1,
                    "%s: line %d: $2: unbound variable" % (sys.argv[0], UNBOUND_LINES[opt]),
                )
            if opt == "--arch":
                arch = argv[i + 1]
            else:
                output_dir = argv[i + 1]
            i += 2
        elif opt == "--dry-run":
            dry_run = True
            i += 1
        elif opt in ("-h", "--help"):
            return (
                arch,
                output_dir,
                dry_run,
                0,
                "Usage: %s --arch ARCH [--output DIR] [--dry-run]" % sys.argv[0],
            )
        else:
            return (arch, output_dir, dry_run, 1, "Unknown option: %s" % opt)
    return (arch, output_dir, dry_run, None, "")


def _run(command: list[str], **kw) -> int:
    """A child process whose streams the caller inherits unless told otherwise.

    Returns bash's status for the three outcomes bash distinguishes: the child's own code, 126 for "cannot execute", 127 for "command not found". A real status is never flattened to 1.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        return subprocess.run(command, check=False, **kw).returncode
    except PermissionError:
        return 126
    except OSError:
        return 127


def main(argv: list[str]) -> int:
    arch, output_dir, dry_run, code, message = parse_args(argv)
    if code is not None:
        if code == 0:
            print(message, flush=True)
        elif message.startswith("Unknown option: "):
            log.error(message)
        else:
            print(message, file=sys.stderr, flush=True)
        return code

    # `:50-53`.
    if not arch:
        log.error("Missing required argument: --arch")
        return 1

    # `:55-58`.
    root = console_root()
    if not output_dir:
        output_dir = str(root / "dist" / "cli")

    binary_name = "%s%s" % (BINARY_PREFIX, arch)

    # `:62-64`.
    log.step("Building musl-linked CLI SEA executable: %s" % binary_name)
    log.info("  Arch: %s" % arch)
    log.info("  Output: %s/%s" % (output_dir, binary_name))

    # `:66-69`. DEFECT 1 lives here: the architecture is still unvalidated.
    if dry_run:
        log.info("[DRY-RUN] Would build %s" % binary_name)
        return 0

    # `:71`.
    try:
        common.require_cmd("docker")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    # `:77-86`. The release seam, checked here as well as inside the container so a release build fails in seconds instead of after an `npm ci` in Alpine.
    if os.environ.get("RELEASE_BUILD", "") == "true":
        cli_version = os.environ.get("CLI_VERSION", "")
        if not cli_version:
            log.error(
                "RELEASE_BUILD=true but CLI_VERSION is empty; refusing to build a "
                "publishable artifact without a version"
            )
            return 1
        # `>/dev/null` on stdout only: the script's own diagnostics stay visible.
        with open(os.devnull, "wb") as sink:
            status = _run(
                [str(root / INJECT_ENV_REL), "--version", cli_version, "--strict", "--print"],
                stdout=sink,
            )
        if status != 0:
            log.error(
                "Release build refused: CLI_VERSION='%s' is not a publishable version" % cli_version
            )
            return 1

    # `:90-97`.
    platform = DOCKER_PLATFORMS.get(arch)
    if platform is None:
        log.error("Invalid architecture '%s'. Must be x64 or arm64" % arch)
        return 1

    # `:102-128`.
    log.step("Running build inside %s container..." % CONTAINER_IMAGE)
    status = _run(
        docker_argv(
            platform=platform,
            repo_root=str(root),
            arch=arch,
            ci=os.environ.get("CI", ""),
            cli_version=os.environ.get("CLI_VERSION", ""),
            release_build=os.environ.get("RELEASE_BUILD", ""),
        )
    )
    # `set -e`: docker's own status, not a flattened 1.
    if status != 0:
        return status

    # `:131-136`. DEFECT 2: existence, never freshness.
    docker_output = root / "dist" / "cli" / ("rdc-linux-%s" % arch)
    if not docker_output.is_file():
        log.error("Docker build produced no output: %s" % docker_output)
        return 1

    # `:139`. Best-effort by design: `2>/dev/null || true`.
    with open(os.devnull, "wb") as sink:
        _run(
            [
                "sudo",
                "chown",
                "-R",
                "%d:%d" % (os.getuid(), os.getgid()),
                "%s/" % (root / "dist" / "cli"),
            ],
            stderr=sink,
        )

    # `:142-143`.
    out = pathlib.Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / binary_name
    shutil.move(str(docker_output), str(target))

    # `:146-156`.
    docker_checksum = docker_output.with_name(docker_output.name + ".sha256")
    if docker_checksum.is_file():
        with open(out / ("%s.sha256" % binary_name), "wb") as dest:
            status = _run(
                [
                    "sed",
                    "s/rdc-linux-%s/%s/" % (arch, binary_name),
                    str(docker_checksum),
                ],
                stdout=dest,
            )
        if status != 0:
            return status
        docker_checksum.unlink(missing_ok=True)
    else:
        # `command -v` for each, in the twin's order. When NEITHER is present the twin writes no checksum file and carries on, so neither does this.
        if shutil.which("sha256sum") is not None:
            checksum_argv = ["sha256sum", binary_name]
        elif shutil.which("shasum") is not None:
            checksum_argv = ["shasum", "-a", "256", binary_name]
        else:
            checksum_argv = []
        if checksum_argv:
            with open(out / ("%s.sha256" % binary_name), "wb") as dest:
                status = _run(checksum_argv, stdout=dest, cwd=str(out))
            if status != 0:
                return status

    # `:158-159`. DEFECT 3: two floor divisions.
    binary_size = target.stat().st_size
    log.info("Musl binary: %s (%dMB)" % (target, binary_size // 1024 // 1024))

    # `:161-163`. `$(cat ...)` strips every trailing newline.
    checksum_file = out / ("%s.sha256" % binary_name)
    if checksum_file.is_file():
        log.info(
            "Checksum: %s"
            % checksum_file.read_text(encoding="utf-8", errors="replace").rstrip("\n")
        )

    # `:165`.
    log.info("CLI musl build complete: %s" % target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
