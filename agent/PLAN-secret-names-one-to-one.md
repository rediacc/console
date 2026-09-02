Status: DESIGN, not started. Measured 2026-09-02 against the working tree as it then
stood (the Part 19 rename already applied, uncommitted; org secrets not yet renamed).
Every count below was produced by running a parser over the real files, not by reading;
the parsers are named so the numbers can be re-derived rather than believed.

# One credential, one name: the alias inventory and the 1-1 target state

## The ask

> *"I see some horrible aliasing! Employ a planning agent! We should have 1-1"*

The complaint is right and the measurement backs it: in the workflow layer alone there
are **465 lines that bind a secret to a name other than its own**, against **394 that
bind it to its own name**. Fifty-four percent of every secret-name binding in
`.github/workflows/` is an alias.

But the headline number is misleading in the direction that matters, and a plan that
chases it will make the repo worse. Two corrections come first.

## Tasks

Everything here is a real unit of work. The four in the first group need no cutover, no
operator, and no org-secret change; they are one commit at zero migration risk.

- [x] Delete `SSH_USER: ${{ env.USER }}` at `ct-tests.yml:1774,1787` — the source does not exist, the line is inert (finding 1)
      AUDIT: DONE 2026-09-02 (audit): `git grep -n --recurse-submodules 'SSH_USER: '` finds nothing; both lines removed from ct-tests.yml and both steps survive without them (ct-tests.yml:1769-1786).
- [ ] Fix the schema extractor in `scripts/check-worker-secret-names.ts:69` so it sees all 85 `env.ts` keys, and derive the count in the refusal message at `:104` instead of hardcoding it (finding 2, assertion 12)
      AUDIT: PARTIAL: the extractor is fixed -- check-worker-secret-names.ts:76 reads `/^\s{2}([A-Z][A-Z0-9_]*):\s*(?:z\.|z$|boolFromEnv)/gm` and both counts over env.ts agree at 85; floor raised 40->80 at :113. NOT done: the count is still the hand-maintained ratchet EXPECTED_SCHEMA_KEYS = 85 at :74, not derived from the file, so a hand-edit of that constant still lets the extractor drop a key silently.
- [ ] Rename the six gratuitous workflow aliases onto their sources (`SES_FROM`, `REPO_CHANNEL`, `EFFORT_VAR`, `FORCE_FULL_CI`, `WATCHDOG_SKIP_RERUN`), consuming scripts included — 12 lines, table row D
- [x] Delete the `STRIPE_KEY_${SUFFIX}` fan-in at `cd-deploy-account.yml:334-337,341-342`; export `STRIPE_SECRET_KEY` directly, leaving the webhook loop intact
      AUDIT: DONE 2026-09-02 (audit): STRIPE_KEY_ survives only in past-tense comments (cd-deploy-account.yml:340,377; cd-deploy-worker.yml:217; resolve-account-deploy-config.sh:28; set-account-worker-secrets.sh:13). The webhook SUFFIX loop is intact at cd-deploy-account.yml:366 -> set-account-worker-secrets.sh:114-115.
- [ ] Write `.ci/config/name-role-substitutions.json` — one entry per homograph site in section 1.3, each naming source key, target key and reason
- [ ] Write `.ci/config/env-alias-forced.json` — the six externally-read env names only, each with its binary and a `file:line` where that binary is invoked
- [ ] Add assertion 9 (NO GRATUITOUS ALIAS) to `check_bws_map.py`, with the two planted defects and the silent control named in section 4
- [ ] Add assertion 10 (THE SCAFFOLD EXPIRES) to `check_bws_map.py`, sharing assertion 6's job index
- [ ] Add assertion 11 (THE HOMOGRAPH REGISTER DOES NOT ROT) to `check_bws_map.py`
- [ ] Rename `.env`'s `CF_EMAIL` / `CF_GLOBAL_API_KEY` onto the `CLOUDFLARE_` prefix (Q5)
- [ ] Mark the migration plan's Part 2 table historical and correct its Part 12 line numbers (finding 4)
- [ ] After steps 1-5 of section 3: delete the 62 compare steps and 197 `GH_*` env lines, and rewrite the 197 request lines to the bare identity form

