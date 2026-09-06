r"""The config-migration runner, its file coverage, and its committed fixtures.

Ported from `.ci/scripts/quality/check-config-migrations.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__` for why both copies live and for the
phase-5 decision that retires the twin.

THE TWIN'S OWN HEADER, carried over because the list of catches IS the gate:

  Verify the config-migration runner round-trips every committed fixture
  through runMigrations() + RdcConfigSchema.parse() without error, and
  that every version gap in [1..CURRENT_SCHEMA_VERSION-1] has a
  corresponding v<N>-to-v<N+1>.ts migration file.

  This catches:
    - Dropping a migration without bumping CURRENT_SCHEMA_VERSION
    - Bumping CURRENT_SCHEMA_VERSION without adding the migration file
    - A fixture under tests/fixtures/config/ that no longer parses

  Exit codes: 0 = OK, 1 = problem detected

And the twin's note on WHERE the two halves live, which is the fact a reader
needs before the paths below make sense: "The schema and its migrations live in
packages/shared so the CLI and the executor consume one definition. The fixtures
stay with the CLI, which is the only consumer that loads a config file from
disk."

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE "Could not parse CURRENT_SCHEMA_VERSION" ERROR IS DEAD CODE, and this is the
finding that matters most in this file. The twin writes:

    CURRENT=$(grep -oE 'CURRENT_SCHEMA_VERSION = [0-9]+' "$RUNNER" | grep -oE '[0-9]+$')
    if [[ -z "$CURRENT" ]]; then
        log_error "Could not parse CURRENT_SCHEMA_VERSION from $RUNNER"
        exit 1
    fi

Under `set -euo pipefail` an ASSIGNMENT takes the exit status of its command
substitution, so when the runner carries no such constant both greps exit 1,
pipefail propagates it, and errexit kills the script AT THE ASSIGNMENT. The
`if` beneath it can never run. Measured in this tree:

    set -euo pipefail
    echo "before" >&2
    CURRENT=$(grep -oE 'CURRENT_SCHEMA_VERSION = [0-9]+' runner.ts | grep -oE '[0-9]+$')
    if [[ -z "$CURRENT" ]]; then echo "REACHED THE -z BRANCH" >&2; exit 1; fi
    -> prints only "before", rc=1

So a runner whose constant was renamed produces EXIT 1 WITH NO EXPLANATION: the
step goes red having printed one `log_step` line and nothing else, which is
precisely the invisible-failure shape `check-battery-clean-tree.sh` exists to
gate against. Reproduced exactly -- `main` returns 1 without printing the message
-- because printing it would be a finding the twin never emits, and reported.

THE MULTI-DECLARATION CASE IS THE ONE SHAPE THE TWO SIDES' STDERR DIFFERS ON, and
it is stated here rather than discovered later. Two `CURRENT_SCHEMA_VERSION = N`
lines make `$CURRENT` a two-line string; bash then fails the arithmetic `for`
with its own interpreter diagnostic and CONTINUES:

    m.sh: line 4: ((: 3
    5: arithmetic syntax error in expression (error token is "5")
    survived, rc=0

The port skips the coverage loop for the same input and prints nothing. The
diagnostic carries a script path and a line number that no port could reproduce,
and `scripts/lib/shadow-gate.ts` classifies it as CHATTER rather than a finding,
so the two sides still agree on the verdict and on the finding set. The shape is
also unreachable in valid TypeScript, where a duplicate `const` does not compile.
Named as a divergence rather than hidden.

`grep -oE '[0-9]+$'` TAKES THE TRAILING DIGITS OF THE FIRST GREP'S OUTPUT, not of
the source line, so `CURRENT_SCHEMA_VERSION = 4;` yields `4` and not `4;`. The
two-stage pipeline is reproduced as two stages for that reason: a single regex
over the file would have to re-derive the anchoring by hand.

THE TEMPORARY TSX SCRIPT IS WRITTEN INTO THE REPOSITORY, NOT INTO A TEMPDIR.
`$REPO_ROOT/packages/cli/.config-migrations-check.tmp.ts` exists for the duration
of the run, which makes the working tree DIRTY while the gate is executing. A
`trap ... EXIT` removes it, so the window is short, but any concurrent
clean-tree check sees it and the file survives a `kill -9`. Carried unchanged --
the path is what the generated script's relative `src/__tests__/fixtures/config`
is resolved against -- and reported.

`2>&1` MERGES THE ROUND-TRIP'S STREAMS. `result=$(cd ... && npx ... 2>&1)` is the
merge this repo warns about everywhere else, and here it is load-bearing: the tsx
script prints its PASS lines on stdout and its FAIL lines on stderr, and the twin
re-emits every captured line through ONE logger chosen by the exit code. So a
PASS line from a partially failing run is re-printed as a `log_error`. Preserved,
because splitting the streams would change which lines carry which marker, and
the marker is what the differential compares.

A MISSING FIXTURES DIRECTORY, AND AN EMPTY ONE, ARE WARNINGS AND NOT FAILURES.
`log_warn ... (skipping round-trip)` then carry on to the exit-0 path. That is a
vacuity hole in the twin: delete every fixture and the gate reports success
having round-tripped nothing. It is preserved because closing it would change the
verdict, and reported. Note that the warning is still VISIBLE -- `log_warn` emits
a `⚠` line that the comparator classifies as a finding -- so the debt is not
silent, which is the only thing that makes carrying it defensible.

`npx --no-install` IS DELIBERATE ON BOTH SIDES. It refuses to reach the network
for a missing `tsx` and fails loudly instead, which is what turns "the toolchain
is not installed" into a red rather than into a silent download in CI.
"""

import contextlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# Where the two halves live. See the twin's note, carried in the docstring.
MIGRATIONS_REL = "packages/shared/src/config-schema/migrations"
FIXTURES_REL = "packages/cli/src/__tests__/fixtures/config"
RUNNER_NAME = "index.ts"

# The two-stage pipeline, as two stages. See the port notes for why.
VERSION_RE = re.compile(r"CURRENT_SCHEMA_VERSION = [0-9]+")
TRAILING_DIGITS_RE = re.compile(r"[0-9]+$")

# `find "$FIXTURES_DIR" -maxdepth 1 -name 'v*-sample.json'`, as a glob. maxdepth 1
# means the directory itself and its immediate children, and a directory cannot
# match the name pattern, so this is exactly the non-recursive glob.
FIXTURE_GLOB = "v*-sample.json"

# The scratch file the round-trip runs from. INSIDE packages/cli, because the
# generated script resolves `src/__tests__/fixtures/config` relative to its own
# working directory. See the port notes for the dirty-tree consequence.
TMP_SCRIPT_NAME = ".config-migrations-check.tmp.ts"

# The generated tsx program, byte for byte from the twin's quoted heredoc. It is
# a QUOTED heredoc (`<<'TSX'`), so nothing in it is expanded by the shell and
# nothing here is interpolated either.
TSX_SOURCE = """import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { runMigrations, RdcConfigSchema } from '@rediacc/shared/config-schema';

const fixturesDir = 'src/__tests__/fixtures/config';
const fixtures = readdirSync(fixturesDir).filter((f) => /^v\\d+-sample\\.json$/.test(f));

// Committed fixtures are plaintext; a fixture needing a master password (an
// encrypted-blob v2 config) cannot be gate-checked without one and is covered
// in vitest instead, so both crypto hooks throw here.
const ctx = {
  getMasterPassword: async () => {
    throw new Error('gate fixtures must be plaintext (no /resources blob)');
  },
  decryptLegacyBlob: async () => {
    throw new Error('gate fixtures must be plaintext (no /resources blob)');
  },
};

async function main() {
  let failed = 0;
  for (const f of fixtures) {
    const raw = JSON.parse(readFileSync(join(fixturesDir, f), 'utf8'));
    try {
      const migrated = await runMigrations(raw, ctx);
      const parsed = RdcConfigSchema.safeParse(migrated.config);
      if (!parsed.success) {
        console.error(`FAIL ${f}: ${JSON.stringify(parsed.error.issues)}`);
        failed++;
        continue;
      }
      console.log(`PASS ${f} (from=${migrated.fromVersion}, to=${migrated.toVersion}, \
migrated=${migrated.migrated})`);
    } catch (err) {
      console.error(`FAIL ${f}: ${(err as Error).message}`);
      failed++;
    }
  }
  process.exit(failed > 0 ? 1 : 0);
}

void main();
"""


def parse_current_version(text: str) -> str | None:
    """`grep -oE 'CURRENT_SCHEMA_VERSION = [0-9]+' | grep -oE '[0-9]+$'`.

    Returns the version STRING, or None when the constant is absent -- which the
    twin turns into a silent exit 1, not into the error message written beneath
    it. See the port notes.

    A LIST WOULD BE MORE HONEST AND WOULD BE WRONG. `$(...)` joins multiple
    matches with newlines and the twin then feeds that whole string to bash
    arithmetic, so the multi-match case is not "the first one wins"; it is an
    arithmetic error. `current_versions` below exposes the list for the caller
    that has to decide.
    """
    versions = current_versions(text)
    if len(versions) != 1:
        return None
    return versions[0]


