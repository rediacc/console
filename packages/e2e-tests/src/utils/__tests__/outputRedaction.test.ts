import { describe, expect, it, vi } from 'vitest';
import { KubeMethods } from '../renet-functions/methods/KubeMethods';
import { formatExecutionLog } from '../renet-functions/outputRedaction';
import type { ExecResult, TestFunctionOptions } from '../renet-functions/types';

const TOKEN = 'K10abcdef0123456789::server:s3cr3t-join-token';

describe('formatExecutionLog', () => {
  it('logs a secret verbatim when not redacting', () => {
    expect(formatExecutionLog(TOKEN, '', 0).join('\n')).toContain(TOKEN);
  });

  it('never puts a redacted stdout or stderr in the log', () => {
    const logged = formatExecutionLog(TOKEN, `warn ${TOKEN}`, 0, true).join('\n');
    expect(logged).not.toContain(TOKEN);
    expect(logged).not.toContain('s3cr3t');
    expect(logged).toContain(`[STDOUT] ${TOKEN.length} bytes (redacted)`);
    expect(logged).toContain('[EXIT] 0');
  });

  it('counts UTF-8 bytes, not UTF-16 code units', () => {
    const logged = formatExecutionLog('é€', '', 0, true).join('\n');
    expect(logged).toContain('[STDOUT] 5 bytes (redacted)');
  });
});

describe('KubeMethods secret-output verbs', () => {
  it.each([
    ['kubeJoinToken', 'kube_join_token'],
    ['kubeKubeconfig', 'kube_kubeconfig'],
  ] as const)('%s asks the runner to redact and returns the real output', async (method, fn) => {
    const real: ExecResult = { stdout: TOKEN, stderr: '', code: 0 };
    const testFunction = vi.fn((_opts: TestFunctionOptions) => Promise.resolve(real));
    const result = await new KubeMethods(testFunction)[method]({ mountPath: '/m', networkId: '1' });
    expect(testFunction.mock.calls[0][0]).toMatchObject({ function: fn, redactOutput: true });
    expect(result.stdout).toBe(TOKEN);
  });
});
