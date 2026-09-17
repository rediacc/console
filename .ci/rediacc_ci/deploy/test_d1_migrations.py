#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/test-d1-migrations.sh`.

Validates that the account D1 migrations apply cleanly against a CLONE of every
regional production database, edge clones first. A migration that works on an
empty schema can still fail on real data (a NOT NULL added to a populated
column, a unique index over existing duplicates), and cloning is what surfaces
that before a release touches production. Every clone is ephemeral and deleted
by an EXIT trap, including on failure; no worker is deployed and no public URL
is created.

NOTHING HERE REACHES CLOUDFLARE IN A TEST. `npx` (wrangler) is the only tool
that carries a credential, so the differential
(`.ci/rediacc_ci/tests/test_deploy_test_d1_migrations.py`) puts a RECORDING FAKE
for it on a scratch PATH with an on-disk D1 state file, and drives both sides
through it. `.ci/shadow/w7p5a-status.json` records this path as blocked only for
the "one real run" clause and says in as many words that the mocked parity
ledger is a separate, achievable piece of work. This is that piece.

THE CALL LOG IS THE PRIMARY EVIDENCE. What the run PRINTS is `::group::`
directives and one `log_info` line; the observable effect is the ordered set of
`npx wrangler d1` invocations, one clone-d1.sh invocation per region, and the
bytes of the generated `wrangler-migration-test.toml`.

-----------------------------------------------------------------------------
`clone-d1.sh`, `jq` AND `sed` ARE CALLED, NOT REIMPLEMENTED
-----------------------------------------------------------------------------
`clone-d1.sh` is invoked as the bash script the twin invokes, for the reason
`upload_repos_to_r2.py` gives: agreement with the live twin includes that
script's exact bytes, and it has its own export/import/verify behaviour that a
second implementation would have to track. Its port, if it gets one, is a
different box.

`jq` reads `regions.json` and `sed` strips wrangler's banner, both for the
reasons `deploy/deploy_www.py` sets out at length for the same two programs.

-----------------------------------------------------------------------------
FOUR FACTS ABOUT THE TWIN THAT LOOK LIKE MISTAKES. ALL FOUR ARE REPRODUCED
-----------------------------------------------------------------------------
  1. AN UNREADABLE `regions.json` PRODUCES A GREEN RUN THAT TESTED NOTHING.
     Both database lists are filled from `< <(jq ... regions.json)`, a PROCESS
     SUBSTITUTION, whose exit status neither `set -e` nor `pipefail` can see. A
     missing or malformed `regions.json` therefore leaves both arrays empty, the
     per-region loop runs zero times, and the run ends with
     `All 0 regional migration tests passed (0 edge + 0 stable)` and exit 0,
     with jq's own complaint the only trace. Driven 2026-09-13 against the twin
     with `regions.json` deleted: exit 0, that exact line.
     `AN_EMPTY_REGION_LIST_IS_A_GREEN_RUN` names it. This is the anti-vacuity
     floor the script does not have, and adding one is a cutover-box decision
     rather than a port's.
  2. THE FIRST REGION USES `$REPO_ROOT` AND EVERY LATER ONE USES
     `$GITHUB_WORKSPACE`. The loop `cd workers/www` RELATIVELY and then
     `cd "$WORKSPACE"`, so iteration 1 resolves against the repository root the
     script derived from its own location and iterations 2..N resolve against
     whatever `GITHUB_WORKSPACE` says. The two are the same directory on a
     GitHub runner and need not be anywhere else.
     `THE_WORKSPACE_TAKES_OVER_AFTER_THE_FIRST_REGION` names it.
  3. THE `Failed to get UUID` GUARD ALMOST NEVER FIRES, because the pipeline
     that feeds it is unguarded under `pipefail`: a `d1 info` that EXITS
     NON-ZERO kills the assignment and therefore the script, with wrangler's
     status and no message from this script at all. The guard is reachable only
     when all three stages succeed and the JSON simply has no `uuid`.
     `THE_UUID_GUARD_IS_ONLY_FOR_VALID_JSON_WITHOUT_A_UUID` names it.
  4. THE GENERATED `wrangler-migration-test.toml` IS REMOVED ONLY ON THE SUCCESS
     PATH of its own iteration, so a failed `migrations apply` leaves it in
     `workers/www/`. Unlike `/tmp/promote-<dir>` in the promote scripts this
     cannot promote anything, but it does leave a tracked-looking file in the
     tree for the next step to trip over.

