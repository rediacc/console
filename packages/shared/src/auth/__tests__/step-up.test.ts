import { describe, expect, it } from 'vitest';
import {
  compareStepUpStrength,
  isStepUpMethod,
  meetsMinimum,
  STEP_UP_METHODS,
  type StepUpMethod,
  sortStrongestFirst,
  strongestHeld,
} from '../step-up.js';

const ORDER = ['passkey', 'totp', 'email', 'password'] as const satisfies readonly StepUpMethod[];
const PAIRS = ORDER.flatMap((a, i) => ORDER.map((b, j) => [a, b, i, j] as const));

describe('step-up rank', () => {
  it('lists the methods strongest first', () => {
    expect([...STEP_UP_METHODS]).toEqual(ORDER);
  });

  describe.each(PAIRS)('%s against %s', (method, minimum, i, j) => {
    it('meetsMinimum follows the rank', () => {
      expect(meetsMinimum(method, minimum)).toBe(i <= j);
    });

    it('compareStepUpStrength follows the rank', () => {
      expect(Math.sign(compareStepUpStrength(method, minimum))).toBe(Math.sign(j - i));
    });
  });

  it('strongestHeld picks the strongest of any subset', () => {
    expect(strongestHeld(['password', 'email'])).toBe('email');
    expect(strongestHeld(['password', 'totp', 'email'])).toBe('totp');
    expect(strongestHeld(['password', 'passkey'])).toBe('passkey');
    expect(strongestHeld(['password'])).toBe('password');
  });

  it('strongestHeld is null for an empty set', () => {
    expect(strongestHeld([])).toBeNull();
  });

  it('sortStrongestFirst orders and deduplicates', () => {
    expect(sortStrongestFirst(['password', 'passkey', 'password', 'email'])).toEqual([
      'passkey',
      'email',
      'password',
    ]);
  });

  it('isStepUpMethod accepts the four methods only', () => {
    for (const method of ORDER) expect(isStepUpMethod(method)).toBe(true);
    expect(isStepUpMethod('sms')).toBe(false);
    expect(isStepUpMethod(undefined)).toBe(false);
  });
});
