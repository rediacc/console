import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockExecute, mockGetStateProvider } = vi.hoisted(() => ({
  mockExecute: vi.fn(),
  mockGetStateProvider: vi.fn(),
}));

vi.mock('../local-executor.js', () => ({
  localExecutorService: {
    execute: mockExecute,
  },
}));

vi.mock('../../providers/index.js', () => ({
  getStateProvider: mockGetStateProvider,
}));

const { assertRepoMountedOnMachine } = await import('../repo-mount-check.js');
const { ValidationError } = await import('../../utils/errors.js');

const REPO_NAME = 'mail';
const REPO_GUID = 'repo-guid-001';
const MACHINE = 'host-1';

function localProvider() {
  return { isCloud: false };
}
function cloudProvider() {
  return { isCloud: true };
}

function listResultStdout(repos: { name: string; mounted: boolean }[]): string {
  return JSON.stringify(repos);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetStateProvider.mockResolvedValue(localProvider());
});

describe('assertRepoMountedOnMachine', () => {
  it('does not throw when the repo is mounted', async () => {
    mockExecute.mockResolvedValue({
      success: true,
      exitCode: 0,
      stdout: listResultStdout([
        { name: 'other-guid', mounted: true },
        { name: REPO_GUID, mounted: true },
      ]),
    });

    await expect(
      assertRepoMountedOnMachine(REPO_NAME, REPO_GUID, MACHINE)
    ).resolves.toBeUndefined();
    expect(mockExecute).toHaveBeenCalledTimes(1);
  });

  it('throws ValidationError when the repo is present but not mounted', async () => {
    mockExecute.mockResolvedValue({
      success: true,
      exitCode: 0,
      stdout: listResultStdout([{ name: REPO_GUID, mounted: false }]),
    });

    await expect(assertRepoMountedOnMachine(REPO_NAME, REPO_GUID, MACHINE)).rejects.toBeInstanceOf(
      ValidationError
    );
  });

  it('throws ValidationError when the repo is absent from the list', async () => {
    mockExecute.mockResolvedValue({
      success: true,
      exitCode: 0,
      stdout: listResultStdout([{ name: 'someone-else', mounted: true }]),
    });

    await expect(assertRepoMountedOnMachine(REPO_NAME, REPO_GUID, MACHINE)).rejects.toBeInstanceOf(
      ValidationError
    );
  });

  it('silently passes when the executor reports failure', async () => {
    mockExecute.mockResolvedValue({
      success: false,
      exitCode: 1,
      error: 'machine unreachable',
    });

    await expect(
      assertRepoMountedOnMachine(REPO_NAME, REPO_GUID, MACHINE)
    ).resolves.toBeUndefined();
  });

  it('silently passes when stdout is empty', async () => {
    mockExecute.mockResolvedValue({ success: true, exitCode: 0, stdout: '' });

    await expect(
      assertRepoMountedOnMachine(REPO_NAME, REPO_GUID, MACHINE)
    ).resolves.toBeUndefined();
  });

  it('silently passes when the parser cannot extract a JSON array', async () => {
    mockExecute.mockResolvedValue({
      success: true,
      exitCode: 0,
      stdout: 'renet warning: not even close to JSON',
    });

    await expect(
      assertRepoMountedOnMachine(REPO_NAME, REPO_GUID, MACHINE)
    ).resolves.toBeUndefined();
  });

  it('is a silent no-op when the cloud adapter is active', async () => {
    mockGetStateProvider.mockResolvedValue(cloudProvider());

    await expect(
      assertRepoMountedOnMachine(REPO_NAME, REPO_GUID, MACHINE)
    ).resolves.toBeUndefined();
    expect(mockExecute).not.toHaveBeenCalled();
  });
});
