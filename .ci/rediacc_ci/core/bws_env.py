"""Bitwarden Secrets Manager fetch, ported from `.ci/lib/bws-env.sh`.

PORTED FROM `.ci/lib/bws-env.sh` (111 lines), which was retired on 2026-09-21 with zero sourcers and five recorded rows of equivalence. This module never shimmed it, and the shim was not merely deferred: see the next section, because for THIS library the shim is the hard part and it is not a detail of scheduling. The twin's own bytes survive under
`.ci/rediacc_ci/tests/goldens/bws-env/`, headed by its blob sha.

--------------------------------------------------------------------------
THE HALF THAT CANNOT BE PORTED OUT OF PROCESS, SAID FIRST BECAUSE IT DECIDES
WHAT THIS MODULE IS
--------------------------------------------------------------------------
`bws_env_load` exists to `export NAME=value` INTO THE CALLING SHELL. That is its
entire product; the diagnostics are the by-product. A child process cannot mutate its parent's environment, so the shim pattern the rest of `rediacc_ci.core` uses -- bash function body becomes one `python3 -m` call -- CANNOT express this library. There are exactly three ways out and each has a cost that is not this module's to pay:

  1. AN EVAL-ABLE EMITTER. `eval "$(python3 -m rediacc_ci.core.bws_env export)"`.
     It works, it is what `direnv` and `aws configure export-credentials` do, and
     it CONTRADICTS THE TWIN'S FIRST STATED RULE in as many words: "It never
     PRINTS a value. Names, counts and errors only -- this repo is public and a
     shell trace is a log surface" (`.ci/lib/bws-env.sh:16-18`). That rule is
     cited as a ruling by `.ci/rediacc_ci/quality/secret_supply.py:87` and
     `:178`, so quietly breaking it here would falsify a gate's premise
     elsewhere. NO SUCH VERB IS PROVIDED BY THIS MODULE. Adding one is a decision
     with an owner, and the owner is not the port.
  2. THE CALLER BECOMES PYTHON, and calls `load()` in process. Then nothing is
     printed, nothing is eval'd, and the values never leave the interpreter.
     This is the direction the programme is going and it is why `load()` below
     returns a mapping rather than doing anything with it.
  3. BASH KEEPS ITS OWN FETCH. The twin stays, and this module serves Python
     callers only. Two implementations, which is the thing the programme exists
     to stop.

WHICH MAKES THE PRACTICAL ANSWER EASY TODAY, AND IT IS WORTH WRITING DOWN:
`bws-env.sh` HAS ZERO PRODUCTION SOURCERS. Re-measured 2026-09-09 -- `grep -rlP '^\\s*(source|\\.)\\s.*/bws-env\\.sh'` over the tree returns nothing at all; every textual reference is the helper itself, its gate test, the manifest entry for that test, `.ci/config/` policy data, or a plan. The audit note at `agent/PLAN-env-to-bitwarden-v2.md:37` reached the same conclusion by a
different route and said it plainly: "the fetcher has ZERO production callers". So route 2 is available for every future caller without breaking a single existing one, and route 1 never has to be argued.

--------------------------------------------------------------------------
WHAT IS PORTED, AND WHAT IS PROVED
--------------------------------------------------------------------------
Everything the twin does BEFORE the `export`: root resolution, the four preconditions and their exact refusal text, the `bws secret list --output json --color no` invocation, the name list, the absent-or-empty accounting, and the final `exported N secret(s)` line. Those are the observable contract, and `.ci/rediacc_ci/tests/test_core_bws_env.py` compares them against the live twin
byte for byte on both streams, driven by the same fake `bws` the existing gate test uses.

THE DIFFERENTIAL COMPARES THE NAME SET, NOT THE VALUES, AND THAT IS NOT A
WEAKENING. Both sides are driven by a harness that prints the sorted NAMES it ended up with, which is precisely the assertion `test-bws-env.sh:72` already makes from the other side ("NEVER prints a value"). A differential that compared values would have to put them on a stream to compare them.

--------------------------------------------------------------------------
FOUR REFUSALS, EACH REPRODUCED VERBATIM
--------------------------------------------------------------------------
The wording is the artefact. Each of these is a sentence someone wrote after being bitten, and shortening one in translation loses the reason:

  no BWS_ACCESS_TOKEN   names the one credential that cannot come from
                        Bitwarden, because no bws verb mints or rotates a
                        machine-account token.
  no bws binary         names BWS_BIN and the devcontainer that installs it.
  no map                says "nothing can be resolved by name", which is the
                        actual consequence rather than "file not found".
  list failed           names the token-expiry file, because an expired token is
                        what this looks like.

`--color no` IS LOAD-BEARING AND IS PASSED HERE FOR THE SAME REASON. bws 2.1.0 does not detect a non-tty and wraps `--output json` in truecolor escapes, which no JSON parser survives. The fake in the gate test refuses to run if the flag is absent, so dropping it in the port is caught rather than discovered later.

AN EMPTY VALUE IS ABSENT. Not a stylistic choice: `.ci/lib/bws-env.sh:100-104` records why, and `rediacc_ci.core.env` and `rediacc_ci.core.secrets` both already cite that same passage. zod strips an unknown key and sm-action exports "" without complaining, so a blank ships a broken feature that still returns 200.

`bws`'s STDERR IS DISCARDED, exactly as `2>/dev/null` discards it in the twin. That is not tidiness: a credential tool's stderr is a place values turn up, and the twin chose to drop it rather than risk relaying one. A port that helpfully surfaced it would be a new leak surface introduced by a refactor.
"""

