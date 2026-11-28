/**
 * Recipe parser (D1 and D7 of PLAN-console-command-line).
 *
 * A recipe body is text:
 *
 *     # description line (any number)
 *     $name = required "Prompt shown when the recipe runs"
 *     $tag = "default value"
 *     rdc repo fork $repo --tag $tag
 *     rdc repo up $repo:$tag
 *
 * Declarations come before the first step; a declaration after a step is a
 * problem. Each other line is one `rdc` step with `$name` substitutions, and a
 * single-quoted word is never substituted. Every step must be proxy-capable, since
 * the console runs steps through the executor. Problems carry `[start, end)`
 * offsets into the body and never stop the parse, so an editor can show all of
 * them under the text area.
 */
import type { CliContract, ContractCommand } from '../cli-contract/types.js';
import { shellQuote } from './contract-index.js';
import { type DiagnosticCode, diagnose } from './diagnose.js';
import { analyze } from './state.js';
import { isFlagLike, type Token, tokenize } from './tokenize.js';

export interface RecipeVariable {
  name: string;
  /** Declared `required "prompt"`: the runner must ask, there is no default. */
  required: boolean;
  /** The prompt of a required variable. */
  prompt: string | null;
  /** The default of an optional variable. */
  default: string | null;
  start: number;
  end: number;
}

export interface RecipeStep {
  /** Zero-based line of the body. */
  line: number;
  start: number;
  end: number;
  /** The step line, trimmed. */
  text: string;
  /** The line's tokens with spans relative to the whole body. */
  tokens: Token[];
  /** The command the step resolves to, or null when it resolves to none. */
  command: ContractCommand | null;
  /** The command's severity is `destructive`: the runner asks step-up for it. */
  destructive: boolean;
  /** Variable names the step uses, in order of first use. */
  variables: string[];
}

export type RecipeProblemCode =
  | DiagnosticCode
  | 'bad-declaration'
  | 'duplicate-variable'
  | 'late-declaration'
  | 'undeclared-variable'
  | 'not-proxy-capable'
  | 'no-steps';

export interface RecipeProblem {
  code: RecipeProblemCode;
  message: string;
  start: number;
  end: number;
  /** Zero-based line of the body. */
  line: number;
}

export interface ParsedRecipe {
  /** The `#` lines, one per line, without the marker. */
  description: string;
  variables: RecipeVariable[];
  steps: RecipeStep[];
  problems: RecipeProblem[];
}

