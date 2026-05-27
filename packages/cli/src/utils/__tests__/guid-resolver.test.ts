import { describe, expect, it, vi } from 'vitest';

// guid-resolver imports configService at module load (used only by loadGuidMap).
// Stub it so importing the pure resolver functions has no side effects.
vi.mock('../../services/config-resources.js', () => ({
  configService: { getRepositoryGuidMap: vi.fn(() => Promise.resolve({})) },
}));

import { createRepoNameResolver } from '../guid-resolver.js';

const GUID = '0bfd1f65-7926-4912-a012-8bd94dcb28c2';

describe('createRepoNameResolver', () => {
  it('prefers the local config name and strips :latest', () => {
    const resolve = createRepoNameResolver({ [GUID]: 'mautic:latest' });
    expect(resolve(GUID, 'demo-stackoverflow:kopya3')).toEqual({
      name: 'mautic',
      source: 'config',
    });
  });

  it('keeps a non-latest config tag', () => {
    const resolve = createRepoNameResolver({ [GUID]: 'mautic:staging' });
    expect(resolve(GUID)).toEqual({ name: 'mautic:staging', source: 'config' });
  });

  it('falls back to the server repo_name when config has no entry', () => {
    const resolve = createRepoNameResolver({});
    expect(resolve(GUID, 'demo-stackoverflow:kopya3')).toEqual({
      name: 'demo-stackoverflow:kopya3',
      source: 'server',
    });
  });

  it('strips :latest from the server name too', () => {
    const resolve = createRepoNameResolver({});
    expect(resolve(GUID, 'nextcloud:latest')).toEqual({
      name: 'nextcloud',
      source: 'server',
    });
  });

  it('falls back to the bare GUID when neither config nor server knows the name', () => {
    const resolve = createRepoNameResolver({});
    expect(resolve(GUID)).toEqual({ name: GUID, source: 'guid' });
    expect(resolve(GUID, '')).toEqual({ name: GUID, source: 'guid' });
  });
});
