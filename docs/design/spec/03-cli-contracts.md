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

## 0. The leaf count is NOT the contract. The mapping is. (AMENDED 2026-07-13)

Gate ruling R2 retired the "~90" prose figure as wrong arithmetic and put **153 target
leaves** in its place, derived from a **162-leaf** current baseline. Both of those numbers
have now failed, in exactly the way "~90" failed:

1. **The 162 baseline is arithmetically wrong.** §6's mapping tables enumerate **163** rows
   (machine 17, storage 6, ops 6, datastore 5, repo 44, run+term 2, subscription 8, config
   57, singles 10, cluster 8). The 162 comes from §6.7's header, which says
   "subscription (7)" while the table beneath it lists 8 rows. The published baseline was
   off by one on the day it was published. (§6.7's header is corrected below; the tables
   were right, the header was not.)
2. **It went stale within days.** Operator commits landed 19 invokable commands after this
   spec was written, including an entire new noun. Measured 2026-07-13 by walking the live
   Commander tree: **179 leaves in `command-tree.json`, plus 3 actionable parents
   (`repo replicate`, `repo canary`, `subscription refresh`, each carrying an `.action()`
   AND subcommands), plus the hidden `run` = 183 invokable commands.**
   `walkContractCommands()` reports 182 of those (it excludes `run`); a naive leaf-walk of
   the JSON reports 179 and silently drops the three actionable parents. Any P4 tooling
   that counts must use the walker, not a subcommand-empty test.
3. Both figures also ignore actionable parents entirely. At spec time there was one
   (uncounted); today there are three.

**RULING (extends R2 one step): the mapping is the contract; the count is descriptive.**
A figure its author could not compute correctly, and that every merge invalidates, is not
serving as a contract; a P4 that treats "153" as a pass/fail gate will spend its budget
arguing with merges instead of shipping the reshape. What P4 is held to is **§6: every
command in the live tree carries a disposition row, and every disposition row resolves to
a real command.** Both halves are mechanically checkable now that `command-tree.json`
exists and both new gates walk the live tree, and unlike a number they cannot be satisfied
by accident. Make that the CI gate.

Descriptive figures, for orientation only, with no contractual force: ~183 invokable
commands today; the reshape lands at **165** (163 if the two foldable leaves in §9 fold).
The honest simplification claim is unchanged and does not depend on a number: the DAILY
surface consolidates (config 57 to 25, repo plumbing under `repo admin`, five backup
surfaces unified).

The program plan's P4 task is reworded accordingly: "full CLI reshape **per the §6 disposition
table**", never "153 leaves". The two gate reviews that still quote the old figure
(`spec/00-gate-review.md` R2, `spec/10-p3-gate-review.md` carry-in 16) carry a superseded
note; they are historical records and are annotated, not rewritten.

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

| 130 | `DETACHED` | **[AMENDED 2026-07-13]** The operator pressed Ctrl-C while following a running detached job (`job logs --follow`), or a followed job ended nonzero. NOT a failure of the CLI: the job is running under systemd, not under this terminal, and a user stopping a scrolling log is not asking to destroy a half-finished migration. 130 is the SIGINT convention (128+2) and is deliberately outside the 0-15 block, so a script can tell "you detached" from "the operation failed". Already implemented as `EXIT_DETACHED` in `packages/cli/src/commands/job.ts:42`; this table is catching up to the code. | n/a |

Deviations (exhaustive; every other leaf uses the table as-is):

- `rdc run` (hidden), `rdc repo exec`, `rdc term connect -c` — propagate the REMOTE
  command's exit code verbatim (ssh semantics). The table applies only to failures that
  happen before the remote command runs.
- **`rdc job logs --follow` [AMENDED 2026-07-13]** — two deviations, both live in
  `commands/job.ts`. Ctrl-C during a follow exits **130** (above), and a follow that runs
  to a FAILED job's completion propagates **the job's own `exit_code`** verbatim
  (`job.ts:248`), which is a remote renet code, not a code from this table. Same rationale
  as `repo exec`: the CLI is a viewport onto a remote process, and remapping its exit code
  would destroy the only thing the operator asked for.
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

### 2.0 PREREQUISITE: the contract is options-only, and it hard-throws on positionals (BLOCKER, 2026-07-13)

**P4's first deliverable is a positional-argument serialisation rule in the contract layer.
It is not a command rename. Nothing in §2.2 can land before it.**

The CLI has **zero** positional arguments today (verified by walking the live Commander
tree). That is not an accident of style: it is load-bearing. Every consumer of the
generated CLI contract serialises a command as **flags alone**, and the shared tree walker
enforces it. `walkContractCommands()`
(`packages/cli/scripts/lib/command-tree-lib.ts:270-279`) throws on the first command that
registers one:

> `Command "repo up" registers positional argument(s): ref.`
> `The CLI contract is options-only: every contract consumer (web console, --proxy thin
> client, executor) serialises a command as flags alone.`
> `Add a positional-argument serialisation rule to the contract (types.ts ContractCommand
> + generate-cli-contract.ts) before registering positionals.`

That walker is shared by the contract generator, the plane gate and the plane-coverage
test, so **the first leaf P4 converts to a positional takes down `check:ci-cli-contract`,
`check:ci-command-planes` and `plane-coverage.test.ts` simultaneously**, and the failure is
a thrown exception in a build script, not a diff. The error message is the work order.

This is not a cosmetic gate. The wire format really is options-only:

| Consumer | Code | What a positional does today |
|---|---|---|
| `--proxy` thin client | `paramsFromCommand`, `packages/cli/src/services/executor/proxy-command.ts:81-96` | iterates `entry.options` only. A positional **silently does not travel**: the executor runs the command with the name argument simply missing |
| Executor daemon | `buildFlags`, `packages/cli/src/services/serve/command-dispatch.ts:137-150` | reconstructs argv from `entry.options` only, and REFUSES anything undeclared as argv-injection defence |
| Web console | `fieldDescriptors`, `private/account/web/src/lib/contract-form.ts:114-115` | is `entry.options.map(...)`. A positional **gets no form control at all**, and the render gate (`check:ci-console-coverage`, which requires one labeled control per field) passes while the form is unusable |

**Scope of the prerequisite** (cross-repo: console + the account submodule):

1. `packages/shared/src/cli-contract/types.ts`: `ContractCommand` grows a positional
   descriptor (name, required, variadic, and the ref-kind so a consumer knows to render a
   repo/machine picker; see the `machineOption`/`repoOption` trap below).
2. `packages/cli/scripts/generate-cli-contract.ts`: emit it. `walkContractCommands` already
   collects `registeredArguments`; today it throws instead of serialising them. Lift the
   throw, emit the descriptor.
3. `packages/cli/src/services/executor/proxy-command.ts`: put positionals on the wire.
4. `packages/cli/src/services/serve/command-dispatch.ts`: rebuild argv WITH positionals,
   in order, before the flags, keeping the refuse-the-undeclared property.
5. `private/account/web/src/lib/contract-form.ts`: render a control per positional.

**Trap that comes with it, and must be solved in the same change.**
`resolveMachineOption` (`generate-cli-contract.ts:183-187`) returns `'machine'` if a
`--machine` option exists, else `'name'` on the `machine` domain, else `null`.
`resolveRepoOption` (lines 194-203) mirrors it with `repoArg` / `--repo` / `--name` on the
`repo` domain. §2.2 kills `--name` tree-wide and §2.3 removes `-m/--machine` from every
repo verb, so **both resolvers return `null` for most of the reshaped tree** and the web
console's machine and repo PICKERS (`contract-form.ts:128-129`, keyed on
`entry.machineOption` / `entry.repoOption`) silently degrade to plain text inputs or vanish.
The contract needs a positional-ref concept that these resolvers can bind to. No gate
catches this: the console still renders, it just renders a worse form.

### OPERATOR RULING R-P4-1 (2026-07-13): BUILD THE REF CONCEPT. This is P4 task zero.

The options were:

| Option | Cost | Consequence |
|---|---|---|
| **A. Build the serialisation rule** | Real work in 5 modules across 2 repos, before a single command is renamed. It is a contract-shape change, so it also re-emits `contract.generated.ts` + `contract.json` + 13 i18n bundles and touches the account submodule's render gate. | §2.2 ships as designed. `rdc repo up shop` is the CLI the whole redesign is written around |
| B. Abandon positional names | Zero prerequisite work | Keeps `--name` tree-wide and `-m` on repo verbs. §2.2, §2.3, §3 (`@place` on the positional ref) and most of §5's help text are rewritten in flag terms. The addressing model 06 §6 was built to fix survives only in the derived-machine half |

**RULED: A.** The positional name is not decoration; it is what makes the
`repo[:tag][@place]` ref a single addressable token that verbs share, and it is the reason
`-m` can disappear. Option B would keep the CLI's central ergonomic defect and leave 06 §6
half-implemented. Nothing in §2.2 may land before this does.

#### What "a ref concept" means, precisely (the deliverable)

The naive reading of option A — "let the walker emit positionals" — is **not sufficient**,
and shipping only that would quietly break the operator's dynamic-GUI guarantee. A
positional is not just another field on the wire; for most leaves it is *the field the
console binds its resource pickers and its action buttons to*. Concretely, the deliverable
has two halves:

**Half 1 — serialisation (the wire).** `ContractCommand` grows a positional descriptor and
every consumer learns to carry it:

```ts
positionals: [{ name: 'ref', kind: 'repo-ref', required: true, variadic: false }]
```

`kind` is the load-bearing field: `repo-ref` | `machine` | `datastore-ref` | `cluster` |
`storage` | `strategy` | `artifact-ref` | `job-id` | `target` | `file` | `plain`. It is what
lets a consumer know that this token names a repo without having to guess from the flag name.

**Half 2 — rebinding (the pickers).** Today the console resolves its machine and repo
pickers from `machineOption` / `repoOption`, i.e. from the *flags* `--machine` and
`--name` — the exact flags §2.2/§2.3 delete. `resolveMachineOption`/`resolveRepoOption`
(`generate-cli-contract.ts:183-203`) would return `null` across most of the reshaped tree,
and two things silently degrade:

- `fieldDescriptors` (`private/account/web/src/lib/contract-form.ts:114-115`) renders a
  plain text box where a resource picker belongs;
- **`ActionBar.tsx` empties.** Its own header states the invariant: *"The list is computed
  from the contract, never written down... There is no array of command names in this file,
  and there must never be."* A repo page's buttons are every command whose binding matches
  the context. Kill the binding and the buttons vanish — and because the commands are then
  no longer context-bound *at all*, the coverage gate can pass while the pages sit empty.

So the contract must expose the binding on the **ref**, not only on the flag:
`repoPositional` / `machinePositional` (or a single resolved `refBinding`) alongside the
existing `repoOption` / `machineOption`, and `prefillFor` / `fieldDescriptors` /
`ActionBar` bind to whichever is present. **The GUI guarantee is the acceptance test for
task zero**: after the reshape, `rdc repo up shop` must render as one repo picker, and the
repo page's action bar must still compute its buttons.

The five modules, in dependency order:

1. `packages/shared/src/cli-contract/types.ts` — `ContractCommand.positionals[]` + the ref
   bindings.
2. `packages/cli/scripts/generate-cli-contract.ts` — emit them; extend
   `resolveMachineOption`/`resolveRepoOption` to resolve through positionals; **re-key
   `PROXY_EXCLUSIONS`** in the same pass.
3. `packages/cli/scripts/lib/command-tree-lib.ts` — `walkContractCommands()` currently
   *throws* on `registeredArguments` (:270-279). Lift the throw, serialise instead.
4. `packages/cli/src/services/executor/proxy-command.ts` (`paramsFromCommand`) and
   `packages/cli/src/services/serve/command-dispatch.ts` (`buildArgv`) — put positionals on
   the wire and rebuild argv **positionals first, then flags**, preserving the
   refuse-the-undeclared property (it is argv-injection defence, not incidental strictness).
5. `private/account/web/src/lib/contract-form.ts` (+ `ActionBar` / `prefillFor`) — a control
   per positional, and the picker/action bindings moved onto the ref.

**Acceptance for task zero** (before any leaf is renamed): a temporary leaf carrying a
positional walks the contract, round-trips over `--proxy` to a local `rdc serve`, renders in
the console with a resource picker, and `check:ci-console-coverage` + `check:ci-cli-contract`
+ `check:ci-command-planes` + `plane-coverage.test.ts` are all green.

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

**Blocked on §2.0.** The first leaf that registers one of the positionals below throws in
`walkContractCommands()` and reds three gates at once. Read §2.0 before writing any of this.

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
grammar in P4 (06 §6.6). **[AMENDED 2026-07-13]** They are the SMALL half. This spec
originally named only the docs validators as the things that treat positional syntax as
invalid; the load-bearing one is the CONTRACT walker (§2.0), which does not warn, it throws.

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
(06 §8; `mcp` XOR `mcpExcludeReason` per leaf). **[AMENDED 2026-07-13]** Gate class and MCP
disposition are two of THREE per-leaf classifications P4 owes. The third, the execution
plane, did not exist when this spec was written. See §4.9 and §4.10.

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

### 4.9 Command planes: where a command RUNS, and the silent-flip hazard (NEW 2026-07-13)

Commit `c3dc6bf44` (enterprise proxy executor + dynamic web console) introduced a
per-command **plane**, and it constrains the reshape more sharply than anything else in
this document, because **the gates cannot catch the dangerous half of a mistake.**

**What a plane is.** A declared claim about where a command's code actually runs:

- `machine`: it reaches a customer machine (renet execute via
  `services/executor/local-executor`, `services/machine/*`, `remote/ssh`, `remote/sftp`,
  or `services/tofu`).
- `config`: it only reads or writes the local CLI config and resource state.
- `other`: neither of those. Local tooling (self-update, diagnostics, local KVM dev VMs,
  the MCP server), or an account-server HTTPS call. **An account-server call is NOT
  `machine`.**

It is a security-relevant trust label, not a cosmetic one. The generated contract turns
`plane === 'machine'` into `proxyCapable`, and both `rdc --proxy` and the web console use
that flag to decide whether a command may be shipped to a remote executor and run on the
operator's behalf (`packages/cli/src/config/command-planes.ts:1-25`).

**How it is decided: purely from the PATH STRING.** The data lives in exactly one
hand-maintained table, `COMMAND_PLANES` (`command-planes.ts:42-163`), keyed by the
space-joined command path (`"repo secret list"`). Resolution is longest-prefix ancestor
inheritance (`command-planes.ts:169-207`): `getCommandPlane("repo secret list")` tries
`"repo secret list"`, then `"repo secret"`, then `"repo"`. **A domain entry supplies the
default; every other entry is an exception.** Today's domain defaults:

| default `machine` | default `config` | default `other` |
|---|---|---|
| `machine`, `repo`, `cluster`, `term`, `job`, `datastore`, `vscode`, `serve` | `config`, `storage` | `subscription`, `ops`, `doctor`, `credits`, `update`, `mcp` |

`getCommandPlane` THROWS on an unresolvable path, so a command can never reach the contract
unclassified. A second, orthogonal flag rides in the same table and inherits the same way:
`interactive` (needs a TTY, or never returns). It kills proxyability independently of plane.

`proxyCapable` is **derived, never declared** (`generate-cli-contract.ts:229`):

```ts
const proxyCapable = plane === 'machine' && !interactive && !(w.pathKey in PROXY_EXCLUSIONS);
```

**Nothing derives the plane from the implementation.** The import-graph gate only
cross-checks it, and only at TOP-LEVEL DOMAIN granularity
(`packages/cli/scripts/check-command-planes.ts:157`, `const domain = cmd.path[0]`), with two
coarse rules: an isolated domain must declare zero machine leaves (Rule 1), and a
machine-reaching domain must declare at least one (Rule 2).

#### THE RULE FOR P4: every move is an implicit plane re-declaration

A command's plane is a pure function of its path string. **The reshape is therefore
completely free to move verbs between nouns, and the plane system will never block a move.
But it will not follow the verb either.** A moved verb silently adopts its new domain's
default, and the import-graph gate stays green because it only checks domain-level
reachability. The two cases behave differently, and the difference is the whole hazard:

**Case 1, LOUD and safe: `config machine set-ceph` becomes `datastore create --backend rbd`.**
`'config machine set-ceph': { plane: 'machine' }` is an EXPLICIT entry
(`command-planes.ts:110`). Deleting the leaf makes that key stale, and
`plane-coverage.test.ts:119-129` fails with `COMMAND_PLANES entries that are not commands in
the CLI tree: config machine set-ceph`. You cannot miss it. The new home inherits
`datastore: { plane: 'machine' }`: same plane, correct answer, arrived at honestly.