def current_versions(text: str) -> list[str]:
    """Every `CURRENT_SCHEMA_VERSION = N` in source order, as the digits alone.

    Separated from `parse_current_version` so the multi-declaration case is
    VISIBLE to a caller rather than silently collapsing to the first match, which
    is what a naive `re.search(...).group()` would do and is not what the shell
    does.
    """
    matches = (TRAILING_DIGITS_RE.search(m.group(0)) for m in VERSION_RE.finditer(text))
    return [m.group(0) for m in matches if m]


def missing_migrations(migrations_dir: pathlib.Path, current: int) -> list[int]:
    """Every `v` in [1, current) with no `v<v>-to-v<v+1>.ts` beside it.

    Returns the version numbers rather than the filenames, because the caller
    prints BOTH the missing name and the directory it should go in and would
    otherwise have to take the name apart again.
    """
    return [
        v
        for v in range(1, current)
        if not (migrations_dir / ("v%d-to-v%d.ts" % (v, v + 1))).is_file()
    ]


def fixture_files(fixtures_dir: pathlib.Path) -> list[str]:
    """`find <dir> -maxdepth 1 -name 'v*-sample.json' | sort`, as full paths.

    Sorted by BYTES, not by locale: the differential harness pins LC_ALL=C so
    `sort` is byte order, and encoding the key makes that explicit rather than
    true by accident on an ASCII-only corpus.
    """
    if not fixtures_dir.is_dir():
        return []
    found = [str(p) for p in fixtures_dir.glob(FIXTURE_GLOB)]
    return sorted(found, key=lambda p: p.encode("utf-8", "surrogateescape"))


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 OK, 1 problem detected.

    `--selftest` is intercepted BEFORE any real scan. The twin takes no arguments
    at all, so no caller can be passing this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    repo_root = paths.repo_root()
    migrations_dir = repo_root / MIGRATIONS_REL
    fixtures_dir = repo_root / FIXTURES_REL
    runner = migrations_dir / RUNNER_NAME

    errors = 0

    log.step("Checking migration runner exists...")
    if not runner.is_file():
        log.error("Migration runner missing: %s" % runner)
        return 1

    # Extract CURRENT_SCHEMA_VERSION from the runner.
    versions = current_versions(runner.read_text(encoding="utf-8", errors="replace"))
    if not versions:
        # SILENT EXIT 1. The twin's `log_error "Could not parse ..."` is
        # unreachable: errexit kills the assignment before the `if`. See the port
        # notes for the measurement. Reproduced rather than repaired.
        return 1
    # Bash fails the arithmetic `for` with its own diagnostic and carries on with
    # the loop body never having run, so more than one declaration means NO coverage
    # loop at all. See the port notes for why the diagnostic itself is not reproduced.
    current = None if len(versions) > 1 else int(versions[0])

    log.info("CURRENT_SCHEMA_VERSION = %s" % "\n".join(versions))

    log.step("Checking migration file coverage...")
    if current is not None:
        for v in range(1, current):
            nxt = v + 1
            if not (migrations_dir / ("v%d-to-v%d.ts" % (v, nxt))).is_file():
                log.error("Missing migration file: v%d-to-v%d.ts" % (v, nxt))
                log.error(
                    "Either add it under %s/, or roll back the CURRENT_SCHEMA_VERSION bump."
                    % migrations_dir
                )
                errors += 1
            else:
                log.info("  ✓ v%d-to-v%d.ts present" % (v, nxt))

    log.step("Round-tripping committed fixtures...")
    if not fixtures_dir.is_dir():
        log.warn("Fixtures dir not found: %s (skipping round-trip)" % fixtures_dir)
    else:
        fixtures = fixture_files(fixtures_dir)
        if not fixtures:
            log.warn("No v*-sample.json fixtures in %s (skipping round-trip)" % fixtures_dir)
        else:
            # Use a tsx script to run the actual TypeScript runner -- keeps the
            # check from re-implementing migration logic.
            cli_dir = repo_root / "packages" / "cli"
            tmp_script = cli_dir / TMP_SCRIPT_NAME
            try:
                tmp_script.write_text(TSX_SOURCE, encoding="utf-8")
                proc = subprocess.run(
                    ["npx", "--no-install", "tsx", tmp_script.name],
                    cwd=str(cli_dir),
                    stdout=subprocess.PIPE,
                    # `2>&1`, inside the child. See the port notes: the merge is
                    # load-bearing here rather than accidental.
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                )
                # `result=$(...)` strips trailing newlines and nothing else.
                result = (proc.stdout or "").rstrip("\n")
                if proc.returncode != 0:
                    log.error("Fixture round-trip failed:")
                    for line in result.split("\n"):
                        log.error("  %s" % line)
                    errors += 1
                else:
                    for line in result.split("\n"):
                        log.info("  %s" % line)
            finally:
                # `trap 'rm -f "$tmpscript"' EXIT`. A `finally` rather than an
                # atexit hook, so the file is gone before the caller sees the
                # verdict and a crash in the reporting below cannot leave it.
                with contextlib.suppress(OSError):
                    tmp_script.unlink()

    if errors > 0:
        log.error("")
        log.error("Config-migrations check failed with %d error(s)" % errors)
        return 1

    log.info("Config-migrations check passed")
    return 0


