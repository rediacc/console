Status: draft
Owner: 74de73ca
Measured: 2026-09-02, against the working tree (uncommitted) and the live GitHub org.
Every count below was produced by a parser over the real files or by `gh api`, not by reading.

> **The tree is being edited by another session while this was written.**
> `.github/workflows/cd-deploy-worker.yml` (22:55:45) and
> `.github/workflows/cleanup-r2-staging.yml` (22:56:30) both changed mid-analysis; two
> independent scans nine minutes apart disagree on their line numbers by a few lines.
> The aggregates and the shapes hold; re-derive `file:line` in those two files before
> editing them, and expect a merge.

# Delete the GitHub secrets: what goes, what cannot, and the order

## Headline

**The ask is achievable, with exactly one survivor.** `BWS_ACCESS_TOKEN` must stay a GitHub
secret in three repositories (`console`, `account`, `renet`). It is the only credential
read before anything can be fetched, and I verified there is no second one: a PyYAML parse
of all 28 workflows plus `.ci/breakpoint/workflow/breakpoint.yml` finds **zero** secret
reads at `env:` (workflow or job level), **zero** in any `if:`, and **zero** `secrets:
inherit`. Every one of the 669 secret bindings in the tree is either a step-level `env:`/
`with:` (fetchable) or a `jobs.<id>.secrets:` passthrough into a reusable workflow (which
collapses to `BWS_ACCESS_TOKEN` alone). Method in §1.

**Three things in the framing do not survive contact with the evidence.**

1. **The Bitwarden layer has never run.** `git cat-file -e HEAD:.github/actions/bws-secrets/action.yml`
   returns *"exists on disk, but not in 'HEAD'"*, and `git grep -c "Compare shadow secrets" HEAD`
   matches nothing. The action, all 63 fetch steps, all 63 compare steps and
   `.ci/config/bws-secret-map.json` exist **only in the uncommitted working tree**. Not one
   shadow comparison has ever executed in CI. So this is not "delete the GitHub secrets now
   that Bitwarden is proven" — nothing is proven yet, and the proof is already written and
   costs one CI run.

2. **The rename is pure waste, and the current tree is a live foot-gun.** The 22-secret
   rename exists only to make this tree's `secrets.<NEW_NAME>` reads resolve. If those reads
   are deleted in the same commit that adds the fetch — which is what "remove GitHub secrets"
   means — no `secrets.<NEW_NAME>` read ever exists and the operator never has to locate 11
   operator-only values. Verdict and the one reduced piece that IS needed: §2.

