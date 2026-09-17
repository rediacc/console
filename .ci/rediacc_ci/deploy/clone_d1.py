#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/clone-d1.sh` (158 lines).

Clone a D1 database from source to target: export the source, wrap the dump in
`PRAGMA defer_foreign_keys=ON` / `foreign_keys=OFF` because D1 exports tables
alphabetically rather than in FK dependency order, import into the target, and verify FK integrity afterwards.

LIVE CALLERS, NOT REPOINTED. `.github/workflows/edge-clone-d1.yml:78` runs the bash twin, and so does `.ci/scripts/deploy/test-d1-migrations.sh:114` (whose own port, `deploy/test_d1_migrations.py`, deliberately invokes the BASH twin for the reason its docstring gives). This module is the twin's verified-equivalent alternative; the cutover is a separate, later, driver-only step.

NOTHING HERE REACHES CLOUDFLARE IN A TEST. `npx` (wrangler) and `sqlite3` are the only two programs that could, and the differential (`.ci/rediacc_ci/tests/test_deploy_clone_d1.py`) puts a RECORDING FAKE for each on a scratch PATH. `.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and says in as many words that the mocked parity ledger
is a separate, achievable piece of work. This is that piece.

Ledger: `.ci/shadow/w7p6-clone-d1.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-clone-d1 --assert --k 5`).

-----------------------------------------------------------------------------
`grep`, `sed`, `wc`, `du`, `cut`, `jq` AND `mktemp` ARE CALLED, NOT REIMPLEMENTED
-----------------------------------------------------------------------------
Seven small programs, one rule, and it is about agreement rather than laziness.

  * `grep` IS THE REDACTION, AND WHICH grep IS INSTALLED DECIDES WHAT IT DOES.
    The pattern is a BRE with a `\\|` alternation, and this host's `grep` is
    ugrep 7.8.4, not GNU grep. A Python `if "r2.cloudflarestorage.com" in line`
    would agree with GNU grep and might not agree with whatever runs on the
    runner; calling the same binary the twin calls agrees with both by
    construction. Verified live on 2026-09-14 that ugrep does honour the
    alternation here, so the pre-signed URL really is stripped:

        $ printf 'a r2.cloudflarestorage.com/x\\nbbb\\nc valid for one hour\\n' |
          grep -v 'r2.cloudflarestorage.com\\|valid for one hour'
        bbb

  * `sed` RUNS TWO NON-TRIVIAL SCRIPTS: the transaction strip (five addresses)
    and the DROP-statement generator, a BRE with `\\?`, two capture groups and a
    bracket class over backtick and double quote. Both are GNU-flavoured, and a
    re-expression in Python's `re` would be a second dialect of the same intent
    that has to be kept in step by hand.
  * `du -h` IS FILESYSTEM ARITHMETIC. It reports allocated blocks, not the
    apparent size, so its answer depends on the filesystem's block size and its
    rounding. There is no Python expression that is "the same number".
  * `wc -l`, `cut -f1`, `jq` and `mktemp -d` come along for consistency, and
    `mktemp -d` earns its place separately: its directory name has a shape
    (`/tmp/tmp.` plus exactly ten alphanumerics) that `tempfile.mkdtemp` does
    not produce, and the differential's mask for that random suffix is narrow
    precisely so everything around it is still compared verbatim.

-----------------------------------------------------------------------------
DEFECT A -- `--sanitize` CANNOT WORK. ITS SQL FILE WAS DELETED IN APRIL
-----------------------------------------------------------------------------
Twin :117 reads `"$SCRIPT_DIR/sanitize-d1.sql"`. That file was DELETED on 2026-04-06 by commit 57b61098c (152 lines removed, `.ci/scripts/deploy/ sanitize-d1.sql`), and nothing has recreated it:

    $ git show --stat 57b61098c | grep -i sanitize
     .ci/scripts/deploy/sanitize-d1.sql                 |   152 -
    $ ls .ci/scripts/deploy/sanitize-d1.sql
    ls: cannot access '.ci/scripts/deploy/sanitize-d1.sql': No such file or directory

The ONLY caller that passes `--sanitize` is `.github/workflows/edge-clone-d1.yml:78`, so that workflow's clone step has been unable to complete for five months. It FAILS CLOSED, which is the one piece of good news: the input redirection cannot be opened, `set -e` ends the run before the import, and no unsanitised data reaches the target. The comment above it -- "The target D1 never
sees real PII" -- is true only because the target sees nothing at all. Reproduced here, not repaired: recreating a deleted 152-line SQL file is not a port's decision.

-----------------------------------------------------------------------------
DEFECT B -- A FAILED FK VERIFICATION IS REPORTED AS ZERO VIOLATIONS
-----------------------------------------------------------------------------
Step 5 is the script's whole safety claim, and it cannot fail for any reason other than a violation it actually managed to read:

    FK_RESULT=$(npx wrangler d1 execute ... --json 2>/dev/null || true)
    FK_COUNT=$(echo "$FK_RESULT" | jq '.[0].results | length' 2>/dev/null || echo "0")
    if [[ "$FK_COUNT" -gt 0 ]]; then ... fi
    log_info "FK integrity check passed (0 violations)"

`2>/dev/null || true` discards both wrangler's message and its status, so an expired token, a network failure or a wrangler crash all yield an empty `FK_RESULT`. `jq` on empty input then prints NOTHING and exits 0 -- so the `|| echo "0"` fallback never even fires -- and `[[ "" -gt 0 ]]` is false without error. Driven 2026-09-14:

    $ FK_RESULT=""; FK_COUNT=$(echo "$FK_RESULT" | jq '.[0].results | length' 2>/dev/null || echo "0")
    $ echo "[$FK_COUNT]"; [[ "$FK_COUNT" -gt 0 ]] && echo gt || echo notgt
    []
    notgt

The run then prints `✓ FK integrity check passed (0 violations)` and exits 0. This is the "an API call that failed folded into the check passed" shape, on the step whose entire job is to notice corruption. Reproduced here, not repaired.

-----------------------------------------------------------------------------
DEFECT C -- THE HEADER PROMISES A GUARD ON `CLOUDFLARE_ACCOUNT_ID` THAT IS ABSENT
-----------------------------------------------------------------------------
The twin's header says `Requires: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID` and then calls `require_var` on the first one only (:54). A run with the account id missing gets past the guard and fails later inside wrangler, in wrangler's words. Reproduced here, not repaired.

-----------------------------------------------------------------------------
DEFECT D -- TWO `BLOCKER:` COMMENTS DESCRIBE A VALUE THIS SCRIPT NEVER BUILDS
-----------------------------------------------------------------------------
Both shellcheck suppressions (:142, :149) justify the unquoted `$CONFIG_FLAG`
with "may be empty OR `--env=X` depending on cloneSource". Nothing in this file
builds `--env=X` and there is no `cloneSource` here: the only assignment is
`CONFIG_FLAG="--config $WRANGLER_CONFIG"` (:61). The suppression is correct
about the mechanism (word-splitting is genuinely wanted) and stale about the value, which is the shape the BLOCKER-liveness convention exists to catch.

AND `--wrangler-config` HAS NO CALLER AT ALL. `edge-clone-d1.yml` passes `--source/--target/--sanitize`; `test-d1-migrations.sh` passes `--source/--target`. The flag, its documented usage line, and both BLOCKER comments are all about a code path nothing exercises.

-----------------------------------------------------------------------------
WHAT IS BYTE-IDENTICAL, AND THE THREE THINGS THAT ARE NOT
-----------------------------------------------------------------------------
Every message this script emits is its own literal string passed through `common.sh`'s logger, so all of them are reproduced byte for byte on stderr with the same marker glyph, and the generated `import.sql` is reproduced byte for byte because the two `sed` scripts that build it are the twin's own.

THREE DIVERGENCES, all of them a bash DIAGNOSTIC carrying a bash line number:

  1. `--source` with no value is `$2` under `set -u`: bash prints
     `<script>: line 27: $2: unbound variable` and exits 1. This port prints the
     same three facts in its own sentence, same stream, same status.
  2. A `wc -l <file` whose file is absent is bash's redirection error, and the
     surrounding `log_info` still prints with an empty count. Same ruling.
  3. `cd`-style failures on the temporary directory, same ruling.

A FOURTH, SMALLER ONE, STATED RATHER THAN HIDDEN: `$CONFIG_FLAG` unquoted is subject to bash's pathname expansion as well as its word splitting. This port splits on whitespace and does not glob. No caller passes the flag at all (DEFECT D), and a `--wrangler-config` value containing `*` would be a wrangler path that does not exist either way.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# The twin's own name, carried in its usage line and in the bash-diagnostic stand-ins.
SELF = "clone-d1.sh"

# `EXPORT_ATTEMPTS=3` (twin :90) and the `sleep 10` between them (twin :99).
# RETRIED because `d1 export` stages through R2 and R2 fails transiently in ways that have nothing to do with the database; the twin's header records the two distinct R2 errors seen on 2026-08-07 that motivated it. A database that genuinely cannot be exported still fails, three times over.
EXPORT_ATTEMPTS = 3
EXPORT_RETRY_SECONDS = 10

# The redaction pattern (twin :102), a BRE with an escaped alternation, quoted verbatim. Wrangler prints a pre-signed R2 URL valid for one hour; leaking it into a CI log is a database download link in plain text.
#
# NOT A PIPE INTO `grep -v`, and the twin's comment explains why at length: the old form died silently two ways under `pipefail` (a failing wrangler whose message was lost, and a SUCCESSFUL export whose entire output was the filtered lines, which made `grep -v` exit 1 and kill the step with nothing to show). Capture first, redact after, report wrangler's own status.
REDACT_PATTERN = r"r2.cloudflarestorage.com\|valid for one hour"

# The transaction strip (twin :126). D1 rejects raw BEGIN/COMMIT in SQL imports, and these arrive from `sqlite3 .dump` during sanitisation or from the export.
STRIP_TRANSACTIONS_SED = (
    "/^BEGIN TRANSACTION;$/d; /^COMMIT;$/d; /^BEGIN;$/d; /^SAVEPOINT /d; /^RELEASE /d"
)

# The DROP generator (twin :135). Handles `CREATE TABLE name(`, ``CREATE TABLE `name` (`` and `CREATE TABLE IF NOT EXISTS "name" (`.
DROP_STATEMENTS_SED = (
    r's/^CREATE TABLE \(IF NOT EXISTS \)\?[`"]*\([a-zA-Z_][a-zA-Z0-9_]*\)[`"]*.*'
    r'/DROP TABLE IF EXISTS "\2";/p'
)

