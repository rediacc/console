/**
 * Remote install / launch / status / stop orchestration for browser VS Code
 * servers (`rdc vscode connect --browser`, `rdc vscode serve ...`).
 *
 * Two SSH trust paths are used deliberately:
 *  - INSTALL runs over the TEAM key with sudo — it writes the shared
 *    read-only install under /usr/lib/rediacc/vscode via the hidden
 *    `renet vscode-server install` command (download + sha256 + untar).
 *  - LAUNCH/STATUS/STOP run over the REPO key, which lands in the
 *    sandbox-gateway: the server inherits the Landlock sandbox and writes
 *    only to the per-repo overlay home.
 */

import { randomBytes } from 'node:crypto';
import http from 'node:http';
import { SSHConnection, spawnSSH } from '@rediacc/shared-desktop/ssh';
import type { VSCodeServerProvider, ServerPlatform } from '@rediacc/shared-desktop/vscode-server';
import { t } from '../i18n/index.js';
import { ValidationError } from '../types/errors.js';
import { debugLog } from '../utils/debug.js';
import type { ConnectionDetails } from './ssh-connection.js';

/** Mutable per-repo server state root, inside the sandbox overlay home. */
const STATE_ROOT = '$HOME/.rediacc-vscode';

/** Deterministic remote port base; collisions probe upward (max +9). */
const REMOTE_PORT_BASE = 9300;
const REMOTE_PORT_SPAN = 200;

export interface ServerLaunchResult {
  remotePort: number;
  /** Token (url-token providers) or password (password-env providers). */
  secret?: string;
  reused: boolean;
}

interface SSHExecResult {
  code: number | null;
  stdout: string;
  stderr: string;
}

/** Run a command over SSH with the given private key, capturing output. */
async function execSSH(
  connectionDetails: ConnectionDetails,
  privateKey: string,
  command: string
): Promise<SSHExecResult> {
  const conn = new SSHConnection(privateKey, connectionDetails.known_hosts, {
    port: connectionDetails.port,
    forceTTY: false,
  });
  try {
    await conn.setup();
    const dest = `${connectionDetails.user}@${connectionDetails.host}`;
    const child = spawnSSH(dest, conn.sshOptions, command, {
      env: process.env,
      stdio: 'pipe',
      agentSocketPath: conn.agentSocketPath,
    });
    let stdout = '';
    let stderr = '';
    child.stdout?.on('data', (d: Buffer) => {
      stdout += d.toString();
    });
    child.stderr?.on('data', (d: Buffer) => {
      stderr += d.toString();
    });
    const code = await new Promise<number | null>((resolve, reject) => {
      // 'close' (not 'exit') guarantees stdout/stderr are fully flushed first.
      child.on('close', resolve);
      child.on('error', reject);
    });
    return { code, stdout, stderr };
  } finally {
    await conn.cleanup();
  }
}

/** Resolve the machine's CPU architecture to a server artifact platform. */
export async function detectServerPlatform(
  connectionDetails: ConnectionDetails,
  teamKey: string
): Promise<ServerPlatform> {
  const result = await execSSH(connectionDetails, teamKey, 'uname -m');
  const arch = result.stdout.trim();
  if (arch === 'x86_64') return 'linux-x64';
  if (arch === 'aarch64' || arch === 'arm64') return 'linux-arm64';
  throw new ValidationError(t('errors.vscode.unsupportedArch', { arch }));
}

/**
 * Ensure the provider's server release is installed on the machine.
 * Idempotent: renet skips the download when the pinned digest is already
 * unpacked (`.ok` marker).
 */
export async function ensureServerInstalled(
  provider: VSCodeServerProvider,
  connectionDetails: ConnectionDetails,
  teamKey: string,
  options: { platform: ServerPlatform; archive?: string }
): Promise<void> {
  const artifact = provider.artifact(options.platform);
  const args = [
    'sudo renet vscode-server install',
    `--sha256 '${artifact.sha256}'`,
    `--dest '${provider.installDir()}'`,
    `--strip-components ${artifact.stripComponents}`,
  ];
  if (options.archive) {
    args.push(`--archive '${options.archive}'`);
  } else {
    args.push(`--url '${artifact.url}'`);
  }
  const result = await execSSH(connectionDetails, teamKey, args.join(' '));
  if (result.code !== 0) {
    throw new ValidationError(
      t('errors.vscode.serverInstallFailed', {
        provider: provider.id,
        error: result.stderr.trim().split('\n').slice(-3).join(' ') || `exit ${result.code}`,
      })
    );
  }
}

/**
 * State dir for a provider inside the overlay home (single-quoted shell-safe).
 * Includes the repository GUID: every repo's overlay home mounts at the
 * IDENTICAL `/home/rediacc`, so without the guid the state-dir path string is
 * the same across all repos — making `find_server_pids` (which matches that
 * path in /proc cmdlines) cross-match servers from other repos and reuse the
 * wrong one. The guid makes the path string unique per repo.
 */
