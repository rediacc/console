Status: draft
Owner: 74de73ca
Date: 2026-09-02
Supersedes: the classification in `agent/PLAN-env-to-bitwarden.md` Part 1. That plan's
Parts 2-7 (consumer map, fetch helper, clone protocol, gate retargets, migration order)
still stand except where Part 6 below amends them.
Scope: design. The two-way mapping in Part 2 was RUN (read-only, names only). Nothing was
written to Bitwarden, AWS, Cloudflare or GitHub. No value of any secret was read or printed.

# `.env` → Bitwarden, v2: classify on SHAREABILITY, not on secrecy

## Tasks

- [ ] Fix `private/growth/video_pipeline/publish-solutions.sh:55` and `publish.py:40` — they
      still require the pre-rename names `R2_MEDIA_{ACCESS_KEY_ID,SECRET_ACCESS_KEY,ENDPOINT}`
      while `.env` now holds `CLOUDFLARE_R2_MEDIA_*`. **The solution-video publish pipeline
      aborts at step 0 today.** Part 3, defect D1. Operator/`private/growth` write access.
- [ ] Delete `R2_MEDIA_BUCKET` from `private/account/.env` and `.env.example`. Zero readers
      anywhere; `sync-media-to-r2.sh:35` hardcodes `BUCKET="rediacc-www-media"`. Part 3, D2.
- [ ] Rename the local `.env` key `STRIPE_WEBHOOK_SECRET` → `STRIPE_WEBHOOK_SECRET_E2E_FIXTURE`
      (writer `.ci/lib/account.sh:238,296`; reader `.ci/lib/account.sh:825-827`). It is a
      committed test constant that collides by NAME with the real production secret in the
      store. Part 3, D3 — the one collision that would break something on cutover.
- [ ] Seed the 6 shareable store entries that cover 14 `.env` keys: `ROOT_EMAIL`,
      `AWS_SES_FROM`, `OTEL_ENDPOINT`, `UPSTREAM_URL`, `UPSTREAM_PUBLIC_KEY`, and the nine
      `SELLER_*` as one `SELLER_PROFILE_JSON` (Part 1 §c, §e). Operator-only.
      A seventh, `UPSTREAM_API_KEY`, waits on `## Remaining` Q1.
- [ ] Seed the 4 admin credentials (`AWS_IAM_ADMIN_ACCESS_KEY_ID`,
      `AWS_IAM_ADMIN_SECRET_ACCESS_KEY`, `CF_GLOBAL_API_KEY`, `CF_EMAIL`) into whichever
      project the operator picks in `## Remaining` Q2. Operator-only.
- [ ] Everything in v1's task list from "Write `.ci/lib/bws-env.sh`" onward, unchanged.
- [ ] Build `.ci/scripts/test/gates/test-bws-env-helper.sh` (Part 5, harness B).
- [ ] Add assertion 8 to `.ci/scripts/quality/check_bws_map.py` over
      `private/account/.env.example` + a new `.ci/config/env-local-allowlist.json` (Part 5,
      harness C). This is the gate that keeps the migration from silently rotting.
- [ ] Do NOT create `private/account/scripts/__tests__/`. Part 5 §"where it does not belong".

---

## Part 0 — what changed versus v1, and why

### 0.1 The axis changed, and it moves 18 names across the line

v1 split the 50 keys on **secrecy**: 23 secrets move, 21 non-secret config stays in a
committed `dev.defaults.env`, 5 machine-local stay in a gitignored `dev.local.env`, 1
bootstrap token stays in `.env`.

The operator's motive is **convenience of sharing across machines**, which is a different
axis. `SELLER_VAT_NUMBER` is not secret and is byte-identical on every machine and in every
deployment — it is precisely what a shared store is for. `PORT` is not secret either and is
a property of the machine. Secrecy does not separate those two; shareability does.

**The decision rule for v2, stated once:**

> A key STAYS LOCAL only if its correct value is a **function of this machine** — a path, a
> listening port, a URL derived from that port, or the bootstrap credential that is the root
> of trust for reading everything else. Everything else MOVES.

Applying it: **39 MOVE, 9 STAY, 1 ASK, 1 DELETE.** v1's "stays" set was 26; v2's is 9. The
18 that crossed are `ROOT_EMAIL`, `OTEL_ENDPOINT`, `AWS_SES_REGION`, `AWS_SES_FROM`, the
nine `SELLER_*`, `GITHUB_AUTOPILOT_APP_ID`, `UPSTREAM_URL`, `UPSTREAM_PUBLIC_KEY`, and the
two account public keys — which v1 put in a local file specifically to keep builds offline
(v1 headline §4). v2 keeps that property with a **cache**, not with a second home; see 0.4.

### 0.2 v1's Part 1 table is stale: the rename has already landed in `.env`

v1 tabulated `.env` as spelling `R2_ACCESS_KEY_ID`, `SES_AK_ID`, `AUTOPILOT_PRIVATE_KEY`,
`BREAKPOINT_TUNNEL_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN` — the pre-rename names — and concluded
that "alias handling is load-bearing and non-optional" because `.env` "MIXES both
conventions".

Measured today, name-only, from `private/account/.env`: it holds
`CLOUDFLARE_R2_ACCESS_KEY_ID`, `AWS_IAM_ADMIN_ACCESS_KEY_ID`, `GITHUB_AUTOPILOT_PRIVATE_KEY`,
`CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN`, `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`. `secret-rename.py`
carries `private/account/.env` in `EXTRA` (`scripts/dev/secret-rename.py:105`) and the
`--apply` ran: `private/account/.env.pre-rename.bak` exists beside it, mode 0600, exactly as
`:269` promises.

Consequence: **20 of the 50 `.env` keys now match a store name byte for byte** (Part 2),
against v1's implied 0. Alias handling is still needed, but for **three** names, not ten:
`AWS_SES_ACCESS_KEY_ID`, `AWS_SES_SECRET_ACCESS_KEY` (regional collapse) and
`OBS_OTLP_CREDENTIALS` (pre-regional leftover).

