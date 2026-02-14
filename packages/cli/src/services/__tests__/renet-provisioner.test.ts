import { describe, expect, it } from 'vitest';
import { compareVersions } from '../updater.js';

/**
 * Version guard logic tests.
 *
 * These test the decision logic used by RenetProvisionerService.provision()
 * to prevent accidental renet downgrades on remote machines.
 *
 * Integration testing of the full provisioning flow (including SSH, binary
 * upload, and version checking against real VMs) is covered in:
 *   packages/cli/tests/tests/08-e2e/01-local-execution.test.ts
 */

/**
 * Parse a renet version from its localized output.
 * Mirrors the regex used in RenetProvisionerService.getRemoteVersion().
 */
function parseVersionFromOutput(output: string): string | null {
  const match = /\d+\.\d+\.\d+/.exec(output);
  return match ? match[0] : null;
}

/**
 * Determine if a downgrade would occur.
 * Returns true if localVersion is older than remoteVersion.
 */
function wouldDowngrade(localVersion: string, remoteVersion: string): boolean {
  return compareVersions(localVersion, remoteVersion) < 0;
}

// ============================================
// Version Parsing Tests
// ============================================

describe('renet version parsing', () => {
  it('should parse English output', () => {
    expect(parseVersionFromOutput('renet version 0.4.90')).toBe('0.4.90');
  });

  it('should parse English output with newline', () => {
    expect(parseVersionFromOutput('renet version 0.4.90\n')).toBe('0.4.90');
  });

  it('should parse Chinese output', () => {
    expect(parseVersionFromOutput('renet版本 0.4.90')).toBe('0.4.90');
  });

  it('should parse Turkish output', () => {
    expect(parseVersionFromOutput('renet sürümü 0.5.0')).toBe('0.5.0');
  });

  it('should parse German output', () => {
    expect(parseVersionFromOutput('renet Version 0.4.90')).toBe('0.4.90');
  });

  it('should parse Arabic output', () => {
    expect(parseVersionFromOutput('renet الإصدار 0.4.90')).toBe('0.4.90');
  });

  it('should parse Russian output', () => {
    expect(parseVersionFromOutput('renet версия 1.0.0')).toBe('1.0.0');
  });

  it('should parse Japanese output', () => {
    expect(parseVersionFromOutput('renet バージョン 0.4.90')).toBe('0.4.90');
  });

  it('should return null for garbage output', () => {
    expect(parseVersionFromOutput('garbage output')).toBeNull();
  });

  it('should return null for empty string', () => {
    expect(parseVersionFromOutput('')).toBeNull();
  });

  it('should return null for partial version', () => {
    expect(parseVersionFromOutput('renet version 0.4')).toBeNull();
  });
});

// ============================================
// Downgrade Detection Tests
// ============================================

describe('downgrade detection', () => {
  it('should detect downgrade (remote newer)', () => {
    expect(wouldDowngrade('0.4.90', '0.5.0')).toBe(true);
  });

  it('should not flag upgrade (remote older)', () => {
    expect(wouldDowngrade('0.5.0', '0.4.90')).toBe(false);
  });

  it('should not flag same version', () => {
    expect(wouldDowngrade('0.4.90', '0.4.90')).toBe(false);
  });

  it('should detect major version downgrade', () => {
    expect(wouldDowngrade('0.4.90', '1.0.0')).toBe(true);
  });

  it('should detect patch-level downgrade', () => {
    expect(wouldDowngrade('0.4.89', '0.4.90')).toBe(true);
  });

  it('should not flag patch-level upgrade', () => {
    expect(wouldDowngrade('0.4.91', '0.4.90')).toBe(false);
  });
});
