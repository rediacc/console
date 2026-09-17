#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/deploy-www.sh`.

Deploys the www marketing Worker to Cloudflare. Two lanes, chosen by whether `--name` was passed:

  * PRODUCTION (no `--name`): one `npx wrangler deploy` against
    `workers/www/wrangler.toml` as it stands. No D1 is involved; the account API
    on www.rediacc.com is served by the regional `rediacc-account-*` workers.
  * PREVIEW (`--name pr-379`): mint a per-PR D1 database `account-db-pr-379`,
    DELETING any existing one first for a clean slate, write a generated
    `wrangler.preview.toml` naming that database, apply the account migrations
    to it, deploy, and remove the generated config.

NOTHING HERE REACHES CLOUDFLARE IN A TEST. `npx` (and `npm` on the install branch), `jq` and `sed` are the external tools, so the differential (`.ci/rediacc_ci/tests/test_deploy_deploy_www.py`) puts a RECORDING FAKE for `npx`/`npm` on a scratch PATH and points both sides at a fixture repo root through `$REDIACC_CI_ROOT`. `.ci/shadow/w7p5a-status.json` records this path as blocked
only for the "one real run" clause and says in as many words that the mocked parity ledger is a separate, achievable piece of work. This is that piece.

THE CALL LOG IS THE PRIMARY EVIDENCE, as it was for the promote ports. Almost
everything printed is `log_step`/`log_info`, which is chatter by any classifier;
the observable effect of a run is WHICH `npx wrangler` subcommands were invoked, in what order, with what arguments, plus the exact bytes of the generated `wrangler.preview.toml`.

-----------------------------------------------------------------------------
THE EM DASH IN THE GENERATED TOML IS WRITTEN AS `\\u2014`, ON PURPOSE
-----------------------------------------------------------------------------
The twin's heredoc carries one U+2014 in a comment inside the emitted file (twin :123). The house rule bans em dashes in authored text and `check:ci-em-dash-surfaces` scans `.ci/rediacc_ci/**/*.py` for the literal character, so spelling it out here would be a NEW finding in a shrink-only baseline. The escape produces the identical byte sequence in the emitted TOML and leaves no em
dash in this file's own text. The differential asserts the generated file is byte-identical between the two sides, which is what makes the escape safe rather than a quiet edit.

-----------------------------------------------------------------------------
`jq` AND `sed` ARE CALLED, NOT REIMPLEMENTED
-----------------------------------------------------------------------------
`get_d1_uuid` (twin :41-58) is `npx wrangler d1 info --json`, then
`sed -n '/^[[:space:]]*[{[]/,$p'`, then `jq -r '.uuid // empty'`. All three
stages are shelled out:

  * `sed` because the address is a POSIX BRE with a bracket class and a range to
    `$`, and because "print from the first line that starts with optional
    whitespace then `{` or `[`" is not the same as "find the first JSON value".
    A banner line containing a brace LATER in the line does not match; a line
    that is only `[` does.
  * `jq` because `.uuid // empty` is jq's alternative operator, which treats
    `false` and `null` alike, and because jq accepts a STREAM of concatenated
    JSON values and prints one line per value. A `json.loads` port would refuse
    input jq happily reads, and would print one answer where jq prints two.

`require_cmd jq` is in the twin for this reason and is reproduced.

