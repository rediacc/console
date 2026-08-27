## SESSION 9d92d9b6 2026-08-27T22:36:07Z

Wave 0827-1 — epic `f2757830`, PR #579, still DRAFT. Round log under `reports/`.

## Seven commits on `0827-1`, unpushed

    070096b95  hooks/gates: a name is not a target, a missing tool is not a verdict
    0c3afc742  ci: containerised tts/render/web toolchains
    db9e035d2  www: solution-page density pass + currency-integrity gate
    5fc385241  agent: session state
    5106ce6f4  pr: epic snapshot refresh
    799410a65  ci: two reds the quick lane could not see
    929cdb380  agent: STATE.md for a session that knows nothing

All seven carry `PR-TASK: f2757830`. `0081ab315` (already HEAD when this session
resumed) does NOT — bash executed the backticks in its `git commit -m`.

UNCOMMITTED right now: `scripts/ci-runner/run.ts` (the `stable` field, below),
`.dead-bash-allowlist`, and new `.ci/scripts/test/manual/probe-receipt-stability.sh`.

## In CI, exactly ONE gate fails

`check:ci-pr-task-trailers`, on that missing trailer. Everything else that looks
red locally was probed, not assumed:

- `check:ci-renet` — host go is 1.26.4; CI installs go1.25.13 via `go-version-file`
  on `private/renet/go.mod`. Same-moment govulncheck: 1.26.4 = 9 vulns,
  1.26.6 = 2, 1.25.13 = 2, the two being `GO-2026-4883/4887` (docker/docker,
  `Fixed in: N/A`) which `.ci/scripts/quality/security.sh:89` suppresses.
- `check:ci-python-lint` — BLOCKED here (no ruff); passes in the devbox and CI.
- `check:test-workers` — `workers/www` is NOT a root workspace, its node_modules
  is absent locally, and CI runs `npm ci --prefix workers/www` first
  (`.github/workflows/ci-quality.yml:1479`).

## THE MEASUREMENT TRAP THAT COST TWO 12-MINUTE RUNS

**This worktree is SHARED with a live peer session, and a whole-lane run takes
~12 minutes.** Anything a peer touches inside that window flips gates red that
pass standalone before and after. `check:lint`, `check:ci-toolchain-pins`,
`check:ci-browser-smoke` and `check:ci-ssr-locale` failed in BOTH whole-lane runs
and pass standalone every time. Proof it was not the code:
`check-toolchain-pins.sh` derives ROOT from BASH_SOURCE, nothing writes
`.devcontainer/Dockerfile`, and its `COPY toolchain.env` is at line 222 of the
very commit under test.

Also: **the quick lane defers 62 gates.** Reporting lane health from `ci:quick`
is how this session claimed "green but for one gate" and was wrong.

## The receipt now says whether the tree held still

`run.ts` sampled `dirtyDigest()` only at start, so mid-run churn was invisible.
It now samples again at the end, records `stable`, and warns by name. Proven both
ways; the probe is `.ci/scripts/test/manual/probe-receipt-stability.sh`.
Deliberately NOT a CI gate — it must plant a change while a lane is in flight, so
any automated form races the gate it times. It also does NOT detect an edit made
and reverted inside the window; two samples cannot.

## The renet fix is committed but NOT in this PR

`3f49e09` on submodule branch `0827-1`. Console pointer deliberately restored to
`dbdbeb884`: `check-submodule-branches.sh` requires a pointer change to carry a
matching branch AND a linked submodule PR. Commit is anchored to its branch ref.

## Next action

1. Confirm `check:ci-dead-bash` accepts the new `manual:` allowlist entry, then
   commit `run.ts` + allowlist + probe.
2. Then `[?] #9e2c9d54`: either the operator's rebase reword of `0081ab315` (CI
   goes green outright) or, on DEFAULT, build the named-carried-reds receipt —
   named+justified reds only, unnamed still refused, an entry refused once its
   gate goes green — design drafted in the scratchpad.
3. `gh pr ready` → Claude review → resolve threads. **Never merge, never push main.**
