#!/usr/bin/env python3
"""Port of `.ci/scripts/docker/retag-image.sh`.

Promotes a CI-tagged image to a release version with `docker buildx imagetools create -t <dst> <src>`, which copies the whole multi-arch manifest without pulling a single layer. Drives one image, one full image path, or every name in `PUBLISH_IMAGES`.

`--skip-if-exists` COMPARES DIGESTS, NOT EXISTENCE, and the twin's comment says why in the sharpest terms in this directory: a destination tag left over from a PREVIOUS failed release at the same version would otherwise "silently lock the new image out of promotion", and the symptom is post-publish pull tests reading the OLD version. So the skip fires only when `<dst>` and `<src>`
resolve to the
same `{{.Manifest.Digest}}`, and an unreadable SOURCE falls THROUGH to the retag
rather than skipping. Both halves are reproduced, and both have their own case in the differential, because either one inverted turns an idempotent retry into a silent no-op.

`--image` VERSUS `--image-path` IS DECIDED BY A SLASH, INSIDE `retag_image`.
The twin does not pass a mode through; it looks for `/` in the name it was
handed. Two consequences it never states, both kept and both pinned:

  * `--image ghcr.io/acme/thing` is treated as a FULL PATH, so `--image` does
    not always mean "relative to PUBLISH_DOCKER_REGISTRY".
  * `--image-path server` (no slash) is treated as RELATIVE and gets the
    registry prefixed, so `--image-path` does not always bypass it either.

`basename` IS bash's, NOT `os.path.basename`. They disagree on a trailing slash: `basename a/b/` is `b`, `os.path.basename("a/b/")` is `""`. An empty label would print `Re-tagging : a -> b`, so `_basename` strips trailing slashes first and `test_basename_matches_bash_on_trailing_slashes` checks it against the real tool.

THE SUMMARY LINE IS `log_info` EVEN WHEN THINGS FAILED, so a run that promoted nothing prints a green tick beside `0 succeeded, 2 failed` and only the exit code says otherwise. That is the twin's, and `cleanup-staging.sh` one directory over does the opposite (`log_error` on the failing summary), so the two are inconsistent with each other. Reproduced, and recorded as
`test_defect_the_failing_summary_is_still_a_green_tick`.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci import log

# --------------------------------------------------------------------------- The twin's constants ---------------------------------------------------------------------------

# `.ci/config/constants.sh:169` and `:162`. Restated for the reason `cleanup_staging` records, and pinned against constants.sh by the differential.
PUBLISH_IMAGES = ("renet", "rdc")
REGISTRY_DEFAULT = "ghcr.io/rediacc"

# The digest format string the twin hands `imagetools inspect` (twin :148,:150).
DIGEST_FORMAT = "{{.Manifest.Digest}}"

# `set -u` death sites: the line of each `VAR="$2"` assignment in the twin.
UNBOUND_LINES = {"--image": 42, "--image-path": 46, "--from": 54, "--to": 58}

# docker call sites, for the `command not found` line number bash would print. The two `--skip-if-exists` probes are absent on purpose: they carry `2>/dev/null`, which suppresses the shell's own diagnostic as well.
DRY_RUN_INSPECT_LINE = 161
RETAG_CREATE_LINE = 172
LATEST_CREATE_LINE = 178


def registry() -> str:
    """`$PUBLISH_DOCKER_REGISTRY` with constants.sh's default."""
    return os.environ.get("PUBLISH_DOCKER_REGISTRY") or REGISTRY_DEFAULT


def dry_run_default() -> str:
    """`DRY_RUN="${DRY_RUN:-false}"`, compared `== "true"` and nothing else."""
    return os.environ.get("DRY_RUN") or "false"


def _basename(path: str) -> str:
    """`basename "$path"`, which is not `os.path.basename`. See the docstring."""
    stripped = path.rstrip("/")
    if not stripped:
        return "/" if path else ""
    return stripped.rsplit("/", 1)[-1]


def resolve(name: str) -> tuple[str, str]:
    """`retag_image`'s first six lines (:120-129): (image_root, label).

    A `/` anywhere in the name means "already a full path".
    """
    if "/" in name:
        return name, _basename(name)
    return "%s/%s" % (registry(), name), name


