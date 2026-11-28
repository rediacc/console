/**
 * Span-anchored problems of one command line (D3 of PLAN-console-command-line):
 * an unknown command or flag with the nearest match, a missing required
 * positional or flag, a value outside `choices`, a flag given twice. Each carries
 * a `[start, end)` span, a message key for the UI's translation and the English
 * message. Nothing here decides how a problem is shown.
 */

import type { ContractCommand } from '../cli-contract/types.js';
import { childrenOf, nearest } from './contract-index.js';
import type { ParsedFlag, ParsedLine } from './parse.js';
import type { LineState } from './state.js';
import { unclosedQuote } from './tokenize.js';

export type DiagnosticCode =
  | 'not-rdc'
  | 'unclosed-quote'
  | 'unknown-command'
  | 'unknown-flag'
  | 'duplicate-flag'
  | 'missing-value'
  | 'unexpected-value'
  | 'invalid-choice'
  | 'missing-positional'
  | 'missing-flag'
  | 'too-many-positionals';

export interface Diagnostic {
  code: DiagnosticCode;
  /** Translation key, `commandLine.diagnostic.<code>`. */
  messageKey: string;
  /** Values the translation interpolates. */
  params: Record<string, string>;
  /** English message. */
  message: string;
  /** Offset where the problem starts. A missing value or argument is zero-width at the end of the line. */
  start: number;
  end: number;
  /** The nearest valid word for an unknown command or flag, or the nearest choice for an invalid value. */
  suggestion?: string;
}

function make(
  code: DiagnosticCode,
  message: string,
  params: Record<string, string>,
  start: number,
  end: number,
  suggestion?: string
): Diagnostic {
  return {
    code,
    messageKey: `commandLine.diagnostic.${code}`,
    params,
    message,
    start,
    end,
    ...(suggestion === undefined ? {} : { suggestion }),
  };
}

function unclosedQuoteProblem(state: LineState): Diagnostic[] {
  const open = unclosedQuote(state.tokens);
  if (!open) return [];
  return [
    make(
      'unclosed-quote',
      `The quote opened at position ${open.start} is never closed`,
      { position: String(open.start) },
      open.start,
      open.end
    ),
  ];
}

/** The line names no command: report the first path word that extends no command. */
function pathProblems(state: LineState): Diagnostic[] {
  const unknown = state.parsed.unknownPath;
  if (!unknown) return [];
  const words = state.parsed.pathTokens.map((t) => t.text);
  const near = nearest(
    unknown.text,
    childrenOf(state.env.contract, words).map((c) => c.word)
  );
  const where = words.length === 0 ? 'rdc' : `rdc ${words.join(' ')}`;
  return [
    make(
      'unknown-command',
      near
        ? `${where} has no "${unknown.text}"; did you mean "${near}"?`
        : `${where} has no "${unknown.text}"`,
      { word: unknown.text, parent: where, ...(near ? { suggestion: near } : {}) },
      unknown.start,
      unknown.end,
      near
    ),
  ];
}

function unknownFlagProblem(command: ContractCommand, flag: ParsedFlag): Diagnostic {
  const bare = flag.name.replace(/^-+/, '');
  const near = flag.name.startsWith('--')
    ? nearest(
        bare,
        command.options.map((o) => o.long)
      )
    : undefined;
  return make(
    'unknown-flag',
    near
      ? `${flag.name} is not a flag of rdc ${command.pathKey}; did you mean "--${near}"?`
      : `${flag.name} is not a flag of rdc ${command.pathKey}`,
    { flag: flag.name, command: command.pathKey, ...(near ? { suggestion: `--${near}` } : {}) },
    flag.token.start,
    flag.token.end,
    near ? `--${near}` : undefined
  );
}

/** Problems of the value (or its absence) of a known flag. */
function valueProblems(flag: ParsedFlag, lineEnd: number): Diagnostic[] {
  const spec = flag.spec;
  if (!spec) return [];
  const name = `--${spec.long}`;
  if (!spec.valueTaking) {
    return flag.inline
      ? [
          make(
            'unexpected-value',
            `${name} takes no value`,
            { flag: name },
            flag.token.start,
            flag.token.end
          ),
        ]
      : [];
  }
  if (flag.valueText === null) {
    return [make('missing-value', `${name} needs a value`, { flag: name }, lineEnd, lineEnd)];
  }
  const choices = spec.option?.choices;
  if (!choices || choices.includes(flag.valueText)) return [];
  return [
    make(
      'invalid-choice',
      `${name} takes one of ${choices.join(', ')}, not "${flag.valueText}"`,
      { flag: name, value: flag.valueText, choices: choices.join(', ') },
      flag.valueStart ?? flag.token.start,
      flag.value?.end ?? flag.token.end,
      nearest(flag.valueText, choices)
    ),
  ];
}

function flagProblems(command: ContractCommand, parsed: ParsedLine, lineEnd: number): Diagnostic[] {
  const problems: Diagnostic[] = [];
  const seen = new Set<string>();
  for (const flag of parsed.flags) {
    const { spec } = flag;
    if (!spec) {
      problems.push(unknownFlagProblem(command, flag));
      continue;
    }
    if (seen.has(spec.long) && !spec.variadic) {
      problems.push(
        make(
          'duplicate-flag',
          `--${spec.long} is given twice`,
          { flag: `--${spec.long}` },
          flag.token.start,
          flag.token.end
        )
      );
    }
    seen.add(spec.long);
    problems.push(...valueProblems(flag, lineEnd));
  }
  return problems;
}

function extraPositionalProblems(command: ContractCommand, parsed: ParsedLine): Diagnostic[] {
  const count = command.positionals.length;
  return parsed.positionals.flatMap((extra) =>
    extra.slot
      ? []
      : [
          make(
            'too-many-positionals',
            `rdc ${command.pathKey} takes ${count} argument${count === 1 ? '' : 's'}; "${extra.token.text}" is extra`,
            { command: command.pathKey, word: extra.token.text },
            extra.token.start,
            extra.token.end
          ),
        ]
  );
}

function missingProblems(
  command: ContractCommand,
  parsed: ParsedLine,
  lineEnd: number
): Diagnostic[] {
  const named = new Set(parsed.flags.flatMap((f) => (f.spec ? [f.spec.long] : [])));
  const positionals = command.positionals
    .filter((slot) => slot.required && parsed.values[slot.name] === undefined)
    .map((slot) =>
      make(
        'missing-positional',
        `<${slot.name}> is required`,
        { name: slot.name },
        lineEnd,
        lineEnd
      )
    );
  const flags = command.options
    .filter((option) => option.mandatory && !named.has(option.long))
    .map((option) =>
      make(
        'missing-flag',
        `--${option.long} is required`,
        { flag: `--${option.long}` },
        lineEnd,
        lineEnd
      )
    );
  return [...positionals, ...flags];
}

/** Every problem of the line, in line order. An empty line has none. */
export function diagnose(state: LineState): Diagnostic[] {
  const { parsed, tokens, line } = state;
  if (tokens.length === 0) return [];
  const problems = unclosedQuoteProblem(state);

  if (!parsed.hasRdc) {
    const first = tokens[0];
    problems.push(
      make('not-rdc', 'A command starts with rdc', { word: first.text }, first.start, first.end)
    );
    return problems;
  }
  const command = parsed.command;
  if (!command) return [...problems, ...pathProblems(state)];

  problems.push(
    ...flagProblems(command, parsed, line.length),
    ...extraPositionalProblems(command, parsed),
    ...missingProblems(command, parsed, line.length)
  );
  return problems.sort((a, b) => a.start - b.start);
}
