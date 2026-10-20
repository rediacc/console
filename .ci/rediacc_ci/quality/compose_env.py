"""Every docker-compose env var must be PERSISTED, not merely exported once.

Ported from `.ci/scripts/quality/check-compose-env.sh`, retired in W7 P5;
see `rediacc_ci.quality.__init__` for the phase-5 decision that retired the twin.

THE BUG CLASS, from the twin's header. This "prevents silent failures when env vars are added to docker-compose.yml but not exported in ci-env.sh (or its .env / GITHUB_ENV blocks). This catches the class of bugs where a new variable works on first docker compose invocation (same shell) but breaks on subsequent invocations (new shell) because the variable isn't persisted."

That is the whole subtlety, and it explains why the gate reads ONE TABLE rather than every assignment: a variable the CI environment merely sets is present for the rest of THAT process and gone in the next workflow step. Only the names in `PERSISTED`, which `rediacc_ci.infra.ci_env` writes to the `.env` file and to `$GITHUB_ENV`, survive a step boundary. A gate that accepted any
name the module mentions would pass the exact configuration this one exists to catch.

THE PERSISTED SET IS `ci_env.PERSISTED`, READ AS SOURCE (W7P5-c). Until the sourced-only `ci-env.sh` was deleted, this gate parsed that file's `<<ENVBLOCK` heredoc with a `sed` range. The port of that file, `.ci/rediacc_ci/infra/ci_env.py`, carries the same block as the `PERSISTED` tuple (pinned to the twin's frozen heredoc by `test_infra_ci_env.py`), and this gate reads the tuple's first elements with `ast` from the file under the root it is pointed at. It does NOT import the module: an import would read the checkout `rediacc_ci` was loaded from, so a fixture root (`$REDIACC_CI_ROOT`, the selftest's plants) could never change the answer and every plant would pass. A name in any OTHER table of that file (`SYSTEM_DEFAULTS`, `MASKED`) does not count, which is the same near miss the heredoc range guarded against.

WHAT COUNTS AS SAFE. A reference with a NON-EMPTY default, `${ENABLE_HTTPS:-false}`,
needs no persistence: "Vars with non-empty defaults (e.g., ${ENABLE_HTTPS:-false})
are safe even if not in ci-env.sh -- they won't cause failures or container recreation."

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE SECOND FILTER IN THE SAFE-DEFAULT PIPELINE CANNOT MATCH, AND IS CARRIED
ANYWAY. The twin extracts safe defaults with

    grep -ohP '\\$\\{[A-Z0-9_]+:-[^}]+\\}'  |  grep -vP ':-\\}$'  |  grep -oP ...

and the middle filter is meant to drop `${VAR:-}`, an EMPTY default, which is
not safe. It can never fire: `[^}]+` requires at least one non-`}` character
before the closing brace, so `${VAR:-}` never matches the first pattern in the
first place and never reaches the filter. The filter is reproduced here as a predicate over the same matched text rather than dropped, for the reason `www_build_token.py` gives for its own dead filter: removing a line a port judged useless is how the next reader comes to believe the original never tried. It is reported as a finding instead of silently repaired.

AND IT IS DORMANT RATHER THAN WRONG, WHICH WAS MEASURED, NOT ASSUMED. Planting a
control for the shadow differential on 2026-09-06 by loosening `[^}]+` to
`[^}]*` produced NO divergence at all: the loosened pattern matched
`${EMPTY_DEFAULTED:-}`, the "dead" filter then dropped it exactly as written,
and both sides agreed. Only removing BOTH made the port blind (verdict
NEW_SIDE_TRUE, the finding `docker-compose references ${EMPTY_DEFAULTED} (no
safe default)` lost). So the filter is the only thing standing behind that `+`, and a reader who deletes "the dead line" has removed the guard rather than dead code. `selftest` pins both halves of that observation.

THE NESTED-DEFAULT CASE IS REAL AND SURPRISING. `${FOO:-${BAR}}` matches the
first pattern as `${FOO:-${BAR}` and the final `grep -oP '(?<=\\$\\{)[A-Z0-9_]+'`
then extracts BOTH `FOO` and `BAR`, so an inner variable used only as a default is recorded as having a safe default itself. That is the twin's behaviour, it is reproduced exactly, and it is why the extraction runs over the MATCHED TEXT rather than over the variable name the outer pattern captured.

A MISSING ci_env.py, OR ONE WITHOUT A LITERAL `PERSISTED` TABLE, IS A REFUSAL NAMING THE FILE. The bash-era gate printed `sed`'s complaint and then reported every compose variable as unpersisted, which was red for a reason one line away from the true one. Reading an empty persisted set now fails on its own line first, so the reader is told the table could not be read rather than that nine variables were forgotten.

BOTH `\\u2014` CHARACTERS THE TWIN EMITS ARE WRITTEN AS ESCAPES HERE. The twin's "No env var references found in compose files \\u2014 check parse logic" carries an em dash, which the house rule forbids in authored text while the differential requires the port to emit the same bytes. The escape satisfies both. The em dash in the twin is a finding reported rather than repaired,
because editing the twin is what invariant 5 forbids.

THE ANTI-VACUITY REFUSAL IS ALREADY THERE, and it is the reason this gate is worth porting carefully: zero compose vars is a FAILURE, not a pass, and the success line prints the count so a reader can see the day it collapses. Both are carried unchanged.
"""

