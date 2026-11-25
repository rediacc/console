import { describe, expect, it } from 'vitest';
import { CliExitError } from '../../../utils/cli-exit-error.js';
import { parseWindow } from '../window.js';

const NOW = new Date('2026-11-25T12:00:00.000Z');

describe('parseWindow', () => {
  it('defaults to the last 24 hours', () => {
    expect(parseWindow({}, NOW)).toEqual({
      from: '2026-11-24T12:00:00.000Z',
      to: '2026-11-25T12:00:00.000Z',
    });
  });

  it('reads spans back from now and ISO instants', () => {
    expect(parseWindow({ since: '90m', until: '2026-11-25T11:00:00Z' }, NOW)).toEqual({
      from: '2026-11-25T10:30:00.000Z',
      to: '2026-11-25T11:00:00.000Z',
    });
    expect(parseWindow({ since: '7d' }, NOW).from).toBe('2026-11-18T12:00:00.000Z');
  });

  it.each([
    [{ since: 'yesterday' }],
    [{ since: '2026-11-25T12:00:00Z', until: '2026-11-25T11:00:00Z' }],
    [{ since: '32d' }],
  ])('refuses %j as a validation error', (options) => {
    expect(() => parseWindow(options, NOW)).toThrow(CliExitError);
  });
});
