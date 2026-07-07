import { describe, expect, it } from 'vitest';
import type { ConnectionDetails } from '../../services/machine/ssh-connection.js';
import { buildEnvPrefix } from '../term.js';

// The `--cluster -r <repo>` term session is the k8s analog of a docker-repo
// session: KUBECONFIG replaces DOCKER_HOST and a kubectl namespace pin replaces
// the repo `cd`. buildEnvPrefix is the one place that shell preamble is built.
function details(over: Partial<ConnectionDetails>): ConnectionDetails {
  return {
    host: 'h',
    user: 'root',
    port: 22,
    privateKey: 'k',
    known_hosts: 'kh',
    datastore: '/mnt/rediacc',
    universalUser: 'u',
    ...over,
  };
}

describe('buildEnvPrefix — cluster namespace pin', () => {
  it('emits a namespace set-context after exporting KUBECONFIG', () => {
    const prefix = buildEnvPrefix(
      details({
        environment: { KUBECONFIG: '/mnt/rediacc/mounts/prod/.rediacc/k3s/kubeconfig.yaml' },
        kubeNamespace: 'shop',
        workingDirectory: '/mnt/rediacc',
      })
    );
    expect(prefix).toContain(
      "export KUBECONFIG='/mnt/rediacc/mounts/prod/.rediacc/k3s/kubeconfig.yaml'"
    );
    expect(prefix).toContain(
      "kubectl config set-context --current --namespace='shop' >/dev/null 2>&1 || true"
    );
    // KUBECONFIG must be exported before the set-context that relies on it.
    const kubeconfigAt = prefix.indexOf('export KUBECONFIG');
    const setContextAt = prefix.indexOf('kubectl config set-context');
    expect(kubeconfigAt).toBeGreaterThanOrEqual(0);
    expect(setContextAt).toBeGreaterThan(kubeconfigAt);
  });

  it('does not emit a set-context when no namespace is pinned (machine target)', () => {
    const prefix = buildEnvPrefix(
      details({ environment: { DOCKER_HOST: 'unix:///sock' }, workingDirectory: '/home/app' })
    );
    expect(prefix).not.toContain('kubectl config set-context');
    expect(prefix).toContain("cd '/home/app' 2>/dev/null");
  });

  it('escapes single quotes in the namespace to keep the preamble shell-safe', () => {
    const prefix = buildEnvPrefix(details({ kubeNamespace: "a'b" }));
    expect(prefix).toContain("--namespace='a'\\''b'");
  });
});