**Case 2, SILENT and dangerous: `config repository list` becomes `repo list`.**
`config repository list` has NO explicit entry; it inherits `config: { plane: 'config' }`.
Its contract entry today is `proxyCapable: false`. Move it under `repo` and it inherits
`repo: { plane: 'machine' }`, so **`proxyCapable` flips to `true`**. The web console now
offers it for remote execution, and `rdc --proxy repo list` now ships it to the executor,
**which reads the EXECUTOR's config file, not the caller's, and returns the executor's
repositories.** That is precisely the "local effect" class `PROXY_EXCLUSIONS` exists to
catch (`generate-cli-contract.ts:72-79`: *"the command reaches a machine, but its whole
point is to write what it found back into the CALLER's config... A remote executor would
write it into its own, and the caller would be none the wiser."*).

**And every gate stays green.** Rule 1 does not fire (the `repo` domain CAN reach a
machine). Rule 2 does not fire (`repo` has ~40 other machine leaves). The stale-entry test
does not fire (there was no explicit entry to go stale). The contract regenerates cleanly.
The only thing that changes is a `true` where a `false` used to be, buried in a 182-entry
generated JSON. This case is not hypothetical: **`repo list` already exists** as a
machine-plane command (`commands/repo.ts:346-352`, `-m/--machine`, queries live repos on a
machine), so §6.8 merges a config-plane lister and a machine-plane lister onto one pathKey.
Whichever implementation wins, the plane must be re-declared deliberately.

> **Plane classification is a FIRST-CLASS PER-LEAF DELIVERABLE of the reshape, reviewed leaf
> by leaf, not a regeneration afterthought.** For every leaf P4 moves into a machine-default
> domain, ask: *"would running this at a remote executor produce the CALLER's answer?"* If
> no, it needs either an explicit `plane: 'config'` entry in `COMMAND_PLANES` or an entry in
> `PROXY_EXCLUSIONS` with a user-facing refusal reason. **No gate will ask this for you.**

#### The loud traps, for completeness

- **Rule 2 fires when `config` loses its last machine leaf.** P4 moves
  `config machine scan-keys|setup|set-ceph`, `config infra push` and
  `config cert-cache pull|push` out of `config`. Those are ALL FIVE of `config`'s
  machine-plane leaves (`command-planes.ts:104-118`). If `config` ends with zero machine
  leaves while `commands/config.ts` still transitively imports `remote/ssh` or
  `services/machine/*`, Rule 2 fires. The CORRECT fix is to remove the now-dead machine
  imports from the config command module. The TEMPTING WRONG fix is an `OVERRIDES` entry,
  and the file warns against exactly that (`check-command-planes.ts:82`: *"Every entry here
  is a rule this gate stops enforcing"*). Do not paper over it.
- **A stale contract makes a renamed command fail-CLOSED under `--proxy`, which reads as a
  bug.** `cli.ts:213-221` does `assertProxyCapable(commandPath, entry?.proxyCapable ?? false)`.
  A rename with an unregenerated contract means `getCommand` misses and the `?? false`
  refuses the command with a generic "cannot be proxied" message. Safe, but it does not look
  like staleness. Regenerate the contract before testing any proxy path.
- **i18n key moves break `descriptionKey` silently.** The key is recovered by matching the
  RENDERED ENGLISH STRING back to `en/cli.json` (`command-tree-lib.ts:127-159`, first-wins,
  `options.*` deliberately ordered before `commands.*`). Give two commands the same English
  description, or move a key without moving its value, and `descriptionKey` goes `null`:
  the web console and `--lang` lose the translation with NO gate failing. **Keep English
  description strings unique per leaf.**

### 4.10 The three per-leaf classification systems (NEW 2026-07-13)

P4 must classify every reshaped leaf in all THREE. They are independent lookups that never
consult each other, and they are all keyed by the same space-joined path string, so a rename
must be applied to all three in the same commit.

| System | File | Keyed by | Inheritance | Stale-entry gate |
|---|---|---|---|---|
| **Plane** (`plane`, `interactive`) | `config/command-planes.ts` | full path | **yes**, ancestor | LOUD: `plane-coverage.test.ts` + `check-command-planes.ts` |
| **MCP** (`mcp`, `mcpExcludeReason`) | `config/command-metadata.ts` | full path | no, exact | LOUD: `mcp-coverage.test.ts` (checks exclusions against the live tree) |
| **Guardrails** (`grandGuard`, `forkBlocked`, `agentBlocked`) | `config/command-metadata.ts` | full path | no, exact | **NONE** |

They meet in exactly one place, `generate-cli-contract.ts:234-261`, which flattens all three
onto the same `ContractCommand`. Two couplings worth knowing:

- `resolveRepoOption` (`generate-cli-contract.ts:194-203`) reads the **MCP** `repoArg`
  annotation to decide which option the WEB CONSOLE renders as a repo picker. An MCP
  annotation therefore has a UI consequence.
- The MCP coverage test iterates `COMMAND_REGISTRY` at TOP-LEVEL DOMAIN granularity, so a
  new domain needs a registry entry AND either an MCP tool or an `mcpExcludeReason`.
  **Verified 2026-07-13: `COMMAND_REGISTRY` holds 13 domains while the live tree has 16.
  `job`, `cluster`, `credits` and `serve` are in no registry entry, so they are not
  MCP-checked at all** (which is how `serve` and `config rotate-cek` reached main with no
  `COMMAND_METADATA` entry of any kind, and it is the same hole 06 §8's 56-drifted-commands
  finding describes). `ContractCommand.group` is `null` for all four; the type's own comment
  saying "today: cluster and credits" is itself stale.

**The guardrail row is the one to fear: it has no stale-entry gate at all.**
`utils/command-policy.ts` looks up `COMMAND_METADATA[path]`, and a missed rename means
`grandGuard` simply **stops being enforced** on that command, quietly. The plane goes stale
loudly, the MCP entry goes stale loudly, the guardrail goes stale silent. Verify guardrails
per-leaf during P4; do not trust the gates to find them.

### 4.11 The policy layer: a FOURTH classification system, and the only one that fails OPEN (NEW 2026-07-13)

Not in any design document until now. The enterprise-proxy work (W8, commit `c3dc6bf44`)
landed a permission-policy layer — `packages/shared/src/policy/{schema,evaluate}.ts`,
`packages/cli/src/services/serve/policy.ts`, and the console's `PolicyRuleEditor.tsx` — and
**it is keyed by the command path string, exactly like the other three.**

A policy document is authored per organization, stored **inside the encrypted config**, and
evaluated by **both** the executor and the console UI (so the decision the console shows is
the decision the executor makes). Its rules carry command **globs**:

```ts
commands: {
  allow: ['repo *', 'machine status'],   // whitelist: a command must match at least one
  deny:  ['repo delete', 'cluster *'],   // deny outranks any allow, at any tier
}
```

Globs match the whole path, `*` spans segments (`schema.ts`). Two more couplings: `machines`
and `repos` globs scope a rule to resource names, and `evaluate.ts:55` **derives the
cluster-ops classification from the path prefix** (a leading `cluster` or `kube`), so moving
a verb across nouns can change its policy class as a side effect.

**Why this is the dangerous one.** P4 renames essentially every path. The two halves of a
policy fail in opposite directions:

| Stale glob | Failure direction | Result |
|---|---|---|
| `allow: ['repo takeover']` | **CLOSED** | the command is refused. Loud, safe, a user reports it |
| `deny: ['repo takeover']` | ⚠ **OPEN** | the moment the leaf becomes `repo promote`, the deny **silently stops denying**. The command the org explicitly forbade is now permitted, and nothing anywhere says so |

This is a security-relevant regression with **no gate**, in a document a customer authored
and reasonably expects to keep holding. The other three systems are, in comparison, safe:
plane and MCP go stale loudly; the guardrail goes stale silent but only *removes* an
unlock's requirement on a command the operator already had to unlock deliberately. The
policy deny-glob is the only one where staleness *grants* a permission that was explicitly
withheld.

**P4 owes three things here:**

1. **Re-key every authored glob** in lockstep with the rename, including the presets and
   fixtures in `PolicyRuleEditor.tsx`, `policy/__tests__/evaluate.test.ts`, and any policy
   document in the operator's own configs (sole operator, so this is bounded; there is no
   migration to write — per the no-backcompat rule, the rename is applied, not shimmed).
2. **A stale-glob gate.** Every glob in a policy document must match at least one command in
   the live tree, and the gate must be loudest on the `deny` side: a `deny` glob that matches
   nothing is a **failure**, not a warning, because its only possible meanings are "typo" or
   "the command it forbade was renamed out from under it".
3. **Re-verify the derived cluster-ops prefix rule** (`evaluate.ts:55`) against the reshaped
   tree: the reshape keeps `cluster` as a noun, so the prefix survives, but any verb moving
   INTO or OUT OF `cluster` changes its policy class silently.
4. **The detach coupling (found by the parallel detached-jobs pass):** an org with
   `allow: ['repo *'], deny: ['job *']` can *start* a detached command through the proxy but
   never reattach to it or read its outcome. Once the executor detaches by default (R-P4-2v2),
   enabling proxy execution effectively implies allowing `job status`/`job logs`; the policy
   evaluator or its documentation must say so, and the reattach route anchors its policy
   check on the real `job logs` contract command rather than inventing new vocabulary.
5. **A SECOND fail-open, found and fixed in task zero (w0-B, 2026-07-13): `targetFrom` read
   only the flag bag.** `services/serve/server.ts:targetFrom` resolved a command's policy
   target as `params[machineOption]` / `params[repoOption]` — the FLAG bags only. The moment
   §2.2 moves a noun's primary name onto a positional (`repo up shop` instead of
   `repo up --name shop`), the value lives in the `positionals` bag, so a machine- or
   repo-scoped rule resolves `undefined` and **silently stops matching** — the command runs
   unscoped, exactly the deny-side fail-open above but reached through the addressing change
   rather than a rename. This is a hard prerequisite of the ref concept, not a follow-up:
   landing positionals without it would ship the fail-open. **Fixed in task zero**:
   `targetFrom` now reads BOTH bags (`params[machineOption]` OR `positionals[machinePositional]`,
   and likewise for repo), and the loopback suite carries a positional-addressed deny test
   (`_refprobe run shop` against a `repos: ['locked-*']` allowlist → 403). The `*Positional`
   bindings the fix depends on are a distinct contract field from the `*Option` flag bindings
   precisely so this read cannot regress to one bag.

**The per-leaf checklist is therefore FIVE systems, not three** (§8.3): plane, MCP,
guardrails, policy globs, and the ref binding (§2.0) that the console's pickers and action
bars resolve through.

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
  **`--no-wait`** (RENAMED from `--detach` by ruling R-P4-2v2, §9 Q5: it means "return once
  the containers are started, health checks continue in the background", which is what
  `--no-wait` says and what `--detach` did not; after the rename the word "detach" no longer
  exists as a flag anywhere in the tree), `--all --machine <m>` batch form (§4.8),
  `--parallel`, `--concurrency <n>`, `--include-forks`, `-y`, `--dry-run`. Detached-job runs
  use the GLOBAL `--background`/`-b` (§5.13), not a per-verb flag.
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
  `--immutable` (create as immutable commit object); **`--no-wait`** (RENAMED from
  `--detach`, ruling R-P4-2v2 — this REOPENS AND SUPERSEDES U6, which had kept `--detach`
  here with the old meaning; detached-job runs use the global `--background`, §5.13).
  DELETED: `--cluster`,
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
- **`serve` [NEW-SINCE-SPEC, 2026-07-13]** — `rdc serve --mode <daemon|container>`,
  `-p/--port`, `--host`. The executor daemon: it runs machine operations on a caller's
  behalf, and it is the other end of the `--proxy` global flag. This section enumerated 5
  singles and did not know about it. Plane: `machine` + `interactive` (honest on both
  counts: running machine operations IS its job, and it listens until SIGINT, which is also
  what keeps it out of the proxy, since forwarding `rdc serve` to an executor would ask the
  executor to start another one). Gate and MCP disposition are UNSET in
  `COMMAND_METADATA` today, because the MCP coverage test never sees it (§4.10).
  **RULED (§9 Q4): `serve` STAYS a top-level single, and `--proxy` is contract-frozen.**
  They are the two ends of one wire; burying either would hide the mechanism that makes the
  generated contract load-bearing. P4 owes it a `COMMAND_METADATA` entry (Gate: E, absolute
  agentBlocked — an agent must never start an executor; MCP: exclude: `The executor daemon
  itself.`) and a `COMMAND_REGISTRY` entry so the MCP gate can finally see it.

**Global flags [AMENDED 2026-07-13].** The anchor at the top of this file
(`cli.ts:136-141`: `-o/--output`, `--config`, `-l/--lang`, `-q/--quiet`, `-y/--yes`,
`--fields`) predates **`--proxy <url>`** (`cli.ts:173`). It needs a contract row of its own:
`--proxy` is the thin-client entry point that makes the entire generated CLI contract
load-bearing rather than decorative, and it is why §2.0's positional blocker exists at all.
`REDIACC_PROXY_URL` is its env equivalent (`cli.ts:213`).

**P4 adds one more global: `--background`/`-b`** (R-P4-2v2, §5.13) — run the command as a
detached job, print the id and a resume hint, exit 0. Guarded by `assertDetachable` in the
same preAction hook that guards `--proxy`, BEFORE the `--proxy` branch; refusal on a
non-detachable command names the reason from `DETACH_EXCLUSIONS`, mirroring
`assertProxyCapable`.

### 5.13 `rdc job` (5 leaves) — NEW-SINCE-SPEC (2026-07-13)

Management surface over renet's detached-job spool: work runs under a transient systemd
unit on the machine, so it survives a dropped SSH channel, a closed laptop, or a Ctrl-C on
the log tail (`packages/cli/src/commands/job.ts`; renet's
`cmd/renet/job_commands.go`). Kept as a noun by 06 §9: a job is a real addressable resource
on the machine (an id, a state machine, logs, a lifecycle), and folding `job list` into
`machine jobs` would put one resource's CRUD on another resource's noun, which is exactly
what the reshape is undoing everywhere else. The noun deliberately has **no create verb**:
a job is born as a side effect of another verb.

**Nothing can fill the spool today.** `LocalExecutorService.tryDetachedExecution()` returns
`null` unless `ExecuteOptions.detached` is set, and no CLI command sets it
(`services/executor/local-executor.ts:1236`; the comment at :1225 says so outright, and a
grep across `commands/` and `services/serve/` confirms it). `rdc job` manages a spool no
`rdc` command can create an entry in.

#### OPERATOR RULING R-P4-2v2 (2026-07-13, §9 Q5+Q7, twice-ruled and MERGED): a job is EXECUTOR-BORN, plus a global `--background`/`-b`

The operator ruled this question in two sessions: this one chose a per-verb `--detach`; a
parallel session — which had additionally found that Commander resolves a root-level and a
subcommand flag of the same name **by position**, making any reuse of the word a silent trap
(`rdc --detach repo up` vs `rdc repo up --detach`) — chose a **global `--background`/`-b`**
with fire-and-forget semantics. The operator confirmed the MERGE (2026-07-13): the
better-informed flag decision wins, and this session's `--no-wait` rename survives, so the
word "detach" disappears from flags entirely. The parallel session's full findings are
preserved at `~/.claude/projects/-home-muhammed-monorepo-console/reports/handoff-detached-jobs.md`
(every claim file:line-anchored; the four load-bearing ones re-verified against this tree).

**Two producers, and the executor is the important one:**

1. **The executor births jobs automatically.** When a *detachable* command (see the contract
   annotation below) arrives through `rdc serve` (from the web console or a `--proxy` thin
   client), the dispatch layer sets `ExecuteOptions.detached` **itself and keeps following
   the live stream**. This is structural, not a convenience: the container tier is a warm
   Cloudflare Container that **sleeps after 2 to 5 minutes idle**, and you cannot know in
   advance which `repo up` takes 3 seconds and which takes 40 minutes. Client disconnect
   means **detach, not cancel** (an `AbortSignal` on the follow, from `c.req.raw.signal`).
   Version skew is already safe: on an old renet, `startJob` returns `null` and the run
   falls back to synchronous silently.
2. **Direct CLI stays synchronous; the global `--background`/`-b` is the opt-in, and it is
   FIRE-AND-FORGET**: start the job, print the job id plus a resume hint, exit 0. The user
   watches later via `rdc job logs <job-id> -m <machine>`. ⚠ This needs a **no-follow mode
   that does not exist**: today's `runDetachedExecution` (`local-executor.ts:1271`) always
   tails the job to completion. An `ExecuteOptions` follow bit (default true) that
   `--background` clears; the serve path keeps following.

`rdc job start -- <cmd>` was **rejected**: it re-creates the `run` escape hatch and defeats
typed commands.

**The word "detach" survives only as the `datastore detach` verb.** The flag table:

| Was | Now | Meaning |
|---|---|---|
| `repo up --detach` / `repo fork --detach` | **`--no-wait`** | return once containers start; health checks continue (renet `repository_up.go:30`) |
| (nothing) | **`--background` / `-b`, GLOBAL** | run the whole operation as a detached job; print id + hint; exit 0 |
| `datastore detach` | unchanged | unmount a datastore (a verb on a noun; docker and kubectl live with this overload) |

⚠ **This REOPENS AND SUPERSEDES gate finding U6** (§7), which explicitly kept `--detach` on
`repo fork` with the old meaning. Deliberate reversal: when U6 was written the `job` noun did
not exist, so there was no collision to see.

**`detachable` becomes a contract annotation**, derived next to `proxyCapable` in
`generate-cli-contract.ts` via a `DETACH_EXCLUSIONS` table beside `PROXY_EXCLUSIONS`
(proposed rule: `detachable = proxyCapable && domain !== 'job'` — the classes `proxyCapable`
already excludes are exactly the ones that break under detach, and detaching a `job` command
is circular). Enforced by an `assertDetachable` mirroring `assertProxyCapable`, in the
`cli.ts` preAction hook before the `--proxy` branch. **P4 keys `DETACH_EXCLUSIONS` by the NEW
tree's paths from birth** — it is one more path-keyed table (§8.3), and there is no reason to
key it by paths the same phase deletes.

**Two silent-corruption constraints, verified in this tree, that MUST land before anything
sets `detached`** (they are invisible until a producer exists, which is exactly what this
ruling creates):

- **The detached path discards stdout.** `jobStatusToExecuteResult` (`job-client.ts:417`)
  returns no `stdout`/`stderr`/`steps`, and under `captureOutput: true` the event handler is
  a no-op (`local-executor.ts:1296`) — so every `parseCapturedJson` caller (`cluster-fork.ts`
  ×4, `repo-replicate-ops.ts`, `cluster-ceph.ts`) breaks under detach. The fix is
  reconstruction from the spool's `output` events, and it is provably byte-exact (renet's
  `execute_command.go:215-224` feeds the same string to the event writer or to `Println`).
  **The same accumulator fixes bug #31**: the serve tap forces `eventsMode + captureOutput`
  and `runRemoteExecution` (`local-executor.ts:1176`) accumulates raw NDJSON into `stdout`,
  so `--proxy cluster fork` is broken TODAY, before any detach work.
- **The detached path bypasses license recovery and identity refresh.** `tryDetachedExecution`
  returns at `local-executor.ts:738`, above the `needsLicenseRecovery` block and
  `maybeRefreshRepoIdentity`. A detached exit-10 is never retried (safe to retry: renet
  refuses before doing work) and a detached `repo create`/`repo fork` never refreshes its
  repo identity.

**The reattach half is declared but dead, and the console is already waiting**: `wire.ts`
carries a `StreamLine kind:'job'` variant and a `PROXY_ROUTES.jobEvents` route that nothing
emits or implements — while `useCommand.ts:63` in the account console **already handles
`kind:'job'`**. P4 wires: the dispatch emits `{kind:'job', jobId, machine, sinceLine}` before
any event line; a `GET /v1/jobs/:id/events?machine&sinceLine` route (authenticated like
`/v1/command`, `assertJobId` FIRST — on this route the id arrives from an untrusted HTTP
client and is interpolated into a remote shell command); exactly-once reattach via per-event
spool line ordinals (chunk-granular resume would duplicate `output` events and corrupt the
reconstructed stdout). Known limitation, documented rather than hidden: a reattached stream
replays renet's spool; the Commander action body's own rendered envelope is gone with the
process that ran it.