# The FK safety wrapper written around the dump (twin :131-137). D1 exports tables alphabetically rather than in dependency order, so the import needs both pragmas or a child row lands before its parent table exists.
IMPORT_HEADER = ("PRAGMA defer_foreign_keys=ON;", "PRAGMA foreign_keys=OFF;")
IMPORT_FOOTER = ("PRAGMA foreign_keys=ON;",)

# `jq '.[0].results | length'` (twin :152) and the `--command` at :151.
FK_JQ = ".[0].results | length"
FK_RESULTS_JQ = ".[0].results"
FK_COMMAND = "PRAGMA foreign_key_check"

# The usage line (twin :50), which is also the only place `--wrangler-config` is documented. `--sanitize` is absent from it; see DEFECT D.
USAGE = "Usage: clone-d1.sh --source <db-name> --target <db-name> [--wrangler-config <path>]"

# The one variable `require_var` demands (twin :54). The header claims two; see
# DEFECT C.
REQUIRED_VAR = "CLOUDFLARE_API_TOKEN"

# `"$SCRIPT_DIR/sanitize-d1.sql"` (twin :117), relative to the repository root so the missing-file path is checkable without guessing at an absolute one.
SANITIZE_SQL_RELATIVE = (".ci", "scripts", "deploy", "sanitize-d1.sql")

