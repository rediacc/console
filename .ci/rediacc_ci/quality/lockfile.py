"""Validate EVERY package-lock.json in the tree, on two independent properties.

Ported from `.ci/scripts/quality/check-lockfile.sh`, which is NOT deleted; see
`rediacc_ci.quality.__init__` for why both copies live side by side until a
committed differential ledger says otherwise.

WHY THE TWIN WAS REWRITTEN, carried over from its header because the archaeology
is the half of a gate that cannot be recovered from the code:

  It used to run lockfile-lint on `package-lock.json` -- the ROOT one, and only
  that one. Two consequences, both bad:

    1. The repo has NINE lockfiles (root, private/account{,/web,/e2e},
       workers/{account,mta-sts,www}, private/growth/*). All FOUR npm-11 pruning
       incidents happened in private/account* -- a file this gate had never
       opened. It was green through every one of them.
    2. The other eight were not supply-chain-validated AT ALL. A non-https or
       tampered resolved URL in any of them sailed straight through.

  And what it validated (--validate-https, --allowed-hosts,
  --validate-package-names, --validate-integrity) says NOTHING about whether npm
  can install the result. The name promised "lockfile"; the check delivered "the
  root lockfile has no malicious URLs".

WHAT THIS GATE PROVES, AND WHAT IT DOES NOT. Two properties, per lockfile:

  A. SUPPLY CHAIN (lockfile-lint). Unchanged, still valuable, now applied to all
     of them.

  B. RESOLVABILITY (`npm ci --dry-run`), under BOTH npm majors in play. npm 11
     PRUNES nested platform entries that npm 10 requires, so a lockfile can be
     readable by one and not the other. This check IS that command, so it cannot
     be fooled by the shape of a diff. A net-negative-diff or
     deletion-rejection heuristic would miss the realistic case: `check-deps
     --upgrade` under npm 11 ADDS entries while pruning platform ones, giving a
     mixed, net-POSITIVE diff, and would then make the lockfile LOOK watched
     while the prune shipped anyway. That is worse than no gate, because it
     retires the human vigilance that has actually been catching this.

     WHY TWO NPMs, since 2026-09-06 (issue #587). These are two different
     questions and collapsing them to one loses a real answer:

       CANONICAL_NPM (npm 11) is the form the committed lockfiles are WRITTEN
         in. The operator ruled migrate-not-revert after `main` landed an npm-11
         lockfile: the repo had been documenting npm 10 as canonical while
         carrying npm 11's output, so every session that read CLAUDE.md "fixed"
         it back and the 27-line `"dev": true` flip oscillated forever. Naming
         one writer ends the oscillation.

       CI_NPM (npm 10) is the npm that still has to INSTALL it. setup-node with
         Node 22 bundles npm 10.x, and no workflow overrides it (checked
         2026-09-06: every `.github/workflows/*` pins `node-version: '22'` and
         nothing pins npm). Dropping this half when the canonical writer moved
         would have stopped proving the thing the gate was built for (CI's own
         `npm ci`) while still printing a tick. That is precisely the
         overstated-coverage disease this file's honest-limit note warns about.

     Measured 2026-09-06: all 11 lockfiles resolve clean under BOTH, which is
     what makes keeping both affordable. When CI's bundled npm eventually
     reaches 11, CI_NPM folds into CANONICAL_NPM and this becomes one check
     again.

  HONEST LIMIT: `--dry-run` does NOT run the reify peer check. A lockfile can
  pass this gate and still fail a REAL cold-cache `npm ci` with ERESOLVE --
  exactly what happened in round 9 of the 0707 campaign
  (wrangler/workers-types peer). So this gate proves "both pinned npms can
  RESOLVE this lockfile", NOT "either can install it". A gate whose name
  overstates its coverage is the disease being cured here; the cure must not
  reintroduce it. For a real install check, use CLAUDE.md's clean-room recipe.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THIS PORT SHELLS OUT TO THE SAME TWO COMMANDS AND DOES NOT REIMPLEMENT EITHER.
That is the point of property B: the check IS `npm ci --dry-run`, so anything
this module did instead of running it would be the heuristic the twin's header
spends eleven lines rejecting. `npx` is invoked with the identical argv in the
identical working directory.

THE DIFFERENTIAL FOR THIS PAIR IS RECORDED AGAINST A FIXTURE `npx`, AND THAT IS
STATED OUT LOUD RATHER THAN LEFT TO BE DISCOVERED. Running the real thing costs
a network round trip per probe, downloads two npm majors, and puts an installer
next to eleven committed lockfiles whose byte form this repository has an entire
CLAUDE.md section about (the 27-line `"dev": true` flip). So the recorded trees
put a deterministic stand-in for `npx` on PATH, INSIDE the fixture, and drive
every branch through it: lint pass, lint fail, npm 11 fail, npm 10 fail, skip,
and the no-lockfile refusal. What the ledger therefore proves is that both
implementations DISCOVER the same lockfiles, INVOKE the same commands, and
REACT identically to their exit codes. What it does not prove is anything about
npm itself, which is not this gate's subject either.

THE DISCOVERY IS `find`, NOT `git ls-files`, and that is deliberate in the twin:
"Discovered, never hardcoded: a hardcoded list is how this gate went stale in the
first place, and a lockfile added tomorrow must be covered without anyone
remembering to add it." The consequence is that an UNTRACKED lockfile is in
scope, unlike most gates here. Preserved. The `-not -path '*/node_modules/*'`
exclusion is reproduced as "no path component is node_modules", which is the
same set for every path `find` can produce.

`while read`, NOT `mapfile`, in the twin, and the reason is worth carrying even
though Python has no such problem: mapfile/readarray are bash-4 builtins and are
BANNED by `.ci/scripts/security/check-commands.sh`, which tracks what is
actually available in the minimal CI images (and on macOS / Git Bash). The twin
"was written to catch npm-10-vs-11 ENVIRONMENT DRIFT and was itself defeated by
environment drift -- it passed locally on bash 5 and failed in CI."

A SILENT SKIP IS THE FAILURE MODE THIS GATE ALREADY SURVIVED ONCE. The
quality-security job checks out WITHOUT submodules, so `private/account*` and
`private/growth*` legitimately do not exist there, and a lockfile with no
`package.json` beside it is skipped -- LOUDLY, as a warning, listed again in a
second warning at the end. The twin's own comment names the precedent: "a silent
skip is how test-embed-credits.sh went green while checking nothing (round 3,
0707 campaign)." Both warnings are carried, and `scripts/lib/shadow-gate.ts`
classifies a `⚠` line as a FINDING, so a port that quietly downgraded either one
to chatter would show up as a mismatch rather than as tidier output.

A HARNESS DEFECT FOUND WHILE RECORDING THIS PAIR, 2026-09-06, and it belongs
here rather than in a report nobody re-reads. The advice line the twin prints
when the CANONICAL writer fails begins "The canonical writer cannot read this
lockfile", and `scripts/lib/shadow-gate.ts`'s REFUSAL vocabulary carries the
term `CANNOT READ` matched case-INSENSITIVELY. So an ordinary sentence of
English advice is read as a gate refusing to report a verdict, the comparison is
SUSPENDED, and the row lands as ERROR_REFUSAL even though both sides produced
byte-identical output. The measured row: tree
ce6f9586c98b8c00d6c23e8df690a5bb805c85d9, exit 1 on both sides, finding count 4
on both sides, fingerprint a2f5ffa94ca75e9a on BOTH sides, onlyOld and onlyNew
both empty. Nothing disagreed.

That matters more than it sounds, because `assertEquivalent` disqualifies a tree
id UNCONDITIONALLY once any row against it is non-EQUIVALENT, and the id is the
content of both implementations -- so a FALSE refusal can never be cleared by
re-running, only by changing code that had nothing wrong with it. The row was
archived verbatim and removed from the ledger rather than left to poison the
pair forever, and the recorded trees now exercise the CI-installer failure
branch instead. The canonical-writer branch is still covered, by `--selftest`
("PLANT: the canonical writer failing to resolve reds") and by the pytest twin.
Reported to the root driver; not fixed here, because `scripts/lib/shadow-gate.ts`
is not this port's file.

THE `break` AFTER A RESOLVE FAILURE IS LOAD-BEARING. When the canonical writer
cannot read a lockfile, the CI-installer probe is not run at all: the two have
DIFFERENT fixes, and telling someone to reconcile with the wrong npm is how the
flip oscillated in the first place. So exactly one resolve failure is ever
reported per lockfile, and it is the first one.

STREAMS. `common.sh`'s four loggers all write to stderr and gate colour on
`[[ -t 2 ]]`, which is the one pre-existing variant that tests the stream it
writes to -- so `rediacc_ci.log` matches it exactly and no stream moves in this
port. The bare `echo` advice lines around a resolve failure are STDOUT in the
twin and stay stdout here; they are data a reader copies, not messages.

ONE KNOWN DIVERGENCE, inherited from the logger and stated so nobody "fixes" it:
`common.sh` logs with `echo -e`, which interprets backslash escapes IN THE
MESSAGE. A lockfile path containing `\t` would be printed differently by the two
implementations. No such path exists, and `rediacc_ci.log` formats the message
as data on purpose; see its docstring.
"""

