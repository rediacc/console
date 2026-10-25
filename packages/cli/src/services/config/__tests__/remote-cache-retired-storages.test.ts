import { createEmptyRdcConfig, RdcConfigSchema } from '@rediacc/shared/config-schema';
import { describe, expect, it } from 'vitest';
import type { RdcConfig } from '../../../types/index.js';
import { mergeRemoteIntoCache } from '../remote-cache.js';

describe('mergeRemoteIntoCache', () => {
  it('drops an empty resources.storages carried by a pulled server copy', () => {
    const local = createEmptyRdcConfig() as RdcConfig;
    const pulled = {
      ...createEmptyRdcConfig(),
      resources: { storages: {} },
    } as unknown as RdcConfig;

    const merged = mergeRemoteIntoCache(local, pulled, 3);

    expect('storages' in (merged.resources ?? {})).toBe(false);
    expect(() => RdcConfigSchema.parse(merged)).not.toThrow();
  });
});
