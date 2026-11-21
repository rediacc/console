import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchMachineStatus } from '../machine/machine-status.js';

const { mockExecStreaming, mockAcquire, mockConfigService, mockAcquireRenet, mockExecute } =
  vi.hoisted(() => {
    const mockExecStreaming = vi.fn();
    const sftp = { execStreaming: mockExecStreaming };
    const mockRelease = vi.fn();
    const mockAcquire = vi.fn().mockResolvedValue({
      sftp,
      machine: { machineName: 'm1', ip: '127.0.0.1', user: 'root', port: 22 },
      sshPrivateKey: 'dummy-key',
      ensure: vi.fn().mockResolvedValue(sftp),
      release: mockRelease,
    });
    return {
      mockExecStreaming,
      mockAcquire,
      mockExecute: vi.fn(),
      mockConfigService: { getLocalConfig: vi.fn() },
      mockAcquireRenet: vi
        .fn()
        .mockResolvedValue({ remotePath: '/usr/lib/rediacc/renet/current/renet' }),
    };
  });

vi.mock('../machine/machine-connection.js', () => ({
  machineConnections: { acquire: mockAcquire },
}));

vi.mock('../config/config-resources.js', () => ({
  configService: mockConfigService,
}));

vi.mock('../renet/renet-execution.js', () => ({
  acquireRemoteRenet: mockAcquireRenet,
}));

vi.mock('../executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));

describe('fetchMachineStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockConfigService.getLocalConfig.mockResolvedValue({
      machines: { m1: { ip: '127.0.0.1', user: 'root', port: 22 } },
    });
    mockExecute.mockResolvedValue({
      success: true,
      exitCode: 0,
      stdout: JSON.stringify({ containers: [] }),
    });
  });

  it('makes one list-all job, with no client-side renet command and no pooled connection', async () => {
    const result = await fetchMachineStatus('m1');

    expect(result).toEqual({ containers: [] });
    expect(mockExecute).toHaveBeenCalledTimes(1);
    expect(mockExecute.mock.calls[0][0]).toMatchObject({
      functionName: 'list-all',
      machineName: 'm1',
      commandKind: { name: 'list-all', args: { datastore: WK_DATASTORE_PATH } },
      captureOutput: true,
      probe: true,
    });
    expect(mockAcquire).not.toHaveBeenCalled();
    expect(mockExecStreaming).not.toHaveBeenCalled();
    expect(mockAcquireRenet).not.toHaveBeenCalled();
  });

  it('uses the machine datastore when it names one', async () => {
    mockConfigService.getLocalConfig.mockResolvedValue({
      machines: { m1: { ip: '127.0.0.1', user: 'root', port: 22, datastore: '/mnt/other' } },
    });

    await fetchMachineStatus('m1');

    expect(mockExecute.mock.calls[0][0].commandKind.args).toEqual({ datastore: '/mnt/other' });
  });

  it('passes the sections filter through the job args', async () => {
    await fetchMachineStatus('m1', { sections: ['system', 'repositories'] });

    expect(mockExecute.mock.calls[0][0].commandKind.args).toEqual({
      datastore: WK_DATASTORE_PATH,
      sections: 'system,repositories',
    });
  });

  it('omits sections for an empty filter', async () => {
    await fetchMachineStatus('m1', { sections: [] });

    expect(mockExecute.mock.calls[0][0].commandKind.args).not.toHaveProperty('sections');
  });

  it('names the parse failure when the job succeeds with no stdout', async () => {
    mockExecute.mockResolvedValue({ success: true, exitCode: 0 });

    await expect(fetchMachineStatus('m1')).rejects.toThrow('Failed to parse renet output');
  });

  it('throws with the job stderr when the job fails', async () => {
    mockExecute.mockResolvedValue({ success: false, exitCode: 1, stderr: 'boom' });

    await expect(fetchMachineStatus('m1')).rejects.toThrow('renet list all failed (exit 1): boom');
  });

  it('rejects unknown machines before any job', async () => {
    await expect(fetchMachineStatus('nope')).rejects.toThrow('Machine "nope" not found');
    expect(mockExecute).not.toHaveBeenCalled();
  });
});
