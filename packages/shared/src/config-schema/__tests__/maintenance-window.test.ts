/**
 * The machine `maintenanceWindow` field (D-remedy, X2): `HH:MM-HH:MM` in UTC, the window `rdc machine repair` runs
 * window-only fixes in. Pinned here: it survives a parse (an unknown machine key is stripped), and a malformed window
 * is refused rather than silently read as "never".
 */

import { describe, expect, it } from 'vitest';
import { RdcConfigSchema } from '../schemas.js';

const config = (machine: Record<string, unknown>) => ({
  schemaVersion: 3,
  id: '6f1c2b8e-3d4a-4b5c-8d9e-0f1a2b3c4d5e',
  version: 1,
  resources: { machines: { m1: { ip: '192.0.2.10', user: 'ops', ...machine } } },
});

describe('machine maintenanceWindow', () => {
  it('keeps a valid window through a parse, including one that wraps midnight', () => {
    for (const window of ['00:00-03:00', '23:30-01:30']) {
      const parsed = RdcConfigSchema.parse(config({ maintenanceWindow: window }));
      expect(parsed.resources?.machines?.m1?.maintenanceWindow).toBe(window);
    }
  });

  it('refuses a malformed window', () => {
    for (const window of ['3am-4am', '24:00-01:00', '00:00', '00:60-01:00']) {
      expect(RdcConfigSchema.safeParse(config({ maintenanceWindow: window })).success, window).toBe(
        false
      );
    }
  });

  it('is optional', () => {
    const parsed = RdcConfigSchema.parse(config({}));
    expect(parsed.resources?.machines?.m1?.maintenanceWindow).toBeUndefined();
  });
});
