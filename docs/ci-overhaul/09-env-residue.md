# 09. Environment residue and the passthrough class (W8 P0 + P1 survey)

Measurement point: `HEAD = ac817a647`, branch `tooling-transformation-w0`, 2026-09-06. Every count below was re-derived from the tree and the live GitHub API on that date. Nothing here is quoted from a plan. Where a plan premise is contradicted, the contradiction is stated out loud rather than silently corrected.

**This phase performs NO cutover.** It is measurement only, because the passthrough drain is the highest outage risk in the programme and the only file that can carry a cutover (`.github/workflows/**`) has a single writer that is not W8.

Related: [08-driver-contract.md](08-driver-contract.md) section 2 (Bitwarden token schema) and
section 3 (single-writer lock table).

---

## 1. P0 — the shadow retirement at `7343ae9dc`, verified

The commit exists and is an ancestor of `HEAD`. `git show --stat 7343ae9dc` reports 28 files, `188 insertions(+), 1016 deletions(-)`.

| Claim | Verdict | Evidence |
|---|---|---|
| the comparator is deleted | TRUE | `git cat-file -e HEAD:.ci/scripts/ci/shadow-compare.sh` → absent |
| its fixture is deleted | TRUE | `git cat-file -e HEAD:.ci/config/shadow-expected-mismatches.json` → absent |
| its gate test is deleted | TRUE | `git cat-file -e HEAD:.ci/scripts/test/gates/test-shadow-compare.sh` → absent |
| the 45 org secrets are gone | TRUE, and then some | `gh api orgs/rediacc/actions/secrets` → `{"total_count":0,"secrets":[]}` |
| `mc_migrate_claude` is the sole credential path for CI and CD | TRUE | `gh api repos/rediacc/console/actions/secrets` → exactly `BREAKPOINT_TUNNEL_TOKEN`, `BWS_ACCESS_TOKEN`. All 8 environments (`edge`, `edge-{asia,eu,us}`, `stable`, `stable-{asia,eu,us}`) hold **zero** secrets. `BWS_ACCESS_TOKEN` is read at 74 sites; every other value is fetched through it. |
| the shadow step is gone from the workflows | TRUE | `grep -rn "SHADOW_NAMES\|SHADOW_EXPECTED_MISMATCH\|Compare shadow secrets" .github/` → no matches |

### Where the draft plan's premises are wrong

