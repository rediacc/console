#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/simulate-promotion.sh`.

Simulates an edge-to-stable promotion into a throwaway `<channel>-promoted` R2
channel, so the package-manager install tests (apt/dnf/apk/pacman) can run
against PROMOTED bytes before a real promotion happens. A broken promotion is
then caught in CI rather than after `promote-stable` has already moved
production bytes.

NOTHING HERE REACHES R2 OR CLOUDFLARE IN A TEST. `aws` and (through
`cf-purge-urls.sh`) `curl` are the two external tools that carry a credential,
so the differential
(`.ci/rediacc_ci/tests/test_deploy_simulate_promotion.py`) puts RECORDING FAKES
for both on a scratch PATH, with an on-disk fixture standing in for the bucket.
`.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one
real run" clause and says in as many words that the mocked parity ledger is a
separate, achievable piece of work. This is that piece.

THE CALL LOG IS THE PRIMARY EVIDENCE. The run prints six or seven `log_info`
lines, none of them derived from what moved; the ENTIRE observable effect is the
`aws` invocations, the exact `--key`/`--copy-source` pairs they carry, and the
URL list handed to `cf-purge-urls.sh`.

-----------------------------------------------------------------------------
`awk`, `sed`, `sleep` AND `cf-purge-urls.sh` ARE CALLED, NOT REIMPLEMENTED
-----------------------------------------------------------------------------
`awk` because the field program at twin :187 is what turns an
`aws s3 ls --recursive` listing into keys, and its exact behaviour is the thing
that has to survive: default `FS` splits on RUNS of whitespace, so a key
containing two consecutive spaces comes back with one, and `printf "%s%s", $i,
(i < NF ? OFS : ORS)` rejoins with single spaces. A Python `line.split(None,
3)[3]` would keep the doubled space and quietly promote a different key. Driven
2026-09-13 in the fixture, where a key with an embedded space is deliberately
present.

`sed`, through `core.common.sed_in_place`, because the substitution is a regex
with `|` delimiters.

`sleep` because both retry loops call it as an external program, and calling it
here rather than using `time.sleep` makes the RETRY SCHEDULE observable in the
call log rather than only in wall-clock time. That is what lets the differential
prove `1 2 3 4 5` attempts with 15/30/45/60-second gaps without waiting three
minutes for it, and it is what a `time.sleep` port would have hidden.

`cf-purge-urls.sh` is invoked as the bash script the twin invokes, for the
reason `upload_repos_to_r2.py` gives: agreement with the live twin includes that
script's exact bytes.

-----------------------------------------------------------------------------
THE COPIES ARE PARALLEL, SO THEIR ORDER IS NOT DETERMINISTIC ON EITHER SIDE
-----------------------------------------------------------------------------
`xargs -P 8 -I{} bash -c 'copy_one_object "$@"' _ {}` dispatches up to eight
independent server-side copies at once, so two runs of the SAME implementation
can log them in different orders. The port uses a `ThreadPoolExecutor` with the
same width and reproduces xargs' failure contract:

  * a command exiting 1..125 does NOT stop the run, every remaining item is
    still attempted, and xargs exits 123 at the end;
  * `set -e` then ends the script with that 123.

The differential compares the copy calls as a MULTISET within each directory
block rather than as a sequence, and says so where it does it. Everything
outside those blocks is compared in order.

-----------------------------------------------------------------------------
FIVE FACTS ABOUT THE TWIN THAT LOOK LIKE MISTAKES. ALL FIVE ARE REPRODUCED
-----------------------------------------------------------------------------
  1. THE MISSING-CREDENTIAL MESSAGE NAMES THE WRONG VARIABLE. Twin :41 tests
     `AWS_ACCESS_KEY_ID` and twin :42 reports `CLOUDFLARE_R2_ACCESS_KEY_ID not
     set`. The two names are related (the workflow maps one to the other) but
     they are not the same variable, so a reader who exports the name in the
     message still gets the same refusal.
     `THE_ACCESS_KEY_MESSAGE_NAMES_A_DIFFERENT_VARIABLE` names it.
  2. `AWS_SECRET_ACCESS_KEY` IS DOCUMENTED AS REQUIRED AND IS NEVER CHECKED.
     The header lists it under "Required env"; nothing in the body tests it. A
     run with the id and no secret gets as far as the first `aws` call and fails
     there, with aws's message rather than this script's.
     `THE_SECRET_KEY_IS_NEVER_CHECKED` names it.
  3. THE EMPTY-CHANNEL FLOOR MAY BE UNREACHABLE, DEPENDING ON THE `aws` BUILD.
     The floor at twin :192 tests whether the awk output file is empty, but it
     is only reached if the `aws s3 ls | awk` pipeline SUCCEEDED, and `pipefail`
     is on. An `aws s3 ls` that exits non-zero on a prefix with no objects
     therefore ends the run one line earlier, with aws's own message and aws's
     own status, and the floor's sentence never prints. Both endings are driven
     in the differential and both agree, because the port reproduces the
     structure rather than the guess about which one the installed aws does.
     `THE_EMPTY_CHANNEL_FLOOR_SITS_BEHIND_PIPEFAIL` names it.
  4. `/tmp/config` IS A FIXED PATH SHARED BY BOTH SED-FIX FILES, and it is never
     removed. A run leaves the LAST downloaded config there, and a concurrent
     run of this script on the same machine would read the other's bytes. In CI
     each job has its own container, which is why it has never mattered.
     `THE_SED_FIX_SCRATCH_PATH_IS_FIXED` names it.
  5. AN UNSET `CLOUDFLARE_ZONE_ID` ENDS THE RUN AFTER THE PROMOTION HAS ALREADY
     HAPPENED. Twin :226 spells it `"$CLOUDFLARE_ZONE_ID"`, with no `:-`, so
     `set -u` refuses on an UNBOUND variable at the very last line. Every object
     has been copied and both configs rewritten by then. Contrast
     `promote-r2-to-stable.sh:180`, which uses `${CLOUDFLARE_ZONE_ID:-}` and
     lets `cf-purge-urls.sh` do the refusing.
     `AN_UNSET_ZONE_IS_AN_UNBOUND_VARIABLE_AT_THE_END` names it.

None is repaired here. This wave's acceptance rule is agreement with the live
twin.

-----------------------------------------------------------------------------
ONE `${VAR:?msg}` GUARD, ONE DIVERGENCE, AND TWO SMALLER ONES
-----------------------------------------------------------------------------
`: "${CHANNEL:?CHANNEL is required (the source channel, e.g. pr-123)}"` is
bash's own refusal and names the bash FILE and a bash LINE NUMBER before the
message. This port prints the `VAR: msg` half, on the same stream, with the same
exit status 1. Identical ruling to `deploy/promote_r2_to_stable.py`.

`set -u` ON `$CLOUDFLARE_ZONE_ID` (fact 5) is the second: bash says
`CLOUDFLARE_ZONE_ID: unbound variable` with its own prefix, this port says the
same words with the script's name.

A `$GITHUB_ENV` THAT CANNOT BE APPENDED TO is the third, and it is the same
shape: bash's redirection error against this port's own sentence, same stream,
same status 1.

K=5 LEDGER: `.ci/shadow/w7p6-simulate-promotion.observations.jsonl`.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import os
import subprocess
import sys
import tempfile

from rediacc_ci import log
from rediacc_ci.core import common

# The twin's own name, used in the bash-diagnostic stand-ins.
SELF = "simulate-promotion.sh"

# `BUCKET="rediacc-releases"` (twin :51) and the public host (twin :202, :213),
# both hard-coded in the twin.
BUCKET = "rediacc-releases"
PUBLIC_HOST = "https://releases.rediacc.com"

# `CC_MUTABLE="no-cache"` (twin :97). Channel paths reuse filenames per release,
# so nothing under `<fmt>/<promoted>/` is safe to cache.
CC_MUTABLE = "no-cache"

# `for dir in apt rpm apk archlinux` (twin :179). ORDER MATTERS to the call log
# and to the purge list. NOTE `cli` IS ABSENT: this script promotes only the
# package-manager repositories, because only those are what the install tests
# exercise.
CHANNEL_DIRS = ("apt", "rpm", "apk", "archlinux")

# `aws configure set ...` (twin :62-64), in order. R2's S3 API drops multi-MB
# streams under the CLI's default 10-way parallelism, so the transfer profile is
# tamed before anything moves. THESE MUTATE `~/.aws/config`; that is the twin's
# behaviour and it is not sandboxed here either.
AWS_CONFIGURE: tuple[tuple[str, str], ...] = (
    ("default.s3.max_concurrent_requests", "3"),
    ("default.s3.multipart_threshold", "64MB"),
    ("default.s3.multipart_chunksize", "32MB"),
)

# `awk '{ for (i = 4; i <= NF; i++) printf "%s%s", $i, (i < NF ? OFS : ORS) }'`
# (twin :187), verbatim. Fields 1..3 of `aws s3 ls --recursive` are date, time
# and size; everything after is the key.
KEY_AWK = '{ for (i = 4; i <= NF; i++) printf "%s%s", $i, (i < NF ? OFS : ORS) }'

# `xargs -P 8` (twin :198) and the two retry loops (twin :80, :160).
COPY_PARALLELISM = 8
COPY_ATTEMPTS = 3
COPY_BACKOFF_SECONDS = 5
CP_ATTEMPTS = 5
CP_BACKOFF_SECONDS = 15

# GNU xargs' status when at least one invocation exited 1..125 (twin :198 under
# `set -e`). Not 1: a caller reading the script's status sees 123.
XARGS_FAILURE_STATUS = 123

# `/tmp/config` (twin :209-211). A FIXED path shared by both sed-fix files,
# which is fact 4 in the module docstring.
SED_FIX_SCRATCH = "/tmp/config"

# The two files whose channel URLs are rewritten after the copy (twin :208).
# Templates over the PROMOTED channel, because the rewrite happens on the copy
# that has already landed there.
SED_FIX_FILES = ("rpm/%s/rediacc.repo", "archlinux/%s/rediacc.conf")

# `.ci/scripts/deploy/cf-purge-urls.sh` (twin :226). RELATIVE in the twin, and
# reached from the repository root the script `cd`s to at :36.
PURGE_SCRIPT_RELATIVE = ".ci/scripts/deploy/cf-purge-urls.sh"

# `export BUCKET CC_MUTABLE CLOUDFLARE_R2_ENDPOINT SRC_PREFIX DST_PREFIX`
# (twin :145, :183). The exports exist so the `bash -c` children xargs spawns
# can see them; nothing `aws` reads is among them. Reproduced anyway, because
# the environment a child sees is part of what the two implementations are being
# compared on.
EXPORTED_FOR_CHILDREN = (
    "BUCKET",
    "CC_MUTABLE",
    "CLOUDFLARE_R2_ENDPOINT",
    "SRC_PREFIX",
    "DST_PREFIX",
)

# The five facts in the module docstring, as constants so a test can assert each
# by name instead of restating the sentence.
THE_ACCESS_KEY_MESSAGE_NAMES_A_DIFFERENT_VARIABLE = True
THE_SECRET_KEY_IS_NEVER_CHECKED = True
THE_EMPTY_CHANNEL_FLOOR_SITS_BEHIND_PIPEFAIL = True
THE_SED_FIX_SCRATCH_PATH_IS_FIXED = True
AN_UNSET_ZONE_IS_AN_UNBOUND_VARIABLE_AT_THE_END = True


class BashExitError(Exception):
    """`set -e`, `set -u` or an explicit `exit N` ending the run."""

    def __init__(self, code: int) -> None:
        super().__init__("bash exit %d" % code)
        self.code = code


def repo_root() -> str:
    """`get_repo_root` (common.sh:205-210), by location rather than by cwd."""
    return str(common.repo_root())


def promoted_channel(channel: str) -> str:
    """`PROMOTED="${CHANNEL}-promoted"` (twin :50)."""
    return "%s-promoted" % channel


def endpoint_args(endpoint: str) -> list[str]:
    """`EP=(--endpoint-url "$CLOUDFLARE_R2_ENDPOINT")` (twin :52).

    AN ARRAY, expanded as `"${EP[@]}"`, so it is EXACTLY TWO elements even when
    the endpoint contains whitespace. Contrast `promote-r2-to-stable.sh`, whose
    `$EP` is unquoted and word-splits; the two twins genuinely differ here and
    the ports differ with them.
    """
    return ["--endpoint-url", endpoint]


def configure_argv(key: str, value: str) -> list[str]:
    """`aws configure set <key> <value>` (twin :62-64)."""
    return ["aws", "configure", "set", key, value]


def list_argv(prefix: str, endpoint: str) -> list[str]:
    """`aws s3 ls "s3://<bucket>/<prefix>" --recursive "${EP[@]}"` (twin :186)."""
    return [
        "aws",
        "s3",
        "ls",
        "s3://%s/%s" % (BUCKET, prefix),
        "--recursive",
        *endpoint_args(endpoint),
    ]


def copy_object_argv(dst_key: str, src_key: str, endpoint: str) -> list[str]:
    """`aws s3api copy-object ...` (twin :161-167).

    `s3api`, NOT `s3 cp`/`s3 sync`, and the twin's comment is emphatic about
    why: R2 does not implement the object-tagging surface, and the high-level
    commands reach for it on EVERY s3-to-s3 path. `--tagging-directive` is
    omitted, so neither the tag read nor the tag replace is attempted;
    `--metadata-directive REPLACE` is required because a new Cache-Control is
    being set.
    """
    return [
        "aws",
        "s3api",
        "copy-object",
        "--bucket",
        BUCKET,
        "--key",
        dst_key,
        "--copy-source",
        "%s/%s" % (BUCKET, src_key),
        "--metadata-directive",
        "REPLACE",
        "--cache-control",
        CC_MUTABLE,
        "--endpoint-url",
        endpoint,
    ]


def download_argv(key: str, endpoint: str) -> list[str]:
    """`aws s3 cp "s3://<bucket>/<file>" /tmp/config "${EP[@]}"` (twin :209)."""
    return [
        "aws",
        "s3",
        "cp",
        "s3://%s/%s" % (BUCKET, key),
        SED_FIX_SCRATCH,
        *endpoint_args(endpoint),
    ]


def upload_argv(key: str, endpoint: str) -> list[str]:
    """`aws_s3_cp_retry /tmp/config "s3://..." "${EP[@]}" --cache-control ...` (twin :211).

    `aws_s3_cp_retry` prepends `s3 cp --cli-read-timeout 0` (twin :81), so the
    flag lands BEFORE the two paths rather than at the end.
    """
    return [
        "aws",
        "s3",
        "cp",
        "--cli-read-timeout",
        "0",
        SED_FIX_SCRATCH,
        "s3://%s/%s" % (BUCKET, key),
        *endpoint_args(endpoint),
        "--cache-control",
        CC_MUTABLE,
    ]


def purge_argv(zone: str) -> list[str]:
    """`.ci/scripts/deploy/cf-purge-urls.sh --zone "$CLOUDFLARE_ZONE_ID"` (twin :226)."""
    return [PURGE_SCRIPT_RELATIVE, "--zone", zone]


def purge_url(dst_prefix: str, relative: str) -> str:
    """`https://releases.rediacc.com/${DST_PREFIX}${key#"$SRC_PREFIX"}` (twin :202)."""
    return "%s/%s%s" % (PUBLIC_HOST, dst_prefix, relative)


