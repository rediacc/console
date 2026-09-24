# PLAN: bound `_is_invoked`'s `sh` alternative without breaking real `.sh` invocations

Status: done
First-Seen: 2026-09-24
Owner: d778be9d
Updated: 2026-09-23

## Finding

`block_host_toolchain_run.py:_is_invoked` treats `sh` as an interpreter token with no left boundary, so `re.search` matches it as the SUFFIX of any unrelated `.sh` path. Reported live: a command naming two `.sh` paths back to back reads the trailing `sh` of the first as the interpreter and the second (a NEEDS_ENV/NEEDS_SCRIPT key) as its own invoked argument, refusing a command that never ran either script.

## A naive fix was tried this session and reverted

Adding `(?<![\w./-])` before the `interp` alternative (refusing a preceding letter/digit/underscore/dot/slash/hyphen) does stop the false positive, but it also breaks a real, already-tested invocation shape: `./run.sh --publish-www --langs en` must be DENIED (NEEDS_ENV, `--publish-www`), and the ONLY reason the existing pattern catches it is the exact same unanchored `sh`-as-suffix match on `run.sh`. The two cases are syntactically identical -- `<word>.sh<space><stuff-with-no-separator-until-key>` -- and differ only in whether `<word>.sh` is the command actually being run (first word of the whole command) or a path buried mid-argument-list to something else (e.g. the Nth positional argument to `grep`).
A boundary on the token alone cannot tell those apart; bounding it broke the real case as fast as it fixed the false one. Reverted in full (verified via `git status --short` returning empty on both the guard and its test file), confirmed via the guard's own test script:

    python3 .claude/rediacc_hooks/guards/test-block_host_toolchain_run.py

## What would actually distinguish the two cases

The command-opening alternatives (`^`, `[;&|(]`, `` \$( ``, backtick) already express "this token starts a (sub)shell command." The real fix is requiring `interp` to occur at THAT position -- immediately after one of those markers and optional whitespace, not merely "not preceded by a word/dot/slash/hyphen character" (which a plain space anywhere in a long argument list already satisfies).
That stricter anchoring was not attempted this session: a naive version of it (require `interp` to start exactly at the command-start offset) fails `./run.sh` too, because `sh` sits at offset 6 of `./run.sh`, not offset 0 -- the anchor has to permit a `./`-style prefix or a bare filename stem before the recognized interpreter suffix, which needs its own design rather than a one-line patch.

## Boxes

- [x] Design the anchoring precisely: `interp` must be reachable from a genuine command-start position, allowing a `./`/directory prefix and a filename stem before the `.sh` suffix, while still refusing the same suffix when it is not the FIRST token of its (sub)command.
    (ticked) 2026-09-24T07:10:37Z by d778be9d: per-subcommand anchoring, commit 0f0e54185, .claude/rediacc_hooks/guards/block_host_toolchain_run.py:265
- [x] Re-verify both directions against the full existing suite (`test-block_host_toolchain_run.py`) plus new cases for: the reported false positive (two `.sh` paths named inside one command, second one a tracked key, neither actually invoked), and the `./run.sh --publish-www` true positive, run together so neither regresses the other.
    (ticked) 2026-09-24T07:10:38Z by d778be9d: exit 0: test-block_host_toolchain_run.py 87 cases FAILURES 0, commit 0f0e54185
- [x] Decide whether NEEDS_ENV's and NEEDS_SCRIPT's shared use of `_is_invoked` both need the fix or whether the two call sites can safely diverge (unlikely, since the function is one implementation for both tables).
    (ticked) 2026-09-24T07:10:38Z by d778be9d: one implementation serves both tables, .claude/rediacc_hooks/guards/block_host_toolchain_run.py:391, commit 0f0e54185
- [x] Fix the unrelated, confirmed-pre-existing `test-block_host_toolchain_run.py` failure found in passing (`bare-tool: shellcheck routed when constructed-absent from PATH`, tracked as worklist `#517efcd1`). Fixed and committed separately (`7a5b2e30c`, ahead of the anchoring fix below): `_path_without` stripped whole PATH directories to hide one tool, silently also hiding `docker` (bash/docker/shellcheck all resolve to `/usr/bin` in this devbox), which broke the guard's own `docker ps` devbox-detection. Replaced with a per-tool symlink shim; 85/85 cases pass, host and devbox.
    (ticked) 2026-09-23T16:52:08Z by d778be9d: This session's own earlier fix: _path_without rewritten from directory-stripping to a per-tool symlink shim, fixing the docker-hiding side-effect it caused. Committed 7a5b2e30c, verified 85/85 cases pass on host and inside the devbox.

## Critical files

- `.claude/rediacc_hooks/guards/block_host_toolchain_run.py` (`_is_invoked`, lines ~265-281)
- `.claude/rediacc_hooks/guards/test-block_host_toolchain_run.py` (existing NEEDS_ENV/NEEDS_SCRIPT/bare-tool cases, new false-positive case)

Found by writer `acb6821fba4415b3d`, deliberately out of scope for its own change (the devbox-toolchain-guard-extension plan). A first quick-fix attempt and its revert are recorded above so the next session does not re-discover the same dead end.