---

## Correction 1 — "1-1" has two directions, and only one of them is aliasing

| | shape | what it is | how many | how it fails |
|---|---|---|---|---|
| **A** | one value, many names | ALIAS | 95 relations / 465 lines | you cannot find the consumers of a credential; a rename tool cannot see a name it cannot spell |
| **B** | one name, many values | HOMOGRAPH | 6 sites | a fetch-by-name helper signs production webhooks with the wrong key |

The operator saw A. B is the one that has already produced a live hazard, recorded in
the migration plan's Part 19: `STRIPE_WEBHOOK_SECRET` names the committed E2E fixture
constant in `private/account/.env`, the real production endpoint secret in Bitwarden,
and a per-region value in `cd-deploy-account.yml`. A naive "make everything 1-1" pass
**collapses names**, which is exactly how a homograph is created. Enumerating B is
therefore part of this design, not a footnote.

## Correction 2 — the four-namespace picture is out of date, and three of them are already 1-1

`agent/PLAN-secret-namespace-migration.md` Part 2 tabulates the Worker layer as a
separate namespace (`ACCOUNT_ED25519_PRIVATE_KEY` in GitHub, `ED25519_PRIVATE_KEY` in
the Worker). **That is history.** Decision 2's work landed. Measured now:

```
private/account/src/types/env.ts        85 declared keys
.ci/config/bws-secret-map.json          56 stored names
names present in BOTH                   21
of those 21, spelled differently         0
```

Same for the two other layers that used to disagree:

- `private/account/.env` — 49 keys, all on the post-rename canonical spellings. The
  10 GitHub-spelled exceptions Part 2 lists (`R2_ACCESS_KEY_ID`, `TURNSTILE_SECRET_KEY`,
  `CLAUDE_CODE_OAUTH_TOKEN`, …) no longer exist under those names.
- `run.sh`'s preview builder (`run.sh:1523-1537`) — 11 identity pairs, 2 deliberate
  role substitutions, 0 aliases.

**So the residual aliasing is not spread across four namespaces. It is concentrated in
one mechanism plus twenty-five lines**, and saying so is the difference between a week
of renaming and an afternoon.

---

## The alias inventory (Part 1)

### 1.1 The measurement, and how to re-run it

Three parsers, all already in the tree, so no number here depends on a hand count:

| what | parser | result |
|---|---|---|
| bws request lines and their aliases | `check_bws_map.py::parse_requests` over `check_bws_map.py::call_sites()` | 197 lines, **0 identity**, 197 renaming |
| workflow `env:` bindings | regex `^\s*(NAME)\s*:\s*\$\{\{\s*(secrets\|vars\|env)\.(SRC)\s*\}\}\s*$` over `.github/workflows/*.yml` + `.ci/breakpoint/workflow/*.yml` | 394 identity, 197 `GH_`-prefixed, 71 genuine crossings |
| Worker push keys vs schema | `scripts/check-worker-secret-names.ts::{pushedKeys,schemaKeys}` | 84 of 85 schema keys extracted — see finding 2 |

Scope note on the first row: a measurement over `.github/workflows/` alone gives **193**;
`check_bws_map.py::call_sites()` adds `.ci/breakpoint/workflow/breakpoint.yml` for
**197**. Both are right at their scope; 197 is the one used here, because it is the scope
the gate enforces.

### 1.2 The table

Value -> every name it wears -> layer -> FORCED (by what) or OURS.