### 0.3 The rename broke a consumer that no console-side scan can see

`private/growth` is its own git repository. `git grep --recurse-submodules` from console is
blind to it — the trap `agent/PLAN-secret-namespace-migration.md` Part 18 records paying
for once already — and `secret-rename.py`'s file walk never reaches it. So the rename
updated `.env` and left `private/growth/video_pipeline/publish-solutions.sh:55` asserting
the old names against a file that no longer has them. Details and severity in Part 3, D1.

**This is not a migration risk. It is a live outage, today, in the publish pipeline.**

### 0.4 The three public keys move, and stay offline, via a cache

v1 declined to route `ACCOUNT_ED25519_PUBLIC_KEY`, `ACCOUNT_X25519_PUBLIC_KEY` and
`UPSTREAM_PUBLIC_KEY` through Bitwarden because four build-time readers need them offline
(`private/renet/build.sh:411-416`, `.ci/lib/local-common.sh:758-759`,
`scripts/docker/build-server.sh:41-42`, `rdc.sh:246-248`), and "a build that needs the
network to read a *public* key is a regression". That reasoning is correct and survives.

But it argues for a **cache**, not for a second source of truth. Two of the three are
already in the store (`ACCOUNT_ED25519_PUBLIC_KEY`, `ACCOUNT_X25519_PUBLIC_KEY`), so v1's
design would have left the store and the local file both claiming to be authoritative for
the same value with nothing comparing them — the exact shape of
`agent/PLAN-secret-namespace-migration.md` Part 16's "a generated file hand-edited to match
a rename is a lie with a timer on it".

v2: the store is authoritative. `./run.sh setup` writes
`private/account/.cache/public-keys.env` (gitignored, mode 0644 — these are public) from
`bws_export`, and the four readers `sed` that file instead of `.env`. `rdc.sh` still never
sources anything and still passes `.ci/scripts/test/test-rdc-sh-env.sh:55,61-68`.
A cache with one writer and a named refresh command is not a second home.

### 0.5 What v1 got right and v2 does not re-litigate

- `BWS_ACCESS_TOKEN` is the one irreducible local secret; no `bws` verb mints or rotates a
  machine-account token. `door:operator-only`, permanently.
- The token in `.ci/config/bws-token-expiry.json` is `mc_migrate_claude`, read-WRITE,
  **expires 2026-09-08**. Every task below that depends on `bws` waits on the `mc-ci-read` /
  `mc-rotate` split.
- `.env` is a **write** target for seven code paths (v1 Part 2 §Writers). Retarget them or
  the file re-grows silently.
- The clone → delete → update protocol (v1 Part 4) is unchanged and orthogonal to this.
- `private/elite/.env.template` is customer-supplied and never enters our store.

---

## Part 1 — the 50, classified on shareability

Names extracted with `sed -n 's/=.*//p'`. No value was read except one equality test whose
right-hand side is already committed in the clear (Part 3, D3). "map" = present in
`.ci/config/bws-secret-map.json` (56 entries, `refreshed_at` 2026-09-02T19:12:14Z).

### (a) STAYS LOCAL — 9 names

| name | why it is a function of THIS machine |
|---|---|
| `BWS_ACCESS_TOKEN` | the root of trust for reading the store; cannot come from the store. `.ci/config/bws-token-expiry.json` |
| `REDIACC_ACCOUNT_SERVER` | `http://localhost:4800`, and `private/account/src/entry/dev-gateway.ts:150-164` **rewrites it on every gateway start** with the port actually bound |
| `DATABASE_PATH` | `account.db`, a relative path resolved against the local checkout (`.ci/lib/account.sh:217`) |
| `PORT` | `3000` (`.ci/lib/account.sh:245,303`); a listening port |
| `CI_MODE` | asserts what this process is; `private/account/src/app.ts:200,204` gates Turnstile on it. A shared store cannot know |
| `WEBAUTHN_RP_ID` | `localhost` (`.ci/lib/account.sh:248,304`) |
| `WEBAUTHN_ORIGIN` | `http://localhost:${GATEWAY_PORT:-4800}` (`.ci/lib/account.sh:250,306`) |
| `WEBAUTHN_RP_NAME` | `Rediacc`; shareable in principle, kept local because the WebAuthn spec requires the origin's host to equal RP_ID, so the three form **one consistency triple**. Splitting a triple across two stores is how the halves drift |
| `STRIPE_WEBHOOK_SECRET` | **not a credential** — the committed E2E fixture constant. See D3; it is renamed, not moved |

That is the whole "stays" set. `PORT`, `DATABASE_PATH`, `CI_MODE` and the dev server URL are
exactly the four the brief named as untouchable, and the measurement agrees.

### (b) MOVE, already in the store — 19 names, nothing to seed

`ACCOUNT_ED25519_PRIVATE_KEY`, `ACCOUNT_ED25519_PUBLIC_KEY`, `ACCOUNT_X25519_PRIVATE_KEY`,
`ACCOUNT_X25519_PUBLIC_KEY`, `ACCOUNT_SERVER_API_KEY`, `ACCOUNT_JWT_SECRET`,
`CLOUDFLARE_TURNSTILE_SECRET_KEY`, `AWS_SES_REGION`, `CLOUDFLARE_R2_ACCESS_KEY_ID`,
`CLOUDFLARE_R2_SECRET_ACCESS_KEY`, `CLOUDFLARE_R2_ENDPOINT`,
`CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID`, `CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY`,
`CLOUDFLARE_R2_MEDIA_ENDPOINT`, `OBS_OTLP_CREDENTIALS`, `CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN`,
`GITHUB_AUTOPILOT_APP_ID`, `GITHUB_AUTOPILOT_PRIVATE_KEY`,
`ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`.

Two carry caveats that are not blockers:

- `AWS_SES_REGION` is exempted in `.ci/config/bws-unrequested.json` with the reason "public
  data … **should never enter a secret store**", while sitting in the store. The exemption
  argues against the entry it exempts. Reading it from there is harmless (it is public
  either way) but the contradiction should be resolved in one direction; recommendation:
  amend the reason to "public, stored for one-fetch convenience", because deleting the entry
  now costs a second config source for one string.
