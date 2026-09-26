#!/usr/bin/env python3
"""Port of `.ci/scripts/quality/typecheck-workers.sh` (111 lines).

Typecheck every Cloudflare Worker under `workers/`, installing its deps first. The twin's header owns WHY this is a script rather than more `tsc -p` clauses in `package.json` (each worker is a separate npm project whose `@cloudflare/workers-types` resolves from ITS OWN `node_modules`), and that argument is not restated here.

THIS FILE IS WHAT RUNS, since W7P4-b on 2026-09-20. Five surfaces moved together, because a cutover that leaves any one of them naming the twin is a half-cutover that reads as finished: the `Install worker project deps` step in `.github/workflows/ci-quality.yml`, the three `package.json` scripts (`check:types`, `typecheck`, `lint:unused`), both `scripts/ci-runner/manifest.ts`
leaves, and `scripts/gates/check-typecheck-scope-coverage.ts`, which resolved the clause by finding a token ending in `.sh` and would have read every `workers/*/tsconfig.json` as UNCOVERED the moment there was no longer one to find.

THE `---- gate ----` HEADER STAYED ON THE TWIN, and the `run:` inside it moved with everything else. `gate-bind` requires a header's derived `run` to equal its `package.json` script byte for byte, so the block now reads `run: PYTHONPATH=.ci python3 -m rediacc_ci.quality.typecheck_workers --install && knip ...` from a file nothing executes. That is deliberate rather than
overlooked: `lint:unused` is a COMPOSITE gate whose second clause is `knip`, so the header belongs to neither file more than the other, and moving it would re-derive `needs` under the `.py` rules for no behavioural gain. `check:ci-gate-bind` and `check:ci-parity` were both run green after the move.

Ledger: `.ci/shadow/w7p4b-typecheck-workers.observations.jsonl` -- nine rows, nine distinct clean trees, nine distinct finding sets (`npx tsx scripts/lib/shadow-gate.ts --pair w7p4b-typecheck-workers --assert --k 5`). The older `w7p6-typecheck-workers` ledger is superseded and not cited: its rows reach both sides through a fixture that no longer exists.

-----------------------------------------------------------------------------
`find | sort` IS CALLED, NOT REIMPLEMENTED
-----------------------------------------------------------------------------
Discovery is `find workers -maxdepth 2 -name tsconfig.json -type f | sort`, and both halves are run as the twin runs them, for two reasons that are about agreement rather than laziness:

  * `sort` COLLATES BY LOCALE. `sorted()` in Python is a byte/codepoint sort;
    GNU sort under a UTF-8 locale ignores punctuation on its first pass, which
    is exactly the case this tree has (`workers/mta-sts` sorts differently from
    `workers/mtasts` under the two rules). Today's four directories do not
    expose the difference; a fifth one could, and a port that only agrees on
    today's input is not a port.
  * `find`'S FAILURE IS INVISIBLE TO THE TWIN, and that is a property this port
    has to keep rather than improve. The pipeline feeds a `while read` loop
    through a PROCESS SUBSTITUTION, so neither `set -e` nor `pipefail` can see
    its status. A missing `workers/` directory therefore yields find's own
    complaint on stderr and an EMPTY list, and it is the zero-discovery guard
    below -- not the exit status -- that turns that into a refusal. See
    DEFECT B for the case the guard does not cover.

-----------------------------------------------------------------------------
DEFECT A -- AN UNKNOWN ARGUMENT IS SILENTLY A FULL RUN
-----------------------------------------------------------------------------
The twin reads `${1:-}` twice and has no `*)` arm. `--list` and `--install` are
recognised; ANYTHING else -- `--help`, `--isntall`, `-l`, a stray path -- falls through to the default branch and runs the whole install-and-typecheck. Driven 2026-09-14 against the twin in a one-worker fixture whose `npx` is a stub that prints `tsc ok`:

    $ PATH=<fixture>/bin bash <fixture>/.ci/scripts/quality/typecheck-workers.sh --isntall
    typecheck-workers: workers/a/tsconfig.json
    tsc ok
    typecheck-workers: 1 worker project(s) typechecked clean
    rc=0

    $ PATH=<fixture>/bin bash <fixture>/.ci/scripts/quality/typecheck-workers.sh --install
    typecheck-workers: 1 worker project(s) have their deps
    rc=0

`--help` prints the first transcript too. The dangerous half is `--isntall` on the `lint:unused` path: the caller means "install only", gets a full typecheck, and any tsc error in a worker surfaces as a knip-step failure. Reproduced here, not repaired.

-----------------------------------------------------------------------------
DEFECT B -- A PARTIAL `find` FAILURE IS A GREEN RUN OVER A SMALLER SET
-----------------------------------------------------------------------------
The zero-discovery guard is real and it fires, but it only covers the TOTAL collapse. `find` exits non-zero and still prints what it did reach, so an unreadable `workers/<x>` (permissions, a broken mount) drops that worker from the set while the run stays green and reports the smaller count as if it were the whole estate. Driven 2026-09-14 in a two-worker fixture with `workers/b`
chmod 000 (a real permission denial, not a stubbed find):

    $ PATH=<fixture>/bin bash <fixture>/.ci/scripts/quality/typecheck-workers.sh
    find: 'workers/b': Permission denied
    typecheck-workers: workers/a/tsconfig.json
    tsc ok
    typecheck-workers: 1 worker project(s) typechecked clean
    rc=0

find's status says 1; nothing reads it. The gate prints its count, which is the right instinct, but nothing compares that count against anything. Reproduced here, not repaired: an anti-vacuity floor is a cutover-box decision.

-----------------------------------------------------------------------------
DEFECT C -- A PRESENT-BUT-STALE `node_modules` IS NEVER REFRESHED
-----------------------------------------------------------------------------
The install is guarded by `[ ! -d "$dir/node_modules" ]`, a bare EXISTENCE test. An empty `node_modules/` directory, or one predating a lockfile change, counts as installed, so the `lint:unused` contract ("knip needs exactly the same trees") is satisfied only when the directory happens to be complete. The failure this produces is knip's, in the shape the twin's own comment says the
flag exists to prevent. Reproduced here, not repaired.

-----------------------------------------------------------------------------
WHAT IS BYTE-IDENTICAL, AND THE ONE THING THAT IS NOT
-----------------------------------------------------------------------------
Every line this script prints is its own literal string, so all of them are reproduced byte for byte on the same stream: the two-line refusal on stderr, the `--list` output, the two install lines, the per-config line, and both summary lines. The exit status of a failed `npm`/`npx` is the twin's `set -e` status, which is the child's own, and it is reproduced.

THE ONE DIVERGENCE: `cd "$REPO_ROOT"` that cannot happen is bash's own `<script>: line N: cd: ...` with a bash line number. This port prints the same three facts in its own sentence, on the same stream, with the same exit status
1. Identical ruling to every other port in this campaign.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci.core import common

# The message prefix every line of output carries (twin :44-111). The twin hard-codes its own basename rather than deriving it, so the port does too and the name stays `typecheck-workers` after the cutover renames nothing.
SELF = "typecheck-workers"

# `find workers -maxdepth 2 -name tsconfig.json -type f` (twin :41), verbatim. `-maxdepth 2` is what keeps `workers/<x>/node_modules/**/tsconfig.json` out of the set, and it is also why a worker whose tsconfig sits deeper is invisible.
FIND_ARGV = ("find", "workers", "-maxdepth", "2", "-name", "tsconfig.json", "-type", "f")

# The two recognised arguments (twin :52, :64). There is deliberately no third entry and no `*)` arm; see DEFECT A.
LIST_FLAG = "--list"
INSTALL_FLAG = "--install"

# `NPM_NET=(--fetch-timeout=120000 --fetch-retries=5 --fetch-retry-mintimeout=2000
# --fetch-retry-maxtimeout=30000)` (twin :89-90). NPM'S OWN BOUND, not
# coreutils' `timeout(1)`: `check:ci-shell-commands` refuses `timeout` because the minimal CI image does not ship it. The order is the twin's, because it is observable in the call log.
NPM_NET = (
    "--fetch-timeout=120000",
    "--fetch-retries=5",
    "--fetch-retry-mintimeout=2000",
    "--fetch-retry-maxtimeout=30000",
)

# The zero-discovery refusal (twin :44-45), the two lines quoted exactly, including the two-space indent on the second and the sentence split.
NO_WORKERS_LINES = (
    "%s: found no workers/*/tsconfig.json. The layout moved, or this" % SELF,
    "  script is looking in the wrong place; either way a green here would be vacuous.",
)

# The three defects in the module docstring, as constants a test can assert by name instead of restating the sentence.
AN_UNKNOWN_ARGUMENT_IS_A_FULL_RUN = True
A_PARTIAL_FIND_FAILURE_IS_A_SMALLER_GREEN_RUN = True
A_PRESENT_BUT_STALE_NODE_MODULES_IS_NEVER_REFRESHED = True


class BashExitError(Exception):
    """`set -e` ending the run on an unguarded command.

    `npm ci`, `npm install` and `npx tsc` are all unguarded, so the failing program's own stderr is the entire explanation and its status becomes the script's.
    """

    def __init__(self, code: int) -> None:
        super().__init__("set -e: exit %d" % code)
        self.code = code


def repo_root() -> str:
    """`REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"` (twin :33).

    `.ci/scripts/quality/<twin>` and `.ci/rediacc_ci/quality/<this>` are both three directories under the root, so the arithmetic is the same one. Delegated to `common.repo_root()` so `$REDIACC_CI_ROOT` steers a harness the same way it steers every other module in the package.
    """
    return str(common.repo_root())


def read_configs(text: str) -> list[str]:
    """`while IFS= read -r config; do CONFIGS+=("$config"); done < <(...)`.

    TWO BASH RULES, BOTH REPRODUCED:

      * A FINAL LINE WITH NO NEWLINE IS DROPPED. `read` stores it and then
        returns non-zero at EOF, so the loop body never runs for it.
      * AN EMPTY LINE IS KEPT. Unlike `test-d1-migrations.sh`'s version of this
        loop there is no `[[ -n "$config" ]]` guard here, so a blank line would
        become an empty array element and be counted. `find` does not emit one,
        which is why the difference has never mattered; a port that "tidied" it
        away would still be a different program.
    """
    if not text:
        return []
    lines = text.split("\n")
    lines.pop()
    return lines


def discover(root: str) -> list[str]:
    """`find workers -maxdepth 2 -name tsconfig.json -type f | sort` (twin :41).

    BOTH PROGRAMS ARE RUN, and their exit statuses are DISCARDED, because the twin reads this through a process substitution where neither `set -e` nor `pipefail` can see them. `find`'s stderr is inherited so its complaint lands where the twin's does. See the module docstring for why neither half is reimplemented in Python.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    found = subprocess.run(list(FIND_ARGV), cwd=root, stdout=subprocess.PIPE, check=False)
    ordered = subprocess.run(
        ["sort"], cwd=root, input=found.stdout, stdout=subprocess.PIPE, check=False
    )
    return read_configs(ordered.stdout.decode("utf-8", "surrogateescape"))