| # | class | names it wears beside the canonical one | layer | lines | verdict |
|---|---|---|---|---|---|
| A1 | shadow request alias | `BWS_<NAME>`, for 35 distinct names | `secrets:` block of `./.github/actions/bws-secrets` | **197** | **SCAFFOLD** — forced *while the shadow runs*; the mechanism is temporary |
| A2 | shadow GitHub-side alias | `GH_<NAME>`, for the same 35 | `env:` of each "Compare shadow secrets" step | **197** | **SCAFFOLD** — same |
| B1 | external binary reads the name | `AWS_ACCESS_KEY_ID` (×7), `AWS_SECRET_ACCESS_KEY` (×7), `AWS_DEFAULT_REGION` (×3), `GH_TOKEN` (×1) | workflow `env:` feeding `aws` / `gh` | **18** | **FORCED** — `upload-repos-to-r2.sh:107-109` exports them immediately before `aws s3`; `cancel-older-runs.sh:48` refuses without `GH_TOKEN` |
| B1b | external binary, outside workflows | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` (wrangler auth), `BWS_ACCESS_TOKEN` (`bws`) | deploy scripts | n/a | **FORCED** — `deploy-account.sh:38-42`; `rotation/lib/credentials.ts:144-155` |
| B2 | third-party Action input key | `username` (×11), `password` (×11), `claude_code_oauth_token` (×3), `track_progress` (×1) | `with:` of a `uses:` step | **26** | **FORCED** — the key is fixed by the callee's own `action.yml` |
| B3 | build-framework prefix | `VITE_TURNSTILE_SITE_KEY` (×2) | build env | **2** | **FORCED** — Vite exposes only `VITE_`-prefixed vars to client code |
| B4 | Go linker symbol | `keys.ProductionPublicKey` | renet ldflags | 3 sites | **FORCED** — `go build -ldflags -X` takes a `package.Var` path; `keys.go:4-8` names `ACCOUNT_ED25519_PUBLIC_KEY` as the source |
| C1 | regional fan-in, built to be indirected | `STRIPE_KEY_EU`, `STRIPE_KEY_US`, `STRIPE_KEY_ASIA`, `STRIPE_SANDBOX_KEY` | `cd-deploy-account.yml:334-337`, read at `:341-342` via `key_var` | **4** | **OURS** — all three read the *same* `secrets.STRIPE_SECRET_KEY` |
| C2 | regional collapse EU -> unsuffixed | `AWS_SES_ACCESS_KEY_ID`, `AWS_SES_SECRET_ACCESS_KEY`, `AWS_SES_REGION` | `cd-deploy-worker.yml:224,227,228`; `ci.yml:1471-1473` | **6** | **OURS**, but see 1.4 — the *collapse* is correct, the *name* need not change |
| D | gratuitous rename | `SES_FROM`(×3), `REPO_CHANNEL`(×4), `SSH_USER`(×2), `EFFORT_VAR`, `FORCE_FULL_CI`, `WATCHDOG_SKIP_RERUN` | workflow `env:` | **12** | **OURS** — nothing outside this repo reads any of them |
| E | role substitution (**homograph**, not an alias) | see 1.3 | several | 6 sites | **OURS**, and deliberate |

Arithmetic that ties out: **18 + 26 + 2 = 46 FORCED** of the 71 genuine workflow
crossings; **12 + 6 + 4 = 22 OURS**; **3 homograph**. 46 + 22 + 3 = 71. ✓

Adding the scaffold: **70 alias relations FORCED-while-the-shadow-runs, 12 FORCED
outright, 13 OURS.**

### 1.3 The homograph register — every place one name holds a different value

| site | name | value it actually holds | why |
|---|---|---|---|
| `run.sh:1535` | `STRIPE_SECRET_KEY` (Worker) | `.env`'s `STRIPE_SANDBOX_SECRET_KEY` | a preview *is* a sandbox; `app.ts` reads the live key name for the ordinary billing path |
| `run.sh:1536` | `STRIPE_WEBHOOK_SECRET` (Worker) | `.env`'s `STRIPE_E2E_WEBHOOK_SECRET` | same, for webhook signing |
| `ci.yml:1468` | `STRIPE_SECRET_KEY` | `secrets.STRIPE_SANDBOX_SECRET_KEY` | CI does the identical substitution as the local builder |
| `autopilot.yml:990,1002` | `AUTOPILOT_ALLOW_PUSH` | `vars.AUTOPILOT_ALLOW_FINISH` | `finish.sh` gates writes on the PUSH flag; the finish STAGE is armed by the FINISH flag (S3 precedes S5) — documented at `:983-985` |
| `set-account-worker-secrets.sh:128-131` | `AWS_SES_ACCESS_KEY_ID`/`_SECRET_ACCESS_KEY` for ASIA | the EU pair | ap-northeast-1 production access not granted; `regions.json` already says `asia.sesRegion == "eu-central-1"` |
| the store | `STRIPE_WEBHOOK_SECRET`, `OBS_OTLP_CREDENTIALS` (unsuffixed) | one region's value, while the regional trio is authoritative | pre-regional leftovers, both exempted in `bws-unrequested.json` |

Five of the six are documented at the site. The sixth — the two unsuffixed store entries —
is documented only in the exemption file, which is why `STRIPE_WEBHOOK_SECRET` reads as a
single credential to anyone who looks at the map.

**These are not defects to be renamed away. They are decisions that must be REGISTERED,**
because the failure they invite is a future session "fixing the aliasing" by pointing
`STRIPE_SECRET_KEY` at the live key in a preview.

### 1.4 What is genuinely per-region, and what is a fiction

Collapsing a regional triple is only de-aliasing when the three values are one value.
Evidence, per family:

| family | three distinct values? | evidence | collapse verdict |
|---|---|---|---|
| `STRIPE_SECRET_KEY_{EU,US,ASIA}` | **NO — one value** | one Stripe account, `set-account-worker-secrets.sh:38-42`; the map holds a single `STRIPE_SECRET_KEY` with one UUID; `rotation-manifest.json` tracks no Stripe credential at all | collapse was **correct**, already done |
| `STRIPE_WEBHOOK_SECRET_{EU,US,ASIA}` | **YES** | three endpoints, three signing secrets, three distinct UUIDs in the map | must **stay** split |
| `AWS_SES_*_{EU,US}` | **YES** | `rotation-manifest.json` records different IAM users (`rediacc-ses-eu`, `rediacc-ses-us`) and different key ids | must **stay** split |
| `AWS_SES_*_ASIA` | **dead** | stored, read at `:123-126`, discarded at `:128-131`; the `ses-asia` manifest entry has an empty `consumers` list; not in the map, exempt as `superseded-at-runtime` | the *name* should go; see Q2 |
| `OBS_OTLP_CREDENTIALS_{EU,US,ASIA}` | **NO — one value, copied** | created 2026-09-02 by copying the unsuffixed value on the operator's instruction (one self-hosted collector, one login), Part 19 | genuinely three names for one value, but see Q6 |

C2's collapse (`AWS_SES_ACCESS_KEY_ID_EU` -> `AWS_SES_ACCESS_KEY_ID` for the www Worker
and CI) is **information-preserving**: www is a single global site with no regional
identity, so there is nothing to lose. It is an alias, not a collapse, and 1-1 does not
require removing it — the Worker binding genuinely is unsuffixed because the Worker
genuinely is one region. The name that would make it 1-1 (`AWS_SES_ACCESS_KEY_ID_EU` as
the Worker binding) would be a lie about the Worker.

---

## The 1-1 target state (Part 2)

### 2.1 The rule, in one sentence

> **A name may differ from the canonical store name only when something outside this
> repository reads it, or when the value differs. Everything else is a defect.**

Both halves are mechanically checkable, which is the point: the first is "is the alias
under a `with:` of a `uses:` step, or exported to a named external binary"; the second is
"is the site in the homograph register".

### 2.2 The `GH_`/`BWS_` prefixes — does a 1-1 world need them?

**No, and the mechanism already supports removing them.** `bws-secrets/action.yml:65-70`
accepts a bare `NAME` and sets `env_name="$name"`; today **zero** of the 197 request lines
use it.

But the elimination is not a rename, and getting this backwards destroys the only
evidence the migration has. While two sources exist, one shell must hold two different
values for one concept, so the two prefixes are **structurally forced by the comparator**.
They go away when the *left operand* goes away:

```
today          197 × "NAME > BWS_NAME"   +  197 × "GH_NAME: ${{ secrets.NAME }}"  +  62 compare steps
after cutover  197 × "NAME"              +    0                                   +   0
```

Net: **−394 alias lines, −197 lines of YAML, −62 steps, and 0 aliases in this class.**
It is the single largest de-aliasing available and it costs no new machinery.

`SHADOW_NAMES` (62 definitions, union = 197 words, e.g. `cd-deploy-worker.yml:110`)
disappears with the compare steps. It is a third copy of the same name list and needs no
separate treatment.

### 2.3 The OURS rows, and what changes in each layer

| row | target | change |
|---|---|---|
| A1/A2 scaffold | one name | delete the compare steps and their `GH_*` env blocks; rewrite 197 request lines to the bare form. **After** section 3 step 3, never before. |
| C1 Stripe fan-in | one name | `cd-deploy-account.yml`: delete `STRIPE_KEY_{EU,US,ASIA}` / `STRIPE_SANDBOX_KEY` (`:334-337`) and the `key_var="STRIPE_KEY_${SUFFIX}"` indirection (`:341-342`); export `STRIPE_SECRET_KEY` directly. Removes 4 names *and* one of the `${!VAR}` constructs assertion 7 exists to compensate for. |
| C2 SES collapse | **keep** | the Worker binding is unsuffixed because the Worker is unregional. Record it as a documented narrowing, not a defect. |
| D gratuitous | one name | rename the targets to their sources: `SES_FROM`->`AWS_SES_FROM`, `EFFORT_VAR`->`AUTOPILOT_EFFORT`, `FORCE_FULL_CI`->`FULL_CI`, `REPO_CHANNEL`->`PROMOTED`, `WATCHDOG_SKIP_RERUN`->`SKIP_RERUN`, and **delete** `SSH_USER: ${{ env.USER }}` (finding 1 — the line is inert). Each rename touches the consuming script too: `test-install-methods.sh` reads `REPO_CHANNEL`, `watchdog-monitor.cjs` reads `WATCHDOG_SKIP_RERUN`. |
| E homographs | **keep, register** | `.ci/config/name-role-substitutions.json`, one entry per site in 1.3, each naming source key, target key, and reason. |
| `.env` non-conformers | one name | `CF_EMAIL` -> `CLOUDFLARE_ACCOUNT_EMAIL`, `CF_GLOBAL_API_KEY` -> `CLOUDFLARE_GLOBAL_API_KEY`. Local-only, 2 names, no org secret. See Q5. |
| store leftovers | one meaning | delete the unsuffixed `STRIPE_WEBHOOK_SECRET` and `OBS_OTLP_CREDENTIALS` store entries once the regional trios are live. Operator-only; see Q6. |

### 2.4 What the FORCED rows get instead of a rename

Nothing is renamed. They get **derivability**, so a reader never has to ask whether an
alias is deliberate:

- B2 (action inputs) needs no register at all: the alias sits under `with:` of a `uses:`
  step, structurally distinguishable from an `env:` binding. Free and exact.
- B1/B1b (six env-name conventions) get a small `.ci/config/env-alias-forced.json`, each
  entry naming the external reader and a `file:line` where it is invoked. Re-derived, not
  believed: the entry is valid only while the step's `run:` (or the script it calls) still
  invokes that binary.
- B3/B4 (one each) go in the same file with their one-line reason.

---

## Migration order, and which steps are irreversible (Part 3)

The ordering constraint that matters: **the shadow is the only thing that proves the
Bitwarden copy equals the GitHub copy. Deleting it before it has run green on the NEW
names throws away the whole safety argument for the rename.** Steps 1-5 are therefore not
reorderable.

| # | step | who | reversible? |
|---|---|---|---|
| 0 | tree rename applied; dry run reports `0 replacements` | done (Part 19) | yes (git) |
| 1 | `gh secret set` the 20 new org-secret names — `scripts/dev/rename-org-secrets.sh`, 22 `set` lines, all commented out by design | **OPERATOR** | yes (a set is additive) |
| 2 | let one full CI run go green on the new names | — | yes |
| 3 | the shadow must report `match` for all 197 on the new names | — | yes |
| 4 | `npm run check:ci-secret-reachability -- --refresh` (org-admin token); this gate is RED today and correctly so | **OPERATOR** | yes (regenerate) |
| 5 | `gh secret delete` the 22 old names — the separate second block of the same script | **OPERATOR** | **NO. GitHub keeps no undo, and values are write-only, so nothing in this repo can restore one.** |
| 6 | cutover: consumers read the bws-injected env instead of `secrets.X` | — | yes, but re-wiring 62 jobs |
| 7 | delete the 62 compare steps + 197 `GH_*` lines; 197 request lines -> bare form | — | yes (git) |
| 8 | delete the two unsuffixed store leftovers (Q6) | **OPERATOR** | **NO in practice.** Probed live 2026-09-02 (Part 18): after `bws secret delete` the id 404s and vanishes from `list`, indistinguishable from a hard delete, and `bws` has no restore verb. Recovery is a human in the web UI within 30 days, if Trash works at all. |

Steps **6 and 7 are the deliverable of this design**; 1-5 are the migration plan's
existing operator half and are cited, not re-litigated.

**Independent of all of the above** — needing no cutover, no operator, and no org-secret
change, landable as one commit today: C1 (Stripe fan-in), D (6 gratuitous renames), the
homograph register, and the finding-2 gate fix. That is 22 alias lines and one latent
instrument defect, at zero migration risk. They are the first four boxes in `## Tasks`.