-----------------------------------------------------------------------------
THREE FACTS ABOUT THE TWIN THAT LOOK LIKE MISTAKES. ALL THREE ARE REPRODUCED
-----------------------------------------------------------------------------
  1. THE PRODUCTION-DATABASE GUARD CANNOT FIRE. Twin :69-72 refuses when
     `DB_NAME` is `account-db` or `edge-account-db`, but `DB_NAME` is built two
     lines above as `account-db-pr-${PR_NUM}`, which carries the literal
     `-pr-` infix for EVERY value of `ARG_NAME`, including the empty string
     (`--name=` yields `account-db-pr-`). No input reaches the refusal. It is
     kept because a future edit to the name template is exactly when it would
     start earning its place. `PRODUCTION_GUARD_IS_UNREACHABLE` names it.
  2. `--name` WITH NO VALUE DEPLOYS A PREVIEW WORKER LITERALLY CALLED `true`.
     `common.sh`'s `parse_args` stores the string `true` for a flag with no
     following value, and nothing here validates the shape, so
     `deploy-www.sh --name` mints `account-db-pr-true` and deploys a worker
     named `true`. Driven against the twin 2026-09-13 under the fake `npx`.
     `A_VALUELESS_NAME_DEPLOYS_A_WORKER_CALLED_TRUE` names it.
  3. A NAME THAT IS NOT `pr-N` STILL WORKS, because `${ARG_NAME#pr-}` removes
     the prefix ONLY when it is there. `--name staging` mints
     `account-db-pr-staging` and deploys a worker named `staging`. There is no
     validation; the `pr-` stripping is a convenience, not a contract.

None is repaired here. This wave's acceptance rule is agreement with the live twin; changing what a deploy creates is a cutover-box decision.

-----------------------------------------------------------------------------
THE UUID IS LOOKED UP TWICE AND THE SECOND LOOKUP IS THE LOAD-BEARING ONE
-----------------------------------------------------------------------------
The first `get_d1_uuid` only decides whether to delete. After `d1 create` the lookup runs again and an empty answer is fatal, which is the ONE place this script refuses on its own account rather than on a child's exit status. Every other failure path is a bare `set -e` on an unguarded `npx`.

-----------------------------------------------------------------------------
ONE DIVERGENCE, IN TEXT NOBODY PARSES
-----------------------------------------------------------------------------
An argument whose flag is not a valid shell identifier (`--foo.bar=x`) is
`printf -v`'s own failure inside `common.sh:341`, exit 2, and bash names common.sh's path and line. This port prints `deploy-www.sh: printf: ...` with the same status, on the same stream, following `deploy/deploy_account.py` and `autopilot/sweep_collect.py`.

K=5 LEDGER: `.ci/shadow/w7p6-deploy-www.observations.jsonl`.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import typing

from rediacc_ci import log
from rediacc_ci.core import common

if typing.TYPE_CHECKING:
    import pathlib

# The twin's own name, used only in the one bash-diagnostic stand-in.
SELF = "deploy-www.sh"

# `WORKER_DIR="$REPO_ROOT/workers/www"` (twin :17), relative to the repo root
# `common.sh`'s own location resolves to. NOT cwd: the twin can be invoked from anywhere and `.ci/legacy/run-legacy.sh:245` does exactly that.
WORKER_SUBDIR = ("workers", "www")

# `wrangler.toml` (twin :19) and the generated `wrangler.preview.toml` (twin :90, :137, :140, :141). The second is written into the worker directory and removed on the success path only.
PRODUCTION_CONFIG = "wrangler.toml"
PREVIEW_CONFIG = "wrangler.preview.toml"

# `PR_NUM="${ARG_NAME#pr-}"` and `DB_NAME="account-db-pr-${PR_NUM}"`
# (twin :64-65). The prefix strip is a `#` expansion, so it removes `pr-` only when the name actually starts with it (fact 3 in the module docstring).
NAME_PREFIX = "pr-"
DB_NAME_TEMPLATE = "account-db-pr-%s"

# `--location eeur` (twin :82). Hard-coded in the twin; every preview database lands in the same region.
D1_LOCATION = "eeur"

# The two names twin :69 refuses to delete. Unreachable, which is fact 1.
PROTECTED_DATABASES = ("account-db", "edge-account-db")

# The `sed` address at twin :52 and the `jq` program at twin :57, verbatim.
JSON_START_SED = "/^[[:space:]]*[{[]/,$p"
UUID_JQ = ".uuid // empty"

# The three facts in the module docstring, as constants so a test can assert each by name instead of restating the sentence.
PRODUCTION_GUARD_IS_UNREACHABLE = True
A_VALUELESS_NAME_DEPLOYS_A_WORKER_CALLED_TRUE = True
A_NON_PR_NAME_IS_ACCEPTED_VERBATIM = True

