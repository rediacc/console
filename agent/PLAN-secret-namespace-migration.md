Status: executing — as of 2026-09-02 EVERY LOCAL PIECE HAS LANDED, uncommitted: the
Worker side, the Bitwarden side (names AND per-secret notes), the CI shadow-run in 61 jobs,
five minted credentials (decision 9), and both backup-family renames (decision 10). What
remains is not migration work. It is (a) LANDING — this cannot be one commit, because the
gates that read across a submodule boundary are green only against the dirty worktrees, so
it needs account, renet and elite committed first and then console with the pointers bumped;
and (b) the GitHub-secret-side rename, which **APPLIED on 2026-09-02 (Part 19)** after the
operator ruled "mint the 5, then apply" -- the tree now carries the new names and the dry run
reports 0 replacements. **CANCELLED as of Part 22**: the operator has directed that GitHub
secrets be DELETED rather than renamed, so `scripts/dev/rename-org-secrets.sh` must NOT be
run. See agent/PLAN-github-secrets-removal.md. It was previously described here as DRY-RUN ONLY, blocked on a
prerequisite rather than a preference: the operator ruled cutover-first, and the cutover has
executed zero times because the work is uncommitted. Re-measured 2026-09-02 against the tree
as it then stood: 1289 replacements in 102 files (down from 1315/106 that morning, because
decision 10 had already moved the backup families out of its path), plus 1 generated file to
regenerate, 2 runtime-constructed lines and 46 Stripe-collapse lines to hand-edit. See
Part 12 for the sed rules, Parts 13-22 for what execution taught, and the execution plan.
**Parts 17-18 are the live ones, and the 18-name gap is CLOSED**: the shadow compared 35 of
53 because the request list was a set intersection, not a coverage rule. Part 17c's gate now
asserts the converse in three directions and the read-without-request class is swept. What
remains is not analysis: three OTLP secrets only the operator can mint, and the `.env` ->
Bitwarden fetch that Part 18 measures as blocking every local `.env` key's removal.

# Secret namespace migration: Bitwarden SM + a project-prefixed naming convention

## Context

The operator has approved a full migration of every CI credential into Bitwarden Secrets
Manager **and** a repo-wide rename onto a project-prefixed convention (`ACCOUNT_`,
`RENET_`, `RDC_`, …). The motivating complaint, in their words: *"we had struggled what is
for what"* — the current names do not say which component owns a credential, and the same
value appears under three different names depending on layer.

This document is the handoff. It carries what is PROVEN, what is DECIDED, and what is
still open, so a session that knows nothing can continue.

---


## Tasks

The canonical, decomposed task list. Everything below is a real unit of work; the evidence
for each one is in the Part it names. Checkbox lines are what `wl_planfid.plan_tasks`
parses, so this list and the worklist must stay in step: one `worklist.py --add` item per
line here. States are `- [ ]` open and `- [x]` done ONLY — a `- [?]` or `- [>]` line is
invisible to the parser and belongs in `## Remaining (operator)` instead.

Prerequisites (5a) — nothing else can start until these land:

- [x] Refactor `rotateCloudflareToken` onto the consumer loop instead of a sixth `slug ===` branch (5a.1). **Done 2026-09-02.** This task's original text — "minting a token, pushing it nowhere and exiting 0" — was WRONG; `rotate.ts:109` rejected the slug before anything was minted. See 5a for the corrected finding.
- [x] Add `cf-r2-media` and `cf-breakpoint` to `KNOWN_CREDENTIAL_SLUGS` (`rotation-manifest.ts:288`, 13 of 15 listed) so `rotate.ts:109`, `deactivate.ts:49` and `delete.ts:37` stop rejecting slugs (5a.2). **Done 2026-09-02**; the real severity was that this check gates all THREE verbs, so both credentials had no retirement path at all.
- [x] Fix backup-bucket region-suffixing as a standalone change ahead of the rename (`#5914a537`) — decision 4. **Done 2026-09-02 by DERIVING from regions.json, not by suffixing secrets**; see Part 3 for why the stated mechanism could not work, and for the credential-scope question that is still the operator's.

The rename, as ONE atomic commit (5e forces atomicity):