def dirname(path: str) -> str:
    """`dirname "$config"` (twin :67), which is NOT `os.path.dirname`.

    POSIX `dirname` answers `.` for a path with no slash and for the empty string; `os.path.dirname` answers the empty string for both. `find` only ever emits `workers/<x>/tsconfig.json` here, so the difference is unreachable through the twin's own discovery -- and an unreachable difference is still a difference, which is why it is spelled out rather than assumed away.
    """
    head = os.path.dirname(path)
    return head or "."


def npm_argv(directory: str, *, has_lockfile: bool) -> list[str]:
    """`npm ci|install --prefix "$dir" --ignore-scripts "${NPM_NET[@]}"` (twin :93, :96).

    `--ignore-scripts` MATCHES `.npmrc`'s repo-wide setting rather than overriding it, and none of these workers has a native dependency, so nothing needs `install:natives` afterwards.
    """
    verb = "ci" if has_lockfile else "install"
    return ["npm", verb, "--prefix", directory, "--ignore-scripts", *NPM_NET]


def tsc_argv(config: str) -> list[str]:
    """`npx tsc --noEmit -p "$config"` (twin :103)."""
    return ["npx", "tsc", "--noEmit", "-p", config]


def _run(argv: list[str], **kwargs) -> int:
    """One unguarded command, streams inherited unless the caller says otherwise.

    FLUSHED FIRST, ALWAYS. Python's `print()` is fully buffered against a pipe
    while the child writes straight to the inherited descriptor, so without this
    the port's own lines land out of real order regardless of when they were printed. Found the hard way in this campaign's third wave.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.run(argv, check=False, **kwargs).returncode


def install_one(directory: str) -> None:
    """One iteration's install (twin :69-98), skipped when `node_modules` exists.

    DEFECT C lives on the first line: the test is existence, not completeness.
    """
    if os.path.isdir(os.path.join(directory, "node_modules")):
        return
    has_lockfile = os.path.isfile(os.path.join(directory, "package-lock.json"))
    if has_lockfile:
        print("%s: installing %s (npm ci)" % (SELF, directory))
    else:
        print("%s: installing %s (npm install, no lockfile)" % (SELF, directory))
    # `>/dev/null` ON STDOUT ONLY (twin :93, :96): npm's progress is dropped and its errors are not.
    status = _run(npm_argv(directory, has_lockfile=has_lockfile), stdout=subprocess.DEVNULL)
    if status:
        raise BashExitError(status)


def main(argv: list[str]) -> int:
    root = repo_root()
    # `cd "$REPO_ROOT"` (twin :34). THE ONE DIVERGENCE, see the module docstring.
    try:
        os.chdir(root)
    except OSError as exc:
        print(
            "%s.py: cd: %s: %s" % (SELF, root, exc.strerror),
            file=sys.stderr,
            flush=True,
        )
        return 1

    configs = discover(root)

    # THE ANTI-VACUITY FLOOR THE TWIN ALREADY HAS, and the reason this port does not add a second one: a discovery gate that finds nothing has verified nothing, and the twin says so in exactly these words on stderr.
    if not configs:
        for line in NO_WORKERS_LINES:
            print(line, file=sys.stderr)
        return 1

    # `${1:-}`, twice, with no other arm. DEFECT A is the absence of an else.
    first = argv[0] if argv else ""

    if first == LIST_FLAG:
        # `printf '%s\n' "${CONFIGS[@]}"` (twin :53) and nothing else, so
        # `check-typecheck-scope-coverage.ts` reads the REAL set.
        for config in configs:
            print(config)
        return 0

    install_only = first == INSTALL_FLAG

    try:
        for config in configs:
            # `dir="$(dirname "$config")"` (twin :67).
            directory = dirname(config)
            install_one(directory)
            if install_only:
                continue
            print("%s: %s" % (SELF, config))
            status = _run(tsc_argv(config))
            if status:
                raise BashExitError(status)
    except BashExitError as exc:
        return exc.code

    if install_only:
        print("%s: %d worker project(s) have their deps" % (SELF, len(configs)))
        return 0

    print("%s: %d worker project(s) typechecked clean" % (SELF, len(configs)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
