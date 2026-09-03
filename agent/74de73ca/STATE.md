## SESSION 74de73ca 2026-09-03T13:24:23Z

Branch `0903-1`, PR #585, epic `24c98380`. **PUSHED** through `8fbf15c73`; working tree
CLEAN, nothing uncommitted. `ci:quick` 292/292 exit 0 on the committed tree.

## What is on the branch (8 new commits this session, all `PR-TASK: 24c98380`)

`980b87ba1` ci-overhaul docs wave 2 · `535b25a01` TRAPS + CLAUDE.md ownership rule ·
`b5c02fe11` check:format widened to `biome format .` · `44659d249` resource profiling
layer · `5d470cee9` shadow-compare extracted from 62 inline steps · `bb8aa55ea`
onboarding notice · `644a4d071` worklist `--adopt` lineage · `7efc4f7ef` www bundle
budget · `aee7e5489` shallow-checkout fix.

## Three CI reds diagnosed and fixed since the compaction

1. **`check:ci-format-scope` was in the wrong tier** (`4e74eba82`). It asked biome the
   same question up to five times; memoised to three, and the determinism control keeps
   `fresh=True` so it still runs biome twice for real. 11.2s idle, 21.6s under the quick
   lane's 20x contention, so `slow: true` with that measurement as the reason.
2. **sm-action's one-shot download killed the Initialize job** (`04dfbe4a7`), which gates
   every other job in the run. It downloads its binary once, no retry, and its fallback
   is `cargo build` with cwd = the workspace, so it could NEVER have worked here.
   bws-secrets now pre-places the binary (5 retries, sha256 pinned per triple, version
   read from sm-action's own version.json so a pin bump cannot serve a stale binary).
   Two other single-attempt fetches on critical paths now retry too.
3. **`check:i18n` was truncating the history the rest of its job depends on**
   (`8fbf15c73`), and this is the one worth remembering. `translation-freshness-git.js`
   ran `git fetch --depth=50`; on a COMPLETE clone that writes a graft and truncates the
   repository — reproduced against the real remote, 2467 commits to 114, the exact number
   CI reported. Four steps later `check:ci-plan-housekeeping` refused, naming the
   checkout, which was innocent and had `fetch-depth: 0` all along. Fixed, sibling in
   detect-pointer-bump.sh swept, `gate-test:fetch-depth-safety` added, TRAPS entry
   `fetch-depth-truncates-full-clone`. **The tell was arithmetic**: a real shallow
   checkout has a STABLE commit count; `--depth=N` on a full clone leaves N + your
   branch, which grows daily. Three jobs had logged 90, 99, 114 and nobody read it.

4. **`Quality / Go` red on 24 stdlib advisories** (renet `6c85007`, pointer bumped here).
   CI installs Go from `go-version-file: private/renet/go.mod`, so the `go` directive IS
   the toolchain CI runs — and it said `1.26.0` while `.devcontainer/Dockerfile` already
   pinned `ARG GO_VERSION=1.26.6`. Six patch releases of drift, which also meant the
   devbox was not the rehearsal it is supposed to be. Directive aligned to 1.26.6 (the
   highest floor any finding demanded); `run-renet.sh quality` in the devbox exits 0 with
   exactly the six pre-existing no-fix suppressions.

## Two judge findings answered EARLIER — do not redo either

1. **History-depth gating.** `check:ci-git-history-depth` ALREADY gates "a job that reads
   history must have checked out history". I extended it to resolve `npm run <key>` to
   the script's source, and it worked — then found the gate's own docstring (lines 40-55)
   records that this exact hop was tried, measured at **89 unactionable findings**, and
   deliberately REVERTED, with a control at line 365 (`a script written shallow-safe is
   not flagged for being called`) that exists to stop it. My new `quality-go` hit proved
   them right: `check-renet-types.sh:56` feeds `git describe` into `--version` and the
   comparison is `compare_ignoring_version`, so shallowness cannot change the verdict.
   **Reverted; the file is byte-identical to HEAD.** Do not re-add the npm-key hop.
2. **check:format determinism.** Verified empirically, not argued: a real
   `git clone --depth 1` of HEAD formats **1760 files, 0 fixes, exit 0** — identical to
   local. biome is pinned to 2.5.11 in the lockfile and CI installs with `npm ci`; there
   is no biome cache directory. NOTE: `git archive` is NOT a valid stand-in for a CI
   checkout here — `.gitattributes` carries `* export-ignore` with only `LICENSE`
   exempted, so an archive contains one file and any test built on it is vacuous.

## Next action

1. **`[?] #13d281a2` is the only open item.** Its DEFAULT's precondition is ONE GREEN
   CYCLE, and there has not been one yet — 33753814832 died on (2) above and 33757353062
   on (3). The cycle for `8fbf15c73` is running. When it is green: `scripts/dev/derive-shadow-pass-list.sh --branch 0903-1`, then run exactly the
   `gh secret delete` lines it prints — today four (ACCOUNT_ED25519_PUBLIC_KEY,
   APP_PRIVATE_KEY, CLOUDFLARE_API_TOKEN, DOCKERHUB_TOKEN). It refuses if no passing
   compare exists and skips any org name shadowed by a repo-level twin.
2. Read a failing JOB's conclusion, never the run's — a cancelled run reports nothing and
   this branch has been fooled by that twice.
3. `gh pr edit --body` is hook-blocked and `--body-file` fails on a Projects-classic
   deprecation; use `gh api repos/rediacc/console/pulls/585 -X PATCH -F body=@file`, and
   keep the `worklist-epics` AND `pushed-head` marker pairs plus the three submodule PR
   links (dropping those failed CI once already).
4. Commits need `PR-TASK: <epic>` and must NOT carry `Co-Authored-By`.
