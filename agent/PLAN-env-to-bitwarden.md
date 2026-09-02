Status: draft
Owner: 74de73ca
Date: 2026-09-02
Scope: design only. Nothing here was executed against Bitwarden, AWS, Cloudflare or GitHub.

# `.env` → Bitwarden: shrink the local secret file to a bootstrap token, and give
# rotation a recoverable pre-rotation copy

## Tasks

- [?] Verify empirically that `bws secret delete` soft-deletes to Trash and that `bws secret list` excludes trashed rows (throwaway secret in a scratch project). Everything below Part 4 depends on it.
      AUDIT: UNVERIFIABLE from the tree: a live-store experiment leaves no in-tree artifact and `bws` is not installed here. Proof would be a recorded result committed under docs/ or noted in .ci/config/bws-token-expiry.json.
- [ ] Mint machine accounts `mc-ci-read` (read, ci-shared) and `mc-rotate` (read/write ci-shared + read admin-bootstrap); replace the token expiring 2026-09-08 and update the GitHub org secret `BWS_ACCESS_TOKEN`.
- [ ] Create the `admin-bootstrap` SM project and seed the 5 names ci-shared lacks (`UPSTREAM_API_KEY`; `AWS_ADMIN_ACCESS_KEY_ID`, `AWS_ADMIN_SECRET_ACCESS_KEY`, `CLOUDFLARE_GLOBAL_API_KEY`, `CLOUDFLARE_ACCOUNT_EMAIL`), then refresh `.ci/config/bws-secret-map.json`.
- [ ] Write `.ci/lib/bws-env.sh` implementing `bws_export` with the `NAME > LOCAL_NAME` grammar, no cache by default, and the seven loud failure modes (Part 3).
      AUDIT: PARTIAL: .ci/lib/bws-env.sh:1-105 exists with no-cache-by-default and five named failure modes, but the function is `bws_env_load` not `bws_export`, there is NO `NAME > LOCAL_NAME` alias grammar (so the AWS_SES_*_EU collapse is inexpressible), it binds with `export` not `declare -g`, and there is no `set +x` guard.
- [ ] Add `with_fake_bws` to `.ci/scripts/test/lib/test-helpers.sh` beside `with_fake_gh` (`:93-112`).
- [ ] Write `.ci/scripts/test/gates/test-bws-env-helper.sh` with assertions B1-B7 and their planted-defect controls; wire it three-point (package.json + `scripts/ci-runner/manifest.ts` + `.github/workflows/ci-quality.yml`).
      AUDIT: PARTIAL: landed as .ci/scripts/test/gates/test-bws-env.sh (different filename), covering B1/B2/B3 and half of B5. MISSING B4 (injection binds verbatim), B6 (alias grammar), B7 (grammar parity with check_bws_map.parse_requests). Three-point wiring IS present: manifest.ts:5160-5172, package.json:129, ci-quality.yml:2079-2081.
- [ ] Add `archiveBitwardenSecret()` to `private/account/scripts/rotation/consumers/bitwarden-sm.ts` and call it from the edit branch of `pushBitwardenSecret` (`:96-103`).
- [ ] Add `./run.sh rotation bws-gc` (list `__ROTATED_*` in both projects; `--apply` deletes).
- [ ] Teach `scripts/dev/bws-map-refresh.py` to exclude `__ROTATED_<stamp>` names after the projection at `:96-104` and report each on stderr.
- [ ] Add assertion 5 to `.ci/scripts/quality/check_bws_map.py`: no mapped name matches the archive regex; prove the failure direction in its `selftest()`.
- [ ] Upgrade `private/account/tests/integration/rotation-bitwarden-consumer.test.ts` to a stateful fixture store with a redacted call log; add assertions A1-A8 and their controls.
- [ ] Add the three live-store locks to the vitest harness (shim-on-PATH precondition, sentinel token, `--server-url http://127.0.0.1:1`) plus the `globalSetup` refusal in `private/account/vitest.config.ts`.
- [ ] Back up `private/account/.env` to a `.env.pre-bws-<utc>.bak` (0600) and to the personal Bitwarden vault as one secure note.
- [ ] Create committed `private/account/dev.defaults.env` (the 21 non-secret names) and gitignored `private/account/dev.local.env` (the 5 machine-local names).
- [ ] Repoint the four non-secret readers at `dev.local.env`: `private/renet/build.sh:411-416`, `.ci/lib/local-common.sh:758-759`, `scripts/docker/build-server.sh:41-42`, `rdc.sh:246-248`. Keep `.ci/scripts/test/test-rdc-sh-env.sh` green.
- [ ] Cut over the secret readers one at a time, each verified by running the real command: `run.sh:1433-1437`, `.ci/lib/account.sh:443-445`, `.ci/lib/account.sh:795-797`, `programs/backup-storage/start-local-plane.sh:60-64`, `private/growth/video_pipeline/publish-solutions.sh:49-52`.
- [ ] Retarget the seven `.env` writers listed in Part 2, especially `private/account/src/entry/dev-gateway.ts:150-164`, which rewrites the file on every gateway start.
- [ ] Add `check:env-is-token-only` as a BLOCKING preflight in `./run.sh setup`, local-only,
      with `SKIP_ENV_TOKEN_ONLY_CHECK=1` documented. **Do not place it beside the drift
      check at `run.sh:1915-1925` without noting the difference**: that neighbour only
      `log_warn`s and says why in four lines -- "ROTATION IS AN OPS TASK, NOT A DEVELOPER
      ONE, so this does not stop setup". Copying the placement invites copying the
      severity, and these two have opposite intent: a stale rotation is someone else's
      job, a `.env` that has regrown is this developer's.
- [ ] Truncate `private/account/.env` to `BWS_ACCESS_TOKEN` + `BWS_ACCESS_TOKEN_ROTATE`. This is the only irreversible step; it goes last.
- [ ] Retarget `scripts/check-env-credential-drift.ts` (`ENV_FILE` at `:53`) at a `bws_export` of its three tracked names, and the probe at `.claude/hooks/pre-bash/block-host-toolchain-run.sh:86-100` at the token + map.
- [x] Fix two stale citations found on the way: `scripts/check-env-credential-drift.ts:23-24` (set-account-worker-secrets.sh does not read `.env`) and `.ci/scripts/private/license-e2e.sh:180` (the function is at `private/renet/build.sh:409-451`).
      AUDIT: DONE 2026-09-02 (audit): scripts/check-env-credential-drift.ts:26-29 carries the correction verbatim; .ci/scripts/private/license-e2e.sh:180 now cites build.sh:409-451.
- [ ] Add `private/account/dev.local.env` and `dev.defaults.env` to `scripts/dev/secret-rename.py`'s `EXTRA` (`:105`).

---

## Headline conclusion, including the parts of the ask the evidence does not support

**1. Ask (B) is already built.** "The rotation script should also rotate the Bitwarden
side" is done and shipped. `private/account/scripts/rotation/consumers/bitwarden-sm.ts`
exists (155 lines), the manifest schema has a first-class `bitwarden-sm:` consumer ref
(`private/account/src/types/rotation-manifest.ts:108-113`) and a declared-never-derived
`bitwarden_secret_names` field (`:142-166`), **11 of the 15 slugs already declare a
`bitwarden-sm:` consumer**, `commands/rotate.ts:165` refreshes `.ci/config/bws-secret-map.json`
after a successful rotate, and there are two vitest suites over it
(`private/account/tests/integration/rotation-bitwarden-consumer.test.ts`,
`rotation-bitwarden-names.test.ts`, 149 + 588 lines) with a fake `bws` on PATH.
What is actually missing on (B) is narrow: the 4 slugs with no Bitwarden consumer
(`ses-bench`, `otlp-bench`, `turnstile-bench`, `dkim-notify`) and the clone protocol of ask (C).
Do not re-plan (B); extend it.

