# PLAN: a plan that touches a deployable surface closes only on a live receipt from bench or hostinger

Status: approved -- operator answered the four questions 2026-10-27 (see Operator rulings); filed 2026-10-27 from the operator request of the same day ("For all the plans we need a rule on ci side that ticks 'tested on bench' rule ... Plus on hostinger maybe")
Depends-On: no-dep -- builds on gates and verbs that already landed (check:ci-plan-boxes, check:ci-plan-implementation, worklist.py --plan-tick); no open plan blocks it
Priority: P2 -- process rule; nothing is broken today, but live-only boxes currently live in carried reds (P-A1) with no typed evidence
Concurrency: parallel -- V1, V2 and V3 own disjoint files; V4 follows V1; V5 follows V1 to V4; V6 (migration) and V7 (pilot) run last and alone
Owns: .ci/config/live-proof.json, .ci/rediacc_ci/quality/live_proof.py, .ci/rediacc_ci/ops/live_proof.py, .ci/scripts/quality/check_plan_live_proof.py, .ci/rediacc_ci/tests/test_quality_live_proof.py, .ci/rediacc_ci/tests/test_ops_live_proof.py, .ci/rediacc_ci/tests/gates/test_gate_plan_live_proof.py, .ci/rediacc_ci/ops/deploy_bench.py (the version capture only), .ci/rediacc_ci/tests/test_ops_deploy_bench.py, .claude/hooks/stop/wl_plandeps.py (the Live-Proof grammar only), .claude/hooks/stop/test-plandeps.py, .claude/hooks/stop/worklist.py (the --live-proof verb only), .claude/hooks/stop/worklist_messages.py, .claude/rediacc_hooks/guards/block_plan_without_depends.py, agent/ledgers/live-proof.jsonl, package.json (one script line), .ci/config/lane-durations.json (one entry), docs/agent-reference/plan-records.md, agent/plans/PLAN-*.md (V6 only: the Live-Proof header line and the LP boxes), .ci/config/plan-boxes.json
Live-Proof: none -- CI and agent tooling only; deploy_bench.py is deploy tooling, not a deployable surface
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
     "plan":"agent/plans/PLAN-x.md","box":"<box sig>","target":"bench|hostinger","region":"eu|us|asia|null",
     "head":"<console commit>","tree":"<HEAD^{tree}>","dirty":false,
     "submodules":{"private/account":{"pointer":"<sha>","checkout":"<sha>","modified":false},"private/renet":{...}},
     "inputs":"<live-proof inputs digest, item 6>",
     "deploy":{"surface":"account|proxy|www|cli|renet","worker":"<name>|null","version_id":"<uuid>|<renet/cli version>",
               "source":"bench-cache|r2:release-records/...|rdc:eu-edge","deployed_head":"<sha>","confirmed_live":true},
     "check":{"id":"<registry id>","argv":["..."],"rc":0,"duration_s":41.2,"log_sha256":"<hex>","tail":["<=20 scrubbed lines"]},
     "verdict":"PASS","retro":false}

- The full log stays in `.ci/cache/live-proof/<id>.log`, which is gitignored. Only its sha256 is committed.
- Before writing, the recorder refuses any row that carries a secret value. It runs `deploy_record.refuse_secret_values` over the serialized row and the secret-shape scanner over the tail. Hostinger rows name the rdc config (`eu-bench`) and the machine alias, never an address.

**2. Which plans need it: derived, then declared.**
- `.ci/config/live-proof.json` holds a surface map. Each surface has globs, excludes and admissible targets:

  | Surface | Globs | Admissible targets |
  |---|---|---|
  | account | `private/account/src/**`, the account migrations and wrangler files, `workers/account/**`, `packages/shared/src/**` | bench |
  | proxy | `workers/proxy/src/**`, `workers/proxy/wrangler*.toml`, `workers/proxy/Dockerfile` | bench |
  | www | `packages/www/src/**`, `workers/www/**` | bench |
  | cli | `packages/cli/src/**` | bench, hostinger |
  | renet | `private/renet/cmd/**`, `private/renet/pkg/**`, `private/renet/proxy/**` | hostinger |

  The excludes cover `**/tests/**`, `**/*.test.ts`, `**/*_test.go`, `**/testdata/**` and `**/*.md`.
- A plan is **required** when all of these hold:
  - it is a live plan: not a stub, not under `_done/` or `_removed/`, and its Status is not in `wl_planfile.FINISHED_STATES`;
  - its `Owns:` globs intersect a surface glob, decided by `wl_planconc.owns_overlap`, the same engine the concurrency guard uses.
