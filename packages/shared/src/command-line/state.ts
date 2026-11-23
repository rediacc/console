/**
 * The input of completion and diagnostics: a contract, a source of resource
 * names, and one analysed line.
 */
import type { CliContract, ResourceKind } from '../cli-contract/types.js';
import { type ParsedLine, parse } from './parse.js';
import { type Token, tokenize } from './tokenize.js';

/** Resource names already chosen on the line, so a source can narrow (a machine narrows the repos). */
type ResourceContext = Partial<Record<ResourceKind, string>>;

export type { ResourceContext };

/**
 * Names of one resource kind. `'locked'` means the config is not unlocked, so no
 * name can be offered; the console shows one row that opens the unlock form.
 */
export type ResourceSource = (kind: ResourceKind, ctx: ResourceContext) => string[] | 'locked';

export interface CommandLineEnv {
  contract: CliContract;
  source: ResourceSource;
}

export interface LineState {
  env: CommandLineEnv;
  line: string;
  tokens: Token[];
  parsed: ParsedLine;
}

/** Tokenize and parse one line into the state `complete` and `diagnose` read. */
export function analyze(env: CommandLineEnv, line: string): LineState {
  const tokens = tokenize(line);
  return { env, line, tokens, parsed: parse(env.contract, tokens) };
}
