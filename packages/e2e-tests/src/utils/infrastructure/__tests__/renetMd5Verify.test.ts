import { beforeEach, describe, expect, it, vi } from 'vitest';
import { InfrastructureManager } from '../InfrastructureManager';

const LOCAL = 'a'.repeat(32);
const OTHER = 'b'.repeat(32);

const { IP, executeOnVM, waitForHost } = vi.hoisted(() => ({
  IP: '192.168.111.22',
  executeOnVM:
    vi.fn<
      (ip: string, command: string) => Promise<{ stdout: string; stderr: string; code: number }>
    >(),
  waitForHost: vi.fn<(host: string, timeoutMs?: number, intervalMs?: number) => Promise<boolean>>(),
}));

vi.mock('../../bridge/OpsManager', () => ({
  getOpsManager: () => ({
    getBridgeVMIp: () => IP,
    getWorkerVMIps: () => [IP],
    getAllVMIps: () => [IP],
    executeOnVM,
  }),
}));
vi.mock('../../RenetResolver', () => ({ getRenetResolver: () => ({}) }));
vi.mock('../../ssh', () => ({ getSSHExecutor: () => ({ waitForHost }) }));

const REFUSED = {
  stdout: '',
  stderr: `ssh: connect to host ${IP} port 22: Connection refused`,
  code: 255,
};

type Verifier = { verifyRemoteRenetMD5(ip: string, md5: string): Promise<void> };
const verify = (): Promise<void> =>
  (new InfrastructureManager() as unknown as Verifier).verifyRemoteRenetMD5(IP, LOCAL);

describe('InfrastructureManager post-deploy renet MD5 verification', () => {
  beforeEach(() => {
    executeOnVM.mockReset();
    waitForHost.mockReset();
    waitForHost.mockResolvedValue(true);
  });

  it('passes after one SSH refusal once the host answers again', async () => {
    executeOnVM
      .mockResolvedValueOnce(REFUSED)
      .mockResolvedValueOnce({ stdout: `${LOCAL}\n`, stderr: '', code: 0 });
    await expect(verify()).resolves.toBeUndefined();
    expect(waitForHost).toHaveBeenCalledTimes(1);
    expect(executeOnVM).toHaveBeenCalledTimes(2);
  });

  it('names the transport failure and its stderr when the refusal persists', async () => {
    executeOnVM.mockResolvedValue(REFUSED);
    const error = await verify().catch((e: Error) => e);
    expect(error).toBeInstanceOf(Error);
    const message = (error as Error).message;
    expect(message).toContain('SSH transport failure');
    expect(message).toContain('exit 255');
    expect(message).toContain('Connection refused');
    expect(message).not.toContain('remote=null');
    expect(waitForHost.mock.calls.length).toBeGreaterThan(1);
  });

  it('fails at once on a real mismatch without retrying', async () => {
    executeOnVM.mockResolvedValue({ stdout: `${OTHER}\n`, stderr: '', code: 0 });
    await expect(verify()).rejects.toThrow(`local=${LOCAL}, remote=${OTHER}`);
    expect(executeOnVM).toHaveBeenCalledTimes(1);
    expect(waitForHost).not.toHaveBeenCalled();
  });

  it('fails at once when the binary is missing and ssh itself worked', async () => {
    executeOnVM.mockResolvedValue({ stdout: '', stderr: '', code: 0 });
    await expect(verify()).rejects.toThrow('remote=null');
    expect(executeOnVM).toHaveBeenCalledTimes(1);
  });
});

type Step = { success: boolean; code: number; stderr: string };
type Retrier = { retryOnceOnTransportFailure(ip: string, run: () => Promise<Step>): Promise<Step> };
const retry = (run: () => Promise<Step>): Promise<Step> =>
  (new InfrastructureManager() as unknown as Retrier).retryOnceOnTransportFailure(IP, run);

describe('InfrastructureManager post-deploy MD5 check on an unreachable network', () => {
  beforeEach(() => {
    executeOnVM.mockReset();
    waitForHost.mockReset();
    waitForHost.mockResolvedValue(true);
  });

  it('waits and reads again when ssh reports the network unreachable', async () => {
    executeOnVM
      .mockResolvedValueOnce({
        stdout: '',
        stderr: `ssh: connect to host ${IP} port 22: Network is unreachable`,
        code: 1,
      })
      .mockResolvedValueOnce({ stdout: `${LOCAL}\n`, stderr: '', code: 0 });
    await expect(verify()).resolves.toBeUndefined();
    expect(waitForHost).toHaveBeenCalledTimes(1);
  });

  it('does not read a remote message that merely says "host is down" as a transport failure', async () => {
    executeOnVM.mockResolvedValue({
      stdout: '',
      stderr: 'md5sum: the host is down for maintenance',
      code: 1,
    });
    const error = await verify().catch((e: Error) => e);
    expect(error).toBeInstanceOf(Error);
    expect(waitForHost).not.toHaveBeenCalled();
  });
});

describe('InfrastructureManager install step retry', () => {
  beforeEach(() => {
    waitForHost.mockReset();
    waitForHost.mockResolvedValue(true);
  });

  it('re-runs an idempotent step once after a transport refusal', async () => {
    const run = vi
      .fn<() => Promise<Step>>()
      .mockResolvedValueOnce({ success: false, code: 255, stderr: REFUSED.stderr })
      .mockResolvedValueOnce({ success: true, code: 0, stderr: '' });
    await expect(retry(run)).resolves.toMatchObject({ success: true });
    expect(run).toHaveBeenCalledTimes(2);
    expect(waitForHost).toHaveBeenCalledTimes(1);
  });

  it('does not re-run a step whose command failed on a working connection', async () => {
    const run = vi.fn<() => Promise<Step>>().mockResolvedValue({
      success: false,
      code: 1,
      stderr: 'install: cannot stat /var/tmp/renet',
    });
    await expect(retry(run)).resolves.toMatchObject({ success: false, code: 1 });
    expect(run).toHaveBeenCalledTimes(1);
    expect(waitForHost).not.toHaveBeenCalled();
  });

  it('treats an unreachable network as a transport failure', async () => {
    const run = vi
      .fn<() => Promise<Step>>()
      .mockResolvedValueOnce({
        success: false,
        code: 1,
        stderr: `ssh: connect to host ${IP} port 22: Network is unreachable`,
      })
      .mockResolvedValueOnce({ success: true, code: 0, stderr: '' });
    await expect(retry(run)).resolves.toMatchObject({ success: true });
    expect(run).toHaveBeenCalledTimes(2);
  });
});