def _seed(root: pathlib.Path, current: int, migrations: tuple[int, ...]) -> None:
    """A tree whose runner declares `current` and carries `migrations` files."""
    mig = root / MIGRATIONS_REL
    mig.mkdir(parents=True, exist_ok=True)
    (mig / RUNNER_NAME).write_text(
        "export const CURRENT_SCHEMA_VERSION = %d;\n" % current, encoding="utf-8"
    )
    for v in migrations:
        (mig / ("v%d-to-v%d.ts" % (v, v + 1))).write_text("export default {};\n", encoding="utf-8")
    (root / "packages" / "cli").mkdir(parents=True, exist_ok=True)


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    BOTH DIRECTIONS FOR EVERY CONTROL. A gate with only positive plants will
    happily flag a correct tree, and the mirrors below are the half that proves
    it does not.

    THE ROUND-TRIP IS NOT DRIVEN HERE. It needs `npx`, `tsx` and a built
    `@rediacc/shared`, none of which a self-test may depend on: a control that
    cannot run on a fresh checkout is a control that gets deleted. The fixtures
    directory is left absent or empty in every case below, which takes the two
    WARNING paths, and the round-trip proper is covered by the committed ledger
    `.ci/shadow/w7p2-config-migrations.observations.jsonl` against a stubbed npx.
    """
    ctl = Controls("config-migrations", floor=24, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "tree"

        def run() -> int:
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved

        def fresh(current: int = 3, migrations: tuple[int, ...] = (1, 2)) -> pathlib.Path:
            shutil.rmtree(root, ignore_errors=True)
            root.mkdir(parents=True)
            _seed(root, current, migrations)
            return root

        fresh()
        ctl.check("CONTROL: a complete migration chain passes", run(), 0)

        # VACUITY: no runner at all is a refusal with a message, not a pass.
        r = fresh()
        (r / MIGRATIONS_REL / RUNNER_NAME).unlink()
        ctl.check("VACUITY: a missing runner is refused", run(), 1)

        # THE DEAD-CODE PATH. A runner with no constant exits 1 and says NOTHING.
        # Asserted as a named control so the silence is a decision on the record.
        r = fresh()
        (r / MIGRATIONS_REL / RUNNER_NAME).write_text("export const OTHER = 3;\n", encoding="utf-8")
        ctl.check("PRESERVED DEFECT: an unparseable version exits 1 SILENTLY", run(), 1)

        # PLANT: a gap in the chain, in each position.
        r = fresh(current=3, migrations=(2,))
        ctl.check("PLANT: a missing v1-to-v2 is caught", run(), 1)
        r = fresh(current=3, migrations=(1,))
        ctl.check("PLANT: a missing v2-to-v3 is caught", run(), 1)
        r = fresh(current=4, migrations=(1, 3))
        ctl.check("PLANT: a gap in the middle is caught", run(), 1)
        r = fresh(current=4, migrations=())
        ctl.check("PLANT: three missing files are caught", run(), 1)

        # MIRROR: version 1 needs NO migration files at all, so the loop being
        # empty is a PASS and not a vacuity hole. This is the boundary the range
        # gets wrong if someone writes `range(1, current + 1)`.
        r = fresh(current=1, migrations=())
        ctl.check("MIRROR: CURRENT=1 needs no migrations and passes", run(), 0)
        r = fresh(current=2, migrations=(1,))
        ctl.check("MIRROR: CURRENT=2 needs exactly v1-to-v2", run(), 0)

        # MIRROR: an EXTRA migration beyond the current version is not a finding.
        # The gate checks coverage, not tidiness.
        r = fresh(current=3, migrations=(1, 2, 3, 4))
        ctl.check("MIRROR: migrations beyond CURRENT are not reported", run(), 0)

        # -- the pure helpers, driven directly ----------------------------
        ctl.check(
            "parse: the trailing digits come off the MATCH, not the line",
            current_versions("export const CURRENT_SCHEMA_VERSION = 4;\n"),
            ["4"],
        )
        ctl.check(
            "parse: a multi-digit version survives",
            current_versions("CURRENT_SCHEMA_VERSION = 42\n"),
            ["42"],
        )
        ctl.check(
            "parse: the spacing is EXACT -- one space either side of the `=`",
            current_versions("CURRENT_SCHEMA_VERSION=4\n"),
            [],
        )
        ctl.check(
            "parse: two spaces after the `=` do not match either",
            current_versions("CURRENT_SCHEMA_VERSION =  4\n"),
            [],
        )
        ctl.check(
            "parse: a comment mentioning it IS matched -- there is no filter",
            current_versions("// CURRENT_SCHEMA_VERSION = 9\n"),
            ["9"],
        )
        ctl.check(
            "parse: two declarations are both returned, and collapse to None",
            (
                current_versions("CURRENT_SCHEMA_VERSION = 3\nCURRENT_SCHEMA_VERSION = 5\n"),
                parse_current_version("CURRENT_SCHEMA_VERSION = 3\nCURRENT_SCHEMA_VERSION = 5\n"),
            ),
            (["3", "5"], None),
        )
        ctl.check("parse: nothing at all is None", parse_current_version("nope\n"), None)

        r = fresh(current=5, migrations=(1, 3))
        ctl.check(
            "coverage: the missing versions are named, in order",
            missing_migrations(r / MIGRATIONS_REL, 5),
            [2, 4],
        )
        ctl.check(
            "coverage: CURRENT=1 asks for nothing",
            missing_migrations(r / MIGRATIONS_REL, 1),
            [],
        )

        # -- the fixture lister -------------------------------------------
        fx = r / FIXTURES_REL
        fx.mkdir(parents=True, exist_ok=True)
        ctl.check("fixtures: an EMPTY directory lists nothing", fixture_files(fx), [])
        ctl.check("fixtures: an ABSENT directory lists nothing", fixture_files(fx / "nope"), [])
        (fx / "v2-sample.json").write_text("{}", encoding="utf-8")
        (fx / "v10-sample.json").write_text("{}", encoding="utf-8")
        (fx / "v1-sample.json").write_text("{}", encoding="utf-8")
        (fx / "notes.md").write_text("x", encoding="utf-8")
        (fx / "sample.json").write_text("{}", encoding="utf-8")
        # BYTE ORDER, MEASURED AGAINST `LC_ALL=C find | sort`, NOT GUESSED. `-`
        # is 0x2D and `0` is 0x30, so `v1-sample.json` sorts BEFORE
        # `v10-sample.json`, which in turn sorts before `v2-sample.json`. This
        # assertion was written the other way round on the first draft and the
        # control caught it, which is the whole reason a numeric-looking sort
        # gets a named case rather than a comment.
        ctl.check(
            "fixtures: only v*-sample.json, in byte order, so v1- precedes v10- precedes v2-",
            [pathlib.Path(p).name for p in fixture_files(fx)],
            ["v1-sample.json", "v10-sample.json", "v2-sample.json"],
        )
        sub = fx / "nested"
        sub.mkdir(exist_ok=True)
        (sub / "v3-sample.json").write_text("{}", encoding="utf-8")
        ctl.check(
            "fixtures: -maxdepth 1 means a nested fixture is NOT round-tripped",
            len(fixture_files(fx)),
            3,
        )

        # THE VACUITY HOLE, named so it cannot be mistaken for a passing tree: a
        # complete chain with NO fixtures at all still exits 0, having
        # round-tripped nothing. The warning is visible, which is the only thing
        # that makes carrying this defensible.
        r = fresh()
        (r / FIXTURES_REL).mkdir(parents=True, exist_ok=True)
        ctl.check("PRESERVED DEFECT: zero fixtures is a WARNING, not a failure", run(), 0)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
