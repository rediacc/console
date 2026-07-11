# 07 — Examples Catalog and CI Enhancement

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