def strip_prefix(key: str, prefix: str) -> str:
    """`${src_key#"$SRC_PREFIX"}`: the prefix is QUOTED inside the expansion, so
    it is a literal and not a pattern, and it is removed only when present."""
    return key.removeprefix(prefix)


def read_lines(text: str) -> list[str]:
    """`while IFS= read -r key; do [[ -n "$key" ]] || continue; ...` (twin :200-203).

    A FINAL LINE WITH NO NEWLINE IS DROPPED (`read` returns non-zero at EOF), and
    an EMPTY line is skipped by the explicit `continue`.
    """
    if not text:
        return []
    lines = text.split("\n")
    lines.pop()
    return [line for line in lines if line]


def _flush() -> None:
    sys.stdout.flush()
    sys.stderr.flush()


def _run(argv: list[str], **kwargs) -> int:
    """One child with BOTH streams inherited unless a caller says otherwise."""
    _flush()
    return subprocess.run(argv, check=False, **kwargs).returncode


def _sleep(seconds: int) -> None:
    """`sleep $((n))` as the EXTERNAL PROGRAM bash runs.

    Not `time.sleep`. See the module docstring: shelling out is what puts the
    retry schedule in the call log, where a differential can read it.
    """
    _run(["sleep", str(seconds)])


def list_keys(prefix: str, endpoint: str) -> list[str]:
    """`aws s3 ls ... | awk '...' >"$KEYS"` (twin :186-187), under `pipefail`.

    Raises `BashExitError` when either stage fails, which is fact 3: the floor
    below is only reached when the pipeline SUCCEEDED, so an `aws s3 ls` that
    exits non-zero on an empty prefix ends the run here instead.

    THE TEMPORARY FILE IS REAL, because the twin reads it twice (once for the
    copies, once for the purge URLs) and `[[ -s ]]` asks about the FILE. Its
    name is `mktemp`'s and appears nowhere observable.
    """
    handle, keys_path = tempfile.mkstemp()
    os.close(handle)
    try:
        _flush()
        listing = subprocess.run(
            list_argv(prefix, endpoint),
            stdout=subprocess.PIPE,
            check=False,
        )
        with open(keys_path, "wb") as out:
            awk = subprocess.run(
                ["awk", KEY_AWK],
                input=listing.stdout,
                stdout=out,
                check=False,
            )
        # `pipefail`: the RIGHTMOST non-zero status wins.
        status = awk.returncode or listing.returncode
        if status:
            raise BashExitError(status)
        with open(keys_path, encoding="utf-8", errors="surrogateescape") as handle_in:
            text = handle_in.read()
    finally:
        # `rm -f "$KEYS"` on both the refusal path (twin :193) and the normal
        # one (twin :204).
        with contextlib.suppress(FileNotFoundError):
            os.unlink(keys_path)
    return read_lines(text)