3. **Three secrets cannot leave GitHub yet, and one class should be deleted rather than
   migrated.** `OTLP_CLIENT_CREDENTIALS_{EU,US,ASIA}` are mapped but their Bitwarden values
   have never been written (`.ci/config/bws-unrequested.json:198-216`, kind `deferred`, "the
   value is readable nowhere"); only `./run.sh rotation rotate otlp-{eu,us,asia}` can create
   them, and that is operator work on the critical path. Separately
   `AWS_SES_{ACCESS_KEY_ID,SECRET_ACCESS_KEY}_ASIA` are read 4× each and then discarded at
   `.ci/scripts/deploy/set-account-worker-secrets.sh:127-131`; they should be deleted, not
   migrated. §3, rows O3 and O4.

---

## 1. The irreducible set

### 1.1 Method

`jobs.<job_id>.env`, `jobs.<job_id>.if` and `jobs.<job_id>.secrets.<secrets_id>` are the
three places a `secrets.X` read is structurally un-fetchable, because a value written to
`$GITHUB_ENV` by a step cannot reach them. GitHub's own context-availability table is the
authority (docs.github.com, *"Contexts"*, "Context availability"), and it lists for each:

| expression location | contexts allowed | `env` present? |
|---|---|---|
| `jobs.<job_id>.env` | `github, needs, strategy, matrix, vars, secrets, inputs` | **no** |
| `jobs.<job_id>.if` | `github, needs, vars, inputs` | **no** |
| `jobs.<job_id>.secrets.<secrets_id>` | `github, needs, strategy, matrix, secrets, inputs, vars` | **no** |
| `jobs.<job_id>.steps[*].with` | `github, needs, strategy, matrix, job, runner, **env**, vars, secrets, steps, inputs` | **yes** |
| `jobs.<job_id>.steps[*].env` | same as above | **yes** |
| `jobs.<job_id>.steps[*].if` | `… **env**, vars, steps, inputs` | **yes** |

and the workflow-commands page fixes the propagation rule: *"The step that creates or
updates the environment variable does not have access to the new value, but all subsequent
steps in a job will have access."* So a fetch step at position *k* covers every consumer at
position > *k* in the same job, and nothing else.

I enumerated the un-fetchable positions by parsing every workflow with PyYAML and walking
`env`, `jobs.*.env`, `jobs.*.if`, `jobs.*.strategy`, `jobs.*.container`, `jobs.*.services`,
`jobs.*.environment` and every `steps[*].if` for the substring `secrets.`:

    PRE-STEP / non-step secret reads found: 0

A second, independent PyYAML `compose`-based scan (node positions, run separately) reached
the same verdict from the other direction and classified all 664 reads: **0** at workflow or
job-level `env:`, **0** in any job with no `bws-secrets` step, **0** `if:` gates, **7** in a
step preceding the fetch (all `GITHUB_APP_PRIVATE_KEY` → `app-token`, §4.2 Trap A), **171**
in `jobs.<id>.secrets:` passthroughs, **62** the fetch's own `access-token:`, and **424**
after the fetch. Two scans, two parsers, same seven.

A `grep -rn "if:.*secrets\."` over `.github/workflows/` and `.ci/breakpoint/workflow/`
returns nothing, and `grep -rn "secrets: inherit"` returns nothing here or in either
submodule. There is no environment-scoped secret to worry about either: all 30 GitHub
environments (`edge`, `stable`, `edge-{eu,us,asia}`, 25 `pr-*`) return an empty
`/environments/<name>/secrets` list, and `orgs/rediacc/dependabot/secrets` is empty.

### 1.2 The survivor, and why nothing else joins it

| # | name | why it must stay | evidence |
|---|---|---|---|
| 1 | `BWS_ACCESS_TOKEN` | It is the argument to the fetch. It is read at `with: access-token:` on the `bws-secrets` step (62 sites) and at `jobs.<id>.secrets:` when passed into a reusable workflow (14 sites). The `with:` sites could in principle read `env`, but there is nothing to read it *from*; the `jobs.<id>.secrets:` sites cannot read `env` at all. No `bws` verb mints or rotates a machine-account token, so it cannot be self-hosting. | `.github/actions/bws-secrets/action.yml:26-30` states the contract; 62 `access-token:` sites, e.g. `.github/workflows/cd-deploy-worker.yml:89`, `.github/workflows/cd-deploy-account.yml:224`; 14 passthrough sites, e.g. `.github/workflows/cd-v2.yml:459,489,542,575` |

Two near-misses that are **not** additional roots:

- **`GITHUB_APP_PRIVATE_KEY`, read at 51 `private-key:` sites.** GitHub-minted `GITHUB_TOKEN`
  is too weak for private-submodule checkouts, so the App token is fetched first in 7 of the
  51 jobs — but `steps[*].with` accepts the `env` context, so the fix is to move the
  `bws-secrets` step ahead of `./.github/actions/app-token` in those 7 jobs. 44 of 51 already
  have the right order. Exact list and the one trap in §4.2.
- **`GITHUB_TOKEN` / `github.token`.** Minted per-run by GitHub; never stored, never
  deletable, never in scope. `check_bws_map.py:155` already excludes it via
  `NOT_SHADOWED`. Exactly two `secrets.GITHUB_TOKEN` sites —
  `.github/workflows/ci-quality.yml:838` (`GH_TOKEN:`, the `gh` CLI convention; note it
  *looks* like a shadow line and is not) and `.github/workflows/ci.yml:1180` — against 66
  live `${{ github.token }}` sites, which are the same token by another spelling.

### 1.3 The fate of all 48 stored secrets

45 org secrets (`gh api orgs/rediacc/actions/secrets`) + 3 console repo secrets
(`BREAKPOINT_TUNNEL_TOKEN`, `BWS_ACCESS_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`) + 2 each in
`account` and `renet` (`BWS_ACCESS_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`).

| fate | count | names |
|---|---|---|
| **Deletable — a workflow requests the Bitwarden twin** | 37 | 36 org + `BREAKPOINT_TUNNEL_TOKEN` (repo). Includes the 17 that carry a rename pre-image: `APP_PRIVATE_KEY`, `AUTOPILOT_PRIVATE_KEY`, `BACKUP_S3_{ACCESS_KEY_ID,ENDPOINT,SECRET_ACCESS_KEY}`, `CLAUDE_CODE_OAUTH_TOKEN`, `GPG_{PASSPHRASE,PRIVATE_KEY}`, `R2_{ACCESS_KEY_ID,ENDPOINT,SECRET_ACCESS_KEY}`, `R2_MEDIA_{ACCESS_KEY_ID,ENDPOINT,SECRET_ACCESS_KEY}`, `STRIPE_SECRET_KEY_{EU,US,ASIA}`→one, `TURNSTILE_SECRET_KEY`, `BREAKPOINT_TUNNEL_TOKEN` |
| **Deletable — dead, zero workflow reads** | 4 | `BACKUP_S3_BUCKET` (derived from `regions.json` since 2026-09-02), `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` (the SMTP set is customer-supplied on the onprem image; `.ci/config/bws-unrequested.json:88-104`) |
| **Deletable — read but discarded** | 2 | `AWS_SES_ACCESS_KEY_ID_ASIA`, `AWS_SES_SECRET_ACCESS_KEY_ASIA` (§3 row O4) |
| **BLOCKED on an operator rotation** | 3 | `OTLP_CLIENT_CREDENTIALS_{EU,US,ASIA}` (§3 row O3) |
| **Stays** | 1 (×3 repos) | `BWS_ACCESS_TOKEN` |

Total: 37 + 4 + 2 + 3 + 1 = 47 org/console rows, plus the two submodule `CLAUDE_CODE_OAUTH_TOKEN`
copies which go with §6. **44 of 48 are deletable in the cutover commit's wake; 3 wait on a
rotation; 1 stays.**

---

## 2. Rename-first: **skip it.** Do the reduced version instead.

### 2.1 Why the rename exists at all

`scripts/dev/rename-org-secrets.sh` is a commented-out checklist that renames 22 org secrets
into 20 names (`:24`), generated by intersecting `scripts/dev/secret-rename.py`'s 25-pair
`RENAMES` table with the console-reachable list. It exists for one reason: the **working
tree already spells every read with the new name**. Push this tree without the rename and 102
of the 197 `GH_<NAME>: ${{ secrets.<NAME> }}` shadow lines, plus every consuming
`secrets.<NEW>` read, resolve to `""` — *"If a secret has not been set, the return value of
an expression referencing the secret … will be an empty string"* (docs.github.com,
*"Use secrets in GitHub Actions"*).

The rename costs the operator 22 `gh secret set` calls, and **11 of the values are
operator-only** (`agent/PLAN-secret-namespace-migration.md:243-252`: 4 Stripe, 3
`BACKUP_S3_*`, `ANTHROPIC_API_KEY`, `DOCKERHUB_USERNAME`, 2 GPG).

### 2.2 The verdict

**Do not rename. The rename buys exactly one thing — a shadow whose left operand resolves —
and there is a cheaper way to buy it.** The comparator's left operand is a *GitHub* read;
nothing requires it to use the *new* spelling. Point it at the pre-image instead:

```yaml
# today (needs the org secret renamed first)
GH_CLOUDFLARE_R2_ACCESS_KEY_ID: ${{ secrets.CLOUDFLARE_R2_ACCESS_KEY_ID }}
# instead (works against the org as it stands today)
GH_CLOUDFLARE_R2_ACCESS_KEY_ID: ${{ secrets.R2_ACCESS_KEY_ID }}
```

**102 of the 197 GH_ lines need this rewrite; 95 already name a conforming secret.** The
rewrite is mechanical and generated from `secret-rename.py`'s `RENAMES` table, not typed. The
per-name counts, which are also the blast radius:

