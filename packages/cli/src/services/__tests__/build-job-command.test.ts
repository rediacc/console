/**
 * Tests for the `renet job ...` remote command builders.
 *
 * The env prefix on `job start` is the part that actually matters. `job start`
 * snapshots its own environment into the job's spool so that `job run`, which
 * systemd spawns with a CLEAN environment, can re-inject it. renet captures
 * exactly five things (REDIACC_SECRET_*, REDIACC_OTLP_*, REDIACC_ENVIRONMENT,
 * REDIACC_TELEMETRY_DISABLED, KUBECONFIG), so anything missing from the launch
 * is silently absent from every detached deployment: a repo's secrets would just
 * vanish, and the failure would look like a broken app rather than a broken CLI.
 * The secret ones ride stdin ahead of the vault, the rest the command's prefix.
 *
 * The environment is composed by buildRenetEnv, the SAME function the
 * synchronous path uses, and these tests build it that way rather than hand-
 * writing a string, so they exercise the real composition and inherit its
 * telemetry rules (renet#51): an opt-out must never ship OTLP credentials.
 */

import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it } from 'vitest';
import {
  buildJobCancelCommand,
  buildJobGcCommand,
  buildJobListCommand,
  buildJobLogsCommand,
  buildJobStartCommand,
  buildJobStatusCommand,
  InvalidJobIdError,
} from '../executor/job-client.js';
import { buildRenetEnv } from '../executor/local-executor.js';
import { STDIN_ENV_READER } from '../executor/renet-launch.js';

const RENET = '/usr/bin/renet';
const JOB_ID = 'j18c1994eaa33d30d-3d9813b2';
const CREDS = { user: 'otlp-eu-abc123', pass: 'base64url-pass_-_' };

/** Compose the start launch the way production does. */
function startLaunch(
  env: Parameters<typeof buildRenetEnv>[0],
  extra: { timeoutMs?: number; debug?: boolean } = {}
): { command: string; stdinPrefix: string } {
  return buildJobStartCommand({
    remoteRenetPath: RENET,
    env: buildRenetEnv(env),
    ...extra,
  });
}

/** The start command alone. */
function startCommand(
  env: Parameters<typeof buildRenetEnv>[0],
  extra: { timeoutMs?: number; debug?: boolean } = {}
): string {
  return startLaunch(env, extra).command;
}

/** The secret-carrying form: root bash reads the stdin records, then execs renet. */
function stdinLaunch(invocation: string): string {
  const script = `${STDIN_ENV_READER}${invocation}`;
  return `sudo bash -c '${script.replaceAll("'", "'\\''")}'`;
}

describe('buildJobStartCommand', () => {
  it('bare: no env prefix', () => {
    expect(startCommand({ isDevelopment: false, telemetryDisabled: false })).toBe(
      `sudo '/usr/bin/renet' job start --executor local --json`
    );
  });

  it('carries OTLP credentials on stdin so the job can emit telemetry', () => {
    expect(
      startLaunch({ isDevelopment: false, telemetryDisabled: false, otlpCreds: CREDS })
    ).toEqual({
      command: stdinLaunch(`'/usr/bin/renet' job start --executor local --json`),
      stdinPrefix: 'REDIACC_OTLP_USER=otlp-eu-abc123\0REDIACC_OTLP_PASS=base64url-pass_-_\0\0',
    });
  });

  it('telemetry opt-out: propagates the disable and ships NO credentials', () => {
    // otlpCreds present, and must still be ignored.
    const cmd = startCommand({ isDevelopment: false, telemetryDisabled: true, otlpCreds: CREDS });

    expect(cmd).toContain('REDIACC_TELEMETRY_DISABLED=1');
    expect(cmd).not.toContain('REDIACC_OTLP_USER');
    expect(cmd).not.toContain('REDIACC_OTLP_PASS');
  });

  it('carries per-repo env secrets into the job environment, on stdin', () => {
    const launch = startLaunch({
      isDevelopment: false,
      telemetryDisabled: false,
      envSecrets: { REDIACC_SECRET_DB_PASSWORD: "p'wd", REDIACC_SECRET_API_KEY: 'k1' },
    });

    // Verbatim on stdin, absent from the command: a quote cannot break out of anything.
    expect(launch.stdinPrefix).toBe(
      "REDIACC_SECRET_DB_PASSWORD=p'wd\0REDIACC_SECRET_API_KEY=k1\0\0"
    );
    expect(launch.command).not.toContain("p'wd");
    expect(launch.command).not.toContain('k1');
  });

  it('carries KUBECONFIG for a cluster target', () => {
    const cmd = startCommand({
      isDevelopment: false,
      telemetryDisabled: false,
      kubeconfig: `${WK_DATASTORE_PATH}/mounts/abc/kubeconfig`,
    });

    expect(cmd).toContain(`KUBECONFIG='${WK_DATASTORE_PATH}/mounts/abc/kubeconfig'`);
  });

  it('renders the timeout as a Go duration', () => {
    const cmd = startCommand(
      { isDevelopment: false, telemetryDisabled: false },
      { timeoutMs: 600_000 }
    );

    expect(cmd).toContain('--timeout 600000ms');
  });

  it('omits the timeout flag when none was given, so renet uses its own default', () => {
    expect(startCommand({ isDevelopment: false, telemetryDisabled: false })).not.toContain(
      '--timeout'
    );
  });

  /**
   * The vault carries the repo credential and every file-mode secret. It goes
   * over stdin, exactly as `renet execute` takes it. If it ever appeared in the
   * command string it would be visible in `ps` on the machine.
   */
  it('never puts the vault or a password on the command line', () => {
    const cmd = startCommand(
      {
        isDevelopment: true,
        telemetryDisabled: false,
        otlpCreds: CREDS,
        envSecrets: { REDIACC_SECRET_X: 'x' },
        kubeconfig: '/k',
      },
      { timeoutMs: 1000, debug: true }
    );

    expect(cmd).not.toContain('--vault');
    expect(cmd).not.toContain('--master-password');
    expect(cmd).not.toContain(CREDS.pass);
    expect(cmd).not.toContain('REDIACC_SECRET_X');
  });

  it('all env vars together, in a stable order', () => {
    expect(
      startLaunch({
        isDevelopment: true,
        telemetryDisabled: false,
        otlpCreds: CREDS,
        envSecrets: { REDIACC_SECRET_A: 'a' },
        kubeconfig: '/k',
      })
    ).toEqual({
      command: stdinLaunch(
        `env REDIACC_ENVIRONMENT=development KUBECONFIG='/k' '/usr/bin/renet' job start --executor local --json`
      ),
      stdinPrefix:
        'REDIACC_OTLP_USER=otlp-eu-abc123\0REDIACC_OTLP_PASS=base64url-pass_-_\0REDIACC_SECRET_A=a\0\0',
    });
  });
});