- [x] Put the Part 4 open questions to the operator and record the answers here — **all five answered 2026-09-02**, recorded in Part 0. Nothing in Part 4 is open; do not re-ask it.
- [ ] Rename every console occurrence onto the agreed convention in a single commit — `.github/workflows` and `.ci/` are ~75% of ~1,770 hits; `packages/` has 7 and `workers/` has 1 (5e)
- [ ] Rewrite the seven runtime-constructed names by hand, since find-and-replace cannot see them: `set-account-worker-secrets.sh:70-73,79-89`, `cd-deploy-account.yml:249`, `regions.json:15,30,45`, and the `${!var_name}` presence-checkers in `common.sh:133`, `upload-to-r2.sh:147`, `breakpoint-common.sh:178,346`, `assert-ci-complete.sh:65,74` (5e)
- [x] **Done 2026-09-02 (Writer B; the workflow env side is Writer D's, in flight).** Delete the `SECRET_*` / `<PREFIX>_<SUFFIX>` workflow-env shim in `set-{account,www,preview}-worker-secrets.sh` (contract at `:26-41`, consumed at `:92-141`) and have the Worker read the full names, updating the `env.ts` zod schema — decision 2, the fourth namespace
- [x] **Done 2026-09-02 (Writer B for Worker names; Writer E adds explicit `bitwarden_secret_names`).** Update the rotation literals in `scripts/rotation/lib/config.ts:39,54,70,91,97,107,117,133,201,212,222` in the same commit, or `commands/init.ts` reseeds a manifest that disagrees with itself (5b)
- [x] **Done 2026-09-02** (exit 0, 46 references across 3 repos; the gate is now red only on `BWS_ACCESS_TOKEN`, which is absent from the org by design until the operator mints it). Regenerate `.ci/config/secret-reachability.json` with `npm run check:ci-secret-reachability -- --refresh` (needs the org-admin token; carries `MAX_BASELINE_AGE_DAYS=45` and hardcoded `OPTIONAL` entries) — the one gate guaranteed to fail otherwise (5e)

Submodule and sibling-repo coordination, in the same window as the rename:

- [ ] Land the six `private/growth` secrets under provider prefixes — `ELEVENLABS_API_KEY`, `PEXELS_API_KEY`, `MAUTIC_USER`, `MAUTIC_PASS`, `APOLLO_EMAIL`, `APOLLO_PASSWORD` — as a coordinated GitLab commit (decision 6, 5d)
- [ ] Rename growth's five console-secret reads behind their two indirection constructs — `publish-solutions.sh:51-58` (`${!v}` over a name list) and `publish.py:40` (`_R2_ENV_VARS` tuple) — together with console's `.ci/scripts/deploy/upload-media-to-r2.sh`, or growth's guard passes and the upload dies inside `aws` (5d)
- [ ] Rename `TTS_ENGINE` in `private/generative` (`src/tutorial_tts/config.py:116`) and `private/growth` (`step4000_voiceover.py:46`) in the SAME change; growth passes its whole environment through at `:157`, so a one-sided rename silently falls back to a different narration engine (5c)
- [ ] Rename `RDC_GPU_LOCK_FILE` (generative) and `RDC_REMOTION_CONCURRENCY` (growth) out of the `RDC_` prefix — neither has anything to do with the CLI (5c)

Populating `ci-shared` (Part 10's measured gap — 15 absent, 2 copyable, 13 to re-mint):

- [x] ~~Ask the operator for `STRIPE_SECRET_KEY_US`, `STRIPE_SECRET_KEY_ASIA` and `STRIPE_WEBHOOK_SECRET_ASIA`~~ **Done 2026-09-02.** The operator established there is ONE Stripe account, so the two regional secret keys collapse into `STRIPE_SECRET_KEY` (already in ci-shared); `STRIPE_WEBHOOK_SECRET_ASIA` was supplied by the operator and stored. Original text: write them into `ci-shared` — the only three of the 44 absent from every readable source and not mintable locally (decision 8ter)
- [x] Populate `ci-shared` by COPYING every readable value, minting nothing (decision 8ter) — **Done 2026-09-02 under the CURRENT names (39 -> 48, read back and diffed); the rename onto Part 10 targets is Writer C's task, see Part 12**; sources are ci-shared itself, vault `c38d82bb`, vault notes, vault login items, and `.env`
- [x] **Done 2026-09-02** (as `GPG_PRIVATE_KEY`/`GPG_PASSPHRASE`, renamed with the rest). Copy `RELEASE_GPG_PRIVATE_KEY` and `RELEASE_GPG_PASSPHRASE` into `ci-shared` from the vault items `gpg-private.asc - 1`/`- 2` and `passphrase - info@rediacc.com` — verified importable as the published `rsa4096/49BA687F0527C72B` (Part 9); decision 8bis says COPY, not regenerate
- [ ] Generate the GPG revocation certificate that has never existed (`docs/code-signing-guide.md:559` unticked) — the one half of the old GPG finding that survived
- [>] **SCOPE CHANGED by decision 9 (below): FOUR, not six — EU and US only.** ASIA is
  deliberately absent and stays absent. In flight 2026-09-02 as part of the five-credential
  mint. Original text: Re-mint the 6 `AWS_SES_*_{EU,US,ASIA}` into `ci-shared`; `./run.sh rotation rotate ses-eu|ses-us|ses-asia` already pushes them, and ses-asia now refuses until it declares consumers (Part 8)
- [>] **`CLOUDFLARE_API_TOKEN` is in flight 2026-09-02** under decision 9; the `CLOUDFLARE_R2_*`
  trio and `CLOUDFLARE_TURNSTILE_SECRET_KEY` are already present in `ci-shared` (verified against
  the map) and need no mint. Original text: Re-mint the 3 `CLOUDFLARE_R2_*` (`R2_ACCESS_KEY_ID`/`_SECRET_ACCESS_KEY`/`_ENDPOINT`) plus `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_TURNSTILE_SECRET_KEY` into `ci-shared`
- [ ] Supply the 2 operator-only values `DOCKERHUB_USERNAME` and `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` — no console can re-mint the first
- [x] **Settled 2026-09-02: one account, so the secret key has no region; the unsuffixed webhook secret is treated as EU per the operator.** Establish which REGION `ci-shared`'s unsuffixed `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` belong to before either is used as a migration source (Part 10)
- [x] **Done 2026-09-02 (Writer C), id 2b34dfab preserved.** Rename `OTLP_AUTH_TOKEN=USER:PASS` to `OBS_OTLP_CREDENTIALS` in the vault and `ci-shared` — the current name contains `=` and `:` and breaks KEY=VALUE parsing
- [ ] Replace `mc_migrate_claude` before it expires 2026-09-08, renamed `BWS_ACCESS_TOKEN` (target corrected, Part 10) — parked as `[?] #d76f8e3d`, the operator creates the read-only machine account; it is the only Bitwarden WRITE credential

Bitwarden, second (see Sequencing):

- [x] **Done 2026-09-02** (`consumers/bitwarden-sm.ts`, regex in `rotation-manifest.ts`, 4 dispatch sites + `needsBw`, 5 fake-`bws` tests). Add a `bitwarden-sm:` consumer type: extend the consumer-prefix regex at `rotation-manifest.ts:103` and wire the 5 dispatch sites — `rotate.ts:666-696` (turnstile), `:839-881` (otlp), `:1401-1427` (dkim), `pushToConsumer:1662-1707`, and the `needsCf`/`needsGh` capability probes at `:164,410,642,788` (5b)
- [x] **Half done 2026-09-02 (Writer E):** `tests/integration/rotation-bitwarden-names.test.ts` pins every `github_secret_names` entry to a `reachable: true` secret under `repos.console` in the reachability record. STILL OPEN: the conformance leg comparing a live Worker binding's VALUE against the secret. Original: Add the verification nobody has: a gate asserting every `github_secret_names` entry actually exists in the org, plus a conformance leg for worker binding == secret value (`rotation check` never contacts GitHub today; `check-env-credential-drift.ts:175` skips absent keys, so a rename would make it track nothing) (5b)
- [x] **Done 2026-09-02:** 5 fake-`bws` consumer tests, 21 name/manifest/config-agreement tests, 16 dkim-state tests (92 files / 1550 passing). Original: Add rotation test coverage beyond the single vitest file covering `pushWorkerSecret` argv: assert the secret names, the dispatch, the manifest schema, and `check.ts` (5b)

Post-migration cleanup (detail in Part 6):

- [ ] Narrow the `gh` token back to `gist,read:org,repo,workflow` once the reachability baseline is regenerated, and verify by CAPABILITY (`gh api /user/orgs` still works, `gh secret list --org rediacc` starts 403ing) rather than by the scope label (Part 6.1)
- [ ] Delete the old GitHub org secrets once CI reads from Bitwarden — this is what makes decision 3 pay off (Part 6.2)
- [ ] Revoke the predecessor backup R2 credential, identified via the Cloudflare audit log, and narrow `backup-s3-20260901T103133Z` from account-wide R2 write to the backup buckets only (Part 6.3, decision 8)
- [ ] Decide the 3 SMTP orphans — `SMTP_HOST`, `SMTP_PASS`, `SMTP_USER` are org secrets no workflow references: delete them, or document what outside CI uses them (Part 6.4)
- [ ] Rotate the `mc_migrate_claude` machine-account token — created 2026-09-01 with 7-day validity and read-WRITE on `ci-shared`; the long-lived CI tokens must be read-only and per-project (Part 6.5)
- [x] ~~Regenerate the GPG signing key~~ **SUPERSEDED by decision 8bis (Part 9): the key IS readable in the vault and was verified importable as `rsa4096/49BA687F0527C72B`, so it was COPIED, not regenerated.** The revocation certificate remains open as its own item above. Original text: produce a revocation certificate — the pair exists only in the unreadable org store, the local keyring is empty, and `docs/code-signing-guide.md:559` is unticked (Part 3; operator accepted regeneration, no users yet)

---

## Decisions locked by the operator, 2026-09-02 (Part 0)

1. **Provider-named prefixes.** `CLOUDFLARE_`, `DOCKERHUB_`, `AWS_`, `STRIPE_`,
   `ANTHROPIC_` — the vendor is the namespace, because minting and revoking is what you
   actually do with these. Component prefixes (`ACCOUNT_`, `RENET_`, `RDC_`) stay for
   values a component owns.
2. **Unify the namespaces — one name everywhere.** The Worker reads the full name
   directly; the `SECRET_*` shim and the suffix collapse go away. This is the fix for
   "we struggled what is for what".
3. **Bitwarden gets the clean names; GitHub keeps the old ones**, transitionally. No
   org-secret flag-day: old names simply stop being used once CI fetches from Bitwarden,
   then get deleted. Avoids needing `admin:org` for the rename itself.
4. **Backup bucket region-suffixing: fix now, standalone** (`#5914a537`), ahead of the
   rename.
5. **The two rotation defects fold INTO the rename PR** (`#d1cba7e6` — **code written 2026-09-02, uncommitted**; see 5a), not a standalone
   submodule PR. Land the `rotateCloudflareToken` refactor as its own commit inside that PR
   and run the gates between commits, so a red is attributable. Until it lands, **do not run
   `rotate cf-breakpoint`** — it reports success while pushing nothing.
6. **`private/growth`'s six uncovered secrets are IN SCOPE** — `ELEVENLABS_API_KEY`,
   `PEXELS_API_KEY`, `MAUTIC_USER`, `MAUTIC_PASS`, `APOLLO_EMAIL`, `APOLLO_PASSWORD` get
   provider prefixes and go into Bitwarden with the rest. Needs a coordinated commit on the
   GitLab remote.
7. **The leaked `AUTOPILOT_PRIVATE_KEY` stays closed as accepted risk.** Operator confirmed
   the relayed ruling directly on 2026-09-02.
8quater. **OPERATOR RULINGS 2026-09-02, fourth round:**
   - **`STRIPE_WEBHOOK_SECRET_ASIA` stored AS-IS** in `ci-shared` (id
     `d9bfdc91-2366-4e9e-9848-b4b900b6b67b`), exposure accepted. **Every one of the 44 now
     has a readable source; `ci-shared` holds 40.**
   - **Delete both Stripe leftovers — EXECUTED by the operator 2026-09-02.** Webhook
     destination `we_1TPMZ7AH2UKrsSNmJrKlUayY` deleted; standard key `interim`
     (`sk_live_…kui6`, last used 2026-02-25) expired after a step-up 2FA prompt. Verified
     after: the three regional endpoints still Active, the active key `sk_live_…kVQA`
     untouched. Residual the operator flagged: anything still using `…kui6` now fails auth
     (nothing indicated use in 189 days, not checked against application logs), and the
     deleted endpoint's signing secret went with it.

8ter. **OPERATOR RULINGS 2026-09-02, third round** — these set the execution shape:
   - **Naming table ACCEPTED as written** (all four judgement calls in Part 10):
     `BACKUP_S3_* -> CLOUDFLARE_R2_BACKUP_*`, `OTLP_* -> OBS_*`, `GPG_* -> RELEASE_GPG_*`,
     `SES_AK_ID -> AWS_IAM_ADMIN_ACCESS_KEY_ID`. Part 10 is the rename's single input.
     **The first of those four was OVERTURNED later the same day by decision 10:** the
     backup family's target is `ACCOUNT_BACKUP_S3_*`, not `CLOUDFLARE_R2_BACKUP_*`. The
     other three stand.
   - **The unsuffixed Stripe values in SM/vault are EU.** Copy to `STRIPE_SECRET_KEY_EU`
     only; never fan them out to US/ASIA.
   - **POPULATE `ci-shared` FIRST, then rename the codebase.** GitHub stays live and
     untouched as the fallback throughout.
   - **COPY what exists; MINT NOTHING.** The operator's words: "We must use what we have
     already!" So the population pass writes readable values only — including the GPG pair
     from vault notes and `DOCKERHUB_USERNAME` from the `id.docker.com` login item — and
     does NOT rotate to fill regional gaps.
   - **The operator will supply the three genuinely-absent Stripe values** —
     `STRIPE_SECRET_KEY_US`, `STRIPE_SECRET_KEY_ASIA`, `STRIPE_WEBHOOK_SECRET_ASIA`.
   - **`rotate cf-r2` was authorized and is DONE** (see the ticked `#64ae7343`): new token
     `rediacc-r2-20260902T102203Z`, pushed to both org secrets and to `.env`. The
     `rotation sweep` landmine is gone.
   - `#2d728f0a` (SES drift) and `#6716d52f` (turnstile has no manifest versions) keep
     their no-op defaults: reported, not fixed.

8bis. **OPERATOR RULINGS 2026-09-02, second round** (these OVERTURN decision 7's premise):
   - **GPG: COPY, do not regenerate.** The key is in the vault and verified importable as
     the published `rsa4096/49BA687F0527C72B`. Also produce the revocation certificate,
     which is still genuinely missing. Part 3's "regenerate, no users yet" is VOID — it
     rested on my false report that the key existed nowhere readable.
   - **The leaked GPG passphrase is accepted risk**, same ruling as `AUTOPILOT_PRIVATE_KEY`.
     The key material never left the vault; only the passphrase reached the transcript.
   - **Vault `S3_*` IS the backup plane.** `.env-account`'s `S3_ACCESS_KEY_ID`,
     `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`, `S3_ENDPOINT` map to `BACKUP_S3_*` and are
     COPIED, not re-minted.
   - **`c38d82bb` "github.com" is the authoritative vault item.** Diffed against
     `d062dba7` "github.com - cariad": all 30 shared fields byte-identical, ZERO conflicts,
     and `c38d82bb` carries 6 more (AUTOPILOT_*, BREAKPOINT_TUNNEL_TOKEN, R2_MEDIA_*).
     `cariad` is a strict subset — a stale partial copy, safe to ignore.

   **Net effect on the re-mint list: 22 -> 16.** GPG (2) and BACKUP_S3_* (4) are copyable.

8. **R2 token `backup-s3-20260901T103133Z` is kept**, then narrowed to the backup buckets
   only, and the unidentified predecessor credential is found via the Cloudflare audit log
   and revoked. Net effect: one fewer live account-wide R2 token than today.

## What is already true (Part 1 — proven this session, not assumed)

### The migration mechanism works end to end

- Bitwarden org **Rediacc** `61f8e970` has Secrets Manager enabled.
- Project `ci-shared` = `2b5e33f9-b5ae-4ecc-972d-b36f00b0f86a`.
- Machine-account token lives in `private/account/.env` as `mc_migrate_claude`,
  **7-day validity**, read-write on `ci-shared`.
- **39 secrets are already in it**: all 36 custom fields from the personal vault item
  `c38d82bb` (round-trip verified, 0 missing) plus 3 freshly minted R2 backup credentials.

The pipe is `bw get item → jq → normalise → bws secret create`, values crossing a pipe
only. Three implementation facts that only surfaced by doing it:

1. **`bws secret create` needs `--` before its positionals.** A value starting with
   `-----` is parsed as a flag, and the error **echoes the entire value**. This is how
   `AUTOPILOT_PRIVATE_KEY` leaked into a transcript.
2. The normaliser must handle **literal `\n`**, **spaces**, and real newlines.
3. `bws` takes the value on **argv only** — there is no stdin form.

### The migration repaired two keys in flight

Both PEMs were corrupt in the vault, differently: `rediacc-ci-cd.2026-02-01.private-key.pem`
had armor and base64 separated by **spaces**; `AUTOPILOT_PRIVATE_KEY` by **literal `\n`**.
Neither parsed as stored (`openssl` said "Could not find private key"). Both parse when
read back from Secrets Manager. **SM currently holds a more correct copy than the vault.**

### `ACCOUNT_ED25519_*` is the production licence-signing pair — proven, not inferred

Streamed the released `s3://rediacc-releases/cli/stable/rdc-linux-x64` (503 MB) and
grepped: the vault's public key appears **6 times**; the dev key from `.env` appears **0
times** (the control that makes it non-vacuous). That binary carries
`keys.ProductionPublicKey`, injected from `ACCOUNT_ED25519_PUBLIC_KEY` at
`.ci/scripts/build/build-renet.sh:201`. Fingerprint `fb37f1ae16f8b7c0` via
`packages/shared/src/subscription/fingerprint.ts`.

Corroborating: vault `ACCOUNT_X25519_PUBLIC_KEY` equals `~/.config/rediacc/rediacc.json`
`account.e2ePublicKey` byte-for-byte (server `edge-eu.rediacc.com`, fp `ee936479b32d3162`);
dev differs. **renet contains ZERO X25519 references** — X25519 is the CLI config-encryption
key, ED25519 is the licence key. Worth stating because it was a live question.

### Do NOT re-derive coverage with a name-equality diff (added 2026-09-02)

`agent/a276391d/secret-mapping.md` is the authoritative map and it is NOT reproducible by
intersecting name sets. Doing exactly that this session produced "29 have no Bitwarden
copy", which is wrong by 7. Two reasons, both recorded in that file:

- **Two cross-name aliases.** `rediacc-ci-cd.2026-02-01.private-key.pem` IS
  `APP_PRIVATE_KEY`; `DOCKERHUB_TOKEN_GITHUB` IS `DOCKERHUB_TOKEN`.
- **Five are covered by an exact `.env` key name**, not by the vault at all.

And a third trap on the input side: `.ci/config/secret-reachability.json` lists secrets
**referenced by workflows**, not the org's secret list. The three SMTP orphans are org
secrets that appear in neither. Do not use it as "the GitHub secrets".

The real split is **17 vault (incl. the 2 aliases) + 5 `.env`-only + 22 with no readable
source = 44**. The 22 must be RE-MINTED, never copied.

### Where every value comes from (44 migratable; `GITHUB_TOKEN` never migrates)

| Source | Count | Operator effort |
|---|---|---|
| Already in the vault | 17 | none |
| `.env`, not environment-split so the value is real | 5 | none |
| `./run.sh rotation rotate <slug>` can re-mint and push | 16 | none — admin creds already in `.env` |
| **Operator only** | **11** | 4 Stripe (revealable), **3** `BACKUP_S3_*`, `ANTHROPIC_API_KEY`, `DOCKERHUB_USERNAME`, 2 GPG |

(Was 12 with 4 `BACKUP_S3_*`. `BACKUP_S3_BUCKET` stopped being a secret on 2026-09-02 — it is derived from `regions.json` now, see Part 3 — so it is neither migratable nor operator work.)

`gh secret` has **no `get`** — Actions secrets are decryptable only inside a runner. The
migration is a re-mint, never a copy. Only **2** secrets are repo-level
(`BREAKPOINT_TUNNEL_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`); the other ~42 are org-level and
need `admin:org` even to enumerate.

### Cloudflare access is working

`CF_EMAIL` + `CF_GLOBAL_API_KEY` in `private/account/.env` authenticate against account
`fa51e4a18d553c30e1633288e9733d04` ("Rediacc OÜ"). Minted token
`backup-s3-20260901T103133Z` (account-scoped `Workers R2 Storage Write`, matching the three
existing R2 tokens). Derived S3 credentials verified live with `aws s3 ls`. **The OLD
backup credential is still active and unidentified** — none of the six tokens is named for
backups.

---

## The three name-spaces (Part 2 — this is the actual problem)

The same value carries different names at each layer, and nothing reconciles them:

| GitHub Actions | Cloudflare Worker / `.env` | renet (Go) |
|---|---|---|
| `ACCOUNT_ED25519_PRIVATE_KEY` | `ED25519_PRIVATE_KEY` | — |
| `ACCOUNT_ED25519_PUBLIC_KEY` | `ED25519_PUBLIC_KEY` | `keys.ProductionPublicKey` (ldflags) |
| `ACCOUNT_X25519_PRIVATE_KEY` | `X25519_PRIVATE_KEY` | — |
| `ACCOUNT_JWT_SECRET` | `JWT_SECRET` | — |
| `ACCOUNT_SERVER_API_KEY` | `API_KEY` | — |
| `STRIPE_SECRET_KEY_{EU,US,ASIA}` | `STRIPE_SECRET_KEY` | — |
| `STRIPE_WEBHOOK_SECRET_{EU,US,ASIA}` | `STRIPE_WEBHOOK_SECRET` | — |
| `AWS_SES_ACCESS_KEY_ID_{EU,US}` | `AWS_SES_ACCESS_KEY_ID` | — |
| `OTLP_CLIENT_CREDENTIALS_{EU,US,ASIA}` | `OTLP_CLIENT_CREDENTIALS` | — |

The translation table is `.ci/scripts/deploy/set-account-worker-secrets.sh`. The personal
vault **mixes both conventions**, which is exactly the confusion the rename must end.

### `private/account/.env`, measured 2026-09-02 — it MIXES both conventions

This section used to say `.env` "uses the WORKER names throughout". That is **not right**,
and the exceptions are the interesting part. Measured by extracting names only (never
values) from the live file: **50 assignments**, against 43 GitHub secret names known to
`.ci/config/secret-reachability.json` and 88 keys in the Worker's zod schema
(`private/account/src/types/env.ts`).

**10 of the 50 are spelled EXACTLY like the GitHub secret, not like the Worker binding:**
`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT`, `R2_MEDIA_ACCESS_KEY_ID`,
`R2_MEDIA_SECRET_ACCESS_KEY`, `R2_MEDIA_ENDPOINT`, `TURNSTILE_SECRET_KEY`,
`BREAKPOINT_TUNNEL_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`, `AUTOPILOT_PRIVATE_KEY`. So `.env`
mixes the two conventions exactly as the personal vault does — the same confusion, in a
third place. Any rename must treat `.env` as a genuine namespace, not as a mirror of the
Worker's.

The collapse cases the table above predicts DO hold: `.env` carries `AWS_SES_ACCESS_KEY_ID`,
`OTLP_CLIENT_CREDENTIALS` and `STRIPE_WEBHOOK_SECRET` **unsuffixed**, against the
`_{EU,US,ASIA}` triples in GitHub.

**`.env` carries values that exist in NO other namespace** — operator-only admin
credentials and local config, which is why they are invisible to a `secrets.X` sweep:
`SES_AK_ID`, `SES_AK_SECRET` (the rotation tool's AWS admin), `CF_GLOBAL_API_KEY`,
`CF_EMAIL` (its Cloudflare fallback), `AUTOPILOT_APP_ID`, `R2_MEDIA_BUCKET`,
`UPSTREAM_{URL,API_KEY,PUBLIC_KEY}`, `WEBAUTHN_{ORIGIN,RP_ID,RP_NAME}`,
`REDIACC_ACCOUNT_SERVER`, `DATABASE_PATH`, `PORT`, `CI_MODE`, `OTEL_ENDPOINT`, `ROOT_EMAIL`,
and `mc_migrate_claude`.

**`mc_migrate_claude` is the only lowercase name in the file** — a Bitwarden machine-account
token in a file of SCREAMING_SNAKE. It is non-conforming twice over: by case, and by not
naming its provider. Part 6.5 already tracks rotating it; note the **deadline**: created
2026-09-01 with 7-day validity, so it **expires 2026-09-08**.

**`.env` contains NO `BACKUP_S3_*` at all.** Worth stating plainly as a blind spot on the
backup work done 2026-09-02: local dev has no backup-plane credentials, so nothing on this
machine exercises the presign path that was changed. It was verified by gates and by
driving the deploy script's logic directly, never against a live R2.

**`.env.example` documented 22 of the 50 names, so 33 were undocumented — COMPLETED
2026-09-02**, and it now documents all 50 (verified: zero undocumented). Values are empty
placeholders or non-secret defaults; nothing was copied out of `.env`.
The measurement, for the record: (A first count
said 40; it was wrong because the template documents many names as COMMENTED lines and the
extractor skipped them. Corrected by counting `^#? ?NAME=`.) Part 5e lists `.env.example`
as a rename surface, and renaming a template that is 60% incomplete carries the
incompleteness forward — so it is worth completing FIRST.

Two of the 33 are worth naming individually:

- **`X25519_PRIVATE_KEY` / `X25519_PUBLIC_KEY` are undocumented**, while their `ED25519_*`
  siblings are documented WITH a `npm run generate-keys` hint. These are the CLI
  config-encryption keys (Part 1), so a fresh checkout gets a working licence-signing pair
  and silently no config-encryption pair.
- **`CLOUDFLARE_API_TOKEN` is documented but NOT set**, so every local Cloudflare consumer
  falls through to `CF_GLOBAL_API_KEY` — the classic Global API Key, full account access,
  which the template itself describes as "fallback only". Setting the scoped token locally
  would shrink the blast radius of this file considerably. Operator's call, not a defect.

Boolean probes confirming it is one single-region dev instance rather than a mirror of CI:
3 localhost URLs, zero `sk_live_`, `CI_MODE` set. (Part 1 recorded "one `sk_test_`" — that
was reading the literal placeholder `sk_test_...`, 11 characters, copied from the template.
Stripe sandbox is not configured locally at all.)

### Two gate findings that came out of reading `.env` (2026-09-02)

- **`check:env-credential-drift` tracked a category error, now fixed.** Its `TRACKED` list
  checked `SES_AK_ID` against the `ses-eu`/`ses-us`/`ses-asia` slugs. But `SES_AK_ID` is the
  AWS **IAM admin** credential the rotation tool uses to create and delete the SES sending
  keys (`scripts/rotation/lib/credentials.ts:59-61`), not a sending key itself. No manifest
  slug records it and none can, so the check could never pass — a permanently red gate,
  which is worse than one that cannot fail because it teaches you to skip the output.
  Removed, with the honest consequence stated in the source: **the admin credential is
  outside the rotation record entirely, so nothing tracks its age.** Closing that means an
  `aws-admin` slug in the manifest — operator's call.
- **One real drift survives and is the operator's** (`[?] #2d728f0a`): `.env`'s
  `AWS_SES_ACCESS_KEY_ID` matches no version the manifest records for any `ses-*` slug.
  Either a stale key or a separate never-rotated dev key. Resolving it needs
  `rotation rotate ses-eu` (mints and pushes a real AWS key) or a paste from the AWS
  console. The gate is local-only, not in CI, so nothing is blocked meanwhile.

---

## Defects found on the way (Part 3), and their status

| Defect | Evidence | Status |
|---|---|---|
| `AUTOPILOT_PRIVATE_KEY` leaked into a transcript | `bws` parser echoed it | **`[?] #76f6f55e`** — operator must rotate |
| `GPG_PRIVATE_KEY`/`GPG_PASSPHRASE` exist ONLY in the unreadable org store; local keyring empty; no revocation cert (`docs/code-signing-guide.md:559` unticked) | published half is `rsa4096/49BA687F0527C72B` | Operator accepted: **regenerate**, no users yet |
| `BACKUP_S3_BUCKET`/`_ENDPOINT` are single global secrets while R2 bindings are **per-region and EU-jurisdiction-locked** | `cd-deploy-account.yml:296-297` justifies not suffixing the CREDENTIAL then applies it to the BUCKET too; `backup-chunk-store.ts:980` uses the value verbatim | **DONE 2026-09-02** — see the passage below; fixed by derivation, not by suffixing |
| `cd-stage.yml` piped nfpm into `sudo tar` while sibling `ci.yml:810` already verified the same pin | class-sweep miss by a prior session | **Fixed** |
| `ci-build-renet.yml` pulled golangci-lint's installer from the `master` branch | moving target piped to `sh` | **Fixed** (pinned to the release tag) |
| 5 Dockerfile downloads unverified; ttyd pinned by a mutable tag | — | **Fixed** + gate `check:ci-unverified-downloads` |

On the backup bucket specifically — **SETTLED 2026-09-02, no provisioning needed.**
The EU buckets exist. A default-jurisdiction listing simply does not show them; sending
`cf-r2-jurisdiction: eu` to
`/accounts/fa51e4a18d553c30e1633288e9733d04/r2/buckets` returns `rediacc-backups-eu`,
`edge-rediacc-backups-eu`, `rediacc-configs-eu` and `edge-rediacc-configs-eu`. The
absence was a listing artifact exactly as predicted, so ignore any instruction to
settle it with `npx wrangler r2 bucket list --jurisdiction eu`; that question is closed.

The real defect survives, and it is **two secrets wide, not one**:

- `BACKUP_S3_BUCKET` — one global name against seven per-region bindings, so clients PUT
  to bucket A while `BackupGcService` lists and deletes in bucket B.
- `BACKUP_S3_ENDPOINT` — **needs region-suffixing too, and the plan previously missed
  this entirely.** An EU-jurisdiction bucket is reachable ONLY at
  `<account>.eu.r2.cloudflarestorage.com`, and that hostname form appears **nowhere in
  the repo** (`backup-chunk-store.ts:560,595` and `.ci/docs/r2-setup.md:35` all use the
  default form). A correct bucket name against a global endpoint still fails, so fixing
  the bucket alone would produce a green-looking change that does not work.

Never shipped — `docs/backup-storage/CHECKLIST.md:49` leaves w8 open.

**DONE 2026-09-02, and NOT by suffixing secrets.** The plan said "region-suffix the
two secrets via `matrix.secretSuffix`". That mechanism cannot express this problem and
was abandoned once the evidence was in, for two reasons found while implementing:

1. **The matrix is six wide, not three.** `secretSuffix` is `EU`/`US`/`ASIA`, but each
   region has a *stable* and an *edge* bucket (`rediacc-backups-eu` and
   `edge-rediacc-backups-eu`). Suffixing would have needed six new org secrets, which
   needs org-admin — turning a standalone fix into one blocked on the operator.
2. **A bucket name is not a secret.** All six names are already committed in
   `workers/account/wrangler.*.toml` as the `BACKUP_BUCKET` binding. Carrying one of
   them as a global secret is precisely what let the two halves drift.

So the bucket is now **derived**, and `BACKUP_S3_BUCKET` is gone from the secret
plumbing entirely (clean break, no fallback):

- `regions.json` gains `backupR2` / `edgeBackupR2` / `r2Jurisdiction`, the missing
  siblings of the `r2` / `edgeR2` fields that were already there; mirrored to
  `packages/shared/src/regions/data.json` (`check:ci-regions-sync` holds them together).
- `cd-deploy-account.yml` drops the `BACKUP_S3_BUCKET` secret declaration, adds the
  three fields to the matrix jq, and passes `BACKUP_BUCKET_STABLE`,
  `BACKUP_BUCKET_EDGE` and `R2_JURISDICTION` from the matrix. The pass-throughs in
  `cd-v2.yml` (×2) and `promote-stable.yml` went in the same change — `check:ci-workflow-gates`
  CHECK 2 forces that atomicity, and confirms it green.
- `set-account-worker-secrets.sh` picks the bucket by `TARGET`, **fails loudly on an
  empty one** (`backup-chunk-store.ts:980` reads `?? ''`, so an empty value silently
  signs against bucket `""`), and inserts the jurisdiction label into the endpoint host.
  Proven on five inputs including idempotence and a non-R2 endpoint.
- `.ci/config/secret-reachability.json` loses the now-dead record; the gate reports 45
  refs, controls firing both ways.
- **New gate `check:ci-backup-bucket-conformance`** (`scripts/check-backup-bucket-conformance.ts`),
  wired three-point, asserting bucket AND jurisdiction agreement across all six
  deployments. Proven by planting three separate defects — bucket mismatch, jurisdiction
  mismatch, missing field — each of which fired with a precise message; restore verified
  byte-exact.

**One extra defect swept in the same pass**, in `private/account`: `backup-chunk-store.ts`
built the grant's `aud` as `` `${accountId}.r2.cloudflarestorage.com` ``, reconstructing the
host from the first label and so **silently dropping the `.eu.`** for a jurisdiction-locked
endpoint. Replaced with `r2AudHost(endpoint)`, which returns the endpoint's own host. Latent
rather than live — `createBackupPlane` does not select that minter — but it would have bitten
the moment it was wired back.

**STILL OPEN, and it is the operator's:** the R2 *credential*. The header comment claimed
"one bucket-scoped R2 credential serves every region". If `backup-s3-20260901T103133Z` is
genuinely scoped to a single bucket, it cannot presign for six, and an EU-jurisdiction
bucket additionally needs a token that can reach that jurisdiction. The code fix is correct
and necessary either way; confirm the token's scope in Cloudflare before the first real
backup deploy.

---

## Open questions for the operator — ALL ANSWERED (Part 4)

**Nothing here is open. Do not re-ask any of it.** All five were answered by the
operator on 2026-09-02 and the rulings are recorded verbatim in *Decisions locked by
the operator* above. Kept only so a future session recognises the question and stops:

| # | Question that was open | Where the answer lives |
|---|---|---|
| 1 | Prefix scheme for credentials owned by no component | decision 1 — provider-named prefixes |
| 2 | Do the name-spaces unify or stay mapped? | decision 2 — **unify**, delete the `SECRET_*` shim |
| 3 | Does the rename apply to GitHub secret names too? | decision 3 — Bitwarden gets clean names, GitHub keeps old ones transitionally |
| 4 | Region suffixing for backups, before or after? | decision 4 — **before**, standalone (`#5914a537`) |
| 5 | Rename first then migrate, or the reverse? | decision 5 — folded into the sequencing section below |

---

## Investigation findings — the evidence (Part 5)

### 5a. Two LIVE rotation defects — FIXED 2026-09-02, and the earlier write-up was wrong

**Correction first, because the wrong version is quotable.** This section used to say
`rotate cf-breakpoint` "mints a token, pushes it nowhere, and reports success". It does
not, and never did. `runRotate` validates the slug at
`private/account/scripts/rotation/commands/rotate.ts:109` **before** loading the manifest
or touching Cloudflare, so an unlisted slug was refused with `unknown credential slug`
and nothing was ever minted. Any guard elsewhere phrased as "do NOT run
`rotate cf-breakpoint`, it will mint" was protecting against a danger that did not exist.

The real defect was both simpler and worse. `KNOWN_CREDENTIAL_SLUGS` listed 13 of the 15
slugs CLAUDE.md documents, and the same check gates **all three verbs** — `rotate.ts:109`,
`deactivate.ts:49`, `delete.ts:37`. So `cf-r2-media` and `cf-breakpoint` could not be
rotated, deactivated *or* deleted: two live credentials with no retirement path at all.
`rotateCloudflareToken` already knew how to mint `cf-r2-media`; that branch was simply
unreachable.

**What was done.** Both slugs added to `KNOWN_CREDENTIAL_SLUGS`
(`src/types/rotation-manifest.ts:288`, now exported). The push step was refactored off its
hard-coded slug branches: secret NAMES now come from `cred.consumers` in the manifest, and
the only per-slug knowledge left is a `CF_TOKEN_CONSUMER_SHAPE` of `bearer` (one consumer,
gets the token value) or `r2-keypair` (two consumers, get the id and sha256(value)).
Verified behaviour-preserving: the manifest's consumer names for all four cf slugs are
byte-identical to the ones the old code hard-coded. The usage string, which had drifted to
offer `cf-r2-media` while the slug check refused it, is now derived from
`KNOWN_CREDENTIAL_SLUGS` rather than restated.

`rotate cf-breakpoint` still refuses, deliberately and loudly: no permission set is
declared for it, and minting with guessed scopes would silently widen or narrow what a
debug session can reach. The refusal names `.ci/breakpoint/README.md` as the source and
says that deactivate/delete/list work today. `deactivate`/`delete`/`list` are unblocked.

### 5a-original. The findings as first written

Both block the migration because you cannot rotate the affected credentials at all today.

1. **`rotate cf-breakpoint` mints a token, pushes it nowhere, and reports success.**
   `rotateCloudflareToken` (`commands/rotate.ts:388`) branches only on `cf-cd` (`:488`) and
   `cf-r2`/`cf-r2-media` (`:495`). `cf-breakpoint` falls through with `pushErrors` empty, so
   it reaches `saveManifest` at `:563` and exits 0. Its manifest entry declares
   `consumers: ['github-secret:BREAKPOINT_TUNNEL_TOKEN']`, which is **never read**. Result:
   GitHub keeps the old value while the manifest records the new one active — and seven days
   later `deactivate` kills the token CI is still using.
2. **`KNOWN_CREDENTIAL_SLUGS` (`rotation-manifest.ts:288`) lists 13 of 15**, missing
   `cf-r2-media` and `cf-breakpoint`. `rotate.ts:109` rejects unknown slugs, so
   `./run.sh rotation rotate cf-r2-media` fails with "unknown credential slug" even though
   `:495` implements it and the usage string advertises it. Same in `deactivate.ts:37`,
   `delete.ts:37`.

### 5b. Rotation system shape (what a rename and a Bitwarden consumer must touch)

- **Names live in TWO places that must agree**: the manifest's `github_secret_names` /
  `consumers`, and `scripts/rotation/lib/config.ts` `ROTATION_CONFIG` literals
  (`:39,54,70,91,97,107,117,133,201,212,222`), read by `commands/init.ts` to seed the
  manifest. Rename one and init disagrees with the manifest.
- **The consumer-prefix regex is the gate for any new type**:
  `rotation-manifest.ts:103`, `^(worker|github-secret|local|machine|ses-dkim):`.
- **A `bitwarden-sm:` consumer must touch 5 dispatch sites** — `rotate.ts:666-696`
  (turnstile), `:839-881` (otlp), `:1401-1427` (dkim), `pushToConsumer:1662-1707`, plus the
  `needsCf`/`needsGh` capability probes at `:164,410,642,788` — **and** either a sixth
  `slug ===` branch in `rotateCloudflareToken` or a refactor of that function onto the
  consumer loop. The latter is right: both defects above came from that function.
- **`github_secret_names` has only two real reads** (`rotate.ts:262-263`, AWS-IAM only).
  For cf-token, otlp and turnstile it is documentation.
- **Nothing verifies a named GitHub secret exists.** `rotation check` never contacts GitHub;
  `check-env-credential-drift.ts` compares local `.env` values against manifest version ids
  and its `TRACKED` list names *env keys*, not GitHub secrets. So a rename is mechanically
  safe but **unverified** — and renaming local env keys would make that gate silently track
  nothing (`:175` filters by presence; a missing key is a skip, not a failure).
- **Rollback is push-then-persist with no compensation except DKIM.** A mid-rotation failure
  leaves the new credential live at the platform, absent from the manifest, and pushed to an
  arbitrary prefix of its consumers. Adding Bitwarden as a second store doubles that surface
  with no reconciler.
- **Test coverage is effectively zero**: one vitest file covers `pushWorkerSecret` argv
  handling only. Nothing asserts a secret name, the dispatch, the schema, or `check.ts`.

### 5c. `private/generative` — near-zero risk

Real GitLab repo (`gitlab.rediacc.io/rediacc-org/secret/generative.git`), so coordinatable.
**Zero secrets, no `.env`, no dotenv.** ~30 vars, all `QWEN_*` / `VOXCPM_*` / `FFMPEG_BIN`
engine tuning read in `src/tutorial_tts/config.py`.

One coupling that matters: **`TTS_ENGINE` is deliberately duplicated** in both repos
(`config.py:116` and growth's `step4000_voiceover.py:46`, with a comment explaining the
mirroring). Growth passes its whole environment through
(`step4000_voiceover.py:157`, `env = {**os.environ, ...}`). **Rename it in both repos in the
same change or narration silently falls back to a different engine.**

`RDC_GPU_LOCK_FILE` squats the `RDC_` prefix while having nothing to do with the CLI —
worth renaming out while we are here. So does growth's `RDC_REMOTION_CONCURRENCY`.

### 5d. `private/growth` — moderate but sharply localized risk

Real GitLab repo, dirty tree, broken nested gitlinks under `corporate/`.

**The entire console-secret blast radius is two files and five names:**
`video_pipeline/publish-solutions.sh:51-58` does `set -a; source "$REPO_ROOT/private/account/.env"`
— the only place growth reads console secrets — and `video_pipeline/publish.py:40`. The five
are `R2_MEDIA_{ACCESS_KEY_ID,SECRET_ACCESS_KEY,ENDPOINT}`, `CF_GLOBAL_API_KEY`, `CF_EMAIL`.

**Two constructs a literal grep will miss**: `publish-solutions.sh` guards with `${!v}`
indirection over a name list, and `publish.py` uses a `_R2_ENV_VARS` tuple constant. A
rename must also land in console's `.ci/scripts/deploy/upload-media-to-r2.sh` in the same
window, or growth's guard passes and the upload fails deep inside `aws`.

**Six secrets exist outside the 44-name inventory** — `ELEVENLABS_API_KEY`,
`PEXELS_API_KEY`, `MAUTIC_USER`, `MAUTIC_PASS`, `APOLLO_EMAIL`, `APOLLO_PASSWORD`. If the
convention is meant to be complete, these are in scope.

Marketing docs and **baked video source payloads** reference `STRIPE_KEY`/`STRIPE_LIVE_KEY`
(~20 files, `video_pipeline/processing/*/1000_source.json`). Nothing executes them, but
renaming would desync published video content from the docs.

### 5e. Rename blast radius — ~1,770 literal occurrences, and it is mechanical

**There are FOUR namespaces, not three.** The one missing from earlier analysis is the
**workflow-env shim**: GitHub secret → `SECRET_*` / `<PREFIX>_<SUFFIX>` → Worker binding.
Contract documented at `.ci/scripts/deploy/set-account-worker-secrets.sh:26-41`, consumed
at `:92-141`. Decision 2 deletes this layer.

Distribution: `.github/workflows` + `.ci/` are ~75% of all occurrences. **`packages/` has 7
hits (2 files) and `workers/` has 1** — the product code is not in the blast radius at all.
Heaviest names: `CLOUDFLARE_API_TOKEN` 182, `R2_ENDPOINT` 147, `R2_ACCESS_KEY_ID` 91,
`APP_PRIVATE_KEY` 90, `ACCOUNT_ED25519_PUBLIC_KEY` 87.

**16 of the 44 never reach a Worker** (CI-only) and rename with zero cross-namespace
coordination. **19 collapse** through the shim — the region suffix is stripped, and
`env.ts` only ever sees the short name.

**Names constructed at runtime — the find-and-replace blind spots**, and there are only
seven:
- `set-account-worker-secrets.sh:70-71,72-73,79-82,88-89` — `${!STRIPE_VAR}`, `${!WH_VAR}`,
  `${!SES_K}`, `${!SES_S}`, `${!OTLP_VAR}`
- `:84-86` — the ASIA special case borrowing literal `${SES_KEY_EU}`
- `cd-deploy-account.yml:249` — a **second, independent** `key_var="STRIPE_KEY_${SUFFIX}"`
- `regions.json:15,30,45` — `secretSuffix` is the single source for every suffix above
- generic `${!var_name}` presence-checkers in `.ci/scripts/lib/common.sh:133`,
  `upload-to-r2.sh:147`, `breakpoint-common.sh:178,346`, `assert-ci-complete.sh:65,74`

There is **no** dynamic `secrets[...]` indexing in GitHub expressions — all construction is
bash-side, and the only variable part is `EU|US|ASIA` from one file.

**Schema surfaces**: `env.ts` (short names only — touched because of decision 2);
`rotation/lib/config.ts:39,54,70,91,97,107,117,201,212,222` (the literal source);
`rotation-manifest.json` (16 of 44); `.env{,.example,.bench}`;
`.ci/scripts/infra/ci-env.sh:63,80,83,87,90`; `private/renet/build.sh:411` (reads
`ED25519_PUBLIC_KEY=` out of `.env` as a fallback). **`wrangler*.toml` needs no work** —
zero bindings for any of these; secrets are pushed by API. **`constants.sh` needs no work.**

**The one gate guaranteed to fail**: `check:ci-secret-reachability`. Its baseline
`.ci/config/secret-reachability.json` is keyed by GitHub name per repo, so every renamed
secret reads as unreachable. Regenerate wholesale with `--refresh`, which **needs an
org-admin token**. Also carries `MAX_BASELINE_AGE_DAYS=45` and hardcoded `OPTIONAL` entries.

**Atomicity is forced, not chosen.** `check:ci-workflow-gates` and
`check-workflow-submodule-deps` verify that every `secrets.X` a reusable workflow reads is
declared by its caller. Any staged rollout that renames a callee before its caller — or a
console workflow before the `account`/`renet` submodule ones — fails mid-flight. **Do it as
one commit.** Three files carry the shim contract independently
(`set-{account,www,preview}-worker-secrets.sh`) and must move together.


## Sequencing — the recommended order

**Rename first, Bitwarden second.** The rename's blast radius is almost entirely outside the
rotation tool (~40 workflow and `.ci` files via `secrets.X`); inside it, three places. Doing
Bitwarden first means performing the rename across two stores at once, with a rotate flow
that has no rollback and would leave GitHub on new names and Bitwarden on old ones after any
partial failure.

0. ~~**Fix the two rotation defects (5a).**~~ **DONE 2026-09-02.** For the record, the
   second half of this line was wrong: `cf-breakpoint` never "lied about success", it was
   rejected at the slug check. What was true is that neither slug could be rotated,
   deactivated or deleted. Both are unblocked now.
1. Decide the convention (Part 4 questions).
2. Rename, as one atomic change, coordinated with growth's publish path.
3. Add the `bitwarden-sm:` consumer, folding `rotateCloudflareToken` onto the consumer loop
   rather than adding a sixth `slug ===` branch.
4. Add the verification nobody has: a gate asserting every `github_secret_names` entry
   actually exists in the org, and a conformance leg for worker binding == secret value.

## Immediate focus

Which of the `## Tasks` checkboxes is next, and why. This section decides ORDER; it never
adds work that is not already a checkbox above.

**Updated 2026-09-02.** The three prerequisites are done: both 5a rotation defects and
the backup fix (`#5914a537`). Part 4 is answered. So the next checkbox is no longer a
question to the operator — it is the rename itself.

1. The rename blast-radius report has landed — it is Part 5e, and the atomicity finding
   there is what forces the rename to be one commit.
2. **Agree the concrete old→new table** from decision 1's provider prefixes. Part 7's
   Agent A prompt produces it; that table is the only thing standing between here and a
   mechanical change.
3. Then the rename, as ONE commit, with the seven runtime-constructed sites hand-edited
   and `check:ci-aws-credential-bridge` (Part 7) as a second net under it.

## Remaining (operator)

- `[?] #76f6f55e` rotate the leaked `AUTOPILOT_PRIVATE_KEY`.
- ~~`#5914a537` backup bucket region-suffixing~~ — no longer the operator's: ruled
  "fix now, standalone" on 2026-09-02, and the EU-bucket unknown is settled. This is
  ordinary open work, not something waiting on an answer.
- GPG regeneration + revocation certificate.
- Repoint the org secret at the new R2 backup credential, revoke the old.
- `gh auth refresh -h github.com -s admin:org`.

## Post-migration cleanup detail (Part 6 — do not skip; these are the loose ends)

1. **Narrow the `gh` token back.** `admin:org` was granted 2026-09-02 for exactly two read
   operations: `gh secret list --org rediacc` (done — it found the 3 SMTP orphans) and
   `npm run check:ci-secret-reachability -- --refresh` (needed during the rename). Once that
   baseline is regenerated:

   ```bash
   gh auth refresh -h github.com -s gist,read:org,repo,workflow
   ```

   `admin:org` grants org membership, team and settings WRITE — far more than those two
   reads need, and it is the exact class `04-decisions.md` A.1 rules out. Verify by
   CAPABILITY, not by the scope label: `gh api /user/orgs --jq '.[].login'` should still
   work while `gh secret list --org rediacc` should start failing with 403. (Note GitHub
   collapses `read:org` into `admin:org` in the listing, so the label alone misleads —
   that is why the check is a live call.)

2. **Delete the old GitHub org secrets** once CI reads from Bitwarden. This is what makes
   decision 3 pay off: the old names are retired by deletion, never by a rename flag-day.

3. **Revoke the predecessor backup R2 credential** (identify it via the Cloudflare audit
   log) and **narrow `backup-s3-20260901T103133Z`** from account-wide R2 write to the backup
   buckets only.

4. **Decide the 3 SMTP orphans** — `SMTP_HOST`, `SMTP_PASS`, `SMTP_USER` are org secrets no
   workflow references, mirroring `SMTP_*` fields in the personal vault. Delete them, or
   document what outside CI uses them.

   **New evidence 2026-09-02 that pushes this towards DELETE.** The code does not spell
   them that way. `private/account/src/types/env.ts:83-88` declares `SMTP_HOST`, `SMTP_PORT`,
   `SMTP_USER`, **`SMTP_PASSWORD`**, `SMTP_SECURE`, `SMTP_FROM`, and
   `services/email.service.ts:76-92` reads `SMTP_PASSWORD`. The org secret is `SMTP_PASS`.
   So even if something had wired them up, the password would never have arrived — the
   names do not match. The consumer is the self-hosted path (`entry/on-premise.ts:15`),
   which does not read GitHub secrets at all. Nothing in CI can be using these.

5. **Rotate the `mc_migrate_claude` machine-account token** — it was created with 7-day
   validity on 2026-09-01 for the migration and holds read-WRITE on `ci-shared`. The
   long-lived CI tokens should be read-only and per-project.

---

# THE RENAME SLICE — everything a fresh session needs (Part 7)

**Read this if you are picking up after compaction.** The backup fix (`#5914a537`) is a
separate, smaller slice. This section is the big one, deliberately over-specified so nobody
has to re-derive it. Every claim here was verified in-session; the file:line references
resolve.

## What this slice is

Rename every credential name onto the agreed convention, in **ONE commit**, and fold the two
rotation defects (`#d1cba7e6`) into it as their own commit inside the same PR.

## Why one commit, not staged

`check:ci-workflow-gates` CHECK 2 (`.ci/scripts/security/check-workflow-gates.sh:21-33`)
verifies **both directions**: a reusable workflow may not read a `secrets.X` its caller does
not declare, and a caller may not pass one the callee never declares. Rename a callee before
its caller — or a console workflow before the `account`/`renet` submodule ones — and it fails
mid-flight. `check-workflow-submodule-deps` enforces the same across submodules. Atomicity is
**forced by the gates**, not a stylistic preference.

## The four namespaces (not three — this trips everyone)

```
GitHub secret  →  workflow-env shim  →  Worker binding / .env  →  renet Go
ACCOUNT_ED25519_PRIVATE_KEY → SECRET_ED25519_PRIVATE_KEY → ED25519_PRIVATE_KEY → —
STRIPE_SECRET_KEY_{EU,US,ASIA} → STRIPE_KEY_{SUFFIX} → SECRET_STRIPE_KEY → STRIPE_SECRET_KEY
```

The shim is contracted at `.ci/scripts/deploy/set-account-worker-secrets.sh:26-41`, consumed
at `:92-141`. **Operator decision 2 deletes this layer.** Three files carry the contract
independently and must move together: `set-{account,www,preview}-worker-secrets.sh`.

## The seven runtime-constructed names — find-and-replace CANNOT see these

1-5. `set-account-worker-secrets.sh:70-71,72-73,79-82,88-89` — `${!STRIPE_VAR}`,
     `${!WH_VAR}`, `${!SES_K}`, `${!SES_S}`, `${!OTLP_VAR}`
6. `set-account-worker-secrets.sh:84-86` — the ASIA special case borrowing literal
   `${SES_KEY_EU}` / `${SES_SECRET_EU}` (**deliberate**: AWS has not granted
   `ap-northeast-1` production access; ASIA is kept for when it does)
7. `cd-deploy-account.yml:249` — a **second, independent** `key_var="STRIPE_KEY_${SUFFIX}"`

`regions.json:15,30,45` is the single source of `secretSuffix`. There is **no** dynamic
`secrets[...]` indexing in GitHub expressions — all construction is bash-side.

## Scale, so nobody over-estimates it

~1,770 literal occurrences. `.github/workflows` + `.ci/` are ~75%. **`packages/` has 7 hits
in 2 files and `workers/` has 1** — product code is NOT in the blast radius. 16 of 44 names
never reach a Worker and rename with zero cross-namespace coordination.

## The gate that WILL fail, and the only place org-admin is unavoidable

`check:ci-secret-reachability` — its baseline `.ci/config/secret-reachability.json` is keyed
by GitHub name per repo, so every renamed secret reads as unreachable. Regenerate with
`npm run check:ci-secret-reachability -- --refresh`, which needs `admin:org`. The token has
it as of 2026-09-02; **narrow it back afterwards** (Part 6).

## Ready-to-paste sub-agent prompts

Investigation parallelises here; writing does not. Spawn these read-only, then implement
yourself or with at most 2 writers on disjoint files.

**Agent A — mechanical rename inventory**
> Repo /home/developer/console. Produce the exact sed-able rename table for a secret-name
> migration. For each of the 44 names in `agent/PLAN-secret-namespace-migration.md`, list
> every file:line where it appears as a LITERAL, grouped by surface. EXCLUDE the seven
> runtime-constructed sites listed in Part 7 of that plan — those are hand-edited. Flag any
> occurrence inside a string that is concatenated, interpolated, or passed to `${!…}`.
> Output a machine-readable table: old_name, new_name (leave blank), file, line, surface.
> Conclusions with file:line only; no file dumps.

**Agent B — the shim deletion**
> Repo /home/developer/console. Operator decided to UNIFY the secret namespaces: the
> Cloudflare Worker should read the full GitHub name directly, deleting the `SECRET_*` /
> `<PREFIX>_<SUFFIX>` shim contracted at `.ci/scripts/deploy/set-account-worker-secrets.sh:26-41`.
> Design that change. Cover: all three `set-{account,www,preview}-worker-secrets.sh`, the zod
> schema `private/account/src/types/env.ts` (short names only today), every worker entry point,
> `private/account/.env{,.example,.bench}`, `.ci/scripts/infra/ci-env.sh:63,80,83,87,90`, and
> `private/renet/build.sh:411` which reads `ED25519_PUBLIC_KEY=` out of `.env` as a fallback.
> State what breaks at RUNTIME rather than in CI — that is the half CI cannot catch.

**Agent C — the rotation refactor — SUPERSEDED, do not run it.**
> Done in-session on 2026-09-02, and its premise was false: the prompt asserted
> `cf-breakpoint` "mints a token, pushes it NOWHERE, and exits 0", which never happened
> (`rotate.ts:109` rejects the slug first). It is kept only as a worked example of a
> sub-agent prompt that would have sent an agent hunting a defect that did not exist.
> What remains of it is one small task, and it is NOT a refactor: transcribe
> `cf-breakpoint`'s scopes from `.ci/breakpoint/README.md` into `CF_TOKEN_PERMISSIONS`.
> The one live gap that survives is the last sentence: **test coverage is still one vitest
> file covering `pushWorkerSecret` argv only** — that task is checkbox 5b/3 above.

## A THIRD name-crossing, relayed by f88f9be7 and fixed 2026-09-02

Part 7 tracks names that find-and-replace cannot see because they are built at
runtime. There is a second way a name escapes a search, and it had already broken
production: **a script consumes `R2_ACCESS_KEY_ID` and immediately re-exports it
under a DIFFERENT name in its own body.** A sweep for the consumer finds the
script; the `AWS_*` name it turns into is invisible to that sweep.

`.ci/scripts/release/assert-edge-tag-exists.sh` did neither the bridge nor a
requirement, so `aws s3api head-object` died on `NoCredentials` and
`promote-stable.yml` failed **all seven runs from 2026-08-27**, never once green.
`check_secret_reachability.py` is blind to this by construction: it proves the
workflow's `secrets.X` are reachable, and all three were. The gap is one layer
below, inside the script.

Fixed, along with the script's self-misdiagnosis (it advised cutting a release
and backfilling a sentinel when in fact the check had not run at all), and gated:
`check:ci-aws-credential-bridge` requires every `aws`-CLI caller to bridge or
demand the name. It found three more siblings — `delete-r2-channel.sh` and two
sourced library functions. **When the rename runs, this gate is a second net
under it.**

## Cloudflare read-access changed the picture (Part 8, 2026-09-02)

The operator pointed out that `CF_EMAIL` + `CF_GLOBAL_API_KEY` are in `.env`, so tokens can
be READ and minted on demand. Reading them settled three parked questions with evidence and
turned up four more defects.

### Settled

- **`backup-s3-20260901T103133Z` is ACCOUNT-WIDE `Workers R2 Storage Write`**, not
  bucket-scoped. So it CAN presign for all six backup buckets, and the header comment in
  `set-account-worker-secrets.sh` claiming "one bucket-scoped R2 credential" was simply
  wrong. **The last open question on the backup fix is closed.**
- **An account-scoped R2 token DOES reach the EU jurisdiction**, and ONLY via the
  jurisdictional host. Proven by listing buckets on both endpoints with a stdlib SigV4
  signer: the default endpoint returns 14 buckets and **none of the `-eu` ones**; the
  `.eu.` endpoint returns exactly `rediacc-backups-eu`, `edge-rediacc-backups-eu`,
  `rediacc-configs-eu`, `edge-rediacc-configs-eu`. This is direct proof the endpoint fix
  was necessary, and it independently confirms **all six backup buckets exist** — the
  blind spot `check:ci-backup-bucket-conformance` explicitly disclaims.
- **`cf-breakpoint`'s permission set is now declared, read off the LIVE token.** Account:
  `Cloudflare Tunnel Write`, `Access: Organizations, Identity Providers, and Groups Read`,
  `Access: Apps and Policies Write`. Zone: `DNS Write` on `rediacc.io` only.
  `.ci/breakpoint/README.md` omits the Access-Organizations READ group, so transcribing
  from prose would have minted a token short one permission.

### Four defects found while doing it, all fixed

1. **The policy builder applies zone permissions to EVERY zone in the account**
   (`rotate.ts:506`, `listZoneIds`). cf-breakpoint's DNS Write is scoped to one zone.
   Declaring it without a fix would have WIDENED a debug token from 1 zone to 2. Added an
   optional `zoneNames` field; verified by building the policy and diffing it against the
   live token — account perms, zone perms and zone resource ids all MATCH, and the
   counter-check confirms the unfixed path would have covered 2 zones.
2. **The R2 bucket resource id hardcoded `_default_`** as the jurisdiction. Part 6.3 asks
   to narrow the backup token to the backup buckets — two of which are `eu`. Now derived.
3. **A credential with NO consumers rotates "successfully".** `ses-asia` has
   `consumers: []`, so `rotate ses-asia` would mint a real AWS key, log "pushing new key to
   0 consumer(s)", record it active and exit 0 — while every consumer keeps the old value.
   **This is the genuine instance of the defect that was wrongly attributed to
   cf-breakpoint in 5a.** Guarded in `runRotate` before dispatch, for all platforms.
4. **`cf-r2` never had a `local:` consumer**, and `rotateCloudflareToken` had no `local:`
   branch — so `.env`'s R2 credential was never maintained. **CORRECTED 2026-09-02 (Part 17): it is
no longer `Github-R2`.** `.env`'s `R2_ACCESS_KEY_ID` now matches cf-r2 version
`rediacc-r2-20260902T102203Z`, state **active**, created 2026-09-02T10:22:05Z — the `local:.env`
push loop (`rotate.ts:732-748`) did its job on the 10:22 rotation. The diagnosis below was right
when written; the token it names is `Github-R2`,
   **`grace` under cf-r2 and eligible for deactivation since 2026-04-18**. `rotation status`
   lists 8 eligible transitions, and `rotation sweep` would execute them — retiring the
   credential local development is using. Added the `local:` push and declared
   `local:.env` on cf-r2.

### And the drift gate was blind to exactly that

`check:env-credential-drift` only tested MEMBERSHIP, so a `grace` version read as clean. It
now classifies `absent` vs `retiring` and reports the state; `R2_ACCESS_KEY_ID` is tracked
too. 18 selftests, including controls that an active version stays clean and that
active-under-one-slug beats grace-under-another.

### The region-specificity class, swept (2026-09-02) — backup was the only instance

Asked the inverse of the obvious question: not "what already uses `secretSuffix`" (nothing
pairs it with a name on one line — it is applied by bash indirection) but **which values
the per-region deploy passes GLOBALLY that are per-region in reality**. That is the shape
the backup bucket had.

All 36 env keys in `cd-deploy-account.yml`'s per-region step: 21 region-varying, 15 global.
Every one of the 15 is correctly global — `CLOUDFLARE_*` are account-level; `SECRET_API_KEY`
and `SECRET_JWT_SECRET` have **no per-region variants in existence** and must not (a JWT
minted in EU has to verify in US); `SECRET_ROOT_EMAIL`, `VAR_SELLER_*` and `VAR_SES_*` are
org identity; `SECRET_TURNSTILE_KEY` is one widget. `WORKER_NAME` looks global but is
resolved from `matrix.workerName` through `steps.config`.

Cross-checked from the other side: every per-region field in `regions.json` is accounted
for by the deploy.

**The two structural siblings that could have carried the same defect do not.**
`CONFIG_R2_*` — the exact analogue, since `CONFIG_BUCKET` is per-region and EU is
jurisdiction-locked — is set **nowhere** in workflows or deploy scripts, so the config
plane uses only the native binding, has no presign signer, and therefore has no
global/per-region split to get wrong. `BACKUP_R2_*` appears only in a comment stating it
must stay UNSET. `PUBLIC_SITE_URL` is set nowhere either.

### The drift class, swept properly (2026-09-02)

`R2_ACCESS_KEY_ID` was added to the drift gate because this session tripped over it.
That is fixing the instance. Sweeping the class means asking which OTHER `.env` values
the manifest records: every value in `.env` was compared against every version id in
`rotation-manifest.json`. Result:

- **One genuine sibling**, now tracked: `R2_MEDIA_ACCESS_KEY_ID` matches `cf-r2-media`'s
  active version. It is clean today, so it adds no noise — it is there to catch the next
  drift, not to report one.
- **Four are NOT id-matchable by construction** and must never be added:
  `R2_SECRET_ACCESS_KEY`, `R2_MEDIA_SECRET_ACCESS_KEY`, `BREAKPOINT_TUNNEL_TOKEN` hold a
  token's SECRET while the manifest records its ID; `TURNSTILE_SECRET_KEY` has nothing to
  match at all (below). Adding them reproduces the `SES_AK_ID` category error exactly.
  The reasons are written into `check-env-credential-drift.ts` beside the list so the
  next session does not "fix" it.

**NEW FINDING — `turnstile` and `turnstile-bench` have ZERO versions in the manifest.**
Every other slug has 1 to 4. So two live credentials sit outside the rotation record
entirely: nothing tracks their age, `rotation status` can never list them as eligible,
and `deactivate`/`delete` have nothing to act on. `TURNSTILE_SECRET_KEY` is a real org
secret and is set in `.env`. Seeding those versions is operator/tool work — do not run
`rotate turnstile` to "fix" it, since that mints and pushes a real widget secret to seven
consumers.

### Still open

- `.env`'s `AWS_SES_ACCESS_KEY_ID` is in NO ses-* version (`[?] #2d728f0a`).
- ~~`.env`'s `R2_ACCESS_KEY_ID` is the retiring `Github-R2`.~~ **CLOSED 2026-09-02**: it is the
  active `rediacc-r2-20260902T102203Z` (version ids compared, no values read). What remains is that
  `Github-R2` is still `grace`, four months past its 2026-04-18 eligibility, and `cf-r2` now carries
  TWO grace versions, as does `cf-cd`. Fixing it needed the active
  token's value, which Cloudflare shows only at creation — so either paste it, or
  `rotate cf-r2` (which now updates `.env` itself). **Do not run `rotation sweep` first.**
- **`rotation check` is not read-only in practice.** It works, but partway through the
  otlp slugs it triggers `Renet sources changed, rebuilding...` and a full Docker image
  build — minutes, not seconds. `scripts/dev/deploy-bench.sh` runs it as a preflight.

## Part 9 — what EXECUTING bw against the vault found (2026-09-02)

The operator pointed out that a name-equality diff undercounts, and told me to run the
Bitwarden CLI rather than reason about it. Doing so overturned a locked decision.

### GPG IS RECOVERABLE. Decision 7's premise was false.

Part 3 says `GPG_PRIVATE_KEY`/`GPG_PASSPHRASE` "exist ONLY in the unreadable org store;
local keyring empty", and the operator accepted **regenerate** on that basis. **The key is
in the vault.** It is split across two items whose names are file names, not secret names:

    gpg-private.asc - 1     note, 3808 chars, starts -----BEGIN PGP PRIVATE KEY BLOCK-----
    gpg-private.asc - 2     note, 3707 chars, the continuation
    gpg-public.asc          note, 3894 chars
    passphrase - info@rediacc.com   note, 44 chars

Reassembled and imported into a throwaway keyring: **`sec rsa4096/49BA687F0527C72B`,
fingerprint `42EAD1408A684AB8F185F03F49BA687F0527C72B`, uid `Rediacc <info@rediacc.com>`**
— exactly the published key id in `docs/code-signing-guide.md`. Keyring destroyed after.

So GPG moves from "regenerate" to "copy", and regenerating would have invalidated the key
users pin for no reason. **The revocation certificate is still missing** — that half of the
finding stands.

### The method lesson, which is why this was missed twice

A secret stored as an item's NOTE is invisible to a field-name search, and an item named
after a FILE (`gpg-private.asc - 1`) is invisible to a search for `GPG_PRIVATE_KEY`.
`agent/a276391d/secret-mapping.md` was built from one item's custom fields and so could
only ever see field-shaped secrets in that item.

### There are TWO CI items in the vault, not one

`c38d82bb` "github.com" (36 fields) and `d062dba7` "github.com - cariad" (30 fields) carry
overlapping names. Which is authoritative is undecided, and copying from the wrong one is
silent.

### Candidate semantic matches still to confirm

`.env-account` and `development-account-.env` (notes) carry `S3_ACCESS_KEY_ID`,
`S3_SECRET_ACCESS_KEY`, `S3_BUCKET`, `S3_ENDPOINT`, `S3_REGION` and an unsuffixed
`AWS_SES_ACCESS_KEY_ID`/`AWS_SES_SECRET_ACCESS_KEY`. If the `S3_*` set is the backup plane
under an older name, that is 4 more of the 22 recoverable; the SES pair may be one region's.
**Not asserted — the operator has to say whether `S3_*` there is the backup plane.**

### An exposure to record

While classifying note shapes I printed a 60-character preview of
`passphrase - info@rediacc.com`, which exposed that value in the session transcript. Same
class as the `AUTOPILOT_PRIVATE_KEY` leak in Part 1, different cause: previewing content to
classify it rather than a tool echoing an argument. Treat the GPG passphrase as exposed.

---

# Part 10 — THE NAMING PROFILE AND THE RENAME TABLE

Authoritative from 2026-09-02. This is the table Part 7's "Agent A" prompt was meant to
produce; it is produced here instead, from the three stores read directly rather than
inferred. `ci-shared` was read live over the Secrets Manager API (39 secrets, decrypted
names only) — see Part 11 for how, since `bws` is installed nowhere.

## The profile

    <OWNER>_<THING>[_<REGION>]

`OWNER` is a **provider** when minting/revoking is what you do with the value
(`CLOUDFLARE_`, `AWS_`, `STRIPE_`, `DOCKERHUB_`, `GITHUB_`, `ANTHROPIC_`, `BITWARDEN_`),
and a **component** when a component owns it (`ACCOUNT_`, `RENET_`, `RDC_`, `OBS_`,
`RELEASE_`). `REGION` is `EU`/`US`/`ASIA` and appears ONLY where the value genuinely
differs per region. Decision 1 chose provider-first; this is that rule applied.

## The table

Columns: current GitHub secret → target → where the value lives today.
`SM` = the `ci-shared` project, `V` = vault item `c38d82bb`, `—` = nowhere readable.

### Account component — already conforming, no rename

| current | target | source |
|---|---|---|
| `ACCOUNT_ED25519_PRIVATE_KEY` | unchanged | SM, V |
| `ACCOUNT_ED25519_PUBLIC_KEY` | unchanged | SM, V |
| `ACCOUNT_X25519_PRIVATE_KEY` | unchanged | SM, V |
| `ACCOUNT_X25519_PUBLIC_KEY` | unchanged | SM, V |
| `ACCOUNT_JWT_SECRET` | unchanged | SM, V |
| `ACCOUNT_SERVER_API_KEY` | unchanged | SM, V |

### Cloudflare — the biggest rename group

| current | target | source |
|---|---|---|
| `CLOUDFLARE_API_TOKEN` | unchanged | — (re-mint) |
| `R2_ACCESS_KEY_ID` | `CLOUDFLARE_R2_ACCESS_KEY_ID` | — (re-mint) |
| `R2_SECRET_ACCESS_KEY` | `CLOUDFLARE_R2_SECRET_ACCESS_KEY` | — (re-mint) |
| `R2_ENDPOINT` | `CLOUDFLARE_R2_ENDPOINT` | — (re-mint) |
| `R2_MEDIA_ACCESS_KEY_ID` | `CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID` | SM, V |
| `R2_MEDIA_SECRET_ACCESS_KEY` | `CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY` | SM, V |
| `R2_MEDIA_ENDPOINT` | `CLOUDFLARE_R2_MEDIA_ENDPOINT` | SM, V |
| `BACKUP_S3_ACCESS_KEY_ID` | ~~`CLOUDFLARE_R2_BACKUP_ACCESS_KEY_ID`~~ → `ACCOUNT_BACKUP_S3_ACCESS_KEY_ID` | SM |
| `BACKUP_S3_SECRET_ACCESS_KEY` | ~~`CLOUDFLARE_R2_BACKUP_SECRET_ACCESS_KEY`~~ → `ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY` | SM |
| `BACKUP_S3_ENDPOINT` | ~~`CLOUDFLARE_R2_BACKUP_ENDPOINT`~~ → `ACCOUNT_BACKUP_S3_ENDPOINT` | SM |
| `BACKUP_S3_BUCKET` | **DELETED — not a secret** | derived from `regions.json` |
| `TURNSTILE_SECRET_KEY` | `CLOUDFLARE_TURNSTILE_SECRET_KEY` | — (re-mint) |
| `BREAKPOINT_TUNNEL_TOKEN` | `CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN` | SM, V |

~~`BACKUP_S3_*` keeps the `S3_` word nowhere: R2 speaks the S3 API but the provider is
Cloudflare, and the `AWS_*` bridge those scripts perform is a *client* detail
(`check:ci-aws-credential-bridge` gates it), not a naming one.~~

**OVERTURNED by decision 10 (operator, 2026-09-02).** The three struck rows above and this
paragraph are kept as the record of what was accepted earlier the same day, not as the
target. The argument was wrong in its premise: this family is not Cloudflare's, it is
whatever S3-compatible endpoint the deployment points it at, and the `S3_` word is the only
accurate part of the name. The target is `ACCOUNT_BACKUP_S3_*`. See **Decision 10**.

### AWS

| current | target | source |
|---|---|---|
| `AWS_SES_ACCESS_KEY_ID_{EU,US,ASIA}` | unchanged | — (re-mint ×3) |
| `AWS_SES_SECRET_ACCESS_KEY_{EU,US,ASIA}` | unchanged | — (re-mint ×3) |
| `SES_AK_ID` (`.env` only) | `AWS_IAM_ADMIN_ACCESS_KEY_ID` | `.env` |
| `SES_AK_SECRET` (`.env` only) | `AWS_IAM_ADMIN_SECRET_ACCESS_KEY` | `.env` |

The admin pair is renamed because `SES_AK_ID` reads as a SES sending key and is not one —
it is the IAM admin that mints them. That confusion already cost a permanently-red gate
(see the drift-gate note in Part 8).

### Stripe — CORRECTED 2026-09-02: there is only ONE Stripe account

Established by the operator directly in the Stripe dashboard, not inferred. **The regions
are not separate Stripe accounts.** There is one account, `acct_1ONIroAH2UKrsSNm`
(Rediacc OÜ), live mode, carrying FOUR webhook endpoints:

| endpoint | destination id | status |
|---|---|---|
| `https://eu.rediacc.com/account/api/v1/webhooks/stripe` | `we_1TIk5jAH2UKrsSNmyVK0sJKg` | Active |
| `https://us.rediacc.com/account/api/v1/webhooks/stripe` | `we_1TIk5kAH2UKrsSNmRrygw90f` | Active |
| `https://asia.rediacc.com/account/api/v1/webhooks/stripe` | `we_1TIlyRAH2UKrsSNmpesmHjSp` | Active |
| `https://www.rediacc.com/account/api/v1/webhooks/stripe` | `we_1TPMZ7AH2UKrsSNmJrKlUayY` | **Disabled** |

(The other accounts in the switcher, "Mercor" and "New Business", are unrelated businesses.)

**Consequence: `STRIPE_SECRET_KEY_{EU,US,ASIA}` are three GitHub secrets holding ONE
value.** A single live secret key serves every region, so the region suffix on the SECRET
KEY is a fiction. This is the purest instance of the "what is for what" complaint that
started this programme, and the migration should collapse it:

| current | target | why |
|---|---|---|
| `STRIPE_SECRET_KEY_{EU,US,ASIA}` | **`STRIPE_SECRET_KEY`** — one secret | one account, one key |
| `STRIPE_WEBHOOK_SECRET_{EU,US,ASIA}` | unchanged, genuinely per-region | one signing secret PER ENDPOINT |

The webhook secrets stay suffixed because they really do differ: each endpoint has its own
signing secret. The secret key does not.

**The live secret key CANNOT be re-read.** Stripe shows a standard secret key's value only
once, at creation; the dashboard row offers Copy-ID / Rotate / Edit / Expire and no reveal.
So the copy in the vault and `ci-shared` is the ONLY readable source that exists, and
losing it means a rotation that breaks billing in all three regions at once. Treat it with
the same care as `ACCOUNT_ED25519_PRIVATE_KEY`.

Two housekeeping observations from the same dashboard visit, both operator decisions:
- The **disabled `www.rediacc.com` endpoint** is still subscribed to the same 24 events.
  Delete it or record why it is kept.
- A second live key, `interim` (created 2026-02-25), has been **unused for 189 days** and
  Stripe itself recommends deleting it.

### Observability

| current | target | source |
|---|---|---|
| `OTLP_CLIENT_CREDENTIALS_{EU,US,ASIA}` | `OBS_OTLP_CREDENTIALS_{EU,US,ASIA}` | — (re-mint) |
| `OTLP_AUTH_USERNAME` | `OBS_OTLP_USERNAME` | SM, V |
| `OTLP_AUTH_PASSWORD` | `OBS_OTLP_PASSWORD` | SM, V |
| `OTLP_AUTH_TOKEN=USER:PASS` | `OBS_OTLP_CREDENTIALS` | SM, V |

That last rename is not cosmetic: **the current name contains `=` and `:`**, which breaks
any `KEY=VALUE` parse and is a hostile shape for a store key. `OBS_` rather than a provider
prefix because the collector is self-hosted (`obs.rediacc.com`); there is no vendor.

### GitHub / CI identity

| current | target | source |
|---|---|---|
| `APP_PRIVATE_KEY` | `GITHUB_APP_PRIVATE_KEY` | SM, V (as `rediacc-ci-cd.2026-02-01.private-key.pem`) |
| `AUTOPILOT_APP_ID` | `GITHUB_AUTOPILOT_APP_ID` | SM, V |
| `AUTOPILOT_PRIVATE_KEY` | `GITHUB_AUTOPILOT_PRIVATE_KEY` | SM, V |
| `DOCKERHUB_TOKEN` | unchanged | SM, V (as `DOCKERHUB_TOKEN_GITHUB`) |
| `DOCKERHUB_USERNAME` | unchanged | — (operator) |
| `CLAUDE_CODE_OAUTH_TOKEN` | `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` | — (re-mint) |
| ~~`ANTHROPIC_API_KEY`~~ | **REMOVED 2026-09-02** — no API billing; the reference is deleted, not merely empty | never |
| — (`rediacc-ci-cd-client-secret`, SM/V only) | `GITHUB_APP_CLIENT_SECRET` | SM, V |

### Release signing

| current | target | source |
|---|---|---|
| `GPG_PRIVATE_KEY` | `RELEASE_GPG_PRIVATE_KEY` | **V** — `gpg-private.asc - 1` + `- 2` |
| `GPG_PASSPHRASE` | `RELEASE_GPG_PASSPHRASE` | **V** — `passphrase - info@rediacc.com` |

`RELEASE_` not `RENET_`: the key signs the apt/yum repositories, which are a release
artifact, not a renet one.

### Bitwarden itself

| current | target | source |
|---|---|---|
| `mc_migrate_claude` (`.env`) | `BWS_ACCESS_TOKEN` | `.env` |

Lowercase in a file of SCREAMING_SNAKE, and it names neither its provider nor its purpose.
Expires **2026-09-08**.

**Target CORRECTED 2026-09-02 from `BITWARDEN_SM_ACCESS_TOKEN` to `BWS_ACCESS_TOKEN`.**
The rename inventory (Part 12) found the two names colliding in intent: `bws` itself reads
`BWS_ACCESS_TOKEN`, the composite action documents that GitHub secret name, and
`check_bws_map.py:107` expects it. One token, one name, the one the tool already reads.

### Out of scope — in the vault and SM, read by nothing

`SMTP_{HOST,PORT,USER,PASS,FROM}`, `STRIPE_PUBLISHABLE_KEY`,
`STRIPE_SANDBOX_PUBLISHABLE_KEY`, `STRIPE_{,SANDBOX_}WEBHOOK_SECRET_ID`,
`AWS_SES_HOST`, `AWS_SES_REGION`, `R2_TOKEN_AUTH_API`. The SMTP set is provably dead: the
code reads `SMTP_PASSWORD`, every store spells it `SMTP_PASS` (Part 6.4).

## What is genuinely missing — CORRECTED 2026-09-02, twice

**Two earlier counts in this session were wrong and the operator caught both.** First "29
missing", from naive name-equality. Then "13 need re-minting", which compared `ci-shared`
against GitHub and **forgot `private/account/.env` as a source** — even though the mapping
being read says five secrets are covered by an exact `.env` key name. The operator's
instruction stands: *use what we already have.*

Sources actually checked: `ci-shared` (39), vault item `c38d82bb` (36 fields), vault NOTES,
vault LOGIN username/password fields, and `.env` (50 keys).

### Present somewhere readable — copy, do NOT re-mint

| secret | where |
|---|---|
| the 6 `ACCOUNT_*` | SM + vault |
| `AUTOPILOT_PRIVATE_KEY`, `BREAKPOINT_TUNNEL_TOKEN` | SM + vault + `.env` |
| the 3 `BACKUP_S3_*` | SM |
| the 3 `R2_MEDIA_*` | SM + vault + `.env` |
| `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT` | **`.env`** |
| `TURNSTILE_SECRET_KEY`, `CLAUDE_CODE_OAUTH_TOKEN` | **`.env`** |
| `STRIPE_SANDBOX_SECRET_KEY`, `STRIPE_SANDBOX_WEBHOOK_SECRET`, `STRIPE_WEBHOOK_SECRET_{EU,US}` | SM + vault |
| `APP_PRIVATE_KEY` | vault, as `rediacc-ci-cd.2026-02-01.private-key.pem` (alias) |
| `DOCKERHUB_TOKEN` | SM + vault, as `DOCKERHUB_TOKEN_GITHUB` (alias) |
| `DOCKERHUB_USERNAME` | **vault login item `id.docker.com`** |
| `GPG_PRIVATE_KEY`, `GPG_PASSPHRASE` | **vault notes** — verified importable as `rsa4096/49BA687F0527C72B` |
| `STRIPE_SECRET_KEY_EU`, `STRIPE_WEBHOOK_SECRET_ASIA` source | SM/vault unsuffixed value — operator ruled it is **EU** |
| `OTLP_CLIENT_CREDENTIALS` (one region) | `.env`, plus vault `OTLP_AUTH_USERNAME`/`PASSWORD` and the `obs.rediacc.com` login |
| one `AWS_SES_ACCESS_KEY_ID`/`SECRET` pair | `.env` unsuffixed, and vault notes `.env-account` |

### Mintable right now with credentials already in hand

- `CLOUDFLARE_API_TOKEN` — `CF_GLOBAL_API_KEY` + `CF_EMAIL` in `.env` authenticate today
  (proven this session by reading every account token through them).
- the remaining `AWS_SES_*_{EU,US,ASIA}` — `SES_AK_ID`/`SES_AK_SECRET` in `.env` are the
  IAM admin that mints exactly these, and `./run.sh rotation rotate ses-*` already pushes them.
- the remaining `OBS_OTLP_CREDENTIALS_{US,ASIA}` — `rotation rotate otlp-*` mints them.

### Genuinely absent — CORRECTED to ONE

Was "three, all Stripe". The operator checked the dashboard and two of the three do not
exist as separate values at all: `STRIPE_SECRET_KEY_US` and `STRIPE_SECRET_KEY_ASIA` are
the SAME key as EU, because there is one Stripe account (above). Nothing to fetch.

That leaves **`STRIPE_WEBHOOK_SECRET_ASIA`**, which the operator retrieved from endpoint
`we_1TIlyRAH2UKrsSNmpesmHjSp`. It was pasted into the session transcript, so it is
**exposed** and tracked as `#cefe6f54` — roll it at the endpoint before storing it, rather
than migrating a known-exposed value.

Plus two that must stay as they are: `ANTHROPIC_API_KEY` (deliberately absent everywhere)
and `BACKUP_S3_BUCKET` (stopped being a secret this session — derived from `regions.json`).

**So the real operator-only gap is 3, not 13.**

---

# Part 11 — READING `ci-shared` WITHOUT `bws`

`bws` is installed on **neither the host nor the devcontainer** (both checked 2026-09-02).
The Secrets Manager REST API works with the machine-account token in `.env`, and this is
how the 39 names in Part 10 were read. Reusable, read-only, nothing installed:

1. Split `mc_migrate_claude` as `0.<client_id>.<client_secret>:<encryption_key>`.
2. `POST https://identity.bitwarden.com/connect/token`, `grant_type=client_credentials`,
   `scope=api.secrets`, with that id/secret. Needs a `Device-Type` header. Returns a
   Bearer token AND an `encrypted_payload`.
3. Derive `HKDF-Expand(prk=HMAC-SHA256(key="bitwarden-accesstoken", msg=<encryption_key>),
   info="sm-access-token", len=64)`; first 32 bytes encrypt, last 32 authenticate.
4. Decrypt `encrypted_payload` (Bitwarden EncString `2.<iv>|<ct>|<mac>`, AES-256-CBC then
   HMAC-SHA256 verify) to get `{"encryptionKey": ...}` — the ORG key, again 32+32.
5. `GET /organizations/<orgId>/secrets` with the Bearer token. The org id is in the JWT's
   `organization` claim: `61f8e970-e166-445e-873c-b09500f699e1`. Each secret's `key` and
   `value` are EncStrings under the org key.

**Two traps that cost a wrong answer here.** The org-level response nests under
`secrets`, NOT `data` — reading `data` returns 0 and looks like an empty project, which is
exactly the false "ci-shared is empty" this produced on the first attempt. And
`/organizations/<id>/projects` DOES use `data`, so the two endpoints disagree.

Project `ci-shared` = `2b5e33f9-b5ae-4ecc-972d-b36f00b0f86a`, created 2025-10-07.

## Guards that must survive into the new session

- **This file's FORMAT is now enforced by a hook, so keep the checkbox list.**
  `.claude/hooks/pre-edit/block-plan-without-tasks.sh` blocks a Write/Edit that
  creates a plan carrying no parseable task list, in `agent/PLAN-*.md` and in the
  harness plan directory alike. The parser is the worklist's own
  `.claude/hooks/stop/wl_planfid.py`, so the rules are not this hook's invention:
  **only `- [ ]` and `- [x]` count as tasks — `- [?]` and `- [>]` do NOT**, and a
  file under `MIN_PLAN_CHARS = 400` is exempt as a stub. Amending a plan that
  already predates the convention is grandfathered with a note.
  The defect it exists to catch was measured on THIS file: before it was
  reformatted, `plan_tasks()` returned 21 "tasks" of which 8 were the operator's
  locked decisions and 5 were open questions, while every real unit of work was
  invisible. A guard keyed on "zero tasks" would have waved that straight through,
  which is why the harness's first case is a prose plan whose DECISIONS parse.

- **`rotate cf-breakpoint` is safe to run and will refuse.** This guard used to say it
  "reports success while pushing nothing" — that was wrong; see Part 5a. As of 2026-09-02
  it refuses before touching Cloudflare, naming `.ci/breakpoint/README.md` as the place the
  missing permission set is recorded. Agent C's task is therefore smaller than it was
  written: transcribe those scopes into `CF_TOKEN_PERMISSIONS`, nothing else.
- **`ANTHROPIC_API_KEY` is GONE, not absent — decided 2026-09-02.** The operator ruled
  out pay-as-you-go API billing, so this credential will never exist. It used to be
  referenced-but-absent, held in place by an `OPTIONAL` allowlist entry in
  `check_secret_reachability.py`; both the reference and the entry were deleted, that
  allowlist is now empty, and the watchdog's tier 2 authenticates with
  `CLAUDE_CODE_OAUTH_TOKEN` alone. **Do not re-add it, and do not mint a key.** If a
  future reader finds this name in a comment, that comment is the record of its removal.
- **`AWS_SES_*_ASIA` are NOT dead.** They are held for when AWS grants `ap-northeast-1`;
  `set-account-worker-secrets.sh:84` substitutes EU at deploy time only.
- **`private/growth` and `private/generative` are real GitLab repos**, coordinatable but not
  atomic with console. `TTS_ENGINE` is duplicated in both and must move in lockstep or
  narration silently falls back to a different engine.

## Part 12 — rename inventory for the GitHub/Bitwarden-side sed pass (2026-09-02)

Produced by a read-only agent over `git ls-files --recurse-submodules` plus the
untracked `private/account/.env*`: 5,285 files, 1,085 raw hits for the 30 Part 10
names. This is what the sed pass in section 4 of the execution plan must respect.
The Worker-side rename (decision 2, the `env.ts` schema and the five builders) is
NOT covered here; it ran as its own writer this session.

### Sed rules that are not optional

- **Left word boundary on every prefix-adding rename**, because the old name is a
  substring of its own replacement (`R2_ENDPOINT` → `CLOUDFLARE_R2_ENDPOINT`). A second
  pass without the anchor yields `CLOUDFLARE_CLOUDFLARE_R2_ENDPOINT`. No target name
  exists anywhere in the tree yet, so a partial run is detectable but not self-healing.
- **Container tokens that must NOT change** (each is a different credential):
  `CONFIG_R2_{ENDPOINT,ACCESS_KEY_ID,SECRET_ACCESS_KEY}` (37 sites, the on-prem rustfs
  blob store; `.ci/lib/account.sh`, `src/entry/*.ts`, `env.ts:157-163`,
  `docker-compose.yml`, `scripts/drills/backup.sh:111-112`), `ACCOUNT_BACKUP_R2_GRANT_*`
  (formerly `BACKUP_R2_*`, renamed by decision 10; a distinct optional Worker binding, and
  it is now impossible to hit by accident since it no longer shares a stem with the S3
  family), `ACCOUNT_BACKUP_S3_*` (which CONTAINS `BACKUP_S3_*`, so the GitHub-side rename
  needs its left boundary or a second pass doubles the prefix), `CD_APP_PRIVATE_KEY`
  (`scripts/dev/SECURITY-HARDENING-SETUP.md:50,194`).
- **`STRIPE_SECRET_KEY_{EU,US,ASIA}` before any bare `STRIPE_SECRET_KEY` rule, with a
  RIGHT boundary too.** `STRIPE_SANDBOX_SECRET_KEY` (18 refs) and
  `STRIPE_WEBHOOK_SECRET_*` are unchanged and must be excluded.
- **`OTLP_CLIENT_CREDENTIALS_{EU,US,ASIA}` longest-first.** The bare
  `OTLP_CLIENT_CREDENTIALS` is a live Worker key and `.env` key, not in the table.
- `OTLP_AUTH_{USERNAME,PASSWORD,TOKEN}` have ZERO live readers (two dead comments at
  `ci-build-renet.yml:28` and `ci.yml:716`). Rename them in Bitwarden only.

### Runtime-constructed names sed cannot see (verified line numbers)

- `set-account-worker-secrets.sh:83-102`: six `${!VAR}` indirections over
  `STRIPE_KEY_$SUFFIX`, `STRIPE_WH_$SUFFIX`, `SES_KEY_$SUFFIX`, `SES_SECRET_$SUFFIX`,
  `OTLP_CRED_$SUFFIX`, plus the literal `_EU` ASIA fallback at `:98-99`. These are
  workflow-local env names minted at `cd-deploy-account.yml:246-248,277-282,287-295`;
  only the `secrets.X:` left-hand side of those YAML lines carries a Part 10 name.
- `cd-deploy-account.yml:253-254`: a second independent `key_var="STRIPE_KEY_${SUFFIX}"`
  in "Verify Stripe prices". The one-account collapse makes `:252-257` dead.
- `private/account/scripts/ops.sh:134,138,144`: name held as a string in `key_var`.
- `scripts/dev/migrate-stripe-to-envs.sh`: exists solely to push the three regional
  Stripe keys into GitHub environments. The collapse voids the script; **deleted 2026-09-02 (Writer D)**.
- `scripts/dev/deploy-bench.sh:203,205,206`: nested defaults carrying TWO renamed names
  per line with DIFFERENT targets (`ACCOUNT_BACKUP_S3_*` vs `CLOUDFLARE_R2_*`; the first
  read `CLOUDFLARE_R2_BACKUP_*` until decision 10, which is precisely the collision that
  made the line hazardous — the two no longer share a prefix at all).
- `run.sh:1438` `_env()` greps `.env` by literal key; callers at `:1501-1520`.
- `credentials.ts:60-61`: `SES_AK_ID ?? AWS_SES_ADMIN_KEY_ID`, a THIRD spelling of the
  IAM admin pair, also at `deploy-bench.sh:163`. Not in the table; collapse it.
- `credentials.ts:152-153`: exports the token under `BWS_ACCESS_TOKEN`, not Part 10's
  `BITWARDEN_SM_ACCESS_TOKEN`.

### Gates that hardcode a renamed name (fail on the rename unless moved with it)

`check-workflows.sh:99` and `check_workflow_submodule_deps.py:482` (`APP_PRIVATE_KEY`);
`check_secret_reachability.py:7,70,85,173` (`CLAUDE_CODE_OAUTH_TOKEN`);
`check-autopilot-no-bypass.sh` (7 × `AUTOPILOT_APP_ID`, a `vars.` not a secret) and its
two harnesses; `check-breakpoint-drift.sh` pairs `.ci/breakpoint/workflow/breakpoint.yml`
with `.github/workflows/breakpoint.yml`, which must change together.

### Part 10 rows that are missing, reported for a ruling

1. `BWS_ACCESS_TOKEN` (composite action, `check_bws_map.py:107`, credentials.ts) versus the
   table's `BITWARDEN_SM_ACCESS_TOKEN`: two names, one token, neither settled.
   DEFAULT: `BWS_ACCESS_TOKEN` stays; it is what `bws` itself reads.
2. `STRIPE_SANDBOX_SECRET_KEY` and `STRIPE_SANDBOX_WEBHOOK_SECRET`: live secrets, no row.
3. `vars.APP_ID` and `vars.TURNSTILE_SITE_KEY`: the public halves of renamed pairs.
4. `CF_GLOBAL_API_KEY`/`CF_EMAIL`, `R2_MEDIA_BUCKET`, `OTEL_ENDPOINT`: `.env` keys adjacent
   to renamed groups, no row.

### Old names outside the surfaces the sed will walk

`private/elite/{docker-compose.yml,.env.template,scripts/s3-conformance-probe.sh}`,
`programs/backup-storage/start-local-plane.sh`, `private/renet/.github/workflows/claude-review.yml`,
`.ci-parity-exempt:48`, root `CLAUDE.md`, `.claude/hooks/pre-bash/block-host-toolchain-run.sh`,
`private/growth/video_pipeline/{publish.py:40,283,publish-solutions.sh:55}`.
`private/generative`: zero hits.

### Incidental defect, not a Part 10 matter

`run.sh:1512` reads `$(_env STRIPE_SANDBOX_SECRET_KEY)` but that key is absent from
`private/account/.env`; the `select(.value != "")` at `:1537` drops it silently, so local
preview Workers ship with no Stripe key and no error.

## Part 13 — what EXECUTION changed about the design (2026-09-02)

Five things the plan assumed and the doing disproved. Recorded here rather than in a
session's notes because each one is a design fact the next reader needs, and four of
them were invisible until something real ran.

### 1. `BWS_ACCESS_TOKEN` is a REPOSITORY secret in three repos, not an org secret

Every earlier section assumed the org-secret shape: one secret, `--visibility selected`,
scoped to console/account/renet. **That is unavailable on GitHub Free for private
repositories.** The operator therefore created the read-only `ci-shared`-scoped machine
account and set the token as a repository secret in each of the three repos separately,
2026-09-02 (console 13:43:11Z, account 13:43:24Z, renet 13:43:31Z).

Consequences that are NOT obvious: the org has 45 secrets and none is named
`BWS_ACCESS_TOKEN`, so nothing shadows the repo-level value; `check:ci-secret-reachability`
records it as `via: repo`; and rotating it later is three operations, not one. The
composite action reads it identically either way, so no code cares — only the runbook does.

### 2. Deleting the shim was not a five-file change; it was a five-file change plus 61 workflow env lines

Section 5 said "delete the `SECRET_*` shim from the five payload builders and have each
write the full target name". True, and incomplete: the workflows that CALL those builders
were exporting the old short names (`SECRET_*`, `VAR_*`, `STRIPE_KEY_${SUFFIX}`,
`SES_KEY_*`, `OTLP_CRED_*`). The moment the builders read full names, every one of those
61 lines across `cd-deploy-account.yml`, `cd-deploy-worker.yml` and `ci.yml` became a
`_require_nonempty` failure waiting for the next deploy.

**The lesson generalises: a rename on the READ side is only half a rename.** Nothing in
the plan's blast-radius arithmetic caught this, because the old names were not GitHub
secret names and so were not in the count. The gate that now catches the whole class is
`check:ci-builder-env-contract` (§4 below).

### 3. The rotation tool cannot DERIVE the Bitwarden name from the GitHub name

Section 6 assumed the two stores spell a credential identically, and `rotate.ts` did too:
every `bitwarden-sm:` push site took the name from the credential's `github-secret:`
sibling "so both stores agree". Decision 3 deliberately makes them DISAGREE — Bitwarden on
the new profile, GitHub on the old — so after the ci-shared rename the next `rotate` would
have called `bws secret create` and produced a DUPLICATE under the old spelling, silently,
while reporting success.

The fix is a declared field, `bitwarden_secret_names`, beside `github_secret_names` in the
manifest schema, the config and `init`, with every push site refusing when a credential
declares a `bitwarden-sm:` consumer and no names. Derivation was the defect; declaration is
the design.

### 4. Three gates that did not exist in the plan, and one allowlist that should not have

- `check:ci-builder-env-contract` — compares each workflow step's exported env NAMES with
  the names its builder reads, both directions. This is the gate for §2's class.
- `check:ci-worker-secret-names` — every name a builder pushes must be declared in
  `env.ts`, because zod v4 STRIPS unknown keys and 79 of 85 schema keys are optional, so a
  renamed key is discarded with no diagnostic anywhere.
- `check:ci-bws-map` — the replacement for `check-workflow-gates.sh` CHECK 2, which goes
  structurally vacuous once secrets arrive as `$GITHUB_ENV` injections.
- `check_secret_reachability.py`'s `OPTIONAL` allowlist is now EMPTY. Its only entry
  excused a reference to `ANTHROPIC_API_KEY`; the operator ruled out pay-as-you-go API
  billing on 2026-09-02, so the reference was DELETED rather than excused. That is the
  right end for every entry in that list: a suppression outlives its reason silently, a
  deleted reference cannot.

### 5. The Worker-side namespace is NOT the GitHub namespace, and conflating them is a live hazard

Decision 2 collapsed the shim so the Worker reads full names. But five names are now
HOMOGRAPHS: `STRIPE_SECRET_KEY`, `CLOUDFLARE_TURNSTILE_SECRET_KEY`, `OBS_OTLP_CREDENTIALS`
and the `CLOUDFLARE_R2_BACKUP_*` family exist as BOTH a Worker binding key and a GitHub
secret name, and they rename on different schedules. A file-wide find-and-replace over
`set-account-worker-secrets.sh` corrupts the Worker contract at exactly those lines while
looking correct.

~~Related and still open as an operator question:~~ **ANSWERED — see Decision 10.**
`CLOUDFLARE_R2_BACKUP_*` (the S3-API presign path) read as a sibling of `BACKUP_R2_*` (the
native-binding grant minter, `env.ts:183-192`), and they are different things. The S3 family
is also what an on-prem MinIO or RustFS install sets, which made `CLOUDFLARE_` wrong for
that surface. The operator ruled on both: they are now `ACCOUNT_BACKUP_S3_*` and
`ACCOUNT_BACKUP_R2_GRANT_*`, and the homograph list above loses one of its five members —
`CLOUDFLARE_R2_BACKUP_*` no longer exists as a Worker key, so the Worker key and the GitHub
secret `BACKUP_S3_*` can no longer be confused for each other by a file-wide replace.

## Part 14 — what a four-angle audit found that every local gate had passed (2026-09-02)

After the six writers landed, four read-only agents audited the same tree from angles
that fail differently: is it ONE coherent change; do the plans match reality; what breaks
at RUN time; and what has no gate. They found **five live breaks while `npm run ci` was
344/354 green and every migration-specific gate exited 0.** That ratio is the finding —
each break below was invisible to a gate that was, on its own terms, working correctly.

### 1. The shadow run compared nothing and said "match"

The compare step hashed both sides and diffed the digests. An ABSENT GitHub secret and an
EMPTY Bitwarden value both hash to `e3b0c442…`, so two nothings compared EQUAL and printed
`shadow X match`. The mechanism built to prove the Bitwarden path works would have
certified an empty credential all the way to a Worker.

**This is the `OTLP_CLIENT_CREDENTIALS` defect — the one this whole migration's gate story
starts from — reintroduced inside the tool built to prevent it.** Fixed: an empty value on
either side is now a failure that names which side. The general rule: a comparison whose
inputs can both be absent must test presence BEFORE equality, because equality is
vacuously true at the bottom.

### 2. Ten jobs could not read the map, because sparse checkout is a second dependency graph

`.github/actions/bws-secrets` resolves its map through the WORKSPACE
(`${{ github.action_path }}/../../../.ci/config/…`). Ten jobs sparse-checkout narrow cone
lists; eight fetched `.github/actions` but not `.ci/config`, and two fetched neither. All
six regional account deploys and `finalize-release-sentinel` were among them, so the first
merge would have produced no release.

**A workspace-resolved local action has TWO path dependencies — itself and everything it
reads — and a sparse checkout satisfies neither by default.** Nothing in this repo
reasons about `sparse-checkout` at all; that is a gate-shaped hole, not just a bug.

### 3. A script and its caller, renamed by different hands

`ci-start-account.sh` and `run-account-e2e.sh` were rewritten to demand `ACCOUNT_*` and
abort otherwise, while `ci.yml` and `ct-tests.yml` still exported the short spellings.
Same class as Part 13 §2 and, tellingly, `check:ci-builder-env-contract` — the gate
written for exactly this class in this same wave — covers three builder steps and does not
see these two. **A gate scoped to the instance that produced it does not cover its class.**

### 4. The on-prem plane was killed by the schema rename

`private/elite/docker-compose.yml` exported `BACKUP_S3_*` into the on-premise account
server whose schema now declares only `CLOUDFLARE_R2_BACKUP_*`. zod v4 strips unknown
keys, so `createBackupPlane` would return null and on-prem backups would stop with no
error anywhere. `check:ci-worker-secret-names` cannot see it: elite's compose is not one of
the five builders it knows about. Swept across the compose, `.env.template`, the S3
conformance probe and `programs/backup-storage/start-local-plane.sh`.

**And then the family moved AGAIN, hours later** (`CLOUDFLARE_R2_BACKUP_* ->
ACCOUNT_BACKUP_S3_*`, decision 10). Two moves in one day through a surface no gate watches
is the reason the on-prem sites are re-checked against `env.ts` by hand on every pass rather
than assumed correct because the previous pass fixed them. The names above are the historical
record of the break; the live spelling is `ACCOUNT_BACKUP_S3_*`.

### 5. One value cannot be shadow-compared against three different secrets

`cd-deploy-account.yml` fanned a single stored `OBS_OTLP_CREDENTIALS` into three aliases
compared against three genuinely different regional secrets, so at most one could ever
match. Removed until the regional values exist in `ci-shared`. The Stripe fan-out of the
same shape is legitimate and stays, because the operator established the three regions are
one account — **identical shape, opposite verdict, and only a fact about the credentials
tells them apart.**

### The two structural findings, which are not bugs and do not have fixes yet

- **Green gates on a dirty tree.** `check:ci-worker-secret-names` passes because it reads
  `private/account/src/types/env.ts` from the dirty submodule WORKTREE. At the pinned
  commit it fails on all 112 keys. Every gate that reads across a submodule boundary
  measures the working tree while CI would measure the pointer, so a console-only commit
  ships code CI resolves against old content. **This migration is therefore not landable as
  one commit**: it needs account, renet and elite committed first, then console with the
  pointers bumped.
- **`git ls-files` gates cannot see the deliverable.** `check:ci-aws-credential-bridge`
  and `check:ci-fetch-integrity` enumerate tracked files. This repo's standing deliverable
  is an UNCOMMITTED tree. A new script is therefore invisible to both gates for exactly as
  long as it is the thing being worked on.

## Decision 9 — MINT the five, and ASIA stays absent on purpose (operator, 2026-09-02)

**This partially overturns decision 8ter.** 8ter said "copy what exists, mint nothing", and
that was right for the population pass: it kept a bulk migration from quietly creating
credentials nobody had audited. It is NOT right as a permanent rule, because seven of the
44 existed in no readable source at all, so under 8ter the cutover would have stayed
permanently partial in those slots — and, worse, they were five of the seven credentials
that no shadow step compares, so they would have reached the flip unverified.

**The ruling: mint five.** `AWS_SES_ACCESS_KEY_ID_EU`, `AWS_SES_SECRET_ACCESS_KEY_EU`,
`AWS_SES_ACCESS_KEY_ID_US`, `AWS_SES_SECRET_ACCESS_KEY_US`, `CLOUDFLARE_API_TOKEN`, each
pushed to GitHub, to `ci-shared`, and to the Workers its slug names.

**ASIA is not an oversight, it is the answer.** AWS has not granted `ap-northeast-1`, so
there is no identity to mint a key for. `set-account-worker-secrets.sh` already substitutes
the EU pair for ASIA at deploy time, and that stays true. **Do not create an ASIA IAM key,
and do not touch the `ses-asia` slug**: its empty-consumer guard refuses it correctly, and
the guard stays. So the "seven mintable gaps" resolve as **five minted plus two deliberately
absent**.

### Three defects had to be fixed BEFORE any rotation, and they are the durable part

1. **The SES path can strand a live IAM key.** `rotate.ts:190` computes `needsGh` from
   `github-secret:` consumer refs; the SES slugs declare `github_secret_names` but no such
   consumer, so `verifyGitHubCli()` at `:219-229` is skipped — while the GitHub push at
   `:309` runs unconditionally. A `gh` failure mid-run therefore leaves a real key live at
   AWS, already pushed to four Workers and `.env`, with the command exited non-zero. The
   Bitwarden half has exactly this preflight (`needsBw` + `verifyBitwardenSm()`); the GitHub
   half did not. **The general rule: a preflight must be keyed on what the command WILL DO,
   not on how that work happens to be declared.**
2. **`bws` is absent from the running devbox**, though the Dockerfile pins it — the
   container predates that layer. The binary must be fetched and hash-verified before
   extraction, and `unzip` is not installed here.
3. **`scripts/dev/bws-map-refresh.py` had no caller.** Every one of the five mints is a
   Bitwarden CREATE with a fresh UUID, so without a refresh the committed map keeps
   resolving old ids and CI fetches pre-rotation values with no error at all.

### One asymmetry worth carrying forward

`cred.github_secret_names` is read on the **aws-iam path only** (one push site,
`rotate.ts:309-310`). cloudflare-token derives its GitHub names from the `github-secret:`
consumer refs (`:518-520`), and turnstile/otlp use `parseGitHubSecretRef(consumerRef)`
(`:924`, `:1134`). So for 10 of the 15 slugs that manifest field is DECORATIVE at rotate
time: edit it without editing `consumers` and the rotation still pushes under the consumer
spelling. Anything reasoning about "which GitHub name will this slug write" must read the
consumers, not the field.

### Outcome — executed 2026-09-02, all five minted

Three `rotate` runs, each exit 0, in this order. Predecessors are `grace` and NOTHING was
deactivated or deleted; `sweep` was never run.

| slug | new id | pushed to |
|------|--------|-----------|
| `ses-eu` | `AKIAWXE5TUDQ3BKBVCE5` (prev `AKIAWXE5TUDQ4T2EY5KV` → grace until 2026-09-09) | 4 Workers (eu, edge-eu, asia, edge-asia), `local:.env`, `ci-shared`, GitHub `AWS_SES_{ACCESS_KEY_ID,SECRET_ACCESS_KEY}_EU` |
| `ses-us` | `AKIAWXE5TUDQXRAPZBCP` (prev `AKIAWXE5TUDQ66PGNX7A` → grace until 2026-09-09) | 2 Workers (us, edge-us), `ci-shared`, GitHub `AWS_SES_{ACCESS_KEY_ID,SECRET_ACCESS_KEY}_US` |
| `cf-cd` | token `af23e9600c96a055421dd3da405e58c9` `rediacc-cd-20260902T152043Z` (prev `8f36d9c1…` → grace until 2026-09-09) | `ci-shared`, GitHub `CLOUDFLARE_API_TOKEN` |

All five were Bitwarden **creates**, as predicted — `ci-shared` went 48 → 53 secrets and the
map gained five entries. `check:ci-bws-map` reports `53 secret(s) mapped, 20 caller file(s)`.
The ASIA org secrets still carry their 2026-04-05 timestamps, which is the ruling holding.

The five are now covered by the shadow run: `cd-deploy-worker.yml:76` (EU pair +
`CLOUDFLARE_API_TOKEN`) and `cd-deploy-account.yml:223` (EU + US pairs +
`CLOUDFLARE_API_TOKEN`), each wired as the full triple — the `NAME > BWS_NAME` request, the
`SHADOW_NAMES` entry, and the `GH_<NAME>` env. ASIA is deliberately NOT added to either:
`ci-shared` holds no ASIA value and the compare step now fails on an empty side, so adding
it would turn the ruling into a red job.

**How the three pre-fixes actually resolved**

1. **Stranded-key preflight — FIXED and proven.** `rotate.ts` now derives one
   `ghSecretPair` and uses it for both the preflight and the push, so they cannot drift;
   `needsGh` ORs it with the consumer scan. Control: the old expression is `false` for
   `ses-eu`/`ses-us`/`ses-asia` while their GitHub push runs, and stays `false` for
   `ses-bench`, which pushes nothing — so the fix fires exactly where the gap was. Live
   proof: with a bogus `GH_TOKEN`, `rotate ses-eu` exits 1 on `GitHub CLI is not
   authenticated` and `iam:ListAccessKeys` shows the key count unchanged. The gh/bws
   preflights were also moved AHEAD of the Cloudflare one, which is the only preflight that
   mutates anything (it mints an ephemeral token on the global-key path).
2. **`bws` — installed by hand, hash-verified.** The 2.1.0 zip named by
   `.devcontainer/Dockerfile` was downloaded, `sha256sum -c`'d against the pinned digest
   BEFORE extraction, and unpacked with `python3 -m zipfile -e` (no `unzip` here). The
   extracted binary is byte-identical to the copy already in the scratchpad.
3. **Map refresh — WIRED INTO ROTATION, not left as a checklist step.** New
   `scripts/rotation/lib/bws-map.ts`, called once in `runRotate` after a successful
   dispatch, for every platform. Rationale: the failure it prevents is silent until some
   later CI job asks for a name the map cannot resolve, and a step with no caller is a step
   that gets skipped — which is precisely why the script had none. It is advisory, never
   fatal: by the time it runs the credential is live, pushed and recorded, so returning
   non-zero would report a good rotation as a failure and invite a re-run. It fired on all
   three rotations and added exactly the five expected names.

### The defect that would have made all of this fail silently: `bws --color`

Found before the first mint, while proving pre-fix 3. **`bws` 2.1.0's default `--color auto`
does not detect a non-tty**: it wraps `--output json` in truecolor ANSI escapes even when
stdout is a pipe or a plain file. Verified against the hash-pinned binary with both
redirections.

Both JSON-parsing callers were therefore broken:

- `scripts/dev/bws-map-refresh.py:77` — died on `bws secret list did not return JSON`. It
  only ever runs through a pipe, so it had never worked.
- `private/account/scripts/rotation/consumers/bitwarden-sm.ts:69` — `JSON.parse` throws at
  char 0, so EVERY `bitwarden-sm:` push would have failed at the `findBitwardenSecret`
  listing, before writing anything. This path had never executed against real `bws`: the
  `bitwarden-sm:` consumers are uncommitted work added AFTER the 2026-09-02T10:22 `cf-r2`
  rotation, the last one to run.

Both now pass `--color no` (a global flag, so it goes in the `bws()` helper). The regression
lives in the two rotation test suites: the fake `bws` now REPRODUCES the bug — it colorizes
unless `--color no` is passed — and the shared `calls()` helper throws unless every recorded
invocation leads with `--color no`. Control: reverting the one-line production fix turns 9
of those tests red; restoring it returns all 26 to green.

## Part 15 — three rulings the operator gave when ASKED, and all three overturned the default

On 2026-09-02 the session put three parked decisions to the operator rather than letting
their timers run. **Every one came back against the session's own recommendation.** That
record is the point of this Part: the defaults were not obviously wrong, they were argued
for, and they were wrong anyway.

### 1. Both backup families renamed, not one (decision 10, applied by a writer)

The deferral offered "rename the grant minter, leave the S3 family as Part 10 says" as its
default, on the reasoning that dropping `CLOUDFLARE_` would overturn a row the operator had
already accepted. The operator took the stronger option: rename both. See decision 10.

### 2. EXTRACT the duplicated span; do not accept the divergence

`check:ci-shape-duplication` failed when a new gate became the third copy of a ~5-line span
(`check-ci-fetch-integrity.ts:114`, `check-guard-mutations.ts:149`,
`check-test-scripts-reachable.ts:187`). The session recorded an accepted divergence with a
`BLOCKER:` reason arguing the three were "a shared token skeleton, not a shared purpose" —
a control-fixture table, a missing-subject refusal and an over-report control — and that a
helper spanning them would take the message, the exit policy and the assertion direction as
parameters.

**That argument was wrong, and the way it was wrong is worth keeping.** It compared the
three sites' INTENTS, which do differ, and concluded there was nothing to share. But what
had been duplicated was the ACT: state why the gate cannot answer, then stop. `refuse(...
lines): never` now lives in `scripts/lib/controls.ts`. Two adoptions were enough to drop
the shape below three copies, so the gate passes with **zero** accepted entries and the
third site never needed touching — the suppression was not replaced, it was deleted.

The `never` return type is what the accepted-divergence path would have thrown away:
callers get unreachable-code checking that a hand-written `console.error(); process.exit(1)`
pair cannot provide. **A suppression argued from intent will always find a difference;
the question is whether the ACT is one thing.**

### 3. The judge blocks on the first missing answer; no retry

The stop-gate judge blocked a stop having produced no structured output, at $0.0731 of a
$0.25 budget with `stop_reason=end_turn` — so neither the budget nor the prompt. Reproducing
the identical call by hand answered cleanly at $0.057 with `stop_reason=tool_use`, proving
an intermittent miss. The session added ONE retry on exactly that shape, arguing that a gate
which blocks on a coin flip gets switched off, which is failing open by a slower route.

The operator reverted it. The retry and its six controls are gone; the judge blocks on the
first miss again. **The standing rule this restates: a judge that fails open is an escape
hatch, and "it was only flake" is the argument every escape hatch is built from.** If the
misses become frequent the evidence will be a pile of blocked stops, which is the loud
failure this project prefers to a quiet recovery.

## Decision 10 — both backup families renamed; `CLOUDFLARE_` comes OFF the S3 family (operator, 2026-09-02)

**This overturns a row of Part 10 that the same operator accepted earlier the same day**
(decision 8ter, "naming table ACCEPTED as written"). The plan's convention is to mark a
correction rather than silently restate it, so the three `BACKUP_S3_* -> CLOUDFLARE_R2_BACKUP_*`
rows are struck through in place, the paragraph that justified them is struck through with
them, and 8ter carries a pointer here. Nothing was deleted.

**How the ruling arose, because it matters that it was not a writer's initiative.** Writer B
raised the collision as a found-not-fixed item. The manager parked it as a deferral whose
DEFAULT was the weaker option — rename the grant minter only, leave the S3 family as Part 10
says — and put the question to the operator directly. The operator chose the STRONGER option:
rename both families, and take `CLOUDFLARE_` off the S3 one. So this is an explicit operator
instruction against a standing accepted decision, not a plan drifting under its implementers.

### The ruling

| was | is | what it actually is |
|---|---|---|
| `CLOUDFLARE_R2_BACKUP_{ENDPOINT,BUCKET,ACCESS_KEY_ID,SECRET_ACCESS_KEY}` | `ACCOUNT_BACKUP_S3_{ENDPOINT,BUCKET,ACCESS_KEY_ID,SECRET_ACCESS_KEY}` | the **S3-API presign path**: presigns against any S3-compatible endpoint |
| `BACKUP_R2_{ENDPOINT,BUCKET,PARENT_ACCESS_KEY_ID,PARENT_SECRET}` | `ACCOUNT_BACKUP_R2_GRANT_{ENDPOINT,BUCKET,PARENT_ACCESS_KEY_ID,PARENT_SECRET}` | the **native-binding grant minter**: locally-signed R2 JWTs over the parent API token |

After this the two names say what they are, and they no longer read as siblings of one
family. `ACCOUNT_*` keeps the `<OWNER>_<THING>` profile with the account service as owner.

### Why `CLOUDFLARE_` was wrong, in the sentence worth keeping

`.ci/scripts/deploy/set-account-worker-secrets.sh` documents this family as the "S3 flavor
(node/elite/RustFS/customer S3)" path. It is what `private/elite/docker-compose.yml` and
`programs/backup-storage/start-local-plane.sh` set for an on-premise MinIO or RustFS install.
So the prefix asked an on-prem operator to configure a **Cloudflare**-named variable for a
service with nothing to do with Cloudflare — the same "what is for what" complaint that
started this whole migration, reproduced inside the migration's own output.

### This family is load-bearing, not merely untidy

On 2026-09-02 `private/elite/docker-compose.yml` was still exporting the OLD `BACKUP_S3_*`
spelling into the on-premise account server after `env.ts` had already moved to
`CLOUDFLARE_R2_BACKUP_*`. zod v4 strips unknown keys, so `createBackupPlane` would have
returned null and on-prem backups would have died with no error anywhere (Part 14 §4).

**The family has now moved TWICE in one day**, through a surface `check:ci-worker-secret-names`
structurally cannot see — elite's compose is not one of its five builders. The standing rule
this leaves behind: **on every pass over this family, re-verify the on-prem sites against
`env.ts` by hand.** Not by inference, and not on the strength of the previous pass having
fixed them. The four sites are `private/elite/docker-compose.yml`,
`private/elite/.env.template`, `private/elite/scripts/s3-conformance-probe.sh` and
`programs/backup-storage/start-local-plane.sh`.

### What moved, and the one thing that deliberately did NOT

Moved (26 files, 179 → 0 occurrences of either old family outside this plan's historical
record): the Worker zod schema, `backup-chunk-store.ts`, the four `src/entry/*.ts`, the
plane-selection test, all five on-prem/local/drill/preflight shell surfaces, the two
`check-*` gates that name it, the `docs/backup-storage/*` runbooks, the `cd-deploy-account.yml`
Worker env block, the Bitwarden NAME column (`.ci/config/bws-secret-map.json` plus the
`bws-secrets` request lines that resolve through it, every UUID untouched), and the Part 10
target column in `scripts/dev/secret-rename.py`.

**The GitHub org-secret names did NOT move.** `BACKUP_S3_{ENDPOINT,ACCESS_KEY_ID,SECRET_ACCESS_KEY}`
stay exactly as they are, under the operator's standing "CI cutover first, rename after"
sequencing. Concretely, in `cd-deploy-account.yml` the LEFT side of `NAME: ${{ secrets.X }}`
became `ACCOUNT_BACKUP_S3_*` while the `secrets.X` on the right is still `BACKUP_S3_*`; the
shadow trio (`SHADOW_NAMES`, `GH_<NAME>`, `BWS_<NAME>`) keys on the GitHub name and so is
untouched, while the Bitwarden NAME on the left of each `>` moved with the map. Those three
names are what `scripts/dev/secret-rename.py` will rewrite when the operator un-defers the
GitHub side — its table now targets `ACCOUNT_BACKUP_S3_*`, and its instrument control was
extended to prove that prefix-add idempotent.

### The trap this rename cost, recorded so the next one is cheaper

`ACCOUNT_BACKUP_R2_GRANT_ENDPOINT` must not be produced by a rename firing INSIDE
`CLOUDFLARE_R2_BACKUP_ENDPOINT`, and the glob spellings (`CLOUDFLARE_R2_BACKUP_*`,
`BACKUP_R2_*`) are load-bearing prose that a `(?=[A-Z])` lookahead silently skips — the first
pass here missed 21 of them exactly that way. Anchor BOTH boundaries with
`(?<![A-Za-z0-9_])` and `(?![A-Za-z0-9_])`, replace the PREFIX only so every suffix and the
`*` form ride along, and do it as ONE alternation in a single pass so no replacement can be
re-matched.

## Part 16 — the store now explains itself, and what that exposed (2026-09-02)

### Every `ci-shared` secret carries a note

The operator's observation: Bitwarden has a notes field, and the repo already knows what each
credential is for — so the store should say it rather than making every reader re-derive it
from the plan. All **53** secrets now carry one, written from Part 10/12/13/14, decision 9,
`rotation-manifest.json`, `lib/config.ts`, `env.ts` and a sweep of every workflow.

**The mechanism was confirmed, not assumed**, and the confirmation is the durable part:
`bws secret edit` takes `--key`, `--value`, `--note` and `--project-id` as a required
one-of group, and the SDK source shows edit is a GET-then-merge (`value:
secret.value.unwrap_or(old_secret.value)`) with the id as a path parameter. So **`--note`
alone never re-supplies the value through argv and the UUID cannot rotate** — which matters
because CI fetches by UUID, so an id change would break every workflow at once. Verified
empirically too: 53 secrets before and after, `id + key + projectId` triples byte-identical.

One secret, `R2_TOKEN_AUTH_API`, is noted as **unattributed** rather than given an invented
purpose: nothing reads it, no slug covers it, and its name predates the convention. The note
says to identify it in the Cloudflare dashboard before revoking. **A note that admits it does
not know is worth more than a plausible one**, because the plausible one ends the inquiry.

### The store's NAMES had not followed the repo, and the gate cannot see that

Decision 10 renamed the S3-presign family to `ACCOUNT_BACKUP_S3_*` everywhere in the tree —
including the committed map, by hand. Bitwarden still held `CLOUDFLARE_R2_BACKUP_*`. Nothing
was broken and nothing would have been: `sm-action` fetches by UUID and the UUIDs never
moved. **The trap is what happens next.** `scripts/dev/bws-map-refresh.py` regenerates the
map FROM the store, so the next refresh would have silently reverted the names, and the
workflows requesting `ACCOUNT_BACKUP_S3_*` would then resolve against nothing.

Fixed by renaming the three keys in place (`bws secret edit --key`, ids preserved), after
which a fresh `bws-map-refresh.py` reproduces the hand-edited map exactly. **The general
rule: a generated file hand-edited to match a rename is a lie with a timer on it.** Either
the source moves too, or the next regeneration undoes the work.

`check:ci-bws-map` cannot catch this by design — it never contacts Bitwarden, and says so in
its own docstring. That blind spot is correct (a gate needing a token degrades to "passed"
wherever the token is absent) but it must be stated where a reader will meet it, which is
here.

### Two coverage gaps the notes work measured

- **Three secrets reach the Workers but are never shadow-compared.** `AWS_SES_REGION`,
  `STRIPE_WEBHOOK_SECRET` and `OBS_OTLP_CREDENTIALS` are consumed by
  `set-account-worker-secrets.sh` (`:59`, `:28`, `:29`) and sit in the map, yet **no workflow
  requests them**, so the comparison that proves Bitwarden matches GitHub never runs for
  them. Same class as the seven gaps decision 9 closed: coverage that looks complete because
  the gate only checks what it is asked for. `OBS_OTLP_CREDENTIALS` is additionally a
  pre-regional leftover — the regional names do not exist in `ci-shared`, and the first
  `rotate otlp-<region>` creates them.
- **`check_bws_map.py` does not scan the vendored breakpoint workflow.** It globs
  `.github/workflows/*.yml` and `.github/actions/*/action.yml`, but
  `.ci/breakpoint/workflow/breakpoint.yml` is a REAL `bws-secrets` call site requesting two
  names. A name added only there is never validated — and `check-breakpoint-drift.sh` pairs
  the two files precisely because they are expected to move together.

---

## Part 17 — the shadow compares 35 of 53, and that is one bug, not eighteen judgement calls (2026-09-02)

### The correction to Part 16

Part 16 recorded "three secrets reach the Workers but are never shadow-compared" and treated
them as three known consumers that had been missed. **The real number is 18 of 53**, and
framing them as individual oversights was the error. Measured with `check_bws_map.py`'s OWN
request parser (`parse_requests`, so the count cannot disagree with the gate's) across
`.github/workflows/`, `.ci/breakpoint/workflow/` and both submodules' `.github/workflows/`:

```
requested by some workflow : 35
requested by nobody        : 18
map total                  : 53
```

The 18: `AWS_SES_HOST`, `AWS_SES_REGION`, `GITHUB_APP_CLIENT_SECRET`,
`GITHUB_AUTOPILOT_APP_ID`, `OBS_OTLP_CREDENTIALS`, `OBS_OTLP_PASSWORD`, `OBS_OTLP_USERNAME`,
`R2_TOKEN_AUTH_API`, `SMTP_FROM`, `SMTP_HOST`, `SMTP_PASS`, `SMTP_PORT`, `SMTP_USER`,
`STRIPE_PUBLISHABLE_KEY`, `STRIPE_SANDBOX_PUBLISHABLE_KEY`, `STRIPE_SANDBOX_WEBHOOK_SECRET_ID`,
`STRIPE_WEBHOOK_SECRET`, `STRIPE_WEBHOOK_SECRET_ID`.

### Why it matters more than a coverage number

The shadow run exists to prove, BEFORE cutover, that the Bitwarden copy of a secret equals
the GitHub copy. For a name no workflow requests, that comparison never runs — so cutover
flips it on the strength of nothing. And the failure is silent in exactly the way this whole
plan was written about: an unset secret evaluates to `""`, `sm-action` exports `""` without
complaint, and zod's `z.object()` normalises `""` to undefined. That is the OTLP class,
which is why `check-workflow-gates.sh` CHECK 2 exists at all.

### The operator's reading, which reframed it

Offered a choice of how to LABEL the 18 (an `_` prefix in the store so they are recognisable
at a glance), the operator rejected all three options:

> *"This is a huge bug. STRIPE AUTOPILOT AWS and R2 maybe should be used for something! It
> seems either we or the system has a bug! Let's employ parallel sub-agents to find the
> gaps!"*

That is right, and it is the difference between a symptom and a cause. Marking the 18 would
have made the gap legible and permanent. Several of them plausibly SHOULD be wired — the
operator's later hint that **there is a per-PR preview deployment, which is where sandbox
Stripe actually lives**, is exactly the kind of consumer a workflow-level `secrets.*` sweep
cannot see, because the names are set inside a deploy script rather than named in the YAML.

### What is running

Five read-only agents, one per family plus one on the mechanism: Stripe (including the
per-PR preview path), autopilot and the two GitHub Apps, SES and the SMTP set, R2/Cloudflare
plus identifying `R2_TOKEN_AUTH_API`, and the systemic angle — what rule produced the current
request list, what it structurally cannot see, and the exact missing gate assertion. Each
returns per name: WIRE IT (with the consumer's `file:line` and where the request line
belongs), DEAD (with what was searched), or OPERATOR.

**No renaming happens until that lands.** A `_` prefix on a secret that turns out to have a
consumer is worse than no prefix: it says "nothing depends on this" in the one place a reader
will believe it.

### The gate that would have caught it, stated but not built

`check_bws_map.py` asserts one direction only — every REQUESTED name exists in the map. The
missing assertion is the converse: every MAPPED name is either requested by some workflow or
carries an explicit, reasoned exemption. Anti-vacuity matters as much as the rule (an empty
exemption list and an empty request set would both pass a naive version), and the exemption
list is the design question, not the scan. Agent 5 is specifying it; it is deliberately not
implemented ahead of that.

### One unrelated defect fixed while checking `.env` coverage

`scripts/dev/secret-rename.py --apply` rewrote every file in place with no backup. For
tracked files git is the undo. For the two in `EXTRA` — `private/account/.env` and
`.env.bench`, untracked live-credential files — there was none, so a bad `--apply` destroyed
them irrecoverably. `:269` now copies each untracked target to `<name>.pre-rename.bak` (mode
0600) before the first write and refuses the whole run without writing anything if a backup
fails, because a half-rewritten credential file is worse than no rewrite. Dry run unchanged
at 1291 replacements in 103 files (up 2/1 from Part 12's 1289/102: `.github/external-callers.yml`
is new and names `CLAUDE_CODE_OAUTH_TOKEN` twice, which is correct — the registry follows the
rename instead of drifting from it).

### Part 17b — what the five agents found, and the correction to Part 16's mechanism

**The root cause, measured on this session's own run rather than taken from a report.** The
request list is a SET INTERSECTION, not a coverage rule:

```
mapped 53   requested 35   map-names-with-a-console-reachable-GitHub-twin 35
requested XOR has_twin: EMPTY -- an exact bijection
```

None of the 18 was a judgement call. "Unrequested" is definitionally "no GitHub secret of that
name exists", because the shadow's left operand IS a GitHub secret. So the shadow proves the
OVERLAP agrees and asserts nothing whatever about coverage — and `check_bws_map.py` asserts
`requested ⊆ map`, the same direction a third time.

**Part 16's mechanism was wrong, which matters because it implies the wrong fix.** It said
`AWS_SES_REGION`, `STRIPE_WEBHOOK_SECRET` and `OBS_OTLP_CREDENTIALS` "are consumed by
`set-account-worker-secrets.sh`, yet no workflow requests them". The scripts consume the *env
var* of that name; CI populates that env var from a **differently-named** GitHub secret or from
`vars.`. "Add a request line" is therefore wrong for the first two — they have no GitHub value
to compare against at all. `AWS_SES_REGION` is public data already committed in
`regions.json:17,35,53` and should never enter a secret store.

**THE CUTOVER BREAKER.** `set-account-worker-secrets.sh:134-135` builds
`OBS_OTLP_CREDENTIALS_${SUFFIX}` at RUNTIME and `_require_nonempty`s it at `:209`; today it is
fed from `secrets.OTLP_CLIENT_CREDENTIALS_{EU,US,ASIA}` (`cd-deploy-account.yml:404-406`), which
`secret-rename.py:70-72` renames to exactly those three names — **none of which is in the map**.
No scan on either side can see them, because the name never appears as a literal. This is the
founding OTLP incident, reproduced by the migration built to prevent it. Severity, stated
precisely: `_require_nonempty:185-192` **exits 1**, so all three regions fail the deploy LOUDLY
rather than shipping blank. The Part 14 guard is the whole difference. The three values are
readable nowhere (GitHub secrets are write-only; `.env` holds only the unsuffixed copy), so they
must be created by `./run.sh rotation rotate otlp-eu|otlp-us|otlp-asia`, which mints — operator
work, and `rotation sweep` must never be run.

**The largest wiring gap is not in the 18 at all.** `CLOUDFLARE_API_TOKEN` is spent by **12 jobs
across 10 workflows** and shadow-requested by **2**; `edge-clone-d1.yml:55` consumes it with no
`bws-secrets` step in the file. It IS shadow-compared, in `cd-deploy-account`/`cd-deploy-worker`,
which is exactly why a name-count of 35-vs-18 could not see it. **Counting names hides
per-job coverage.**

**A measurement trap for whoever builds the gate.** A file-level `secrets.X`-vs-request scan
reports 75 gaps, but ~48 are PASSTHROUGH declarations in `cd-v2.yml` and `promote-stable.yml`
(`secrets:` blocks feeding reusable callees that request inside). The gate must be **job-level
and passthrough-aware**, or its first run is 48 false positives and it gets switched off.

**`R2_TOKEN_AUTH_API` is identified** — the raw bearer VALUE of a Cloudflare R2 API token, the
third artifact beside `id` (= access key id) and `sha256(value)` (= secret access key);
`rotate.ts:502-505,724-726` implements that transform and never pushes the raw value for
`cf-r2`. Dead as a stored entry. Whether the Cloudflare TOKEN is dead is settled without
revealing anything by comparing `sha256(R2_TOKEN_AUTH_API)` against
`CLOUDFLARE_R2_SECRET_ACCESS_KEY`: equal means it is the active `cf-r2` credential and revoking
it breaks every R2 upload.

**Two credentials are in no store at all** — `SES_AK_ID`/`SES_AK_SECRET`, the AWS IAM **admin**
pair the rotation tool authenticates with (`rotation/lib/credentials.ts:60-61`), strictly more
powerful than the four SES sending keys that ARE stored; and the `dkim-notify` RSA key
(`rotation-manifest.json:152-157`), staged by hand. A larger hole than the 18, and the subject
of `agent/PLAN-env-to-bitwarden.md`.

**Verdicts on the 18:** all DEAD except `GITHUB_AUTOPILOT_APP_ID`, which is *unshadowable* — it
is `vars.AUTOPILOT_APP_ID`, no GitHub secret of that name exists, and the comparator fails on an
empty side, so adding a request line would turn the shadow RED. All 53 notes now record their
own verdict; 16 were corrected after the agents contradicted them.

### Part 17c — the gate that closes it (2026-09-02, operator: "build the whole cluster")

`check_bws_map.py` asserted one direction: `requested ⊆ map`. Three converse
assertions now sit beside it, each the converse of something already checked, plus
`.ci/config/bws-unrequested.json` — the only escape hatch, and every entry's `kind`
is RE-DERIVED rather than believed.

- **5. COVERAGE.** Every mapped name is requested by some call site, or exempt.
- **6. PER-JOB.** Every `secrets.X` a job reads DIRECTLY is requested by that job's own
  bws step. Counting names hid this: `CLOUDFLARE_API_TOKEN` was compared in 2 of the 12
  jobs that spend it, so a name-level count showed it covered. Passthrough jobs are
  COMPUTED and excluded, never exempted — the file-level version opens with 48 false
  positives and gets switched off in a week.
- **7. SUFFIX EXPANSION.** `VAR="PREFIX_${SUFFIX}"` + `${!VAR}` in a deploy script demands
  names that appear as a literal nowhere. This is the assertion that would have caught the
  OTLP breaker, and on its very first run it found two MORE:
  `AWS_SES_{ACCESS_KEY_ID,SECRET_ACCESS_KEY}_ASIA`.

**The three kinds, and what re-derives each:**

| kind | re-derived against | goes red when |
|---|---|---|
| `no-github-twin` | `secret-reachability.json`, for the name AND every rename pre-image | the org secret is created — the shadow becomes possible, so the exemption must end with it |
| `deferred` | its own `expires` date, and it must name a worklist id | that date passes, whether or not anyone looked |
| `superseded-at-runtime` | the deploy script must BOTH branch on the suffix and reassign from the named region | the substitution is removed — the secret is genuinely needed again |

`superseded-at-runtime` exists because of the ASIA pair: the org secrets exist and are
reachable, so `no-github-twin` is false, yet `set-account-worker-secrets.sh:123-131` reads
them and immediately overwrites them with the EU pair. "Read and thrown away" is a third
state, and collapsing it into either of the others would have been a lie.

**Proven both ways, not asserted.** 11 controls run inside `--selftest` before any verdict,
covering every way of writing a bad exemption plus a clean allowlist that must stay SILENT
(the direction "every fixture reds" would pass). Then nine defects were planted against the
REAL tree and each required to red with its own message — a dropped exemption, a
`no-github-twin` claim whose twin now exists, a job reading what it does not request, the
ASIA substitution removed, an exemption naming nothing, an exemption for a name that IS
requested, a SUFFIX name neither mapped nor exempt, the SUFFIX scan losing its subject, and
an emptied reachability file. All four touched files restored byte-identical afterwards and
the clean tree passes.

Two blind spots closed in passing: the gate now scans `.ci/breakpoint/workflow/` (a real
call site Part 16 recorded it could not see), and it reads the rename table out of
`secret-rename.py` as DATA rather than keeping a second copy — a second copy of a name table
is the exact defect this gate exists to find.

**Also landed under the same ruling:** `SMTP_PASS` renamed in the store to `SMTP_PASSWORD`,
uuid preserved, map regenerated from the store. The old spelling could not configure
anything (`env.ts:123` declares `SMTP_PASSWORD`), and zod v4 strips the unknown key, so
wiring it would have authenticated with `pass: undefined` and `smtp.ts:66-70` would have
swallowed the failure and returned false. Silent non-delivery, disarmed before anyone wired
it.

---

## Part 18 — four rulings, and what executing them corrected (2026-09-02, after the /ask)

The operator took every recommended option. Executing them changed three things the
plan had wrong.

### The rename needs THREE secrets minted, not five

The ruling was "mint the 5, then apply". Executing it found the preflight I had just
written was **over-strict**: it demanded a map entry for every rename TARGET, but
`SES_AK_ID`/`SES_AK_SECRET` -> `AWS_IAM_ADMIN_*` is a rename of names that live only in
`private/account/.env`. They are not GitHub org secrets (`secret-reachability.json`
confirms), nothing fetches them from Bitwarden, and blocking the whole rename on creating
a secret with no consumer is a refusal to act dressed as caution.

`scripts/dev/secret-rename.py` now re-derives the set from reachability: a target must be
mapped only when its SOURCE is a console-reachable org secret. That leaves exactly three,
all genuinely operator-only: `OBS_OTLP_CREDENTIALS_{EU,US,ASIA}` via
`./run.sh rotation rotate otlp-eu|otlp-us|otlp-asia`, which MINTS. Never `rotation sweep`.

### `bws secret delete` cannot be told apart from a hard delete, and that is the answer

Probed live with a throwaway secret carrying a generated value (53 secrets before and
after, nothing real involved). After `delete`, the id 404s on `get` and disappears from
`list` — which is exactly what BOTH soft-delete-to-Trash and hard delete look like from
the CLI. The docs say Trash holds a deleted secret for 30 days, but **`bws` has no trash,
restore or undelete verb**, so even when Trash works, recovery is a human in the web UI.

Consequence for the operator's clone -> delete -> update protocol: its safety net is
human-only and 30 days long, and for 9 of the 11 wired slugs it duplicates the `grace`
window they already have. The genuinely new coverage is `turnstile`, which carries no
`versions` array at all. Parked as `[?] #09ff1d77`; its default replaces the protocol with
a `<NAME>_PREV_<datestamp>` entry that needs neither trash nor a human.

### The `.env` files: NOTHING is removable yet, and the measurement is the deliverable

Operator ask: archive the local `.env` files and leave only what Bitwarden needs. Archived
all five untracked ones to `~/archive/env-20260902T2045Z/` (paths and mode 0600 preserved,
sha256 recorded). Then measured before deleting anything, name-only: **all 50 keys in
`private/account/.env` have live readers**, as do 17 in `packages/e2e-tests/.env`, 16 in
`.env.groupb` and 6 in `.env.bench`. Zero are safely removable, because the fetch mechanism
is designed and not built — stripping the file breaks `./run.sh account dev`,
`scripts/dev/deploy-bench.sh`, `./rdc.sh --dev`, renet's licence-key ldflags and
`private/growth`'s publish pipeline.

**A near-miss worth recording as a method, not an anecdote.**
`private/growth/apollo-companies/.env` first measured as 9 of 10 keys unreferenced. That
was WRONG: `private/growth` is its own git repository, so `git grep --recurse-submodules`
from console cannot see it, and the consumers are `to_mautic.py` and
`gemma_outreach/mautic_push.py`. A scan that cannot see a consumer reports the same thing
as a key with no consumer. **Before deleting on the strength of "no hits", prove the scan
could have found a hit.**

So the end state is documented rather than enacted: a three-group header on the live file
and on the tracked `.env.example` — the BOOTSTRAP (`BWS_ACCESS_TOKEN`, which can never come
from Bitwarden), the ~21 keys of non-secret LOCAL CONFIG that stay forever, and the
credentials that move one at a time. Worth stating plainly because the ask assumed
otherwise: the target is **not** "only the Bitwarden token". `PORT`, `SELLER_*`,
`WEBAUTHN_*`, `AUTOPILOT_APP_ID` (an Actions variable) and `AWS_SES_REGION` (public,
already committed in `regions.json`) are not credentials and gain nothing from a fetch.

`private/elite/.env.template` is explicitly out of scope: those values are supplied by the
CUSTOMER on their own on-prem install and must never enter our store.

### The shape rule fires, and both branches stayed testable

`wl_shapedup.read_verdict` no longer maps `already` + a real harness to silent. Rather than
delete the branch the fixture was testing, `harness_real` moved onto the payload and picks
the ORDER: an existing harness gets "adopt it", a claimed one gets "extract it". 269
controls green.

---

## Part 19 — THE RENAME APPLIED (2026-09-02), and the three things that went wrong doing it

Operator ruling: *"Mint the 5, then apply."* Executing it corrected the count to THREE
(Part 18), and once `OBS_OTLP_CREDENTIALS_{EU,US,ASIA}` existed the preflight cleared and
`--apply` ran. **The rename is no longer dry-run only. It has landed, uncommitted.** The
dry run now reports `0 replacement(s) in 0 file(s)` — idempotent, nothing half-done.

The OTLP trio was created by COPYING the unsuffixed value, on the operator's instruction
(*"for the otlp we must copy what we have for all 3 regions"*) — one self-hosted collector,
one login.

### 1. The copy exposed a live defect in the value itself

`OBS_OTLP_CREDENTIALS` is documented everywhere — this plan included — as `USER:PASS`.
**The code disagrees.** `private/account/src/routes/telemetry.ts:41` runs `JSON.parse` and
requires string `user` and `pass` fields; `container.ts:132-137` states the contract as
`{"user":"...","pass":"..."}`. The stored value is **neither JSON nor colon-separated**, and
`telemetry.ts:47-50` catches the parse failure and returns `{otlp: null}` — **fail closed and
silent**, so clients keep telemetry off and nothing says why.

Scope, stated honestly: only the BITWARDEN copy was read. Deployed Workers take theirs from
the write-only GitHub org secrets, which may be correct — detecting exactly that difference
is what the shadow run is for. All four OTLP notes now carry the real contract and say the
fix is `rotation rotate otlp-<region>`, never a hand-edit.

### 2. I destroyed 26 workflow files, and the recovery is the interesting part

`actionlint` correctly flagged the duplicate keys the `STRIPE_SECRET_KEY_{EU,US,ASIA}`
collapse produced — the hand-edit this plan's own AFTER--apply list names. I wrote a script
instead. Its indent tracking treated same-depth keys in DIFFERENT blocks as duplicates, so it
kept the first `name:`/`run:`/`env:`/`uses:` per indent and deleted the rest: **2001 keys
across 26 files, 12 left unparseable.** I ran it across all 26 without reading the first
file's output.

Recovery, with the operator's approval, from four sources: 8 files from `.bak` copies taken
earlier the same turn (which still carried the shadow wiring), 2 from harness file-history
snapshots, `breakpoint.yml` from `.ci/breakpoint/workflow/` — the vendored copy the glob never
touched — and 15 from `HEAD`, losing their wiring.

**Then the gate written that morning produced the repair recipe.** `check_bws_map.py`
assertion 6 enumerated all 85 missing request lines with file, line, job and secret. 26 job
sites were rebuilt from that enumeration rather than from memory: 10 gained names on an
existing step, 16 gained a whole shadow pair. Final state: `56 secret(s) mapped, 22 caller
file(s), floor 22, ZERO reads-without-request`.

Two lessons worth more than the incident. **A gate that enumerates its findings precisely
enough is also a repair tool** — that is a reason to spend the extra effort on a finding's
text. And the narrow redo of the same job removed **8 duplicates across 3 files** instead of
2001 across 26, by being narrow in three ways at once: one named key, only inside a
`secrets:`/`env:` mapping, only second-and-later occurrences.

### 3. CHECK 4 caught a cross-repo break within hours of being written

Repairing the contract, I declared `BWS_ACCESS_TOKEN` **required** in
`claude-review-reusable.yml` — which `private/account` and `private/renet` call and cannot
pass. That breaks THEIR next run, an hour later, in a log nobody on the console PR reads.
CHECK 4 (Part 17's D3) reported it immediately and named the fix. It is back to
`required: false` with both shadow steps repo-guarded, which is the design it always had.

### 4. The rename broke a repo it could not see

`private/growth/video_pipeline/{publish-solutions.sh,publish.py}` require
`R2_MEDIA_{ACCESS_KEY_ID,SECRET_ACCESS_KEY,ENDPOINT}`; `.env` had become
`CLOUDFLARE_R2_MEDIA_*`, so the publish pipeline died at its step-0 credential check.

`files()` walks `git ls-files --recurse-submodules`, which reaches submodules but **not
`private/growth`** — its own git repository, gitignored by console. Fixed both files and the
gap: `NON_SUBMODULE_REPOS` now asks each sibling repo its OWN index. Surface 6,622 -> 17,870
files, and the dry run over the widened surface reports 0 replacements, which independently
proves the manual fix was complete. Same blindness that earlier reported 9 of 10 keys in that
repo as unreferenced; closed at the tool rather than remembered.

### Corrections to earlier Parts

- **Part 18's "all 50 `.env` keys have live readers" is wrong: 49 do.** `R2_MEDIA_BUCKET` has
  zero readers (`sync-media-to-r2.sh:35` hardcodes the bucket), and
  `.claude/agents/media-pipeline.md:343` claims it is not in `.env` when it is, at line 41.
- **`SMTP_PASS` is now `SMTP_PASSWORD`** in the store (uuid preserved, map regenerated from
  the store) — the spelling `env.ts:123` actually reads.
- **A hazard for the `.env` -> Bitwarden work**: `STRIPE_WEBHOOK_SECRET` is ONE name for TWO
  different things. `.env` holds the committed E2E fixture constant (the same literal as
  `.ci/lib/account.sh:238`); the store holds the real production secret. A naive fetch by
  name into `account dev` would sign simulated webhooks with the PRODUCTION key
  (`account.sh:825-827`). Rename the local key before any fetch helper exists.

### What is left, and it is not analysis

`check:ci-secret-reachability` is RED and stays red until the **GitHub org secrets are
renamed**: its record is keyed on the old names, the tree now references the new ones, and
`--refresh` needs an org-admin token. The gate is reporting exactly the gap it exists to
report. That, plus `gh secret set` for the renamed set, is the operator's next step.

---

## Part 20 — the operator's half, generated rather than described (2026-09-02)

Part 19 left one gate red: `check:ci-secret-reachability`, because its record is keyed on the
OLD org-secret names while the tree now carries the new ones. That is the gate reporting
exactly the gap it exists to report, and closing it is operator-only three times over —
GitHub has no rename verb, secret values are write-only so nothing can read one to copy it,
and `--refresh` needs an org-admin token.

So the half that WAS ours is done: **`scripts/dev/rename-org-secrets.sh`**, generated from
`secret-rename.py`'s `RENAMES` table intersected with `secret-reachability.json`'s
console-reachable list. It therefore names exactly the **22 org secrets that both exist and
are renamed**, collapsing into **20 targets**, and nothing else — no guesses, no names from
memory. Three deliberate properties:

- **Every command is commented out.** It deletes org secrets, and each `set` needs a value
  only the operator holds. An executable that does both is one stray `bash` from an outage.
- **The deletes are a separate block, after the sets.** Set, let one CI run go green, then
  delete. GitHub keeps no undo for a deleted secret.
- **It is regenerated, not maintained.** If `RENAMES` or the reachability record moves, the
  checklist moves with them, so a paste that waits a week is still correct.

### The three deploy-contract corrections, and the rule behind them

Rebuilding `cd-deploy-account.yml` and `cd-deploy-worker.yml` from the Bitwarden map (the
operator's rule: *"we should always have what we have at bitwarden side in the code"*) got 57
of 60 exports right and **three wrong, all the same way**: `AWS_SES_REGION` in both files and
`STRIPE_WEBHOOK_SECRET` in the worker are IN the map, so a map-driven rule chose
`secrets.<name>` — but their source here is `matrix.sesRegion`, `vars.AWS_SES_REGION_EU`, and
a per-CHANNEL ternary respectively.

**The map is the NAMING authority, not the SOURCE authority.** A name being in the store says
what it is called, never where a given workflow should read it from. All three were caught by
`actionlint` and CHECK 2 within one run, which is the argument for having them.

### Assertion 8: every stored name must appear in the code

Operator ask, and it generalises the whole programme: *"generate a new CI gate for from
bitwarden match ... not just for this session."* `check_bws_map.py::represented_problems` now
requires every stored name to be spelled somewhere in the tree, or carry an exemption.

The corpus is console **plus submodules plus the gitignored sibling repos** — the last part
matters, because that blindness is what let this rename break `private/growth`'s publish
pipeline (Part 19 §4). Names beginning with `_` are skipped, the operator's marker for a
parked entry; there are none today. The map, the allowlist and `agent/` do NOT count as an
appearance, or every name would satisfy the rule by being written down in the file that lists
it. It prints `48 of 56 stored name(s) appear in the tree` so a silent pass is visible.

Why it is worth having beyond this session: **a name the code never mentions cannot be renamed
safely**, because a rename tool can only move a name it can see. That is the general form of
every incident in Parts 17-19.

---

## Part 21 — the gates written after the incidents, and one that was measured and NOT written

Parts 17-20 record what went wrong. This records what now stops each class from recurring,
and one case where the honest answer was to build nothing.

### `check:ci-greenlight-closures` — new, wired, and it found the live defect first run

Every path a `greenlight.cjs` closure names must exist on disk AND be tracked by git.
Greenlight hashes the CONTENTS of those paths off the REMOTE commit, so a path resolving to
nothing there makes it refuse — and `gate-test:greenlight` then reds naming the KEY, not the
path, which is why the diagnosis cost real time. Control-first: a missing path and an
untracked path are planted against a `mktemp` git fixture and each must be reported, plus a
clean fixture that must stay SILENT; it exits 2 without judging the real tree if a control
misbehaves. First run reported `.github/actions/bws-secrets -- on disk but NOT TRACKED`.
Now `all 77 declared path(s) exist and are tracked`.

**Its residue is printed in its own output rather than hidden**: tracked is not IN HEAD, so a
staged-but-uncommitted path still reds `gate-test:greenlight` while this passes. Asserting
HEAD-presence would red on every new file in an uncommitted tree — this repo's standing state
— and a gate that is always red gets switched off.

### `check-worker-secret-names` was under-extracting, and the first fix did not hold

Its `SCHEMA_KEY` regex required `z.` on the same line, so a prettier-wrapped
`MIN_CLI_VERSION: z` was invisible: **84 of 85 keys**. A latent FALSE POSITIVE — the day a
builder pushes that key, the gate calls a correct line undeclared.

Fixing the regex was easy. What is worth recording is that **the obvious guard did not
work**: raising the population floor from 40 to 80 still let 84 through, reporting "84 schema
keys" as though that were the answer. A floor guards against finding NOTHING; only an exact
count guards against finding ALMOST everything. So `EXPECTED_SCHEMA_KEYS = 85` sits beside
the floor as a ratchet, updated deliberately in the same commit as a key change — and with
the old regex it now reds `yielded 84 keys, expected exactly 85`.

**General form, and it applies to every anti-vacuity floor in this repo**: a floor set well
below the real population cannot detect a small loss, and a small loss is the shape that
produces a wrong verdict rather than an obvious one.

### The gate that was measured and deliberately NOT written

The stale-`file:line`-citation class looked gateable. Measured: **755 citations in comments
and markdown prose across the tracked tree, 4 out of range** — 0.5%, two files, both
historical `agent/` plans, none in code. All four fixed; the count is now 754 and zero.

But an out-of-range check would have caught **NONE** of the three stale citations actually
fixed this session: `build.sh:409` was cited as `:333-343`, a real line that was the wrong
one; `check-env-credential-drift.ts` named a script with zero `.env` references;
`media-pipeline.md:343` asserted the exact opposite of the truth. All three resolve. All
three were wrong.

So the mechanically checkable subset is 0.5% of the population, and `TRAPS.md` already carries
the class as `wrong-comment-is-a-delayed-defect`, JUDGMENT-ONLY, residue *"No parser knows
what a comment OVERCLAIMS"*. **A gate here would give false comfort about the other 99.5%**,
which is a worse outcome than the honest absence of one. Measuring first is what made that
answerable instead of a matter of taste.

### Two defects found on the way, both fixed

- `ct-tests.yml` set `SSH_USER: ${{ env.USER }}` at two sites. The GitHub `env` CONTEXT holds
  only workflow/job/step `env:` keys and that file defines no `USER`, so it always expanded to
  `""`. Harmless only by luck: both consumers use `${SSH_USER:-...}` and `:-` treats empty as
  unset. Change either to `${SSH_USER-...}` and every SSH targets `@$VM_IP` with no user.
  Removed — the shell fallback is where `$USER` is real.
- The aliasing survey (`agent/PLAN-secret-names-one-to-one.md`) corrects this plan's premise:
  of 859 workflow secret-name bindings, 465 are aliases, but **394 of those are the `GH_`/
  `BWS_` shadow pair, structurally forced while the shadow runs and dead at cutover**. Only
  **22 lines** are gratuitous. The four-namespaces framing is history: `env.ts` and the store
  share 21 keys with **zero spelled differently**.

---

## Part 22 — the endgame changed: GitHub secrets are being DELETED, not renamed (2026-09-02)

Operator directive: *"let's remove github secrets completely and migrate fully to the
bitwarden."* This supersedes the last step of this plan. The design was
shadow -> cutover -> **rename the org secrets**. It is now shadow -> cutover -> **delete the
GitHub side entirely**. Full design: `agent/PLAN-github-secrets-removal.md` (564 lines).

**The org-secret rename is CANCELLED, and `scripts/dev/rename-org-secrets.sh` must not be
run.** The rename existed so this tree's `secrets.<NEW>` reads would resolve; under the new
directive those reads are deleted in the same commit that adds the fetch, so no `secrets.<NEW>`
read ever exists — 22 handlings of waste, 11 operator-only. Worse, its DELETE half removes
exactly the pre-image names the shadow comparison needs as its left operand. What the rename
appeared to buy is free: point the shadow's GH side at the PRE-IMAGE (102 of the 197 `GH_`
lines), generated from Part 12's table rather than typed. The script stays on disk as the
record of what would have been renamed.

**The irreducible set is exactly ONE**: `BWS_ACCESS_TOKEN`, in console, account and renet.
Proven, not assumed — all 28 workflows plus the vendored breakpoint copy parsed, and every
position where the `env` context is unavailable walked (`jobs.<id>.env`, `.if`, `.secrets.<id>`,
`strategy`, `container`, `services`, `environment`, `steps[*].if`). Zero reads outside
step-level `env:`/`with:` and passthroughs; zero `secrets: inherit`; zero environment-scoped
secrets. Of 664 reads, 7 sit in a step BEFORE the fetch (all `GITHUB_APP_PRIVATE_KEY` feeding
`app-token`) and reorder cleanly. Of 48 stored secrets: 43 deletable, 3 blocked, 1 stays.

**The risk that matters is not the deletion.** The Bitwarden layer HAS NEVER RUN: the composite
action is not in HEAD and not one of the 63 comparisons has executed. Everything Parts 17-21
built is unproven against a live run. The mitigation is already in the design — each compare
step sits between the fetch and every consumer IN ITS OWN JOB and fails on mismatch OR on
either side being empty, so through the soak it is a precondition rather than an observer.
Second-order: after deletion Bitwarden is the only copy CI can reach and `gh secret` has no
`get`; recovery covers roughly 90% of rows (vault, `.env` under new spellings, re-mintable
slugs) but Stripe, Dockerhub and the App key are dashboard-or-reissue only.

### The pre-landing audit, and the one that was fail-OPEN

An agent audited the whole uncommitted diff, because the tree had been through
rename -> destruction -> recovery from four sources and nobody had read it end to end.

**P1, mine, fail-OPEN on production**: `cd-deploy-worker.yml` had lost the per-channel ternary
on `STRIPE_SECRET_KEY` while the webhook four lines below kept its — an EDGE deploy would have
configured the www Worker with the LIVE Stripe key against a SANDBOX webhook secret, a pair no
code path expects. Restored. **My first restore used HEAD's `STRIPE_SECRET_KEY_EU`, which the
collapse had removed, and assertion 9 — written an hour earlier — is what caught it.**

**P2, fail-closed but total**: the `cd-deploy-account` matrix projection never emitted
`backupBucket`, `edgeBackupBucket` or `r2Jurisdiction`, so all three resolved empty and every
account deploy exited 1. `regions.json` nests two of them, so the jq had to map as well as
select. The dead `STRIPE_KEY_${SUFFIX}` indirection was DELETED rather than repaired: the
collapse had made all three bindings one value, so it chose between identical things on a
`SUFFIX` that no longer existed.

**P3/P4**: a sparse cone missing the composite action and the map; and a rename that rewrote a
**detector pattern** (`APP_PRIVATE_KEY` -> `GITHUB_APP_PRIVATE_KEY`) in a portability gate, so
it silently matched nothing in the vendored trees it exists to police. Both fixed.

Clean, with the searches that prove it: 63 fetch steps, 63 compare steps, 197 names, zero
inconsistent triples; a 5,738-leaf HEAD-vs-tree diff with all 128 differences accounted for;
719 `run:` bodies compared with zero losses.

### What the local side gained

`.ci/lib/bws-env.sh` — the shared fetcher whose absence was the real reason `.env` could not
shrink. Every plan to empty that file had been blocked on the same gap: 19 of its 49 keys are
already in Bitwarden and merely duplicated, but nothing could put a stored value into a local
shell. It never prints a value, never caches to disk, and never falls back to `.env` — a
silent fallback is how a dead fetch keeps working locally and fails in CI. Seven cases in
`test-bws-env.sh` with a faked `bws`, including the one that matters: an empty stored value
FAILS rather than exporting a blank.

`test-bws-map.sh` closes the other gap the removal plan named: `check_bws_map.py`'s assertions
5-9 are defined over the tree and had no fixture coverage at all, while being about to become
the sole guard on every credential. A `BWS_MAP_ROOT` override makes the real scan drivable
against fixtures, and the fourth case proves that override is not an escape hatch — an empty
tree still reds, because the anti-vacuity clauses fire.
