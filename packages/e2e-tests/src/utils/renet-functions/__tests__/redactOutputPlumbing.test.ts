import { promisify } from 'node:util';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const SECRET = 'K10abcdef0123456789::server:s3cr3t-join-token';

const h = vi.hoisted(() => ({
  lines: [] as string[],
  // Each entry decides one exec call: resolve with output, or reject the way child_process does.
  script: [] as Array<{ stdout?: string; stderr?: string; fail?: { code: number } }>,
  commands: [] as string[],
}));

vi.mock('node:child_process', () => {
  const exec = Object.assign(() => undefined, {
    [promisify.custom]: (command: string) => {
      h.commands.push(command);
      const step = h.script.shift() ?? {};
      const outcome = step.fail
        ? Promise.reject(
            Object.assign(new Error('failed'), {
              code: step.fail.code,
              stdout: step.stdout ?? '',
              stderr: step.stderr ?? '',
            })
          )
        : Promise.resolve({ stdout: step.stdout ?? '', stderr: step.stderr ?? '' });
      return Object.assign(outcome, { child: { stdin: null } });
    },
  });
  return { exec };
});
vi.mock('../../log', () => ({ log: (...args: unknown[]) => h.lines.push(args.join(' ')) }));
vi.mock('../../ssh', () => ({
  getSSHExecutor: () => ({
    escapeForNestedSSH: (c: string) => c,
    getSSHOptions: () => '',
    getInnerSSHOptions: () => '',
  }),
  SSHExecutor: class {},
}));
vi.mock('../OpsManager', () => ({
  getOpsManager: () => ({ getBridgeVMIp: () => '10.0.0.1' }),
  OpsManager: class {},
}));

import { RenetFunctionsTestRunner } from '../RenetFunctionsTestRunner';

const logged = () => h.lines.join('\n');

function makeRunner(): RenetFunctionsTestRunner {
  process.env.BRIDGE_TIMEOUT = '1000';
  process.env.USER ??= 'tester';
  return new RenetFunctionsTestRunner({ targetVM: '10.0.0.2' });
}

describe('redactOutput plumbing through the runner', () => {
  beforeEach(() => {
    h.lines.length = 0;
    h.script.length = 0;
    h.commands.length = 0;
  });

  it('testFunction -> executeViaBridge success: logs a byte count, returns the secret', async () => {
    h.script.push({ stdout: SECRET, stderr: `warn ${SECRET}` });
    const result = await makeRunner().testFunction({
      function: 'kube_join_token',
      redactOutput: true,
    });
    expect(result.stdout).toBe(SECRET);
    expect(logged()).not.toContain('s3cr3t');
    expect(logged()).toContain(`[STDOUT] ${SECRET.length} bytes (redacted)`);
  });

  it('logs the secret verbatim when the flag is absent (the control)', async () => {
    h.script.push({ stdout: SECRET });
    await makeRunner().testFunction({ function: 'kube_join_token' });
    expect(logged()).toContain(SECRET);
  });

  it('executeViaBridge failure path redacts too', async () => {
    h.script.push({ stdout: SECRET, stderr: SECRET, fail: { code: 3 } });
    const result = await makeRunner().executeViaBridge('renet x', undefined, {
      redactOutput: true,
    });
    expect(result.code).toBe(3);
    expect(logged()).not.toContain('s3cr3t');
    expect(logged()).toContain('[EXIT] 3');
  });

  it('the executeOnVM fallback keeps redacting', async () => {
    h.script.push({ stderr: 'renet: command not found', fail: { code: 127 } });
    h.script.push({ stdout: SECRET });
    const result = await makeRunner().executeViaBridge('renet x', undefined, {
      redactOutput: true,
    });
    expect(result.stdout).toBe(SECRET);
    expect(h.commands).toHaveLength(2);
    expect(logged()).toContain('Falling back to direct SSH');
    expect(logged()).not.toContain('s3cr3t');
  });

  it('executeOnVM redacts when asked', async () => {
    h.script.push({ stdout: SECRET });
    await makeRunner().executeOnVM('10.0.0.2', 'renet x', undefined, { redactOutput: true });
    expect(logged()).not.toContain('s3cr3t');
  });
});

describe('testFunction rejects instead of throwing synchronously', () => {
  it('an unsupported option on a password call is a rejected promise', async () => {
    const pending = makeRunner().testFunction({
      function: 'repository_create',
      repository: 'r1',
      password: 'pw',
      mountPath: '/m',
    });
    await expect(pending).rejects.toThrow('password vault cannot carry: mountPath');
  });
});
