import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getServerInstallPath } from '../settings.js';

describe('getServerInstallPath', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('never reads the universal user as a datastore path', () => {
    vi.stubEnv('REDIACC_DATASTORE_PATH', undefined);
    vi.stubEnv('REDIACC_DATASTORE_USER', 'rediacc');
    expect(getServerInstallPath()).toBe(`${WK_DATASTORE_PATH}/.vscode-server`);
  });

  it('never reads a datastore name as a datastore path', () => {
    vi.stubEnv('REDIACC_DATASTORE_PATH', undefined);
    vi.stubEnv('REDIACC_DATASTORE', 'default');
    expect(getServerInstallPath()).toBe(`${WK_DATASTORE_PATH}/.vscode-server`);
  });

  it('takes the datastore path from REDIACC_DATASTORE_PATH', () => {
    vi.stubEnv('REDIACC_DATASTORE', 'default');
    vi.stubEnv('REDIACC_DATASTORE_PATH', '/srv/ds-2');
    vi.stubEnv('REDIACC_DATASTORE_USER', 'rediacc');
    expect(getServerInstallPath()).toBe('/srv/ds-2/.vscode-server');
  });

  it('prefers an explicit datastore path', () => {
    vi.stubEnv('REDIACC_DATASTORE_PATH', '/srv/ds-2');
    expect(getServerInstallPath('/srv/ds-3')).toBe('/srv/ds-3/.vscode-server');
  });
});
