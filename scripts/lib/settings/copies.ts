/**
 * Reading and rewriting one copy of a registered tunable in place
 * (agent/plans/PLAN-settings-set-verb.md Design 2).
 *
 * A COPY IS EDITED BY ITS BYTE SPAN, never by re-serialising its file. `.ci/config/cf-spend-guard.json`
 * keeps some arrays on one line and a re-serialised file would rewrite them, so a one-number
 * change would land as a whole-file diff. The JSON locator below walks the text with its own
 * small scanner and returns the [start, end) offsets of the value a JSON pointer names; the
 * write replaces exactly those bytes. Two kinds of copy exist:
 *
 *   {file, json_path}         a JSON pointer (`/report/r2_storage_bytes`) into a JSON file;
 *   {file, py_dict, py_key}   one `"key": <number>` entry of a module-level Python dict literal
 *                             (`DEFAULT_CEILINGS = {...}` in cf_usage_report.py), written as an
 *                             int with `_` grouping.
 *
 * Every locator throws a CopyError naming the file and the path when the copy does not
 * resolve, so a dangling registry entry is refused, never skipped.
 */

export class CopyError extends Error {}

export interface JsonCopy {
  file: string;
  json_path: string;
}
export interface PyCopy {
  file: string;
  py_dict: string;
  py_key: string;
}
export type Copy = JsonCopy | PyCopy;

export const isJsonCopy = (c: Copy): c is JsonCopy => 'json_path' in c;
export const copyLabel = (c: Copy): string =>
  isJsonCopy(c)
    ? `${c.file}#${c.json_path}`
    : `${c.file}#${c.py_dict}[${JSON.stringify(c.py_key)}]`;

// ---- JSON spans -------------------------------------------------------------------------------

interface Span {
  start: number;
  end: number;
}

/** The pointer's tokens (RFC 6901: `~1` is `/`, `~0` is `~`). */
function pointerTokens(pointer: string): string[] {
  if (pointer === '') return [];
  if (!pointer.startsWith('/')) throw new CopyError(`${pointer} is not a JSON pointer`);
  return pointer
    .slice(1)
    .split('/')
    .map((t) => t.replace(/~1/g, '/').replace(/~0/g, '~'));
}

/** A scanner over JSON text that records where each value starts and ends. */
class Scanner {
  i = 0;
  constructor(
    readonly text: string,
    readonly where: string
  ) {}

  fail(msg: string): never {
    const line = this.text.slice(0, this.i).split('\n').length;
    throw new CopyError(`${this.where}:${line}: ${msg}`);
  }

  /** The character under the cursor ('' past the end). */
  ch(): string {
    return this.text.charAt(this.i);
  }

  ws(): void {
    while (this.i < this.text.length && /\s/.test(this.ch())) this.i++;
  }

  string(): string {
    if (this.ch() !== '"') this.fail('expected a string');
    const start = this.i;
    this.i++;
    while (this.i < this.text.length && this.ch() !== '"') {
      if (this.ch() === '\\') this.i++;
      this.i++;
    }
    if (this.i >= this.text.length) this.fail('unterminated string');
    this.i++;
    return JSON.parse(this.text.slice(start, this.i)) as string;
  }

  /** Skip one value, returning its span; descend into `tokens` when they remain, returning the span of the value they name. */
  value(tokens: string[]): Span | null {
    this.ws();
    const start = this.i;
    const c = this.ch();
    if (c === '{') {
      this.i++;
      let found: Span | null = null;
      this.ws();
      if (this.ch() === '}') {
        this.i++;
      } else {
        for (;;) {
          this.ws();
          const key = this.string();
          this.ws();
          if (this.ch() !== ':') this.fail(`expected ':' after ${JSON.stringify(key)}`);
          this.i++;
          const hit = this.value(tokens.length > 0 && tokens[0] === key ? tokens.slice(1) : []);
          if (tokens.length > 0 && tokens[0] === key) found = hit;
          this.ws();
          if (this.ch() === ',') {
            this.i++;
            continue;
          }
          if (this.ch() === '}') {
            this.i++;
            break;
          }
          this.fail("expected ',' or '}'");
        }
      }
      return tokens.length === 0 ? { start, end: this.i } : found;
    }
    if (c === '[') {
      this.i++;
      let found: Span | null = null;
      let idx = 0;
      this.ws();
      if (this.ch() === ']') {
        this.i++;
      } else {
        for (;;) {
          const mine = tokens.length > 0 && tokens[0] === String(idx);
          const hit = this.value(mine ? tokens.slice(1) : []);
          if (mine) found = hit;
          idx++;
          this.ws();
          if (this.ch() === ',') {
            this.i++;
            continue;
          }
          if (this.ch() === ']') {
            this.i++;
            break;
          }
          this.fail("expected ',' or ']'");
        }
      }
      return tokens.length === 0 ? { start, end: this.i } : found;
    }
    if (c === '"') {
      this.string();
    } else {
      const m = /^(?:-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null)/.exec(
        this.text.slice(this.i)
      );
      if (!m) this.fail('expected a JSON value');
      this.i += m[0].length;
    }
    return tokens.length === 0 ? { start, end: this.i } : null;
  }
}

