"""Differential: `rediacc_ci.housekeeping.cleanup_stale_d1` against its twin `.ci/scripts/housekeeping/cleanup-stale-d1.sh`.

A RECORDING FAKE `npx` ON A PREPENDED PATH, AND `npx` IS THE RIGHT THING TO STUB. Both call sites go through it -- `npx wrangler d1 list --json` and `npx wrangler d1 delete <name> --skip-confirmation` -- and `require_cmd` guards `npx`, never `wrangler`. Stubbing `wrangler` alone would leave both sides resolving the REAL npx, which would try to fetch the wrangler package from the
network on a cold cache, so the fake answers as npx and dispatches the `wrangler d1 ...` shapes itself. A `wrangler` stub is installed beside it and records to the same log, purely so that a future call site that drops the `npx` prefix cannot silently reach the real CLI; `test_neither_side_can_reach_a_real_ wrangler` asserts both resolutions.

WHAT WOULD HAPPEN WITHOUT THE STUB IS NOT HYPOTHETICAL: this subject's entire purpose is `wrangler d1 delete --skip-confirmation`, against whatever Cloudflare account `CLOUDFLARE_ACCOUNT_ID` names, with no confirmation prompt to stop it. `CLOUDFLARE_API_TOKEN` is pinned to a fixture value in every case for the same reason, so even a leaked real wrangler would be unauthenticated.

THE CALL LOG IS THE PRIMARY ARTIFACT, and the dry-run split is exactly why. A `--dry-run` that still deleted, or a real run that only listed, prints text that differs by one bracketed word and makes a call sequence that differs completely. Both paths are driven and both compare the log.

`date`, `sed`, `jq` AND `wc` ARE THE REAL BINARIES ON BOTH SIDES. The port EXECUTES `date` (so the GNU/BSD probe and every unvalidated `--max-age` shape answer identically) and keeps `require_cmd jq` while parsing JSON natively; the twin uses jq, sed and wc for work this port does in Python. That asymmetry is the point of comparing outputs rather than implementations.

TIME IS NOT PINNED, AND DOES NOT NEED TO BE. The two sides compute their cutoff milliseconds apart, so the `Cutoff: <ts>` line could legitimately differ by a second. Every fixture timestamp is therefore placed FAR from the boundary (hours, or the year 2000 against 2099), so no selection can turn on that difference, and `test_the_cutoff_line_is_the_only_clock_dependent_output`
asserts that the cutoff line is the only place a clock appears.

K=5 LEDGER: `.ci/shadow/w7p6-cleanup-stale-d1.observations.jsonl`, recorded in a
disposable scratch git repository outside this checkout.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.housekeeping import cleanup_stale_d1 as csd

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "housekeeping" / "cleanup-stale-d1.sh"
PORT = pathlib.Path(csd.__file__).resolve()
BASH = shutil.which("bash") or "/bin/bash"

TOKEN = "fixture-cloudflare-token"  # noqa: S105 -- a throwaway fixture value that authenticates nowhere
ACCOUNT = "fixture-account-id"

# Far in the past and far in the future, so no selection can turn on the sub-second gap between the two sides' clocks. See the module docstring.
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

# What the twin needs on PATH before its `require_cmd`s can speak. `tr` is here because `parse_args` -> `to_upper` forks it once PER FLAG (common.sh:302), and a curated PATH without it kills the twin at 127 before any validation runs -- measured while porting the sibling `docker-pull-ghcr.sh`, where its absence made a perfectly good port look like it had lost `require_cmd`.
CURATED = ("dirname", "uname", "tr", "sed", "date", "wc", "cat")


def _stub_bin(base: pathlib.Path, *, drop: tuple[str, ...] = ()) -> str:
    """The fakes, prepended to the real PATH -- or a curated path when a case needs a tool to be ABSENT.

    `drop` names tools the case wants missing (`jq`, `npx`). Those cases cannot prepend, because the real PATH has both, so they get a symlink farm of exactly what the twin needs to reach its refusal and nothing else.
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
        assert real is not None, "no %s on PATH; the twin cannot even source common.sh" % name
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


# The `Cutoff: ...` line is the one place a clock reaches the output, and the two sides compute theirs milliseconds apart. Masked for comparison and asserted separately.
def _mask_cutoff(stderr: bytes) -> bytes:
    out = []
    for line in stderr.split(b"\n"):
        if b"Cutoff: " in line:
            head, _, tail = line.partition(b"Cutoff: ")
            out.append(head + b"Cutoff: <ts> " + tail.split(b" ", 1)[1])
        else:
            out.append(line)
    return b"\n".join(out)