# The four defects in the module docstring, as constants a test can assert by name instead of restating the sentence.
THE_SANITIZE_PATH_CANNOT_WORK = True
A_FAILED_FK_CHECK_REPORTS_ZERO_VIOLATIONS = True
THE_ACCOUNT_ID_GUARD_THE_HEADER_PROMISES_IS_ABSENT = True
THE_BLOCKER_COMMENTS_NAME_A_VALUE_THAT_IS_NEVER_BUILT = True


class BashExitError(Exception):
    """`set -e` ending the run, or an explicit `exit N`.

    Carries the status the twin would exit with. The EXIT trap still runs, which is why every raise below passes through the `finally` that removes the temporary directory.
    """

    def __init__(self, code: int) -> None:
        super().__init__("exit %d" % code)
        self.code = code


def parse_argv(argv: list[str]) -> tuple[str, str, str, bool]:
    """The `while [[ $# -gt 0 ]]` loop (twin :24-47).

    Returns `(source, target, wrangler_config, sanitize)`.

    LAST FLAG WINS, because each arm assigns rather than appends: `--source a --source b` clones `b`. That is bash's behaviour here and it is reproduced rather than turned into an error.

    A FLAG WITH NO VALUE raises `BashExitError(1)` after printing this port's stand-in for bash's `$2: unbound variable`; divergence 1 in the module docstring.
    """
    source_db = ""
    target_db = ""
    wrangler_config = ""
    sanitize = False

    index = 0
    while index < len(argv):
        flag = argv[index]
        if flag in ("--source", "--target", "--wrangler-config"):
            if index + 1 >= len(argv):
                print(
                    "%s: %s: $2: unbound variable" % (SELF, flag),
                    file=sys.stderr,
                    flush=True,
                )
                raise BashExitError(1)
            value = argv[index + 1]
            if flag == "--source":
                source_db = value
            elif flag == "--target":
                target_db = value
            else:
                wrangler_config = value
            index += 2
        elif flag == "--sanitize":
            sanitize = True
            index += 1
        else:
            log.error("Unknown argument: %s" % flag)
            raise BashExitError(1)
    return source_db, target_db, wrangler_config, sanitize


