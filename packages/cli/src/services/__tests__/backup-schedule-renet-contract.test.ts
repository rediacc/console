/**
 * G9 contract: every ExecStart a scheduled backup unit carries must parse against the flag set renet
 * ACTUALLY declares for `backup snapshot`, read from its Go source.
 *
 * Why the source and not a hand-written list: the unit runs at 03:00 inside a systemd timer, and a
 * flag renet does not know (or a value it refuses) fails there, after `backup schedule` reported
 * success. The two sides agreed on nothing but a string. Reading backup_snapshot.go means a renamed or
 * retyped flag, or a newly GUID-only one, fails THIS test instead.
 *
 * What is checked, mirroring pflag and renet's own validation without executing anything:
 *   - the subcommand is `backup snapshot`;
 *   - every token is a declared long flag (`--name value` or `--name=value`), no positionals;
 *   - Bool flags take no separate value; Int/Int64 values are integers; a `rateFlag` (`--bwlimit`) takes what
 *     renet's pkg/bwrate parses, checked here with the CLI's bandwidthToBytesPerSecond (same grammar, same vectors);
 *   - flags renet passes to requireRepoGUIDs take GUIDs only (renet refuses a repo NAME at run time).
 *
 * The renet submodule is checked out by the CI job that runs these tests (ci-quality.yml, the
 * PACKAGES lane, `submodules: true`); a missing file throws rather than skipping, because a contract
 * check that quietly does not run is the failure this exists to prevent.
 */

import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it } from 'vitest';
import { computeDesiredUnits } from '../backup/backup-schedule-reconcile.js';
import { machineUnitSpecs, type ScheduledStrategy } from '../backup/backup-schedule-targets.js';
import { bandwidthToBytesPerSecond } from '../backup/backup-strategy-validate.js';

const RENET_CMD_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../../../../private/renet/cmd/renet'
);
const SNAPSHOT_GO = path.join(RENET_CMD_DIR, 'backup_snapshot.go');
const GUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type FlagType =
  | 'String'
  | 'StringArray'
  | 'StringSlice'
  | 'Bool'
  | 'Int'
  | 'Int64'
  | 'Duration'
  | 'Rate';

interface SnapshotFlagSet {
  flags: Map<string, FlagType>;
  guidOnly: Set<string>;
}

/** String constants declared across cmd/renet (`FlagDatastore = "datastore"`). */
function renetStringConstants(): Map<string, string> {
  const consts = new Map<string, string>();
  for (const file of readdirSync(RENET_CMD_DIR)) {
    if (!file.endsWith('.go') || file.endsWith('_test.go')) continue;
    const src = readFileSync(path.join(RENET_CMD_DIR, file), 'utf8');
    for (const m of src.matchAll(/^\s*([A-Z]\w*)\s*=\s*"([^"]*)"/gm)) consts.set(m[1], m[2]);
  }
  return consts;
}

