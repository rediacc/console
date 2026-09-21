"""`rediacc_ci.housekeeping.cleanup_stale_d1`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/housekeeping/cleanup-stale-d1.sh` and the port over two fresh scratch directories and compared exit code, stdout, stderr and the `npx` call log. The K=5 ledger `.ci/shadow/w7p6-cleanup-stale-d1.observations.jsonl` recorded that comparison over five distinct trees, in a disposable scratch git repository outside this
checkout. The twin has now been deleted and every case that executed it compares against `goldens/cleanup-stale-d1/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

A RECORDING FAKE `npx` ON A PREPENDED PATH, AND `npx` IS THE RIGHT THING TO STUB. Both call sites go through it -- `npx wrangler d1 list --json` and `npx wrangler d1 delete <name> --skip-confirmation` -- and `require_cmd` guards `npx`, never `wrangler`. Stubbing `wrangler` alone would leave the subject resolving the REAL npx, which would try to fetch the wrangler package from the
network on a cold cache, so the fake answers as npx and dispatches the `wrangler d1 ...` shapes itself. A `wrangler` stub is installed beside it and records to the same log, purely so that a future call site that drops the `npx` prefix cannot silently reach the real CLI; `test_the_port_cannot_reach_a_real_wrangler` asserts both resolutions.

WHAT WOULD HAPPEN WITHOUT THE STUB IS NOT HYPOTHETICAL: this subject's entire purpose is `wrangler d1 delete --skip-confirmation`, against whatever Cloudflare account `CLOUDFLARE_ACCOUNT_ID` names, with no confirmation prompt to stop it. `CLOUDFLARE_API_TOKEN` is pinned to a fixture value in every case for the same reason, so even a leaked real wrangler would be
unauthenticated.

THE CALL LOG IS THE PRIMARY ARTIFACT, and the dry-run split is exactly why. A `--dry-run` that still deleted, or a real run that only listed, prints text that differs by one bracketed word and makes a call sequence that differs completely. Both paths are recorded and both compare the log.

`date`, `sed`, `jq` AND `wc` WERE THE REAL BINARIES ON BOTH SIDES. The port EXECUTES `date` (so the GNU/BSD probe and every unvalidated `--max-age` shape answer identically) and keeps `require_cmd jq` while parsing JSON natively; the twin used jq, sed and wc for work this port does in Python. That asymmetry is the point of comparing outputs rather than implementations.

TIME IS NOT PINNED, AND DOES NOT NEED TO BE. The recording and the replay compute their cutoff minutes or months apart, so the `Cutoff: <ts>` line is masked. Every fixture timestamp is placed FAR from the boundary (the year 2000 against 2099), so no selection can turn on that difference, and `test_the_cutoff_line_is_the_only_clock_dependent_output` asserts that the cutoff
line is the only place a clock appears.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

from rediacc_ci import paths
from rediacc_ci.housekeeping import cleanup_stale_d1 as csd
from rediacc_ci.tests import frozen

ROOT = paths.repo_root()
PORT = pathlib.Path(csd.__file__).resolve()
BASH = shutil.which("bash") or "/bin/bash"

SLUG = "cleanup-stale-d1"

TOKEN = "fixture-cloudflare-token"  # noqa: S105 -- a throwaway fixture value that authenticates nowhere
ACCOUNT = "fixture-account-id"

# Far in the past and far in the future, so no selection can turn on the gap between the recording's clock and the replay's. See the module docstring.
OLD = "2000-01-01T00:00:00.000Z"
NEW = "2099-01-01T00:00:00.000Z"

FAKE_NPX = """#!/usr/bin/python3
import json
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(os.path.basename(sys.argv[0]) + "\\t" + "\\t".join(argv) + "\\n")

# `npx wrangler d1 ...` and a bare `wrangler d1 ...` are the same two shapes.
rest = argv[1:] if argv[:1] == ["wrangler"] else argv

