#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/upload-repos-to-r2.sh`.

Uploads the built package repositories (`apt`, `rpm`, `apk`, `archlinux`) and the two channel install scripts to R2, then purges the Cloudflare cache for every URL it touched.

WHY THE CACHE-CONTROL IS `no-cache` AND NOT `immutable`, carried over from the twin's header because it is the reason this script exists in its own file:
package-manager channel paths reuse filenames across releases, so
`cli/edge/rdc-0.9.13.deb` can serve DIFFERENT bytes from one CI run to the next. Marking those immutable let CF keep a previous run's body under a URL the next run's APKINDEX points at with a different sha256, and `BAD signature` cascaded. `no-cache` means CF never caches, so there is no stale body to go stale. Truly versioned paths (`cli/v<semver>/`, `npm/<channel>/*.tgz`) keep
their one-year immutable policy and are `upload-to-r2.sh`'s business, not this file's.

NOTHING HERE REACHES R2 OR CLOUDFLARE IN A TEST. `aws` and (through `cf-purge-urls.sh`) `curl` are the two external tools that carry a credential, so the differential (`.ci/rediacc_ci/tests/test_deploy_upload_repos_to_r2.py`) puts RECORDING FAKES for both on a scratch PATH. The `aws` fake logs its exact argv and, for a `cp`, the CONTENT of the file being uploaded. That content log
is load bearing: the install scripts are REWRITTEN on the way past (the default channel is substituted), and two implementations can print an identical `Repos uploaded to R2 channel: edge` while uploading a script that still points at `stable`.

THREE EXTERNAL TOOLS ARE CALLED RATHER THAN REIMPLEMENTED, each for a measured reason and not for symmetry:

  * `find`, because ITS ORDER IS THE PURGE ORDER. The twin walks
    `find <dir> -type f` and appends one URL per line, and find emits directory
    order, not sorted order. Driven 2026-09-13 on a fixture: `InRelease` comes
    out BEFORE `dists/stable/Packages.gz`. `os.walk` is free to disagree, and
    then the JSON body posted to Cloudflare differs while every printed line
    matches.
  * `sed`, because the two substitutions are REGEX with `|` delimiters and an
    unescaped `${CHANNEL}` on the replacement side. A channel containing `&` or
    `|` therefore does something specific in sed and something else in
    `str.replace`. The channel is `edge`, `stable` or `pr-<n>` today, so this is
    latent rather than live, and a port that quietly normalised it would be
    deciding a question the twin has not decided.
  * `mktemp`, so the temporary path has the same SHAPE (`/tmp/tmp.XXXXXXXXXX`,
    honouring TMPDIR) as the twin's. That path appears in the `aws s3 cp` argv,
    which is the thing the differential compares.

`cf-purge-urls.sh` IS INVOKED AS THE BASH SCRIPT THE TWIN INVOKES, deliberately, even though `rediacc_ci.deploy.cf_purge_urls` exists and is itself a verified port. The acceptance rule for this wave is agreement with the LIVE twin, and the twin's observable behaviour includes that script's exact bytes; repointing a call site is a cutover-box decision, not this one's. `PURGE_SCRIPT`
names the path once so the cutover is a one-line change when the box that owns it lands.

`get_repo_root` IS REPRODUCED BY LOCATION, NOT BY cwd. The twin does `cd "$(get_repo_root)"`, and `get_repo_root` resolves `.ci/scripts/lib/../../..`
from `common.sh`'s own directory. This file sits at `.ci/rediacc_ci/deploy/`,
also three directories under the root, so the arithmetic is identical. It is `abspath`, NOT `realpath`, on purpose: bash's `cd` is logical, so a checkout reached through a symlink keeps the symlinked spelling on both sides. `paths.repo_root()` is deliberately not used, because it resolves symlinks and honours `$REDIACC_CI_ROOT`, and neither is a thing the twin does.

TWO VACUITY FACTS ABOUT THE TWIN, THE FIRST DELIBERATE AND THE SECOND NOT.
Neither is repaired here; this wave's acceptance rule is agreement with the live twin.

  1. THE `VACUOUS:` GUARD IS SCOPED NARROWLY AND SAYS SO (twin :123-127). A
     MISSING `dist/repos/<dir>` is legitimate, because not every channel builds
     every package format, so it is skipped. A directory that EXISTS and holds
     nothing is refused, because the sync uploaded nothing and the run would
     still report success.
  2. AN ENTIRELY EMPTY `dist/` IS A GREEN RUN THAT MOVED NOTHING. With no
     `dist/repos/*` directory and neither install script present, every loop body
     is skipped, `PURGE_URLS` stays empty, no purge runs, and the script prints
     `Repos uploaded to R2 channel: <channel>` and exits 0. Driven 2026-09-13.
     That line is the only thing a workflow log shows, and it is false. The guard
     in (1) cannot see it, because its subject is one directory rather than the
     upload as a whole. `AN_EMPTY_DIST_REPORTS_SUCCESS` names it so the
     differential can pin it by name rather than by restating the sentence.

