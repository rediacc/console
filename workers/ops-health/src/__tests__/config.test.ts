import { describe, expect, it } from 'vitest';

import { CONFIG, ingestMaxAgeHours, type OpsHealthConfig } from '../config';

const config: OpsHealthConfig = {
  ...CONFIG,
  ingest: { max_age_h: { drift: 36, 'local-*': 12, default: 24 } },
};

describe('ingestMaxAgeHours', () => {
  it('prefers an exact key, then a prefix key, then the default', () => {
    expect(ingestMaxAgeHours('drift', config)).toBe(36);
    expect(ingestMaxAgeHours('local-backup', config)).toBe(12);
    expect(ingestMaxAgeHours('anything-else', config)).toBe(24);
  });

  it('gives a source named like an inherited Object member the default, not a function', () => {
    // `constructor` passes the source name pattern in index.ts.
    expect(ingestMaxAgeHours('constructor', config)).toBe(24);
  });
});