if rest[:2] == ["d1", "list"]:
    rc = int(os.environ.get("FAKE_LIST_RC", "0"))
    # `FAKE_LIST_SILENT` RATHER THAN `FAKE_LIST_STDOUT=""`, because the harness
    # treats an EMPTY environment value as UNSET -- that is how `${CI:-}` and
    # `${CLOUDFLARE_API_TOKEN:-}` get driven down their absent arms. Passing an
    # empty stdout therefore fell back to this default `[]` and the
    # api-unreachable case quietly tested a healthy empty account instead. The
    # sides still AGREED, so only the expected text caught it.
    if not os.environ.get("FAKE_LIST_SILENT"):
        sys.stdout.write(os.environ.get("FAKE_LIST_STDOUT", "[]"))
    sys.stderr.write(os.environ.get("FAKE_LIST_STDERR", ""))
    sys.exit(rc)

if rest[:2] == ["d1", "delete"]:
    name = rest[2] if len(rest) > 2 else ""
    sys.stdout.write("Deleted database %s\\n" % name)
    if name in os.environ.get("FAKE_DELETE_FAILS", "").split(","):
        sys.stderr.write("fixture: refusing to delete %s\\n" % name)
        sys.exit(1)
    sys.exit(0)

sys.stderr.write("fixture npx: unexpected argv %r\\n" % (argv,))
sys.exit(70)
"""

# What the twin needed on PATH before its `require_cmd`s could speak. `tr` is here because `parse_args` -> `to_upper` forks it once PER FLAG (common.sh:302), and a curated PATH without it killed the twin at 127 before any validation ran -- measured while porting the sibling `docker-pull-ghcr.sh`, where its absence made a perfectly good port look like it had lost `require_cmd`.
CURATED = ("dirname", "uname", "tr", "sed", "date", "wc", "cat")

CALLS_MARKER = "--- calls ---\n"


def _stub_bin(base: pathlib.Path, *, drop: tuple[str, ...] = ()) -> str:
    """The fakes, prepended to the real PATH -- or a curated path when a case needs a tool to be ABSENT.

    `drop` names tools the case wants missing (`jq`, `npx`). Those cases cannot prepend, because the real PATH has both, so they get a symlink farm of exactly what the subject needs to reach its refusal and nothing else.
    """
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    for name in ("npx", "wrangler"):
        if name in drop:
            continue
        fake = stub / name
        fake.write_text(FAKE_NPX, encoding="utf-8")
        fake.chmod(0o755)
    if not drop:
        return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))
    for name in (*CURATED, "jq"):
        if name in drop:
            continue
        real = shutil.which(name)
        assert real is not None, "no %s on PATH; the subject cannot even start" % name
        (stub / name).symlink_to(real)
    return str(stub)


def _run(subject: pathlib.Path, base: pathlib.Path, argv: list[str], extra: dict[str, str]):
    log = base / "calls.log"
    log.write_text("", encoding="utf-8")
    drop = tuple(x for x in extra.pop("_drop", "").split(",") if x)
    env = {
        "PATH": _stub_bin(base, drop=drop),
        "HOME": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "TZ": "UTC",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_LOG": str(log),
        "CLOUDFLARE_API_TOKEN": TOKEN,
        "CLOUDFLARE_ACCOUNT_ID": ACCOUNT,
    }
    for key, value in list(extra.items()):
        if value == "":
            env.pop(key, None)
            extra.pop(key)
    env.update(extra)
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *argv],
        capture_output=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=120,
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    return proc.returncode, proc.stdout, proc.stderr, calls


# The `Cutoff: ...` line is the one place a clock reaches the output, and the recording and the replay compute theirs far apart. Masked for comparison and asserted separately.
def _mask_cutoff(stderr: str) -> str:
    out = []
    for line in stderr.split("\n"):
        if "Cutoff: " in line:
            head, _, tail = line.partition("Cutoff: ")
            out.append(head + "Cutoff: <ts> " + tail.split(" ", 1)[1])
        else:
            out.append(line)
    return "\n".join(out)


def _listing(*rows: tuple[str, str], banner: str = "") -> str:
    """Wrangler's `d1 list --json`, optionally behind the banner it really prints."""
    payload = json.dumps(
        [{"uuid": "u-%d" % i, "name": n, "created_at": c} for i, (n, c) in enumerate(rows)],
        indent=2,
    )
    return banner + payload + "\n"