None is repaired here. This wave's acceptance rule is agreement with the live
twin.

-----------------------------------------------------------------------------
THE CLEANUP TRAP RUNS ON EVERY EXIT AFTER IT IS INSTALLED, AND ONLY THEN
-----------------------------------------------------------------------------
`trap cleanup EXIT` is installed AFTER `require_cmd` and after the two
`${VAR:?}` guards, so a run that refuses for a missing tool or a missing
credential prints no `::group::Cleanup` block at all. After that point every
exit, including the `set -e` ones, prints the block and attempts a delete for
every name appended so far. The trap does NOT change the exit status: it ends
with `echo`, not with `exit`.

A DELETE THAT FAILS IS REPORTED AS FAILED, which the twin's own comment records
as a repair: the old form swallowed stderr, ignored the status and printed
`Deleted $db` unconditionally, so a clone left behind in the Cloudflare account
announced itself as cleaned up.

-----------------------------------------------------------------------------
TWO `${VAR:?msg}` GUARDS, ONE DIVERGENCE
-----------------------------------------------------------------------------
bash's own refusal names the bash FILE and a bash LINE NUMBER before the twin's
message. This port prints the `VAR: msg` half, on the same stream, with the same
exit status 1. Identical ruling to `deploy/promote_r2_to_stable.py` and
`deploy/delete_r2_channel.py`. The ORDER is kept: `require_cmd jq`, then
`require_cmd npx`, then the two variables.

A SECOND, SMALLER DIVERGENCE: a `cd workers/www` that cannot happen is bash's
own `cd: ...: No such file or directory` with the script's path and a line
number. This port prints its own sentence, on the same stream, with the same
exit status 1.

K=5 LEDGER: `.ci/shadow/w7p6-test-d1-migrations.observations.jsonl`.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# The twin's own name, carried in its two guard messages and in the two bash-diagnostic stand-ins.
SELF = "test-d1-migrations.sh"

# `jq -r '.regions[].edgeD1.name' regions.json` and `.regions[].d1.name` (twin :55, :59). EDGE FIRST: edge is the release soak environment, so a regression should surface there before it can reach stable on the next promotion. The order is observable in the call log and is the twin's design.
REGIONS_FILE = "regions.json"
EDGE_JQ = ".regions[].edgeD1.name"
STABLE_JQ = ".regions[].d1.name"

# `REGION_ID="${SOURCE_DB#account-db-}"; REGION_ID="${REGION_ID#edge-account-db-}"`
# (twin :90-91), in that order. Both are `#` expansions, so each strips only when its prefix is actually there.
STABLE_PREFIX = "account-db-"
EDGE_PREFIX = "edge-account-db-"

# `if [[ "$SOURCE_DB" == edge-account-db-* ]]` (twin :94).
EDGE_TAG = "edge"
STABLE_TAG = "stable"

# `DB_NAME="migration-test-${CHANNEL_TAG}-${REGION_ID}-${RUN_ID}-${RUN_ATTEMPT}"`
# (twin :99).
DB_NAME_TEMPLATE = "migration-test-%s-%s-%s-%s"

# `--location eeur` (twin :104), hard-coded exactly as in `deploy-www.sh`.
D1_LOCATION = "eeur"

# `TMPCONFIG="workers/www/wrangler-migration-test.toml"` (twin :116), RELATIVE
# to the current directory, which is fact 2 in the module docstring.
TMPCONFIG_RELATIVE = ("workers", "www", "wrangler-migration-test.toml")
WORKER_SUBDIR = ("workers", "www")
TMPCONFIG_BASENAME = "wrangler-migration-test.toml"

