# 07 — Examples Catalog and CI Enhancement

**Status: §7 (the kube e2e suites) is AS-BUILT. Everything else is forward-looking (P5/P6).**

Purpose: the `rdc` surface has ZERO CI e2e coverage today (e2e drives `renet` over bridge
SSH; grep confirms no cli-bundle/rdc invocation in packages/e2e-tests). The examples suite
is simultaneously (a) user-facing copy-pasteable documentation-as-code, (b) the local
validation vehicle for the redesign, (c) the CI rdc coverage. Examples target the NEW
command surface (06).

## 1. Catalog (~24 self-contained folders, 5 tracks)

```
examples/README.md               index, prereqs (ops up), env conventions, safety notes
Track 0  00-machine-setup  01-datastore-create  02-first-repo  03-multiple-repos
         (03: THREE repos on one datastore + isolation proof: own dockerd socket,
          own 127.0.x.x/26, own LUKS file; one shared snapshot moment)
Track 1  10-real-app  11-fork-and-diverge  12-branching-workflow  13-secrets
         14-size-management  15-push-pull-backup  16-migrate  17-checkpoint-fork
         18-promote  (+ NEW on feature layer: 19-replicate)
Track 2  20-datastore-rbd  21-datastore-fork (--writes local overlay; ceph untouched)
         22-snapshot-moment (all repos, one instant)
Track 3  30-cluster-create (KVM)  31-deploy-app (PVC via local PVs)  32-namespace-fork
         33-cluster-fork  34-cluster-migrate  35-scale  (+ 36-rehearse)
Track 4  40-provision-cloud (manual/nightly — costs money)  41-monitoring-health
         42-terminal-vscode (README + asciinema only; interactive)
```

Folder anatomy (self-contained; NO shared lib inside examples/): `README.md` (one concept,
stated in the first line; teardown section), `run.sh`, plus `app/` (Rediaccfile,
docker-compose.yml, Dockerfile, go.mod, main.go) and/or `manifests/` where relevant.
The shared real workload: a ~60-line Go notes-API + Postgres (POST /notes, GET /notes,
/healthz) — fork divergence becomes provable SQL rows ("fork has the row, parent doesn't").
Language policy: shell + Go + YAML only, NO TypeScript (keeps eslint/knip/biome out
structurally).

## 2. Conventions (verified against code; the footguns are real)

- **run.sh preamble** (identical everywhere): `set -euo pipefail`; RDC indirection
  `if [[ -n "${RDC:-}" && "$RDC" != "rdc" ]]; then rdc() { $RDC "$@"; }; fi` (recursion-
  guarded, tutorial-helpers.sh pattern) so scripts call literal `rdc ...` — copy-pasteable
  AND statically checkable; `export REDIACC_CONFIG=examples`;
  `REDIACC_SKIP_MACHINE_ACTIVATION=1` (ops VMs are license-less).
- **FOOTGUN (verified)**: `config init` IGNORES `REDIACC_CONFIG` and merges flags into the
  user's real default config when `--name` is omitted (packages/cli/src/commands/config.ts).
  Examples must ALWAYS `rdc config init --name examples`. Harness self-check greps for
  violations.
- Machine registration is the script's job (ops VMs are NOT auto-registered):
  `rdc config machine add --name machine-11 --ip 192.168.111.11 --user $USER` + `setup`,
  idempotently guarded. (Post-reshape: `rdc machine add ...`.)
- **Resource naming**: everything prefixed `exNN-`; `trap cleanup EXIT`; idempotent start
  deletes own leftovers incl. stale config rows. Teardown-verify = no `exNN-` residue.
- **Cluster fixture**: track-3 honors `EXAMPLES_CLUSTER` (reuse-or-create; creator-tears-
  down; `EXAMPLES_KEEP_CLUSTER=1` pins). Cluster net `renet12`/`192.168.112` — NEVER the
  ambient ops fleet's `renet11`/`192.168.111`.
