"""Port of `.ci/scripts/release/cleanup-channel-docker-tags.sh`.

Deletes the staging channel Docker tag after cd-v2.yml has retagged its images
to the released semver. Non-critical by design: every outcome is written to the
step summary and the script still exits 0, because a channel tag left behind in
GHCR is harmless.

THE `staging-` GUARD IS REPRODUCED, NOT ROUTED AROUND, and the twin's header is
emphatic about why. `cleanup-staging.sh` accepts only `staging-*` tags
deliberately, so a stray call cannot delete a real one; `CHANNEL` is `edge` or
`stable`, so the guard rejects it every single release. That is a KNOWN GAP with
its own summary text, not a token-scope problem, and a port that widened the
guard to "make the cleanup work" would remove the safety rail the twin exists to
respect. The first branch below therefore never calls anything at all, which is
the branch production actually takes.

THE THREE OUTCOMES ARE THREE DIFFERENT SUMMARY BLOCKS, and the summary file is
the whole observable of this script: stdout and stderr carry only whatever
`cleanup-staging.sh` itself prints. So the port appends line by line with an
open-append-close per line, exactly as the twin's repeated `>>` redirects do,
rather than buffering the block and writing once. `GITHUB_STEP_SUMMARY` is
routinely pointed at `/dev/stdout` when this is run by hand, and a buffered
write would reorder the block against the subprocess's own inherited output.

`cleanup-staging.sh` IS FORWARDED TO RATHER THAN REIMPLEMENTED, the same
reasoning `rediacc_ci.release.backfill_write_sentinel` records for the sentinel
writer: it is a whole separate contract (GHCR package resolution, the
`PUBLISH_IMAGES` table from `constants.sh`, `gh api --method DELETE`) that
already has one implementation. Its stdout and stderr are INHERITED, not
captured, because the twin does not capture them either -- the reader of a CI
log sees the delete's own output interleaved with the summary block.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

SELF = "cleanup-channel-docker-tags.py"

# `.ci/rediacc_ci/release/cleanup_channel_docker_tags.py` -> `.ci` -> repo root.
# The twin resolves the same file as `$SCRIPT_DIR/../docker/cleanup-staging.sh`
# from `.ci/scripts/release`; both spellings are three levels up plus the same
# tail, even though the two files sit in different directories.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_CLEANUP_STAGING = os.path.join(_ROOT, ".ci", "scripts", "docker", "cleanup-staging.sh")

_HEADING = "## Cleanup Channel Tags"

# The KNOWN-GAP block, verbatim from the twin (:63-65). Reproduced as constants
# so a reader can diff the two files line for line without reading Python.
_NOT_CLEANED = "**Channel tag NOT cleaned up:** %s"
_NOT_CLEANED_WHY = (
    "cleanup-staging.sh only deletes `staging-*` tags by design, so a channel tag can never "
    "be removed through it. This is a KNOWN GAP, not a token-scope problem, and it is "
    "non-critical: a channel tag left in GHCR is harmless."
)
_CLEANED = "**Channel tag cleaned up:** %s"
_FAILED = "**Failed to clean up channel tag:** %s"
_FAILED_WHY = "The delete call failed; check that GH_TOKEN carries `delete:packages`."


def _require_var(name: str) -> str:
    """`${NAME:?message}`: unset AND empty both refuse, with exit 1.

    The wording differs from bash's own `<script>: line N: NAME: ...` prefix and
    is not meant to match it; the exit code and the named variable are what the
    differential compares, same as every sibling port in this package.
    """
    value = os.environ.get(name)
    if not value:
        print("%s: %s must be set" % (SELF, name), file=sys.stderr)
        raise SystemExit(1)
    return value


def append_summary(path: str, line: str) -> None:
    """One `echo "$line" >>"$GITHUB_STEP_SUMMARY"`, open and close included."""
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def is_staging_tag(channel: str) -> bool:
    """`[[ "$CHANNEL" =~ ^staging- ]]`, an anchored ERE match on the prefix."""
    return re.match(r"staging-", channel) is not None


def _delete_channel_tag(channel: str) -> bool:
    """Run the twin's `elif`: true when `cleanup-staging.sh --tag <channel>` exits 0.

    A MISSING SCRIPT IS THE `else` BRANCH, not a traceback. Under bash a
    `command not found` inside an `elif` is a non-zero status like any other and
    falls through to the failure summary; `FileNotFoundError` here would instead
    abort before the summary was written, which is the one difference that would
    change what a reader of the step summary sees.
    """
    try:
        proc = subprocess.run([_CLEANUP_STAGING, "--tag", channel], check=False)
    except (FileNotFoundError, PermissionError) as exc:
        print("%s: %s" % (_CLEANUP_STAGING, exc.strerror), file=sys.stderr)
        return False
    return proc.returncode == 0


def main(argv: list[str]) -> int:
    del argv
    channel = _require_var("CHANNEL")
    summary = _require_var("GITHUB_STEP_SUMMARY")

    append_summary(summary, _HEADING)
    append_summary(summary, "")

    if not is_staging_tag(channel):
        append_summary(summary, _NOT_CLEANED % channel)
        append_summary(summary, _NOT_CLEANED_WHY)
    elif _delete_channel_tag(channel):
        append_summary(summary, _CLEANED % channel)
    else:
        append_summary(summary, _FAILED % channel)
        append_summary(summary, _FAILED_WHY)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