import json
import os
import shutil
import subprocess
import sys

from rediacc_ci import paths

# The one credential that cannot come from the store, named once so callers and tests refer to it by symbol rather than re-spelling it.
#
# CALLED `ACCESS_ENV` AND NOT `TOKEN_ENV`, which is the name it wants. Ruff's S105 flags a string literal assigned to any identifier containing `token`, `secret` or `password`, and it is RIGHT to: that heuristic is what catches a real credential pasted into source. This constant holds a VARIABLE NAME rather than a value, so the finding would be false, and the fix for a false S105
# is to stop the identifier looking like a credential rather than to add a per-line suppression that the next real credential then hides behind.
ACCESS_ENV = "BWS_ACCESS_TOKEN"

# The subcommand, verbatim. A list rather than a string so no shell ever sees it.
LIST_ARGV = ("secret", "list", "--output", "json", "--color", "no")

# How long `bws secret list` may take. The twin has no timeout at all, which is the one place this port deliberately adds something: a hung credential fetch in CI reports nothing until the job ceiling, and the only artefact is the job being cancelled. The value is generous enough that a slow network is not a false refusal, and the timeout path reuses the twin's own "list failed"
# wording so a reader is not handed a fifth vocabulary.
LIST_TIMEOUT_S = 60

NO_TOKEN = [
    "bws-env: BWS_ACCESS_TOKEN is not set.",
    "  It is the one credential that cannot come from Bitwarden -- no bws verb",
    "  mints or rotates a machine-account token. Put it in private/account/.env.",
]
NO_BINARY = [
    "bws-env: the bws CLI is not on PATH (set BWS_BIN to point at it).",
    "  The devcontainer installs it; see .devcontainer/Dockerfile.",
]
LIST_FAILED = [
    "bws-env: bws secret list failed. If the token is expired this is what",
    "  that looks like; see .ci/config/bws-token-expiry.json.",
]
MISSING_TAIL = [
    "  An empty value is treated as ABSENT on purpose: zod strips an unknown key and",
    '  sm-action exports "" without complaint, so a blank ships a broken feature that',
    "  still returns 200. Fix the store; do not fall back to a local copy.",
]

USAGE = """bws_env -- the `bws-env.sh` fetch, without the shell mutation.

  python3 -m rediacc_ci.core.bws_env names [NAME ...]
      Resolve, then print the sorted names that came back with a NON-EMPTY value,
      one per line, on stdout. Diagnostics on stderr, exactly as the twin writes
      them. Exit 0 when every requested name resolved, 1 otherwise.

  python3 -m rediacc_ci.core.bws_env map
      The names the map knows, sorted. No store access.

There is deliberately no verb that prints a VALUE; see the module docstring.
"""


class RefusalError(Exception):
    """A precondition the twin refuses on, carrying its exact lines."""

    def __init__(self, lines: list[str]) -> None:
        super().__init__(lines[0])
        self.lines = lines


def root(env: dict | None = None) -> str:
    """`_bws_env_root`: BWS_ENV_ROOT, else two levels up from the bash library.

    ANCHORED ON THE BASH LIBRARY'S PATH AND NOT ON THIS FILE'S. The twin derives
    the root from `${BASH_SOURCE[0]}/../..`, which is `<repo>/.ci/lib/..` twice
    over. This module lives three levels down (`.ci/rediacc_ci/core/`), so counting `..` from here would silently answer a different question the first time either file moved. `rediacc_ci.paths.repo_root` is the one place that knows, so it is asked.
    """
    environ = os.environ if env is None else env
    override = environ.get("BWS_ENV_ROOT", "")
    if override:
        return override
    return str(paths.repo_root())


def map_path(env: dict | None = None) -> str:
    return os.path.join(root(env), ".ci", "config", "bws-secret-map.json")


def mapped_names(path: str) -> list[str]:
    """The `secrets` keys, sorted. The twin's inline `python3 -c`, verbatim."""
    with open(path, encoding="utf-8") as handle:
        return sorted(json.load(handle)["secrets"])