import ast
import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls, plant

# The two subjects, relative to the repository root.
CI_ENV_SUBPATH = ".ci/rediacc_ci/infra/ci_env.py"
# The module-level table in that file whose first elements are the persisted names.
PERSISTED_NAME = "PERSISTED"
COMPOSE_SUBDIR = ".ci/docker/ci"
COMPOSE_GLOB = "docker-compose*.yml"

# `grep -ohP '\$\{[A-Z0-9_]+'`: every reference, opening brace included, with no
# requirement that it be closed. A `${FOO` with no `}` is a reference as far as
# this gate is concerned, which is deliberate: it is still a thing compose will
# try to expand.
REFERENCE_RE = re.compile(r"\$\{[A-Z0-9_]+")

# `grep -ohP '\$\{[A-Z0-9_]+:-[^}]+\}'`: a reference WITH a non-empty default.
SAFE_DEFAULT_RE = re.compile(r"\$\{[A-Z0-9_]+:-[^}]+\}")

# `grep -vP ':-\}$'`: the filter that cannot fire. See the port notes.
EMPTY_DEFAULT_RE = re.compile(r":-\}$")

# `grep -oP '(?<=\$\{)[A-Z0-9_]+'`: every name that follows a `${`, applied to
# the MATCHED TEXT, which is what picks up a nested default's inner name.
NAME_AFTER_BRACE_RE = re.compile(r"(?<=\$\{)[A-Z0-9_]+")

# The em dash the twin emits, as an escape. See the port notes.
PARSE_LOGIC_ERROR = "No env var references found in compose files \u2014 check parse logic"


def compose_files(compose_dir: pathlib.Path) -> list[pathlib.Path]:
    """`<dir>/docker-compose*.yml`, byte-sorted, as bash expands it.

    An EMPTY result is returned as an empty list rather than as the literal pattern, and here that is faithful rather than a divergence: the twin passes the unexpanded pattern to `grep`, whose complaint is swallowed by `2>/dev/null` and which then produces no output. Empty list, same outcome, and the caller's refusal is what turns it into a verdict.
    """
    if not compose_dir.is_dir():
        return []
    return sorted(compose_dir.glob(COMPOSE_GLOB), key=lambda p: str(p).encode())


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def referenced_vars(files: list[pathlib.Path]) -> list[str]:
    """Every `${VAR` reference across the compose files, sorted and unique."""
    names: set[str] = set()
    for path in files:
        for match in REFERENCE_RE.findall(_read(path)):
            names.add(match[2:])  # drop the leading `${`, which `sed 's/\${//'` does
    return sorted(names, key=str.encode)


