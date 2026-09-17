#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/deploy-account.sh`.

Deploys ONE region of the account Worker to Cloudflare: apply the D1 migrations
for that region's database, then `wrangler deploy` against that region's config.
Region and target select a wrangler config file by NAME
(`wrangler.<region>.toml`, or `wrangler.edge-<region>.toml` when
`--target edge`), and everything else the deploy needs -- the D1 database, the
R2 bucket, the routes -- lives inside that file rather than in this script.

NOTHING HERE REACHES CLOUDFLARE IN A TEST. `npx` (and `npm`, on the install
branch) are the only external tools, so the differential
(`.ci/rediacc_ci/tests/test_deploy_deploy_account.py`) puts RECORDING FAKES for
both on a scratch PATH and points both sides at a fixture repo root.
`.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one
real run" clause and says in as many words that the mocked parity ledger is a
separate, achievable piece of work. This is that piece.

THE DATABASE NAME IS READ WITH grep/head/sed, NOT WITH A TOML PARSER, and that
is a reproduction rather than a preference. The twin's line 50 is

    DB_NAME=$(grep 'database_name' "$CONFIG" | head -1 | sed 's/.*= *"\\(.*\\)"/\\1/' || true)

and every one of those three stages leaks into what gets migrated:

  * `grep` matches the SUBSTRING anywhere on any line, comments included.
  * `head -1` takes the first match, so a file with two `[[d1_databases]]`
    blocks migrates the first and never mentions the second.
  * `sed` is a SUBSTITUTION, not a match: a line the pattern does not fit is
    passed through UNCHANGED, so the "could not read" guard below never fires
    and the whole line becomes the database name.

Two of those are defects (see the two constants near the bottom of this
docstring's section, `A_COMMENT_BECOMES_THE_DATABASE_NAME` and
`THE_LAST_QUOTE_WINS`), both driven against the real twin and pinned in the
differential in both directions. A `tomllib.load` port would produce a
DIFFERENT database name on those inputs, which is exactly the thing a port may
not do. So the pipeline is shelled out to the same three binaries.

TWO DIVERGENCES IN TEXT NOBODY PARSES, both the standard `${VAR:?msg}` shape
this campaign has ruled on before (`deploy/set_www_worker_secrets.py`,
`deploy/wait_for_preview_worker.py`, `deploy/delete_r2_channel.py`):

  1. `REGION="${ARG_REGION:?--region is required (eu, us)}"` (:21) is bash's own
     refusal and prints the SCRIPT PATH AS INVOKED and a bash LINE NUMBER:

         .ci/scripts/deploy/deploy-account.sh: line 21: ARG_REGION: --region is required (eu, us)

     `MISSING_REGION` carries the `VAR: message` half, on the same stream, with
     the same exit status 1.
  2. An argument whose flag is not a valid shell identifier (`--foo.bar`) is
     `printf -v`'s own failure inside `common.sh:341`, exit 2, and names
     common.sh's path and line. The port prints `deploy-account.sh: printf:
     ...` with the same status, following `autopilot/sweep_collect.py:284`.

`:?` IS AN UNSET-OR-EMPTY TEST, so `--region=` refuses exactly as an absent
`--region` does. Driven; a port testing only for presence would resolve
`wrangler..toml` and report it missing instead.

K=5 LEDGER: `.ci/shadow/w7p6-deploy-account.observations.jsonl`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import log
from rediacc_ci.core import common

if typing.TYPE_CHECKING:
    import pathlib

# The twin's own name, used only in the two bash-diagnostic stand-ins.
SELF = "deploy-account.sh"

# The `${ARG_REGION:?...}` stand-in named in the docstring. The twin's own text
# after the `VAR: ` prefix bash adds; kept verbatim, because that is the text.
MISSING_REGION = "ARG_REGION: --region is required (eu, us)"

# `TARGET="${ARG_TARGET:-production}"` (:22) and the one value that branches
# (:25). ANY OTHER VALUE IS PRODUCTION: there is no validation in the twin, so `--target edg` deploys the production config for the region without comment.
DEFAULT_TARGET = "production"
EDGE_TARGET = "edge"

# `$REPO_ROOT/workers/account` (:20), relative to the repo root `common.sh`'s own location resolves to. NOT cwd: the twin can be invoked from anywhere.
WORKER_SUBDIR = ("workers", "account")

# The sed program at :50, byte for byte. A BRE, and both `.*` are GREEDY, which is what `THE_LAST_QUOTE_WINS` below is about.
SED_PROGRAM = r's/.*= *"\(.*\)"/\1/'

# The string grep looks for (:50). A SUBSTRING, not a key: `# database_name` and `preview_database_name` both match.
DB_NAME_NEEDLE = "database_name"

