/**
 * A repo's env-mode secrets (`REDIACC_SECRET_*`) reach a `term connect`
 * session without riding any command line and without asking anything of the
 * machine's sshd or of the local terminal. One non-interactive ssh call stages
 * them from its stdin into a private file on the machine; the session's remote
 * command loads that file and deletes it before anything else runs.
 *
 * The staging command and the loading prefix are run for real under bash and
 * sh, so the test proves the remote end, not only the strings.
 */

import { execFileSync } from 'node:child_process';
import { mkdtempSync, readdirSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import type { ConnectionDetails } from '../../services/machine/ssh-connection.js';
import {
  consumeStagedSecrets,
  parseStagedSecretsDir,
  STAGE_SECRETS_COMMAND,
  STAGED_SECRETS_TTL_SECONDS,
  secretExportScript,
} from '../../utils/secret-env.js';
import {
  buildEnvPrefix,
  buildRemoteCommand,
  type StagingRunner,
  stageSessionSecrets,
} from '../term.js';

const SECRET = `term-secret 'quoted' \\ back $HOME\nline2`;

const details: ConnectionDetails = {
  host: 'h',
  user: 'repo',
  port: 22,
  privateKey: 'k',
  known_hosts: 'kh',
  datastore: WK_DATASTORE_PATH,
  universalUser: 'u',
  environment: {
    REDIACC_REPOSITORY: 'app',
    DOCKER_HOST: 'unix:///run/docker-1.sock',
    REDIACC_SECRET_DB_PASSWORD: SECRET,
  },
  workingDirectory: `${WK_DATASTORE_PATH}/mounts/x`,
};

/** Runs a remote command locally under bash, the way the sandbox gateway runs it. */
function bashRunner(env: NodeJS.ProcessEnv): StagingRunner {
  return (remoteCommand, input) => {
    try {
      const stdout = execFileSync('bash', ['-c', remoteCommand], { input, env }).toString();
      return Promise.resolve({ code: 0, stdout });
    } catch (error) {
      return Promise.resolve({ code: (error as { status: number }).status, stdout: '' });
    }
  };
}

describe('term connect secret delivery', () => {
  let root: string;

  beforeAll(() => {
    root = mkdtempSync(join(tmpdir(), 'term-stage-'));
  });

  afterAll(() => {
    rmSync(root, { recursive: true, force: true });
  });

  it('leaves secret values out of the session prefix', () => {
    const prefix = buildEnvPrefix(details);
    expect(prefix).not.toContain('term-secret');
    expect(prefix).not.toContain('REDIACC_SECRET_DB_PASSWORD');
    expect(prefix).toContain("export REDIACC_REPOSITORY='app'");
  });

  it('stages the secrets on stdin only, and the session loads them', async () => {
    const calls: { command: string; input: string }[] = [];
    const real = bashRunner({ PATH: process.env.PATH, TMPDIR: root });
    const prefix = await stageSessionSecrets(
      details,
      (command, input) => {
        calls.push({ command, input });
        return real(command, input);
      },
      () => undefined
    );

    expect(calls).toHaveLength(1);
    expect(calls[0].command).not.toContain('term-secret');
    expect(calls[0].command).toContain("export REDIACC_REPOSITORY='app'");
    expect(calls[0].input).toContain('REDIACC_SECRET_DB_PASSWORD=');
    expect(prefix).not.toContain('term-secret');

    // The staged directory is private and holds a private file.
    const [staged] = readdirSync(root);
    expect(staged).toMatch(/^rdc-env\./);
    expect(statSync(join(root, staged)).mode & 0o777).toBe(0o700);
    expect(statSync(join(root, staged, 'env')).mode & 0o777).toBe(0o600);

    // The session's command loads the value intact and removes the directory first.
    const remote = buildRemoteCommand({ command: 'true' }, details, prefix);
    expect(remote.startsWith(prefix)).toBe(true);
    const out = execFileSync('bash', ['-c', `${prefix}printf '%s' "$REDIACC_SECRET_DB_PASSWORD"`]);
    expect(out.toString()).toBe(SECRET);
    expect(readdirSync(root)).toEqual([]);
  });

  it('falls back from an unusable runtime directory, and loads under sh too', () => {
    const env = {
      PATH: process.env.PATH,
      TMPDIR: root,
      XDG_RUNTIME_DIR: join(root, 'missing'),
    };
    const script = secretExportScript({ REDIACC_SECRET_A: SECRET }, () => undefined);
    const stdout = execFileSync('sh', ['-c', STAGE_SECRETS_COMMAND], { input: script, env });
    const dir = parseStagedSecretsDir(stdout.toString());
    expect(dir?.startsWith(`${root}/rdc-env.`)).toBe(true);
    const out = execFileSync('sh', [
      '-c',
      `${consumeStagedSecrets(dir!)}printf '%s' "$REDIACC_SECRET_A"`,
    ]);
    expect(out.toString()).toBe(SECRET);
    expect(readdirSync(root)).toEqual([]);
  });

  it('reports a session whose staged file is gone, and still runs it', () => {
    const out = execFileSync(
      'bash',
      ['-c', `${consumeStagedSecrets(`${root}/rdc-env.gone1234`)}echo ran 2>&1`],
      { stdio: ['ignore', 'pipe', 'pipe'] }
    );
    expect(out.toString()).toBe('ran\n');
  });

  it('skips a secret whose name is not a shell name, warning with the name only', async () => {
    const warnings: string[] = [];
    const inputs: string[] = [];
    const prefix = await stageSessionSecrets(
      {
        ...details,
        environment: {
          'REDIACC_SECRET_BAD-NAME': 'bad-value-9X',
          REDIACC_SECRET_GOOD: 'good',
        },
      },
      (_command, input) => {
        inputs.push(input);
        return Promise.resolve({
          code: 0,
          stdout: `RDC_STAGED_SECRETS=${root}/rdc-env.abcDEF123\n`,
        });
      },
      (message) => warnings.push(message)
    );
    expect(prefix).toContain(`${root}/rdc-env.abcDEF123`);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain('REDIACC_SECRET_BAD-NAME');
    expect(warnings[0]).not.toContain('bad-value-9X');
    expect(inputs[0]).not.toContain('bad-value-9X');
    expect(inputs[0]).toContain("export REDIACC_SECRET_GOOD='good'");
  });

  it('reads a staged directory whose parent holds a space, and refuses one with a .. segment', () => {
    // Review 67e482c0.1: $TMPDIR or $XDG_RUNTIME_DIR may hold any character but a newline; every use quotes the path.
    expect(parseStagedSecretsDir('RDC_STAGED_SECRETS=/tmp/my dir /rdc-env.Ab12Cd34Ef\n')).toBe(
      '/tmp/my dir /rdc-env.Ab12Cd34Ef'
    );
    expect(
      parseStagedSecretsDir('RDC_STAGED_SECRETS=/tmp/../etc/rdc-env.Ab12Cd34Ef\n')
    ).toBeUndefined();
    expect(parseStagedSecretsDir('RDC_STAGED_SECRETS=relative/rdc-env.Ab12\n')).toBeUndefined();
  });

  it('keeps the staged file long enough for an interactive prompt before the session', () => {
    // Review 67e482c0.2: the reaper only removes a session that never began.
    expect(STAGED_SECRETS_TTL_SECONDS).toBeGreaterThanOrEqual(600);
    expect(STAGE_SECRETS_COMMAND).toContain(`sleep ${STAGED_SECRETS_TTL_SECONDS}`);
  });

  it('makes no staging call for a session without secrets', async () => {
    let called = false;
    const prefix = await stageSessionSecrets(
      { ...details, environment: { REDIACC_MACHINE: 'm' } },
      () => {
        called = true;
        return Promise.resolve({ code: 0, stdout: '' });
      },
      () => undefined
    );
    expect(prefix).toBe('');
    expect(called).toBe(false);
  });

  it('fails the session when the staging call fails or prints no directory', async () => {
    for (const result of [
      { code: 1, stdout: '' },
      { code: 0, stdout: 'motd only\n' },
      { code: 0, stdout: 'RDC_STAGED_SECRETS=relative/rdc-env.x\n' },
    ]) {
      await expect(
        stageSessionSecrets(
          details,
          () => Promise.resolve(result),
          () => undefined
        )
      ).rejects.toThrow();
    }
  });
});