| Bitwarden name | pre-image to read on the GH side | GH_ lines |
|---|---|---|
| `GITHUB_APP_PRIVATE_KEY` | `APP_PRIVATE_KEY` | 48 |
| `CLOUDFLARE_R2_{ACCESS_KEY_ID,ENDPOINT,SECRET_ACCESS_KEY}` | `R2_*` | 10 each |
| `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` | `CLAUDE_CODE_OAUTH_TOKEN` | 4 |
| `GITHUB_AUTOPILOT_PRIVATE_KEY` | `AUTOPILOT_PRIVATE_KEY` | 4 |
| `CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN` | `BREAKPOINT_TUNNEL_TOKEN` | 3 |
| `STRIPE_SECRET_KEY` | `STRIPE_SECRET_KEY_{EU,US,ASIA}` — **three pre-images, see below** | 3 |
| `CLOUDFLARE_TURNSTILE_SECRET_KEY` | `TURNSTILE_SECRET_KEY` | 2 |
| `ACCOUNT_BACKUP_S3_*` (3), `RELEASE_GPG_*` (2), `CLOUDFLARE_R2_MEDIA_*` (3) | as tabled in `rename-org-secrets.sh:26-67` | 1 each |

The Stripe row is the one that is not a substitution but a **test**: the collapse asserts
one Stripe account serves all three regions
(`agent/PLAN-secret-namespace-migration.md:1085`). Shadowing `STRIPE_SECRET_KEY` against all
three pre-images turns that assertion into a measurement. If they differ, the shadow says so
before a deploy does.

### 2.3 What the operator should be told

- **Skip** all 22 `gh secret set` lines in `scripts/dev/rename-org-secrets.sh:26-67`.
- **Skip** the 22 `gh secret delete` lines at `:69-91` too — they delete the *pre-images*,
  which are exactly the values the one-run shadow needs. They are superseded by the bulk
  deletion in §4 step 6, which removes 44 secrets rather than 22.
- **Do** run the `check:ci-secret-reachability --refresh` afterwards (§8), for the opposite
  reason it was originally needed: to record that the org list is now nearly empty.
- The one thing the rename would still have bought — the two submodule repos' own
  `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` — is **also** obviated, by §6.

Net saving: 22 credential handlings, 11 of which require the operator to go find a value that
`gh` cannot read back.

---

## 3. The rows that cannot go, and the two that should go a different way

| id | rows | verdict | evidence |
|---|---|---|---|
| **O1** | `BWS_ACCESS_TOKEN` × 3 repos | **stays forever.** Rotate by hand; `.ci/config/bws-token-expiry.json` + `scripts/dev/bws-map-refresh.py:56-115` already fingerprints the client-id so a swapped token cannot hide behind a stale date. | §1.2 |
| **O2** | `GITHUB_TOKEN` | never a stored secret | `.github/workflows/ci-quality.yml:838` |
| **O3** | `OTLP_CLIENT_CREDENTIALS_{EU,US,ASIA}` | **blocked.** The Bitwarden names `OBS_OTLP_CREDENTIALS_{EU,US,ASIA}` are in the map with UUIDs, but the exemption records them as REAL GAPS whose values do not exist. They reach the Worker through a runtime-built name (`otlp_var="OBS_OTLP_CREDENTIALS_${SUFFIX}"`) and are hard-guarded. Deleting the GitHub secrets before `./run.sh rotation rotate otlp-{eu,us,asia}` runs fails every regional deploy — loudly, which is the good failure, but it fails. | `.ci/config/bws-unrequested.json:198-216`; `.ci/scripts/deploy/set-account-worker-secrets.sh:133-135` and the `_require_nonempty OBS_OTLP_CREDENTIALS` at `:209` |
| **O4** | `AWS_SES_{ACCESS_KEY_ID,SECRET_ACCESS_KEY}_ASIA` | **delete the reads, then the secrets — do not migrate.** The value is read and then unconditionally overwritten with the EU pair. It is passed through 3 `jobs.<id>.secrets:` lines and declared in `cd-deploy-account.yml`'s `workflow_call` block for nothing. | `.ci/scripts/deploy/set-account-worker-secrets.sh:127-131`; `.ci/config/bws-unrequested.json:218-226` (operator ruling 2026-09-02: do not mint an ASIA IAM key) |
| **O5** | `BACKUP_S3_BUCKET`, `SMTP_{HOST,USER,PASS}` | **delete outright.** Zero `secrets.X` reads anywhere in `.github/workflows/`. | measured: `grep -c "secrets.BACKUP_S3_BUCKET"` etc. = 0 |

---

## 4. The cutover

### 4.1 What each of the 669 binding sites becomes

Classified by YAML parent key across all 22 caller files:

| shape | count | becomes | why |
|---|---|---|---|
| `GH_<N>: ${{ secrets.<N> }}` under a compare step's `env:` | **197** | rewritten to the pre-image for 102 of them (§2.2); **all 197 deleted** at the end of the soak | the shadow's left operand |
| `<N>: ${{ secrets.<N> }}` under a step's `env:` (identity) | **137** | **deleted outright** — the fetch already exported `<N>` into `$GITHUB_ENV` at job scope | e.g. `cd-deploy-worker.yml:218` |
| `<alias>: ${{ secrets.<N> }}` under a step's `with:` | **140** | 62 `access-token:` sites keep `${{ secrets.BWS_ACCESS_TOKEN }}`; the other **78 become `${{ env.<N> }}`** (51 `private-key:`, 20 dockerhub `username:`/`password:`, 3 `claude_code_oauth_token:`, 4 other) | `steps[*].with` allows the `env` context |
| `<alias>: ${{ secrets.<N> }}` under a step's `env:` | **24** | **`${{ env.<N> }}`** — e.g. `AWS_ACCESS_KEY_ID: ${{ env.CLOUDFLARE_R2_ACCESS_KEY_ID }}`, `STRIPE_KEY_EU: ${{ env.STRIPE_SECRET_KEY }}` | `cd-deploy-account.yml:332-335`; `ci.yml`, `promote-stable.yml`, `cleanup-r2-staging.yml` R2/AWS aliases |
| `<N>: ${{ secrets.<N> }}` under `jobs.<id>.secrets:` (passthrough) | **171** | **157 deleted; 14 `BWS_ACCESS_TOKEN` lines stay.** `jobs.<id>.secrets` cannot read `env`, so the callee must fetch for itself — which it already does. | 88 in `cd-v2.yml`, 44 in `promote-stable.yml`, 37 in `ci.yml`, 2 in `claude-review.yml` |
| `on.workflow_call.secrets:` declarations | **80** across 9 reusable workflows | **each collapses to 1 (`BWS_ACCESS_TOKEN`)**, i.e. 80 → 9 | `cd-deploy-account.yml` 28, `cd-deploy-worker.yml` 16, `cd-v2.yml` 16, `promote-stable.yml`* 16, `ct-tests.yml` 11, `cd-stage.yml` 7, `ci-quality.yml` 6, `ci-ops-test.yml` 4, `ci-build-{docker,renet}.yml` 3 each, `claude-review-reusable.yml` 2 |
| `secrets: |` request lines `<N> > BWS_<N>` | **197** | **`<N>`** — the bare identity form the action already supports and zero lines use today | `.github/actions/bws-secrets/action.yml:65-70`; `agent/PLAN-secret-names-one-to-one.md:176-178` |
| `Compare shadow secrets against GitHub` steps | **63** | deleted at the end of the soak, with their `SHADOW_NAMES:` lines | §5 |

