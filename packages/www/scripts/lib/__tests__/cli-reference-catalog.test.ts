import { describe, expect, it } from 'vitest';
import { parseRdcCommand } from '../cli-reference-catalog.js';

describe('parseRdcCommand: a defined flag after a variadic positional is a flag', () => {
  const lines = [
    'rdc backup download mail@prod --to /mnt/usb',
    'rdc backup download mail --store --to /mnt/usb',
    'rdc backup download mail --store --to /mnt/usb --at 2026-10-01T00:00:00Z',
  ];
  for (const line of lines) {
    it(`accepts ${line}`, () => {
      const r = parseRdcCommand(line);
      expect(r.reason).not.toBe('missing-mandatory-option');
      expect(r.ok).toBe(true);
    });
  }

  it('still reports the mandatory option when --to is really absent', () => {
    const r = parseRdcCommand('rdc backup download mail@prod');
    expect(r.ok).toBe(false);
    expect(r.reason).toBe('missing-mandatory-option');
  });
});