- Dependencies: every docker-track example re-creates its prereqs inline (11 forks its own
  tiny `ex11-base`, not 10's repo) — standalone, any order. The cluster is the ONE shared
  fixture (creation ~10+ min).

## 3. Local harness

`.ci/scripts/test/run-examples.sh` + `.ci/scripts/test/lib/examples-helpers.sh` (inside
`.ci/` → auto-covered by shfmt/shellcheck).

- Modes: `--example NN-x | --track N | --ci-set docker|k8s|ceph | --all`; flags
  `--continue` (default fail-fast), `--keep`, `--reset`, `--ops-up`.
- Does: rdc resolution (PATH rdc → `RDC` env → repo-local `./rdc.sh`); `go vet && go build`
  for every examples app (NO Go gate reaches examples/ otherwise); ssh preflight of needed
  VMs (exit 2 with "run ./rdc.sh ops up [--basic]" hint — never boots VMs implicitly;
  `--ops-up` opts in); guardrail-env warnings; per-example logs under
  `reports/examples/<ts>/` + summary table with timings; teardown-verify; **flock so
  concurrent invocations serialize VM access**.
- `--reset` removes ONLY `~/.config/rediacc/examples.json` + prunes orphaned `exNN-` repos.
  Examples never `rm` any config file.

## 4. Gate opt-ins (exact, verified scopes)

| Gate | Edit |
|---|---|
| shfmt (`.ci/scripts/security/shfmt.sh`) | add `examples` to the dir loop (~line 60) — scope today is ONLY `.ci/**`, `run.sh`, `scripts/dev|docker/**` |
| shellcheck (`.ci/scripts/security/shellcheck.sh`) | guarded `find examples -name '*.sh'` block |
| eslint | add `'examples/**'` to global ignores (belt-and-braces; the `**/*.ts` glob would otherwise hit any stray TS) |
| biome / knip | nothing — allowlist/workspace-based, examples/ invisible (do NOT add a package.json to examples/) |
| `check:cli-examples` (`scripts/validate-cli-examples.ts`) | add `examples/**/*.{md,sh}` to TARGET_GLOBS; a dedicated `.sh` extractor (strip `\|\| true`, redirects, pipes) is a separate low-risk task — the whole-file positional scan already applies |
| editorconfig | repo-wide: 4-space shell indent, LF |

## 5. CI topology

New reusable workflow `.github/workflows/ci-examples.yml` (do NOT extend ci-ops-test.yml —
different contract and blast radius). Clone the `ops-vm-provision` setup steps verbatim
(SHA-pinned actions, app-token checkout w/ submodules, GHCR+DockerHub login, KVM udev
enable, install-deps + build-packages, `build-renet.sh --nolicense`, CLI build+bundle, the
"Configure local config" rediacc.json step, monthly VM-image cache
`vm-base-image-<image>-YYYY-MM` shared with ops-tests).

- **Job `examples-docker`** (timeout 60m): `ops up` with `VM_WORKERS="11 12"`,
  `VM_CEPH_NODES=""`, `VM_RAM_WORKER=3072` (1024 bridge + 2×3072 = 7.2 GB, under the
  14.5 GB modeled ceiling); `run-examples.sh --ci-set docker` with
  `RDC="node $GITHUB_WORKSPACE/packages/cli/dist/cli-bundle.cjs"` (no rdc on PATH in CI),
  `REDIACC_ALLOW_GRAND_REPO=1`; upload logs always(); `ops down` always(); cache save.
- **Job `examples-k8s`** (timeout 75m): `run-examples.sh --ci-set k8s` = 30→31→32 on shared
  `ex30-demo` with `VM_RAM=3072`, `VM_RAM_CEPH=2560` (control 1024 fixed + ceph 2560 +
  server 3072 + agent 3072 = 9.7 GB); `REDIACC_ALLOW_CLUSTER_OPS='*'`; leftover-destroy
  always(). (Cluster RAM IS env-tunable through `rdc cluster create` — env passes through
  to renet opsconfig; floor 2048; bridge pinned 1024.)
- **ci.yml wiring**: `examples-tests` job cloning the `ops-tests` needs/if idiom
  (`needs: [initialize, quality, review-gate, build-renet]`; if full_suite +
  quality/review-gate success-or-skipped) + the THREE `ci-complete` touches: needs array,
  `[[ ... == "failure" ]] && FAILED=true` line (soft tier), echo line.
- `check:ci-workflows` is a custom linter (no actionlint): SHA-pinned actions only, no
  inline `script:`, secrets via `env:` only.

CI-vs-local matrix (wave 1): 00-17 + 19 in examples-docker (15/16 need machine-12); 30-32
in examples-k8s; 18/20-22/33-36 local-only (33/34 need a second cluster = over RAM budget;
ceph track deferred — e2e ceph legs already run daily; harness ships `--ci-set ceph` so the
job is a 20-line YAML later). If examples-docker exceeds ~50 min, trim 14/17 from the CI
set before splitting jobs (every leg re-pays ~15 min setup).

## 6. Guardrail note for CI

`REDIACC_ALLOW_*` ancestry verification triggers only in agent environments; a CI shell has
no agent ancestor, so plain `env:` exports are expected to pass. Residual risk confirmed on
the first real CI run.

## 7. The kube e2e suites (AS-BUILT): P6's CI candidates

The three kube e2e suites were rewritten on the new model in P3 and **now exist and pass
functionally**. They are the strongest asset P6 inherits: between them they prove the entire
datastore-cluster model end to end, and they are resettable, which is what makes them CI
candidates rather than hand batteries.

| Suite | Result | What it proves |
|---|---|---|
| **15** k8s-repo (single node, local datastore) | **7/7 GREEN, exit 0** | A kube repo end to end through the runtime-generic `repository up` dispatch: the isolation trio, a no-provisioner StorageClass, a bound local PV, a Running pod, secret env-transport, router annotations, the security lint, and a clean teardown with zero leaked LUKS mounts or loop devices |
| **16** datastore-cluster (ceph group-snap fork) | **11/12**, the entire functional battery green, three independent times | Atomic group snapshot with the parent never stopped, clone-format-2, cross-node adopt and attach, the F1-F8 PKI re-mint, fork carries a fresh CA with no parent secret material and ROLE=fork, the parent's admin cert 401s on the fork and 200s on the parent, parent continuity, and a CA-preserving migrate |
| **17** multinode (fork + migrate) | **6/7**, the entire functional battery green | A real 2-node cluster with a NIC-joined agent; **whole-cluster fork** (one atomic group snapshot, clone, identity-rewrite, a FRESH agent joining the fork's NEW CA, kine diverging from the parent); the parent untouched afterwards; and **cluster migrate** with a measured cutover |

### The two known reds (teardown only)

Both are `#29` and `#30` from the bug ledger, both are teardown-only, **no functional proof
depends on either**, and both have post-failure probes already wired so the next run names the
cause rather than costing a blind cycle.

- **Suite 16 test 12 (#29)**: after a clean unmount, `dmsetup remove <fork>-cow` returns EBUSY
  for 27 seconds of retries. Not a mount, not a process, not a loop, and not btrfs's
  scanned-device cache (refuted by controlled experiment). Unexplained.
- **Suite 17 test 7 (#30)**: after a cluster **migrate**, the repo namespace refuses to
  terminate, while the identical `down` on a never-migrated cluster finishes in seconds (suite
  15 is green). Migrate-specific, distinct from #28.

**P6 should expect these two reds until the P4 work lands**, and must not paper over them by
loosening the assertions.

### Test-side workarounds P6 must handle

- **DROP suite 16's test-side `csiNodeDown` call.** It was a workaround for #26 (the product
  started CSI daemons it never stopped). #26 is fixed: the product now stops them on detach and
  on `kube uninstall`. Suite 17 already carries **zero** test-side CSI teardown, and that is
  precisely what proves the fix, so keeping the workaround in 16 would hide a regression.
- **KEEP the deepest-first submount unwind helper** for now (it matches the mount string
  anywhere in the `/proc/mounts` line, not just mountpoints under the datastore). It becomes
  redundant once P4 lands the shared node-side teardown primitive over the holder taxonomy
  (02 §3), and should be dropped in the same change.

### Harness lessons (these cost real time; do not re-learn them)

- **The BRIDGE test timeout must exceed 120 seconds.** It was 120,000ms while the F1-F8 PKI
  re-mint takes 117.9 to 120.0 seconds. The harness was **SIGKILLing the product** at exactly
  the moment it was about to succeed, and the re-mint had been passing on a coin flip for the
  entire campaign. Raised to 360s in **each suite's own playwright config** (not in a local
  `.env`, so CI inherits it). Generalized rule: when a test harness kills a product operation,
  suspect the harness bound before suspecting the product.
- **The test-mode dispatcher's flags drift from the bridge ParamDefs.** `functions once
  --test-mode` hand-lists its flags, and it lagged every redesigned verb. Three separate
  harness bugs (H1, H2, H3) were all this one class. The fix, which is on the P4 carry-in
  list, is to **derive the dispatcher flags from the bridge `ParamDef` registry** so they
  cannot drift.
- **A `; true` in a shell assertion makes the assertion vacuous.** `expect(down.code).toBe(0)`
  could never fail, and it hid a failing `repository down` for the entire campaign. All three
  suites were swept; no other instance was found. Worth a lint rule.
- **Mid-suite kube failures wedge k3s containerd mounts**, and only `ops up --force` clears
  them, so every failed iteration pays the roughly 13-minute reset. Teardown resilience for
  partially-failed kube suites is a real candidate improvement (it relates to the convergent-init
  contract in 03 §2b).