**2. Ask (C)'s premise HOLDS — the trash is real — but the protocol buys less than it
looks like it does, and it costs something.** Bitwarden Secrets Manager soft-deletes to a
Trash with a 30-day window and a Restore action (quoted below). So clone → delete → update
does leave a recoverable copy of the pre-rotation value. Four corrections:

- **`bws` has no trash, restore or undelete verb.** Recovery is a human in the SM web UI.
  The CLI reference lists `secret create|edit|delete|get|list` and nothing else, and the
  `bws` changelog records no such command in any version. So the protocol produces an
  archive the *operator* can restore, never one a script can.
- **It is 30 days, not an archive.** After 30 days the copy is gone and unrecoverable.
- **For 9 of the 11 wired slugs it duplicates protection that already exists.** The
  versioned platforms (`aws-iam`, `cloudflare-token`, `otlp-basic-auth`) already keep the
  predecessor credential *live* at the platform in `grace` for `policy.grace_days` = 7
  (`rotate.ts:379-408`; `rotation-manifest.json` policy `{grace_days:7, inactive_days:7,
  turnstile_grace_hours:2}`). The genuinely new coverage is `turnstile` (rotates in place;
  `platform: cloudflare-turnstile` has **no `versions` array at all** —
  `src/types/rotation-manifest.ts:251` — and only a 2-hour platform grace) and any future
  Bitwarden-only value. That is worth having. It is not "now we have backups".
- **It widens the argv exposure window.** `bitwarden-sm.ts:19-23` already records that
  `bws` has no stdin form, so the value goes on argv and is visible in the process table.
  Cloning puts the *old* value on argv too — one rotation now exposes two values instead
  of one. There is no `bws` flag that avoids this.

**3. Ask (A) — "`.env` only for storing bitwarden tokens" — is achievable, and the hard
part is not the bootstrap.** There is no circularity: `BWS_ACCESS_TOKEN` is the sole root
of trust and it is not rotated by this tool, so even the AWS/Cloudflare **admin**
credentials can come from Bitwarden. The real obstacles are three, and two of them are not
about secrets at all:

- **Only 23 of the 50 names are secrets.** 21 are non-secret local config (`PORT`,
  `WEBAUTHN_*`, the 9 `SELLER_*` company-registration fields, `CI_MODE`…) and 5 are
  machine-local mutable state or public-key material. Putting those in a secrets store
  would be wrong; they need a second and third file, so "`.env` holds only the token"
  means a **three-file split**, not a two-file one.
- **`.env` is a WRITE target, not just a read target.** Seven code paths rewrite it,
  including `private/account/src/entry/dev-gateway.ts:150-164`, which rewrites
  `REDIACC_ACCOUNT_SERVER` on *every gateway start*. If those writers are not retargeted
  in the same change, `.env` silently re-grows and the invariant erodes with nothing to
  say so.
- **The token in `.env` today expires in six days.** Per
  `agent/PLAN-secret-namespace-migration.md` Part 6.5 and Part 10 §"Bitwarden itself", it
  is the machine account `mc_migrate_claude`, created 2026-09-01 with **7-day validity →
  expires 2026-09-08**, holding read-**WRITE** on `ci-shared`. Making every local
  `./run.sh` depend on it converts a 6-day expiry into a total local-toolchain outage, and
  gives every ordinary local command write access to the whole store. Minting replacement
  machine accounts is the first task and everything else waits on it.

**4. One thing this plan does NOT do, deliberately.** It does not route the three public
keys (`ACCOUNT_ED25519_PUBLIC_KEY`, `ACCOUNT_X25519_PUBLIC_KEY`, `UPSTREAM_PUBLIC_KEY`)
through a network fetch. Four build-time readers depend on them
(`private/renet/build.sh:411-416`, `.ci/lib/local-common.sh:758-759`,
`scripts/docker/build-server.sh:41-42`, `rdc.sh:246-248`), and a build that needs the
network to read a *public* key is a regression. They are cached into a local file by
`./run.sh setup` and read from there.

---

## Evidence: what the official docs say, and where they are silent

Quoted, with the page named. Anything not quoted here is marked unverified rather than
filled in from memory.