---

## What a gate would assert (Part 4)

Standing rule: **name the planted defect that must make the check RED, or do not propose
the check.** Each of the four below extends `check_bws_map.py`, which already walks every
call site, computes passthrough jobs, reads the rename table as data, and runs 11
self-test controls before any verdict.

### Assertion 9 — NO GRATUITOUS ALIAS

For every `NAME: ${{ (secrets|vars|env).SRC }}` line in a workflow, `NAME == SRC`, unless
one of: (a) `NAME == "GH_" + SRC` (scaffold — and assertion 10 makes that temporary);
(b) the binding is a `with:` key of a `uses:` step (action input, structurally forced);
(c) `NAME` has an entry in `.ci/config/env-alias-forced.json` whose named external binary
still appears in the step's `run:` or the script it calls; (d) the site is in
`.ci/config/name-role-substitutions.json`.

- **Planted defect (must RED):** add `SES_FROM_ADDRESS: ${{ vars.AWS_SES_FROM }}` to a
  step whose `run:` invokes no external binary. Must be reported with file, line, and BOTH
  names — Part 19's lesson is that a finding precise enough to act on is also a repair
  recipe.
- **Second planted defect (must RED):** take a valid `env-alias-forced.json` entry for
  `AWS_ACCESS_KEY_ID` and remove the `aws` invocation from the step it points at. A
  forced-ness claim that is no longer true must expire on its own.