`-m/--machine` REMAINS on this noun, on the same grounds as `backup` (§5.6): a job id has no
config record, so its machine cannot be derived from anything. Plane: `machine` for all five
(each SSHes to the machine to drive `renet job ...`), and **none is `interactive`** — even
`logs --follow` streams to stdout and ends on its own when the job finishes, so a headless
executor can drive all five. All five are therefore `proxyCapable`.

#### `job list --machine <m>`
- Help: `List detached jobs on a machine.`
- Gate: A. MCP: mcp(read).

#### `job status <job-id> --machine <m>`
- Help: `Show one job's state, timing, and outcome.`
- Args: **RULED (§9 Q9)** `job-id` positional (today `--id <jobId>`, a required option),
  `-m` explicit. Positional per §2.2; `-m` stays because a job id has no config record, so
  its machine cannot be derived from anything (the `backup` precedent, §5.6). Positional
  `kind: 'job-id'` (§2.0).
- Errors: unknown id → 5.
- Gate: A. MCP: mcp(read).

#### `job logs <job-id> --machine <m>`
- Help: `Show a job's log. Follow it live with -f.`
- Flags: `-f/--follow`, `--since-line <n>` (line-based offsets: the CLI can leave and come
  back without losing or repeating a line).
- Exit: RAW STREAM. Two §1 deviations: Ctrl-C during a follow exits **130** (detach, not
  cancel), and a follow that reaches a failed job's completion propagates the **job's own
  exit code** (`job.ts:248`).
- Gate: A. MCP: mcp(read; excludeOptions: follow).

#### `job cancel <job-id> --machine <m>`
- Help: `Stop a running job.`
- Flags: `-y`. Idempotency: cancelling a finished job is a no-op 0 (`job.ts:260`, and it
  does not even prompt: never ask an operator to confirm something that will not happen).
- Gate: A. MCP: mcp(write, destructive, idempotent).

#### `job gc --machine <m>`
- Help: `Remove finished jobs and their logs. Dry-run unless --apply.`
- Flags: `--older-than <duration>` (default 168h, matching renet), `--apply`, `-y`. Running
  jobs are never collected.
- **RULED (§9 Q6)**: today `job gc` destroys immediately with `-y` to skip the prompt, while
  §5.4's `repo gc` is **dry-run unless `--apply`**. Both verbs mean "reclaim unreferenced
  things", so principle 2 says they must agree, and the safer default wins: `job gc` adopts
  dry-run + `--apply`.
- Gate: A. MCP: mcp(write, destructive).

---

## 6. Mapping table: CURRENT tree → TARGET (for mechanical P4 execution)

**THIS TABLE IS THE CONTRACT (§0).** Every command in the live tree carries a row here, and
every row resolves to a real command. That pair is what P4 is held to, and it is
mechanically checkable against `packages/cli/scripts/command-tree.json`. The leaf counts in
the sub-headings below are descriptive and were correct when written; do not gate on them.

The current tree was enumerated from code (`packages/cli/src/commands/**`, including the
`commandFactory.ts` CRUD for machine/storage and the hidden `run` in `shortcuts.ts`).
Dispositions: `kept` (same path, contract per §5), `renamed`, `moved`, `merged-into`,
`replaced-by`, `deleted`. Every row's target contract is in §5; flag-level deltas are
stated there.

**[AMENDED 2026-07-13] Two disposition classes were added when the tree moved under this
document:**

- **EARLY-BUILT** — this spec calls it "new with no current ancestor", but an operator
  commit has since built it. **P4 recontracts it; it does not create it.** Seven commands:
  `cluster join`, `cluster evict`, `cluster rehearse`, `config edit`,
  `repo replicate` (+ `status`, `remove`).
- **NEW-SINCE-SPEC** — it exists in the live tree and this document has never seen it.
  Twelve commands, in §6.11 and §6.12. **All twelve are now dispositioned** by the 2026-07-13
  rulings (§9); none is left open.

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

New with no current ancestor: `repo logs`, `repo exec`, `repo admin archive
list|restore|purge` (from config, below).
**EARLY-BUILT** (recontract, do not create): `repo replicate` (+`status`, `remove`).
**NEW-SINCE-SPEC and unmapped here**: `repo canary` ×4, `repo replicate refresh` (§6.12).

### 6.6 `run`, `term` (2)

| Current | Disposition | Target |
|---|---|---|
| `run` (hidden) | kept | unchanged; absolute agent block |
| `term connect` | kept (recontract) | `term connect <target>` (`-m`/`-r`/`-t` → positional; container flags die — U4) |

### 6.7 `subscription` (8 leaves + 1 actionable parent)

**[CORRECTED 2026-07-13]** This header said "(7)" while the table below it listed 8 rows.
That one-character slip is the entire origin of the "162 current leaves" figure §0 retires.
`subscription refresh` is additionally an ACTIONABLE PARENT (it carries an `.action()` AND
subcommands), which no count in this document ever included.

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

New with no current ancestor: `config reconcile`.
**EARLY-BUILT** (recontract, do not create): `config edit`.
**NEW-SINCE-SPEC and unmapped here**: `config rotate-cek` (§6.12).

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

New with no current ancestor: `cluster snapshot create|list`.
**EARLY-BUILT** (this spec called them new; they exist, so recontract only):
`cluster join`, `cluster evict`, `cluster rehearse`.

### 6.11 `job` (5) — NEW-SINCE-SPEC (2026-07-13)

| Current | Disposition | Target |
|---|---|---|
| `job list` | NEW-SINCE-SPEC | `job list --machine <m>` (§5.13) |
| `job status` | NEW-SINCE-SPEC | `job status <job-id> --machine <m>` (positional id, Q9) |
| `job logs` | NEW-SINCE-SPEC | `job logs <job-id> --machine <m>` (raw stream; exit 130 on detach) |
| `job cancel` | NEW-SINCE-SPEC | `job cancel <job-id> --machine <m>` |
| `job gc` | NEW-SINCE-SPEC | `job gc --machine <m> [--apply]` (aligned to `repo gc`, Q6) |

The noun SURVIVES (06 §9), and its producer is now ruled: **executor-born + the global
`--background`/`-b`** (R-P4-2v2, §5.13). Every `job` leaf keeps `-m` (a job id has no config
record).

### 6.12 The rest of the NEW-SINCE-SPEC surface (2026-07-13, ALL RULED)

Seven more commands and one global flag exist that this document had never mapped. All are
dispositioned by the §9 rulings.

| Current | Disposition | Target |
|---|---|---|
| `repo replicate` (actionable parent) | EARLY-BUILT; **bug #37 carry-fix (w0-B, 2026-07-13)** | `repo replicate <ref> --replicas <n>` (§5.4). INTERIM: its bare-form option `--name <repo>` was renamed to `--repo <repo>` because, as an actionable parent, `--name` collided with its subcommands' own `--name <set>` and Commander bound it to the parent (bug #37 — `replicate refresh/remove/status --name` never worked). The parent option dies entirely at w2b when §2.2 makes the primary name a positional `<ref>`; the rename is that removal, early, for the colliding flag only |
| `repo replicate status` | EARLY-BUILT | `repo replicate status <ref>` |
| `repo replicate remove` | EARLY-BUILT | `repo replicate remove <ref>` |
| `repo replicate refresh` | **RESOLVED (Q2): KEEP** (w0-B, 2026-07-13) | Implementation read: `refreshReplicaSet` (`services/cluster/repo-replicate-ops.ts:204-255`) does a rolling **force re-fork** — a fresh datastore snapshot, then per replica it discards + re-forks + re-attaches the fork datastore under the unchanged PV path (`:199-242`). That is a genuinely distinct verb, not a reconcile, so it is KEPT. w2b recontracts it as `repo replicate refresh <ref>` and its help must say "re-fork replicas from a fresh snapshot now", not "refresh" |
| `repo canary` (actionable parent) | **RULED (Q1): KEEP under `repo`**; **bug #37 carry-fix (w0-B, 2026-07-13)** | `repo canary create <ref> --tag <t> --weight <n>`. INTERIM: as an actionable parent it collided with its subcommands on TWO flags, so its bare-form options were renamed `--name <repo>` → `--repo <repo>` and `--weight <percent>` → `--initial-weight <percent>` (the latter collided with `canary weight`'s required `--weight`, which the `--name` fix uncovered). Both revert to their natural names at w2b when `canary create` becomes a real subcommand (§2.2) and the collision dies |
| `repo canary status` | **RULED (Q1)** | `repo canary status <ref>` |
| `repo canary weight` | **RULED (Q1)** | `repo canary weight <ref> --weight <n>` |
| `repo canary remove` | **RULED (Q1)** | `repo canary remove <ref>` |
| `config rotate-cek` | **RULED (Q3): stays TOP-LEVEL** | `config rotate-cek`. NOT folded under `config field rotate --cek`: §5.1's `config field rotate <pointer>` rotates a sensitive field VALUE, while the CEK is the key the whole config is encrypted under. It is org-wide and destructive, and burying it under the field verb would make it look routine. It also already has a portal surface (`RotateCekWizard.tsx`), so the two must agree. P4 moves its registration from `commands/config-remote.ts:609` into `config.ts` |
| `serve` | **RULED (Q4): stays top-level** | `rdc serve --mode daemon\|container` (§5.12) |
| `--proxy <url>` (global) | **RULED (Q4): contract-frozen** | It is what makes the generated contract load-bearing (§5.12) |

