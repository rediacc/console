/**
 * Browser VS Code server providers.
 *
 * `rdc vscode connect --browser` serves a web VS Code from INSIDE the repo
 * sandbox: the server binary lives read-only under /usr/lib/rediacc/vscode
 * (visible through the sandbox's Landlock /usr allowance), all mutable state
 * goes to the per-repo overlay home, and the only way in is an SSH -L tunnel
 * over the per-repo gateway key.
 *
 * The provider abstraction exists because the server implementation is
 * swappable (openvscode-server today, code-server or other OSS forks
 * tomorrow). Everything implementation-specific — artifact pins, launch
 * argv, auth mechanism, URL shape, ready probe, settings seeding — lives
 * behind this interface; install/launch/tunnel orchestration is shared.
 *
 * Licensing note: only redistributable servers belong here (openvscode and
 * code-server are MIT). Microsoft's `code serve-web` server bits are NOT
 * redistributable and must never become a provider.
 */

export type ServerPlatform = 'linux-x64' | 'linux-arm64';

export interface ServerArtifact {
  /** Pinned release URL (mirror to R2 by changing only this). */
  url: string;
  /** sha256 of the tarball — verified by `renet vscode-server install`. */
  sha256: string;
  /** tar --strip-components depth so binaries land directly in installDir. */
  stripComponents: number;
}

export type ServerAuth =
  /** Token carried in the URL (`?tkn=`), file-fed to the server. */
  | { kind: 'url-token' }
  /** Password fed via environment variable; cookie session after login. */
  | { kind: 'password-env'; envVar: string }
  | { kind: 'none' };

export interface LaunchOptions {
  /** Loopback port the server binds on the machine. */
  port: number;
  /** Mutable state root in the overlay home (data dir, logs, pidfile). */
  stateDir: string;
  /** Absolute path of the token file (url-token providers). */
  tokenFile?: string;
}

export interface BuildUrlOptions {
  /** Local base, e.g. `http://localhost:9341`. */
  base: string;
  /** Absolute remote folder to open (the repo mount path). */
  folder: string;
  /** Token value for url-token providers. */
  token?: string;
}

export interface SeededFile {
  /** Path relative to the provider state dir. */
  relPath: string;
  /** JSON content written only when the file does not exist yet. */
  json: Record<string, unknown>;
}

export interface VSCodeServerProvider {
  id: string;
  version: string;
  artifact(platform: ServerPlatform): ServerArtifact;
  /** Read-only shared install dir: /usr/lib/rediacc/vscode/<id>/<version>. */
  installDir(): string;
  /** Absolute path of the server entry binary inside installDir. */
  serverBinary(): string;
  auth: ServerAuth;
  launchArgs(options: LaunchOptions): string[];
  launchEnv(options: { password?: string }): Record<string, string>;
  buildUrl(options: BuildUrlOptions): string;
  /** HTTP probe configuration for "server is up". */
  readyCheck: { path: string; expectStatus: number[] };
  /** First-run settings written into the state dir (never overwritten). */
  seedSettings(options: { repoName: string }): SeededFile[];
}

/** Shared base for install paths — must stay under the sandbox-readable /usr. */
export const VSCODE_SERVER_INSTALL_ROOT = '/usr/lib/rediacc/vscode';

/** Default workbench settings shared by all providers. */
export function baseSeedSettings(repoName: string): Record<string, unknown> {
  return {
    'security.workspace.trust.enabled': false,
    'workbench.startupEditor': 'none',
    'telemetry.telemetryLevel': 'off',
    'update.mode': 'none',
    'chat.commandCenter.enabled': false,
    // Show the repo name instead of the GUID mount path.
    'window.title': `${repoName}\${separator}\${activeEditorShort}`,
  };
}