def case_kw(name: str) -> tuple[list[str], dict[str, str]]:
    """One recorded case's argv and fake knobs, rebuilt fresh because `_run` consumes the mapping."""
    table: dict[str, tuple[list[str], dict[str, str]]] = {
        "a-missing-token": ([], {"CLOUDFLARE_API_TOKEN": ""}),
        "a-missing-account-id": ([], {"CLOUDFLARE_ACCOUNT_ID": ""}),
        "a-missing-jq": ([], {"_drop": "jq"}),
        "a-missing-npx": ([], {"_drop": "npx"}),
        "an-unreachable-api": (
            [],
            {
                "FAKE_LIST_RC": "1",
                "FAKE_LIST_SILENT": "1",
                "FAKE_LIST_STDERR": "Authentication error [code: 10000]\n",
            },
        ),
        "a-banner-with-no-array": ([], {"FAKE_LIST_STDOUT": "Fetching account details...\n"}),
        "a-banner-before-the-array": (
            [],
            {
                "FAKE_LIST_STDOUT": _listing(
                    ("prod-db", OLD), banner="⛅️ wrangler 4.0.0\n----------\n"
                )
            },
        ),
        "a-database-without-the-prefix": (
            [],
            {"FAKE_LIST_STDOUT": _listing(("prod-db", OLD), ("staging", OLD))},
        ),
        "a-prefixed-database-newer-than-the-cutoff": (
            [],
            {"FAKE_LIST_STDOUT": _listing(("migration-test-fresh", NEW))},
        ),
        "the-real-delete-path": (
            [],
            {
                "FAKE_LIST_STDOUT": _listing(
                    ("migration-test-b", OLD),
                    ("prod-db", OLD),
                    ("migration-test-a", OLD),
                    ("migration-test-fresh", NEW),
                )
            },
        ),
        "a-dry-run": (
            ["--dry-run"],
            {"FAKE_LIST_STDOUT": _listing(("migration-test-a", OLD), ("migration-test-b", OLD))},
        ),
        "a-dry-run-with-nothing-stale": (
            ["--dry-run"],
            {"FAKE_LIST_STDOUT": _listing(("migration-test-x", NEW))},
        ),
        "a-failed-delete": (
            [],
            {
                "FAKE_LIST_STDOUT": _listing(("migration-test-a", OLD), ("migration-test-b", OLD)),
                "FAKE_DELETE_FAILS": "migration-test-a",
            },
        ),
        "a-widened-max-age": (
            ["--max-age", "1440"],
            {"FAKE_LIST_STDOUT": _listing(("migration-test-a", OLD))},
        ),
        "an-unparseable-max-age": (
            ["--max-age", "not-a-number"],
            {"FAKE_LIST_STDOUT": _listing(("migration-test-a", OLD))},
        ),
        "a-negative-max-age": (
            ["--dry-run", "--max-age", "-30"],
            {"FAKE_LIST_STDOUT": _listing(("migration-test-brand-new", NEW))},
        ),
        "one-stale-database-under-dry-run": (
            ["--dry-run"],
            {"FAKE_LIST_STDOUT": _listing(("migration-test-a", OLD))},
        ),
        "an-empty-array": ([], {"FAKE_LIST_STDOUT": "[]\n"}),
        "a-flag-that-is-not-an-identifier": (["--max.age=5"], {}),
    }
    return table[name]


CASES = (
    "a-missing-token",
    "a-missing-account-id",
    "a-missing-jq",
    "a-missing-npx",
    "an-unreachable-api",
    "a-banner-with-no-array",
    "a-banner-before-the-array",
    "a-database-without-the-prefix",
    "a-prefixed-database-newer-than-the-cutoff",
    "the-real-delete-path",
    "a-dry-run",
    "a-dry-run-with-nothing-stale",
    "a-failed-delete",
    "a-widened-max-age",
    "an-unparseable-max-age",
    "a-negative-max-age",
    "one-stale-database-under-dry-run",
    "an-empty-array",
    "a-flag-that-is-not-an-identifier",
)


