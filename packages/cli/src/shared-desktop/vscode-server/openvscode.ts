import {
  baseSeedSettings,
  VSCODE_SERVER_INSTALL_ROOT,
  type SeededFile,
  type ServerArtifact,
  type ServerPlatform,
  type VSCodeServerProvider,
} from './types.js';

const VERSION = '1.109.5';

// Pinned release assets. sha256 values come from the GitHub release digests;
// verify with `sha256sum` when bumping. Mirroring to R2 later only changes
// the URLs.
const ARTIFACTS: Record<ServerPlatform, ServerArtifact> = {
  'linux-x64': {
    url: `https://github.com/gitpod-io/openvscode-server/releases/download/openvscode-server-v${VERSION}/openvscode-server-v${VERSION}-linux-x64.tar.gz`,
    sha256: 'b433bf4f0227321a7014d8460d10a8f958adc0f45aa79bd889e84e65e8f88363',
    stripComponents: 1,
  },
  'linux-arm64': {
    url: `https://github.com/gitpod-io/openvscode-server/releases/download/openvscode-server-v${VERSION}/openvscode-server-v${VERSION}-linux-arm64.tar.gz`,
    sha256: '36d9c14036489b63de84ebace837fcacf7e60e669a0dc715802c5443684ea4dc',
    stripComponents: 1,
  },
};

/**
 * openvscode-server (Gitpod, MIT) — the default browser VS Code provider.
 * Token-in-URL auth makes it the best fit for `--url-only` automation: the
 * printed URL is self-contained and the loopback port rejects strangers.
 */
export const openvscodeProvider: VSCodeServerProvider = {
  id: 'openvscode',
  version: VERSION,

  artifact(platform: ServerPlatform): ServerArtifact {
    return ARTIFACTS[platform];
  },

  installDir(): string {
    return `${VSCODE_SERVER_INSTALL_ROOT}/openvscode/${VERSION}`;
  },

  serverBinary(): string {
    return `${this.installDir()}/bin/openvscode-server`;
  },

  auth: { kind: 'url-token' },

  launchArgs({ port, stateDir, tokenFile }): string[] {
    const args = [
      '--host',
      '127.0.0.1',
      '--port',
      String(port),
      '--server-data-dir',
      `${stateDir}/data`,
      '--disable-telemetry',
    ];
    if (tokenFile) {
      args.push('--connection-token-file', tokenFile);
    } else {
      args.push('--without-connection-token');
    }
    return args;
  },

  launchEnv(): Record<string, string> {
    return {};
  },

  buildUrl({ base, folder, token }): string {
    const params = new URLSearchParams();
    if (token) params.set('tkn', token);
    params.set('folder', folder);
    return `${base}/?${params.toString()}`;
  },

  readyCheck: { path: '/', expectStatus: [200, 302, 403] },

  seedSettings({ repoName }): SeededFile[] {
    const json = baseSeedSettings(repoName);
    return [
      { relPath: 'data/Machine/settings.json', json },
      { relPath: 'data/User/settings.json', json },
    ];
  },
};