- `OBS_OTLP_CREDENTIALS` is a pre-regional leftover holding one region's value
  (`.ci/config/bws-unrequested.json`). Local `account dev` only ever needs one region, so it
  is the right thing to fetch locally — but the name is a trap for anyone who assumes it is
  the regional set. Fetch it aliased: `OBS_OTLP_CREDENTIALS > OBS_OTLP_CREDENTIALS`, with a
  comment naming the three `_EU/_US/_ASIA` entries as the deploy-time set.

### (c) MOVE, needs seeding — 12 names → 4 new store entries

| `.env` name(s) | store name to create | note |
|---|---|---|
| `ROOT_EMAIL` | `ROOT_EMAIL` | operator identity; identical on every machine. 46 files reference it, incl. `.ci/lib/account.sh:822` |
| `AWS_SES_FROM` | `AWS_SES_FROM` | already an org **variable** (`.ci/breakpoint/workflow/breakpoint.yml:332` `vars.AWS_SES_FROM`); consumed by all three `set-*-worker-secrets.sh` |
| `OTEL_ENDPOINT` | `OTEL_ENDPOINT` | `https://otlp.rediacc.io`, a constant (`.ci/lib/account.sh:302`) |
| `SELLER_{NAME,VAT_NUMBER,REGISTRATION_NUMBER,ADDRESS_LINE1,ADDRESS_LINE2,CITY,POSTAL_CODE,COUNTRY,EMAIL}` | **one** entry `SELLER_PROFILE_JSON` | nine fields of one company record. See below |

**Why the nine `SELLER_*` become one entry.** They are one object: a company's registration
identity, read together at `private/account/src/app.ts:308-310` and pushed together as nine
`--arg`s at `.ci/scripts/deploy/set-account-worker-secrets.sh:239-269` and
`set-www-worker-secrets.sh:107-132`. Nine store entries make nine independent things that can
disagree; one JSON blob cannot half-update. It also keeps the store's entry count honest —
adding nine rows for one fact inflates `MIN_MAP_ENTRIES`-style floors with no coverage gain.
The fetch helper expands it: `bws_export --json SELLER_PROFILE_JSON` binds the nine
`SELLER_*` names from the object's keys, and refuses if any of the nine is missing.

**Counter-argument, recorded rather than hidden:** nine flat entries mirror CI's nine
`vars.SELLER_*` (`cd-deploy-account.yml:401-405,…`) one-to-one, and a flat name is greppable.
If the operator prefers that symmetry, it is nine `create`s and one line of helper code less;
the cost is nine ways to have a stale address. Recommendation stands at one blob.

### (d) MOVE, admin-tier — 4 names, destination is `## Remaining` Q2

`AWS_IAM_ADMIN_ACCESS_KEY_ID`, `AWS_IAM_ADMIN_SECRET_ACCESS_KEY`, `CF_GLOBAL_API_KEY`,
`CF_EMAIL`. These are in **no store at all** today (`agent/PLAN-secret-namespace-migration.md`
Part 17b calls them "a larger hole than the 18"). They authenticate the rotation tool itself
(`private/account/scripts/rotation/lib/credentials.ts:59-71,86-106`) and are strictly more
powerful than the four SES sending keys that *are* stored. They MOVE; the only question is
into which project, and that is a security-posture call, not a classification one.

### (e) MOVE, on-prem upstream — 3 names, one of which is an ASK

- `UPSTREAM_URL` → MOVE. `https://www.rediacc.com`, a constant
  (`private/account/src/entry/on-premise.ts:141`, `src/types/env.ts:246`).
- `UPSTREAM_PUBLIC_KEY` → MOVE + cache (0.4). Baked at image build time by
  `.ci/docker/web/entrypoint.sh:221-226`, so it must be readable offline.
- `UPSTREAM_API_KEY` → **ASK**, see `## Remaining` Q1.

### (f) DELETE — 1 name

`R2_MEDIA_BUCKET`. Zero readers in console, both submodules, and `private/growth`. See D2.

### Count

Counted in `.env` keys, so the four buckets sum to 50.

| bucket | `.env` keys | store entries created |
|---|---|---|
| MOVE — exact name already in the store (b) | 19 | 0 |
| MOVE — resolves to an existing store entry by alias (b) | 2 | 0 |
| MOVE — seed (c): `ROOT_EMAIL`, `AWS_SES_FROM`, `OTEL_ENDPOINT`, 9 × `SELLER_*` | 12 | 4 |
| MOVE — admin (d) | 4 | 4 |
| MOVE — upstream (e): `UPSTREAM_URL`, `UPSTREAM_PUBLIC_KEY` | 2 | 2 |
| **MOVE total** | **39** | **10** |
| ASK (e): `UPSTREAM_API_KEY` | 1 | 0 or 1 |
| STAYS LOCAL (a) | 9 | 0 |
| DELETE (f) | 1 | 0 |
| **total** | **50** | |

Three of the 39 (`ACCOUNT_ED25519_PUBLIC_KEY`, `ACCOUNT_X25519_PUBLIC_KEY`,
`UPSTREAM_PUBLIC_KEY`) additionally get a local cache so builds stay offline (0.4).

The store grows by **10 entries, not 39** — 19 names already exist, 2 alias onto existing
regional entries, and 9 `SELLER_*` collapse into one. Both entry floors clear it unchanged:
`MIN_MAP_ENTRIES = 30` (`.ci/scripts/quality/check_bws_map.py:94`) and `MIN_ENTRIES = 40`
(`scripts/dev/bws-map-refresh.py:50`); the map goes 56 → 66.

---

## Part 2 — the two-way mapping, RUN

