# Post-Fork Fixes Plan

Three independent improvements discovered during fork testing on linode-1.

## Part 1: Fix IPv6 Dual-Stack Proxy Conflict

### Problem

When `publicIPv6` is not configured, the proxy config generator falls back to `[::]:port` (IPv6 wildcard). On Linux with `net.ipv6.bindv6only=0` (default), `[::]` creates a dual-stack socket that also binds `0.0.0.0:port`. This conflicts with repo containers already listening on `127.0.x.x:port` (loopback IPs), causing Traefik to crash-loop.

### Root Cause

`private/renet/pkg/proxy/infra.go`:
- `formatTCPAddressIPv6()` (line 51-56): returns `[::]:port` when IPv6 is empty
- `formatUDPAddressIPv6()` (line 59-64): same pattern
- HTTP/HTTPS entrypoints (lines 209-214): fall back to `[::]:80/443`

### Fix

Only generate entrypoints for address families that are actually configured. Skip IPv6 when `PublicIPv6` is empty, skip IPv4 when `PublicIPv4` is empty. At least one must be configured.

1. `formatTCPAddressIPv4()` / `formatTCPAddressIPv6()`: return empty string when IP is empty (no `0.0.0.0` or `[::]` fallbacks)
2. Same for UDP format functions
3. HTTP/HTTPS entrypoint blocks: only generate IPv4 section when `PublicIPv4 != ""`, only generate IPv6 section when `PublicIPv6 != ""`. Remove the `else` branches that fall back to `0.0.0.0` / `[::]`.
4. Common TCP/UDP port entrypoints: wrap each in IP-availability guard
5. Dynamic port range entrypoints: same guards

### Files

- `private/renet/pkg/proxy/infra.go` — remove all `0.0.0.0` and `[::]` fallbacks, guard each address family by IP availability
- `private/renet/pkg/proxy/infra_test.go` — update tests: IPv4-only config produces no IPv6 entrypoints, IPv6-only config produces no IPv4 entrypoints, dual-stack produces both

## Part 2: Auto-Infra After Machine Provision

### Problem

`machine provision` creates the VM but does not configure infra (set-infra + push-infra). Without infra config, `repo up` silently skips DNS record creation and proxy setup. Users don't realize they need to manually run `config set-infra` + `config push-infra`.

### Root Cause

`provision.ts` step 12 (line 210): `const infraSource = options.inheritInfra ?? (options.baseDomain ? { baseDomain: options.baseDomain } : undefined)` — only runs when `--base-domain` is explicitly passed or `inheritInfra` is set (backup push auto-provision).

### Fix

Auto-detect `baseDomain` from sibling machines in the same config:

1. In step 12 of `provision.ts`, before the existing check, add:
   ```typescript
   if (!infraSource) {
     const machines = await configService.listMachines();
     const sibling = machines.find(m => m.name !== machineName && m.config.infra?.baseDomain);
     if (sibling) {
       infraSource = { baseDomain: sibling.config.infra!.baseDomain! };
     }
   }
   ```

2. Add `--no-infra` flag to `machine provision` command as escape hatch

3. When step 12 is skipped (no baseDomain anywhere), log an info message telling the user what to do

4. `config setup-machine`: after successful `renet setup`, check if machine has infra configured and auto-run `push-infra`

### Files

- `packages/cli/src/services/tofu/provision.ts` — sibling baseDomain detection, `noInfra` option, skip message
- `packages/cli/src/commands/machine/cloud.ts` — add `--no-infra` flag
- `packages/cli/src/commands/config-setup.ts` — conditional push-infra after setup-machine
- `packages/cli/src/i18n/locales/*/cli.json` (9 files) — new i18n keys
- `packages/cli/src/commands/mcp/tools.ts` — update machine_provision description

## Part 3: Repo-Based DOCKER_HOST in Terminal

### Problem

`rdc term <machine> <repo> -c "docker ps"` shows system Docker daemon containers instead of the repo's containers. `DOCKER_HOST` defaults to `unix:///var/run/docker.sock` instead of `unix:///var/run/rediacc/docker-<networkId>.sock`.

### Root Cause

`term.ts` line 102: `DOCKER_HOST: (machineVault.dockerHost ?? DEFAULTS.DOCKER.HOST_URI)` — falls back to system socket. The local adapter path accidentally works because `local-state-provider.ts:231-232` pre-populates `machineVault.dockerHost`. But the cloud adapter path and VS Code paths don't.

### Fix

When a repository is specified and `networkId` is available, derive `DOCKER_HOST` from the network ID:

```typescript
const repoDockerSocket = (machineVault.dockerSocket ??
  (networkId ? `/var/run/rediacc/docker-${networkId}.sock` : DEFAULTS.DOCKER.SOCKET_PATH)) as string;
const repoDockerHost = (machineVault.dockerHost ?? `unix://${repoDockerSocket}`) as string;
```

This preserves backward compat: `machineVault.dockerHost` takes precedence if explicitly set.

Reference implementation exists at `packages/shared-desktop/src/repository/environment.ts:125-131`.

### Files

- `packages/cli/src/commands/term.ts` — fix `buildRepositoryEnvironment()` lines 102-103
- `packages/cli/src/commands/vscode-utils.ts` — same fix at lines 107-108
- `packages/shared-desktop/src/vscode/envCompose.ts` — fix default params at lines 111-112 to derive from networkId
- Optional: extract shared `resolveDockerPaths(networkId, machineDockerSocket?, machineDockerHost?)` helper

## Completed

- [x] Router repo-level route for custom domain services (`routes.go` — triple route generation)
- [x] Linode-1 infra config (manual set-infra + push-infra with IPv4 + IPv6)
- [x] Fork test verified: all 7 containers running on linode-1
- [x] Part 1: IPv6/IPv4 proxy entrypoint fix — skip entrypoints for unconfigured address families
- [x] Part 2: Auto-infra after provision — sibling baseDomain detection + `--no-infra` flag + auto push-infra after setup-machine
- [x] Part 3: Repo-based DOCKER_HOST — derive socket from networkId in term.ts, vscode-utils.ts, envCompose.ts

## Verification

```bash
# Part 1: Build renet, push-infra to a machine without IPv6, verify no [::] in config
cd private/renet && go test ./pkg/proxy/...
# Verify: docker-compose.override.yml should have NO [::] entries when IPv6 is empty

# Part 2: Provision a new machine without --base-domain, verify infra is auto-configured
# Expected: baseDomain inherited from hostinger, DNS records created, proxy started

# Part 3: Test DOCKER_HOST in term
rdc term hostinger marketing-staging -c "echo \$DOCKER_HOST"
# Expected: unix:///var/run/rediacc/docker-3200.sock (not /var/run/docker.sock)
```
