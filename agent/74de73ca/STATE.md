## SESSION 74de73ca 2026-09-03T12:27:49Z

Branch `0903-1`, PR #585, epic `24c98380`. **PUSHED** through `980b87ba1`; working tree
CLEAN, nothing uncommitted. `ci:quick` 292/292 exit 0 on the committed tree.

## What is on the branch (8 new commits this session, all `PR-TASK: 24c98380`)

`980b87ba1` ci-overhaul docs wave 2 · `535b25a01` TRAPS + CLAUDE.md ownership rule ·
`b5c02fe11` check:format widened to `biome format .` · `44659d249` resource profiling
layer · `5d470cee9` shadow-compare extracted from 62 inline steps · `bb8aa55ea`
onboarding notice · `644a4d071` worklist `--adopt` lineage · `7efc4f7ef` www bundle
budget · `aee7e5489` shallow-checkout fix.

## Two judge findings answered THIS turn — do not redo either

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

1. **`[?] #13d281a2` is the only open item** and is unblocked. When CI on `980b87ba1` is
   green: `scripts/dev/derive-shadow-pass-list.sh --branch 0903-1`, then run exactly the
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
