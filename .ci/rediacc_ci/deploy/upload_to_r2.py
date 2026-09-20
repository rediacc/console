#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/upload-to-r2.sh`.

Uploads the release artifacts to R2: the CLI binaries to the immutable versioned prefix `cli/v<V>/` and to the mutable channel prefix `cli/<channel>/`, the npm tarballs to `npm/<channel>/`, the two channel pointers (`manifest.json` and `latest.json`), then trims the retention window recorded in `cli/versions.json`.

--------------------------------------------------------------------------
`write_once_guard` IS NOT PORTED. IT IS CALLED, AS BASH, FROM THE TWIN ITSELF
--------------------------------------------------------------------------
The sentinel-aware write guard is the one function in this file that decides whether a SEALED release may be overwritten, and its three answers (0 proceed, 10 skip, `exit 1` refuse) are the difference between an idempotent rerun and the `sealed-but-empty` state that burned v1.1.16 and v1.1.17. A Python reimplementation of it would be, in `write_once_guard_check.py`'s words, "a
second instrument certifying itself": the harness that proves the guard correct would then be checking a copy rather than the guard.

So this port does what that harness does. `extract_guard` applies the same
`sed -n '/^write_once_guard()/,/^}/p'` range to the twin's own text, and
`Uploader.write_once_guard` sources `common.sh` (for the real `log_info`/`log_error`) and the real `.ci/scripts/lib/release-state-validator.sh` beside it, then calls the extracted function. The bytes on stderr, the `aws s3api` calls it makes and the code it returns are the twin's, because they ARE the twin's.

IT IS INVOKED THROUGH `|| rc=$?`, AND THAT IS LOAD BEARING, NOT STYLE. The twin
writes `write_once_guard ... || guard_rc=$?`, and a function whose status is
consumed by a `||` list runs with errexit SUPPRESSED THROUGHOUT ITS BODY. That suppression is what produces defect 2 below. A runner that called the function bare would abort where the twin continues, and the two would disagree on exactly the path that matters most.

`RELEASES_BUCKET` AND `DRY_RUN` REACH THE CHILD THROUGH THE ENVIRONMENT rather than by sourcing `.ci/config/constants.sh`. constants.sh hard-requires `.devcontainer/toolchain.env` and `return 1 2>/dev/null || exit 1`s without it, which would make the guard's availability depend on a file the guard does not read. The two values it needs are computed here from the same defaults
(`BUCKET_DEFAULT`, `MAX_RELEASE_VERSIONS`) and pinned against constants.sh by `test_the_constants_are_the_twins_constants`.

--------------------------------------------------------------------------
THREE OTHER PROGRAMS ARE SPAWNED, EACH FOR A MEASURED REASON
--------------------------------------------------------------------------
  * `aws`, because it is the credentialed tool with a real remote side. Faked on
    `PATH` in the differential, never reimplemented.
  * `jq`, because THE TRACKER IS jq'S BYTES. `update_versions_tracker` uploads
    `jq ".[:20]"`'s output verbatim to `cli/versions.json`, and jq's default
    pretty-printer emits two-space indent with `[` on its own line. `json.dumps`
    is a second answer to a question the twin has already answered, and the
    difference would be uploaded rather than printed.
  * `bash`, for THE GLOBS. `for binary in "$CLI_DIR"/rdc-*` expands in the
    shell's collation order, which is `strcoll` and therefore LOCALE dependent,
    and falls back to the literal unmatched pattern when nothing matches (the
    twin relies on that: `[[ -f "$binary" ]] || continue` is what filters it).
    `sorted(glob.glob(...))` is codepoint order and returns an empty list, so
    the two agree only by accident of today's locale and today's filenames.
    `bash_glob` asks bash.
  * `bash`, for the guard, as above.

`basename` IS THE ONE EXTERNAL THE PORT DOES NOT SPAWN. `os.path.basename` differs from the binary only for a path with a trailing slash or an empty argument, and every argument here is a glob expansion of `<dir>/rdc-*`, which can be neither.

--------------------------------------------------------------------------
FOUR DEFECTS IN THE TWIN, ALL REPRODUCED RATHER THAN REPAIRED
--------------------------------------------------------------------------
This wave's acceptance rule is agreement with the LIVE twin, so each is carried, named as a constant so a test can pin it, and reported to the driver.