`repo canary` was the largest unmapped block in the tree: four invokable commands
implementing a weighted traffic split on shared data (`packages/cli/src/commands/repo-canary.ts`,
backed by `repo-release.ts`'s rung-0 + canary ladder and renet's `pkg/router/canary.go`).
**It stays under `repo`**: it is the same subject (a repo's traffic), and a new top-level
noun for four leaves is not earned. P4 recontracts it in place with a positional ref and the
full five-system classification (§8.3). Note for the as-built pass: it must be ADDED to the
06 §1 tree, which never listed it.

### 6.13 Tally, and what "complete" means

**[REPLACED 2026-07-13]** The old tally read: *"162 current leaves, every one carries a
disposition above; 25 new leaves have no ancestor."* The first number was wrong (§0), and
the sentence has been overtaken by 19 commands that landed after it was written.

The completeness claim, restated so it survives the next merge:

> Every command in `command-tree.json` (plus the three actionable parents and the hidden
> `run`, which the JSON's shape hides) carries a disposition row in §6. Every disposition
> row in §6 resolves to a command that exists, or is explicitly marked NEW (P4 creates it).

That is the gate. Today it holds: **183 invokable commands, all dispositioned**, of which
**12 are NEW-SINCE-SPEC** (5 job, 4 canary, `repo replicate refresh`, `config rotate-cek`,
`serve`) and **7 are EARLY-BUILT**. P4 creates 12 leaves from nothing (`repo logs`,
`repo exec`, `config reconcile`, `datastore list/attach/detach/delete`,
`datastore snapshot create/list`, `cluster snapshot create/list`, `backup restore`), plus
the `backup` noun's 10 leaves and `machine infra`'s 7, which are relocations rather than
inventions. Nothing in `packages/cli/src/commands/**` is unaccounted for as a COMMAND; the
residual findings below are contract-level, not missing rows.

---

## 7. Gate findings U1-U8 — dispositions after the P0 gate review

Original findings kept for the record; each now carries its ruling from
`docs/design/spec/00-gate-review.md`. Nothing in THIS SECTION remains open for P4.

**[AMENDED 2026-07-13]** That sentence used to read "nothing here remains open for P4" and
was true of the gate findings. It is no longer true of the document: the tree moved, the
proxy/contract/plane system landed, and ten new choices are open. They are in **§9**, which
did not exist when this line was written. U5 (leaf count) and U6 (`--detach` on `repo fork`)
are both REOPENED there.

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
- **U6 — `repo fork --to-cluster/--provider` deleted, `--detach` kept.** ⚠ **REOPENED AND
  SUPERSEDED 2026-07-13 by ruling R-P4-2v2 (§9 Q5).** The deletions stand. The `--detach`
  half does NOT: the flag is renamed **`--no-wait`** on `repo up`/`repo fork` (which is what
  it always meant), and the job producer is the GLOBAL `--background`/`-b` — the word
  "detach" leaves the flag vocabulary entirely (only the `datastore detach` verb keeps it).
  Recorded as a deliberate reversal of a gate disposition, with its reason: when U6 was
  written the `job` noun did not exist, so there was no collision to see.
- **U7 — MCP surface promotions/demotions** (`repo cat` gains a tool; `repo promote`
  loses one; `machine deprovision` loses `appendArgs: ['--force']`; `repo sync *`
  explicit exclude; `credits` annotated). Stand as the P4 MCP-gate seed classification,
  revisitable there. The gate additionally recorded the `repo replicate` gate-B (not D)
  tension for that same P4 record.
- **U8 — `backup schedule` per-machine systemd model.** CONFIRMED by ruling R5: spec 01
  keeps all 9 `backup_*`/`checkpoint_*` bridge functions unchanged; §5.6's model is
  today's proven shape.

## 8. P4 execution checklist (AMENDED 2026-07-13: the obligations are no longer "no new")

The original obligations still hold: cli-docs, skill reference, `validate-cli-examples`,
`command-metadata` re-annotation from §4.7/§5, CLI i18n (en + 12 locales), renet-contract
types + e2e-coverage, and the MCP tree-walk gate with this file's §5 MCP fields as the
starter classification. The §1 exit-code names land in `packages/cli/src/types/index.ts`
(`EXIT_CODES` 11-15) and `types/errors.ts` (`ERROR_CODES`) in the same phase, **plus the
ruling on 130** (§1).

**This section said "no new obligations". That is now false.** Five artifacts and their
gates were built after it was written, and they are the heaviest part of the reshape.

### 8.1 The five new regeneration obligations

1. **`packages/cli/scripts/command-tree.json`** (committed). Consumed by
   `scripts/check-cli-docs.ts`, the www doc generators, and two ESLint rules. Nothing diffs
   it against the live tree directly, but `validate:cli-docs` regenerates `cli-application.md`
   from it in memory and diffs against disk for all 13 languages, so a stale tree surfaces
   there.
   Regen: `npm run export:command-tree -w @rediacc/cli`.

2. **The generated CLI contract** (`packages/shared/src/cli-contract/data/`):
   `contract.generated.ts`, `contract.json`, and **`i18n/<lang>.json` for all 13 locales**.
   Gated by **`check:ci-cli-contract`**, which is a **regenerate-and-diff, not a hash**
   (`.ci/scripts/quality/check-cli-contract.sh`): ANY rename, move, added flag or changed
   help string turns it red. **This is the heaviest new obligation.** Every CLI i18n change
   re-emits 13 files, and the contract drives the web console, the `--proxy` thin client and
   the executor, so a stale contract means those three disagree with the CLI they are
   driving.
   Regen: `npm run generate:cli-contract -w @rediacc/cli`.

3. **`packages/cli/src/config/command-planes.ts`.** Every new, renamed or moved leaf needs a
   plane (§4.9). Gated TWICE: `check:ci-command-planes` (import-graph cross-check) and
   `plane-coverage.test.ts`, which fails both on a command that resolves no plane **and on
   stale map entries that no longer match a real command**. Every rename in the reshape
   strands an entry and fails the gate until fixed. `plane-coverage.test.ts` also carries
   **hand-maintained snapshots** P4 must update: the command count, the plane distribution,
   the exact nine-entry interactive list, and the proxyable count. They are deliberate
   tripwires, not incidental assertions. **As of task zero (w0-B) these read 183 /
   `{config: 68, machine: 95, other: 20}` / proxyable 91** — the +1 over the pre-P4 baseline
   (182 / machine 94 / proxyable 90) is the hidden `_refprobe run` acceptance vehicle (§8.1a),
   and the shared `proxyCapableCommands().length` snapshot is 85 (was 84) for the same reason.
   w1 removes the probe and reverts all four numbers.

4. **`DOMAIN_MODULES` in `packages/cli/scripts/check-command-planes.ts:48`.**
   ⚠ **A NEW TOP-LEVEL NOUN WITH NO ENTRY HARD-FAILS THE GATE** ("Domain X has no entry in
   DOMAIN_MODULES"). **The reshape introduces `backup`, so it must register
   `commands/backup.ts` there.** The gate's Rule 1 / Rule 2 verdicts can also flip when
   `repo admin` and the moved `config` subtrees change the import graph; expect to revisit
   `OVERRIDES`, and read §4.9's warning before adding one.

5. **`PROXY_EXCLUSIONS` in `packages/cli/scripts/generate-cli-contract.ts:61.`** The
   machine-plane commands a remote executor must never run for the caller, keyed by command
   path (today: `repo sync upload|download|status`, `config cert-cache pull`,
   `cluster kubeconfig`, `config machine scan-keys`). **Every rename silently breaks a key**
   (the key just stops matching, and the command becomes proxyable), and every NEW
   machine-plane leaf needs a proxy verdict plus a user-facing refusal reason: the CLI prints
   it verbatim when `--proxy` refuses.

Two more that are not new but are easy to miss:

6. **`command-help-coverage.test.ts`** (`packages/cli/src/config/__tests__/`): every registry
   command needs a non-empty English description, plus an `I18N_KEY_OVERRIDES` entry where
   the key does not follow the default convention.
7. **`COMMAND_REGISTRY`** (`packages/cli/src/config/command-registry.ts`): domain grouping and
   experimental gating. It feeds the contract generator (`group`) and the MCP coverage gate.
   **It is missing 4 of the 16 live domains today** (`job`, `cluster`, `credits`, `serve`),
   which is why they are MCP-unchecked (§4.10). Any new noun P4 adds needs an entry, or its
   `group` is `null` and the MCP gate has nothing to iterate.

### 8.1a The task-zero acceptance vehicle: `_refprobe` (w0-B, temporary)

Task zero built the ref concept (§2.0) but nothing in the real tree may carry a positional
until w1 renames the nouns. To prove the machinery end-to-end **before** the first rename, w0-B
added one hidden throwaway leaf, `rdc _refprobe run <ref>` (`packages/cli/src/commands/refprobe.ts`):

- `<ref>` is kind `repo-ref`, so it exercises positional serialisation, the generator's
  `repoPositional` resolution, `detachable` derivation, the `--proxy` wire round-trip through
  the loopback fake executor, and the console rendering it as a repo picker. It is the first
  and only positional-carrying leaf that also calls `getExecutor().execute` — the seam the
  `job` leaves deliberately bypass (they drive `job-remote` directly), which is why a `job`
  leaf could not serve as the round-trip vehicle.
- It is hidden (Commander `{ hidden: true }` + the `_` prefix), so it stays out of `--help`
  and the skill reference (`generate-skill-reference.ts` filters `_hidden`). It is NOT in
  `COMMAND_REGISTRY`, so its `group` is `null` and `experimental` is `false`, like `cluster`
  and `credits`. Its plane is declared in `command-planes.ts` and `check-command-planes.ts`
  (`DOMAIN_MODULES._refprobe`), both of which w1 reverts.
- It is the ONLY new positional the walker actually serialises besides the two real `job`
  conversions (`job status <job-id>` / `job logs <job-id>`, kept `-m`, kind `job-id`, zero
  plane-count churn — the first REAL positional leaves).

**w1's removal list** (do all together, so no snapshot is left stale): delete
`commands/refprobe.ts` and its `cli.ts` registration; drop `_refprobe` from `command-planes.ts`
and `check-command-planes.ts`; regenerate the contract; revert the four hand-maintained
snapshots (`plane-coverage.test.ts` 183→182, machine 95→94, proxyable 91→90; `contract.test.ts`
`proxyCapableCommands().length` 85→84). The generic contract-invariant tests
(`contract.test.ts`, `command-dispatch.test.ts` positionals block, `contract-form.test.ts`'s
synthetic repo-ref entry) keep the machinery under test after the probe is gone.

### 8.2 Regeneration order

```bash
npm run build:packages                            # shared + provisioning: the contract's consumers
npm run generate:cli-contract -w @rediacc/cli     # contract.generated.ts + contract.json + i18n/*.json
npm run export:command-tree -w @rediacc/cli       # packages/cli/scripts/command-tree.json
npm run generate:cli-docs -w @rediacc/www         # re-exports the tree, regenerates cli-application.md
npm run generate:skill-reference -w @rediacc/cli  # .claude/skills/rdc reference
# then HAND-UPDATE the snapshots in:
#   packages/cli/src/config/__tests__/plane-coverage.test.ts  (counts + interactive list + proxyable count)
npm run check:ci-command-planes
npm run check:ci-cli-contract
npm run check:cli-docs
npm run check:cli-examples
npm run check:test-cli
npm run check:ci-console-coverage                 # account submodule: mounts a form for EVERY contract entry
```

`check:ci-console-coverage` runs in the account submodule
(`private/account/web/src/components/console/__tests__/contract-coverage.test.tsx`) and mounts
`CommandForm` for **every** entry in `CLI_CONTRACT`, failing if any cannot render. Its
`EXCLUSIONS` list is empty and may only ever contain `interactive` commands. It consumes
`@rediacc/shared/cli-contract`, so it needs a **rebuilt shared package** after the contract
regen, and it is the gate that a positional (§2.0) would pass while rendering an unusable
form.

### 8.3 The per-leaf checklist (every leaf P4 renames, moves, adds or deletes)

**FIVE classification systems, all keyed by the same space-joined path string.** Ranked by
how a mistake fails, worst first, because that is the order in which they will hurt you:

1. ⚠ **POLICY GLOBS** (§4.11) — `commands.allow` / `commands.deny` in every authored policy
   document, plus the `PolicyRuleEditor` presets and the `evaluate.test.ts` fixtures. **A
   stale `deny` glob FAILS OPEN**: it silently stops denying the command it was written to
   forbid. No gate exists today; P4 builds one. This is the only system whose staleness
   *grants* a permission.
2. ⚠ **`COMMAND_METADATA` guardrails** (`grandGuard` / `forkBlocked` / `agentBlocked`) — move
   the entry to the new pathKey. **No stale-entry gate**: a missed rename silently stops
   enforcing `grandGuard` (§4.10).
3. **`COMMAND_PLANES`** — delete the old pathKey if it had an explicit entry (else the
   stale-entry test fails), and **explicitly re-declare the plane at the new path if the new
   domain's default is wrong for it**. Loud on the half it catches; **silent on a move into a
   machine-default noun**, which flips `proxyCapable` to `true` (§4.9). Ask per leaf: *would
   running this at a remote executor produce the CALLER's answer?*
4. **`COMMAND_METADATA` MCP** (`mcp` XOR `mcpExcludeReason`) — exact-keyed; stale entries are
   caught loudly by `mcp-coverage.test.ts`.
5. **The ref binding** (§2.0) — `repoPositional` / `machinePositional`. Silent: if a leaf's
   ref carries no binding, the console renders a text box instead of a resource picker and
   the resource page's **action bar loses the button** for that command.

Plus the four registration/regeneration duties:

6. **`COMMAND_REGISTRY`** — any new top-level domain needs an entry (`serve` needs one now).
7. **`DOMAIN_MODULES`** — any new top-level domain needs an entry, or the plane gate hard-fails.
8. **`PROXY_EXCLUSIONS`** — re-key it (every rename silently breaks a key and makes the
   command proxyable), and give every new machine-plane leaf a proxy verdict plus a
   user-facing refusal reason. **`DETACH_EXCLUSIONS` (R-P4-2v2) is its sibling with the same
   failure mode** — key it by the NEW tree's paths from birth; a stale key silently makes a
   command detachable.
9. **i18n** (`packages/cli/src/i18n/locales/*/cli.json`) — a moved command whose key moves in
   `en/cli.json` needs all 13 locales moved in lockstep, or `descriptionKey` silently goes
   `null` (§4.9). Keep English descriptions unique per leaf.

### 8.4 Housekeeping found in passing

**`EXCLUDED_TOP_LEVEL` in `command-tree-lib.ts:200` is stale.** It lists
`login, logout, run, trace, cancel, retry`, but only `run` still exists; the rest are residue
from the retired middleware era. Harmless today, but it would silently erase any future
top-level command with one of those names. Prune it in P4.

---

## 9. OPERATOR RULINGS for P4 (DECIDED 2026-07-13)

All eleven questions are answered. Nothing in this document is open. The rulings are
recorded with their reasons, because two of them (Q0, Q5) cost real work and one (Q5)
deliberately reverses an earlier gate disposition.

| # | Question | RULING |
|---|---|---|
| **Q0** | **Positionals (§2.0): build the contract serialisation rule, or abandon positional names?** | ★ **BUILD IT (R-P4-1). P4 task zero, before any rename.** And "it" is bigger than the walker: the deliverable is a **ref concept** — positional descriptors WITH a `kind`, plus `repoPositional`/`machinePositional` bindings, because the console's pickers and its computed action bars currently bind to `--name`/`--machine`, the very flags §2.2/§2.3 delete. Serialisation alone would ship a CLI that works and a GUI that quietly empties. Full deliverable + acceptance test in §2.0 |
| **Q1** | **Does `repo canary` survive, and where?** | **KEEP under `repo` (R-P4-3).** Same subject (a repo's traffic); a new top-level noun for 4 leaves is not earned. Recontract in place; ADD it to the 06 §1 tree, which never listed it |
| **Q2** | **Is `repo replicate refresh` redundant?** | **RESOLVED: KEEP** (w0-B, 2026-07-13). The code was read: `refreshReplicaSet` (`services/cluster/repo-replicate-ops.ts:204-255`) force re-forks — fresh snapshot, then per replica discard + re-fork + re-attach — so it is not a reconcile and not a second spelling of create. w2b recontracts it as `repo replicate refresh <ref>` with help that says "re-fork replicas from a fresh snapshot now" |
| **Q3** | **`config rotate-cek`: top-level, or under `config field rotate`?** | **TOP-LEVEL.** The CEK is the key the whole config is encrypted under, not a field value; it is org-wide and destructive, and it already has a portal wizard (`RotateCekWizard.tsx`) that must agree with it. Move its registration into `config.ts` |
| **Q4** | **`rdc serve` stays top-level? Is `--proxy` contract-frozen?** | **Yes to both.** They are the two ends of one wire. `serve` gets Gate E + an MCP exclusion + a `COMMAND_REGISTRY` entry (it has none today, which is why the MCP gate never saw it) |
| **Q5** | **The `--detach` triple meaning** (06 §7.8) | ★ **RENAME the health-check flag to `--no-wait`** on `repo up`/`repo fork`, and the job producer is the global `--background`/`-b` — after P4 the word "detach" exists only as the `datastore detach` verb (R-P4-2v2). The parallel session's finding sealed the name question: Commander resolves a root-level and a subcommand flag of the same name BY POSITION, so reusing `--detach` for jobs would make `rdc --detach repo up` and `rdc repo up --detach` silently mean different things. ⚠ **This REOPENS AND SUPERSEDES U6** (§7). Deliberate: when U6 was written the `job` noun did not exist |
| **Q6** | **`job gc` vs `repo gc` flag contract** | **Align `job gc` to dry-run + `--apply`.** Same verb, same meaning (principle 2); the safer default wins |
| **Q7** | **How is a job BORN?** | ★ **EXECUTOR-BORN, plus a global `--background`/`-b` (R-P4-2v2, twice-ruled and MERGED).** The dispatch layer sets `detached` **itself** for detachable commands and keeps following (the container tier sleeps after 2-5 min idle; client disconnect = detach, not cancel). Direct CLI stays synchronous; `--background` is FIRE-AND-FORGET (job id + resume hint, exit 0) and needs a no-follow mode that does not exist yet. `detachable` becomes a contract annotation derived beside `proxyCapable` (`DETACH_EXCLUSIONS`, keyed by NEW paths from birth). Two silent-corruption bugs MUST land before anything sets `detached` (stdout discard = #32, license/identity bypass = #33): §5.13. `rdc job start -- <cmd>` REJECTED (re-creates the `run` escape hatch) |
| **Q8** | **Exit code 130** (job detach) | **ADMITTED** to the §1 table. 130 is the SIGINT convention; a script must be able to tell "you detached" from "it failed" |
| **Q9** | **Does `job` take a positional id?** | **Positional id + explicit `-m`.** A job id has no config record, so its machine cannot be derived (the `backup` precedent, §5.6) |
| **Q10** | **Is the leaf count still a contract?** | **No.** §0 retires it. The §6 disposition table is the contract, gated mechanically ("every live command carries a row; every row resolves to a real command") |

### 9.1 What these rulings ADD to P4's scope (be honest about the cost)

Three of them are not free, and a P4 plan that budgets only "rename commands" will be wrong:

1. **Task zero (Q0)** — the ref concept across 5 modules in 2 repos, with a green
   `check:ci-console-coverage` as its acceptance test. Nothing else in P4 may start first.
2. **The detached-jobs completion (Q5+Q7, R-P4-2v2)** — this is a WORKSTREAM, not a flag.
   The parallel session's handoff (`reports/handoff-detached-jobs.md`, verified) supplies the
   design and an 8-step ordering whose first five steps are runtime no-ops: the output
   collector + byte-exact stdout reconstruction (fixes #32 AND live bug #31, the broken
   `--proxy cluster fork`), the license-recovery/identity-refresh restructure (#33), the
   `AbortSignal` follow, the `detachable` contract annotation, THEN the global
   `--background` + no-follow mode, and finally the serve/wire/reattach half
   (`kind:'job'` emission, the `jobEvents` route, exactly-once line ordinals). Steps 1-4
   touch only executor/job files (zero overlap with task zero); steps 5-8 touch the same
   contract files as task zero and fold into it as ONE contract-shape change.
3. **The policy re-key + its new gate (§4.11)** — every authored command glob, and a gate
   that fails loudly on a `deny` glob matching nothing.

---

## 10. As-built delta — w1 (2026-07-13): the addressing machinery

w1 landed the **pure machinery** of §1/§2.1/§2.3/§3 as unit-tested services and utils, with
**no command-tree or contract changes**. `check:ci-cli-contract`, `check:ci-command-planes`,
and the console coverage gate are therefore untouched; tsc is 0/0 across `shared` and `cli`;
the cli vitest suite is green at 1731 (1665 baseline + 66 new). eslint / biome / knip clean.

Implemented (file → what):

- **§1 exit-code table is live.** `packages/cli/src/types/index.ts` — `EXIT_CODES` gains
  `AMBIGUOUS` 11, `STATE_MISMATCH` 12, `HEALTH_GATE_FAILED` 13, `INFRA_FAILED` 14, `BUSY` 15,
  and `DETACHED` 130 (0-10 unchanged, not renumbered). `packages/cli/src/types/errors.ts` —
  the matching `ERROR_CODES` names plus `errorToExitCode(code)`, the sibling of
  `httpStatusToExitCode`, so `errors[].code` mirrors the exit-code name (§1). New
  `packages/cli/src/utils/cli-exit-error.ts` — the `CliExitError` class (derives its exit
  code from its code) + `ambiguous`/`stateMismatch`/`notFound` helpers; `utils/errors.ts`
  `normalizeError` passes it through (code + exit code + details + next). Tests:
  `utils/__tests__/cli-exit-error.test.ts` (9).
- **§2.1 grammar parser.** `packages/cli/src/services/addressing/ref-parser.ts` — `parseRef`
  (`repo[:tag][@place]` → struct), `validateLabel` (RFC-1123, offending-char-named exit-2
  texts), `validateTag` (refuses reserved `base`), `isValidLabel`, `RESERVED_TAG`,
  `LABEL_MAX_LENGTH`. Tests: `__tests__/ref-parser.test.ts` (26).
- **§2.3 derived-machine resolution.** `packages/cli/src/services/addressing/resolve-machine.ts`
  — the six steps exactly (parse → family/tag lookup with candidates → placement tagged
  union → `@place` redundant-accept vs §3.2 conflict → injected `verifyMount` seam →
  execute), read-only-skip as a parameter. Pure over a `PlacementView`; `placementViewFromConfig`
  bridges the config service. Tests: `__tests__/resolve-machine.test.ts` (18).
- **§3 `@place` rules.** `packages/cli/src/services/addressing/place-rules.ts` — the §3.1
  acceptance table as data (`placeAcceptance`, `REPO_VERBS_ACCEPTING_PLACE`,
  `assertPlaceAccepted`), and the §3.2 conflict + §3.3 term-connect collision error builders
  reproducing the canonical texts verbatim. Tests: `__tests__/place-rules.test.ts` (13).

**Scope boundary — §2.2's first real positional conversion and `_refprobe` retirement move to
w2b (ruling, not a gap).** w1's brief allowed converting `repo cat` to a positional as the
probe's replacement "if convenient." Two findings made it not convenient in w1, and the lead
ruled it reassigned to w2b:

1. **Placement is null in every live config.** The `repo create` placement porcelain is w2b's
   (`commands/repo-create-delete.ts` marks it "Final placement porcelain is P4"), so a
   spec-clean derived `repo cat` (§2.3, `-m` removed) would exit 12 (no placement) on *every*
   real repo until w2b lands the porcelain or the operator runs `config reconcile` — a live
   regression on the running campaign's own config tree.
2. **Retiring `_refprobe` retargets task zero's acceptance battery.** Deleting it breaks three
   `serve/__tests__/loopback.test.ts` round-trip tests, four assertions in
   `shared/cli-contract/__tests__/contract.test.ts`, and two account-submodule tests
   (`web/src/lib/__tests__/contract-{context,form}.test.ts`), all keyed by `_refprobe run`.

w2b owns both the repo-family recontract and the placement porcelain that `repo cat`'s
derivation needs, so it converts `repo cat` (or the safest repo leaf) to `<ref>`, deletes
`commands/refprobe.ts` + its cli.ts registration + its eslint/i18n exemptions, and reverts the
four probe snapshot bumps (plane-coverage 183→182, machine 95→94, proxyable 91→90; shared
`proxyCapableCommands().length` 85→84) — retiring the probe alongside a leaf whose end-to-end
story is real. Until then the probe stays hidden and harmless.

---

## 11. As-built delta — w2a (2026-07-13): the config exodus + backup noun

w2a landed the whole config exodus and the `backup` noun. tsc is **0/0** across `shared` and
`cli`; cli vitest **1731 passed** (128 files); shared vitest **525 passed**;
`check:ci-cli-contract` **up-to-date**; `check:ci-command-planes` **green** (18 domains, 163
commands: 94 machine / 48 config / 21 other); `check:ci-console-coverage` **190 passed** (every
one of the 163 contract entries renders a usable form, so every positional/ref binding
resolves). The live tree went **183 → 163 invokable commands** (the exodus consolidated ~20
config leaves back onto their resource nouns).

**⚠ The `_refprobe` revert targets in §10 are now stale.** The reshape moved the baseline the
probe rides on. When w2b removes `_refprobe` the new reverts are **plane-coverage 163→162,
machine 94→93, `machineNonInteractive` 90→89; shared `proxyCapableCommands().length` 83→82**
(the plane-coverage.test.ts / contract.test.ts comments already carry these).

### §6 disposition rows flipped to DONE

- **§6.1 machine (17):** `machine create/delete`→`add/remove` (positional `<name>`);
  `machine query`→`machine status [name]` with the section commands folded in as flags
  (`--containers --health-check`, `--services --stability-check`, `--repositories --search`,
  plus new `--datastores`); `machine containers|services|repos` **deleted**; `machine backup *`
  ×5 → `backup *`.
- **§6.2 storage (6):** `storage create/delete`→`add/remove`; `storage rename` deleted;
  `storage list [name] --reveal` absorbs `config storage show`; `storage import <file>` from
  `config storage import`.
- **§6.5 repo (archive only):** new `repo admin` parent carries `admin archive {list,restore,purge}`
  from `config repository {list,restore,purge}-archived`; `config repository add/remove/list`
  **deleted** (GUID mapping internal). *(w2b adds validate/fsck/ownership/autostart/template
  under the same `admin` parent.)*
- **§6.7/§5.11 subscription:** untouched (w2b).
- **§6.8 config (57 → 26 leaves, zero resource subgroups):** the +1 over §5.1's 25 is
  `config rotate-cek` — the §6.12/Q3 NEW-SINCE-SPEC leaf §5.1 predated (count is descriptive
  per §0). machine/provider/infra/cert-cache →
  `machine …`; storage → `storage …`; repository archive → `repo admin archive`; cluster →
  `cluster …`; backup-strategy → `backup strategy …`; `config machine set-ceph` and
  `config cluster add-pool` **deleted**. `config set/clear` take positionals over the v3
  `DefaultsSchema` (team/region/machine keys retired, R2-F9); `config init [name]` /
  `config delete <name>` positional; **`config reconcile` NEW** (wired to the existing
  `reconcileState` service); **`config rotate-cek`** registration moved into `config.ts`.
- **§6.10 cluster (create/status/destroy):** `cluster create` is one-step — `--provider/--pool`
  (+ KVM topology + `--declare-only`) absorbed from `config cluster add`; a bare create
  provisions an already-declared cluster (resume). `cluster install` **folded/deleted**;
  `config cluster {add,add-pool,list,remove}` removed. fork/migrate/rehearse/scale/join/evict/
  kubeconfig/snapshot untouched (w2b + `services/cluster/*` off-limits).
- **§5.6 backup (10) NEW noun:** `strategy {set,remove,list,show}` (config-plane), `schedule`,
  `run` (←`machine backup now`), `status`, `cancel`, `list` (artifact lister), `restore` (NEW).
  Registered in `DOMAIN_MODULES`, `COMMAND_REGISTRY`, `COMMAND_PLANES` (domain `machine`,
  `backup strategy` = `config`). `-m` stays on the noun.

### Deviations (worth knowing)

1. **`backup restore` is built by composition, not new renet.** It parses the artifact ref
   (`repo[:tag]@place`, `@place` required), looks the source repo up for its GUID, registers a
   fresh live record under `--as`, `backup_pull`s the bytes to the placement machine, and
   optionally `repo up`s with the health-window/timeout flags. The `--machine` (docker) arm is
   complete; `--datastore` resolves the datastore's `state.datastores[d].attachedTo`. k8s
   up-richness rides w2b/w3.
2. **`backup list` executor for `--storage`.** §5.6 pins `--machine XOR --storage` but does not
   say which machine runs rclone for a storage listing. As-built: `--machine` is the executor;
   `--storage` uses the ref's `@place`, else the sole registered machine, else **exit 11**
   (AMBIGUOUS) asking to qualify.
3. **`config set/clear` scope.** They now write the v3 `DefaultsSchema`
   (`language`/`datastore-size`/`prune-grace-days`) via new `configService.setDefault/clearDefault/
   clearDefaults`. `team`/`region`/`machine` give the R2-F9 retired-key error. The
   `AccountSchema.team/region` **fields still exist in the shared schema** (v2→v3 migration path);
   only the CLI surface stopped exposing them. Full schema-field removal is a follow-up.
4. **`machine infra set/show` and `machine infra cert status/clear` are declared `plane: config`**
   inside the machine-default domain (§4.9 Case 2): their effect is the caller's local config /
   cert cache, so they must not become proxyable. `machine infra push` / `infra cert pull|push` /
   `scan-keys` / `setup` reach the machine and stay machine-plane. `config reconcile` is
   `plane: machine` (config's ONLY machine leaf, which keeps Rule 2 satisfied) **plus a
   `PROXY_EXCLUSIONS` entry** because its effect lands in the caller's state bucket.
5. **PROXY_EXCLUSIONS re-key:** `config cert-cache pull`→`machine infra cert pull`,
   `config machine scan-keys`→`machine scan-keys`, **+`config reconcile`**. Policy fixtures
   re-keyed: `machine query`→`machine status` (`policy/schema.ts` doc, `policy-round-trip.test.ts`,
   account `policy-rule-editor.test.tsx`).

### Declared debt (allowed-red per the wave brief; for w4)

- **`check:cli-docs` / `validate-cli-examples`: 171 stale doc snippets** across `packages/www`
  content and `CLAUDE.md` (e.g. `rdc config backup-strategy …`, `rdc config cert-cache …`,
  `rdc config infra …`, `rdc cluster install`, `rdc machine containers`). The **generated**
  `cli-application.md` (13 locales) regenerated clean and stale i18n *keys* are **0**; only
  hand-written example prose is stale.
- **`check:i18n` completeness: 49 new English keys** (`backup.list/restore.*`,
  `machine.status.ambiguous`, `storage.add.*`, `config.reconcile.*`, `cluster.create.declared`,
  …) carry English only; the 12 locales fall back to English until w4/P7 re-naturalizes. All
  **moved** keys travelled in lockstep across all 13 locales (byte-identical round-trip verified).

---

## 12. As-built delta — w2b (2026-07-13, LANDED): the repo-family recontract

w2b is the repo-family/datastore/cluster/subscription recontract. This section records what
has LANDED so far (each batch fully gated) and enumerates the remaining scope, so a
continuation (w2b resumed, w4, or the gate review) has an exact picture. Everything below is
uncommitted and green: tsc 0/0 (shared+cli), `check:ci-cli-contract` up-to-date,
`check:ci-command-planes` (162 cmds, 93 machine), `check:ci-console-coverage` 189, full cli
vitest 1738, shared contract 18.

### The reusable seam (built once, used by every converted repo verb)

`packages/cli/src/utils/repo-target.ts::resolveRepoRef(ref, {readOnly?, verifyMount?})` — the
reshape-era funnel that replaces `resolveRepoTarget` as `-m`/`--cluster` come off the repo
verbs. It parses the ref, builds a `PlacementView` from the live config, runs w1's six-step
`resolveMachine`, and returns `{name, repoKey, machineName, kubeCluster, datastore, tag,
place}`. `repoKey` (= the ref minus `@place`, `name[:tag]`) is what `getRepository` and renet's
`repository:` param consume; `kubeCluster` is the datastore's cluster backref (k8s arm).
**verifyMount (step 5) is DEFERRED for mutating verbs** — omitted means step 5 is skipped,
which is parity with today's `resolveRepoTarget` (it also never verified), NOT a regression;
wiring a real renet mount check is a tracked follow-up.

### Landed leaves

- **`repo cat <ref>`** (§10 handoff): first real positional conversion (read-only). Retired
  `_refprobe` entirely (file, cli.ts reg, command-planes, check-command-planes DOMAIN_MODULES)
  and retargeted its 9 acceptance tests onto `repo cat` (loopback ×3, shared contract ×4,
  account contract-context ×2). Reverted the four probe snapshots: plane-coverage 163→162,
  machine 94→93, machineNonInteractive 90→89, shared `proxyCapableCommands().length` 83→82.
  New shared i18n key `options.repoRef` (the positional-arg help every repo verb reuses).
- **`repo create <name>`** (§5.4 placement union = **#38 fix**): positional `<name>`,
  `--machine` XOR `--datastore`, `--size` conditional (docker requires it, a k8s datastore →
  exit 2 "sized from PVC declarations"); `--cluster`/`--name` deleted. The birth record now
  carries the declared `placement: {machine}|{datastore}` — the field every derived-machine op
  resolves through, composing with w2a's `config reconcile` (which fills MISSING placement and
  never overwrites declared). **#38**: a cluster (k8s) datastore repo lands on its DATA
  datastore mount `/mnt/rediacc-ds/<D>` with the kube arm, not the control datastore
  `replicate` excludes. New helper `namedDatastoreMount` (cluster-target.ts). Teaching errors:
  placementRequired, machineInCluster (R2-F12), sizeOnK8s, sizeRequiredDocker, datastore
  not-found (5) / not-attached (12). Test `repo-create-placement.test.ts` (8).
- **`repo status <ref>`** (read-only derived-machine) and **`repo delete <ref>`** (derives the
  machine, then `resolveDestructiveTarget` for the strict fail-closed key #495; the `--cluster`
  delete path is gone). Metadata `repoArg` name/repo → `ref` for both.
- **Serve-layer fix exposed by derived-machine:** the `/v1/command` audit sourced `machineName`
  from the request via `targetFrom`, but a derived-machine verb has no machine in the request —
  it is resolved from placement inside the action body — so the audit recorded `undefined`.
  Now the dispatch taps the executor's actual `machineName` the way it already taps
  `functionName` (`command-dispatch.ts` `DispatchOutcome.machineName` + the recordingExecutor
  tap; `server.ts` uses `observed ?? targetFrom(...)`, so machine-declared verbs (backup, job)
  are unchanged). The serve test suite (loopback, proxy-command, command-dispatch,
  container-config, proxy-audit-attribution) moved off the `repo status --name -m` example onto
  the positional+placed-config form; pure flag-mechanics tests repointed to `repo list`/`repo
  cat`, which retain flags.

### Remaining scope (NOT yet done — for the continuation)

repo up/down (batch `--all --machine` form + fold `repo mount`/`unmount` into `--no-start`/
`--unmount` + `--detach`→`--no-wait` + **#39** empty-manifests-cluster-repo-must-error), repo
list (`--datastore` filter), the ~20 satellites (fork/push/pull/migrate/promote(←takeover)/
secret/sync[+ kube-arm target + PROXY_EXCLUSIONS re-key]/diff[del `--json`]/logs NEW/exec NEW/
tunnel/commit/branch/checkout/log/merge/gc/resize/expand/trim/policy), the `repo admin` subtree
move (validate/fsck/ownership/autostart/template under the existing admin parent), canary +
replicate recontract (the **#37** carry-fix reverts `--repo`/`--initial-weight` → natural names,
plus **#41** refresh evict-and-hold), the datastore family (**#34** init→create + list/attach/
detach/snapshot/delete + unfork→detach), cluster verbs recontract + snapshot + **#44**
(rehearseCluster catch destControl), subscription flatten, term/vscode targets, singles,
**#42** (renet `runRouter` KubeconfigPattern — coordinate with w3), the **★ LUKS live replicate
probe** (gated on lead GO + a serialized live window), and the walker-truth i18n/policy-glob
per-leaf sweeps for the leaves above.

### Landed since (fan-out batch + B7 smalls)

- **`repo fork <ref>`** (bounded 2-agent fan-out): positional, derived-machine, `--detach` →
  `--no-wait`, `--tag base`/already-exists → exit 2. Its registration moved out of the inline
  block in `repo-extended.ts` into `registerRepoForkCommand` (repo-fork.ts), wired in repo.ts;
  the dead k8s `handleClusterForkSeam` + `--cluster`/`--to-cluster`/`--provider` were deleted
  (k8s forking now runs through placement + the runtime-generic `repository_fork`, the #38
  substrate), and the stale `repo-fork-cluster.test.ts` retired.
- **`repo migrate <ref>`**: positional, source derived, `--to <place>`, `--from` deleted,
  same-home no-op added. New `command-metadata` entry (was absent) with `grandGuard` + MCP.
- The generator's positional-kind table gained the repo-ref role aliases `parent-ref` /
  `fork-ref` / `commit-or-branch-ref` / `source-ref` so role-named ref positionals still bind
  the console's repo picker.
- **#22** (config-side): `removeClusterFromStore` now clears `state.clusters` as well as
  `resources.clusters` (was orphaning state after destroy and poisoning same-name recreate with
  a stale memberIds ledger). Test added.
- **SKIP_MACHINE_ACTIVATION teaching error**: the license-issuance/activation failure message
  now names `REDIACC_SKIP_MACHINE_ACTIVATION=1` as the dev/test escape.

### Declared debt added by w2b so far

- i18n: `options.repoRef` + 8 `commands.repo.create.*` keys + `commands.repo.fork.noWaitOption`
  + 3 `commands.repo.migrate.*` (optionHealthWindow/optionHealthTimeout/noOpSameHome) +
  `errors.license.skipActivationHint` carry English only (w4/P7 naturalizes). Several
  descriptions/examples rewritten in English.
- **`repo migrate` health-gate + exit 13/14 = spec §5.4 behaviors that have NEVER existed**: the
  current migrate is a two-phase rsync with no post-cutover health-gate path and no structured
  exit codes (it uses exit 1). Per the batch-4 ruling, the `--health-window`/`--health-timeout`
  flags are NOT registered (registered-but-inert flags mislead the console into rendering dead
  fields); they return when the gate is wired. Recorded as a conscious deviation; disposition =
  post-P4 hardening item alongside verifyMount (both need renet-side plumbing).
- **verifyMount (spec §2.3 step 5) DEFERRED** for mutating verbs — lead-accepted conscious
  deviation, parity with the old resolveRepoTarget; post-P4 hardening item.
- **Continuation handoff**: batches 1-5 landed; task #7 stays in_progress. The CURRENT handoff
  (per-verb recipe, real remaining inventory, the executor-reroute trap, gotchas) is
  `~/.claude/projects/-home-muhammed-monorepo-console/reports/w2b2-handoff.md`, which SUPERSEDES
  the earlier `w2b-handoff.md`.
- skill-reference / cli-docs regen batched to the end of w2b (tree exports clean).

### As-built — w2b-2 continuation (2026-07-13): batches A-D

Gate state at the w2b-2 checkpoint: tsc **0/0**; `check:ci-cli-contract` **up-to-date**
(**160** commands, config=48 / machine=91 / other=21, proxyCapable **80**, interactive 9;
options 619 → **560** as the dead flags came off); `check:ci-command-planes` **green** (17
domains); `check:ci-console-coverage` **188**; cli vitest **1737**; shared vitest (contract +
policy + audit) **62**; biome clean across `packages/cli/src` + `packages/shared/src`.

**Batch A — repo up / down.** Positional `[ref]` (single) or `--all --machine <m>` (batch);
a bare `up`/`down` with neither is exit 2. `repo mount` folds into **`repo up --no-start`**
(dispatches `repository_mount`) and `repo unmount` into **`repo down --unmount`**;
`commands/repo-volume.ts`, `CMD.REPO_MOUNT/UNMOUNT` and both metadata entries are deleted.
`--detach` → **`--no-wait`** (Commander negated option: read `options.wait === false`; the
`--no-start` twin reads `options.start === false`). Snapshot reverts: plane-coverage 162→**160**,
machine 93→**91**, machineNonInteractive 89→**87**, shared `proxyCapableCommands().length`
82→**80**.

**Batch B — the config-local resolver (a NEW seam) + branching/tunnel/diff.**
`resolveRefLocal` (`services/addressing/resolve-machine.ts`) + `resolveRepoRefLocal`
(`utils/repo-target.ts`) do §2.3 steps 1-2 ONLY (parse + family/tag; exit 2 / exit 5) with **no
placement or machine derivation, so they never exit 12**. `repo secret {get,list,set,unset}` and
`repo branch` route through it. Rationale (a correctness fix, not a style choice): those verbs
read/write the CONFIG only and never dispatch to a machine, so forcing the full derived-machine
resolution would refuse them on a repo whose datastore is merely **detached** or not yet
reconciled. `repo checkout` also fixed: its `<commit-or-branch-ref>` positional is NOT a repo
family, so the machine now derives from the **source family** (`--from`, else the commit's base),
not from the positional. Also converted: `repo commit`/`log`(`--json` deleted)/`merge`,
`repo tunnel` (refuses a k8s-placed repo: no kubernetes tunnel in v1), `repo diff`
(`--json` deleted, `--base <ref>` kept).

**Batch C — sync / trim / policy, and the B2 unblock.** `repo sync {upload,download,status}
<ref>`; `repo trim [ref]` and `repo policy {set,get} [ref]` keep `-m` as the machine-wide
selector (ref + `-m` together = exit 2, new key `commands.repo.refMachineConflict`).
★ **The kube-arm sync target is IN** (unblocks B2 / task #3): a kubernetes-placed repo now syncs
to `<named-datastore-mount>/repos/<name>/` on the machine that HOLDS the datastore, instead of the
docker per-repo GUID mount — that misroute is exactly why B1's anchor manifest never reached where
`repo up` reads it. The kube arm also skips the docker-only mount-check and per-repo SSH-key
deploy (a k8s repo has neither; the mount check would fail a healthy repo).

**Batch D — push / pull, and `takeover` → `promote`.** `repo push <ref>` / `repo pull <ref>`;
push loses `--up` (a pushed copy is a backup artifact; `backup restore --up` boots it), `--tag`
(rides the ref) and `--json` (§4.6). **`repo takeover` → `repo promote <fork-ref>`**, a full
re-key: file + symbol (`repo-promote.ts` / `registerRepoPromoteCommand`), `CMD.REPO_PROMOTE`,
the `command-metadata.ts` entry (now `mcpExcludeReason: 'Production swap; human decision.'` per
§5.4 `[P0-DECIDED]`), the dead `cli.repo.takeover` audit type, and the
`commands.repo.takeover.*` → `commands.repo.promote.*` i18n subtree **moved across all 13 locales
in lockstep**. Policy globs were grepped hard: **no authored `repo takeover` glob exists in-repo**
(the residual fail-open risk is the operator's own encrypted policy document, which is exactly
what §4.11's stale-glob gate is for). `repo gc` / `repo fsck` were reviewed and deliberately LEFT
machine-scoped: they scan a machine's object store across all repos, so they have no subject repo.

### GUARDRAIL FINDINGS (w2b-2) — §4.10's silent-staleness hazard, made real

§4.10 ranks the guardrail row as **the one to fear: it has no stale-entry gate at all**. Both of
the following are that hazard in the wild. Neither is a shipped-product bug (they live on the P4
surface), so neither takes a ledger number — but both were LIVE on `main` before this wave, and
neither would ever have been caught by a gate.

1. **`grandGuard` was silently a no-op on `repo push` and `repo pull`.** Both declared
   `repoArg: 'repo'` in `COMMAND_METADATA`, but **no `repo` field existed in the derived MCP
   schema** (the schema carried `name`). `applyGrandRepoGuard` resolves the subject as
   `args[tool.repoArgField]`, so it read `undefined` and the grand-repo guard **never fired** —
   an agent could push or pull a production grand with no unlock. Nothing failed loudly: the MCP
   coverage test checks that an entry EXISTS, not that its `repoArg` names a field the schema
   actually has. Fixed by binding `repoArg: 'ref'` to the real positional, which is what finally
   enables Gate B on the MCP path for both verbs. **The generalizable lesson: `repoArg` must name
   a field that EXISTS. A gate asserting `repoArg ∈ schema.fields` for every MCP tool would have
   caught this and is cheap — recommended for w4.**
2. **`repo trim`'s machine-wide form was agent-reachable and unguarded.** With no `repoArg` and
   `machine` exposed to MCP, an agent could omit the ref entirely and trim EVERY mounted repository
   on a machine — across grands — with nothing to guard on (the guard keys off `repoArg`). Fixed by
   `repoArg: 'ref'` + `requiredArgs: ['ref']` + excluding `machine`: the machine-wide trim is now
   CLI-only, and the per-repo form is properly guarded.

Both were found by fan-out sub-agents reading their own file's metadata against the derived schema,
which is an argument for keeping that step in the per-leaf checklist rather than trusting the gates.

**#39 (CLI half done, renet half pending).** For a kubeCluster-placed repo the CLI now sends
`runtime=kube` on `repository_up` AND `repository_mount` (param name agreed with w3). renet will
honor it as an ASSERTION: if the caller says kube but the on-datastore descriptor resolves docker,
it errors instead of the silent docker fallback B1 caught. w3 owns the renet dispatch half
(`reporuntime_dispatch.go`) and lands it after its live leg. **#39 is NOT closed end-to-end yet.**

### BUG #46 — the executor's silent control-node reroute (FOUND, RULED, FIXED in w2b-2)

**Was:** `local-executor.execute()` OVERRODE `machineName` with the cluster's CONTROL NODE
whenever `kubeCluster` was set. Defensible while `kubeCluster` could only come from an explicit
`--cluster` flag ("run this against the cluster"), but the reshape DERIVES it from placement, so
the override silently sent EVERY verb on a k8s-placed repo to the control node — including
volume-level operations (trim, diff, commit, merge, and `repo up`'s LUKS-mount step) that must run
on the machine which actually MOUNTS the datastore (`state.datastores[D].attachedTo`). Masked in
practice only because current topologies attach control-node datastores; #38's DATA-datastore
placement is exactly the topology that unmasks it.

**RULING (operator, 2026-07-13): option (a) — inject KUBECONFIG WITHOUT rerouting the machine.**
KUBECONFIG is the k8s analog of DOCKER_HOST, and DOCKER_HOST never reroutes the machine either;
the target machine must remain the derived one. A verb that genuinely must run FROM the control
node resolves that machine EXPLICITLY at its call site — explicit, not ambient.

**As-built:** the `machineName` override is deleted from `execute()`; the KUBECONFIG injection in
`runRemoteExecution` (and the job-start path) is untouched and still keys off `options.kubeCluster`.
Audited every `kubeCluster`-passing call site: the cluster-scoped ops in `services/cluster/*`
(`repo-replicate-ops.ts`, `repo-release.ts`, `repo-replicate.ts`) ALREADY resolved the control node
explicitly via `resolveExecutionTarget({ cluster })` → `machineName: control`, so they were
unaffected — confirming the override was redundant there and harmful only for the derived-machine
repo verbs. Three regression tests in `services/__tests__/local-executor.test.ts` pin the contract:
a datastore attached to a NON-control node routes there; KUBECONFIG is still injected while running
on that machine; a cluster-scoped op still reaches the control node because its call site says so.

#### ⚠ OPEN GATE QUESTION (surfaced by the #46 fix; NOT a regression, NOT a P4 blocker)

**The cluster kubeconfig is control-node-local.** `clusterKubeconfigRemotePath(c)` =
`${controlDatastoreMount(c)}/.rediacc/k3s/kubeconfig.yaml`, so it exists ONLY where
`ds-control-<cluster>` is attached. In the very topology #46 unmasks (a repo's DATA datastore
attached to a worker), the repo's manifests sit on one host and the kubeconfig on another. With the
override gone, a kubectl-needing verb therefore fails LOUDLY with a missing kubeconfig instead of
silently misrouting. That is strictly better — and every volume-level verb is now correct — but the
unmasked topology still needs an operator decision:

| Option | What it means |
|---|---|
| (i) | Stage/distribute the kubeconfig to the executing machine |
| **(ii)** | **Require cluster datastores to be attached to the control node** — makes `attachedTo == control node`, which moots the entire class |
| (iii) | Split `repository_up`'s kube arm (volume work on the attach host, kubectl work on control) |

**Lead's lean: (ii)** — it dissolves the problem rather than managing it. Recorded as a lean only;
the choice is the operator's design call, to be made at the gate review. Nothing in P4 depends on it.

### Declared debt added by w2b-2

- **`repo push`/`repo pull` batch form NOT implemented.** §4.8 lists them as batch-capable, but
  the pre-reshape batch keyed off the removed `-m` + an omitted `--name`. Rather than ship
  `--parallel`/`--concurrency`/`-y` as registered-but-inert flags (the batch-4 inert-flag ruling:
  a dead flag is a user-facing lie the console renders as a dead form field), those three are
  REMOVED from push/pull. Restoring an `--all --machine <m>` arm (mirroring `repo up`/`down`) is
  a tracked follow-up.
- **`repo promote --force` REMOVED** (same ruling). It was declared but the action body never read
  it and the generated bridge type `RepositoryPromoteParams` exposes only `parent`+`fork`, so it
  has ALWAYS been a no-op even though renet's `repository_takeover.go` honors a force. It returns
  when `force` is added to the bridge param map (renet/shared).
- **`postPushDeploy` is now dead in src** (push lost `--up`); only its unit test imports it. Its 3
  i18n keys (`push.deploying`/`.deployed`/`.deployFailed`) are orphaned. Cleanup = w4/knip.
- i18n en-only NEW keys (w4/P7 naturalizes): `commands.repo.up.{noStartOption,noWaitOption,allOption}`,
  `commands.repo.down.allOption`, `commands.repo.{batchMachineOption,batchRefConflict,
  batchNeedRefOrAll,batchAllNeedsMachine,refMachineConflict}`, `commands.repo.promote.confirm`.
  English VALUES changed on up/down/push/pull/trim/policy/promote descriptions, so the 12 locales
  are stale there (they still translate the old text; et/it/ko/pt even keep the loanword
  "takeover" inside translated promote prose). No `rdc repo takeover` COMMAND NAME survives in any
  locale.
- Stale prose still teaching the retired syntax (`--parent`, `-m`, `--name`) in
  `help.repo.keyConcepts` and the three `errors.agent.grandGuard*` strings: part of w4's existing
  171-snippet stale-example debt, not newly created here, but now more visibly wrong.
- Orphaned i18n keys from the deleted flags/verbs: `commands.repo.{mount,unmount}.*`,
  `up.detachOption`, `up.mountOption`, `push.{optionUp,optionTag,optionJson}`, `log.jsonOption`,
  `diff.jsonOption`, `diff.nameOption`, `trim.nameOption`, `policy.nameOption`,
  `secret.nameOption`, `secret.get.repoNotFound`, plus the branching `*.nameOption` set.

### As-built — w2b-3 continuation (2026-07-13): the tail of the repo-family recontract

Certified: tsc 0/0; contract up-to-date at **164 commands** (config 48 / machine 96 / other 20,
proxyCapable 85); planes green; console-coverage 193; cli vitest 1750; shared vitest 525.

#### §6 disposition rows flipped to DONE

- **canary + replicate RE-KEYED to the repo ref** (§6.12, the ruled item). `repo replicate <ref>
  --replicas N` keeps the bare create form (§5.4); `replicate status|remove|refresh <ref>`;
  `repo canary create|status|weight|remove <ref>` (the actionable parent becomes a pure group).
  `--repo`/`--cluster`/`--set`/`--name`/`--datastore` die to the ref; `--initial-weight` reverts to
  `--weight`. Set names are DERIVED (`<repo>-replicas`, `<repo>-canary`), so recorded state maps 1:1
  and there is no migration. A tagged ref is slugged, because a k8s object name and a datastore fork
  tag both reject a colon. Gate class B (grandGuard) added to both families: they had NO policy entry
  before, so an agent could replicate or canary a grand repo unguarded.
- **cluster** (§6.10): positionals on every leaf; `cluster status`'s private `--output` deleted;
  `fork --cluster` → `--to`, `rehearse --cluster` → `--on`; NEW `cluster snapshot create|list`
  (R2-F13), which reports local-backend datastores as OUTSIDE the group instant rather than omitting
  them.
- **subscription** (§6.7): flattened 8 leaves + 1 actionable parent to 4.
- **datastore** (§6.4, #34): the facade is replaced by the real 10-leaf surface over P1's named
  registry, plus a config-side registry service maintaining `resources.datastores` (the spec) and
  `state.datastores` (the routing hint derived-machine resolution reads).
- **term / vscode** (§5.8/§5.9): `<target>` = a place or a repo ref; the §3.3 collision rule lives in
  exactly one place (`resolveConnectTarget`).
- **NEW `repo logs` / `repo exec`** (§5.4, R2-F14).

#### Bugs fixed, with what each one taught

- **#41 (replicate refresh)** — fixed with NO renet change. The evict-and-hold primitive already
  existed: a replica's PV pins via `nodeAffinity` to the `rediacc.io/ds-<fork>` node label, so
  stripping that label BEFORE bouncing the ordinal pod leaves the recreated pod unschedulable
  (volume node affinity conflict). It cannot re-mount the old fork, the discard-detach wins
  deterministically, and `provisionOneReplica`'s trailing re-stamp re-opens the gate onto the new
  fork. The fix is an ordering change.
- **#44 (rehearse teardown)** — the failure path passed the destination CLUSTER name into
  `discardRehearsal`'s `destControl` (a MACHINE param), so every teardown step was aimed at a machine
  that does not exist; `tryDispatch` is best-effort, so it swallowed the errors and a FAILED rehearsal
  silently left its entire fork behind. ★ The existing test PASSED despite the bug because it asserted
  only that the teardown calls happened, never WHERE they landed. Asserting the target, not just the
  action, is the lesson.
- **#25 (vestigial agent repo)** — `kube_join`'s contract is unchanged by dropping it, because
  `K3sDistro.Install` MkdirAll's its own data-dir. FOUR sites did the identical vestigial thing (not
  the two the brief named): initial join, scale-up, fork agents, and `cluster join`. All four now
  allocate a networkID without minting a LUKS volume per agent.
- **#20 (evict)** — `evictCluster` now dispatches `kube_uninstall` at the EVICTED machine, so the
  control plane forgetting the Node is no longer half an eviction.
- **#34 (datastore)** — worse than the row implied: `datastore init` dispatched
  `datastore_init`/`datastore_ceph_init`, **which do not exist in renet**, and `fork`/`unfork` were
  leaves whose entire body was a `throw`.
- **Gate class D was unreachable for datastore.** §4.7 makes the family class D, but
  `enforceAgentBlock` only routed `cluster ` paths to the unlockable guard, so datastore verbs would
  have hit the ABSOLUTE block with no possible override. Per ruling R6 the per-name unlock matches the
  SUBJECT's name, so a datastore verb unlocks on the DATASTORE name. Both wired.
- **`term_exec` (MCP) had invalid argv and no gate caught it.** It built `term connect -m <machine>
  -c <cmd>`; when `-m` died the tool broke and the suite stayed green, because the MCP tests assert
  the argv a tool BUILDS, never that the CLI ACCEPTS it. Retired; `repo exec` replaces the repo case.

#### Declared debt added by w2b-3

1. `--reset-home` on `term connect` is DEAD CODE and always has been (the real switch is renet-side;
   the CLI has no channel to set it). §5.8 says keep the flag, so it was kept: it is a flag that lies.
2. A k8s repo's namespace is passed verbatim, so a TAGGED ref yields an ILLEGAL namespace (a colon).
   It fails silently (`kubectl config set-context … || true`). Pre-existing and shared with renet
   (`h.Namespace = name`). The fork-to-namespace mapping needs a decision, and it must match renet's.
3. `subscription refresh -m` does not refresh an activation: there is no activation-refresh action
   anywhere in the family (activation is issued inside `local-executor` during `execute`). All three
   old refresh leaves called the same repo-batch refresh under three different success strings.
   §5.11's "-m = machine activation + repos" cannot be honored literally.
4. `cluster rehearse --on` takes a destination CLUSTER, not a machine (§5.5 says machine): a rehearsal
   boots a whole k3s control plane plus agents. The spec's flag NAME is kept; the help states the truth.
5. The `term_exec` MCP capability (an arbitrary command on a bare machine) is removed, deliberately:
   that is the escape hatch `run` already is, and `run` is an absolute agent block.
6. The old cluster form of `term connect` was never repo-gated, so an agent could open a shell on a
   grand cluster repo without `REDIACC_ALLOW_GRAND_REPO`. The recontract closes it.
7. §6.9 says `vscode serve status|stop` are unchanged while §5.9 gives them `<target>`. §5.9 followed.
8. MCP tests assert the argv a tool BUILDS, never the argv the CLI ACCEPTS, so any MCP tool can rot
   silently. Worth a real gate in w4.

#### Still open in task #7

`repo admin` subtree move (+ killing `assertDockerOnly`), `repo resize`/`expand`, `repo list
--datastore`, **#42** (needs the w3 announce), and the **LUKS live probe** (GO granted, window
serialized). ★ Highest-severity carry-out: **14 executable scripts under `.ci/tutorials/` still call
`rdc term connect --machine … --repository …`, so they now fail at RUNTIME**, not merely read wrong.

### As-built — w2b-4 (2026-07-13): task #7 closed out

Certified: tsc 0/0; contract up-to-date at **164 commands** (config 51 / machine 93 / other 20,
proxyCapable **82**); planes green; console-coverage 193; cli vitest 1748; shared vitest 525; biome
clean. renet: gofmt clean, `go build ./...`, `go vet`, `go test ./cmd/renet ./pkg/router`, and
golangci-lint (0 issues) all green.

#### §6 disposition rows flipped to DONE

- **`repo admin` subtree** (§5.4): `validate`, `fsck`, `ownership`, `autostart`, `template` relocated
  under the `admin` parent alongside `archive`. The parent is created once and handed to the files
  that own the verbs' implementations, so `repo gc` (which the spec keeps on the daily surface) stays
  next to `fsck`'s shared ref-graph walk. `assertDockerOnly` is DELETED: its last caller was
  autostart, which now refuses a cluster-placed repo based on the REF's derived placement instead of
  on a `--cluster` flag the user typed, which is the honest test.
- **`repo resize` / `repo expand`** (§5.4): positional `<ref>`, staying on the daily surface.
- **`repo list --datastore`** (§5.4): a datastore is the honest filter unit, because a repo lives in a
  datastore and the machine is wherever that datastore happens to be attached today. `-m` and
  `--datastore` are mutually exclusive.
- **`repo admin template apply <ref> --template <name>`**: the old `--name` meant the TEMPLATE, on a
  tree where `--name` means the repo everywhere else.

#### Bugs fixed, with what each one taught

- **#42 (router discovery wiring, renet)** — and it was worse than the ledger said. `runRouter` built
  `router.Config` as a BARE STRUCT LITERAL listing only the flag-backed fields, so every field with no
  flag behind it silently took its zero value. That is TWO fields, not one: `KubeconfigPattern` (empty,
  so `generateAllKubeRoutesWithExec` early-returns and no kube route is ever generated, which is why
  the canary weighted split was inert on every real machine) and `K3sBinary` (empty, so even with the
  pattern set, route generation would exec `""` instead of kubectl at `pkg/router/kube.go:153`).
  **Fixing only the pattern would have left it broken one step later while looking fixed.**
  `routerConfigFromFlags` now starts from `router.DefaultConfig()` and overrides only what the flags
  cover, which kills the bug CLASS: a field added to `Config` in future reaches production without
  anyone remembering to extend the function.
  ★ The test is the point. The old unit suite was green because the ONLY path that set the field was
  the test-only `DefaultConfig()`, which production never called: **a test that cannot observe the
  production wiring cannot prove it.** The new test drives the REAL cobra flag set through the REAL
  config builder, and it was verified to FAIL against the old implementation before being kept.
- **`repo admin archive` was PROXY-CAPABLE (found in-wave, data-loss class)** — §4.9's silent-flip
  hazard, already struck, unnoticed. `archive {list,restore,purge}` are pure config bookkeeping
  (`repo-admin.ts` imports no executor and no SSH; they only read and write the config's archive map).
  They were `config repository {list,restore,purge}-archived`, config-plane by their old domain's
  default. The §5.4 relocation carried them into `repo`, they inherited repo's MACHINE default, and no
  plane entry was written, which also made them `proxyCapable`. Through the enterprise proxy that is a
  wrong-target bug: the effect is entirely on the CALLER's config file, so a proxied
  `repo admin archive purge` would have **permanently deleted the PROXY HOST's archived records**.
  Fixed with `'repo admin archive': { plane: 'config' }`.
  ★ **GATE HOLE, still open (w4).** `check-command-planes` works at DOMAIN granularity (Rule 1: a
  domain that cannot reach a machine declares no machine-plane leaf; Rule 2: one that can must declare
  at least one). `repo` plainly reaches machines, so a single config-only LEAF inheriting the machine
  default is invisible to it, and its docstring admits the coarseness. A per-leaf check (does the
  module that REGISTERS this leaf import a machine marker at all?) would have caught this on the day
  it was introduced. Every other config-only leaf (`repo secret`, `repo branch`, `backup strategy`,
  `repo replicate|canary status`) already carries its entry; archive was the one relocation that lost
  it.

#### ★ THE LUKS REPLICATE VERDICT: EMPTY-BY-CONSTRUCTION (settled statically; live confirmation pending)

The #38 acceptance question ("do kube-repo replicas SERVE the data, or come up EMPTY?") is answered by
the code, ahead of the live probe. **Replicas are empty by construction.** The chain, every link cited:

1. **Write path.** `repo up` on a kube repo (`kubeArmUp` → `KubeRuntime.ProvisionVolumes`,
   `pkg/reporuntime/kube.go`) calls `kubevolume.Provisioner.Provision`
   (`pkg/kubevolume/provisioner.go`), which per PVC creates a LUKS image at
   `<ds>/repos/<repo>/volumes/<pvc>.img`, luksFormats/luksOpens/mkfs's it, and MOUNTS the decrypted
   ext4 at `<ds>/mounts/volumes/<repo>/<pvc>`. Critically it `MkdirAll`s that mountpoint ON the
   datastore filesystem BEFORE overmounting, so the directory underneath the mount exists and stays
   EMPTY; all pod data goes into the `.img`.
2. **Replica read path.** `renderReplicaPV` (`services/cluster/repo-replicate.ts`) renders a static
   `local` PV whose path is `<forkMount>/mounts/volumes/<repo>/<pvc>`: the same relative path, rooted
   at the FORK's mount.
3. **The gap.** `provisionOneReplica` is exactly four bridge verbs (`datastore_fork`,
   `datastore_adopt`, `datastore_attach{writes:local}`, `kube_node_label`). NOTHING re-opens LUKS.
   There is zero cryptsetup/LUKS reference anywhere in `pkg/datastore/*.go` (only RBD and dm-thin), and
   the only callers of the LUKS-open primitives are the `repo up` / `repo fork` arms and the CSI node
   driver. It is even documented as deliberate, without the consequence being noticed
   (`pkg/functions/commands/kube.go`: "overlays never ProvisionVolumes; their PVs point into fork
   datastores the feature orchestrator attached").
4. **What the replica gets.** The RBD block clone faithfully carries BOTH the ciphertext `.img` AND the
   empty mountpoint directory from step 1, so the PV path resolves to a real, valid, EMPTY directory
   and kubelet bind-mounts it happily.

**`repo fork` gets this right** (it calls `ProvisionVolumes` on the fork, which takes the adopt branch
and re-opens the reflinked image with the shared grand key), which is what proves replicate's omission
is an oversight and not a design.

★ **Why the probe's methodology is load-bearing.** A broken replica does NOT crashloop. It schedules,
mounts, and comes up **healthy and Ready**, serving nothing. Every assertion weaker than a
parent-only nonce ("pod Running", "PVC Bound", "the app responds") PASSES against the broken
implementation. That is exactly the failure that made an earlier "live proof" worthless. The probe
therefore seeds a random nonce, generated at probe time, through the primary's pod, and asserts the
REPLICA returns that exact value: no default image, no empty volume and no fresh LUKS format can
produce it.

**The fix — LANDED (source-only; the live red/green probe is a separate leg).** The primitive already
existed and was exactly the right shape: `kubevolume`'s path-keyed `ResolveKeyForRepoDir` +
`OpenAndMount` / `TeardownVolume` (`pkg/kubevolume/csi.go`), built for the CSI driver. Both inputs it
needs (`.rediacc/repo.json` and `.credentials/volkeys/<grandGUID>.key`) ride the clone already.

- NEW bridge verbs `datastore_volumes_open` / `datastore_volumes_close` (`cmd/renet/datastore_volumes.go`,
  registered in `pkg/functions/commands/datastore.go`): enumerate `<forkMount>/repos/<repo>/volumes/*.img`
  and open (or close) each through those primitives.
- The CLI dispatches the open in `provisionOneReplica` between `datastore_attach` and `kube_node_label`.
  That ORDER is the safety property, not a detail: the label is the PV's nodeAffinity key and therefore
  the scheduling gate, so opening first means a pod can never be scheduled onto a volume that is not yet
  mounted.
- **TRAP 1, fork-scoped dm name.** `kubevolume.MapperName` is `rediacc-vol-<repo>-<vol>`, derived from
  the repo ALONE — and a replica keeps its parent's repo name, because the fork is of the DATASTORE, not
  the repo. `resolveReplicaNodes` round-robins replicas over every node INCLUDING the primary's, so a
  parent-derived name collides with the primary's live mapping ("device already mapped"), and two forks
  of one parent on one node collide with each other. The replica path therefore uses a FORK-SCOPED name
  (`rediacc-vol-<ds>-<tag>-<repo>-<vol>`), built on `ImageRef.MapperName` so `kubevolume`'s shared helper
  (which CSI's path-derived volume id depends on) is left alone. Bounded against the 128-byte DM_NAME_LEN
  and refused cleanly when over.
- **TRAP 2, teardown symmetry.** Anything the provision path opens, the discard path must close: a fork
  holding a live LUKS mapping and loop device is BUSY, so `detach --discard` would simply fail. The close
  now precedes the discard in BOTH teardown paths — `discardReplicaDatastores`, and the refresh loop
  before `detachWithRetry` (which the type-checker surfaced: refresh re-forks, so it needs both halves).
- Pinned by tests, not by comments: the full dispatch sequences for create / remove / refresh assert the
  open-after-attach-before-label and close-before-detach orderings, and the fork-scoped mapper name is
  asserted to differ from both the primary's and a sibling fork's. A comment cannot fail; an ordering
  assertion can.

##### ★ THE ORDER IS THE INVARIANT (state it, do not bury it in a code comment)

Two orderings in the replicate path are safety properties, not implementation detail:

1. **Open BEFORE label.** The node label is the PV's `nodeAffinity` key, which means it is the
   SCHEDULING GATE. Opening the LUKS volume before stamping the label makes it impossible for a pod to
   be scheduled onto a volume that is not yet mounted. Label-first would open a window in which kubelet
   can bind a pod to an empty directory.
2. **Close BEFORE detach.** Anything the provision path opens, the discard path must close. A fork
   holding a live LUKS mapping and its loop device is BUSY, so a discard-detach that skipped the close
   does not "mostly work" — it fails.

##### ★★ A TIGHTER TYPE FOUND A BUG NO TEST WAS LOOKING FOR

The scoped fix was "wire the close into `discardReplicaDatastores`". That is what the diagnosis called
for, and it was incomplete. Threading the repo through `provisionOneReplica` required adding `repo` to
its input type — and the TYPE-CHECKER immediately failed the OTHER caller: `refreshReplicaSet`.

That second site matters more than the first. Refresh re-forks each replica and goes straight to
`detachWithRetry`. Post-fix, that fork holds a live LUKS mapping, so refresh would have burned all five
retries against a BUSY datastore and thrown. And a refresh that re-forked WITHOUT re-opening would have
rolled the ENTIRE replica set to empty — #49 reintroducing itself through the back door, on the one
command whose entire purpose is to refresh data.

No test was looking for it. No reviewer had listed it. A looser signature (an optional field, an `any`,
a `Partial<>`) would have compiled and shipped the hole silently. **The precise type was the thing that
found it.** That is the concrete argument in this program for paying the cost of exact signatures, and
it generalizes: when a fix threads a new value through a call graph, TIGHTEN THE TYPE FIRST and let the
compiler enumerate the call sites — it knows all of them, and a human enumerating them from memory does
not.

#### Declared debt added by w2b-4

1. **The plane gate is domain-granular** and cannot see a config-only leaf inheriting a machine-plane
   domain default. It let a data-destructive proxy misclassification through. A per-leaf import-marker
   check belongs in w4.
2. **#49's fix is SOURCE-ONLY until the live probe runs.** The code, the two traps, and the ordering are
   landed and unit-pinned, but `repo replicate` has still never been executed live end-to-end. The unit
   suite cannot see the one thing that matters (whether the replica serves the parent's bytes), which is
   precisely how the bug survived 13 green tests in the first place. The verdict is not in until the
   red-then-green nonce probe reports.
3. **`repo admin autostart enable|disable` keep an `--all -m <machine>` batch form** (the §4.8 shape)
   because the retired name-less invocation meant "every repo on the machine". §5.4 states only
   `<ref>`; dropping the batch form would have deleted a real capability (`repository_autostart_*_all`).

---

## 13. As-built delta — w4 (2026-07-13, LANDED): surface closure

The last implementation wave. Its job was to close the surfaces the reshape had invalidated
(MCP, policy globs, snippets, i18n, docs) and to build the two gates §4.9 and §4.11 said were
missing. It did that, and in the process it found that **four of the repo's own validators were
themselves wrong** — three of them wrong in the direction that lets a defect through, and one
wrong in the direction that forbids correct work.

### 13.0 THE FINDING ABOVE ALL THE OTHERS: every gate that failed measured something ADJACENT to the truth

Six gates failed in this phase. Not one of them was measuring nothing — every one was measuring
something *correlated* with the property it was supposed to guarantee. **That correlation is
precisely why nobody noticed it was not the property.**

| The gate | What it measured | What it was supposed to measure |
|---|---|---|
| Command planes | the DOMAIN's reachability | whether **this leaf** can reach a machine |
| MCP coverage | the **leaves** of the tree | every **runnable** command (an actionable parent is runnable) |
| Docs scanner | `rdc` preceded by one of five DELIMITERS | `rdc` at a **word boundary** |
| Flag checker | does this flag exist **anywhere** | is it valid **on the command it is written on** |
| Command parity | unresolved **prose words**, compared across languages | **commands**, which are never translated |
| Untranslated values | whether a key is **present** | whether it is **translated** |

Each substitution is reasonable. Each is nearly always right. And each is wrong exactly where it
matters: at the leaf that moved, the parent that runs, the quoted invocation, the renamed flag, the
translated sentence, the English-filled fallback.

> ★★ **A MEASUREMENT CORRELATED WITH THE TRUTH IS THE MOST DANGEROUS KIND OF WRONG, BECAUSE IT
> AGREES WITH THE TRUTH EVERYWHERE YOU HAPPEN TO LOOK.** A gate that measured nothing would be
> caught in a day. A gate that measures *almost* the right thing survives for years, and is trusted
> the whole time.

The remedy is the one this whole section keeps arriving at from different directions: **ask the
thing that actually decides.** Not the metadata — `buildAllTools`. Not the domain — the module that
registers the leaf. Not the count — the raw output. Not the work order — the code. And when you
narrow a check to quiet its false alarms, ask what TRUE alarm the narrowing also silences, because
an exclusion written against noise fails open exactly like every other exclusion.

### ★ The seventh instance, and why it is the strongest argument this section can make

The six above were found by hunting them. **The seventh was found by accident, in this phase's own
tooling, by the agent writing this section, at the last minute of the last sweep.**

`check-cli-docs.ts` carried a comment saying — in as many words — that `docs/design/**` is excluded
from the scan, because the design record deliberately quotes dead commands while ARGUING about
them. (This very section cites `rdc auth login`, `repo takeover` and `machine query` precisely
because they are the bugs it documents.)

**The exclusion was never implemented.** The comment asserted a behavior the code did not have, and
the gate spent the whole phase flagging 34 correct citations as defects — the bug report reported
for containing the bug.

> ★★★ **IF THE PEOPLE WHO SPENT A NIGHT HUNTING THIS EXACT BUG STILL SHIPPED ONE, THEN "BE MORE
> CAREFUL" WAS NEVER THE REMEDY.** Diligence does not scale, does not persist, and does not survive
> the people who had it. Only the gate does. That is the entire argument of this section, and it
> was proved on its own author.

A COMMENT CANNOT FAIL. Nothing you write in prose — including every line of this document —
enforces anything. The exclusion is now code, and it is asserted in both directions: a dead command
inside `docs/design/**` is ignored; a dead command in any other doc is still caught.

Everything below is an instance of this.

### 13.1 The two new gates (both proven RED before being trusted)

**Per-leaf plane rule (Rule 3)** — `packages/cli/scripts/lib/plane-rules.ts`, wired into
`check-command-planes.ts`, pinned by `src/config/__tests__/plane-leaf-rule.test.ts`.

§4.9 predicted the hazard and §4.10 said no gate would ask the question for you. Bug #51 then
happened exactly as written: `repo admin archive {list,restore,purge}` moved out of `config`,
inherited `repo`'s machine default, became `proxyCapable`, and a proxied `archive purge` would
have permanently deleted the PROXY HOST's archived records instead of the caller's. The domain
gate cannot see it (the `repo` domain really does reach machines; it has dozens of other machine
leaves), and there was no explicit entry to go stale.

The rule: **a leaf claiming plane `machine` must be registered by a module that can actually
reach a machine.** Commander does not record where a leaf was registered, so the gate patches
`Command.prototype.command`/`.action` before importing the CLI and keeps the innermost stack
frame under `src/`. That frame is the module where the leaf's action handler is written, which
is exactly the module whose imports decide what the leaf can touch. 165 leaves, zero
unattributable — and **an unattributable leaf is a hard failure, not a skip**, because a leaf
the rule cannot judge is the leaf #51 hid in.

Verified by reconstructing #51 (deleting its plane entry): the gate names all three archive
leaves, names `commands/repo-admin.ts`, and exits 1. The old gate is green in that same state.

**Stale policy globs** — `packages/shared/src/policy/stale-globs.ts`, enforced at the executor
in `services/serve/policy.ts`, pinned by `policy/__tests__/stale-globs.test.ts` and
`serve/__tests__/policy-stale-deny.test.ts`.

§4.11 called the deny glob the only classification that fails OPEN. That is now demonstrated
against the real evaluator rather than asserted: a document reading
`{ allow: ['repo *'], deny: ['repo takeover'] }` refuses `repo takeover` before P4 and
**permits `repo promote` after it** — the same operation, the organization's rule silently dead.
`takeover` -> `promote` is this phase's own rename (§5.4), so that document is not hypothetical.

`readPolicyDocument` already refused a MALFORMED document, and its comment gave the reason:
*"quietly ignoring them would be the worst possible failure, since it would look like the rules
were in force."* A stale deny is that failure exactly, one level subtler — well-formed, parsing,
and not in force. It is now refused on the same grounds, naming the glob and saying a rename is
the likely cause, so the author re-keys rather than deletes.

**Deliberate asymmetry:** a stale DENY is fatal; a stale ALLOW is not. An allow glob matching
nothing already fails CLOSED (the command is refused, a user reports it). Making it fatal would
convert a safe, self-announcing condition into a total executor outage. The asymmetry is pinned
in a test, not a comment.

### 13.2 Four validators that were wrong, and the shape they share

| Validator | Was | Consequence |
|---|---|---|
| `EXCLUDED_TOP_LEVEL` (`command-tree-lib.ts`) | 5 of 6 entries named commands that do not exist (`login`, `logout`, `trace`, `cancel`, `retry`) | An entry here is invisible to the plane gate, MCP coverage, console coverage AND the docs checks. Add a top-level `cancel` tomorrow and it is silently exempt from all of them. Pruned to `run`; every remaining entry is now asserted to be a live command. |
| `scripts/check-cli-docs.ts` | hand-copied that same list, and registered every name as a VALID arg-accepting command | The gate whose job is catching stale docs would have BLESSED `rdc login --whatever`. Fixed by IMPORTING the list, so divergence is impossible rather than merely corrected. |
| `scripts/check-cli-docs.ts` (extractor + globs) | markdown-only, non-recursive, and blind to a quote before `rdc` | `.ci/tutorials/` holds ~14 EXECUTABLE scripts making 337 `rdc` calls. They were in no glob, and even once globbed the scanner read no `.sh` line and no `run_cmd "rdc …"` wrapper. Adding the glob ALONE would have been a false fix: 337 calls "covered" by a scanner reading none of them. Fixed all three; 174 real violations surfaced and were fixed. |
| `scripts/check-cli-docs.ts` (`--fix` RENAMES) | pointed `machine status` -> `machine query`, the OPPOSITE of this phase's rename | `--fix` would have rewritten CORRECT docs into broken ones. The repair tool would have been the thing introducing the staleness. Re-keyed, and the script now hard-fails if any RENAMES target is not a live command. |
| `positional-cli-detector.ts` (+ its 2 ESLint copies) | its placeholder pass ran over EVERY command path | Its own docstring always said "used for PARENT commands"; only the code said "all". Harmless until P4 gave leaves positional refs — at which point it flagged `rdc datastore create <name>`, the CORRECT form, and told the author the command "accepts zero positional arguments", which is false. It forbade the grammar the phase is built on. Scoped to parents-with-no-positional; pinned by `.ci/scripts/test/gates/test-positional-detector.sh`, proven red on the old logic. |

**The shape they share, and it is the phase's thesis one level up:** a validator's blind spot is
indistinguishable from a passing check. Three of these were green because they were not looking;
the fourth was red because it was looking at the wrong thing. Coverage of a file is not coverage
of its contents, and a rule that has only ever been observed to pass is not a control.

### 13.3 MCP

The coverage check iterated `COMMAND_REGISTRY`, which declares only TOP-LEVEL domains, so every
leaf under an undeclared domain was **unchecked, not merely ungrouped** — which is how `serve`
reached main carrying no command metadata of any kind. Replaced with a real Commander leaf-walk
(the parked `mcp-coverage-gate.patch`), which immediately surfaced **32 unclassified leaves**.
All 32 now carry `mcp` XOR `mcpExcludeReason`. The registry gained its 4 missing domains
(`cluster`, `credits`, `job`, `serve`) and a both-ways assertion that it names every top-level
command and only real ones.

**And the argv gate (§4.10's missing row).** MCP tests asserted the argv a tool BUILDS and never
that the CLI ACCEPTS it, which is why `term_exec` kept emitting `term connect -m … -r …` after
those flags were deleted while the whole suite stayed green. `mcp/__tests__/argv-acceptance.test.ts`
now populates every field of every tool's schema, builds the argv, and resolves it against the
REAL Commander tree: the path must exist, every flag must be registered, positionals must fit.
Proven red by reintroducing term_exec's disease (`unknown flag "-m"`). `repoArg` is likewise
asserted to name a field that exists in the tool's schema — one that does not makes the
grand-repo guard read `undefined` and scope nothing, on the very tool whose annotation exists
because it touches a repo.

### 13.3a An inference is not a disposition: five leaves shipped against an explicit [P0-DECIDED] ruling

The tree-walk gate surfaced 32 unclassified leaves, and they were classified by INFERRING from
the posture of the surrounding file rather than by reading §5. Fourteen of the inferences happened
to match §5. Five contradicted it, and one was needlessly stricter than it.

| Leaf | §5 says | What was shipped |
|---|---|---|
| `repo sync upload` / `download` / `status` | **MCP: exclude (all three)** — "Requires local filesystem paths on the MCP host." `[P0-DECIDED]` | all three exposed as MCP TOOLS |
| `repo admin archive list` / `restore` | **MCP: exclude (group)** — "Config archive bookkeeping." | both exposed as MCP TOOLS |
| `config prune` | **mcp(write, idempotent; excludeOptions: purge-archived)** | excluded entirely |

**The sync case is the instructive one, because the spec does not merely overrule the inference —
it refutes its premise.** The argument for exposing sync was: "client-side transfer is fine over
MCP, because MCP runs locally as the operator." §5 denies exactly that. **The MCP host is not
necessarily the caller.** The paths belong to the caller's filesystem; the MCP server need not be
sitting on it. The reasoning was plausible, confident, and wrong, and it would have handed an agent
a file-transfer primitive pointed at the wrong disk.

**The fourteen that happened to be right are not a defence.** They were reached by the same method
as the five that were wrong. Had §5 ruled differently on `machine setup` or `config audit tail`,
those would have shipped wrong too. The method did not look; the outcome was luck.

> **AN UNMAPPED LEAF IS AN OPEN QUESTION, NOT A DEFAULT.** Every silent-inheritance defect in this
> phase — #51's plane, #42's zero-valued struct fields, the guardrail that goes stale in silence,
> and this — is something taking a default that nobody chose. When the spec is silent the answer is
> "ask", not "do what the neighbours do". And when the spec is NOT silent, read it.

All six corrected to §5, verified against `buildAllTools(cli)` (the thing that actually builds what
an agent sees) rather than against the metadata that had just been written — with `repo up` and
`machine status` as negative controls, because a check that only ever confirms exclusions cannot
tell you it is working.

### 13.3a-ii A declaration that does nothing: the MCP tool factory could not see an actionable parent

The #49 probe came back green and the flip was authorized: `repo replicate`, `replicate status`,
`replicate remove` become MCP tools (§5.4). The metadata was written, `tsc` passed, and the
mcp-coverage gate was satisfied.

**And `repo replicate` was not a tool.**

`walkCommandTree` (tool-factory.ts) recursed into any command with subcommands and NEVER EMITTED
THE PARENT ITSELF. So an ACTIONABLE PARENT — a command with subcommands AND its own action
handler — could never become an MCP tool, whatever COMMAND_METADATA said. There is exactly one
such command in the tree, and it is exactly the one the spec authorizes: `repo replicate <ref>`
keeps its bare create form alongside `replicate status|remove|refresh`.

**Every signal said the flip had worked.** The `mcp` block existed. The coverage gate (which also
walked leaves only) was satisfied by its presence. `tsc` was clean. The tool count moved, because
five OTHER leaves were being excluded in the same edit. Nothing anywhere reported that the
declaration was inert — and the operator would have been told `repo replicate` was exposed to
agents when it was not.

It was caught only because the verification asked the REAL ORACLE: not "does the metadata say
tool?" but `buildAllTools(cli)` — the function that actually builds what an agent sees — with
negative controls (`repo up`, `machine status` must still be tools, so a check that merely refuses
everything cannot pass). ASK THE THING THAT DECIDES, AND PROVE IT CAN STILL SAY YES.

Both walkers now treat "runnable" (leaf OR has an action handler) rather than "leaf" as the unit,
so an actionable parent must be classified and can be built.

### 13.3b The hand-copy sweep: if two places must agree and neither imports the other, they already disagree

An operator rule, applied to the whole contract surface after `check-cli-docs.ts` was found
re-listing `EXCLUDED_TOP_LEVEL` by hand. It paid out twice more.

**`PROXY_EXCLUSIONS` had no stale-key gate, and it is the table whose entire job is to stop a
command being shipped to a remote executor.** `proxyCapable` is
`plane === 'machine' && !interactive && !(pathKey in PROXY_EXCLUSIONS)`. A key that goes stale
through a rename therefore does not fail loudly. The lookup simply misses, the exclusion STOPS
EXCLUDING, and the command silently becomes proxyCapable.

Concretely: `machine scan-keys` is excluded because it runs ssh-keyscan from the CALLER's network
position and stores the result in the CALLER's config. Rename it and forget this table, and a
remote executor starts scanning from its own network and keeping the answer, with nothing anywhere
saying so. That is bug #51's failure mode occurring INSIDE the mechanism built to prevent #51.
Its sibling `COMMAND_PLANES` has had this protection all along (`plane-coverage.test.ts` reds on a
stale entry); the proxy table did not. All seven keys were live when the gate was added, by luck
rather than by control. The generator now hard-fails on a stale key in either exclusion table,
proven red by renaming one.

**The positional-checker's exemption lists were hand-copied FOUR times, and every entry was dead.**
`scripts/lib/positional-cli-detector.ts`, both ESLint rules, and a fourth paste in
`eslint.config.js` each carried `EXEMPT_COMMAND_PREFIXES` = `rdc auth`, `audit`, `bridge`,
`organization`, `permission`, `protocol`, `queue`, `region`, `repository`, `team`, `user`, `ceph`
— all twelve deleted with the cloud adapter — plus `FREEFORM_ARG_COMMAND_PATHS` naming the removed
`agent` noun and three `mcp` leaves that no longer exist. A blanket prefix exemption for a command
that does not exist is not inert: it is a fail-open that arms itself the day someone reuses the
name. All four now import `eslint-rules/lib/cli-exempt-lists.js` (plain ESM, because an ESLint rule
cannot import a `.ts` module — which is exactly why the copies existed). The prefix list is now
empty, and that is the correct value.

### 13.3c A diff-based delta cannot see a string that became wrong without being edited

The CLI i18n delta was computed as (keys added since HEAD) + (keys whose English VALUE CHANGED
since HEAD). That is a correct TRANSLATION delta and a dangerously incomplete CORRECTNESS one.

Eighteen English strings name a flag the reshape DELETED — `--parent` ten times (the guard messages
the CLI prints to an AI agent, telling it to pass a flag that now fails with "unknown option
'--parent'", because `repo fork --parent` became a positional), `--repository` three times, plus
`--json` and `--ref`. **Their English is byte-identical to HEAD.** The reshape invalidated them by
deleting the flag they NAME, not by touching the string, so no diff of any kind can see them — and
their existing translations, in all twelve locales, were being preserved as correct.

Only a SEMANTIC check sees this: `i18n/no-undefined-cli-flags` resolves every `--flag` in every
locale string against the live command tree. Run it directly on the file; do not infer its verdict
from an aggregate lint summary (that mistake is how the strings were reported clean in the first
place).

**The rule this yields, and it generalises past i18n:** when a rename removes a symbol, every
string that NAMES the symbol is invalidated whether or not it was edited. Diffing finds what
changed. It cannot find what CHANGED MEANING. Those need a check that resolves the reference.

### 13.4 Declared debt

1. **`validate-docs-cli-usage` is SANCTIONED-RED at the P4 gate.** 309 violations remain under
   `packages/www/src/content/docs/**`. Operator ruling: www content is rewritten wholesale in
   P7, and editing 60 English files plus 772 locale files twice is waste. Precedent: the P3 i18n
   deferral. Everything else the validator covers is at zero.
2. **CLI i18n: 225 keys need translation, PLUS 18 English strings need repair** (see §13.3c — they
   name flags the reshape deleted, and no diff can see them). The 225 breaks down as (185 missing in all 12 locales, 40 whose English
   was reworded so the existing translation is present but stale). English is FINAL and has zero
   i18n lint errors. The delta is exact; the translation itself is dispatched separately, because
   the model policy reserves naturalization for Sonnet/kimi and the operator's `i18n_pipeline`
   has no `cli` surface (a known gap).
3. **OPERATOR-VISIBLE: every policy document written before P4 will now HARD-FAIL AT LOAD until
   it is re-keyed.** That is the intended behavior — refusing loudly beats permitting silently, and
   §13.1 shows what "permitting silently" actually costs — but it is a real consequence of this
   phase and it will look like a regression to whoever hits it first. The refusal names the offending
   glob and says a rename is the likely cause, precisely so the author RE-KEYS the rule rather than
   deleting it. Deleting it would complete the downgrade the rename started.
4. **`repo replicate` / `repo canary` remain MCP-excluded.** §5.4 wants them exposed; the flip is
   held until bug #49's live verdict is in. We do not advertise a command to an AI agent while
   its data path is unproven.
5. **★ THE RESHAPED CLI HAS NO PATH TO ADOPT EXISTING INFRASTRUCTURE (#68, P5 design item).**
   `datastore list <machine>` returns an EMPTY ARRAY against a machine whose renet registry holds
   four datastores. The CLI treats its own config as the sole source of truth and never asks the
   machine what is actually there. **An operator who loses their config cannot recover a live
   deployment.** `config reconcile` rebuilds state from machines, but there is no verb that
   ADOPTS resources the config has never heard of. The datastore-centric model made the machine
   the authority on storage; the CLI has not caught up.
6. **The CLI told users to run commands that do not exist.** Not docs: runtime strings. After a
   successful `repo delete` it printed *"To remove: rdc config repository remove --name X"*, a
   command the reshape deleted; `config prune`'s help named `rdc config repository purge-archived`;
   `term connect`'s description advertised `--container` actions it no longer has; `repo fork`'s
   description taught the retired `--parent`/`-m` form. All rewritten. Worth remembering that no
   gate catches a command name embedded in a sentence — the two stale KEYS
   (`commands.repo.mount`, `commands.repo.unmount`) were caught mechanically; these four were
   found by a human reading the strings.

### 13.4b A green vitest does not prove the package compiles (a REPORTING hole, not a CI one)

Vitest resolves SOURCE, not `dist`. Invalid test fixtures in this wave passed the entire
`packages/shared` vitest run and were caught only when the package was COMPILED — the type error
was real, and the suite could not see it, because running a test never type-checks the file.

**Stated precisely, because the tempting conclusion is wrong.** CI already catches this:
`check:types` runs `tsc -b packages/shared`, shared's tsconfig includes `src/**/*.ts` (tests
included), and `check:types` is in `npm run ci`. There is no missing gate. The hole is in what
AGENTS REPORT: several waves this phase, this one included, declared "all green" on a vitest run
alone, which cannot fail for a type error and therefore cannot be evidence of one.

The rule is about the claim, not the pipeline: **tsc, build and vitest each answer a different
question, and none of them is a proxy for another.** A green suite is evidence the code behaves;
it is not evidence the code compiles. Say which check you ran.

### 13.4c The placeholder gate: nothing checked what a translation INTERPOLATES

`cross-language-consistency` checks that a KEY EXISTS in every locale. Nothing checked that a
locale's `{{placeholders}}` match English's. So a translation could DROP one — or INVENT one that
never interpolates and renders to the user as the literal text `{{regions}}` — and every gate
stayed green. A missing key is loud. A mangled interpolation is silent.

It had already happened: `errors.remoteNotFound` in pt, it and ko dropped `{{clusters}}`, so the
error whose entire job is to LIST THE VALID NAMES never listed the clusters, in exactly the case
where the name you typed was meant to be one. Byte-identical to HEAD, never in any delta: §13.3c's
disease, one layer deeper — not a stale VALUE but a stale STRUCTURE.

`scripts/check-i18n-placeholders.ts` (gate: `check:ci-i18n-placeholders`) compares placeholder SETS
per key, both directions, across every locale. Written BEFORE the fix so the red was real: it found
exactly those three and nothing else across 22,056 comparisons. **It then caught its own author** —
two of the English repairs in §13.4 had themselves dropped a `{{machine}}`, which would have
committed the very bug being fixed. That is the argument for gates over habits, in one line.

### 13.4c-ii "Present" is not "translated": the fallback satisfies the gate

A missing locale key is filled by the sync/regen with THE ENGLISH TEXT, so the key is PRESENT.
Every check we owned was then satisfied by that fallback:

| Check | Asks | Verdict on an English-filled key |
|---|---|---|
| `cross-language-consistency` | is the KEY present? | green |
| `check-i18n-placeholders` | do the PLACEHOLDERS match? | green — identical text has identical placeholders |
| the translation delta | is the key NEW or REWORDED? | blind — it is neither |

**★ AN ENGLISH-FILLED PLACEHOLDER IS INDISTINGUISHABLE FROM A TRANSLATION, TO EVERY GATE WE OWN.**
Four keys shipped English in every locale, and one of them is `commands.repo.promote.confirm` —
**the confirmation prompt for promoting a fork into production.** Users in twelve languages were
asked to confirm a destructive production cutover in English.

This is §13.3c's rule from the other side. A diff cannot see a string that became wrong without
being edited; a PRESENCE check cannot see a string that was never translated at all. Both measure
a proxy (changed / present) for the property that matters (correct / translated).

`scripts/check-i18n-untranslated.ts` (gate: `check:ci-i18n-untranslated`) fails a locale value that
is byte-identical to English above a length threshold. ★ The threshold was MEASURED, not guessed:
bucketing every identical value by length showed the shortest real defect at 38 characters
(`repo.promote.revertHint`) and every legitimate one (`OK`, `ID`, product names) below 30. A
threshold of 61 — the "obviously long" cutoff — would have MISSED a real defect. The allowlist
carries a reason per entry and is itself gated against the live key set, because an allowlist that
outlives its keys is the fail-open this repo has now found five times over (§13.3b).

### 13.4c-iii The flag check asked whether a flag exists ANYWHERE, not whether it is valid HERE

`i18n/no-undefined-cli-flags` builds ONE GLOBAL SET of every flag on every command and asks "does
this flag exist?" So `rdc repo secret get --name {{repository}} --key {{key}}` PASSED — `--name`
exists, just not on that command. And nothing at all validated the SUBCOMMAND PATH inside a locale
value, so `rdc auth login` (the `auth` noun was deleted with the cloud adapter), `rdc config machine
add`, `rdc repo takeover`, `rdc machine query` and `rdc config set --key` all shipped as
instructions the CLI prints to users.

**25 such examples, across 23 keys, in every language.** `errors.precondition.next.options.confirm.run`
is the sharpest: it is the NEXT-STEP HINT after a precondition failure, so when something had
already gone wrong the CLI handed the user a command that fails too.

The fix reuses `validateInvocation` — the per-command resolver `check-cli-docs` already had — and
points it at the locale VALUES. ★ CHECKING THAT A TOKEN EXISTS SOMEWHERE IS NOT CHECKING THAT IT IS
VALID WHERE IT IS WRITTEN. That is `term_exec`'s disease (§13.3), stated for flags instead of argv.

### 13.4c-iv A locale can invent product behavior, and nothing can diff prose

Recorded as a known limitation rather than a gate. A pass-2 translator found that Turkish's
`help.keyConcepts` was not merely untranslated: it contained **a bullet that does not exist in the
English source at all** ("Containers must bind to SERVICE_IP…") and was missing several that do.
The translation said something the product never said.

That is content drift in the opposite direction from a dropped placeholder — a locale INVENTING
behavior. Placeholders and flags can be checked mechanically because they are tokens; prose cannot.
The i18n surface can therefore assert things about the product that no gate will ever contradict.
P7 review item.

### 13.4c-v Command parity: a command name is never translated

The sibling of placeholder parity, and the gate that replaced a worthless piece of bookkeeping.

Asked "which locale strings are stale?", the obvious method is to diff the English keys you edited
against the keys you sent to translators. **That answer is worthless.** It tells you what went
through your process; it cannot tell you what is wrong on a user's screen. Run against this tree it
reported 239 uncovered keys, nearly all of which were fine (earlier waves had translated them
directly), while MISSING keys that were genuinely broken.

The semantic question is answerable, because of one invariant: **a command name is never
translated.** `repo up` is `repo up` in every language, and so is `--name`. So for any key, the
command paths and flags a LOCALE names must be a SUBSET of what ENGLISH names.

- Naming FEWER is a translator's stylistic choice (mentioning a command once where English mentions
  it twice). Tolerated.
- Naming something ELSE is staleness or invention. Always a bug.

★ Subset, not equality — and that distinction is what makes it usable. An ABSOLUTE check on a
locale is hopeless: a locale value is prose with commands embedded, and the prose is translated, so
`rdc repo sync en su lugar:` puts a Spanish preposition in command position. The first attempt
produced ten "defects" that were all Spanish, German and Arabic function words. No list of English
stopwords fixes that, and no one should maintain a list of twelve languages' stopwords. Under the
parity rule the translated prose simply ends the path, identically in every language, and vanishes
from the comparison.

It found 29 keys — including several the diff-based method could not see: keys pass-1 had
translated BEFORE English changed again, and keys that were never in any delta at all.

### 13.4c-v-b A false-positive filter can blind a gate to the very case it exists to catch

The command-parity gate had to survive twelve languages of prose. `rdc para usar la versión
anterior` puts a Spanish preposition in command position, so the rule became: ignore any invocation
whose head token is not a LIVE top-level command.

★ That rule ignores `rdc auth login`.

`auth` WAS a live top-level command until the cloud adapter was deleted. It is the single worst
string in the catalogue — the CLI telling a user, in twelve languages, to run a noun that no longer
exists — and the filter written to keep the gate quiet made it *silent on exactly that*. A gate
tuned not to cry wolf had been tuned into not seeing the wolf.

**The fix is a discriminator, not a bigger stoplist.** Record the unresolved head, and let ENGLISH
decide: if English names a REAL command for that key and the locale's head names nothing, the locale
is stale — because prose does not REPLACE a command, but a dead noun does. If English names no
command either, it is prose on both sides and ignored.

Verified in both directions, which is the only way this can be trusted: `rdc auth login` is now
flagged in all twelve locales, and the three prose false positives it was built to suppress stay
green.

> ★ When you narrow a check to silence false alarms, ask what TRUE alarm the narrowing also
> silences. An exclusion written against noise is still an exclusion, and it fails open exactly like
> every other one in this document (§13.3b).

### 13.4c-vi A half-applied fix is a new blind spot wearing the old fix's green

The docs scanner matched `rdc` only when preceded by whitespace, a backtick or a paren, so
`run_cmd "rdc ..."` — how most of `.ci/tutorials` is written — was invisible. The MATCH class was
widened to accept a quote. **The STRIP that removes the leading delimiter was not.**

So a quoted invocation was matched, kept its leading quote, failed `startsWith('rdc')`, and was
SILENTLY DISCARDED. The scanner then reported ZERO for `.ci/tutorials` and ZERO for the English
locale, and that zero was reported upward as evidence.

★★ THE SCANNER REPORTED ZERO AND HAD LOOKED AT NOTHING. It is the same shape as the crashed lint
run that "found 1 error", and the replica that comes up Ready and serves nothing. Behind it sat four
more dead commands in English (`rdc config cert-cache pull`, `rdc config infra set|push`, `rdc config
repository restore-archived`) — every one inside a single-quoted example, every one invisible.

> ★ A HALF-APPLIED FIX IS NOT A PARTIAL IMPROVEMENT. It is a fresh blind spot, and it is wearing the
> green of the fix it half-applied. When a tool goes quiet somewhere it used to be noisy, that is not
> success — that is the first thing to explain.

### 13.4d An aggregate hides the thing that moved

Three separate near-misses in this wave shared one shape, and it is worth stating as a rule rather
than as three anecdotes.

- **The lint count collapsed from 2379 to 1.** It looked like a triumph. ESLint had CRASHED. A
  detector fix cannot delete 2244 cross-language errors, so the number was read as a question and
  the RAW OUTPUT was opened. ★ An error count that COLLAPSES is as suspicious as one that rises —
  and more dangerous, because nobody audits a victory.
- **"English has zero i18n errors"** rested on a grep of AGGREGATE lint output. English had 22.
  Running ESLint DIRECTLY ON THE FILE gave the truth.
- **A test total could not be reconciled** because only the SUM had ever been recorded. The answer
  came from an A/B run diffing PER FILE.

> ★ **A TOTAL IS NOT A RECONCILABLE ARTIFACT; A BREAKDOWN IS.** An aggregate answers "how much",
> which is never the question. The question is always "which one moved", and a sum has thrown that
> away before you read it. Snapshot the breakdown. Read the raw output. And when a number improves,
> ask why with the same suspicion you would give a number that got worse.

This is the same failure as trusting a checker that cannot fail for the right reason, one level up:
the aggregate IS a checker, and its blind spot is indistinguishable from a passing check.

### 13.4e The teardown was tested in both directions, and the product now refuses loudly

Worth recording because it is the doctrine landing as SHIPPED BEHAVIOR rather than as review
standard. The #49 fix adds a LUKS close on the discard path. w3 tested its ABSENCE as well as its
presence: discard WITHOUT the close produces an HONEST REFUSAL — *"failed to unmount thin overlay
(holders still present) ... target is busy"* — rather than a silent success.

So the close is genuinely necessary (its absence is observable), and the failure mode of forgetting
it is a REFUSAL, not a quiet corruption. That is the same shape as `datastore.detach_residue`: the
software declining to claim a success it cannot substantiate. A fix validated only in the direction
where it works has not been validated.

### 13.5 The doc gate

`docs/design/06-cli-reshape.md` §1 is no longer a target tree; it is a transcript, and
`scripts/check-design-tree.ts` checks it against the shipped CLI **in both directions** — no
phantom commands, no omitted ones. It found four real omissions the moment it was written
(`machine infra *` had been unlisted for the whole phase). A design doc that describes a tree the
code no longer has is worse than no doc: the next reader trusts it, and all five path-keyed
classification systems are keyed by the exact command path it gets wrong.