FIVE `${VAR:?msg}` GUARDS, ONE DIVERGENCE. bash's own refusal names the bash
FILE and a bash LINE NUMBER and then the twin's message, which already begins
with the script name:

    .ci/scripts/deploy/upload-repos-to-r2.sh: line 49: CHANNEL: upload-repos-to-r2.sh: CHANNEL must be set

This port prints the `VAR: msg` half, on the same stream, with the same exit status 1. Identical ruling to `deploy/delete_r2_channel.py`. The ORDER of the guards is kept, and `require_cmd aws` runs BEFORE all five, so a run missing both the binary and every variable names the binary.

`:?` IS AN UNSET-OR-EMPTY TEST: `CHANNEL=` refuses exactly as an absent CHANNEL
does. Driven, because a port testing `"CHANNEL" in os.environ` would sail past it and then sync every package format to `s3://rediacc-releases/apt//`.

-----------------------------------------------------------------------------
RULE T DELTA: A TRANSIENT R2 FAILURE IS RETRIED (#4175e786)
-----------------------------------------------------------------------------
The twin ran each `aws s3 sync` and `aws s3 cp` once under `set -e`, so one transient R2 `IncompleteRead` (measured on 2026-09-24 on a large package) ended a release upload half-way. The port retries the two transfers up to three times, `RETRY_DELAY_S` apart, and only when aws's stderr names a failure a retry can change (`transfer_retry.is_transient`: a broken read, a timeout, a 5xx, a throttle). A refusal (`AccessDenied`, `NoSuchBucket`, an expired key) and anything unrecognised fails on the
first try exactly as the twin did, with byte-identical output. A retried transfer replays aws's own stderr each time, says `retrying (n/3)`, and a transfer that never succeeds ends with a line naming the cause and then aws's own status. `sync` and `cp` of one object are idempotent, which is what makes the repeat safe. Pinned by the `test_delta_*` cases at the end of the differential, each a fake `aws` that fails once and then succeeds, or always.

-----------------------------------------------------------------------------
DELTA: THE CHANNEL SNAPSHOT (PLAN-plan-per-pr-loop R2 follow-up)
-----------------------------------------------------------------------------
With `SNAPSHOT_VERSION` set (on the `edge` channel only; another channel is refused before any write), the run also writes the version's channel snapshot (`channel_snapshot`) after the channel upload and before the purge:

  1. every METADATA file of each `dist/repos/<fmt>` (what `promote_r2_to_stable.META_EXCLUDES` keeps out of phase 1) to `snapshots/v<V>/<fmt>/`, one `aws s3 sync` per format with the include filter that selects exactly those files: the same local files the channel sync has just uploaded;
  2. each stamped install script, the same temporary the channel upload used, to `snapshots/v<V>/cli/`;
  3. a listing of `snapshots/v<V>/`, which must show the cli part `upload_to_r2` wrote in the step before (`channel_snapshot.CLI_REQUIRED`), then the `.complete` marker LAST, naming every metadata key and every package file (with its size) of `dist/repos`.

A snapshot that cannot be completed fails the run with the reason. Unset, the run is the twin's, byte for byte.

-----------------------------------------------------------------------------
DELTA: EACH PACKAGE TREE KEEPS ONLY WHAT ITS INDEX LISTS (operator ruling 2026-10-06, "Current version only")
-----------------------------------------------------------------------------
The twin's `aws s3 sync` never deletes, so every release left its packages and, for rpm, its six content-hashed `repodata/` files behind: on 2026-10-06 `edge` held 21 versions (about 61 GB nobody's index named) and 924 stale repodata files. After the upload, the purge and the snapshot seal, each `<fmt>/<channel>/` this run built is PRUNED (`_prune_trees`, after `r2_promote.prune_tree`):

  1. UPLOAD FIRST. The prune runs only after every sync and copy above has returned 0.
  2. LIST, AND REQUIRE THE NEW BUILD. `<fmt>/<channel>/` is listed, and every file of `dist/repos/<fmt>` must be in that listing. One missing file refuses the prune with nothing deleted (`INCOMPLETE:`), so the index can never point at a package that a delete removed or an upload never landed.
  3. DELETE SECOND. Every listed key outside the keep set is deleted (`delete-objects`, batched, its per-key `Errors` read back).

THE KEEP SET is the build (`dist/repos/<fmt>`, every file of it), plus, on `edge` only, the package files named by the `.complete` marker of every OTHER version's channel snapshot that `check_soak_period` may still select (`in_walk`: newer than the version `cli/stable/manifest.json` names, or every snapshot when that manifest cannot be read). The promote of an older soaked version copies its packages from `<fmt>/edge/` and refuses when they are gone (`promote_r2_to_stable.verify_snapshot`), so deleting a candidate's packages would starve stable. Its METADATA is not kept: the snapshot holds its own copy under `snapshots/v<ver>/`. A candidate marker that cannot be read refuses the prune.

