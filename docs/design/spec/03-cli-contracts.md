# P0 Spec 03 — CLI Command Contracts (the P4 execution contract)

Companion to `docs/design/06-cli-reshape.md` (the mapping decision file). Where 06 decided,
this file follows it exactly; where 06 was thin, the decision is made here and marked
`[P0-DECIDED]`. This file is deliberately exhaustive: it is the mechanical contract P4
implements, leaf by leaf.

Verified code anchors used throughout:

- `outputService` (class `OutputService`, exported singleton) —
  `packages/cli/src/services/core/output.ts:273`; `print(data, format)` at line 231;
  JSON envelope shape at `formatJson` (line 119): `{success, command, data, errors,
  warnings, metrics}`. Error envelope: `outputJsonError` in `packages/cli/src/utils/errors.ts`.
- `EXIT_CODES` — `packages/cli/src/types/index.ts:75` (0..9 today).
- `RENET_LICENSE_REQUIRED_EXIT_CODE = 10` —
  `packages/cli/src/services/renet/renet-license-contract.ts:1`, consumed by the recovery
  framework in `packages/cli/src/services/executor/local-executor.ts:744`.
- Command policy metadata (`grandGuard`, `forkBlocked`, `agentBlocked`, `mcp`,
  `mcpExcludeReason`) — `packages/cli/src/config/command-metadata.ts:28-39`, enforced by
  `packages/cli/src/utils/command-policy.ts` (`REDIACC_ALLOW_GRAND_REPO`,
  `REDIACC_ALLOW_CLUSTER_OPS`, ancestry-verified).
- Global program options — `packages/cli/src/cli.ts:136-141`
  (`-o/--output`, `--config`, `-l/--lang`, `-q/--quiet`, `-y/--yes`, `--fields`) plus the
  output-format precedence rule (`REDIACC_DEFAULT_OUTPUT` env, auto-JSON for non-TTY/agent).

Leaf count (RESOLVED by gate ruling R2, `00-gate-review.md`): the tree-as-drawn is the
contract. Enumerating 06 §1 exactly (plus the `machine infra` subtree that 06 §2 moves
but §1 forgot to draw — finding U1) yields **153 target leaves**, accepted as the P4
contract; the "~90" prose figure is retired as wrong arithmetic (README/06 drop it in
the as-built pass). The honest simplification claim: 162 current → 153 target with the
DAILY surface consolidated (config 57 → 25, repo plumbing under `repo admin`, five
backup surfaces unified).

---

## 1. Program-wide exit-code table (R2-F15) — defined FIRST, deviations marked per verb

Codes 0-9 are today's `EXIT_CODES` (`packages/cli/src/types/index.ts:75`), kept with their
meanings so nothing that scripts against the current CLI breaks by renumbering. Code 10
adopts the renet `LICENSE_REQUIRED` precedent verbatim. Codes 11-15 are new, one per
refusal class the redesign introduces. `[P0-DECIDED]` for 11-15 and for the sharpened
meanings of 4, 6, 14.