DEFECT 1, `AN_EMPTY_CLI_DIR_PUBLISHES_A_POINTER`. A `dist/cli/` that EXISTS and holds no `rdc-*` and no `manifest.json` uploads nothing, then still writes
`cli/<channel>/latest.json` = `{"version":"<V>"}` and prints
`CLI: uploaded to cli/v<V>/ + cli/<channel>/`. Every installer and every auto-updater on that channel then resolves to a version with zero binaries. The summary prints `Artifacts uploaded: 0` on the line below and nothing acts on it. This is the same harm the bump-none guard at the top of the same file exists to prevent, arriving by a different door. Driven 2026-09-13.

DEFECT 2, `AN_UNANSWERED_COUNT_READS_AS_SEALED_BUT_EMPTY`. When the sentinel exists and `rsv_binary_count` CANNOT ANSWER (AccessDenied, a 5xx, an expired token), the guard reports the release as corrupt and tells the operator to run `scripts/ops/scrub-sentinel.sh v<V> --execute`, which destroys the sentinel of a perfectly healthy sealed release. The library goes to explicit trouble
to avoid this: its own comment at `release-state-validator.sh:161-166` says the `|| echo 0` was removed because "callers run under `set -e`, so a failed probe now aborts them instead of feeding them a fabricated zero". The abort never happens here,
because `write_once_guard ... || guard_rc=$?` suppresses errexit inside the
function, so `bin_count` is the empty string, `[[ "" -gt 0 ]]` is false, and the
refusal path runs. The one call site the library names in its header is the one where its protection does not hold. Driven 2026-09-13.

DEFECT 3, `A_FAILED_TRACKER_READ_RESETS_THE_WINDOW`. `r2_get` is `aws s3 cp ... - 2>/dev/null || echo ""`, so "the tracker does not exist yet", "the credentials expired" and "R2 answered 500" are one empty string. `update_versions_tracker` then treats it as `[]` and OVERWRITES `versions.json`
with a single-element list. Driven 2026-09-13 against a 22-entry tracker: the
file came back as `["1.2.3"]`, no warning, exit 0, and the 21 versions that fell out were never passed to `cleanup_old_versions`, so their prefixes are orphaned on R2 until the nightly sweep. aws's own explanation is discarded by the `2>/dev/null`.

DEFECT 4, `A_MALFORMED_TRACKER_IS_OVERWRITTEN_EMPTY`, and this one destroys data. A `cli/versions.json` that is not valid JSON (truncated, half-downloaded, or hand-edited) makes the first jq fail. Nothing stops, because
`CLI_PRUNED=$(update_versions_tracker ...)` is an ASSIGNMENT and bash does not
apply errexit inside a command substitution whose value is assigned. Measured on bash 5.3.9, 2026-09-13, isolated from this script:

    $ bash -c 'set -e; f(){ false; echo body; }; V=$(f); echo "rc=$? V=[$V]"'
    rc=0 V=[body]
    $ bash -c 'set -e; f(){ false; echo body; }; f; echo unreachable'
    (exits 1, prints nothing)

So `updated` is empty, the next two jq calls on empty input succeed producing nothing, and `r2_put ""` UPLOADS AN EMPTY `cli/versions.json`. Driven end to end on the twin: one `jq: parse error: Invalid literal at line 1, column 7` scrolls past in the log, the retention history is gone, the run prints `R2 upload complete` and exits 0. Same root cause family as defect 2: a caller's
syntax silently switching errexit off for a whole function body.

--------------------------------------------------------------------------
FOUR DIVERGENCES, EACH ASSERTED IN BOTH DIRECTIONS BY THE DIFFERENTIAL
--------------------------------------------------------------------------
1. `-h`/`--help` prints `Usage: $0`, and `$0` is the path the program was
   invoked by. The twin therefore names a `.sh` and this names a `.py`. The rest
   of the line is byte-identical.
2. A FLAG WITH NO VALUE. `VERSION="$2"` under `set -u` makes bash print
   `<path>: line 38: $2: unbound variable`; the line number is the flag's own
   (38, 42, 46, 50). This prints the `$2: unbound variable` half, same stream,
   same status 1. Identical ruling to `deploy/upload_repos_to_r2.py`.
3. `common.sh` logs with `echo -e`, which INTERPRETS backslash escapes in the
   message; `rediacc_ci.log` formats the message as data. A `dist/cli` path
   containing `\t` prints a tab on one side and two characters on the other.
   `log.py`'s own docstring records this as a bug being dropped rather than a
   decision, and the same ruling is taken here.
4. `common.sh` colours when stderr is a tty and `NO_COLOR` is unset;
   `rediacc_ci.log` additionally suppresses colour under `CI=true`. Under
   `CI=true` WITH a tty the two disagree, and in that one case this file
   disagrees with ITSELF, because the guard subprocess sources common.sh and
   emits colour while the Python half does not.