def copy_one_object(src_key: str, src_prefix: str, dst_prefix: str, endpoint: str) -> int:
    """`copy_one_object` (twin :147-176), as one xargs child would run it.

    THE PREFIX GUARD IS THE POINT OF THE FUNCTION. A key that does not start
    with `SRC_PREFIX` would make the strip below a silent no-op and write to a
    DOUBLED destination (`apk/edge-promoted/apt/edge/...`). A wrong destination
    is worse than a failed copy, because the install tests that follow would
    read a channel nobody wrote.

    Returns the child's status; 1 for either refusal, 0 for a copy that landed.
    """
    if not src_key.startswith(src_prefix):
        print(
            "key '%s' is not under expected prefix '%s'" % (src_key, src_prefix),
            file=sys.stderr,
            flush=True,
        )
        return 1
    dst_key = dst_prefix + strip_prefix(src_key, src_prefix)
    for attempt in range(1, COPY_ATTEMPTS + 1):
        # `>/dev/null` ON STDOUT ONLY: copy-object's JSON reply is discarded and
        # its stderr is inherited.
        status = _run(copy_object_argv(dst_key, src_key, endpoint), stdout=subprocess.DEVNULL)
        if status == 0:
            return 0
        if attempt == COPY_ATTEMPTS:
            print("copy-object failed after 3 attempts: %s" % src_key, file=sys.stderr, flush=True)
            return 1
        _sleep(attempt * COPY_BACKOFF_SECONDS)
    return 0  # unreachable: attempt 3 always returns


