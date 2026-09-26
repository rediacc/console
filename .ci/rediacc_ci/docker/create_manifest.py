#!/usr/bin/env python3
"""Port of `.ci/scripts/docker/create-manifest.sh`.

Combines `<image>:<tag>-amd64` and `<image>:<tag>-arm64` into one multi-arch manifest at `<image>:<tag>`, via `docker buildx imagetools create`, optionally also at `<image>:latest`, then tries to verify what it pushed.

THE ARCH LIST IS THE CONTRACT AND IT IS NOT DISCOVERED. `ARCHS=("amd64" "arm64")`
is hard-coded in the twin, so an image built for only one of the two produces a `create` against a tag that does not exist and the failure comes from the registry, not from this script. Reproduced rather than "fixed" with a probe: a port that skipped a missing arch would publish a SILENTLY single-arch manifest under a name every consumer reads as multi-arch.

THE DOUBLE SPACE IS REAL OUTPUT, NOT A TYPO IN THIS PORT. The twin accumulates
`SOURCE_IMAGES="${SOURCE_IMAGES} ${IMAGE_PATH}:${TAG}-${arch}"` starting from
the empty string, so the value carries a LEADING space, and every line that interpolates it after a space of its own therefore prints two:

    log_info "  Sources: ${SOURCE_IMAGES}"      ->  "  Sources:  ghcr.io/..."
    echo "  docker ... -t $MANIFEST_TAG ${SOURCE_IMAGES}"

`source_images_field()` below reproduces the leading space deliberately and `test_the_leading_space_in_the_sources_field_is_the_twins` pins it, so nobody "cleans it up" into a byte divergence. The ACTUAL argv passed to docker is built
from a list and has no such artefact; only the human-readable echoes do.

VERIFICATION IS ADVISORY, AND IT INSPECTS TWICE. The twin runs `docker buildx imagetools inspect` once with `&>/dev/null` to decide the verdict, then AGAIN, piped through `grep -E "(Platform:|Name:)" | head -10`, to show platforms. Both calls are kept: the recorded call log is the evidence in the differential, so collapsing them into one would be a behaviour change hidden behind
identical printed bytes. A failed verification only WARNS (`may still be pushing`) and the script still exits 0, which means this script cannot tell you whether the manifest it just created is readable. Recorded as `test_defect_a_manifest_that_cannot_be_verified_still_exits_zero`.

`--push-latest` IS NEVER VERIFIED. Only `$MANIFEST_TAG` is inspected, so a `:latest` that failed to become readable passes silently. Same class, same treatment: pinned, not repaired.

grep AND head ARE IMPLEMENTED IN PYTHON, unlike jq in `cleanup_staging`. The distinction is whether the external tool's semantics DECIDE anything. jq picks which package version gets deleted; here the pipeline only selects lines for a human to read, `grep -E "(Platform:|Name:)"` is an unanchored substring alternation with no metacharacters, `head -10` is the first ten lines, and
the whole pipeline's exit status is discarded by `|| true`. Reproducing that in Python removes two more processes from the differential's fake-PATH surface without changing a byte; `test_the_platform_filter_matches_grep_e_on_a_corpus` checks the two against real grep on a corpus that includes the awkward cases.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci import log

# --------------------------------------------------------------------------- The twin's constants ---------------------------------------------------------------------------

# `.ci/config/constants.sh:162`. `:-` takes the default on unset OR empty.
REGISTRY_DEFAULT = "ghcr.io/rediacc"

# `ARCHS=("amd64" "arm64")` (twin :38), in order: the source list order is the
# order docker is handed, and imagetools keeps it in the manifest.
ARCHS = ("amd64", "arm64")

# `grep -E "(Platform:|Name:)" | head -10` (twin :167).
PLATFORM_NEEDLES = ("Platform:", "Name:")
PLATFORM_HEAD = 10

# `set -u` death sites: the line of each `VAR="$2"` assignment in the twin, so
# the port prints bash's own message including the line number. Pinned against the twin by the differential.
UNBOUND_LINES = {"--image": 43, "--image-path": 47, "--tag": 51}

# The `docker buildx imagetools create` call site (twin :134). Named only so the `command not found` message can carry the same line number bash would.
DOCKER_CREATE_LINE = 134


def registry() -> str:
    """`$PUBLISH_DOCKER_REGISTRY` with constants.sh's default."""
    return os.environ.get("PUBLISH_DOCKER_REGISTRY") or REGISTRY_DEFAULT