**What was executed, and what was not.** `bws` is **not installed in this environment**
(`command -v bws` → exit 1; `/usr/local/bin/bws` absent; the devcontainer installs it at
`.devcontainer/Dockerfile:453-463`). So the comparison below is against the **committed
map**, not a live `bws secret list`. That is a real limitation and it is the same one
`check_bws_map.py`'s own docstring accepts ("DELIBERATELY NOT ASSERTED — that a UUID is live
in Bitwarden"). The map's `refreshed_at` is 2026-09-02T19:12:14Z — today — and
`bws-map-refresh.py` regenerates it from the store, so it is the freshest name-level record
available without a token. **Re-run the identical comparison with `bws --color no secret list
<project> --output json` inside the devcontainer before acting on the "absent" column.**

Method: name-only set algebra over `sed -n 's/=.*//p' private/account/.env` (50) and
`.ci/config/bws-secret-map.json .secrets | keys` (56). GitHub twins resolved through
`secret-rename.py`'s `RENAMES` table read as data (the technique `check_bws_map.py` uses, so
the two cannot disagree) against `.ci/config/secret-reachability.json`.

### 2.1 `.env` → store

| `.env` key | store name | status |
|---|---|---|
| `ACCOUNT_ED25519_PRIVATE_KEY` | same | exact |
| `ACCOUNT_ED25519_PUBLIC_KEY` | same | exact |
| `ACCOUNT_X25519_PRIVATE_KEY` | same | exact |
| `ACCOUNT_X25519_PUBLIC_KEY` | same | exact |
| `ACCOUNT_SERVER_API_KEY` | same | exact |
| `ACCOUNT_JWT_SECRET` | same | exact |
| `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` | same | exact |
| `AWS_SES_REGION` | same | exact |
| `CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN` | same | exact |
| `CLOUDFLARE_R2_ACCESS_KEY_ID` | same | exact |
| `CLOUDFLARE_R2_ENDPOINT` | same | exact |
| `CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID` | same | exact |
| `CLOUDFLARE_R2_MEDIA_ENDPOINT` | same | exact |
| `CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY` | same | exact |
| `CLOUDFLARE_R2_SECRET_ACCESS_KEY` | same | exact |
| `CLOUDFLARE_TURNSTILE_SECRET_KEY` | same | exact |
| `GITHUB_AUTOPILOT_APP_ID` | same | exact |
| `GITHUB_AUTOPILOT_PRIVATE_KEY` | same | exact |
| `OBS_OTLP_CREDENTIALS` | same | exact |
| `STRIPE_WEBHOOK_SECRET` | same | **exact name, DIFFERENT THING — D3** |
| `AWS_SES_ACCESS_KEY_ID` | `AWS_SES_ACCESS_KEY_ID_EU` | alias, intended |
| `AWS_SES_SECRET_ACCESS_KEY` | `AWS_SES_SECRET_ACCESS_KEY_EU` | alias, intended |
| `ROOT_EMAIL` | — | absent, seed (c) |
| `AWS_SES_FROM` | — | absent, seed (c) |
| `OTEL_ENDPOINT` | — | absent, seed (c) |
| `SELLER_*` ×9 | — | absent, seed as `SELLER_PROFILE_JSON` (c) |
| `AWS_IAM_ADMIN_ACCESS_KEY_ID` | — | absent, seed (d) |
| `AWS_IAM_ADMIN_SECRET_ACCESS_KEY` | — | absent, seed (d) |
| `CF_GLOBAL_API_KEY` | — | absent, seed (d) |
| `CF_EMAIL` | — | absent, seed (d) |
| `UPSTREAM_URL` | — | absent, seed (e) |
| `UPSTREAM_PUBLIC_KEY` | — | absent, seed (e) |
| `UPSTREAM_API_KEY` | — | absent, pending Q1 |
| `R2_MEDIA_BUCKET` | — | absent, and **dead — D2** |
| `BWS_ACCESS_TOKEN` | — | absent **by design**; bootstrap |
| `REDIACC_ACCOUNT_SERVER`, `DATABASE_PATH`, `PORT`, `CI_MODE`, `WEBAUTHN_RP_ID`, `WEBAUTHN_RP_NAME`, `WEBAUTHN_ORIGIN` | — | absent **by design**; machine-local (a) |

**20 exact / 2 intended aliases / 20 absent-and-should-be-seeded / 1 dead / 7 absent by
design.** No `.env` key resolves to a store name by accident.

### 2.2 store → `.env`

36 of the 56 mapped names have no `.env` key. **Every one is explainable and none is a
defect**, which is worth stating because a 36-name gap looks alarming:

| group | names | why no `.env` key |
|---|---|---|
| deploy-time regional expansions | `AWS_SES_{ACCESS_KEY_ID,SECRET_ACCESS_KEY}_{EU,US}`, `OBS_OTLP_CREDENTIALS_{EU,US,ASIA}`, `STRIPE_WEBHOOK_SECRET_{EU,US,ASIA}` | built at runtime as `PREFIX_${SUFFIX}` (`set-account-worker-secrets.sh:134-135`); a dev machine runs one region |
| Stripe live/sandbox set | `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_SANDBOX_{SECRET_KEY,PUBLISHABLE_KEY,WEBHOOK_SECRET,WEBHOOK_SECRET_ID}`, `STRIPE_WEBHOOK_SECRET_ID` | opt-in locally; `.env.example` lists them commented out. `STRIPE_SANDBOX_WEBHOOK_SECRET` is auto-captured from `stripe listen` (`.ci/lib/account.sh:235`) |
| customer-supplied onprem | `SMTP_{HOST,PORT,USER,PASSWORD,FROM}` | set by the customer on the onprem image; `.ci/config/bws-unrequested.json` says so per name |
| account-backup plane | `ACCOUNT_BACKUP_S3_{ACCESS_KEY_ID,SECRET_ACCESS_KEY,ENDPOINT}` | `programs/backup-storage/start-local-plane.sh:60-64` **relies on these being ABSENT from `.env`** so its own exports survive |
| CI-only | `DOCKERHUB_{USERNAME,TOKEN}`, `RELEASE_GPG_{PRIVATE_KEY,PASSPHRASE}`, `GITHUB_APP_{PRIVATE_KEY,CLIENT_SECRET}`, `CLOUDFLARE_API_TOKEN` | publish/release paths that never run on a dev machine |
| observability halves | `OBS_OTLP_{USERNAME,PASSWORD}` | everything consumes the joined `OBS_OTLP_CREDENTIALS` |
| unattributed | `R2_TOKEN_AUTH_API` | identified in Part 17b as the raw bearer value of a CF R2 token; dead as a stored entry, pending dashboard confirmation before revoking |
| SMTP endpoint | `AWS_SES_HOST` | the account server talks to SES over the API |