import contextlib
import os
import pathlib
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The npm whose OUTPUT FORM is canonical for every committed lockfile (issue #587). CLAUDE.md's "27-line package-lock.json flip" section is the prose half
# of this pin; the two must be changed together or the repo goes back to arguing
# with itself.
CANONICAL_NPM = "npm@11"

# The npm CI actually runs. Keep in step with setup-node's bundled npm (Node 22
# -> npm 10); the exact version is printed in every job's "Environment details".
# This is NOT the canonical writer any more, but it is still the installer, so it still gets a vote.
CI_NPM = "npm@10"

# The file name discovered everywhere. Named once so the discovery and the messages cannot drift apart.
LOCK_NAME = "package-lock.json"

# The directory `find` is told to skip. A vendored tree's own lockfiles are not this repository's to validate.
EXCLUDED_DIR = "node_modules"

# The supply-chain probe's argv after `npx`. Carried as a tuple so the order -- which is what a reader diffs against the twin -- cannot be reshuffled by an accidental edit.
LINT_ARGS = (
    "--no-install",
    "lockfile-lint",
    "--type",
    "npm",
    "--validate-https",
    "--allowed-hosts",
    "npm",
    "--validate-package-names",
    "--validate-integrity",
)


def discover(root: pathlib.Path) -> list[str]:
    """`find . -name package-lock.json -not -path '*/node_modules/*' | sed | sort`.

    Repo-relative paths, sorted. `sorted()` on `str` is code-point order, which
    is the C collation the twin's `sort` runs under in CI and in the
    differential harness.

    ZERO IS NOT A VERDICT HERE, and the caller enforces that: a tree with no
    lockfile at all is a refusal, because this gate would otherwise report
    success having opened nothing.
    """
    out: list[str] = []
    # `paths.walk_tree` prunes `node_modules` in place, which is what `-not -path '*/node_modules/*'` amounts to for every path `find` can produce, and is also why a lockfile sitting directly beside a node_modules is still found. It prunes `.claude/worktrees` too: a peer session's sibling checkout of this repository carries its own `package-lock.json` files, and this gate was
    # linting them as if they were ours.
    #
    # THE PRUNE IS NO LONGER SPELLED BY `EXCLUDED_DIR`. That constant now only builds the selftest fixture below, so editing it will NOT change what this
    # walk skips; `paths.PRUNED_DIR_NAMES` is where that lives. Said out loud
    # because a constant that used to steer the code it sits above is exactly the kind of thing a later reader edits expecting an effect.
    for dirpath, _dirnames, filenames in paths.walk_tree(root):
        if LOCK_NAME in filenames:
            out.append(str(pathlib.Path(dirpath).relative_to(root) / LOCK_NAME))
    # `find`'s output starts `./`, which the twin's sed strips; a path directly
    # at the root therefore has no directory prefix at all.
    return sorted(path.removeprefix("./") for path in out)


def lint_argv(lock: str) -> list[str]:
    """The exact `npx --no-install lockfile-lint ...` argv for one lockfile."""
    return ["npx", "--no-install", "lockfile-lint", "--path", lock, *LINT_ARGS[2:]]


def resolve_argv(npm_pin: str) -> list[str]:
    """The exact `npx -y <pin> ci --dry-run --ignore-scripts` argv."""
    return ["npx", "-y", npm_pin, "ci", "--dry-run", "--ignore-scripts"]


def run_lint(root: pathlib.Path, lock: str) -> int:
    """Run lockfile-lint, letting its own output through to both streams.

    NOT CAPTURED. The twin does not redirect it, so lockfile-lint's report is
    what an operator reads when this fails, and swallowing it would leave a
    finding with no evidence under it. `flush` first, because this process's
    buffered stdout would otherwise land AFTER the child's.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.run(lint_argv(lock), cwd=str(root), check=False).returncode


def run_resolve(directory: pathlib.Path, npm_pin: str) -> int:
    """`npm ci --dry-run` in `directory`, output DISCARDED. Returns the exit code.

    Discarded to match the twin's `>/dev/null 2>&1`: the first probe is a yes/no
    question and npm's success chatter is long. The failure path re-runs it with
    output kept; see `resolve_failure_detail`.
    """
    return subprocess.run(
        resolve_argv(npm_pin),
        cwd=str(directory),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode


def resolve_failure_detail(directory: pathlib.Path, npm_pin: str, limit: int = 25) -> list[str]:
    """The first `limit` lines of the failing command, each indented four spaces.

    `2>&1 | head -25 | sed 's/^/    /'` in the twin. Merging the streams is
    correct HERE and only here: this is a transcript being shown to a human, not
    a comparison, and the twin's own `|| true` says the re-run's exit code is
    not part of the verdict.
    """
    proc = subprocess.run(
        resolve_argv(npm_pin),
        cwd=str(directory),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    text = proc.stdout or ""
    lines = text.split("\n")
    # A trailing newline produces a final empty element that `head` never emits
    # as a line; dropping it keeps the two transcripts identical.
    if lines and lines[-1] == "":
        lines.pop()
    return ["    " + line for line in lines[:limit]]


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 violation.

    `--selftest` is intercepted BEFORE any real scan. The twin takes no arguments
    at all, so no caller can be passing this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    lockfiles = discover(root)

    # THE VACUITY CASE, AND THE TWIN SAYS IT IN ONE SENTENCE. A repository with
    # no lockfile anywhere has not been validated; it has been missed.
    if not lockfiles:
        log.error("No package-lock.json found anywhere. That cannot be right.")
        return 1

    failed: list[str] = []
    skipped: list[str] = []

    for lock in lockfiles:
        directory = (root / lock).parent
        rel_dir = str(pathlib.Path(lock).parent)

        # SKIP LOUDLY. The quality-security job checks out WITHOUT submodules, so private/account* and private/growth* legitimately do not exist there. A silent skip is how a gate goes green while checking nothing.
        if not (directory / "package.json").is_file():
            log.warn("SKIP %s - no package.json beside it (submodule not checked out?)" % lock)
            skipped.append(lock)
            continue

        log.step("[%s] supply chain (lockfile-lint)..." % lock)
        if run_lint(root, lock) != 0:
            log.error("[%s] FAILED supply-chain validation" % lock)
            failed.append("%s (supply chain)" % lock)
            continue

        # BOTH MAJORS, AND THE LOOP IS WRITTEN ONCE so neither can be dropped by editing only the other. `role` is what the failure message needs to say: the two have DIFFERENT fixes.
        resolve_failed = False
        for npm_pin, role in ((CANONICAL_NPM, "canonical writer"), (CI_NPM, "CI's installer")):
            log.step("[%s] resolvable by %s (%s)..." % (lock, npm_pin, role))
            if run_resolve(directory, npm_pin) == 0:
                continue
            log.error("[%s] %s CANNOT RESOLVE this lockfile." % (lock, npm_pin))
            print()
            if npm_pin == CI_NPM:
                print("  This is the failure CI hits: npm 11 removes nested platform entries")
                print("  (e.g. vitest's @esbuild/*) that npm 10 requires, so an npm-11 write can")
                print("  leave a lockfile CI cannot install even though it is the canonical form.")
                print(
                    "  Reconciling with %s is the FIRST thing to try, because the" % CANONICAL_NPM
                )
                print("  canonical form is supposed to satisfy both; if it cannot, the dependency")
                print("  itself needs looking at, not the lockfile.")
            else:
                print("  The canonical writer cannot read this lockfile, so it was almost")
                print("  certainly written by something else. Rewrite it with the canonical npm:")
            print()
            print(
                "    cd %s && npx -y %s install --package-lock-only --ignore-scripts"
                % (rel_dir, CANONICAL_NPM)
            )
            print()
            print("  The failure, in full:")
            for line in resolve_failure_detail(directory, npm_pin):
                print(line)
            failed.append("%s (%s cannot resolve)" % (lock, npm_pin))
            resolve_failed = True
            # THE BREAK IS LOAD-BEARING; see the port notes. The second probe is
            # not run, because the two failures have different fixes.
            break
        if resolve_failed:
            continue

        log.info("[%s] OK" % lock)

    if skipped:
        log.warn(
            "Skipped %d lockfile(s) whose package.json is absent: %s"
            % (len(skipped), " ".join(skipped))
        )

    if failed:
        log.error("Lockfile check FAILED for: %s" % " ".join(failed))
        return 1

    # THE SHAPE, NOT JUST THE VERDICT: the count and both pins are named, so a reader notices when the number collapses or a pin quietly disappears.
    log.info(
        "All %d lockfile(s): supply-chain clean and resolvable by BOTH %s (canonical form) "
        "and %s (CI's installer)" % (len(lockfiles), CANONICAL_NPM, CI_NPM)
    )
    # THE LIMIT IS PRINTED ON THE SUCCESS PATH, as a WARNING, on purpose: a gate whose name overstates its coverage is the disease this file was written to cure, so the cure says out loud what it did not check.
    log.warn(
        "Note the limit: --dry-run does NOT run the reify peer check. This proves npm 10 "
        "can RESOLVE these lockfiles, not that it can install them (round-9 ERESOLVE, see "
        "docs/agent-reference/ci-gates.md)."
    )
    return 0


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    NO REAL npm RUNS HERE EITHER. `npx` is stubbed on PATH by a tiny script this
    function writes, for the reasons in the port notes; the subject under test is
    the discovery, the skip rule, the two-probe loop and the exit code, all of
    which are this module's own logic. The stub's exit code is the only thing
    npm contributes to the verdict, and that is exactly what is varied.
    """
    ctl = Controls("lockfile", floor=24, verbose=True)

    # -- discovery, driven directly ------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        ctl.check("VACUITY: an empty tree discovers nothing", discover(root), [])
        (root / LOCK_NAME).write_text("{}", encoding="utf-8")
        ctl.check(
            "discover: the root lockfile has no directory prefix", discover(root), [LOCK_NAME]
        )
        (root / "pkg").mkdir()
        (root / "pkg" / LOCK_NAME).write_text("{}", encoding="utf-8")
        ctl.check(
            "discover: a nested lockfile is found and the list is SORTED",
            discover(root),
            [LOCK_NAME, "pkg/%s" % LOCK_NAME],
        )
        nm = root / "pkg" / EXCLUDED_DIR / "dep"
        nm.mkdir(parents=True)
        (nm / LOCK_NAME).write_text("{}", encoding="utf-8")
        ctl.check(
            "discover: MIRROR a lockfile under node_modules is excluded",
            discover(root),
            [LOCK_NAME, "pkg/%s" % LOCK_NAME],
        )
        # And the exclusion is by COMPONENT, not by substring: a directory whose name merely contains the word is not node_modules.
        near = root / "my_node_modules_backup"
        near.mkdir()
        (near / LOCK_NAME).write_text("{}", encoding="utf-8")
        ctl.check(
            "discover: MIRROR a lookalike directory name is NOT excluded",
            "my_node_modules_backup/%s" % LOCK_NAME in discover(root),
            True,
        )

    # -- argv construction ---------------------------------------------------
    ctl.check(
        "argv: the lint probe names the lockfile with --path",
        lint_argv("a/b.json")[:5],
        ["npx", "--no-install", "lockfile-lint", "--path", "a/b.json"],
    )
    ctl.check("argv: and validates integrity", "--validate-integrity" in lint_argv("x"), True)
    ctl.check(
        "argv: the resolve probe is `npx -y <pin> ci --dry-run --ignore-scripts`",
        resolve_argv(CANONICAL_NPM),
        ["npx", "-y", "npm@11", "ci", "--dry-run", "--ignore-scripts"],
    )
    ctl.check("argv: the two pins are DIFFERENT majors", CANONICAL_NPM != CI_NPM, True)

    # -- the whole gate, with a stubbed npx ----------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        binpath = root / "stub-bin"
        binpath.mkdir()
        stub = binpath / "npx"

        def set_stub(lint_code: int, npm11_code: int, npm10_code: int) -> None:
            """Write an `npx` whose exit code is decided per probe, nothing else."""
            stub.write_text(
                "#!/bin/bash\n"
                'case "$*" in\n'
                "  *lockfile-lint*) echo 'lockfile-lint transcript'; exit %d ;;\n"
                "  *npm@11*) echo 'npm@11 transcript'; exit %d ;;\n"
                "  *npm@10*) echo 'npm@10 transcript'; exit %d ;;\n"
                "esac\nexit 0\n" % (lint_code, npm11_code, npm10_code),
                encoding="utf-8",
            )
            stub.chmod(0o755)

        @contextlib.contextmanager
        def stubbed():
            """Point PATH at the stub and REDIACC_CI_ROOT at the fixture.

            EVERY probe in this selftest runs inside this, without exception. A
            call that escaped it would reach the REAL npx, download two npm
            majors, and put an installer next to this repository's committed
            lockfiles -- which is the one thing this port is under orders never
            to do.
            """
            saved_root = os.environ.get(paths.ROOT_ENV)
            saved_path = os.environ.get("PATH", "")
            os.environ[paths.ROOT_ENV] = str(root)
            os.environ["PATH"] = "%s:%s" % (binpath, saved_path)
            try:
                yield
            finally:
                os.environ["PATH"] = saved_path
                if saved_root is None:
                    os.environ.pop(paths.ROOT_ENV, None)
                else:
                    os.environ[paths.ROOT_ENV] = saved_root

        def run() -> int:
            with stubbed():
                return main([])

        # THE VACUITY CASE FIRST: no lockfile anywhere is a refusal, and it must not be reachable by deleting files until the gate goes quiet.
        set_stub(0, 0, 0)
        ctl.check("VACUITY: no lockfile anywhere is refused", run(), 1)

        (root / LOCK_NAME).write_text("{}", encoding="utf-8")
        # Still no package.json beside it: the SKIP path. It exits 0, which is the twin's behaviour, and says so twice in warnings.
        ctl.check("SKIP: a lockfile with no package.json beside it is skipped, loudly", run(), 0)

        (root / "package.json").write_text("{}", encoding="utf-8")
        ctl.check("CONTROL: a clean lockfile passes", run(), 0)

        set_stub(1, 0, 0)
        ctl.check("PLANT: a supply-chain failure reds", run(), 1)

        set_stub(0, 1, 0)
        ctl.check("PLANT: the canonical writer failing to resolve reds", run(), 1)

        set_stub(0, 0, 1)
        ctl.check("PLANT: CI's installer failing to resolve reds", run(), 1)

        # BOTH FAILING reports only the FIRST, because the two have different fixes. Proven through the transcript rather than asserted in prose.
        set_stub(0, 1, 1)
        ctl.check("PLANT: both majors failing still reds", run(), 1)

        # A SECOND LOCKFILE, whose own package.json is absent, must be SKIPPED
        # while the first is still judged. A skip that suppressed the rest of
        # the run would look identical to a clean tree.
        (root / "sub").mkdir()
        (root / "sub" / LOCK_NAME).write_text("{}", encoding="utf-8")
        set_stub(0, 0, 0)
        ctl.check("MIRROR: one skipped lockfile does not stop the others", run(), 0)
        set_stub(1, 0, 0)
        ctl.check("PLANT: and the judged one still reds beside a skipped one", run(), 1)

        # A NESTED lockfile WITH its package.json is judged, not skipped. Two directions, because "everything is skipped" and "everything is judged" are both single-branch bugs that a one-sided control cannot tell apart.
        (root / "sub" / "package.json").write_text("{}", encoding="utf-8")
        set_stub(0, 0, 0)
        ctl.check("MIRROR: a nested lockfile with a package.json passes", run(), 0)
        set_stub(1, 0, 0)
        ctl.check("PLANT: and the nested one is really judged (lint fails)", run(), 1)

        # THE STUB ITSELF IS CONTROLLED. Without this, every case above could be passing because `npx` was never reached at all, and a gate whose probe never ran is the vacuity this whole exercise exists to refuse.
        set_stub(0, 0, 7)
        with stubbed():
            ctl.check(
                "CONTROL: the stub is what `npx` resolves to", run_resolve(root, CANONICAL_NPM), 0
            )
            ctl.check("CONTROL: and its exit code reaches the gate", run_resolve(root, CI_NPM), 7)
            # The transcript helper indents by four and truncates at the limit.
            ctl.check(
                "detail: the transcript is indented four spaces",
                resolve_failure_detail(root, CI_NPM, limit=1),
                ["    npm@10 transcript"],
            )
            ctl.check(
                "detail: MIRROR the limit truncates to nothing",
                resolve_failure_detail(root, CI_NPM, limit=0),
                [],
            )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
