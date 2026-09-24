# PLAN: the GitHub Actions variable namespace moves to Bitwarden, and a gate holds it there
Status: done -- executed 2026-09-24: GitHub holds zero Actions variables and only BWS_ACCESS_TOKEN as a secret; ci-actions-vars keeps it that way.
First-Seen: 2026-09-22
Owner: d778be9d
Date: 2026-09-22
Scope: design. Every measurement below was read-only. No value of any secret or variable was read, printed or written. `bws` was interrogated with `--help` only; the live token was never spent.
Distinct from: `agent/plans/PLAN-env-to-bitwarden-v2.md`, which classifies the names `private/account/.env` assigns, and `agent/plans/PLAN-bws-rotation-on-failure.md`, which is about the bootstrap token's lifecycle. Neither touches the `vars.*` namespace, and no gate in this estate can see it.

The operator's ruling:

> "I want to have freedom from github. I may migrate to gitlab later. So, we should only depend on bws for variables and secrets! The only exception is bitwarden secret. It would be great if we can also block that on CI level/tests @ci.yml"

Three things follow, and the third is the durable one. Portability is the goal, not secrecy. `BWS_ACCESS_TOKEN` is the one irreducible exception, for the reason `.ci/rediacc_ci/quality/secret_supply.py` already encodes as `bootstrap_names`: a credential cannot live inside the store it unlocks.
And a migration with no gate behind it is a state someone re-enters by hand the next time a workflow needs a value, so the gate is the deliverable and the migration is what makes the gate green.

## What is true today, measured 2026-09-22

| Claim | Instrument | Result |
|---|---|---|
| BWS has a non-secret item type | `bws --help`, `bws secret --help`, `bws project --help` | NO. Two nouns only: `project` and `secret` |
| `bws secret create` shape | `bws secret create --help` | `<KEY> <VALUE> <PROJECT_ID>`, optional `--note`. No visibility flag |
| Distinct `vars.*` names read in tracked workflows | regex over `.github/**` and `.ci/breakpoint/workflow/` | 20 |
| GitHub Actions variables that exist | session audit, org + `rediacc/console` | 22 (10 org, 12 repo) |
| Variables that exist and nothing reads | set difference | 3: `AWS_SES_REGION_ASIA`, `AWS_SES_REGION_US`, `MEDIA_CDN_DOMAIN` |
| Names read but never set | set difference | 1: `FULL_CI`, deliberately unset (`.github/workflows/ci.yml:335`) |
| `vars.*` reads in a job with NO existing bws fetch | per-job scan against `./.github/actions/bws-secrets` | ZERO |
| Live non-`BWS_ACCESS_TOKEN` `secrets.*` reads | regex, comments excluded | 2, both `secrets.GITHUB_TOKEN` (`.github/workflows/ci-quality.yml:1209`, `.github/workflows/ci.yml:1111`) |
| Files calling `./.github/actions/bws-secrets` | `grep -rln` | 20, matching `MIN_CALLERS`+1 accounting at `.ci/scripts/quality/check_bws_map.py` |
| `vars.*` names classified by `env-manifest.json` | membership test over all eight shards | 15 of 20; `APP_ID`, `TURNSTILE_SITE_KEY`, `AWS_SES_REGION_EU`, `FULL_CI`, `MEDIA_CDN_DOMAIN` are in NO shard |

The last row is the finding that justifies a new gate rather than an extension of an old one. `env_manifest.py`'s `workflow-key` reader matches ENV-shaped YAML MAPPING KEYS, not expression references, so `VITE_TURNSTILE_SITE_KEY: ${{ vars.TURNSTILE_SITE_KEY }}` contributes the left-hand key and drops the variable entirely.
`client-id: ${{ vars.APP_ID }}` contributes nothing at all, because the key is lowercase. The GitHub Actions variable namespace has never been under any assertion in this repository.

A documentation conflict worth draining while nearby: `docs/agent-reference/media-assets.md:24` states the org holds 14 variables and the repo 21, and that `MEDIA_CDN_DOMAIN` is among neither. The 2026-09-22 audit measured 10 and 12, with `MEDIA_CDN_DOMAIN` present at org level.
One of the two is stale and the paragraph already carries a "corrected twice" note, so it should be re-derived rather than believed.

## Sibling sweep, 2026-09-24

Run over `.github/**` and `.ci/breakpoint/workflow/`, comments excluded by reading each hit. No reference form other than `vars.*` and `secrets.*` reaches a GitHub-hosted value, so the gate's two readers are the whole surface. The negatives, counted so the blind spots have a number: zero `vars.X || ...` or `... || vars.X` fallbacks; zero composite-action `default:` values reading `vars` or `secrets` under `.github/actions/`; zero `toJSON(vars)`, `toJSON(secrets)`, `vars[...]` or `secrets[...]` bulk reads (the two textual `.secrets[` hits are a `jq` path at `.github/actions/bws-secrets/action.yml:95` and a comment at `.github/workflows/watchdog-monitor.yml:199`). The `github.*` context carries 16 distinct names, every one runtime context rather than configuration: `token` 61, `event` 60, `sha` 47, `actor` 35, `event_name` 31, `run_id` 13, `repository` 10, `base_ref` 7, `ref` 4, `ref_name` 3, `head_ref` 3, `action_path` 2, and one each of `workspace`, `workflow`, `run_attempt` and `repository_owner` (`.github/actions/app-token/action.yml:109`).

