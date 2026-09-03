## SESSION 74de73ca 2026-09-03T23:42:35Z

# Session 74de73ca -- state

Branch `0903-1`, PR #585, epic `24c98380`. Head as of this write: 873cce233
(pushed through c770b8ebc; three commits are LOCAL AND UNPUSHED, deliberately --
see "Why the tail is unpushed").

## What landed tonight

- **The secret cutover's wave 1.** 79 consumer reads flipped from
  `secrets.{APP_PRIVATE_KEY,CLOUDFLARE_API_TOKEN,DOCKERHUB_TOKEN}` to
  `env.BWS_*` across 16 workflow files (c770b8ebc). The survey that drove it
  separates four populations, and the one a find-and-replace would have
  destroyed is the 73 `GH_<NAME>:` halves of the comparator steps: flipping
  those makes the shadow compare a value against itself and pass forever.
  Seven jobs needed the Bitwarden fetch MOVED ahead of app-token first.
- **CHECK 6 of check-workflow-gates.sh now states a property, not a name.** A
  step ahead of the watchdog's monitor is admitted when it carries BOTH
  `continue-on-error: true` and `timeout-minutes: <= 5`, both as literals. It
  had no test at all; it has nine assertions now
  (`gate-test:watchdog-monitor-ordering`), and the checker is EXTRACTED from
  the live gate so a copy cannot outlive the original.
- **breakpoint.yml lost its shadow rather than gaining a flip** (cc3b468ed).
  bws-secrets exports through GITHUB_ENV, and this job's later steps hand a
  human a shell -- so the shadow was promoting the App private key, the tunnel
  token and the SES EU pair from step scope to that shell. `check_bws_map.py`
  gained a `no_fetch_jobs` key to say so per-JOB, since its old escape hatch is
  keyed by secret NAME and would have quieted all 20 files.
- **private/account's Dockerfile stopped building today** on an npm 10 arborist
  crash from a package published this morning; fixed in the submodule (b0924d1)
  by installing from the root workspace lockfile where npm can, and pinning
  npm@12.0.2 in the two stages where `npm ci` genuinely refuses.
- **Resprofile wave 2 is complete.** `rank()` folds `bash.jsonl` (246 shell
  shapes, and `sh:-c` is now the largest row in the corpus at 57,718 CPU
  seconds); an empty bash corpus is UNJUDGEABLE rather than clean; and the
  retirement trigger no longer counts prose about the layer as work -- caught by
  its own first trailer, one commit after it was written.
- **The retirement tool** (873cce233) writes out the last, irreversible step and
  applies nothing.

## Why the tail is unpushed

CI is mid-flight on c770b8ebc, which is the first run where 79 flipped reads
actually mint tokens from Bitwarden. Every push supersedes that run, and the
answer it is producing is the one that matters. The three commits after it
(cc3b468ed, 2e6877c50, dd4be3790, 873cce233) are green on ci:quick 296/296 and
go out the moment that run reports.

## Next action

Pin the two unpinned global npm installs, which are the same class as tonight's
Docker break: `.devcontainer/Dockerfile:340` installs `@openai/codex` and
`@google/gemini-cli` with no version at all, and `.ci/docker/web/Dockerfile:33`
installs `agent-browser@latest`. Both resolve live at build time, so a package
published this morning breaks the image -- which is exactly what happened to
private/account's shared-build stage today. `gate-test:devcontainer-pin-freshness`
already enforces a pinning discipline these two lines sit outside; check whether
its scope should widen rather than adding two pins it does not watch.

## Remaining

- `[?] #13d281a2` -- retire the three org secrets, or hold. DEFAULT is HOLD and
  it parks no work: everything mechanical is committed and the tool exists.