function stateDirExpr(provider: VSCodeServerProvider, repoGuid: string | undefined): string {
  // repoGuid is always set for repo-scoped vscode serve commands; the empty
  // fallback is purely defensive (`?? ''` is the lint-allowed nullish default).
  return `${STATE_ROOT}/${provider.id}/${repoGuid ?? ''}`;
}

/**
 * Shell snippet defining `find_server_pids` — every PID whose /proc cmdline
 * carries BOTH the provider install dir AND this server's state dir.
 *
 * The recorded `$!` pidfile is unreliable: openvscode's launcher re-execs /
 * forks, so the recorded PID exits while the real server (a child with a
 * different PID) keeps running — which made the old pid-only stop report
 * "not running" and leak a port-bound, data-dir-locking zombie every render.
 * Matching on the immutable `--server-data-dir <state>` argument (unique per
 * repo+provider) finds the actual server regardless of fork/re-exec. Excludes
 * this shell ($$) and its parent so the kill script can't match itself (its
 * own cmdline embeds both marker strings).
 */
function findServerPidsFn(provider: VSCodeServerProvider, state: string): string {
  return `
find_server_pids() {
  local d pid c
  for d in /proc/[0-9]*; do
    pid="\${d##*/}"
    [ "$pid" = "$$" ] && continue
    [ "$pid" = "$PPID" ] && continue
    c="$(tr '\\0' ' ' < "$d/cmdline" 2>/dev/null)" || continue
    case "$c" in *'${provider.installDir()}'*) ;; *) continue ;; esac
    case "$c" in *'${state}'*) echo "$pid" ;; esac
  done
}`;
}

/** Swap the placeholder port (0) in a launch arg for the remote __PORT__ marker. */
function portPlaceholder(arg: string): string {
  if (arg === '0') {
    return '__PORT__';
  }
  if (arg === '127.0.0.1:0') {
    return '127.0.0.1:__PORT__';
  }
  return arg;
}

