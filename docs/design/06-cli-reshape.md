# 06 — Full CLI Reshape: Command-by-Command Mapping

User decision 2026-07-10: the FULL reshape ships in this program, not just the
redesign-required verbs. No backward compatibility, no aliases, no deprecation windows
(sole operator, clean break).

**THE MAPPING IS THE CONTRACT, NOT THE LEAF COUNT.** The "~90 leaves" this file once
promised was retired by gate ruling R2 as bad arithmetic; spec/03's replacement figure
("162 current, 153 target") has now failed the same way (its own §6.7 header contradicts
the table under it, and operator commits moved the live tree by 19 commands within days of
the spec being written). A number that its author miscomputed and that drifts with every
merge cannot gate anything. What P4 is held to is the **disposition table in spec/03 §6**:
every command in the live tree carries a row, and every row resolves to a real command.
That is mechanically checkable now that `packages/cli/scripts/command-tree.json` exists,
and unlike a number it cannot be satisfied by accident. For orientation only, and with no
contractual force: the tree is ~183 invokable commands today and the reshape lands around
165.

Design principles:
1. Nouns mirror the physical layers: `machine` → `datastore` → `repo`, plus `cluster`
   (composition) and `backup` (cross-cutting).
2. Same verb = same meaning at every layer: `fork` is always CoW, `migrate` is always
   move + lifecycle + health gate, `snapshot` is always a moment, `up/down` always run
   Rediaccfile hooks, `status` always reads.
3. Resource CRUD lives on the resource; `config` keeps only the FILE itself.
4. The simple case stays invisible: every machine gets a `default` datastore; single-machine
   docker users never type `--datastore`.
5. Gating carries over by verb class (grandGuard on mutating repo verbs; cluster family
   behind `REDIACC_ALLOW_CLUSTER_OPS`; hidden `run` unchanged, absolutely agent-blocked).

## 1. The tree — AS BUILT (verified against the live CLI, 2026-07-13)

This is no longer a target. It is a transcript of the shipped tree, generated from
`packages/cli/scripts/command-tree.json` and checked in BOTH directions: every leaf below
exists in the CLI, and every leaf in the CLI appears below. **166 contract commands**
(93 machine-plane, 53 config-plane, 20 other; 82 proxyCapable). `run` is hidden and held
out of the contract.

```
rdc config:     init list show current delete set clear recover prune edit reconcile rotate-cek
                field {get set unset rotate list}    audit {log tail verify}
                remote {enable disable status refresh}    ssh {set show remove}
rdc machine:    add remove list status setup scan-keys health prune
                provision deprovision
                provider {add remove list}
                infra {set show push  cert {pull push status clear}}
rdc datastore:  create list status attach detach fork snapshot {create list} resize delete
rdc repo:       create up down status list delete fork push pull migrate promote
                secret {get list set unset}    sync {upload download status}
                cat diff logs exec tunnel
                replicate {status remove refresh}          (the parent also runs: `replicate <ref>`)
                commit branch checkout log merge gc
                resize expand trim policy {set get}
                admin {validate fsck ownership autostart {enable disable list}
                       template {list apply}  archive {list restore purge}}
                canary {create status weight remove}
rdc cluster:    create scale join evict destroy status kubeconfig snapshot {create list}
                fork migrate rehearse
rdc backup:     strategy {set remove list show bind unbind}  retention {set clear}  schedule  run  status  cancel  list  snapshot  restore  verify  manifests  usage  browse
rdc storage:    add remove list import browse prune
rdc term:       connect
rdc vscode:     connect list cleanup check serve {status stop}
rdc ops:        up down status ssh setup check
rdc subscription: login logout status refresh
rdc job:        list status logs cancel gc          (see §9)
rdc doctor | credits | update | serve | mcp serve | run (hidden)
```

### 1.1 Where the shipped tree differs from the tree this section used to draw

Nine differences. The first six are deliberate and each is traceable to a ruling. The
seventh IS drift, and is recorded as such: it is what this gate exists to catch. The
last two are a whole program landing after this transcript was drawn.

