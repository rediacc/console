/**
 * Argv redaction for the feedback ring buffer and report payload.
 *
 * Sensitive option values come from the generated CLI contract (the same
 * `resolveOptionSensitive` classification, emitted as `sensitive`), machine
 * names are replaced by `<machine>`, and the joined string then goes through
 * the shared free-text scrubber.
 */
import { scrubText } from '@rediacc/shared';
import type {
  ContractCommand,
  ContractOption,
  ContractPositional,
} from '@rediacc/shared/cli-contract';
import { getCommand } from '@rediacc/shared/cli-contract';
import { isSensitiveKey } from '@rediacc/shared/telemetry';

export const REDACTED = '<redacted>';
export const MACHINE = '<machine>';

function isOption(token: string): boolean {
  return token.startsWith('-') && token.length > 1;
}

/** Longest leading run of non-option tokens that names a contract command (empty when none). */
export function resolveCommandPath(argv: readonly string[]): string[] {
  const words = argv.filter((t) => !isOption(t));
  for (let n = Math.min(words.length, 4); n > 0; n--) {
    if (getCommand(words.slice(0, n).join(' '))) return words.slice(0, n);
  }
  return [];
}

function findOption(cmd: ContractCommand | undefined, name: string): ContractOption | undefined {
  if (!cmd) return undefined;
  const isLong = name.startsWith('--');
  return cmd.options.find((o) =>
    isLong ? o.long === name.slice(2) : o.flags.split(/[ ,|]+/).includes(name)
  );
}

function redactAtMachine(value: string): string {
  const at = value.lastIndexOf('@');
  return at > 0 ? `${value.slice(0, at + 1)}${MACHINE}` : value;
}

export interface RedactOptions {
  homeDir?: string;
}

function positionalToken(spec: ContractPositional | undefined, token: string): string {
  if (spec?.kind === 'machine') return MACHINE;
  if (spec?.kind === 'repo-ref' || spec?.kind === 'datastore-ref') return redactAtMachine(token);
  return token;
}

/** The replacement for an option's value, or undefined when the value is kept. */
function optionMask(opt: ContractOption | undefined, sensitive: boolean): string | undefined {
  if (sensitive) return REDACTED;
  return opt?.kinds?.includes('machine') ? MACHINE : undefined;
}

/** A known option answers from the contract; an unknown one fails closed on its name. */
function isSensitiveOption(opt: ContractOption | undefined, name: string): boolean {
  return opt ? opt.sensitive === true : isSensitiveKey(name.replace(/^-+/, ''));
}

/** Whether the token after an option is that option's value. */
function takesValue(opt: ContractOption | undefined, sensitive: boolean, next: string): boolean {
  return opt ? opt.valueTaking : sensitive && !isOption(next);
}

/**
 * Redact the option at `argv[i]`; returns the tokens to emit and how many argv
 * tokens were consumed (2 when a separate value token was masked or skipped).
 */
function redactOption(
  cmd: ContractCommand | undefined,
  argv: readonly string[],
  i: number
): { emit: string[]; consumed: number } {
  const token = argv[i];
  const inline = token.startsWith('--') && token.includes('=');
  const name = inline ? token.slice(0, token.indexOf('=')) : token;
  const opt = findOption(cmd, name);
  const sensitive = isSensitiveOption(opt, name);
  const mask = optionMask(opt, sensitive);
  if (inline) return { emit: [mask ? `${name}=${mask}` : token], consumed: 1 };
  const next = argv[i + 1];
  if (next !== undefined && takesValue(opt, sensitive, next)) {
    return { emit: [name, mask ?? next], consumed: 2 };
  }
  return { emit: [token], consumed: 1 };
}

/** Redacted, scrubbed one-line form of the argv (without the program name). */
export function redactArgv(argv: readonly string[], options: RedactOptions = {}): string {
  const path = resolveCommandPath(argv);
  const cmd = path.length > 0 ? getCommand(path.join(' ')) : undefined;
  const specs = cmd?.positionals ?? [];
  const out: string[] = [];
  let words = 0;
  let positional = 0;
  for (let i = 0; i < argv.length; ) {
    const token = argv[i];
    if (isOption(token)) {
      const { emit, consumed } = redactOption(cmd, argv, i);
      out.push(...emit);
      i += consumed;
      continue;
    }
    i++;
    if (words < path.length) {
      words++;
      out.push(token);
      continue;
    }
    out.push(positionalToken(specs[Math.min(positional, specs.length - 1)], token));
    positional++;
  }
  return scrubText(out.join(' '), { homeDir: options.homeDir });
}
