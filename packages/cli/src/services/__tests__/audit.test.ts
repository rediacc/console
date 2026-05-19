import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockAccountServerFetch, mockGetSubscriptionTokenState } = vi.hoisted(() => ({
  mockAccountServerFetch: vi.fn(),
  mockGetSubscriptionTokenState: vi.fn(),
}));

vi.mock('../account-client.js', () => ({
  accountServerFetch: mockAccountServerFetch,
}));

vi.mock('../subscription-auth.js', () => ({
  getSubscriptionTokenState: mockGetSubscriptionTokenState,
}));

vi.mock('../../version.js', () => ({
  VERSION: '1.0.0-test',
}));

const { auditService, functionNameToEventType } = await import('../audit.js');

describe('functionNameToEventType', () => {
  it('maps repository_ prefix to cli.repo.*', () => {
    expect(functionNameToEventType('repository_up')).toBe('cli.repo.up');
    expect(functionNameToEventType('repository_template_apply')).toBe('cli.repo.template_apply');
    expect(functionNameToEventType('repository_down')).toBe('cli.repo.down');
    expect(functionNameToEventType('repository_autostart_enable_all')).toBe(
      'cli.repo.autostart_enable_all'
    );
  });

  it('maps backup_ prefix to cli.backup.*', () => {
    expect(functionNameToEventType('backup_push')).toBe('cli.backup.push');
    expect(functionNameToEventType('backup_pull')).toBe('cli.backup.pull');
    expect(functionNameToEventType('backup_list')).toBe('cli.backup.list');
    expect(functionNameToEventType('backup_delete')).toBe('cli.backup.delete');
  });

  it('maps datastore_ prefix to cli.datastore.*', () => {
    expect(functionNameToEventType('datastore_status')).toBe('cli.datastore.status');
    expect(functionNameToEventType('datastore_ceph_fork')).toBe('cli.datastore.ceph_fork');
  });

  it('maps machine_ prefix to cli.machine.*', () => {
    expect(functionNameToEventType('machine_ssh_test')).toBe('cli.machine.ssh_test');
  });

  it('maps explicit non-bridge events to canonical types', () => {
    expect(functionNameToEventType('sync_upload')).toBe('cli.sync.upload');
    expect(functionNameToEventType('sync_download')).toBe('cli.sync.download');
    expect(functionNameToEventType('term_connect')).toBe('cli.term.session');
  });

  it('returns null for unrecognized function names', () => {
    expect(functionNameToEventType('custom_fn')).toBeNull();
    expect(functionNameToEventType('repository_unknown_op')).toBeNull();
  });
});

describe('auditService.record', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset the internal queue by flushing with no token
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'missing' });
    void auditService.flush();
  });

  it('queues event when subscription token is ready', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      token: { token: 'test' },
      serverUrl: 'http://localhost',
    });
    mockAccountServerFetch.mockResolvedValue({ accepted: 1 });

    auditService.record({
      type: 'cli.repo.up',
      data: {
        functionName: 'repository_up',
        machineName: 'prod-1',
        success: true,
        exitCode: 0,
        durationMs: 1234,
        cliVersion: '1.0.0-test',
      },
    });

    await auditService.flush();

    expect(mockAccountServerFetch).toHaveBeenCalledOnce();
    expect(mockAccountServerFetch).toHaveBeenCalledWith(
      '/account/api/v1/licenses/audit-events',
      expect.objectContaining({
        method: 'POST',
        body: {
          events: [
            {
              type: 'cli.repo.up',
              data: expect.objectContaining({
                functionName: 'repository_up',
                machineName: 'prod-1',
                success: true,
              }),
            },
          ],
        },
      })
    );
  });

  it('is a no-op when subscription token is missing', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'missing' });

    auditService.record({
      type: 'cli.repo.up',
      data: {
        functionName: 'repository_up',
        machineName: 'prod-1',
        success: true,
        exitCode: 0,
        durationMs: 1234,
        cliVersion: '1.0.0-test',
      },
    });

    // Switch to ready for flush to actually attempt sending
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      token: { token: 'test' },
      serverUrl: 'http://localhost',
    });
    await auditService.flush();

    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('is a no-op when getSubscriptionTokenState throws', async () => {
    mockGetSubscriptionTokenState.mockImplementation(() => {
      throw new Error('no config');
    });

    auditService.record({
      type: 'cli.repo.up',
      data: {
        functionName: 'repository_up',
        machineName: 'prod-1',
        success: true,
        exitCode: 0,
        durationMs: 1234,
        cliVersion: '1.0.0-test',
      },
    });

    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      token: { token: 'test' },
      serverUrl: 'http://localhost',
    });
    await auditService.flush();

    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });
});