WHY NOT `aws s3 sync --delete`: see `r2_promote`'s docstring. It deletes in the same pass as the uploads, with no order between them, and it knows nothing of the candidate keep set.

THE FLOORS. A format whose `dist/repos/<fmt>` is missing is not pruned (and is skipped by the upload, as before); one that exists empty is already refused by the `VACUOUS:` guard before any write. Only `apt`, `rpm`, `apk` and `archlinux` under a one-segment channel are ever pruned: never `cli/`, `npm/`, the install scripts, `snapshots/` or another channel. `KEEPS_ONLY_WHAT_THE_INDEX_LISTS` names the delta.
A prune that fails after the upload and purge have succeeded fails the run with the reason; the next release prunes what this one could not.

The twin is unchanged: the differential strips this delta's calls and its `Pruned`/`Prune` lines from the port's side (`test_deploy_upload_repos_to_r2.py`, `_without_prune`) and pins the delta in its own `test_prune_*` cases.

K=5 LEDGER: `.ci/shadow/w7p6-upload-repos-to-r2.observations.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from rediacc_ci.core import common
from rediacc_ci.deploy import channel_snapshot, r2_promote, transfer_retry
from rediacc_ci.deploy.promote_r2_to_stable import META_EXCLUDES
from rediacc_ci.release import check_soak_period, check_stable_manifest
from rediacc_ci.well_known import RELEASES_BUCKET, RELEASES_ORIGIN

# The twin's own name, printed in its five guard messages and its one non-release-channel notice. A literal, because the bytes must survive the port.
SELF = "upload-repos-to-r2.sh"

# `for dir in apt rpm apk archlinux` (:114). ORDER MATTERS to both the call log and the purge list, which is how this port is proved equivalent.
FORMATS = ("apt", "rpm", "apk", "archlinux")

# `CC_MUTABLE="no-cache"` (:111). The whole subject of the header above.
CC_MUTABLE = "no-cache"

# The bucket and the public host, both hard-coded in the twin (:116, :135).
BUCKET = RELEASES_BUCKET
PUBLIC_HOST = RELEASES_ORIGIN

# Seconds between the attempts of a retried transfer (Rule T, #4175e786). A module constant, not an environment variable: the bash twin has no knob, and a test that must not sleep sets it directly.
RETRY_DELAY_S = 5.0

# `.ci/scripts/deploy/cf-purge-urls.sh` (:162), relative to the repository root the twin cd's into. Named once so the cutover to `cf_purge_urls.py` is one line in the box that owns it.
PURGE_SCRIPT = ".ci/scripts/deploy/cf-purge-urls.sh"

# The two install scripts (:142), in order, relative to the repository root.
INSTALL_SCRIPTS = ("dist/pages/install.sh", "dist/pages/install.ps1")

# The five `${VAR:?msg}` guards (:49-53), in order, as (name, message). The
# messages are the twin's verbatim, each already prefixed with the script name.
REQUIRED_ENV: tuple[tuple[str, str], ...] = (
    ("CHANNEL", "%s: CHANNEL must be set" % SELF),
    ("CLOUDFLARE_R2_ACCESS_KEY_ID", "%s: CLOUDFLARE_R2_ACCESS_KEY_ID must be set" % SELF),
    ("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "%s: CLOUDFLARE_R2_SECRET_ACCESS_KEY must be set" % SELF),
    ("CLOUDFLARE_R2_ENDPOINT", "%s: CLOUDFLARE_R2_ENDPOINT must be set" % SELF),
    ("CLOUDFLARE_ZONE_ID", "%s: CLOUDFLARE_ZONE_ID must be set" % SELF),
)

# The `case` arms of `skip_release_requested` (:70-73). A SET, because the twin lists each spelling explicitly rather than lowercasing: `TrUe` and `Y` are NOT
# skip values, and a port using `.lower() in {...}` would skip a release the twin
# publishes. Sits between the two marker comments the gate test `.ci/rediacc_ci/tests/gates/test_gate_skip_release_channel_pointer.py` splits the twin on; that test assembles its mutants from the twin's own text, so it is unaffected by this file, but the set has to stay in step with those lines.
SKIP_RELEASE_VALUES = frozenset({"true", "TRUE", "True", "1", "yes", "YES", "y", "on", "ON"})

# `if [[ "$CHANNEL" == "stable" || "$CHANNEL" == "edge" ]]` (:77). A `pr-N`
# channel has no tag contract, so the bump-none refusal is scoped to these two.
RELEASE_CHANNELS = ("stable", "edge")

# Vacuity fact 2 in the module docstring, as a constant so a test can assert the defect by name instead of restating the sentence.
AN_EMPTY_DIST_REPORTS_SUCCESS = True

# The prune delta in the module docstring, by name.
KEEPS_ONLY_WHAT_THE_INDEX_LISTS = r2_promote.PRUNE_IS_COPY_THEN_DELETE

# The stable CLI manifest, whose version bounds which edge snapshots are still promotion candidates.
STABLE_MANIFEST_KEY = "cli/stable/manifest.json"


class MissingEnvError(Exception):
    """One `${VAR:?msg}` firing. Exit 1, message on stderr, nothing else runs."""

    def __init__(self, name: str, message: str) -> None:
        super().__init__("%s: %s" % (name, message))
        self.name = name
        self.message = message


class BashExitError(Exception):
    """`set -e` ending the run on a command the twin does not guard.

    `aws s3 sync`, `aws s3 cp`, `sed` and the final purge pipeline are all unguarded, so the failing program's own stderr is the only explanation the caller gets and its status becomes the script's.
    """

    def __init__(self, code: int) -> None:
        super().__init__("set -e: exit %d" % code)
        self.code = code


def repo_root() -> str:
    """`cd "$(get_repo_root)"` (:105), by location rather than by cwd.

    `.ci/rediacc_ci/deploy/` is three directories under the root, exactly as `.ci/scripts/lib/` is. `abspath` and not `realpath`: see the module docstring.
    """
    return os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
    )


def require_env(env: dict[str, str]) -> dict[str, str]:
    """The five guards, in the twin's order. Returns the five values.

    Raises on the FIRST missing or empty one, because `: "${VAR:?}"` ends the
    shell there and the later guards never run.
    """
    values: dict[str, str] = {}
    for name, message in REQUIRED_ENV:
        value = env.get(name, "")
        if not value:
            raise MissingEnvError(name, message)
        values[name] = value
    return values


def skip_release_requested(env: dict[str, str]) -> bool:
    """`skip_release_requested` (:69-74). Exact-match against the case arms."""
    return env.get("SKIP_RELEASE", "") in SKIP_RELEASE_VALUES


def skip_banner(channel: str) -> list[str]:
    """The bump-none refusal block (:78-96), as the lines it echoes to STDOUT.

    On stdout and not stderr, and exit 0: the twin's closing sentence says this is "the intended outcome of a bump-none merge, not an error", and a port that treated it as a warning would make a correct build look broken.
    """
    return [
        "",
        "================================================================",
        "  RELEASE SKIPPED (bump-none) -- NOTHING WAS WRITTEN TO R2",
        "================================================================",
        "  channel:  %s" % channel,
        "",
        "  The merged PR carried the 'bump-none' label, so no tag and no",
        "  GitHub Release exist for this build. The package repositories",
        "  and install scripts are channel pointers, so publishing them",
        "  would advertise a version nobody can install.",
        "",
        "  NOT written:",
        "    - apt/%s/  rpm/%s/  apk/%s/  archlinux/%s/" % (channel, channel, channel, channel),
        "    - cli/%s/install.sh  cli/%s/install.ps1" % (channel, channel),
        "    - no Cloudflare cache purge (nothing changed)",
        "",
        "  This is the intended outcome of a bump-none merge, not an error.",
        "================================================================",
        "",
    ]


def sync_argv(fmt: str, channel: str, endpoint: str) -> list[str]:
    """One `aws s3 sync dist/repos/<fmt> s3://.../<fmt>/<channel>/` (:116-118)."""
    return [
        "aws",
        "s3",
        "sync",
        "dist/repos/%s" % fmt,
        "s3://%s/%s/%s/" % (BUCKET, fmt, channel),
        "--cache-control",
        CC_MUTABLE,
        "--endpoint-url",
        endpoint,
        "--only-show-errors",
    ]