def aws_s3_cp_retry(argv_tail: list[str], display: list[str]) -> int:
    """`aws_s3_cp_retry` (twin :78-91). Five attempts, 15/30/45/60-second gaps.

    `display` is what `$*` expands to in the failure message: the arguments the
    FUNCTION was called with, NOT the `aws s3 cp --cli-read-timeout 0` prefix it
    adds. Kept separate for that reason alone.
    """
    for attempt in range(1, CP_ATTEMPTS + 1):
        if _run(argv_tail) == 0:
            return 0
        if attempt == CP_ATTEMPTS:
            log.error("aws s3 cp %s failed after 5 attempts" % " ".join(display))
            return 1
        log.warn(
            "aws s3 cp attempt %d failed, retrying in %ds..."
            % (attempt, attempt * CP_BACKOFF_SECONDS)
        )
        _sleep(attempt * CP_BACKOFF_SECONDS)
    return 0  # unreachable


def _copy_directory(
    dir_name: str, channel: str, promoted: str, endpoint: str, purge_urls: list[str]
) -> None:
    """One iteration of `for dir in apt rpm apk archlinux` (twin :179-205)."""
    log.info("Copying %s/%s/ -> %s/%s/ (server-side)" % (dir_name, channel, dir_name, promoted))
    src_prefix = "%s/%s/" % (dir_name, channel)
    dst_prefix = "%s/%s/" % (dir_name, promoted)
    os.environ["SRC_PREFIX"] = src_prefix
    os.environ["DST_PREFIX"] = dst_prefix

    keys = list_keys(src_prefix, endpoint)

    # THE ANTI-VACUITY FLOOR (twin :192-196), reproduced with the twin's exact
    # sentence. An empty listing is a FAILURE, not a fast success: the install
    # tests that follow would run against an empty channel and pass while
    # proving nothing. Fact 3 is about whether this line is reachable, not about
    # whether it is right.
    if not keys:
        log.error("no objects found under %s; refusing to promote an empty channel" % src_prefix)
        raise BashExitError(1)

    # `xargs -P 8`. See the module docstring for the failure contract.
    _flush()
    with concurrent.futures.ThreadPoolExecutor(max_workers=COPY_PARALLELISM) as pool:
        statuses = list(
            pool.map(lambda key: copy_one_object(key, src_prefix, dst_prefix, endpoint), keys)
        )
    if any(status != 0 for status in statuses):
        raise BashExitError(XARGS_FAILURE_STATUS)

    purge_urls += [purge_url(dst_prefix, strip_prefix(key, src_prefix)) for key in keys]