- **CONTROL that must stay SILENT:** the 46 genuinely forced crossings, unchanged. A
  version of this check where "every fixture reds" would also pass, so the silent
  direction is the one that proves it.
- **Anti-vacuity:** a floor on lines scanned (today 859 = 394 + 197 + 197 + 71). An
  emptied glob must refuse, not pass.

### Assertion 10 — THE SCAFFOLD EXPIRES

Every `GH_<NAME>` env line must have a matching `<NAME> > BWS_<NAME>` request in the SAME
job, and `<NAME>` must be console-reachable in `secret-reachability.json`.

This is assertion 6's converse and can share its job index. Its real value arrives on the
day of step 5: when an old org secret is deleted, its `GH_` line goes red instead of the
comparator silently reporting `EMPTY` in one job nobody reads.

- **Planted defect A:** delete one `<NAME> > BWS_<NAME>` request while leaving its
  `GH_<NAME>` env line — the exact shape Part 19's 26-file accident produced.
- **Planted defect B:** remove one name from the reachability record; its `GH_` lines must
  red.

### Assertion 11 — THE HOMOGRAPH REGISTER DOES NOT ROT

Every site in `.ci/config/name-role-substitutions.json` must still be a substitution
(source key and target key both exist in their layers, and they differ), and every
substitution the scan finds must have an entry.

