## SESSION d1589e0b 2026-09-05T19:47:47Z

# Wave DONE + org secrets deleted + AWS key leak redacted and ROTATED

## Next action
**Nothing tracked, nothing in flight.** `main` = **56e640324**, tree clean,
`ci:quick` **310/310**. Two things want the operator:

1. **`BWS_ACCESS_TOKEN` EXPIRES 2026-09-08** (3 days). Only the operator can mint
   a replacement — no `bws` verb rotates a machine-account token. Everything
   Bitwarden-backed dies when it lapses. Update `.ci/config/bws-token-expiry.json`.
2. **The `gh`-removal plan is still owed.** See "owed work" below.

## Done this session
PR #585 MERGED · Edge GREEN · **Production GREEN** (soak skipped) — the chain that
had failed 5 consecutive times. Then, on operator rulings:
- **All 45 org secrets DELETED**; `orgs/rediacc/actions/secrets` is EMPTY. Survivors
  are repo-level: `BWS_ACCESS_TOKEN` (bootstrap) + `BREAKPOINT_TUNNEL_TOKEN`.
- **ASIA SES synced from EU** (AWS issues no ASIA identity), hash-verified.
- **AWS key ids were published** in tracked `agent/PLAN-secret-namespace-migration.md`
  in a PUBLIC repo → redacted, and **ses-eu + ses-us ROTATED** (private/account
  `65820fd`). Secret halves were never exposed; ids alone cannot authenticate.

## Traps paid for — do not re-learn
- **`rotate.ts` pushes `github_secret_names` UNCONDITIONALLY**, not from the
  `consumers` list. Checking `consumers` says nothing. Rotation RESURRECTED 4 org
  secrets; they were deleted again.
- **`git show HEAD:f > f` to undo an edit destroyed the manifest a rotation had
  just written.** AWS state was real, the record wasn't. **Recovery: Bitwarden** —
  it holds pushed key ids, so live truth is readable.
- **A plan box's TEXT is its identity.** Ticking while rewriting the text reads as
  DELETED. `- [?]` is NOT honoured by `check_plan_boxes.py` despite its own advice.
- **R2 EU buckets need the `cf-r2-jurisdiction: eu` HEADER**; `?jurisdiction=eu`
  as a query param is silently ignored. All 12 buckets exist.
- **4 secret sources**, assuming one is complete caused 3 false "unrecoverable"
  reports: `bws-secret-map.json` (58) · `github-secret-preimage.json` (17 aliases) ·
  personal vault `github.com`/`mfbayraktar@live.com` via `~/.bw-session` (36 fields,
  **35 already mirrored** into SM) · `private/account/.env` (49 keys).
- `bws` is NOT in the running devbox image; install per `.devcontainer/Dockerfile:492`.
  No `aws`/`boto3`. Use Cloudflare REST with `CF_EMAIL`+`CF_GLOBAL_API_KEY`.

## Owed work
- **The missing gate**: nothing scans tracked files for credential patterns. Six
  secret gates exist; only `check-env-credential-drift.ts` knows `AKIA` and only as
  test fixtures. Write it shrink-only.
- **`gh`-removal plan**: stripping `githubSecretNames` from the manifest +
  `lib/config.ts` breaks 4 tests in `rotation-bitwarden-names.test.ts` that encode
  the old GitHub↔Bitwarden mapping. I made the change and REVERTED it. `cf-breakpoint`
  must KEEP its `gh` path (`BREAKPOINT_TUNNEL_TOKEN` still exists).
- **147 org-scope reads** resolve to the empty string; `check:ci-secret-scope` (310th
  gate) freezes the set, so migration can only shrink it. Already drained 2.
- **#587** npm 11 · **#588** effort-cap steps 4-6 · `breakpoint.yml` reshape (it must
  never fetch: `bws-secrets` exports to GITHUB_ENV and its later step is a debug
  shell) · wire `run.sh setup` to `bws_env_load` (`.ci/lib/bws-env.sh` exists; 19 of
  49 `.env` keys are already in Bitwarden).

## Operator caps
Max **3 background workers**. "Commit ALL files, not just your changes."