- A bare submodule path (`private/renet`, `private/account`) claims the gitlink, not the code, so it is not a surface claim.
- Deploy tooling (`.ci/rediacc_ci/deploy/**`, `ops/deploy_bench.py`, `release/**`) is not a surface.
- A required plan declares its proof in a header line inside the 12-line X window:
  - `Live-Proof: bench|hostinger[, <target>...] -- <reason>`, or
  - `Live-Proof: none -- <reason>` (gated, item 3 LP2).
- Every surface the plan touches must be covered by at least one declared target admissible for that surface. For example, a plan that touches both account and renet declares `bench, hostinger`.

**3. The CI-side rule: a new gate, `check:ci-plan-live-proof`.**
- It is a separate gate rather than an extension. `check_plan_implementation.py` is already 2494 lines and owns the clock, and the house shape is one concern per gate.
- It reads `.ci/config/plan-boxes.json` (proven equal to the tree by G-A0) and `agent/ledgers/live-proof.jsonl`, and it never re-parses boxes.
- Lane `quality-branch`, `selftest: true`, control-first with one plant per rule (the `check_hint_corpus.py` and `check_plan_implementation.py` shape).
- The rules:
  - **LP1** A required plan has no `Live-Proof:` line, or the line is malformed, emphasized, duplicated or outside the window. The grammar lives in `wl_plandeps` beside Depends-On, so the pre-edit guard and the gate share one parser.
  - **LP2** A declared target is not admissible for a touched surface, or a touched surface is left uncovered. `none` on a required plan passes only under a resolvable waiver (see Question 2), resolved through `wl_planfile.resolve_ruling`.
  - **LP3** A required plan that declares targets lacks one `LP-<target> [live]` box per target. Each such box must carry an `Accept: live-proof <target> <check-id> [args]` sub-line.
  - **LP4** An `LP-<target>` box moved from open to done on this branch with no receipt row matching all of the following: plan, box sig, target, `verdict: PASS`, `check.rc == 0`, `dirty: false`, and the Accept line's check id and arguments.
  - **LP5** A matching receipt is invalid. Any one of these makes it invalid:
    - its `head` is not an ancestor of the commit that ticked the box (judged through the rebase successor map, the way P-A4 judges, via `make_successor_of`);
    - `tree` or `head` does not resolve;
    - the `inputs` digest recomputed at `head` differs from the digest at the ticking commit, meaning surface code changed after the proof;
    - `deploy.deployed_head` differs from `head`;
    - `deploy.confirmed_live` is false for bench or edge;
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
- **Advisory lines, printed every run, red or green:** every `retro: true` receipt on the branch, and every `Live-Proof: none` on a required plan.
- **Forward-only.** LP4 to LP6 judge only transitions in commits dated strictly after `baseline_at` in `.ci/config/live-proof.json`, the device P-A2 uses. On the landing commit the gate is silent on transitions by construction. LP1 to LP3 judge every live required plan from V6 on.
- **No allowlist and no suppression** (`docs/agent-reference/suppressions.md`). The waiver is a named operator ruling, never a config entry.

**4. How the receipt is produced.**
- **Engine.** `rediacc_ci.ops.live_proof` (pure decision logic in `rediacc_ci.quality.live_proof`, shared with the gate):

      PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof record --plan <rel> --box <sig> --target bench|hostinger [--region eu] --check <id> [-- <args>] [--write]
      PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof verify [--plan <rel>]     # the gate's LP5 over the ledger, locally
      PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof record ... --retro --evidence <r2-key|review-file|commit> --write   # V6 backfill only

- **Check registry.** `checks` in `live-proof.json` maps an id to an argv template, its admissible targets and the surfaces it covers. Free argv is refused, so `true` cannot pass as a check. Initial entries:
  - `account-smoke`: `/health` plus `.well-known/server-info` on `bench.rediacc.com` or `edge-<region>.rediacc.com`.
  - `edge-smoke`: `rediacc_ci.deploy.verify_edge_endpoints`.
  - `proxy-ready`: `rediacc_ci.deploy.deploy_proxy --smoke-only`.
  - `drill:<name>`: any `rediacc_ci.drills.<name>` that takes a target.
  - `rdc`: `./rdc.sh --config eu-bench <args>`, where the args are recorded verbatim after the scrub.
  - `npm`: `npm run <script>`, where the script must be in an allowlist inside the registry.
