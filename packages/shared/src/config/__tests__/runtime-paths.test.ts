import { describe, expect, it } from 'vitest';
import {
  legacyRepoDockerSocketPath,
  REPO_NET_DIR_PATTERN,
  repoDockerHost,
  repoDockerSocketFallbackShell,
  repoDockerSocketPath,
  repoNetDir,
  repoSecretsDir,
} from '../runtime-paths.js';

// The literals below are the contract with renet's pkg/runpaths, whose test pins the same strings. Spelled out on purpose: building them from WK_RUNTIME_DIR here would let a drift on both sides pass.
describe('per-network runtime paths', () => {
  it('puts the Docker socket inside the network directory, keeping its basename', () => {
    expect(repoDockerSocketPath(7104)).toBe('/var/run/rediacc/net-7104/docker-7104.sock');
    expect(repoDockerSocketPath('7104')).toBe('/var/run/rediacc/net-7104/docker-7104.sock');
  });

  it('derives the network directory, DOCKER_HOST and secrets directory from the same root', () => {
    expect(repoNetDir(7104)).toBe('/var/run/rediacc/net-7104');
    expect(repoDockerHost(7104)).toBe('unix:///var/run/rediacc/net-7104/docker-7104.sock');
    expect(repoSecretsDir(7104)).toBe('/var/run/rediacc/net-7104/secrets');
  });

  it.each([0, -1, '', 'abc', '7104/../7105', '07104', 3.5])(
    'refuses a network id that is not a positive integer: %j',
    (networkId) => {
      expect(() => repoDockerSocketPath(networkId)).toThrow(/Invalid network id/);
    }
  );

  it('recognises a path inside some network directory and nothing else', () => {
    expect(REPO_NET_DIR_PATTERN.test('/var/run/rediacc/net-7104/secrets/KEY')).toBe(true);
    expect(REPO_NET_DIR_PATTERN.test('/var/run/rediacc/net-7104/docker-7104.sock')).toBe(true);
    expect(REPO_NET_DIR_PATTERN.test('/var/run/rediacc/docker-7104.sock')).toBe(false);
    expect(REPO_NET_DIR_PATTERN.test('/var/run/rediacc/net-x/docker.sock')).toBe(false);
  });
});

describe('the flat-socket fallback for a daemon on the old layout', () => {
  const derived = {
    REDIACC_NETWORK_ID: '3136',
    DOCKER_SOCKET: '/var/run/rediacc/net-3136/docker-3136.sock',
    DOCKER_HOST: 'unix:///var/run/rediacc/net-3136/docker-3136.sock',
  };

  it('spells the flat path the old renet serves', () => {
    expect(legacyRepoDockerSocketPath(3136)).toBe('/var/run/rediacc/docker-3136.sock');
  });

  it('switches to the flat socket only when the net-<N> socket is absent and the flat one is a socket', () => {
    expect(repoDockerSocketFallbackShell(derived)).toBe(
      "if [ ! -S '/var/run/rediacc/net-3136/docker-3136.sock' ] && [ -S '/var/run/rediacc/docker-3136.sock' ]; then " +
        "export DOCKER_SOCKET='/var/run/rediacc/docker-3136.sock' DOCKER_HOST='unix:///var/run/rediacc/docker-3136.sock'; fi"
    );
  });

  it.each([
    ['no network id', { ...derived, REDIACC_NETWORK_ID: '' }],
    ['a malformed network id', { ...derived, REDIACC_NETWORK_ID: '3136; rm -rf /' }],
    ['a socket the vault names', { ...derived, DOCKER_SOCKET: '/srv/custom.sock' }],
    ['a DOCKER_HOST the vault names', { ...derived, DOCKER_HOST: 'tcp://10.0.0.1:2375' }],
  ])('emits nothing for %s', (_label, environment) => {
    expect(repoDockerSocketFallbackShell(environment)).toBe('');
  });
});
