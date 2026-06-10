import type { SpawnSyncReturns } from 'node:child_process';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockSpawnSync = vi.hoisted(() => vi.fn());
const mockAccessSync = vi.hoisted(() => vi.fn());
const mockIsSEA = vi.hoisted(() => vi.fn(() => false));
const mockExtractSync = vi.hoisted(() => vi.fn(() => '/tmp/.rdc-local/renet'));

vi.mock('node:child_process', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:child_process')>()),
  spawnSync: mockSpawnSync,
}));

vi.mock('node:fs', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:fs')>()),
  accessSync: mockAccessSync,
}));

vi.mock('../../services/embedded-assets.js', () => ({
  isSEA: mockIsSEA,
  extractRenetToLocalSync: mockExtractSync,
}));

import { resolveRenetSyncPath, runAncestryHelper } from '../ancestry-helper.js';

function spawnResult(overrides: Partial<SpawnSyncReturns<string>>): SpawnSyncReturns<string> {
  return {
    pid: 1234,
    output: [],
    stdout: '',
    stderr: '',
    status: 0,
    signal: null,
    ...overrides,
  };
}

const VALID_OUTPUT = JSON.stringify({
  ancestors: [
    { pid: 100, env: { CLAUDECODE: '1' } },
    { pid: 50, env: { CLAUDECODE: '1', REDIACC_ALLOW_GRAND_REPO: '*' } },
  ],
});

beforeEach(() => {
  vi.clearAllMocks();
  mockIsSEA.mockReturnValue(false);
  mockExtractSync.mockReturnValue('/tmp/.rdc-local/renet');
  mockAccessSync.mockReturnValue(undefined);
});

describe('resolveRenetSyncPath', () => {
  it('uses the SEA extraction when running as SEA', () => {
    mockIsSEA.mockReturnValue(true);
    expect(resolveRenetSyncPath()).toBe('/tmp/.rdc-local/renet');
    expect(mockSpawnSync).not.toHaveBeenCalled();
  });

  it('returns null when SEA extraction throws', () => {
    mockIsSEA.mockReturnValue(true);
    mockExtractSync.mockImplementation(() => {
      throw new Error('asset missing');
    });
    expect(resolveRenetSyncPath()).toBeNull();
  });

  it('falls back to PATH lookup in dev mode', () => {
    mockSpawnSync.mockReturnValue(spawnResult({ stdout: '/usr/local/bin/renet\n' }));
    expect(resolveRenetSyncPath()).toBe('/usr/local/bin/renet');
    const expectedLookup = process.platform === 'win32' ? 'where' : 'which';
    expect(mockSpawnSync).toHaveBeenCalledWith(
      expectedLookup,
      ['renet'],
      expect.objectContaining({ encoding: 'utf-8' })
    );
  });

  it('returns null when the PATH lookup fails', () => {
    mockSpawnSync.mockReturnValue(spawnResult({ status: 1 }));
    expect(resolveRenetSyncPath()).toBeNull();
  });

  it('returns null when the resolved path is not accessible', () => {
    mockSpawnSync.mockReturnValue(spawnResult({ stdout: '/usr/local/bin/renet\n' }));
    mockAccessSync.mockImplementation(() => {
      throw new Error('ENOENT');
    });
    expect(resolveRenetSyncPath()).toBeNull();
  });
});

describe('runAncestryHelper', () => {
  beforeEach(() => {
    mockIsSEA.mockReturnValue(true); // resolve via mocked extraction, no which-lookup
  });

  it('spawns the process-ancestry subcommand with our pid and the keys', () => {
    mockSpawnSync.mockReturnValue(spawnResult({ stdout: VALID_OUTPUT }));

    const result = runAncestryHelper(['CLAUDECODE', 'REDIACC_ALLOW_GRAND_REPO']);

    expect(mockSpawnSync).toHaveBeenCalledWith(
      '/tmp/.rdc-local/renet',
      [
        'process-ancestry',
        '--pid',
        String(process.pid),
        '--keys',
        'CLAUDECODE,REDIACC_ALLOW_GRAND_REPO',
      ],
      expect.objectContaining({ timeout: 5000, windowsHide: true })
    );
    expect(result).toEqual([
      { pid: 100, env: { CLAUDECODE: '1' } },
      { pid: 50, env: { CLAUDECODE: '1', REDIACC_ALLOW_GRAND_REPO: '*' } },
    ]);
  });

  it('returns null when the binary cannot be resolved', () => {
    mockExtractSync.mockImplementation(() => {
      throw new Error('not SEA');
    });
    expect(runAncestryHelper(['CLAUDECODE'])).toBeNull();
    expect(mockSpawnSync).not.toHaveBeenCalled();
  });

  it('returns null on non-zero exit (old renet without the subcommand)', () => {
    mockSpawnSync.mockReturnValue(spawnResult({ status: 1, stderr: 'unknown command' }));
    expect(runAncestryHelper(['CLAUDECODE'])).toBeNull();
  });

  it('returns null on spawn error or timeout', () => {
    mockSpawnSync.mockReturnValue(
      spawnResult({ status: null, error: new Error('ETIMEDOUT'), signal: 'SIGTERM' })
    );
    expect(runAncestryHelper(['CLAUDECODE'])).toBeNull();
  });

  it('returns null on malformed JSON', () => {
    mockSpawnSync.mockReturnValue(spawnResult({ stdout: 'not-json{' }));
    expect(runAncestryHelper(['CLAUDECODE'])).toBeNull();
  });

  it('returns null when the envelope shape is wrong', () => {
    for (const bad of [
      '{}',
      '{"ancestors": "nope"}',
      '{"ancestors": [{"pid": "100", "env": {}}]}',
      '{"ancestors": [{"pid": 100}]}',
      '{"ancestors": [{"pid": 100, "env": {"A": 1}}]}',
    ]) {
      mockSpawnSync.mockReturnValue(spawnResult({ stdout: bad }));
      expect(runAncestryHelper(['CLAUDECODE']), `input: ${bad}`).toBeNull();
    }
  });

  it('accepts an empty ancestors array', () => {
    mockSpawnSync.mockReturnValue(spawnResult({ stdout: '{"ancestors": []}' }));
    expect(runAncestryHelper(['CLAUDECODE'])).toEqual([]);
  });
});
