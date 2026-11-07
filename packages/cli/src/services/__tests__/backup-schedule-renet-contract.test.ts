/**
 * G9 contract: every ExecStart a scheduled backup unit carries must parse against the flag set renet
 * ACTUALLY declares for its subcommand (`backup snapshot`, `backup verify`, `backup report`), read from its Go source.
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
const SUBCOMMANDS = {
  snapshot: { file: 'backup_snapshot.go', cmdVar: 'backupSnapshotCmd' },
  verify: { file: 'backup_verify.go', cmdVar: 'backupVerifyCmd' },
  report: { file: 'backup_report.go', cmdVar: 'backupReportCmd' },
} as const;
type Subcommand = keyof typeof SUBCOMMANDS;
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

type FlagSets = Record<Subcommand, SnapshotFlagSet>;

/** String constants declared across cmd/renet (`FlagDatastore = "datastore"`, and the unexported `flagTarget = "target"` of the target flags). */
function renetStringConstants(): Map<string, string> {
  const consts = new Map<string, string>();
  for (const file of readdirSync(RENET_CMD_DIR)) {
    if (!file.endsWith('.go') || file.endsWith('_test.go')) continue;
    const src = readFileSync(path.join(RENET_CMD_DIR, file), 'utf8');
    for (const m of src.matchAll(/^\s*([A-Za-z]\w*)\s*=\s*"([^"]*)"/gm)) consts.set(m[1], m[2]);
  }
  return consts;
}

