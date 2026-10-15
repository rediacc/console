# Review f56ddcde: fix(pins): attribute only generator-written files, draft each repository's own changes, report extraneous installs, and name ungated pins

Commit: f56ddcde1a0daf9a7c0a564e096dfcadded26f58
Repo: console
Branch: 1008-1
Parent: d726e3edc61b9484b357f66490f910bc09ed6818
Patch-Id: 2d4ad9689da29158596f1184124e32338588b223
Reviewed-At: 2026-10-15T02:03:04Z
Model: claude-haiku-5-5
Cost: $0.0117 USD, 1 call(s), 66.3s
Diff: 41504 bytes, 4 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug,feature why=Fixes pins tooling attribution and drafting bugs; adds new internal report lines (ungated pins, extraneous installs) to a dev CLI, not a shipped product feature.
Dropped: 0
Body-Sig: 7561a8158980ab73

## Findings

### f56ddcde.1 [medium] scripts/lib/pins/drivers/npm.ts:490
Anchor: in-diff
Claim: A package-lock.json without a `packages` map (lockfileVersion 1) makes `locked` empty, so every installed package in the hidden lockfile is reported as `installed <v>, not in the lockfile` and every on-disk package as `present in node_modules, not in the lockfile`; the base code reported nothing for such a tree, and no selftest covers a lockfile lacking `packages`.
Resolution: fixed 1ae65ef67bfa66029ff56de59721e312b54afafc | d778be9d 2026-10-15T02:20:34Z

### f56ddcde.2 [medium] scripts/pins/pins.ts:253
Anchor: in-diff
Claim: In a submodule draft whose repository has changed paths but no owning site line, `owners` is empty and the subject falls back to every plan's name, so the subject names pins from other repositories (e.g. `bump npm trees, zed in private/renet: N file(s)`), contrary to the stated rule that a submodule subject names only its own changes; no case exercises this fallback.
Resolution: fixed 1ae65ef67bfa66029ff56de59721e312b54afafc | d778be9d 2026-10-15T02:20:34Z

### f56ddcde.3 [medium] scripts/pins/pins.ts:447
Anchor: in-diff
Claim: If gen-docs regenerates a file without printing a `wrote <file> (<providers>)` line for it, that file is now returned as unclaimed and left out of the add and commit lines (only a note is printed), so the commit can go out with a stale generated doc; this holds only if the generator's output is not complete, which the diff cannot show.
Resolution: not-a-bug | 1ae65ef67bfa66029ff56de59721e312b54afafc records it: a generated file changed without a gen-docs wrote line is printed as an unclaimed note, and the gen-docs pre-commit hook refuses a commit whose generated docs drift from their inputs (it refused the 01:2xZ pins commit for scripts/data/doc-registry.md), so a stale generated doc cannot be committed | d778be9d 2026-10-15T02:20:35Z
