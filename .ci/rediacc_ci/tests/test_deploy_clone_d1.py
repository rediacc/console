"""Differential: `rediacc_ci.deploy.clone_d1` against its twin
`.ci/scripts/deploy/clone-d1.sh`.

RECORDING FAKES FOR `npx` AND `sqlite3` ON A SCRATCH PATH, INSIDE A FIXTURE REPO. Those two are the only programs in this script that can reach anything
outside the machine or open a database; every other tool it uses (`grep`, `sed`,
`wc`, `du`, `cut`, `jq`, `mktemp`, `rm`, `cat`) is the real binary symlinked into the same scratch directory, because both sides call the same one and that is the point of calling them at all.

`.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and says in as many words that the mocked parity ledger is a separate, achievable piece of work. This is that piece: no Cloudflare credential, no D1 database, nothing that leaves this host.

THREE KINDS OF EVIDENCE, and the last two are what a stdout comparison alone would miss:

  1. THE STREAMS, separately, byte for byte.
  2. THE CALL LOG: which wrangler subcommands ran, in what order, with which
     flags. The retry loop, the `--config` word-splitting and the FK probe are
     all invisible in the printed output.
  3. THE GENERATED `import.sql`, byte for byte. It is the artifact the whole
     script exists to produce, and it is assembled by two `sed` programs whose
     output nothing else reports.

THE ONE MASKED THING is `mktemp -d`'s random suffix, which cannot be equal between two runs of the SAME implementation. The mask is deliberately narrow (ten alphanumerics after `/tmp/tmp.`, stopping at the word boundary) so the `/export.sql` and `/import.sql` tails, and any other `/tmp` path either side might invent, are still compared verbatim.
"""

from __future__ import annotations

import inspect
import os
import re
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import clone_d1 as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "clone-d1.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "deploy" / "clone_d1.py"
BASH = shutil.which("bash") or "/bin/bash"

BASE_ENV = {"CLOUDFLARE_API_TOKEN": "tok-fixture", "CLOUDFLARE_ACCOUNT_ID": "acct-fixture"}

# The real binaries. `mktemp` matters twice over: both sides call it, and its output shape is what the mask below is written against.
PATH_MINIMUM = (
    "grep",
    "sed",
    "wc",
    "du",
    "cut",
    "jq",
    "cat",
    "rm",
    "mktemp",
    "uname",
    "tr",
    "dirname",
    "basename",
    "env",
)

