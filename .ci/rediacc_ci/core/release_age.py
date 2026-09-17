"""Release-age freshness deferral, ported from `.ci/scripts/lib/release-age.sh`.

PORTED FROM `.ci/scripts/lib/release-age.sh` (237 lines), which still exists, is
untouched by this file, and has exactly TWO real sourcers, re-measured on
2026-09-10 (`grep -rnP '^\\s*(source|\\.)\\s+.*release-age\\.sh'`):
`.ci/scripts/security/audit.sh:39` and
`.ci/scripts/quality/check-go-deps.sh:43`. That agrees with the twin's own
"Consumed by:" line at `release-age.sh:41`, and it is NOT the "237" in the
programme plan, which is this file's LINE COUNT rather than its fan-in.

A PORT OF A SHIM IS ANOTHER SHIM, NOT A THIRD COPY OF THE RULE. The rule
collapsed into `scripts/lib/release-age.ts` on 2026-09-06 and lives nowhere else:

    eligibleAt = startOfNextUtcDay(publishedAt + window)   # window default 24h
    deferred   = now < eligibleAt                          # effective age 24-48h

The TypeScript side won that collapse because it has six consumers to the bash
side's two, because it is portable while the bash round-up needed GNU-only
`date -u -d`, and because the bash tree is the one scheduled to be ported away.
Re-deriving the round-up here would undo all three arguments at once, so this
module delegates exactly as the twin does and owns only the transport, the memo
and the two caller policies.

--------------------------------------------------------------------------
THE DUPLICATE THAT ALREADY EXISTS, NAMED RATHER THAN LEFT TO BE FOUND
--------------------------------------------------------------------------
`.ci/rediacc_ci/quality/go_deps.py:300` ALREADY carries a `ReleaseAge` class that
is this same shim, inlined into one gate because that gate was ported before the
library was. This module is the one implementation it can eventually reach.
REPOINTING IT IS NOT DONE HERE and is not this module's licence to grant:
`go_deps.py` is a gate with its own recorded shadow ledger, and a body swap under
a ledger is a separate change. The differences between the two are real and
listed, so whoever collapses them knows what moves:

  * `go_deps.ReleaseAge.is_deferred(publish, now=None)` DROPPED the twin's third
    parameter. `is_release_deferred <publish> [now] [window]` takes a window
    override; the gate's copy always uses `window_seconds()`. Neither live caller
    passes a window, so no verdict differs today.
  * that copy's runner probe runs with `cwd=<root>`; the twin's probe runs in the
    CALLER's directory and only the real queries `cd` (`release-age.sh:118`
    versus `:137`). Immaterial, because `release-age.ts` resolves `.npmrc`
    against its own `__dirname`, but it is a difference and this module keeps the
    twin's.

--------------------------------------------------------------------------
DEFECT 1, MEASURED: THE RUNNER MEMO NEVER PERSISTS. N+1 PROBES, NOT ONE.
--------------------------------------------------------------------------
`release-age.sh:95-97` says the file picks between the three runners "ONCE per
shell process", and `:140-147` explains at length that a value written inside a
command substitution dies with the subshell. The RUNNER falls into precisely that
trap while the comment is busy diagnosing it for the caches:
`__release_age_resolve_runner` assigns `__RELEASE_AGE_RUNNER` at `:120`/`:125`/
`:128`, but it is only ever reached from `__release_age_delegate`, which is only
ever reached from `answer=$(__release_age_delegate ...)` at `:159` and `:178`.
Both are command substitutions, so the assignment is discarded every time.

Measured 2026-09-10 on bash 5.3.9, with a counting wrapper first on PATH and five
DISTINCT publish epochs through `is_release_deferred`:

    node invocations: 12
      5 x --eligible-epoch <epoch> 86400
      7 x --window-seconds

Seven `--window-seconds` runs for one window: one real query plus SIX probes.
With the memo working the same work is 7 node starts, not 12; wall clock 1.37s
against a measured 0.111s per node start. Direct confirmation that the variable
never survives:

    $ bash -c 'source .ci/scripts/lib/release-age.sh
               is_release_deferred 1756000000 1756100000
               echo "runner=[$__RELEASE_AGE_RUNNER]"'
    runner=[]

THIS PORT CACHES THE RUNNER, which is a DIVERGENCE and is why it is written down
here in full rather than inherited quietly. Three reasons it is the right side to
come down on: no verdict moves, because all three rungs execute the same file and
the ladder is deterministic; the twin's stated intent is the cached behaviour, so
reproducing the loss would be reproducing a comment's contradiction rather than a
contract; and `go_deps.py:319` already caches it, so a port that did not would
disagree with the Python sibling it is supposed to replace.
`test_core_release_age.py` COUNTS the delegate invocations on both sides and pins
the N+1 against the 1, so the divergence cannot quietly change size. THE BASH IS
NOT FIXED HERE; it is not this box's file.

--------------------------------------------------------------------------
DEFECT 2, MEASURED: `now` IS UNVALIDATED, AND ITS FAILURE IS FAIL-OPEN
--------------------------------------------------------------------------
`is_release_deferred` validates `publish_epoch` against `^[0-9]+$` and documents
a fail-CLOSED policy: "a lookup hiccup must never turn into a false 'must
upgrade' gate failure" (`release-age.sh:221-223`). The second argument gets no
such check and goes straight into `((now < __RELEASE_AGE_ELIGIBLE))` at `:236`,
where bash arithmetic decides. Measured 2026-09-10 against a real delegate:

    now="abc"          -> DEFERRED   (bare word resolves as a variable, unset, 0)
    now="9-9"          -> DEFERRED   (evaluates to 0)
    now="0x10"         -> DEFERRED   (16)
    now="1756100000x"  -> ELIGIBLE   (arith error, `(( ))` returns 1)

and under the `set -u` the two real callers run with, `now="abc"` prints
`abc: unbound variable` and also yields ELIGIBLE. So the one shape most likely to
arrive from a broken date parse, a number with a stray suffix, resolves to the
exact false "must upgrade" the fail-closed rule exists to prevent, and does it
silently.

LATENT, NOT LIVE, and the difference is worth stating: both real call sites pass
one argument (`is_release_deferred "$epoch"` at `audit.sh:271` and
`check-go-deps.sh:151`), so `now` is always `date -u +%s` today. THIS PORT TAKES
`now` AS AN `int | None` AND REFUSES ANYTHING ELSE, which is a divergence on
inputs no live caller produces; `test_core_release_age.py` drives the TWIN for
each of the four rows above so the defect is pinned as a fact about the bash
rather than as a claim in a docstring.

--------------------------------------------------------------------------
WHAT IS FAITHFULLY REPRODUCED
--------------------------------------------------------------------------
  * THE THREE-RUNG LADDER AND ITS PROOF. `node --experimental-strip-types` is
    tried first and ACCEPTED ONLY IF a real query answers with an integer, so a
    future Node that renames or drops the flag falls through to
    `node_modules/.bin/tsx` instead of poisoning every verdict. That matters
    because the fail-closed policy turns an unreachable delegate into "deferred",
    and a freshness gate stuck on "deferred" is a gate that has gone quiet.
    Measured warm on 2026-09-06: 0.11s / 0.55s / 0.98s, which is the order.
  * THE 86400-SECOND FALLBACK IS THE CALLER'S POLICY AND STAYS ON THIS SIDE.
    `getMinReleaseAgeMs()` returns 0 (deferral disabled) when `.npmrc` carries no
    key; this side has always used 24h. The divergence between the two
    implementations is preserved rather than resolved in either direction, and it
    is unreachable today because `check-npmrc.sh` gates the key's presence.
    NOTE FOR ANYONE WRITING A TEST: this repo's `.npmrc` says
    `minimum-release-age=1440` MINUTES, which is 86400 seconds, so the live value
    and the fallback are the same number and no test can tell them apart from the
    real tree. Point `--npmrc` somewhere else to distinguish them.
  * THE LOUD REFUSAL. An unreachable delegate prints
    `release-age: could not reach scripts/lib/release-age.ts (tsx missing or
    failing); treating '<epoch>' as DEFERRED` on stderr, byte for byte, rather
    than inventing a number. A silent fallback here would make every version look
    eligible, or every one deferred, depending on the sentinel chosen.
  * THE FAILED LOOKUP IS NOT MEMOISED. `release-age.sh:190` writes the cache only
    after the regex accepts, so a transient delegate failure is retried on the
    next call instead of being frozen into the run.
  * A NEGATIVE ELIGIBLE EPOCH IS ACCEPTED. `:179` matches `^-?[0-9]+$`, one
    character wider than the `^[0-9]+$` at `:227` and `:160`, so a publish epoch
    before 1970 round-trips.

WHAT HAS NO COUNTERPART. `release-age.sh:71-78` refuses bash older than 4.2
because `declare -gA` is 4.2 and the cache keys are `"<epoch>:<window>"`, which an
INDEXED array evaluates as arithmetic (`syntax error in expression`, once per
lookup, while the memo silently misses). A Python dict has no such precondition,
so the guard is absent BY CONSTRUCTION rather than dropped.
"""

