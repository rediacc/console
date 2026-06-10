import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Mock the helper bridge so the darwin/win32 paths are testable on any host.
const mockRunAncestryHelper = vi.hoisted(() =>
  vi.fn((_keys: readonly string[]): { pid: number; env: Record<string, string> }[] | null => null)
);

vi.mock('../ancestry-helper.js', () => ({
  runAncestryHelper: mockRunAncestryHelper,
}));

import {
  _resetAncestryCache,
  getParentPid,
  hasAgentEnvVar,
  isAgentByAncestry,
  isAncestryVerificationAvailable,
  isOverrideLegitimate,
  OVERRIDE_VAR_CONFIG_EDIT,
  readProcEnviron,
  walkAncestors,
} from '../process-ancestry.js';

const isLinux = process.platform === 'linux';
const originalPlatform = process.platform;

function setPlatform(platform: string) {
  Object.defineProperty(process, 'platform', { value: platform, configurable: true });
}

beforeEach(() => {
  _resetAncestryCache();
  vi.clearAllMocks();
  mockRunAncestryHelper.mockReturnValue(null);
});

afterEach(() => {
  setPlatform(originalPlatform);
  _resetAncestryCache();
});

describe('readProcEnviron', () => {
  it.skipIf(!isLinux)('reads own process environment', () => {
    const env = readProcEnviron('self');
    expect(env).not.toBeNull();
    // PATH should always be set
    expect(env!.has('PATH')).toBe(true);
  });

  it.skipIf(!isLinux)('returns null for non-existent PID', () => {
    const env = readProcEnviron(999999999);
    expect(env).toBeNull();
  });

  it('returns null on non-Linux', () => {
    if (isLinux) return; // skip on Linux
    const env = readProcEnviron('self');
    expect(env).toBeNull();
  });
});

describe('getParentPid', () => {
  it.skipIf(!isLinux)('returns PPID for current process', () => {
    const ppid = getParentPid(process.pid);
    expect(ppid).toBe(process.ppid);
  });

  it.skipIf(!isLinux)('returns null for non-existent PID', () => {
    expect(getParentPid(999999999)).toBeNull();
  });

  it.skipIf(!isLinux)('returns null for PID 1', () => {
    expect(getParentPid(1)).toBeNull();
  });
});

describe('hasAgentEnvVar', () => {
  it('detects CLAUDECODE=1', () => {
    const env = new Map([['CLAUDECODE', '1']]);
    expect(hasAgentEnvVar(env)).toBe(true);
  });

  it('detects REDIACC_AGENT=1', () => {
    const env = new Map([['REDIACC_AGENT', '1']]);
    expect(hasAgentEnvVar(env)).toBe(true);
  });

  it('detects GEMINI_CLI=1', () => {
    const env = new Map([['GEMINI_CLI', '1']]);
    expect(hasAgentEnvVar(env)).toBe(true);
  });

  it('detects COPILOT_CLI=1', () => {
    const env = new Map([['COPILOT_CLI', '1']]);
    expect(hasAgentEnvVar(env)).toBe(true);
  });

  it('detects CURSOR_TRACE_ID (any value)', () => {
    const env = new Map([['CURSOR_TRACE_ID', 'some-trace']]);
    expect(hasAgentEnvVar(env)).toBe(true);
  });

  it('ignores CLAUDECODE=true (wrong value)', () => {
    const env = new Map([['CLAUDECODE', 'true']]);
    expect(hasAgentEnvVar(env)).toBe(false);
  });

  it('returns false when no agent vars', () => {
    const env = new Map([
      ['PATH', '/usr/bin'],
      ['HOME', '/root'],
    ]);
    expect(hasAgentEnvVar(env)).toBe(false);
  });

  it('returns false for empty map', () => {
    expect(hasAgentEnvVar(new Map())).toBe(false);
  });
});

describe('walkAncestors (Linux /proc)', () => {
  it.skipIf(!isLinux)('returns at least the current process', () => {
    const ancestors = walkAncestors();
    expect(ancestors.length).toBeGreaterThan(0);
    expect(ancestors[0].pid).toBe(process.pid);
  });

  it.skipIf(!isLinux)('only reports witnessed keys, never the full environment', () => {
    // PATH is set in every test environment but is not a witness key.
    const ancestors = walkAncestors();
    for (const a of ancestors) {
      expect(a.env.has('PATH')).toBe(false);
    }
  });

  it.skipIf(!isLinux)('does not spawn the helper on Linux', () => {
    walkAncestors();
    expect(mockRunAncestryHelper).not.toHaveBeenCalled();
  });
});