# THE TWO DEFECTS THE grep/head/sed PIPELINE HAS, named as constants so the differential can assert them by name instead of restating the sentences, and so nobody "fixes" them in the port. Both driven against the real twin on
# 2026-09-13 in a fixture tree; both are reproduced here, not repaired, because
# repairing a twin is a cutover decision and this file is not the cutover.
#
# 1. A COMMENT BECOMES THE DATABASE NAME. A config whose first `database_name` occurrence is a comment (`# database_name is chosen per environment`) fails the sed pattern, so sed passes the line through unchanged, `[[ -z "$DB_NAME" ]]` is false, and the run prints "Applying migrations to # database_name is chosen per environment..." and calls `wrangler d1 migrations apply '#
# database_name is chosen per environment'`. The guard at :51-54 exists for exactly this case and cannot see it, because the pipeline's output is only empty when grep matched NOTHING.
#   2. THE LAST QUOTE WINS. `database_name = "account-db-eu" # was "old-db"`
# yields the eleven-word string `account-db-eu" # was "old-db`, because `\(.*\)` runs to the final `"` on the line.
#
# Blast radius today is zero: all seven `workers/account/wrangler.*.toml` files carry exactly one `database_name` line each, in the canonical shape.
A_COMMENT_BECOMES_THE_DATABASE_NAME = True
THE_LAST_QUOTE_WINS = True


def config_name(region: str, target: str) -> str:
    """`wrangler.edge-<region>.toml` or `wrangler.<region>.toml` (:24-29).

    The comparison is against the literal `edge` and nothing else, so every
    other target string -- including `Edge`, `edge ` and a typo -- selects the
    PRODUCTION config. That is the twin's behaviour and it is not guarded there.
    """
    if target == EDGE_TARGET:
        return "wrangler.edge-%s.toml" % region
    return "wrangler.%s.toml" % region


def strip_newlines(token: str) -> str:
    """`printf '%s' "$TOKEN" | tr -d '\\r\\n'` (:41).

    NOT shelled out, unlike the database-name pipeline, and the reason is that
    this one is provably the same: `tr -d` deletes BYTES, and in UTF-8 the bytes
    0x0D and 0x0A cannot appear inside a multi-byte sequence, so deleting the
    two characters and deleting the two bytes agree for every input.

    WHAT IT DOES NOT DO, and the twin does not either: an ACCOUNT ID carrying a
    stray carriage return is passed through untouched, because only the token is
    cleaned. Named in the differential rather than fixed.
    """
    return token.replace("\r", "").replace("\n", "")


def needs_npm_install(worker_dir: pathlib.Path, env: dict[str, str]) -> bool:
    """`if ! command -v wrangler &>/dev/null && [[ ! -d "node_modules" ]]` (:45).

    BOTH conditions, and the `!` binds to the `command -v` pipeline alone: an
    install happens only when wrangler is absent from PATH AND the worker
    directory has no `node_modules`. A machine with a global wrangler and no
    local install therefore skips it, which is the CD workflow's own case.

    `node_modules` is a RELATIVE path in the twin, tested after the `cd`, so it
    is the worker directory's -- passed explicitly here rather than depending on
    the process cwd.
    """
    if shutil.which("wrangler", path=env.get("PATH")) is not None:
        return False
    return not (worker_dir / "node_modules").is_dir()