1. **"27 files are uncommitted."** Refuted, and refuted a second way than the first refutation.
Not only are they committed, the number is 28, and `git status --porcelain -- <each path>` is empty for every one of them. There is no uncommitted residue of `7343ae9dc` at all. (The working tree does hold 289 uncommitted paths, all of them other workstreams' in-flight work — `.ci/rediacc_ci/**` (W1), `.ci/media/**` (W10), `.claude/rediacc_hooks/**` (W5), `.ci/legacy/**` (W6). None
is W8's and none is shadow residue.)

2. **"P1 is the highest outage risk in the programme; exactly two agents, one green real deploy
between boxes."** The risk model is sized for a drain that no longer exists. Measured today the whole `workflow_call.secrets` class is **10 declarations**, of which **9 are the same irreducible bootstrap credential** and **1** is a cross-repo relay. See section 3. The "exactly two agents" and "one deploy between boxes" machinery has one item to spend itself on. That does not make
the item safe — it makes the ceremony disproportionate to the queue.

3. **`.ci/scripts/quality/bws-map-refresh.py` does not exist.** The task brief hedged this and
the hedge was right. The only reader of `bws-token-expiry.json` is `scripts/ops/bws-map-refresh.py:53`. `.ci/lib/bws-env.sh:66` merely *names* the path in an error string; it never parses it. This matters for driver-contract section 2's `scripts/dev` ordering, which puts W8's edits at the CURRENT path before W9 moves the directory.

---

## 2. P0b — `bws-token-expiry.json` restructured to `tokens[]`

`.ci/config/bws-token-expiry.json` now carries a top-level `warn_days: 5` (preserved byte-for-byte in value) and a `tokens[]` array whose single entry holds `name`, `expires`, `client_id_sha256`, `access`, `used_by`, `replacement_plan`.

The one reader, `scripts/ops/bws-map-refresh.py::warn_if_token_expiring`, was rewritten to match. New behaviour the array buys: the live `BWS_ACCESS_TOKEN` fingerprint now **selects** which entry's date is in force, instead of merely agreeing or disagreeing with the single date. A live token matching no declared entry short-circuits with a "DIFFERENT machine account" report and
prints no dates at all, because in that state every date in the file is about the wrong account.

**No CI gate reads this file** — `grep -rn "bws-token-expiry" scripts .ci/scripts package.json` returns only the reader's own line. That is the settled decision (08-driver-contract section 2) and this change does not reopen it.

Proof, 17 assertions, controls firing in both directions (`python3 <scratch>/prove_reader.py`, exit 0, `0 FAIL`):

- **fires**: the real committed file (`expires in 2 day(s) (2026-09-08)`); exactly `warn_days`
out; `expires in 0 day(s)`; `EXPIRED 3 day(s) ago`.
- **stays silent**: `warn_days + 1` out; +400 days; file absent; malformed JSON; empty
`tokens[]`; the OLD single-token schema (clean break — no dual code path).
- **fingerprint**: matching fp selects and warns; non-matching fp reports the wrong account and
suppresses every date; absent `client_id_sha256` prints the add-it note.
- **selection**: with two entries and no env token only the near one shouts and the far one is
not named; with an env token pinning the FAR entry the reader goes silent even though a near entry exists; pinning the NEAR entry shouts only about it.

End-to-end, `python3 scripts/ops/bws-map-refresh.py --dry-run` prints the warning on stdout and then dies on its real refusal (`✗ bws secret list exited 1: ... Missing access token`) on stderr — the warning is emitted before the failure it explains, which is the whole point.

---

## 3. P1 SURVEY — the complete passthrough class

Method: PyYAML 6.0.3 node parse of all 28 workflow files and 5 `action.yml` files, cross-checked
against raw `grep -rn`. No sampling.

### 3.1 `secrets: inherit` — zero, and banned

`grep -rn '^\s*secrets:\s*inherit\s*$' .github/` → **0 matches**. It is not an available simplification either: `.ci/scripts/quality/check-workflows.sh:101-105` bans the pattern outright ("Pass required secrets explicitly"). Any proposal to collapse the 14 caller mappings by switching to `inherit` must first delete that ban, and the ban is a least-privilege rule, not an accident.

### 3.2 `workflow_call.secrets` — 10 declarations across 9 callees

| Callee : decl line | Secret | `required` | read in callee body at |
|---|---|---|---|
| `cd-deploy-account.yml:19` | BWS_ACCESS_TOKEN | true | 70, 153 |
| `cd-deploy-worker.yml:26` | BWS_ACCESS_TOKEN | true | 46 |
| `cd-stage.yml:53` | BWS_ACCESS_TOKEN | true | 97 |
| `ci-build-docker.yml:32` | BWS_ACCESS_TOKEN | true | 199, 293, 500 |
| `ci-build-renet.yml:26` | BWS_ACCESS_TOKEN | true | 65, 192, 263, 349 |
| `ci-ops-test.yml:6` | BWS_ACCESS_TOKEN | true | 49 |
| `ci-quality.yml:101` | BWS_ACCESS_TOKEN | true | 132, 623, 671, 1221, 1518, 1707, 1882, 2015, 2233 |
| `ct-tests.yml:96` | BWS_ACCESS_TOKEN | true | 144, 200, 283, 451, 600, 753, 903, 1059, 1275, 1444, 1606, 1750, 1802, 1917 |
| `claude-review-reusable.yml:36` | BWS_ACCESS_TOKEN | **false** | 207 |
| `claude-review-reusable.yml:42` | **ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN** | **false** | **never — 0 reads** |

Three callees declare no secrets at all and are already at the target state: `ci-build-cli.yml`, `ct-install-methods.yml`, `ct-update-flow.yml`.

### 3.3 Caller passthroughs — 14 secret mappings across 18 call sites

All 18 in-repo `uses: ./.github/workflows/…` call sites, with the `secrets:` mapping line:

| Caller : `uses:` line | Callee | secrets mapping |
|---|---|---|
| `cd-v2.yml:413` | cd-deploy-worker | `:418` → `BWS_ACCESS_TOKEN:419` |
| `cd-v2.yml:429` | cd-deploy-account | `:433` → `BWS_ACCESS_TOKEN:434` |
| `cd-v2.yml:454` | cd-deploy-worker | `:459` → `BWS_ACCESS_TOKEN:460` |
| `cd-v2.yml:473` | cd-deploy-account | `:477` → `BWS_ACCESS_TOKEN:478` |
| `cd-v2.yml:535` | ct-install-methods | none |
| `ci.yml:492` | ci-quality | `:498` → `BWS_ACCESS_TOKEN:499` |
| `ci.yml:748` | ci-build-renet | `:753` → `BWS_ACCESS_TOKEN:754` |
| `ci.yml:766` | ci-build-docker | `:775` → `BWS_ACCESS_TOKEN:776` |
| `ci.yml:785` | ci-build-docker | `:795` → `BWS_ACCESS_TOKEN:796` |
| `ci.yml:805` | ci-build-cli | none |
| `ci.yml:820` | ct-update-flow | none |
| `ci.yml:914` | cd-stage | `:928` → `BWS_ACCESS_TOKEN:929` |
| `ci.yml:944` | ct-tests | `:966` → `BWS_ACCESS_TOKEN:967` |
| `ci.yml:988` | ci-ops-test | `:989` → `BWS_ACCESS_TOKEN:990` |
| `ci.yml:1466` | ct-install-methods | none |
| `claude-review.yml:88` | claude-review-reusable | `:95` → `BWS_ACCESS_TOKEN:96` — **does not pass ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN** |
| `promote-stable.yml:165` | cd-deploy-worker | `:170` → `BWS_ACCESS_TOKEN:171` |
| `promote-stable.yml:177` | cd-deploy-account | `:181` → `BWS_ACCESS_TOKEN:182` |

Cross-repo callers, declared in `.github/external-callers.yml:22-34` and verified against the checked-out submodules:

| Caller | line | passes |
|---|---|---|
| `private/account/.github/workflows/claude-review.yml` | `:42` uses `rediacc/console/…/claude-review-reusable.yml@main` | `:54` `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}` — and **no** `BWS_ACCESS_TOKEN` |
| `private/renet/.github/workflows/claude-review.yml` | `:42` same | `:54` same |

### 3.4 `workflow_call.inputs` — 51 declarations, 0 dead

Every one of the 51 input declarations is referenced at least once as `inputs.<name>` in its own callee body. There are no dead input declarations. Two callers deliberately omit an optional input and take the default (`cd-v2.yml:535` omits `docker_tag`; `ci.yml:766` omits `test_images_only`), and both submodule callers omit `model`. Only **2 of 70** caller `with:` values are
relay-shaped (`claude-review.yml:91` `pr_number`, `:94` `model`, each relaying the caller's own `workflow_dispatch`/`workflow_call` input); the other 68 are literals or `needs.*.outputs`.

### 3.5 Composite-action inputs — the largest population, and 100% irreducible

| Action | inputs | call sites |
|---|---|---|
| `.github/actions/bws-secrets/action.yml` | `access-token:48` (required), `secrets:54` | **60**, every one passing `access-token: ${{ secrets.BWS_ACCESS_TOKEN }}` verbatim |
| `.github/actions/app-token/action.yml` | `client-id:7`, `private-key:10`, `preset:13`, `repositories:33` | **50** (29 pass `preset`, 21 take the `readonly` default) |
| `.github/actions/setup-workspace/action.yml` | `node-version:19`, `account:23`, `natives:31`, `build-packages:40` | **27** |
| `.github/actions/profiler/action.yml` | `interval:25`, `strict:33`, `runner-label:48` | **6** |
| `.github/actions/profiler/nest-probe/action.yml` | `interval:16`, `runner-label:20` | 2 |

`60 (composite) + 14 (caller mappings) = 74`, which is exactly the `grep -c 'secrets\.BWS_ACCESS_TOKEN'` total. The class closes.

**The 60 `access-token:` lines cannot be removed by any refactor.** GitHub does not expose the `secrets` context inside a composite action, so a composite that needs a credential must take it as an input from the workflow. This is the single largest passthrough population in the repo and it is irreducible by construction, not by choice.

---

## 4. Irreducible vs pure relay

**Irreducible (do not attempt to drain):**

- 9 × `BWS_ACCESS_TOKEN` `workflow_call.secrets` declarations and their 14 caller mappings. The
callee genuinely reads it (reference lines in 3.2), and it is the one credential that cannot come from Bitwarden because it is the credential that opens Bitwarden (`.github/actions/bws-secrets/action.yml:48-52`: "the ONE credential that stays in GitHub"). A called workflow receives no secret it is not explicitly passed, and `secrets: inherit` is banned (3.1). There is no shorter
form.
- 60 × `bws-secrets` `access-token:` — no `secrets` context in composite actions (3.5).
- 51 × `workflow_call.inputs` — all live (3.4).

**Pure relay — exactly one item in the whole graph:**

- `claude-review-reusable.yml:42` `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`. Declared, **never read**.
The callee fetches the same value from Bitwarden instead (`:209` maps it into `BWS_ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`, consumed at `:310` as `env.`). The in-repo caller does not pass it. The only things that pass it are the two cross-repo callers, into a parameter whose value goes nowhere.

That is the entire drain: **1 declaration, 2 caller lines, 2 manifest rows.** The 57 sibling declarations this class used to hold were removed in one sweep on 2026-09-06 and the arm that catches them is now permanent (`.ci/scripts/security/check-workflow-gates.sh:262-269`, "a reusable workflow may not DECLARE a secret nothing in it reads"), with this one pair recorded as its sole
exemption at `:270-276`.

---

## 5. The cutover order

### The rule, and the one place it inverts

The programme rule is: **a cutover deletes the callee declaration AND its caller passthroughs in ONE commit.** That holds for same-repo callers, which move with their callee.

**It cannot hold for a cross-repo caller, and the only remaining item is one.** A caller that passes a secret the callee does not declare is a hard contract violation — it is what `check-workflow-gates.sh` CHECK 2 exists to refuse (`:33`, "a caller may not pass a secret/input the callee never declares"), and cross-repo callers resolve `@main` at run time, so a console-only deletion
breaks *their* next run an hour later rather than this PR. So the order inverts: **caller first, callee second.**

### Box order

**Box 1 — submodule PRs (2, concurrent).** Delete the passthrough line only.
- `private/account/.github/workflows/claude-review.yml:54`
- `private/renet/.github/workflows/claude-review.yml:54`

Safe in isolation: the callee still declares the secret as `required: false`, so a caller that stops passing it is valid. Merge both. Each repo's own `claude-review` run on its next PR is the green proof; no console deploy is involved.

**BLOCKED, measured 2026-09-09. Do not run Box 1 or Box 2 as written.** Deleting the declaration leaves the two external callers with NO token path at all, so their reviews run unauthenticated. `claude-review-reusable.yml:343` consumes `env.BWS_ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`, and the step that sets it (`:234-242`) carries `if: ${{ github.repository == 'rediacc/console' }}`. For
a reusable workflow called from another repo, `github.repository` is the CALLER's, so that step is skipped and the env var is empty. `7343ae9dc` (2026-09-05) flipped `:343` from `secrets.ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` to the env form and left the guard behind, so account and renet have been reviewing with a blank credential since that commit; the passed secret is unread not
because it was migrated for them, but because their branch of the migration was never written. They cannot pass `BWS_ACCESS_TOKEN` either, which is exactly why it is `required: false` at `:36-41`.

The fix restores the read instead of deleting it, which also drains the exemption because a read declaration is not a declared-unused one:

```yaml
# .github/workflows/claude-review-reusable.yml:343
          claude_code_oauth_token: ${{ env.BWS_ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN || secrets.ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN }}
```

Console runs take the env value (the fetch step ran); external callers take the secret they already pass. `DECLARED_UNUSED_OK` then drains to empty with no submodule PR and no registry edit. Proven on a scratch copy of the real tree on 2026-09-09: CHECK 2 and CHECK 4 both green, `arm (a3): 0 declared-unused exemption(s) == 0 pinned alive by 2 external-caller entries`.

**And the registry entries must SURVIVE.** Deleting them, as the plan box words it, empties `callers:`, which CHECK 4 and arm (a3) both treat as blind and fail on (reproduced: rc=1, "declares no callers"). Only the two `passes_secrets` ROWS may go, and only if the callers really stop passing the value. The list below is the original Box 2 and is kept for the shape of the work, not
as an instruction.

**Box 2 — console, one commit, after both submodule PRs are on `main`.**
- delete `claude-review-reusable.yml:42` and its comment block `:43-49`
- delete the `DECLARED_UNUSED_OK` exemption `.ci/scripts/security/check-workflow-gates.sh:293-299`
(an exemption naming a declaration that is gone is itself refused by the arm below it, and since 2026-09-09 also by arm (a3), which requires every exemption to be pinned alive by a real `.github/external-callers.yml` entry). The list is a LIST converted to a set at `:300` precisely so draining it to empty stays valid Python.
- delete the two `passes_secrets: [ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN]` rows in
`.github/external-callers.yml:28,34`
- update the prose that names the pair: `.ci/scripts/quality/check_secret_reachability.py:7`
(module docstring), `:100` (a closed `KNOWN_UNREACHABLE` comment) and `:224` (a generated note). None of these is a live coupling — they are comments — but leaving them turns a deleted declaration into archaeology that reads as current.

Green proof: `check:ci-workflow-gates` (CHECK 2 and CHECK 4, which verifies each external caller against its real file when the submodule is checked out) plus one real `claude-review` run from each submodule against the new `@main`.

**There is no Box 3.** Everything else in section 3 is irreducible.

### The release window this must avoid

Deleting a passthrough is a workflow-graph edit, so it must not land while a release is resolving `@main`:

| Window (UTC) | What runs |
|---|---|
| 01:00 – ~02:00 | `ci.yml` nightly cron `'0 1 * * *'` |
| 03:00 | `housekeeping.yml` cron `'0 3 * * *'` |
| 06:00 – ~07:00 | `promote-stable.yml` cron `'0 6 * * *'` — **production**, calls `cd-deploy-worker`/`cd-deploy-account` at `:165`/`:177` |
| any merge to `main` | `cd-v2.yml` "Release to Edge" is dispatched from CI's finalize job (`workflow_dispatch`, not `workflow_run` — `cd-v2.yml:7-14`), so every merge opens an edge-deploy window |

Land Box 2 outside those, and let the following CI-to-edge cycle go green before anything else in W8 moves.

---

## 6. `secrets.X` reads outside the allowlist today

The allowlist is `ALLOWED` in `scripts/gates/check-secret-scope.ts:71-76`: `GITHUB_TOKEN`, `BWS_ACCESS_TOKEN`, `BREAKPOINT_TUNNEL_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`.

**Count today: 1.** `npx tsx scripts/gates/check-secret-scope.ts` → exit 0, `✓ secret scope: 1 org-scope read(s) frozen, none added`. The one entry is `watchdog-monitor.yml:CLOUDFLARE_API_TOKEN` (`.ci/config/secret-scope-baseline.json`, read at `.github/workflows/watchdog-monitor.yml:139`), frozen shrink-only with a stated goal state of an empty list.

Full read census across `.github/workflows` and `.github/actions`, 88 references:

| Name | refs | exists? |
|---|---|---|
| `BWS_ACCESS_TOKEN` | 74 | yes — repo secret on `rediacc/console` |
| `BREAKPOINT_TUNNEL_TOKEN` | 3 | yes — repo secret |
| `GITHUB_TOKEN` | 2 | built-in, minted per run |
| `CLOUDFLARE_API_TOKEN` | 1 | **NO** — resolves to `""` (this is the baselined entry) |
| `CLAUDE_CODE_OAUTH_TOKEN` | 1 | **NO on this repo** — see finding F1 |

**The count is 1 only because the allowlist forgives F1.** Correct the allowlist to the measured truth and it is 2.

---

## 7. Findings

### F1 — the watchdog's tier-2 classifier authenticates as nobody (P1 blocker, not W8's to fix)

`.github/workflows/watchdog-monitor.yml:161` reads `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}`, and the comment directly above it at `:159-160` asserts:

> `CLAUDE_CODE_OAUTH_TOKEN` is repo-scoped and survives the org deletion, so this read is live,
> not empty.

Measured against the live API on 2026-09-06, that is false for this repository:

```
$ gh api repos/rediacc/console/actions/secrets -q '.secrets[].name'
BREAKPOINT_TUNNEL_TOKEN
BWS_ACCESS_TOKEN
```

`CLAUDE_CODE_OAUTH_TOKEN` exists on `rediacc/renet`, `rediacc/account` and `rediacc/elite` — not on `rediacc/console`, which is where `watchdog-monitor.yml` runs. `gh api orgs/rediacc/actions/secrets` returns `total_count: 0`, and all 8 environments hold zero secrets, so there is no other scope it could resolve from. `scripts/gates/check-secret-scope.ts:49` records the same wrong
reason ("repo-scoped on renet/account/elite") as the justification for allowlisting it.

Consequence: the watchdog's tier 1 (`CLOUDFLARE_API_TOKEN`) is already known-empty and baselined,
and tier 2 is empty too. **Both classifier tiers are dead**, so every CI failure falls through to `WATCHDOG_RETRY_ALLOWLIST_PATTERNS` — which is precisely the "a judgment nobody made decided whether to spend a ~500-machine-minute retry" outcome the comment at `:142-147` says the second provider exists to prevent. This is the same failure class as `7343ae9dc` itself: a
successful-looking call that authenticates as nobody.

Door: `.github/workflows/**` has a single writer that is not W8 (08-driver-contract section 3),
so this is handed to the driver rather than fixed here. The fix is a decision, not a patch: either add `CLAUDE_CODE_OAUTH_TOKEN` as a repo secret on `rediacc/console` (operator-only), or fetch it from Bitwarden — which `watchdog-monitor.yml:153-158` argues against, because a bws step ahead of the monitor can take the monitor down, as it did on 2026-09-03 in run 33704079162.

### F2 — a green line that describes machinery that no longer exists

`check:ci-bws-map` prints, exit 0:

> `✓ shadow triple: SHADOW_NAMES, GH_* and BWS_* name the same set in all 19 shadowed file(s)`

No workflow contains a `SHADOW_NAMES` key any more (section 1). Reading `.ci/scripts/quality/check_bws_map.py:616-650`, `checked` counts files where `shadow or gh or bws` is non-empty, and `bws` (fetch targets) is non-empty in 19 files — so the count is real, but three of the assertion's four sub-checks (`shadow - gh`, `gh - shadow`, `shadow - bws`) are now permanently empty. Only
the fourth, `bws - shadow - consumed` (fetched, never compared, never used), still carries load. The printed sentence claims a set equality that no file can violate. Not vacuous, but it reads as more than it is.

### F3 — `check_bws_map.py` still points at a deleted file

`.ci/scripts/quality/check_bws_map.py:489`: `EXPECTED_MISMATCH_LEDGER = ROOT / ".ci" / "config" / "shadow-expected-mismatches.json"`. That file was deleted in `7343ae9dc`. Assertion 12 is written to survive it — with nothing excusing a mismatch it returns `[], 0, 0` (`:526-530`) — so it is inert rather than broken. It is dead scaffolding whose only remaining effect is to make a
reader believe the ledger exists.

### F4 — `docs/agent-reference/suppressions.md:47` documents a deleted suppression as live

The row describes `.ci/config/shadow-expected-mismatches.json` and "the `Compare shadow secrets against GitHub` step in every workflow" in the present tense. Both are gone. The row's own text ends "**Temporary**: deleted with the org secrets, along with the rest of the shadow" — the org secrets are at zero, so its own condition for deletion is met. `check:ci-suppression-liveness`
runs 12 probes and none covers this row, so nothing catches it. W11 owns that file.

### F5 — `scripts/ops/derive-shadow-pass-list.sh` is the dead script section 2 of the driver contract assigns to W8

Its stated purpose (`:1-13`) is to derive, from shadow-compare verdicts in CI run logs, which org secrets are safe to delete. The compare step no longer exists and `gh api orgs/rediacc/actions/secrets` returns `total_count: 0`. `git grep -n "derive-shadow-pass-list"` finds no caller anywhere except one prose mention at `docs/ci-overhaul/06-progress.md:6621`. 08-driver-contract
section 2 sequences this as "W8 deletes its dead script, W0 and W8 make their edits at the current path, THEN W9 moves the directory" — so the deletion is W8's and it must land BEFORE W9 touches `scripts/dev/`. Not deleted here: it falls outside the file set this phase owns.

### F6 — `.ci/scripts/housekeeping/retire-shadowed-secrets.py` survives its purpose

15 KB of machinery that strips `GH_<NAME>` lines and `SHADOW_NAMES` entries. Neither pattern occurs in any workflow. It is still load-bearing for two gates that use it as a subject — `.ci/scripts/test/gates/test-vacuity-floors.sh:98-104` and `scripts/gates/check-enumeration-vacuity.ts:15,64,166` — so it cannot simply be deleted; those two would have to be re-keyed to another
subject in the same change. Recorded so the deletion is not attempted as a one-liner.

### F7 — CLAUDE.md's account-key instruction is stale

The `RDC_RENET_LICENSE=1` section states `ACCOUNT_ED25519_PUBLIC_KEY` "already exists as an **organisation secret** … Verify with `gh api orgs/rediacc/actions/secrets`". That command now returns `{"total_count":0,"secrets":[]}`. The value lives in Bitwarden and reaches CI through `BWS_ACCESS_TOKEN`. W11 owns CLAUDE.md.

### F8 — `check:ci-python-lint` is red on `main`, and not from anything W8 touched

```
✗ .claude/rediacc_hooks/proc.py has a shebang but git mode is 100644 (EXE001 in CI)
✗ .claude/rediacc_hooks/run_tests.py has a shebang but git mode is 100644 (EXE001 in CI)
✗ .claude/rediacc_hooks/shellscan.py has a shebang but git mode is 100644 (EXE001 in CI)
```

All three are W5's uncommitted new files (`git status --porcelain` shows ` A ` for each). The ruff half of the same gate passes on 127 files including `scripts/ops/bws-map-refresh.py`. Fix is `git update-index --chmod=+x` on the three, which is W5's to run. This is the same class as the `ac817a647` commit already on `main` ("restore +x on two gate scripts I stripped").

### F9 — the gate that exists to catch F1 is green from a snapshot taken before the deletion

`check:ci-secret-reachability` exists to refuse "a workflow references a secret its repository cannot read". It runs green:

```
$ npm run check:ci-secret-reachability            # exit 0
6 secret reference(s) across 3 repo(s) are all reachable (controls fired in both directions)
```

It reads `.ci/config/secret-reachability.json`, whose `refreshed_at` is **2026-09-02T14:06:16Z** — three days BEFORE the 45 org secrets were deleted on 2026-09-05. Its one guard against that, `MAX_BASELINE_AGE_DAYS = 45` (`check_secret_reachability.py:55`), leaves the record admissible until 2026-10-17.

The six references it checks (`references()` per repo, measured) against live API truth:

| Repo | Secret | Snapshot says | Live API says |
|---|---|---|---|
| console | `BWS_ACCESS_TOKEN` | reachable, `via: repo` | correct — repo secret |
| console | `BREAKPOINT_TUNNEL_TOKEN` | reachable, `via: repo` | correct — repo secret |
| console | `CLOUDFLARE_API_TOKEN` | reachable, `via: org:selected` | **WRONG** — org holds 0 secrets |
| console | `CLAUDE_CODE_OAUTH_TOKEN` | reachable, `via: repo` | **WRONG** — console's repo secrets are exactly `BREAKPOINT_TUNNEL_TOKEN`, `BWS_ACCESS_TOKEN` |
| account | `CLAUDE_CODE_OAUTH_TOKEN` | reachable, `via: repo` | correct |
| renet | `CLAUDE_CODE_OAUTH_TOKEN` | reachable, `via: repo` | correct |

Two of six are wrong, and they are precisely the two dead reads of section 6. The snapshot also still asserts ~30 further console names reachable `via: org:selected`, every one of which is now false. **This is why F1 went unnoticed:** the instrument built to catch it is answering from a record of the world as it was before the change.

Not refreshed here, deliberately. `npm run check:ci-secret-reachability -- --refresh` (needs an org-admin token; this session's `gh` has `admin:org`) would write the truth and turn the gate **red with two real findings** — the correct end state, but a tree-wide red during a twelve-workstream programme is a packaging decision for the driver, not a survey phase's to make
unilaterally. Recommended default: refresh in the SAME change that resolves F1, so the gate flips from lying-green to telling-the-truth-green rather than sitting red between two commits.