def cp_argv(source: str, channel: str, name: str, endpoint: str) -> list[str]:
    """One `aws s3 cp <tmp> s3://.../cli/<channel>/<name>` (:148-150)."""
    return [
        "aws",
        "s3",
        "cp",
        source,
        "s3://%s/cli/%s/%s" % (BUCKET, channel, name),
        "--cache-control",
        CC_MUTABLE,
        "--endpoint-url",
        endpoint,
        "--only-show-errors",
    ]


def sed_argv(channel: str, source: str) -> list[str]:
    """The two channel substitutions (:145-147).

    The first rewrites the shell default (`REDIACC_CHANNEL:-stable`), the second
    the PowerShell one (`} else { "stable" }`), so a copy under `cli/<channel>/`
    installs from `<channel>` unless the caller says otherwise.
    """
    return [
        "sed",
        "-e",
        "s|REDIACC_CHANNEL:-stable|REDIACC_CHANNEL:-%s|g" % channel,
        "-e",
        's|} else { "stable" }|} else { "%s" }|g' % channel,
        source,
    ]


def snapshot_sync_argv(fmt: str, version: str, endpoint: str) -> list[str]:
    """Delta step 1: `aws s3 sync dist/repos/<fmt> s3://.../snapshots/v<V>/<fmt>/` restricted to the metadata files."""
    return [
        "aws",
        "s3",
        "sync",
        "dist/repos/%s" % fmt,
        "s3://%s/%s" % (BUCKET, channel_snapshot.tree(version, fmt)),
        *channel_snapshot.include_filters(META_EXCLUDES),
        "--cache-control",
        CC_MUTABLE,
        "--endpoint-url",
        endpoint,
        "--only-show-errors",
    ]