| Was drawn as | Shipped as | Why |
|---|---|---|
| `config` with no `current` | `config current` | The config-universe refactor (server.json folded into per-config `account.*`, dev/prod/bench as named configs) added a "where am I connected" surface: active config, resolved account server with winning source, channel, token state, remote-store status. `show` dumps the config document; `current` answers the runtime resolution question `show` cannot. |
| `storage create \| delete` | `storage add \| remove` | Gate ruling R3, and spec/03 §4.1's own rule: a storage entry REGISTERS an existing external endpoint (an S3 bucket, an rsync target), it does not create one. §4.1 explicitly deferred the rename here to this as-built pass. |
| `machine` with no `infra` | `machine infra {set show push}` + `machine infra cert {pull push status clear}` | The config exodus (§5.2 / w2a) moved `config infra *` and `config cert-cache *` onto the machine noun. Seven leaves this section simply never listed. |
| `repo replicate {status remove}` | `repo replicate <ref>` (actionable parent) + `{status remove refresh}` | `refresh` was a CONDITIONAL in the table below: delete it if it only reconciles, keep it if it forces a re-fork. It forces a re-fork, so it stays, and its help says so. The parent keeps its bare create form (spec §5.4), which makes it an actionable parent — that is load-bearing, see §7's Commander note. |
| `cluster snapshot` | `cluster snapshot {create list}` | R2-F13 landed it as a group, matching `datastore snapshot`. |
| `machine query` | `machine status` | §5.2. Recorded here because the `--fix` map in `scripts/check-cli-docs.ts` had the rename pointing the WRONG WAY and would have rewritten correct docs into broken ones. |
| `backup strategy {set remove list show}` | `backup strategy {set remove list show bind unbind}` | `bind`/`unbind` landed with the backup-strategy binding work in #524 and this transcript was not updated with them. Caught only when `check:ci-design-tree` was run locally: that gate is in `npm run ci` but no workflow invokes it, so main merged the drift green. |
| `backup` with no chunk-store verbs | `backup {snapshot verify manifests usage browse}` + `backup retention {set clear}` | The backup-storage program replaced the rclone/OneDrive push with a content-addressed chunk store, and seven leaves came with it: `snapshot` writes, `verify` checks a stored snapshot end to end, `manifests` and `usage` read the store, `browse` lists what a repository actually contains, and `retention {set clear}` is the policy the pruner reads. `restore` was already drawn, but it now materializes a chunk-store snapshot rather than a pushed image. Not drift in the §1.1 sense: the program is documented at `docs/backup-storage/`, and this transcript simply postdates it. |
| `storage browse` as the only file listing | `backup browse` (local, read-only) | `storage browse` remains, and browses a live rclone remote. `backup browse` answers a different question — what is inside a REPOSITORY — and it answers it without a server, a network, or credentials, which is what makes it usable in a disaster. It cannot be served from the chunk store: the manifest maps grid cells to the SHA-256 of their CIPHERTEXT and carries no filesystem data at all, so a listing has to come from opening the image. The reasoning and the staged plan are at `agent/PLAN-chunk-store-browse-DECISION.md`. |

Four families were built by operator commits AFTER this tree was drawn. They exist in the
live CLI today, so P4 recontracts them; it does not invent them. **All four were ruled on
2026-07-13** (spec/03 §9) and are folded into the §1 tree above:

