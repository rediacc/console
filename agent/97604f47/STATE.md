## SESSION 97604f47 2026-08-18T09:22:04Z

## Where things stand

**Backup-storage wave MERGED AND RELEASED.** `main` synced at `6584a8795`,
ahead=0 behind=0, submodules clean. That work is closed.

**Tree is UNCOMMITTED and holds the operator's WIP.** Operator, verbatim: "do
not commit or do not discard any of them. WIP" / "keep changes local do not
commit". Do not commit, stage, branch, or checkout/restore/stash anything.

## The operator answered three questions (AskUserQuestion)

Rename -> "Rename only". Credentials -> "Mint it now". Pool gate -> "Build it
locally, no branch". Two of the three are now DONE.

## DONE

- **`cf-r2-backup` token MINTED** (`#a90a8649`). id
  `deb56d2eeedff3558888559972514d65`, provably scoped to `rediacc-backups-probe`
  ONLY. Live-proven: SigV4 S3 ListObjectsV2 -> HTTP 200. Four org secrets
  `BACKUP_S3_{ENDPOINT,BUCKET,ACCESS_KEY_ID,SECRET_ACCESS_KEY}` set,
  visibility=selected, reader set exactly `console`. Token value shredded.
  **DO NOT RE-MINT.** Still operator-only: `wrangler secret put` on the LIVE prod
  worker, and machine migration/cutover.
- **CF rename DONE** (`#0ddaa77a`). `CF_API_KEY` -> `CF_GLOBAL_API_KEY` across
  console + the `private/account` submodule. `credentials.ts:92` reads the new
  name; `.env` 49 -> 48 keys (dead `CF_GLOBAL_API_USR` removed);
  `.env.example:58-60` documents all three CF names as commented EMPTY entries.
  `X-Auth-Key` sites not on the right name: 11 -> 1. That ONE survivor,
  `credentials.ts:160`, is DELIBERATE and unfixable by rename -- it sends the
  header from a FUNCTION PARAMETER, so grep cannot cross the boundary. It was
  verified by EXECUTION instead. Do not "fix" it.
- **Two stop-hook bugs fixed, both mutation-proven**: `--update` on a `[?]` no
  longer drops its `DEFAULT:` (cases 218/218b); `V_INTENT_EXPIRED` no longer
  claims covered work is outstanding when it is closed (`wl_checks.py:2786-2806`,
  case 217e).
- **Format gate unblocked**, two files, both flagged as cross-boundary:
  `.ci/scripts/security/shellcheck.sh` (another session's 3h-stale edit; layout
  only, a `;` became a newline, `bash -n` OK) and `test-worklist-v5.sh:1976`
  (one comment-alignment line, not mine). The first was MASKING the second --
  gates here fail serially.

## IN FLIGHT

- **`pool-gate`** writer (`#25be8942` `[>]`): building
  `.ci/scripts/quality/check-pool-writer-safety.sh`. It owns that file plus
  `package.json`, `scripts/ci-runner/manifest.ts`, and I APPROVED it to add one
  step to `.github/workflows/ci-quality.yml` (job `quality-static`). DO NOT EDIT
  THOSE. It refused to register `kind: 'local-only'` because that would be a
  false suppression -- correct call.

## Verified FALSE - do not re-adopt

- "`./run.sh account reset` deletes the global key" -- `.ci/lib/account.sh:802`
  guards it; an existing `.env` gets in-place `_sed_i` preserving user values.
- "bench blocked on credentials / `.env` has only CF_EMAIL" -- that key works.
- The 90 DOTTED `.agent/` citations must NOT be swept: `test-hooks.sh:258`
  asserts the guard BLOCKS that legacy path; the rest are frozen archives.
- `PLAN-promote-mutation-runner` is NOT stranded; its deliverable shipped
  (`mutate-check.sh`, `check:ci-mutate-check` at `package.json:26`). Marked done.

## Next action

1. Collect `pool-gate`'s report. REFUSE it without an external failure control
   it actually ran, and make it say whether its "3 registered writers" are
   already in `WRITER_TESTS` or are genuine misregistrations (a real finding).
2. Confirm the background suite re-run after the whitespace fix is still green
   (expected 745/0).
3. Flag before cutover: `edge-rediacc-backups-us` and `-asia` exist (created
   2026-08-18T05:29Z), there is NO `-eu`; the EU pair reportedly needs
   `--jurisdiction eu`.
4. Unanswered peer question: move `agent/2fd369e0/`, `agent/99ccf057/`,
   `agent/legacy/` under `agent/archive/`? Operator's call.