One name is worth flagging as a **near-miss rather than a gap**: `CLOUDFLARE_API_TOKEN` is in
the store and in `.env.example` but not in `.env`, and `agent/PLAN-secret-namespace-migration.md`
Part 2 records that its absence is what makes every local Cloudflare consumer fall through to
`CF_GLOBAL_API_KEY` — the full-account Global API Key. That is the substance of `## Remaining`
Q2.

### 2.3 The third direction nobody was comparing: `.env` vs `.env.example`

`private/account/.env.example` is **tracked** (`git -C private/account ls-files`), 11 active +
44 commented names. Measured: **all 50 live `.env` keys appear in it**, and the five it has
that `.env` lacks are the opt-ins listed above. It is therefore a complete, CI-visible,
reviewable surrogate for a file CI can never see — which is what makes harness C in Part 5
possible at all. Nothing today asserts it stays that way.

---

## Part 3 — the disagreements, ranked by what they break

### D1 — `private/growth` publish pipeline is BROKEN TODAY (severity: highest)

```
private/growth/video_pipeline/publish-solutions.sh:47-51   set -a; source "$REPO_ROOT/private/account/.env"; set +a
private/growth/video_pipeline/publish-solutions.sh:55      for v in R2_MEDIA_ACCESS_KEY_ID R2_MEDIA_SECRET_ACCESS_KEY R2_MEDIA_ENDPOINT; do
private/growth/video_pipeline/publish-solutions.sh:56          [[ -n "${!v:-}" ]] || die "$v is empty; the upload would fail open and publish nothing"
private/growth/video_pipeline/publish.py:40                _R2_ENV_VARS = ("R2_MEDIA_ACCESS_KEY_ID", "R2_MEDIA_SECRET_ACCESS_KEY", "R2_MEDIA_ENDPOINT")
```

`.env` holds `CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID` etc. since the rename
(`scripts/dev/secret-rename.py:58-60`). The three `${!v}` reads therefore expand empty and
`die` fires at step 0 of every solution-video publish.

**How it escaped every gate.** `secret-rename.py`'s walk covers tracked console files plus
`EXTRA` (`:105`); `private/growth` is a separate git repository, so it is in neither. And
`check_bws_map.py` only scans workflows. There is no console-side instrument that can see a
`private/growth` consumer — Part 18 already recorded exactly this blindness for
`apollo-companies/.env` and the lesson did not generalise to the rename.

**Severity, precisely.** It fails LOUDLY (`die`, exit 1) rather than publishing nothing and
exiting 0 — the `die` at `:56` was written for a different reason and happens to catch this.
So it is an outage, not a silent corruption. `CF_GLOBAL_API_KEY`/`CF_EMAIL` at `:58` are
unaffected; those names did not change.

**Fix**: rename the three names in `publish-solutions.sh:55` and `publish.py:40`. Outside
this session's write access (`door:no-write-access` for a design-only agent) — it belongs to
whoever holds `private/growth`.

**And the class, not the instance**: any `private/growth` or `private/generative` file that
sources console's `.env` must be swept for all 25 rename pre-images, not just these three.
`grep -rIn -E '\b(R2_|BACKUP_S3_|TURNSTILE_|BREAKPOINT_|SES_AK_|APP_PRIVATE_KEY|AUTOPILOT_|CLAUDE_CODE_OAUTH|GPG_|OTLP_CLIENT_)' private/growth private/generative`
is the sweep.

### D2 — `R2_MEDIA_BUCKET` is dead, and a doc asserts the opposite

Zero readers. `.ci/scripts/deploy/sync-media-to-r2.sh:35` hardcodes
`BUCKET="rediacc-www-media"`. The only mentions anywhere are prose:
`CLAUDE.md:649` (calls it an org *variable*), and `.claude/agents/media-pipeline.md:343`,
which says **"`R2_MEDIA_BUCKET` is not in `private/account/.env`"** — it is, at line 41.

This falsifies `agent/PLAN-secret-namespace-migration.md` Part 18's measurement that "**all
50 keys** in `private/account/.env` have live readers". 49 do. The one that does not is the
one whose readers were assumed from a CLAUDE.md sentence rather than grepped.

**Disposition: DELETE from `.env` and `.env.example`. Do not seed it.** Migrating a dead key
into a shared store is how a store accumulates entries nobody can retire, which is the
`R2_TOKEN_AUTH_API` situation reproduced deliberately.

### D3 — `STRIPE_WEBHOOK_SECRET`: one name, two different things (severity: cutover-breaking)

The store's `STRIPE_WEBHOOK_SECRET` (uuid `6d666417-8d60-4b87-a5bf-b4b800aaeb21`) is the real
Stripe webhook signing secret. `.env`'s `STRIPE_WEBHOOK_SECRET` is **the committed test
constant** — verified by an exact-line match against the literal already in the clear at
`.ci/lib/account.sh:238` and `:296` (`whsec_e2e_test_webhook_secret_for_simulation_only`), so
no secret was read to establish it.

`.ci/lib/account.sh:825-827` exports it as `E2E_WEBHOOK_SECRET` for the E2E webhook
simulation suite. A naive `bws_export STRIPE_WEBHOOK_SECRET` in `account dev` would therefore
(a) sign simulated webhooks with the production secret, breaking the suite in a way that
looks like a test bug, and (b) put a production credential into a dev gateway that did not
previously hold one.