\* `promote-stable.yml`'s 16 are a `jobs.<id>.secrets:` passthrough that my declaration
scanner cannot distinguish from a `workflow_call` block by indentation alone (both sit at
4 spaces). Verify per file before editing; the aggregate is unaffected.

Net: roughly **−1,000 lines of YAML** and **−63 steps**, adding no new machinery.

### 4.2 The two mechanical traps

**Trap A — 7 jobs run `app-token` before `bws-secrets`.** (Line numbers below anchor on the
`uses:` line of each step, not the `- name:` line; a second scan anchoring on `- name:`
reports each 2-4 lines earlier. Same seven jobs either way.) Computed by walking step order per
job: 44 jobs already have `bws-secrets` first, 7 do not, 0 jobs use `app-token` without a
`bws-secrets` step:

| file | job | app-token | bws-secrets |
|---|---|---|---|
| `.github/workflows/backfill-release-sentinel.yml` | `backfill` | :74 | :93 |
| `.github/workflows/cd-deploy-account.yml` | `build` | :113 | :129 |
| `.github/workflows/cd-deploy-account.yml` | `deploy` | :206 | :222 |
| `.github/workflows/cd-deploy-worker.yml` | `deploy` | :71 | :87 |
| `.github/workflows/ci-build-docker.yml` | `build-server-docker-amd64` | :197 | :211 |
| `.github/workflows/ci-build-docker.yml` | `build-server-docker-arm64` | :310 | :324 |
| `.github/workflows/ci-build-docker.yml` | `build-renet-docker` | :536 | :550 |

**Trap B — two of those seven start with a sparse checkout that excludes the map.**
`bws-secrets` resolves the map at `${{ github.action_path }}/../../../.ci/config/bws-secret-map.json`
(`.github/actions/bws-secrets/action.yml:57`) and hard-fails if it is absent (`:59`). Two
jobs check out only `.github/actions` first, precisely so the local `app-token` action
resolves:

- `.github/workflows/backfill-release-sentinel.yml:70` — `sparse-checkout: .github/actions`
- `.github/workflows/cd-deploy-account.yml:204` — `sparse-checkout: .github/actions`

Moving `bws-secrets` ahead of `app-token` in those two **requires adding `.ci/config` to the
sparse list**. The other five have a full first checkout (verified: `cd-deploy-account.yml:109`,
`cd-deploy-worker.yml:67`, `ci-build-docker.yml:196,309,535`). Getting this wrong is a loud
failure (`::error::bws-secret-map.json not found`), not a silent one — which is the only
reason it is a trap and not a risk.

### 4.3 The order, and the detection/reversal at each step

The safety argument is one sentence: **the compare step is placed between the fetch and every
consumer in the same job, and it fails the job on any mismatch or on either side being empty
— so during the soak it is a precondition, not an observer.** That is a strict improvement on
today's design, where nothing consumes the comparison at all.

| step | what | detect | reverse |
|---|---|---|---|
| **0. Preflight (operator, before any commit)** | For all 56 map UUIDs, assert `bws secret get <id>` returns a non-empty value **without printing it** — e.g. `bws secret get "$id" -o json \| jq -r '.value \| length'` and assert > 0. `check_bws_map.py:22-30` explicitly declines to do this (it would need a token and would degrade to "passed" where absent), so it is a manual gate. This is where `OBS_OTLP_CREDENTIALS_*` shows up as zero-length if row O3 is still open. | a length of 0 for any name a workflow requests | nothing committed yet |
| **1. Land the shadow, left operand on the pre-images** (§2.2), consumers untouched | one full CI run on a PR. Every one of the 63 compare steps must print `shadow <N> match` for each of its names. `.ci/scripts/quality/check_bws_map.py` must be green. | any `MISMATCH` or `EMPTY` line fails its job | revert the commit; nothing outside CI has changed |
| **2. Flip the consumers** (§4.1 rows 2-6), keeping the compare steps | the same run: consumers now read `$GITHUB_ENV`, and the compare step in front of them still proves equality. `.ci/scripts/deploy/set-*-worker-secrets.sh`'s `_require_nonempty` block (`:198-213`) is the second net. | a job fails at the compare step before any consumer runs | revert; the org secrets are all still present and still hold the pre-image names |
| **3. Soak** | one full cycle that actually exercises the rare paths: Console CI on `main`, CD edge deploy, one `Release to Production` (`promote-stable.yml`) and one `housekeeping.yml`/`autopilot.yml`/`breakpoint.yml` run. `ct-tests.yml` (14 fetch steps, 41 request lines) and `cd-v2.yml` are the two heaviest and must both be seen green. | as step 2 | as step 2 |
| **4. Delete the shadow** (§5) | CI green with the fetch as the sole source | revert restores the compare steps; the org secrets still exist |
| **5. Cross-repo** (§6) | one PR opened in each of `account` and `renet`, Claude Review posts | re-add `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.… }}` to the two callers |
| **6. Delete the GitHub secrets** (operator, irreversible) | **after** steps 1-5 are green and O3 is closed | **see §7** |

