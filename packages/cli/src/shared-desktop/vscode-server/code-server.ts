import {
  baseSeedSettings,
  VSCODE_SERVER_INSTALL_ROOT,
  type SeededFile,
  type ServerArtifact,
  type ServerPlatform,
  type VSCodeServerProvider,
} from './types.js';

const VERSION = '4.123.0';

const ARTIFACTS: Record<ServerPlatform, ServerArtifact> = {
  'linux-x64': {
    url: `https://github.com/coder/code-server/releases/download/v${VERSION}/code-server-${VERSION}-linux-amd64.tar.gz`,
    sha256: 'e54325a6439652f188203fb80a25c303b87f153550e9eee0c078b798b791d657',
    stripComponents: 1,
  },
  'linux-arm64': {
    url: `https://github.com/coder/code-server/releases/download/v${VERSION}/code-server-${VERSION}-linux-arm64.tar.gz`,
    sha256: '855bdd7b8f522399e951c33a885a138ecf392427fb4464669ee55c9cc8fcb5f3',
    stripComponents: 1,
  },
};

/**
 * code-server (Coder, MIT) — alternate provider. No URL-token mode: auth is
 * a password fed via env (cookie session after the login page), so the CLI
 * prints the password on a separate line instead of embedding it in the URL.
 */
export const codeServerProvider: VSCodeServerProvider = {
  id: 'code-server',
  version: VERSION,

  artifact(platform: ServerPlatform): ServerArtifact {
    return ARTIFACTS[platform];
  },

  installDir(): string {
    return `${VSCODE_SERVER_INSTALL_ROOT}/code-server/${VERSION}`;
  },

  serverBinary(): string {
    return `${this.installDir()}/bin/code-server`;
  },

  auth: { kind: 'password-env', envVar: 'PASSWORD' },

  launchArgs({ port, stateDir }): string[] {
    return [
      '--bind-addr',
      `127.0.0.1:${port}`,
      '--user-data-dir',
      `${stateDir}/data`,
      '--auth',
      'password',
      '--disable-telemetry',
      '--disable-update-check',
      '--disable-workspace-trust',
      '--disable-getting-started-override',
    ];
  },

  launchEnv({ password }): Record<string, string> {
    return password ? { PASSWORD: password } : {};
  },

  buildUrl({ base, folder }): string {
    const params = new URLSearchParams();
    params.set('folder', folder);
    return `${base}/?${params.toString()}`;
  },

  readyCheck: { path: '/', expectStatus: [200, 302] },

  seedSettings({ repoName }): SeededFile[] {
    return [{ relPath: 'data/User/settings.json', json: baseSeedSettings(repoName) }];
  },
};