K=5 LEDGER: `.ci/shadow/w7p6-upload-to-r2.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

from rediacc_ci import log

# The twin's own name. Used for nothing the twin prints (it prints `$0`), only
# for this port's own refusals, which the twin has no analogue for.
SELF = "upload-to-r2.sh"

# `.ci/config/constants.sh:201` and `:213`. Restated rather than sourced, for the reason in the docstring, and pinned against constants.sh by a staleness alarm.
BUCKET_DEFAULT = "rediacc-releases"
MAX_RELEASE_VERSIONS = 20

# `CACHE_CONTROL_MUTABLE` / `CACHE_CONTROL_IMMUTABLE` (:176-177). The immutable policy is legitimate HERE, unlike in `upload-repos-to-r2.sh`, because the URL itself carries the version: `cli/v1.2.3/rdc-linux-x64` never serves other bytes.
CACHE_CONTROL_MUTABLE = "no-cache"
CACHE_CONTROL_IMMUTABLE = "public, max-age=31536000, immutable"

# `if [[ "$CHANNEL" == "stable" || "$CHANNEL" == "edge" ]]`, which appears five
# times (:113, :382, :409, :416, :451). A `pr-N` channel has no tag contract, so neither the bump-none refusal, the versioned prefix, the retention tracker nor the cleanup applies to it.
RELEASE_CHANNELS = ("stable", "edge")

# The `case` arms of `skip_release_requested` (:106-109). A SET of SPELLINGS, because the twin lists each one rather than lowercasing: `TrUe` and `Y` are NOT
# skip values, and a port using `.lower() in {...}` would suppress a release the
# twin publishes. These lines sit between the SKIP_RELEASE_GUARD_BEGIN/END markers that `.ci/scripts/test/gates/test-skip-release-channel-pointer.sh` splits the twin on to assemble its mutants.
SKIP_RELEASE_VALUES = frozenset({"true", "TRUE", "True", "1", "yes", "YES", "y", "on", "ON"})

# The three credentials checked, IN ORDER, when `--dry-run` is absent (:146). The first missing one wins, and the loop is what makes that observable.
REQUIRED_CREDENTIALS = (
    "CLOUDFLARE_R2_ACCESS_KEY_ID",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY",
    "CLOUDFLARE_R2_ENDPOINT",
)

# The four defects in the module docstring, named so a test can pin each by name instead of restating the sentence.
AN_EMPTY_CLI_DIR_PUBLISHES_A_POINTER = True
AN_UNANSWERED_COUNT_READS_AS_SEALED_BUT_EMPTY = True
A_FAILED_TRACKER_READ_RESETS_THE_WINDOW = True
A_MALFORMED_TRACKER_IS_OVERWRITTEN_EMPTY = True

# `sed -n '/^write_once_guard()/,/^}/p'`, the same range
# `.ci/rediacc_ci/deploy/write_once_guard_check.py:120-121` uses: from the definition line to the first line that is a closing brace at column 0.
GUARD_START = re.compile(r"^write_once_guard\(\)")
GUARD_END = re.compile(r"^\}")


class BashExitError(Exception):
    """`set -e` ending the run on a command the twin does not guard.

    `aws s3 cp` (both directions) and the closing `r2_put` of the tracker update are unguarded, so the failing program's own stderr is the only explanation the caller gets and its status becomes the script's. The three `jq` pipelines are NOT in that set: see defect 4.
    """

    def __init__(self, code: int) -> None:
        super().__init__("set -e: exit %d" % code)
        self.code = code


class UsageError(Exception):
    """`log_error ...; exit 1` from the argument parser, and its bash cousins.

    `logged` decides which stream shape the message takes. For the two `--x is required` refusals and `Unknown option:` it goes through `log_error`, so it gains the `common.sh` glyph; for `$2: unbound variable` it does not, because bash's own `set -u` refusal is not a `log_error` call.
    """

    def __init__(self, message: str, *, logged: bool = True) -> None:
        super().__init__(message)
        self.message = message
        self.logged = logged


def repo_root() -> str:
    """`get_repo_root` (common.sh:205-210), by location rather than by cwd.

    The twin resolves `.ci/scripts/lib/../../..` from `common.sh`'s own directory; this file sits at `.ci/rediacc_ci/deploy/`, also three directories under the root, so the arithmetic is identical. `abspath` and NOT `realpath`, because bash's `cd` is logical and a checkout reached through a symlink keeps the symlinked spelling on both sides. `paths.repo_root()` is deliberately not
    used: it resolves symlinks and honours `$REDIACC_CI_ROOT`, and the twin does neither.
    """
    return os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
    )


def releases_bucket() -> str:
    """`readonly RELEASES_BUCKET="${RELEASES_BUCKET:-rediacc-releases}"`.

    `:-` is an unset-OR-EMPTY test, so `RELEASES_BUCKET=` falls back to the
    default exactly as an absent one does.
    """
    return os.environ.get("RELEASES_BUCKET", "") or BUCKET_DEFAULT


def skip_release_requested(value: str) -> bool:
    """`skip_release_requested` (:105-110). Exact match against the case arms."""
    return value in SKIP_RELEASE_VALUES


def skip_banner(version: str, channel: str) -> list[str]:
    """The bump-none refusal block (:114-135), as the lines it echoes to STDOUT.

    STDOUT and exit 0, not stderr and not an error: the twin's own closing sentence says this is "the intended outcome of a bump-none merge, not an error", and a port that logged it as a warning would make a correct build look broken. The `cli/v<V>/` line's padding is the twin's, fixed regardless of how long the version is, so it is misaligned for every version and identical to the
    byte.
    """
    return [
        "",
        "================================================================",
        "  RELEASE SKIPPED (bump-none) -- NOTHING WAS WRITTEN TO R2",
        "================================================================",
        "  version:  v%s" % version,
        "  channel:  %s" % channel,
        "",
        "  The merged PR carried the 'bump-none' label, so this run cuts",
        "  no git tag and publishes no GitHub Release. Advancing the R2",
        "  channel pointer would therefore aim every installer and every",
        "  auto-updater at a version that does not exist.",
        "",
        "  NOT written:",
        "    - cli/%s/manifest.json  (channel pointer)" % channel,
        "    - cli/%s/latest.json    (channel pointer)" % channel,
        "    - cli/%s/rdc-*          (channel binaries)" % channel,
        "    - cli/v%s/              (versioned, immutable path)" % version,
        "    - npm/%s/               (npm tarballs)" % channel,
        "",
        "  This is the intended outcome of a bump-none merge, not an error.",
        "================================================================",
        "",
    ]


def cp_argv(src: str, full_dest: str, endpoint: str, cache_control: str) -> list[str]:
    """`r2_cp` (:193-196). Flag ORDER is the twin's and is part of the call log."""
    return [
        "aws",
        "s3",
        "cp",
        src,
        full_dest,
        "--endpoint-url",
        endpoint,
        "--cache-control",
        cache_control,
        "--no-progress",
    ]


def put_argv(full_dest: str, endpoint: str, content_type: str) -> list[str]:
    """`r2_put` (:213-217). Always the MUTABLE policy: its only callers are the three channel pointers (`latest.json`, `manifest.json`, `versions.json`)."""
    return [
        "aws",
        "s3",
        "cp",
        "-",
        full_dest,
        "--endpoint-url",
        endpoint,
        "--content-type",
        content_type,
        "--cache-control",
        CACHE_CONTROL_MUTABLE,
        "--no-progress",
    ]


def rm_argv(full_path: str, endpoint: str) -> list[str]:
    """`r2_rm` (:227-228)."""
    return ["aws", "s3", "rm", full_path, "--recursive", "--endpoint-url", endpoint]


def get_argv(full_path: str, endpoint: str) -> list[str]:
    """`r2_get` (:301-302)."""
    return ["aws", "s3", "cp", full_path, "-", "--endpoint-url", endpoint]


def r2_path(kind: str, channel: str, rest: str) -> str:
    """`r2_path` (:306-310): `{type}/{channel}/{rest}`."""
    return "%s/%s/%s" % (kind, channel, rest)


def extract_guard(text: str) -> str:
    """`sed -n '/^write_once_guard()/,/^}/p'`, range semantics and all.

    A sed range RE-ARMS after it closes, so a second `write_once_guard()` further down would be appended rather than ignored. Reproduced, because the point of extracting rather than reimplementing is that the bytes are the twin's.
    """
    out: list[str] = []
    inside = False
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()
    for line in lines:
        if not inside:
            if GUARD_START.search(line):
                inside = True
                out.append(line)
            continue
        out.append(line)
        if GUARD_END.search(line):
            inside = False
    return "".join(line + "\n" for line in out)


def guard_runner_source(common_sh: str, validator_sh: str, guard: str) -> str:
    """The bash the guard is called from, assembled once so a test can read it.

    `|| rc=$?` REPRODUCES THE TWIN'S CALL CONTEXT, which suppresses errexit
    inside the function body and is what makes defect 2 reachable. A bare call would abort where the twin continues.
    """
    return ('source %s\nsource %s\n%s\nrc=0\nwrite_once_guard "$1" "$2" || rc=$?\nexit $rc\n') % (
        _quote(common_sh),
        _quote(validator_sh),
        guard,
    )


def _quote(path: str) -> str:
    """Single-quote a path for bash. Paths here come from `__file__`."""
    return "'" + path.replace("'", "'\\''") + "'"


def _flush() -> None:
    """Empty Python's buffers before a child inherits the descriptor.

    NOT HOUSEKEEPING. bash's `echo` writes through immediately; Python block-buffers stdout when it is a pipe. Without this the `log_step` line that precedes a call can land AFTER the child's own output, byte-identical content in a different order, with an identical call log and identical exits. Every spawn in this file goes through here.
    """
    sys.stdout.flush()
    sys.stderr.flush()


class Uploader:
    """One run. Holds the six values every helper in the twin reads as a global."""

    def __init__(self, version: str, channel: str, dry_run: bool) -> None:
        self.version = version
        self.channel = channel
        self.dry_run = dry_run
        self.bucket = releases_bucket()
        # Read HERE and not cached from a dict: in dry-run the twin never checks
        # this variable, and `${CLOUDFLARE_R2_ENDPOINT}` under `set -u` would only
        # fire if a real call were made, which dry-run never makes.
        self.endpoint = os.environ.get("CLOUDFLARE_R2_ENDPOINT", "")
        self.root = repo_root()
        self.uploaded = 0

    # -- the four R2 primitives ------------------------------------------------

    def r2_cp(self, src: str, dest: str, cache_control: str = CACHE_CONTROL_MUTABLE) -> None:
        full_dest = "s3://%s/%s" % (self.bucket, dest)
        if self.dry_run:
            log.info(
                "[DRY-RUN] Would upload: %s → %s (Cache-Control: %s)"
                % (src, full_dest, cache_control)
            )
            return
        _flush()
        status = subprocess.run(
            cp_argv(src, full_dest, self.endpoint, cache_control), check=False
        ).returncode
        if status:
            raise BashExitError(status)

    def r2_put(
        self,
        content: str,
        dest: str,
        content_type: str = "application/json",
        *,
        quiet: bool = False,
    ) -> None:
        """`echo "$content" | aws s3 cp - ...`.

        `quiet` is the one caller that writes `r2_put ... >/dev/null` (`update_versions_tracker`, whose whole stdout is captured by
        `CLI_PRUNED=$( )` and must not gain aws's). Every other caller INHERITS
        stdout, so aws writes to the script's own stream in real time rather than through a buffer here, which is what keeps the interleaving with stderr the twin's.
        """
        full_dest = "s3://%s/%s" % (self.bucket, dest)
        if self.dry_run:
            log.info(
                "[DRY-RUN] Would write: %s (Cache-Control: %s)" % (full_dest, CACHE_CONTROL_MUTABLE)
            )
            return
        _flush()
        status = subprocess.run(
            put_argv(full_dest, self.endpoint, content_type),
            input=content + "\n",
            stdout=subprocess.DEVNULL if quiet else None,
            text=True,
            check=False,
        ).returncode
        if status:
            # Under `pipefail` the pipeline's status is aws's; `echo` cannot fail.
            raise BashExitError(status)

    def r2_rm(self, path: str) -> None:
        """`aws s3 rm ... 2>/dev/null || true`: stderr discarded, status ignored.

        A deletion that fails is therefore invisible AND unretried, because the version has already left the tracker by the time this runs.
        """
        if self.dry_run:
            log.info("[DRY-RUN] Would delete: s3://%s/%s" % (self.bucket, path))
            return
        _flush()
        subprocess.run(
            rm_argv("s3://%s/%s" % (self.bucket, path), self.endpoint),
            stderr=subprocess.DEVNULL,
            check=False,
        )

    def r2_get(self, path: str) -> str:
        """`$(aws s3 cp ... - 2>/dev/null || echo "")`, defect 3 included.

        The `|| echo ""` appends a newline on failure, and `$( )` then strips every trailing newline, so a FAILED read is indistinguishable from an absent object. A partial read followed by a failure keeps the partial bytes, which is reproduced rather than tidied.
        """
        _flush()
        proc = subprocess.run(
            get_argv("s3://%s/%s" % (self.bucket, path), self.endpoint),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        out = proc.stdout
        if proc.returncode:
            out += "\n"
        return out.rstrip("\n")

    # -- the guard, which stays bash ------------------------------------------

    def write_once_guard(self, prefix: str, context: str) -> int:
        """Call the twin's OWN `write_once_guard`, as bash. See the docstring.

        Returns the guard's status: 0 proceed, 10 skip, 1 the guard's `exit 1`. The twin's `exit 1` kills the whole script, so the caller must too.
        """
        twin = os.path.join(self.root, ".ci", "scripts", "deploy", SELF)
        common_sh = os.path.join(self.root, ".ci", "scripts", "lib", "common.sh")
        validator = os.path.join(self.root, ".ci", "scripts", "lib", "release-state-validator.sh")
        for required in (twin, common_sh, validator):
            if not os.path.isfile(required):
                # NOT A DIVERGENCE, because the twin cannot reach this state: the
                # function lives inside the twin. Loud rather than a `command not
                # found` from bash, with the fix in the message.
                log.error(
                    "%s: cannot run the write-once guard: %s is missing. The guard is "
                    "deliberately NOT reimplemented in Python; it is sourced from the "
                    "bash twin, so this port needs the twin's tree intact." % (SELF, required)
                )
                raise BashExitError(1)

        guard = extract_guard(_read(twin))
        if not guard.strip():
            log.error(
                "%s: cannot run the write-once guard: no `write_once_guard()` block in "
                "%s. Either it was renamed or the sed range this port shares with "
                "write_once_guard_check.py no longer matches." % (SELF, twin)
            )
            raise BashExitError(1)

        # The guard reads both as globals. constants.sh is deliberately not sourced, so they are handed over through the environment instead.
        os.environ["RELEASES_BUCKET"] = self.bucket
        os.environ["DRY_RUN"] = "true" if self.dry_run else "false"
        _flush()
        return subprocess.run(
            [
                "bash",
                "-c",
                guard_runner_source(common_sh, validator, guard),
                SELF,
                prefix,
                context,
            ],
            check=False,
        ).returncode

    # -- the retention tracker -------------------------------------------------

    def update_versions_tracker(self, prefix: str, new_version: str, max_versions: int) -> str:
        """`update_versions_tracker` (:320-351). Returns the versions to prune.

        Its stdout is captured by `CLI_PRUNED=$(...)`, which strips trailing
        newlines; its log lines go to stderr and are not.
        """
        tracker_path = "%s/versions.json" % prefix
        if self.dry_run:
            log.info("[DRY-RUN] Would update %s" % tracker_path)
            return ""

        existing = self.r2_get(tracker_path)
        if not existing:
            existing = "[]"

        # `command -v jq &>/dev/null`. `shutil.which` differs only for a shell FUNCTION or alias named jq, which a script bash spawns cannot inherit.
        if shutil.which("jq") is None:
            log.warn("jq not available, skipping version tracking for %s" % prefix)
            return ""

        updated = _jq(
            ["jq", "--arg", "v", new_version, "if index($v) then . else [$v] + . end"],
            existing + "\n",
        )
        pruned = _jq(["jq", "-r", ".[%d:][]" % max_versions], updated + "\n")
        kept = _jq(["jq", ".[:%d]" % max_versions], updated + "\n")
        # THE LAST COMMAND IS THE ONE THAT CAN STILL ABORT THE SCRIPT. A command substitution takes the status of its final command, so a failing `r2_put` here DOES become the assignment's status and errexit fires in the caller, while every jq above it is swallowed. That asymmetry is bash's, not this port's, and it is defect 4's other half.
        self.r2_put(kept, tracker_path, quiet=True)
        # `$( )` strips the trailing newlines of the whole function's stdout.
        return pruned.rstrip("\n")

    def cleanup_old_versions(self, prefix: str, pruned_versions: str) -> None:
        """`cleanup_old_versions` (:354-366).

        `<<<"$pruned_versions"` appends a newline, so every line including the last reaches the loop body. An empty string returns before the log_step, which is why a run with nothing to prune prints no cleanup section.
        """
        if not pruned_versions:
            return
        log.step("Cleaning up old %s versions" % prefix)
        for ver in pruned_versions.split("\n"):
            if not ver:
                continue
            log.info("  Deleting %s/v%s/" % (prefix, ver))
            self.r2_rm("%s/v%s/" % (prefix, ver))


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _jq(argv: list[str], stdin: str) -> str:
    """One `echo "$x" | jq ...`, with `$( )`'s newline strip. DEFECT 4 lives here.

    THE EXIT STATUS IS IGNORED, WHICH IS NOT AN OVERSIGHT AND NOT A CHOICE. It is what the twin does, for the reason in the module docstring: all three jq
    pipelines sit inside `CLI_PRUNED=$(update_versions_tracker ...)`, and bash
    does not apply errexit to a command inside a command substitution whose value is being assigned. Measured on bash 5.3.9, 2026-09-13:

        $ bash -c 'set -e; f(){ false; echo body; }; V=$(f); echo "rc=$? V=[$V]"'
        rc=0 V=[body]
        $ bash -c 'set -e; f(){ false; echo body; }; f; echo unreachable'
        (exits 1, prints nothing)

    WHATEVER jq PRINTED BEFORE FAILING IS KEPT, because `$( )` captures it either way. jq's stderr is inherited, so the parse error is still visible; it is just not acted on.
    """
    _flush()
    proc = subprocess.run(argv, input=stdin, stdout=subprocess.PIPE, text=True, check=False)
    return proc.stdout.rstrip("\n")


