import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Mock i18n
vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) => {
    if (key === 'errors.agent.machineGuard' && params?.machine) {
      return `Cannot access machine "${params.machine}" directly in agent mode.`;
    }
    if (key === 'errors.agent.createGuard' && params?.name) {
      return `Cannot create repository "${params.name}" in agent mode.`;
    }
    return key;
  },
}));

// Mock process-ancestry module
const mockIsAgentByAncestry = vi.hoisted(() => vi.fn(() => false));
const mockIsOverrideLegitimate = vi.hoisted(() => vi.fn(() => true));

vi.mock('../process-ancestry.js', () => ({
  isAgentByAncestry: mockIsAgentByAncestry,
  isOverrideLegitimate: mockIsOverrideLegitimate,
}));

import {
  _resetCache,
  assertAgentMachineAccess,
  assertAgentRepoCreate,
  isAgentEnvironment,
} from '../agent-guard.js';

// All env vars that affect agent detection
const ALL_AGENT_KEYS = [
  'REDIACC_AGENT',
  'CLAUDECODE',
  'GEMINI_CLI',
  'COPILOT_CLI',
  'CURSOR_TRACE_ID',
  'REDIACC_ALLOW_GRAND_REPO',
] as const;

function backupAndClearEnv(backup: Record<string, string | undefined>) {
  for (const key of ALL_AGENT_KEYS) {
    backup[key] = process.env[key];
    delete process.env[key];
  }
}

function restoreEnv(backup: Record<string, string | undefined>) {
  for (const [key, value] of Object.entries(backup)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
}

describe('isAgentEnvironment', () => {
  const envBackup: Record<string, string | undefined> = {};

  beforeEach(() => {
    _resetCache();
    vi.clearAllMocks();
    mockIsAgentByAncestry.mockReturnValue(false);
    backupAndClearEnv(envBackup);
  });

  afterEach(() => {
    restoreEnv(envBackup);
  });

  it('returns false with no agent env vars', () => {
    expect(isAgentEnvironment()).toBe(false);
  });

  it('returns true when REDIACC_AGENT=1', () => {
    process.env.REDIACC_AGENT = '1';
    expect(isAgentEnvironment()).toBe(true);
  });

  it('returns true when CLAUDECODE=1', () => {
    process.env.CLAUDECODE = '1';
    expect(isAgentEnvironment()).toBe(true);
  });

  it('returns true when GEMINI_CLI=1', () => {
    process.env.GEMINI_CLI = '1';
    expect(isAgentEnvironment()).toBe(true);
  });

  it('returns true when COPILOT_CLI=1', () => {
    process.env.COPILOT_CLI = '1';
    expect(isAgentEnvironment()).toBe(true);
  });

  it('returns true when CURSOR_TRACE_ID is set', () => {
    process.env.CURSOR_TRACE_ID = 'some-trace-id';
    expect(isAgentEnvironment()).toBe(true);
  });

  it('returns false when env var is not "1"', () => {
    process.env.REDIACC_AGENT = 'true';
    expect(isAgentEnvironment()).toBe(false);
  });

  it('detects agent via ancestry even when process.env is clean', () => {
    mockIsAgentByAncestry.mockReturnValue(true);
    expect(isAgentEnvironment()).toBe(true);
  });

  it('caches result across calls', () => {
    _resetCache();
    vi.clearAllMocks();
    mockIsAgentByAncestry.mockReturnValue(false);
    isAgentEnvironment();
    isAgentEnvironment();
    expect(mockIsAgentByAncestry).toHaveBeenCalledTimes(1);
  });
});

describe('assertAgentMachineAccess', () => {
  const envBackup: Record<string, string | undefined> = {};

  beforeEach(() => {
    _resetCache();
    vi.clearAllMocks();
    mockIsAgentByAncestry.mockReturnValue(false);
    mockIsOverrideLegitimate.mockReturnValue(true);
    backupAndClearEnv(envBackup);
  });

  afterEach(() => {
    restoreEnv(envBackup);
  });

  it('does nothing when not in agent environment', () => {
    expect(() => assertAgentMachineAccess('prod-1')).not.toThrow();
  });

  it('throws in agent mode for machine-level access', () => {
    process.env.REDIACC_AGENT = '1';
    expect(() => assertAgentMachineAccess('prod-1')).toThrow();
  });

  it('respects legitimate REDIACC_ALLOW_GRAND_REPO=* wildcard', () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = '*';
    mockIsOverrideLegitimate.mockReturnValue(true);
    expect(() => assertAgentMachineAccess('prod-1')).not.toThrow();
  });

  it('blocks illegitimate override (injected by agent)', () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = '*';
    mockIsOverrideLegitimate.mockReturnValue(false);
    expect(() => assertAgentMachineAccess('prod-1')).toThrow();
  });

  it('does not allow specific repo name as machine access consent', () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = 'mail';
    expect(() => assertAgentMachineAccess('prod-1')).toThrow();
  });
});

describe('assertAgentRepoCreate', () => {
  const envBackup: Record<string, string | undefined> = {};

  beforeEach(() => {
    _resetCache();
    vi.clearAllMocks();
    mockIsAgentByAncestry.mockReturnValue(false);
    mockIsOverrideLegitimate.mockReturnValue(true);
    backupAndClearEnv(envBackup);
  });

  afterEach(() => {
    restoreEnv(envBackup);
  });

  it('does nothing when not in agent environment', () => {
    expect(() => assertAgentRepoCreate('my-app')).not.toThrow();
  });

  it('throws in agent mode', () => {
    process.env.REDIACC_AGENT = '1';
    expect(() => assertAgentRepoCreate('my-app')).toThrow();
  });

  it('respects legitimate wildcard override', () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = '*';
    mockIsOverrideLegitimate.mockReturnValue(true);
    expect(() => assertAgentRepoCreate('my-app')).not.toThrow();
  });

  it('blocks illegitimate override', () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = '*';
    mockIsOverrideLegitimate.mockReturnValue(false);
    expect(() => assertAgentRepoCreate('my-app')).toThrow();
  });
});