**Trash exists, 30 days, restorable — [Secrets | Bitwarden](https://bitwarden.com/help/secrets/), section "Delete a secret":**
> "When you delete a secret, it moves to **Trash** for 30 days. After that time, it will be permanently deleted."
> "Once a secret is permanently deleted, it cannot be recovered."
> "To undo a deletion or permanently delete a secret before 30 days: 1. Go to **Trash**. 2. On the same line as the secret, select the **icon**. 3. Select **Restore secret** or **Permanently delete**"

**The CLI surface — [Secrets Manager CLI | Bitwarden](https://bitwarden.com/help/secrets-manager-cli/):**
> `bws secret create <KEY> <VALUE> <PROJECT_ID>` — "Optionally, you can add a note using the `--note <NOTE>` option."
> `bws secret edit <SECRET_ID> [--key <KEY>] [--value <VALUE>] [--note <NOTE>] [--project-id <PROJECT_ID>]`
> `bws secret delete <SECRET_IDS>` — accepts multiple ids.
> Global flags include `--output json|yaml|table|tsv|none|env`, `--color yes|no|auto`, `--server-url <URL>`, `--profile`, `--config-file`.
> On `--output env`: "if the key name is non-POSIX-compliant, that key value pair will be commented-out".

**Trash HTTP routes exist on the server — [bitwarden/server PR #2688 "SM-281: Secrets Manager Trash"](https://github.com/bitwarden/server/pull/2688):**
controller `TrashController`, routes `[HttpGet("secrets/{organizationId}/trash")]`,
`[HttpPost("secrets/{organizationId}/trash/empty")]`,
`[HttpPost("secrets/{organizationId}/trash/restore")]`.

**Machine accounts and token scope — [Secrets Manager Quick Start | Bitwarden](https://bitwarden.com/help/secrets-manager-quick-start/):**
> "**Can read**: Machine account can retrieve secrets from assigned projects."
> "**Can read, write**: Machine account can retrieve and edit secrets from assigned projects, as well as create new secrets in assigned projects or create new projects."
> "When the token **Expires**. By default, Never."

### Where the docs are SILENT — do not assume, verify at implementation time

| Question | Status |
|---|---|
| Does `bws secret delete` soft-delete to Trash, or hard-delete? | **The CLI page never says.** The Secrets page says deleting a secret trashes it, and the server has one delete path, so soft-delete is the strong inference — but it is an inference. Verify before shipping. The whole protocol is worthless if this is wrong. |
| Does `bws secret list <project>` exclude trashed secrets? | **Silent.** Verify in the same experiment. If trashed rows *are* listed, `bws-map-refresh.py` and `findBitwardenSecret`'s duplicate-name refusal (`bitwarden-sm.ts:81-88`) both break. |
| Can a machine-account access token call the `TrashController` routes? | **Silent.** No public API reference for these routes was found. Assume no; do not design a scripted restore. |
| Does SM enforce unique secret KEYs within a project? | **Silent.** Irrelevant to the clone (the suffix makes it unique) but relevant to `findBitwardenSecret`, which already refuses on duplicates rather than guessing. |
| Is there a `bws` verb to mint or rotate an access token? | **Not in the CLI reference and not in the changelog.** Treat `BWS_ACCESS_TOKEN` rotation as operator-only and web-UI-only. |

---

## The 50 names, classified (Part 1)

Extracted by name only (`sed -n 's/=.*//p'`), never by value. Target column is the
`ci-shared` spelling from `.ci/config/bws-secret-map.json` (refreshed 2026-09-02T16:26:11Z,
53 entries, org `61f8e970-…`, project `2b5e33f9-b5ae-4ecc-972d-b36f00b0f86a`).

### (a) Secrets → Bitwarden Secrets Manager — 23 names

| `.env` name | `ci-shared` target | in map today? |
|---|---|---|
| `ACCOUNT_ED25519_PRIVATE_KEY` | same | yes |
| `ACCOUNT_X25519_PRIVATE_KEY` | same | yes |
| `ACCOUNT_SERVER_API_KEY` | same | yes |
| `ACCOUNT_JWT_SECRET` | same | yes |
| `STRIPE_WEBHOOK_SECRET` | same | yes |
| `CLOUDFLARE_TURNSTILE_SECRET_KEY` | same | yes |
| `AWS_SES_ACCESS_KEY_ID` | `AWS_SES_ACCESS_KEY_ID_EU` | yes (collapse case) |
| `AWS_SES_SECRET_ACCESS_KEY` | `AWS_SES_SECRET_ACCESS_KEY_EU` | yes (collapse case) |
| `R2_ACCESS_KEY_ID` | `CLOUDFLARE_R2_ACCESS_KEY_ID` | yes |
| `R2_SECRET_ACCESS_KEY` | `CLOUDFLARE_R2_SECRET_ACCESS_KEY` | yes |
| `R2_ENDPOINT` | `CLOUDFLARE_R2_ENDPOINT` | yes |
| `R2_MEDIA_ACCESS_KEY_ID` | `CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID` | yes |
| `R2_MEDIA_SECRET_ACCESS_KEY` | `CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY` | yes |
| `R2_MEDIA_ENDPOINT` | `CLOUDFLARE_R2_MEDIA_ENDPOINT` | yes |
| `OBS_OTLP_CREDENTIALS` | `OBS_OTLP_CREDENTIALS` today; `_EU` after the first `rotate otlp-eu` | yes |
| `BREAKPOINT_TUNNEL_TOKEN` | `CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN` | yes |
| `AUTOPILOT_PRIVATE_KEY` | `GITHUB_AUTOPILOT_PRIVATE_KEY` | yes |
| `CLAUDE_CODE_OAUTH_TOKEN` | `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` | yes |
| `UPSTREAM_API_KEY` | `UPSTREAM_API_KEY` | **no — seed** |
| `SES_AK_ID` | `AWS_ADMIN_ACCESS_KEY_ID` | **no — seed, admin project** |
| `SES_AK_SECRET` | `AWS_ADMIN_SECRET_ACCESS_KEY` | **no — seed, admin project** |
| `CF_GLOBAL_API_KEY` | `CLOUDFLARE_GLOBAL_API_KEY` | **no — seed, admin project** |
| `CF_EMAIL` | `CLOUDFLARE_ACCOUNT_EMAIL` | **no — seed, admin project** |

18 of 23 already resolve. 5 are seeded once, by the operator, from the values in `.env`.
The store goes 53 → 58 entries; `MIN_MAP_ENTRIES = 30` (`check_bws_map.py:55`) and
`MIN_ENTRIES = 40` (`bws-map-refresh.py:50`) are floors, so neither moves.

Alias handling is load-bearing and non-optional: `.env` spells 10 names like the GitHub
secret rather than the Worker binding, and carries the SES/OTLP/Stripe collapse cases
unsuffixed — see `agent/PLAN-secret-namespace-migration.md` §"`private/account/.env`,
measured 2026-09-02 — it MIXES both conventions". The fetch helper therefore needs the same
`NAME > ENV_NAME` grammar the CI composite already speaks
(`.github/actions/bws-secrets/action.yml:35-40`).

### (b) Non-secret config → committed `private/account/dev.defaults.env` — 21 names

`DATABASE_PATH`, `PORT`, `WEBAUTHN_RP_ID`, `WEBAUTHN_RP_NAME`, `WEBAUTHN_ORIGIN`,
`OTEL_ENDPOINT`, `CI_MODE`, `AWS_SES_REGION`, `AWS_SES_FROM`, `R2_MEDIA_BUCKET`,
`AUTOPILOT_APP_ID`, `UPSTREAM_URL`, and the nine `SELLER_*` (company name, VAT number,
registration number, two address lines, city, postal code, country, email).

Defaults, not secrets. `AWS_SES_REGION` is already recorded as "in the vault and SM, read
by nothing" (namespace plan Part 10 §"Out of scope"); `R2_MEDIA_BUCKET` and
`MEDIA_CDN_DOMAIN` are org *variables*, not secrets (CLAUDE.md §Media Assets);
`AUTOPILOT_APP_ID` is a public GitHub App id. Committing them ends the "33 of 50
undocumented" problem for good, because the file *is* the documentation.

### (b′) Machine-local, gitignored `private/account/dev.local.env` — 5 names

`REDIACC_ACCOUNT_SERVER` (rewritten by `dev-gateway.ts:150-164` on every start),
`ROOT_EMAIL` (operator identity), and the three public halves
`ACCOUNT_ED25519_PUBLIC_KEY`, `ACCOUNT_X25519_PUBLIC_KEY`, `UPSTREAM_PUBLIC_KEY`,
populated once by `./run.sh setup` from Bitwarden so builds stay offline (headline §4).

### (c) The bootstrap credential(s) → stay in `private/account/.env` — 1 name today, 2 after

```
BWS_ACCESS_TOKEN         # read-only on ci-shared; every local script and CI
BWS_ACCESS_TOKEN_ROTATE  # read/write ci-shared + read admin-bootstrap; ONLY ./run.sh rotation
```

Nothing else. Mode 0600. `private/account/.gitignore:3-4` (`.env`, `.env.*`) already covers
it and the backup files.

### The bootstrap answer, stated plainly

- **There is no circularity for the admin credentials.** `SES_AK_ID` / `SES_AK_SECRET`
  (`lib/credentials.ts:59-71`, `resolveAwsAdmin`, legacy aliases
  `AWS_SES_ADMIN_KEY_ID`/`AWS_SES_ADMIN_SECRET`) and `CF_GLOBAL_API_KEY`+`CF_EMAIL`
  (`:86-106`, `resolveCloudflare`, which mints an ephemeral scoped token at `:183-311` and
  self-destructs it at `:112-124`) are *rotated by nothing*. No manifest slug records them
  and none can — `scripts/check-env-credential-drift.ts:91-105` spells out why. So they can
  be read from Bitwarden with no chicken-and-egg: the only thing needed to read them is the
  BWS token, which they do not mint and which does not depend on them.
- **`BWS_ACCESS_TOKEN` is the one true root and it cannot come from Bitwarden.** There is
  no CLI verb to mint or rotate a machine-account access token; it is created in the web
  UI. It is therefore permanently operator-only and no `bws-token` rotation slug is
  possible. Record that as `door:operator-only`, not as a gap.
- **Break-glass is the personal Bitwarden *vault*, a different product with a different
  auth path.** Per namespace plan Part 9, the operator's Password Manager vault (`bw`,
  unlocked by master password / `BW_SESSION`) already holds the ACCOUNT keys,
  `AUTOPILOT_PRIVATE_KEY`, `BREAKPOINT_TUNNEL_TOKEN`, the `R2_MEDIA_*` trio and the GPG
  material. Two Bitwarden products, two independent credentials, so a dead BWS token costs
  a manual unlock rather than a lockout. Before the `.env` truncation task, the five seeded
  names must also land in that vault — otherwise the admin credentials exist in exactly one
  place reachable by exactly one 6-day-old token.
- **Seeding the admin credentials into `ci-shared` would be a security downgrade.** It
  would upgrade `BWS_ACCESS_TOKEN` from "everything CI can deploy" to "everything the AWS
  and Cloudflare accounts can do", for a token that today sits unencrypted in a file every
  local script sources. So they go into a **second project, `admin-bootstrap`**, readable
  only by the rotation machine account. `.ci/config/bws-secret-map.json` stays
  single-project (its `project` field, the refresh script and `check_bws_map.py` all assume
  one); the rotation tool addresses the admin project by UUID from `lib/config.ts`, which
  already carries `bitwardenSmProject` at `:19`.

### The two machine accounts, which block everything else

| account | scope | consumed by | env var |
|---|---|---|---|
| `mc-ci-read` | read on `ci-shared`, expiry **Never** | GitHub org secret `BWS_ACCESS_TOKEN` (`.github/actions/bws-secrets/action.yml:27-32`) and every local script via the fetch helper | `BWS_ACCESS_TOKEN` |
| `mc-rotate` | read/write on `ci-shared`, read on `admin-bootstrap` | `./run.sh rotation` only | `BWS_ACCESS_TOKEN_ROTATE` |

`verifyBitwardenSm()` (`lib/credentials.ts:151-168`) currently requires `BWS_ACCESS_TOKEN`;
it changes to require `BWS_ACCESS_TOKEN_ROTATE` and to *reject* a run where only the
read-only one is present, so a rotate can never silently fail its writes.

---

## Every consumer, and what happens to it (Part 2)

Verified read sites, absolute paths. "Whole-file source" means `set -a; source; set +a`.

| Site | Mechanism | Names it needs | Disposition |
|---|---|---|---|
| `/home/developer/console/.ci/lib/account.sh:443-445` (`account_dev`, fn at `:397`) | whole-file source | all `ACCOUNT_*`, `DATABASE_PATH`, `PORT`, `WEBAUTHN_*`, `OTEL_ENDPOINT`, `OBS_OTLP_CREDENTIALS`, `STRIPE_*` | `bws_export` an **explicit list**, then source the two local files. The explicit list is the point: today this exports 50 variables into the gateway and nothing says which it needs. |
| `/home/developer/console/.ci/lib/account.sh:795-797` (`account_test`, fn at `:777`) | whole-file source | `REDIACC_ACCOUNT_SERVER` (`:805`), `ROOT_EMAIL` (`:818`), `STRIPE_WEBHOOK_SECRET`→`E2E_WEBHOOK_SECRET` (`:821`), `STRIPE_SANDBOX_SECRET_KEY` (`:829`) | `bws_export STRIPE_WEBHOOK_SECRET STRIPE_SANDBOX_SECRET_KEY`; the other two from `dev.local.env`. |
| `/home/developer/console/run.sh:1433-1437` (`--publish-pr`) | subshell source captured as text; `_env()` at `:1438` greps it | the 13-pair `_required` list at `:1526-1539` plus `AWS_SES_FROM`, `AWS_SES_CONFIGURATION_SET` at `:1585-1586` | `bws_export` with the alias grammar; `_env` becomes a plain `${!name}` read. The existing non-empty guards at `:1541-1560` stay — they are the model for the helper's own guard. |
| `/home/developer/console/scripts/dev/deploy-bench.sh:137-148` | sources `.env` **then** `.env.bench` | 6 hard-required at `:175-180`, 8 non-empty-guarded at `:201-208`, 13 soft at `:222-239`, plus `SES_AK_ID` at `:163` | Bench needs its own answer — see Part 4 §four slugs. Unchanged under the default. |
| `/home/developer/console/private/growth/video_pipeline/publish-solutions.sh:49-52` | whole-file source (`set -a` `:49`, `source` `:51`, `set +a` `:52`) | asserted non-empty at `:55-58`: `R2_MEDIA_ACCESS_KEY_ID`, `R2_MEDIA_SECRET_ACCESS_KEY`, `R2_MEDIA_ENDPOINT`, `CF_GLOBAL_API_KEY`, `CF_EMAIL` | Separate gitignored repo; sources the console helper by absolute path (it already computes `$REPO_ROOT`). Needs two `admin-bootstrap` names — see the open question in Part 5. |
| `/home/developer/console/programs/backup-storage/start-local-plane.sh:60-64` | whole-file source, then overrides `ACCOUNT_BACKUP_S3_*` / `CONFIG_R2_*` | the ACCOUNT crypto keys; **relies on `ACCOUNT_BACKUP_S3_*` being ABSENT from `.env`** so its own exports survive | `bws_export` the 4 ACCOUNT keys. The absence-reliance becomes explicit rather than accidental — an explicit list cannot be widened by someone adding a key to `.env`. |
| `/home/developer/console/private/renet/build.sh:411-416` (`_account_key_ldflags`, fn `:409-451`) | `sed -n 's/^KEY=//p'`; tries `ED25519_PUBLIC_KEY` (`:415`) then `ACCOUNT_ED25519_PUBLIC_KEY` (`:416`); warns `:425-427`; prints a sha256 fingerprint, not the key, at `:439` | `ACCOUNT_ED25519_PUBLIC_KEY` | **No Bitwarden.** Repoint the `sed` at `dev.local.env`; the build stays offline. |
| `/home/developer/console/.ci/lib/local-common.sh:758-759` | `sed -n 's/^ACCOUNT_ED25519_PUBLIC_KEY=//p'` | same, only as a rebuild-stamp hash input | same |
| `/home/developer/console/scripts/docker/build-server.sh:41-42` | same `sed` | same, baked into the onprem image | same |
| `/home/developer/console/rdc.sh:246-248` (`--dev`) | `grep -E '^KEY=' \| tail -1 \| cut -d= -f2-`; deliberately refuses to source (`:241-245`) | `REDIACC_ACCOUNT_SERVER`, `ACCOUNT_X25519_PUBLIC_KEY` | **No Bitwarden and no sourcing.** Repoint the two greps at `dev.local.env`. `rdc.sh` runs on every CLI invocation, so a network fetch there is unacceptable — and `.ci/scripts/test/test-rdc-sh-env.sh:55,61-68` already gates that `rdc.sh` contains no `set -a`, no `source` of the account env, and exports only `PATH`/`REDIACC_CONFIG`/`NODE_COMPILE_CACHE`. That gate staying green is the cheapest proof the CLI path did not grow a secret dependency. |
| `/home/developer/console/scripts/check-env-credential-drift.ts:53,110` | own line parser; compares IDs only, prints an 8-char prefix | `AWS_SES_ACCESS_KEY_ID`, `R2_ACCESS_KEY_ID`, `R2_MEDIA_ACCESS_KEY_ID` (`TRACKED`, `:58-70`) | Its subject disappears; retarget at Bitwarden (Part 5). |
| `/home/developer/console/.claude/hooks/pre-bash/block-host-toolchain-run.sh:86-100` | `grep -q "^R2_MEDIA_ACCESS_KEY_ID="` — existence probe, no value read | one name | Retarget the probe: token present in `.env` **and** the name present in `bws-secret-map.json`. |

### Writers — the half that will silently undo this if missed

| Site | What it writes |
|---|---|
| `.ci/lib/account.sh:209-251` `account_generate_fresh_env` | `cat >` heredoc creating `.env` with `REDIACC_ACCOUNT_SERVER`, `DATABASE_PATH`, four `ACCOUNT_*` keys, `ACCOUNT_SERVER_API_KEY`, `ACCOUNT_JWT_SECRET`, `STRIPE_WEBHOOK_SECRET`, `ROOT_EMAIL`, `PORT`, `WEBAUTHN_*` |
| `.ci/lib/account.sh:257-266` `account_env_add_if_missing` | appends when `grep -q "^${key}="` misses |
| `.ci/lib/account.sh:269-312` `account_ensure_env_keys` | idempotent top-up; adds `OTEL_ENDPOINT` at `:302` |
| `.ci/lib/account.sh:864-871` `account_reset` | in-place `sed` rewrite of six crypto/secret keys |
| `private/account/src/entry/dev-gateway.ts:150-164` `updateEnvServerUrl` | regex-replaces `^REDIACC_ACCOUNT_SERVER=.*$` and writes back, **called at `:170` on every gateway start** |
| `private/account/scripts/rotation/consumers/local-env-file.ts:55-90` `updateEnvFile` | atomic tmp+rename, mode 0600; `resolveLocalPath` `:35-42`; callers `rotate.ts:744-751, 973-974, 1183-1184, 2019-2025`; manifest refs `local:.env` at `rotation-manifest.json:82` and `local:.env.bench` at `:219,358,505` |
| `scripts/dev/secret-rename.py:105,316-329` | `EXTRA = ["private/account/.env", "private/account/.env.bench"]`, bulk rename with mandatory `.pre-rename.bak` |

All seven retarget to `dev.local.env`, except `local-env-file.ts`, whose `local:` refs are
removed from the manifest for the credentials that already carry a `bitwarden-sm:` ref and
retargeted to `dev.local.env` for the bench ones.

`account_generate_fresh_env` writing locally-generated dev keys to `dev.local.env` is also
a **safety improvement**: today `./run.sh account reset` sed-rewrites
`ACCOUNT_ED25519_PRIVATE_KEY`, which namespace plan Part 1 proves is the *production
licence-signing pair*. After the split, reset touches a local file and can no longer
clobber a production key that also lives in `ci-shared`.

**Two stale citations found on the way.** `scripts/check-env-credential-drift.ts:23-24`
claims "`.ci/scripts/deploy/set-account-worker-secrets.sh` reads the same file". It does
not — that script has zero `.env` references; its only `source` is `../lib/common.sh` at
`:102`, and it takes secrets from the CI process environment. The gate's argument survives
via `run.sh`, but the citation is wrong. Separately,
`.ci/scripts/private/license-e2e.sh:180` cites `build.sh:333-343` for
`_account_key_ldflags`; the function is at `private/renet/build.sh:409-451`.

---

## The fetch mechanism, `.ci/lib/bws-env.sh` (Part 3)

### Shape

```bash
bws_export ACCOUNT_JWT_SECRET \
           "AWS_SES_ACCESS_KEY_ID_EU > AWS_SES_ACCESS_KEY_ID" \
           "CLOUDFLARE_R2_ACCESS_KEY_ID > R2_ACCESS_KEY_ID"
```

One `NAME` or `NAME > LOCAL_NAME` per argument — **the same grammar as
`.github/actions/bws-secrets/action.yml:35-40`**, deliberately, so there is one grammar in
the repo and a gate can prove the two implementations agree.

### Mechanics, and why each choice

- **One network call per process, not per name.** `bws --color no secret list <project>
  --output json`, indexed by `key` in-process. `bws secret get` would be N round trips.
  `--color no` is not cosmetic: bws 2.1.0's `--color auto` emits truecolor ANSI through a
  pipe, which is why `bws-map-refresh.py:76-80` and `bitwarden-sm.ts:56-64` both pin it —
  and why the refresh script "had never worked from a pipe".
- **No `eval`, ever.** Values are bound with `declare -g "$name=$value"`, whose RHS is not
  re-evaluated. The tempting `eval "$(bws run --output env)"` is rejected twice over: it is
  a shell-injection seam on any value containing `$(...)`, and the docs say a
  non-POSIX-compliant key "will be commented-out" — silent omission, which is exactly the
  empty-secret failure this work exists to stop.
- **`bws run -- '<cmd>'` is rejected** for a third reason on top: it injects *every* secret
  the machine account can see (53 today) into the child, the opposite of least privilege,
  and it cannot alias, so the collapse cases (`AWS_SES_ACCESS_KEY_ID_EU` →
  `AWS_SES_ACCESS_KEY_ID`) are unexpressible.
- **`set +x` around the binding loop**, restored afterwards, so a caller running under
  `bash -x` cannot print values.

### Caching — the honest answer is "none by default"

A value cache means writing decrypted production credentials to disk, which is the thing
this change is meant to reduce. Default: **no cache**. One HTTPS round trip per `./run.sh`
invocation is acceptable, and `rdc.sh` plus the three build readers never call the helper
at all (headline §4), so the hot paths are untouched.

Opt-in only, for slow links: `REDIACC_BWS_CACHE_TTL=<seconds>` writes
`$XDG_RUNTIME_DIR/rediacc-bws/<project>.json` at mode 0600. **`$XDG_RUNTIME_DIR` or
nothing** — it is tmpfs, so values never touch persistent storage. If it is unset, or is
not a 0700 directory owned by the caller, the helper refuses to cache and says so rather
than falling back to `/tmp`.

### Failure modes — all loud, none empty

| Condition | Behaviour |
|---|---|
| `bws` not on PATH | exit 1, naming `.devcontainer/Dockerfile:448-463` (hash-pinned 2.1.0) as the install site |
| `BWS_ACCESS_TOKEN` unset or empty | exit 1, naming `private/account/.env` |
| `bws` exits non-zero | exit 1 printing **stderr only** — stdout on a partial failure can carry values (`bws-map-refresh.py:89` states this rule) |
| stdout is not JSON | exit 1 **without printing stdout**, same reason (`bws-map-refresh.py:93`) |
| a requested NAME is absent from the listing | exit 1 naming it and pointing at `.ci/config/bws-secret-map.json` |
| a requested NAME resolves to an **empty value** | **exit 1.** The one the CI path deliberately does not catch: `action.yml:21-24` records that "sm-action exports `""` without complaint" and pushes the job onto the deploy scripts' guards. There is no downstream guard on `./run.sh account dev`, so the helper closes it. |
| offline / DNS failure | `bws` exits non-zero → the row above. **No degraded mode and no fallback to a stale `.env`.** A fallback that silently serves an old value is how a rotated credential keeps working locally and stops working nowhere visible. |

---

## The clone → delete → update protocol (Part 4)

### The seam: one function, so no push site can forget

Today `pushBitwardenSecret` (`consumers/bitwarden-sm.ts:96-103`) is:

```ts
const existing = findBitwardenSecret(projectId, name);
if (existing) { bws(['secret','edit','--value',value,'--',existing.id]); }
else          { bws(['secret','create','--',name,value,projectId]); }
```

The archive belongs on the **edit branch only** — a create has nothing to preserve — and
inside this function rather than at the call sites, because there are five call sites across
`rotate.ts` and the registration pattern is a prefix `if/else` chain per platform
(`rotate.ts:1983-2044`, and the CF variant's `KNOWN_PREFIXES` at `:549-560`), i.e. exactly
the shape where one site gets forgotten.

```ts
export function archiveBitwardenSecret(projectId: string, existing: BwsSecretRow): string {
  const ts    = utcStamp();                     // 20260902T164500Z, from an injected clock
  const key   = `${existing.key}__ROTATED_${ts}`;
  const old   = JSON.parse(bws(['secret','get','--output','json','--',existing.id])).value;
  const clone = JSON.parse(bws(['secret','create','--output','json','--note',note,'--',key,old,projectId]));
  try {
    bws(['secret','delete','--', clone.id]);    // -> Trash, 30 days
  } catch (e) {
    throw new Error(
      `bitwarden-sm: created archive clone ${key} (${clone.id}) but could not delete it to Trash. ` +
      `A PLAINTEXT COPY OF THE PRE-ROTATION VALUE IS LIVE IN PROJECT ${projectId}. ` +
      `Remove it: ./run.sh rotation bws-gc  (or bws secret delete ${clone.id})`, { cause: e });
  }
  return key;
}
```

Note text carries no value: `pre-rotation copy of <NAME> (uuid <id>) taken by rotation
<slug> at <ts>; deleted to Trash immediately, recoverable for 30 days`.

**Suffix format: `__ROTATED_<YYYYMMDD>T<HHMMSS>Z`.** Double underscore because single
underscores are already meaningful in this namespace (`_EU`, `_US`, `_ASIA`); a strict,
anchored, UTC-only shape so the GC regex and the map gate can be exact rather than fuzzy.
The clock is injected so tests are deterministic.

### Where in `rotate.ts` it runs

Between the smoke test and the consumer push — after `rotate.ts:318-334` (mint plus STS
smoke test; on failure the fresh key is deleted and nothing is written) and before the push
loop at `:341-350`. A failed mint must not leave a trash entry behind, and the archive must
exist before anything overwrites the original. Because it lives inside
`pushBitwardenSecret`, this ordering falls out of the existing control flow with no change
to the loop.

### Failure matrix — partial rotation is the dangerous state, so name every cell

| Crash point | Store state | Recovery |
|---|---|---|
| before `create` | untouched | re-run |
| after `create`, before `delete` | **a live plaintext duplicate of the credential in `ci-shared`** | the error above names the key; `./run.sh rotation bws-gc` sweeps it; the map gate below fails loudly if it survives to a refresh |
| after `delete`, before `edit` | original unchanged, one trash entry | re-run; idempotent, produces a second trash entry (harmless, both dated) |
| `edit` fails | original holds the OLD value while the platform already minted the NEW one | **unchanged from today.** `rotate.ts:369-376` collects push errors and returns 1 *without saving the manifest*; the minted platform credential stays live and the operator re-runs. There is no rollback on this path today and this change does not add one. |
| Bitwarden write succeeds, a downstream (Worker / GitHub / `.env`) push fails | same as above — errors are collected at `:341-350`, not thrown; manifest unsaved | re-run. The Bitwarden edit is idempotent by construction (`edit --value` by UUID), so the second run's archive clone is a copy of the *new* value — noise, not damage. Accept it; skipping the archive on a re-run needs state the tool does not have. |

The manifest is never written on a partial failure, which is what keeps the record truthful;
the cost is that a partial rotation leaves the platform ahead of the record. That trade
already exists (`rotate.ts:369-376`) and this change does not alter it.

The one true rollback in the tool today is `rotateDkimNotify` (`rotate.ts:1614-1830`,
`rollbackDkimNotify` at `:1858-1885`), which flips touched SES identities back to Easy DKIM
and deletes the fresh DNS record. Nothing analogous is proposed here, because reversing a
Bitwarden edit would mean holding the old value in memory across the whole push loop — a
longer-lived plaintext than the archive itself.

### Keeping clones out of the map and the gates — required, not an afterthought

`ci-shared` is a single project (`bws-secret-map.json.project`), so a clone is listed by the
same `bws secret list` the refresher uses. Three changes:

1. **`scripts/dev/bws-map-refresh.py`** — add
   `ARCHIVE_RE = re.compile(r"__ROTATED_\d{8}T\d{6}Z$")` and exclude matches from `entries`
   **after** the `{id, key, projectId}` projection at `:96-104` and **before** the
   `MIN_ENTRIES` floor at `:106`. Report each excluded name on **stderr** with the `bws-gc`
   command. This does not weaken the duplicate-name refusal at `:116-119`, because a
   suffixed key is a distinct key.
2. **`.ci/scripts/quality/check_bws_map.py`** — add assertion 5: **no mapped name matches
   `ARCHIVE_RE`**. A clone reaching the committed map means one leaked *and* survived a
   refresh; that must be red, not silently mapped. `MIN_MAP_ENTRIES` is a floor, so nothing
   catches it today.
3. **`./run.sh rotation bws-gc`** — a new command listing `__ROTATED_*` rows in both
   projects and deleting them (to Trash). Read-only by default, `--apply` to act.

`refreshBwsMap` (`lib/bws-map.ts:63-96`) is advisory — it logs a warning and never returns
non-zero (`:84-95`) — so a refresh that now exits non-zero on a leaked clone warns rather
than failing the rotate. That is the right severity: the rotation itself succeeded.

### The four slugs with no Bitwarden consumer

`ses-bench`, `otlp-bench`, `turnstile-bench` (all `local:.env.bench` + `worker:…-bench`) and
`dkim-notify` (three `ses-dkim:` refs). Bench values are a *different universe* from
`ci-shared`; giving them `bitwarden-sm:` refs into the same project would collide names.
Two options, and the DEFAULT is (i):

- **(i) leave bench alone.** Bench keeps `.env.bench` as a genuinely local file. It is a
  disposable internal D1 environment (`scripts/dev/reset-bench.sh` wipes it), it is the only
  `.env.bench` consumer, and its preflight already guards staleness (`deploy-bench.sh:158`,
  `rotation check --for=bench`). Cost: `.env.bench` still holds values, so "`.env` only for
  tokens" is true of `.env` and not of `.env.bench`.
- **(ii) a `bench` SM project.** Correct, but a second project, a second set of names, and a
  map that only models one project.

`dkim-notify` genuinely has no Bitwarden home: its private key is staged from a file path
(`DKIM_NOTIFY_PRIVATE_KEY_PATH`, `lib/config.ts:285`) and the manifest records only the
selector and a public-key SHA-256 fingerprint. Storing the PEM in `ci-shared` would be an
improvement — CLAUDE.md already warns "production rotations must stage the PEM so the key
can be backed up to 1Password before the process exits" — but it is a separate decision.

---

## Retargeting the two gates that lose their subject (Part 5)

**`scripts/check-env-credential-drift.ts`.** Its `TRACKED` list (`:58-70`) compares `.env`
values against manifest version ids for `AWS_SES_ACCESS_KEY_ID`, `R2_ACCESS_KEY_ID`,
`R2_MEDIA_ACCESS_KEY_ID`. Post-migration those names are not in `.env`. Retarget `ENV_FILE`
to a `bws_export` of the same three names into the process, keeping everything else
identical — it already prints only an 8-character prefix and never transmits. Keep the loud
skip when the submodule or the token is absent (`:44-46`). The `'absent' | 'retiring'`
distinction (`:148-160`) is the valuable half and is unaffected.

**`.claude/hooks/pre-bash/block-host-toolchain-run.sh:86-100`.** The existence probe on
`^R2_MEDIA_ACCESS_KEY_ID=` in `.env` becomes: `BWS_ACCESS_TOKEN` present in `.env` **and**
`CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID` present in `.ci/config/bws-secret-map.json`. Same
question — could this command actually reach the media credentials — and the same zero value
reads.

**New, local-only: `check:env-is-token-only`.** `.env` is gitignored so CI can never see it;
this runs where `check:env-credential-drift` already runs — a blocking preflight in
`./run.sh setup` (`run.sh:1915-1925`), with `SKIP_ENV_TOKEN_ONLY_CHECK=1` documented. It
asserts every assignment in `private/account/.env` is one of `BWS_ACCESS_TOKEN`,
`BWS_ACCESS_TOKEN_ROTATE`. This is the only thing standing between the invariant and the
seven writers; without it, one missed writer re-grows the file and nothing says so.

### The `CF_GLOBAL_API_KEY` question, which the operator should settle

`publish-solutions.sh:55-58` asserts `CF_GLOBAL_API_KEY` and `CF_EMAIL` are non-empty. Under
this design those live in `admin-bootstrap`, readable only by the rotation account — so the
video pipeline would need the privileged token, defeating the split.
`lib/credentials.ts:86-106` shows `CLOUDFLARE_API_TOKEN` is the *preferred* path and the
global key is the fallback; namespace plan Part 2 already notes `CLOUDFLARE_API_TOKEN` is
"documented but NOT set" locally, "so every local Cloudflare consumer falls through to
`CF_GLOBAL_API_KEY` — the classic Global API Key, full account access".
`CLOUDFLARE_API_TOKEN` *is* in `ci-shared` today.

---

## Testing, designed and not run (Part 6)

Two harnesses, both extending patterns already in the repo. **Control-first throughout: a
gate that cannot fail is worse than no gate**, so every assertion below is first run against
a deliberately broken variant and must go RED before the real one is trusted.

### Harness A — vitest, extending `rotation-bitwarden-consumer.test.ts`

That file already installs a fake `bws` (`installFakeBws` at `:41`) which faithfully
reproduces bws 2.1.0's ANSI-on-pipe behaviour (`:51-60`), so `--color no` is a *real*
control rather than a decoration. Upgrade it from a canned-output fake to a **stateful
fixture store**: a JSON file the fake reads and writes, so `create`/`edit`/`delete` are
observable, plus an append-only **call log** recording argv with every value position
replaced by `<redacted:len=N>` — the log is a test artifact and must never carry a value.

| # | Assertion | The planted defect that must make it RED |
|---|---|---|
| A1 | On an EXISTING name the call log is exactly, **in order**: `secret list`, `secret get`, `secret create -- <NAME>__ROTATED_<ts> … <project>`, `secret delete <cloneId>`, `secret edit --value … -- <origId>` | a variant that edits before deleting — this asserts order, not set membership |
| A2 | The original row's `id` is byte-identical before and after | a variant that deletes and recreates the original — the failure that would silently break every `bws-secret-map.json` UUID and therefore every workflow |
| A3 | On an ABSENT name: exactly one `create`, zero `get`, zero `delete` | a variant that always archives |
| A4 | The clone key matches `/^.+__ROTATED_\d{8}T\d{6}Z$/` and the timestamp equals the injected clock in UTC | a variant using local time, and one using a `-` separator |
| A5 | `bwsGc(project)` deletes exactly the `__ROTATED_<stamp>` rows | seed `X__ROTATED_NOTATIMESTAMP` and `Y__ROTATED_20260902` and assert **neither** is deleted — proves the regex is anchored and strict, not a substring match |
| A6 | Fake throws on `delete`: `pushBitwardenSecret` propagates, the message contains the clone KEY and the word `bws-gc`, and the original is **still unedited** | a variant that swallows the delete failure and proceeds to edit — the leaked-clone-plus-rotated-value state |
| A7 | The duplicate-name refusal (`bitwarden-sm.ts:81-88`) still fires when a clone shares the original's exact key | a variant whose suffix is empty |
| A8 | **Value hygiene sweep.** Every fixture value is a sentinel `SENTINEL-DO-NOT-PRINT-<uuid>`; after the suite, assert no sentinel appears in any captured stdout, stderr, call log, or thrown error message | a variant that includes the value in its error text — the exact class that leaked `AUTOPILOT_PRIVATE_KEY` into a transcript (`bitwarden-sm.ts:24-27`) |

Keep `rotation-bitwarden-names.test.ts:290`'s allowlist as it stands. Its five entries
(`AWS_SES_{ACCESS_KEY_ID,SECRET_ACCESS_KEY}_ASIA`, `OBS_OTLP_CREDENTIALS_{EU,US,ASIA}`) are
deliberate and documented at `:275-289`, not drift.

### Harness B — bash gate test for the fetch helper

New: `.ci/scripts/test/gates/test-bws-env-helper.sh`, sourcing
`.ci/scripts/test/lib/test-helpers.sh` (`assert_eq` `:38`, `assert_contains` `:46`,
`assert_not_contains` `:54`, `assert_exit_code` `:62`). Add `with_fake_bws` beside
`with_fake_gh` (`:93-112`), following the richer `SHIMDIR` + `plant()` shape of
`.ci/scripts/test/gates/test-autopilot-no-bypass.sh:36-58`.

| # | Assertion | The planted defect |
|---|---|---|
| B1 | token unset → exit non-zero, message names `private/account/.env` | a helper that proceeds with an empty token |
| B2 | requested name absent from the listing → exit non-zero naming it | a helper that leaves the variable unset and returns 0 |
| B3 | **name present, value `""` → exit non-zero** | a helper that exports the empty string. The headline assertion: the CI action explicitly does *not* do this (`action.yml:21-24`) |
| B4 | a value containing `` $(touch $SENTINEL) ``, backticks, a newline and a leading `-----BEGIN` binds **verbatim** and executes nothing | assert `$SENTINEL` does not exist; the control is an `eval`-based helper, which must create it |
| B5 | `bws` exits 1 with a value-bearing stdout → the value appears in **no** captured output | a helper that prints stdout on failure |
| B6 | the alias grammar `NAME > LOCAL` binds `LOCAL` and leaves `NAME` unset | a helper that binds both |
| B7 | **grammar parity**: the helper's parse of a fixture list equals `parse_requests()`'s (`check_bws_map.py:62-98`) on the same list — aliases, comments and blanks included | a fixture where only one side strips `#` comments |

### Preventing any contact with the live store — three independent locks

1. The fake `bws` is at the head of `PATH` (established: `installFakeNpx`
   `rotation-worker-consumer.test.ts:54`, `installFakeBws`
   `rotation-bitwarden-consumer.test.ts:41`).
2. **Anti-vacuity precondition:** before any assertion, assert `command -v bws` resolves
   *inside the shim dir*, and abort the whole file otherwise. Without this a broken shim
   silently tests the real CLI and every green means nothing — the exact pattern
   `.ci/scripts/test/gates/test-gate-anti-vacuity.sh` exists to catch.
3. **Belt and braces:** the harness sets `BWS_ACCESS_TOKEN` to a sentinel that is not a
   valid token and passes `--server-url http://127.0.0.1:1`, so a bypassed shim fails to
   connect rather than reaching the org. In addition,
   `private/account/vitest.config.ts`'s `globalSetup` refuses to start if
   `BWS_ACCESS_TOKEN` matches the real machine-token shape.

### Wiring, three-point, per `scripts/ci-runner/manifest.ts`

The vitest suites already ride `check:ci-account-server` (manifest `:2278-2292`, job
`quality-go`). The new bash gate needs all three points or `ci-parity` /
`ci-gate-reachability-coverage` will fail it:

```jsonc
// package.json
"check:ci-bws-env-helper": ".ci/scripts/test/gates/test-bws-env-helper.sh"
```
```ts
// scripts/ci-runner/manifest.ts — same shape as check:ci-bws-map at :1303-1313
{ id: 'check:ci-bws-env-helper', run: 'npm run check:ci-bws-env-helper', gate: true,
  leaves: ['.ci/lib/bws-env.sh', '.ci/scripts/test/gates/test-bws-env-helper.sh'],
  ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml',
        job: 'quality-security', step: 'bws fetch helper' } }
```

`check:env-is-token-only` is deliberately **not** CI-wired, for the reason
`check-env-credential-drift.ts:5-12` already gives: `.env` is never present in CI, so a CI
entry would skip on every run — "a gate that is defined, reachable, and structurally
incapable of checking anything".

---

## Migration order, and the rollback (Part 7)

`.env` is untracked; there is no git undo. The ordering below maps one-to-one onto the task
list at the top of this file, and the backup is not optional.

1. **Preserve, twice, in two places** —
   `cp -p private/account/.env private/account/.env.pre-bws-$(date -u +%Y%m%dT%H%M%SZ).bak`
   (mode 0600; matched by `private/account/.gitignore:4` `.env.*`, so it cannot be
   committed), **and** an operator-run export of all 50 name/value pairs into the personal
   Bitwarden vault as one secure note. The vault is the only store outside this machine and
   it is unlocked by a different credential than `BWS_ACCESS_TOKEN`. Same discipline
   `secret-rename.py:316-329` already enforces before `--apply`.
2. **Mint the two machine accounts and replace the expiring token.** Blocks everything; the
   current token expires 2026-09-08. Update the GitHub org secret in the same sitting.
3. **Create `admin-bootstrap`, seed the 5 missing names**, verify the 18 that already
   resolve match what `.env` holds, then refresh the map. Operator-run, one time; no script
   writes to the store during migration.
4. **Land the read-only scaffolding with `.env` untouched** — `.ci/lib/bws-env.sh`,
   `with_fake_bws`, harness B, the `bws-map-refresh.py` / `check_bws_map.py` archive rules,
   `rotation bws-gc`. Everything green while the helper is still unused. Reversible by
   reverting code.
5. **Cut over the four non-secret readers first.** Zero Bitwarden dependency, removes 4 of
   12 read sites, and `test-rdc-sh-env.sh` must stay green.
6. **Cut over the secret readers one at a time**, each verified by running the real command
   and reading stdout and stderr separately.
7. **Retarget the seven writers** and land `check:env-is-token-only`.
8. **Only now truncate `.env`.** The single irreversible step, and it is last. Rollback at
   any earlier point is a code revert plus an untouched `.env`; after this it is a `cp` from
   the step-1 backup.
9. **Retarget the two gates**, fix the two stale citations, and decide bench and
   `dkim-notify`.

---

## Remaining (operator)

- `[?]` **`CLOUDFLARE_API_TOKEN` vs `CF_GLOBAL_API_KEY` for local scripts.**
  DEFAULT: set the scoped token in `ci-shared` as the local path, change
  `publish-solutions.sh:55-58` to require it instead of the global key, and confine the
  global key to `admin-bootstrap`. This shrinks the blast radius of every non-rotation local
  script from "full Cloudflare account" to a scoped token, and it is what makes the
  two-account split mean anything.
- `[?]` **Bench: leave `.env.bench` alone, or give bench its own SM project.**
  DEFAULT: leave it alone (option (i) in Part 4).
- `[?]` **Store the `dkim-notify` PEM in Secrets Manager?**
  DEFAULT: no, not this round; keep the staged-file path and the 1Password backup discipline
  CLAUDE.md already mandates.
- **Operator-only, no door around it** (`door:operator-only`): minting the two machine
  accounts and the `admin-bootstrap` project, seeding the 5 values, and rotating
  `BWS_ACCESS_TOKEN` itself. There is no `bws` verb for any of it.

## The one thing to verify before writing any code

Create a throwaway secret in a scratch project, `bws secret delete` it, and confirm from the
web UI that (1) it landed in **Trash** rather than being destroyed, and (2)
`bws secret list <project>` no longer returns it. Both are inferences today, both are
load-bearing, and the CLI documentation states neither. If (1) is false the protocol
destroys the value it was meant to preserve, and Part 4 must be replaced with a different
mechanism — most likely a long-lived `__ARCHIVE_<ts>` secret that is *not* deleted, with a
retention sweep, accepting the live-duplicate exposure as the price.

---

## Answers that arrived while this plan was being written (2026-09-02)

### The Trash question is SETTLED, and the protocol survives

Operator, after checking the web vault: *"_TRASH_PROBE_20260902T1833Z visible in trash at UI"*.
So `bws secret delete` is a **soft delete** — the value sits in Trash for 30 days, restorable.
The clone -> delete -> update protocol therefore does what it was designed to do, and the
`<NAME>_PREV_<datestamp>` alternative this plan proposed as a fallback is NOT needed.

Two caveats survive the answer and belong in the implementation:

1. **`bws` has no trash, restore or undelete verb** (its CLI is `create|edit|delete|get|list`).
   Recovery is a human in the web vault, inside 30 days. Nothing scripted can undo a rotation.
2. **For 9 of the 11 wired slugs this duplicates protection that already exists** — versioned
   platforms keep the predecessor live in `grace` for 7 days. The genuinely new coverage is
   `turnstile`, which carries no `versions` array at all and only 2h of platform grace.

Worth recording HOW it was settled, because the method generalises: the CLI could not answer
it. A probe created a throwaway secret with a generated value and deleted it; afterwards the
id 404s on `get` and vanishes from `list` — **identical under soft and hard delete**. A tool
that cannot distinguish two outcomes cannot be used to choose between them, and the honest
move was to say so and ask, rather than to infer from the 404.

### The single-token posture, recorded as an accepted risk

`BWS_ACCESS_TOKEN` today is ONE read-WRITE machine token (`mc_migrate_claude`), expiring
**2026-09-08**. This plan would make every local script depend on it. That is two risks in
one: an expiry cliff, and store-wide WRITE access present in every ordinary `./run.sh`.

The operator has approved the split (`mc-ci-read` read-only, `mc-rotate` read-write supplied
per rotation and never stored), but only they can mint it — no CLI verb creates or rotates a
machine-account token. **Until that lands, the single-token posture is an accepted risk**,
mitigated but not removed by:

- `.ci/config/bws-token-expiry.json` — the expiry date, written down because a BWS token
  carries no expiry inside itself, so the alternative is discovering it as an outage.
- `scripts/dev/bws-map-refresh.py::warn_if_token_expiring` — warns inside `warn_days`, and
  says plainly that a following auth error means expiry rather than a network fault.
- `client_id_sha256` in that file, checked against the live token, so a token swapped
  without updating the record is reported instead of the date silently describing a machine
  account that no longer exists.

The mitigation buys **warning, not time**. The token still dies on 2026-09-08.
