/**
 * Ranked suggestions at a cursor (D2 of PLAN-console-command-line).
 *
 * Order of the sections: domains, then subcommands with their summaries, then
 * the next required positional, then flags with common before advanced, then
 * the next optional positional; a value slot lists `choices` first, then the resource
 * names of every unlocked kind, plus one inert "Unlock to suggest" row when any kind is locked.
 * Within the list a prefix match ranks before a subsequence match and ties keep
 * contract order.
 */
import type {
  CommandSeverity,
  ContractCommand,
  ContractOption,
  ContractPositional,
  ResourceKind,
} from '../cli-contract/types.js';
import {
  childrenOf,
  optionKinds,
  type PathChild,
  positionalKinds,
  shellQuoteValue,
} from './contract-index.js';
import { type ParsedLine, parse } from './parse.js';
import type { LineState, ResourceContext } from './state.js';
import { type Token, tokenize } from './tokenize.js';

export type SuggestionKind =
  | 'keyword'
  | 'domain'
  | 'command'
  | 'positional'
  | 'flag'
  | 'choice'
  | 'value'
  | 'unlock';

export interface Suggestion {
  kind: SuggestionKind;
  /** The text shown for the row. */
  label: string;
  /** Replaces `[start, end)` of the line when accepted. Empty for an inert row. */
  insert: string;
  start: number;
  end: number;
  /** One-line description: a command's summary, an option's label. */
  summary?: string;
  /** i18n key of `summary` when the contract has one. */
  summaryKey?: string | null;
  /** How costly a mistaken run of this command is. */
  severity?: CommandSeverity;
  /** Why this command cannot run in the console, when it cannot. */
  blockedReason?: string;
  /** A mandatory flag or a required positional. */
  required?: boolean;
  /** The row cannot be accepted: a placeholder, or the unlock prompt. */
  inert?: boolean;
  /** Translation key for an inert row's label (`commandLine.unlock`), when it has one. */
  labelKey?: string;
}

const UNLOCK_LABEL = 'Unlock to suggest';

function isSubsequence(text: string, pattern: string): boolean {
  let at = 0;
  for (const ch of text) {
    if (ch === pattern[at]) at++;
  }
  return at === pattern.length;
}

/** 0 when `candidate` starts with `prefix`, 1 when it contains it as a subsequence, -1 otherwise. Case-insensitive. */
export function matchRank(candidate: string, prefix: string): number {
  const c = candidate.toLowerCase();
  const p = prefix.toLowerCase();
  if (c.startsWith(p)) return 0;
  return isSubsequence(c, p) ? 1 : -1;
}

interface Slot {
  /** Section order, so equal ranks keep D2's order. */
  section: number;
  suggestion: Suggestion;
  /** Position inside the section. */
  index: number;
  /** The text matched against the prefix. */
  match: string;
  /** Extra matched text that ranks as a prefix match (a short flag). */
  alias?: string;
}

interface Target {
  start: number;
  end: number;
  prefix: string;
}

const SECTION = { path: 0, positional: 1, flag: 2, optionalPositional: 3, value: 0 } as const;

/** Kind and value pairs the line has already chosen, from flags then positionals. */
function chosenResources(
  command: ContractCommand,
  flags: ParsedLine['flags'],
  positionals: ParsedLine['positionals']
): [ResourceKind, string][] {
  const fromFlags = flags.flatMap((flag) => {
    const option = flag.spec?.option;
    if (!option || flag.valueText === null) return [];
    return optionKinds(command, option).map((kind): [ResourceKind, string] => [
      kind,
      flag.valueText as string,
    ]);
  });
  const fromPositionals = positionals.flatMap((p) =>
    p.slot
      ? positionalKinds(p.slot).map((kind): [ResourceKind, string] => [kind, p.token.text])
      : []
  );
  return [...fromFlags, ...fromPositionals];
}

function resourceContext(
  command: ContractCommand,
  flags: ParsedLine['flags'],
  positionals: ParsedLine['positionals']
): ResourceContext {
  const ctx: ResourceContext = {};
  for (const [kind, value] of chosenResources(command, flags, positionals)) ctx[kind] ??= value;
  return ctx;
}

function valueSlot(kind: 'choice' | 'value', value: string, index: number, target: Target): Slot {
  return {
    section: SECTION.value,
    index,
    match: value,
    suggestion: {
      kind,
      label: value,
      insert: `${shellQuoteValue(value)} `,
      start: target.start,
      end: target.end,
    },
  };
}

function unlockSlot(index: number, target: Target): Slot {
  return {
    section: SECTION.value + 1,
    index,
    match: '',
    suggestion: {
      kind: 'unlock',
      label: UNLOCK_LABEL,
      labelKey: 'commandLine.unlock',
      insert: '',
      start: target.start,
      end: target.end,
      inert: true,
    },
  };
}