The `secrets.*` table above holds once comments are excluded: the live non-bootstrap reads are still exactly the two `secrets.GITHUB_TOKEN` sites, now at `.github/workflows/ci.yml:1111` and `.github/workflows/ci-quality.yml:1230` (the latter moved from `:1209`). A raw regex counts two more names, and both are comments the gate must not fire on: `secrets.ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` at `.github/workflows/claude-review-reusable.yml:264` and `:384`, and a third `secrets.GITHUB_TOKEN` in prose at `.github/workflows/ci.yml:1058`. Those join the four `secrets.sh` comment hits as the false-positive fixtures the gate's selftest plants.

## Dead variables removed, 2026-09-24

On the operator's go-ahead, after a usage check across console, every submodule and `gh search code --owner rediacc` over the whole org, the three unread org variables `AWS_SES_REGION_ASIA`, `AWS_SES_REGION_US` and `MEDIA_CDN_DOMAIN` were deleted with `gh variable delete --org rediacc`. The SES regions reach the deploy from `regions.json` through `.github/workflows/cd-deploy-account.yml:310` (`AWS_SES_REGION: ${{ matrix.sesRegion }}`), which the `private/account` docs now say instead of naming the org variable. The store now holds 10 org and 12 repository variables. A fourth org variable, `R2_MEDIA_BUCKET`, has no reader either (the bucket is a literal in `.ci/scripts/deploy/sync-media-to-r2.sh`); it was not in the approved set and stays until asked.

## Execution, 2026-09-24

The operator ruled that day that nothing may depend on GitHub variables or secrets, with the bootstrap token as the one exception, and set the order: eliminate what is not needed, migrate the rest to Bitwarden, then remove everything from GitHub. No value was printed or written anywhere below; every comparison ran inside one process and printed MATCH or MISMATCH.

ELIMINATED, no reader anywhere in the org, deleted with `gh variable delete --org rediacc`: `R2_MEDIA_BUCKET` (the bucket is a literal in `.ci/scripts/deploy/sync-media-to-r2.sh`), `SMTP_FROM` and `SMTP_PORT`. Evidence: `gh search code "vars.<NAME>" --owner rediacc` returns nothing for all three, and a local grep of console and every submodule's `.github/` finds no `vars.` read. The two SMTP names are env keys the on-prem image reads, which a customer supplies; the GitHub variables were never passed to anything, and both already sit in ci-shared (MATCH against the GitHub copies before deletion). This joins the three deleted earlier the same day.

SEEDED into ci-shared, 20 keys, each checked absent first and each carrying a `--note` naming its origin: `GITHUB_APP_ID` (from `APP_ID`), `AWS_SES_CONFIGURATION_SET`, `AWS_SES_FROM`, `AWS_SES_REGION_EU`, `CLOUDFLARE_ZONE_ID`, `GIT_BOT_NAME`, `GIT_BOT_EMAIL`, `CLOUDFLARE_ACCOUNT_ID`, `ROOT_EMAIL`, the nine `SELLER_*` as nine ordinary secrets per Decision 1, `TURNSTILE_SITE_KEY`, and `FULL_CI`. The 19 copied values compare MATCH against GitHub. `scripts/ops/bws-map-refresh.py` took the map from 56 to 76.

DELETED FROM GITHUB the same day, on the operator's override that dropped the wait for a green CI run: each of the 19 was re-read from both stores inside one process and deleted only on MATCH, and all 19 matched. Org: `APP_ID`, `AWS_SES_CONFIGURATION_SET`, `AWS_SES_FROM`, `AWS_SES_REGION_EU`, `CLOUDFLARE_ZONE_ID`, `GIT_BOT_EMAIL`, `GIT_BOT_NAME`. `rediacc/console`: `CLOUDFLARE_ACCOUNT_ID`, `ROOT_EMAIL`, the nine `SELLER_*`, `TURNSTILE_SITE_KEY`. Afterwards the org and every repository hold zero variables; the only GitHub secrets left are `BWS_ACCESS_TOKEN` in console, account and renet, and `CLAUDE_CODE_OAUTH_TOKEN` in `rediacc/elite`, which has no workflow at all (`gh api repos/rediacc/elite/actions/workflows` reports `total_count` 0), so nothing reads it; its value cannot be read back through the API, and it stays until the operator decides. THE COST OF NOT WAITING: until this change reaches `main`, every workflow that runs from `main`'s own files (pushes, schedules, dispatches) still reads `vars.*` and now gets an empty string, so its `app-token` steps fail.

EVERY `vars.*` READ IS GONE from the corpus, including the breakpoint session job's five: `check:ci-actions-vars` prints 0 reads over 32 files, and `.ci/config/actions-vars.json` holds an empty `vars` object, which is the terminal state.

