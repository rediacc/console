import { describe, expect, it } from 'vitest';
import { buildMachineEnvironment, buildRepositoryEnvironment } from '../envCompose.js';

// On the machine REDIACC_DATASTORE names a datastore ("default" inside a Rediaccfile hook), so the datastore path the CLI hands a VS Code session travels as REDIACC_DATASTORE_PATH, the name renet's gateway, sandbox shell and .envrc read.
describe('VS Code session environment', () => {
  it('sends the datastore path as REDIACC_DATASTORE_PATH for a repository', () => {
    const env = buildRepositoryEnvironment({
      teamName: 't',
      machineName: 'm',
      repositoryName: 'app',
      datastore: '/srv/ds',
      repositoryPath: '/mounts/guid',
      universalUser: 'rediacc',
    });
    expect(env.REDIACC_DATASTORE_PATH).toBe('/srv/ds');
    expect(env).not.toHaveProperty('REDIACC_DATASTORE');
  });

  it('sends the datastore path as REDIACC_DATASTORE_PATH for a machine', () => {
    const env = buildMachineEnvironment({
      teamName: 't',
      machineName: 'm',
      datastore: '/srv/ds',
      universalUser: 'rediacc',
    });
    expect(env.REDIACC_DATASTORE_PATH).toBe('/srv/ds');
    expect(env).not.toHaveProperty('REDIACC_DATASTORE');
  });
});