- **Planted defect A:** change `run.sh:1535` to `STRIPE_SECRET_KEY:STRIPE_SECRET_KEY`
  while leaving the register entry. A register that describes a substitution nobody makes
  any more is worse than none — it is the file a future reader will trust.
- **Planted defect B:** add a new `A:B` pair to `run.sh`'s `_required` with no entry.

### Assertion 12 — THE SCHEMA EXTRACTOR SEES EVERY KEY (a live bug; finding 2)

In `scripts/check-worker-secret-names.ts`, require
`schemaKeys(env.ts).size == |{ /^\s{2}[A-Z][A-Z0-9_]*:/ }|`, and derive the number in the
refusal message at `:104` instead of hardcoding `85`.

- **Planted defect:** wrap a second declaration across lines
  (`ACCOUNT_JWT_SECRET: z\n    .string()`). The gate must red rather than silently drop
  the key from the set it validates pushes against.
- Smallest of the four, and the only one fixing something already broken.

### Not asserted, deliberately

That an alias is *necessary*. Assertion 9 proves an alias is either structural or
declared-and-re-derived; it cannot prove a human's judgement was right. That is what the
`reason` fields are for, and they are read by people.

---

## Findings this measurement produced (Part 5)

**1. `ct-tests.yml:1774,1787` bind `SSH_USER: ${{ env.USER }}`, and `env.USER` is always
empty.** The GitHub `env` context holds only what a workflow, job, or step `env:` key
sets — not the runner's process environment — and no `USER:` env key exists anywhere in
that file (`grep -nE '^\s*USER:' .github/workflows/ct-tests.yml` -> no match). So
`SSH_USER` is exported as `""`. It is harmless **by luck**: both consumers use
`SSH_USER="${SSH_USER:-${USER:-$(whoami)}}"`
(`concurrent-fork-isolation-test.sh:37`, `compose-healthcheck-smoke-test.sh:39`), and `:-`
treats empty as unset. Change either default to `${SSH_USER-...}` and every SSH target
becomes `@$VM_IP` with no user. The line does nothing and should be deleted.
*This is the ask's thesis in miniature: the alias is what hides the fact that the source
does not exist.*