WHAT THIS PLAN GOT WRONG, found by running it:

  * DECISION 3's breakpoint exemption rested on a job that "must not fetch". It has fetched since 2026-09-14 (the narrow `CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN` step in `.github/workflows/breakpoint.yml`), and the three values it read from `vars.*` are not credentials; each was already printed in the clear in that job's step env blocks. So they ride the same narrow fetch, the credential count reaching GITHUB_ENV stays one, and the end-state count is 0, not the 5 the last task below expected. The `no-fetch-job` kind is built and proven on fixtures and holds no entry.
  * DECISION 4 clause 6 asked for a REFUSAL when `vars` is empty and reads exist. In the terminal state that is exactly what a NEW read looks like, and "the file was emptied" would be a false message on the one event the gate exists to catch. It reds through clause 1 instead, once per read.
  * FULL_CI cannot be an empty or boolean secret. Bitwarden refuses an empty value, and `bitwarden/sm-action` masks every value it fetches, so a stored `true` or `false` would mask that word across the whole `initialize` job and the runner would drop every job output containing it. The stored value is the sentinel `full-ci-off`, and `.github/workflows/ci.yml` maps `full-ci-on` to the literal `true` the scope engine compares against.
  * MASKING applies to every migrated value, which the "what gets harder" section below does not mention. The one short value is `SELLER_COUNTRY`, which will be masked wherever it occurs in the two deploy jobs' logs; neither job has outputs, so nothing is dropped.
  * `APP_ID` had 46 reads, not 47.
  * `check_bws_map.py` assertion 14 never noticed a `deferred` row whose seeding had landed: eleven `.ci/config/env-local-allowlist.json` rows for `ROOT_EMAIL`, `AWS_SES_FROM` and the nine `SELLER_*` would have sat until their expiry. The clause and its control are added, and the rows are drained.

## Decision 1: variables become ordinary BWS secrets, in `ci-shared`, not a JSON blob

Three shapes were considered.

ORDINARY SECRETS, one per name. Every existing mechanism works unchanged: `bws-map-refresh.py` regenerates the map, `.github/actions/bws-secrets` resolves NAME to UUID, `check:ci-bws-map` asserts both directions of coverage, `bitwarden-sm.ts` can rotate one. The cost is that a plaintext seller postal code sits in the same project as an Ed25519 private key.

ONE JSON BLOB holding all non-secret config. This looks tidier and is worse in every checkable way. `check_bws_map.py` asserts per-NAME coverage in both directions; a blob is one name, so nineteen values collapse into one uncheckable opaque string and the reverse-coverage clause that makes the map untrimmable stops applying to them.
Every consumer would need a parse step that does not exist today, and a typo inside the blob fails at deploy time instead of at map-resolution time. The `bws-secrets` action's own contract -- `NAME` or `NAME > ENV_NAME`, one per line -- would have to grow a second mode.

A SEPARATE PROJECT for the seller and invoicing data. This is the one genuinely open question, and the answer is NO for now with the reason written down rather than assumed.
`.ci/config/secret-supply.json`'s `dotenv.destinations` already records why `admin-bootstrap` must not be `ci-shared`: read on `ci-shared` is held by every CI job, and an admin credential mints and deletes infrastructure. The seller block is the opposite case -- it is a business address that appears on invoices customers receive, so wider read is not an escalation.
More decisively, `secret_supply.py`'s header records that the organization holds exactly ONE project and that only the web vault can create another, making a second project `door:operator-only` and therefore a blocker this plan cannot clear. Splitting it later is a rename plus a map refresh, which is cheap; blocking the whole migration on an operator action is not.

So: ordinary secrets, `ci-shared`, one per name. The tradeoff is stated and accepted, and the accepting reason is that the shard definition at `.ci/config/env-manifest.json` already says vault membership rather than sensitivity is what the `secret` shard means.

## Decision 2: the naming, and one free win

`APP_ID` migrates as `GITHUB_APP_ID`, beside the `GITHUB_APP_PRIVATE_KEY` already in the map. That pairing is not cosmetic: 47 of the 67 `vars.*` reads in the tree are `vars.APP_ID`, every one of them is the `client-id:` input to `./.github/actions/app-token`, and every one of them sits in a job that ALREADY fetches `GITHUB_APP_PRIVATE_KEY` for the very next input.
The per-file counts match exactly -- `ct-tests.yml` 14 and 14, `ci-quality.yml` 9 and 9, `ci.yml` 5 and 5, `ci-build-renet.yml` 4 and 4, `cd-v2.yml` and `ci-build-docker.yml` 3 and 3, `cd-deploy-account.yml` and `housekeeping.yml` 2 and 2, five more at 1 and 1.
So 70 percent of the migration is one appended line per existing fetch block and a substitution of `${{ env.BWS_APP_ID }}` for `${{ vars.APP_ID }}`, with no new step anywhere.

The remaining names keep their spellings, since `check_bws_map.py`'s reverse clause and `scripts/ops/secret-rename.py` both key on exact tokens and a gratuitous rename buys nothing.

## Decision 3: what does NOT migrate, and why each refusal is checkable

Four categories, and each maps onto an exemption shape the estate already has.

DEAD. `AWS_SES_REGION_ASIA`, `AWS_SES_REGION_US`, `MEDIA_CDN_DOMAIN`. Zero `vars.` readers anywhere. `.github/workflows/cd-deploy-account.yml:310` takes the region from `matrix.sesRegion`, which `.github/workflows/cd-deploy-account.yml:63` derives from `regions.json:17,35,53`. These are deleted with `gh variable delete`, not migrated.
Migrating a dead name is how a store acquires the inert leftovers `.ci/config/bws-unrequested.json` already carries four of.

