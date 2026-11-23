/**
 * Parse a tokenized `rdc` line against a CliContract: the longest command path,
 * then flags and positionals bound the way the console's form reads them
 * (`formValuesFromExec`): a positional by its name, a flag by its long name, a
 * switch as 'true', a variadic as its values joined by a space.
 */
import type { CliContract, ContractCommand, ContractPositional } from '../cli-contract/types.js';
import { type FlagSpec, findFlag, lookupFor } from './contract-index.js';
import { isFlagLike, type Token } from './tokenize.js';

export interface ParsedFlag {
  /** The flag token as typed, `--long`, `--long=value` or `-s`. */
  token: Token;
  /** The flag as typed without the value part, e.g. `--dry-run`. */
  name: string;
  /** Null for a flag the command and the root do not declare. */
  spec: FlagSpec | null;
  /** The value token, or null for a switch or a value-taking flag still waiting for one. */
  value: Token | null;
  /** The value came after `=` inside the flag token itself. */
  inline: boolean;
  /** Offset where the value text starts: after `=`, else the value token's start, else null. */
  valueStart: number | null;
  /** The value text, or null when none was given. */
  valueText: string | null;
}

export interface ParsedPositional {
  /** The slot it binds to; null for a token past the last slot. */
  slot: ContractPositional | null;
  token: Token;
}

export interface ParsedLine {
  tokens: readonly Token[];
  /** The first token reads `rdc`. */
  hasRdc: boolean;
  /** The resolved command, or null when no command path matched. */
  command: ContractCommand | null;
  /** The tokens (after `rdc`) that form the path, resolved or still a prefix of one. */
  pathTokens: Token[];
  /** The first path token that extends no command path, set only while no command is resolved. */
  unknownPath: Token | null;
  flags: ParsedFlag[];
  positionals: ParsedPositional[];
  /** Tokens after a bare `--`, which belong to the trailing variadic positional. */
  rest: Token[];
  /** The bare `--` token, when present. */
  separator: Token | null;
  /** The last flag when the line ends right after a value-taking flag with no value. */
  pending: ParsedFlag | null;
  /** Form values keyed by positional name and flag long name; absent for a root option. */
  values: Record<string, string>;
}

function appendValue(values: Record<string, string>, key: string, value: string): void {
  const had = values[key];
  values[key] = had === undefined ? value : `${had} ${value}`;
}

interface PathResolution {
  command: ContractCommand | null;
  /** Tokens of the longest full command path. */
  pathLen: number;
  /** Tokens that are still a prefix of some path. */
  consumed: number;
  unknown: Token | null;
}

/** Longest command path: extend while the joined words are still a prefix of some path. */
function resolvePath(contract: CliContract, body: readonly Token[]): PathResolution {
  const lookup = lookupFor(contract);
  const result: PathResolution = { command: null, pathLen: 0, consumed: 0, unknown: null };
  const words: string[] = [];
  for (const token of body) {
    if (isFlagLike(token)) break;
    words.push(token.text);
    const candidate = words.join(' ');
    if (!lookup.prefixes.has(candidate)) {
      result.unknown = token;
      break;
    }
    result.consumed = words.length;
    const hit = lookup.byKey.get(candidate);
    if (hit) {
      result.command = hit;
      result.pathLen = words.length;
    }
  }
  if (result.command) result.unknown = null;
  return result;
}

/** One flag token, with its value token when the flag takes one and `next` is it. */
function readFlag(command: ContractCommand, token: Token, next: Token | undefined): ParsedFlag {
  const eq = token.text.indexOf('=');
  const split = token.text.startsWith('--') && eq !== -1;
  const name = split ? token.text.slice(0, eq) : token.text;
  const inlineText = split ? token.text.slice(eq + 1) : null;
  const spec = findFlag(command, name) ?? null;
  const flag: ParsedFlag = {
    token,
    name,
    spec,
    value: null,
    inline: inlineText !== null,
    valueStart: inlineText === null ? null : token.start + token.raw.indexOf('=') + 1,
    valueText: inlineText,
  };
  if (spec?.valueTaking && inlineText === null && next) {
    flag.value = next;
    flag.valueStart = next.start;
    flag.valueText = next.text;
  }
  return flag;
}

function recordFlag(parsed: ParsedLine, flag: ParsedFlag): void {
  const spec = flag.spec;
  if (!spec?.option) return;
  if (!spec.valueTaking) parsed.values[spec.long] ??= 'true';
  else if (flag.valueText !== null) appendValue(parsed.values, spec.long, flag.valueText);
}

function bindSeparator(
  parsed: ParsedLine,
  command: ContractCommand,
  rest: readonly Token[],
  at: number
): void {
  parsed.separator = rest[at];
  parsed.rest = rest.slice(at + 1);
  const trailing = command.positionals.at(-1);
  if (trailing?.variadic && parsed.rest.length > 0) {
    appendValue(parsed.values, trailing.name, parsed.rest.map((t) => t.text).join(' '));
  }
}

/** Handle the flag at `rest[i]`; returns the index of the last token it used. */
function consumeFlag(
  parsed: ParsedLine,
  command: ContractCommand,
  rest: readonly Token[],
  i: number
): number {
  const flag = readFlag(command, rest[i], rest.at(i + 1));
  if (flag.spec?.valueTaking && !flag.inline && !flag.value) parsed.pending = flag;
  parsed.flags.push(flag);
  recordFlag(parsed, flag);
  return flag.value ? i + 1 : i;
}

/** Bind a bare token to the next positional slot; returns the next slot index. */
function consumePositional(
  parsed: ParsedLine,
  command: ContractCommand,
  token: Token,
  slotIndex: number
): number {
  const last = command.positionals.at(-1);
  const bound = command.positionals.at(slotIndex) ?? (last?.variadic ? last : null);
  parsed.positionals.push({ slot: bound, token });
  if (bound) appendValue(parsed.values, bound.name, token.text);
  return bound?.variadic ? slotIndex : slotIndex + 1;
}

/** Bind the tokens after the command path to flags, positionals and the words after `--`. */
function bindArguments(parsed: ParsedLine, command: ContractCommand, rest: readonly Token[]): void {
  let slotIndex = 0;
  for (let i = 0; i < rest.length; i++) {
    const token = rest[i];
    if (token.raw === '--') {
      bindSeparator(parsed, command, rest, i);
      return;
    }
    if (isFlagLike(token)) i = consumeFlag(parsed, command, rest, i);
    else slotIndex = consumePositional(parsed, command, token, slotIndex);
  }
}

/** Resolve the tokens of one line against the contract. Never throws. */
export function parse(contract: CliContract, tokens: readonly Token[]): ParsedLine {
  const parsed: ParsedLine = {
    tokens,
    hasRdc: tokens[0]?.text === 'rdc',
    command: null,
    pathTokens: [],
    unknownPath: null,
    flags: [],
    positionals: [],
    rest: [],
    separator: null,
    pending: null,
    values: {},
  };
  if (!parsed.hasRdc) return parsed;

  const body = tokens.slice(1);
  const path = resolvePath(contract, body);
  parsed.command = path.command;
  parsed.unknownPath = path.unknown;
  if (!path.command) {
    parsed.pathTokens = body.slice(0, path.consumed);
    return parsed;
  }
  parsed.pathTokens = body.slice(0, path.pathLen);
  bindArguments(parsed, path.command, body.slice(path.pathLen));
  return parsed;
}