/** The span of the value `pointer` names in `text`; throws when it does not resolve. */
export function jsonSpan(text: string, pointer: string, where: string): Span {
  const s = new Scanner(text, where);
  const span = s.value(pointerTokens(pointer));
  s.ws();
  if (s.i !== text.length) s.fail('trailing bytes after the JSON value');
  if (span === null) throw new CopyError(`${where}: ${pointer} does not resolve`);
  return span;
}

// ---- Python dict entries ----------------------------------------------------------------------

const PY_NUMBER = /[0-9][0-9_]*(?:\.[0-9_]*)?(?:[eE][+-]?[0-9]+)?/;

function pySpan(text: string, c: PyCopy): Span {
  const head = new RegExp(`^${c.py_dict}\\b[^=\\n]*=\\s*\\{`, 'm').exec(text);
  if (!head) throw new CopyError(`${c.file}: no module-level dict ${c.py_dict} = {...}`);
  const bodyStart = head.index + head[0].length;
  const close = text.slice(bodyStart).search(/^\}/m);
  if (close < 0) throw new CopyError(`${c.file}: ${c.py_dict} has no closing brace at column 0`);
  const body = text.slice(bodyStart, bodyStart + close);
  const key = c.py_key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`^\\s*["']${key}["']\\s*:\\s*(${PY_NUMBER.source})\\s*,`, 'gm');
  const hits = [...body.matchAll(re)];
  if (hits.length !== 1)
    throw new CopyError(
      `${c.file}: ${c.py_dict}[${JSON.stringify(c.py_key)}] ${hits.length === 0 ? 'is not a plain number entry' : 'appears more than once'}`
    );
  const h = hits[0];
  const start = bodyStart + (h.index ?? 0) + h[0].lastIndexOf(h[1]);
  return { start, end: start + h[1].length };
}

/** Python's int literal with `_` every three digits (`5_000_000_000_000`), the style the dict already uses. */
const pyInt = (n: number): string =>
  Number.isInteger(n) ? String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '_') : String(n);

// ---- reading and writing ------------------------------------------------------------------------

export interface CopyValue {
  value: unknown;
  line: number;
}

const lineOf = (text: string, offset: number): number => text.slice(0, offset).split('\n').length;

/** The value one copy holds now, and its 1-based line. */
export function readCopy(text: string, c: Copy): CopyValue {
  if (isJsonCopy(c)) {
    const s = jsonSpan(text, c.json_path, c.file);
    return { value: JSON.parse(text.slice(s.start, s.end)), line: lineOf(text, s.start) };
  }
  const s = pySpan(text, c);
  return {
    value: Number(text.slice(s.start, s.end).replace(/_/g, '')),
    line: lineOf(text, s.start),
  };
}

/** `text` with the copy's value replaced by `n`, every other byte unchanged. */
export function writeCopy(text: string, c: Copy, n: number): string {
  if (isJsonCopy(c)) {
    const s = jsonSpan(text, c.json_path, c.file);
    if (typeof JSON.parse(text.slice(s.start, s.end)) !== 'number')
      throw new CopyError(`${copyLabel(c)} does not hold a number`);
    return `${text.slice(0, s.start)}${JSON.stringify(n)}${text.slice(s.end)}`;
  }
  const s = pySpan(text, c);
  return `${text.slice(0, s.start)}${pyInt(n)}${text.slice(s.end)}`;
}

// ---- reasons --------------------------------------------------------------------------------

/**
 * Where a ruling's text lands. `replace` owns the whole string (a product's `why`), written as
 * `<prefix><value>. <reason>`; `segment` shares a string with other keys (`report_reason`), so
 * only the `<key>: ...` segment is replaced, up to the next `. <word>: ` segment or the end, and
 * a missing segment is prepended.
 */
export interface ReasonPath {
  file: string;
  json_path: string;
  mode: 'replace' | 'segment';
  prefix?: string;
  key?: string;
}

export function writeReason(text: string, r: ReasonPath, human: string, reason: string): string {
  const s = jsonSpan(text, r.json_path, r.file);
  const now = JSON.parse(text.slice(s.start, s.end)) as unknown;
  if (typeof now !== 'string') throw new CopyError(`${r.file}#${r.json_path} is not a string`);
  const ruling = reason.trim().replace(/\.$/, '');
  let next: string;
  if (r.mode === 'replace') {
    next = `${r.prefix ?? ''}${human}. ${ruling}.`;
  } else {
    if (!r.key) throw new CopyError(`${r.file}#${r.json_path}: a segment reason needs a key`);
    const seg = `${r.key}: ${human}, ${ruling}.`;
    const at = now.startsWith(`${r.key}: `) ? 0 : now.indexOf(` ${r.key}: `) + 1;
    if (at === 0 && !now.startsWith(`${r.key}: `)) {
      next = now === '' ? seg : `${seg} ${now}`;
    } else {
      const rest = now.slice(at + r.key.length + 2);
      const m = /\.\s+(?=[A-Za-z0-9_*]+: )/.exec(rest);
      const tail = m ? rest.slice(m.index + m[0].length) : '';
      next = `${now.slice(0, at)}${seg}${tail === '' ? '' : ` ${tail}`}`;
    }
  }
  return `${text.slice(0, s.start)}${JSON.stringify(next)}${text.slice(s.end)}`;
}