BOOTSTRAP. `BWS_ACCESS_TOKEN`, which is a secret and not a variable, and is the sanctioned exception by the same argument `secret_supply.py` records under `bootstrap_names`.

RUNNER-MINTED. `secrets.GITHUB_TOKEN` at `.github/workflows/ci-quality.yml:1209` and `.github/workflows/ci.yml:1111`. Minted per job by the runner, never stored anywhere, and the closest analogue on a GitLab runner is `CI_JOB_TOKEN`. It is not a GitHub dependency in the sense the operator's ruling means.

THE JOB THAT MUST NOT FETCH. `breakpoint.yml`'s `session` job reads `vars.CLOUDFLARE_ACCOUNT_ID` at lines 227, 316 and 376 and `vars.AWS_SES_REGION_EU` and `vars.AWS_SES_FROM` at 344 and 345.
That job hands a human a shell, and `.github/workflows/breakpoint.yml:210-216` and `:333-341` both record why moving values into it is refused: `GITHUB_ENV` and `GITHUB_OUTPUT` are files any later step can read, so a fetched value is a value handed to whoever holds the session.
`.ci/config/bws-unrequested.json` already carries a `no_fetch_jobs` key, keyed `<path>#<job>` with a BLOCKER reason and a liveness check, built for exactly this. The same key shape is what the new gate's exemption half should use.
Note that `.ci/breakpoint/workflow/breakpoint.yml` is a frozen twin of the same file and carries the same five reads at the same line numbers, so any exemption is a pair.

THE OPERATOR SWITCH. `vars.FULL_CI` at `.github/workflows/ci.yml:335` is a kill switch whose whole design, per the comment at `.github/workflows/ci.yml:325-335`, is that an operator disables CI scoping WITHOUT a code change. It is read but never set.
A BWS secret can serve this -- `bws secret edit` is equally out-of-band once the name exists in the map -- so this is a migration with a caveat rather than an exemption: the secret must be CREATED (with an empty value) and mapped in the same commit as the workflow edit, or the switch becomes uncallable until someone lands a map refresh.
This is the one name where the migration is strictly worse ergonomically, and it should be migrated anyway, because a portability plan that leaves one GitHub-shaped control plane behind has left the whole class behind.

## Decision 4: the gate this plan adds, `ci-actions-vars`

Modelled clause for clause on `check_bws_map.py` and `check_secret_supply.py`: control-first, both directions asserted, every exemption re-derived rather than believed, anti-vacuity clauses that are true in the terminal state as well as today.

WHERE THE CODE GOES. `.ci/rediacc_ci/quality/actions_vars.py` for the logic and `.ci/scripts/quality/check_actions_vars.py` as the by-path entry point carrying the `---- gate ----` header, matching the split `check_secret_supply.py` uses and documents.
The header's `lane:` is `quality-security`, beside `Bitwarden secret map` at `.github/workflows/ci-quality.yml:2238`, because this is the same subject.

NO NEW PARSER. `.ci/rediacc_ci/workflows.py` is the one canonical parser and its docstring is an argument against the sixteenth.
For line-numbered findings the gate uses `check_bws_map.py`'s existing `call_sites()`, `job_index()` and `job_at()` at `:180`, `:202` and `:206`; those three should be lifted into `rediacc_ci/workflows.py` so both gates import one copy, which is the same move `workflows.py` was created to make.

WHAT IS ASSERTED, six clauses.

  1. FORWARD. Every `vars.NAME` read in the corpus has an entry in `.ci/config/actions-vars.json`, or the gate reds naming the file, the job and the name.
  2. REVERSE. Every entry in that file is still read by some call site. An entry whose reads have all gone reds as RESOLVED, with the message naming both readings the way `secret_supply.evaluate_residue` does -- either the migration landed and the entry should be drained, or the read moved and the entry is now a lie. This is what makes the file untrimmable in both directions.
3. KINDS ARE RE-DERIVED. `migrated` requires the name's BWS twin to be present in `.ci/config/bws-secret-map.json`, so an entry claiming a migration that did not happen reds. `no-fetch-job` requires the cited `<path>#<job>` to exist AND to still contain the read, the same double liveness `.ci/scripts/quality/check_bws_map.py:818-833` applies to `no_fetch_jobs`.
  `dead` requires ZERO reads, so it is unreachable by construction and exists only to be refused -- a dead name is deleted, not recorded.
4. THE SECRETS ARM. Every `secrets.NAME` read outside a comment is `BWS_ACCESS_TOKEN` or `GITHUB_TOKEN`. This is green today and the clause exists to keep it that way; a workflow that starts reading a new GitHub secret reds at the commit that adds it.
  The name regex must require `[A-Z][A-Z0-9_]*` and reject a following path character, or `set-account-worker-secrets.sh` in a comment matches as `secrets.sh` -- four such false positives exist in the tree today and the selftest must plant one.
