## SESSION 9d92d9b6 2026-08-27T14:48:06Z

# Wave 0827-1 — enforcement layer, epic `f2757830`, PR #579

Inline `/pr-babysit` on branch `0827-1`. Round log:
`~/.claude/projects/-home-developer-console/reports/pr-babysit-0827-1.md`
(read the wave header + STATUS + DECISIONS before touching anything).

## Commits on top of `origin/0827-1` (= `f05ea28fc`)

    b425a74f1  base-ref precondition controls
    219707ac9  PR-body guard covers `gh pr create`
    72b25952f  ...and reads its flags per segment, not line-wide
    cd9d2c7b0  trailer gate no longer judges the synthetic merge commit
    06b3c8244  ...and its fetch sends an explicit refspec
    3eb2e5e08  fixture identity per git dir + non-interactive run_git
    e91e21399  CI reports that a rebase is needed; it no longer performs one
    a1e1dd27c  --git help text vs the dispatch; a suite that cannot run says so

`e91e21399` is the operator's own ask: the `rediacc-ci-cd` bot was rebasing and
force-pushing PR branches from `check-branch.sh`. Detection stays (now via
`git merge-tree --write-tree`, which touches no ref), the write is gone, and
`preset: push` is deleted from the app-token action.

## The constraint that shapes every commit here

Another session (`e580532b`) is working in this same tree — `.claude/settings.json`,
`scripts/data/hook-inventory-baseline.json`, `run.sh`, `.ci/docker/`,
`packages/www/**`, `agent/e580532b/`, `agent/programs/clarity-round6/`,
`block-agent-browser-repo-output.sh`, and fourteen lines inside
`.claude/hooks/test-hooks.sh`.

**Stage by explicit path, never `git add -A`.** `test-hooks.sh` is shared: my
hunks were committed by index surgery (`git hash-object -w` +
`git update-index --cacheinfo`), leaving their lines uncommitted in the working
tree. If you touch it again, do the same and diff the committed blob against
HEAD afterwards to prove only your hunks landed.

## Verified, and how

- `test-hooks.sh` — harness green, 1507 offline cases (CI last saw 1481 with 2 FAIL).
- `test-rebase-resolve.sh` 9/9, `test-swallowed-failures.sh` 22/0,
  `test-scrub-sentinel-empty.sh` clean — all under `HOME=<empty>
  GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null`, which is what
  reproduced the runner's missing git identity.
- `wl_git.py --selftest` 60 (was 54); `check-pr-task-trailers.ts --selftest` 18
  (was 10).
- `check:ci-parity`, `check:ci-actionlint`, `check:ci-workflow-invariants`,
  `check:ci-hook-integrity`, `check:ci-pipefail-grep-q`, `check:ci-watch-recipe`
  — all pass.

Every new control is paired, and four reproduce the actual defect: a parentless
commit reading as a merge is not excluded by `--no-merges`; a bare fetch under a
narrow refspec leaves the tracking ref absent; a blocking `core.editor` hangs
plain git; deleting one verb from `USAGE` reddens exactly one arm.

## Known local red that is NOT ours

`check-dead-bash` reports `.ci/docker/run-in-render.sh` as unreferenced. That
file is UNTRACKED and belongs to `e580532b`, so CI never sees it. Do not
"fix" it.

## Next action

Push the eight commits and watch CI on PR #579. Do not merge, do not push `main`.