Steps 1 and 2 can be one commit — and probably should be, because a tree that has flipped the
consumers but not the shadow, or vice versa, is a tree where the names disagree. The
distinction that matters is not "two commits" but "the compare step precedes every consumer
in its own job", which is already true of all 63 sites.

Step 6 must not be split into "delete a few and watch". `gh secret delete` is irreversible
and the blast radius of a wrong guess is identical whether you delete 1 or 44. The soak is
the safety, not the batch size.

---

## 5. The shadow machinery after the cutover

Once `secrets.<N>` no longer appears for any `<N>` but `BWS_ACCESS_TOKEN`, the comparator has
no left operand and every part of it is dead:

- **63 compare steps + 63 `SHADOW_NAMES:` lines** — delete. `SHADOW_NAMES` is a third copy of
  each job's name list (the other two being the request lines and the `GH_` lines), so drift
  between the three is invisible to the comparator itself; deleting it removes a copy.
- **197 `GH_<N>` env lines** — delete.
- **The `BWS_` prefix on 197 request lines** — delete, leaving the bare identity form. The
  action has supported it since it was written (`action.yml:65-70`) and zero lines use it.
- **`.github/actions/bws-secrets/action.yml`** — keep, unchanged. Its docstring at `:14-24`
  needs one edit: the sentence "The live `secrets.*` reads below are untouched until the
  cutover flips them", repeated at all 63 call sites, becomes false.

### 5.1 The assertions that are phrased in GitHub terms

`.ci/scripts/quality/check_bws_map.py` (807 lines) has four assertions whose subject is a
GitHub secret. Each needs a decision, not a deletion by default.

| assertion | phrased in | after cutover | replacement |
|---|---|---|---|
| **1** (`:756-759`) every requested NAME is in the map | Bitwarden | **unchanged, and now the load-bearing one** | — |
| **2** (`:760-761`) every env name is a legal identifier | neither | unchanged | — |
| **3** (`:715-726`) map freshness ≤ 45 days | Bitwarden | unchanged | — |
| **4** (`:706-713`) map non-vacuity, `MIN_MAP_ENTRIES=30` | Bitwarden | unchanged | — |
| **5** COVERAGE (`:476-491`) | **hybrid** — a `no-github-twin` exemption is re-derived by asking whether the name or a rename pre-image "IS a console-reachable org secret" (`:484-489`) | **dies.** With no org secrets, every name is a `no-github-twin` and the exemption becomes unfalsifiable — which is the shape the file's own header warns about. | **Retire the `no-github-twin` kind entirely.** Replace with `unrequested`, re-derived the other way: the name must appear in the tree (assertion 8 already proves that) **and** must not be constructible by assertion 7's SUFFIX expansion. That is a real re-derivation with no GitHub input. |
| **6** PER-JOB (`:429-473`) every `secrets.X` a job reads is also requested by that job | **GitHub** — the LHS is a `secrets.X` read | **becomes vacuous**, and its own vacuity guard at `:470-473` (`direct_reads == 0`) turns that into a hard failure rather than a silent pass. Good design, wrong direction now. | **Invert it.** New assertion 6': for every job, the set of `$GITHUB_ENV` names the job's consuming steps reference (`${{ env.<N> }}` and bare `$<N>` in `run:` blocks of steps after the fetch) must be a subset of that job's request block. Same defect class — "the job spends a credential it never fetched" — with the fetch, not GitHub, as the authority. This is the single most valuable new gate, because it is the one that catches the failure mode in §7.1. |
| **7** SUFFIX EXPANSION (`:493-517`) | Bitwarden only | **unchanged, and more important**: it is the only thing that sees `OBS_OTLP_CREDENTIALS_${SUFFIX}` and the SES/Stripe regional fan-ins, which no request line names | — |
| **8** REPRESENTED (`:250-321`) every stored name appears in the code | Bitwarden, `git grep --recurse-submodules` + the two gitignored sibling repos | unchanged | — |
| **9** UNMAPPED READ (`:324-354`) a workflow reads an org secret console can reach that the map does not hold | **GitHub**, explicitly — reads `secret-reachability.json`'s console list | **retire.** Its whole subject is "an org secret exists and is read". With `BWS_ACCESS_TOKEN` the only survivor, the assertion reduces to a one-name allowlist. | Fold into a much smaller assertion 9': **the set of `secrets.X` names read anywhere in the tree must equal exactly `{BWS_ACCESS_TOKEN, GITHUB_TOKEN}`.** One line, no baseline, no network, and it is the gate that makes "GitHub secrets are gone" a fact rather than a claim. |
| exemption loader (`:357-408`) | kinds `no-github-twin \| deferred \| superseded-at-runtime` | `no-github-twin` retires with assertion 5; `deferred` and `superseded-at-runtime` survive unchanged | — |
| `MIN_CALLERS = 22` (`:100`) | neither | the floor sits exactly at today's value with no headroom, so removing any caller file reds the gate. That is correct and should stay. | — |

`.ci/scripts/quality/check_secret_reachability.py` (361 lines) is the harder call. Its whole
subject is "can this repo read this org secret", born of the 2026-08-07 incident where Claude
Review had never once succeeded in `account` or `renet` (`:4-33`). After the cutover it
guards exactly three rows: `BWS_ACCESS_TOKEN` in three repos. **Keep it, do not retire it** —
that is precisely the credential whose silent unreachability would break everything, its
`--refresh` is the only thing that watches an org admin narrowing a `visibility=selected`
list, and its planted-defect controls at `:246-259` already exist. Its `MIN_REFERENCES = 10`
floor (`:50`) must drop to 3, and that change must be made deliberately with a comment, not
silently, because lowering a vacuity floor is how a gate stops asserting.

---

## 6. The two external repositories

### 6.1 What is actually there