- **Deploy identity, read and confirmed live (not believed).**
  - **bench:** V2 makes `deploy_bench` parse wrangler's version id and write `.ci/cache/live-deploys/bench.json` with `{version_id, head, tree, dirty, submodules, at}`. The recorder reads that file. Under the `deploy-bench` Bitwarden profile it then confirms through `wrangler deployments status` that this version serves 100% at check time.
  - **edge:** the recorder reads the deploy record that `release:local --channel edge` wrote (local `DEPLOY_RECORD_OUT` or R2 `release-records/v<V>/edge/deploy-record-edge-<region>.json`) and confirms live the same way. This catches a peer or CD redeploying edge mid-proof.
  - **hostinger:** the recorder records `renet version` and the CLI version that `./rdc.sh --config <cfg>` reports. `rdc.sh` builds renet from source, so the version must name `head`.
- **Refusals.** The recorder refuses a dirty tree on surface paths and a modified submodule checkout. It also refuses a deploy whose `deployed_head` differs from HEAD, and a live version that no longer matches the deploy record.
- **Agent verb.** `worklist.py --live-proof <me> <plan> <LP-box-sig> [--tick] [--write]` reads the box's Accept line, delegates to the engine and, with `--tick`, closes the box through `wl_planrec.plan_tick` in the same run. Its evidence line is `live-proof <id> <target> <check> rc=0 v=<version>`, and it writes the ledger and `plan-boxes.json` together, so the tick and the receipt always land in one commit (the `--plan-tick` pairing rule).
- **R2 mirror.** Not in scope. The committed ledger is the system of record. A write-once mirror under `live-proof/` can follow without changing the schema.

**5. Interplay with existing gates.**
- An LP box is an ordinary open box. P-A1 counts it, and since bench and edge are free for agents it closes pre-merge.
- The live boxes that today ride in the carried reds become LP boxes with a typed exit, which shrinks the carry instead of growing it.
- P-A2 and P-A4 still apply to LP boxes: an investigation row first (`--plan-investigate`), then the receipt, then the tick.

**6. Inputs digest.** It is computed by `git ls-tree` at a commit, as `lp1` followed by sorted blob lines. It covers paths matching both the plan's Owns and the surface globs, minus the excludes. For surfaces inside a submodule it uses the gitlink pointer, which is the vm:check v2 precedent and is coarse on purpose, because CI cannot rely on submodule objects. Staleness is judged only at the ticking commit, never at HEAD, so a commit after the tick never reopens a closed plan.

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
- **Required, zero open boxes, not yet finished:** converge-preflight-and-repo-recovery, renet-fetch-retries, renet-bridge-leftovers, backup-presign-bucket-require-and-wrangler-vars, renet-run-docker-sock-isolation (a write-up only; expected to get `none` under a ruling). V6 adds the LP boxes. Each then needs a fresh run or, per Question 3, a `--retro` row citing existing evidence, printed as ADVISORY on every run.

## Tasks

- [ ] V1 [writer] Engine core and config.
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
- [ ] V2 [writer] The `Live-Proof:` grammar in `wl_plandeps`. It has the X-field shape and the 12-line window, and its `none -- <reason>` reason needs at least 12 characters. The pre-edit guard `block_plan_without_depends.py` refuses a new plan whose Owns hit a surface and that carries no Live-Proof line.
  - Accept: `python3 .claude/hooks/stop/test-plandeps.py` rc=0 and `python3 .claude/rediacc_hooks/guards/test-block_plan_without_depends.py` rc=0, with new cases for a missing, malformed, emphasized and out-of-window line.
- [ ] V3 [writer] Bench version capture. `deploy_bench` parses `Current Version ID:` from the wrangler deploy output and writes `.ci/cache/live-deploys/bench.json` with `{version_id, head, tree, dirty, submodules, at}` and no secret values. An unparsed version id is a named DeployError after the deploy, never a silent skip.
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ops_deploy_bench.py -q` rc=0, with a test that fails on today's code (no cache file written).
- [ ] V4 [writer] The recorder `rediacc_ci.ops.live_proof`: `record`, `verify`, and `record --retro`; check-registry argv expansion; live version confirmation for bench and edge; hostinger `renet version` via `./rdc.sh`; and the secret refusal. Dry run is the default and `--write` appends.
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ops_live_proof.py -q` rc=0, with recording fakes for wrangler, curl and rdc. Cases:
    - a dirty tree refuses
    - a moved live version refuses
    - a planted secret in the tail refuses
    - `true` as a check refuses
    - the row id round-trips