def snapshot_cp_argv(source: str, key: str, endpoint: str) -> list[str]:
    """One `aws s3 cp <file> s3://.../<key>` into a snapshot."""
    return [
        "aws",
        "s3",
        "cp",
        source,
        "s3://%s/%s" % (BUCKET, key),
        "--cache-control",
        CC_MUTABLE,
        "--endpoint-url",
        endpoint,
        "--only-show-errors",
    ]


def dist_inventory(fmts: tuple[str, ...] = FORMATS) -> tuple[list[str], dict[str, int]]:
    """`(metadata, packages)` of `dist/repos`: metadata as snapshot-relative keys (`apt/dists/stable/InRelease`), packages as channel-relative keys with their sizes (`apt/pool/x.deb`: 123). A format that was not built is absent."""
    metadata: list[str] = []
    packages: dict[str, int] = {}
    for fmt in fmts:
        directory = "dist/repos/%s" % fmt
        if not os.path.isdir(directory):
            continue
        for dirpath, _dirs, files in os.walk(directory):
            for name in files:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, directory).replace(os.sep, "/")
                if channel_snapshot.is_metadata(rel, META_EXCLUDES):
                    metadata.append("%s/%s" % (fmt, rel))
                else:
                    packages["%s/%s" % (fmt, rel)] = os.path.getsize(full)
    return sorted(metadata), packages


def _snapshot_repos(version: str, endpoint: str) -> None:
    """Delta step 1."""
    for fmt in FORMATS:
        if not os.path.isdir("dist/repos/%s" % fmt):
            continue
        status = _transfer(
            snapshot_sync_argv(fmt, version, endpoint), "snapshot of dist/repos/%s" % fmt
        )
        if status:
            raise BashExitError(status)