def config_flag_words(wrangler_config: str) -> list[str]:
    """`CONFIG_FLAG=""` or `CONFIG_FLAG="--config $WRANGLER_CONFIG"` (twin :59-62),
    expanded UNQUOTED at both call sites.

    The unquoted expansion is what makes an empty value contribute NO argument rather than an empty one, which is the whole reason the twin carries two
    `# shellcheck disable=SC2086` lines. Word splitting is on the default IFS, so
    a run of whitespace is one separator and leading or trailing whitespace contributes nothing.
    """
    if not wrangler_config:
        return []
    return ("--config %s" % wrangler_config).split()


def export_argv(source_db: str, out_path: str) -> list[str]:
    """`npx wrangler d1 export "$SOURCE_DB" --remote --output=...` (twin :94)."""
    return ["npx", "wrangler", "d1", "export", source_db, "--remote", "--output=%s" % out_path]


def execute_file_argv(target_db: str, config_words: list[str], file_path: str) -> list[str]:
    """`npx wrangler d1 execute "$TARGET_DB" --remote $CONFIG_FLAG --file=...` (twin :144)."""
    return [
        "npx",
        "wrangler",
        "d1",
        "execute",
        target_db,
        "--remote",
        *config_words,
        "--file=%s" % file_path,
    ]


