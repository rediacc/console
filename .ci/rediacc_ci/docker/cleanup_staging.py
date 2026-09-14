#!/usr/bin/env python3
"""Port of `.ci/scripts/docker/cleanup-staging.sh`.

Deletes the staging Docker tags from GHCR after a Phase 1 staging failure or a
Phase 2 commit. One GHCR package version per image in `PUBLISH_IMAGES`, found by
listing the org's container package versions and picking the one whose tag list
contains the staging tag.

THE `staging-` PREFIX GUARD IS THE WHOLE SAFETY MODEL, so it is reproduced
character for character rather than "improved". The twin refuses any tag that
does not start with `staging-` before it reaches a single API call, which is
what makes a stray invocation unable to delete `edge`, `stable`, `latest` or a
semver. `rediacc_ci.release.cleanup_channel_docker_tags` documents the same
guard from the caller's side, and `.ci/scripts/quality/check-staging-tag-guard.sh`
is a gate whose subject is that this guard exists. A port that widened it would
delete the rail three separate things are leaning on.

WHAT IS DELETED IS A PACKAGE VERSION, NOT A TAG. GHCR has no delete-one-tag API,
so the twin resolves a version id and deletes the VERSION. A version carrying a
second tag loses that tag too. Reproduced as-is and pinned by
`test_a_version_carrying_a_second_tag_is_deleted_whole`; changing it is a
cutover-box decision.

jq IS SHELLED OUT TO, NOT REIMPLEMENTED, and the reason is the two filters
rather than laziness. `type == "array"` under `jq -e` is a REFUSAL TEST on
arbitrary bytes -- the twin merges gh's stderr into the response with `2>&1`
precisely so that an error page fails to parse -- and
`.[] | select(.metadata.container.tags | index("<tag>")) | .id` has jq's own
null-tolerance semantics at three levels (`.metadata` absent, `.container`
absent, `.tags` null). `json.loads` plus hand-written `.get()` chains is a second
answer to a question the twin already answered, and the difference would decide
which package version gets DELETED.

THE STAGING TAG IS INTERPOLATED INTO THE jq PROGRAM UNQUOTED, as in the twin. A
tag containing a `"` produces a jq syntax error, jq's stderr goes to /dev/null,
the filter yields nothing and the run reports "may already be deleted". That is
a real (small) defect of the twin's, recorded by
`test_defect_a_quote_in_the_tag_is_swallowed_as_already_deleted` rather than
fixed here.

STREAM DISCIPLINE. Every log line is stderr (common.sh's loggers) and the two
blank separator lines are stdout (`echo ""`). The DELETE call's own stdout is
INHERITED -- the twin redirects only its stderr -- so `sys.stdout` is flushed
before each spawn, or Python's block buffering against a pipe would move the two
blank lines behind gh's output.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

from rediacc_ci import log

# ---------------------------------------------------------------------------
# The twin's constants
# ---------------------------------------------------------------------------

# `.ci/config/constants.sh:169`, `readonly PUBLISH_IMAGES=("renet" "rdc")`.
# Restated rather than sourced (constants.sh hard-requires
# `.devcontainer/toolchain.env` and `exit 1`s without it, which would make this
# port refuse on a checkout where the twin's own dependency is merely absent),
# and pinned against constants.sh by a staleness alarm in the differential.
PUBLISH_IMAGES = ("renet", "rdc")

# `.ci/config/constants.sh:162`,
# `PUBLISH_DOCKER_REGISTRY="${PUBLISH_DOCKER_REGISTRY:-ghcr.io/rediacc}"`.
# `:-` means unset OR EMPTY takes the default, which is why the read below is
# `or` rather than a two-argument `get`.
REGISTRY_DEFAULT = "ghcr.io/rediacc"

# The prefix `${PUBLISH_DOCKER_REGISTRY#ghcr.io/}` strips (twin :67).
GHCR_PREFIX = "ghcr.io/"

# Where `set -u` kills the twin when a value-taking flag is last on the command
# line. bash names the line of the ASSIGNMENT, not of the `case` arm, and the
# port reproduces the whole message including that number so a caller who greps
# CI logs for it still finds it. The differential asserts the constant still
# points at `STAGING_TAG="$2"` in the twin, so a twin edit reds here rather than
# silently drifting.
UNBOUND_LINE_TAG = 26


def registry() -> str:
    """`$PUBLISH_DOCKER_REGISTRY` with constants.sh's default."""
    return os.environ.get("PUBLISH_DOCKER_REGISTRY") or REGISTRY_DEFAULT


def dry_run_default() -> str:
    """`DRY_RUN="${DRY_RUN:-false}"`, before `--dry-run` can override it.

    The twin compares `== "true"` exactly, so `DRY_RUN=1` is NOT a dry run. Kept
    as a string rather than a bool for that reason: a bool here would invite
    `bool(os.environ.get("DRY_RUN"))` and turn `DRY_RUN=0` into a preview.
    """
    return os.environ.get("DRY_RUN") or "false"