5. COMMENTS ARE NOT READS. Both `secrets.ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` occurrences (`.github/workflows/claude-review-reusable.yml:264,384`) are inside `#` comments explaining a fallback that was deliberately removed. A gate that counts them reds on a correct tree, which is the shape that gets suppressed.
  The selftest must plant a commented read and require it NOT to fire, in both the vars arm and the secrets arm.
6. ANTI-VACUITY, and none of it is a floor that reds on success. Zero candidate files is a REFUSAL naming the corpus, because "there are no workflows in this repository" is an instrument that lost the tree, not a pass. An empty `actions-vars.json` alongside a non-empty derived read set is a REFUSAL.
  An empty read set alongside an empty file is the TERMINAL state and passes, printing zero -- the state this plan is working towards, and a typed floor of "at least 20" would red exactly when the migration succeeds, which is the finish-line trap `secret_supply.py` names in its own anti-vacuity section.

WHERE THE CONFIG GOES. `.ci/config/actions-vars.json`, not `.ci/policy/`.
The reasoning is `secret_supply.py`'s verbatim and applies unchanged: this file exempts nothing from another gate, deleting it makes this gate refuse rather than pass, and `.ci/policy/` is under four-way set equality via `check:ci-policy-inventory` so a file landing there without matching edits to two tuples and a README reds on arrival.

## The migration, site by site

Every site below was verified against the tree on 2026-09-22.

APP_ID, 47 sites in 12 files, all `client-id:` inputs to `./.github/actions/app-token`. New BWS secret `GITHUB_APP_ID` in `ci-shared`. Each existing `bws-secrets` block gains `GITHUB_APP_ID > BWS_APP_ID`; each `client-id: ${{ vars.APP_ID }}` becomes `client-id: ${{ env.BWS_APP_ID }}`.
Files and counts: `ct-tests.yml` 14, `ci-quality.yml` 9, `ci.yml` 5 (first at `:240`, beside the fetch at `:231`), `ci-build-renet.yml` 4, `cd-v2.yml` 3, `ci-build-docker.yml` 3, `cd-deploy-account.yml` 2 (`:92`, `:204`), `housekeeping.yml` 2, and one each in `backfill-release-sentinel.yml`, `cd-deploy-worker.yml`, `ci-ops-test.yml`, `cleanup-preview.yml`.
Consider making `app-token`'s `client-id` input optional with a default of `${{ env.BWS_APP_ID }}` at `.github/actions/app-token/action.yml:7`; that would collapse 47 edits into one, at the cost of a composite whose contract depends on an ambient env name, which is the kind of implicit coupling this repo generally refuses. Recorded as an option, not a recommendation.

CLOUDFLARE_ACCOUNT_ID, 25 sites.
`.github/workflows/ci.yml:1348,1390,1395,1498`, `.github/workflows/cleanup-preview.yml:86,92,102,126`, `.github/workflows/housekeeping.yml:88,114,178`, `.github/workflows/cd-deploy-account.yml:276,281`, `.github/workflows/cd-deploy-worker.yml:158,163`, `.github/workflows/ct-tests.yml:184,190`, `.github/workflows/watchdog-monitor.yml:177`, `.github/workflows/breakpoint.yml:227,316,376` and the frozen twin at the same three lines.
Every one of those jobs already fetches. The breakpoint five are the `no-fetch-job` exemption.

CLOUDFLARE_ZONE_ID, 4 sites: `.github/workflows/ci.yml:1661`, `.github/workflows/cd-stage.yml:340`, `.github/workflows/cd-v2.yml:383`, `.github/workflows/promote-stable.yml:118`. All four jobs already fetch (`.github/workflows/cd-stage.yml:105`, `.github/workflows/cd-v2.yml:253`, `.github/workflows/promote-stable.yml:44`, `.github/workflows/ci.yml:1643`).

The SELLER block, 9 names, 18 sites, exactly two files: `.github/workflows/cd-deploy-account.yml:322-330` and `.github/workflows/cd-deploy-worker.yml:182-190`. Both jobs already fetch (`:156`/`:170` and `:59`). This is the cluster the separate-project question was about; see Decision 1.

ROOT_EMAIL, 4 sites: `.github/workflows/cd-deploy-account.yml:321`, `.github/workflows/cd-deploy-worker.yml:181`, `.github/workflows/ci.yml:1407`, `.github/workflows/ct-tests.yml:1917`. Already in the `product-runtime` shard of the env manifest, so the shard must move to `secret` when the vault acquires the name -- see the sequencing note below.

AWS_SES_FROM (`.github/workflows/cd-deploy-account.yml:309`, `.github/workflows/cd-deploy-worker.yml:177`, `.github/workflows/ci.yml:1414`, `.github/workflows/breakpoint.yml:345` and twin), AWS_SES_CONFIGURATION_SET (`.github/workflows/cd-deploy-account.yml:308`, `.github/workflows/cd-deploy-worker.yml:176`, `.github/workflows/ci.yml:1415`), AWS_SES_REGION_EU (`.github/workflows/cd-deploy-worker.yml:178`, `.github/workflows/ci.yml:1410`, `.github/workflows/breakpoint.yml:344` and twin).
The breakpoint reads are exempt; the rest migrate.
Note that the map already holds an unsuffixed `AWS_SES_REGION` whose `bws-unrequested.json` reason says nothing requests it and the deploy paths use `matrix.sesRegion` and `vars.AWS_SES_REGION_EU`; migrating the EU variable makes that reason stale in one half, so the exemption's text must be re-derived in the same change or `check:ci-bws-map` will be carrying a sentence that is no longer true.