import functools
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

from rediacc_ci import paths

# `readonly RELEASE_AGE_DEFAULT_WINDOW_SECONDS=86400` (release-age.sh:93).
RELEASE_AGE_DEFAULT_WINDOW_SECONDS = 86400

# The delegate, relative to the repository root (release-age.sh:114).
RELEASE_AGE_TS = "scripts/lib/release-age.ts"

_UNSIGNED = re.compile(r"[0-9]+")
# One character wider on purpose: `:179` accepts a negative epoch, `:160` and `:227` do not. See WHAT IS FAITHFULLY REPRODUCED.
_SIGNED = re.compile(r"-?[0-9]+")

USAGE = """release_age -- the `release-age.sh` shim verbs.

  window-seconds                        the base freshness window in seconds
  eligible-epoch <publish> [window]     the epoch it becomes actionable
  deferred <publish> [now] [window]     prints deferred/eligible; exit 0 when
                                        deferred, 1 when eligible
"""


class ReleaseAge:
    """The freshness delegate, with the twin's runner ladder and two memos.

    ONE INSTANCE PER RUN. The twin's caches are shell globals that live for the
    length of the process, so `MODULE_SHIM` below is a module-level singleton and
    the free functions are bound to it, which is the literal translation. A
    module-level singleton would also let one test's answer leak into the next,
    which is the shape of a control that cannot fail, so every test constructs
    its own instance -- the one capability the port adds and bash cannot express.
    """

    def __init__(self, root: pathlib.Path | None = None) -> None:
        self.root = paths.repo_root() if root is None else pathlib.Path(root)
        self._runner: list[str] | None = None
        self._window: int | None = None
        self._eligible: dict[tuple[int, int], int] = {}
        # Not part of the twin. The count `test_core_release_age.py` compares
        # against the twin's N+1 probes; see DEFECT 1.
        self.delegate_calls = 0
        self.probe_calls = 0

    @property
    def lib(self) -> str:
        return str(self.root / RELEASE_AGE_TS)

    # -- the ladder --------------------------------------------------------

    def resolve_runner(self) -> list[str]:
        """`__release_age_resolve_runner` (release-age.sh:112-129), memoised.

        THE MEMO IS THE DIVERGENCE, not the ladder. See DEFECT 1 in the module
        docstring for the measurement of what the twin does instead.
        """
        if self._runner is not None:
            return self._runner
        # `command -v node >/dev/null 2>&1`.
        if shutil.which("node") is not None:
            # NO `cd` HERE, deliberately: the twin probes at `:118` without the subshell `cd` that `:137` uses for real queries.
            self.probe_calls += 1
            probe = self._capture(
                ["node", "--experimental-strip-types", self.lib, "--window-seconds"], cwd=None
            )
            if probe is not None and _UNSIGNED.fullmatch(probe):
                self._runner = ["node", "--experimental-strip-types"]
                return self._runner
        local_tsx = self.root / "node_modules" / ".bin" / "tsx"
        # `[[ -x ... ]]`.
        if os.access(str(local_tsx), os.X_OK):
            self._runner = [str(local_tsx)]
            return self._runner
        self._runner = ["npx", "tsx"]
        return self._runner

    def _capture(self, argv: list[str], *, cwd: str | None) -> str | None:
        """Run one delegate command. None when it could not answer.

        `2>/dev/null` on both call sites, so the delegate's own diagnostics never
        reach the caller and the ONLY thing that distinguishes a failure is the
        empty answer. Reproduced rather than improved: a port that let the
        TypeScript's `release-age: publish epoch must be an integer ...` through
        would print a line the twin swallows, and the differential would call
        that a mismatch in the port.
        """
        try:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
        except OSError:
            return None
        if proc.returncode != 0:
            return None
        # `$(...)` strips every trailing newline.
        return proc.stdout.rstrip("\n")

    def delegate(self, *args: str) -> str | None:
        """`__release_age_delegate` (release-age.sh:131-138). Runs in the ROOT."""
        runner = self.resolve_runner()
        self.delegate_calls += 1
        return self._capture([*runner, self.lib, *args], cwd=str(self.root))

    # -- the two memos -----------------------------------------------------

    def window_seconds(self) -> int:
        """`release_age_window_seconds` (release-age.sh:199-202). ALWAYS succeeds.

        An unreachable delegate, a non-numeric answer or a NON-POSITIVE one all
        fall back to 24h, and the third of those is the live path: the TypeScript
        prints `0` when `.npmrc` carries no key, and `((answer <= 0))` at `:160`
        turns that 0 into 86400. That is the caller policy, not a guard.
        """
        if self._window is not None:
            return self._window
        answer = self.delegate("--window-seconds")
        if answer is None or not _UNSIGNED.fullmatch(answer) or int(answer) <= 0:
            self._window = RELEASE_AGE_DEFAULT_WINDOW_SECONDS
        else:
            self._window = int(answer)
        return self._window

    def eligible_epoch(self, publish_epoch: int, window: int, *, err=None) -> int | None:
        """`__release_age_ensure_eligible` (release-age.sh:168-192). None on failure.

        THE FAILURE IS NOT CACHED, matching `:190`: the write happens only after
        the regex accepts, so a transient delegate failure is retried rather than
        frozen into the run.
        """
        key = (publish_epoch, window)
        if key in self._eligible:
            return self._eligible[key]
        answer = self.delegate("--eligible-epoch", str(publish_epoch), str(window))
        if answer is None or not _SIGNED.fullmatch(answer):
            print(
                "release-age: could not reach scripts/lib/release-age.ts (tsx missing or "
                "failing); treating '%s' as DEFERRED" % publish_epoch,
                file=sys.stderr if err is None else err,
            )
            return None
        self._eligible[key] = int(answer)
        return self._eligible[key]

    # -- the public verbs --------------------------------------------------

    def release_eligible_epoch(
        self, publish_epoch: str | int, window: int | None = None, *, err=None
    ) -> int | None:
        """`release_eligible_epoch <publish_epoch> [window_seconds]`.

        NO VALIDATION OF `publish_epoch` HERE, and that is the twin: `:208-216`
        passes whatever it was given straight to the delegate, which rejects it,
        which produces the loud stderr refusal and a failure. An empty string
        therefore prints `treating '' as DEFERRED`, naming nothing useful, and
        that message is what a caller sees today.
        """
        if window is None:
            window = self.window_seconds()
        return self.eligible_epoch(publish_epoch, window, err=err)  # type: ignore[arg-type]

    def is_release_deferred(
        self,
        publish_epoch: str | int | None,
        now: int | None = None,
        window: int | None = None,
        *,
        err=None,
    ) -> bool:
        """`is_release_deferred <publish_epoch> [now] [window]`. True = deferred.

        FAIL-CLOSED on an empty or unparseable `publish_epoch` and on a delegate
        that could not answer. The twin returns 0 for deferred and 1 for
        eligible, which is the inverse of the boolean here; `main` does the flip.

        `now` IS AN `int | None` AND NOT A STRING. See DEFECT 2: the twin lets
        bash arithmetic decide, and one of the four shapes measured there is
        fail-OPEN.
        """
        text = "" if publish_epoch is None else str(publish_epoch)
        if not text or not _UNSIGNED.fullmatch(text):
            return True
        moment = int(time.time()) if now is None else int(now)
        if window is None:
            window = self.window_seconds()
        eligible = self.eligible_epoch(int(text), window, err=err)
        if eligible is None:
            return True
        return moment < eligible


