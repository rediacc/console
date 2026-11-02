---
name: renet-dev
description: Go development on renet (private/renet), the machine-side orchestrator. Covers build.sh and its embedded assets, the licence-key build requirement, the package map, adding a renet function end to end (registry, builder, tier map, generated contract, CLI pairing, e2e coverage), local Go tests and the CI stages, which tests a change needs, running e2e under sudo, and the submodule-first commit rules. Use for any change under private/renet, before building a renet binary, or when a renet gate or Go test fails.
tools: Bash, Read, Edit, Write, Grep, Glob
model: opus
---

Renet changes go through this file. The tree is the truth; every line below names the file that proves it, so that file is re-read before building on a detail.

## Build

One build exists: licence-enforcing, with the production public key baked in. There is no `nolicense` tag, no keyless build and no `bin/enforce/` split (renet `aa872ed`, console `c0e67f9c9`; `.ci/rediacc_ci/tests/test_private_renet_build_dev_flavor.py` pins it).

| Command (from `private/renet`) | Effect |
|---|---|
| `./build.sh dev` | Host binary `bin/renet` plus `bin/renet-linux-amd64` and `bin/renet-linux-arm64` (the CLI pushes the one matching a remote). Takes no arguments; the retired flavor flags are refused. |
| `./build.sh build` | Release cross-compile. |
| `./build.sh embed_assets [--force]` | Extracts CRIU, rsync and the other lockfile assets from the Docker image into `pkg/embed/assets/<arch>/<class>/*.zst`. Needs Docker. |
| `./build.sh docker_image` | The asset image `rediacc/renet:latest`. |
| `./build.sh key-ldflags` | Prints the key ldflag, or fails: the seam the key test drives. |

- Embedded assets come from `embed-assets.lock.json`, the single list of versions, digests and base/cluster classes. A change to that file or to `go.mod` / `go.sum` changes the binary the VMs run.
- `ACCOUNT_ED25519_PUBLIC_KEY` is required. `_account_key_ldflags` refuses to build without it. `./rdc.sh` and `./run.sh` supply it from bws; a hand build exports it first.
- Never `go build -o bin/renet`. It skips the key ldflag and the embedded assets, and `bin/renet` is the slot `./rdc.sh` deploys. A scratch build for a tool goes to `/tmp` (`go build -o /tmp/renet-x ./cmd/renet`) and is never copied into `bin/`.
- A binary is proven before it is trusted: `go version -m <path>` must show `ProductionPublicKey=` in the ldflags. A binary without it is a foreign bare build and fails every licensed call.
- A compile error anywhere in `packages/cli` also fails `./rdc.sh` before renet builds: `npx tsc --noEmit --project packages/cli/tsconfig.json` tells the two apart. The VM fleet is the `ops-vms` agent's.

## Package map (`private/renet/pkg`)

- `cmd/renet`: the Cobra CLI; every verb a function wraps lives here.
- `pkg/functions` and `pkg/functions/commands`: the function registry (`commands/registry.go`, `CommandBuilder`), the builders per area (`repository.go`, `backup.go`, `datastore.go`, `kube.go`, `ceph.go`, `system.go`, `daemon.go`, ...), the executors (`executor_local.go`, `executor_ssh.go`, `executor_hybrid.go`) and `vault/`.
- `pkg/license`: validation, chain state, renewal, and `tiermap.go`, the total tier map. An entry carries `tier`, `repoParam` (the parameter naming the repository) and, for a call that may arrive without one, `repoless` (renet `c388e2a` and later). Details: the `licensing-ops` agent.
- `pkg/kube`, `pkg/kubecsi`, `pkg/kubevolume`: the k3s repo runtime and the CSI driver.
- `pkg/rbd`, `pkg/datastore`, `pkg/thinpool`: Ceph and local storage backends.
- `pkg/chunkstore`, `pkg/coldbackup`, `pkg/backupstate`, `pkg/snapshot`: backup.
- `pkg/daemon`, `pkg/router`, `pkg/dockerproxy`, `pkg/dockerpolicy`: the per-network daemon, the router and the Docker policy proxy.
- `pkg/embed`: the `go:embed` assets.
- `pkg/infra`, `pkg/orchestration`: KVM, Docker, SSH and the `ops` cluster lifecycle.
- `pkg/i18n`: catalogs per locale; the i18n checks run inside `check:ci-renet`.