describe('auditService.recordOperation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'missing' });
    void auditService.flush();
  });

  it('queues event with correct type mapping and data shape', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      token: { token: 'test' },
      serverUrl: 'http://localhost',
    });
    mockAccountServerFetch.mockResolvedValue({ accepted: 1 });

    auditService.recordOperation({
      functionName: 'backup_push',
      machineName: 'server-1',
      repoName: 'my-app',
      success: true,
      exitCode: 0,
      durationMs: 5678,
    });

    await auditService.flush();

    expect(mockAccountServerFetch).toHaveBeenCalledWith(
      '/account/api/v1/licenses/audit-events',
      expect.objectContaining({
        body: {
          events: [
            {
              type: 'cli.backup.push',
              data: {
                functionName: 'backup_push',
                machineName: 'server-1',
                repoName: 'my-app',
                success: true,
                exitCode: 0,
                durationMs: 5678,
                cliVersion: '1.0.0-test',
              },
            },
          ],
        },
      })
    );
  });

  it('truncates error to 500 characters', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      token: { token: 'test' },
      serverUrl: 'http://localhost',
    });
    mockAccountServerFetch.mockResolvedValue({ accepted: 1 });

    const longError = 'x'.repeat(1000);
    auditService.recordOperation({
      functionName: 'repository_up',
      machineName: 'server-1',
      success: false,
      exitCode: 1,
      durationMs: 100,
      error: longError,
    });

    await auditService.flush();

    const sentBody = mockAccountServerFetch.mock.calls[0][1].body;
    expect(sentBody.events[0].data.error).toHaveLength(500);
  });
});

describe('auditService.flush', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'missing' });
    void auditService.flush();
  });

  it('does nothing when queue is empty', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      token: { token: 'test' },
      serverUrl: 'http://localhost',
    });
    await auditService.flush();
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('clears queue after successful flush', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      token: { token: 'test' },
      serverUrl: 'http://localhost',
    });
    mockAccountServerFetch.mockResolvedValue({ accepted: 1 });

    auditService.recordOperation({
      functionName: 'repository_up',
      machineName: 'server-1',
      success: true,
      exitCode: 0,
      durationMs: 100,
    });

    await auditService.flush();
    expect(mockAccountServerFetch).toHaveBeenCalledOnce();

    // Second flush should be a no-op (queue cleared)
    await auditService.flush();
    expect(mockAccountServerFetch).toHaveBeenCalledOnce();
  });

  it('clears queue when token becomes unavailable between record and flush', async () => {
    // Token available during record
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      token: { token: 'test' },
      serverUrl: 'http://localhost',
    });

    auditService.recordOperation({
      functionName: 'repository_up',
      machineName: 'server-1',
      success: true,
      exitCode: 0,
      durationMs: 100,
    });

    // Token gone during flush
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'missing' });
    await auditService.flush();

    // Should not have called API
    expect(mockAccountServerFetch).not.toHaveBeenCalled();

    // Queue should be cleared, so re-enabling token and flushing does nothing
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      token: { token: 'test' },
      serverUrl: 'http://localhost',
    });
    await auditService.flush();
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('swallows accountServerFetch errors', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      token: { token: 'test' },
      serverUrl: 'http://localhost',
    });
    mockAccountServerFetch.mockRejectedValue(new Error('network error'));

    auditService.recordOperation({
      functionName: 'repository_up',
      machineName: 'server-1',
      success: true,
      exitCode: 0,
      durationMs: 100,
    });

    // Should not throw
    await expect(auditService.flush()).resolves.toBeUndefined();
  });

  it('sends multiple events in a single batch', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      token: { token: 'test' },
      serverUrl: 'http://localhost',
    });
    mockAccountServerFetch.mockResolvedValue({ accepted: 3 });

    auditService.recordOperation({
      functionName: 'repository_up',
      machineName: 'server-1',
      success: true,
      exitCode: 0,
      durationMs: 100,
    });
    auditService.recordOperation({
      functionName: 'backup_push',
      machineName: 'server-1',
      repoName: 'my-app',
      success: true,
      exitCode: 0,
      durationMs: 200,
    });
    auditService.recordOperation({
      functionName: 'repository_down',
      machineName: 'server-1',
      success: false,
      exitCode: 1,
      durationMs: 50,
      error: 'timeout',
    });

    await auditService.flush();

    expect(mockAccountServerFetch).toHaveBeenCalledOnce();
    const sentBody = mockAccountServerFetch.mock.calls[0][1].body;
    expect(sentBody.events).toHaveLength(3);
    expect(sentBody.events[0].type).toBe('cli.repo.up');
    expect(sentBody.events[1].type).toBe('cli.backup.push');
    expect(sentBody.events[2].type).toBe('cli.repo.down');
  });
});