def safe_default_vars(files: list[pathlib.Path]) -> list[str]:
    """Every name reachable through a NON-EMPTY default, sorted and unique.

    "Reachable through" rather than "given" because of the nested-default case
    in the port notes: `${FOO:-${BAR}}` puts both names in this set.
    """
    names: set[str] = set()
    for path in files:
        for match in SAFE_DEFAULT_RE.findall(_read(path)):
            # The dead filter, carried. It has never removed anything.
            if EMPTY_DEFAULT_RE.search(match):
                continue
            names.update(NAME_AFTER_BRACE_RE.findall(match))
    return sorted(names, key=str.encode)


class PersistedUnreadableError(Exception):
    """The persisted table could not be read: the file is missing, does not parse, or holds no literal `PERSISTED` tuple."""


def persisted_vars(ci_env: pathlib.Path) -> list[str]:
    """The first element of every entry of the module-level `PERSISTED` tuple in `ci_env`, sorted and unique.

    Read with `ast`, never imported; see the module docstring for why an import would make every plant pass. Each entry must be a literal `("NAME", <default>)` tuple whose first element is a string; anything else is refused rather than skipped, because a skipped entry is a persisted name this gate silently stopped seeing.
    """
    if not ci_env.is_file():
        raise PersistedUnreadableError("%s does not exist" % ci_env)
    try:
        tree = ast.parse(_read(ci_env), filename=str(ci_env))
    except SyntaxError as exc:
        raise PersistedUnreadableError("%s does not parse: %s" % (ci_env, exc)) from None
    value: ast.expr | None = None
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == PERSISTED_NAME
        ) or (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == PERSISTED_NAME for t in node.targets)
        ):
            value = node.value
    if not isinstance(value, ast.Tuple):
        raise PersistedUnreadableError(
            "%s has no module-level `%s = (...)` tuple" % (ci_env, PERSISTED_NAME)
        )
    names: set[str] = set()
    for entry in value.elts:
        if (
            not isinstance(entry, ast.Tuple)
            or not entry.elts
            or not isinstance(entry.elts[0], ast.Constant)
            or not isinstance(entry.elts[0].value, str)
        ):
            raise PersistedUnreadableError(
                '%s:%d: a `%s` entry is not a literal ("NAME", default) tuple'
                % (ci_env, getattr(entry, "lineno", 0), PERSISTED_NAME)
            )
        names.add(entry.elts[0].value)
    return sorted(names, key=str.encode)


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 violation."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    ci_env = root / CI_ENV_SUBPATH
    compose_dir = root / COMPOSE_SUBDIR

    log.step("Checking docker-compose env var completeness...")

    errors = 0

    files = compose_files(compose_dir)
    compose_vars = referenced_vars(files)

    # ZERO INPUTS IS A FAILURE, NEVER A PASS. A parse that finds no references at all is a broken parse or a moved directory; either way its green would mean nothing, and the twin says so in the message rather than in a comment.
    if not compose_vars:
        log.error(PARSE_LOGIC_ERROR)
        return 1

    safe = set(safe_default_vars(files))
    try:
        persisted = set(persisted_vars(ci_env))
    except PersistedUnreadableError as exc:
        log.error("cannot read the persisted set: %s" % exc)
        print("  Every compose variable would read as unpersisted, so no verdict is reported.")
        print("  Fix: restore the `%s` tuple in %s" % (PERSISTED_NAME, CI_ENV_SUBPATH))
        return 1

    log.step("Checking compose vars without safe defaults are persisted by ci_env.py...")
    for var in compose_vars:
        if var in safe:
            continue
        if var in persisted:
            continue
        log.error(
            "docker-compose references ${%s} (no safe default) but ci_env.py does not "
            "persist it" % var
        )
        # STDOUT, as in the twin: these two are bare `echo`, not log_error, so they land on the data stream while the finding lands on stderr.
        print(
            "  This variable will be empty in every workflow step after the one that set up the CI environment"
        )
        print(
            "  Fix: Add it to %s in %s (it is written to the .env file AND to GITHUB_ENV)"
            % (PERSISTED_NAME, CI_ENV_SUBPATH)
        )
        errors += 1

    if errors > 0:
        print()
        log.error("Found %d compose env var issue(s)" % errors)
        print("See: %s (%s)" % (CI_ENV_SUBPATH, PERSISTED_NAME))
        return 1

    # THE SHAPE, NOT JUST THE VERDICT: the count is in the success line so a reader notices the day the parse collapses from 9 to 1.
    log.info(
        "All compose env vars are properly defined (%d vars checked, %d persisted by %s)"
        % (len(compose_vars), len(persisted), CI_ENV_SUBPATH)
    )
    return 0


