/**
 * Lookups over a CliContract that the command line core needs on every keystroke,
 * built once per contract object and cached.
 */
import type {
  CliContract,
  ContractCommand,
  ContractOption,
  ContractPositional,
  PositionalKind,
  ResourceKind,
} from '../cli-contract/types.js';

/**
 * Options of the root `rdc` command. They are accepted before or after the
 * command path and never belong to a command's own form, so they are not in the
 * contract; a command's own option of the same long name wins.
 * A test compares this list with the root options registered in packages/cli/src/cli.ts.
 */
export const GLOBAL_OPTIONS: readonly {
  long: string;
  short?: string;
  valueTaking: boolean;
}[] = [
  { long: 'output', short: 'o', valueTaking: true },
  { long: 'config', valueTaking: true },
  { long: 'lang', short: 'l', valueTaking: true },
  { long: 'quiet', short: 'q', valueTaking: false },
  { long: 'yes', short: 'y', valueTaking: false },
  { long: 'fields', valueTaking: true },
  { long: 'proxy', valueTaking: true },
  { long: 'license-region', valueTaking: true },
  { long: 'accept-terms', valueTaking: false },
  { long: 'background', short: 'b', valueTaking: false },
  { long: 'help', short: 'h', valueTaking: false },
  { long: 'version', short: 'V', valueTaking: false },
];

/** A recognised flag: a command's own option, or a root option. */
export interface FlagSpec {
  long: string;
  short?: string;
  valueTaking: boolean;
  variadic: boolean;
  /** The command's own option, absent for a root option. */
  option?: ContractOption;
}

export interface ContractLookup {
  byKey: ReadonlyMap<string, ContractCommand>;
  /** Every proper prefix of a command path and every full path, space-joined. */
  prefixes: ReadonlySet<string>;
  /** Position of each command in the contract, for stable ranking. */
  order: ReadonlyMap<string, number>;
}

const cache = new WeakMap<CliContract, ContractLookup>();

export function lookupFor(contract: CliContract): ContractLookup {
  const hit = cache.get(contract);
  if (hit) return hit;
  const byKey = new Map<string, ContractCommand>();
  const prefixes = new Set<string>();
  const order = new Map<string, number>();
  contract.commands.forEach((cmd, i) => {
    byKey.set(cmd.pathKey, cmd);
    order.set(cmd.pathKey, i);
    for (let n = 1; n <= cmd.path.length; n++) prefixes.add(cmd.path.slice(0, n).join(' '));
  });
  const made = { byKey, prefixes, order };
  cache.set(contract, made);
  return made;
}

const POSITIONAL_KIND_TO_RESOURCE: Partial<Record<PositionalKind, ResourceKind>> = {
  'repo-ref': 'repo',
  'datastore-ref': 'datastore',
  'artifact-ref': 'artifact',
  'job-id': 'job',
  strategy: 'strategy',
  provider: 'provider',
  machine: 'machine',
  cluster: 'cluster',
};

/** The resource kinds a positional names; empty for plain, file and target tokens. */
export function positionalKinds(positional: ContractPositional): ResourceKind[] {
  const kind = POSITIONAL_KIND_TO_RESOURCE[positional.kind];
  return kind ? [kind] : [];
}

/**
 * The resource kinds an option names: its own `kinds`, else `machine` or `repo`
 * for the flag the command resolves as its machine or repository binding.
 */
export function optionKinds(command: ContractCommand, option: ContractOption): ResourceKind[] {
  if (option.kinds && option.kinds.length > 0) return [...option.kinds];
  if (!option.valueTaking) return [];
  if (option.long === command.machineOption) return ['machine'];
  if (option.long === command.repoOption) return ['repo'];
  return [];
}

/** Find a flag by `--long` or `-s` text (with the dashes), command options first. */
export function findFlag(command: ContractCommand | null, flag: string): FlagSpec | undefined {
  const isLong = flag.startsWith('--');
  const name = isLong ? flag.slice(2) : flag.slice(1);
  if (command) {
    const own = command.options.find((o) => (isLong ? o.long === name : o.short === name));
    if (own) {
      return {
        long: own.long,
        short: own.short,
        valueTaking: own.valueTaking,
        variadic: own.variadic,
        option: own,
      };
    }
  }
  const root = GLOBAL_OPTIONS.find((o) => (isLong ? o.long === name : o.short === name));
  if (root) return { ...root, variadic: false };
  return undefined;
}

/** POSIX-quote a token only when it needs it. Matches the console's buildCliCommand. */
export function shellQuote(token: string): string {
  if (/^[A-Za-z0-9._/:@%+=-]+$/.test(token)) return token;
  return `'${token.replaceAll("'", `'\\''`)}'`;
}

/** Quote a value token: like shellQuote, and a leading '-' is quoted too so parse() never reads it as a flag. */
export function shellQuoteValue(token: string): string {
  return token.startsWith('-') ? `'${token.replaceAll("'", `'\\''`)}'` : shellQuote(token);
}

/** One next word under a path prefix: a domain at the root, a subcommand below it. */
export interface PathChild {
  word: string;
  /** The command with exactly this path, when this word completes one. */
  command?: ContractCommand;
  /** Commands under or at this word, for a group's summary. */
  count: number;
}

/** The distinct next words of every command path that starts with `prefix`, in contract order. */
export function childrenOf(contract: CliContract, prefix: readonly string[]): PathChild[] {
  const found = new Map<string, PathChild>();
  for (const cmd of contract.commands) {
    if (cmd.path.length <= prefix.length) continue;
    if (!prefix.every((word, i) => cmd.path[i] === word)) continue;
    const word = cmd.path[prefix.length];
    const child = found.get(word) ?? { word, count: 0 };
    child.count++;
    if (cmd.path.length === prefix.length + 1) child.command = cmd;
    found.set(word, child);
  }
  return [...found.values()];
}

/** One cell of the Damerau-Levenshtein table (optimal string alignment). */
function editCell(d: number[][], a: string, b: string, i: number, j: number): number {
  const cost = a[i - 1] === b[j - 1] ? 0 : 1;
  const base = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
  const swapped = i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1];
  return swapped ? Math.min(base, d[i - 2][j - 2] + 1) : base;
}

/** Damerau-Levenshtein distance (optimal string alignment): insert, delete, substitute, swap. */
export function editDistance(a: string, b: string): number {
  const d: number[][] = Array.from({ length: a.length + 1 }, (_, i) => {
    const row = new Array<number>(b.length + 1).fill(0);
    row[0] = i;
    return row;
  });
  for (let j = 0; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) d[i][j] = editCell(d, a, b, i, j);
  }
  return d[a.length][b.length];
}
/**
 * The candidate nearest to `word`, ties by candidate order; undefined when none is close.
 * Close means at most 2 edits, and at most 1 for a word under 6 characters so a short
 * typo never matches an unrelated short name.
 */
export function nearest(word: string, candidates: readonly string[]): string | undefined {
  const maxDistance = word.length < 6 ? 1 : 2;
  let best: string | undefined;
  let bestDistance = maxDistance + 1;
  for (const candidate of candidates) {
    const distance = editDistance(word, candidate);
    if (distance < bestDistance) {
      best = candidate;
      bestDistance = distance;
    }
  }
  return best;
}