# A MODEL of `wrangler d1`, not wrangler.
#
# THE `call: ` PREFIX IS LOAD-BEARING FOR THE LEDGER, not decoration. `shadow-gate.ts` classifies any line starting with `→ ` or `✓ ` as CHATTER before a `--finding-re` is ever consulted, and this script reports almost entirely through `log_step`/`log_info`, which are exactly those two glyphs. A finding regex over the message text could therefore never match anything and every
# ledger row would read VACUOUS_BOTH_EMPTY. `call: ` is a shape no logger in this tree emits.
FAKE_NPX = r'''#!/usr/bin/python3
"""Recording fake for `npx wrangler d1`. See the test module docstring."""
import json
import os
import sys

argv = sys.argv[1:]
log = os.environ["FAKE_CALL_LOG"]


def emit(text):
    with open(log, "a") as fh:
        fh.write(text)


emit("call: npx %s\n" % " ".join(argv))

with open(log) as fh:
    call_index = len([line for line in fh if line.startswith("call: ")])

rest = argv[1:] if argv[:1] == ["wrangler"] else None
if rest is None:
    sys.stderr.write("fake npx: unmodelled tool %r\n" % (argv[:1],))
    sys.exit(127)

if rest[:2] == ["d1", "export"]:
    fail_until = int(os.environ.get("FAKE_EXPORT_FAIL_UNTIL", "0"))
    attempt = int(os.environ.get("FAKE_EXPORT_ATTEMPT", "0")) + 1
    os.environ["FAKE_EXPORT_ATTEMPT"] = str(attempt)
    # The attempt counter lives on disk: each invocation is a fresh process.
    counter = os.environ["FAKE_CALL_LOG"] + ".export-attempts"
    try:
        with open(counter) as fh:
            attempt = int(fh.read().strip() or "0") + 1
    except FileNotFoundError:
        attempt = 1
    with open(counter, "w") as fh:
        fh.write(str(attempt))

    out = ""
    for a in rest:
        if a.startswith("--output="):
            out = a.split("=", 1)[1]
    # THE PRE-SIGNED URL IS ON BOTH STREAMS, because the twin merges them into
    # one log file and redacts afterwards. A fake that printed it on one stream
    # only would let a port that redacted just that stream pass.
    sys.stdout.write("Downloading https://fixture.r2.cloudflarestorage.com/dump.sql?sig=abc\n")
    sys.stderr.write("This URL is valid for one hour.\n")
    if attempt <= fail_until:
        sys.stderr.write("ERROR Could not create a presigned URL to R2\n")
        sys.exit(1)
    if out and os.environ.get("FAKE_EXPORT_WRITES_NOTHING") != "1":
        with open(out, "w") as fh:
            fh.write("PRAGMA foreign_keys=OFF;\n")
            fh.write("BEGIN TRANSACTION;\n")
            fh.write('CREATE TABLE IF NOT EXISTS "users" (id INTEGER PRIMARY KEY);\n')
            fh.write("INSERT INTO users VALUES (1);\n")
            fh.write("CREATE TABLE `sessions` (id INTEGER, user_id INTEGER);\n")
            fh.write("INSERT INTO sessions VALUES (1, 1);\n")
            fh.write("COMMIT;\n")
    sys.stdout.write("Exported to %s\n" % out)
    sys.exit(0)

if rest[:2] == ["d1", "execute"]:
    # THE ARTIFACT IS STASHED BEFORE THE EXIT TRAP CAN REMOVE IT. The script
    # deletes its own temporary directory on the way out, so `import.sql` is
    # unobservable afterwards; the only place it can be captured is here, in
    # the program the script hands it to.
    stash = os.environ.get("FAKE_STASH_FILE", "")
    for a in rest:
        if stash and a.startswith("--file="):
            with open(a.split("=", 1)[1]) as src, open(stash, "w") as dst:
                dst.write(src.read())
    if os.environ.get("FAKE_EXECUTE_FAILS_ON") == str(call_index):
        sys.stderr.write("wrangler: execute refused (fixture)\n")
        sys.exit(3)
    if "--json" in rest:
        mode = os.environ.get("FAKE_FK", "clean")
        if mode == "silent":
            # A verification that produced NOTHING at all: the shape DEFECT B is
            # about. Non-zero, no stdout, its stderr swallowed by 2>/dev/null.
            sys.stderr.write("wrangler: could not reach the API (fixture)\n")
            sys.exit(1)
        if mode == "violations":
            sys.stdout.write(
                json.dumps([{"results": [{"table": "sessions", "rowid": 1}]}]) + "\n"
            )
            sys.exit(0)
        sys.stdout.write(json.dumps([{"results": []}]) + "\n")
        sys.exit(0)
    sys.stdout.write("Executed against the target database\n")
    sys.exit(0)

sys.stderr.write("fake wrangler: unmodelled subcommand %r\n" % (rest,))
sys.exit(127)
'''

# A RECORDING, INSTANT `sleep`. The twin's retry waits 10 real seconds between
# attempts and so does the port, because both exec the same program; replacing
# it here does two things at once. It keeps this suite from spending 40 seconds asleep, and -- the reason it is a RECORDING stub rather than `true` -- it makes the wait OBSERVABLE, so the differential proves the retry slept rather than inferring it from a wall-clock gap it cannot see.
FAKE_SLEEP = r"""#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("call: sleep %s\n" % " ".join(sys.argv[1:]))
sys.exit(0)
"""

# A MODEL of `sqlite3` that records and does nothing. The sanitize path cannot reach the second call (DEFECT A), so this exists to prove the FIRST call happens and that the run dies where the missing file is, not earlier.
FAKE_SQLITE3 = r"""#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("call: sqlite3 %s\n" % " ".join(sys.argv[1:]))
if sys.argv[2:3] == [".dump"]:
    sys.stdout.write("PRAGMA foreign_keys=OFF;\nCREATE TABLE \"users\" (id INTEGER);\n")
sys.exit(0)
"""


def _bin(root: pathlib.Path, *, drop: str = "") -> str:
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        link = stub / real_name
        if real_name == drop:
            if link.is_symlink() or link.exists():
                link.unlink()
            continue
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        if not link.exists():
            link.symlink_to(real)
    for tool, body in (("npx", FAKE_NPX), ("sqlite3", FAKE_SQLITE3), ("sleep", FAKE_SLEEP)):
        path = stub / tool
        if drop == tool:
            if path.exists():
                path.unlink()
            continue
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    if drop:
        assert shutil.which(drop, path=str(stub)) is None, f"{drop} leaked into the stub PATH"
    return str(stub)