## Adding a function end to end

1. Register it and write its builder in `pkg/functions/commands/<area>.go` (registry in `registry.go`; the builder returns the argv and optional stdin).
2. Give it a tier map entry in `pkg/license/tiermap.go`. Set `repoParam` when a repository is named, and `repoless` when a call without one is legitimate. `TestTierMapCoversRegistry` (`pkg/functions/tiermap_completeness_test.go`) fails on an unmapped name and `TestRepolessTieredCallsAreDecided` (`pkg/functions/executor_repoless_test.go`) on an undecided repo-less call.
3. Regenerate the contract: `cd private/renet && go build -o /tmp/renet-types ./cmd/renet` (with `ACCOUNT_ED25519_PUBLIC_KEY` exported), then `/tmp/renet-types functions generate-types --output ../../packages/shared/src/renet-contract/data --version $(git describe)`. `--output` is the `data` directory itself: the parent directory collects stray files. Then `npm run check:ci-renet-types` and `npm run check:ci-renet-tiers`; rebuild `packages/shared` or CLI tests read a stale `dist`.
4. Pair it in the CLI: the verb or builder in `packages/cli/src` (`services/executor/renet-command.ts`, `services/renet/renet-license-contract.ts`; licensed-function knowledge comes only from the generated `LICENSE_TIERS`).
5. Cover it in `packages/e2e-tests`: `npm run check:ci-e2e-coverage` greps there for every generated function name.

## Go tests

- One package: `cd private/renet && go test ./pkg/<x>/...`. Tag-gated files (`root`, `ebpf_e2e`) need `go vet -tags "root ebpf_e2e" ./...` to compile; root tests need sudo.
- CI stages, same script CI runs: `private/renet/.ci/ci.sh quality|govulncheck|test|build|all`. From the console root, `npm run check:ci-renet` runs the quality stage (gofmt, golangci-lint, deadcode, i18n) and `check:ci-renet-govulncheck` the advisory stage.
- `test-renet-go` in CI splits the packages into shards: `.ci/config/shards/test-renet-go.json`. A new package lands in a shard through the manifest generator; a package in no shard never runs in CI.
- Which tests a change needs: `.ci/config/renet-test-map.json` maps renet paths to the Go packages to test, and `npm run vm:check -- --changed` runs the VM areas the diff touches. Those two files hold the current table; none is copied here. The vm:check mechanics (receipts, verdicts, costs) live once, in `ops-vms.md`.

## e2e and cross-VM runs

- `renet functions once` runs as root (`sudo -n renet functions once`), as the CLI does in production: test mode enforces licensing, and the licence check reads the machine id as root (renet `23c0c03b`, console `94fbfe12d`). Test mode has no bypass.
- Under root the invoking user's identity is gone, so cross-VM verbs (`backup_push`, `backup_pull`, `repository_migrate`) carry `--source-user` / `--dest-user` plus `--ssh-key` for the bridge user. A new cross-VM verb takes the same three params and the e2e runner (`packages/e2e-tests/utils/renet-functions/`) injects them.
- Running the suites: the `e2e-local` agent. Build flavor: the one build above, never a CI artifact.

## Commit rules

- Submodule first: commit in `private/renet`, then the console commit moves the pointer (`private/renet`) in the same unit. The pointer move is what the console gates and the VM proof read.
- The console PR carries one `PR-TASK:` trailer per commit; the renet branch matches the console `MMDD-N` branch. Never `git checkout`, `restore`, `stash` or `clean` in either tree.
- An upload of a dev binary built from a dirty renet tree is refused unless `REDIACC_ALLOW_DIRTY_RENET=1`; commit first instead.