def fk_check_argv(target_db: str, config_words: list[str]) -> list[str]:
    """`npx wrangler d1 execute ... --command="PRAGMA foreign_key_check" --json` (twin :151)."""
    return [
        "npx",
        "wrangler",
        "d1",
        "execute",
        target_db,
        "--remote",
        *config_words,
        "--command=%s" % FK_COMMAND,
        "--json",
    ]


def _flush() -> None:
    sys.stdout.flush()
    sys.stderr.flush()


def _run(argv: list[str], **kwargs) -> int:
    """One command with both streams inherited, as the twin leaves them.

    FLUSHED FIRST, ALWAYS: Python's `print` is block-buffered against a pipe
    while the child writes straight to the inherited descriptor, so without this
    the port's own lines land out of real order regardless of when they were printed.
    """
    _flush()
    return subprocess.run(argv, check=False, **kwargs).returncode


def _capture(argv: list[str], **kwargs) -> tuple[int, str]:
    """`$(...)`: stdout captured with ALL trailing newlines stripped, stderr
    inherited unless the caller redirects it."""
    _flush()
    proc = subprocess.run(argv, stdout=subprocess.PIPE, check=False, **kwargs)
    return proc.returncode, proc.stdout.decode("utf-8", "surrogateescape").rstrip("\n")


def _open_for_redirect(path: str):
    """`< "$path"` on a simple command, under `set -e`.

    bash does not run the command at all when the redirection cannot be opened: it prints its own diagnostic and the command's status is 1, which `set -e` turns into the script's. This raises `BashExitError(1)` after printing the same three facts in its own sentence, which is divergence 2 in the module docstring.
    """
    try:
        return open(path, "rb")
    except OSError as exc:
        print("%s: %s: %s" % (SELF, path, exc.strerror), file=sys.stderr, flush=True)
        raise BashExitError(1) from exc


def make_temp_dir() -> str:
    """`TMPDIR="$(mktemp -d)"` (twin :56).

    THE REAL `mktemp`, not `tempfile.mkdtemp`, so the directory name has the same shape on both sides and the differential's mask for the random suffix can stay narrow. It honours `$TMPDIR` exactly as the twin's does.
    """
    status, path = _capture(["mktemp", "-d"])
    if status or not path:
        raise BashExitError(status or 1)
    return path


def wc_lines(path: str) -> str:
    """`$(wc -l <path)` inside a message, which is a COMMAND SUBSTITUTION.

    A redirection that cannot be opened there does NOT end the run: the enclosing command is `log_info`, which succeeds, so bash prints its own complaint and the message interpolates an empty string. Both halves are reproduced; only the wording of the complaint diverges.
    """
    try:
        handle = open(path, "rb")  # noqa: SIM115
    except OSError as exc:
        print("%s: %s: %s" % (SELF, path, exc.strerror), file=sys.stderr, flush=True)
        return ""
    with handle:
        _, text = _capture(["wc", "-l"], stdin=handle)
    return text


def export_line_report(export_sql: str) -> str:
    """`Exported $(wc -l <f) lines ($(du -h f | cut -f1))` (twin :107).

    BOTH SUBSTITUTIONS ARE UNGUARDED IN THE TWIN, and a failing one does not end the run: the enclosing command is `log_info`, which succeeds. So a missing file yields bash's own redirection complaint on stderr and the message `Exported lines ()`. Divergence 2 is only the WORDING of that complaint.
    """
    lines = wc_lines(export_sql)

    _flush()
    du = subprocess.run(["du", "-h", export_sql], stdout=subprocess.PIPE, check=False)
    cut = subprocess.run(["cut", "-f1"], input=du.stdout, stdout=subprocess.PIPE, check=False)
    size = cut.stdout.decode("utf-8", "surrogateescape").rstrip("\n")
    return "Exported %s lines (%s)" % (lines, size)