**2. `check:ci-worker-secret-names` extracts 84 of `env.ts`'s 85 keys.** Its `SCHEMA_KEY`
regex (`scripts/check-worker-secret-names.ts:69`) requires `z.` on the same line as the
key; `MIN_CLI_VERSION` is wrapped by the formatter across `env.ts:56-59`, so the gate
never sees it. Proven by running the gate's own regex: 84 matched, 85 two-space keys
present, `missed: ['MIN_CLI_VERSION']`. The floor check (`schema.size < 40`) cannot catch
a one-key loss, and the file's own header says "85 keys" in three places (`:15,:21,:104`)
while the code yields 84.

Direction of the failure, stated precisely: it is a **false positive**, not a silent hole.
No builder pushes `MIN_CLI_VERSION` today (`grep` across all five builders: no match), but
the day one does, the gate reports "pushes a key `env.ts` does not declare" about a key
`env.ts` declares — and the natural repair is to delete a correct push line. Assertion 12.

**3. `PROMOTED` and `SKIP_RERUN` are legitimate** and were checked rather than assumed:
`simulate-promotion.sh:55` and `check-rerun-attempt.sh:46` both append to `$GITHUB_ENV`.
They are still gratuitous renames (row D), just not broken ones.

**4. Corrections to the migration plan's Part 12 and Part 2, for whoever reads them next:**

- Part 2's Worker-vs-GitHub alias table is **fully resolved**; 0 of the 21 shared names
  disagree. It should be marked historical rather than left as a description of today.
- `cd-deploy-account.yml:387` is `AWS_SES_SECRET_ACCESS_KEY_ASIA`, not a Stripe line, and
  **no secret named `STRIPE_SECRET_KEY_EU` exists anywhere in the tree** any more. The
  one-Stripe-account collapse lives at `:334-336,341-342,407`.
- The runtime-constructed names are **four** templates in `set-account-worker-secrets.sh`
  (`:114,:123,:125,:134`) plus **one** in `cd-deploy-account.yml:341`; Part 12's "six
  `${!VAR}` indirections at `:83-102`" is stale on both count and line numbers.

---

## The rows I cannot decide (Part 6)

Each carries a recommendation, and each recommendation is what should execute if the
question goes unanswered.

