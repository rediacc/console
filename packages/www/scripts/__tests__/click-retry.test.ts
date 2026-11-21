import { describe, expect, it } from 'vitest';
import { CLICK_ATTEMPTS, clickWithRetry, REFUSED_BEFORE_DISPATCH } from '../lib/click-retry.js';

type Result = { ok: true } | { ok: false; reason: string };

function harness(results: Result[]) {
  const calls: string[] = [];
  let i = 0;
  const deps = {
    click: () => {
      calls.push('click');
      return results[Math.min(i++, results.length - 1)];
    },
    reveal: () => calls.push('reveal'),
    wait: () => calls.push('wait'),
    log: () => undefined,
  };
  return { deps, calls };
}

describe('REFUSED_BEFORE_DISPATCH', () => {
  it('matches the covered-by refusal the hidden control bar produces', () => {
    expect(REFUSED_BEFORE_DISPATCH.test('Element is covered by <video>')).toBe(true);
    expect(REFUSED_BEFORE_DISPATCH.test('element not visible')).toBe(true);
  });

  it('does not match an unrelated failure', () => {
    expect(REFUSED_BEFORE_DISPATCH.test('browser crashed')).toBe(false);
  });
});

describe('clickWithRetry', () => {
  it('returns at once on success, without waiting or revealing', () => {
    const { deps, calls } = harness([{ ok: true }]);
    expect(clickWithRetry(deps, '.play')).toEqual({ ok: true });
    expect(calls).toEqual(['click']);
  });

  it('retries a covered-by refusal and reveals the controls before each retry', () => {
    const refused: Result = { ok: false, reason: 'Element is covered by <video>' };
    const { deps, calls } = harness([refused, refused, { ok: true }]);
    expect(clickWithRetry(deps, '.play').ok).toBe(true);
    expect(calls).toEqual(['click', 'wait', 'reveal', 'click', 'wait', 'reveal', 'click']);
  });

  it('stops at CLICK_ATTEMPTS and reports the failure', () => {
    const refused: Result = { ok: false, reason: 'covered by <video>' };
    const { deps, calls } = harness([refused]);
    expect(clickWithRetry(deps, '.play').ok).toBe(false);
    expect(calls.filter((c) => c === 'click')).toHaveLength(CLICK_ATTEMPTS);
  });

  it('does not retry a failure that may have reached the page', () => {
    const { deps, calls } = harness([{ ok: false, reason: 'timeout after dispatch' }]);
    expect(clickWithRetry(deps, '.play').ok).toBe(false);
    expect(calls).toEqual(['click']);
  });
});
