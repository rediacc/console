## SESSION 74de73ca 2026-09-03T15:32:17Z

Branch `0903-1`, PR #585, epic `24c98380`. **PUSHED** through `d7ffdbfda`; renet submodule
pushed through `6c85007` (its PR is rediacc/renet#110, open on the same branch). Working
tree CLEAN. `ci:quick` 292/292 exit 0 on the committed tree.

## The four CI reds fixed since the compaction, and none was the thing its error named

1. `4e74eba82` **check:ci-format-scope mis-tiered.** Asked biome the same question five
   times; memoised to three. The determinism control keeps `fresh=True` so it still runs
   biome twice for real. 11.2s idle, 21.6s contended, so `slow: true`.
2. `04dfbe4a7` **sm-action's one-shot download killed `Initialize`**, which gates every
   other job. It downloads its binary once with no retry and its fallback is `cargo build`
   with cwd = the workspace, so it could never have worked here -- the error named Cargo.
   bws-secrets now pre-places the binary (5 retries, sha256 pinned per triple, version
   read from sm-action's own version.json so a pin bump cannot serve a stale binary). Two
   other single-attempt fetches now retry.
3. `8fbf15c73` **check:i18n was truncating the history the rest of its job depends on.**
   `translation-freshness-git.js` ran `git fetch --depth=50`; on a COMPLETE clone that
   writes a graft and truncates the repo (reproduced: 2467 -> 114 commits, the exact number
   CI reported). `check:ci-plan-housekeeping` then refused four steps later and demanded
   `fetch-depth: 0`, which both checkouts already had. Fixed conditionally, sibling in
   detect-pointer-bump.sh swept, `gate-test:fetch-depth-safety` added, TRAPS entry
   `fetch-depth-truncates-full-clone`.
4. `dd2b2633e` + `d7ffdbfda` **Quality / Go, 24 stdlib advisories.** CI installs Go from
   `go-version-file: private/renet/go.mod`, so that directive IS CI's toolchain, and it
   said 1.26.0 while .devcontainer/Dockerfile pinned 1.26.6. Directive aligned; then
   check:ci-go-module-sync correctly demanded license-mint be re-tidied.

5. `<pending>` **The shallow-history class, swept properly after the judge pushed back.**
   The `--depth` producer side was already closed; the CONSUMER side had one real sibling.
   `age-check.sh:entry_age_days` asks `git log --diff-filter=A` when a suppression line was
   ADDED, and on a truncated history every line is attributed to the graft. Measured on the
   real docker/docker entry in `.go-deps-upgrade-blocklist`: **195 days on a full clone, 2
   days on a truncated one**, with `AGE_WARN_DAYS=180`. Its two consumers (`audit.sh`,
   `check-go-deps.sh`) run in `quality-security` and `quality-go`, which had **no
   `fetch-depth` at all** -- so the gates whose whole job is expiring stale suppressions had
   been green for a reason unrelated to the suppressions. Fixed three ways: the library now
   prints -1 for CANNOT-VERIFY and `check_entry_age` refuses in CI / warns locally; both jobs
   got `fetch-depth: 0` + `filter: blob:none`; and `check_git_history_depth.py` now states the
   blind spot that hid it (it cannot follow a `source`d library, and teaching it to would be
   the reverted npm-key hop by another name). The gate now emits a warning it could never
   emit before: "github.com/docker/docker ... 195 days old (>180) -- due for re-review".
   Only ONE such library exists (`.ci/scripts/lib/` swept; setup.sh and local-common.sh read
   history but no gate sources them).
6. `<pending>` **`gate-test:fetch-depth-safety` failed on its own first CI run**, and the
   worse half passed vacuously: the runner's `init.defaultBranch` is not this machine's, so a
   bare `git init` left origin's HEAD on a nonexistent `master` and the battery ran against a
   1-commit tree -- one case went red honestly, another reported "leaves a full clone full (1
   commits)". The branch is now pinned in three places and the commit count is a hard
   precondition, proven by reproducing with `GIT_CONFIG_GLOBAL` set to `master` and by a
   mutant that fires `FIXTURE BROKEN` three times.

## Two earlier judge findings -- do NOT redo either

- **History-depth gating**: `check:ci-git-history-depth` already covers it. Extending it to
  resolve `npm run <key>` was tried before, measured at 89 unactionable findings, and
  deliberately reverted with a control at line 365. Do not re-add the npm-key hop.
- **check:format determinism**: verified by a real `git clone --depth 1` (1760 files, 0
  fixes, exit 0). `git archive` is NOT a valid stand-in -- `.gitattributes` carries
  `* export-ignore` with only LICENSE exempted, so an archive holds one file.

## Next action

1. **`[?] #13d281a2`** -- org-secret cutover. Its precondition is ONE GREEN CYCLE and there
   has not been one; the three runs before this each died on (2), (3), (4) above. The cycle
   for `d7ffdbfda` is running, watched by bg `b2le11vok` (`ci-trace.py --wait`). When green:
   `scripts/dev/derive-shadow-pass-list.sh --branch 0903-1`, then run exactly the
   `gh secret delete` lines it prints -- today four (ACCOUNT_ED25519_PUBLIC_KEY,
   APP_PRIVATE_KEY, CLOUDFLARE_API_TOKEN, DOCKERHUB_TOKEN), unchanged across re-derivations.
2. **`[?] #475f728c`** -- operator-only. A live 56-char Pexels key is hardcoded at
   `private/growth/video_pipeline/pexels_lib.py:22`; rotation needs the Pexels account.
   Nothing is published today. Do not print the value, and do not delete the line without
   the rotation -- it is in that repo's history from `64167a5`, so deletion buys nothing
   and breaks the documented fallback.
3. Read a failing JOB's conclusion, never the run's. This branch has been fooled twice.