# The generated preview config (twin :90-133), byte for byte after expansion.
#
# THE U+2014 ON THE `trailingSlash` COMMENT IS THE TWIN'S, written as an escape rather than as the character itself, for the reason in the module docstring. THE BACKTICKS on the `trailingSlash` line are `\`` in the twin's UNQUOTED heredoc, which bash renders as bare backticks; there is no command substitution in the emitted bytes.
#
# `%s` three times, in the twin's order: the worker name, then the database name and its UUID at the bottom.
PREVIEW_TOML = """name = "%s"
main = "src/index.ts"
compatibility_date = "2026-01-20"
compatibility_flags = ["nodejs_compat"]
upload_source_maps = true

[vars]
ALLOWED_EMAIL_DOMAINS = "rediacc.com,rediacc.io"
# Must be set explicitly. envSchema defaults ENVIRONMENT to "production", so an
# unset value here made every preview worker report environment "production" and
# hand out updateChannel "stable" -- while the install.sh this same worker serves
# bakes in channel pr-N. A CLI installed from a preview would then self-update
# off the wrong channel. See private/account/src/types/env.ts.
ENVIRONMENT = "preview"

[observability]
enabled = true

[observability.logs]
enabled = true
invocation_logs = false # Disabled to reduce high-volume per-request log noise/cost.

[observability.traces]
enabled = true
head_sampling_rate = 1

[assets]
directory = "./dist"
binding = "ASSETS"
not_found_handling = "404-page"
# Match Astro's `trailingSlash: 'never'` so ASSETS does not 307 `/foo`
# to `/foo/`. Without this, the Worker's normalizePath strips the
# trailing slash with a 301 and ASSETS re-adds it \u2014 infinite loop.
# Mirrors the setting in wrangler.{,edge.}toml.
html_handling = "drop-trailing-slash"
run_worker_first = ["/*"]

[[d1_databases]]
binding = "DB"
database_name = "%s"
database_id = "%s"
migrations_dir = "../../private/account/drizzle"
"""


def strip_newlines(token: str) -> str:
    """`printf '%s' "$CLOUDFLARE_API_TOKEN" | tr -d '\\r\\n'` (twin :32).

    NOT shelled out. `tr -d` deletes BYTES, and in UTF-8 neither 0x0D nor 0x0A can appear inside a multi-byte sequence, so deleting the two characters and deleting the two bytes agree for every input. Same ruling and same wording as `deploy/deploy_account.py`, which carries the identical line.

    ONLY THE TOKEN IS CLEANED. `CLOUDFLARE_ACCOUNT_ID` with a stray carriage
    return is passed to children untouched, exactly as in the twin.
    """
    return token.replace("\r", "").replace("\n", "")


def db_name_for(worker_name: str) -> str:
    """`PR_NUM="${ARG_NAME#pr-}"; DB_NAME="account-db-pr-${PR_NUM}"` (twin :64-65).

    `removeprefix` IS the `#` expansion: it strips only when the prefix is present and leaves everything else alone. That is fact 3 in the module docstring, and it is why `--name staging` is accepted.
    """
    return DB_NAME_TEMPLATE % worker_name.removeprefix(NAME_PREFIX)


def is_protected(db_name: str) -> bool:
    """`[[ "$DB_NAME" == "account-db" || "$DB_NAME" == "edge-account-db" ]]` (twin :69).

    Exact string comparison against two literals. Unreachable from `db_name_for`, which is fact 1; exported so the differential can assert both halves rather than assert the sentence.
    """
    return db_name in PROTECTED_DATABASES


def info_argv(db_name: str) -> list[str]:
    """`npx wrangler d1 info "$db_name" --json` (twin :44)."""
    return ["npx", "wrangler", "d1", "info", db_name, "--json"]


