import { describe, expect, it } from 'vitest';
import { buildRenetExitError } from '../renet-output.js';

describe('buildRenetExitError', () => {
  it("surfaces renet's cobra Error line", () => {
    expect(buildRenetExitError(1, 'Error: repository x is not mounted\n', '')).toBe(
      'renet exited with code 1: repository x is not mounted'
    );
  });

  it('answers a flag the remote renet does not know with the version-skew message (C12)', () => {
    const stderr = 'Error: unknown flag: --datastore\nUsage:\n  renet list [flags]\n';
    expect(buildRenetExitError(1, stderr, '', 'hermes')).toBe(
      'renet on hermes is older than this CLI; run machine setup'
    );
  });

  it('finds the flag rejection on stdout too, where the bridge relays it', () => {
    expect(
      buildRenetExitError(1, '', "[backup_verify] Error: unknown shorthand flag: 'x' in -x", 'm1')
    ).toBe('renet on m1 is older than this CLI; run machine setup');
  });

  it('keeps the cobra line when no machine name is known', () => {
    expect(buildRenetExitError(1, 'Error: unknown flag: --datastore\n', '')).toBe(
      'renet exited with code 1: unknown flag: --datastore'
    );
  });

  it('leaves every other failure alone with a machine name given', () => {
    expect(buildRenetExitError(2, 'Error: disk full\n', '', 'm1')).toBe(
      'renet exited with code 2: disk full'
    );
  });
});