**Fix: rename the local key `STRIPE_WEBHOOK_SECRET_E2E_FIXTURE`** at its writer
(`.ci/lib/account.sh:238,296`) and its reader (`:825-827`), and add it to `.env.example`.
Then the collision is gone by construction and the store entry can be fetched by any consumer
that genuinely wants the production secret. A name that means two things in two places is not
a spelling difference; it is the only entry in this table that would have shipped a wrong
value rather than an empty one.

### D4 — spelling differences that are INTENDED

- `AWS_SES_ACCESS_KEY_ID` / `AWS_SES_SECRET_ACCESS_KEY` (`.env`) vs `_EU` / `_US` (store).
  Deliberate: `set-account-worker-secrets.sh:26,205` documents the
  `AWS_SES_ACCESS_KEY_ID_<SUFFIX> -> Worker AWS_SES_ACCESS_KEY_ID` collapse, and
  `.github/workflows/ci.yml:1471` already does exactly this aliasing. Local dev is EU.
  Express it with the existing `NAME > ENV_NAME` grammar
  (`.github/actions/bws-secrets/action.yml:35-40`), never by renaming either side.
- `OBS_OTLP_CREDENTIALS` (unsuffixed, both sides) alongside `OBS_OTLP_CREDENTIALS_{EU,US,ASIA}`
  (store only). Intended today, but it is a name that will read as a bug to the next person;
  the exemption file already explains it and the fetch site should cite that line.
- `SELLER_*` vs the proposed `SELLER_PROFILE_JSON`: a deliberate shape change, not a rename.

### D5 — spelling differences that are NOT intended

None found beyond D1 and D3. Specifically checked and clean: every `.env` key that resolves
to a store name resolves to the right one, and no store name is a near-miss of a `.env` key
(no case, underscore, or `CLOUDFLARE_`/`CF_`-prefix variants left over from the rename inside
`.env` itself). `CF_GLOBAL_API_KEY` and `CF_EMAIL` keep the `CF_` prefix while everything else
moved to `CLOUDFLARE_`; that is a **pre-existing inconsistency in the rename table**
(`secret-rename.py:54-64` renames `TURNSTILE_*` and `BREAKPOINT_*` to `CLOUDFLARE_*` but not
these two) and should be settled when they are seeded in (d), so the store is not born with
it.

---

## Part 4 — what the fetch mechanism must gain over v1

v1's `.ci/lib/bws-env.sh` design (Part 3: one `bws secret list` per process, `--color no`,
`declare -g` never `eval`, no cache by default, seven loud failure modes) is unchanged and
correct. Four additions follow from v2's wider MOVE set:

1. **`--json NAME` mode**, for `SELLER_PROFILE_JSON`: parse the value as an object and bind
   each key as a variable, refusing on a missing key, a non-object, or a key that is not a
   legal shell identifier. Same `declare -g`, same no-`eval` rule.
2. **`--cache-to <file>` mode**, used only by `./run.sh setup` for the three public keys
   (0.4). Writes `NAME=value` lines to a gitignored file. Distinct from v1's rejected value
   cache: this writes **public** keys only, and the helper must refuse `--cache-to` for any
   name not on a hardcoded 3-name public allowlist. Without that refusal it is a general
   secret-to-disk primitive one argument away.
3. **The alias list shrank to three names** (0.2), so the grammar-parity assertion against
   `check_bws_map.py::parse_requests` (v1 harness B, B7) matters more, not less — three is
   few enough that a broken alias parser would look like it works.
4. **A refusal on `STRIPE_WEBHOOK_SECRET` until D3 lands.** A hardcoded temporary guard, with
   the reason in the message. Cheaper than remembering.

---

## Part 5 — the test question, answered

### Where it does NOT belong

**`private/account/scripts/__tests__/env-from-bitwarden.test.ts` would never run.**
`private/account/vitest.config.ts:7`:

```ts
include: ['tests/integration/**/*.test.ts', 'tests/pricing/**/*.test.ts'],
```

A file under `scripts/__tests__/` matches neither glob, and no vitest workspace file exists
in the repo (`private/account`, `private/account/web`, `packages/{shared,cli,www,e2e-tests}`
each have their own standalone `vitest.config.ts`). It would be collected by nothing, report
nothing, and pass forever. **That is the exact failure mode this repo's control-first rule
exists to prevent, so the scaffold is deliberately not written.** The directory does not
exist today and should not be created.

The convention the repo actually has: rotation/`bws` tests are vitest files under
`private/account/tests/integration/` — `rotation-bitwarden-consumer.test.ts` (149 lines) and
`rotation-bitwarden-names.test.ts` (588 lines) — and bash-helper tests are gates under
`.ci/scripts/test/gates/` (73 files).

### Three candidates, and what each cannot catch

| | catches | does NOT catch |
|---|---|---|
| **A. vitest unit test over the fetch helper with a faked `bws`** | nothing new — the helper is bash. A TS test would have to shell out, which is harness B with a worse runner | — |
| **B. bash gate test over `.ci/lib/bws-env.sh` with a faked `bws` on PATH** | every failure mode of the fetch: empty value exported, injection through a value, alias binding the wrong variable, stdout leaking on error, offline degrading to a stale read | that a name is *missing from the store*, or that a `.env` key was forgotten. It only tests the mechanism, against fixtures it supplies itself |
| **C. a completeness gate: every `.env.example` key is mapped or explicitly local** | the migration rotting — a new key added to `.env` that nobody moved, a store entry deleted out from under a consumer, a rename landing on one side only. **This is the class that produced D1, D2 and D3** | anything about values or runtime behaviour. It is a name-level gate and says so |
| **D. round-trip against a scratch project** | that `create`/`get`/`delete` really behave as documented | **rejected.** It needs a live read-WRITE token in CI — the exact credential this work exists to stop spreading — and per `check_bws_map.py`'s own docstring a gate that needs a token "silently degrades to *passed* wherever the token is absent". It would be green in every CI run and only ever exercised locally |

### Recommendation: B **and** C. B alone is the wrong answer.