def _sides(name: str, argv: list[str], **extra: str):
    results = []
    with tempfile.TemporaryDirectory() as td:
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            results.append(_run(subject, base, argv, dict(extra)))
    old, new = results
    assert new[0] == old[0], "%s: exit diverged: twin %r port %r" % (name, old[0], new[0])
    assert new[1] == old[1], "%s: stdout diverged:\n twin: %r\n port: %r" % (name, old[1], new[1])
    assert _mask_cutoff(new[2]) == _mask_cutoff(old[2]), (
        "%s: stderr diverged:\n twin: %r\n port: %r" % (name, old[2], new[2])
    )
    assert new[3] == old[3], "%s: calls diverged:\n twin: %r\n port: %r" % (name, old[3], new[3])
    return old


def _listing(*rows: tuple[str, str], banner: str = "") -> str:
    """Wrangler's `d1 list --json`, optionally behind the banner it really prints."""
    payload = json.dumps(
        [{"uuid": "u-%d" % i, "name": n, "created_at": c} for i, (n, c) in enumerate(rows)],
        indent=2,
    )
    return banner + payload + "\n"


# --------------------------------------------------------------------------- The controls, first: a fake that is not reached proves nothing. ---------------------------------------------------------------------------


def test_neither_side_can_reach_a_real_wrangler() -> None:
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


def test_both_subjects_exist_where_this_file_says_they_do() -> None:
    assert TWIN.is_file(), TWIN
    assert PORT.is_file(), PORT