def dry_run_default() -> str:
    """`DRY_RUN="${DRY_RUN:-false}"`, compared `== "true"` and nothing else."""
    return os.environ.get("DRY_RUN") or "false"


def source_images(image_path: str, tag: str) -> list[str]:
    """The real argv tail: one `<path>:<tag>-<arch>` per arch, no stray spaces."""
    return ["%s:%s-%s" % (image_path, tag, arch) for arch in ARCHS]


def source_images_field(image_path: str, tag: str) -> str:
    """The twin's `$SOURCE_IMAGES` string, LEADING SPACE INCLUDED.

    See the module docstring. This is the value the human-readable lines interpolate, and it is not the same thing as `source_images()`.
    """
    field = ""
    for ref in source_images(image_path, tag):
        field = "%s %s" % (field, ref)
    return field


def platform_lines(inspect_stdout: str) -> list[str]:
    """`grep -E "(Platform:|Name:)" | head -10` over one stream.

    grep works on LINES and re-adds the newline it split on, so a final line
    with no terminator still prints with one. `splitlines()` plus a per-line
    `print` reproduces that; a trailing empty segment is not a line and is dropped, which is also what grep does.
    """
    hits = [
        line for line in inspect_stdout.splitlines() if any(n in line for n in PLATFORM_NEEDLES)
    ]
    return hits[:PLATFORM_HEAD]


def usage(prog: str) -> str:
    """`-h | --help` (:58-70): STDOUT, exit 0."""
    return "\n".join(
        [
            "Usage: %s (--image NAME | --image-path PATH) --tag TAG [--push-latest] [--dry-run]"
            % prog,
            "",
            "Create multi-arch Docker manifest from architecture-specific images",
            "",
            "Options:",
            "  --image NAME      Image name relative to PUBLISH_DOCKER_REGISTRY (api, bridge, ...)",
            "  --image-path PATH Full image path (e.g., ghcr.io/rediacc/server)",
            "  --tag TAG         Tag for the manifest",
            "  --push-latest     Also create and push :latest manifest",
            "  --dry-run         Preview without creating manifest",
        ]
    )


class HelpRequested(Exception):  # noqa: N818
    """`-h | --help`: usage on stdout, exit 0."""


class UnboundVariable(Exception):  # noqa: N818
    """One `set -u` death, in bash's wording, on stderr, exit 1."""

    def __init__(self, name: str, line: int) -> None:
        super().__init__("%s: line %d: %s: unbound variable" % (sys.argv[0], line, name))


class Refusal(Exception):  # noqa: N818
    """A `log_error` followed by `exit 1`."""


class Options:
    """The five variables the twin's `while` loop sets (:31-79)."""

    def __init__(self) -> None:
        self.image_name = ""
        self.image_path = ""
        self.tag = ""
        self.push_latest = False
        self.dry_run = dry_run_default()


def parse_args(argv: list[str]) -> Options:
    """The twin's argument loop, `set -u` deaths included."""
    opts = Options()
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag in ("--image", "--image-path", "--tag"):
            if i + 1 >= len(argv):
                raise UnboundVariable("$2", UNBOUND_LINES[flag])
            value = argv[i + 1]
            if flag == "--image":
                opts.image_name = value
            elif flag == "--image-path":
                opts.image_path = value
            else:
                opts.tag = value
            i += 2
        elif flag == "--push-latest":
            opts.push_latest = True
            i += 1
        elif flag == "--dry-run":
            opts.dry_run = "true"
            i += 1
        elif flag in ("-h", "--help"):
            raise HelpRequested
        else:
            raise Refusal("Unknown option: %s" % flag)
    return opts


def validate(opts: Options) -> None:
    """`--image`/`--image-path` exclusivity then `--tag`, in the twin's ORDER.

    The order is observable: `--image a --image-path b` with no `--tag` reports the exclusivity error, not the missing tag.
    """
    if opts.image_name and opts.image_path:
        raise Refusal("--image and --image-path are mutually exclusive")
    if not opts.image_name and not opts.image_path:
        raise Refusal("--image or --image-path is required")
    if not opts.tag:
        raise Refusal("--tag is required")


def resolve_image_path(opts: Options) -> str:
    """`--image-path` wins as given; `--image` is prefixed with the registry."""
    if opts.image_path:
        return opts.image_path
    return "%s/%s" % (registry(), opts.image_name)


def _flush() -> None:
    """stdout before every spawn that inherits it. See `cleanup_staging`."""
    sys.stdout.flush()


