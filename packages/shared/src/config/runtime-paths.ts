/**
 * Per-network runtime paths on a Rediacc machine, the TypeScript mirror of
 * renet's `pkg/runpaths`.
 *
 * Every file a repo's dockerd and containerd write at runtime lives under one
 * directory per network, `/var/run/rediacc/net-<N>/`, so the repo's sandbox
 * binds that directory alone and never sees another repo's socket or secrets
 * (agent/plans/PLAN-renet-cross-repo-isolation.md, D1 and D3). The basenames
 * inside it are unchanged: the Docker socket is still `docker-<N>.sock`.
 *
 * `runtime-paths.test.ts` pins the literal `/var/run/rediacc/net-7104/docker-7104.sock`,
 * the same literal renet's `runpaths` test pins, so a drift on either side
 * fails a test.
 */

import { WK_RUNTIME_DIR } from './well-known.generated.js';

/** A renet network id: a positive integer, as a number or its decimal string. */
export type NetworkId = number | string;

const NETWORK_ID_PATTERN = /^[1-9]\d*$/;

function normalizeNetworkId(networkId: NetworkId): string {
  const value = String(networkId);
  if (!NETWORK_ID_PATTERN.test(value)) {
    throw new Error(`Invalid network id ${JSON.stringify(value)}: expected a positive integer`);
  }
  return value;
}

/** `/var/run/rediacc/net-<N>`: the one runtime directory a network's sandbox binds. */
export function repoNetDir(networkId: NetworkId): string {
  return `${WK_RUNTIME_DIR}/net-${normalizeNetworkId(networkId)}`;
}

/** `/var/run/rediacc/net-<N>/docker-<N>.sock`: the repo's own Docker socket (`DOCKER_SOCKET`). */
export function repoDockerSocketPath(networkId: NetworkId): string {
  const id = normalizeNetworkId(networkId);
  return `${repoNetDir(id)}/docker-${id}.sock`;
}

/** `unix:///var/run/rediacc/net-<N>/docker-<N>.sock`: the repo's `DOCKER_HOST`. */
export function repoDockerHost(networkId: NetworkId): string {
  return `unix://${repoDockerSocketPath(networkId)}`;
}

/** `/var/run/rediacc/net-<N>/secrets`: the tmpfs directory holding the repo's file-mode secrets. */
export function repoSecretsDir(networkId: NetworkId): string {
  return `${repoNetDir(networkId)}/secrets`;
}

const escapedRuntimeDir = WK_RUNTIME_DIR.replaceAll(/[.*+?^${}()|[\]\\/]/g, String.raw`\$&`);

/** Matches any path inside some network's runtime directory, `/var/run/rediacc/net-<N>/...`. */
export const REPO_NET_DIR_PATTERN = new RegExp(String.raw`${escapedRuntimeDir}/net-\d+/`);

/**
 * `/var/run/rediacc/docker-<N>.sock`: the flat socket path of the layout before `net-<N>/`. A renet that has not
 * moved yet serves it, and so does a daemon a moved renet has not restarted: renet deletes the old path only when it
 * starts the network's daemon (renet `pkg/daemon/start_foreground.go`), and a binary update restarts no daemon.
 */
export function legacyRepoDockerSocketPath(networkId: NetworkId): string {
  const id = normalizeNetworkId(networkId);
  return `${WK_RUNTIME_DIR}/docker-${id}.sock`;
}

/**
 * The shell statement that re-points a session at the flat socket when the network's daemon still serves it, or ''
 * when the environment does not carry the derived `net-<N>` socket (no network id, or a socket the vault names).
 *
 * The CLI cannot know from its side which layout a daemon serves: a read-only connection (`term connect`, `vscode`,
 * `repo tunnel`) runs the machine's renet as-is, and a running daemon keeps its old socket until its next start. The
 * test runs on the machine in the same command, so it costs no round trip, and it re-runs in every shell that sources
 * it, so a session follows the daemon once it restarts on the new layout.
 */
export function repoDockerSocketFallbackShell(environment: Record<string, string>): string {
  const networkId = environment.REDIACC_NETWORK_ID;
  if (!networkId || !NETWORK_ID_PATTERN.test(networkId)) return '';
  const current = repoDockerSocketPath(networkId);
  if (environment.DOCKER_SOCKET !== current || environment.DOCKER_HOST !== `unix://${current}`)
    return '';
  const legacy = legacyRepoDockerSocketPath(networkId);
  return (
    `if [ ! -S '${current}' ] && [ -S '${legacy}' ]; then ` +
    `export DOCKER_SOCKET='${legacy}' DOCKER_HOST='unix://${legacy}'; fi`
  );
}