def run_export(source_db: str, tmpdir: str) -> int:
    """The retry loop (twin :92-101). Returns the LAST attempt's status.

    `>"$TMPDIR/export.log" 2>&1` merges both streams into the log, which is what makes the redaction possible at all: the pre-signed URL can arrive on either one. The loop breaks on the first success, and the warning between attempts names the attempt number so a retry is visible in the job log.
    """
    export_rc = 0
    for attempt in range(1, EXPORT_ATTEMPTS + 1):
        export_rc = 0
        with open(os.path.join(tmpdir, "export.log"), "wb") as handle:
            export_rc = _run(
                export_argv(source_db, os.path.join(tmpdir, "export.sql")),
                stdout=handle,
                stderr=subprocess.STDOUT,
            )
        if export_rc == 0:
            break
        if attempt < EXPORT_ATTEMPTS:
            log.warn(
                "wrangler d1 export %s failed (exit %d) on attempt %d/%d; retrying in 10s"
                % (source_db, export_rc, attempt, EXPORT_ATTEMPTS)
            )
            # THE EXTERNAL `sleep`, not `time.sleep`. The twin execs sleep(1) and `set -e` reaches it, so a `sleep` that is missing or refuses ends the run rather than being silently skipped. It is also the only way the wait is visible in a call log, which is what lets a differential prove the retry waited rather than infer it from a wall-clock gap it cannot see.
            status = _run(["sleep", str(EXPORT_RETRY_SECONDS)])
            if status:
                raise BashExitError(status)
    return export_rc


def sanitize(tmpdir: str, root: str) -> None:
    """Step 1.5 (twin :110-122), which cannot complete; see DEFECT A.

    Three `sqlite3` invocations and an `rm -f`, all unguarded, so the first one that fails ends the run with its own status. The second reads a file that has not existed since April: bash's redirection error, then `set -e`.
    """
    log.step("Sanitizing data via local sqlite3")
    try:
        common.require_cmd("sqlite3")
    except common.RefusalError as exc:
        exc.report()
        raise BashExitError(exc.code) from exc

    temp_db = os.path.join(tmpdir, "temp.db")
    export_sql = os.path.join(tmpdir, "export.sql")
    sanitize_sql = os.path.join(root, *SANITIZE_SQL_RELATIVE)

    with _open_for_redirect(export_sql) as handle:
        status = _run(["sqlite3", temp_db], stdin=handle)
    if status:
        raise BashExitError(status)

    # DEFECT A: this open is the one that fails, and it fails before any data can move. bash reports its own redirection error and exits 1.
    with _open_for_redirect(sanitize_sql) as handle:
        status = _run(["sqlite3", temp_db], stdin=handle)
    if status:
        raise BashExitError(status)

    with open(export_sql, "wb") as out:
        status = _run(["sqlite3", temp_db, ".dump"], stdout=out)
    if status:
        raise BashExitError(status)

    # `rm -f`: a missing file is not an error.
    _run(["rm", "-f", temp_db])

    # `log_info "Sanitized ($(wc -l <f) lines)"`: a command SUBSTITUTION again, so a missing file is a diagnostic and an empty count rather than an exit.
    log.info("Sanitized (%s lines)" % wc_lines(export_sql))


def build_import_sql(tmpdir: str) -> None:
    """Steps 2 and 3 (twin :126-138).

    The strip is IN PLACE on `export.sql` and runs whether or not `--sanitize` was asked for. The DROP statements are generated FROM the stripped file, so a table the strip removed cannot be dropped, and the dump is then appended whole. Order inside `import.sql` is: two pragmas, every DROP, the dump, one
    pragma.
    """
    export_sql = os.path.join(tmpdir, "export.sql")
    import_sql = os.path.join(tmpdir, "import.sql")

    status = common.sed_in_place([STRIP_TRANSACTIONS_SED, export_sql])
    if status:
        raise BashExitError(status)

    log.step("Preparing import with FK safety wrapper")
    with open(import_sql, "wb") as out:
        out.writelines(("%s\n" % line).encode("utf-8") for line in IMPORT_HEADER)
        out.flush()
        _run(["sed", "-n", DROP_STATEMENTS_SED, export_sql], stdout=out)
        out.flush()
        _run(["cat", export_sql], stdout=out)
        out.flush()
        out.writelines(("%s\n" % line).encode("utf-8") for line in IMPORT_FOOTER)


