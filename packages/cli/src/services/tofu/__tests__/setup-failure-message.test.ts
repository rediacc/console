import { describe, expect, it } from 'vitest';
import { setupFailureMessage } from '../provision.js';

describe('setupFailureMessage', () => {
  it('names a nonzero exit code', () => {
    expect(setupFailureMessage({ exitCode: 4 })).toBe('Machine setup exited with code 4');
  });

  it('does not call a failure with no exit code "code 0"', () => {
    expect(setupFailureMessage({ exitCode: 0, error: 'step failed' })).toBe(
      'Machine setup failed: step failed'
    );
    expect(setupFailureMessage({ exitCode: 0 })).toBe('Machine setup failed');
  });
});