describe('buildJobLogsCommand', () => {
  it('a fresh attach asks for everything', () => {
    expect(
      buildJobLogsCommand({ remoteRenetPath: RENET, jobId: JOB_ID, sinceLine: 0, follow: true })
    ).toBe(`sudo '/usr/bin/renet' job logs --id ${JOB_ID} --since-line 0 --follow`);
  });

  it('a resume asks only for what it has not seen', () => {
    expect(
      buildJobLogsCommand({ remoteRenetPath: RENET, jobId: JOB_ID, sinceLine: 42, follow: true })
    ).toBe(`sudo '/usr/bin/renet' job logs --id ${JOB_ID} --since-line 42 --follow`);
  });

  it('can replay without following', () => {
    expect(
      buildJobLogsCommand({ remoteRenetPath: RENET, jobId: JOB_ID, sinceLine: 0, follow: false })
    ).not.toContain('--follow');
  });

  /**
   * No secrets on a log tail. Reading the spool needs no credentials, and
   * handing them over anyway would be a second, pointless exposure of them.
   */
  it('carries no env prefix', () => {
    const cmd = buildJobLogsCommand({
      remoteRenetPath: RENET,
      jobId: JOB_ID,
      sinceLine: 0,
      follow: true,
    });

    expect(cmd).not.toContain('env ');
    expect(cmd).not.toContain('REDIACC_');
  });
});

describe('buildJobStatusCommand / buildJobCancelCommand / buildJobListCommand / buildJobGcCommand', () => {
  it('status asks for JSON', () => {
    expect(buildJobStatusCommand({ remoteRenetPath: RENET, jobId: JOB_ID })).toBe(
      `sudo '/usr/bin/renet' job status --id ${JOB_ID} --json`
    );
  });

  it('cancel asks for JSON', () => {
    expect(buildJobCancelCommand({ remoteRenetPath: RENET, jobId: JOB_ID })).toBe(
      `sudo '/usr/bin/renet' job cancel --id ${JOB_ID} --json`
    );
  });

  it('list asks for JSON', () => {
    expect(buildJobListCommand({ remoteRenetPath: RENET })).toBe(
      `sudo '/usr/bin/renet' job list --json`
    );
  });

  it('gc renders the age as a Go duration in hours', () => {
    expect(buildJobGcCommand({ remoteRenetPath: RENET, olderThanHours: 168 })).toBe(
      `sudo '/usr/bin/renet' job gc --older-than 168h --json`
    );
  });
});

/**
 * Every builder that interpolates a job id validates it first. The id arrives as
 * JSON from the machine and lands in a shell command, so a malformed one must
 * never reach the shell.
 */
describe('job id validation in the builders', () => {
  const injected = 'j1-deadbeef; rm -rf /';

  it('job logs refuses an injected id', () => {
    expect(() =>
      buildJobLogsCommand({ remoteRenetPath: RENET, jobId: injected, sinceLine: 0, follow: true })
    ).toThrow(InvalidJobIdError);
  });

  it('job status refuses an injected id', () => {
    expect(() => buildJobStatusCommand({ remoteRenetPath: RENET, jobId: injected })).toThrow(
      InvalidJobIdError
    );
  });

  it('job cancel refuses an injected id', () => {
    expect(() => buildJobCancelCommand({ remoteRenetPath: RENET, jobId: injected })).toThrow(
      InvalidJobIdError
    );
  });
});

describe('a renet path with shell metacharacters stays one word', () => {
  const HOSTILE = "/opt/my renet/o'brien;rm -rf x/renet";
  const QUOTED = `'/opt/my renet/o'\\''brien;rm -rf x/renet'`;

  it('quotes the path in every job subcommand', () => {
    expect(buildJobStatusCommand({ remoteRenetPath: HOSTILE, jobId: JOB_ID })).toBe(
      `sudo ${QUOTED} job status --id ${JOB_ID} --json`
    );
    expect(buildJobListCommand({ remoteRenetPath: HOSTILE })).toBe(
      `sudo ${QUOTED} job list --json`
    );
    expect(buildJobGcCommand({ remoteRenetPath: HOSTILE, olderThanHours: 1 })).toBe(
      `sudo ${QUOTED} job gc --older-than 1h --json`
    );
    expect(buildJobCancelCommand({ remoteRenetPath: HOSTILE, jobId: JOB_ID })).toBe(
      `sudo ${QUOTED} job cancel --id ${JOB_ID} --json`
    );
  });
});
