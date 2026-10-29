/**
 * The two timeout classes (agent/plans/PLAN-detached-jobs.md section 20, with
 * the J0b additions): every renet function is in exactly one of them, so a new
 * function in renet's tier map fails here until someone decides whether it
 * moves data or waits on a health gate (24 h) or not (renet's 10-minute default).
 */
import { LICENSE_TIERS } from '@rediacc/shared/renet-contract';
import { describe, expect, it } from 'vitest';
import {
  COMMAND_KIND_TIMEOUT_MS,
  DATA_TRANSFER_TIMEOUT_MS,
  DEFAULT_TIMEOUT_FUNCTIONS,
  LONG_TIMEOUT_FUNCTIONS,
  resolveRenetTimeoutMs,
} from '../renet-command.js';

/** The functions in neither class, or in both. Empty means every function is decided once. */
function unclassified(
  functions: readonly string[],
  long: ReadonlySet<string>,
  short: ReadonlySet<string>
): { neither: string[]; both: string[] } {
  return {
    neither: functions.filter((f) => !long.has(f) && !short.has(f)),
    both: functions.filter((f) => long.has(f) && short.has(f)),
  };
}

describe('renet timeout classes', () => {
  const functions = Object.keys(LICENSE_TIERS);

  it('puts every renet function in exactly one class', () => {
    expect(functions.length).toBeGreaterThan(100);
    expect(unclassified(functions, LONG_TIMEOUT_FUNCTIONS, DEFAULT_TIMEOUT_FUNCTIONS)).toEqual({
      neither: [],
      both: [],
    });
  });

  it('names no function renet does not have', () => {
    const known = new Set(functions);
    const stale = [...LONG_TIMEOUT_FUNCTIONS, ...DEFAULT_TIMEOUT_FUNCTIONS].filter(
      (f) => !known.has(f)
    );
    expect(stale).toEqual([]);
  });

  it('control: a planted function in neither set fails the coverage check', () => {
    const planted = [...functions, 'repository_teleport'];
    expect(
      unclassified(planted, LONG_TIMEOUT_FUNCTIONS, DEFAULT_TIMEOUT_FUNCTIONS).neither
    ).toEqual(['repository_teleport']);
  });

  it('gives the J0b additions and the health-gated lifecycle the 24 h ceiling', () => {
    for (const fn of [
      'backup_snapshot',
      'repository_up',
      'repository_up_all',
      'repository_fork',
      'repository_expand',
      'repository_trim',
      'repository_docker_prune',
      'machine_converge_runtime',
      'datastore_create',
      'setup',
    ]) {
      expect(resolveRenetTimeoutMs(fn, undefined), fn).toBe(DATA_TRANSFER_TIMEOUT_MS);
    }
  });

  it('leaves a short read and repository_down on the default, and lets an explicit value win', () => {
    expect(resolveRenetTimeoutMs('repository_list', undefined)).toBeUndefined();
    expect(resolveRenetTimeoutMs('repository_down', undefined)).toBeUndefined();
    expect(resolveRenetTimeoutMs('repository_list', 5000)).toBe(5000);
  });

  it('classes the command-kind jobs, with list-all on the default', () => {
    expect(COMMAND_KIND_TIMEOUT_MS.setup).toBe(DATA_TRANSFER_TIMEOUT_MS);
    expect(COMMAND_KIND_TIMEOUT_MS['backup-unit']).toBe(DATA_TRANSFER_TIMEOUT_MS);
    expect(COMMAND_KIND_TIMEOUT_MS['daemons-restart']).toBe(DATA_TRANSFER_TIMEOUT_MS);
    expect(COMMAND_KIND_TIMEOUT_MS['list-all']).toBeUndefined();
  });
});