| Code | Name | Meaning | Retryable |
|---|---|---|---|
| 0 | `SUCCESS` | Command succeeded. Includes contractual no-ops (attach when already attached; detach when not attached; `repo down` when already down). The JSON payload says whether work happened (`data.noop: true`). | n/a |
| 1 | `GENERAL_ERROR` | Unclassified failure. A leaf exiting 1 where a specific code exists is a bug. | no |
| 2 | `VALIDATION` | Bad input the user can fix without touching infrastructure: unknown flag, missing required flag, name-grammar violation (`:`/`@` in a name), both placement flags at once, create-on-existing, `--tag base`, k8s repo without `--datastore`. Matches Commander's own usage-error exit. | no |
| 3 | `AUTH_REQUIRED` | Missing/invalid token or master password. | no |
| 4 | `GUARD_REFUSAL` | A policy guard refused: `grandGuard` (agent on a grand repo), `agentBlocked`, cluster-ops family without `REDIACC_ALLOW_CLUSTER_OPS`, mutation-gate precondition (`--current`/`--rotate-secret`) not met. Was `PERMISSION_DENIED`; guard refusals are its only remaining producer in the local adapter. | no |
| 5 | `NOT_FOUND` | Named resource does not exist in config or on the machine (repo, machine, datastore, cluster, strategy, snapshot, backup artifact). Remove/delete on a missing name exits 5. | no |
| 6 | `NETWORK` | Transport-level infrastructure failure: SSH unreachable, DNS, connection timeout, account-server unreachable. The operation did NOT run. | yes |
| 7 | `API_ERROR` | Account-server API error (non-auth 4xx/5xx). | yes |
| 8 | `PAYMENT_REQUIRED` | Subscription/usage limit. | no |
| 9 | `RATE_LIMITED` | Back off and retry. | yes |
| 10 | `LICENSE_REQUIRED` | Renet exited 10 (license missing/invalid on the target machine) and the CLI's recovery flow could not resolve it. Propagated, never remapped. | no |
| 11 | `AMBIGUOUS` | A name resolution needed a guess and refused (06 §6: "ambiguity is always an error listing candidates, never a guess"). The error payload and stderr list every candidate. Includes the `term connect` repo-vs-place collision (R2-F11). | no |
| 12 | `STATE_MISMATCH` | The config's derived answer contradicts either the user or the machine: `@place` contradiction (R2-F10), derived-routing verification failure (state bucket says machine M mounts the datastore but M does not — R2-F2), attach-state conflicts. The message always names both sides and the repair verb (`rdc config reconcile`, `repo migrate`, or `backup restore`). | no |
| 13 | `HEALTH_GATE_FAILED` | The operation's data/infra phase succeeded but the post-`up()` health gate failed (repo/cluster migrate, fork `--up`, rehearse, restore `--up`). Payload states the rollback disposition (source intact / fork kept for inspection). | no |
| 14 | `INFRA_FAILED` | The remote operation ran and failed: renet non-zero (other than 10), OpenTofu/provisioning failure, fencing failure, transfer failure. Distinct from 6 (never reached) and 13 (infra fine, app unhealthy). | no |
| 15 | `BUSY` | The operation conflicts with one already running: `backup run` while a run is active (payload carries the running id — R2-F15's worked example), a held file lock, a concurrent migrate on the same subject. | after the blocker finishes |

Deviations (exhaustive; every other leaf uses the table as-is):

- `rdc run` (hidden), `rdc repo exec`, `rdc term connect -c` — propagate the REMOTE
  command's exit code verbatim (ssh semantics). The table applies only to failures that
  happen before the remote command runs.
- `rdc doctor` — exits 1 if any check fails (diagnostic convention; payload has per-check detail).
- `rdc update --check-only` — always exits 0 when the check itself succeeds; availability
  is data, not an error.
- Commander usage errors (unknown command/flag) exit 2 via Commander itself; identical to
  `VALIDATION` by design.

Exit-code layering with the Rediaccfile `health()` protocol (gate ruling C5): hook-level
codes are a SEPARATE namespace that never propagates to the CLI surface. `health()`
returns 0 = healthy, **75 (EX_TEMPFAIL) = warming up, retry**, any other nonzero =
unhealthy (gate fails immediately), and **42 is reserved** (the executor's
function-not-defined sentinel — a user `health()` must never return it). The gate caller
retries 75s within the window (per-attempt timeout 30 s, window default 300 s — flags in
§5 per G6) and maps its FINAL verdict to CLI exit 13. Full contract: spec 05 §6 + spec
02 `HealthReport`.

RepoRuntime sentinel → CLI exit-code mapping (gate gap G1, `[P0-DECIDED]` here, spec 02
concurs):

| RepoRuntime sentinel | CLI exit | Rationale |
|---|---|---|
| `ErrHoldersPresent` | 14 `INFRA_FAILED` | the remote op ran and refused: loop/dm/volume holders still present (03 hygiene rule 1, no lazy-success) |
| `ErrWrongRuntime` | 12 `STATE_MISMATCH` | config placement and the on-datastore descriptor disagree about the repo's world; reconcile-suggestion message |
| `ErrRoleViolation` | 2 `VALIDATION` | the verb is illegal for the record's role (promote a non-fork, autostart a rehearsal fork); user fixes the ref |
| `ErrNotDeployed` | 5 `NOT_FOUND` | the subject does not exist where the verb needs it |

JSON error envelope: every nonzero exit under `-o json` writes the error envelope from
`utils/errors.ts` (`{success:false, command, data:null, errors:[{code, message, details?,
retryable, guidance, next?}], warnings, metrics}`) to stdout. The `errors[].code` string
mirrors the exit-code name above (`VALIDATION`, `AMBIGUOUS`, ...) so scripts can switch on
either. `[P0-DECIDED]` P4 extends `ERROR_CODES` in `packages/cli/src/types/errors.ts`
with the new names and maps them in `httpStatusToExitCode`'s sibling
`errorToExitCode` logic.

---

## 2. Addressing grammar: `repo[:tag][@place]`, positional names, derived machine

### 2.1 Grammar

```
ref        := name [ ':' tag ] [ '@' place ]
name       := label            (the repo / datastore / machine / cluster / storage name)
tag        := label            (fork tag; datastores reuse the same fork-tag grammar)
place      := label            (a machine OR cluster name; one shared namespace at parse
                                time, disambiguated against config, collisions refused
                                at CREATE time for machine-vs-cluster only — see 2.4)
label      := /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/
```

- `[P0-DECIDED]` label charset is an RFC-1123 DNS label (lowercase alphanumerics and
  hyphen, max 63, no leading/trailing hyphen). Rationale: repo names become auto-route
  subdomains and k8s namespace names today; anything looser leaks into DNS and k8s object
  names. `:` and `@` are structurally forbidden by the grammar (06 §6.4). Create-time
  validation enforces this for every noun (`machine add`, `repo create`, `datastore
  create`, `cluster create`, `storage add`, `backup strategy set`, fork `--tag`
  values). Exit 2 with the offending character named.
- v3 migration behavior for pre-existing nonconforming names (uppercase, underscore,
  dots): migrated as-is with a one-time warning; every NEW create enforces. Renames do
  not exist (R2-F4), so nonconforming legacy names die by delete + re-add.
- `[P0-DECIDED]` **Reserved tag `base`**: config v3's structural tags
  (`repositories: Record<name, {tags: Record<tag, RepoRecord>}>`, 02 §11.3) need a key
  for the birth record. The reserved tag is `base`; the bare ref `shop` is exactly
  `shop:base`. `--tag base` (and `:base` collisions at fork) are refused, exit 2:
  "base names the original repository; pick another tag." The `latest` magic default is
  retired with no replacement (R2-F5); `latest` becomes an ordinary, legal tag.
  Gate reconciliation with spec 04 (`00-gate-review.md` §3, both refinements sanctioned):
  `base` is the CLI-level reserved ALIAS for the grand record; the STORED key of that
  record is per-repo data (spec 04: `main` on fresh creates, migrated v2 grands keep
  their literal `latest` key). Resolution goes through the record's grand pointer, never
  by comparing the string `base` against stored keys.
- Parsing is data-driven off the v3 schema, not string-splitting: the parser produces
  `{name, tag?: string, place?: string}` and every resolver consumes the struct.

### 2.2 Positional primary name (per-noun migration)

The first positional argument of every leaf is the noun's primary name; `--name` dies
tree-wide (06 §6.1). Concretely:

| Noun | Positional | Example |
|---|---|---|
| repo verbs | `<repo-ref>` = `repo[:tag][@place]` | `rdc repo up shop:test` |
| machine verbs | `<machine>` | `rdc machine status prod-1` |
| datastore verbs | `<datastore-ref>` = `ds[:tag]` | `rdc datastore attach ds-alpha:exp --to m2` |
| cluster verbs | `<cluster>` (join/evict take `<machine>`) | `rdc cluster fork prod --tag staging` |
| backup verbs | `<strategy>` or `<artifact-ref>` per leaf | `rdc backup run nightly -m prod-1` |
| storage verbs | `<storage>` (`import` takes `<file>`) | `rdc storage browse s3-main` |
| config verbs | config-file name where applicable | `rdc config delete staging` |
| term | `<target>` = `place` or `repo-ref` | `rdc term connect shop@prod-1` |

MCP/agent schemas stay named-parameter (06 §6.4): the MCP tool factory maps its `name`
(or `repoArg`) field onto the positional; nothing in the MCP surface changes shape.

The docs validators `positional-cli-detector` and `validate-cli-examples` flip to the new
grammar in P4 (06 §6.6).

### 2.3 Derived-machine resolution algorithm (R2-F2) — normative

`-m/--machine` disappears from repo verbs. Every repo verb resolves its execution machine
as follows. Steps are ordered; the first failure stops with the exit code shown.

1. **Parse** the ref → `{name, tag=base, place?}`. Grammar violation → exit 2.
2. **Look up** `repositories[name].tags[tag]` in the active config. Missing name or tag →
   exit 5, message lists the tags that DO exist for the name (candidate rule).
3. **Read placement** (the R2-F1 tagged union): `placement: {datastore: D} | {machine: M}`.
   - `{machine: M}` arm → candidate machine is `M` (the machine's implicit default
     datastore; it never appears in the datastore registry).
   - `{datastore: D}` arm → look up `D` in the datastore registry (exit 5 if gone —
     that is a config-integrity error naming the repo that references it), then read
     `state.datastores[D].attachedTo` from the `state` bucket.
     - No attach record → exit 12: "datastore D is not attached to any machine. Attach
       it: `rdc datastore attach D --to <machine>` (or `rdc config reconcile` if it is
       attached but the config does not know)."
4. **`@place` check** (only if the ref carried one): if `place` equals the candidate
   machine (or the cluster that machine belongs to), accept as redundant confirmation.
   Otherwise exit 12 with the R2-F10 teaching error (§3.2). Never retarget.
5. **Verify before executing** (state is a ROUTING HINT, not truth): issue the cheap
   mount check on the candidate machine (renet: datastore/dsdefault mounted at the
   expected path with the expected identity). Mismatch → exit 12:
   "config says <D> is attached to <M>, but <M> does not mount it. Run
   `rdc config reconcile`, then retry." A `config recover` that restored stale attach
   state degrades to this error, never to a wrong-host deploy.
6. Execute on the verified machine.

Read-only verbs (`status`, `list`, `log`, `diff`, `cat`, `logs`, `secret get/list`)
perform steps 1-4 and SKIP step 5's remote round-trip only when the verb itself is about
to talk to the same machine anyway (the operation's own failure is the verification);
purely config-local reads (`repo list` without a machine filter, `secret list`) never
verify. `[P0-DECIDED]`

### 2.4 Namespaces and collisions

- Machine names and cluster names share the "place" namespace: `config` refuses creating
  a cluster whose name collides with a machine and vice versa, exit 2 (06 §6.3).
- Repo names are NOT globally checked against place names (06 §6.4c rejected the global
  tax). The one verb where both namespaces meet — `term connect <bare-name>` — errors at
  collision time, exit 11, demanding qualification (§3.3).
- Repo names unique per config; placement single-valued (06 §6.5). A pushed copy on
  another machine is a **backup artifact**, not a second live repo, until
  `backup restore` or `repo promote` gives it a live name. "Same name running in two
  places" is retired behavior.

---

## 3. `@place` — per-verb acceptance table (R2-F10) and the conflict rule

### 3.1 Acceptance table

`@place` has exactly three legitimate referent classes (06 §6.4b): backup artifacts,
`term connect` targets, and redundant confirmation on live refs. `--to`/`--from`/`--on`
destinations take a BARE place name (no `@` sigil — they are flags, not refs).

| Verb(s) | `@place` on the positional ref | Meaning |
|---|---|---|
| `backup restore <artifact-ref>` | **required referent** | which machine/storage holds the artifact (`shop:nightly@backup-1`) |
| `backup list [artifact-ref]` | optional filter | narrow listing to one place |
| `term connect <target>` | selects the repo shell | `shop@prod-1` = repo shell; bare `prod-1` = machine shell |
| ALL other repo verbs taking a live ref (`up down status delete fork push pull migrate promote secret sync cat diff logs exec tunnel commit branch checkout log merge trim policy admin replicate`) | accepted, verified | redundant-match accepted; contradiction = exit 12, never a retarget |
| machine / datastore / cluster / storage / config / backup strategy verbs | **rejected at parse**, exit 2 | these nouns have no `@place` semantics; error says so ("machine names do not take @place") |

Destination flags (bare place names, validated as machine-or-cluster against config):
`repo push --to`, `repo pull --from`, `repo migrate --to`, `cluster fork --to`,
`cluster migrate --to`, `cluster rehearse --on`, `datastore attach --to`,
`backup strategy set --destination`.

### 3.2 The conflict rule (R2-F10) — canonical error text

For a live repo, placement is derived, so `@place` is either redundant (accepted) or
contradictory (refused). Canonical message shape, used by every verb in the table's
third row:

> `shop is placed at prod-1; you addressed shop@backup-2. For the pushed backup copy on
> backup-2 use "rdc backup restore shop@backup-2"; to move the repo use
> "rdc repo migrate shop --to backup-2".`

Exit 12. Silent retargeting never happens; `repo up shop@other` must never be an
action-at-a-distance deploy.

### 3.3 `term connect` namespace collision (R2-F11)

Repos and places are separate namespaces. `term connect <bare>` resolution order:

1. Exactly one of {place, repo} matches → connect (machine shell / repo shell of the
   repo's derived machine).
2. Both match → exit 11:
   > `shop is both a repository and a machine. Use "term connect shop@<machine>" for the
   > repository shell, or "term connect <machine-name>" for the machine shell.`
3. Neither → exit 5 listing near-miss candidates.

No global collision refusal, no marked form; the ambiguity rule covers it at collision
time only.

---

## 4. Cross-cutting conventions

### 4.1 add vs create (R2-F18) — the rule, stated once in root help

`add`/`remove` = register/deregister something that already exists (machines, providers).
`create`/`delete` = make/destroy the thing itself (repos, datastores, clusters,
snapshots). Root `rdc --help` carries the one-sentence rule.

**RESOLVED (gate ruling R3):** the 06 §1 tree wrote `storage create|delete`, but a
storage entry registers an EXISTING external endpoint (S3 bucket, rsync target) — by
this rule they are **`storage add` / `storage remove`**, and that is what §5.7 and the
mapping in §6 now specify. 06 §1 gets the rename in the as-built pass.

### 4.2 `-y/--yes` vs `--force`/`--discard` (R2-F18)

- `-y/--yes` (also a global program flag): skip the interactive confirmation. Never
  changes WHAT happens, only whether you are asked. Non-TTY without `-y` on a
  confirm-gated verb → exit 2 ("confirmation required; pass -y").
- `--force`: accept data loss / override a safety refusal (e.g. `repo merge --force`
  quiesces a running target; `machine prune --force-delete-mounted`).
- `--discard`: the datastore-family spelling of "throw the writes away"
  (`datastore detach --discard`).
- One flag never carries both meanings. No verb interprets `--force` as "don't ask";
  destructive verbs may require BOTH (`-y` to skip the prompt, `--force` to accept loss).

### 4.3 restore vs promote (R2-F16)

`backup restore` materializes a pushed/backup artifact into a live repo name; placement
is stated at restore time; it never touches production repos. `repo promote` swaps a
validated FORK into production under the parent's name; it never fetches bytes. Restore
never promotes; promote never fetches. Each verb's help names the other for the
wrong-verb case, and the R2-F10 conflict error routes users to the right one.

### 4.4 replicate is managed state (R2-F17)

`repo replicate <repo> --replicas N` is a declarative apply that records a managed
replica-set in config (spec half) and state (status half). It gets CRUD from birth:
`repo replicate status`, `repo replicate remove`, and `repo status` shows the replica
set. Re-running the create form with different values reconciles; with identical values
it is a success no-op.

### 4.5 Idempotency master table (R2-F15) — every verb class

| Class | Re-run behavior | Exit |
|---|---|---|
| `create` on existing name (repo, datastore, cluster, snapshot with explicit name, fork tag, replicate on non-repo) | error, names the existing object | 2 |
| `add` on existing name (machine, provider) — even with identical values (names are identity, R2-F4) | error | 2 |
| `delete`/`remove` on missing name | error | 5 |
| `delete`/`remove` on existing | asks (unless `-y`); destroys | 0 |
| `attach` when already attached to the SAME machine with the SAME `--writes` | success no-op (`data.noop:true`) | 0 |
| `attach --to M2` while attached to M1 | NOT an error: performs the codified relocation sequence (02 §3) | 0/12/14 |
| `attach` same machine, DIFFERENT `--writes` | error (writes disposition is set at attach; detach first) | 2 |
| `detach` when not attached | success no-op | 0 |
| `repo up` when running | success: re-deploys (converges) | 0 |
| `repo down` when down | success no-op | 0 |
| `backup run` while the same strategy is running | error; payload carries the running id | 15 |
| `backup cancel` when nothing runs | success no-op | 0 |
| `migrate --to` its current home | success no-op | 0 |
| `promote` a non-fork / already-promoted ref | error | 2 |
| `replicate` re-run | declarative reconcile (see 4.4) | 0 |
| `secret set` same key | overwrites under the mutation-gate ceremony; re-running `up` re-injects idempotently (that IS rotation, 02 §11.5) | 0 |
| `config reconcile` | always safe; convergent by definition | 0 |
| any converge-verb against half-broken state (03 hygiene rule 4) | must converge, not corner-error | 0 |

### 4.6 Output and JSON (`-o json`) contract

- Every new/changed verb emits its result exclusively through
  `outputService.print(data, format)` (`packages/cli/src/services/core/output.ts:231`)
  and its errors through `handleError` — no bare `console.log` of data. The JSON envelope
  is the existing `{success, command, data, errors, warnings, metrics}`.
- The global `-o/--output <table|json|yaml|csv>` is the ONLY switch.
  `[P0-DECIDED]` the per-command `--json` flags (`repo push --json`, `repo diff --json`,
  `repo log --json`) and per-command `--output` flags (`cluster status`, `doctor`,
  `credits`, `config field list`) are DELETED in P4; the auto-JSON precedence
  (`REDIACC_DEFAULT_OUTPUT` → non-TTY/agent → table) already covers their use cases.
- Raw-stream deviations (documented per leaf, not envelope-wrapped even under
  `-o json` unless stated): `repo cat` (file bytes), `repo logs` (log stream),
  `repo exec` / `term connect` (remote stdio), `cluster kubeconfig` (kubeconfig YAML),
  `config audit tail` (stream). For these, `-o json` affects only their error paths.
- Long-running verbs (`push`, `pull`, `migrate`, `cluster fork/migrate/rehearse`,
  `backup run --watch`) render progress to stderr; stdout stays reserved for the final
  envelope so `-o json | jq` always works.

### 4.7 Gating metadata classes (06 principle 5)

| Class | Metadata | Unlock | Applied to |
|---|---|---|---|
| A. read | none | n/a | every status/list/get/log/diff |
| B. repo-mutating | `grandGuard: true` | `REDIACC_ALLOW_GRAND_REPO` (ancestry-verified) | up, down, delete, push, pull, migrate, promote, sync up/down, tunnel, exec, commit, branch, checkout, merge, resize, expand, admin mutators, replicate mutators, restore `--up` target |
| C. fork-nonsense | `forkBlocked: true` | none | `repo admin autostart enable|disable`, `repo resize`, `repo expand` (as today) |
| D. infra-ops family | `agentBlocked: true` | `REDIACC_ALLOW_CLUSTER_OPS` (ancestry-verified; per-name or `*`) | whole `cluster` mutating family, `machine provision|deprovision`, and the mutating `datastore` family (create/attach/detach/fork/resize/delete/snapshot create) — APPROVED by gate ruling R6: datastore verbs move every repo in the pool at once, same blast radius as cluster verbs, and the unlock is exactly what an agent sandbox needs for `--writes local` fork-attaches. The env var KEEPS its historical name for this program (ancestry-verified overrides cannot be renamed mid-program without stranding P5/P6 runs); the per-name unlock value matches the SUBJECT's name — cluster names for cluster verbs, datastore names for datastore verbs, or `*`. Help text calls the class the "infrastructure operations unlock". Cosmetic rename revisited after the program, not during it. |
| E. absolute block | `agentBlocked: true`, no unlock | none | hidden `run`, `mcp serve` |

Every leaf below states its class (A-E) and its MCP disposition (`mcp(...)` or
`exclude: <reason>`), which together are the P4 re-annotation of
`command-metadata.ts` and the seed classification for the P4 MCP alignment gate
(06 §8; `mcp` XOR `mcpExcludeReason` per leaf).

### 4.8 Common flags (stated once)

- `--debug`: kept on every remote-executing leaf (streams renet/ssh output). Not listed
  per leaf below.
- `--skip-router-restart`: `[P0-DECIDED]` kept only on deploy-affecting repo verbs
  (up, down, delete, fork, push, pull, migrate, promote, checkout), HIDDEN from help.
  Deleted everywhere else (it leaked onto ~25 leaves).
- `--dry-run`: report what would happen, exit 0, `data.dryRun:true`. Present where listed.
- Batch flags `--parallel`, `--concurrency <n>` (default 3), `--include-forks`: kept on
  the batch-capable verbs (`repo up/down/push/pull`) with today's semantics (omitted
  positional ref = all repos on `-m`... which no longer exists; `[P0-DECIDED]` batch form
  becomes `rdc repo up --all --machine <m>` — `--all` is the explicit "every repo whose
  derived machine is m" selector; a bare `repo up` with no ref is exit 2, never a batch).

---

## 5. Per-leaf contracts (the entire target tree)

Block format. Fields omitted when the §1/§4 defaults apply unchanged:

```
### rdc <leaf> <positionals>
Help: <one line, grade 5-7, no em dashes>
Args/Flags: name — type — required?/default — meaning
Errors: <specific cases> → exit codes (beyond the standard table)
Idempotency: <per 4.5, deviations only>
Gate: A|B|C|D|E   MCP: mcp(read|write, ...) | exclude: <reason>
```

Every leaf supports `-o json` per §4.6 unless marked "raw stream".

### 5.1 `rdc config` (25 leaves) — the FILE itself, nothing else

Resource CRUD left this noun (06 principle 3). What remains operates on named config
FILES and their cross-cutting facilities.

#### `config init [name]`
- Help: `Create a named configuration file.`
- Args: `name` positional, optional → default config auto-creates on first use, so a
  bare `config init` prints the teaching note and exits 2 ("the default config is created
  automatically; config init <name> is for named configs"). Flags kept from today:
  `--ssh-key <path>`, `--renet-path <path>`, `--master-password <pw>`, `--server <url>`.
- Errors: existing name → 2 (create class). Grammar violation → 2.
- Idempotency: create class.
- Gate: A. MCP: exclude: `Creates local config files; agents operate within one config.`

#### `config list`
- Help: `List configuration files and show which one is active.`
- Gate: A. MCP: mcp(read).

#### `config show`
- Help: `Show the active configuration with secrets masked.`
- Flags: `--reveal` (TTY-gated secret reveal, as today).
- Gate: A. MCP: mcp(read; excludeOptions: reveal).

#### `config delete <name>`
- Help: `Delete a named configuration file.`
- Args: `name` positional required. Flags: `-y`.
- Errors: deleting the ACTIVE config → 2 with "switch configs first"; missing → 5.
- Gate: A (confirm-gated). MCP: exclude: `Deletes local config files.`

#### `config set <key> <value>` / `config clear [key]`
- Help: `Set a top-level config option.` / `Clear a config option.`
- Args: positionals (migrated from `--key/--value`). Valid keys are the v3 defaults
  schema; `team` and `region` are DELETED keys (R2-F9 residue sweep) → unknown-key
  error, exit 2, listing valid keys. `DefaultsSchema.machine` is deleted the same way.
- Gate: A. MCP: exclude: `Config value mutation; use CLI directly.` (as today)

#### `config recover [name]`
- Help: `Restore a config file from its latest local backup.`
- Flags: `-y`. Behavior note (R2-F2): recovery restores the SPEC half; the `state`
  bucket is restored but marked stale, and the first derived-machine verification that
  disagrees exits 12 pointing at `config reconcile` (never a wrong-host deploy).
- Gate: A. MCP: exclude: `Interactive recovery of local files.`

#### `config prune`
- Help: `Remove expired certificates, archives, and dangling refs from the config.`
- Flags (today's): `--dry-run`, `--certs-only`, `--archives-only`, `--refs-only`,
  `--purge-archived`, `--grace-days <n>`.
- Idempotency: convergent.
- Gate: A. MCP: mcp(write, idempotent; excludeOptions: purge-archived).

#### `config edit` (NEW)
- Help: `Open the active config in your editor, with locking and validation.`
- Behavior: takes the config file lock, opens `$EDITOR` on the SPEC half (state bucket
  is not hand-editable), validates against schema v3 on save, appends an audit entry,
  atomic write. Non-TTY → exit 2. Validation failure → keep temp file, print path, exit 2.
- Gate: A. MCP: exclude: `Interactive editor session.`

#### `config reconcile` (NEW, R2-F2)
- Help: `Rebuild runtime state from machine truth. Fixes stale attach and routing data.`
- Flags: `--machine <m...>` limit scope; `--dry-run` show the diff without writing.
- Behavior: for each machine (all reachable machines by default) run
  `renet list all --json`, rebuild the `state` bucket (datastore attach/mounter,
  networkId allocations, observed versions, mount facts); print a spec-vs-observed diff.
  Never touches the spec half. Unreachable machines are reported per-machine
  (`data.unreachable[]`) and do NOT fail the whole run; exit 0 if at least one machine
  reconciled, 6 if none reachable. `[P0-DECIDED]`
- Idempotency: convergent by definition.
- Gate: A. MCP: mcp(write, idempotent, timeout write; descriptionOverride pointing agents
  here when they hit exit 12).

#### `config field get|set|unset|rotate|list`
Unchanged surface (06 §5) except positional migration:
- `config field get <pointer>` (`--reveal`, `--digest`), `set <pointer> <new>`
  (`--current <v>`), `unset <pointer>` (`--current <v>`), `rotate <pointer> <new>`,
  `list` (`--sensitive`; its private `--output` flag dies per §4.6).
- Help lines: `Read one config field by JSON pointer.` / `Set one config field.` /
  `Remove one config field.` / `Rotate a sensitive field value.` / `List config fields.`
- Errors: mutation-gate ceremony violations (`--current` mismatch) → exit 4.
- Gate: A (mutation-gate enforced). MCP: `get`/`list` mcp(read, digest-only);
  `set`/`unset`/`rotate` exclude: `Requires --current ceremony; human eyes-on.`

#### `config audit log|tail|verify`
Unchanged (06 §5). `log` flags: `--since <spec>`, `--path <glob>`, `--actor <kind>`.
`tail` is a raw stream. `verify` exits 1 on a broken hash chain (its one deviation:
verification failure is the diagnostic result, GENERAL_ERROR).
- Help: `Show the config audit log.` / `Follow the audit log live.` /
  `Verify the audit log hash chain.`
- Gate: A. MCP: `log` mcp(read); `tail` exclude: `Endless stream.`; `verify` mcp(read).

#### `config remote enable|disable|status|refresh`
Unchanged (06 §5): zero-knowledge config sync. `enable` flags `--headless`,
`--api-url <url>`.
- Gate: A. MCP: exclude (group, as today): `Interactive browser flow.` `status`
  mcp(read).

#### `config ssh set|show|remove`
Unchanged: `set <path>` positional (`--embed`), `show`, `remove`.
- Help: `Set the SSH key used for machine connections.` etc.
- Gate: A. MCP: exclude (group, as today): `Writes key material.`

### 5.2 `rdc machine` (20 leaves)

Absorbs `config machine *` and `config provider *` (06 §2). `query` renamed `status`.
Section commands fold into `status` flags. `machine rename` is eliminated (R2-F4).

#### `machine add <name>`
- Help: `Register an existing machine you can reach over SSH.`
- Args: `name` positional. Flags: `--ip <address>` required, `--user <name>` required,
  `--port <n>` default 22. `[P0-DECIDED]` today's `--datastore <path>` flag is DELETED
  here (the implicit default datastore's path is a `machine setup` concern, see below);
  registration records connection facts only.
- Errors: existing name → 2; name collides with a cluster name → 2 (place namespace,
  §2.4).
- Gate: A. MCP: mcp(write, non-destructive, idempotent:false).
- Note: add + setup auto-create the machine's IMPLICIT `default` datastore record
  (placement machine-arm; never enters the datastore registry — R2-F1).

#### `machine remove <name>`
- Help: `Remove a machine from the config. Does not touch the machine itself.`
- Flags: `-y`. Errors: missing → 5; machine still referenced by a named datastore's
  attach state or cluster membership → 2 listing the referents (names are identity;
  no dangling refs). `[P0-DECIDED]`
- Gate: A. MCP: mcp(write, destructive, idempotent:false).

#### `machine list`
- Help: `List registered machines.`
- Flags: `--search <text>`, `--sort <field>`, `--desc` (factory heritage).
- Gate: A. MCP: mcp(read).

#### `machine status [name]` (renamed from `machine query`)
- Help: `Show a machine's system, repositories, containers, and services.`
- Args: `name` positional (required unless exactly one machine is registered;
  otherwise exit 11 listing machines `[P0-DECIDED]`).
- Flags (kept section filters): `--system`, `--repositories`, `--containers`,
  `--services`, `--network`, `--block-devices`, `--licenses`, `--storage-health`,
  `--sync-certs`, `--strict`, plus NEW `--datastores` (per-datastore mount/attach/usage)
  and `--health-check` / `--stability-check` / `--search <text>` (absorbing today's
  `machine containers|services|repos` extras).
- Gate: A. MCP: mcp(read; descriptionOverride as today's `machine query`).

#### `machine setup <name>`
- Help: `Install renet and prepare a registered machine for repositories.`
- Flags: `--datastore-path <path>` default `/mnt/rediacc`, `--datastore-size <size>`
  default `95%` (today's `config machine setup` flags, renamed from `--datastore`).
  Auto-creates the implicit `default` datastore (02 §7).
- Idempotency: convergent (re-run repairs a half-set-up machine).
- Errors: renet install/verify failure → 14; unreachable → 6.
- Gate: A. MCP: mcp(write, idempotent).

#### `machine scan-keys [name]`
- Help: `Scan and pin the machine's SSH host keys.`
- Idempotency: convergent.
- Gate: A. MCP: mcp(write, idempotent).

#### `machine health <name>`
- Help: `Run connectivity and readiness checks against a machine.`
- Exit: 0 healthy; 1 if any check fails (doctor convention); 6 unreachable.
- Gate: A. MCP: mcp(read).

#### `machine prune <name>`
- Help: `Clean up orphaned repositories and unknown files on a machine.`
- Flags (kept): `--dry-run`, `--orphaned-repos`, `--prune-unknown`,
  `--force-delete-mounted`, `--force`, `--grace-days <n>`.
- Gate: A (confirm-gated; `--force*` = data loss). MCP: mcp(write, destructive,
  idempotent; excludeOptions: grace-days, force-delete-mounted).

#### `machine provision <name>`
- Help: `Create a cloud VM with a provider and register it as a machine.`
- Flags (kept): `--provider <name>` required, `--region`, `--type`, `--image`,
  `--ssh-user`, `--base-domain`, `--no-infra`.
- Errors: tofu failure → 14; provider missing → 5.
- Idempotency: create class (existing machine name → 2).
- Gate: D. MCP: mcp(write, destructive:false, idempotent:false; excludeOptions:
  ssh-user) — as today, execution still guarded by D at runtime.

#### `machine deprovision <name>`
- Help: `Destroy a provisioned cloud VM and remove its machine entry.`
- Flags: `-y`, `--force` (destroy even with repos present — data loss).
- Gate: D. MCP: mcp(write, destructive, idempotent:false; appendArgs [--force] dies:
  `[P0-DECIDED]` MCP must NOT auto-force; the agent gets the refusal instead).

#### `machine provider add|remove|list`
Moved verbatim from `config provider *` (06 §2), positional name migration.
- `add <name>`: today's full flag set kept (`--provider|--source`, `--token` required,
  `--region`, `--type`, `--image`, `--ssh-user`, `--resource`, `--label-attr`,
  `--region-attr`, `--size-attr`, `--image-attr`, `--ipv4-output`, `--ipv6-output`,
  `--ssh-key-attr`, `--ssh-key-format`, `--ssh-key-resource`).
- Help: `Register a cloud provider account for provisioning.` / `Remove a provider.` /
  `List registered providers.`
- Gate: A. MCP: as today (add/remove mcp(write), list mcp(read)).

#### `machine infra set|show|push` + `machine infra cert pull|push|status|clear`
Moved from `config infra *` + `config cert-cache *` (06 §2; §1 tree omission flagged as
U1). `[P0-DECIDED]` cert-cache is nested as `machine infra cert` (it caches the TLS
material infra provisions; keeping it under infra keeps machine's top level flat).
- `set <machine>`: flags kept (`--public-ipv4`, `--public-ipv6`, `--base-domain`,
  `--cert-email`, `--cf-dns-token`, `--tcp-ports`, `--udp-ports`).
  Help: `Set infrastructure settings for a machine.`
- `show <machine>`: Help: `Show infrastructure settings.` MCP: mcp(read) (as today's
  `config infra show`).
- `push <machine>`: Help: `Apply infrastructure settings to the machine.` Errors: renet
  failure → 14. Idempotency: convergent.
- `cert pull|push|status|clear <machine>`: today's flags (`pull --no-prune`).
  Help: `Pull TLS certificates into the local cache.` etc.
- Gate: A. MCP: `show`/`cert status` mcp(read); rest exclude: `Infra credential
  material; use CLI directly.`

### 5.3 `rdc datastore` (10 leaves)

Named, mobile, single-mounter pools (02 §1). The implicit `default` datastore never
appears here (R2-F1): every leaf below addresses NAMED datastores only, and `default` as
a positional is exit 2 with "the default datastore is implicit; these verbs manage
additional named datastores". Datastore refs use the fork-tag grammar `ds[:tag]`.
All mutating leaves are gate class D (§4.7 decision); reads are class A.

#### `datastore create <name>`
- Help: `Create an additional named datastore on a machine.`
- Flags: `--machine <m>` required (creation host), `--backend <local|rbd>` default
  `local`, `--size <size>` required, `--pool <name>` (rbd backend; default `rbd`),
  `--image <name>` (rbd; default = datastore name), `--cluster <c>` optional (gate
  ruling C7): records the datastore's one-world cluster backref — set means kubernetes
  repos only, unset means docker repos only, IMMUTABLE after create (spec 02 §3.2
  runtime derivation keys off it). Both backends may carry it: `--backend local
  --cluster c1` is the local-NVMe tiering datastore inside a cluster (outside the group
  snapshot instant, 03 §3); `--backend rbd` WITHOUT `--cluster` is the docker-world rbd
  datastore (the `config machine set-ceph` replacement, 06 §2).
- Errors: name exists in registry → 2; name `default` → 2 (above); `--cluster` naming
  an unknown cluster → 5 listing configured clusters; rbd backend on a machine without
  Ceph reach → 14 with the Ceph prerequisite named; mount-path collision on the machine
  → 2 (02 §3: a machine never mounts two datastores with the same mount-path name).
- Idempotency: create class; a failed half-create converges on re-run after
  `datastore delete` OR resumes if the on-machine state matches the request
  (03 hygiene rule 4). `[P0-DECIDED]` resume-if-identical.
- Gate: D. MCP: exclude: `Infrastructure storage provisioning; operator unlock only.`

#### `datastore list [cluster|machine]`
- Help: `List named datastores, where they are attached, and what they hold.`
- Args: optional place positional narrows to one cluster or machine (this is the
  `rdc datastore list <cluster>` the 02 §7 teaching error advertises).
- Output: name, backend, size/usage, attachedTo, writes-disposition, repos, k3s-version
  metadata (F14), snapshot count.
- Gate: A. MCP: mcp(read).

#### `datastore status <name>`
- Help: `Show one datastore: attachment, usage, repos, snapshots, health.`
- Errors: not in registry → 5; attach-state mismatch detected during the read is
  REPORTED in the payload (`state.verified:false`), not an error (reads never exit 12).
- Gate: A. MCP: mcp(read).

#### `datastore attach <name[:tag]> --to <machine>`
- Help: `Attach a datastore to a machine. Forks must state where writes go.`
- Flags: `--to <machine>` required; `--writes <local|ceph>` required IFF the ref is a
  fork (`:tag` present or record marked fork); `--cow-size <size>` (writes local overlay
  size); `--no-auto` (skip auto-reattach on boot, 06 §7.6 policy flag).
- Errors: fork without `--writes` → 2 with the 03 §2 teaching error: "<ref> is a fork.
  Say where its writes go: --writes local (instant, ephemeral, lost on detach) or
  --writes ceph (durable clone in the pool)." `--writes` on a non-fork → 2. Mount-path
  collision on dest → 2 (F12). Fencing failure on the old holder → 14 (attach aborted,
  old attach intact).
- Idempotency: per §4.5 (same machine+writes = no-op 0; different machine = codified
  relocation 02 §3; same machine different writes = 2).
- Gate: D. MCP: exclude: `Moves every repo in the pool; operator unlock only.`

#### `datastore detach <name[:tag]>`
- Help: `Detach a datastore from its machine. Repos in it stop first.`
- Flags: `--discard` (fork with local writes: throw the overlay away — REQUIRED to
  detach a `--writes local` fork, exit 2 without it, message states the writes are
  ephemeral and will be lost); `-y`.
- Errors: repos still running and graceful stop fails → 14 (no lazy-success, 03 hygiene
  rule 2: kubelet/docker still holding mounts fails the detach loudly).
- Idempotency: not attached = no-op 0.
- Gate: D. MCP: exclude: same as attach.

#### `datastore fork <name> --tag <tag>`
- Help: `Fork a datastore copy-on-write. Instant, any size.`
- Flags: `--tag <tag>` required (result ref `name:tag`); `--attach-to <machine>`
  optional convenience (implies attach; then `--writes <local|ceph>` required with it);
  `--cow-size <size>` (with `--writes local`).
- Errors: tag exists → 2; `--attach-to` without `--writes` → 2 (same teaching error as
  attach); local-backend datastore → 2, teaching (gate ruling C8, spec 01 wins): "repos
  inside a local datastore fork individually by reflink (rdc repo fork); datastore-level
  fork needs the rbd backend" — datastore fork is REFUSED for the local backend in v1,
  same-machine included (no block-level clone primitive).
- Gate: D. MCP: exclude: `Infrastructure storage operation; operator unlock only.`

#### `datastore snapshot create <name>` / `datastore snapshot list <name>`
- Help: `Take a point-in-time snapshot of a datastore.` / `List datastore snapshots.`
- `create` flags: `--snapshot <label>` optional (default `<utc-timestamp>`
  `[P0-DECIDED]`); `--group <cluster>` = the cluster-consistent RBD GROUP snapshot
  across every datastore image of the cluster (03 §3 plumbing; the porcelain is
  `cluster snapshot create`).
- Errors: label exists → 2; `--group` naming a cluster whose datastores include
  local-tier members → warning in payload (they are outside the group instant, 03 §3),
  not an error; pre-Squid Ceph without group-snap support → 14 naming the fallback
  (spike a decides the fallback text).
- Gate: `create` D; `list` A. MCP: `list` mcp(read); `create` exclude: `Infrastructure
  snapshot; operator unlock only.`

#### `datastore resize <name> --size <size>`
- Help: `Grow or shrink a datastore. Offline operation.`
- Errors: attached and busy → 15; shrink below usage → 2.
- Gate: D. MCP: exclude: `Destructive storage geometry change.`

#### `datastore delete <name[:tag]>`
- Help: `Destroy a datastore and everything in it.`
- Flags: `-y`, `--force` (delete even with repo records pointing at it — data loss;
  without it, referenced datastore → 2 listing the repos).
- Behavior: detach first if attached (full hygiene sequence; failed detach fails the
  delete — detach-before-unlink, 03 rule 1).
- Gate: D. MCP: exclude: `Destroys a storage pool.`

### 5.4 `rdc repo` (48 leaves)

Daily verbs keep today's semantics (06 §5) with the addressing migration: positional
`<ref>`, `-m/--machine` and `--cluster` DELETED (derived per §2.3), `--name` deleted.
`REDIACC_ROLE`/`REDIACC_WRITES`/`REDIACC_DATASTORE` are injected by up/down lifecycle
(02 §4) — invisible at the CLI surface. Placement errors follow 02 §7 verbatim.

#### `repo create <name>`
- Help: `Create a new repository. State its home once: a machine or a datastore.`
- Args: `name` positional. Flags: exactly ONE of `--machine <m>` (docker shortcut: the
  machine's implicit default datastore) or `--datastore <d>` (docker tiering AND the
  only kubernetes form); `--size <size>` required for docker-runtime placements;
  `--no-docker` kept (docker world: skip daemon start).
- Errors (02 §7, canonical texts):
  - both flags → 2: "repo create takes exactly one placement flag: --machine (docker,
    default datastore) or --datastore (named datastore; required for cluster repos)."
  - neither flag → 2 with the same message.
  - `--datastore` naming a cluster datastore = the k8s form; `--size` with a k8s
    placement → 2: "kubernetes repos size their volumes from the PVC declarations;
    --size applies to docker repos." `[P0-DECIDED]`
  - `--machine` naming a machine with a cluster membership backref → 2 (R2-F12):
    "prod-3 is a member of cluster c1. A repo on a cluster machine needs a datastore:
    rdc datastore list c1. --machine here would create a docker repo on that node."
  - k8s intent without datastore (detected: `--machine` omitted, name matches no
    machine, user passed a cluster to a dead `--cluster` flag) → 2: "a cluster repo
    needs a home: pick a datastore (rdc datastore list <cluster>)." The `--cluster`
    flag itself is DELETED; passing it gets Commander's unknown-option error plus this
    hint via the error-suggestion hook. `[P0-DECIDED]`
- Idempotency: create class.
- Gate: A (creation is not grand-gated today; stays). MCP: mcp(write, destructive,
  idempotent:false) as today.

#### `repo up <ref>`
- Help: `Deploy or update a repository. Runs its Rediaccfile up steps.`
- Flags: `--no-start` (NEW: mount/prepare only — replaces `repo mount`; LUKS open and,
  for k8s, PV generation happen without running `up()`), `--skip-checkpoint`, `--tls`,
  `--detach`, `--all --machine <m>` batch form (§4.8), `--parallel`,
  `--concurrency <n>`, `--include-forks`, `-y`, `--dry-run`.
- Errors: derived-routing per §2.3 (5/11/12); deploy failure → 14; k8s manifests with
  cluster-scoped kinds → warning (02 §2), not an error; renet license → 10.
- Idempotency: converges; re-run on running repo redeploys (0).
- Gate: B (grandGuard). MCP: mcp(write, destructive, idempotent, repoArg:ref;
  descriptionOverride updated for --no-start replacing mount).

#### `repo down <ref>`
- Help: `Stop a repository. Add --unmount to also close its encrypted volume.`
- Flags: `--unmount` (replaces `repo unmount` for the full close), `--checkpoint`,
  `--all --machine <m>`, `--parallel`, `--concurrency <n>`, `-y`, `--dry-run`.
- Idempotency: down-when-down = no-op 0.
- Gate: B. MCP: mcp(write, destructive, idempotent, repoArg:ref).

#### `repo status <ref>`
- Help: `Show a repository's containers, mounts, size, role, and replicas.`
- Output additions: `role` (primary|fork|rehearsal|replica), `writes`, `datastore`,
  placement, replica-set summary (R2-F17), branching head info.
- Gate: A. MCP: mcp(read, repoArg:ref).

#### `repo list`
- Help: `List repositories in this config and where they live.`
- Flags: `--machine <m>` / `--datastore <d>` / `--cluster <c>` as FILTERS (listing is
  the one place these remain, as narrowing filters, not routing).
- Gate: A. MCP: mcp(read).

#### `repo delete <ref>`
- Help: `Delete a repository and its data.`
- Flags: `--archive-config` (keep the config record in archives), `-y`, `--dry-run`.
- Errors: running repo → 2 "stop it first (rdc repo down <ref>) or pass --force";
  `--force` added for stop+delete. Missing → 5.
- Gate: B. MCP: mcp(write, destructive, idempotent:false, repoArg:ref).

#### `repo fork <parent-ref> --tag <tag>`
- Help: `Fork a repository copy-on-write. Instant at any size. New identity, empty secrets.`
- Flags: `--tag <tag>` required; `--up` (deploy after fork); `--checkpoint` (CRIU);
  `--immutable` (create as immutable commit object); `--detach`. DELETED: `--cluster`,
  `--to-cluster`, `--provider` (06 §3: no runtime flag at all — the parent's placement
  decides docker-vs-k8s and `RepoRuntime` dispatches; cross-machine = fork + push).
- Errors: tag exists → 2; `--tag base` → 2 (§2.1); cross-datastore fork request → 2
  teaching "same-datastore forks are instant; cross-datastore moves are a copy: use
  repo push" (02 §3).
- Contract invariants (02 §4, enforced by RepoRuntime, stated in help long-form):
  fork = new principal: empty secret map, regenerated identity (k8s: PKI + secret scrub
  + ROLE rewrite), `REDIACC_ROLE=fork`. With `--up`, the health gate runs with the C5
  DEFAULTS only (30 s attempt / 300 s window; no flags on fork verbs in v1 — G6
  defaults-only, stated explicitly). Same rule for `cluster fork --up`.
- Gate: A + forkBlocked:false (fork of fork allowed). MCP: mcp(write, destructive,
  idempotent:false; the constant-time descriptionOverride from today kept).

#### `repo push <ref>`
- Help: `Push a repository backup to a storage or another machine.`
- Flags: `--to <place|storage>` required-unless-strategy-default; `--tag <t>` DELETED
  (tag rides the ref); `--provision <provider>`, `--checkpoint`, `--force`, `--up`
  (deploy the copy on the dest — note 06 §6.5: the pushed copy is a backup artifact;
  `--up` on push is therefore DELETED `[P0-DECIDED]`, replaced by
  `backup restore ... --up` — a pushed copy that boots under the same name IS the
  two-places bug being retired), `-w/--watch`, `--parallel`, `--concurrency`, `-y`,
  `--bwlimit <limit>`, `--delta-base <guid>`, `--strategy <s>`.
- Errors: live-ref `@place` conflict per §3.2; dest unreachable → 6; transfer → 14.
- Idempotency: re-push converges (delta transfer); success.
- Gate: B. MCP: mcp(write, destructive, idempotent, repoArg:ref; descriptionOverride:
  same-GUID backup warning kept, minus the --up path).

#### `repo pull <ref>`
- Help: `Pull a repository backup from a storage or machine onto its home machine.`
- Flags: `--from <place|storage>` required; `--force` (overwrite local divergence —
  data loss); `--up`; `-w/--watch`; `--parallel`; `--concurrency`; `-y`; `--bwlimit`;
  `--delta-base`; `--strategy`.
- Gate: B. MCP: mcp(write, destructive, idempotent, repoArg:ref).

#### `repo migrate <ref> --to <place>`
- Help: `Move a repository to another machine with minimal downtime and a health check.`
- Flags: `--to <place>` required; `--from` DELETED (derived; §2.3); `--provision
  <provider>`, `--bwlimit`, `--checkpoint`, `--delta-base`, `--strategy`, `--skip-dns`.
- Behavior additions (06 §3): transport disclosure BEFORE cutover (in-datastore relocate
  vs copy pipeline — printed and in `--dry-run` payload); health gate after `up()` on
  dest; secrets re-inject automatically (same principal); `REDIACC_ROLE` stays primary.
- Health-gate flags (G6/C5): `--health-window <seconds>` default 300 (total gate
  window), `--health-timeout <seconds>` default 30 (per attempt; a timeout counts as
  one warming result). Same pair, same defaults, on `cluster migrate`,
  `cluster rehearse`, and `backup restore --up`.
- Errors/exits: pre-cutover failure → 14 (source untouched, stated); health-gate
  failure → 13 (source restarted, stated in payload); `--to` its current home → no-op 0.
- Gate: B. MCP: mcp(write, destructive, idempotent:false, repoArg:ref).

#### `repo promote <fork-ref>` (renamed from `repo takeover`)
- Help: `Make a validated fork the production repository under its parent name.`
- Flags: `--force` (today's semantics: proceed past divergence warnings), `-y`.
- Errors: ref is not a fork → 2 ("promote swaps a fork into production; <name> is the
  production record"); parent running → asks (down+swap+up) unless `-y`.
- Boundary (R2-F16): never fetches; both records must live in the same datastore, else
  2 pointing at `repo push`/`backup restore`.
- Gate: B. MCP: exclude: `Production swap; human decision.` `[P0-DECIDED]` (today
  takeover had grandGuard but no MCP block; promote is exactly the verb an agent should
  hand back to the operator).

#### `repo secret get|list|set|unset <ref> ...`
Unchanged surface (06 §3: UX identical; k8s repos materialize Secret objects at up()).
Positional migration: `repo secret get <ref> --key <KEY>`; `set <ref> --key K --value V
[--mode env|file] [--current <v>|--rotate-secret]`; `unset <ref> --key K
[--current|--rotate-secret]`; `list <ref>`.
- Help: `Show a secret's digest (never the value).` / `List secret keys for a repo.` /
  `Set a per-repo secret.` / `Remove a per-repo secret.`
- Errors: ceremony violations → 4 (mutation gate); file-mode size above the v3 cap
  (02 §11.5, far below 10 MB; exact cap set by the config spec) → 2.
- Fork policy: fork = empty secret map (get/list on a fresh fork return empty, not
  parent values) — contract-tested, not CLI-enforced.
- Gate: A (mutation-gate is the property; §see today's rationale). MCP: as today —
  group exclude with `get`/`list` exposed as mcp(read).

#### `repo sync upload|download|status <ref>`
Kept (06 §5) with addressing migration: positional ref replaces `-r/--repository` +
`-m`; `-t/--team` DELETED (R2-F9 dead vocabulary).
- Flags kept: `--local <paths...>`, `--remote <path>`, `--remote-file <path>`,
  `--mirror`, `--verify`, `--confirm`, `--exclude <patterns...>`, `--dry-run`.
- Help: `Upload files into a repository.` / `Download files from a repository.` /
  `Show what a sync would change.`
- Gate: upload/download B; status A. MCP: exclude (all three): `Requires local
  filesystem paths on the MCP host.` `[P0-DECIDED]` (today they were policy-only).

#### `repo cat <ref> --remote-file <path>`
- Help: `Print a file from inside a repository.`
- Flags kept: `--max-bytes`, `--offset`, `--head <n>`, `--tail <n>`, `--stat`,
  `--force-binary`. Raw stream output (§4.6).
- Gate: A. MCP: mcp(read, repoArg:ref) `[P0-DECIDED]` (agent-useful, read-only).

#### `repo diff <ref> [--base <ref>]`
- Help: `Show block and file changes between a repository and its fork or base.`
- Flags kept: `--name-only`, `--stat`, `--content [path]`, `--fast`. `--json` deleted.
- Gate: A. MCP: mcp(read, repoArg:ref).

#### `repo logs <ref>` (NEW, R2-F14)
- Help: `Show application logs from a repository's containers.`
- Flags: `--container <name>` (omit = single container, else exit 11 listing
  containers), `-f/--follow`, `--lines <n>` default 100, `--since <spec>`.
- Backend: docker runtime = `docker logs` via per-repo daemon; k8s runtime = pod logs in
  the repo namespace (same verb, same meaning — principle 2). Raw stream.
- Gate: A. MCP: mcp(read, repoArg:ref; excludeOptions: follow).

#### `repo exec <ref> -- <cmd...>` (NEW, R2-F14)
- Help: `Run a command inside a repository container.`
- Flags: `--container <name>` (ambiguity rule as logs), `-i/--interactive` (TTY).
- Exit: remote command's code verbatim (§1 deviation).
- Gate: B (grandGuard — arbitrary mutation potential). MCP: mcp(write, destructive,
  idempotent:false, repoArg:ref; excludeOptions: interactive).

#### `repo tunnel <ref>`
- Help: `Open a local port tunnel to a repository service.`
- Flags kept: `--container <name>`, `--port <p>`, `--local <p>`, `--url-only`.
- Gate: B. MCP: exclude: `Blocks until Ctrl+C.` (as today)

#### `repo replicate <ref> --replicas <n>` (NEW, 05 §1)
- Help: `Create point-in-time read replicas of a repository across its cluster.`
- Flags: `--replicas <n>` required; `--refresh <duration>` (rolling re-fork cadence);
  `--headless` (DNS-all-pods Service variant).
- Errors: docker-placement repo → 2 (replicate is a cluster feature; message says so);
  overlay budget exceeded → 14 (storage-health integration, F10).
- Idempotency: declarative reconcile (§4.4).
- Gate: B + class D unlock NOT required (`[P0-DECIDED]` replicate stays within one
  cluster's datastores and is the flagship agent-safe demo; grandGuard suffices).
- MCP: mcp(write, destructive:false, idempotent, repoArg:ref).

#### `repo replicate status <ref>` / `repo replicate remove <ref>`
- Help: `Show a repository's replica set.` / `Remove a repository's replicas.`
- `remove` flags: `-y`. Removing a non-existent set = no-op 0 (converge-to-absent).
- Gate: status A; remove B. MCP: status mcp(read); remove mcp(write, destructive,
  idempotent, repoArg:ref).

#### `repo commit <ref> --message <msg>`
- Help: `Freeze the working fork into an immutable commit.`
- Flags kept: `--message` required, `--author <a>`.
- Gate: B. MCP: mcp(write, as today).

#### `repo branch <ref> --branch <name>`
- Help: `Point a branch at a working fork.` (config-only ref operation)
- Gate: B. MCP: exclude: `Config-only ref operation.` (as today)

#### `repo checkout <commit-or-branch-ref> --tag <tag>`
- Help: `Clone an immutable commit into a fresh writable fork.`
- Flags kept: `--tag` required (new working fork), `--from <workingFork>`. `--ref`
  merges into the positional.
- Gate: B. MCP: mcp(write, as today).

#### `repo log <ref>`
- Help: `Show a repository's commit history.` (`--json` deleted)
- Gate: A. MCP: mcp(read, as today).

#### `repo merge <ref> --from <source-ref>`
- Help: `Merge a commit or fork into a working fork, safely.`
- Flags kept: `--from` required, `--force` (quiesce a running target — data-loss class:
  in-flight writes stop), `--resolve <ours|theirs>`, `--base <guid>`.
- Gate: B. MCP: mcp(write, as today, descriptionOverride kept).

#### `repo gc --machine <m>`
- Help: `Delete unreferenced commit objects on a machine. Dry-run unless --apply.`
- Flags: `-m/--machine` KEPT (machine-scoped scan, no repo to derive from), `--apply`.
- Gate: A (never touches mounted objects). MCP: mcp(write, destructive, as today).

#### `repo resize <ref> --size <s>` / `repo expand <ref> --size <s>`
- Help: `Resize a repository volume offline. Grows and shrinks.` /
  `Grow a repository volume while it runs. Grow only.`
  (06 §7.4: the offline-grow/shrink vs online-grow-only split is deliberate; both help
  texts state it.)
- Errors: `resize` on running repo → 15 ("stop it or use repo expand to grow online");
  `expand` shrink request → 2.
- Gate: B + forkBlocked (as today). MCP: exclude (both): `Destructive volume geometry;
  use CLI directly.` (as today)

#### `repo trim [ref]`
- Help: `Return freed space to the pool. Safe on running repositories.`
- Flags kept: `--docker`, `--docker-volumes` (data-destructive; stays CLI-only),
  `--report-only`; `--machine <m>` kept as filter for the all-repos form.
- Gate: A (no grandGuard, per today's reasoned annotation). MCP: mcp(write,
  destructive:false, idempotent; excludeOptions: docker-volumes) (as today).

#### `repo policy set|get [ref]`
- Help: `Set size policy: auto-grow and auto-trim.` / `Show size policy.`
- Flags kept on set: `--auto-grow <bool>`, `--max-quota <size>`,
  `--grow-threshold <pct>`, `--grow-step <s>`, `--auto-trim <bool>`,
  `--trim-interval <h>`; `--machine <m>` kept for the machine-default form.
- Gate: A. MCP: exclude (group): `Changes machine auto-grow behavior.` (as today)

#### `repo admin validate <ref>`
- Help: `Run integrity checks on a repository.`
- Gate: B (as today's grandGuard). MCP: exclude: `Use repo status for MCP.` (as today)

#### `repo admin fsck --machine <m>`
- Help: `Check config refs against the commits present on a machine.`
- Gate: A. MCP: mcp(read, as today).

#### `repo admin ownership <ref>`
- Help: `Fix file ownership inside a repository.`
- Flags kept: `--uid <uid>`.
- Gate: B. MCP: exclude: `Destructive ownership transfer.` (as today)

#### `repo admin autostart enable|disable|list`
- `enable|disable <ref>`: Help: `Start this repository automatically on boot.` /
  `Do not start this repository on boot.` `list --machine <m>`.
- Gate: enable/disable B + forkBlocked (as today); list A.
- MCP: exclude (group): `Autostart management.` (as today)

#### `repo admin template list|apply`
- `list`: Help: `List available repository templates.`
- `apply <ref> --template <name>`: flags `--file <path>`, `--grand <name>`; today's
  `-r/--repository` collapses into the positional, `--name` becomes `--template`.
- Gate: B. MCP: exclude: `Requires file upload.` (as today)

#### `repo admin archive list|restore|purge`
Relocated from `config repository {list,restore,purge}-archived` (06 §2).
- `list`: Help: `List archived repository records.`
- `restore <name> [--new-name <n>]`: Help: `Restore an archived record into the config.`
- `purge [name]`: Help: `Permanently delete archived records.` Flags: `-y`; no name =
  all (confirm-gated).
- Gate: A. MCP: exclude (group): `Config archive bookkeeping.`

### 5.5 `rdc cluster` (12 leaves)

Whole family stays gate class D (agentBlocked, `REDIACC_ALLOW_CLUSTER_OPS` unlock,
ancestry-verified — `packages/cli/src/utils/command-policy.ts`), reads excepted.
`cluster install` and `config cluster {add,add-pool,list,remove}` are dead (06 §2).

#### `cluster create <name>`
- Help: `Declare and provision a cluster: machines, Ceph pools, and Kubernetes.`
- Args: `name` positional. Flags (merger of today's `config cluster add` +
  `cluster create`): `--provider <kvm|provider-name>` required; `--pool <spec...>`
  required (repeatable pool specs; Ceph-first ordering is renet's job);
  `--declare-only` (record without provisioning — the old two-phase flow);
  `--network-cidr <cidr>`, `--network-primitive <p>`, `--control-node <machine>`,
  `--net-name <n>`, `--net-base <prefix>`, `--net-offset <n>`, `--control-id <n>`
  (required KVM topology set, as today's config cluster add), `--docker-registry <ep>`,
  `--ssh-user <u>`, `--base-domain <d>`.
- Provider ≠ distro guard (02 §10b): `--provider` never selects a Kubernetes; a value
  like `eks`/`gke` that matches no configured provider → 5 listing configured providers.
- Errors: name exists → 2; name collides with a machine → 2 (place namespace);
  KVM without the net topology flags → 2 naming the missing flags; provisioning → 14.
- Idempotency: create class; `--declare-only` then re-run WITHOUT it provisions the
  declared record (resume semantics `[P0-DECIDED]`).
- `ds-control` behavior (gate gap G4, `[P0-DECIDED]` here, P2 implements): provisioning
  auto-creates a dedicated rbd-backed control-plane datastore named
  **`ds-control-<cluster>`** (per-cluster suffix preserves the names-unique-per-config
  invariant; suite files saying bare `ds-control` get the suffix in the as-built pass),
  cluster backref set, attached to the control node, default size 10 GiB, overridable
  via `--control-ds-size <size>`. The `ds-control-` name prefix is RESERVED:
  `datastore create` refuses it (exit 2). It appears in `datastore list/status` like
  any named datastore; `datastore delete` on it while the cluster exists → 2 pointing
  at `cluster destroy`. Rationale: F8 — a repo filling a shared pool must not take the
  control plane down with it (02 §1).
- Gate: D. MCP: exclude: `Provisions infrastructure.` (as today)

#### `cluster status [name]`
- Help: `Show cluster health, nodes, pools, and datastores. Lists clusters with no name.`
- No-name form replaces `config cluster list`. Private `--output` flag dies.
- Gate: A. MCP: mcp(read) (as today).

#### `cluster scale <name> --pool <p> --count <n>`
- Help: `Change a node pool's machine count.`
- Kept for pool-count semantics only (09 §P2); targeted removal is `evict`.
- Errors: shrink that would evict the control-plane datastore holder → 2 pointing at
  `datastore attach --to` first.
- Gate: D. MCP: exclude: `Mutates node pools.` (as today)

#### `cluster join <machine> --cluster <c>` (NEW, 06 §4)
- Help: `Add a registered machine to a cluster as an agent node.`
- Errors: machine already in a cluster → 2 naming it; machine not set up → 2 pointing
  at `machine setup`; join failure → 14.
- Idempotency: already a member of THIS cluster = no-op 0.
- Gate: D. MCP: exclude: `Cluster membership mutation.`

#### `cluster evict <machine>` (NEW, 06 §4)
- Help: `Remove a node from its cluster: drain, fence, delete, deregister.`
- Flags: `--force` (skip the drain when the node is dead — the failure path of the
  codified F3 sequence), `-y`.
- Cluster derived from the machine's membership backref; no `--cluster` flag.
- Errors: machine holds an attached datastore → 2 teaching "move it first:
  rdc datastore attach <ds> --to <other>"; not a member → 5.
- Gate: D. MCP: exclude: `Cluster membership mutation.`

#### `cluster destroy <name>`
- Help: `Tear down a cluster and its provisioned machines.`
- Flags: `-y`, `--force` (destroy with datastores present — data loss; without it,
  clusters with named datastores → 2 listing them).
- Gate: D. MCP: exclude: `Destroys infrastructure.` (as today)

#### `cluster kubeconfig <name>`
- Help: `Print a kubeconfig for the cluster.` Raw YAML to stdout (§4.6 deviation).
- Gate: A. MCP: mcp(read) (as today).

#### `cluster snapshot create <name>` / `cluster snapshot list <name>` (NEW, R2-F13)
- Help: `Snapshot every datastore in the cluster at one instant.` /
  `List cluster snapshots.`
- `create` flags: `--snapshot <label>` (default timestamp). Porcelain over
  `datastore snapshot --group` (which stays as plumbing).
- Local-tier datastores in the cluster: listed in the payload as outside the group
  instant (03 §3), warning not error.
- Gate: create D; list A. MCP: create exclude: `Infrastructure snapshot.`;
  list mcp(read).

#### `cluster fork <name> --tag <tag> --to <places...>`
- Help: `Fork a running cluster from one instant. The source never stops.`
- Flags (06 §3 contract): `--tag` required; `--to <machine...|cluster>` required
  (any node count — anchor+rejoin, 04 §1); `--writes <ceph|local>` default `ceph`
  `[P0-DECIDED]` (durable unless the user opts into ephemeral); `--up` (boot after
  fork); `--cow-size <size>` (with local).
- Errors: same-machine fork → 2 (04 §7: two k3s cannot share a host netns); mount-path
  collision on a dest → 2 (F12); non-embeddable distro → 2 first-class "not applicable"
  (02 §10b); group-snap unsupported → 14 (spike-a fallback text).
- Fork invariants stated in output: fresh PKI, scrubbed secrets, ROLE=fork (04 §2.4).
- Exits: infra failure → 14; `--up` health-gate failure → 13 (fork kept for inspection,
  stated).
- Gate: D. MCP: exclude: `Clones a whole cluster.` (as today)

#### `cluster migrate <name> --to <places...>`
- Help: `Move a cluster to new machines. Zero copy inside Ceph, staged copy across sites.`
- Behavior: transport disclosure BEFORE cutover (in-Ceph fenced remap vs cross-site
  snapshot+diff pipeline — 06 §7.4); down() → final snap → diff → up() → per-repo
  health gate; CA preserved (same principal), secrets stay.
- Flags: `--to` required; `--bwlimit <l>`; `--health-window <seconds>` default 300 and
  `--health-timeout <seconds>` default 30 (G6/C5); `--rehearsed` `[P0-DECIDED]` optional
  assertion flag: refuse (exit 2) if no rehearse of the latest snapshot succeeded on
  the dest — scripting hook for the canonical rehearse-then-migrate flow.
- Exits: pre-cutover → 14 (source intact); health gate → 13 (source restarted);
  `--to` current placement → no-op 0.
- Gate: D. MCP: exclude: `Moves a whole cluster.` (as today)

#### `cluster rehearse <name> --on <machine>` (NEW)
- Help: `Boot a throwaway copy of the cluster from a snapshot, health-check it, discard it.`
- Flags: `--on <machine>` required; `--snapshot <label>` (default: latest);
  `--keep` (skip the discard, keep the ephemeral fork for inspection);
  `--health-window <seconds>` default 300, `--health-timeout <seconds>` default 30
  (G6/C5 — a k3s-upgrade rehearse is the canonical case for a longer window).
- Behavior: `--writes local` fork of the group snapshot, ROLE=rehearsal, secretless by
  policy (04 §4 — documented, apps degrade), health gate, report, discard.
- Exits: 0 = gate passed (and discarded unless --keep); 13 = gate failed (report in
  payload; fork kept, named, discard instructions printed); 14 = infra failure.
- Gate: D. MCP: exclude: `Provisions a throwaway cluster; operator unlock only.`

### 5.6 `rdc backup` (10 leaves)

Unifies `machine backup *`, `repo backup *`, `config backup-strategy *` (06 §2).
Strategies are named records in config; runs are machine-scoped systemd-driven
executions; artifacts are addressed `repo[:tag]@place`. `-m/--machine` REMAINS on this
noun (a strategy can apply to several machines; nothing to derive from).

#### `backup strategy set <name>`
- Help: `Create or update a named backup strategy.`
- Flags (today's `config backup-strategy set`): `--destination <place>`,
  `--storage <s>`, `--cron <expr>`, `--mode <mode>`, `--bwlimit <l>`,
  `--include <repos>`, `--exclude <repos>`, `--folder <path>`, `--enable`, `--disable`.
- Idempotency: set semantics (upsert) — deliberately NOT create class; help says
  "create or update".
- Gate: A. MCP: exclude: `Backup policy mutation; use CLI directly.`

#### `backup strategy remove <name>` / `backup strategy list` / `backup strategy show [name]`
- Help: `Remove a backup strategy.` / `List backup strategies.` / `Show one strategy.`
- Gate: A. MCP: list/show mcp(read); remove exclude: `Backup policy mutation.`

#### `backup schedule --machine <m>`
- Help: `Install or repair the machine's scheduled backup timers.`
- Flags kept: `--dry-run`, `--force`, `--reset-failed`.
- Idempotency: convergent reconcile (today's backup-schedule-reconcile behavior).
- Gate: A. MCP: exclude: `Systemd unit management.` (as today's machine backup)

#### `backup run [strategy] --machine <m>` (renamed from `machine backup now`, R2-F16)
- Help: `Run a backup now.`
- Args: `strategy` positional optional — omitted with exactly one strategy configured
  for the machine = that one; several = exit 11 listing them.
- Flags: `-w/--watch` (follow to completion; without it, returns the run id async).
- Errors: already running → **15 with the running id in the payload** (the R2-F15
  worked example); no strategy configured → 5 pointing at `backup strategy set`.
- Gate: A. MCP: mcp(write, destructive:false, idempotent:false; excludeOptions: watch).

#### `backup status --machine <m> [strategy]`
- Help: `Show running and recent backups for a machine.`
- Gate: A. MCP: mcp(read).

#### `backup cancel --machine <m> [strategy]`
- Help: `Cancel a running backup.`
- Idempotency: nothing running = no-op 0.
- Gate: A. MCP: mcp(write, idempotent).

#### `backup list [artifact-ref] --machine <m> | --storage <s>`
- Help: `List backup artifacts on a machine or storage.`
- Args: optional `repo[:tag][@place]` filter (§3.1). Flags: exactly one of
  `--machine <m>` / `--storage <s>` unless the filter carries `@place`; `--path <sub>`;
  `-w/--watch`.
- Gate: A. MCP: mcp(read).

#### `backup restore <artifact-ref>` (NEW, R2-F16)
- Help: `Turn a backup artifact into a live repository. Placement is stated here.`
- Args: `artifact-ref` = `repo[:tag]@place` — the `@place` is the REQUIRED referent
  (§3.1); missing `@place` → 2 teaching the artifact grammar.
- Flags: `--as <name>` (default: artifact repo name); exactly ONE placement flag
  `--machine <m>` | `--datastore <d>` (same rule + same teaching errors as
  `repo create`, 02 §7); `--up` (deploy after restore); with `--up`:
  `--health-window <seconds>` default 300, `--health-timeout <seconds>` default 30
  (G6/C5); `-y`.
- Errors: target name already live → 2: "shop already exists; restore under another
  name (--as) or promote/delete the existing repo first." Restore never overwrites and
  never promotes (R2-F16). Transfer failure → 14; `--up` gate failure → 13 (restored
  repo kept, not started).
- Idempotency: create class on the target name.
- Gate: B (grandGuard on the write side). MCP: mcp(write, destructive, idempotent:false).

### 5.7 `rdc storage` (6 leaves)

External backup endpoints (S3, rsync targets). Absorbs `config storage *` (06 §2);
`storage rename` dies (R2-F4). Verbs are **`add`/`remove`** per gate ruling R3 (a
storage record registers an existing external endpoint; 06 §7.1's own rule).

- `storage list [name]` — Help: `List storage endpoints. Give a name for full detail.`
  Flags: `--reveal` (with `name`; TTY-gated — absorbs `config storage show`, U2b
  confirmed by R3). Gate: A. MCP: mcp(read; excludeOptions: reveal).
- `storage add <name>` — Help: `Register a storage endpoint.` Flags: today's factory
  create options for storage records. Add class (§4.5). Gate: A. MCP: mcp(write).
- `storage remove <name>` — Help: `Remove a storage endpoint from the config.`
  Flags: `-y`, `--dry-run`. Errors: referenced by a strategy → 2 listing referents.
  Gate: A. MCP: mcp(write, destructive).
- `storage import <file>` — Help: `Import a storage endpoint from a definition file.`
  Flags: `--name <n>` override. Positional migration from `--file`. Gate: A.
  MCP: exclude: `Reads local files.`
- `storage browse <name>` — Help: `Browse files on a storage endpoint.` Flags:
  `--path <sub>`. Interactive TTY browser (raw). Gate: A. MCP: exclude: `Interactive
  file browser; requires TTY.` (as today)
- `storage prune <name> --machine <m>` — Help: `Delete old backup artifacts by policy.`
  Flags kept: `--dry-run`, `--force`, `--force-delete-mounted`, `--grace-days <n>`.
  Gate: A. MCP: mcp(write, destructive, idempotent; excludeOptions: grace-days,
  force-delete-mounted) (as today).

### 5.8 `rdc term` (1 leaf)

#### `term connect <target>`
- Help: `Open a shell on a machine, or inside a repository with its Docker set up.`
- Args: `target` positional = place (machine shell) or `repo[:tag][@place]` (repo
  shell; derived machine per §2.3; collision rule §3.3). Replaces `-m` + `-r`.
- Flags kept: `-c/--command <cmd>` (run one command; exit code passthrough per §1),
  `--external`, `--reset-home`. DELETED `[P0-DECIDED]`: `--container`,
  `--container-action`, `--log-lines`, `--follow` — the container side door is retired
  in favor of `repo logs` / `repo exec` (R2-F14); `-t/--team` (dead vocabulary).
- Gate: repo-shell form B (grandGuard, as today's `term repo`); machine form A.
  MCP: exclude: `Interactive shell.`

### 5.9 `rdc vscode` (6 leaves)

Kept as-is (06 §5) with addressing migration on `connect`.

- `vscode connect <target>` — Help: `Open VS Code on a machine or inside a repository.`
  Target grammar as `term connect`. Flags kept: `-f/--folder <path>`, `--url-only`,
  `-n/--new-window`, `--skip-env-setup`, `--insiders`, `--browser`, `--no-open`,
  `--local <port>`, `--server-provider <id>`, `--server-archive <file>`. `-t` deleted.
  Gate: repo form B (as today's `vscode repo`). MCP: exclude (group): `Opens a GUI.`
- `vscode list` — Help: `List VS Code remote connections.` Gate: A.
- `vscode cleanup` — Flags: `--all`, `-c/--connection <name>`. Help: `Remove stale VS
  Code remote state.` Gate: A.
- `vscode check` — Flags: `--insiders`. Help: `Check VS Code remote prerequisites.` Gate: A.
- `vscode serve status|stop <target>` — Flags: `--server-provider <id>`. Help: `Show the
  remote VS Code server.` / `Stop the remote VS Code server.` Gate: A.
- MCP: whole noun excluded (as today): `Opens VS Code GUI.`

### 5.10 `rdc ops` (6 leaves)

Local KVM dev fleet; unchanged surface (06 §5), no addressing changes (ops has its own
VM-id vocabulary).

- `ops up` — Flags: `--force`, `--parallel`, `--basic`, `--lite`,
  `--skip-orchestration`, `--backend <b>`, `--os <name>`. Help: `Start the local VM fleet.`
- `ops down` — Flags: `--backend <b>`. Help: `Stop the local VM fleet.`
- `ops status` — Flags: `--backend <b>`. Help: `Show the local VM fleet.`
- `ops ssh --vm-id <id>` — Flags: `-c/--command <cmd>`, `--backend <b>`, `--user <u>`.
  Help: `SSH into a fleet VM.` Exit: passthrough with `-c`.
- `ops setup` — Help: `Install host prerequisites for the VM fleet.`
- `ops check` — Help: `Check host virtualization support.` Exit 1 on failed checks.
- Gate: A (host-local; requires host KVM anyway). MCP: exclude (group, as today):
  `Requires host KVM/QEMU.`

### 5.11 `rdc subscription` (4 leaves)

Flattened per 06 §2: `activation status`, `repo status`, `refresh {activation,repos,repo}`
collapse into `status`/`refresh` with scope flags.

- `subscription login` — Flags: `-t/--token <t>`, `--server <url>`. Help: `Sign in to
  your Rediacc account.` Errors: auth → 3.
- `subscription logout` — Help: `Sign out and remove the stored token.` Idempotency:
  not signed in = no-op 0.
- `subscription status [-m <machine>]` — Help: `Show subscription, and license state for
  a machine.` No `-m` = account view; with `-m` = activation + per-repo license table
  (absorbs `activation status`, `repo status`).
- `subscription refresh [-m <machine>] [--repo <ref>]` — Help: `Refresh licenses from
  the account server.` No flags = account; `-m` = machine activation + repos;
  `--repo` narrows to one repo (requires `-m`... `[P0-DECIDED]` no: `--repo` takes a
  ref and derives the machine per §2.3; `-m` remains for the machine-wide form).
  Errors: license refresh rejection → 10 where renet reports it; payment → 8.
- Gate: A. MCP: exclude (noun, as today): `License management; local concern.`

### 5.12 Top-level singles (5 leaves)

- `doctor` — Help: `Check this CLI installation and its dependencies.` Private
  `--output` dies (§4.6). Exit: 1 on failed checks. Gate: A. MCP: exclude: `Diagnoses
  the local install.` (as today)
- `credits` — Help: `Show subscription credits and licenses.` Flags: `--licenses`;
  private `--output` dies. Gate: A. MCP: exclude: `Local account view.` `[P0-DECIDED]`
  (was unannotated — one of the 56 drifted).
- `update` — Help: `Update this CLI to the latest release.` Flags kept: `--force`,
  `--check-only`, `--rollback`, `--status`, `--channel <stable|edge>`. Exit: per §1
  deviation. Gate: A. MCP: exclude: `CLI self-update.` (as today)
- `mcp serve` — Help: `Run the MCP server for AI agents.` Flags: `--config <name>`,
  `--timeout <ms>`. Gate: E. MCP: exclude: `The MCP server itself.` (as today)
- `run` (hidden) — unchanged: `-f/--function <name>` required, `-m/--machine <m>`
  required, `--param k=v...`, `-w/--watch`. Exit: renet passthrough incl. 10.
  Gate: E (absolute agentBlocked). MCP: exclude: `Escape hatch; agents use typed
  tools.` (as today)

---

## 6. Mapping table: CURRENT tree → TARGET (for mechanical P4 execution)

The current tree below was enumerated from code (`packages/cli/src/commands/**`,
including the `commandFactory.ts` CRUD for machine/storage and the hidden `run` in
`shortcuts.ts`), not from memory: **162 current leaves**. Dispositions: `kept` (same
path, contract per §5), `renamed`, `moved`, `merged-into`, `replaced-by`, `deleted`.
Every row's target contract is in §5; flag-level deltas are stated there.

### 6.1 `machine` (17)

| Current | Disposition | Target |
|---|---|---|
| `machine list` | kept | `machine list` |
| `machine create` | replaced-by | `machine add` (add/remove naming, 06 §2; one pair, not two) |
| `machine rename` | deleted | names are identity (R2-F4); delete + re-add |
| `machine delete` | replaced-by | `machine remove` |
| `machine query` | renamed | `machine status` (section flags kept + `--datastores`) |
| `machine health` | kept | `machine health` |
| `machine prune` | kept | `machine prune` |
| `machine provision` | kept | `machine provision` |
| `machine deprovision` | kept | `machine deprovision` (MCP appendArgs --force removed) |
| `machine containers` | merged-into | `machine status --containers [--health-check]` |
| `machine services` | merged-into | `machine status --services [--stability-check]` |
| `machine repos` | merged-into | `machine status --repositories [--search]` |
| `machine backup list` | moved | `backup list --machine <m>` |
| `machine backup schedule` | moved | `backup schedule --machine <m>` |
| `machine backup now` | renamed+moved | `backup run [strategy] --machine <m>` (R2-F16) |
| `machine backup status` | moved | `backup status --machine <m>` |
| `machine backup cancel` | moved | `backup cancel --machine <m>` |

### 6.2 `storage` (6)

| Current | Disposition | Target |
|---|---|---|
| `storage list` | kept | `storage list [name]` (absorbs config storage show detail) |
| `storage create` | renamed | `storage add <name>` (gate ruling R3, add-vs-create rule) |
| `storage rename` | deleted | R2-F4 |
| `storage delete` | renamed | `storage remove <name>` (R3) |
| `storage browse` | kept | `storage browse <name>` |
| `storage prune` | kept | `storage prune <name> --machine <m>` |

### 6.3 `ops` (6) — all kept unchanged

`ops up`, `ops down`, `ops status`, `ops ssh`, `ops setup`, `ops check` → kept.

### 6.4 `datastore` (5)

| Current | Disposition | Target |
|---|---|---|
| `datastore init` | replaced-by | `datastore create <name>` (named, multi-datastore; 06 §2) |
| `datastore status` | kept (recontract) | `datastore status <name>` (named; `-m` dies) |
| `datastore resize` | kept (recontract) | `datastore resize <name> --size` |
| `datastore fork` | kept (recontract) | `datastore fork <name> --tag T [--attach-to M --writes ...]` (06 §3) |
| `datastore unfork` | replaced-by | `datastore detach <name:tag> --discard` (06 §2) |

New with no current ancestor: `datastore list`, `datastore attach`, `datastore detach`,
`datastore snapshot create|list`, `datastore delete`.

### 6.5 `repo` (44)

| Current | Disposition | Target |
|---|---|---|
| `repo up` | kept (recontract) | `repo up <ref>` (+`--no-start`; `-m`/`--cluster`/`--mount-only` die) |
| `repo down` | kept (recontract) | `repo down <ref>` (`--unmount` kept) |
| `repo status` | kept | `repo status <ref>` (+role/writes/replicas) |
| `repo list` | kept | `repo list` (place flags become filters) |
| `repo create` | kept (recontract) | `repo create <name>` (placement union; `--cluster` dies; 02 §7) |
| `repo delete` | kept | `repo delete <ref>` |
| `repo push` | kept (recontract) | `repo push <ref> --to <place>` (`--tag`, `--up` die — U3) |
| `repo pull` | kept | `repo pull <ref> --from <place>` |
| `repo backup list` | moved | `backup list <ref> --machine/--storage` |
| `repo backup schedule` | moved | `backup schedule --machine <m>` (was identical to machine's) |
| `repo migrate` | kept (recontract) | `repo migrate <ref> --to` (health gate; `--from` derived) |
| `repo fork` | kept (recontract) | `repo fork <parent-ref> --tag` (`--cluster`/`--to-cluster`/`--provider` die — U11) |
| `repo resize` | kept | `repo resize <ref> --size` (offline; help states grow+shrink) |
| `repo expand` | kept | `repo expand <ref> --size` (online grow-only) |
| `repo validate` | moved | `repo admin validate <ref>` |
| `repo autostart enable` | moved | `repo admin autostart enable <ref>` |
| `repo autostart disable` | moved | `repo admin autostart disable <ref>` |
| `repo autostart list` | moved | `repo admin autostart list --machine <m>` |
| `repo ownership` | moved | `repo admin ownership <ref>` |
| `repo template list` | moved | `repo admin template list` |
| `repo template apply` | moved | `repo admin template apply <ref> --template <name>` |
| `repo secret get` | kept | `repo secret get <ref> --key` |
| `repo secret list` | kept | `repo secret list <ref>` |
| `repo secret set` | kept | `repo secret set <ref> --key --value` (k8s Secret materialization at up) |
| `repo secret unset` | kept | `repo secret unset <ref> --key` |
| `repo sync upload` | kept | `repo sync upload <ref>` (`-t` dies) |
| `repo sync download` | kept | `repo sync download <ref>` |
| `repo sync status` | kept | `repo sync status <ref>` |
| `repo commit` | kept | `repo commit <ref> --message` |
| `repo branch` | kept | `repo branch <ref> --branch` |
| `repo checkout` | kept | `repo checkout <commit-ref> --tag` (`--ref` → positional) |
| `repo log` | kept | `repo log <ref>` (`--json` dies) |
| `repo merge` | kept | `repo merge <ref> --from` |
| `repo gc` | kept | `repo gc --machine <m> [--apply]` |
| `repo fsck` | moved | `repo admin fsck --machine <m>` |
| `repo mount` | merged-into | `repo up <ref> --no-start` (06 §2) |
| `repo unmount` | merged-into | `repo down <ref> --unmount` (06 §2) |
| `repo cat` | kept | `repo cat <ref> --remote-file` |
| `repo diff` | kept | `repo diff <ref> [--base]` (`--json` dies) |
| `repo tunnel` | kept | `repo tunnel <ref>` (`-r`/`-m` → positional) |
| `repo takeover` | renamed | `repo promote <fork-ref>` (06 §2) |
| `repo trim` | kept | `repo trim [ref]` |
| `repo policy set` | kept | `repo policy set [ref]` |
| `repo policy get` | kept | `repo policy get [ref]` |

New with no current ancestor: `repo logs`, `repo exec`, `repo replicate` (+`status`,
`remove`), `repo admin archive list|restore|purge` (from config, below).

### 6.6 `run`, `term` (2)

| Current | Disposition | Target |
|---|---|---|
| `run` (hidden) | kept | unchanged; absolute agent block |
| `term connect` | kept (recontract) | `term connect <target>` (`-m`/`-r`/`-t` → positional; container flags die — U4) |

### 6.7 `subscription` (7)

| Current | Disposition | Target |
|---|---|---|
| `subscription login` | kept | `subscription login` |
| `subscription logout` | kept | `subscription logout` |
| `subscription status` | kept (recontract) | `subscription status [-m]` |
| `subscription activation status` | merged-into | `subscription status -m <m>` |
| `subscription repo status` | merged-into | `subscription status -m <m>` (per-repo table) |
| `subscription refresh activation` | merged-into | `subscription refresh -m <m>` |
| `subscription refresh repos` | merged-into | `subscription refresh -m <m>` |
| `subscription refresh repo` | merged-into | `subscription refresh --repo <ref>` |

### 6.8 `config` (57)

| Current | Disposition | Target |
|---|---|---|
| `config init` | kept | `config init [name]` (bare form teaches auto-creation) |
| `config list` | kept | `config list` |
| `config show` | kept | `config show` |
| `config delete` | kept | `config delete <name>` |
| `config set` | kept (recontract) | `config set <key> <value>` (`team`/`region`/`machine` keys die, R2-F9) |
| `config clear` | kept (recontract) | `config clear [key]` |
| `config recover` | kept | `config recover [name]` (stale-state degradation per R2-F2) |
| `config prune` | kept | `config prune` |
| `config machine add` | moved | `machine add <name>` (`--datastore <path>` dies) |
| `config machine remove` | moved | `machine remove <name>` |
| `config machine list` | merged-into | `machine list` (duplicate dies) |
| `config machine scan-keys` | moved | `machine scan-keys [name]` |
| `config machine setup` | moved | `machine setup <name>` (auto-creates default datastore) |
| `config machine set-ceph` | deleted | datastore-backend property: `datastore create --backend rbd` (06 §2) |
| `config provider add` | moved | `machine provider add <name>` |
| `config provider remove` | moved | `machine provider remove <name>` |
| `config provider list` | moved | `machine provider list` |
| `config repository add` | deleted | GUID mapping is internal (06 §2) |
| `config repository remove` | deleted | same (repo delete `--archive-config` covers the record) |
| `config repository list` | deleted | same; `repo list` is the surface (update CLAUDE.md + MCP tool) |
| `config repository list-archived` | moved | `repo admin archive list` |
| `config repository restore-archived` | moved | `repo admin archive restore <name>` |
| `config repository purge-archived` | moved | `repo admin archive purge [name]` |
| `config storage import` | moved | `storage import <file>` |
| `config storage remove` | moved | `storage remove <name>` (R3) |
| `config storage list` | merged-into | `storage list` |
| `config storage show` | merged-into | `storage list <name> [--reveal]` (U2b, confirmed by R3) |
| `config cluster add` | merged-into | `cluster create <name> [--declare-only]` (06 §2) |
| `config cluster add-pool` | deleted | pools declared at create / edited via `cluster scale` (06 §2) |
| `config cluster list` | merged-into | `cluster status` (no-name form) |
| `config cluster remove` | merged-into | `cluster destroy` |
| `config infra set` | moved | `machine infra set <m>` |
| `config infra show` | moved | `machine infra show <m>` |
| `config infra push` | moved | `machine infra push <m>` |
| `config cert-cache pull` | moved | `machine infra cert pull <m>` |
| `config cert-cache push` | moved | `machine infra cert push <m>` |
| `config cert-cache status` | moved | `machine infra cert status <m>` |
| `config cert-cache clear` | moved | `machine infra cert clear <m>` |
| `config backup-strategy set` | moved | `backup strategy set <name>` |
| `config backup-strategy remove` | moved | `backup strategy remove <name>` |
| `config backup-strategy list` | moved | `backup strategy list` |
| `config backup-strategy show` | moved | `backup strategy show [name]` |
| `config remote enable/disable/status/refresh` | kept ×4 | unchanged |
| `config ssh set/show/remove` | kept ×3 | `config ssh set <path>` positional |
| `config field get/set/unset/rotate/list` | kept ×5 | positional pointers (§5.1) |
| `config audit log/tail/verify` | kept ×3 | unchanged |

New with no current ancestor: `config edit`, `config reconcile`.

### 6.9 `doctor`, `update`, `credits`, `vscode`, `mcp` (10)

| Current | Disposition | Target |
|---|---|---|
| `doctor` / `update` / `credits` | kept ×3 | private `--output` flags die (§4.6) |
| `vscode connect/list/cleanup/check` | kept ×4 | `connect <target>` positional |
| `vscode serve status/stop` | kept ×2 | unchanged |
| `mcp serve` | kept | unchanged |

### 6.10 `cluster` (8)

| Current | Disposition | Target |
|---|---|---|
| `cluster create` | kept (recontract) | `cluster create <name>` one-step (absorbs config cluster add flags) |
| `cluster status` | kept | `cluster status [name]` |
| `cluster scale` | kept | `cluster scale <name>` (pool-count only; removal case → `evict`) |
| `cluster install` | deleted | folded into `cluster create` (06 §2) |
| `cluster destroy` | kept | `cluster destroy <name>` |
| `cluster kubeconfig` | kept | `cluster kubeconfig <name>` |
| `cluster fork` | kept (recontract) | `cluster fork <name> --tag --to [--writes] [--up]` (06 §3) |
| `cluster migrate` | kept (recontract) | `cluster migrate <name> --to` (transport disclosure + gate) |

New with no current ancestor: `cluster join`, `cluster evict`,
`cluster snapshot create|list`, `cluster rehearse`.

Tally: 162 current leaves — every one carries a disposition above; 25 new leaves have no
ancestor (marked "new" per noun). Nothing in `packages/cli/src/commands/**` is
unaccounted for as a COMMAND; the residual findings below are contract-level, not
missing rows.

---

## 7. Gate findings U1-U8 — dispositions after the P0 gate review

Original findings kept for the record; each now carries its ruling from
`docs/design/spec/00-gate-review.md`. Nothing here remains open for P4.

- **U1 — `machine infra` missing from the 06 §1 tree.** RESOLVED (accepted with R2's
  tree-as-drawn ruling): this spec includes the subtree (§5.2, 7 leaves, `cert` nesting
  `[P0-DECIDED]`); 06 §1 gets the one-line fix in the as-built pass.
- **U2 — `storage create|delete` vs the add/remove rule.** RESOLVED by ruling R3:
  renamed to `storage add`/`storage remove` (§5.7, §6.2, §6.8 updated).
- **U2b — `config storage show` target.** CONFIRMED by R3: `storage list <name>
  [--reveal]` absorbs it.
- **U3 — `repo push --up` deletion.** APPROVED by ruling R4: a pushed copy is a backup
  artifact (06 §6.5); replacement flows are `backup restore <ref>@<place> --up` and
  `repo migrate`. P4 updates the documented CLAUDE.md/docs snippets (already a 06 §8
  gate item).
- **U4 — `term connect` container flags deleted** in favor of `repo logs`/`repo exec`
  (R2-F14). Stands as specced; no gate objection recorded.
- **U5 — leaf count.** RESOLVED by ruling R2: 153 leaves is the contract; "~90" retired
  as wrong arithmetic (see §0 note). No scope cut.
- **U6 — `repo fork --to-cluster/--provider` deleted, `--detach` kept.** Stands as
  specced; no gate objection recorded.
- **U7 — MCP surface promotions/demotions** (`repo cat` gains a tool; `repo promote`
  loses one; `machine deprovision` loses `appendArgs: ['--force']`; `repo sync *`
  explicit exclude; `credits` annotated). Stand as the P4 MCP-gate seed classification,
  revisitable there. The gate additionally recorded the `repo replicate` gate-B (not D)
  tension for that same P4 record.
- **U8 — `backup schedule` per-machine systemd model.** CONFIRMED by ruling R5: spec 01
  keeps all 9 `backup_*`/`checkpoint_*` bridge functions unchanged; §5.6's model is
  today's proven shape.

## 8. P4 execution checklist hooks (cross-references, no new obligations)

Regeneration obligations are 06 §8 verbatim (cli-docs, skill reference,
validate-cli-examples, command-metadata re-annotation from §4.7/§5, CLI i18n en + 12
locales, renet-contract types + e2e-coverage, MCP tree-walk gate with this file's §5 MCP
fields as the starter classification). The §1 exit-code names land in
`packages/cli/src/types/index.ts` (`EXIT_CODES` 11-15) and `types/errors.ts`
(`ERROR_CODES`) in the same phase.