- [ ] V5 [writer] The gate `.ci/scripts/quality/check_plan_live_proof.py` (LP1 to LP7, the advisory lines, the gate metadata block with `lane: quality-branch` and `selftest: true`), its `package.json` script `check:ci-plan-live-proof`, and a lane-durations entry. Set `baseline_at` to the landing date.
  - Accept: `npm run check:ci-plan-live-proof -- --selftest` rc=0 (every plant caught, healthy fixture silent). `npm run check:ci-plan-live-proof` rc=0 on the landing tree, where it reports LP1 findings for the V6 set as expected until V6 lands in the same PR. `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/gates/test_gate_plan_live_proof.py -q` rc=0.
- [ ] V6 [lead] Migration. Add the `Live-Proof:` line and the `LP-<target> [live]` boxes (with Accept sub-lines) to every required live plan listed in Design item 7, then regenerate `plan-boxes.json`. Any `none` gets the waiver Question 2 settles. Retro rows only as Question 3 allows.
  - Accept: `npm run check:ci-plan-live-proof` rc=0 with zero LP1 to LP3 findings; `npm run check:ci-plan-boxes` rc=0; `npm run check:ci-plan-deps` rc=0.
- [ ] V7 [lead] Pilot: one real receipt end to end on bench and one on hostinger through `--config eu-bench`. Candidate: PLAN-config-server-key's live box, after its K3 provisioning. Run `worklist.py --live-proof <me> agent/plans/PLAN-config-server-key.md <LP-bench sig> --tick --write`.
  - Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof verify --plan agent/plans/PLAN-config-server-key.md` rc=0, and `npm run check:ci-plan-live-proof` rc=0 on the commit that ticks it.
- [ ] V8 [writer] Docs: a "Live proof" section in `docs/agent-reference/plan-records.md` covering the header, the LP box form, the verb, the receipt schema and the LP rules.
  - Accept: `npm run check:ci-plan-citations` rc=0 and the docs lint lane rc=0.
- [ ] LP-none: this plan carries `Live-Proof: none` because its Owns hit no deployable surface. V7 is its live exercise.

## Operator rulings 2026-10-27 (answers to the questions below)

1. Renet and every surface: "Let's go with bench only not edge. I'll call subscription command after copy from EU config to bench." The live targets are bench (account, proxy, www, cli) and hostinger reached through the `eu-bench` rdc config (cli, renet), the EU stable store mirrored to bench. Edge is not a live-proof target; vm:check does not substitute. Every edge reference above is superseded by this ruling. Confirmed ASKED:2026-10-27T14:33Z: "Yes, bench + hostinger via eu-bench".
2. Opt-out: only with a ruling. `Live-Proof: none` passes only when it cites a closed worklist item or a committed operator quote.
3. Backfill: fresh runs for all. No `--retro` receipts; the four closed plans each get a new live run, and V4 drops `record --retro`.
4. Enforcement: LP1 to LP6 fail CI from the landing commit; forward-only judging keeps existing work green.

## Questions for the operator (answered above)

1. **Renet proof target.** Renet cannot run on bench or edge. Is a hostinger run (`./rdc.sh --config eu-edge`) mandatory for every renet-surface plan, or does a VERIFIED vm:check receipt for the same tree substitute?
   Recommended default: hostinger is mandatory, and vm:check does not substitute, because it is a pre-push VM run, not a live one.
2. **The `none` waiver.** May a plan whose Owns touch a deployable surface opt out with `Live-Proof: none -- <reason>` alone, or only under a resolvable operator ruling (a closed worklist item or a committed operator quote)?
   Recommended default: only under a resolvable ruling. A reason-only `none` is a silent bypass that the suppressions policy forbids.
3. **Backfill for plans whose implementation boxes are already closed** (converge-preflight-and-repo-recovery, renet-fetch-retries, renet-bridge-leftovers, backup-presign-bucket-require-and-wrangler-vars). Fresh live run, or a `--retro` receipt citing existing evidence (an R2 deploy record, a hostinger session in `agent/reviews`)?
   Recommended default: a retro receipt is allowed for these four only, printed as ADVISORY on every run. Every plan with open boxes needs a fresh run.
4. **Enforcement mode at landing.** Red from day one for LP4 to LP6 (forward-only, so nothing existing reds), or advisory first, as the 2026-10-23 ruling "Lean first, enforcement warns" set for P-A9?
   Recommended default: red for LP1 to LP6 from the landing commit. The request asks for a rule that gates the tick, and the forward-only cut already keeps existing work green.