# `"$SCRIPT_DIR/clone-d1.sh"` (twin :114), where SCRIPT_DIR is `.ci/scripts/deploy`. Relative to the repository root so the cutover to a Python clone-d1 is a one-line change in the box that owns it.
CLONE_SCRIPT_RELATIVE = (".ci", "scripts", "deploy", "clone-d1.sh")

# The `sed` address at twin :106 and the `jq` program at twin :107, verbatim.
JSON_START_SED = "/^[[:space:]]*[{[]/,$p"
UUID_JQ = ".uuid // empty"

# `RUN_ID="${GITHUB_RUN_ID:-local}"`, `RUN_ATTEMPT="${GITHUB_RUN_ATTEMPT:-1}"`
# (twin :45-46). `:-` so an EMPTY value falls back too, not just an unset one.
DEFAULT_RUN_ID = "local"
DEFAULT_RUN_ATTEMPT = "1"

# The two `${VAR:?msg}` guards (twin :42-43), in order, as (name, message).
REQUIRED_ENV: tuple[tuple[str, str], ...] = (
    ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_API_TOKEN is required"),
    ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID is required"),
)

# The generated per-region config (twin :117-127), byte for byte after expansion. `%s` twice: the database name, then its UUID.
MIGRATION_TEST_TOML = """name = "migration-test"
main = "src/index.ts"
compatibility_date = "2026-01-20"

[[d1_databases]]
binding = "DB"
database_name = "%s"
database_id = "%s"
migrations_dir = "../../private/account/drizzle"
"""

# The `::warning::` the cleanup emits for a delete it could not do. Quoted whole because its WORDING is the repair the twin's comment describes: it must not say "needs manual removal", because the pre-reap step on the next run sweeps anything older than 60 minutes.
CLEANUP_WARNING = (
    "  ::warning::FAILED to delete test database %s. It is orphaned in the Cloudflare "
    "account; the pre-reap step on the next migration-test run deletes anything older "
    "than 60 minutes, so no manual action is needed unless it survives that."
)

# The four facts in the module docstring, as constants so a test can assert each by name instead of restating the sentence.
AN_EMPTY_REGION_LIST_IS_A_GREEN_RUN = True
THE_WORKSPACE_TAKES_OVER_AFTER_THE_FIRST_REGION = True
THE_UUID_GUARD_IS_ONLY_FOR_VALID_JSON_WITHOUT_A_UUID = True
THE_GENERATED_CONFIG_SURVIVES_A_FAILED_APPLY = True


class MissingEnvError(Exception):
    """One `${VAR:?msg}` firing. Exit 1, message on stderr, nothing else runs."""

    def __init__(self, name: str, message: str) -> None:
        super().__init__("%s: %s" % (name, message))
        self.name = name
        self.message = message


class BashExitError(Exception):
    """`set -e` ending the run on a command the twin does not guard.

    Every `npx wrangler` in the per-region loop, the UUID pipeline under
    `pipefail`, `clone-d1.sh`, both `cd`s and the guard's own `exit 1` are
    unguarded, so the failing program's own stderr is the only explanation the
    caller gets and its status becomes the script's.
    """

    def __init__(self, code: int) -> None:
        super().__init__("set -e: exit %d" % code)
        self.code = code


def repo_root() -> str:
    """`get_repo_root` (common.sh:205-210), from this file's own location.

    `.ci/rediacc_ci/deploy/<this>` is three directories under the root, which is
    the same arithmetic `common.sh` does from `.ci/scripts/lib`. Delegated to
    `common.repo_root()` so `$REDIACC_CI_ROOT` steers a harness the same way it
    steers every other module in the package.
    """
    return str(common.repo_root())


def region_id(source_db: str) -> str:
    """`${SOURCE_DB#account-db-}` then `${REGION_ID#edge-account-db-}` (twin :90-91).

    THE ORDER IS LOAD-BEARING AND IS ALSO WHY BOTH WORK. `edge-account-db-eu`
    does not start with `account-db-`, so the first strip is a no-op and the
    second one does the work; `account-db-eu` is the mirror image. A single
    combined pattern would have to be written carefully to get both.
    """
    return source_db.removeprefix(STABLE_PREFIX).removeprefix(EDGE_PREFIX)


