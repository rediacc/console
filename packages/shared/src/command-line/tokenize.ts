/**
 * Quote-aware tokenizer for an `rdc` command line, with spans.
 *
 * The one tokenizer shared by the console command box, the recipe parser, the
 * shell-completion generator and the CLI contract generator's example parser
 * (packages/cli/scripts/lib/example-parse.ts). Spans are UTF-16 offsets into the
 * line, so `line.slice(token.start, token.end)` is the token as typed (`raw`).
 *
 * Shell-like rules, deliberately small:
 * - tokens split on spaces, tabs and line breaks outside quotes;
 * - single quotes keep every character literally until the closing quote;
 * - double quotes keep every character except that a backslash escapes `"` and `\`;
 * - outside quotes a backslash escapes the next character;
 * - adjacent quoted and unquoted pieces join into one token (`a"b c"d`).
 */

/** The quote character of a token's first quoted piece, or null when it has none. */
export type QuoteChar = '"' | "'";

export interface Token {
  /** The value after quote removal and escape handling. */
  text: string;
  /** Offset of the first character of the token as typed. */
  start: number;
  /** Offset just past the last character of the token as typed. */
  end: number;
  /** The token exactly as typed, `line.slice(start, end)`. */
  raw: string;
  /** Quote character of the first quoted piece; null for a token typed without quotes. */
  quote: QuoteChar | null;
  /** False only for a token whose quote never closed; its `end` is the end of the line. */
  closed: boolean;
}

function isSpace(ch: string): boolean {
  return ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r';
}

/** Scanner state for one line; `tokenize` drives it one character at a time. */
class Scanner {
  readonly tokens: Token[] = [];
  private current = '';
  private start = -1;
  private quote: QuoteChar | null = null;
  private firstQuote: QuoteChar | null = null;

  constructor(private readonly line: string) {}

  /** Consume the character at `i`; returns the index of the last character consumed. */
  step(i: number): number {
    const ch = this.line[i];
    if (this.quote) return this.stepQuoted(i, ch);
    if (isSpace(ch)) {
      this.flush(i, true);
      return i;
    }
    if (this.start === -1) this.start = i;
    if (ch === '"' || ch === "'") {
      this.quote = ch;
      this.firstQuote ??= ch;
      return i;
    }
    if (ch === '\\' && i + 1 < this.line.length) {
      this.current += this.line[i + 1];
      return i + 1;
    }
    this.current += ch;
    return i;
  }

  private stepQuoted(i: number, ch: string): number {
    if (ch === this.quote) {
      this.quote = null;
      return i;
    }
    const next = this.line[i + 1];
    if (this.quote === '"' && ch === '\\' && (next === '"' || next === '\\')) {
      this.current += next;
      return i + 1;
    }
    this.current += ch;
    return i;
  }

  /** End of input: close the last token, marked unclosed when a quote is still open. */
  finish(): Token[] {
    this.flush(this.line.length, this.quote === null);
    return this.tokens;
  }

  private flush(end: number, closed: boolean): void {
    if (this.start === -1) return;
    this.tokens.push({
      text: this.current,
      start: this.start,
      end,
      raw: this.line.slice(this.start, end),
      quote: this.firstQuote,
      closed,
    });
    this.current = '';
    this.start = -1;
    this.firstQuote = null;
  }
}

/** Split `line` into tokens with spans. Never throws; an unclosed quote yields a token with `closed: false`. */
export function tokenize(line: string): Token[] {
  const scanner = new Scanner(line);
  for (let i = 0; i < line.length; i++) i = scanner.step(i);
  return scanner.finish();
}

/** The token that never closed its quote, or undefined when every quote closed. */
export function unclosedQuote(tokens: readonly Token[]): Token | undefined {
  return tokens.find((t) => !t.closed);
}

/** True for a token that reads as a flag: starts with `-` as typed, more than one character, and not quoted. */
export function isFlagLike(token: Token): boolean {
  return token.raw.length > 1 && token.raw.startsWith('-') && token.text.startsWith('-');
}
