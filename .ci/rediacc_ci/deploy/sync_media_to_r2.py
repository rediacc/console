#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/sync-media-to-r2.sh`.

The UPLOAD direction of the media sync: three `aws s3 sync` calls that push
`packages/www/public/assets/{tutorials/video,videos,tutorials/audio}` into the
R2 bucket `rediacc-www-media`. Its download counterpart is `sync-media-from-r2.sh`, ported beside this file as `rediacc_ci.deploy.sync_media_from_r2`. Same bucket, same three prefixes, same flag vocabulary; the differences between the two ports are exactly the differences between reading a bucket and writing one, and they are named where they occur rather than factored into a
shared helper (see the last section).

INCREMENTAL BY DESIGN, which is the twin's own headline and the reason there is no "changed files" logic to port: `aws s3 sync` uploads only what is new or whose size/mtime differs, so re-running after re-recording a handful of tutorials pushes those and not the whole 5GB+ tree.

THE AUDIO PREFIX IS NOT A CDN ASSET. `tutorials/audio/` is a build-time TTS cache (`.ci/docs/r2-media-setup.md` #3) that the public media.rediacc.com host does not serve at all. It rides this script purely because it is the same bucket and the same primitive, and it still gets the one-year `Cache-Control` below, which is meaningless for an object nothing fetches over HTTP.

-----------------------------------------------------------------------------
NOTHING HERE REACHES R2 IN A TEST
-----------------------------------------------------------------------------
`aws` is the one external tool that carries a credential, so the differential (`.ci/rediacc_ci/tests/test_deploy_sync_media_to_r2.py`) puts a RECORDING FAKE `aws` on a scratch PATH that logs its exact argv and answers from the environment. `.ci/shadow/w7p5a-status.json` records this path as blocked only
for the "one real run" clause and says in as many words that the mocked parity
ledger is a SEPARATE, achievable piece of work. This is that piece.

THE CALL LOG IS THE PRIMARY EVIDENCE. What this script prints is three `Syncing ...` lines plus a three-line closing recipe, none of it derived from what actually moved; the entire observable effect is the argv of the `aws s3 sync` calls. A port that dropped `--cache-control`, or appended `--delete` in the wrong position, would print byte-identical output and exit 0 while
publishing objects with the wrong headers.

-----------------------------------------------------------------------------
FOUR FACTS ABOUT THE TWIN THAT LOOK LIKE MISTAKES. ALL FOUR ARE REPRODUCED
-----------------------------------------------------------------------------
  1. A RUN THAT UPLOADS NOTHING PRINTS `Sync complete.` AND EXITS 0. `sync_dir`
     answers a missing local directory with `return 0` and a warning, and
     nothing counts how many of the three legs actually ran. Driven 2026-09-13
     in a fixture with no `packages/www/public/assets/videos/`:
     `--solutions-only` printed one `Skipping ...` warning, then `Sync
     complete. Verify with:` and its two recipe lines, and exited 0. THIS IS THE
     VACUITY CLASS, in the script whose whole job is to move bytes: the closing
     line is unconditional on work, so "it said complete" is not evidence that
     anything was published.
     `A_RUN_THAT_UPLOADS_NOTHING_STILL_SAYS_COMPLETE` names it.
  2. `require_var` VALIDATES ONLY ITS FIRST ARGUMENT. The twin writes
     `require_var CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID
     CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY CLOUDFLARE_R2_MEDIA_ENDPOINT` and
     `common.sh:131-137` reads `local var_name="$1"` and stops. Driven
     2026-09-13: `require_var A B C` with only `A` set reaches the next line.
     What catches the other two is `set -u`, three lines later, and only when
     they are UNSET.
     `REQUIRE_VAR_CHECKS_ONLY_ITS_FIRST_ARGUMENT` names it.
  3. AN EMPTY SECRET OR AN EMPTY ENDPOINT IS NOT CAUGHT AT ALL, which is fact 2
     with the one escape `set -u` leaves open. Driven 2026-09-13 with
     `CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY=` and
     `CLOUDFLARE_R2_MEDIA_ENDPOINT=`: the run handed `--endpoint-url` followed
     by the empty string to `aws`, printed the closing recipe and exited 0. This
     is the SHAPE of the 2026-08-28 incident the repository's own pre-bash hook
     describes ("uploads nothing, exits 0, and warns about the wrong thing"):
     the script cannot tell a credential it never validated from one that works.
     `AN_EMPTY_CREDENTIAL_IS_NOT_CAUGHT` names it.
  4. A PATH THAT EXISTS AS A FILE IS REPORTED AS "not present locally". The test
     is `[[ ! -d "$local_dir" ]]`, so a regular file where a directory belongs
     produces the same warning as an absent path. Driven 2026-09-13. Fails
     closed, with a diagnosis that names the wrong thing, and `os.path.isdir`
     reproduces it exactly.

None is repaired here. This wave's acceptance rule is agreement with the live twin; changing what a credential guard accepts, or making a no-op run non-zero, is a cutover-box decision rather than a port's.

-----------------------------------------------------------------------------
THE ONE DIVERGENCE: WHAT `set -u` PRINTS
-----------------------------------------------------------------------------
When `CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY` or `CLOUDFLARE_R2_MEDIA_ENDPOINT` is UNSET, bash's own refusal names the bash FILE and a bash LINE NUMBER:

    .ci/scripts/deploy/sync-media-to-r2.sh: line 83: \
CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY: unbound variable

This port prints the `NAME: unbound variable` half, on the same stream, with the same exit status 1. Identical ruling and identical wording to `deploy/promote_r2_to_stable.py`, `deploy/delete_r2_channel.py` and `deploy/upload_repos_to_r2.py`. The differential asserts BOTH directions so nobody "fixes" either side into the other.

THE ORDER OF THE REFUSALS IS PART OF THE CONTRACT: `require_var` on the access key, then `require_cmd aws`, then the secret, then the endpoint. A machine with no `aws` and no credentials at all reports the MISSING BINARY.

-----------------------------------------------------------------------------
THE TWIN SHARES REAL LOGIC WITH `sync_media_from_r2` AND IT IS DELIBERATELY NOT
FACTORED OUT
-----------------------------------------------------------------------------
The two BASH twins share nothing but `common.sh`. There is no media-sync bash library, each file carries its own copy of the parse loop, its own copy of the credential block and its own `SYNC_ARGS`, and the copies are NOT identical: this one adds `--cache-control` and `--delete`, the other adds `mkdir -p`, and the `--dry-run` sentences differ word for word. A shared Python helper
would have no bash counterpart, and an edit to one twin would silently change the other's port. Collapsing the pair belongs to the cutover box that deletes both bash files. Same ruling, and the same reason, as `promote_r2_to_stable.py` gives for its hotfix sibling.

K=5 LEDGER: `.ci/shadow/w7p6-sync-media-to-r2.observations.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `BUCKET="rediacc-www-media"` (twin :36). Hard-coded there, hard-coded here.
BUCKET = "rediacc-www-media"

# `CACHE_CONTROL="public, max-age=31536000"` (twin :37). ONE ARGV ELEMENT
# CONTAINING A SPACE, which is why the differential records argv with a quoting join rather than a plain space: `--cache-control 'public,
# max-age=31536000'` and `--cache-control public, max-age=31536000` are two
# different calls that a space-joined log renders identically.
CACHE_CONTROL = "public, max-age=31536000"

# The three legs, in the twin's order (twin :107-117), as (local_path_relative_to_repo_root, remote_prefix). ORDER IS OBSERVABLE: it is the order of the step lines and of the `aws` calls. Every local path keeps its TRAILING SLASH because the twin's does, and `aws` is handed it as written.
TUTORIALS = ("packages/www/public/assets/tutorials/video/", "tutorials/video/")
SOLUTIONS = ("packages/www/public/assets/videos/", "videos/")
AUDIO = ("packages/www/public/assets/tutorials/audio/", "tutorials/audio/")

# The environment names, as literals, for the messages and the registry.
ACCESS_KEY_ENV = "CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID"
SIGNING_KEY_ENV = "CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY"
ENDPOINT_ENV = "CLOUDFLARE_R2_MEDIA_ENDPOINT"

# `export AWS_DEFAULT_REGION="auto"` (twin :84). R2 has one region and it is
# spelled `auto`; a real region name makes the SigV4 signature wrong.
AWS_DEFAULT_REGION = "auto"

# The closing recipe (twin :120-124), three `log_info` calls rather than one multi-line message, so it is three `✓ ` lines and the two indented ones keep their two leading spaces. `\$CLOUDFLARE_R2_MEDIA_ENDPOINT` in the twin is an ESCAPED dollar inside double quotes, so it reaches the terminal as a literal `$CLOUDFLARE_R2_MEDIA_ENDPOINT` for the reader to paste, NOT as the endpoint
# this run used. Reproduced literally; a port that interpolated it would leak the endpoint into a log that is often shared.
CLOSING_LINES = (
    "Sync complete. Verify with:",
    "  aws s3 sync --dryrun <local-dir> s3://%s/<prefix>/ --endpoint-url "
    "$CLOUDFLARE_R2_MEDIA_ENDPOINT" % BUCKET,
    "  curl -sI https://media.rediacc.com/<path>",
)

# The four facts in the module docstring, as constants so a test can assert each by name instead of restating the sentence.
A_RUN_THAT_UPLOADS_NOTHING_STILL_SAYS_COMPLETE = True
REQUIRE_VAR_CHECKS_ONLY_ITS_FIRST_ARGUMENT = True
AN_EMPTY_CREDENTIAL_IS_NOT_CAUGHT = True
A_FILE_IN_A_DIRECTORYS_PLACE_IS_REPORTED_AS_ABSENT = True


class UnknownArgumentError(Exception):
    """The `*)` arm of the twin's parse loop (twin :71-74). Exit 1."""

    def __init__(self, argument: str) -> None:
        super().__init__("Unknown argument: %s" % argument)
        self.argument = argument
        self.code = 1


class UnboundVariableError(Exception):
    """`set -u` on a variable the twin's own guard never checked.

    See "THE ONE DIVERGENCE" in the module docstring: bash prefixes its message
    with the script name and a line number, this carries the `NAME: unbound
    variable` half, and both exit 1 on stderr.
    """

    def __init__(self, name: str) -> None:
        super().__init__("%s: unbound variable" % name)
        self.name = name
        self.code = 1


class BashExitError(Exception):
    """`set -e` ending the run on the unguarded `aws s3 sync`.

    The failing program's own stderr is the only explanation the caller gets and its status becomes the script's. Unlike the download twin there is no `mkdir` here, so `aws` is the only command that can end a run this way.
    """

    def __init__(self, code: int) -> None:
        super().__init__("set -e: exit %d" % code)
        self.code = code


class Options:
    """The five parse-loop variables (twin :39-43), as one object.

    Plain attributes rather than a dataclass: the differential compares these against literal booleans, and a dataclass would add a repr nobody reads and an equality nobody wants (two runs with the same flags are not the same run).
    """

    def __init__(
        self,
        *,
        tutorials: bool = True,
        solutions: bool = True,
        audio: bool = True,
        dry_run: bool = False,
        delete: bool = False,
    ) -> None:
        self.tutorials = tutorials
        self.solutions = solutions
        self.audio = audio
        self.dry_run = dry_run
        self.delete = delete

    def selected(self) -> list[tuple[str, str]]:
        """The legs this run will sync, in the twin's order."""
        legs = []
        if self.tutorials:
            legs.append(TUTORIALS)
        if self.solutions:
            legs.append(SOLUTIONS)
        if self.audio:
            legs.append(AUDIO)
        return legs


def parse_args(argv: list[str]) -> Options:
    """The `while [[ $# -gt 0 ]]` loop (twin :45-76), verbatim in behaviour.

    EACH `--*-only` FLAG SETS ALL THREE BOOLEANS, so they are not additive and the LAST one wins: `--tutorials-only --audio-only` syncs audio alone. A port that OR-ed them would upload two prefixes where the twin uploads one. `--dry-run` and `--delete` are orthogonal and may appear anywhere.

    `--delete` IS A STRING IN THE TWIN (`DELETE_FLAG="--delete"`, tested with
    `-n`), not a boolean, and the string is what gets appended to `SYNC_ARGS`. A boolean here is the same thing observed through the same two questions ("was it given" and "what is appended"), and the appended literal lives in `sync_args` where the twin puts it.

    An EMPTY STRING argument reaches the `*)` arm and is refused as `Unknown argument: ` with a trailing space, exactly as the twin's `log_error "Unknown argument: $1"` renders it.
    """
    opts = Options()
    for argument in argv:
        if argument == "--tutorials-only":
            opts.tutorials, opts.solutions, opts.audio = True, False, False
        elif argument == "--solutions-only":
            opts.tutorials, opts.solutions, opts.audio = False, True, False
        elif argument == "--audio-only":
            opts.tutorials, opts.solutions, opts.audio = False, False, True
        elif argument == "--dry-run":
            opts.dry_run = True
        elif argument == "--delete":
            opts.delete = True
        else:
            raise UnknownArgumentError(argument)
    return opts


def repo_root() -> str:
    """`REPO_ROOT` (twin :35), by location rather than by cwd.

    The twin resolves `.ci/scripts/deploy/../../..` from its own `BASH_SOURCE`;
    this file sits at `.ci/rediacc_ci/deploy/`, three directories under the same root, so the arithmetic is identical and neither side depends on the caller's cwd. `abspath`, NOT `realpath`: bash's `cd` is logical, so a checkout reached through a symlink keeps the symlinked spelling on both sides, and the paths in the step lines therefore match byte for byte.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", ".."))


def environment() -> dict[str, str | None]:
    """Every variable this module reads, ONE `os.environ.get` PER NAME.

    NOT `dict(os.environ)`, AND THE DIFFERENCE IS A GATE RATHER THAN A STYLE. `check:ci-python-env-registry` derives a module's declared inputs by walking its AST for literal `os.environ` subscripts, `.get` calls and `in` tests; a read that goes through a materialised copy or a local alias is INVISIBLE to it, and the module then reports zero inputs while depending on three.

    `None` MEANS UNSET AND `""` MEANS SET-BUT-EMPTY, and the distinction is the whole of fact 3 in the module docstring: `set -u` fires on the first and not on the second, so a helper that folded them together would refuse a run the twin performs.
    """
    return {
        ACCESS_KEY_ENV: os.environ.get("CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID"),
        SIGNING_KEY_ENV: os.environ.get("CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY"),
        ENDPOINT_ENV: os.environ.get("CLOUDFLARE_R2_MEDIA_ENDPOINT"),
    }


def require_access_key(env: dict[str, str | None]) -> str:
    """`require_var CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID ...` (twin :78).

    THE ONLY ONE OF THE THREE THAT IS ACTUALLY GUARDED (fact 2). Unset and empty
    are one outcome here, because `common.sh`'s test is `[[ -z "${!v:-}" ]]`.
    """
    return common.require_var(ACCESS_KEY_ENV, {ACCESS_KEY_ENV: env.get(ACCESS_KEY_ENV) or ""})


def require_secret_key(env: dict[str, str | None]) -> str:
    """`export AWS_SECRET_ACCESS_KEY="$CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY"` (twin :83).

    Not a guard: an expansion that `set -u` happens to police. An empty value is accepted and exported, which is fact 3.
    """
    value = env.get(SIGNING_KEY_ENV)
    if value is None:
        raise UnboundVariableError(SIGNING_KEY_ENV)
    return value


def require_endpoint(env: dict[str, str | None]) -> str:
    """`SYNC_ARGS=(--endpoint-url "$CLOUDFLARE_R2_MEDIA_ENDPOINT" ...)` (twin :86).

    Same shape as the secret, three lines later, which is why an unset secret is reported before an unset endpoint even though both are missing.
    """
    value = env.get(ENDPOINT_ENV)
    if value is None:
        raise UnboundVariableError(ENDPOINT_ENV)
    return value


def sync_args(endpoint: str, *, dry_run: bool, delete: bool) -> list[str]:
    """`SYNC_ARGS` (twin :86-95). ORDER IS OBSERVABLE, so it is pinned.

    Base, then `--dryrun`, then `--delete`, because that is the order the twin appends them in. `aws` does not care; the recorded argv does, and the argv is the evidence this port is judged on. `--cache-control` is ONE element carrying a space (see `CACHE_CONTROL`).
    """
    args = ["--endpoint-url", endpoint, "--cache-control", CACHE_CONTROL, "--no-progress"]
    if dry_run:
        args.append("--dryrun")
    if delete:
        args.append("--delete")
    return args


def upload_argv(local_dir: str, remote_prefix: str, args: list[str]) -> list[str]:
    """`aws s3 sync "$local_dir" "s3://$BUCKET/$remote_prefix" "${SYNC_ARGS[@]}"` (twin :104)."""
    return ["aws", "s3", "sync", local_dir, "s3://%s/%s" % (BUCKET, remote_prefix), *args]


def _run(argv: list[str], env: dict[str, str]) -> None:
    """The one unguarded external command under `set -e`.

    stdout and stderr are INHERITED, not captured: the twin does not capture them either, and `aws --no-progress` still writes an `upload: ...` line per object that a caller reads as the record of what moved.
    """
    proc = subprocess.run(argv, env=env, check=False)
    if proc.returncode != 0:
        raise BashExitError(proc.returncode)


def sync_dir(local_dir: str, remote_prefix: str, args: list[str], env: dict[str, str]) -> bool:
    """`sync_dir` (twin :98-105). True when it uploaded, False when it skipped.

    THE SKIP IS `return 0`, NOT AN ERROR, and nothing downstream counts the Falses. That is fact 1 in the module docstring. The boolean exists so the differential can assert the skip happened without parsing the warning, and so a future cutover has a value to build a floor on; the twin discards it.

    `os.path.isdir` FOLLOWS SYMLINKS, exactly as `[[ -d ]]` does, and answers False for a regular file, which is fact 4.

    THE TRAILING SLASH MAKES THAT ROBUST IN A WAY WORTH RECORDING, because it swallowed a planted defect while the plant was being validated 2026-09-13. Every `local_dir` here ends in `/`, and a trailing slash asks the kernel to resolve the final component: `os.path.islink("<dir>/")` is False even for a symlinked directory, and `os.path.lexists("<file>/")` is False for a regular
    file. So a port that tried to distinguish a symlink at THIS path would find it cannot, and a reader who "simplifies" the slash away would change three answers at once.
    """
    if not os.path.isdir(local_dir):
        log.warn("Skipping %s (not present locally)" % local_dir)
        return False
    log.step("Syncing %s -> s3://%s/%s" % (local_dir, BUCKET, remote_prefix))
    _run(upload_argv(local_dir, remote_prefix, args), env)
    return True


def child_env(access_key: str, secret_key: str) -> dict[str, str]:
    """The three `export`s (twin :82-84), as the environment the children get.

    `export` in the twin mutates the whole process; passing an explicit `env=`
    to each child reproduces the only part of that which is observable, and leaves this process's own environment alone so an importing caller does not inherit a credential it never asked for.
    """
    env = dict(os.environ)
    env["AWS_ACCESS_KEY_ID"] = access_key
    env["AWS_SECRET_ACCESS_KEY"] = secret_key
    env["AWS_DEFAULT_REGION"] = AWS_DEFAULT_REGION
    return env


def main(argv: list[str]) -> int:
    try:
        opts = parse_args(argv)
    except UnknownArgumentError as exc:
        log.error(str(exc))
        return exc.code

    env = environment()
    try:
        access_key = require_access_key(env)
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    try:
        common.require_cmd("aws")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    try:
        secret_key = require_secret_key(env)
        endpoint = require_endpoint(env)
    except UnboundVariableError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code

    child = child_env(access_key, secret_key)
    args = sync_args(endpoint, dry_run=opts.dry_run, delete=opts.delete)
    if opts.dry_run:
        log.info("Dry run: no objects will be uploaded or deleted.")
    if opts.delete:
        log.warn("Delete mode: remote objects with no local counterpart will be removed.")

    try:
        for local_relative, remote_prefix in opts.selected():
            sync_dir(os.path.join(repo_root(), local_relative), remote_prefix, args, child)
    except BashExitError as exc:
        return exc.code

    if not opts.dry_run:
        for line in CLOSING_LINES:
            log.info(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