def render(returncode: int, stdout: bytes, stderr: bytes, calls: list[str]) -> str:
    """The recorded shape, with this checkout's own path masked.

    One case reaches bash's `<path>: line <n>: ` diagnostic, which names `common.sh` by its absolute path in whatever checkout recorded it. Masking it keeps a machine-specific string out of a tracked file; that case is normalized rather than compared byte for byte, and says so in its own test.
    """
    body = frozen.render(
        returncode,
        frozen.mask_root(stdout.decode("utf-8"), ROOT),
        frozen.mask_root(stderr.decode("utf-8"), ROOT),
    )
    return body + CALLS_MARKER + "".join("%s\n" % line for line in calls)


def recorded(name: str) -> tuple[int, str, str, list[str]]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    streams, calls_text = rest.split(CALLS_MARKER, 1)
    stdout, stderr = streams.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        [line for line in calls_text.splitlines() if line],
    )


def drive(name: str, *, subject: pathlib.Path | None = None) -> tuple[int, str, str, list[str]]:
    argv, extra = case_kw(name)
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td) / "run"
        base.mkdir(parents=True)
        returncode, stdout, stderr, calls = _run(subject or PORT, base, argv, extra)
    return returncode, stdout.decode("utf-8"), stderr.decode("utf-8"), calls


def compare(name: str, *, subject: pathlib.Path | None = None) -> tuple[int, str, str, list[str]]:
    want_exit, want_out, want_err, want_calls = recorded(name)
    returncode, stdout, stderr, calls = drive(name, subject=subject)
    assert returncode == want_exit, "%s: the twin exited %d, the port %d" % (
        name,
        want_exit,
        returncode,
    )
    assert stdout == want_out, "%s: stdout diverged from the recorded bytes" % name
    assert _mask_cutoff(stderr) == _mask_cutoff(want_err), (
        "%s: stderr diverged from the recorded bytes" % name
    )
    assert calls == want_calls, "%s: the call sequence diverged:\n%r\n%r" % (
        name,
        want_calls,
        calls,
    )
    return returncode, stdout, stderr, calls


# --------------------------------------------------------------------------- The controls, first: a fake that is not reached proves nothing. ---------------------------------------------------------------------------


def test_the_port_cannot_reach_a_real_wrangler() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        path = _stub_bin(base)
        assert shutil.which("npx", path=path) == str(base / "bin" / "npx")
        assert shutil.which("wrangler", path=path) == str(base / "bin" / "wrangler")
        # And the four the port EXECUTES must still be the real ones.
        for real in ("jq", "date", "sed", "wc"):
            found = shutil.which(real, path=path)
            assert found is not None, real
            assert not found.startswith(str(base)), real


def test_the_port_exists_where_this_file_says_it_does() -> None:
    assert PORT.is_file(), PORT


# --------------------------------------------------------------------------- The pure halves, driven against the real sed and the real jq. ---------------------------------------------------------------------------


def _real_sed(text: str) -> str:
    """`sed -n '/^\\[/,$p'`, run by the binary the twin ran."""
    proc = subprocess.run(
        ["sed", "-n", "/^\\[/,$p"], input=text, capture_output=True, text=True, check=False
    )
    # The twin wrapped this in `$(...)`, which strips trailing newlines.
    return proc.stdout.rstrip("\n")


def test_sed_from_first_bracket_agrees_with_the_real_sed() -> None:
    for text in (
        "[]",
        "[]\n",
        "banner line\n[\n  {}\n]\n",
        "no json here\n",
        "",
        # ANCHORED: a `[` that is not at the start of a line does not open it.
        "prefix [ not anchored\n[1]\n",
        # The range ran to END OF INPUT, so trailing banner text is INCLUDED and then fails validation. That is the twin's behaviour, not a bug in this helper.
        "[1]\ntrailing banner\n",
        "[1]\n[2]\n",
    ):
        assert csd.sed_from_first_bracket(text) == _real_sed(text), repr(text)