**Q1. Does the cutover ever happen, or does the shadow live forever?**
394 of the 465 alias lines exist only as scaffolding for a cutover that has executed zero
times. If the answer is "not soon", the honest move is to say so here rather than carry
the largest alias class as if it were about to vanish.
*RECOMMEND: cut over.* It is the single largest de-aliasing available, the machinery is
built and gated, and steps 1-5 are already the migration plan's operator half.

**Q2. `AWS_SES_*_ASIA`: keep the dead org secrets and the runtime substitution, or make
the substitution a region property?**
Today two org secrets exist, are read at `set-account-worker-secrets.sh:123-126`, are
discarded at `:128-131`, and cost two `superseded-at-runtime` exemptions plus a
special-cased gate `kind`.
*RECOMMEND: add `sesCredentialRegion: "eu"` to `regions.json`'s asia entry* (which already
carries `sesRegion: "eu-central-1"`), read it in the deploy script, and delete both ASIA
names. Removes 2 dead names, 1 invisible substitution, and 2 exemptions at once, and turns
a fact that today exists only inside an `if` into committed data. Operator-only for the
`gh secret delete` half.

**Q3. Delete the `STRIPE_KEY_${SUFFIX}` fan-in?**
All three names already read one secret (`cd-deploy-account.yml:334-336`).
*RECOMMEND: yes* — export `STRIPE_SECRET_KEY` directly and drop `:341-342`. One caveat to
verify before cutting: the `SUFFIX` loop still legitimately drives
`STRIPE_WEBHOOK_SECRET_${SUFFIX}`, so the loop stays; only the Stripe *key* leaves it.

**Q4. `BWS_ACCESS_TOKEN` versus Part 10's `BITWARDEN_SM_ACCESS_TOKEN`.**
*RECOMMEND: `BWS_ACCESS_TOKEN` stays* — `bws` reads that exact name from its own
environment (`rotation/lib/credentials.ts:144-155`), so it is FORCED. **Delete the
`BITWARDEN_SM_ACCESS_TOKEN` row from Part 10's table**, so the two names stop coexisting
on paper. This re-affirms Part 12's stated default; the new part is deleting the losing
row rather than leaving it as a second spelling.

**Q5. `.env`'s `CF_EMAIL` / `CF_GLOBAL_API_KEY`.**
Two names, local-only, no org secret, no Bitwarden entry, and the only two `.env` keys
still off the provider-prefix convention.
*RECOMMEND: rename to `CLOUDFLARE_ACCOUNT_EMAIL` / `CLOUDFLARE_GLOBAL_API_KEY`* in the
same pass as row D. Cheap. Note `.env` is untracked, so `secret-rename.py:269`'s
`.pre-rename.bak` protection is what makes this safe.

**Q6. Delete the unsuffixed `STRIPE_WEBHOOK_SECRET` and `OBS_OTLP_CREDENTIALS` store
entries?**
These are the homograph inside the store itself: one name holding one region's value while
the regional trio is authoritative. Keeping them is precisely what makes
`STRIPE_WEBHOOK_SECRET` mean three different things across three layers.
*RECOMMEND: delete, but only after the regional trio has deployed green at least once*,
and accept that the deletion is effectively irreversible (Part 18's live probe). Note the
complication: `OBS_OTLP_CREDENTIALS` is *also* a live `env.ts` key (one of the 21-name
overlap) and a live `.env` key, so the store entry and the Worker binding share a name
legitimately. Only the **store's regional ambiguity** is the problem. Operator-only.

**Q7. Register the 46 FORCED crossings, or detect them structurally?**
*RECOMMEND: both, split by shape.* Action inputs (26 of 46) are detectable for free from
`with:` versus `env:` and need no file. The six env-name conventions (18 lines) need a
register, because "the `aws` binary reads this" is not inferable from the YAML alone. A
register of 6 entries is auditable; a register of 46 is a second name table, which is the
exact defect assertion 8 exists to find.

---

## Remaining (operator)

- `[?]` Q1, Q2, Q6 — each needs a ruling or an operator-only action (`gh secret delete`,
  `bws secret delete`). The defaults above execute if unanswered.
- Steps 1, 4 and 5 of the migration order remain the migration plan's operator half;
  nothing here changes them.