B protects the code being written. C protects the migration being *kept*. Every defect this
session actually found — a consumer left on the old spelling, a dead key nobody noticed, a
name meaning two things — is a C-class defect that B is structurally incapable of seeing.

### Harness B — `.ci/scripts/test/gates/test-bws-env-helper.sh`

Prior art to follow, verified: `with_fake_gh` at `.ci/scripts/test/lib/test-helpers.sh:93-112`
(shim dir on `PATH`, restore, `rm -rf`), the richer `SHIMDIR` + `plant()` shape at
`.ci/scripts/test/gates/test-autopilot-no-bypass.sh:36-58`, and the fake-`bws` that
faithfully reproduces bws 2.1.0's ANSI-on-pipe behaviour at
`private/account/tests/integration/rotation-bitwarden-consumer.test.ts:41-90` — which is what
makes `--color no` a real control rather than a decoration. Add `with_fake_bws` beside
`with_fake_gh`.

v1's assertions B1-B7 stand verbatim. Three more, from v2's wider set:

| # | assertion | planted defect that must make it RED |
|---|---|---|
| B8 | `--json SELLER_PROFILE_JSON` binds all nine `SELLER_*`; a fixture missing `SELLER_CITY` exits non-zero **naming `SELLER_CITY`** | a helper that binds the eight it found and returns 0 — the partial-company-record failure, which would ship an invoice with a blank city |
| B9 | `--json` on a value that is a JSON *string* (not an object), and on one whose key is `not-an-identifier`, both exit non-zero | a helper that `declare -g`s a name with a dash in it, or that iterates a string's characters |
| B10 | `--cache-to` refuses any name outside the 3-name public allowlist, exits non-zero, and **writes no file** | a helper that caches `ACCOUNT_ED25519_PRIVATE_KEY`; assert the target path does not exist afterwards, not merely that the exit code is non-zero |

**Anti-vacuity precondition, mandatory** (v1 already specifies it; restating because it is the
one that makes the rest mean anything): before any assertion, assert `command -v bws` resolves
*inside the shim directory* and abort the whole file otherwise. Without it a broken shim
silently tests the real CLI against the real org.

Wiring, three-point, same shape as `check:ci-bws-map`
(`package.json:138`, `scripts/ci-runner/manifest.ts:1303-1314`, workflow
`.github/workflows/ci-quality.yml` job `quality-security`):

```jsonc
"check:ci-bws-env-helper": ".ci/scripts/test/gates/test-bws-env-helper.sh"
```
```ts
{ id: 'check:ci-bws-env-helper', run: 'npm run check:ci-bws-env-helper', gate: true,
  leaves: ['.ci/lib/bws-env.sh', '.ci/scripts/test/gates/test-bws-env-helper.sh'],
  ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml',
        job: 'quality-security', step: 'bws fetch helper' } }
```

### Harness C — assertion 8 in `check_bws_map.py`, over `.env.example`

**Subject.** `private/account/.env.example` (tracked, CI-visible), not `.env` (untracked,
never present in CI). Part 2.3 measured that it currently covers all 50 live keys, which is
what makes it a legitimate surrogate — and assertion 8a below is what keeps it one.

**New file `.ci/config/env-local-allowlist.json`**, modelled on
`.ci/config/bws-unrequested.json` (the exemption registry whose `kind` is **re-derived**
rather than believed):

```jsonc
{
  "entries": {
    "PORT":                  { "kind": "machine-local", "reason": "a listening port", "derive": ".ci/lib/account.sh:245" },
    "WEBAUTHN_ORIGIN":       { "kind": "machine-local", "reason": "derived from GATEWAY_PORT", "derive": ".ci/lib/account.sh:305" },
    "BWS_ACCESS_TOKEN":      { "kind": "bootstrap",     "reason": "root of trust; no bws verb mints one" },
    "STRIPE_SANDBOX_SECRET_KEY": { "kind": "opt-in",    "reason": "commented in .env.example; absent from .env by default" },
    "…":                     { "kind": "deferred",      "reason": "…", "worklist": "…", "expires": "2026-…" }
  }
}
```

Four kinds, each re-derived so the list cannot rot into a lie:

| kind | re-derived against | goes RED when |
|---|---|---|
| `machine-local` | the `derive` citation must exist AND the cited line must still assign that name | someone moves the default into the store, or deletes the writer |
| `bootstrap` | the name must be absent from `bws-secret-map.json` | it is ever added to the store, which would be a circularity |
| `opt-in` | the name must appear **commented out** in `.env.example`, never active | it becomes an active default, at which point it needs a home |
| `deferred` | its own UTC `expires` date and a worklist id | that date passes, whether or not anyone looked |

**Assertions:**

- **8a. `.env.example` is complete.** Every name assigned in `.env.example`, active or
  commented, is either in `bws-secret-map.json` or in `env-local-allowlist.json`. Neither
  side may be empty (anti-vacuity: an empty example file and an empty allowlist both pass a
  naive version).
- **8b. no orphan exemptions.** Every `env-local-allowlist.json` entry names a key that is
  actually in `.env.example`. This is what would have flagged D2: delete `R2_MEDIA_BUCKET`
  from the example and its exemption reds until it is dropped too.
- **8c. the local-only surrogate is honest.** For each `machine-local` entry, the `derive`
  file:line must exist and must contain that name. Cheap, and it is the assertion that keeps
  the "why" from becoming folklore.

**The planted defects that must make it red** — control-first, following
`check_bws_map.py:436-470`'s `selftest()`, which already proves its parser in both directions
on synthetic input before issuing any verdict:

1. Add `NEW_THING=x` to a copy of `.env.example`, in neither store nor allowlist → 8a RED
   naming `NEW_THING`. *(the D1/new-key class)*
2. Remove one name from the map fixture while a `.env.example` key still needs it → 8a RED.
   *(the "store entry deleted under a consumer" class)*
