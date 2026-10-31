# PLAN: a plan that touches a deployable surface closes only on a live receipt from bench or hostinger

Status: approved -- operator answered the four questions 2026-10-27 (see Operator rulings); filed 2026-10-27 from the operator request of the same day ("For all the plans we need a rule on ci side that ticks 'tested on bench' rule ... Plus on hostinger maybe")
Depends-On: no-dep -- builds on gates and verbs that already landed (check:ci-plan-boxes, check:ci-plan-implementation, worklist.py --plan-tick); no open plan blocks it
Priority: P2 -- process rule; nothing is broken today, but live-only boxes currently live in carried reds (P-A1) with no typed evidence
Concurrency: parallel -- V1 first and alone. V2, V3 and V4 run in parallel after V1. V5 follows V1 and V4. V6 follows V3 and V5. V7 (migration) and V8 (pilot) run last and alone. V9 follows V6.
Owns: .ci/config/proof-tiers.json, .ci/rediacc_ci/proof/**, .ci/rediacc_ci/drills/vm_check_trigger.py (moved to proof/surfaces.py), .ci/rediacc_ci/drills/vm_check_receipt.py (moved to proof/vm_tier.py), .ci/rediacc_ci/drills/vm_check.py (imports, go_buildinfo move, schema 3 writer only), .ci/rediacc_ci/drills/backup_check_trigger.py (the import path only), .ci/rediacc_ci/release/local_gates.py (the vm-check gate imports only), .claude/rediacc_hooks/guards/block_vm_unverified_push.py (module names, schema 3, mutants), .claude/rediacc_hooks/guards/test-block_vm_unverified_push.py, .claude/rediacc_hooks/guards/block_backup_unverified_push.py (the import path only), .ci/rediacc_ci/ops/live_proof.py, .ci/scripts/quality/check_plan_live_proof.py, .ci/rediacc_ci/tests/test_proof_surfaces.py, .ci/rediacc_ci/tests/test_proof_receipt.py, .ci/rediacc_ci/tests/test_proof_vm_tier.py, .ci/rediacc_ci/tests/test_proof_live_tier.py, .ci/rediacc_ci/tests/test_drills_vm_check_trigger.py (moved), .ci/rediacc_ci/tests/test_drills_vm_check_receipt.py (moved), .ci/rediacc_ci/tests/test_drills_vm_check.py, .ci/rediacc_ci/tests/test_drills_backup_check_trigger.py, .ci/rediacc_ci/tests/test_release_local_gates.py, .ci/rediacc_ci/tests/test_ops_live_proof.py, .ci/rediacc_ci/tests/gates/test_gate_plan_live_proof.py, .ci/rediacc_ci/ops/deploy_bench.py (the version capture only), .ci/rediacc_ci/tests/test_ops_deploy_bench.py, .claude/hooks/stop/wl_plandeps.py (the Live-Proof grammar only), .claude/hooks/stop/test-plandeps.py, .claude/hooks/stop/worklist.py (the --live-proof verb only), .claude/hooks/stop/worklist_messages.py, .claude/rediacc_hooks/guards/block_plan_without_depends.py, .claude/rediacc_hooks/guards/test-block_plan_without_depends.py, agent/ledgers/live-proof.jsonl, package.json (one script line), scripts/ci-runner/manifest.ts (the check:ci-plan-live-proof entry only), scripts/ci-runner/gates.lock.json (regenerated), .github/workflows/ci-quality.yml (the Plan live proof step only), .ci/config/lane-durations.json (the new and renamed entries), .ci/config/shards/quality-pytest.json (the renamed entries), CLAUDE.md (the vm:check module names only), .claude/agents/ops-vms.md, .claude/agents/e2e-local.md, docs/agent-reference/ci-gates.md (the vm:check module names only), docs/agent-reference/plan-records.md, agent/plans/PLAN-*.md (V7 only: the Live-Proof header line and the LP boxes), .ci/config/plan-boxes.json
Live-Proof: none -- CI and agent tooling only, which Design item 2 excludes from every surface; ruling #11c34df3 (the operator request this plan answers, closed with the four answers)
Owner: d778be9d
First-Seen: 2026-10-27
Worklist: pending -- filed at promotion

**Request.** The operator asked on 2026-10-27 for a CI rule behind a "tested on bench" box, after the same day's work proved changes on edge first (the eu stable-to-edge config-store mirror and the `eu-edge` rdc config). Operator ruling of the same day: stable is CI/CD-only and needs an ASK, while edge and bench are free for agents. The plan first admitted bench, edge and hostinger; the operator ruling below narrows it to bench and hostinger, never edge or stable.

**Today's gap, measured.**
- 13 P-A1 keys are carried in `.ci/config/carried-reds.json`. Its reason says those plans' open boxes include "live or post-merge runs" (edge rollout, hostinger steps). No typed record exists for any of them. Each closes through a free-text `(ticked)` line that CI cannot re-derive.
- Live evidence does exist, but no gate ties it to a plan:
  - `deploy_record.py` writes version ids to R2 `release-records/v<V>/<channel>/`.
  - The vm:check receipt (`drills/vm_check_receipt.py`) binds a tree and an inputs digest, but runs on VMs, not live.
  - `deploy_bench.py` prints wrangler's version id and keeps nothing.
- The account Worker's `/health` (`private/account/src/app.ts:202`) reports no build or version identity. A live check therefore cannot learn which code it hit, and the receipt has to carry the version id from the deploy side.

## Design

**1. The receipt.** One JSON row per live run, appended to `agent/ledgers/live-proof.jsonl`. The file is committed, so CI judges it with no secrets and no network. Shape (schema 1):

    {"schema":1,"id":"lp-<12 hex of sha256(row without id)>","at":"<UTC ISO>","by":"<session prefix>",
     "plan":"agent/plans/PLAN-<name>.md","box":"<box sig>","target":"bench|hostinger","region":"eu|us|asia|null",
     "head":"<console commit>","tree":"<HEAD^{tree}>","dirty":false,
     "submodules":{"private/account":{"pointer":"<sha>","checkout":"<sha>","modified":false},"private/renet":{...}},
     "inputs":"<live-proof inputs digest, item 6>",
     "deploy":{"surface":"account|proxy|www|cli|renet","worker":"<name>|null","version_id":"<uuid>|<renet/cli version>",
               "source":"bench-cache|r2:release-records/...|rdc:eu-bench","deployed_head":"<sha>","confirmed_live":true},
     "check":{"id":"<registry id>","argv":["..."],"rc":0,"duration_s":41.2,"log_sha256":"<hex>","tail":["<=20 scrubbed lines"]},
     "status":"VERIFIED","tier":"live","surfaces":["..."],"renet":{"built":"<sha>","modified":false,"sha256":"<hex>"},"ladder":{"vm":"<vm run id>"}}

- The full log stays in `.ci/cache/live-proof/<id>.log`, which is gitignored. Only its sha256 is committed.
- Before writing, the recorder refuses any row that carries a secret value. It runs `deploy_record.refuse_secret_values` over the serialized row and the secret-shape scanner over the tail. Hostinger rows name the rdc config (`eu-bench`) and the machine alias, never an address.

**2. Which plans need it: one surface map, shared with vm:check.**
- `.ci/config/proof-tiers.json` is the only surface map. It is read only through `rediacc_ci.proof.surfaces`, the vm:check trigger moved there (Design item 6). Surface entries are console-relative globs in the Owns grammar. They are matched with `wl_planconc.glob_regex` for a changed path and with `wl_planconc.owns_overlap` for a plan's Owns, so the push guard, `release:local` and this gate cannot disagree about what a path touches.

  | Surface | Globs | Live targets | VM phase |
  |---|---|---|---|
  | renet | `private/renet/cmd/**`, `private/renet/pkg/**`, `private/renet/proxy/**`, `private/renet/build.sh`, `private/renet/go.mod`, `private/renet/go.sum`, `private/renet/embed-assets.lock.json` | hostinger | renet |
  | cli-remote | `packages/cli/src/remote/**`, `packages/cli/src/services/repo/repo-key-deployment.ts` | hostinger | renet |
  | cli | `packages/cli/src/**` | bench, hostinger | none |
  | account | `private/account/{src,web,drizzle,scripts}/**`, `private/account/{package.json,package-lock.json,tsconfig.json,wrangler*.toml,dev.defaults.env,docker-compose.yml,Dockerfile}`, `packages/shared/src/**` | bench | account |
  | account-worker | `workers/account/**` | bench | none |
  | proxy | `workers/proxy/src/**`, `workers/proxy/wrangler*.toml`, `workers/proxy/Dockerfile` | bench | none |
  | www | `packages/www/src/**`, `workers/www/**` | bench | none |

  - One exclude list serves both tiers: `**/*_test.go`, `**/*.test.ts`, `**/*.test.tsx`, `**/*.spec.ts`, `**/*.spec.tsx`, `**/__tests__/**`, `**/testdata/**`, `**/tests/**`, `**/e2e/**`, `**/*.md`.
  - `tiers.vm.instrument` lists the drill files whose change needs a new VM run but which are not deployable code, each with its phases. These are the 13 drill entries of today's `CONSOLE_PATHS`. The live tier has no instrument list.
  - The map widens vm:check on purpose. The renet phase gains `proxy/**` and `build.sh`: build.sh embeds `proxy/docker-compose.yml` into the binary through a gitignored copy, so a Traefik pin bump never triggered vm:check before. The account phase gains `packages/shared/src/**`, which `private/account/package.json` depends on, and `wrangler*.toml`.
- A path may hit several surfaces (a `packages/cli/src/remote/` file is both cli-remote and cli). A plan must cover each one.
- A plan is **required** when all of these hold:
  - it is a live plan: not a stub, not under `_done/` or `_removed/`, and its Status is not in `wl_planfile.FINISHED_STATES`;
  - its `Owns:` globs intersect at least one surface glob, minus the excludes.
- A bare submodule path (`private/renet`, `private/account`) claims the gitlink, not the code, so it is not a surface claim.
- Deploy tooling (`.ci/rediacc_ci/deploy/**`, `ops/deploy_bench.py`, `release/**`) and proof tooling (`.ci/rediacc_ci/proof/**`, the vm:check drills) are not surfaces.
- A required plan declares its proof in a header line inside the 12-line X window:
  - `Live-Proof: bench|hostinger[, <target>...] -- <reason>`, or
  - `Live-Proof: none -- <reason>`, which passes only under a resolvable ruling (ruling 2; LP2).
- Every touched surface must be covered by at least one declared target admissible for it. For example, a plan touching account and renet declares `bench, hostinger`.
- The VM tier does not substitute for the live tier, and the live tier does not substitute for the VM tier (ruling 1).

**3. The CI-side rule: a new gate, `ci-plan-live-proof`.** (Its npm script carries the `check:` prefix once V5 registers it; every `npm run ci-plan-live-proof` below is that script.)
- It is a separate gate rather than an extension. `check_plan_implementation.py` is already 2494 lines and owns the clock, and the house shape is one concern per gate.
- It reads `.ci/config/plan-boxes.json` (proven equal to the tree by G-A0) and `agent/ledgers/live-proof.jsonl`, and it never re-parses boxes.
- Lane `quality-branch`, `selftest: true`, control-first with one plant per rule (the `check_hint_corpus.py` and `check_plan_implementation.py` shape).
- The rules:
  - **LP1** A required plan has no `Live-Proof:` line, or the line is malformed, emphasized, duplicated or outside the window. The grammar lives in `wl_plandeps` beside Depends-On, so the pre-edit guard and the gate share one parser.
  - **LP2** A declared target is not admissible for a touched surface, or a touched surface is left uncovered. `none` on a required plan passes only under a resolvable waiver (see Question 2), resolved through `wl_planfile.resolve_ruling`.
  - **LP3** A required plan that declares targets lacks one `LP-<target> [live]` box per target. Each such box must carry an `Accept: live-proof <target> <check-id> [args]` sub-line.
  - **LP4** An `LP-<target>` box moved from open to done on this branch with no receipt row matching all of the following: plan, box sig, target, `status: VERIFIED`, `check.rc == 0`, `dirty: false`, and the Accept line's check id and arguments.
  - **LP5** A matching receipt is invalid. Any one of these makes it invalid:
    - its `head` is not an ancestor of the commit that ticked the box (judged through the rebase successor map, the way P-A4 judges, via `make_successor_of`);
    - `tree` or `head` does not resolve;
    - the `inputs` digest recomputed at `head` differs from the digest at the ticking commit, meaning surface code changed after the proof;
    - `deploy.deployed_head` differs from `head`;
    - `deploy.confirmed_live` is false for any target;
    - the version id is malformed;
    - the schema is unknown;
    - the `id` does not hash to the row;
    - the secret-shape scan hits.
  - **LP6** A required plan reaches a finished Status or `_done/` on this branch without a valid receipt per declared target. This is the backstop for a G-A3 `Ruling:` that finishes a plan over an open LP box, unless that Ruling names the live-proof waiver itself.
  - **LP7** Vacuity:
    - the surface map is empty or unparsable;
    - zero required plans are derived from a corpus whose Owns plainly hit surface paths;
    - a check id named in an Accept line is absent from the registry.

    Zero parsed plans is CANNOT RUN (exit 77), never green.
- **Advisory lines, printed every run, red or green:** every `Live-Proof: none` on a required plan.
- **Forward-only.** LP4 to LP6 judge only transitions in commits dated strictly after `baseline_at` in `.ci/config/live-proof.json`, the device P-A2 uses. On the landing commit the gate is silent on transitions by construction. LP1 to LP3 judge every live required plan from V6 on.
- **No allowlist and no suppression** (`docs/agent-reference/suppressions.md`). The waiver is a named operator ruling, never a config entry.

**4. How the receipt is produced.**
- **Engine.** The live tier lives in `rediacc_ci.proof.live_tier`: row body, ledger read, match and validation, shared with the gate. Its envelope and identity judge come from `rediacc_ci.proof.receipt`, the same ones the VM tier uses. The command line is `rediacc_ci.ops.live_proof`:

      PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof record --plan <rel> --box <sig> --target bench|hostinger [--region eu] --check <id> [--write]
      PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof verify [--plan <rel>]     # the gate's LP5 over the ledger, locally

  There is no `--retro` (ruling 3). A dry run is the default; `--write` appends a VERIFIED row only. A FAILED or NOT_VERIFIED run keeps its log in `.ci/cache/live-proof/` and writes nothing to the ledger.
- **Check registry.** `tiers.live.checks` in `proof-tiers.json` maps an id to a fixed argv, its targets and the surfaces it covers.
  - The only parameters are values the registry itself names, such as a machine alias from `tiers.live.targets.hostinger.machines`.
  - There are no free arguments, no generic `rdc` or `npm` entry, and no allowlist.
  - A plan that needs a behaviour-specific check adds a named entry in its own Owns.
  - Initial entries:
    - `account-smoke` (bench; account, account-worker): `/health` and `.well-known/server-info` on `bench.rediacc.com`.
    - `proxy-ready` (bench; proxy): `rediacc_ci.deploy.deploy_proxy --smoke-only` against bench.
    - `www-smoke` (bench; www): the bench www root answers 200. V5 names the URL; LP7 refuses a surface with no check.
    - `cli-bench` (bench; cli): `./rdc.sh --config eu-bench subscription status`.
    - `renet-live` (hostinger; renet, cli-remote, cli), for each alias in `tiers.live.targets.hostinger.machines`:
      1. `surfaces.renet_identity()`, the P1 rule moved out of vm_check: `go version -m private/renet/bin/renet` carries the renet pointer as `vcs.revision` with `vcs.modified=false`, after one `./rdc.sh --version` rebuild. The sha256 of `bin/renet` is recorded.
      2. `./rdc.sh --config eu-bench machine status <alias> -o json`: rc 0 and `stale_binary == []`. This call provisions the tree's binary when the hashes differ.
      3. `./rdc.sh --config eu-bench term connect <alias> -c "/usr/lib/rediacc/renet/current/renet hash"` must equal that sha256. That sets `deploy.confirmed_live`, with `deploy.version_id = "renet:<vcs.revision>@sha256:<64 hex>"`.
      4. A version guard refusing the upload, or any later hash mismatch, is a named refusal `not-live`, never a pass.
- **Deploy identity, read and confirmed live (not believed).**
  - **bench:** V4 makes `deploy_bench` parse wrangler's version id and write `.ci/cache/live-deploys/bench.json` with `{version_id, head, tree, dirty, submodules, at}`. The recorder reads that file. Under the `deploy-bench` Bitwarden profile it then confirms through `wrangler deployments status` that this version serves 100% at check time.
  - **hostinger:** confirmed by `renet-live` steps 1 to 3. The machine runs the binary built from `head`'s renet pointer, byte for byte. `renet version` alone is a semver and proves nothing.
- **Tier ladder.** For any surface with a VM phase (renet, cli-remote, account), the recorder first calls `proof.vm_tier.admit(root, tree, surfaces.inputs(root, tree, tier="vm"), phases)`. It refuses unless the VM tier admits the head tree, and it records `ladder.vm` (the VM run id) in the row. No branch build reaches bench or hostinger before it passes on the ops VMs. CI cannot read the VM cache, so this is a recorder refusal, not a gate rule.
- **Refusals.** The recorder refuses all of these through `proof.receipt.identity_refusal`, the same judge the push guard applies:
  - a dirty tree on surface paths;
  - a submodule checkout that is not its pointer, or is modified;
  - a renet build that is not the pointer, or is modified;
  - a deploy whose `deployed_head` differs from HEAD;
  - a live version that no longer matches the deploy record.

  The codes are the shared `Verdict` vocabulary: `build-mismatch`, `modified-build`, `checkout-mismatch`, `modified-checkout`, `not-live`.
- **Secrets.** `deploy_record.refuse_secret_values` runs over the serialized row and the secret-shape scanner over the tail. Hostinger rows name the rdc config (`eu-bench`) and the machine alias, never an address.
- **Agent verb.** `worklist.py --live-proof <me> <plan> <LP-box-sig> [--tick] [--write]` reads the box's Accept line, delegates to the engine and, with `--tick`, closes the box through `wl_planrec.plan_tick` in the same run. Its evidence line is `live-proof <id> <target> <check> rc=0 v=<version>`. It writes the ledger and `plan-boxes.json` together, so the tick and the receipt land in one commit.
- **R2 mirror.** Not in scope; the committed ledger is the system of record.

**5. Interplay with existing gates.**
- An LP box is an ordinary open box. P-A1 counts it, and bench is free for agents, and a hostinger run needs the V8 confirmation; either closes pre-merge.
- The live boxes that today ride in the carried reds become LP boxes with a typed exit, which shrinks the carry instead of growing it.
- P-A2 and P-A4 still apply to LP boxes: an investigation row first (`--plan-investigate`), then the receipt, then the tick.

**6. One proof family: surfaces, digest, receipt envelope, judges.**
- **Module layout.** It is a clean break: the old paths are deleted, with no re-export shim.
  - `rediacc_ci/proof/surfaces.py` is `drills/vm_check_trigger.py`, moved. It holds the `proof-tiers.json` loader, glob matching, `changed_paths` (now returning `Changed.surfaces`, with VM phases derived through `tiers.vm.phases`), `push_base`, the submodule range, the inputs digest, `account_worktree_digest`, and `go_buildinfo` plus `renet_identity`, moved from `drills/vm_check.py`.
  - `rediacc_ci/proof/receipt.py` holds the envelope, the status vocabulary, `Verdict`, `identity(root, surfaces)` (captures the envelope), `identity_refusal(receipt, surfaces)`, `row_id` and the atomic writer.
  - `rediacc_ci/proof/vm_tier.py` is `drills/vm_check_receipt.py`, moved, at schema 3.
  - `rediacc_ci/proof/live_tier.py` is new.
  - `backup_check_trigger.py` keeps its own tables and imports the git arithmetic from `proof.surfaces`.
- **The envelope**, shared by both tiers: `tier` (`vm` or `live`), `schema`, `status` (VERIFIED, FAILED or NOT_VERIFIED), `tree`, `head`, `dirty`, `inputs`, `surfaces`, `submodules` (`{"private/renet": {pointer, checkout, modified}, "private/account": {...}}`) and `renet` (`{built, modified, sha256}`, null when no touched surface needs renet).
  - The VM body adds `phases`, `fleet`, `forks`, `steps`, `teardown`, `runId`, `gateway`, `runDir` and the timings. Its old top-level `account` and `renet` blocks fold into `submodules` and `renet`.
  - The live body adds `id`, `at`, `by`, `plan`, `box`, `target`, `region`, `deploy`, `check` and `ladder`.
  - Storage stays per tier. VM receipts stay in the gitignored `.ci/cache/vm-check/`, keyed by tree, because they carry VM addresses and logs and are judged locally. Live rows go to the committed `agent/ledgers/live-proof.jsonl`, because CI judges them with no secrets and no network.
- **One inputs digest**, `surfaces.inputs(root, tree, surfaces, instrument=())`, version `v3`:
  1. a `v3` line;
  2. the sorted `git ls-tree -r` blob lines of the console paths in the given surfaces and instrument globs, excludes applied (the full tree listed, then filtered in Python, so the glob grammar is the map's own);
  3. the gitlink pointer of each submodule a given surface lives in, sorted.

  The VM tier passes `tiers.vm` (its phases' surfaces plus its instrument). The live tier passes the plan's touched surfaces. A worktree twin hashes worktree blobs and submodule HEADs, as v2 did. Submodules are covered by pointer, which is coarse on purpose, because CI cannot rely on submodule objects. A v2 digest never equals a v3 one.
- **One judge family.** Every judge uses `receipt.identity_refusal` for the build and checkout rules and reports through the shared `Verdict` codes:
  - the push guard `block_vm_unverified_push` and the `release:local` vm-check gate judge the VM tier through `vm_tier.admit`;
  - `ci-plan-live-proof` (item 3) judges the live tier.

  The live tier has no push guard, because its point of admission is the plan tick, which CI sees. `release:local` gets no live gate: a release cut from `main` already carries the green `ci-plan-live-proof`.
- **Staleness.** It is judged only at the ticking commit: the live-tier digest recomputed at `head` must equal the digest at the ticking commit, never at HEAD, so a commit after the tick never reopens a closed plan.

**7. Migration.**
- **Exempt, never judged:** everything in `_done/` and `_removed/`, compacted records, and stubs. Also every live plan whose Owns hit no surface (census of 2026-10-27, for example):
  - lessons-registry-followups
  - agent-tree-lifecycle
  - ci-quick-cpu-scheduling
  - cloudflare-spend-guard
  - deletion-budget
  - local-release
  - pin-awscli-toolchain-python-compatible
  - plan-* and stop-hook-*
  - haiku-model-routing
  - w7p5a-real-run-dispatch
  - retired-terms-submodule-scan
- **Pointer-only Owns, which become exempt by rule (item 2):** retire-bash-oracles.A0 and submodule-branch-coordination-guard.
- **Required, with open boxes; they gain the header and the LP boxes in V6:**
  - config-server-key (account; edge already exercised today)
  - console-executor-multi-org, telemetry-export, config-sync-hardening, token-ip-rebind (account)
  - cloudflare-proxy, executor-durable-object-policy, proxy-cd-six-targets (proxy plus account)
  - backup-program (account, cli, renet, www)
  - config-networkid-discovery (cli plus renet)
  - sync-remote-file-ownership (cli)
  - renet-runtime-converge, sandbox-tenant-separation, gpu-device-grants, hostinger-upgrade-followups, backup-toc-exact-opt-in (renet)
- **Required, zero open boxes, not yet finished:** converge-preflight-and-repo-recovery, renet-fetch-retries, renet-bridge-leftovers, backup-presign-bucket-require-and-wrangler-vars, renet-run-docker-sock-isolation (a write-up only; expected to get `none` under a ruling). V7 adds the LP boxes. Each then needs a fresh run (ruling 3).

## Tasks

- [x] V1 [writer] The proof package core.
  - `.ci/config/proof-tiers.json` holds `surfaces` (the item 2 table), `exclude`, `tiers.vm` (`phases`, `instrument`), and `tiers.live` (`baseline_at` unset until V6, `targets` with `hostinger.config: eu-bench` and `hostinger.machines`, `checks`, `pointer_only`).
  - `git mv` `drills/vm_check_trigger.py` to `proof/surfaces.py` and replace its constant tables with the loader. It gains glob matching through `wl_planconc.glob_regex` (with the `paths.on_sys_path(paths.hooks_stop_dir())` hop `.ci/scripts/quality/check_plan_deps.py:113` uses), `Changed.surfaces`, digest `v3` taking a surface set, and `go_buildinfo` plus `renet_identity` moved from `.ci/rediacc_ci/drills/vm_check.py:687`.
  - New `proof/receipt.py` holds the envelope, `Verdict`, `identity`, `identity_refusal` and `row_id`.
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_proof_surfaces.py .ci/rediacc_ci/tests/test_proof_receipt.py -q` rc=0. The cases are the moved trigger tests plus these new ones:
    - `private/renet/proxy/docker-compose.yml` and `private/renet/build.sh` hit renet (each fails against today's `RENET_PATHS`);
    - `packages/shared/src/x.ts` hits account;
    - a test file and a `.md` hit nothing;
    - glob parity with `owns_overlap` over the item 7 census Owns;
    - a v3 digest of a tree differs from its v2 digest;
    - a live-tier digest for `{account}` does not move when only the renet pointer moves;
    - one negative case per `identity_refusal` code.
    (ticked) 2026-10-28T05:15:08Z by d778be9d: 2026-10-28 by d778be9d: commit:ba86b0dec; pytest test_proof_surfaces.py test_proof_receipt.py rc=0 (220 passed, with the renet compose and build.sh hits, shared to account, test/.md to nothing, owns_overlap parity, v3 vs v2 digest, account digest stable on a renet pointer move, one negative per identity_refusal code); importers, guard test (97 cases) and 574-test rerun rc=0
- [x] V2 [writer] Move the VM tier onto the family.
  - `git mv` `drills/vm_check_receipt.py` to `proof/vm_tier.py`, at schema 3 (envelope plus VM body; schema 2 is unread, the same clean break as before).
  - Then update every importer in the same commit: `drills/vm_check.py`, `drills/backup_check_trigger.py`, `release/local_gates.py`, `block_vm_unverified_push.py` (`TRIGGER_MOD`, `RECEIPT_MOD` and the mutant source lines), `block_backup_unverified_push.py`, the moved tests, `quality-pytest.json`, `lane-durations.json`, and the module names in CLAUDE.md, ops-vms.md, e2e-local.md and ci-gates.md.
  - Accept:
    - `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_proof_vm_tier.py .ci/rediacc_ci/tests/test_drills_vm_check.py .ci/rediacc_ci/tests/test_drills_backup_check_trigger.py .ci/rediacc_ci/tests/test_release_local_gates.py -q` rc=0;
    - `python3 .claude/rediacc_hooks/guards/test-block_vm_unverified_push.py` rc=0 and `python3 .claude/rediacc_hooks/guards/test-block_backup_unverified_push.py` rc=0, with every mutant still caught;
    - `grep -rn "vm_check_trigger\|vm_check_receipt" .ci .claude CLAUDE.md docs --include=*.py --include=*.md --include=*.json` prints nothing outside `agent/`;
    - `npm run vm:check` exit 0, writing a `tier: vm`, schema 3 `receipt.json`.
    (ticked) 2026-10-28T06:16:24Z by d778be9d: 2026-10-28 by d778be9d: commit:efed615f0; pytest test_proof_vm_tier.py test_drills_vm_check.py test_drills_backup_check_trigger.py test_release_local_gates.py rc=0 (774 with the proof and drill tests); test-block_vm_unverified_push.py rc=0 (98 cases) and test-block_backup_unverified_push.py rc=0; the vm_check_trigger/vm_check_receipt grep prints nothing outside .ci/cache; npm run vm:check exit 0, VERIFIED, 175 assertions 0 failed, receipt tier vm schema 3 (tree bf6f6c5c2b1e)
    (review note 2026-10-29, 9f92c43e) The tick says the grep prints nothing "outside .ci/cache", narrower than the Accept's "outside agent/". Rerun 2026-10-29 of `grep -rn "vm_check_trigger\|vm_check_receipt" .ci .claude CLAUDE.md docs --include=*.py --include=*.md --include=*.json`: no hit outside agent/ and outside other checkouts under .claude/worktrees (whose copies of agent/reviews carry the names).
- [x] V3 [writer] The `Live-Proof:` grammar in `wl_plandeps`, with the X-field shape and the 12-line window. A `none -- <reason>` line must cite a closed worklist item or a committed operator quote (ruling 2). The pre-edit guard `block_plan_without_depends.py` refuses a new plan whose Owns hit a surface in `proof-tiers.json` and that carries no Live-Proof line.
  - Accept: `python3 .claude/hooks/stop/test-plandeps.py` rc=0 and `python3 .claude/rediacc_hooks/guards/test-block_plan_without_depends.py` rc=0, with cases for a missing, malformed, emphasized, out-of-window and rulingless-`none` line.
    (ticked) 2026-10-28T05:33:18Z by d778be9d: 2026-10-28 by d778be9d: commit:c06e530bc; python3 .claude/hooks/stop/test-plandeps.py rc=0 (319 controls, with missing, malformed, emphasized, out-of-window and rulingless-none cases) and python3 .claude/rediacc_hooks/guards/test-block_plan_without_depends.py rc=0 (87 cases, 0 failures); check_plan_deps.py rc=0
- [x] V4 [writer] Bench version capture. `deploy_bench` parses `Current Version ID:` and writes `.ci/cache/live-deploys/bench.json` from `proof.receipt.identity`. An unparsed id is a named DeployError after the deploy.
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ops_deploy_bench.py -q` rc=0, with a test that fails on today's code (no cache file written).
    (ticked) 2026-10-28T05:24:27Z by d778be9d: 2026-10-28 by d778be9d: commit:542327a4f + commit:765bd0b02; pytest test_ops_deploy_bench.py rc=0 (25 passed: parsed id, missing id is a named DeployError writing nothing, overwrite, live version wins); live deploy_bench rc=0 twice, second writes bench.json version_id 6b822ba9 (the 100% version deploy_record reads) with deployed_version_id 335ce034
- [x] V5 [writer] The live tier and recorder: `proof/live_tier.py` and `ops/live_proof.py` (`record`, `verify`; no `--retro`).
  - The registry has fixed argv only (no `rdc` or `npm` passthrough), with the item 4 entries including `renet-live`.
  - The recorder confirms bench through wrangler and hostinger through the hash, applies the tier ladder via `vm_tier.admit`, and refuses secrets. It writes VERIFIED rows only.
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_proof_live_tier.py .ci/rediacc_ci/tests/test_ops_live_proof.py -q` rc=0, with recording fakes for wrangler, curl, `go version -m` and rdc. Cases:
    - a dirty tree refuses;
    - a moved bench version refuses;
    - a remote `renet hash` that differs from the local sha256 refuses `not-live`;
    - a non-empty `stale_binary` refuses;
    - a `bin/renet` with `vcs.modified=true` refuses `modified-build`;
    - a renet run with no admitting VM receipt refuses (ladder);
    - a check id or machine alias outside the registry refuses;
    - a planted secret in the tail refuses;
    - the row id round-trips.
    (ticked) 2026-10-28T09:31:52Z by d778be9d: 2026-10-28 by d778be9d: commit:e0fe73d77; pytest test_proof_live_tier, test_ops_live_proof, test_proof_surfaces, test_proof_receipt, test_proof_vm_tier rc=0 (420 passed); 14 judges each broken once turned a test red; env reads registered in d9cfe934e
- [x] V6 [writer] The gate `.ci/scripts/quality/check_plan_live_proof.py`.
  - Rules LP1 to LP7, with every edge reference removed. LP7 also fires on a surface with an admissible target but no registry check.
  - The advisory line for `Live-Proof: none`, the gate metadata (`lane: quality-branch`, `selftest: true`), the `package.json` script `ci-plan-live-proof` and a lane-durations entry. Set `baseline_at` to the landing date.
  - Accept: `npm run check:ci-plan-live-proof -- --selftest` rc=0 (every plant caught, healthy fixture silent), and `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/gates/test_gate_plan_live_proof.py -q` rc=0.
    (ticked) 2026-10-28T15:36:55Z by d778be9d: V6 gate in commit d7afa95d1: check_plan_live_proof.py --selftest rc=0 (82 controls), test_gate_plan_live_proof.py in a 261-passed pytest run rc=0, baseline_at 2026-10-28, wired in ci-quality.yml quality-branch
    (review note 2026-10-29, 9f92c43e) The Accept named `npm run ci-plan-live-proof`; the package.json script is `check:ci-plan-live-proof` (V5 registers it under that name), and the Accept lines now say so. The tick ran `check_plan_live_proof.py --selftest`, the script that npm entry runs. Rerun 2026-10-29: `npm run check:ci-plan-live-proof -- --selftest` rc=0.
- [x] V7 [lead] Migration.
  - Add the `Live-Proof:` line and the `LP-<target> [live]` boxes (with Accept sub-lines) to every required live plan. Re-run the item 7 census against the widened map first: renet now includes `proxy/**`, and account includes `packages/shared/src/**`.
  - Each `none` needs a ruling (ruling 2). Each zero-open-box plan gets a fresh-run LP box (ruling 3). Then regenerate `plan-boxes.json`.
  - Accept: `npm run check:ci-plan-live-proof` rc=0 with zero LP1 to LP3 findings, `npm run check:ci-plan-boxes` rc=0, `npm run check:ci-plan-deps` rc=0.
    (ticked) 2026-10-28T15:37:00Z by d778be9d: V7 migration in commit d7afa95d1: 27 plans carry Live-Proof lines and 35 LP boxes; npm run check:ci-plan-live-proof rc=0 (28 required plans judged, no finding, 0 PENDING)
    (review note 2026-10-29, 9f92c43e) The tick records `check:ci-plan-live-proof` only. Rerun 2026-10-29: `npm run check:ci-plan-boxes` rc=0 and `npm run check:ci-plan-deps` rc=0. `npm run check:ci-plan-live-proof` itself exits 1 on the current tree with LP1 to LP3 findings on plans added since (for example PLAN-snapshot-read-io-cap, PLAN-backup-download-from-store, PLAN-backup-meter-orphaned-chunks), so the V7 zero-finding Accept holds for the migration commit, not for today's tree.
- [ ] V8 [lead] Pilot: one real receipt on each target. Before running, ASK the operator to confirm a branch renet may be provisioned on hostinger (this restarts the router and daemons).
  - bench: PLAN-config-server-key's LP-bench box after its K3, with `worklist.py --live-proof <me> agent/plans/PLAN-config-server-key.md <LP-bench sig> --tick --write`.
  - hostinger: one renet-surface plan's LP-hostinger box through `renet-live` on `--config eu-bench`; candidate PLAN-hostinger-upgrade-followups T1, whose Traefik pin is renet-embedded. Run it after a VERIFIED `npm run vm:check -- --changed` on the same tree.
  - Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof verify --plan agent/plans/PLAN-config-server-key.md` rc=0 and `PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof verify --plan agent/plans/PLAN-hostinger-upgrade-followups.md` rc=0. Also `npm run ci-plan-live-proof` rc=0 on each ticking commit.
- [ ] V9 [writer] Docs.
  - A "Live proof" section in `docs/agent-reference/plan-records.md`: the header, the LP box form, the verb, the envelope and live body, the ladder and the LP rules.
  - A "Proof tiers" paragraph in `docs/agent-reference/ci-gates.md`: one map, the VM and live tiers, and which judge reads which.
  - Accept: `npm run check:ci-plan-citations` rc=0 and the docs lint lane rc=0.
- [x] V10 [writer] Ledger integrity (review findings 2a2941c4.1 and 2a2941c4.5). CI judges `agent/ledgers/live-proof.jsonl` with no secrets and no network, and LP5 checks only that a row's `id` hashes to its content, so a hand-written row with a recomputed id and `verdict: PASS` would pass the gate. A pre-edit and pre-bash guard refuses any write to that ledger except the append `python3 -m rediacc_ci.ops.live_proof record --write` makes, and the recorder stamps each row with the run's log digest that `verify` re-reads from `.ci/cache/live-proof/` when present. An `LP-<target>` or `LP-none` box tick names the V6 gate's pass on the same tree.
  - Accept: the guard's `test-*.py` rc=0 with a planted hand-appended row refused and a recorder append allowed; `pytest -q .ci/rediacc_ci/tests/test_ops_live_proof.py` rc=0 with a row whose log digest mismatches refused by `verify`.
    (ticked) 2026-10-28T14:59:29Z by d778be9d: V10: ledger guards in commit b8470a0b2; test-block_live_proof_ledger_write.py rc=0 (FAILURES 0), the shell-write guard test rc=0, test_ops_live_proof.py 37 passed including the log-digest mismatch refused by verify
- [ ] LP-none: this plan carries `Live-Proof: none` because its Owns hit no deployable surface (proof tooling is excluded by item 2). V8 exercises the tooling end to end on both targets.
  - Accept: `npm run check:ci-plan-live-proof` rc=0 on the commit that ticks V8.

### Tasks of the first draft (superseded by the revision above)

Kept byte for byte because a box is a durable record. Each closes, ticked with its evidence line, when the revised task that replaces it lands: first-draft V1 with revised V1, V2 with V3, V3 with V4, V4 with V5, V5 with V6, V6 with V7, V7 with V8, V8 with V9, and the first-draft LP-none with the revised LP-none.

- [x] V1 [writer] Engine core and config.
  - `.ci/config/live-proof.json`: `baseline_at` (unset until V5), `surfaces`, `checks`, `pointer_only`.
  - `rediacc_ci/quality/live_proof.py`, as pure functions:
    - `required(plan_header, owns) -> surfaces`
    - `parse_header`, which delegates to `wl_plandeps`
    - `admissible(surfaces, targets)`
    - `inputs_digest(root, commit, owns, surfaces)`
    - `row_id(row)`
    - `validate_row(row) -> problems`
    - `match(row, plan, sig, accept)`
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_quality_live_proof.py -q` rc=0. It covers the census rows above (required, exempt, pointer-only) and one negative test per `validate_row` problem.
    (ticked) 2026-10-28T05:15:12Z by d778be9d: 2026-10-28 by d778be9d: superseded first-draft box, closed with revised V1 (sig 76643438) as the plan's first-draft note orders; commit:7af3442fc
- [x] V2 [writer] The `Live-Proof:` grammar in `wl_plandeps`. It has the X-field shape and the 12-line window, and its `none -- <reason>` reason needs at least 12 characters. The pre-edit guard `block_plan_without_depends.py` refuses a new plan whose Owns hit a surface and that carries no Live-Proof line.
  - Accept: `python3 .claude/hooks/stop/test-plandeps.py` rc=0 and `python3 .claude/rediacc_hooks/guards/test-block_plan_without_depends.py` rc=0, with new cases for a missing, malformed, emphasized and out-of-window line.
    (ticked) 2026-10-28T05:33:31Z by d778be9d: 2026-10-28 by d778be9d: superseded first-draft box, closed with revised V3 (sig 38efe1b5) as the plan's first-draft note orders; commit:c06e530bc
- [x] V3 [writer] Bench version capture. `deploy_bench` parses `Current Version ID:` from the wrangler deploy output and writes `.ci/cache/live-deploys/bench.json` with `{version_id, head, tree, dirty, submodules, at}` and no secret values. An unparsed version id is a named DeployError after the deploy, never a silent skip.
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ops_deploy_bench.py -q` rc=0, with a test that fails on today's code (no cache file written).
    (ticked) 2026-10-28T05:24:30Z by d778be9d: 2026-10-28 by d778be9d: superseded first-draft box, closed with revised V4 (sig 9262ee30) as the plan's first-draft note orders; commit:765bd0b02
- [x] V4 [writer] The recorder `rediacc_ci.ops.live_proof`: `record`, `verify`, and `record --retro`; check-registry argv expansion; live version confirmation for bench and edge; hostinger `renet version` via `./rdc.sh`; and the secret refusal. Dry run is the default and `--write` appends.
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ops_live_proof.py -q` rc=0, with recording fakes for wrangler, curl and rdc. Cases:
    - a dirty tree refuses
    - a moved live version refuses
    - a planted secret in the tail refuses
    - `true` as a check refuses
    - the row id round-trips
    (ticked) 2026-10-28T14:59:04Z by d778be9d: superseded first-draft V4, closed with revised V5 (c5b50ba5, commit b8f513f40); test_ops_live_proof.py 37 passed: dirty tree, moved bench version, planted secret refuse
    (review note 2026-10-29, 9f92c43e) The "revised V5 (c5b50ba5)" in the tick is the revised plan's V5, "The live tier and recorder" (the same commit e0fe73d77), which is ticked above in this file; c5b50ba5 is a stale signature label and no longer matches any box (that box is signed 24fba445).
- [x] V5 [writer] The gate `.ci/scripts/quality/check_plan_live_proof.py` (LP1 to LP7, the advisory lines, the gate metadata block with `lane: quality-branch` and `selftest: true`), its `package.json` script `check:ci-plan-live-proof`, and a lane-durations entry. Set `baseline_at` to the landing date.
  - Accept: `npm run check:ci-plan-live-proof -- --selftest` rc=0 (every plant caught, healthy fixture silent). `npm run check:ci-plan-live-proof` rc=0 on the landing tree, where it reports LP1 findings for the V6 set as expected until V6 lands in the same PR. `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/gates/test_gate_plan_live_proof.py -q` rc=0.
    (ticked) 2026-10-28T15:36:58Z by d778be9d: superseded first-draft V5 gate, closed with the revised V6 (b80617d6) in commit d7afa95d1; check:ci-plan-live-proof rc=0
- [x] V6 [lead] Migration. Add the `Live-Proof:` line and the `LP-<target> [live]` boxes (with Accept sub-lines) to every required live plan listed in Design item 7, then regenerate `plan-boxes.json`. Any `none` gets the waiver Question 2 settles. Retro rows only as Question 3 allows.
  - Accept: `npm run check:ci-plan-live-proof` rc=0 with zero LP1 to LP3 findings; `npm run check:ci-plan-boxes` rc=0; `npm run check:ci-plan-deps` rc=0.
    (ticked) 2026-10-28T15:37:03Z by d778be9d: superseded first-draft V6 migration, closed with the revised V7 (7acacf6d) in commit d7afa95d1; check:ci-plan-live-proof rc=0
- [ ] V7 [lead] Pilot: one real receipt end to end on bench and one on hostinger through `--config eu-bench`. Candidate: PLAN-config-server-key's live box, after its K3 provisioning. Run `worklist.py --live-proof <me> agent/plans/PLAN-config-server-key.md <LP-bench sig> --tick --write`.
  - Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof verify --plan agent/plans/PLAN-config-server-key.md` rc=0, and `npm run ci-plan-live-proof` rc=0 on the commit that ticks it.
- [ ] V8 [writer] Docs: a "Live proof" section in `docs/agent-reference/plan-records.md` covering the header, the LP box form, the verb, the receipt schema and the LP rules.
  - Accept: `npm run check:ci-plan-citations` rc=0 and the docs lint lane rc=0.
- [ ] LP-none: this plan carries `Live-Proof: none` because its Owns hit no deployable surface. V7 is its live exercise.

## Operator rulings 2026-10-27 (answers to the questions below)

1. Renet and every surface: the ruling to go with bench only, not edge, with the subscription command called after the EU config is copied to bench. The live targets are bench (account, proxy, www, cli) and hostinger reached through the `eu-bench` rdc config (cli, renet), the EU stable store mirrored to bench. Edge is not a live-proof target; vm:check does not substitute. Every edge reference above is superseded by this ruling. Confirmed ASKED:2026-10-27T14:33Z: "Yes, bench + hostinger via eu-bench".
2. Opt-out: only with a ruling. `Live-Proof: none` passes only when it cites a closed worklist item or a committed operator quote.
3. Backfill: fresh runs for all. No `--retro` receipts; the four closed plans each get a new live run, and V4 drops `record --retro`.
4. Enforcement: LP1 to LP6 fail CI from the landing commit; forward-only judging keeps existing work green.

5. Renet and consolidation, operator 2026-10-27: "we might also need bench test for @private/renet as well! We already had "ops" related testing enforcement. Maybe we can related similar code or consolidate". Design items 2, 4 and 6 and the task list were revised the same day: one surface map (`.ci/config/proof-tiers.json`) shared with vm:check, one inputs digest (v3), one receipt envelope with a VM tier and a live tier, one judge family, and a ladder (no live run without an admitting VM receipt). V8's hostinger pilot asks the operator first, because provisioning a branch renet restarts the router and daemons on a production machine.

## Questions for the operator (answered above)

1. **Renet proof target.** Renet cannot run on bench or edge. Is a hostinger run (`./rdc.sh --config eu-edge`, moved to `eu-bench` by ruling 1) mandatory for every renet-surface plan, or does a VERIFIED vm:check receipt for the same tree substitute?
   Recommended default: hostinger is mandatory, and vm:check does not substitute, because it is a pre-push VM run, not a live one.
2. **The `none` waiver.** May a plan whose Owns touch a deployable surface opt out with `Live-Proof: none -- <reason>` alone, or only under a resolvable operator ruling (a closed worklist item or a committed operator quote)?
   Recommended default: only under a resolvable ruling. A reason-only `none` is a silent bypass that the suppressions policy forbids.
3. **Backfill for plans whose implementation boxes are already closed** (converge-preflight-and-repo-recovery, renet-fetch-retries, renet-bridge-leftovers, backup-presign-bucket-require-and-wrangler-vars). Fresh live run, or a `--retro` receipt citing existing evidence (an R2 deploy record, a hostinger session in `agent/reviews`)?
   Recommended default: a retro receipt is allowed for these four only, printed as ADVISORY on every run. Every plan with open boxes needs a fresh run.
4. **Enforcement mode at landing.** Red from day one for LP4 to LP6 (forward-only, so nothing existing reds), or advisory first, as the 2026-10-23 ruling "Lean first, enforcement warns" set for P-A9?
   Recommended default: red for LP1 to LP6 from the landing commit. The request asks for a rule that gates the tick, and the forward-only cut already keeps existing work green.