def org_of(registry_url: str) -> str:
    """`${REG#ghcr.io/}` then `${ORG%%/*}` (twin :67-68).

    `%%/*` removes the LONGEST trailing match of `/*`, i.e. keeps everything
    before the FIRST slash. Note that a non-GHCR registry falls through the
    prefix strip and yields the HOST as the org, which is the twin's behaviour
    and is wrong for any registry that is not ghcr.io; the differential records
    it as `test_defect_a_non_ghcr_registry_yields_the_host_as_the_org`.
    """
    # `removeprefix` IS `${VAR#prefix}`: strip if present, leave alone if not.
    return registry_url.removeprefix(GHCR_PREFIX).split("/", 1)[0]


def is_staging_tag(tag: str) -> bool:
    """`[[ "$STAGING_TAG" =~ ^staging- ]]`: an anchored ERE on the prefix."""
    return re.match(r"staging-", tag) is not None


def versions_path(org: str, package: str) -> str:
    """The list endpoint the twin builds at :83."""
    return "/orgs/%s/packages/container/%s/versions" % (org, package)


def version_delete_path(org: str, package: str, version_id: str) -> str:
    """The delete endpoint at :103. `version_id` is interpolated RAW.

    That matters: jq can return more than one id, joined by a newline, and the
    twin puts the whole multi-line string into the URL. See
    `test_defect_two_versions_sharing_a_tag_build_one_malformed_url`.
    """
    return "%s/%s" % (versions_path(org, package), version_id)


def tag_filter(tag: str) -> str:
    """The jq program at :95, with the tag interpolated unquoted, as in bash."""
    return '.[] | select(.metadata.container.tags | index("%s")) | .id' % tag


def usage(prog: str) -> str:
    """`-h | --help` (:32-44). STDOUT, exit 0, and it names the images."""
    return "\n".join(
        [
            "Usage: %s --tag STAGING_TAG [--dry-run]" % prog,
            "",
            "Delete staging Docker tags from GHCR registry.",
            "",
            "Options:",
            "  --tag TAG    Staging tag to delete (e.g., staging-abc123...)",
            "  --dry-run    Preview without executing",
            "",
            "Images to clean: %s" % " ".join(PUBLISH_IMAGES),
        ]
    )


class HelpRequested(Exception):  # noqa: N818
    """`-h | --help`: print usage on stdout and exit 0."""


class UnboundVariable(Exception):  # noqa: N818
    """One `set -u` death, in bash's own wording, on stderr, exit 1."""

    def __init__(self, name: str, line: int) -> None:
        super().__init__("%s: line %d: %s: unbound variable" % (sys.argv[0], line, name))


class Refusal(Exception):  # noqa: N818
    """A `log_error` followed by `exit 1`."""


class Options:
    """The two variables the twin's `while` loop sets (:20-52)."""

    def __init__(self) -> None:
        self.staging_tag = ""
        self.dry_run = dry_run_default()


def parse_args(argv: list[str]) -> Options:
    """The twin's argument loop, including the `set -u` death on a bare `--tag`."""
    opts = Options()
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag == "--tag":
            if i + 1 >= len(argv):
                raise UnboundVariable("$2", UNBOUND_LINE_TAG)
            opts.staging_tag = argv[i + 1]
            i += 2
        elif flag == "--dry-run":
            opts.dry_run = "true"
            i += 1
        elif flag in ("-h", "--help"):
            raise HelpRequested
        else:
            raise Refusal("Unknown option: %s" % flag)
    return opts


def _flush() -> None:
    """stdout before every spawn that INHERITS it.

    Python block-buffers stdout against a pipe; the child writes straight to the
    descriptor. Without this the two `echo ""` separators arrive after gh's own
    output, with byte-identical content in the wrong order.
    """
    sys.stdout.flush()


def _gh_list(org: str, package: str) -> str:
    """`api_response=$(gh api <path> --paginate 2>&1) || true` (:83-85).

    STDERR IS MERGED INTO THE VALUE ON PURPOSE and the exit code is discarded:
    the twin's next step is a jq parse, so a 404 body, a rate-limit warning or a
    `command not found` all fail the `type == "array"` test the same way. Command
    substitution strips trailing newlines, which `rstrip("\\n")` reproduces.

    THE MERGE IS `stderr=STDOUT`, NOT `stdout + stderr`. Concatenating two
    captured buffers puts every stderr byte after every stdout byte, while
    `2>&1` hands the child ONE descriptor and preserves the interleaving. A gh
    that prints a warning before its JSON would parse under one and not the
    other.
    """
    argv = ["gh", "api", versions_path(org, package), "--paginate"]
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    except (FileNotFoundError, PermissionError) as exc:
        # bash writes `<script>: line N: gh: <reason>` INTO the captured value,
        # not to the terminal, because `2>&1` is inside the substitution. The
        # exact text is unobservable (it is only ever fed to jq, which rejects
        # it), so the shape is reproduced and the outcome is identical.
        return "%s: gh: %s" % (sys.argv[0], exc.strerror)
    return proc.stdout.rstrip("\n")