def fixture(tmp_path: pathlib.Path, *, sanitize_sql: bool = False) -> pathlib.Path:
    """A throwaway repository holding the twin and `common.sh`.

    `sanitize_sql=True` RECREATES the file deleted in April, which is the only
    way to see what the `--sanitize` path would do if it worked. It is not written into the real tree by anything here.
    """
    root = tmp_path / "repo"
    (root / ".ci" / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "deploy" / TWIN.name)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / COMMON.name)
    if sanitize_sql:
        (root / ".ci" / "scripts" / "deploy" / "sanitize-d1.sql").write_text(
            "UPDATE users SET email = 'redacted@example.com';\n", encoding="utf-8"
        )
    return root


def _run(
    root: pathlib.Path,
    side: str,
    *,
    args: tuple[str, ...] = ("--source", "account-db-eu", "--target", "edge-account-db-eu"),
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    call_log = root / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    counter = root / f"{side}-calls.log.export-attempts"
    if counter.exists():
        counter.unlink()
    # A PER-SIDE TMPDIR, so `mktemp -d` cannot hand the two sides the same directory and let one see the other's leftovers.
    tmpdir = root / f"{side}-tmp"
    tmpdir.mkdir(exist_ok=True)

    env = {
        "PATH": _bin(root, drop=drop),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "REDIACC_CI_ROOT": str(root),
        "FAKE_CALL_LOG": str(call_log),
        **BASE_ENV,
    }
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)

    if side == "old":
        argv = [BASH, str(root / ".ci" / "scripts" / "deploy" / TWIN.name), *args]
    else:
        argv = [sys.executable, str(PORT_FILE), *args]
    proc = subprocess.run(
        argv,
        cwd=str(root.parent),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=180,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def run_both(tmp_path: pathlib.Path, *, fixture_kw: dict | None = None, **kw):
    root = fixture(tmp_path, **(fixture_kw or {}))
    old = _run(root, "old", **kw)
    new = _run(root, "new", **kw)
    return root, old, new


# `mktemp -d`'s own shape: ten alphanumerics after `/tmp/tmp.`, stopping at the word boundary. `test_the_mktemp_mask_hides_only_the_random_suffix` asserts both halves of the claim rather than leaving it as a comment.
MKTEMP_DIR = re.compile(r"/[A-Za-z0-9_./-]*/tmp\.[A-Za-z0-9]{10}\b")


# THE ONE DIVERGENCE THIS FILE NORMALISES, and it is a bash DIAGNOSTIC rather than either program's own message: a `< file` redirection that cannot be opened is reported by bash as `<script path>: line <n>: <path>: <reason>`, where the line number is a fact about the bash file and nothing else. The port prints `clone-d1.sh: <path>: <reason>`. Both name the same path and the same
# reason on the same stream with the same exit status, which is what the comparison is about.
#
# THE PATTERN IS DELIBERATELY TIGHT: it matches only a leader ending in `clone-d1.sh` optionally followed by ` line <digits>`, and it keeps the path and the reason. A different path, a different reason, or a message from anything else is untouched, which `test_the_bash_diagnostic_normaliser_keeps_the_path_and_the_reason` asserts in both directions.
BASH_DIAG = re.compile(r"^\S*clone-d1\.sh: (?:line \d+: )?(?P<rest>.*)$", re.MULTILINE)


def _mask(text: str) -> str:
    return BASH_DIAG.sub(
        lambda m: "clone-d1: %s" % m.group("rest"), MKTEMP_DIR.sub("<MKTEMP>", text)
    )


def _agree(old, new, label: str) -> None:
    old_proc, old_calls = old
    new_proc, new_calls = new
    assert new_proc.returncode == old_proc.returncode, (
        f"{label}: exit diverged: {old_proc.returncode!r} vs {new_proc.returncode!r}\n"
        f"old stderr: {old_proc.stderr!r}\nnew stderr: {new_proc.stderr!r}"
    )
    assert _mask(new_proc.stdout) == _mask(old_proc.stdout), (
        f"{label}: stdout diverged:\n{old_proc.stdout!r}\n{new_proc.stdout!r}"
    )
    assert _mask(new_proc.stderr) == _mask(old_proc.stderr), (
        f"{label}: stderr diverged:\n{old_proc.stderr!r}\n{new_proc.stderr!r}"
    )
    assert _mask(new_calls) == _mask(old_calls), (
        f"{label}: call log diverged:\n{old_calls}\n---\n{new_calls}"
    )


def _calls(log: str) -> list[str]:
    return [line[len("call: ") :] for line in log.splitlines() if line.startswith("call: ")]


def _verbs(log: str) -> list[str]:
    out = []
    for line in _calls(log):
        fields = line.split()
        if fields[:3] == ["npx", "wrangler", "d1"]:
            out.append(" ".join(fields[2:4]))
        else:
            out.append(fields[0])
    return out


# --------------------------------------------------------------------------- The happy path, the order, and the artifact ---------------------------------------------------------------------------


def test_happy_path_agrees_on_both_streams_and_every_call(tmp_path) -> None:
    _root, old, new = run_both(tmp_path)
    _agree(old, new, "happy")

    proc, calls = old
    assert proc.returncode == 0, proc.stderr
    # PRINT THE SHAPE: one export, one import, one FK probe, in that order.
    assert _verbs(calls) == ["d1 export", "d1 execute", "d1 execute"], _verbs(calls)
    assert "--file=" in _calls(calls)[1]
    assert "--command=PRAGMA foreign_key_check" in _calls(calls)[2]
    assert "--json" in _calls(calls)[2]


def test_the_five_step_narration_is_byte_identical_on_stderr(tmp_path) -> None:
    """Every line here is the twin's own literal string through `common.sh`'s
    logger, so the glyphs are part of the comparison: `→` for a step and `✓` for information, both on stderr, both uncoloured because neither side has a
    tty."""
    _root, old, new = run_both(tmp_path)
    _agree(old, new, "narration")

    proc, _log = old
    lines = [ln for ln in proc.stderr.splitlines() if ln]
    assert lines[0] == "→ Exporting D1 database: account-db-eu"
    assert lines[1].startswith("✓ Exported ")
    assert lines[2] == "→ Preparing import with FK safety wrapper"
    assert lines[3] == "→ Importing into D1 database: edge-account-db-eu"
    assert lines[4] == "✓ Import complete"
    assert lines[5] == "→ Verifying foreign key integrity"
    assert lines[6] == "✓ FK integrity check passed (0 violations)"


def test_the_presigned_url_is_redacted_from_both_streams(tmp_path) -> None:
    """The export's log holds a pre-signed R2 URL valid for one hour, and it
    arrives on BOTH of wrangler's streams because the twin merges them into one file. Neither line may reach the job log.

    THE CONTROL IS IN THE SAME TEST: the fake's third line, which is neither the URL nor the validity notice, MUST survive. A redaction that ate everything
    would satisfy the first half alone."""
    _root, old, new = run_both(tmp_path)
    _agree(old, new, "redaction")

    proc, _log = old
    assert "r2.cloudflarestorage.com" not in proc.stdout
    assert "r2.cloudflarestorage.com" not in proc.stderr
    assert "valid for one hour" not in proc.stdout
    assert "Exported to " in proc.stdout, "the non-matching line must survive"


def test_the_generated_import_sql_is_byte_identical(tmp_path) -> None:
    """THE ARTIFACT THIS SCRIPT EXISTS TO PRODUCE. It is assembled from two
    pragmas, one generated DROP per CREATE TABLE, the stripped dump and a
    closing pragma, and nothing prints it. Both sides' copies are recovered from
    the temporary directory by a fake `npx` that stashes whatever `--file=`
    names before the EXIT trap removes it."""
    root = fixture(tmp_path)
    old = _run(root, "old", FAKE_STASH_FILE=str(root / "old-import.sql"))
    new = _run(root, "new", FAKE_STASH_FILE=str(root / "new-import.sql"))
    _agree(old, new, "import-sql")

    old_sql = (root / "old-import.sql").read_text(encoding="utf-8")
    new_sql = (root / "new-import.sql").read_text(encoding="utf-8")
    assert new_sql == old_sql
    assert old_sql == (
        "PRAGMA defer_foreign_keys=ON;\n"
        "PRAGMA foreign_keys=OFF;\n"
        'DROP TABLE IF EXISTS "users";\n'
        'DROP TABLE IF EXISTS "sessions";\n'
        "PRAGMA foreign_keys=OFF;\n"
        'CREATE TABLE IF NOT EXISTS "users" (id INTEGER PRIMARY KEY);\n'
        "INSERT INTO users VALUES (1);\n"
        "CREATE TABLE `sessions` (id INTEGER, user_id INTEGER);\n"
        "INSERT INTO sessions VALUES (1, 1);\n"
        "PRAGMA foreign_keys=ON;\n"
    ), old_sql
    # THE TRANSACTION STRIP DID ITS JOB: D1 rejects raw BEGIN/COMMIT.
    assert "BEGIN TRANSACTION;" not in old_sql
    assert "\nCOMMIT;" not in old_sql
    # AND BOTH QUOTING STYLES PRODUCED A DROP: backticks and `IF NOT EXISTS`.
    assert old_sql.count("DROP TABLE IF EXISTS") == 2


# --------------------------------------------------------------------------- Argument handling ---------------------------------------------------------------------------


def test_a_missing_source_or_target_is_the_usage_line_and_exit_1(tmp_path) -> None:
    for args in (("--source", "a"), ("--target", "b"), ()):
        _root, old, new = run_both(tmp_path, args=args)
        _agree(old, new, f"usage-{args}")
        proc, calls = old
        assert proc.returncode == 1
        assert proc.stderr == "✗ %s\n" % port.USAGE
        assert _calls(calls) == [], "nothing may run before the arguments are known"


def test_an_unknown_argument_names_itself_and_exits_1(tmp_path) -> None:
    _root, old, new = run_both(tmp_path, args=("--source", "a", "--wat", "x"))
    _agree(old, new, "unknown-arg")

    proc, _log = old
    assert proc.returncode == 1
    assert proc.stderr == "✗ Unknown argument: --wat\n"


def test_the_last_flag_wins_because_each_arm_assigns(tmp_path) -> None:
    """`--source a --source b` clones `b`. Not a defect, and not obvious: an
    arm that appended would clone both."""
    _root, old, new = run_both(
        tmp_path,
        args=("--source", "first", "--source", "second", "--target", "t"),
    )
    _agree(old, new, "last-wins")

    proc, calls = old
    assert proc.returncode == 0
    assert "d1 export second" in _calls(calls)[0]


def test_a_missing_credential_refuses_before_anything_runs(tmp_path) -> None:
    _root, old, new = run_both(tmp_path, drop_env=("CLOUDFLARE_API_TOKEN",))
    _agree(old, new, "no-token")

    proc, calls = old
    assert proc.returncode == 1
    assert proc.stderr == "✗ Required environment variable 'CLOUDFLARE_API_TOKEN' is not set\n"
    assert _calls(calls) == []


def test_the_wrangler_config_flag_is_word_split_into_two_arguments(tmp_path) -> None:
    """The two `# shellcheck disable=SC2086` lines exist for this: an EMPTY
    value must contribute no argument at all, and a set one must arrive as two. Both directions are checked, because a port that always passed `--config`
    with an empty value would satisfy the second alone."""
    _root, old, new = run_both(
        tmp_path,
        args=("--source", "s", "--target", "t", "--wrangler-config", "wrangler.preview.toml"),
    )
    _agree(old, new, "config-flag")

    proc, calls = old
    assert proc.returncode == 0
    assert "--remote --config wrangler.preview.toml --file=" in _calls(calls)[1]
    assert "--remote --config wrangler.preview.toml --command=" in _calls(calls)[2]

    _root2, old2, _new2 = run_both(tmp_path)
    assert "--config" not in _calls(old2[1])[1]


# --------------------------------------------------------------------------- The export retry, which is the twin's only tolerance for a flaky R2 ---------------------------------------------------------------------------


def test_a_transient_export_failure_is_retried_and_the_second_attempt_wins(
    tmp_path,
) -> None:
    """One failure then success: two `d1 export` calls, one warning naming the
    attempt, and a green run. The 10s sleep between attempts is the twin's and
    is not shortened, which is why this is the only retry case driven twice."""
    _root, old, new = run_both(tmp_path, FAKE_EXPORT_FAIL_UNTIL="1")
    _agree(old, new, "retry-then-succeed")

    proc, calls = old
    assert proc.returncode == 0
    assert _verbs(calls) == ["d1 export", "sleep", "d1 export", "d1 execute", "d1 execute"]
    assert "sleep 10" in _calls(calls), "the wait is the twin's, and it is an exec"
    assert (
        "⚠ wrangler d1 export account-db-eu failed (exit 1) on attempt 1/3; retrying in 10s"
        in proc.stderr
    )


def test_three_failures_exhaust_the_retries_and_exit_with_wranglers_status(
    tmp_path,
) -> None:
    """A database that genuinely cannot be exported still fails, three times
    over, with the attempt count and wrangler's own output in the message. And the REDACTION STILL APPLIES on the failure path, which is the case the
    twin's header says the old `| grep -v` form killed silently."""
    _root, old, new = run_both(tmp_path, FAKE_EXPORT_FAIL_UNTIL="3")
    _agree(old, new, "retry-exhausted")

    proc, calls = old
    assert proc.returncode == 1
    assert _verbs(calls) == ["d1 export", "sleep", "d1 export", "sleep", "d1 export"], (
        "three attempts, and only TWO waits: nothing sleeps after the last one"
    )
    assert (
        "✗ wrangler d1 export account-db-eu failed (exit 1) after 3 attempts; "
        "its full output is above (R2 URL redacted)" in proc.stderr
    )
    assert "r2.cloudflarestorage.com" not in proc.stdout
    assert "ERROR Could not create a presigned URL to R2" in proc.stdout, (
        "the real error must survive the redaction"
    )


# --------------------------------------------------------------------------- Failure propagation on the two unguarded wrangler calls ---------------------------------------------------------------------------


def test_a_failing_import_ends_the_run_with_wranglers_status(tmp_path) -> None:
    """`npx wrangler d1 execute --file=` is unguarded, so `set -e` hands its
    status straight out. The FK verification never runs, which is the important
    half: a failed import must not be followed by a clean bill of health."""
    _root, old, new = run_both(tmp_path, FAKE_EXECUTE_FAILS_ON="2")
    _agree(old, new, "import-fails")

    proc, calls = old
    assert proc.returncode == 3
    assert _verbs(calls) == ["d1 export", "d1 execute"]
    assert "FK integrity check passed" not in proc.stderr


def test_real_fk_violations_are_reported_and_exit_1(tmp_path) -> None:
    _root, old, new = run_both(tmp_path, FAKE_FK="violations")
    _agree(old, new, "fk-violations")

    proc, _log = old
    assert proc.returncode == 1
    assert "✗ Foreign key violations found: 1" in proc.stderr
    # The offending rows are printed on STDOUT by a second jq.
    assert '"table": "sessions"' in proc.stdout


# --------------------------------------------------------------------------- The four named defects ---------------------------------------------------------------------------


def test_defect_a_the_sanitize_path_cannot_work_because_its_sql_file_is_gone(
    tmp_path,
) -> None:
    """`sanitize-d1.sql` was deleted on 2026-04-06 (commit 57b61098c) and the
    only caller that passes `--sanitize` is `edge-clone-d1.yml`. The run dies where the file is opened: AFTER the export, BEFORE the import, so it fails
    closed and no unsanitised data reaches the target."""
    assert port.THE_SANITIZE_PATH_CANNOT_WORK
    assert not (ROOT / ".ci" / "scripts" / "deploy" / "sanitize-d1.sql").exists(), (
        "the file is back; DEFECT A needs re-reading rather than this assertion relaxing"
    )

    _root, old, new = run_both(
        tmp_path,
        args=("--source", "s", "--target", "t", "--sanitize"),
    )
    _agree(old, new, "sanitize-missing-sql")

    proc, calls = old
    assert proc.returncode == 1
    assert "→ Sanitizing data via local sqlite3" in proc.stderr
    assert proc.stderr.rstrip().endswith("sanitize-d1.sql: No such file or directory")
    # The export happened and the import did NOT.
    assert _verbs(calls) == ["d1 export", "sqlite3"]
    assert "Import complete" not in proc.stderr


def test_defect_a_the_same_path_completes_once_the_file_is_restored(tmp_path) -> None:
    """THE CONTROL FOR THE ABOVE. With the deleted file recreated inside the
    fixture, the sanitize path runs end to end: three `sqlite3` calls, then the
    import. So the failure really is the missing file and not something else
    about the branch, and the port's version of the branch is exercised rather
    than merely refused early."""
    _root, old, new = run_both(
        tmp_path,
        fixture_kw={"sanitize_sql": True},
        args=("--source", "s", "--target", "t", "--sanitize"),
    )
    _agree(old, new, "sanitize-restored")

    proc, calls = old
    assert proc.returncode == 0, proc.stderr
    assert _verbs(calls) == [
        "d1 export",
        "sqlite3",
        "sqlite3",
        "sqlite3",
        "d1 execute",
        "d1 execute",
    ]
    assert "✓ Sanitized (" in proc.stderr


def test_defect_a_a_missing_sqlite3_refuses_with_the_common_sh_wording(tmp_path) -> None:
    """`require_cmd sqlite3` runs AFTER the step banner, so the refusal is the
    second line rather than the first."""
    _root, old, new = run_both(
        tmp_path,
        args=("--source", "s", "--target", "t", "--sanitize"),
        drop="sqlite3",
    )
    _agree(old, new, "sanitize-no-sqlite3")

    proc, _log = old
    assert proc.returncode == 1
    assert "✗ Required command 'sqlite3' is not available" in proc.stderr


def test_defect_b_a_verification_that_could_not_run_reports_zero_violations(
    tmp_path,
) -> None:
    """The FK probe exits 1 with nothing on stdout and its stderr discarded. The
    script prints its success line and exits 0, which is the failure this whole
    step exists to prevent, applied to itself."""
    assert port.A_FAILED_FK_CHECK_REPORTS_ZERO_VIOLATIONS
    _root, old, new = run_both(tmp_path, FAKE_FK="silent")
    _agree(old, new, "fk-silent")

    proc, calls = old
    assert proc.returncode == 0, "a verification that never ran is scored as a pass"
    assert "✓ FK integrity check passed (0 violations)" in proc.stderr
    assert "wrangler: could not reach the API" not in proc.stderr, (
        "2>/dev/null means the operator is not even told"
    )
    assert _verbs(calls)[-1] == "d1 execute"


def test_defect_c_the_account_id_is_never_required(tmp_path) -> None:
    """The header says the script requires it. `require_var` is called on the
    token only, so a run without the account id gets all the way to wrangler."""
    assert port.THE_ACCOUNT_ID_GUARD_THE_HEADER_PROMISES_IS_ABSENT
    _root, old, new = run_both(tmp_path, drop_env=("CLOUDFLARE_ACCOUNT_ID",))
    _agree(old, new, "no-account-id")

    proc, _log = old
    assert proc.returncode == 0
    assert "CLOUDFLARE_ACCOUNT_ID" not in proc.stderr
    assert "Requires: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID" in TWIN.read_text(
        encoding="utf-8"
    ), "the header still promises the guard the code does not have"


def test_defect_d_the_blocker_comments_name_a_value_the_script_never_builds() -> None:
    """A source-level assertion, because the defect is in the SUPPRESSION rather
    than in any behaviour: both `# BLOCKER:` lines justify the unquoted
    expansion with a value (`--env=X`, from a `cloneSource`) that appears
    nowhere in the file."""
    assert port.THE_BLOCKER_COMMENTS_NAME_A_VALUE_THAT_IS_NEVER_BUILT
    text = TWIN.read_text(encoding="utf-8")
    assert text.count("# BLOCKER:") == 2
    assert text.count('--env=X"') + text.count("--env=X ") >= 2, "the stale wording"
    assert "cloneSource" in text
    # The only thing actually assigned to CONFIG_FLAG:
    assert 'CONFIG_FLAG="--config $WRANGLER_CONFIG"' in text
    assert "--env=" not in text.split("# BLOCKER", 1)[0], (
        "no code above the first suppression builds --env= either"
    )


# --------------------------------------------------------------------------- Pure helpers, exercised directly ---------------------------------------------------------------------------


def test_bash_arithmetic_gt_zero_follows_bash_rather_than_int() -> None:
    """EVERY ROW HERE WAS PROBED AGAINST REAL BASH, and three of them are
    surprising: a bare word is a VARIABLE and is fatal under `set -u`, `0x10` is
    hex, and `08` is a malformed octal that evaluates FALSE without stopping."""
    assert port.bash_arithmetic_gt_zero("1") is True
    assert port.bash_arithmetic_gt_zero("0") is False
    assert port.bash_arithmetic_gt_zero("") is False, "an empty count is zero, not an error"
    assert port.bash_arithmetic_gt_zero("   ") is False
    assert port.bash_arithmetic_gt_zero("-3") is False
    assert port.bash_arithmetic_gt_zero("010") is True, "octal 10 is 8, still positive"
    assert port.bash_arithmetic_gt_zero("0x10") is True, "hex is arithmetic too"
    assert port.bash_arithmetic_gt_zero("08") is False, (
        "bash cannot parse 08 as octal; the comparison is FALSE and does not stop"
    )
    assert port.bash_arithmetic_gt_zero("1a") is False, "a bad number, not a variable"
    assert port.bash_arithmetic_gt_zero("1 2") is False, "a syntax error, not a variable"

    # THE FATAL ROWS: a bare word is a variable reference, and an unset one under `set -u` ends the script.
    for fatal in ("null", "a b", "a-b"):
        with pytest.raises(port.BashUnboundError) as caught:
            port.bash_arithmetic_gt_zero(fatal)
        assert caught.value.name == fatal.split()[0].split("-")[0]


def test_config_flag_words_splits_the_way_an_unquoted_expansion_does() -> None:
    assert port.config_flag_words("") == []
    assert port.config_flag_words("w.toml") == ["--config", "w.toml"]
    assert port.config_flag_words("  a  b  ") == ["--config", "a", "b"], (
        "a run of whitespace is one separator and the empties vanish"
    )


def test_the_argv_builders_match_the_twins_words() -> None:
    assert port.export_argv("db", "/t/e.sql") == [
        "npx",
        "wrangler",
        "d1",
        "export",
        "db",
        "--remote",
        "--output=/t/e.sql",
    ]
    assert port.execute_file_argv("db", [], "/t/i.sql")[-1] == "--file=/t/i.sql"
    assert port.execute_file_argv("db", ["--config", "w"], "/t/i.sql")[-3:-1] == ["--config", "w"]
    assert port.fk_check_argv("db", [])[-2:] == [
        "--command=PRAGMA foreign_key_check",
        "--json",
    ]


def test_the_sed_programs_are_the_twins_own_bytes() -> None:
    """A STALENESS GUARD ON THE TWO PROGRAMS THAT BUILD THE ARTIFACT. They are
    quoted out of the twin rather than paraphrased, so a change to either one in
    the bash file fails here instead of silently diverging."""
    text = TWIN.read_text(encoding="utf-8")
    assert port.STRIP_TRANSACTIONS_SED in text
    assert port.DROP_STATEMENTS_SED in text
    assert port.REDACT_PATTERN in text
    assert port.USAGE in text
    assert port.FK_COMMAND in text


def test_the_twin_still_says_what_this_port_says_it_says() -> None:
    text = TWIN.read_text(encoding="utf-8")
    assert "EXPORT_ATTEMPTS=3" in text
    assert "sleep 10" in text
    assert "require_var CLOUDFLARE_API_TOKEN" in text
    assert "trap 'rm -rf \"$TMPDIR\"' EXIT" in text
    assert '"$SCRIPT_DIR/sanitize-d1.sql"' in text
    assert 'echo "PRAGMA defer_foreign_keys=ON;"' in text
    assert 'echo "PRAGMA foreign_keys=ON;"' in text
    assert "FK integrity check passed (0 violations)" in text


def test_the_helpers_the_selftest_leans_on_are_exported() -> None:
    for name in (
        "parse_argv",
        "config_flag_words",
        "export_argv",
        "execute_file_argv",
        "fk_check_argv",
        "bash_arithmetic_gt_zero",
        "wc_lines",
    ):
        assert inspect.isfunction(getattr(port, name)), name


def test_the_mktemp_mask_hides_only_the_random_suffix() -> None:
    """A MASK THAT SWALLOWED MORE THAN THE SUFFIX WOULD MAKE `_agree` VACUOUS.

    Both halves, because either alone is satisfiable by a broken pattern.
    """
    a = "call: npx wrangler d1 export db --remote --output=/tmp/tmp.KSwRwsYJRr/export.sql"
    b = "call: npx wrangler d1 export db --remote --output=/tmp/tmp.JTIJi7lgUF/export.sql"
    assert _mask(a) == _mask(b)
    assert _mask(a).endswith("--output=<MKTEMP>/export.sql")
    c = "call: npx wrangler d1 export db --remote --output=/tmp/tmp.KSwRwsYJRr/dump.sql"
    assert _mask(a) != _mask(c)
    assert _mask("/tmp/somewhere/else") == "/tmp/somewhere/else"
    assert _mask("/tmp/tmp.short") == "/tmp/tmp.short"


def test_the_bash_diagnostic_normaliser_keeps_the_path_and_the_reason() -> None:
    """A NORMALISER THAT SWALLOWED MORE WOULD MAKE `_agree` VACUOUS on the one
    path that uses it. Both halves: the two spellings of the same diagnostic
    collapse together, and a DIFFERENT path or reason still differs."""
    bash_side = "/x/y/.ci/scripts/deploy/clone-d1.sh: line 117: /t/sanitize-d1.sql: No such file"
    port_side = "clone-d1.sh: /t/sanitize-d1.sql: No such file"
    assert _mask(bash_side) == _mask(port_side)
    assert _mask(bash_side) == "clone-d1: /t/sanitize-d1.sql: No such file"

    other_path = "/x/y/clone-d1.sh: line 117: /t/OTHER.sql: No such file"
    assert _mask(other_path) != _mask(bash_side)
    other_reason = "/x/y/clone-d1.sh: line 117: /t/sanitize-d1.sql: Permission denied"
    assert _mask(other_reason) != _mask(bash_side)
    # AND A MESSAGE FROM ANYTHING ELSE IS NOT TOUCHED AT ALL.
    assert _mask("wrangler: execute refused") == "wrangler: execute refused"
    assert _mask("✗ Unknown argument: --wat") == "✗ Unknown argument: --wat"


def test_the_port_declares_the_environment_it_reads() -> None:
    """`CLOUDFLARE_API_TOKEN` is reached through `common.require_var`, which
    reads `os.environ` inside `rediacc_ci.core.common` where the env-registry scanner already sees it. This module therefore owes no registry entry of its
    own, and this assertion is what will notice the day it does."""
    body = PORT_FILE.read_text(encoding="utf-8").split('"""', 2)[2]
    assert "os.environ" not in body
    assert "common.require_var(REQUIRED_VAR)" in body
    assert port.REQUIRED_VAR == "CLOUDFLARE_API_TOKEN"