def test_stale_names_keeps_array_order_and_the_prefix_and_the_cutoff() -> None:
    dbs = [
        {"name": "migration-test-a", "created_at": OLD},
        {"name": "prod-db", "created_at": OLD},
        {"name": "migration-test-b", "created_at": NEW},
        {"name": "migration-test-c", "created_at": OLD},
    ]
    assert csd.stale_names(dbs, "2026-01-01T00:00:00") == [
        "migration-test-a",
        "migration-test-c",
    ]


def test_the_comparison_is_lexicographic_so_the_same_second_is_not_stale() -> None:
    """`created_at < $cutoff` was jq STRING comparison, and wrangler's value carries `.000Z` that the cutoff does not. So an identical first 19 characters makes created_at the LONGER, GREATER string and the database survives. A port that parsed both into datetimes would flip this."""
    cutoff = "2026-05-05T10:00:00"
    assert (
        csd.stale_names([{"name": "migration-test-x", "created_at": cutoff + ".000Z"}], cutoff)
        == []
    )
    assert csd.stale_names([{"name": "migration-test-x", "created_at": cutoff}], cutoff) == []
    assert csd.stale_names(
        [{"name": "migration-test-x", "created_at": "2026-05-05T09:59:59.999Z"}], cutoff
    ) == ["migration-test-x"]


def test_a_database_with_no_created_at_is_stale_on_both_sides() -> None:
    """jq sorts `null` BELOW every string, so `null < $cutoff` was true and the row IS selected. Reproduced rather than skipped."""
    assert csd.stale_names([{"name": "migration-test-x"}], "2026-01-01T00:00:00") == [
        "migration-test-x"
    ]


def test_parse_databases_refuses_anything_that_is_not_a_json_array() -> None:
    assert csd.parse_databases("") is None
    assert csd.parse_databases("not json") is None
    assert csd.parse_databases("[1]\ntrailing banner") is None
    assert csd.parse_databases("[]") == []


# --------------------------------------------------------------------------- Every recorded case ---------------------------------------------------------------------------


# The one case whose recorded stderr is bash's own `<path>: line <n>: ` diagnostic, naming `common.sh` rather than the subject. The port cannot and must not reproduce it, so that case is compared by status, call log and reason instead, in its own test below.
NORMALIZED = ("a-flag-that-is-not-an-identifier",)