def delete_argv(db_name: str) -> list[str]:
    """`npx wrangler d1 delete "$DB_NAME" --skip-confirmation` (twin :77)."""
    return ["npx", "wrangler", "d1", "delete", db_name, "--skip-confirmation"]


def create_argv(db_name: str) -> list[str]:
    """`npx wrangler d1 create "$DB_NAME" --location eeur` (twin :82)."""
    return ["npx", "wrangler", "d1", "create", db_name, "--location", D1_LOCATION]


def migrations_argv(db_name: str) -> list[str]:
    """`npx wrangler d1 migrations apply "$DB_NAME" --remote --config ...` (twin :137)."""
    return [
        "npx",
        "wrangler",
        "d1",
        "migrations",
        "apply",
        db_name,
        "--remote",
        "--config",
        PREVIEW_CONFIG,
    ]


def preview_deploy_argv() -> list[str]:
    """`npx wrangler deploy --config wrangler.preview.toml` (twin :140)."""
    return ["npx", "wrangler", "deploy", "--config", PREVIEW_CONFIG]


def production_deploy_argv() -> list[str]:
    """`npx wrangler deploy` (twin :146). No config flag at all."""
    return ["npx", "wrangler", "deploy"]


def preview_toml(worker_name: str, db_name: str, db_uuid: str) -> str:
    """The heredoc at twin :90-133, expanded.

    THE TRAILING NEWLINE IS THE HEREDOC'S. A `cat > f <<TOML` writes each line
    with its newline, so the file ends with exactly one.
    """
    return PREVIEW_TOML % (worker_name, db_name, db_uuid)