Both `private/account/.github/workflows/claude-review.yml:41-45` and
`private/renet/.github/workflows/claude-review.yml:41-45` call
`rediacc/console/.github/workflows/claude-review-reusable.yml@main` and pass exactly one
secret, `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`. Both files are **modified but uncommitted**
(`git status --short .github/` in each submodule shows ` M`), so `@main` still resolves the
*old* spelling in each repo — which is why `.ci/config/secret-reachability.json` records
`CLAUDE_CODE_OAUTH_TOKEN` for `account` and `renet`.

Two facts change the shape of this problem:

1. **Both repos already hold a `BWS_ACCESS_TOKEN`.** `gh api repos/rediacc/{account,renet}/actions/secrets`
   returns `BWS_ACCESS_TOKEN` and `CLAUDE_CODE_OAUTH_TOKEN` for each. The bootstrap is
   already in place; nobody has to mint anything.
2. **The callee can fetch the token itself.** A reusable workflow's `secrets` context resolves
   against the *caller's* repository, so `secrets.BWS_ACCESS_TOKEN` inside
   `claude-review-reusable.yml` reads `account`'s token when `account` calls it. The reusable
   already has a `bws-secrets` step at `:184`.

### 6.2 The target, and why it is smaller than expected

Each caller drops from passing a credential to passing the bootstrap:

```yaml
    secrets:
      BWS_ACCESS_TOKEN: ${{ secrets.BWS_ACCESS_TOKEN }}
```

and `claude-review-reusable.yml` fetches `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` from Bitwarden
for all three callers, dropping its `on.workflow_call.secrets:` block from 2 names to 1 —
and making `BWS_ACCESS_TOKEN` `required: true`, which the comment at `:37-41` currently
forbids for exactly the reason that disappears. `.github/external-callers.yml:29,35` change
`passes_secrets: [ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN]` → `[BWS_ACCESS_TOKEN]`, and CHECK 4 of
`.ci/scripts/security/check-workflow-gates.sh:431-451` enforces it on the console PR.

**This also makes the CLAUDE_CODE_OAUTH_TOKEN rename moot in all three repos**, reinforcing
§2.

### 6.3 Order, and the window

`@main` is resolved at run time, so the callee change lands first and the callers follow —
but a callee that *requires* a secret the callers do not pass fails their runs at startup.
The safe order is therefore:

1. **Submodule PRs first** (`account`, `renet`): add `BWS_ACCESS_TOKEN` to the `secrets:`
   block while **keeping** `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`. Both are then passed.
   `claude-review-reusable.yml@main` still declares both as it does today, so nothing breaks.
2. **Console PR**: the reusable fetches the OAuth token from Bitwarden and stops declaring
   it. Passing an *undeclared* secret is what CHECK 2/CHECK 4 forbid, so this is the step
   that needs the callers already updated **and** their now-superfluous line removed —
   i.e. the submodule PRs in step 1 must be split into 1a (add BWS) and 1c (remove OAuth),
   with the console change between them. Three merges, in that order.
3. **Window**: between 1a and 2, both secrets flow and review works. Between 2 and 1c, the
   callers pass a secret the callee no longer declares — **CHECK 2 fails the console gate,
   and GitHub fails the caller's run**. That window must be closed in the same sitting, not
   left overnight. If the operator will not do three merges in one sitting, keep
   `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` declared as `required: false` in the reusable
   permanently and never remove it from the callers; the cost is one dead declaration.

### 6.4 The privilege question this opens

Giving `account` and `renet` workflows a working `BWS_ACCESS_TOKEN` is already true today —
but today nothing uses it. After this change, `claude-review-reusable.yml` running in those
repos' context can fetch anything the machine account can read: **all 56 secrets in
`ci-shared`**, including the production licence-signing pair and every Cloudflare token. Both
repos are private, both are PR-triggered, and the reusable checks out console's prompt logic
from `@main` rather than from the PR — but the PR's own code is what the review reads. See
Q3 in §9.

---

## 7. Rollback

### 7.1 What "rollback" can and cannot mean

`gh secret` has **no `get`**. GitHub Actions secrets are decryptable only inside a runner
(`agent/PLAN-secret-namespace-migration.md:253-256`). The bulk deletion in §4 step 6 is
therefore **irreversible from GitHub's side**: nothing can put back a value GitHub is the
only holder of.

**The honest statement of the risk: after step 6, for every credential, the copy in Bitwarden
Secrets Manager is the only copy that CI can reach.** Everything else is a re-mint or a
manual restore.

### 7.2 Where the values actually live, per class

This is the part that decides whether the ask is safe at all. Measured, not assumed:

| class | count | where a value can be recovered from | rollback cost |
|---|---|---|---|
| In the Bitwarden **password-manager vault** (a different store from Secrets Manager) | ~17 + GPG | `agent/PLAN-secret-namespace-migration.md:962-980` — the GPG keypair was found split across items named `gpg-private.asc - 1/- 2` and `passphrase - info@rediacc.com`, reassembled, and verified to be fingerprint `42EAD1408A684AB8F185F03F49BA687F0527C72B`, the published signing key | manual paste |
| In `private/account/.env` on the operator's machine | 20 of the names, under the **new** spellings | `ACCOUNT_{ED25519,X25519}_*`, `ACCOUNT_{JWT_SECRET,SERVER_API_KEY}`, `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`, `AWS_SES_*`, `CLOUDFLARE_{R2_*,R2_MEDIA_*,TURNSTILE_SECRET_KEY,BREAKPOINT_TUNNEL_TOKEN}`, `GITHUB_AUTOPILOT_PRIVATE_KEY`, `OBS_OTLP_CREDENTIALS`, `BWS_ACCESS_TOKEN` (names read from the file; no value was opened) | zero |
| Re-mintable by `./run.sh rotation rotate <slug>` | 16 | admin credentials are already in `.env`; slugs `ses-{eu,us,asia}`, `cf-{cd,r2,r2-media,breakpoint}`, `turnstile`, `otlp-{eu,us,asia}`, `dkim-notify` | one rotation |
| **Recoverable only from the third-party dashboard** | Stripe (4), Dockerhub (2), GitHub App private key | Stripe keys are revealable in the Stripe dashboard; a GitHub App private key can be **re-issued** (the old one revoked) but never read back | re-issue, and every consumer must be updated |
| **Not recoverable anywhere** | the GPG *revocation certificate* | recorded as still missing at `agent/PLAN-secret-namespace-migration.md:978-980` | unrelated to this plan, but it means the signing key cannot be revoked if compromised |