3. Leave an allowlist entry for a name deleted from `.env.example` → 8b RED. *(D2's class)*
4. Point a `machine-local` entry's `derive` at a line that does not contain the name → 8c
   RED. *(the folklore class)*
5. **Empty the allowlist AND empty `.env.example`** → must still RED on the floor, not pass
   silently. This is the control that a naive implementation fails.
6. Flip an `opt-in` entry's line in `.env.example` from commented to active → RED.

Each must be run against the **real tree**, not only fixtures, and every touched file
restored byte-identical afterwards — the discipline `agent/PLAN-secret-namespace-migration.md`
Part 17c records for the nine defects planted against assertions 5-7.

Wiring: none new. It rides `check:ci-bws-map`, which is already three-point wired.

### What neither B nor C covers, stated plainly

Neither can see a consumer in `private/growth` (a separate repository), which is exactly where
D1 lives. **No console-side gate can.** The honest fix is a gate *inside* `private/growth`
asserting that every name its scripts require is present in the `.env` it sources — the same
shape as C, in the repo that has the consumer. That is `private/growth`'s to build; recording
it here so the gap is named rather than assumed covered.

---

## Part 6 — amendments to v1's Parts 2, 5 and 7

- **v1 Part 1 (a)/(b)/(b′) are superseded** by Part 1 here. `dev.defaults.env` is **not
  created** — its 21 names now MOVE. `dev.local.env` shrinks from 5 names to the 8
  non-bootstrap entries of Part 1 (a), and `private/account/.cache/public-keys.env` replaces
  its public-key role (0.4).
- **v1 Part 2's consumer table stands**, with two corrections: the `.env` names in it are
  pre-rename (0.2), and `programs/backup-storage/start-local-plane.sh:60-64`'s reliance on
  `ACCOUNT_BACKUP_S3_*` being ABSENT from `.env` becomes *load-bearing*, because v2 fetches
  from a store that DOES hold those three names. The explicit-list rule is what protects it;
  `bws_export` must never be given a wildcard.
- **v1 Part 5's `check:env-is-token-only` is replaced** by harness C. v1's version asserted
  `.env` contains only `BWS_ACCESS_TOKEN*`; under v2 `.env` legitimately holds 9 names, so
  the assertion becomes "every key in `.env` is in the allowlist or was fetched" — and it
  runs in CI against `.env.example` instead of only locally against a file CI cannot see.
  Keep a local-only companion in `./run.sh setup` that applies 8a to the real `.env`.
  **Correction to v1 while placing it:** v1 said to land it "as a blocking preflight …
  beside the drift check (`run.sh:1915-1925`)". That neighbour is explicitly **not**
  blocking — `run.sh:1918-1924` runs `check:env-credential-drift` inside an `if !` that only
  `log_warn`s, and says so in its own text ("ROTATION IS AN OPS TASK … so this does not stop
  setup"). Copying its placement would silently copy its severity. The completeness check
  **must** exit non-zero: a `.env` key with no home is a developer-fixable error, not an ops
  backlog item, and a warning in a 200-line `setup` transcript is not read.
- **v1 Part 7's ordering stands**, with D1/D2/D3 inserted as step 0. They are pre-existing
  defects, they are cheap, and D3 in particular must land before any `bws_export` of
  `STRIPE_WEBHOOK_SECRET` exists in the tree.

---

## Remaining (operator)

- `[?]` **Q1 — `UPSTREAM_API_KEY`: shared or per-install?** It is the delegation auto-renew
  token an on-prem install uses against `www.rediacc.com`
  (`private/account/src/entry/on-premise.ts:45-53,142`;
  `src/routes/portal-delegation-certs.ts:300-301` issues it). The portal enforces **one
  active delegation cert per subscription**, so two machines holding the same token are
  renewing one chain — which is either exactly what you want (one shared dev on-prem
  identity) or a way for two machines to fight over one cert.
  **DEFAULT: MOVE it.** One subscription, one token, one store entry; the alternative is
  each machine minting its own and no way to tell them apart.

- `[?]` **Q2 — where do the 4 admin credentials live, and does `CF_GLOBAL_API_KEY` survive?**
  `AWS_IAM_ADMIN_*` + `CF_GLOBAL_API_KEY`/`CF_EMAIL` are the most powerful credentials in the
  file. Seeding them into `ci-shared` upgrades `BWS_ACCESS_TOKEN` from "everything CI can
  deploy" to "everything the AWS and Cloudflare accounts can do" — for a token that sits
  unencrypted in a file every local script sources. v1 proposed a second `admin-bootstrap`
  project readable only by `mc-rotate`; the snag is `publish-solutions.sh:58`, which needs
  `CF_GLOBAL_API_KEY` for a CDN purge and would then need the privileged token.
  **DEFAULT: `admin-bootstrap` for all four, AND set `CLOUDFLARE_API_TOKEN` (already in
  `ci-shared`, already in `.env.example`, absent from `.env`) as the local Cloudflare path so
  `publish-solutions.sh` requires the scoped token instead of the global key.** That is what
  makes the two-account split mean anything: it shrinks every non-rotation local script from
  "full Cloudflare account" to a scoped token.

- `[?]` **Q3 — nine `SELLER_*` entries or one `SELLER_PROFILE_JSON`?** Part 1 (c) argues both
  sides. **DEFAULT: one blob.**

- `[?]` **Q4 — who fixes D1?** `private/growth` is outside this repo's write access. The fix
  is three names in two files and the sweep in Part 3. **DEFAULT: the operator applies it, or
  grants a session write access to `private/growth`; the publish pipeline is broken until
  then.**

- **Operator-only, no door around it** (`door:operator-only`): minting `mc-ci-read` and
  `mc-rotate` (the current token expires **2026-09-08**), creating whichever project Q2
  picks, seeding the values, and rotating `BWS_ACCESS_TOKEN` itself. There is no `bws` verb
  for any of it.

- **Not verified here, must be verified before acting**: the "absent" column of Part 2 is
  against the committed map, because `bws` is not installed in this environment. Re-run
  `bws --color no secret list <project> --output json` inside the devcontainer and diff the
  key set against `.ci/config/bws-secret-map.json`. If the two disagree, the map is stale and
  every conclusion in Part 2 that depends on absence is provisional.