| Family | Leaves | RULING |
|---|---|---|
| `job {list,status,logs,cancel,gc}` | 5 | **KEEP as a noun** (reasoning in §9). A job is **EXECUTOR-BORN**: `rdc serve` sets `detached` itself for detachable commands (the container tier sleeps after 2-5 min idle), plus a global **`--background`/`-b`** fire-and-forget for direct CLI use (R-P4-2v2, merged from two operator rulings — spec/03 §5.13) |
| `repo canary {create,status,weight,remove}` | 4 | **KEEP under `repo`.** Same subject (a repo's traffic); a new noun for 4 leaves is not earned |
| `repo replicate refresh` | 1 | **Conditional:** DELETE if it only reconciles (the create form is already the declarative surface, spec/03 §4.4); KEEP if it forces a re-fork now, and say so in its help |
| `config rotate-cek`, `serve` | 2 | **Both stay top-level.** The CEK is the key the config is encrypted under (not a field value) and has a portal wizard; `serve` is the other end of `--proxy`, and the two are one wire |

## 2. ELIMINATED commands (deleted with their machinery)

| Command | Why gone |
|---|---|
| `config machine set-ceph` | Ceph is a datastore-backend property → `datastore create --backend rbd ...` |
| `datastore init` | replaced by `datastore create` (named, multi-datastore) |
| `datastore unfork` | replaced by `datastore detach --discard` |
| `cluster install` | folded into `cluster create` (Ceph-first ordering is renet's job, not a user step) |
| `config cluster add-pool` | pools declared at `cluster create` / edited via `cluster scale` |
| `machine backup *` (5 leaves) | unified into `rdc backup` |
| `repo backup {list, schedule}` | unified into `rdc backup` |
| `config backup-strategy {set,remove,list,show}` | unified into `rdc backup strategy *` |
| `repo mount` / `repo unmount` | folded into `repo up`/`repo down` (+ `--no-start` flag for mount-only); LUKS open/close is an implementation detail users never needed separately |
| `repo takeover` | renamed `repo promote` (says what it does) |
| `repo validate`, `repo fsck`, `repo ownership`, `repo autostart *`, `repo template *` | moved under `repo admin *` (niche plumbing out of the daily surface) |
| `machine containers`, `machine services`, `machine repos` | folded into `machine status` sections (today's `machine query --containers` etc.; `query` renamed `status`) |
| `machine create` / `machine delete` | replaced by `machine add` / `machine remove` (the config-CRUD names; one pair, not two) |
| `config machine {add,remove,list,scan-keys,setup}` | moved to `machine add/remove/list/scan-keys/setup` |
| `config provider {add,remove,list}` | moved to `machine provider *` |
| `config storage {import,remove,list,show}` | moved to `storage import/delete/list/browse` |
| `config repository {add,remove,list,list-archived,restore-archived,purge-archived}` | `add/remove/list` die with GUID-mapping being internal; archive verbs move to `repo admin archive {list,restore,purge}` |
| `config cluster {add,list,remove}` | `cluster create` declares + provisions (with `--declare-only` for the old two-phase flow); `cluster status` lists; `cluster destroy` removes |
| `config infra {set,show,push}` + `cert-cache {pull,push,status,clear}` | moved to `machine infra *` (infra is a machine property) |
| `subscription activation status`, `subscription repo status`, `subscription refresh {activation,repos,repo}` | flattened into `subscription status [-m M]` and `subscription refresh [-m M] [--repo N]` |
| `vscode serve status/stop` | kept but likely `vscode serve {status,stop}` unchanged — no elimination, listed for completeness |
| Whole-cluster fork's `dstAgents >= srcAgents` constraint | not a command, but the flag contract changes: `cluster fork --cluster <dest>` no longer requires agent-count symmetry (anchor + rejoin) |
| `machine rename` / `storage rename` | **names are identity (R2-F4)**: name-based cross-references with no referential-integrity machinery make rename a dangling-reference factory; delete + re-add is the rename |
| `backup now` | renamed `backup run` (R2-F16 — "now" is not a verb; matches `kubectl create job --from=cronjob` muscle memory) |

## 3. REPLACED / CHANGED commands (same intent, new contract)

| Today | Target | Change |
|---|---|---|
| `datastore fork --pool --source --dest` | `datastore fork <name> --tag T [--attach-to M --writes local\|ceph]` | named datastores; attach requires explicit `--writes` on forks (fails without) |
| `datastore status/resize` | same verbs, but take `--name` (multi-datastore) | |
| `repo create --name X -m M` | `repo create X --machine M` OR `repo create X --datastore D` (exactly one; k8s ALWAYS --datastore; `--cluster` dies) | placement stated once at birth; 02 §7 |
| `repo fork --parent P --tag T [--cluster C]` | `repo fork P --tag T` — no runtime flag at all | the flag-based seam dies: the parent's placement determines docker-vs-k8s, `RepoRuntime` dispatches; internals for k8s = clone the repo folder + volumes in the datastore + re-render manifests (RADOS-ns/csi path deleted; single-snapshot atomicity across a repo's volumes) |
| `cluster fork --name --tag --cluster DEST` | `cluster fork --name --tag --to <machines\|cluster> [--writes ceph\|local] [--up]` | hot group-snap fork; ephemeral test clusters via `--writes local`; any dest node count |
| `cluster migrate --name --to` | same, but in-Ceph = fenced datastore remap (no data copy); cross-site = snapshot+diff pipeline with down()/up()/health gate | |
| `repo migrate` | unchanged UX; gains the health gate + role env | |
| `repo secret *` | unchanged UX; k8s repos now materialize secrets as k8s Secret objects at up() | fork-empty policy extends to namespaces/clusters |
| `repo up/down` | unchanged UX; inject `REDIACC_ROLE`/`REDIACC_WRITES`/`REDIACC_DATASTORE`; k8s: generate `local` PVs + ds node-affinity | |
| `machine query` | `machine status` (rename; section flags kept) | |
| `cluster create --name` (provider preset via `config cluster add`) | `cluster create --name --provider ... --pool ... [--declare-only]` one-step | KVM topology flags (`--net-name/--net-base/...`) move here |

## 4. NEW commands

| Command | Purpose |
|---|---|
| `datastore create --machine M [--name D] [--backend local\|rbd] [--size]` | ADDITIONAL named datastores only. `machine setup` auto-creates the `default` datastore (local, /mnt/rediacc) — single-machine users never touch this command; `repo create` without `--datastore` targets `default` |
| `datastore attach <name> --to M [--writes local\|ceph]` / `datastore detach <name> [--discard]` | mobility + the fork-write contract; fencing on attach |
| `datastore snapshot create/list [--group <cluster>]` | the consistent-moment primitive (BTRFS local / rbd snap / rbd GROUP snap) |
| `repo replicate --name --replicas N --refresh <d> [--headless]` | read replicas (05 §1) |
| `cluster rehearse --name [--snapshot S] --on <machine>` | boot snapshot as throwaway fork, health-gate, report, discard |
| `repo logs <repo> [--container C] [-f]` | application logs — the #1 operator verb was missing entirely (R2-F14; today only hidden agent-blocked `run container_logs`) |
| `repo exec <repo> [--container C] -- <cmd>` | blessed exec path (R2-F14; today an undocumented `term connect -c` side door) |
| `cluster snapshot create/list --name C` | porcelain for the cluster-consistent moment (R2-F13; plumbing = `datastore snapshot --group`, which stays) |
| `config reconcile` | rebuild the config's `state` bucket from machine truth via `renet list all --json` (R2-F2; also the repair path the derived-routing mismatch error suggests) |
| `repo replicate {status,remove}` | replicate creates ongoing managed state; it gets CRUD from birth (R2-F17), plus replica visibility in `repo status` |
| `cluster join <machine> --cluster C` | adopt an EXISTING registered machine as a k8s agent (CA-token join — the anchor+rejoin machinery makes this cheap). Today membership only enters via pool provisioning; arbitrary machines cannot be enrolled |
| `cluster evict <machine>` | remove a SPECIFIC node: drain → fence → delete Node object → deregister (the codified F3 failover sequence as a verb). Today's `scale` only trims LIFO from the top pool index and cannot target a node |
| `repo admin archive {list,restore,purge}` | relocated archive verbs |
| `backup restore` | first-class restore (today only a hint + pull) |
| image-into-cluster step | minimal viable: part of k8s `repo up()` flow (build + `ctr images import`); a standalone `repo build` verb is optional — P0 spec decides |

## 5. KEPT AS-IS (unchanged surface)

`repo` daily verbs (create/up/down/status/list/delete/fork/push/pull/cat/diff/tunnel/sync/
secret/commit/branch/checkout/log/merge/gc/resize/expand/trim/policy), `term connect`,
`vscode *`, `ops *`, `doctor`, `credits`, `update`, `mcp serve`, hidden `run`, `storage`
core verbs, `config` file-level verbs (init/list/show/delete/set/clear/recover/prune/edit/
field/audit/remote/ssh).

## 6. Addressing model: positional names, derived machine, `@place`

Root cause being fixed: config never stored a repo's machine (`repositories` is a flat
name-keyed record, no machine field) — hence `-m` on every verb. The redesign adds
placement (repo → datastore) and attach state (datastore → current mounter machine), making
the machine DERIVABLE. On top of that:

1. **Positional primary name** per noun: `rdc repo up shop`, `rdc machine status prod-1`,
   `rdc cluster fork prod --tag staging`. `--name` dies (the noun already names the kind).
2. **`--machine` disappears from repo verbs** (derived via placement). The ONE exception is
   `repo create`: placement is stated once at birth with exactly ONE flag —
   `--machine prod-1` (docker shortcut: the machine's `default` datastore) or
   `--datastore ds-alpha` (docker tiering AND the mandatory k8s form; the datastore implies
   its cluster, so `--cluster` on create dies). **Kubernetes repos always name their
   datastore** — placement in a cluster is consequential (home node, failover group,
   fork-affinity, snapshot group) and nearly immutable, so it is never defaulted (02 §7).
   Ambiguity anywhere else is always an error listing candidates, never a guess.
3. **`@place` address**, composing with the existing fork colon: `repo[:tag][@place]` —
   `shop`, `shop:test`, `shop@backup-1`, `shop:test@prod-1`. A "place" is a machine OR a
   cluster (one namespace; config knows the type; name collisions refused at config time).
   Unifies targets: `repo push shop --to backup-1`, `term connect prod-1` (machine shell)
   vs `term connect shop@prod-1` (repo shell).
4. Resource names forbid `:` and `@` (create-time validation). `--datastore` only at
   `repo create`; `--to` only for targets. MCP/agent schemas stay named-parameter
   (unaffected).
4b. **`@place` conflict rule (R2-F10)**: for a live repo, placement is derived, so `@place`
   is either redundant (matches) or CONTRADICTORY — a contradiction always ERRORS listing
   both ("shop is placed at prod-1; you addressed shop@other — for the pushed backup copy
   use `backup restore`, for a move use `repo migrate`"). Silent retargeting never happens;
   `repo up shop@other` must not be an action-at-a-distance deploy. The P0 spec carries a
   per-verb table of where `@` is accepted at all (legitimate referents: backup artifacts,
   `term connect` targets, `--to` destinations).
4c. **`term connect <name>` namespace collapse (R2-F11, resolved by the ambiguity rule)**:
   repos and places are separate namespaces; a bare name that matches BOTH a repo and a
   place errors demanding qualification (`term connect shop@prod-1` for the repo shell,
   or rename one of them). No global repo-vs-place collision refusal (too heavy a tax for
   one verb), no marked form — the existing "ambiguity is always an error, never a guess"
   rule covers it at collision time only.
5. **Semantic decision (spec item)**: placement is single-valued; repo names unique per
   config. A `push`ed copy on another machine is a BACKUP ARTIFACT, not a second live repo,
   until restored/promoted under a name. (Today "push and the same name runs in two places"
   — that behavior is retired.)
6. Rejected alternatives, for the record: kubectl-style default-machine context (mutable
   global state + destructive verbs + agents = surprising targets); resource URIs
   (ceremony). Note the repo's docs validators (`positional-cli-detector`,
   `validate-cli-examples`) currently treat positional syntax as INVALID — both flip to
   parsing the new grammar in P4.
7. **BLOCKER (found 2026-07-13), now RULED: the CLI contract is options-only and HARD-THROWS
   on the first positional.** `walkContractCommands()`
   (`packages/cli/scripts/lib/command-tree-lib.ts:270-279`), the shared walker behind the
   contract generator, the plane gate and the plane-coverage test, raises on any command that
   registers a positional, because every contract consumer (web console, `--proxy` thin
   client, executor) serialises a command as flags alone. Today's CLI has ZERO positionals,
   so the first leaf P4 converts takes down `check:ci-cli-contract`,
   `check:ci-command-planes` and `plane-coverage.test.ts` at once.
   **OPERATOR RULING R-P4-1: BUILD IT. P4's first deliverable is the ref concept, not a
   rename.** And it is more than serialisation: the console binds its resource pickers AND
   its computed action-bar buttons to `machineOption`/`repoOption`, i.e. to `--name` and
   `--machine` — the exact flags item 1 and 06 §6.2 delete. Emit positionals without moving
   those bindings onto the ref and you ship a CLI that works and a GUI that quietly empties
   (`ActionBar.tsx`: *"There is no array of command names in this file, and there must never
   be"*). The full deliverable, the five modules, and the acceptance test (a positional leaf
   that walks the contract, crosses the `--proxy` wire, and renders as a resource picker with
   `check:ci-console-coverage` green) are in spec/03 §2.0.

## 7. CLI conventions (review round 2, adopted)

1. **add vs create is a RULE, not an accident (R2-F18)**: `add`/`remove` = register/
   deregister something that already exists (machines, providers); `create`/`delete` =
   make/destroy the thing itself (repos, datastores, clusters). One sentence in the help
   root; kubectl lacks this distinction and suffers for it.
2. **Confirmation flags standardized (R2-F18)**: `-y/--yes` = skip confirmation,
   everywhere. `--force`/`--discard` = "accept data loss", exclusively. One flag never
   carries both meanings (kubectl's `--force` regret).
3. **Scripting contract is a P0 deliverable (R2-F15)**: documented distinct exit codes for
   health-gate failure vs infrastructure failure vs ambiguity refusal (precedent: exit 10
   = LICENSE_REQUIRED); a per-verb idempotency table (`datastore attach` when already
   attached = success; `create` on existing = error; `backup run` while running = error
   with the running id); every new verb goes through `outputService.print` and supports
   `-o json`.
4. **Verb-semantics notes (R2-F13/F20)**: `repo commit` = moment + ref metadata,
   `datastore/cluster snapshot` = raw moment — the split is documented, not papered over.
   `repo migrate`/`cluster migrate` disclose WHICH transport will run (in-Ceph zero-copy
   remap vs cross-site copy pipeline) in status/rehearse output BEFORE cutover. `resize`
   (offline, grow+shrink) vs `expand` (online, grow-only) distinction stated in help text —
   deliberately not merged.
5. **`backup restore` vs `repo promote` boundary (R2-F16)**: restore materializes a pushed/
   backup artifact into a live repo name (placement stated at restore time); promote swaps
   a validated FORK into production. Restore never promotes; promote never fetches.
6. **Lifecycle is mechanism, not commands**: the node graceful shutdown/boot machinery
   (02 §3) adds ZERO verbs — systemd units trigger it, the reconcile timer converges it,
   and the only visible piece is a policy flag (`datastore attach --no-auto`, mirroring
   the docker world's autostart toggle). Planned relocation is the existing
   `datastore attach --to`; permanent removal is `cluster evict`; pod-level drains belong
   to kubectl via `cluster kubeconfig`. No `machine maintenance`/`node drain` verbs:
   forgettable manual steps are exactly what the mechanism exists to remove.
7. **Every move is an implicit plane re-declaration (2026-07-13).** A command's execution
   plane (`machine` | `config` | `other`, i.e. where its code RUNS) is a pure function of
   its PATH STRING: a longest-prefix lookup in the hand-maintained `COMMAND_PLANES` table
   (`packages/cli/src/config/command-planes.ts:42-163`), where a domain entry is the
   default and everything else is an exception. The plane system will never block a move,
   and it will never follow the verb either: a moved verb silently adopts its new domain's
   default. Because the contract turns `plane === 'machine'` into `proxyCapable`, a move
   into a machine-default noun can silently make a local read remotely executable against
   the WRONG config. **Plane classification is therefore a first-class per-leaf deliverable
   of the reshape, reviewed leaf by leaf, not a regeneration afterthought.** The gates
   catch only the loud half. Full mechanism, both worked hazard cases and the review rule:
   spec/03 §4.9.
8. **`--detach` had three meanings, two of them flags (2026-07-13). RULED.**
   `repo up --detach` / `repo fork --detach` meant "return once containers start, health
   checks continue" (renet `repository_up.go:30`); a detached JOB means "the whole operation
   runs under transient systemd and survives SSH loss"; `datastore detach` means "unmount a
   datastore". The third is a verb on a noun and is tolerable (docker and kubectl live with
   the same overload). The first two were flags on the SAME commands and directly violated
   principle 2. **OPERATOR RULING R-P4-2v2 (twice-ruled, merged): the health-check flag is
   renamed `--no-wait`** (which is what it always meant) **and the job producer is the GLOBAL
   `--background`/`-b`** — so after P4 the word "detach" survives only as the `datastore
   detach` verb. The parallel detached-jobs session settled the name: Commander resolves a
   root-level and a subcommand flag of the same name BY POSITION, so reusing `--detach` for
   jobs would make `rdc --detach repo up` and `rdc repo up --detach` silently mean different
   things. ⚠ This **REOPENS AND SUPERSEDES spec/03 U6**, which explicitly kept `--detach` on
   `repo fork`; the reversal is deliberate, and its reason is that when U6 was written the
   `job` noun did not exist, so there was no collision to see.

## 8. Regeneration obligations (part of the reshape's definition of done)

- cli-docs are GENERATED — never hand-edit; regenerate after the tree changes.
- rdc skill reference regenerates via rdc.sh's generate-skill-reference step.
- `scripts/validate-cli-examples.ts` validates every `rdc ...` snippet in docs/CLAUDE.md/
  skills against the live tree — all documented snippets must be updated in the same phase.
- Command metadata (`command-metadata.ts`): re-annotate grandGuard/agentBlocked per verb.
- CLI i18n: en strings for every new/renamed command; 12 locales re-naturalized via the
  i18n pipeline (Sonnet; ledger-driven).
- Renet bridge functions renamed/added/deleted → `renet functions generate-types --output
  packages/shared/src/renet-contract/data`; every generated function name must appear in
  packages/e2e-tests sources or `check:ci-e2e-coverage` fails.
- **MCP alignment gate (P4 closing step)**: the existing `mcp-coverage.test.ts`
  (`packages/cli/src/commands/mcp/__tests__/`) is registry-keyed and misses unregistered
  leaves — verified 2026-07-10: a tree-walking version found **56 drifted commands** with
  neither `mcp` nor `mcpExcludeReason`. Confirmed still true 2026-07-13 and now worse: it
  iterates `COMMAND_REGISTRY` (13 domains) while the live tree has 16, so the `job`,
  `cluster`, `credits` and `serve` domains are not checked for MCP coverage AT ALL, which
  is how `serve` and `config rotate-cek` reached main with no `COMMAND_METADATA` entry of
  any kind. After the reshape lands, apply the parked patch (strengthened tree-walk test +
  a starter classification; session scratchpad `parked/mcp-coverage-gate.patch`) and
  classify every leaf of the NEW tree. Deliberately deferred to post-reshape (user
  decision): classifying the old tree first would be throwaway work. The test runs under
  `check:test-cli`, already in the `npm run ci` chain — no new CI wiring needed.

**Five artifacts and gates created after this list was written (2026-07-13).** They are
now the heaviest part of the reshape's definition of done. Exact commands and the
per-leaf checklist are spec/03 §8; the short version:

- `packages/cli/scripts/command-tree.json`: committed, regenerated by
  `npm run export:command-tree -w @rediacc/cli`.
- The **generated CLI contract** (`packages/shared/src/cli-contract/data/`:
  `contract.generated.ts` + `contract.json` + **13 per-locale i18n bundles**), regenerated
  by `npm run generate:cli-contract -w @rediacc/cli`. Gated by `check:ci-cli-contract`,
  which is a regenerate-and-diff, not a hash: ANY rename, move, added flag or changed help
  string turns it red. This contract drives the web console, the `--proxy` thin client and
  the executor, so a stale one means those three disagree with the CLI they are driving.
- `packages/cli/src/config/command-planes.ts`: every new, renamed or moved leaf needs a
  plane. Gated twice (`check:ci-command-planes` + `plane-coverage.test.ts`, which also
  fails on STALE entries, so every rename strands one).
- `DOMAIN_MODULES` in `packages/cli/scripts/check-command-planes.ts:48`: **a new
  top-level noun with no entry HARD-FAILS the gate.** The reshape introduces `backup`, so
  it must register `commands/backup.ts` there.
- `PROXY_EXCLUSIONS` in `packages/cli/scripts/generate-cli-contract.ts:61`: the
  machine-plane commands a remote executor must never run for the caller, keyed by command
  path. Every rename silently breaks a key, and every new machine-plane leaf needs a proxy
  verdict plus a user-facing refusal reason.

**Two more systems, found 2026-07-13, that no version of this list has ever named.** Both are
keyed by the command path, like everything else, and between them they carry the reshape's
worst failure modes. Full statements: spec/03 §4.11 and §2.0.

- ⚠ **The PERMISSION-POLICY globs** (`packages/shared/src/policy/`, `services/serve/policy.ts`,
  the console's `PolicyRuleEditor`). Org policy documents allow and deny commands by **glob on
  the path string** (`"repo *"`, `"repo delete"`), live inside the encrypted config, and are
  evaluated by both the executor and the console. P4 renames every path. A stale `allow` fails
  CLOSED (safe, loud). **A stale `deny` FAILS OPEN**: `deny: ["repo takeover"]` silently stops
  denying the moment the leaf becomes `repo promote`. It is the only classification system in
  the tree whose staleness *grants* a permission that was explicitly withheld, and it has no
  gate. P4 re-keys every glob AND builds the gate (a `deny` glob matching no live command is a
  hard failure, not a warning).
- **The console's REF BINDINGS.** Resource pages compute their action buttons from the
  contract (`ActionBar.tsx`: *"There is no array of command names in this file, and there must
  never be"*), binding through `machineOption`/`repoOption` — the flags this reshape deletes.
  The bindings must move onto the positional ref in the same change, or the pages render
  empty while every gate stays green.

## 9. The `job` noun (built 2026-07-12, unmapped by this file)

`rdc job {list,status,logs,cancel,gc}` (`packages/cli/src/commands/job.ts`) manages renet's
detached-job spool: work runs under a transient systemd unit on the machine, so it survives
a dropped SSH channel. Every verb requires `-m/--machine`; `status`, `logs` and `cancel`
also require `--id`. It exposes no `start` and no `run`.

**Keep it as a noun.** Tested against this file's principles: it is a real addressable
resource on the machine (an id, a state machine, logs, a lifecycle), and folding `job list`
into `machine jobs` would put one resource's CRUD on another resource's noun, which is
precisely what the reshape is undoing everywhere else (`config machine *` to `machine *`,
`machine backup *` to `backup *`). Principle 3 decides it. The noun deliberately has no
create verb, which is correct: a job is born as a side effect of another verb.

**But nothing can fill the spool.** The producer,
`LocalExecutorService.tryDetachedExecution()`, returns `null` immediately unless
`options.detached` is set, and **no CLI command sets it**
(`packages/cli/src/services/executor/local-executor.ts:1236`; the comment at :1225 says so
outright, and a grep across `commands/` and `services/serve/` confirms no caller passes it).

**OPERATOR RULING R-P4-2v2 (twice-ruled, MERGED): a job is EXECUTOR-BORN, plus a global
`--background`/`-b`.** The operator ruled this in two sessions (this suite's pass chose a
per-verb `--detach`; the parallel detached-jobs pass, better-informed on the Commander
positional-resolution hazard, chose a global `--background` with fire-and-forget semantics)
and confirmed the merge on 2026-07-13. Full contract and the verified findings behind it:
spec/03 §5.13 and `~/.claude/projects/-home-muhammed-monorepo-console/reports/handoff-detached-jobs.md`.

1. **The executor births jobs by itself, and keeps following.** When a *detachable* command
   arrives through `rdc serve` (from the web console or a `--proxy` thin client), the
   dispatch layer sets `ExecuteOptions.detached`. This is structural, not a convenience: the
   container tier is a warm Cloudflare Container that **sleeps after 2 to 5 minutes idle**,
   and you cannot know in advance which `repo up` takes 3 seconds and which takes 40 minutes.
   Client disconnect = detach, not cancel. The console's Jobs surface already handles the
   `kind:'job'` wire line that nothing emits yet.
2. **Direct CLI stays synchronous; the global `--background`/`-b` is fire-and-forget**: start
   the job, print its id and a resume hint, exit 0. Watch later with `rdc job logs`. Needs a
   no-follow mode that does not exist yet (today's detached path always tails to completion).

`rdc job start -- <cmd>` was **rejected**: it re-creates the `run` escape hatch and defeats
typed commands. The flag collision is resolved in §7.8 (`--no-wait`; "detach" leaves the flag
vocabulary entirely).

**Scope warning for P4:** the flag is the easy half. Before anything sets `detached`, two
verified silent-corruption bugs must land — the detached path discards stdout (breaking every
`parseCapturedJson` caller; the same fix repairs the ALREADY-BROKEN `--proxy cluster fork`,
bug #31) and bypasses license recovery + identity refresh. Then the dead reattach half
(`kind:'job'` emission, the `jobEvents` route, exactly-once line ordinals) makes the console's
Jobs page real. Contract: spec/03 §5.13.