def _docker(args: list[str], *, line: int | None, **kwargs) -> int:
    """One `docker` call. A missing binary is bash's own 127, not a traceback.

    bash prints `<script>: line <n>: docker: command not found` on the SHELL's stderr and the surrounding `if !` then takes its failure branch. `line` is where the call site sits in the twin, so a reader grepping a CI log for that message still finds it.

    `line=None` MEANS THE MESSAGE IS SUPPRESSED, and it is a distinction the
    twin makes: a redirection on the command applies to the shell's own diagnostic too, so `docker ... &>/dev/null` prints NOTHING when docker is absent while `docker ... >/dev/null` prints the line. Measured, not assumed:

        $ bash -c 'if ! nope &>/dev/null; then echo taken; fi'
        taken
        $ bash -c 'if ! nope >/dev/null; then echo taken; fi'
        bash: line 1: nope: command not found
        taken
    """
    _flush()
    try:
        proc = subprocess.run(["docker", *args], check=False, **kwargs)
    except (FileNotFoundError, PermissionError) as exc:
        if line is not None:
            print(
                "%s: line %d: docker: %s" % (sys.argv[0], line, _bash_reason(exc)),
                file=sys.stderr,
                flush=True,
            )
        return 127
    return proc.returncode


def _bash_reason(exc: OSError) -> str:
    """bash's wording for the two ways an exec fails."""
    if isinstance(exc, PermissionError):
        return "Permission denied"
    return "command not found"


def create_manifest(manifest_tag: str, sources: list[str]) -> bool:
    """`create_manifest()` (:124-140). False is the twin's `return 1`."""
    log.step("Creating manifest: %s" % manifest_tag)

    created = _docker(
        ["buildx", "imagetools", "create", "-t", manifest_tag, *sources],
        line=DOCKER_CREATE_LINE,
    )
    if created != 0:
        log.error("Failed to create manifest: %s" % manifest_tag)
        return False

    log.info("Created manifest: %s" % manifest_tag)
    return True


def verify_manifest(manifest_tag: str) -> None:
    """The twin's verification block (:158-171). Advisory: never changes the exit."""
    log.step("Verifying manifest...")
    quiet = _docker(
        ["buildx", "imagetools", "inspect", manifest_tag],
        line=None,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if quiet != 0:
        log.warn("Could not verify manifest (may still be pushing)")
        return

    log.info("Manifest verified: %s" % manifest_tag)

    # The SECOND inspect, with `2>/dev/null` and the pipeline. Its exit status is swallowed by the twin's `|| true`, so nothing here reads it.
    _flush()
    try:
        shown = subprocess.run(
            ["docker", "buildx", "imagetools", "inspect", manifest_tag],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except (FileNotFoundError, PermissionError):
        # SILENT, like the twin: `2>/dev/null` on the command suppresses bash's own `command not found` too (see `_docker`). Unreachable in practice, because the quiet call above already proved the binary exists.
        return
    for line in platform_lines(shown.stdout):
        print(line, flush=True)


def main(argv: list[str]) -> int:
    try:
        opts = parse_args(argv)
        validate(opts)
    except HelpRequested:
        print(usage(sys.argv[0]), flush=True)
        return 0
    except UnboundVariable as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1
    except Refusal as exc:
        log.error(str(exc))
        return 1

    image_path = resolve_image_path(opts)
    manifest_tag = "%s:%s" % (image_path, opts.tag)

    log.step("Creating multi-arch manifest for %s:%s" % (opts.image_name or image_path, opts.tag))

    field = source_images_field(image_path, opts.tag)
    log.info("  Manifest: %s" % manifest_tag)
    log.info("  Sources: %s" % field)

    if opts.dry_run == "true":
        log.info("[DRY-RUN] Would create manifest:")
        print("  docker buildx imagetools create -t %s %s" % (manifest_tag, field), flush=True)
        if opts.push_latest:
            print(
                "  docker buildx imagetools create -t %s:latest %s" % (image_path, field),
                flush=True,
            )
        return 0

    sources = source_images(image_path, opts.tag)

    # `set -e` at the top level: a failing `create_manifest` kills the script right here, with no summary and no verification.
    if not create_manifest(manifest_tag, sources):
        return 1

    if opts.push_latest and not create_manifest("%s:latest" % image_path, sources):
        return 1

    verify_manifest(manifest_tag)

    print(flush=True)
    log.info("Manifest creation complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