**So the answer to "is rollback possible" is: yes for ~90% of rows, at manual cost, and the
exposure is not the deletion — it is Bitwarden Secrets Manager becoming a single point of
failure for CI.** Two consequences the operator should weigh:

- A `bws secret delete` is likewise irreversible: a live probe recorded at
  `agent/PLAN-secret-names-one-to-one.md` step 8 showed a deleted id 404s and vanishes from
  `list`. Do not "clean up" the store in the same sitting.
- `BWS_ACCESS_TOKEN` expiring or being revoked takes down **every** workflow at once, where
  today it takes down nothing. `scripts/dev/bws-map-refresh.py:56-115` warns on the recorded
  expiry; that warning is advisory (`:60-64`) and should become a hard gate once the token is
  load-bearing. See Q1.

### 7.3 One thing to do before step 6 that makes the whole question smaller

Export the 56 Secrets Manager values into the operator's password-manager vault (or a
GPG-encrypted file held offline) **before** the deletion, so that "Bitwarden SM is the only
copy" stops being true on the same day it becomes true. This is one operator action and it
converts an irreversible step into a recoverable one.

---

## 8. What a gate asserts afterwards — control-first

No gate is proposed here without the defect that must turn it red. Where an existing script
already carries a self-test, the new control is added there; `check_bws_map.py:693-697`
refuses to render a verdict if `selftest()` fails, and `check_secret_reachability.py:325-332`
does the same, so both have somewhere to put one.

| # | assertion | planted defect that MUST make it red | planted non-defect that must NOT |
|---|---|---|---|
| **G1** | **The only `secrets.X` names in the tree are `BWS_ACCESS_TOKEN` and `GITHUB_TOKEN`.** Scans `.github/workflows/*.yml`, `.github/actions/*/action.yml`, `.ci/breakpoint/workflow/*.yml`, and each submodule's own workflows. Replaces assertion 9. | add `FOO: ${{ secrets.CLOUDFLARE_API_TOKEN }}` to any step's `env:` | `GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}`; `access-token: ${{ secrets.BWS_ACCESS_TOKEN }}` |
| **G2** | **Assertion 6' (inverted per-job coverage):** every `${{ env.<N> }}` reference and every `$<N>`/`${<N>}` occurrence in a `run:` block, where `<N>` is a name in `bws-secret-map.json`, must appear in that job's own `secrets: |` request block, in a step that precedes it. | move one request line from job A's block to job B's while leaving A's consumer in place | a `${{ env.<N> }}` in a job that does request `<N>`; a `$HOME`-style name that is not in the map |
| **G3** | **The fetch precedes every consumer, and every local action that needs a fetched value.** For each job: index of the `bws-secrets` step < index of any step referencing `env.<N>` for a mapped `<N>`. | swap the `bws-secrets` and `app-token` steps in `cd-deploy-worker.yml`'s `deploy` job | the 44 jobs that are already ordered correctly |
| **G4** | **A job whose first checkout is sparse and which runs `bws-secrets` must include `.ci/config` in the sparse list.** Trap B, §4.2. | delete `.ci/config` from `backfill-release-sentinel.yml:70`'s sparse list | a job with a full checkout |
| **G5** | **No `Compare shadow secrets` step, no `SHADOW_NAMES:`, and no `BWS_`-prefixed alias survives.** A scaffold-expiry gate; the one thing that stops the shadow living forever "just in case". | re-add one compare step | — |
| **G6** | **`secret-reachability.json` records exactly `BWS_ACCESS_TOKEN`, reachable, in all three repos.** The existing script with `MIN_REFERENCES` lowered from 10 to 3 **and the lowering commented**, plus its existing three controls at `:246-259` retained. | mark `BWS_ACCESS_TOKEN` unreachable for `renet` in the baseline | — |
| **G7** | **Every UUID in the map resolves to a non-empty value.** Cannot be a `npm run ci` gate — it needs the token, and `check_bws_map.py:22-30` correctly refuses to add a check that degrades to "passed" where the token is absent. Wire it as a **CD preflight step** inside a job that already holds `BWS_ACCESS_TOKEN`, comparing lengths only, never values. This is the gate that would have caught the blank-OTLP incident. | set one Secrets Manager value to the empty string | a short-but-nonempty value |

**Two existing gates need their controls re-pointed, not just their logic.** There is no
`.ci/scripts/test/gates/test-*bws*` or `test-*secret-reachability*` harness — the only
control-first machinery for these two scripts is their internal `selftest()`/`controls()`.
That is thinner than the repo's own standard for a gate this load-bearing, and the cutover is
the moment to fix it: `.ci/scripts/test/gates/test-bws-map.sh` driving `check_bws_map.py`
against fixture trees, mirroring `test-gate-anti-vacuity.sh`'s pattern.

**One editing constraint that is easy to trip.** `.github/workflows/breakpoint.yml` and
`.ci/breakpoint/workflow/breakpoint.yml` must stay byte-identical (the drift gate,
`.ci/breakpoint/scripts/check-breakpoint-drift.sh`), and the second is hash-frozen in
`.ci/breakpoint/MANIFEST.sha256`. Any edit is three edits: both files plus a manifest
regeneration.

---

## 9. What I could not settle — questions with a recommendation each

**Q1. Does `BWS_ACCESS_TOKEN` becoming a total single point of failure need a second machine
account?**
Today its failure breaks nothing; afterwards it breaks every workflow. Bitwarden Secrets
Manager machine-account tokens have no self-describable expiry, which is why
`bws-map-refresh.py:56-115` fingerprints the client-id against a hand-written date.
*Recommendation:* keep one token, but (a) promote the expiry warning from advisory to a hard
gate, and (b) record a second, unused machine-account token in the vault so a revocation is a
paste rather than a console visit. **Operator decision: whether to mint the standby.**

**Q2. Do the three OTLP credentials get rotated now, or does the deletion stop short of
them?**
Row O3 blocks 3 of 44. *Recommendation:* rotate them (`./run.sh rotation rotate otlp-{eu,us,asia}`)
during step 0's preflight, so the deletion is complete rather than "44 minus 3 with a note".
The alternative — delete 41 and leave 3 — leaves the org secret list non-empty and G1
permanently exempted, which is the shape that rots. **Operator only: it needs the rotation
admin credentials.**