/** The flag set one subcommand registers (`cmdVar.Flags().X(...)`, or a `f := cmdVar.Flags()` alias), and which flags renet holds to GUIDs. */
function readFlagSet(sub: Subcommand): SnapshotFlagSet {
  const { file, cmdVar } = SUBCOMMANDS[sub];
  const goFile = path.join(RENET_CMD_DIR, file);
  const src = readFileSync(goFile, 'utf8');
  const consts = renetStringConstants();
  // `f := cmdVar.Flags()` followed by `f.String(...)` is the other registration style in cmd/renet.
  const alias = new RegExp(`(\\w+)\\s*:=\\s*${cmdVar}\\.Flags\\(\\)`).exec(src)?.[1];
  const receivers = [`${cmdVar}\\.Flags\\(\\)`, ...(alias ? [alias] : [])].join('|');
  const flags = new Map<string, FlagType>();
  for (const m of src.matchAll(
    new RegExp(`(?:${receivers})\\.(\\w+)\\(\\s*("([^"]+)"|(\\w+))`, 'g')
  )) {
    if (m[1] === 'Var' || m[1] === 'AddCommand') continue;
    const name = m[3] ?? consts.get(m[4]);
    if (!name) throw new Error(`cannot resolve flag name ${m[4]} in ${goFile}`);
    flags.set(name, m[1] as FlagType);
  }
  // `Flags().Var(&rateFlag{...}, "bwlimit", ...)`: a custom pflag.Value, read as its own type.
  for (const m of src.matchAll(
    new RegExp(`(?:${receivers})\\.Var\\(\\s*&rateFlag\\{[^}]*\\},\\s*"([^"]+)"`, 'g')
  )) {
    flags.set(m[1], 'Rate');
  }
  if (flags.size === 0) throw new Error(`no ${cmdVar} flags found in ${goFile}`);
  const guidOnly = new Set([...src.matchAll(/requireRepoGUIDs\(\s*"([\w-]+)"/g)].map((m) => m[1]));
  return { flags, guidOnly };
}

function readFlagSets(): FlagSets {
  return {
    snapshot: readFlagSet('snapshot'),
    verify: readFlagSet('verify'),
    report: readFlagSet('report'),
  };
}

/** pflag's parse of an Int/Int64 value, or renet's rateFlag parse of a Rate value. */
function typedValueProblem(name: string, type: FlagType, value: string): string | undefined {
  if ((type === 'Int' || type === 'Int64') && !/^-?\d+$/.test(value)) {
    return `invalid argument "${value}" for --${name}: not an integer`;
  }
  if (type === 'Duration' && !/^(\d+(\.\d+)?(ns|us|µs|ms|s|m|h))+$/.test(value)) {
    return `invalid argument "${value}" for --${name}: not a duration`;
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
function argvProblems(execStart: string, sets: FlagSets): string[] {
  const tokens = execStart.trim().split(/\s+/);
  const sub = tokens[2] as Subcommand;
  if (tokens[1] !== 'backup' || !(sub in SUBCOMMANDS)) {
    return [`not a backup snapshot, verify or report command: ${execStart}`];
  }
  const set = sets[sub];
  const problems: string[] = [];
  for (let i = 3; i < tokens.length; ) {
    // The report's --reason is one single-quoted word, which systemd and the shell read as one argument.
    if (tokens[i] === '--reason') {
      const quoted = tokens.slice(i + 1).join(' ');
      if (!/^'[^']*'$/.test(quoted)) {
        problems.push(`--reason must be one quoted argument, got ${quoted}`);
      }
      break;
    }
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
    repoTargets: { gitlab: { rpo: '30m' } },
  },
  // Every flag a declared target can add, at both levels: the strategy's own target and a per-repo one.
  rpoStrategy: {
    schedule: '0 3 * * *',
    destinations: [hosted],
    exclude: ['gitlab'],
    rpo: '15m',
    indexEvery: '2h',
    hookTimeout: '45s',
    hookFailure: 'abort',
  },
  rpoRepoFull: {
    schedule: '0 3 * * *',
    destinations: [hosted],
    repoTargets: {
      'mail:trial': {
        rpo: '5m',
        cellSize: '1M',
        indexEvery: '1h',
        hookTimeout: '1m30s',
        hookFailure: 'continue',
      },
    },
  },
  // No two-destination entry: the second destination needs a non-home `--store`, which the renet source this contract reads does not declare yet; the generator's own tests cover the multi-destination unit.
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
  const set = readFlagSets();

  it('reads the real flag set, including the GUID-only repo flags', () => {
    expect(set.snapshot.flags.get('datastore')).toBe('String');
    expect(set.snapshot.flags.get('bwlimit')).toBe('Rate');
    expect(set.snapshot.flags.get('parallelism')).toBe('Int');
    expect(set.snapshot.flags.get('cold')).toBe('Bool');
    expect(set.snapshot.flags.get('expected-interval')).toBe('Duration');
    expect(set.snapshot.flags.get('target')).toBe('Duration');
    expect(set.snapshot.flags.get('deadline')).toBe('Duration');
    expect(set.snapshot.flags.get('hook-timeout')).toBe('Duration');
    expect(set.snapshot.flags.get('hook-failure')).toBe('String');
    expect(set.snapshot.flags.get('index-every')).toBe('Duration');
    expect(set.snapshot.flags.get('cell-bytes')).toBe('Int64');
    expect(set.snapshot.guidOnly.has('repo')).toBe(true);
    expect(set.verify.flags.get('level')).toBe('String');
    expect(set.verify.flags.get('next-due')).toBe('String');
    expect(set.verify.flags.get('read-bwlimit')).toBe('Rate');
    expect(set.verify.guidOnly.has('exclude-repo')).toBe(true);
    expect(set.report.flags.get('kind')).toBe('String');
    expect(set.report.flags.get('reason')).toBe('String');
    expect(set.report.guidOnly.has('exclude-repo')).toBe(true);
  });

  it('every generated ExecStart parses, with no flag or value renet would refuse', () => {
    const lines = generatedExecStarts();
    // One unit per strategy per datastore it reaches, plus the per-repo unit; a matrix that rendered nothing would pass vacuously.
    expect(lines.length).toBeGreaterThanOrEqual(Object.keys(MATRIX).length);
    for (const line of lines) {
      expect({ line, problems: argvProblems(line, set) }).toEqual({ line, problems: [] });
    }
  });

  it('renders all three subcommands, and every flag of the verify and report lines is declared (control)', () => {
    const lines = generatedExecStarts();
    for (const sub of ['snapshot', 'verify', 'report']) {
      expect(lines.some((l) => l.split(' ')[2] === sub)).toBe(true);
    }
    expect(argvProblems('/r backup verify --level spot --nope', set)).toEqual([
      'unknown flag: --nope',
    ]);
    expect(argvProblems('/r backup report --accept-identity-change', set)).toEqual([
      'unknown flag: --accept-identity-change',
    ]);
    expect(argvProblems('/r backup snapshot --expected-interval soon', set)).toEqual([
      'invalid argument "soon" for --expected-interval: not a duration',
    ]);
    expect(argvProblems('/r backup report --reason unquoted words', set)).toEqual([
      '--reason must be one quoted argument, got unquoted words',
    ]);
  });

  it('the target flags the generator emits are all rendered, and a malformed one is refused (control)', () => {
    const lines = generatedExecStarts().filter((l) => l.includes(' --target '));
    expect(lines.length).toBeGreaterThanOrEqual(3);
    const all = lines.join('\n');
    for (const flag of [
      '--deadline',
      '--hook-timeout',
      '--hook-failure',
      '--index-every',
      '--cell-bytes 1048576',
    ]) {
      expect(all).toContain(flag);
    }
    expect(argvProblems('/r backup snapshot --target soon', set)).toEqual([
      'invalid argument "soon" for --target: not a duration',
    ]);
    expect(argvProblems('/r backup snapshot --cell-bytes 1M', set)).toEqual([
      'invalid argument "1M" for --cell-bytes: not an integer',
    ]);
  });

  it('the pre-G1 output, a repo NAME on --repo, is refused (control)', () => {
    expect(
      argvProblems(
        `/usr/bin/renet backup snapshot --datastore ${WK_DATASTORE_PATH} --repo mail`,
        set
      )
    ).toEqual(['--repo takes repository GUIDs only, got "mail"']);
  });

  it('an ambiguous bandwidth limit, a non-integer parallelism and an unknown flag are refused (control)', () => {
    expect(
      argvProblems('/r backup snapshot --bwlimit 100Mb --parallelism two --mode=hot', set)
    ).toEqual([
      'invalid argument "100Mb" for --bwlimit: not a rate',
      'invalid argument "two" for --parallelism: not an integer',
      'unknown flag: --mode',
    ]);
  });
});