def _jq(program: str, payload: str, *, exit_status: bool) -> subprocess.CompletedProcess[str]:
    """`echo "$payload" | jq [-e|-r] '<program>'` with the twin's redirections.

    `echo` appends a newline, so the payload does too. `exit_status` picks
    between the `-e` refusal test (:88) and the `-r` extraction (:94-95); both
    have their stderr discarded by the twin.
    """
    flag = "-e" if exit_status else "-r"
    return subprocess.run(
        ["jq", flag, program],
        input=payload + "\n",
        capture_output=True,
        text=True,
        check=False,
    )


def looks_like_json_array(payload: str) -> bool:
    """`echo "$x" | jq -e 'type == "array"' >/dev/null 2>&1` (:88).

    A missing jq is a non-zero status under bash too (`command not found`, with
    both streams already redirected), so it takes the same branch here.
    """
    try:
        proc = _jq('type == "array"', payload, exit_status=True)
    except (FileNotFoundError, PermissionError):
        return False
    return proc.returncode == 0


def extract_version_id(payload: str, tag: str) -> str:
    """`version_id=$(echo "$x" | jq -r '<filter>' 2>/dev/null || true)` (:94-95).

    Returns jq's stdout with trailing newlines stripped, exactly as command
    substitution does, so TWO matching ids come back as `"111\\n222"` rather
    than as a list. Preserving that is the point: the twin then splices the
    whole thing into a URL.
    """
    try:
        proc = _jq(tag_filter(tag), payload, exit_status=False)
    except (FileNotFoundError, PermissionError):
        return ""
    return proc.stdout.rstrip("\n")


def _gh_delete(org: str, package: str, version_id: str) -> bool:
    """`gh api -X DELETE "<path>" 2>/dev/null` (:103).

    STDOUT IS INHERITED, stderr is discarded. Discarding stderr is why a failure
    here reports no reason at all; see the defect note in the differential.
    """
    argv = ["gh", "api", "-X", "DELETE", version_delete_path(org, package, version_id)]
    _flush()
    try:
        proc = subprocess.run(argv, stderr=subprocess.DEVNULL, check=False)
    except (FileNotFoundError, PermissionError):
        return False
    return proc.returncode == 0


def delete_staging_tag(image_name: str, opts: Options, org: str, reg: str) -> bool:
    """`delete_staging_tag()` (:70-110). True is the twin's `return 0`."""
    package_name = image_name
    full_image = "%s/%s:%s" % (reg, image_name, opts.staging_tag)

    log.step("Deleting staging tag for %s: %s" % (image_name, opts.staging_tag))

    if opts.dry_run == "true":
        log.info("[DRY-RUN] Would delete: %s" % full_image)
        return True

    api_response = _gh_list(org, package_name)

    if not looks_like_json_array(api_response):
        log.warn("Package %s not found or not accessible (may not exist yet)" % package_name)
        return True

    version_id = extract_version_id(api_response, opts.staging_tag)
    if not version_id:
        log.warn(
            "Staging tag not found for %s:%s (may already be deleted)"
            % (image_name, opts.staging_tag)
        )
        return True

    if _gh_delete(org, package_name, version_id):
        log.info("Deleted staging tag: %s" % full_image)
        return True
    log.error("Failed to delete staging tag for %s" % image_name)
    return False


def main(argv: list[str]) -> int:
    try:
        opts = parse_args(argv)
    except HelpRequested:
        print(usage(sys.argv[0]), flush=True)
        return 0
    except UnboundVariable as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1
    except Refusal as exc:
        log.error(str(exc))
        return 1

    if not opts.staging_tag:
        log.error("--tag is required")
        return 1

    if not is_staging_tag(opts.staging_tag):
        log.error("Tag must start with 'staging-' prefix for safety")
        return 1

    reg = registry()
    org = org_of(reg)

    deleted = 0
    failed = 0

    log.step("Cleaning up staging tags: %s" % opts.staging_tag)
    print(flush=True)

    for img in PUBLISH_IMAGES:
        if delete_staging_tag(img, opts, org, reg):
            deleted += 1
        else:
            failed += 1

    print(flush=True)
    if failed > 0:
        log.error("Cleanup summary: %d succeeded, %d failed" % (deleted, failed))
        return 1
    log.info("Cleanup summary: %d succeeded" % deleted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
