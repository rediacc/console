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
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
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
    // Review 2e951e55.1: an indented marker line still counts.
    expect(parseStagedSecretsDir('   RDC_STAGED_SECRETS=/tmp/rdc-env.Ab12Cd34Ef\r\n')).toBe(
      '/tmp/rdc-env.Ab12Cd34Ef'
    );
  });

  it('kills a live reaper and its sleep when the session consumes the file', () => {
    // Review 73f53020.1/.3: the pid in "$d/reaper" is the reaper subshell; its trap stops the sleep it started.
    const base = mkdtempSync(join(tmpdir(), 'rdc-reaper-'));
    // Cleanup runs even when an expectation fails (review 224dd838.2).
    try {
      const stdout = execFileSync('sh', ['-c', STAGE_SECRETS_COMMAND], {
        input: "export REDIACC_SECRET_A='v'\n",
        env: { PATH: process.env.PATH ?? '', TMPDIR: base },
      });
      const dir = parseStagedSecretsDir(stdout.toString());
      expect(dir).toBeDefined();
      const reaper = readFileSync(join(dir as string, 'reaper'), 'utf8').trim();
      const children = () =>
        execFileSync('sh', ['-c', `pgrep -P ${reaper} || true`])
          .toString()
          .trim();
      // A zombie counts as gone (review 224dd838.1): an environment whose init does not reap orphans leaves the exited reaper as Z.
      const alive = (pid: string) =>
        execFileSync('sh', [
          '-c',
          `s=$(ps -o stat= -p ${pid} 2>/dev/null); case "$s" in ''|Z*) echo gone;; *) echo up;; esac`,
        ])
          .toString()
          .trim();
      for (let i = 0; i < 50 && children() === ''; i += 1) execFileSync('sleep', ['0.05']);
      const sleeper = children();
      expect(sleeper).not.toBe('');
      execFileSync('sh', ['-c', `${consumeStagedSecrets(dir as string)}true`]);
      for (let i = 0; i < 50 && (alive(reaper) === 'up' || alive(sleeper) === 'up'); i += 1)
        execFileSync('sleep', ['0.05']);
      expect(alive(reaper)).toBe('gone');
      expect(alive(sleeper)).toBe('gone');
    } finally {
      rmSync(base, { recursive: true, force: true });
    }
  });

  it('loads and deletes a staged directory whose path holds shell metacharacters', () => {
    // Review 2e951e55.3: the path reaches the consumer quoted, so a quote, a dollar and a backtick stay literal.
    const parent = mkdtempSync(join(tmpdir(), "rdc q'$x`y "));
    const dir = join(parent, 'rdc-env.Ab12Cd34Ef');
    mkdirSync(dir, { mode: 0o700 });
    writeFileSync(join(dir, 'env'), "export REDIACC_SECRET_A='v'\n", { mode: 0o600 });
    const out = execFileSync('sh', [
      '-c',
      `${consumeStagedSecrets(dir)}printf '%s' "$REDIACC_SECRET_A"`,
    ]);
    expect(out.toString()).toBe('v');
    expect(existsSync(dir)).toBe(false);
    rmSync(parent, { recursive: true, force: true });
  });

  it('keeps the staged file long enough for an interactive prompt before the session', () => {
    // Review 67e482c0.2: the reaper only removes a session that never began.
    // An exact value (review 2e951e55.2): a later increase keeps plaintext on the remote longer and must be a visible change here.
    expect(STAGED_SECRETS_TTL_SECONDS).toBe(600);
    expect(STAGE_SECRETS_COMMAND).toContain('echo $! > "$d/reaper"');
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