def test_the_twin_parses_under_bash() -> None:
    proc = subprocess.run([BASH, "-n", str(TWIN)], capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr


# --------------------------------------------------------------------------- The pure halves, driven against the real sed and the real jq. ---------------------------------------------------------------------------


def _real_sed(text: str) -> str:
    """`sed -n '/^\\[/,$p'`, run by the binary the twin runs."""
    proc = subprocess.run(
        ["sed", "-n", "/^\\[/,$p"], input=text, capture_output=True, text=True, check=False
    )
    # The twin wraps this in `$(...)`, which strips trailing newlines.
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
        # The range runs to END OF INPUT, so trailing banner text is INCLUDED and then fails validation. That is the twin's behaviour, not a bug in this helper.
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
    """`created_at < $cutoff` is jq STRING comparison, and wrangler's value carries `.000Z` that the cutoff does not. So an identical first 19 characters makes created_at the LONGER, GREATER string and the database survives. A port that parsed both into datetimes would flip this."""
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
    """jq sorts `null` BELOW every string, so `null < $cutoff` is true and the row IS selected. Reproduced rather than skipped."""
    assert csd.stale_names([{"name": "migration-test-x"}], "2026-01-01T00:00:00") == [
        "migration-test-x"
    ]


def test_parse_databases_refuses_anything_that_is_not_a_json_array() -> None:
    assert csd.parse_databases("") is None
    assert csd.parse_databases("not json") is None
    assert csd.parse_databases("[1]\ntrailing banner") is None
    assert csd.parse_databases("[]") == []


# --------------------------------------------------------------------------- The differential. ---------------------------------------------------------------------------


def test_a_missing_token_is_refused_before_wrangler_is_reached() -> None:
    exit_code, _, stderr, calls = _sides("no-token", [], CLOUDFLARE_API_TOKEN="")
    assert exit_code == 1
    assert calls == []
    assert stderr == "✗ Required environment variable 'CLOUDFLARE_API_TOKEN' is not set\n".encode()


def test_a_missing_account_id_is_refused_too() -> None:
    exit_code, _, stderr, calls = _sides("no-account", [], CLOUDFLARE_ACCOUNT_ID="")
    assert exit_code == 1
    assert calls == []
    assert stderr == "✗ Required environment variable 'CLOUDFLARE_ACCOUNT_ID' is not set\n".encode()


def test_a_missing_jq_is_refused_even_though_the_port_does_not_use_jq() -> None:
    """`require_cmd jq` IS KEPT IN THE PORT ON PURPOSE. Dropping it would widen the set of hosts the script runs on, which is a cutover decision and not a porting one -- and it would make this case diverge. The port parses JSON
    with `json.loads`; the GUARD is what is being preserved, not the tool."""
    exit_code, _, stderr, calls = _sides("no-jq", [], _drop="jq")
    assert exit_code == 1
    assert calls == []
    assert stderr == b"\xe2\x9c\x97 Required command 'jq' is not available\n"


def test_a_missing_npx_is_refused_after_jq() -> None:
    """The GUARD ORDER is observable: jq is checked first, so a host missing both is told about jq."""
    exit_code, _, stderr, calls = _sides("no-npx", [], _drop="npx")
    assert exit_code == 1
    assert calls == []
    assert stderr == b"\xe2\x9c\x97 Required command 'npx' is not available\n"


def test_an_unreachable_api_is_a_green_exit_on_both_sides() -> None:
    """HAZARD 1, PINNED. `2>/dev/null || true` throws away both the status and the message, so an expired token is indistinguishable from an empty account and the reaper exits 0 having reaped nothing. Both sides do it. This test exists so the day someone makes the failure loud, they have to come here."""
    exit_code, stdout, stderr, calls = _sides(
        "api-down",
        [],
        FAKE_LIST_RC="1",
        FAKE_LIST_SILENT="1",
        FAKE_LIST_STDERR="Authentication error [code: 10000]\n",
    )
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"]
    assert stdout == b""
    text = stderr.decode()
    assert "✓ No D1 databases found (or API unavailable)" in text
    # The real reason never reaches anyone.
    assert "Authentication error" not in text


def test_a_non_json_banner_with_no_array_is_the_same_green_exit() -> None:
    exit_code, _, stderr, calls = _sides(
        "banner-only", [], FAKE_LIST_STDOUT="Fetching account details...\n"
    )
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"]
    assert "✓ No D1 databases found (or API unavailable)" in stderr.decode()


def test_a_banner_before_the_array_is_stripped_and_the_array_is_read() -> None:
    """`sed -n '/^\\[/,$p'` exists for exactly this: wrangler prints chatter before its JSON."""
    exit_code, _, stderr, calls = _sides(
        "banner-then-json",
        [],
        FAKE_LIST_STDOUT=_listing(("prod-db", OLD), banner="⛅️ wrangler 4.0.0\n----------\n"),
    )
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"]
    text = stderr.decode()
    assert "✓ Found 1 total D1 databases" in text
    assert "✓ No stale migration-test databases found" in text


def test_a_database_that_does_not_carry_the_prefix_is_never_touched() -> None:
    exit_code, _, stderr, calls = _sides(
        "prefix", [], FAKE_LIST_STDOUT=_listing(("prod-db", OLD), ("staging", OLD))
    )
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"]
    assert "✓ Found 2 total D1 databases" in stderr.decode()
    assert "✓ No stale migration-test databases found" in stderr.decode()


def test_a_prefixed_database_newer_than_the_cutoff_survives() -> None:
    exit_code, _, stderr, calls = _sides(
        "too-new", [], FAKE_LIST_STDOUT=_listing(("migration-test-fresh", NEW))
    )
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"]
    assert "✓ No stale migration-test databases found" in stderr.decode()


def test_the_real_delete_path_is_one_call_per_stale_database_in_array_order() -> None:
    exit_code, stdout, stderr, calls = _sides(
        "delete",
        [],
        FAKE_LIST_STDOUT=_listing(
            ("migration-test-b", OLD),
            ("prod-db", OLD),
            ("migration-test-a", OLD),
            ("migration-test-fresh", NEW),
        ),
    )
    assert exit_code == 0
    assert calls == [
        "npx\twrangler\td1\tlist\t--json",
        "npx\twrangler\td1\tdelete\tmigration-test-b\t--skip-confirmation",
        "npx\twrangler\td1\tdelete\tmigration-test-a\t--skip-confirmation",
    ], calls
    text = stderr.decode()
    assert "→ Found 2 stale database(s)" in text
    assert "✓ Deleting: migration-test-b" in text
    assert "✓ Deleted 2 of 2 stale databases" in text
    assert "DRY-RUN" not in text
    # `2>/dev/null` covers only stderr, so wrangler's own stdout survives.
    assert stdout == b"Deleted database migration-test-b\nDeleted database migration-test-a\n"


def test_dry_run_lists_and_deletes_nothing() -> None:
    exit_code, stdout, stderr, calls = _sides(
        "dry-run",
        ["--dry-run"],
        FAKE_LIST_STDOUT=_listing(("migration-test-a", OLD), ("migration-test-b", OLD)),
    )
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"], "a --dry-run deleted something"
    assert stdout == b""
    text = stderr.decode()
    assert "⚠ DRY-RUN mode: no deletions will be performed" in text
    assert "⚠ [DRY-RUN] Would delete: migration-test-a" in text
    assert "⚠ [DRY-RUN] Would delete: migration-test-b" in text
    assert "✓ Would delete 2 of 2 stale databases" in text
    assert "Deleted 2 of" not in text


def test_dry_run_still_prints_nothing_extra_when_there_is_nothing_stale() -> None:
    exit_code, _, stderr, calls = _sides(
        "dry-run-empty", ["--dry-run"], FAKE_LIST_STDOUT=_listing(("migration-test-x", NEW))
    )
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"]
    assert "DRY-RUN" not in stderr.decode()


def test_a_failed_delete_is_a_warning_and_the_run_still_exits_zero() -> None:
    """HAZARD 2, PINNED. `log_warn` does not touch `$?`, so the reaper reports success having removed nothing. The count line is at least honest."""
    exit_code, _, stderr, calls = _sides(
        "delete-fails",
        [],
        FAKE_LIST_STDOUT=_listing(("migration-test-a", OLD), ("migration-test-b", OLD)),
        FAKE_DELETE_FAILS="migration-test-a",
    )
    assert exit_code == 0
    assert len(calls) == 3
    text = stderr.decode()
    assert "⚠ Failed to delete: migration-test-a" in text
    assert "✓ Deleted 1 of 2 stale databases" in text
    # `2>/dev/null` on the delete: wrangler's complaint never reaches anyone.
    assert "refusing to delete" not in text


def test_max_age_widens_the_window_and_reaches_the_log_line_verbatim() -> None:
    exit_code, _, stderr, calls = _sides(
        "max-age",
        ["--max-age", "1440"],
        FAKE_LIST_STDOUT=_listing(("migration-test-a", OLD)),
    )
    assert exit_code == 0
    assert len(calls) == 2
    assert "(databases older than 1440m)" in stderr.decode()


def test_an_unparseable_max_age_dies_with_dates_own_status_and_message() -> None:
    """HAZARD 3: `--max-age` is interpolated into `date` unvalidated, and under `set -e` the command substitution takes the run down. The port EXECUTES the same `date` for exactly this reason, so the message is the same binary's."""
    exit_code, _, stderr, calls = _sides(
        "max-age-garbage",
        ["--max-age", "not-a-number"],
        FAKE_LIST_STDOUT=_listing(("migration-test-a", OLD)),
    )
    assert exit_code == 1
    assert calls == ["npx\twrangler\td1\tlist\t--json"], "the cutoff failed after the listing"
    assert "invalid date" in stderr.decode()
    assert "Cutoff:" not in stderr.decode()


def test_a_negative_max_age_reaches_into_the_future_and_selects_everything() -> None:
    """PRESERVED SHAPE, and it is the one that would hurt. `--max-age -30` makes the cutoff THIRTY MINUTES FROM NOW, so a database created seconds ago is "stale". Driven under `--dry-run` so the fixture cannot be read as an endorsement of running it for real."""
    exit_code, _, stderr, _ = _sides(
        "negative",
        ["--dry-run", "--max-age", "-30"],
        FAKE_LIST_STDOUT=_listing(("migration-test-brand-new", NEW)),
    )
    assert exit_code == 0
    # NEW is the year 2099, so even a cutoff half an hour ahead does not reach it; what this pins is that the flag is passed through unvalidated and the two sides agree about the resulting window.
    assert "(databases older than -30m)" in stderr.decode()


def test_the_cutoff_line_is_the_only_clock_dependent_output() -> None:
    """The masking in `_mask_cutoff` is a claim about this subject, so it is checked rather than trusted: with the cutoff line removed, the two sides' stderr must be byte-identical without any masking at all."""
    results = []
    with tempfile.TemporaryDirectory() as td:
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            results.append(
                _run(
                    subject,
                    base,
                    ["--dry-run"],
                    {"FAKE_LIST_STDOUT": _listing(("migration-test-a", OLD))},
                )
            )
    old, new = results
    strip = lambda b: [x for x in b.decode().splitlines() if "Cutoff: " not in x]  # noqa: E731
    assert strip(old[2]) == strip(new[2])
    # And the cutoff line itself is present on both, so the strip is not hiding an absence.
    assert any("Cutoff: " in x for x in old[2].decode().splitlines())
    assert any("Cutoff: " in x for x in new[2].decode().splitlines())


def test_an_empty_array_is_zero_total_and_no_stale() -> None:
    exit_code, _, stderr, calls = _sides("empty-array", [], FAKE_LIST_STDOUT="[]\n")
    assert exit_code == 0
    assert calls == ["npx\twrangler\td1\tlist\t--json"]
    text = stderr.decode()
    assert "✓ Found 0 total D1 databases" in text
    assert "✓ No stale migration-test databases found" in text


def test_a_flag_that_is_not_a_shell_identifier_kills_the_run_on_both_sides() -> None:
    """common.sh QUIRK 3 through `parse_args "$@"`: exit 2, before any guard."""
    results = []
    with tempfile.TemporaryDirectory() as td:
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            results.append(_run(subject, base, ["--max.age=5"], {}))
    old, new = results
    assert old[0] == new[0] == 2
    assert old[3] == new[3] == []
    assert "not a valid identifier" in old[2].decode()
    assert "not a valid identifier" in new[2].decode()
