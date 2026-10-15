/**
 * A repo's env-mode secrets (`REDIACC_SECRET_*`) reach a `term connect`
 * session through the SSH environment, never through the command text. That
 * text is an argument of the local ssh (and of the external terminal), and the
 * machine's sandbox gateway runs it as `bash -c <text>`, so anything in it is
 * readable in `ps` on both hosts.
 */

import { describe, expect, it } from 'vitest';
import type { ConnectionDetails } from '../../services/machine/ssh-connection.js';
import { buildEnvPrefix, sshSessionOptions } from '../term.js';

const SECRET = 'term-secret-value-7Q';

const details: ConnectionDetails = {
  host: 'h',
  user: 'repo',
  port: 22,
  privateKey: 'k',
  known_hosts: 'kh',
  datastore: '/mnt/rediacc',
  universalUser: 'u',
  environment: {
    REDIACC_REPOSITORY: 'app',
    DOCKER_HOST: 'unix:///run/docker-1.sock',
    REDIACC_SECRET_DB_PASSWORD: SECRET,
  },
  workingDirectory: '/mnt/rediacc/mounts/x',
};

describe('term connect secret delivery', () => {
  it('leaves secret values out of the remote command text', () => {
    const prefix = buildEnvPrefix(details);
    expect(prefix).not.toContain(SECRET);
    expect(prefix).not.toContain('REDIACC_SECRET_DB_PASSWORD');
    // The non-secret context still rides along.
    expect(prefix).toContain("export REDIACC_REPOSITORY='app'");
  });

  it('names each secret with SendEnv, carrying no value in the ssh argv', () => {
    const options = sshSessionOptions({ sshOptions: ['-o', 'BatchMode=yes'] }, details);
    expect(options).toEqual(['-o', 'BatchMode=yes', '-o', 'SendEnv=REDIACC_SECRET_DB_PASSWORD']);
    for (const arg of options) expect(arg).not.toContain(SECRET);
  });

  it('adds no SendEnv for a session with no secrets', () => {
    const options = sshSessionOptions(
      { sshOptions: ['-p', '22'] },
      { ...details, environment: { REDIACC_MACHINE: 'm' } }
    );
    expect(options).toEqual(['-p', '22']);
  });
});