def database_name(config: str) -> str:
    """`grep ... | head -1 | sed ...`, run as the same three binaries (:50).

    STDERR IS INHERITED on all three, as the twin leaves it: a grep that cannot
    open the file has already been ruled out by the `-f` check above, but a
    read error mid-file is the only trace anyone would get.

    `|| true` MAKES THE PIPELINE'S STATUS UNOBSERVABLE, including grep's 1 for
    "no match" and the 141 a SIGPIPE from `head` leaves on a long file. Nothing
    is checked here either; the empty result is what the caller tests.

    Bytes are decoded with `surrogateescape` so a config that is not valid UTF-8
    reaches `wrangler` as the same bytes bash would have handed it. The one spot
    where the two still differ is a diagnostic: Python renders an unpaired
    surrogate on stderr as a backslash escape.
    """
    grep = subprocess.Popen(["grep", DB_NAME_NEEDLE, config], stdout=subprocess.PIPE)
    head = subprocess.Popen(["head", "-1"], stdin=grep.stdout, stdout=subprocess.PIPE)
    if grep.stdout is not None:
        # The parent must drop its copy or `head` exiting early never reaches `grep` as a SIGPIPE, which is the twin's behaviour on a long file.
        grep.stdout.close()
    sed = subprocess.Popen(["sed", SED_PROGRAM], stdin=head.stdout, stdout=subprocess.PIPE)
    if head.stdout is not None:
        head.stdout.close()
    out, _ = sed.communicate()
    grep.wait()
    head.wait()
    # Command substitution strips ALL trailing newlines, not just one.
    return out.decode("utf-8", "surrogateescape").rstrip("\n")


def migrations_argv(db_name: str, config: str) -> list[str]:
    """`npx wrangler d1 migrations apply "$DB_NAME" --remote --config "$CONFIG"` (:60)."""
    return ["npx", "wrangler", "d1", "migrations", "apply", db_name, "--remote", "--config", config]


def deploy_argv(config: str) -> list[str]:
    """`npx wrangler deploy --config "$CONFIG"` (:64)."""
    return ["npx", "wrangler", "deploy", "--config", config]


def _run(argv: list[str]) -> int:
    """One child with BOTH streams inherited, as the twin leaves them.

    wrangler's own output is the entire visible result of a good run, and
    capturing it would move it out of the workflow log.
    """
    return subprocess.run(argv, check=False).returncode


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    worker_dir = common.repo_root().joinpath(*WORKER_SUBDIR)

    region = args.get("ARG_REGION", "")
    if not region:
        # THE DIVERGENCE: bash prefixes this with `<script>: line 21: `.
        print(MISSING_REGION, file=sys.stderr, flush=True)
        return 1
    target = args.get("ARG_TARGET") or DEFAULT_TARGET

    config = config_name(region, target)
    if not (worker_dir / config).is_file():
        log.error("Wrangler config not found: %s/%s" % (worker_dir, config))
        return 1

    os.chdir(worker_dir)

    for name in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        try:
            common.require_var(name)
        except common.RefusalError as exc:
            exc.report()
            return exc.code

    # `export CLOUDFLARE_API_TOKEN` after the strip: children see the clean one.
    os.environ["CLOUDFLARE_API_TOKEN"] = strip_newlines(os.environ["CLOUDFLARE_API_TOKEN"])

    if needs_npm_install(worker_dir, dict(os.environ)):
        status = _run(["npm", "install"])
        if status != 0:
            return status  # `set -e`

    db_name = database_name(config)
    if not db_name:
        log.error("Could not read database_name from %s" % config)
        return 1

    log.step("Deploying account worker: %s %s (%s)" % (target, region, config))
    log.step("Applying migrations to %s..." % db_name)
    status = _run(migrations_argv(db_name, config))
    if status != 0:
        return status  # `set -e`
    log.info("Migrations applied to %s" % db_name)

    status = _run(deploy_argv(config))
    if status != 0:
        return status  # `set -e`
    log.info("Account worker deployed: %s %s" % (target, region))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