def verify_fk(target_db: str, config_words: list[str]) -> None:
    """Step 5 (twin :148-158). DEFECT B lives here, whole.

    `2>/dev/null || true` on the wrangler call and `2>/dev/null || echo "0"` on the jq call mean the only observable outcome of a failed verification is the success line. Reproduced exactly, including the fact that on empty input `jq` prints nothing and exits 0, so the `|| echo "0"` fallback does not fire and `FK_COUNT` is the empty string rather than `0`.
    """
    log.step("Verifying foreign key integrity")
    _, fk_result = _capture(fk_check_argv(target_db, config_words), stderr=subprocess.DEVNULL)

    # `echo "$FK_RESULT" | jq ...`: echo appends a newline, so jq's input is never truly empty, and jq's own status is discarded either way.
    _flush()
    jq = subprocess.run(
        ["jq", FK_JQ],
        input=("%s\n" % fk_result).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    fk_count = jq.stdout.decode("utf-8", "surrogateescape").rstrip("\n")
    if jq.returncode != 0:
        fk_count = "0"

    try:
        violations = bash_arithmetic_gt_zero(fk_count)
    except BashUnboundError as exc:
        # bash prints `<script>: line 153: <name>: unbound variable` and stops. Same three facts, same stream, same status; the EXIT trap still runs.
        print("%s: %s: unbound variable" % (SELF, exc.name), file=sys.stderr, flush=True)
        raise BashExitError(1) from exc

    if violations:
        log.error("Foreign key violations found: %s" % fk_count)
        _flush()
        subprocess.run(
            ["jq", FK_RESULTS_JQ],
            input=("%s\n" % fk_result).encode("utf-8"),
            stderr=subprocess.DEVNULL,
            check=False,
        )
        raise BashExitError(1)
    log.info("FK integrity check passed (0 violations)")


# A bash NAME, used to tell "this expression mentions an unset variable" from "this expression is malformed". The lookbehind keeps the `a` in `1a` out: that is a bad NUMBER, and bash treats the two cases differently.
BASH_NAME = re.compile(r"(?<![0-9A-Za-z_])[A-Za-z_][A-Za-z0-9_]*")

# A complete bash arithmetic literal: optional sign, then hex, octal or decimal.
BASH_NUMBER = re.compile(r"^[+-]?(?:0[xX][0-9a-fA-F]+|0[0-7]*|[1-9][0-9]*)$")


class BashUnboundError(Exception):
    """`set -u` firing inside an arithmetic evaluation. FATAL, exit 1."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


def bash_arithmetic_gt_zero(text: str) -> bool:
    """`[[ "$FK_COUNT" -gt 0 ]]`, which is ARITHMETIC EVALUATION under `set -u`.

    Five behaviours, all probed against real bash on 2026-09-14 rather than reasoned about, because three of them are surprising:

        [$v]      exit  output
        [null]    1     bash: line 1: null: unbound variable        <- FATAL
        [a b]     1     bash: line 1: a: unbound variable           <- FATAL
        [1a]      0     [[: 1a: value too great for base   -> FALSE
        [08]      0     [[: 08: value too great for base   -> FALSE
        [0x10]    0     -> TRUE  (hex)
        [010]     0     -> TRUE  (octal 8)
        []        0     -> FALSE
        [-2]      0     -> FALSE

    THE FATAL ROWS ARE THE POINT. A bare word is a VARIABLE REFERENCE, and an unset one under `set -u` ends the script with exit 1 and no message of the script's own -- so a `jq` program that ever emitted `null` here would turn a clone into a hard failure rather than a verdict. It cannot today: `jq length` prints a number or the pipeline fails and `|| echo "0"` supplies one.
    Reproduced anyway, because the next person to edit that jq program should not have to rediscover it.

    THE TWO NON-FATAL ERROR ROWS ARE REPRODUCED WITH THEIR DIAGNOSTIC, minus bash's own `<file>: line <n>:` prefix, because the zero-padded-octal class has bitten this campaign four times and a silent FALSE would hide it a fifth. The residual case (a non-numeric value that does not start with a digit and names no variable, e.g. `+`) evaluates FALSE here with no message, where bash
    prints an `arithmetic syntax error`; it is unreachable
    from `jq length` and from this script's `|| echo "0"` fallback.
    """
    stripped = text.strip()
    if stripped == "":
        return False
    if BASH_NUMBER.match(stripped):
        negative = stripped.startswith("-")
        digits = stripped.lstrip("+-")
        if digits[:2].lower() == "0x":
            value = int(digits, 16)
        elif digits.startswith("0") and digits != "0":
            value = int(digits, 8)
        else:
            value = int(digits)
        return (-value if negative else value) > 0
    name = BASH_NAME.search(stripped)
    if name:
        raise BashUnboundError(name.group(0))
    if stripped[0].isdigit():
        # `[[: 08: value too great for base (error token is "08")`, verbatim apart from bash's own `<file>: line <n>:` prefix.
        print(
            '%s: [[: %s: value too great for base (error token is "%s")'
            % (SELF, stripped, stripped),
            file=sys.stderr,
            flush=True,
        )
    return False


def main(argv: list[str]) -> int:
    root = str(common.repo_root())

    try:
        source_db, target_db, wrangler_config, wants_sanitize = parse_argv(argv)
    except BashExitError as exc:
        return exc.code

    if not source_db or not target_db:
        log.error(USAGE)
        return 1

    try:
        common.require_var(REQUIRED_VAR)
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    try:
        tmpdir = make_temp_dir()
    except BashExitError as exc:
        return exc.code

    config_words = config_flag_words(wrangler_config)

    try:
        # --- Step 1: export ------------------------------------------------
        log.step("Exporting D1 database: %s" % source_db)
        export_rc = run_export(source_db, tmpdir)

        # THE REDACTION, and `|| true` because `grep -v` exits 1 when it filters everything out. Its stdout is the script's stdout.
        _run(["grep", "-v", REDACT_PATTERN, os.path.join(tmpdir, "export.log")])

        if export_rc != 0:
            log.error(
                "wrangler d1 export %s failed (exit %d) after %d attempts; its full output "
                "is above (R2 URL redacted)" % (source_db, export_rc, EXPORT_ATTEMPTS)
            )
            raise BashExitError(export_rc)

        log.info(export_line_report(os.path.join(tmpdir, "export.sql")))

        # --- Step 1.5: sanitize --------------------------------------------
        if wants_sanitize:
            sanitize(tmpdir, root)

        # --- Steps 2 and 3: strip, then wrap -------------------------------
        build_import_sql(tmpdir)

        # --- Step 4: import ------------------------------------------------
        log.step("Importing into D1 database: %s" % target_db)
        status = _run(
            execute_file_argv(target_db, config_words, os.path.join(tmpdir, "import.sql"))
        )
        if status:
            raise BashExitError(status)
        log.info("Import complete")

        # --- Step 5: verify ------------------------------------------------
        verify_fk(target_db, config_words)
    except BashExitError as exc:
        return exc.code
    finally:
        # `trap 'rm -rf "$TMPDIR"' EXIT` (twin :57), which prints nothing and cannot change the status.
        shutil.rmtree(tmpdir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