@pytest.mark.parametrize("name", [c for c in CASES if c not in NORMALIZED])
def test_port_matches_the_twins_recorded_output(name: str) -> None:
    compare(name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_a_missing_token_is_refused_before_wrangler_is_reached() -> None:
    exit_code, _, stderr, calls = recorded("a-missing-token")
    assert exit_code == 1
    assert calls == []
    assert stderr == "✗ Required environment variable 'CLOUDFLARE_API_TOKEN' is not set\n"


def test_a_missing_account_id_is_refused_too() -> None:
    exit_code, _, stderr, calls = recorded("a-missing-account-id")
    assert exit_code == 1
    assert calls == []
    assert stderr == "✗ Required environment variable 'CLOUDFLARE_ACCOUNT_ID' is not set\n"


def test_a_missing_jq_is_refused_even_though_the_port_does_not_use_jq() -> None:
    """`require_cmd jq` IS KEPT IN THE PORT ON PURPOSE. Dropping it would widen the set of hosts the script runs on, which is a cutover decision and not a porting one -- and it would make this case diverge. The port parses JSON
    with `json.loads`; the GUARD is what is being preserved, not the tool."""
    exit_code, _, stderr, calls = recorded("a-missing-jq")
    assert exit_code == 1
    assert calls == []
    assert stderr == "✗ Required command 'jq' is not available\n"


def test_a_missing_npx_is_refused_after_jq() -> None:
    """The GUARD ORDER is observable: jq was checked first, so a host missing both is told about jq."""
    exit_code, _, stderr, calls = recorded("a-missing-npx")
    assert exit_code == 1
    assert calls == []
    assert stderr == "✗ Required command 'npx' is not available\n"


def test_an_unreachable_api_is_a_green_exit() -> None:
    """HAZARD 1, PINNED. `2>/dev/null || true` threw away both the status and the message, so an expired token is indistinguishable from an empty account and the reaper exits 0 having reaped nothing. This test exists so the day someone makes the failure loud, they have to come here."""
    exit_code, stdout, stderr, calls = recorded("an-unreachable-api")
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"]
    assert stdout == ""
    assert "✓ No D1 databases found (or API unavailable)" in stderr
    # The real reason never reached anyone.
    assert "Authentication error" not in stderr


def test_a_non_json_banner_with_no_array_is_the_same_green_exit() -> None:
    exit_code, _, stderr, calls = recorded("a-banner-with-no-array")
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"]
    assert "✓ No D1 databases found (or API unavailable)" in stderr


def test_a_banner_before_the_array_is_stripped_and_the_array_is_read() -> None:
    """`sed -n '/^\\[/,$p'` existed for exactly this: wrangler prints chatter before its JSON."""
    exit_code, _, stderr, calls = recorded("a-banner-before-the-array")
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"]
    assert "✓ Found 1 total D1 databases" in stderr
    assert "✓ No stale migration-test databases found" in stderr


def test_a_database_that_does_not_carry_the_prefix_is_never_touched() -> None:
    exit_code, _, stderr, calls = recorded("a-database-without-the-prefix")
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"]
    assert "✓ Found 2 total D1 databases" in stderr
    assert "✓ No stale migration-test databases found" in stderr


def test_a_prefixed_database_newer_than_the_cutoff_survives() -> None:
    exit_code, _, stderr, calls = recorded("a-prefixed-database-newer-than-the-cutoff")
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"]
    assert "✓ No stale migration-test databases found" in stderr


def test_the_real_delete_path_is_one_call_per_stale_database_in_array_order() -> None:
    exit_code, stdout, stderr, calls = recorded("the-real-delete-path")
    assert exit_code == 0
    assert calls == [
        "npx\twrangler\td1\tlist\t--json",
        "npx\twrangler\td1\tdelete\tmigration-test-b\t--skip-confirmation",
        "npx\twrangler\td1\tdelete\tmigration-test-a\t--skip-confirmation",
    ], calls
    assert "→ Found 2 stale database(s)" in stderr
    assert "✓ Deleting: migration-test-b" in stderr
    assert "✓ Deleted 2 of 2 stale databases" in stderr
    assert "DRY-RUN" not in stderr
    # `2>/dev/null` covered only stderr, so wrangler's own stdout survives.
    assert stdout == "Deleted database migration-test-b\nDeleted database migration-test-a\n"


def test_dry_run_lists_and_deletes_nothing() -> None:
    exit_code, stdout, stderr, calls = recorded("a-dry-run")
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"], "a --dry-run deleted something"
    assert stdout == ""
    assert "⚠ DRY-RUN mode: no deletions will be performed" in stderr
    assert "⚠ [DRY-RUN] Would delete: migration-test-a" in stderr
    assert "⚠ [DRY-RUN] Would delete: migration-test-b" in stderr
    assert "✓ Would delete 2 of 2 stale databases" in stderr
    assert "Deleted 2 of" not in stderr


def test_dry_run_still_prints_nothing_extra_when_there_is_nothing_stale() -> None:
    exit_code, _, stderr, calls = recorded("a-dry-run-with-nothing-stale")
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"]
    assert "DRY-RUN" not in stderr


def test_a_failed_delete_is_a_warning_and_the_run_still_exits_zero() -> None:
    """HAZARD 2, PINNED. `log_warn` did not touch `$?`, so the reaper reports success having removed nothing. The count line is at least honest."""
    exit_code, _, stderr, calls = recorded("a-failed-delete")
    assert exit_code == 0
    assert len(calls) == 3
    assert "⚠ Failed to delete: migration-test-a" in stderr
    assert "✓ Deleted 1 of 2 stale databases" in stderr
    # `2>/dev/null` on the delete: wrangler's complaint never reached anyone.
    assert "refusing to delete" not in stderr


def test_max_age_widens_the_window_and_reaches_the_log_line_verbatim() -> None:
    exit_code, _, stderr, calls = recorded("a-widened-max-age")
    assert exit_code == 0
    assert len(calls) == 2
    assert "(databases older than 1440m)" in stderr


def test_an_unparseable_max_age_dies_with_dates_own_status_and_message() -> None:
    """HAZARD 3: `--max-age` was interpolated into `date` unvalidated, and under `set -e` the command substitution took the run down. The port EXECUTES the same `date` for exactly this reason, so the message is the same binary's."""
    exit_code, _, stderr, calls = recorded("an-unparseable-max-age")
    assert exit_code == 1
    assert calls == ["npx\twrangler\td1\tlist\t--json"], "the cutoff failed after the listing"
    assert "invalid date" in stderr
    assert "Cutoff:" not in stderr


def test_a_negative_max_age_reaches_into_the_future_and_selects_everything() -> None:
    """PRESERVED SHAPE, and it is the one that would hurt. `--max-age -30` makes the cutoff THIRTY MINUTES FROM NOW, so a database created seconds ago is "stale". Recorded under `--dry-run` so the fixture cannot be read as an endorsement of running it for real."""
    exit_code, _, stderr, _ = recorded("a-negative-max-age")
    assert exit_code == 0
    # NEW is the year 2099, so even a cutoff half an hour ahead does not reach it; what this pins is that the flag was passed through unvalidated and that the port agrees about the resulting window.
    assert "(databases older than -30m)" in stderr


def test_the_cutoff_line_is_the_only_clock_dependent_output() -> None:
    """The masking in `_mask_cutoff` is a claim about this subject, so it is checked rather than trusted: with the cutoff line removed, the recording and the port's stderr must be byte-identical without any masking at all."""
    _, _, want_err, _ = recorded("one-stale-database-under-dry-run")
    _, _, stderr, _ = drive("one-stale-database-under-dry-run")
    strip = lambda text: [x for x in text.splitlines() if "Cutoff: " not in x]  # noqa: E731
    assert strip(want_err) == strip(stderr)
    # And the cutoff line itself is present on both, so the strip is not hiding an absence.
    assert any("Cutoff: " in x for x in want_err.splitlines())
    assert any("Cutoff: " in x for x in stderr.splitlines())


def test_an_empty_array_is_zero_total_and_no_stale() -> None:
    exit_code, _, stderr, calls = recorded("an-empty-array")
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"]
    assert "✓ Found 0 total D1 databases" in stderr
    assert "✓ No stale migration-test databases found" in stderr


def test_a_flag_that_is_not_a_shell_identifier_kills_the_run() -> None:
    """common.sh QUIRK 3 through `parse_args "$@"`: exit 2, before any guard.

    THE ONE NORMALIZED CASE, ASSERTED IN BOTH DIRECTIONS. bash reported this against `common.sh`'s own path and line, which is a file the port does not source and a path that would differ per checkout anyway; the port reports the same reason as its own refusal. The STATUS is what a caller branches on and the CALL LOG is what matters operationally, so both are compared; the
    text is compared by reason and asserted DIFFERENT so the divergence stays visible.
    """
    exit_code, _, want_err, want_calls = recorded("a-flag-that-is-not-an-identifier")
    returncode, _, stderr, calls = drive("a-flag-that-is-not-an-identifier")
    assert exit_code == returncode == 2
    assert want_calls == calls == []
    assert "printf: `ARG_MAX.AGE': not a valid identifier" in want_err
    assert "printf: `ARG_MAX.AGE': not a valid identifier" in stderr
    assert want_err != stderr, "the two diagnostics are byte-identical, so this case is not special"


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_sort_of_the_stale_names_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Sort the names the delete loop walks.

    Returning a sorted list is the tidy-looking change a reader would make, and it is invisible in every tally: the SET of databases deleted is identical and "Deleted 2 of 2" still prints. The only witness is the recorded call log, where `migration-test-b` was deleted before `migration-test-a` because jq emitted in array order. The mutation is written to a throwaway file; the
    tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = "            out.append(name)\n    return out\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(
        original.replace(anchor, "            out.append(name)\n    return sorted(out)\n"),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError):
        compare("the-real-delete-path", subject=mutant)
    compare("the-real-delete-path")
    assert PORT.read_text(encoding="utf-8") == original