**Q3. Should `account` and `renet` get a Bitwarden project scoped to the review token, rather
than `ci-shared` access?**
§6.4. A machine account's access is per-project, so the clean answer is a project
`ci-review` holding only `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`, with a second machine-account
token issued to the two submodule repos. **I could not verify** whether a Bitwarden SM secret
can belong to two projects (it appears not — a secret has one `projectId`, which
`bws-map-refresh.py:175-188` relies on), which would mean moving the secret out of
`ci-shared` and granting console's machine account access to `ci-review` as well.
*Recommendation:* do it — one shared credential is worth the extra project — but confirm the
one-project constraint against the Bitwarden docs before committing to the shape. **Not
verified here; treat as a hypothesis.**

**Q4. Should the shadow's left operand read pre-images (§2.2), or should the operator do the
22 renames after all?**
*Recommendation, and my default:* pre-images. It is 102 generated line edits against 22
credential handlings, 11 of which require finding a value `gh` cannot read back, and it makes
the whole rename table dead code the same day. The only argument for the rename is that
`secret-rename.py`'s table would otherwise be exercised nowhere — which is an argument for
deleting the table, not for running it.

**Q5. Is the Stripe three-into-one collapse safe?**
The tree asserts one Stripe account serves all three regions. I did not verify it. The
pre-image shadow (§2.2) turns it into a measurement at zero extra cost. *Recommendation:*
shadow `STRIPE_SECRET_KEY` against all three pre-images and read the result before step 6.

**Q6. Do steps 1 and 2 land as one commit or two?**
*Recommendation:* one. Two commits means an intermediate tree where the shadow's names and
the consumers' names disagree, and the intermediate state is never run in production anyway.
The safety comes from step ordering inside each job, not from commit granularity.

---

## Tasks

- [?] **(operator, step 0)** Non-empty preflight over all 56 map UUIDs — lengths only, never values (G7's manual first run)
      AUDIT: UNVERIFIABLE from the tree: the preflight is a `bws secret get` loop needing BWS_ACCESS_TOKEN and its result is recorded nowhere. Proof would be a committed length-only record, or a CD step running `bws secret get ... | jq -r '.value | length'`.
- [ ] **(operator, Q2)** `./run.sh rotation rotate otlp-{eu,us,asia}`, closing row O3 and the three `deferred` exemptions at `.ci/config/bws-unrequested.json:198-216`
- [?] **(operator, §7.3)** Back the 56 Secrets Manager values out to the password-manager vault before any deletion
      AUDIT: UNVERIFIABLE from the tree: the backup happens inside the operator's password-manager vault, which `gh` cannot see. Proof would be a dated export receipt recorded in a config file, or an operator attestation.
- [ ] Generate the pre-image rewrite of 102 `GH_<N>` lines from `secret-rename.py`'s `RENAMES` table (§2.2)
- [ ] Reorder `bws-secrets` ahead of `app-token` in the 7 jobs of §4.2 Trap A; add `.ci/config` to the 2 sparse lists of Trap B
      HALF DONE 2026-09-02, and the half that was done was a LIVE defect, not a cutover
      preparation. Trap B is fixed: `.ci/config` added to both sparse cones
      (backfill-release-sentinel.yml job `backfill`, cd-deploy-account.yml job `deploy`).
      ./.github/actions/bws-secrets resolves NAMES to UUIDs out of
      .ci/config/bws-secret-map.json AT RUN TIME, so a cone stopping at `.github/actions`
      fails the fetch with "bws-secret-map.json not found" -- on the CD path, in a
      production deploy. Swept as a class rather than as two instances: CHECK 5 in
      .ci/scripts/security/check-workflow-gates.sh now fails any job that both fetches
      from Bitwarden and narrows its checkout without the map, proven by planting the
      defect back (rc=1, names the job) and removing it again. It reports the vacuous
      case explicitly, because it can only fire on a small set by construction.
      STILL OPEN: Trap A, the app-token/bws-secrets ORDER in the 7 jobs. That one only
      bites after the cutover, when the app token's private key comes from Bitwarden.
- [ ] Flip 137 identity `env:` lines (delete), 78 `with:` aliases and 24 `env:` aliases (→ `${{ env.<N> }}`), 157 passthrough lines (delete), 80 `workflow_call` declarations → 9
- [ ] Delete the 4 `AWS_SES_*_ASIA` reads and 3 passthrough lines (row O4); delete the 2 exemptions that describe them
- [ ] Retire assertion 5's `no-github-twin` kind → `unrequested`; invert assertion 6 → 6'; replace assertion 9 with G1
- [ ] Lower `check_secret_reachability.py:50` `MIN_REFERENCES` 10 → 3 **with a comment saying why**
- [ ] Add gates G1-G5 and G7 with the planted defects named in §8
- [x] Write `.ci/scripts/test/gates/test-bws-map.sh` — the harness neither secret gate has
      AUDIT: DONE 2026-09-02 (audit): .ci/scripts/test/gates/test-bws-map.sh exists (5631 bytes, executable), drives the REAL scan against fixture trees, and is picked up automatically by .ci/scripts/test/run-all.sh:72's gates/test-*.sh glob.
- [ ] Delete 63 compare steps, 63 `SHADOW_NAMES:` lines, 197 `GH_` lines; rewrite 197 request lines to the bare identity form; fix the 63 stale "SHADOW RUN" comments
- [ ] `.github/external-callers.yml:29,35` → `passes_secrets: [BWS_ACCESS_TOKEN]`; three-merge sequence of §6.3
- [ ] **(operator, irreversible)** Delete 44 GitHub secrets; keep `BWS_ACCESS_TOKEN` in `console`, `account`, `renet`
- [ ] `npm run check:ci-secret-reachability -- --refresh` and commit the near-empty baseline
- [ ] Mark `scripts/dev/rename-org-secrets.sh` superseded (do not run it); mark `agent/PLAN-secret-names-one-to-one.md` steps 4-5 superseded by this plan