/** The flag set `backupSnapshotCmd` registers, and which flags renet holds to GUIDs. */
function readSnapshotFlagSet(): SnapshotFlagSet {
  const src = readFileSync(SNAPSHOT_GO, 'utf8');
  const consts = renetStringConstants();
  const flags = new Map<string, FlagType>();
  for (const m of src.matchAll(/backupSnapshotCmd\.Flags\(\)\.(\w+)\(\s*("([^"]+)"|(\w+))/g)) {
    const name = m[3] ?? consts.get(m[4]);
    if (!name) throw new Error(`cannot resolve flag name ${m[4]} in ${SNAPSHOT_GO}`);
    flags.set(name, m[1] as FlagType);
  }
  // `Flags().Var(&rateFlag{}, "bwlimit", ...)`: a custom pflag.Value, read as its own type.
  for (const m of src.matchAll(
    /backupSnapshotCmd\.Flags\(\)\.Var\(\s*&rateFlag\{\},\s*"([^"]+)"/g
  )) {
    flags.set(m[1], 'Rate');
  }
  if (flags.size === 0) throw new Error(`no backupSnapshotCmd flags found in ${SNAPSHOT_GO}`);
  const guidOnly = new Set([...src.matchAll(/requireRepoGUIDs\(\s*"([\w-]+)"/g)].map((m) => m[1]));
  return { flags, guidOnly };
}

/** pflag's parse of an Int/Int64 value, or renet's rateFlag parse of a Rate value. */
function typedValueProblem(name: string, type: FlagType, value: string): string | undefined {
  if ((type === 'Int' || type === 'Int64') && !/^-?\d+$/.test(value)) {
    return `invalid argument "${value}" for --${name}: not an integer`;
  }
  if (type !== 'Rate') return undefined;
  try {
    bandwidthToBytesPerSecond(value);
    return undefined;
  } catch {
    return `invalid argument "${value}" for --${name}: not a rate`;
  }
}

/** Problems with one flag's value: pflag's type parse, then renet's GUID-only rule. */
function valueProblems(
  name: string,
  type: FlagType,
  value: string | undefined,
  set: SnapshotFlagSet
): string[] {
  if (type === 'Bool') {
    return value === undefined || /^(true|false)$/.test(value)
      ? []
      : [`--${name} is a bool flag, got "${value}"`];
  }
  if (value === undefined) return [`flag needs an argument: --${name}`];
  const problems: string[] = [];
  const typeProblem = typedValueProblem(name, type, value);
  if (typeProblem) problems.push(typeProblem);
  if (set.guidOnly.has(name) && !GUID.test(value)) {
    problems.push(`--${name} takes repository GUIDs only, got "${value}"`);
  }
  return problems;
}

/**
 * Check the flag token at `tokens[i]`. Returns its problems and how many tokens it consumed: pflag
 * takes `--name=value`, or the next token for any non-bool flag.
 */
function flagTokenProblems(
  tokens: string[],
  i: number,
  set: SnapshotFlagSet
): { problems: string[]; consumed: number } {
  const tok = tokens[i];
  if (!tok.startsWith('--')) return { problems: [`unexpected positional "${tok}"`], consumed: 1 };
  const eq = tok.indexOf('=');
  const name = eq === -1 ? tok.slice(2) : tok.slice(2, eq);
  const type = set.flags.get(name);
  if (!type) return { problems: [`unknown flag: --${name}`], consumed: 1 };
  if (eq !== -1)
    return { problems: valueProblems(name, type, tok.slice(eq + 1), set), consumed: 1 };
  if (type === 'Bool') return { problems: [], consumed: 1 };
  return { problems: valueProblems(name, type, tokens.at(i + 1), set), consumed: 2 };
}

/** Problems pflag or renet would raise for one ExecStart line; [] when it parses. */
function snapshotArgvProblems(execStart: string, set: SnapshotFlagSet): string[] {
  const tokens = execStart.trim().split(/\s+/);
  if (tokens[1] !== 'backup' || tokens[2] !== 'snapshot') {
    return [`not a backup snapshot command: ${execStart}`];
  }
  const problems: string[] = [];
  for (let i = 3; i < tokens.length; ) {
    const { problems: found, consumed } = flagTokenProblems(tokens, i, set);
    problems.push(...found);
    i += consumed;
  }
  return problems;
}

const G = {
  mail: '10000000-0000-4000-8000-000000000001',
  mailFork: '10000000-0000-4000-8000-000000000002',
  gitlab: '20000000-0000-4000-8000-000000000001',
  pool: '40000000-0000-4000-8000-000000000001',
};

const config = {
  resources: {
    machines: { m1: { ip: '10.0.0.1', user: 'u', datastore: WK_DATASTORE_PATH } },
    datastores: { pool: { backend: { kind: 'local', machine: 'm1', path: '/mnt/pool' } } },
    repositories: {
      mail: {
        placement: { machine: 'm1' },
        grand: 'latest',
        tags: { latest: { repositoryGuid: G.mail }, trial: { repositoryGuid: G.mailFork } },
      },
      gitlab: {
        placement: { machine: 'm1' },
        grand: 'latest',
        tags: { latest: { repositoryGuid: G.gitlab } },
      },
      poolrepo: {
        placement: { datastore: 'pool' },
        grand: 'latest',
        tags: { latest: { repositoryGuid: G.pool } },
      },
    },
  },
} as never;

const hosted = { kind: 'hosted-service' as const, name: 'chunks' };

/** Strategies covering every argv shape the generator can emit. */
const MATRIX: Record<string, ScheduledStrategy> = {
  all: { schedule: '0 3 * * *', destinations: [hosted] },
  include: { schedule: '0 3 * * *', destinations: [hosted], include: ['mail', 'poolrepo'] },
  includeTag: { schedule: '0 3 * * *', destinations: [hosted], include: ['mail:trial'] },
  exclude: { schedule: '0 3 * * *', destinations: [hosted], exclude: ['gitlab'] },
  cold: { schedule: '0 3 * * 0', destinations: [hosted], mode: 'cold' },
  bwlimit: { schedule: '0 * * * *', destinations: [hosted], bandwidthLimit: '6M' },
  perRepo: {
    schedule: '0 3 * * *',
    destinations: [hosted],
    repoSchedules: { gitlab: '*/30 * * * *' },
  },
  twoDestinations: {
    schedule: '0 3 * * *',
    destinations: [hosted, { ...hosted, name: 'chunks-b' }],
  },
};

function generatedExecStarts(): string[] {
  const strategies = Object.entries(MATRIX).map(([name, cfg]) => ({ name, config: cfg }));
  const units = computeDesiredUnits(
    machineUnitSpecs(strategies, config, 'm1'),
    '/usr/lib/rediacc/renet/current/renet'
  );
  const lines: string[] = [];
  for (const unit of units.values()) {
    for (const line of unit.serviceContent.split('\n')) {
      if (line.startsWith('ExecStart=')) lines.push(line.slice('ExecStart='.length));
    }
  }
  return lines;
}

describe('scheduled ExecStart lines parse against renet backup snapshot (G9)', () => {
  const set = readSnapshotFlagSet();

  it('reads the real flag set, including the GUID-only repo flags', () => {
    expect(set.flags.get('datastore')).toBe('String');
    expect(set.flags.get('bwlimit')).toBe('Rate');
    expect(set.flags.get('parallelism')).toBe('Int');
    expect(set.flags.get('cold')).toBe('Bool');
    expect(set.guidOnly.has('repo')).toBe(true);
  });

  it('every generated ExecStart parses, with no flag or value renet would refuse', () => {
    const lines = generatedExecStarts();
    // One unit per strategy per datastore it reaches, plus the per-repo unit; a matrix that rendered nothing would pass vacuously.
    expect(lines.length).toBeGreaterThanOrEqual(Object.keys(MATRIX).length);
    for (const line of lines) {
      expect({ line, problems: snapshotArgvProblems(line, set) }).toEqual({ line, problems: [] });
    }
  });

  it('the pre-G1 output, a repo NAME on --repo, is refused (control)', () => {
    expect(
      snapshotArgvProblems(
        `/usr/bin/renet backup snapshot --datastore ${WK_DATASTORE_PATH} --repo mail`,
        set
      )
    ).toEqual(['--repo takes repository GUIDs only, got "mail"']);
  });

  it('an ambiguous bandwidth limit, a non-integer parallelism and an unknown flag are refused (control)', () => {
    expect(
      snapshotArgvProblems('/r backup snapshot --bwlimit 100Mb --parallelism two --mode=hot', set)
    ).toEqual([
      'invalid argument "100Mb" for --bwlimit: not a rate',
      'invalid argument "two" for --parallelism: not an integer',
      'unknown flag: --mode',
    ]);
  });
});
