## SESSION 9d92d9b6 2026-08-27T22:10:55Z

Wave 0827-1 — epic `f2757830`, PR #579, still DRAFT. Round log under `reports/`.

## Where the work is

SIX commits on `0827-1`, unpushed, tree otherwise clean:

    070096b95  hooks/gates: a name is not a target, a missing tool is not a verdict
    0c3afc742  ci: containerised tts/render/web toolchains
    db9e035d2  www: solution-page density pass + currency-integrity gate
    5fc385241  agent: session state
    5106ce6f4  pr: epic snapshot refresh
    799410a65  ci: two reds the quick lane could not see

All six carry `PR-TASK: f2757830`. `0081ab315` (pre-existing HEAD when this
session resumed) does NOT — bash executed the backticks in its `git commit -m`.

## In CI, exactly ONE gate fails

`check:ci-pr-task-trailers`, on that missing trailer. Everything else that looks
red locally is not a CI problem, and each was probed rather than assumed:

- `check:ci-renet` — red only here. HOST go is 1.26.4; CI installs go1.25.13 via
  `go-version-file` on `private/renet/go.mod`. Same-moment govulncheck in
  throwaway containers: go1.26.4 = 9 vulns, go1.26.6 = 2, go1.25.13 = 2. The two
  are `GO-2026-4883/4887` (docker/docker, `Fixed in: N/A`), already suppressed.
- `check:ci-python-lint` — BLOCKED here (no ruff). Passes in the devbox and CI.
- `check:test-workers` — `workers/www` is NOT a root workspace and its
  node_modules is absent locally; CI runs `npm ci --prefix workers/www` first
  (`ci-quality.yml:1479`). Zero `workers/` files in this wave.

**The quick lane defers 62 gates.** Reporting lane health from `ci:quick` is how
this session claimed "green but for one gate" and was wrong. Use `npm run ci`.

## Two traps this session paid for

1. **Do not change the tree while a lane runs.** Restoring the submodule pointer
   mid-run produced FOUR phantom failures (`check:lint`, `check:ci-toolchain-pins`,
   `check:ci-ssr-locale`, `check:ci-browser-smoke`) that all pass standalone.
2. **Backticks in an unquoted heredoc execute.** It ate the PR-TASK trailer, and
   separately ran `devbox remove` from inside a hook's own refusal message.

## The renet fix is committed but NOT in this PR

`3f49e09` on submodule branch `0827-1` (name must match the console branch or
`/pr-merge` drops it). It fixes a 4-instance class: every quality script installs
a Go tool then invokes it bare, dying at exit 127, because `go install` writes to
`$(go env GOPATH)/bin` which is on no PATH. Fixed once in `.ci/scripts/lib/common.sh`.
CI never hit it — `actions/setup-go` adds that directory itself.

The console pointer is deliberately restored to `dbdbeb884`:
`check-submodule-branches.sh` requires a pointer change to carry a matching
branch AND a linked submodule PR. The commit is anchored to its branch ref, not
orphaned — verified.

## Blocked on the operator

The trailer repair is now a rebase reword (six commits deep) and
`block-git-amend.sh` is an unconditional `exit 2` with no override, so it is not
this session's to run. `block-unverified-push.sh` requires a whole-green receipt,
which that one red prevents.

## Next action

1. Commit this STATE.md, then run `npm run ci` ONCE on a stable tree for a
   receipt that can be trusted — do not touch the tree while it runs.
2. Then either the operator's reword (CI goes green outright), or build the
   named-carried-reds receipt mechanism — named+justified reds only, unnamed
   still refused, an entry refused once its gate goes green — and push with
   `check:ci-pr-task-trailers` named. That is `[?] #9e2c9d54`, DEFAULT executes.
3. `gh pr ready` → Claude review → resolve threads. **Never merge, never push main.**
