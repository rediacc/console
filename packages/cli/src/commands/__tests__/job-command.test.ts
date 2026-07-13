/**
 * Tests for the `rdc job` command surface.
 *
 * These cover the WIRING, not the SSH: that every verb is registered, that the
 * flags an operator types are parsed into the right values, and — the part with
 * teeth — that the contract metadata says what the proxy and the MCP layer will
 * act on. A `job cancel` that is not marked destructive is a command an agent
 * will happily run unprompted, and a `job list` mis-planed as `config` would be
 * offered for remote execution it cannot actually perform.
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it } from 'vitest';
import { COMMAND_METADATA } from '../../config/command-metadata.js';
import { COMMAND_PLANES } from '../../config/command-planes.js';
import { registerJobCommands } from '../job.js';

/** Build a bare program with only the job commands registered. */
function jobProgram(): Command {
  const program = new Command();
  program.exitOverride(); // throw instead of process.exit, so tests can assert
  program.option('-o, --output <format>', 'output format', 'table');
  registerJobCommands(program);
  return program;
}

function jobCommand(program: Command, name: string): Command {
  const job = program.commands.find((c) => c.name() === 'job');
  if (!job) throw new Error('job command group was not registered');

  const sub = job.commands.find((c) => c.name() === name);
  if (!sub) throw new Error(`job ${name} was not registered`);

  return sub;
}

describe('rdc job command surface', () => {
  let program: Command;

  beforeEach(() => {
    program = jobProgram();
  });

  it('registers every verb an operator needs to manage a detached job', () => {
    const job = program.commands.find((c) => c.name() === 'job');
    expect(job).toBeDefined();

    const verbs = job?.commands.map((c) => c.name()).sort();
    expect(verbs).toEqual(['cancel', 'gc', 'list', 'logs', 'status']);
  });

  /**
   * Every verb acts on ONE machine, so -m is required. Without it the command
   * would have no idea whose spool to read.
   */
  it('every verb requires --machine', () => {
    for (const verb of ['list', 'status', 'logs', 'cancel', 'gc']) {
      const machine = jobCommand(program, verb).options.find((o) => o.long === '--machine');

      expect(machine, `job ${verb} is missing --machine`).toBeDefined();
      expect(machine?.required || machine?.mandatory, `job ${verb} --machine is optional`).toBe(
        true
      );
    }
  });

  /**
   * A single job is addressed by name, the whole spool is not. `status` and
   * `logs` name the job with a required POSITIONAL `<job-id>` (the first real
   * positional conversion of P4's ref work); `cancel` still uses `--id`; `list`
   * and `gc` act on the whole spool, so they take neither.
   */
  it('addresses a single job by name exactly where one job is meant', () => {
    for (const verb of ['status', 'logs']) {
      const args = jobCommand(program, verb).registeredArguments;
      expect(
        args.map((a) => a.name()),
        `job ${verb} positionals`
      ).toEqual(['job-id']);
      expect(args[0].required, `job ${verb} <job-id> should be required`).toBe(true);
      // ...and no leftover --id flag.
      const id = jobCommand(program, verb).options.find((o) => o.long === '--id');
      expect(id, `job ${verb} should not also carry --id`).toBeUndefined();
    }

    const cancelId = jobCommand(program, 'cancel').options.find((o) => o.long === '--id');
    expect(cancelId, 'job cancel is missing --id').toBeDefined();
    expect(cancelId?.mandatory, 'job cancel --id should be required').toBe(true);

    for (const verb of ['list', 'gc']) {
      expect(jobCommand(program, verb).registeredArguments, `job ${verb} positionals`).toHaveLength(
        0
      );
      const id = jobCommand(program, verb).options.find((o) => o.long === '--id');
      expect(id, `job ${verb} should not take --id`).toBeUndefined();
    }
  });

  it('logs offers --follow and --since-line, the two resume controls', () => {
    const logs = jobCommand(program, 'logs');
    const longs = logs.options.map((o) => o.long);

    expect(longs).toContain('--follow');
    expect(longs).toContain('--since-line');
  });

  /** Destructive verbs take -y, so they can be confirmed or scripted. */
  it('cancel and gc take --yes; the read-only verbs do not', () => {
    for (const verb of ['cancel', 'gc']) {
      const yes = jobCommand(program, verb).options.find((o) => o.long === '--yes');
      expect(yes, `job ${verb} is missing --yes`).toBeDefined();
    }

    for (const verb of ['list', 'status']) {
      const yes = jobCommand(program, verb).options.find((o) => o.long === '--yes');
      expect(yes, `job ${verb} should not need --yes`).toBeUndefined();
    }
  });

  it('gc offers --older-than', () => {
    const longs = jobCommand(program, 'gc').options.map((o) => o.long);
    expect(longs).toContain('--older-than');
  });
});

/**
 * The contract is what the proxy and the web console trust. If a job verb were
 * mis-planed, it would either be refused for remote execution it can perform,
 * or offered for one it cannot.
 */
describe('rdc job command policy', () => {
  it('the job domain is machine-plane', () => {
    // Every verb SSHes to a machine to drive `renet job ...` against its spool.
    expect(COMMAND_PLANES.job.plane).toBe('machine');
  });

  it('is not marked interactive, so a headless executor can drive it', () => {
    // Even `logs --follow` streams to stdout and ends on its own when the job
    // finishes; it never needs a TTY.
    expect(COMMAND_PLANES.job.interactive).toBeFalsy();
  });

  it('cancel and gc are DESTRUCTIVE: they stop work and delete logs', () => {
    expect(COMMAND_METADATA['job cancel'].mcp?.destructive).toBe(true);
    expect(COMMAND_METADATA['job gc'].mcp?.destructive).toBe(true);
  });

  it('list, status and logs are reads', () => {
    for (const path of ['job list', 'job status', 'job logs']) {
      expect(COMMAND_METADATA[path].mcp?.destructive, `${path} should not be destructive`).toBe(
        false
      );
      expect(COMMAND_METADATA[path].mcp?.timeout, `${path} should use the read timeout`).toBe(
        'read'
      );
    }
  });

  /**
   * An agent cannot usefully block on a stream that only ends when the job does,
   * so --follow is kept out of the MCP schema; the agent polls `job status`.
   */
  it('job logs hides --follow from agents', () => {
    expect(COMMAND_METADATA['job logs'].mcp?.excludeOptions).toContain('follow');
  });
});