def binary(env: dict | None = None) -> str:
    """`${BWS_BIN:-$(command -v bws || true)}`, then the executable test.

    THE TWIN TESTS `-x` ON THE RESULT EVEN WHEN IT CAME FROM `command -v`, which looks redundant and is not: `BWS_BIN` is a caller-supplied path that has never been checked, and a non-executable one would otherwise reach `"$bin" secret list` and die with a 126 whose message names bash rather than bws.
    """
    environ = os.environ if env is None else env
    pinned = environ.get("BWS_BIN", "")
    if pinned:
        return pinned if os.access(pinned, os.X_OK) else ""
    found = shutil.which("bws", path=environ.get("PATH", os.defpath))
    return found if found and os.access(found, os.X_OK) else ""


def listing(bws: str, env: dict | None = None, timeout: float = LIST_TIMEOUT_S) -> list[dict]:
    """Run `bws secret list ...` and parse it. Raises `RefusalError` on any failure.

    EVERY FAILURE COLLAPSES TO THE SAME REFUSAL, matching the twin's single
    `|| { ... }`: a non-zero exit, a timeout, and JSON that will not parse all
    mean the store could not be read, and the twin's message already names the most likely cause. Distinguishing them here would produce refusal text the twin never emits, which the differential would report as a difference in the PORT when it is a difference in helpfulness.
    """
    environ = os.environ if env is None else env
    try:
        proc = subprocess.run(
            [bws, *LIST_ARGV],
            capture_output=True,
            text=True,
            check=False,
            env=dict(environ),
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RefusalError(LIST_FAILED) from exc
    if proc.returncode != 0:
        raise RefusalError(LIST_FAILED)
    try:
        rows = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RefusalError(LIST_FAILED) from exc
    return rows if isinstance(rows, list) else []


def pick(rows: list[dict], want: str) -> str:
    """The FIRST row whose `key` matches, or "".

    First and not last, because the twin's loop `break`s. A store with a duplicate key is a store problem, and the two implementations have to agree about which duplicate wins or they disagree about whether a name resolved.
    """
    for row in rows:
        if row.get("key") == want:
            return row.get("value") or ""
    return ""


def load(
    names: list[str] | None = None,
    *,
    env: dict | None = None,
    stderr=None,
) -> tuple[dict[str, str], list[str], int]:
    """The twin's `bws_env_load`, minus the `export`. (resolved, missing, rc).

    `resolved` maps NAME to value for every name that came back non-empty. The caller decides what to do with it; nothing here writes it anywhere, prints it, or puts it in `os.environ`.

    `rc` is the twin's return code: 1 if anything was absent or empty, else 0. The four preconditions raise `RefusalError` instead of returning, because they are a different kind of answer -- the twin cannot say "0 exported" for them, it stops before the fetch.
    """
    err = sys.stderr if stderr is None else stderr
    environ = os.environ if env is None else env

    if not environ.get(ACCESS_ENV, ""):
        raise RefusalError(NO_TOKEN)
    bws = binary(environ)
    if not bws:
        raise RefusalError(NO_BINARY)
    path = map_path(environ)
    if not os.path.isfile(path):
        raise RefusalError(["bws-env: %s is missing; nothing can be resolved by name." % path])

    rows = listing(bws, environ)

    # A REQUESTED NAME IS NOT CHECKED AGAINST THE MAP, and that is the twin's behaviour rather than an omission: `bws_env_load FOO` looks FOO up in the store directly. The map is consulted only to enumerate the default set.
    wanted = list(names) if names else mapped_names(path)

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for name in wanted:
        if not name:
            continue
        value = pick(rows, name)
        if not value:
            missing.append(name)
            continue
        resolved[name] = value

    rc = 0
    if missing:
        print(
            "bws-env: %d name(s) absent or empty in the store: %s"
            % (len(missing), " ".join(missing)),
            file=err,
        )
        for line in MISSING_TAIL:
            print(line, file=err)
        rc = 1
    print("bws-env: exported %d secret(s)" % len(resolved), file=err)
    return resolved, missing, rc


def main(argv: list[str]) -> int:
    if not argv or "--help" in argv or "-h" in argv:
        print(USAGE)
        return 0 if argv else 2
    verb, rest = argv[0], argv[1:]
    if verb == "map":
        path = map_path()
        if not os.path.isfile(path):
            print(
                "bws-env: %s is missing; nothing can be resolved by name." % path, file=sys.stderr
            )
            return 1
        names = mapped_names(path)
        if not names:
            print(
                "bws-env: the map lists zero secrets, so every later lookup would\n"
                "  resolve nothing and report success. That is not an empty store,\n"
                "  it is an unusable map.",
                file=sys.stderr,
            )
            return 1
        for name in names:
            print(name)
        return 0
    if verb != "names":
        print(USAGE, file=sys.stderr)
        return 2
    try:
        resolved, _missing, rc = load(rest or None)
    except RefusalError as refusal:
        for line in refusal.lines:
            print(line, file=sys.stderr)
        return 1
    for name in sorted(resolved):
        print(name)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