const VARIABLE = /\$([A-Za-z_][A-Za-z0-9_]*)/g;
const DECLARATION = /^\$([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/;

interface Line {
  index: number;
  /** Offset of the line's first character in the body. */
  offset: number;
  /** The line trimmed. */
  body: string;
  /** Offset of the first non-blank character. */
  start: number;
  end: number;
}

interface Context {
  recipe: ParsedRecipe;
  declared: Map<string, RecipeVariable>;
  contract: CliContract;
}

function report(
  ctx: Context,
  line: Line,
  code: RecipeProblemCode,
  message: string,
  start = line.start,
  end = line.end
): void {
  ctx.recipe.problems.push({ code, message, start, end, line: line.index });
}

/** The variable a `$name = ...` right-hand side declares, or the reason it is not one. */
function readDeclaration(
  name: string,
  rest: string,
  line: Line
): { variable: RecipeVariable } | { error: string } {
  const values = tokenize(rest);
  const [first, second] = values;
  const span = { start: line.start, end: line.end };
  if (values.some((t) => !t.closed)) return { error: `$${name} has an unclosed quote` };
  if (first && values.length === 2 && first.raw === 'required' && second.quote) {
    return {
      variable: { name, required: true, prompt: second.text, default: null, ...span },
    };
  }
  if (first && values.length === 1 && first.quote) {
    return { variable: { name, required: false, prompt: null, default: first.text, ...span } };
  }
  return {
    error: `$${name} needs required "prompt" or a quoted default, as in $${name} = "value"`,
  };
}

function handleDeclaration(ctx: Context, line: Line): void {
  const match = DECLARATION.exec(line.body);
  if (!match) {
    report(
      ctx,
      line,
      'bad-declaration',
      'A declaration reads $name = required "prompt" or $name = "default"'
    );
    return;
  }
  const name = match[1];
  const read = readDeclaration(name, match[2], line);
  if ('error' in read) {
    report(ctx, line, 'bad-declaration', read.error);
    return;
  }
  if (ctx.declared.has(name)) {
    report(ctx, line, 'duplicate-variable', `$${name} is declared twice`);
  } else {
    ctx.declared.set(name, read.variable);
    ctx.recipe.variables.push(read.variable);
  }
  if (ctx.recipe.steps.length > 0) {
    report(
      ctx,
      line,
      'late-declaration',
      `$${name} is declared after a step; declare variables first`
    );
  }
}

/** Names of the variables a step uses, reporting each undeclared one on its token. */
function stepVariables(ctx: Context, line: Line, tokens: readonly Token[]): string[] {
  const used: string[] = [];
  for (const token of tokens.filter((t) => t.quote !== "'")) {
    for (const m of token.text.matchAll(VARIABLE)) {
      if (!used.includes(m[1])) used.push(m[1]);
      if (!ctx.declared.has(m[1])) {
        report(
          ctx,
          line,
          'undeclared-variable',
          `$${m[1]} is not declared`,
          token.start,
          token.end
        );
      }
    }
  }
  return used;
}

function handleStep(ctx: Context, line: Line, raw: string): void {
  // Tokens are tokenized from the raw line, so spans shift by one offset.
  const tokens = tokenize(raw).map((t) => ({
    ...t,
    start: t.start + line.offset,
    end: t.end + line.offset,
  }));
  const analysis = analyze({ contract: ctx.contract, source: () => [] }, raw);
  const used = stepVariables(ctx, line, tokens);
  const touchesVariable = (s: number, e: number): boolean =>
    tokens.some(
      (t) =>
        t.text.includes('$') &&
        t.quote !== "'" &&
        t.start - line.offset < e &&
        t.end - line.offset > s
    );
  for (const d of diagnose(analysis)) {
    if (d.code === 'invalid-choice' && touchesVariable(d.start, d.end)) continue;
    report(ctx, line, d.code, d.message, d.start + line.offset, d.end + line.offset);
  }
  const command = analysis.parsed.command;
  if (command && !command.proxyCapable) {
    const path = analysis.parsed.pathTokens;
    const reason = command.proxyBlockedReason ? `: ${command.proxyBlockedReason}` : '';
    report(
      ctx,
      line,
      'not-proxy-capable',
      `rdc ${command.pathKey} cannot run in the console${reason}`,
      path[0].start + line.offset,
      path[path.length - 1].end + line.offset
    );
  }
  ctx.recipe.steps.push({
    line: line.index,
    start: line.start,
    end: line.end,
    text: line.body,
    tokens,
    command,
    destructive: command?.severity === 'destructive',
    variables: used,
  });
}

/** Parse a recipe body against the contract. Never throws. */
export function parseRecipe(text: string, contract: CliContract): ParsedRecipe {
  const recipe: ParsedRecipe = { description: '', variables: [], steps: [], problems: [] };
  const ctx: Context = { recipe, declared: new Map(), contract };
  const description: string[] = [];

  let offset = 0;
  for (const [index, raw] of text.split('\n').entries()) {
    const lineOffset = offset;
    offset += raw.length + 1;
    const body = raw.trim();
    if (body === '') continue;
    const start = lineOffset + raw.length - raw.trimStart().length;
    const line: Line = { index, offset: lineOffset, body, start, end: start + body.length };
    if (body.startsWith('#')) description.push(body.slice(1).replace(/^ /, ''));
    else if (body.startsWith('$')) handleDeclaration(ctx, line);
    else handleStep(ctx, line, raw);
  }

  recipe.description = description.join('\n');
  if (recipe.steps.length === 0) {
    recipe.problems.push({
      code: 'no-steps',
      message: 'The recipe has no step',
      start: 0,
      end: 0,
      line: 0,
    });
  }
  recipe.problems.sort((x, y) => x.start - y.start);
  return recipe;
}

/**
 * The value of every declared variable: the answer when one is given and not
 * blank, else the default. A required variable without an answer is listed in
 * `missing`, in declaration order.
 */
export function fillVariables(
  recipe: Pick<ParsedRecipe, 'variables'>,
  answers: Readonly<Record<string, string>>
): { values: Record<string, string>; missing: string[] } {
  const values: Record<string, string> = {};
  const missing: string[] = [];
  for (const variable of recipe.variables) {
    const answer = answers[variable.name];
    if (answer !== undefined && answer.trim() !== '') {
      values[variable.name] = answer;
    } else if (variable.required) {
      missing.push(variable.name);
    } else {
      values[variable.name] = variable.default ?? '';
    }
  }
  return { values, missing };
}

/**
 * The command line of one step with its variables substituted. A word is quoted
 * only when it needs it; a substituted value that starts with `-` is quoted so it
 * can never read back as a flag, and a `--flag=value` word quotes just its value.
 */
export function renderStep(
  step: Pick<RecipeStep, 'tokens'>,
  values: Readonly<Record<string, string>>
): string {
  return step.tokens
    .map((token) => {
      const text =
        token.quote === "'"
          ? token.text
          : token.text.replace(VARIABLE, (whole, name: string) => values[name] ?? whole);
      const substituted = text !== token.text;
      if (isFlagLike(token)) {
        const eq = text.indexOf('=');
        if (eq !== -1) return `${text.slice(0, eq + 1)}${shellQuote(text.slice(eq + 1))}`;
        return shellQuote(text);
      }
      if (substituted && text.startsWith('-')) return `'${text.replaceAll("'", `'\\''`)}'`;
      return shellQuote(text);
    })
    .join(' ');
}
