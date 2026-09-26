#!/usr/bin/env python3
"""Port of `.ci/scripts/setup/install-deps.sh`.

`npm ci` for the root workspace plus the three `private/account` trees, each wrapped in `retry_with_backoff 3 10`, with `--ignore-scripts` added on Windows. Ninety-seven lines of bash, more than half of it comment, and the comments are the reason this file is worth reading rather than skimming: two of them record measured incidents that a bare transcription would drop.

-----------------------------------------------------------------------------
THE LOCKFILE WARNING, CARRIED OVER VERBATIM IN SUBSTANCE
-----------------------------------------------------------------------------
`install-deps.sh:10-14` states it and it is not about this script's code at all, it is about what a reader is tempted to do when this script fails: the lockfile (`package-lock.json`) must contain resolved entries for ALL platform-specific optional deps (rollup, lightningcss, esbuild). Never regenerate it by deleting it on a single platform -- that drops the entries for every other
platform. Update individual packages with `npm install <pkg>` instead, which preserves the cross-platform entries. The advice is repeated here because the natural reaction to "npm ci failed three times" is to delete the lockfile, and the twin's authors clearly met someone who did.

-----------------------------------------------------------------------------
THE `npm cache clean --force` THAT WAS REMOVED, AND WHY IT IS RECORDED
-----------------------------------------------------------------------------
`install-deps.sh:32-42` keeps a NOTE about code that is no longer there, and it is the single most expensive fact in the file, so it is preserved rather than summarised. The script used to run `npm cache clean --force` "to avoid corruption issues on CI runners". It was actively harmful:

  * Every caller pairs this script with `actions/setup-node`, whose
    `cache: 'npm'` had just restored a ~396 MB `~/.npm` cache.
  * Cleaning it meant `npm ci` re-downloaded all 1096 packages over the network
    in every job -- roughly 10 GB of pointless cache traffic per CI run.
  * An isolated A/B put the warm cache at ~1s of the install, so the RESTORE was
    the waste, not the install.

Callers now cache `node_modules` itself (`.github/actions/setup-workspace`) and this script only runs on a cache MISS, where a cold npm cache is strictly worse. `retry_with_backoff` is what actually handles transient corruption. A port that dropped this paragraph would leave the next person free to "fix flakiness" by adding the cache clean back.

-----------------------------------------------------------------------------
ALL THREE ACCOUNT TREES, WHICH IS ALSO A RECORDED DECISION
-----------------------------------------------------------------------------
`install-deps.sh:74-80`: `private/account`, `private/account/web` and `private/account/e2e` used to be installed ad hoc by whichever job happened to need them (quality-lint installed all three inline so knip could resolve imports), which meant the precondition "account deps are installed" meant something different in every job. One list here makes the cached account tree canonical.

-----------------------------------------------------------------------------
FIVE FACTS ABOUT THE TWIN THAT LOOK LIKE MISTAKES. ALL FIVE ARE REPRODUCED
-----------------------------------------------------------------------------
Reported to the driver rather than repaired here: fixing a twin is a cutover-box decision, and a port that silently improves on its original stops being evidence about the original.

  1. THE ACCOUNT TREES NEVER GET `--ignore-scripts`. The flag exists, per the
     twin's own header, because "On Windows, --ignore-scripts is added
     automatically to avoid native module rebuild issues (ssh2 / cpu-features /
     esbuild)". `run_account_ci` is `(cd "$1" && npm ci)` with no flag at all,
     so on Windows -- the exact platform the flag was added for -- the three
     account trees still run their lifecycle scripts. `NPM_ARGS` is a global in
     scope at that point; it is simply not used. Reproduced exactly: this port
     passes `["npm", "ci"]` for the account trees under every combination of
     flags and platform, and the differential asserts the resulting call log.

  2. `--account-only` STILL ANNOUNCES `Using --ignore-scripts flag`. The
     `log_info` sits outside the `WANT_ROOT` guard, so a run that will not
     execute a single root install still says it is using the flag. Harmless,
     visible, and reproduced because output bytes are the contract.

  3. A RUN THAT INSTALLS NOTHING PRINTS `npm install complete` AND EXITS 0.
     This is the vacuity class in the script whose whole job is to install.
     `--account-only` on a checkout with no `private/account/package.json` skips
     the root half by flag and the account half by file test, then falls through
     to the unconditional closing `log_info` and exits 0. `--skip-account
     --account-only` together is stronger still: both halves are switched off by
     ARGUMENTS, no file test involved, and the script reports success having run
     no subprocess whatsoever. Nothing counts how many installs actually
     happened, so there is no number a reader could notice collapsing.

  4. AN UNRECOGNISED ARGUMENT IS SILENTLY IGNORED. The parse loop is a `case`
     with three arms and no `*)` arm, so `--ignore-script` (a plausible typo)
     parses as nothing and the run proceeds WITHOUT the flag the caller asked
     for. On Windows that is invisible, because the platform arm adds the flag
     anyway; on Linux it is a silent no-op.

  5. A MISSING `npm` IS RETRIED THREE TIMES OVER 30 SECONDS. There is no
     `require_cmd npm`. When the binary is absent the shell function exits 127,
     which `retry_with_backoff` treats as an ordinary failure: it sleeps 10, then
     20, then reports `Failed to install dependencies after retries`. Thirty
     seconds and a message that sends the reader to the registry rather than to
     their PATH.

-----------------------------------------------------------------------------
THE ONE DIVERGENCE, WHICH IS A PREFIX AND NOTHING ELSE
-----------------------------------------------------------------------------
When `npm` is not on PATH at all, bash writes its OWN diagnostic once per attempt and gives the failed command status 127:

    .ci/scripts/setup/install-deps.sh: line 60: npm: command not found

`subprocess.run` cannot produce that line -- it raises `FileNotFoundError`, and an unhandled one would replace a five-line report with a twelve-frame traceback, which is strictly worse than the twin. So `spawn` below catches it and writes bash's own wording, `npm: command not found`, WITHOUT the `<script>: line <n>: ` prefix, which names a bash file that does not exist in this
implementation and a line number that would be a lie.

Everything else on that path is identical: three attempts, the 10/20 backoff, the two closing error lines, exit 1. `test_a_127_from_a_missing_npm_...` asserts the divergence as exactly that prefix, by stripping it from the twin's bytes and requiring the remainder to match, so the claim is pinned rather than remembered.

-----------------------------------------------------------------------------
WHAT IS NOT REPRODUCIBLE, STATED RATHER THAN LEFT AS AN ABSENCE
-----------------------------------------------------------------------------
The twin `cd`s to the repo root in ITS OWN shell and never returns; a sourced copy would move the caller. `os.chdir` here has the same effect on this process and the same non-effect on its parent, which is what a caller expects. Every path below the chdir is relative in both implementations, so the working directory is part of the contract rather than a detail.

STREAMS ARE INHERITED, NEVER CAPTURED. `npm ci` on a cold tree prints for minutes and that output is the thing an operator watches; a port that captured it would turn a live install into a silent hang. `subprocess.run` with no
`stdout=`/`stderr=` is what the twin's bare `npm $NPM_ARGS` does.

`npm $NPM_ARGS` IS UNQUOTED IN THE TWIN, deliberately, so that `ci --ignore-scripts` word-splits into two arguments. That is a word-splitting construct that works only because the values are known-safe literals; this port builds an argv LIST, which cannot split wrongly and cannot be widened by a value containing a space. Same argv, structurally instead of by luck.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci import log, proc
from rediacc_ci.core import common

# `retry_with_backoff 3 10` at both call sites (install-deps.sh:57 and :86). Three attempts, ten seconds before the second and twenty before the third; the
# doubling is `delay=$((delay * 2))` in common.sh:229. Named constants rather
# than inline numbers because the two call sites must not drift apart, which is exactly what happened to the account trees before they were listed in one place.
RETRY_ATTEMPTS = 3
RETRY_DELAY = 10.0
RETRY_FACTOR = 2.0

# The three account trees, in the twin's order (install-deps.sh:83). ORDER IS OBSERVABLE: each install prints, and a failure stops the loop, so the tree that fails first is the tree named in the error.
ACCOUNT_DIRS = (
    "private/account",
    "private/account/web",
    "private/account/e2e",
)

# The file whose presence gates the whole account half (install-deps.sh:82), and the same name re-tested per directory inside the loop.
PACKAGE_JSON = "package.json"

# The directory the root half insists on afterwards (install-deps.sh:69). A genuine anti-vacuity check, and the only one in the script: `npm ci` can exit 0 having done nothing if the caller's cwd is wrong.
NODE_MODULES = "node_modules"


class Options:
    """The three flags, as the twin's `case` loop understands them.

    A class rather than an `argparse.Namespace` because the twin's parser is not argparse and must not be replaced by one: argparse would REFUSE an unknown argument (fact 4 above), print a usage block to stderr and exit 2, where the twin ignores it and exits 0. That difference would show up on the first differential row as a mismatch in a case the port had "improved".
    """

    __slots__ = ("ignore_scripts", "want_account", "want_root")

    def __init__(self) -> None:
        self.ignore_scripts = False
        self.want_root = True
        self.want_account = True


def parse_args(argv: list[str]) -> Options:
    """`install-deps.sh:20-28`, arm for arm.

    A `for arg in "$@"` over a three-arm `case` with no default arm. Two properties that follow and are both reproduced:

      * EVERY occurrence is honoured, so `--skip-account --skip-account` is the
        same as one. There is no "last wins" because none of the three arms
        contradict each other.
      * A non-flag positional is ignored as silently as an unknown flag; the
        `case` never looks at anything but the three literals.
    """
    opts = Options()
    for arg in argv:
        if arg == "--ignore-scripts":
            opts.ignore_scripts = True
        elif arg == "--skip-account":
            opts.want_account = False
        elif arg == "--account-only":
            opts.want_root = False
    return opts


def secs(value: float) -> str:
    """A delay as bash would print it: `10`, not `10.0`.

    `common.sh:226` interpolates `${delay}s` where `delay` is a shell integer, so
    the warn line reads `retrying in 10s...`. `proc.backoff_delays` answers floats, and `"%s" % 10.0` is `10.0`, which is one character of divergence in a line the differential compares byte for byte. Integral values print as integers and anything else keeps its decimal, so a future non-integral delay would be visible rather than silently truncated.
    """
    if float(value).is_integer():
        return "%d" % int(value)
    return "%s" % value


def retry(action) -> bool:
    """`retry_with_backoff 3 10 <fn>` (common.sh:218-233), messages included.

    THE TWO ERROR LINES ARE NOT ONE. On exhaustion the helper itself prints `Command failed after 3 attempts` and returns 1, and only then does the CALLER print its own `Failed to install dependencies...`. Both land on stderr, in that order, and a port that emitted only the caller's line would lose the half that says how many attempts were made.

    `action` returns True on success. Anything falsy is a failed attempt, which is the twin's policy exactly: `if "$@"; then return 0; fi` and nothing else. No exit code is inspected, so a 127 (npm absent) and a 1 (registry refused) are the same event -- fact 5 above.
    """

    def on_retry(attempt: int, attempts: int, pause: float, result: object) -> None:
        del result  # the twin has no access to it either; it only sees $?
        log.warn("Attempt %d/%d failed, retrying in %ss..." % (attempt, attempts, secs(pause)))

    outcome = proc.retry_with_backoff(
        action,
        attempts=RETRY_ATTEMPTS,
        delay=RETRY_DELAY,
        factor=RETRY_FACTOR,
        on_retry=on_retry,
    )
    if outcome.ok:
        return True
    log.error("Command failed after %d attempts" % RETRY_ATTEMPTS)
    return False


def npm_argv(*, ignore_scripts: bool) -> list[str]:
    """The root install's argv: `npm ci` plus the flag when it is wanted.

    Separated from `main` so the differential can assert the argv without running anything, and so the one place the flag is added is visible next to fact 1 -- the account trees do NOT come through here.
    """
    argv = ["npm", "ci"]
    if ignore_scripts:
        argv.append("--ignore-scripts")
    return argv


def wants_ignore_scripts(*, requested: bool, os_name: str) -> bool:
    """`[[ "$CI_OS" == "windows" ]] || [[ "$IGNORE_SCRIPTS" == "true" ]]`.

    `CI_OS` is `common.sh:509`, computed at SOURCE time from `uname -s` and exported. `core.common.detect_os()` is the ported spelling and answers the same four words (`linux`, `macos`, `windows`, `unknown`) with the same fail-open arm.

    THE REPO-WIDE BELT AND BRACES, from the twin's header: `.npmrc` now sets
    `ignore-scripts=true` globally, so this flag is not the only thing blocking
    lifecycle scripts. It is still passed, because a caller reading the npm command line should be able to see the intent without knowing about `.npmrc`.
    """
    return os_name == "windows" or requested


def spawn(argv: list[str], cwd: str | None = None) -> bool:
    """One child, BOTH streams inherited, True when it exited 0.

    THE `FileNotFoundError` ARM IS THE WHOLE REASON THIS IS A FUNCTION. Bash prints `<script>: line <n>: npm: command not found` and moves on to the next retry; Python raises, and an unhandled raise here would turn the twin's five-line report into a traceback whose first useful frame is `subprocess._execute_child`. The message is bash's own wording minus the prefix that names a
    shell script, and it is written once per ATTEMPT because that is when bash writes it -- so a run against an absent `npm` still shows three of them.

    `PermissionError` and every other `OSError` take the same arm: from the caller's point of view "the binary did not run" is one event, and bash's `Permission denied` is the same shape of line.
    """
    try:
        return subprocess.run(argv, cwd=cwd, check=False).returncode == 0
    except OSError as exc:
        sys.stderr.write(
            "%s: %s\n"
            % (argv[0], "command not found" if isinstance(exc, FileNotFoundError) else exc.strerror)
        )
        sys.stderr.flush()
        return False


def run_root(argv: list[str]) -> bool:
    """One `npm ci` in the current directory, streams inherited."""
    return spawn(argv)


def run_account(directory: str) -> bool:
    """`run_account_ci` (install-deps.sh:84): `(cd "$1" && npm ci)`.

    THE SUBSHELL IS THE POINT of the twin's parentheses: the `cd` must not outlive the call, because the loop's next iteration and the closing
    `log_info` both assume the repo root. `cwd=` on one child has the same
    property and cannot leak by construction.

    NO `--ignore-scripts`, EVER. Fact 1. Written as a literal list here rather than as `npm_argv(...)` with a False argument, so that the absence is a visible decision in the code and not an argument someone later "fixes".
    """
    return spawn(["npm", "ci"], cwd=directory)


def main(argv: list[str]) -> int:
    opts = parse_args(argv)

    # `cd "$(get_repo_root)"` (install-deps.sh:31). Everything after this is relative, in both implementations.
    os.chdir(common.repo_root())

    if opts.want_root:
        log.step("Installing npm dependencies...")

    ignore_scripts = wants_ignore_scripts(
        requested=opts.ignore_scripts,
        os_name=common.detect_os(),
    )
    if ignore_scripts:
        # OUTSIDE the want_root guard, matching install-deps.sh:52. Fact 2.
        log.info("Using --ignore-scripts flag")

    if opts.want_root:
        argv_root = npm_argv(ignore_scripts=ignore_scripts)
        if retry(lambda: run_root(argv_root)):
            log.info("Dependencies installed successfully")
        else:
            log.error("Failed to install dependencies after retries")
            return 1

        if not os.path.isdir(NODE_MODULES):
            log.error("node_modules directory not created")
            return 1

    if opts.want_account and os.path.isfile(os.path.join(ACCOUNT_DIRS[0], PACKAGE_JSON)):
        log.step("Installing account dependencies...")
        for account_dir in ACCOUNT_DIRS:
            # The outer guard already proved the FIRST one; the per-directory test is what makes `web` and `e2e` optional (install-deps.sh:85).
            if not os.path.isfile(os.path.join(account_dir, PACKAGE_JSON)):
                continue
            if not retry(lambda d=account_dir: run_account(d)):
                log.error("Failed to install dependencies in %s" % account_dir)
                return 1

    # UNCONDITIONAL, and fact 3 is what that costs.
    log.info("npm install complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