def usage(prog: str) -> str:
    """`-h | --help` (:73-89): STDOUT, exit 0, and it names the images."""
    return "\n".join(
        [
            "Usage: %s --image NAME --from CI_TAG --to VERSION [--push-latest]" % prog,
            "       %s --image-path PATH --from CI_TAG --to VERSION [--push-latest]" % prog,
            "       %s --all --from CI_TAG --to VERSION [--push-latest]" % prog,
            "",
            "Options:",
            "  --image NAME       Re-tag image relative to PUBLISH_DOCKER_REGISTRY",
            "  --image-path PATH  Re-tag full image path (e.g., ghcr.io/rediacc/server)",
            "  --all              Re-tag all images in PUBLISH_IMAGES",
            "  --from TAG         Source CI tag",
            "  --to VERSION       Target semantic version",
            "  --push-latest      Also push :latest tag",
            "  --skip-if-exists   Skip if destination exists (idempotent)",
            "  --dry-run          Preview without executing",
            "",
            "Available images: %s" % " ".join(PUBLISH_IMAGES),
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
    """The eight variables the twin's `while` loop sets (:28-104)."""

    def __init__(self) -> None:
        self.image_name = ""
        self.image_path = ""
        self.retag_all = False
        self.from_tag = ""
        self.to_tag = ""
        self.push_latest = False
        self.skip_if_exists = False
        self.dry_run = dry_run_default()


def parse_args(argv: list[str]) -> Options:
    """The twin's argument loop, `set -u` deaths included."""
    opts = Options()
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag in ("--image", "--image-path", "--from", "--to"):
            if i + 1 >= len(argv):
                raise UnboundVariable("$2", UNBOUND_LINES[flag])
            value = argv[i + 1]
            if flag == "--image":
                opts.image_name = value
            elif flag == "--image-path":
                opts.image_path = value
            elif flag == "--from":
                opts.from_tag = value
            else:
                opts.to_tag = value
            i += 2
        elif flag == "--all":
            opts.retag_all = True
            i += 1
        elif flag == "--push-latest":
            opts.push_latest = True
            i += 1
        elif flag == "--skip-if-exists":
            opts.skip_if_exists = True
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
    """The five checks at :92-113, IN ORDER, because the order is observable.

    `--from` and `--to` are demanded BEFORE the target-selection checks, so `retag-image.sh --all --image api` with no tags reports the missing `--from` rather than the mutual exclusion.
    """
    if not opts.from_tag:
        raise Refusal("--from is required")
    if not opts.to_tag:
        raise Refusal("--to is required")
    if opts.image_name and opts.image_path:
        raise Refusal("--image and --image-path are mutually exclusive")
    if opts.retag_all and (opts.image_name or opts.image_path):
        raise Refusal("--all is mutually exclusive with --image / --image-path")
    if not opts.retag_all and not opts.image_name and not opts.image_path:
        raise Refusal("--image, --image-path, or --all required")


def _flush() -> None:
    """stdout before every spawn that inherits it. See `cleanup_staging`."""
    sys.stdout.flush()


def _bash_reason(exc: OSError) -> str:
    """bash's wording for the two ways an exec fails."""
    if isinstance(exc, PermissionError):
        return "Permission denied"
    return "command not found"


def _docker(args: list[str], *, line: int | None, **kwargs) -> int:
    """One `docker` call. `line=None` means the twin's redirection hides bash's
    own `command not found` for that call site; see `create_manifest._docker`.
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


def digest_of(ref: str) -> str:
    """`$(docker buildx imagetools inspect <ref> --format '<fmt>' 2>/dev/null || true)`.

    Empty on ANY failure, including a missing binary, because both the twin's `2>/dev/null` and its `|| true` are unconditional. Command substitution strips trailing newlines.
    """
    _flush()
    try:
        proc = subprocess.run(
            ["docker", "buildx", "imagetools", "inspect", ref, "--format", DIGEST_FORMAT],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except (FileNotFoundError, PermissionError):
        return ""
    return proc.stdout.rstrip("\n")


def retag_image(name: str, opts: Options) -> bool:
    """`retag_image()` (:115-187). False is the twin's `return 1`."""
    image_root, label = resolve(name)
    src = "%s:%s" % (image_root, opts.from_tag)
    dst = "%s:%s" % (image_root, opts.to_tag)
    dst_latest = "%s:latest" % image_root

    log.step("Re-tagging %s: %s -> %s" % (label, opts.from_tag, opts.to_tag))

    if opts.skip_if_exists:
        dst_digest = digest_of(dst)
        if dst_digest:
            src_digest = digest_of(src)
            if src_digest and dst_digest == src_digest:
                log.info("Destination matches source digest, skipping: %s (%s)" % (dst, dst_digest))
                return True
            # `${src_digest:-unknown}`: empty means the SOURCE could not be read,
            # and the twin says so rather than pretending the digests differ.
            log.info(
                "Destination exists but digest differs (dst=%s src=%s), retagging: %s"
                % (dst_digest, src_digest or "unknown", dst)
            )

    if opts.dry_run == "true":
        log.info("[DRY-RUN] Verifying source image: %s" % src)
        probe = _docker(
            ["buildx", "imagetools", "inspect", src],
            line=DRY_RUN_INSPECT_LINE,
            stdout=subprocess.DEVNULL,
        )
        if probe != 0:
            log.error("[DRY-RUN] Failed to inspect source image: %s" % src)
            return False
        log.info("[DRY-RUN] Verified source exists, would re-tag to: %s" % dst)
        if opts.push_latest:
            log.info("[DRY-RUN] Would also tag: %s" % dst_latest)
        return True

    if _docker(["buildx", "imagetools", "create", "-t", dst, src], line=RETAG_CREATE_LINE) != 0:
        log.error("Failed to re-tag %s -> %s" % (src, dst))
        return False

    if opts.push_latest:
        latest = _docker(
            ["buildx", "imagetools", "create", "-t", dst_latest, src],
            line=LATEST_CREATE_LINE,
        )
        if latest != 0:
            log.error("Failed to re-tag %s -> %s" % (src, dst_latest))
            return False
        log.info("Pushed :latest tag")
        # The `:stable` tag is pushed by promote-stable.yml after the 7-day soak.

    log.info("Re-tagged %s successfully" % label)
    return True


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

    failed = 0
    retagged = 0

    if opts.retag_all:
        log.step("Re-tagging all images...")
        for img in PUBLISH_IMAGES:
            if retag_image(img, opts):
                retagged += 1
            else:
                failed += 1
    else:
        # `"${IMAGE_NAME:-$IMAGE_PATH}"`. Which one is set was settled by
        # `validate`; `retag_image` re-derives the mode from the slash.
        target = opts.image_name or opts.image_path
        if retag_image(target, opts):
            retagged += 1
        else:
            failed += 1

    print(flush=True)
    log.info("Re-tag summary: %d succeeded, %d failed" % (retagged, failed))

    if failed > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