describe('isAgentByAncestry', () => {
  it.skipIf(!isLinux)('detects agent vars in current process via /proc', () => {
    // Our own process should have or not have agent vars
    // based on the test runner environment
    const result = isAgentByAncestry();
    // Just verify it returns a boolean without crashing
    expect(typeof result).toBe('boolean');
  });

  it('returns false on darwin without spawning the helper (startup cost)', () => {
    setPlatform('darwin');
    expect(isAgentByAncestry()).toBe(false);
    expect(mockRunAncestryHelper).not.toHaveBeenCalled();
  });

  it('returns false on win32 without spawning the helper (startup cost)', () => {
    setPlatform('win32');
    expect(isAgentByAncestry()).toBe(false);
    expect(mockRunAncestryHelper).not.toHaveBeenCalled();
  });
});

describe('isOverrideLegitimate (Linux)', () => {
  it.skipIf(!isLinux)('returns boolean on Linux', () => {
    // The result depends on whether we're running inside an agent (e.g., Claude Code).
    // If CLAUDECODE=1 is in an ancestor, isOverrideLegitimate checks if the override
    // was set before the agent boundary. Just verify it doesn't crash.
    const result = isOverrideLegitimate();
    expect(typeof result).toBe('boolean');
  });
});

describe.each(['darwin', 'win32'])('helper-based ancestry on %s', (platform) => {
  beforeEach(() => {
    setPlatform(platform);
  });

  it('accepts an override present at the agent boundary', () => {
    mockRunAncestryHelper.mockReturnValue([
      { pid: 100, env: { CLAUDECODE: '1' } }, // rdc child inherits agent var
      { pid: 50, env: { CLAUDECODE: '1', REDIACC_ALLOW_GRAND_REPO: '*' } }, // agent boundary
      { pid: 10, env: { REDIACC_ALLOW_GRAND_REPO: '*' } }, // user shell
    ]);
    expect(isOverrideLegitimate()).toBe(true);
    expect(isAncestryVerificationAvailable()).toBe(true);
  });

  it('rejects an override injected below the agent boundary', () => {
    mockRunAncestryHelper.mockReturnValue([
      { pid: 100, env: { CLAUDECODE: '1', REDIACC_ALLOW_GRAND_REPO: '*' } }, // injected
      { pid: 50, env: { CLAUDECODE: '1' } }, // agent boundary — no override
      { pid: 10, env: {} },
    ]);
    expect(isOverrideLegitimate()).toBe(false);
  });

  it('accepts any override when no agent boundary exists', () => {
    mockRunAncestryHelper.mockReturnValue([
      { pid: 100, env: { REDIACC_ALLOW_GRAND_REPO: 'mail' } },
      { pid: 10, env: {} },
    ]);
    expect(isOverrideLegitimate()).toBe(true);
  });

  it('verifies each override variable independently (config-edit fix)', () => {
    mockRunAncestryHelper.mockReturnValue([
      { pid: 100, env: { CLAUDECODE: '1' } },
      { pid: 50, env: { CLAUDECODE: '1', REDIACC_ALLOW_CONFIG_EDIT: '*' } }, // boundary
    ]);
    expect(isOverrideLegitimate(OVERRIDE_VAR_CONFIG_EDIT)).toBe(true);
    expect(isOverrideLegitimate()).toBe(false); // grand override was NOT at the boundary
  });

  it('fails closed when the helper is unavailable', () => {
    mockRunAncestryHelper.mockReturnValue(null);
    expect(isOverrideLegitimate()).toBe(false);
    expect(isAncestryVerificationAvailable()).toBe(false);
    expect(walkAncestors()).toEqual([]);
  });

  it('fails closed when the helper reports an empty chain', () => {
    mockRunAncestryHelper.mockReturnValue([]);
    expect(isOverrideLegitimate()).toBe(false);
    expect(isAncestryVerificationAvailable()).toBe(true);
  });

  it('spawns the helper once and caches the walk', () => {
    mockRunAncestryHelper.mockReturnValue([{ pid: 100, env: {} }]);
    isOverrideLegitimate();
    isOverrideLegitimate(OVERRIDE_VAR_CONFIG_EDIT);
    isAncestryVerificationAvailable();
    walkAncestors();
    expect(mockRunAncestryHelper).toHaveBeenCalledTimes(1);
  });
});

describe('unsupported platforms', () => {
  it('fails closed without spawning the helper', () => {
    setPlatform('freebsd');
    expect(isOverrideLegitimate()).toBe(false);
    expect(isAncestryVerificationAvailable()).toBe(false);
    expect(walkAncestors()).toEqual([]);
    expect(mockRunAncestryHelper).not.toHaveBeenCalled();
  });
});