def channel_tag(source_db: str) -> str:
    """`[[ "$SOURCE_DB" == edge-account-db-* ]]` (twin :94). A GLOB, so the name
    must both start with the prefix and have something after it."""
    return EDGE_TAG if source_db.startswith(EDGE_PREFIX) else STABLE_TAG


def test_db_name(source_db: str, run_id: str, run_attempt: str) -> str:
    """`migration-test-<tag>-<region>-<run>-<attempt>` (twin :99)."""
    return DB_NAME_TEMPLATE % (
        channel_tag(source_db),
        region_id(source_db),
        run_id,
        run_attempt,
    )


def read_names(text: str) -> list[str]:
    """`while IFS= read -r _db; do [[ -n "$_db" ]] && ...; done < <(jq ...)`.

    TWO BASH RULES, BOTH REPRODUCED:

      * A FINAL LINE WITH NO NEWLINE IS DROPPED, because `read` stores it and
        then returns non-zero at EOF, so the loop body never runs for it.
      * AN EMPTY LINE IS SKIPPED, and skipping it does NOT end the run even
        though the `&&` list then returns 1: a command that fails before the
        final `&&` is exempt from `set -e` (driven 2026-09-13:
        `set -e; x=""; [[ -n "$x" ]] && echo hi; echo reached` prints
        `reached`).
    """
    if not text:
        return []
    lines = text.split("\n")
    lines.pop()
    return [line for line in lines if line]


