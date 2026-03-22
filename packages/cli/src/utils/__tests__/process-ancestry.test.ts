import { describe, expect, it } from 'vitest';

// Import after potential mocks
import {
  getParentPid,
  hasAgentEnvVar,
  isAgentByAncestry,
  isOverrideLegitimate,
  readProcEnviron,
  walkAncestors,
} from '../process-ancestry.js';

const isLinux = process.platform === 'linux';

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

describe('walkAncestors', () => {
  it.skipIf(!isLinux)('returns at least the current process', () => {
    const ancestors = walkAncestors();
    expect(ancestors.length).toBeGreaterThan(0);
    expect(ancestors[0].pid).toBe(process.pid);
  });

  it('returns empty array on non-Linux', () => {
    if (isLinux) return;
    expect(walkAncestors()).toEqual([]);
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

  it('returns false on non-Linux (fallback)', () => {
    if (isLinux) return;
    // On non-Linux, should return false (no /proc to check)
    expect(isAgentByAncestry()).toBe(false);
  });
});

describe('isOverrideLegitimate', () => {
  it('returns true on non-Linux (fail open)', () => {
    if (isLinux) return;
    expect(isOverrideLegitimate()).toBe(true);
  });

  it.skipIf(!isLinux)('returns boolean on Linux', () => {
    // The result depends on whether we're running inside an agent (e.g., Claude Code).
    // If CLAUDECODE=1 is in an ancestor, isOverrideLegitimate checks if the override
    // was set before the agent boundary. Just verify it doesn't crash.
    const result = isOverrideLegitimate();
    expect(typeof result).toBe('boolean');
  });
});
