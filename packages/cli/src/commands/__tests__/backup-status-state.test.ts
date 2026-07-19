import { describe, expect, it } from 'vitest';
import { describeServiceState } from '../backup-ops.js';

describe('describeServiceState', () => {
  // The regression: `failed` used to collapse into `idle`, so a backup that had
  // been broken for six days reported the same thing as one sitting healthily
  // between runs.
  it('never presents a failed unit as idle', () => {
    expect(describeServiceState('failed')).not.toBe('idle');
  });

  it('reports a failed unit as FAILED', () => {
    expect(describeServiceState('failed')).toBe('FAILED');
  });

  it.each(['active', 'activating'])('reports %s as RUNNING', (state) => {
    expect(describeServiceState(state)).toBe('RUNNING');
  });

  it.each(['inactive', ''])('reports %j as idle', (state) => {
    expect(describeServiceState(state)).toBe('idle');
  });

  // An unrecognised systemd state is shown verbatim rather than bucketed, so a
  // state this code has not met yet cannot be silently normalised into "fine".
  it.each(['deactivating', 'reloading', 'maintenance'])('passes %s through', (state) => {
    expect(describeServiceState(state)).toBe(state);
  });

  it('distinguishes all three operator-relevant outcomes', () => {
    const seen = new Set(['active', 'failed', 'inactive'].map(describeServiceState));
    expect(seen.size).toBe(3);
  });
});