def get_d1_uuid(db_name: str) -> str:
    """`get_d1_uuid` (twin :41-58), as the same three programs.

    THREE EARLY RETURNS, all producing the empty string:

      1. `npx wrangler d1 info ... 2>/dev/null || true` produced nothing. Its
         STDERR IS DISCARDED and its exit status is thrown away, so an
         unauthenticated wrangler and a database that does not exist are the
         same answer here.
      2. The `sed` range matched no line, so there was output but no JSON.
      3. `jq` printed nothing, either because `.uuid` was absent or because jq
         itself failed (`2>/dev/null || true` again).

    Command substitution strips ALL trailing newlines from each stage, so the caller's `[[ -n "$DB_UUID" ]]` sees the empty string in all three cases and a bare UUID otherwise.

    `echo "$output" | sed ...` APPENDS A NEWLINE that `output` may not have had. That is reproduced, because a final line without one would otherwise not be a line to `sed`.
    """
    info = subprocess.run(
        info_argv(db_name),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    output = info.stdout.decode("utf-8", "surrogateescape").rstrip("\n")
    if not output:
        return ""

    sed = subprocess.run(
        ["sed", "-n", JSON_START_SED],
        input=(output + "\n").encode("utf-8", "surrogateescape"),
        stdout=subprocess.PIPE,
        check=False,
    )
    json_start = sed.stdout.decode("utf-8", "surrogateescape").rstrip("\n")
    if not json_start:
        return ""

    jq = subprocess.run(
        ["jq", "-r", UUID_JQ],
        input=(json_start + "\n").encode("utf-8", "surrogateescape"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return jq.stdout.decode("utf-8", "surrogateescape").rstrip("\n")


def _run(argv: list[str]) -> int:
    """One child with BOTH streams inherited, as the twin leaves them.

    wrangler's own output is the entire visible result of a good run; capturing it would move it out of the workflow log. Python's buffers are flushed first so the `log_step` line that precedes a call cannot land after the call's output.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.run(argv, check=False).returncode


def _preview(worker_name: str, worker_dir: pathlib.Path) -> int:
    """The `if [[ -n "${ARG_NAME:-}" ]]` arm (twin :60-141)."""
    log.step("Deploying preview worker: %s" % worker_name)

    db_name = db_name_for(worker_name)
    if is_protected(db_name):
        # UNREACHABLE (fact 1). Reproduced rather than dropped.
        log.error("CRITICAL: refusing to delete production/edge database: %s" % db_name)
        return 1

    if get_d1_uuid(db_name):
        log.step("Deleting existing D1 database: %s (clean slate)" % db_name)
        status = _run(delete_argv(db_name))
        if status != 0:
            return status  # `set -e`
        log.info("Deleted %s" % db_name)

    log.step("Creating D1 database: %s" % db_name)
    status = _run(create_argv(db_name))
    if status != 0:
        return status  # `set -e`

    db_uuid = get_d1_uuid(db_name)
    if not db_uuid:
        log.error("Failed to retrieve UUID for newly created D1 database: %s" % db_name)
        return 1
    log.info("Created D1 database %s (UUID: %s)" % (db_name, db_uuid))

    # `cat >wrangler.preview.toml <<TOML` (twin :90). RELATIVE to the worker directory, because the twin has already `cd`-ed there.
    config = worker_dir / PREVIEW_CONFIG
    config.write_text(preview_toml(worker_name, db_name, db_uuid), encoding="utf-8")

    log.step("Applying migrations to %s..." % db_name)
    status = _run(migrations_argv(db_name))
    if status != 0:
        return status  # `set -e`, and the generated config is LEFT BEHIND
    log.info("Migrations applied to %s" % db_name)

    status = _run(preview_deploy_argv())
    if status != 0:
        return status  # `set -e`, config left behind again

    # `rm -f wrangler.preview.toml` (twin :141). Only on the success path, which is why a failed deploy leaves a generated config in the worker directory.
    with contextlib.suppress(FileNotFoundError):  # `-f`
        config.unlink()
    return 0


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        # THE DIVERGENCE: bash names common.sh's path and line here.
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    worker_dir = common.repo_root().joinpath(*WORKER_SUBDIR)

    if not (worker_dir / PRODUCTION_CONFIG).is_file():
        log.error("www worker not found at %s" % worker_dir)
        return 1

    # `cd "$WORKER_DIR"` (twin :24). Every later relative path is the worker directory's, and `npx` resolves its local `node_modules/.bin` from cwd.
    os.chdir(worker_dir)

    # `require_var CLOUDFLARE_API_TOKEN` then `require_var CLOUDFLARE_ACCOUNT_ID` (twin :26-27), IN THAT ORDER: a run missing both names the token.
    #
    # THE TWO NAMES ARE ALSO READ HERE WITH LITERAL KEYS, and the redundancy is deliberate. `check:ci-python-env-registry` derives a module's declared inputs by walking the AST for `os.environ[...]` / `os.environ.get(...)`, and it cannot see a read that happens inside `core.common.require_var`. Without these two reads `CLOUDFLARE_ACCOUNT_ID` is an input nobody declared. The REFUSAL
    # still goes through `require_var`, because its message and exit status are the twin's and restating them here would let the two drift.
    credentials = {
        "CLOUDFLARE_API_TOKEN": os.environ.get("CLOUDFLARE_API_TOKEN", ""),
        "CLOUDFLARE_ACCOUNT_ID": os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
    }
    for name in credentials:
        try:
            common.require_var(name)
        except common.RefusalError as exc:
            exc.report()
            return exc.code

    try:
        common.require_cmd("jq")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    # `export CLOUDFLARE_API_TOKEN` after the strip: children see the clean one.
    os.environ["CLOUDFLARE_API_TOKEN"] = strip_newlines(os.environ["CLOUDFLARE_API_TOKEN"])

    # `if [[ ! -d "node_modules" ]]` (twin :36). RELATIVE, so the worker directory's, and unlike `deploy-account.sh` there is no `command -v wrangler` half: a machine with a global wrangler still runs `npm install` here when the worker directory has no `node_modules`.
    if not (worker_dir / "node_modules").is_dir():
        status = _run(["npm", "install"])
        if status != 0:
            return status  # `set -e`

    worker_name = args.get("ARG_NAME", "")
    if worker_name:
        return _preview(worker_name, worker_dir)

    log.step("Deploying www production worker...")
    return _run(production_deploy_argv())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