/** Choices first, then resource names of each kind, then the unlock row when any source is locked. */
function valueRows(
  state: LineState,
  kinds: readonly ResourceKind[],
  ctx: ResourceContext,
  choices: readonly string[] | undefined,
  target: Target
): Slot[] {
  const rows: Slot[] = (choices ?? []).map((c, i) => valueSlot('choice', c, i, target));
  const seen = new Set<string>(choices);
  const answers = kinds.map((kind) => state.env.source(kind, ctx));
  for (const names of answers) {
    if (names === 'locked') continue;
    for (const name of names.filter((n) => !seen.has(n))) {
      seen.add(name);
      rows.push(valueSlot('value', name, rows.length, target));
    }
  }
  if (answers.includes('locked')) rows.push(unlockSlot(rows.length, target));
  return rows;
}

function pathKind(child: PathChild, root: boolean): SuggestionKind {
  return root && !child.command ? 'domain' : 'command';
}

function pathRows(state: LineState, words: readonly string[], target: Target): Slot[] {
  const root = words.length === 0;
  return childrenOf(state.env.contract, words).map((child, index) => {
    const cmd = child.command;
    const suggestion: Suggestion = {
      kind: pathKind(child, root),
      label: child.word,
      insert: `${child.word} `,
      start: target.start,
      end: target.end,
    };
    if (cmd) {
      suggestion.summary = cmd.summary;
      suggestion.summaryKey = cmd.summaryKey;
      suggestion.severity = cmd.severity;
      if (cmd.proxyBlockedReason) suggestion.blockedReason = cmd.proxyBlockedReason;
    }
    return { section: SECTION.path, index, match: child.word, suggestion };
  });
}

function positionalRows(
  state: LineState,
  slot: ContractPositional,
  ctx: ResourceContext,
  target: Target,
  section: number
): Slot[] {
  const kinds = positionalKinds(slot);
  if (kinds.length === 0) {
    if (target.prefix !== '' || !slot.required) return [];
    return [
      {
        section,
        index: 0,
        match: '',
        suggestion: {
          kind: 'positional',
          label: `<${slot.name}>`,
          insert: '',
          start: target.start,
          end: target.end,
          summary: slot.label,
          required: true,
          inert: true,
        },
      },
    ];
  }
  return valueRows(state, kinds, ctx, undefined, target).map((row) => ({
    ...row,
    section: row.section + section,
    suggestion: { ...row.suggestion, ...(slot.required ? { required: true } : {}) },
  }));
}

/** Common flags are the ones a form shows up front: mandatory, resource-bound, enumerated or tiered common. */
function isCommonOption(command: ContractCommand, option: ContractOption): boolean {
  return (
    option.mandatory ||
    (option.kinds?.length ?? 0) > 0 ||
    (option.choices?.length ?? 0) > 0 ||
    option.long === command.machineOption ||
    option.long === command.repoOption ||
    option.tier === 'common'
  );
}

function flagSlot(option: ContractOption, index: number, target: Target): Slot {
  return {
    section: SECTION.flag,
    index,
    match: `--${option.long}`,
    alias: option.short ? `-${option.short}` : undefined,
    suggestion: {
      kind: 'flag',
      label: `--${option.long}`,
      insert: `--${option.long} `,
      start: target.start,
      end: target.end,
      summary: option.label,
      summaryKey: option.descriptionKey,
      ...(option.mandatory ? { required: true } : {}),
    },
  };
}

function flagRows(command: ContractCommand, given: ReadonlySet<string>, target: Target): Slot[] {
  const open = command.options
    .map((option, index) => ({ option, index }))
    .filter(({ option }) => option.variadic || !given.has(option.long));
  const common = open.filter(({ option }) => isCommonOption(command, option));
  const advanced = open.filter(({ option }) => !isCommonOption(command, option));
  return [
    ...common.map(({ option, index }) => flagSlot(option, index, target)),
    ...advanced.map(({ option, index }, i) => flagSlot(option, index + 10_000 + i, target)),
  ];
}

function currentTarget(
  state: LineState,
  cursor: number
): { current: Token | undefined; target: Target } {
  const current = state.tokens.find((t) => t.start < cursor && cursor <= t.end);
  if (!current) return { current, target: { start: cursor, end: cursor, prefix: '' } };
  const prefix = tokenize(state.line.slice(current.start, cursor)).at(0)?.text ?? '';
  return { current, target: { start: current.start, end: current.end, prefix } };
}

