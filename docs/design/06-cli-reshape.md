# 06 — Full CLI Reshape: Command-by-Command Mapping

User decision 2026-07-10: the FULL reshape ships in this program (~150 → ~90 leaves), not
just the redesign-required verbs. No backward compatibility, no aliases, no deprecation
windows (sole operator, clean break).

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

## 1. The target tree (~90 leaves)

```
rdc config      init list show delete set clear recover prune edit reconcile
                field {get set unset rotate list}    audit {log tail verify}
                remote {enable disable status refresh}    ssh {set show remove}
rdc machine     add remove list status setup scan-keys health prune
                provision deprovision      (absorbs config machine + provider CRUD)
                provider {add remove list}
rdc datastore   create list status attach detach fork snapshot {create list} resize delete
rdc repo        create up down status list delete fork push pull migrate promote
                secret {get list set unset}    sync {upload download status}
                cat diff logs exec tunnel    replicate {status remove}
                commit branch checkout log merge gc
                resize expand trim policy {set get}
                admin {validate fsck ownership autostart {enable disable list}
                       template {list apply}  archive {list restore purge}}
rdc cluster     create scale join evict destroy status kubeconfig snapshot
                fork migrate rehearse
rdc backup      strategy {set remove list show}  schedule  run  status  cancel  list  restore
rdc storage     list create delete browse prune  import
rdc term        connect
rdc vscode      connect list cleanup check serve {status stop}
rdc ops         up down status ssh setup check
rdc subscription login logout status refresh
rdc doctor | credits | update | mcp serve | run (hidden)
```

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
- **MCP alignment gate (P4 closing step)**: the existing `mcp-coverage.test.ts` is
  registry-keyed and misses unregistered leaves — verified 2026-07-10: a tree-walking
  version found **56 drifted commands** with neither `mcp` nor `mcpExcludeReason`.
  After the reshape lands, apply the parked patch (strengthened tree-walk test + a
  starter classification; session scratchpad `parked/mcp-coverage-gate.patch`) and
  classify every leaf of the NEW tree. Deliberately deferred to post-reshape (user
  decision): classifying the old tree first would be throwaway work. The test runs under
  `check:test-cli`, already in the `npm run ci` chain — no new CI wiring needed.
