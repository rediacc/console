import { describe, expect, it, vi } from 'vitest';
import { KubeMethods } from '../renet-functions/methods/KubeMethods';
import { RenetFunctionsTestRunner } from '../renet-functions/RenetFunctionsTestRunner';
import { buildTokenVault } from '../renet-functions/tokenVault';

const TOKEN = 'K10abcdef0123456789::server:s3cr3t-join-token';

interface Bridge {
  executeViaBridge: (
    cmd: string,
    timeout?: number,
    options?: { stdin?: string }
  ) => Promise<{ stdout: string; stderr: string; code: number }>;
}

function spyRunner() {
  // The constructor needs a live ops manager; the command building under test does not.
  const runner = Object.create(RenetFunctionsTestRunner.prototype) as unknown as Bridge &
    Pick<RenetFunctionsTestRunner, 'testFunction'>;
  const calls: { cmd: string; stdin?: string }[] = [];
  runner.executeViaBridge = vi.fn((cmd, _timeout, options) => {
    calls.push({ cmd, stdin: options?.stdin });
    return Promise.resolve({ stdout: '', stderr: '', code: 0 });
  });
  return { kube: new KubeMethods((opts) => runner.testFunction(opts)), calls };
}

describe('buildTokenVault', () => {
  it('carries the token and the kube_join params the flags carried', () => {
    const vault = JSON.parse(
      buildTokenVault(
        {
          function: 'kube_join',
          token: TOKEN,
          mountPath: '/m',
          role: 'agent',
          endpoint: 'https://10.0.0.1:6443',
          bindIp: '10.0.0.2',
        },
        '2816'
      )
    );
    expect(vault.task.function).toBe('kube_join');
    expect(vault.params).toMatchObject({
      token: TOKEN,
      mount_path: '/m',
      role: 'agent',
      endpoint: 'https://10.0.0.1:6443',
      bind_ip: '10.0.0.2',
      network_id: 2816,
    });
  });

  it('refuses an option the vault does not carry rather than dropping it', () => {
    expect(() => buildTokenVault({ function: 'kube_join', token: TOKEN, pool: 'p' }, '1')).toThrow(
      /pool/
    );
  });
});

describe('testFunction with a token', () => {
  it('keeps the token out of every command and sends it on stdin', async () => {
    const { kube, calls } = spyRunner();
    await kube.kubeJoin({
      mountPath: '/m',
      networkId: '2816',
      role: 'agent',
      token: TOKEN,
      endpoint: 'https://10.0.0.1:6443',
    });
    expect(calls.length).toBeGreaterThanOrEqual(2);
    for (const call of calls) {
      expect(call.cmd).not.toContain(TOKEN);
      expect(call.cmd).not.toContain('s3cr3t');
      expect(call.cmd).not.toContain('--token');
    }
    const upload = calls.find((call) => call.stdin !== undefined);
    expect(upload?.stdin).toContain(TOKEN);
    expect(calls.some((call) => call.cmd.includes('--function kube_join --vault-file'))).toBe(true);
  });

  it('does the same for kube_identity_rewrite', async () => {
    const { kube, calls } = spyRunner();
    await kube.kubeIdentityRewrite({
      mountPath: '/m',
      operation: 'migrate',
      newNodeIp: '10.0.0.3',
      server: 'https://10.0.0.1:6443',
      token: TOKEN,
    });
    expect(calls.every((call) => !call.cmd.includes(TOKEN))).toBe(true);
    expect(calls.find((call) => call.stdin !== undefined)?.stdin).toContain(TOKEN);
  });
});
