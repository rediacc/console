import { describe, expect, it } from 'vitest';
import { formatDuration, parseDurationSeconds, rpoCron, rpoProblem } from '../duration.js';

describe('parseDurationSeconds', () => {
  it.each([
    ['30s', 30],
    ['15m', 900],
    ['1h30m', 5400],
    ['2d', 172_800],
    [' 5M ', 300],
  ])('%s -> %d', (raw, seconds) => {
    expect(parseDurationSeconds(raw)).toBe(seconds);
  });

  it.each(['', '15', 'm', '1.5h', '0s', '-5m', '5 m', '1h x'])('refuses %j', (raw) => {
    expect(parseDurationSeconds(raw)).toBeUndefined();
  });
});

describe('formatDuration', () => {
  it.each([
    [300, '5m'],
    [5400, '1h30m'],
    [45, '45s'],
    [7200, '2h'],
  ])('%d -> %s', (seconds, text) => {
    expect(formatDuration(seconds)).toBe(text);
    expect(parseDurationSeconds(text)).toBe(seconds);
  });
});

describe('rpoProblem and rpoCron', () => {
  it('refuses below 5 minutes (O6) and names the reason', () => {
    expect(rpoProblem(299)).toMatch(/below 5 minutes/);
    expect(rpoProblem(60)).toMatch(/below 5 minutes/);
  });

  it('refuses a length a timer cannot repeat evenly', () => {
    expect(rpoProblem(420)).toMatch(/divide 60/);
    expect(rpoProblem(5400)).toMatch(/whole hours/);
    expect(rpoProblem(5 * 3600)).toMatch(/dividing 24/);
    expect(rpoProblem(90_000)).toMatch(/24h/);
  });

  it.each([
    [300, '*/5 * * * *'],
    [900, '*/15 * * * *'],
    [1800, '*/30 * * * *'],
    [3600, '0 */1 * * *'],
    [14_400, '0 */4 * * *'],
    [86_400, '0 0 * * *'],
  ])('%d seconds is accepted and ticks as %s', (seconds, cron) => {
    expect(rpoProblem(seconds)).toBeUndefined();
    expect(rpoCron(seconds)).toBe(cron);
  });
});