function trailingVariadic(command: ContractCommand): ContractPositional | undefined {
  const last = command.positionals.at(-1);
  return last?.variadic ? last : undefined;
}

/** Subcommands, the next positional and the flags of a resolved command, in D2 order. */
function argumentSlots(
  state: LineState,
  ctx: ParsedLine,
  command: ContractCommand,
  resources: ResourceContext,
  target: Target
): Slot[] {
  const flagTyped = target.prefix.startsWith('-');
  const next = command.positionals.at(ctx.positionals.length) ?? trailingVariadic(command);
  const slots: Slot[] = [];
  if (!flagTyped && command.hasSubcommands) slots.push(...pathRows(state, command.path, target));
  if (!flagTyped && next?.required) {
    slots.push(...positionalRows(state, next, resources, target, SECTION.positional));
  }
  if (target.prefix === '' || flagTyped) {
    const given = new Set(ctx.flags.flatMap((f) => (f.spec ? [f.spec.long] : [])));
    slots.push(...flagRows(command, given, target));
  }
  if (!flagTyped && next && !next.required) {
    slots.push(...positionalRows(state, next, resources, target, SECTION.optionalPositional));
  }
  return slots;
}

/** `--flag=va|` : values of the flag named before the `=`, completing only what follows it. */
function inlineValueSuggestions(
  state: LineState,
  command: ContractCommand,
  resources: ResourceContext,
  target: Target,
  cursor: number
): Suggestion[] {
  const eq = target.prefix.indexOf('=');
  const spec = command.options.find((o) => `--${o.long}` === target.prefix.slice(0, eq));
  if (!spec?.valueTaking) return [];
  const valueTarget: Target = {
    start: target.start + state.line.slice(target.start, cursor).indexOf('=') + 1,
    end: target.end,
    prefix: target.prefix.slice(eq + 1),
  };
  const slots = valueRows(state, optionKinds(command, spec), resources, spec.choices, valueTarget);
  return rankSlots(slots, valueTarget.prefix);
}

function commandSuggestions(
  state: LineState,
  ctx: ParsedLine,
  command: ContractCommand,
  target: Target,
  cursor: number
): Suggestion[] {
  if (ctx.separator) return [];
  const resources = resourceContext(command, ctx.flags, ctx.positionals);
  const pending = ctx.pending;
  if (pending?.spec?.valueTaking) {
    const option = pending.spec.option;
    if (!option) return [];
    const slots = valueRows(state, optionKinds(command, option), resources, option.choices, target);
    return rankSlots(slots, target.prefix);
  }
  if (target.prefix.startsWith('--') && target.prefix.includes('=')) {
    return inlineValueSuggestions(state, command, resources, target, cursor);
  }
  return rankSlots(argumentSlots(state, ctx, command, resources, target), target.prefix);
}

/** Ranked suggestions for the token under `cursor` (an offset into `state.line`). */
export function complete(state: LineState, cursor: number): Suggestion[] {
  const { current, target } = currentTarget(state, cursor);
  const before = state.tokens.filter((t) => t !== current && t.end <= cursor);

  if (before.length === 0) {
    if (matchRank('rdc', target.prefix) < 0) return [];
    return [
      { kind: 'keyword', label: 'rdc', insert: 'rdc ', start: target.start, end: target.end },
    ];
  }

  const ctx = parse(state.env.contract, before);
  if (!ctx.hasRdc) return [];
  if (ctx.command) return commandSuggestions(state, ctx, ctx.command, target, cursor);

  const blocked =
    ctx.unknownPath !== null ||
    before.length - 1 !== ctx.pathTokens.length ||
    target.prefix.startsWith('-');
  if (blocked) return [];
  const words = ctx.pathTokens.map((t) => t.text);
  return rankSlots(pathRows(state, words, target), target.prefix);
}

/** Rank of one slot against the typed prefix; negative means it does not match. */
function rankOf(slot: Slot, prefix: string): number {
  if (slot.suggestion.inert) return 0;
  if (slot.suggestion.kind !== 'flag') return matchRank(slot.match, prefix);
  if (prefix === '-' || prefix === '--' || (slot.alias !== undefined && slot.alias === prefix)) {
    return 0;
  }
  return matchRank(slot.match.slice(2), prefix.replace(/^-+/, ''));
}

function rankSlots(slots: Slot[], prefix: string): Suggestion[] {
  const ranked = slots
    .map((slot) => ({ slot, rank: rankOf(slot, prefix) }))
    .filter((r) => r.rank >= 0);
  ranked.sort(
    (a, b) => a.rank - b.rank || a.slot.section - b.slot.section || a.slot.index - b.slot.index
  );
  return ranked.map((r) => r.slot.suggestion);
}