def jq_names(program: str, cwd: str) -> str:
    """`jq -r '<program>' regions.json`, with STDERR INHERITED.

    ITS EXIT STATUS IS UNOBSERVABLE IN THE TWIN, because the caller is a PROCESS
    SUBSTITUTION feeding a `while read` loop. Neither `set -e` nor `pipefail`
    reaches inside one, so a missing `regions.json` yields jq's complaint on
    stderr and an empty list here. That is fact 1 in the module docstring, and
    it is reproduced rather than repaired: `check=False`, status discarded.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    proc = subprocess.run(
        ["jq", "-r", program, REGIONS_FILE],
        cwd=cwd,
        stdout=subprocess.PIPE,
        check=False,
    )
    return proc.stdout.decode("utf-8", "surrogateescape")


def create_argv(db_name: str) -> list[str]:
    """`npx wrangler d1 create "$DB_NAME" --location eeur` (twin :104)."""
    return ["npx", "wrangler", "d1", "create", db_name, "--location", D1_LOCATION]


def info_argv(db_name: str) -> list[str]:
    """`npx wrangler d1 info "$DB_NAME" --json` (twin :105)."""
    return ["npx", "wrangler", "d1", "info", db_name, "--json"]


def delete_argv(db_name: str) -> list[str]:
    """`npx wrangler d1 delete "$db" --skip-confirmation` (twin :71)."""
    return ["npx", "wrangler", "d1", "delete", db_name, "--skip-confirmation"]


def migrations_argv(db_name: str) -> list[str]:
    """`npx wrangler d1 migrations apply "$DB_NAME" --remote --config ...` (twin :130).

    The `--config` value is the BASENAME, not the path the file was written to,
    because the twin has `cd workers/www` first.
    """
    return [
        "npx",
        "wrangler",
        "d1",
        "migrations",
        "apply",
        db_name,
        "--remote",
        "--config",
        TMPCONFIG_BASENAME,
    ]


def clone_argv(root: str, source_db: str, db_name: str) -> list[str]:
    """`"$SCRIPT_DIR/clone-d1.sh" --source "$SOURCE_DB" --target "$DB_NAME"` (twin :114)."""
    return [os.path.join(root, *CLONE_SCRIPT_RELATIVE), "--source", source_db, "--target", db_name]


def migration_test_toml(db_name: str, db_uuid: str) -> str:
    """The heredoc at twin :117-127, expanded."""
    return MIGRATION_TEST_TOML % (db_name, db_uuid)


def require_env() -> None:
    """The two guards, in the twin's order.

    Raises on the FIRST missing or empty one, because `: "${VAR:?}"` ends the
    shell there and the later guard never runs. `:?` is an UNSET-OR-EMPTY test,
    so an exported empty string refuses exactly as an absent one does.

    EACH NAME IS READ FROM `os.environ` WITH A LITERAL KEY, and the repetition
    is deliberate rather than sloppy. `check:ci-python-env-registry` derives a
    module's declared inputs by walking the AST for `os.environ[...]` and
    `os.environ.get(...)`; a loop over `REQUIRED_ENV` reading through a dict
    parameter is invisible to that walk, so both variables would be inputs
    nobody declared. `REQUIRED_ENV` stays as the table a reader checks against
    the twin, and the two reads below are what the scanner can see. Asserted by
    `test_the_guard_table_and_the_literal_reads_cannot_drift`.
    """
    if not os.environ.get("CLOUDFLARE_API_TOKEN", ""):
        raise MissingEnvError(*REQUIRED_ENV[0])
    if not os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""):
        raise MissingEnvError(*REQUIRED_ENV[1])


def _flush() -> None:
    sys.stdout.flush()
    sys.stderr.flush()


def _run(argv: list[str], **kwargs) -> int:
    """One unguarded command with BOTH streams inherited, as the twin leaves them."""
    _flush()
    return subprocess.run(argv, check=False, **kwargs).returncode


def get_d1_uuid(db_name: str) -> str:
    """`npx ... | sed -n ... | jq -r '.uuid // empty'` (twin :105-107).

    A PIPELINE UNDER `pipefail`, ASSIGNED TO A VARIABLE, so unlike
    `deploy-www.sh`'s `get_d1_uuid` there is no `|| true` anywhere: a non-zero
    exit from ANY of the three stages fails the assignment and `set -e` ends the
    run. That is fact 3, and it is why this returns a status alongside the text
    rather than swallowing one.

    `2>/dev/null` IS ON `npx` ONLY. sed's and jq's stderr are inherited.
    """
    _flush()
    info = subprocess.run(
        info_argv(db_name),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    sed = subprocess.run(
        ["sed", "-n", JSON_START_SED],
        input=info.stdout,
        stdout=subprocess.PIPE,
        check=False,
    )
    jq = subprocess.run(
        ["jq", "-r", UUID_JQ],
        input=sed.stdout,
        stdout=subprocess.PIPE,
        check=False,
    )
    # `pipefail`: the RIGHTMOST non-zero status wins.
    status = 0
    for candidate in (info.returncode, sed.returncode, jq.returncode):
        if candidate:
            status = candidate
    if status:
        raise BashExitError(status)
    # Command substitution strips ALL trailing newlines.
    return jq.stdout.decode("utf-8", "surrogateescape").rstrip("\n")


def cleanup(cleanup_dbs: list[str]) -> None:
    """The EXIT trap (twin :63-85). STDOUT, and it never changes the status.

    `>/dev/null 2>&1` ON THE DELETE, so a failing wrangler explains nothing here
    and the `::warning::` is the entire record. That is the twin's shape: the
    trap must not mask the real failure that triggered it.
    """
    print("::group::Cleanup: deleting test databases")
    for db in cleanup_dbs:
        status = _run(
            delete_argv(db),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if status == 0:
            print("  Deleted %s" % db)
        else:
            print(CLEANUP_WARNING % db)
    print("::endgroup::")


def _chdir(target: str) -> None:
    """`cd <target>` under `set -e`.

    THE DIVERGENCE: bash prints `<script>: line N: cd: <target>: <reason>`. This
    prints the same three facts in its own sentence, on the same stream, with
    the same exit status 1.
    """
    try:
        os.chdir(target)
    except OSError as exc:
        print("%s: cd: %s: %s" % (SELF, target, exc.strerror), file=sys.stderr, flush=True)
        raise BashExitError(1) from exc


def _one_region(
    source_db: str,
    root: str,
    workspace: str,
    run_id: str,
    run_attempt: str,
    cleanup_dbs: list[str],
) -> None:
    """One iteration of `for SOURCE_DB in "${ALL_DBS[@]}"` (twin :88-136)."""
    tag = channel_tag(source_db)
    region = region_id(source_db)
    db_name = test_db_name(source_db, run_id, run_attempt)
    # APPENDED BEFORE THE CREATE, so a create that half-succeeded is still attempted by the trap.
    cleanup_dbs.append(db_name)

    print("::group::Test migrations against %s (%s/%s)" % (source_db, tag, region))

    status = _run(create_argv(db_name))
    if status:
        raise BashExitError(status)

    db_uuid = get_d1_uuid(db_name)
    if not db_uuid:
        log.error("Failed to get UUID for %s" % db_name)
        raise BashExitError(1)

    status = _run(clone_argv(root, source_db, db_name))
    if status:
        raise BashExitError(status)

    # `cat >"$TMPCONFIG"` (twin :117), RELATIVE to the current directory. A
    # redirection that cannot be opened is bash's own message and `set -e`; this
    # prints its own sentence with the same stream and the same status, the same ruling as `_chdir`.
    tmpconfig = os.path.join(*TMPCONFIG_RELATIVE)
    try:
        with open(tmpconfig, "w", encoding="utf-8") as handle:
            handle.write(migration_test_toml(db_name, db_uuid))
    except OSError as exc:
        print("%s: %s: %s" % (SELF, tmpconfig, exc.strerror), file=sys.stderr, flush=True)
        raise BashExitError(1) from exc

    _chdir(os.path.join(*WORKER_SUBDIR))
    status = _run(migrations_argv(db_name))
    if status:
        # FACT 4: the generated config is LEFT BEHIND, and the cwd is left inside `workers/www`. Neither matters to the trap, which uses names.
        raise BashExitError(status)
    # `rm -f wrangler-migration-test.toml` (twin :131).
    with contextlib.suppress(FileNotFoundError):  # `-f`
        os.unlink(TMPCONFIG_BASENAME)
    _chdir(workspace)

    print("  %s (%s/%s): migrations applied successfully" % (source_db, tag, region))
    print("::endgroup::")


def main(argv: list[str]) -> int:
    del argv  # the twin parses nothing; every input is an environment variable

    root = repo_root()
    # `cd "$REPO_ROOT"` (twin :37).
    try:
        _chdir(root)
    except BashExitError as exc:
        return exc.code

    for cmd in ("jq", "npx"):
        try:
            common.require_cmd(cmd)
        except common.RefusalError as exc:
            exc.report()
            return exc.code

    try:
        require_env()
    except MissingEnvError as exc:
        # THE DIVERGENCE: bash prefixes this with `<path>: line N: `.
        print("%s: %s" % (exc.name, exc.message), file=sys.stderr, flush=True)
        return 1

    run_id = os.environ.get("GITHUB_RUN_ID") or DEFAULT_RUN_ID
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT") or DEFAULT_RUN_ATTEMPT
    workspace = os.environ.get("GITHUB_WORKSPACE") or root

    edge_dbs = read_names(jq_names(EDGE_JQ, root))
    stable_dbs = read_names(jq_names(STABLE_JQ, root))
    all_dbs = edge_dbs + stable_dbs

    cleanup_dbs: list[str] = []
    code = 0
    try:
        for source_db in all_dbs:
            _one_region(source_db, root, workspace, run_id, run_attempt, cleanup_dbs)
    except BashExitError as exc:
        code = exc.code
    else:
        # FACT 1: with an empty `all_dbs` this line says 0 and the run is green.
        log.info(
            "All %d regional migration tests passed (%d edge + %d stable)"
            % (len(all_dbs), len(edge_dbs), len(stable_dbs))
        )
    # `trap cleanup EXIT`, installed at twin :86 and therefore reached by every exit from here on, including the `set -e` ones. It does not change the status.
    cleanup(cleanup_dbs)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