def _sed_fix(channel: str, promoted: str, endpoint: str, purge_urls: list[str]) -> None:
    """The two config rewrites (twin :208-216).

    THE DOWNLOAD IS THE CONDITION: `if aws s3 cp ... 2>/dev/null; then`, so a
    file that is not in the promoted channel is skipped in silence. Everything
    after it is unguarded.
    """
    for template in SED_FIX_FILES:
        key = template % promoted
        status = _run(download_argv(key, endpoint), stderr=subprocess.DEVNULL)
        if status != 0:
            continue
        expression = "s|/%s/|/%s/|g" % (channel, promoted)
        _flush()
        if common.sed_in_place([expression, SED_FIX_SCRATCH]):
            raise BashExitError(1)
        argv = upload_argv(key, endpoint)
        display = [SED_FIX_SCRATCH, "s3://%s/%s" % (BUCKET, key), *endpoint_args(endpoint)]
        display += ["--cache-control", CC_MUTABLE]
        if aws_s3_cp_retry(argv, display):
            raise BashExitError(1)
        purge_urls.append("%s/%s" % (PUBLIC_HOST, key))
        log.info("Fixed channel in %s" % key)


def _purge(purge_urls: list[str], zone: str) -> None:
    """`printf '%s\\n' "${PURGE_URLS[@]}" | cf-purge-urls.sh --zone <zone>` (twin :225-226).

    Guarded by `${#PURGE_URLS[@]} -gt 0`, so an empty list makes no call at all.
    Under `pipefail` the pipeline's status is the purge script's, since `printf`
    cannot fail here.
    """
    payload = "".join(url + "\n" for url in purge_urls)
    argv = purge_argv(zone)
    try:
        status = _run(argv, input=payload.encode("utf-8", "surrogateescape"))
    except OSError as exc:
        # A MISSING OR UNRUNNABLE PURGE SCRIPT. bash reports this itself with
        # its own line number and status 127; Python raises.
        print("%s: %s: %s" % (SELF, argv[0], exc.strerror), file=sys.stderr, flush=True)
        raise BashExitError(127) from exc
    if status:
        raise BashExitError(status)