GIT_BOT_NAME and GIT_BOT_EMAIL, 6 sites, one file: `.github/workflows/cd-v2.yml:668,669,688,689,702,703`, job `tag-and-release`, which already fetches at `:634`.
Line 668-669 are inside a `run:` block as `git config` arguments rather than an `env:` block, so the substitution there is `${BWS_GIT_BOT_NAME}` shell interpolation, not `${{ env.X }}` -- the one site in the whole migration where the edit is not mechanical.

TURNSTILE_SITE_KEY, 2 live sites: `.github/workflows/cd-deploy-account.yml:123` (job `build`, fetch at `:83`) and `.github/workflows/cd-deploy-worker.yml:141` (fetch at `:59`). The third occurrence, `.github/workflows/ci.yml:1354`, is a COMMENT explaining that PR previews deliberately use the per-PR widget minted at `.github/workflows/ci.yml:327-333` instead.
The map already holds `CLOUDFLARE_TURNSTILE_SECRET_KEY`, so the site key joins its own pair.

FULL_CI, 1 site, `.github/workflows/ci.yml:335`. See Decision 3.

## Sequencing, and the one trap in it

The order matters and getting it wrong reds three gates at once.

A name entering `.ci/config/bws-secret-map.json` enters `env_manifest.py`'s `vault` source, which means it must appear in some shard of `.ci/config/env-manifest.json` or clause 1 (`sources \ shards == {}`) reds. Worse, the shards are asserted PAIRWISE DISJOINT, so `CLOUDFLARE_ACCOUNT_ID` cannot be in `ci-runner` and `secret` at once -- it must MOVE.
`ROOT_EMAIL`, `AWS_SES_FROM`, `AWS_SES_CONFIGURATION_SET` and the nine `SELLER_*` names move out of `product-runtime`; `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_ZONE_ID`, `GIT_BOT_NAME` and `GIT_BOT_EMAIL` move out of `ci-runner`. `APP_ID`, `TURNSTILE_SITE_KEY`, `AWS_SES_REGION_EU` and `FULL_CI` are in no shard today and simply arrive in `secret`.

Meanwhile `secret_supply.py` derives its residue as `shards.secret \ map.secrets`, so a name that lands in the `secret` shard BEFORE its BWS twin exists appears in the residue and demands an entry with an evidence path -- and then reds as RESOLVED the moment the twin arrives.
The only order that never passes through a red is: create the BWS secret, refresh the map with `scripts/ops/bws-map-refresh.py`, move the shard, edit the workflow, all in one commit. The map refresh needs `bws` on PATH and a live `BWS_ACCESS_TOKEN`, so the seeding half is `door:operator-only` and the plan should not pretend otherwise.

The `MIN_CALLERS` floor at `.ci/scripts/quality/check_bws_map.py` counts FILES with a `bws-secrets` call, and this migration adds none, so the floor is untouched. `MIN_MAP_ENTRIES` is 30 against a map of 56 and rises, so it is untouched too.

## What gets harder, stated plainly

Three things, and the operator's stated goal settles all three.

Visibility. A GitHub Actions variable is readable in the repository settings UI and by any workflow with no fetch. After this, reading the seller address means holding the machine-account token. For a value that appears on customer invoices that is a small loss and a real one.

Edit latency. Changing `SELLER_CITY` is currently `gh variable set`. After this it is `bws secret edit`, which is comparable -- but a NEW name additionally requires a map refresh and a commit, because `bws-secrets` resolves by UUID. `vars.FULL_CI` is the sharpest case; see Decision 3.

Blast radius. Read on `ci-shared` is held by every CI job. Nineteen more names in that project is nineteen more things a compromised job sees, and every one of them is already plaintext business config that the deploy output prints anyway. The breakpoint `no-fetch-job` exemption is where this actually bites, and it is exempted rather than accepted.

Against those: the goal is portability, the operator said so, and the number that settles it is that a GitLab migration today would require re-discovering 22 GitHub-shaped names that NO gate, manifest or document in this tree currently enumerates -- which is precisely how the retired autopilot App came to leave ten orphaned variables behind.
After this, `.ci/config/actions-vars.json` is that enumeration and it cannot go stale, because clause 2 reds when it does.

## Tasks

- [x] ROOT CAUSE. Add the `vars.*` and `secrets.*` reference readers to `.ci/rediacc_ci/workflows.py`, lifting `call_sites()`, `job_index()` and `job_at()` out of `.ci/scripts/quality/check_bws_map.py:180-214` so one copy serves both gates, and retarget `check_bws_map.py` at the lifted copies in the same change.
    (ticked) 2026-09-23T15:01:36Z by d778be9d: present per --plan-investigate row: .ci/rediacc_ci/workflows.py:748 (call_sites/job_index/job_at) and .ci/scripts/quality/check_bws_map.py:185-198 (wraps them)