def _seal_snapshot(version: str, endpoint: str) -> None:
    """Delta step 3: verify the snapshot by listing it, then write the marker LAST."""
    root = channel_snapshot.prefix(version)
    _flush()
    proc = subprocess.run(
        r2_promote.list_argv(root, endpoint), check=False, capture_output=True, text=True
    )
    if proc.returncode:
        sys.stderr.write(proc.stderr)
        print("%s: listing %s failed (exit %d)" % (SELF, root, proc.returncode), file=sys.stderr)
        raise BashExitError(proc.returncode)
    listed = {obj.rel for obj in r2_promote.parse_listing(proc.stdout, root)}
    metadata, packages = dist_inventory()
    metadata += sorted(rel for rel in listed if rel.startswith("cli/") and rel not in metadata)
    absent = [key for key in [*channel_snapshot.CLI_REQUIRED, *metadata] if key not in listed]
    if absent:
        print(
            "%s: the channel snapshot %s is incomplete, so no %s marker is written: %s"
            % (SELF, root, channel_snapshot.MARKER, ", ".join(sorted(set(absent))[:10])),
            file=sys.stderr,
        )
        raise BashExitError(1)
    handle, path = tempfile.mkstemp(prefix="snapshot-marker-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(channel_snapshot.marker_body(version, metadata, packages))
        status = _transfer(
            snapshot_cp_argv(path, channel_snapshot.marker_key(version), endpoint),
            "upload of %s" % channel_snapshot.marker_key(version),
        )
    finally:
        os.remove(path)
    if status:
        raise BashExitError(status)
    print("Channel snapshot sealed: %s (%d metadata object(s))" % (root, len(metadata)))


def purge_argv(zone: str) -> list[str]:
    """`.ci/scripts/deploy/cf-purge-urls.sh --zone "$CLOUDFLARE_ZONE_ID"` (:162)."""
    return [PURGE_SCRIPT, "--zone", zone]


def repo_url(fmt: str, channel: str, relative: str) -> str:
    """`https://releases.rediacc.com/<fmt>/<channel>/<path>` (:135).

    `relative` is `${f#dist/repos/$dir/}`, a PREFIX STRIP rather than a basename:
    `dists/stable/Packages.gz` keeps its two directories.
    """
    return "%s/%s/%s/%s" % (PUBLIC_HOST, fmt, channel, relative)


def install_url(channel: str, name: str) -> str:
    """`https://releases.rediacc.com/cli/<channel>/install.{sh,ps1}` (:152)."""
    return "%s/cli/%s/%s" % (PUBLIC_HOST, channel, name)


def strip_prefix(path: str, prefix: str) -> str:
    """`${f#<prefix>}`: remove it only when it is there, leave the rest alone.

    `removeprefix` and not a slice, because the two differ on exactly the case
    the twin cares about: `${f#x}` leaves a non-matching string untouched.
    """
    return path.removeprefix(prefix)


def read_lines(text: str) -> list[str]:
    """`while IFS= read -r f; do ... done < <(find ...)`.

    A FINAL LINE WITH NO NEWLINE IS DROPPED, because `read` stores it and then returns non-zero at EOF so the loop body never runs for it. find always terminates its last line, so this cannot bite on real input; it is written the bash way anyway, because the day it does bite the two would disagree about a URL rather than about a count.
    """
    if not text:
        return []
    lines = text.split("\n")
    lines.pop()
    return lines


def _find_files(directory: str) -> tuple[str, int]:
    """`find <dir> -type f`, and `... | wc -l` over the same output.

    THE TWIN RUNS `find` TWICE, once into `wc -l` for the vacuity floor (:128) and once into the URL loop (:136), and this returns both answers from ONE run. That is the single deliberate consolidation in this file, and it is safe in the direction that matters: two runs can only disagree if the directory changes between them, and if it did, the twin would report a count that does
    not match the URLs it then builds.

    The count is NEWLINES, which is what `wc -l` counts. find's status is DISCARDED, exactly as `|| true` discards it: a find that fails still leaves `wc` printing a number, and the twin acts on the number.
    """
    _flush()
    proc = subprocess.run(
        ["find", directory, "-type", "f"],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return proc.stdout, proc.stdout.count("\n")


def _flush() -> None:
    """Empty Python's own buffers before a child inherits the descriptor.

    NOT HOUSEKEEPING, A REAL DIVERGENCE THIS REPAIRS, measured 2026-09-13. bash `echo` writes through immediately; Python block-buffers stdout when it is a pipe and flushes at exit. Without this, `Repos uploaded to R2 channel: edge` landed AFTER the purge script's two lines instead of before them, on the same stream, with byte-identical content in a different order. The call log
    was identical, both exits were 0, and only a byte comparison of stdout saw it. Every spawn goes through here for that reason.
    """
    sys.stdout.flush()
    sys.stderr.flush()


def _run(argv: list[str], **kwargs) -> int:
    """One unguarded command with BOTH streams inherited, as the twin leaves them."""
    _flush()
    return subprocess.run(argv, check=False, **kwargs).returncode


def _transfer(argv: list[str], what: str) -> int:
    """One `aws s3 sync|cp`, retried through a transient R2 failure (Rule T).

    aws's stderr is captured so the failure can be classified, and replayed byte for byte so a run that does not retry prints exactly what the twin printed. stdout stays inherited.
    """
    last_error = [""]
    attempts = [0]

    def attempt() -> tuple[int, str]:
        attempts[0] += 1
        _flush()
        proc = subprocess.run(argv, check=False, stderr=subprocess.PIPE)
        sys.stderr.buffer.write(proc.stderr)
        sys.stderr.flush()
        last_error[0] = proc.stderr.decode("utf-8", "replace")
        return proc.returncode, last_error[0]

    status = transfer_retry.retried(attempt, what, SELF, RETRY_DELAY_S, only_transient=True)
    if status and attempts[0] > 1 and transfer_retry.is_transient(last_error[0]):
        cause = last_error[0].strip().splitlines()[-1] if last_error[0].strip() else "no output"
        print(
            "%s: %s failed after %d attempts; last error: %s" % (SELF, what, attempts[0], cause),
            file=sys.stderr,
            flush=True,
        )
    return status


def _mktemp() -> str:
    """`tmp="$(mktemp)"` (:144). The binary, not `tempfile`: see the docstring."""
    _flush()
    proc = subprocess.run(["mktemp"], stdout=subprocess.PIPE, text=True, check=False)
    if proc.returncode != 0:
        raise BashExitError(proc.returncode)
    return proc.stdout.rstrip("\n")


def _upload_repos(channel: str, endpoint: str) -> list[str]:
    """The `for dir in apt rpm apk archlinux` loop (:114-137). Returns the URLs."""
    urls: list[str] = []
    for fmt in FORMATS:
        directory = "dist/repos/%s" % fmt
        # `[[ -d ... ]] || continue`: a format this channel does not build is legitimate, and is vacuity fact 1 in the module docstring.
        if not os.path.isdir(directory):
            continue

        status = _transfer(sync_argv(fmt, channel, endpoint), "sync of %s" % directory)
        if status:
            raise BashExitError(status)

        listing, count = _find_files(directory)
        if count == 0:
            print(
                "VACUOUS: %s exists but holds 0 file(s); refusing to report an "
                "upload that moved nothing" % directory,
                file=sys.stderr,
            )
            raise BashExitError(1)

        urls += [
            repo_url(fmt, channel, strip_prefix(f, directory + "/")) for f in read_lines(listing)
        ]
    return urls


def _upload_install_scripts(channel: str, endpoint: str, snapshot_version: str = "") -> list[str]:
    """The install-script loop (:142-153). Returns the URLs. With `snapshot_version`, each stamped script is also uploaded to the version's channel snapshot."""
    urls: list[str] = []
    for source in INSTALL_SCRIPTS:
        if not os.path.isfile(source):
            continue

        tmp = _mktemp()
        # `sed ... "$f" > "$tmp"`. A sed failure ends the run under `set -e`
        # with sed's status, and the temporary file is NOT removed -- the `rm`
        # is the next statement and never runs. Reproduced, leak included.
        with open(tmp, "w", encoding="utf-8") as handle:
            status = _run(sed_argv(channel, source), stdout=handle)
        if status:
            raise BashExitError(status)

        name = os.path.basename(source)
        status = _transfer(cp_argv(tmp, channel, name, endpoint), "upload of %s" % name)
        if status:
            raise BashExitError(status)
        if snapshot_version:
            # The SAME stamped temporary the channel upload just sent.
            key = channel_snapshot.tree(snapshot_version, "cli") + name
            status = _transfer(snapshot_cp_argv(tmp, key, endpoint), "snapshot of %s" % name)
            if status:
                raise BashExitError(status)

        # `rm -f "$tmp"`: -f, so a temporary that has already gone is not an error.
        if os.path.exists(tmp):
            os.remove(tmp)

        urls.append(install_url(channel, name))
    return urls


def _purge(urls: list[str], zone: str) -> None:
    """`printf '%s\\n' "${PURGE_URLS[@]}" | cf-purge-urls.sh --zone <zone>` (:160-163).

    Guarded by `${#PURGE_URLS[@]} -gt 0` in the twin, which is why an empty list
    makes no call at all rather than a call with empty stdin. Under `pipefail` the pipeline's status is the purge script's, since printf cannot fail here.
    """
    payload = "".join(url + "\n" for url in urls)
    try:
        status = _run(purge_argv(zone), input=payload, text=True)
    except OSError as exc:
        # A MISSING OR UNRUNNABLE PURGE SCRIPT. bash reports this itself, with its own line number and status 127; Python raises. Same stream, same
        # status, different sentence -- the same ruling the `${VAR:?}` guards get.
        print("%s: %s: %s" % (SELF, PURGE_SCRIPT, exc.strerror), file=sys.stderr)
        raise BashExitError(127) from exc
    if status:
        raise BashExitError(status)


def get_argv(key: str, endpoint: str) -> list[str]:
    """`aws s3 cp s3://<bucket>/<key> -`: one small object to stdout."""
    return ["aws", "s3", "cp", "s3://%s/%s" % (BUCKET, key), "-", "--endpoint-url", endpoint]


def _read_object(key: str, endpoint: str) -> str | None:
    """One small object's text, or None when it cannot be read. aws's stderr is captured, not shown: the caller decides what an unreadable object means."""
    _flush()
    proc = subprocess.run(get_argv(key, endpoint), check=False, capture_output=True)
    if proc.returncode:
        return None
    return proc.stdout.decode("utf-8", "replace")


def built_rels(fmt: str) -> set[str]:
    """Every file of `dist/repos/<fmt>`, relative to it: the new index and everything it names."""
    directory = "dist/repos/%s" % fmt
    found: set[str] = set()
    for dirpath, _dirs, files in os.walk(directory):
        for name in files:
            found.add(os.path.relpath(os.path.join(dirpath, name), directory).replace(os.sep, "/"))
    return found


def candidate_packages(
    channel: str, endpoint: str, run: r2_promote.Transfers, current: str
) -> dict[str, set[str]]:
    """Per format, the package rels the edge snapshots of OTHER promotion candidates name (the module docstring's KEEP SET). Empty on any channel but `edge`. Raises `r2_promote.PromoteError` when a candidate's marker cannot be read."""
    if channel != "edge":
        return {}
    root = channel_snapshot.SNAPSHOT_ROOT + "/"
    marked = []
    for obj in run.list_tree(root):
        head, _, rest = obj.rel.partition("/")
        if rest == channel_snapshot.MARKER and head.startswith("v") and head[1:] != current:
            marked.append(head[1:])
    if not marked:
        return {}
    text = _read_object(STABLE_MANIFEST_KEY, endpoint)
    try:
        stable = check_stable_manifest.manifest_version(text) if text is not None else ""
    except (ValueError, AttributeError):
        stable = ""
    keep: dict[str, set[str]] = {}
    for version in sorted(marked):
        if not check_soak_period.in_walk(version, stable):
            continue
        marker = _read_object(channel_snapshot.marker_key(version), endpoint)
        try:
            if marker is None:
                raise channel_snapshot.SnapshotError(
                    "%s could not be read" % channel_snapshot.marker_key(version)
                )
            _metadata, packages = channel_snapshot.parse_marker(marker, version)
        except channel_snapshot.SnapshotError as exc:
            print(
                "%s: prune refused, nothing deleted: %s, so the packages promotion candidate v%s "
                "still needs are unknown" % (SELF, exc, version),
                file=sys.stderr,
            )
            raise r2_promote.PromoteError(1) from exc
        for key in packages:
            fmt, _, rel = key.partition("/")
            keep.setdefault(fmt, set()).add(rel)
        why = (
            "newer than stable v%s" % stable
            if check_soak_period.semver(stable) is not None
            else "the stable version is unknown (%s unreadable)" % STABLE_MANIFEST_KEY
        )
        print("Prune keeps v%s's packages: a promotion candidate, %s" % (version, why))
    return keep


def _prune_trees(channel: str, endpoint: str, current: str) -> None:
    """The prune delta in the module docstring, for every format this run built."""
    run = r2_promote.Transfers(SELF, endpoint, RETRY_DELAY_S)
    built = {fmt: built_rels(fmt) for fmt in r2_promote.PACKAGE_TREES}
    built = {fmt: rels for fmt, rels in built.items() if rels}
    if not built:
        return
    try:
        extra = candidate_packages(channel, endpoint, run, current)
        for fmt in r2_promote.PACKAGE_TREES:
            if fmt not in built:
                continue
            prefix = r2_promote.tree(fmt, channel)
            listed = run.list_tree(prefix)
            present = {obj.rel for obj in listed}
            missing = sorted(built[fmt] - present)
            if missing:
                print(
                    "INCOMPLETE: %d file(s) of dist/repos/%s are not listed under %s after the "
                    "upload, so nothing is pruned: %s"
                    % (len(missing), fmt, prefix, ", ".join(missing[:10])),
                    file=sys.stderr,
                )
                raise r2_promote.PromoteError(1)
            r2_promote.prune_tree(fmt, channel, built[fmt] | extra.get(fmt, set()), listed, run)
    except r2_promote.PromoteError as exc:
        raise BashExitError(exc.status) from exc


def main(argv: list[str]) -> int:
    del argv  # the twin takes no argv, and says so at :62

    try:
        common.require_cmd("aws")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    try:
        values = require_env(dict(os.environ))
    except MissingEnvError as exc:
        # THE DIVERGENCE: bash prefixes this with `<path>: line N: `.
        print("%s: %s" % (exc.name, exc.message), file=sys.stderr)
        return 1

    channel = values["CHANNEL"]
    endpoint = values["CLOUDFLARE_R2_ENDPOINT"]
    snapshot_version = os.environ.get("SNAPSHOT_VERSION", "")

    if skip_release_requested(dict(os.environ)):
        if channel in RELEASE_CHANNELS:
            for line in skip_banner(channel):
                print(line)
            return 0
        print(
            "%s: SKIP_RELEASE ignored on channel '%s': not a release channel, "
            "uploading as usual" % (SELF, channel)
        )

    if snapshot_version and channel != "edge":
        print(
            "%s: %s=%s asks for a channel snapshot, which only an edge upload writes (CHANNEL=%s)"
            % (SELF, channel_snapshot.VERSION_ENV, snapshot_version, channel),
            file=sys.stderr,
        )
        return 1

    # The dist/ paths and the purge call below are repo-relative, exactly as they were in the workflow step this came from.
    os.chdir(repo_root())

    # `export`ed, so the `aws` child sees them. R2 speaks S3, and the twin's header names the mapping because a missing bridge surfaces as an unhelpful credentials error rather than as a missing variable.
    os.environ["AWS_ACCESS_KEY_ID"] = values["CLOUDFLARE_R2_ACCESS_KEY_ID"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = values["CLOUDFLARE_R2_SECRET_ACCESS_KEY"]
    os.environ["AWS_DEFAULT_REGION"] = "auto"

    try:
        purge_urls = _upload_repos(channel, endpoint)
        if snapshot_version:
            _snapshot_repos(snapshot_version, endpoint)
        purge_urls += _upload_install_scripts(channel, endpoint, snapshot_version)
        if snapshot_version:
            _seal_snapshot(snapshot_version, endpoint)
    except BashExitError as exc:
        return exc.code

    # UNCONDITIONAL, and vacuity fact 2: this prints even when nothing moved.
    print("Repos uploaded to R2 channel: %s" % channel)

    if purge_urls:
        try:
            _purge(purge_urls, values["CLOUDFLARE_ZONE_ID"])
        except BashExitError as exc:
            return exc.code

    # The prune delta: everything above is written, so the stale files go now.
    try:
        _prune_trees(channel, endpoint, snapshot_version)
    except BashExitError as exc:
        return exc.code
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