@functools.cache
def module_shim() -> ReleaseAge:
    """The shell globals, as ONE process-lifetime instance.

    Cached rather than a module-level constant so importing this module never
    resolves the repository root: `paths.repo_root()` RAISES when
    $REDIACC_CI_ROOT names something unusable, and an import that can raise for
    an environment reason is an import nothing can safely do.

    The cache IS the singleton, which is the literal translation of the twin's
    shell globals. A caller wanting an independent memo constructs `ReleaseAge()`
    directly, which is the one capability the port adds and bash cannot express;
    every test does exactly that, so no case can leak its answer into the next.
    """
    return ReleaseAge()


def release_age_window_seconds() -> int:
    return module_shim().window_seconds()


def release_eligible_epoch(publish_epoch: str | int, window: int | None = None) -> int | None:
    return module_shim().release_eligible_epoch(publish_epoch, window)


def is_release_deferred(
    publish_epoch: str | int | None, now: int | None = None, window: int | None = None
) -> bool:
    return module_shim().is_release_deferred(publish_epoch, now, window)


def main(argv: list[str]) -> int:
    if not argv or "--help" in argv or "-h" in argv:
        print(USAGE, file=sys.stderr)
        return 2
    verb, rest = argv[0], argv[1:]
    shim = module_shim()

    if verb == "window-seconds":
        print(shim.window_seconds())
        return 0

    if verb == "eligible-epoch":
        if not rest:
            print("eligible-epoch needs a publish epoch", file=sys.stderr)
            return 2
        window = int(rest[1]) if len(rest) > 1 and rest[1] else None
        answer = shim.release_eligible_epoch(rest[0], window)
        if answer is None:
            return 1
        print(answer)
        return 0

    if verb == "deferred":
        if not rest:
            print("deferred needs a publish epoch", file=sys.stderr)
            return 2
        now = int(rest[1]) if len(rest) > 1 and rest[1] else None
        window = int(rest[2]) if len(rest) > 2 and rest[2] else None
        deferred = shim.is_release_deferred(rest[0], now, window)
        print("deferred" if deferred else "eligible")
        return 0 if deferred else 1

    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