# The smallest pair that exercises every branch: one variable persisted, one with a safe default, one with an EMPTY default (which is not safe).
_COMPOSE = """services:
  app:
    image: x
    environment:
      A: ${PERSISTED_ONE}
      B: ${DEFAULTED_ONE:-false}
      C: ${EMPTY_DEFAULTED:-}
"""

# A `ci_env.py` in miniature: the persisted table, plus two decoy tables whose names must NOT count.
_CI_ENV = """SYSTEM_DEFAULTS = (
    ("NOT_PERSISTED_AT_ALL", "1"),
)
PERSISTED: tuple[tuple[str, str | None], ...] = (
    ("PERSISTED_ONE", None),
    ("EMPTY_DEFAULTED", ""),
)
MASKED = ("OUTSIDE_THE_BLOCK",)
"""


def selftest() -> int:
    """Plant an unpersisted variable, prove it reds; persist it, prove it greens."""
    ctl = Controls("compose-env", floor=18, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        def build(compose: str | None, ci_env: str | None) -> pathlib.Path:
            root = base / "root"
            compose_dir = root / COMPOSE_SUBDIR
            compose_dir.mkdir(parents=True, exist_ok=True)
            target = compose_dir / "docker-compose.yml"
            if compose is None:
                if target.exists():
                    target.unlink()
            else:
                target.write_text(compose, encoding="utf-8")
            env_path = root / CI_ENV_SUBPATH
            env_path.parent.mkdir(parents=True, exist_ok=True)
            if ci_env is None:
                if env_path.exists():
                    env_path.unlink()
            else:
                env_path.write_text(ci_env, encoding="utf-8")
            return root

        def run(compose: str | None, ci_env: str | None) -> int:
            root = build(compose, ci_env)
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved

        # -- THE PARSERS, asserted directly ------------------------------------
        root = build(_COMPOSE, _CI_ENV)
        files = compose_files(root / COMPOSE_SUBDIR)
        ctl.check("PARSE: one compose file is found", len(files), 1)
        ctl.check(
            "PARSE: every reference is extracted",
            referenced_vars(files),
            ["DEFAULTED_ONE", "EMPTY_DEFAULTED", "PERSISTED_ONE"],
        )
        # THE EMPTY DEFAULT IS NOT SAFE, which is the distinction the dead filter was written for and which the FIRST pattern already enforces.
        ctl.check(
            "PARSE: only the non-empty default counts as safe",
            safe_default_vars(files),
            ["DEFAULTED_ONE"],
        )
        ctl.check(
            "PARSE: only the names in the PERSISTED table are persisted",
            persisted_vars(root / CI_ENV_SUBPATH),
            ["EMPTY_DEFAULTED", "PERSISTED_ONE"],
        )
        # ITS MIRROR: the names in the two decoy tables must be absent, or the gate is reading the whole file and would accept a name that is merely set.
        found = persisted_vars(root / CI_ENV_SUBPATH)
        ctl.falsy(
            "PARSE MIRROR: a name in a table above PERSISTED is not persisted",
            "NOT_PERSISTED_AT_ALL" in found,
        )
        ctl.falsy(
            "PARSE MIRROR: a name in a table below PERSISTED is not persisted",
            "OUTSIDE_THE_BLOCK" in found,
        )

        # THE FILTER IS DORMANT, NOT DEAD, and this is the control that measured it. With the pattern loosened by one character the filter DOES fire, which is what makes deleting it a behaviour change rather than a cleanup. Asserted against the same two constants the gate uses, so it cannot drift away from them.
        loose = re.compile(SAFE_DEFAULT_RE.pattern.replace("[^}]+", "[^}]*"))
        empty_ref = "x: ${EMPTY_DEFAULTED:-}\n"
        ctl.check(
            "DORMANT: the shipped pattern never reaches the filter",
            SAFE_DEFAULT_RE.findall(empty_ref),
            [],
        )
        ctl.check(
            "DORMANT: loosened by one character, the filter is what catches it",
            [m for m in loose.findall(empty_ref) if EMPTY_DEFAULT_RE.search(m)],
            ["${EMPTY_DEFAULTED:-}"],
        )

        # THE NESTED DEFAULT, pinned. `${FOO:-${BAR}}` marks BOTH names safe.
        nested_files = compose_files(build("x: ${FOO:-${BAR}}\n", _CI_ENV) / COMPOSE_SUBDIR)
        ctl.check(
            "DEFECT PINNED: a nested default marks the inner name safe too",
            safe_default_vars(nested_files),
            ["BAR", "FOO"],
        )

        # -- THE VERDICT -------------------------------------------------------
        ctl.check("CONTROL: a fully persisted compose passes", run(_COMPOSE, _CI_ENV), 0)

        # THE PLANT: drop the variable from PERSISTED while leaving the reference. Exactly the shape the gate exists for.
        persisted_one = '    ("PERSISTED_ONE", None),\n'
        unpersisted = plant(_CI_ENV, persisted_one, "")
        ctl.check("PLANT: an unpersisted reference is caught", run(_COMPOSE, unpersisted), 1)

        # AND THE NEAR MISS: the same name moved into ANOTHER table. The CI environment sets it, it works in that step, and it is gone in the next. A gate that read every string in the file would pass this.
        set_only = plant(
            plant(_CI_ENV, persisted_one, ""),
            '    ("NOT_PERSISTED_AT_ALL", "1"),\n',
            '    ("NOT_PERSISTED_AT_ALL", "1"),\n    ("PERSISTED_ONE", "x"),\n',
        )
        ctl.check(
            "PLANT: a name in another table does not count",
            run(_COMPOSE, set_only),
            1,
        )

        # THE MIRROR a reviewer waves through: a variable with a safe default needs no persistence at all and must NOT be reported.
        only_defaulted = "services:\n  app:\n    environment:\n      B: ${DEFAULTED_ONE:-false}\n"
        ctl.check("MIRROR: a safe default needs no persistence", run(only_defaulted, _CI_ENV), 0)

        # ...and its opposite: an EMPTY default is not a safe default.
        only_empty = "services:\n  app:\n    environment:\n      C: ${NOT_ANYWHERE:-}\n"
        ctl.check("PLANT: an empty default is not safe", run(only_empty, _CI_ENV), 1)

        # -- THE REFUSALS ------------------------------------------------------
        # Zero references is a FAILURE. A compose file with no `${` at all, and
        # no compose file whatsoever, are the two ways the parse collapses.
        ctl.check(
            "VACUITY: a compose file with no references is refused",
            run("services:\n  app:\n    image: x\n", _CI_ENV),
            1,
        )
        ctl.check("VACUITY: no compose file at all is refused", run(None, _CI_ENV), 1)

        # A MISSING ci_env.py, one with no PERSISTED tuple, and one whose entry is not a literal all REFUSE. An empty persisted set must never be read as "nothing to persist".
        ctl.check("VACUITY: a missing ci_env.py reddens", run(_COMPOSE, None), 1)
        ctl.check(
            "VACUITY: a ci_env.py without a PERSISTED tuple reddens",
            run(_COMPOSE, plant(_CI_ENV, "PERSISTED: tuple", "RENAMED: tuple")),
            1,
        )
        ctl.check(
            "VACUITY: a non-literal PERSISTED entry reddens",
            run(
                _COMPOSE,
                plant(_CI_ENV, '    ("EMPTY_DEFAULTED", ""),\n', "    NAME_FROM_ELSEWHERE,\n"),
            ),
            1,
        )

        # THE FLOOR MIRROR for the refusal: exactly one reference, persisted, is enough to pass. Without this the vacuity checks above could be passing because the gate refuses everything.
        one_var = "services:\n  app:\n    environment:\n      A: ${PERSISTED_ONE}\n"
        ctl.check("FLOOR MIRROR: one persisted reference is enough", run(one_var, _CI_ENV), 0)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
