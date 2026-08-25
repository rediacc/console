## SESSION 854ac1c6 2026-08-25T12:34:00Z

Branch `0825-1`. The approved plan (`~/.claude/plans/let-s-make-a-new-glimmering-starlight.md`) is **fully implemented**: one pinned gate toolchain, a container-by-default lane, and `run.sh` tests in `ci.yml`. **NOTHING IS COMMITTED — the operator said "do not commit, I'll have additional requests" and has not lifted it.**

## Why any of this exists (measured, not assumed)

| tool | pin | host had | devbox |
|---|---|---|---|
| shellcheck | 0.10.0 | 0.9.0 | absent |
| go | 1.26.4 | 1.25.13 | ok |
| node | 22 | 24.14.0 | ok |

The container already matches CI; the host is the outlier. Plus a live vacuous green: `quality_all` logged a warning and returned SUCCESS when shfmt was missing, so on any non-Debian host `./run.sh quality all` reported green having run no shell gate.

## Done, all verified by running it

- **`.devcontainer/toolchain.env`** — 7 pins, the only place a gate tool's version is written (ruff was defined twice, PyYAML four times, shfmt/shellcheck nowhere). It lives there because the image build context IS `.devcontainer/`.
- **`.ci/scripts/lib/toolchain.sh`** — load/probe/check/**acquire** + `--report|--verify|--env`. `--env` exists because `$GITHUB_ENV` rejects non-KEY=value lines. shfmt via `go install @vX` when Go exists, else a checksummed binary; shellcheck via checksummed download.
- **Gates run the PINNED binary**: `.ci/scripts/security/{shfmt,shellcheck}.sh`, and `fix_shell` too (it used to format with a different shfmt than the gate verified with).
- **Lane**: `gate_lane_decide` / `gate_lane_reexec` in `.ci/lib/local-common.sh`; `quality` routes; sticky `gate_lane` in `.devbox-state`. `devbox_exec` + `devbox_mount_ok/identity_ok/writable_ok` + `./run.sh devbox exec|doctor`.
- **Gates added**: `check:ci-toolchain-pins`, `check:ci-hook-integrity`, `check:ci-watch-recipe` — all three-point wired, parity green.
- **`ci.yml` job `run-sh-tests`** (bare checkout, 5 min) runs `test-run-sh.sh` (14 controls), `test-devbox-probes.sh` (8), `test-toolchain.sh` (15). Wired into `ci-complete` needs + `RESULT_RUN_SH_TESTS`, tiered HARD_REQUIRED.
- Held from earlier: `wl_ci.py` adhoc_watch fixes + `test-adhoc-watch.py` (15 controls).

## Findings worth not rediscovering

- **shellcheck 0.10.0 OOM-killed a 453-file run** (3074 MB) on this 6.6 GB box. Cause was ONE file: `test-worklist-v5.sh` at 11,955 lines costs **2714 MB** with dataflow on, **199 MB** with the `# shellcheck extended-analysis=false` directive. Batching does NOT fix it; the directive does. Whole gate now peaks 275.8 MB.
- **CI Static lane is a BARE CHECKOUT — no Go.** A Go-only shfmt acquisition cannot run there; hence the checksummed-binary fallback. `xz` is a named precondition for shellcheck (used nowhere else in this repo).
- A comment whose FIRST word is `shellcheck` is parsed as a DIRECTIVE (SC1073). Hit three times in one session.
- `run.sh` sources `devbox.sh` LAZILY, so `devbox_*` helpers are undefined in most arms; an undefined function returns non-zero, which read as "no container" and silently degraded the lane.

## Next action

1. **`#a582c47d` is a `[?]` awaiting the operator**: commit the wave, or keep holding. DEFAULT: keep holding. If the operator says commit, land it as ONE commit (32+ files) and say the two `wl_ci.py` fixes ride along.
2. Before any commit, re-run: `bash .ci/scripts/quality/check-toolchain-pins.sh`, `check-hook-integrity.sh`, `check-ci-watch-recipe.sh`, `check-ci-job-aggregation.sh`, `.ci/scripts/security/actionlint.sh`, `npx tsx scripts/check-ci-parity.ts`, and the three gate-tests. All were green at last run.
3. `.ci/scripts/lib/toolchain.sh --report` is the one command that shows a lane's drift; run it in both lanes if anything looks off.
4. shfmt lives at `~/.local/bin/shfmt` (hand-installed); pinned tools cache under `/tmp/rediacc-toolchain/`.