/** Deterministic per-repo base port so status/stop/reuse agree across runs. */
export function deriveRemotePort(repositoryGuid: string, providerId: string): number {
  let hash = 2166136261;
  for (const ch of `${repositoryGuid}:${providerId}`) {
    hash ^= ch.charCodeAt(0);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return REMOTE_PORT_BASE + (hash % REMOTE_PORT_SPAN);
}

/**
 * Launch (or reuse) the server inside the repo sandbox. Returns the remote
 * port and the per-launch secret. The remote script:
 *  - reuses a live pidfile whose cmdline matches the provider install
 *  - otherwise picks the first free port in the probe window, seeds
 *    settings, writes token/port/pid files (0600) and nohups the server
 */
export async function launchServer(
  provider: VSCodeServerProvider,
  connectionDetails: ConnectionDetails,
  options: { repoName: string }
): Promise<ServerLaunchResult> {
  if (!connectionDetails.repositoryGuid || !connectionDetails.workingDirectory) {
    throw new ValidationError(t('errors.vscode.repoRequired'));
  }
  const state = stateDirExpr(provider, connectionDetails.repositoryGuid);
  const basePort = deriveRemotePort(connectionDetails.repositoryGuid, provider.id);
  const secret = randomBytes(24).toString('base64url');
  const usesToken = provider.auth.kind === 'url-token';
  const passwordEnv = provider.auth.kind === 'password-env' ? provider.auth.envVar : '';

  const seedCommands = provider
    .seedSettings({ repoName: options.repoName })
    .map((file) => {
      const target = `${state}/${file.relPath}`;
      const payload = JSON.stringify(file.json).replaceAll("'", "'\\''");
      return `mkdir -p "$(dirname "${target}")"; [ -f "${target}" ] || printf '%s' '${payload}' > "${target}"`;
    })
    .join('\n');

  // Placeholder values; the real argv is assembled remotely with the chosen
  // port substituted into the launch arguments.
  const argvTemplate = provider
    .launchArgs({
      port: 0,
      stateDir: state,
      tokenFile: usesToken ? `${state}/token` : undefined,
    })
    .map(portPlaceholder)
    .map((a) => `'${a.replaceAll("'", "'\\''")}'`)
    .join(' ');

  const script = `
set -e
STATE="${state}"
mkdir -p "$STATE"
chmod 700 "$STATE"
${findServerPidsFn(provider, state)}

# Reuse a live server (matched by install dir + state data-dir in its cmdline,
# not the unreliable recorded pid) so we never leak a duplicate.
if [ -n "$(find_server_pids | head -1)" ] && [ -s "$STATE/port" ] && [ -s "$STATE/secret" ]; then
  echo "VSCODE_SERVER reused=1 port=$(cat "$STATE/port") secret=$(cat "$STATE/secret")"
  exit 0
fi

# Pick the first free port in the probe window.
PORT=""
for i in $(seq 0 9); do
  CAND=$((${basePort} + i))
  if ! (exec 3<>"/dev/tcp/127.0.0.1/$CAND") 2>/dev/null; then PORT="$CAND"; break; fi
  exec 3>&- 2>/dev/null || true
done
[ -n "$PORT" ] || { echo "no free port in window" >&2; exit 1; }

umask 077
printf '%s' '${secret}' > "$STATE/secret"
printf '%s' "$PORT" > "$STATE/port"
${usesToken ? `cp "$STATE/secret" "$STATE/token"` : ':'}
${seedCommands}

ARGS="${argvTemplate}"
ARGS="\${ARGS//__PORT__/$PORT}"
${passwordEnv ? `export ${passwordEnv}='${secret}'` : ':'}
eval "nohup '${provider.serverBinary()}' $ARGS >> '$STATE/server.log' 2>&1 &"
echo $! > "$STATE/server.pid"
echo "VSCODE_SERVER reused=0 port=$PORT secret=${secret}"
`;

  // Run under bash explicitly: the launch script uses bash-only features
  // (parameter-expansion replacement ${ARGS//__PORT__/$PORT}); if the remote
  // login shell is dash/sh it would fail. Single-quote-escape the script body.
  const result = await execSSH(
    connectionDetails,
    connectionDetails.privateKey,
    `bash -c 'eval "$1"' -- '${script.replaceAll("'", "'\\''")}'`
  );
  const line = result.stdout.split('\n').find((l) => l.startsWith('VSCODE_SERVER '));
  if (result.code !== 0 || !line) {
    debugLog(`vscode server launch stderr: ${result.stderr}`);
    throw new ValidationError(
      t('errors.vscode.serverStartFailed', {
        provider: provider.id,
        error: result.stderr.trim().split('\n').slice(-3).join(' ') || `exit ${result.code}`,
      })
    );
  }
  const fields = Object.fromEntries(
    line
      .slice('VSCODE_SERVER '.length)
      .split(' ')
      .map((kv) => kv.split('=', 2) as [string, string])
  );
  return {
    remotePort: Number(fields.port),
    secret: fields.secret,
    reused: fields.reused === '1',
  };
}

export interface ServerStatus {
  running: boolean;
  remotePort?: number;
  pid?: number;
}

export async function serverStatus(
  provider: VSCodeServerProvider,
  connectionDetails: ConnectionDetails
): Promise<ServerStatus> {
  const state = stateDirExpr(provider, connectionDetails.repositoryGuid);
  const script = `${findServerPidsFn(provider, state)}
PID="$(find_server_pids | head -1)"
if [ -n "$PID" ]; then
  echo "VSCODE_STATUS running=1 pid=$PID port=$(cat "${state}/port" 2>/dev/null)"
else
  echo "VSCODE_STATUS running=0"
fi
`;
  const result = await execSSH(connectionDetails, connectionDetails.privateKey, script);
  const line = result.stdout.split('\n').find((l) => l.startsWith('VSCODE_STATUS '));
  if (!line) return { running: false };
  const fields = Object.fromEntries(
    line
      .slice('VSCODE_STATUS '.length)
      .split(' ')
      .map((kv) => kv.split('=', 2) as [string, string])
  );
  if (fields.running !== '1') return { running: false };
  return { running: true, pid: Number(fields.pid), remotePort: Number(fields.port) };
}

/** Stop the server: TERM (cmdline-verified pid), wait, KILL fallback. */
export async function stopServer(
  provider: VSCodeServerProvider,
  connectionDetails: ConnectionDetails
): Promise<boolean> {
  const state = stateDirExpr(provider, connectionDetails.repositoryGuid);
  const script = `${findServerPidsFn(provider, state)}
PIDS="$(find_server_pids)"
rm -f "${state}/server.pid"
if [ -z "$PIDS" ]; then echo "VSCODE_STOP stopped=0"; exit 0; fi
for PID in $PIDS; do kill -TERM "$PID" 2>/dev/null || true; done
for i in $(seq 1 10); do
  REMAIN="$(find_server_pids)"
  [ -z "$REMAIN" ] && break
  sleep 0.5
done
for PID in $(find_server_pids); do kill -KILL "$PID" 2>/dev/null || true; done
echo "VSCODE_STOP stopped=1"
`;
  const result = await execSSH(connectionDetails, connectionDetails.privateKey, script);
  return result.stdout.includes('VSCODE_STOP stopped=1');
}

/** Poll the forwarded local port for the provider's HTTP ready signature. */
export async function waitForHttpReady(
  provider: VSCodeServerProvider,
  localPort: number,
  timeoutMs: number
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  const url = `http://127.0.0.1:${localPort}${provider.readyCheck.path}`;
  while (Date.now() < deadline) {
    const status = await new Promise<number | null>((resolve) => {
      const req = http.get(url, (res) => {
        res.resume();
        resolve(res.statusCode ?? null);
      });
      req.on('error', () => resolve(null));
      req.setTimeout(2000, () => {
        req.destroy();
        resolve(null);
      });
    });
    if (status !== null && provider.readyCheck.expectStatus.includes(status)) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}