def bash_glob(directory: str, pattern: str) -> list[str]:
    """`for x in "$directory"/<pattern>`, asked of bash itself.

    Returns bash's expansion INCLUDING the literal unmatched pattern when nothing matches, because that is what the twin iterates and `[[ -f ]] || continue` is what filters it. See the docstring for why this is not `sorted(glob.glob())`.
    """
    _flush()
    proc = subprocess.run(
        ["bash", "-c", 'for f in "$1"/%s; do printf "%%s\\n" "$f"; done' % pattern, "-", directory],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode:
        raise BashExitError(proc.returncode)
    lines = proc.stdout.split("\n")
    lines.pop()
    return lines


def parse_args(argv: list[str], argv0: str) -> dict[str, str]:
    """The `while [[ $# -gt 0 ]]` parser (:35-70), including its two refusals.

    THE TWO REFUSALS RAISE; `--help` DOES NOT. `Unknown option:` and `$2: unbound variable` are both `UsageError` and differ only in `logged`, which decides whether the message gains `common.sh`'s `✗ ` glyph. `--help` fills the `help` key and RETURNS, because the twin's `echo ...; exit 0` is a success and returning keeps that visible in the type rather than hiding a zero exit
    inside an exception.
    """
    parsed = {
        "version": "",
        "channel": "",
        "cli_dir": "",
        "packages_dir": "",
        "skip_release": os.environ.get("SKIP_RELEASE", ""),
        "dry_run": "false",
        "help": "",
    }
    index = 0
    while index < len(argv):
        flag = argv[index]
        if flag in ("--version", "--channel", "--cli-dir", "--packages-dir"):
            if index + 1 >= len(argv):
                # `set -u` on `"$2"`. bash prefixes `<path>: line N: `.
                raise UsageError("$2: unbound variable", logged=False)
            key = {
                "--version": "version",
                "--channel": "channel",
                "--cli-dir": "cli_dir",
                "--packages-dir": "packages_dir",
            }[flag]
            parsed[key] = argv[index + 1]
            index += 2
        elif flag == "--skip-release":
            parsed["skip_release"] = "true"
            index += 1
        elif flag == "--dry-run":
            parsed["dry_run"] = "true"
            index += 1
        elif flag in ("-h", "--help"):
            parsed["help"] = (
                "Usage: %s --version VERSION --channel CHANNEL [--cli-dir DIR] "
                "[--packages-dir DIR] [--skip-release] [--dry-run]" % argv0
            )
            return parsed
        else:
            raise UsageError("Unknown option: %s" % flag)
    return parsed


def _upload_cli(run: Uploader, cli_dir: str) -> None:
    """The CLI section (:373-421)."""
    log.step("Uploading CLI binaries")

    if run.channel in RELEASE_CHANNELS:
        # 0 proceed, 10 skip (sealed with binaries, an idempotent rerun),
        # `exit 1` inside the guard = refuse (sealed-but-empty).
        guard_rc = run.write_once_guard("cli/v%s/" % run.version, "cli v%s" % run.version)
        if guard_rc == 1:
            # The twin's guard calls `exit 1`, which ends the SCRIPT there.
            raise BashExitError(1)
        if guard_rc == 0:
            for binary in bash_glob(cli_dir, "rdc-*"):
                if not os.path.isfile(binary):
                    continue
                run.r2_cp(
                    binary,
                    "cli/v%s/%s" % (run.version, os.path.basename(binary)),
                    CACHE_CONTROL_IMMUTABLE,
                )
                run.uploaded += 1

    for binary in bash_glob(cli_dir, "rdc-*"):
        if not os.path.isfile(binary):
            continue
        run.r2_cp(binary, r2_path("cli", run.channel, os.path.basename(binary)))

    manifest = os.path.join(cli_dir, "manifest.json")
    if os.path.isfile(manifest):
        run.r2_cp(manifest, r2_path("cli", run.channel, "manifest.json"))

    # `latest.json` LAST, to avoid pointing the channel at bytes not yet there. DEFECT 1 LIVES ON THIS LINE: it is unconditional, so an empty `dist/cli` publishes a pointer to a version with no binaries.
    run.r2_put('{"version":"%s"}' % run.version, r2_path("cli", run.channel, "latest.json"))

    if run.channel in RELEASE_CHANNELS:
        log.info("CLI: uploaded to cli/v%s/ + cli/%s/" % (run.version, run.channel))
    else:
        log.info(
            "CLI: uploaded to cli/%s/ (versioned path skipped; not a release channel)" % run.channel
        )


def _upload_npm(run: Uploader, npm_dir: str) -> None:
    """The npm section (:427-446)."""
    log.step("Uploading CLI npm tarball")

    for tgz in bash_glob(npm_dir, "rediacc-cli-*.tgz"):
        if not os.path.isfile(tgz):
            continue
        local_name = os.path.basename(tgz)
        if local_name == "rediacc-cli-latest.tgz":
            continue
        # The versioned tarball name carries the semver, so its URL is immutable.
        run.r2_cp(tgz, r2_path("npm", run.channel, local_name), CACHE_CONTROL_IMMUTABLE)
        run.uploaded += 1

    latest = os.path.join(npm_dir, "rediacc-cli-latest.tgz")
    if os.path.isfile(latest):
        run.r2_cp(latest, r2_path("npm", run.channel, "rediacc-cli-latest.tgz"))

    log.info("npm: uploaded to npm/%s/" % run.channel)


def main(argv: list[str]) -> int:
    argv0 = sys.argv[0] if sys.argv else "upload_to_r2.py"
    try:
        parsed = parse_args(argv, argv0)
    except UsageError as exc:
        if exc.logged:
            log.error(exc.message)
        else:
            print(exc.message, file=sys.stderr)
        return 1

    if parsed["help"]:
        print(parsed["help"])
        return 0

    version = parsed["version"]
    channel = parsed["channel"]
    if not version:
        log.error("--version is required")
        return 1

    root = repo_root()
    cli_dir = parsed["cli_dir"] or os.path.join(root, "dist", "cli")
    # PACKAGES_DIR is defaulted and then never read again, exactly as in the twin (:79, `--packages-dir` is documented DEPRECATED). Kept so the flag still takes a value rather than falling through to `Unknown option`.
    _packages_dir = parsed["packages_dir"] or os.path.join(root, "dist", "packages")

    if not channel:
        log.error("--channel is required")
        return 1

    if skip_release_requested(parsed["skip_release"]):
        if channel in RELEASE_CHANNELS:
            for line in skip_banner(version, channel):
                print(line)
            return 0
        log.info(
            "--skip-release ignored on channel '%s': not a release channel, uploading as usual"
            % channel
        )

    dry_run = parsed["dry_run"] == "true"
    log.step("Uploading v%s to R2 channel: %s" % (version, channel))

    if not dry_run:
        for name in REQUIRED_CREDENTIALS:
            # Read at the call site, never through an alias.
            if name == "CLOUDFLARE_R2_ACCESS_KEY_ID":
                present = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", "")
            elif name == "CLOUDFLARE_R2_SECRET_ACCESS_KEY":
                present = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "")
            else:
                present = os.environ.get("CLOUDFLARE_R2_ENDPOINT", "")
            if not present:
                log.error("Missing required environment variable: %s" % name)
                return 1

        # `export`ed for the `aws` child. R2 speaks S3, and a missing bridge surfaces as an unhelpful credentials error rather than a missing name.
        os.environ["AWS_ACCESS_KEY_ID"] = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", "")
        os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "")
        os.environ["AWS_DEFAULT_REGION"] = "auto"

    run = Uploader(version, channel, dry_run)
    cli_pruned = ""

    try:
        if os.path.isdir(cli_dir):
            _upload_cli(run, cli_dir)
            if channel in RELEASE_CHANNELS:
                cli_pruned = run.update_versions_tracker("cli", version, MAX_RELEASE_VERSIONS)
        else:
            log.warn("CLI directory not found: %s" % cli_dir)

        npm_dir = os.environ.get("NPM_DIR", "") or os.path.join(root, "dist", "npm")
        if os.path.isdir(npm_dir):
            _upload_npm(run, npm_dir)
        else:
            log.info("npm directory not found: %s (skipping)" % npm_dir)

        if channel in RELEASE_CHANNELS:
            run.cleanup_old_versions("cli", cli_pruned)
    except BashExitError as exc:
        return exc.code

    log.step("R2 upload complete")
    log.info("  Artifacts uploaded: %d" % run.uploaded)
    log.info("  Version: v%s" % version)
    log.info("  Channel: %s" % channel)
    log.info("  Bucket: %s" % run.bucket)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