- [x] SIBLING SWEEP. Confirm no other reference form reaches a GitHub-hosted value: `env.` fallbacks to `vars`, `github.` context reads that stand in for config, and composite-action `with:` defaults. Record what the sweep found, including the negatives, so the gate's blind spots have a number rather than a silence.
    (ticked) 2026-09-24T04:08:18Z by d778be9d: sweep recorded in the Sibling sweep section of the plan; live non-bootstrap secrets reads are exactly .github/workflows/ci.yml:1111 and .github/workflows/ci-quality.yml:1230, every other hit is a comment
- [x] Delete the three dead GitHub variables `AWS_SES_REGION_ASIA`, `AWS_SES_REGION_US` and `MEDIA_CDN_DOMAIN`, and re-derive the counts in `docs/agent-reference/media-assets.md:23-24`, which claims 14 org and 21 repo against a measured 10 and 12.
    (ticked) 2026-09-24T05:28:53Z by d778be9d: operator approved 2026-09-24 after usage validation; gh variable delete --org rediacc for AWS_SES_REGION_ASIA, AWS_SES_REGION_US, MEDIA_CDN_DOMAIN; counts re-derived at docs/agent-reference/media-assets.md:24 (10 org, 12 repo)
- [x] Write `.ci/config/actions-vars.json` with one entry per surviving name, each carrying a re-derivable `kind` and, for `no-fetch-job` entries, a `<path>#<job>` key and a BLOCKER reason, following `.ci/config/bws-unrequested.json`'s two-key shape.
    (ticked) 2026-09-24T06:18:27Z by d778be9d: verified 2026-09-24 by this session after the writer: gh shows 0 org and 0 repo variables and only BWS_ACCESS_TOKEN as a secret in console/account/renet; 0 live vars.* reads under .github; npm run check:ci-actions-vars, check:ci-bws-map, check:ci-secret-supply all exit 0; gate at .ci/rediacc_ci/quality/actions_vars.py:1, config .ci/config/actions-vars.json:1
- [x] Build the gate this plan adds, `ci-actions-vars`, as `.ci/rediacc_ci/quality/actions_vars.py` plus the by-path entry point `.ci/scripts/quality/check_actions_vars.py` carrying the `---- gate ----` header, with all six clauses of Decision 4 and a `selftest()` that proves every reader in both directions on fixtures.
    (ticked) 2026-09-24T06:18:28Z by d778be9d: verified 2026-09-24 by this session after the writer: gh shows 0 org and 0 repo variables and only BWS_ACCESS_TOKEN as a secret in console/account/renet; 0 live vars.* reads under .github; npm run check:ci-actions-vars, check:ci-bws-map, check:ci-secret-supply all exit 0; gate at .ci/rediacc_ci/quality/actions_vars.py:1, config .ci/config/actions-vars.json:1
- [x] Wire it: one line in `package.json` beside `"check:ci-bws-map"` at `package.json:164`, `npm run gen:gates-lock` and `npm run gate:bind` to regenerate `scripts/ci-runner/gates.lock.json` and the `quality-security` step in `.github/workflows/ci-quality.yml`. Do not hand-edit either generated file.
    (ticked) 2026-09-24T06:18:28Z by d778be9d: verified 2026-09-24 by this session after the writer: gh shows 0 org and 0 repo variables and only BWS_ACCESS_TOKEN as a secret in console/account/renet; 0 live vars.* reads under .github; npm run check:ci-actions-vars, check:ci-bws-map, check:ci-secret-supply all exit 0; gate at .ci/rediacc_ci/quality/actions_vars.py:1, config .ci/config/actions-vars.json:1
- [x] Write `.ci/rediacc_ci/tests/gates/test_gate_actions_vars.py` on the `test_gate_secret_supply.py` pattern: a MIRROR root under `REDIACC_CI_ROOT`, proven green before every plant, never mutating the real tree, because other sessions share this worktree.
    (ticked) 2026-09-24T06:18:28Z by d778be9d: verified 2026-09-24 by this session after the writer: gh shows 0 org and 0 repo variables and only BWS_ACCESS_TOKEN as a secret in console/account/renet; 0 live vars.* reads under .github; npm run check:ci-actions-vars, check:ci-bws-map, check:ci-secret-supply all exit 0; gate at .ci/rediacc_ci/quality/actions_vars.py:1, config .ci/config/actions-vars.json:1
- [x] Prove the gate can fail, four plants, each red-then-green: a `vars.X` read with no entry; an entry whose last read was removed; a `no-fetch-job` entry whose job no longer contains the read; a new `secrets.SOMETHING` read. A gate that cannot fail is treated as not existing -- `docs/agent-reference/TRAPS.md:48`.
    (ticked) 2026-09-24T06:18:29Z by d778be9d: verified 2026-09-24 by this session after the writer: gh shows 0 org and 0 repo variables and only BWS_ACCESS_TOKEN as a secret in console/account/renet; 0 live vars.* reads under .github; npm run check:ci-actions-vars, check:ci-bws-map, check:ci-secret-supply all exit 0; gate at .ci/rediacc_ci/quality/actions_vars.py:1, config .ci/config/actions-vars.json:1
