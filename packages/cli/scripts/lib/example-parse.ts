/**
 * Curated-example parsing for the CLI contract generator.
 *
 * Split out of generate-cli-contract.ts: the tokenizer and the parse-and-gate
 * pass are a self-contained unit that only needs the live path keys and a
 * problem sink, and keeping them here leaves the generator itself readable.
 */
import type { ContractOption, ContractPositional } from '../../../shared/src/cli-contract/types.js';

/** What the parser needs from the generator: the live tree, and where to report. */
export interface ExampleParseContext {
  /** Every pathKey in the live Commander tree, for longest-prefix matching. */
  readonly livePathKeys: ReadonlySet<string>;
  /** Collected curation problems; a non-empty list fails generation. */
  readonly problems: string[];
}

/** Global options are tolerated in an example but never become form fields. */
const GLOBAL_SHORT_TO_LONG = new Map<string, string>([
  ['-o', '--output'],
  ['-l', '--lang'],
]);

/** Split an example command line into shell-ish tokens (quote-aware). */
export function tokenizeExampleCommand(command: string): string[] | null {
  const tokens: string[] = [];
  let current = '';
  let hasCurrent = false;
  let quote: '"' | "'" | null = null;

  for (const ch of command) {
    if (quote) {
      if (ch === quote) quote = null;
      else current += ch;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      hasCurrent = true;
      continue;
    }
    if (ch === ' ' || ch === '\t') {
      if (hasCurrent || current.length > 0) {
        tokens.push(current);
        current = '';
        hasCurrent = false;
      }
      continue;
    }
    current += ch;
  }
  if (quote) return null;
  if (hasCurrent || current.length > 0) tokens.push(current);
  return tokens;
}

/**
 * Parse one curated example against the command's OWN declared surface and
 * derive its click-to-fill `values` map: positionals by declared order (a
 * trailing variadic collects), flags by long name, booleans as 'true'.
 *
 * The parse doubles as the example-validity gate: a stale pathKey (checked by
 * longest-prefix match against the live tree), an unknown flag, bad arity, an
 * out-of-choices value, a missing required positional, or a missing mandatory
 * option all fail generation. Global options (-o/--output, --lang, --context)
 * are tolerated but never enter `values` — they are not form fields.
 */
export function parseExampleValues(
  pathKey: string,
  exampleCommand: string,
  options: ContractOption[],
  positionals: ContractPositional[],
  globalOptionLongs: ReadonlySet<string>,
  ctx: ExampleParseContext
): Record<string, string> {
  const fail = (message: string): Record<string, string> => {
    ctx.problems.push(
      `COMMAND_EXAMPLES["${pathKey}"]: ${JSON.stringify(exampleCommand)} — ${message}`
    );
    return {};
  };

  const tokens = tokenizeExampleCommand(exampleCommand);
  if (!tokens) return fail('unterminated quote');
  if (tokens[0] !== 'rdc') return fail('must start with "rdc"');

  // Longest-prefix pathKey match: the tokens after `rdc` must resolve to THIS
  // command, so an example filed under the wrong key cannot slip through.
  let matched = '';
  for (let i = 1; i < tokens.length; i++) {
    const candidate = tokens.slice(1, i + 1).join(' ');
    if (ctx.livePathKeys.has(candidate)) matched = candidate;
  }
  if (!matched) return fail('names no live command');
  if (matched !== pathKey) return fail(`parses as "${matched}" but is filed under "${pathKey}"`);

  const byLong = new Map(options.map((o) => [o.long, o]));
  const byShort = new Map(options.filter((o) => o.short).map((o) => [o.short as string, o]));

  const values = new Map<string, string>();
  let posIndex = 0;
  const rest = tokens.slice(1 + matched.split(' ').length);

  for (let i = 0; i < rest.length; i++) {
    const token = rest[i];

    // End-of-options: everything after `--` belongs to the trailing variadic
    // positional verbatim, so no later token may be read as a flag. NOTE the
    // `values` map does NOT retain the `--` itself; a consumer rebuilding a
    // command line from `values` must re-insert it before that positional.
    if (token === '--') {
      const trailing = positionals.at(-1);
      if (!trailing?.variadic) {
        return fail('`--` needs a trailing variadic positional to collect into');
      }
      const remainder = rest.slice(i + 1);
      if (remainder.length === 0) return fail('`--` is missing the command that follows it');
      const joined = remainder.join(' ');
      const collected = values.get(trailing.name);
      values.set(trailing.name, collected === undefined ? joined : `${collected} ${joined}`);
      break;
    }

    if (token.startsWith('-') && token.length > 1) {
      let flag = token;
      let inlineValue: string | undefined;
      const eq = token.indexOf('=');
      if (eq !== -1) {
        flag = token.slice(0, eq);
        inlineValue = token.slice(eq + 1);
      }

      const globalLong = globalOptionLongs.has(flag) ? flag : GLOBAL_SHORT_TO_LONG.get(flag);
      if (globalLong !== undefined) {
        if (globalLong === '--version' || globalLong === '--help') {
          return fail(`${globalLong} has no place in a worked example`);
        }
        // --output/--lang/--context take a value; consume it, keep it out of
        // `values` — global options are not form fields.
        if (inlineValue === undefined) i++;
        continue;
      }

      const opt = flag.startsWith('--') ? byLong.get(flag.slice(2)) : byShort.get(flag.slice(1));
      if (!opt) return fail(`unknown flag ${flag}`);

      if (!opt.valueTaking) {
        if (inlineValue !== undefined) return fail(`boolean --${opt.long} takes no value`);
        if (values.has(opt.long)) return fail(`--${opt.long} given twice`);
        values.set(opt.long, 'true');
        continue;
      }

      const value = inlineValue ?? rest.at(++i);
      if (value === undefined) return fail(`--${opt.long} is missing its value`);
      if (opt.choices && !opt.choices.includes(value)) {
        return fail(
          `--${opt.long} value "${value}" is not one of its choices (${opt.choices.join(', ')})`
        );
      }
      const given = values.get(opt.long);
      if (given !== undefined) {
        if (!opt.variadic) return fail(`--${opt.long} given twice`);
        values.set(opt.long, `${given} ${value}`);
      } else {
        values.set(opt.long, value);
      }
      continue;
    }

    const positional = positionals.at(posIndex);
    if (!positional) {
      return fail(
        `too many positional tokens (expected ${positionals.length}, "${token}" is extra)`
      );
    }
    const collected = values.get(positional.name);
    values.set(positional.name, collected === undefined ? token : `${collected} ${token}`);
    if (!positional.variadic) posIndex++;
  }

  for (const p of positionals) {
    if (p.required && !values.has(p.name)) {
      return fail(`missing required positional <${p.name}>`);
    }
  }
  for (const o of options) {
    if (o.mandatory && !values.has(o.long)) {
      return fail(`missing mandatory option --${o.long}`);
    }
  }

  return Object.fromEntries(values);
}