def main(argv: list[str]) -> int:
    del argv  # the twin takes no argv; every input is an environment variable

    root = repo_root()
    try:
        os.chdir(root)
    except OSError as exc:
        print("%s: cd: %s: %s" % (SELF, root, exc.strerror), file=sys.stderr, flush=True)
        return 1

    try:
        common.require_cmd("aws")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    channel = os.environ.get("CHANNEL", "")
    if not channel:
        # THE DIVERGENCE: bash prefixes this with `<path>: line N: `.
        print(
            "CHANNEL: CHANNEL is required (the source channel, e.g. pr-123)",
            file=sys.stderr,
            flush=True,
        )
        return 1

    # FACT 1: the test is on AWS_ACCESS_KEY_ID, the message names a different
    # variable. FACT 2: AWS_SECRET_ACCESS_KEY is never tested at all.
    if not os.environ.get("AWS_ACCESS_KEY_ID", ""):
        log.error("CLOUDFLARE_R2_ACCESS_KEY_ID not set")
        return 1
    endpoint = os.environ.get("CLOUDFLARE_R2_ENDPOINT", "")
    if not endpoint:
        log.error("CLOUDFLARE_R2_ENDPOINT not set")
        return 1

    promoted = promoted_channel(channel)

    # `[[ -n "${GITHUB_ENV:-}" ]] && echo "PROMOTED=..." >>"$GITHUB_ENV"`
    # (twin :55). An AND-list, so an UNSET variable is not a failure; a set one
    # whose file cannot be appended to IS, because the append is the command
    # after the final `&&`.
    github_env = os.environ.get("GITHUB_ENV", "")
    if github_env:
        try:
            with open(github_env, "a", encoding="utf-8") as handle:
                handle.write("PROMOTED=%s\n" % promoted)
        except OSError as exc:
            print("%s: %s: %s" % (SELF, github_env, exc.strerror), file=sys.stderr, flush=True)
            return 1

    for key, value in AWS_CONFIGURE:
        # UNGUARDED under `set -e`: an `aws configure set` that fails ends the
        # run with aws's own status, before anything is listed or copied.
        status = _run(configure_argv(key, value))
        if status:
            return status

    os.environ["BUCKET"] = BUCKET
    os.environ["CC_MUTABLE"] = CC_MUTABLE
    os.environ["SRC_PREFIX"] = ""
    os.environ["DST_PREFIX"] = ""

    purge_urls: list[str] = []
    try:
        for dir_name in CHANNEL_DIRS:
            _copy_directory(dir_name, channel, promoted, endpoint, purge_urls)
        _sed_fix(channel, promoted, endpoint, purge_urls)
    except BashExitError as exc:
        return exc.code

    log.info("Promotion simulated: %s -> %s" % (channel, promoted))

    if not purge_urls:
        return 0

    # FACT 5: `"$CLOUDFLARE_ZONE_ID"` with no `:-`, under `set -u`, AFTER the
    # promotion has already happened.
    if "CLOUDFLARE_ZONE_ID" not in os.environ:
        print("%s: CLOUDFLARE_ZONE_ID: unbound variable" % SELF, file=sys.stderr, flush=True)
        return 1
    try:
        _purge(purge_urls, os.environ["CLOUDFLARE_ZONE_ID"])
    except BashExitError as exc:
        return exc.code
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