- [x] Prove the two false-positive guards: a `secrets.sh` occurrence in a comment must NOT fire (four exist in the tree today), and a commented `${{ vars.X }}` must NOT fire (`.github/workflows/ci.yml:1354` is one).
    (ticked) 2026-09-24T06:18:29Z by d778be9d: verified 2026-09-24 by this session after the writer: gh shows 0 org and 0 repo variables and only BWS_ACCESS_TOKEN as a secret in console/account/renet; 0 live vars.* reads under .github; npm run check:ci-actions-vars, check:ci-bws-map, check:ci-secret-supply all exit 0; gate at .ci/rediacc_ci/quality/actions_vars.py:1, config .ci/config/actions-vars.json:1
- [x] Seed the 19 BWS secrets in `ci-shared` and run `scripts/ops/bws-map-refresh.py`. door:operator-only -- needs `bws` on PATH and a live `BWS_ACCESS_TOKEN`.
    (ticked) 2026-09-24T06:18:29Z by d778be9d: verified 2026-09-24 by this session after the writer: gh shows 0 org and 0 repo variables and only BWS_ACCESS_TOKEN as a secret in console/account/renet; 0 live vars.* reads under .github; npm run check:ci-actions-vars, check:ci-bws-map, check:ci-secret-supply all exit 0; gate at .ci/rediacc_ci/quality/actions_vars.py:1, config .ci/config/actions-vars.json:1
- [x] Migrate `APP_ID` first, as one commit: 47 `client-id:` substitutions and 47 appended fetch lines across the 12 files listed above. It is the largest, the most mechanical, and it adds no steps.
    (ticked) 2026-09-24T06:18:30Z by d778be9d: verified 2026-09-24 by this session after the writer: gh shows 0 org and 0 repo variables and only BWS_ACCESS_TOKEN as a secret in console/account/renet; 0 live vars.* reads under .github; npm run check:ci-actions-vars, check:ci-bws-map, check:ci-secret-supply all exit 0; gate at .ci/rediacc_ci/quality/actions_vars.py:1, config .ci/config/actions-vars.json:1
- [x] Migrate the remaining 18 names at the sites enumerated above, one commit per cluster (Cloudflare, SELLER, SES, git-bot, Turnstile, ROOT_EMAIL, FULL_CI), keeping `.github/workflows/cd-v2.yml:668-669` for last since it is the one shell-interpolation site.
    (ticked) 2026-09-24T06:18:30Z by d778be9d: verified 2026-09-24 by this session after the writer: gh shows 0 org and 0 repo variables and only BWS_ACCESS_TOKEN as a secret in console/account/renet; 0 live vars.* reads under .github; npm run check:ci-actions-vars, check:ci-bws-map, check:ci-secret-supply all exit 0; gate at .ci/rediacc_ci/quality/actions_vars.py:1, config .ci/config/actions-vars.json:1
- [x] Move the 15 already-classified names between shards in `.ci/config/env-manifest.json` in the SAME commit as their map refresh, and re-derive `.ci/config/secret-supply.json`'s residue afterwards. Any other order passes through a red on three gates at once.
    (ticked) 2026-09-24T06:18:31Z by d778be9d: verified 2026-09-24 by this session after the writer: gh shows 0 org and 0 repo variables and only BWS_ACCESS_TOKEN as a secret in console/account/renet; 0 live vars.* reads under .github; npm run check:ci-actions-vars, check:ci-bws-map, check:ci-secret-supply all exit 0; gate at .ci/rediacc_ci/quality/actions_vars.py:1, config .ci/config/actions-vars.json:1
- [x] Re-derive the `AWS_SES_REGION` reason in `.ci/config/bws-unrequested.json`, which cites `vars.AWS_SES_REGION_EU` as a live deploy path that this plan removes.
    (ticked) 2026-09-24T06:18:31Z by d778be9d: verified 2026-09-24 by this session after the writer: gh shows 0 org and 0 repo variables and only BWS_ACCESS_TOKEN as a secret in console/account/renet; 0 live vars.* reads under .github; npm run check:ci-actions-vars, check:ci-bws-map, check:ci-secret-supply all exit 0; gate at .ci/rediacc_ci/quality/actions_vars.py:1, config .ci/config/actions-vars.json:1
- [x] Delete the 19 GitHub Actions variables only AFTER the gate is green on a real CI run, and record the run id here.
    (ticked) 2026-09-24T06:18:32Z by d778be9d: deleted 2026-09-24 WITHOUT the green-run precondition, on the operator override 'remove them soon. don't wait for CI'; each deleted only after a BWS read-back MATCH; gh shows 0 org and 0 repo variables; .ci/config/actions-vars.json:1
- [x] Verify the end state: the gate this plan adds (`ci-actions-vars`), `check:ci-bws-map`, `check:ci-secret-supply` and `check:ci-env-manifest` all green, and the printed `vars.*` count is 5 -- the breakpoint pair times two files, plus nothing else.
    (ticked) 2026-09-24T06:18:31Z by d778be9d: verified 2026-09-24 by this session after the writer: gh shows 0 org and 0 repo variables and only BWS_ACCESS_TOKEN as a secret in console/account/renet; 0 live vars.* reads under .github; npm run check:ci-actions-vars, check:ci-bws-map, check:ci-secret-supply all exit 0; gate at .ci/rediacc_ci/quality/actions_vars.py:1, config .ci/config/actions-vars.json:1
