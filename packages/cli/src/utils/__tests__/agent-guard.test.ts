import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Mock i18n
vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) => {
    if (key === 'errors.agent.machineGuard' && params?.machine) {
      return `Cannot access machine "${params.machine}" directly in agent mode.`;
    }
    return key;
  },
}));

import { assertAgentMachineAccess, isAgentEnvironment } from '../agent-guard.js';

describe('isAgentEnvironment', () => {
  const envBackup: Record<string, string | undefined> = {};

  beforeEach(() => {
    for (const key of [
      'REDIACC_AGENT',
      'CLAUDECODE',
      'GEMINI_CLI',
      'COPILOT_CLI',
      'CURSOR_TRACE_ID',
    ]) {
      envBackup[key] = process.env[key];
      delete process.env[key];
    }
  });

  afterEach(() => {
    for (const [key, value] of Object.entries(envBackup)) {
      if (value === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    }
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
});

describe('assertAgentMachineAccess', () => {
  const ALL_AGENT_KEYS = [
    'REDIACC_AGENT',
    'CLAUDECODE',
    'GEMINI_CLI',
    'COPILOT_CLI',
    'CURSOR_TRACE_ID',
    'REDIACC_ALLOW_GRAND_REPO',
  ] as const;
  const envBackup: Record<string, string | undefined> = {};

  beforeEach(() => {
    for (const key of ALL_AGENT_KEYS) {
      envBackup[key] = process.env[key];
      delete process.env[key];
    }
  });

  afterEach(() => {
    for (const [key, value] of Object.entries(envBackup)) {
      if (value === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    }
  });

  it('does nothing when not in agent environment', () => {
    expect(() => assertAgentMachineAccess('prod-1')).not.toThrow();
  });

  it('throws in agent mode for machine-level access', () => {
    process.env.REDIACC_AGENT = '1';
    expect(() => assertAgentMachineAccess('prod-1')).toThrow();
  });

  it('respects REDIACC_ALLOW_GRAND_REPO=* wildcard', () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = '*';
    expect(() => assertAgentMachineAccess('prod-1')).not.toThrow();
  });

  it('does not allow specific repo name as machine access consent', () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = 'mail';
    expect(() => assertAgentMachineAccess('prod-1')).toThrow();
  });
});
