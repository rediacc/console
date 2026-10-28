/**
 * The authorized_keys planner behind `rdc machine access push`
 * (agent/plans/PLAN-ssh-key-source-ranges.md, Design 2). Pure: text in, text
 * out, no I/O and no SSH.
 *
 * A line rdc manages carries `rdc-access:<configId[0:8]>:<key name>` as the
 * last token of its comment. The config-id prefix scopes management, so two
 * configs managing one machine never touch each other's lines. Every line the
 * planner does not manage keeps its bytes and its line ending.
 */

import {
  ACCESS_KEY_MARKER_PREFIX,
  canonicalKeyBlob,
  parseOpenSshPublicKey,
  type SourceRanges,
} from '@rediacc/shared/config-schema';

/** The options written in front of a restricted access key: the set that passed live (round 4). */
export const ACCESS_RESTRICT_OPTIONS = [
  'no-port-forwarding',
  'no-agent-forwarding',
  'no-X11-forwarding',
  'no-pty',
  'no-user-rc',
] as const;

/** Length of the config-id prefix in a marker. */
const CONFIG_ID_PREFIX_LENGTH = 8;

export type AuthorizedKeysLineKind = 'blank' | 'comment' | 'key' | 'unparsed';

export interface AccessMarker {
  /** The first eight characters of the config id that wrote the line. */
  configPrefix: string;
  /** The access key's name in that config. */
  name: string;
}

export interface AuthorizedKeysLine {
  /** 1-based physical line number. */
  number: number;
  /** The line's bytes without its line ending. */
  raw: string;
  /** The line ending as found; '' only for a last line without one. */
  eol: '\n' | '\r\n' | '';
  kind: AuthorizedKeysLineKind;
  /** The options field as written (`from="a,b",no-pty`), when the key line has one. */
  options?: string;
  /** The options field split on unquoted commas; quoted values stay one token. */
  optionTokens: string[];
  type?: string;
  blob?: string;
  /** Everything after the blob, marker included. */
  comment?: string;
  marker?: AccessMarker;
}

export interface DesiredAccessKey {
  /** The access key's name. */
  name: string;
  /** One OpenSSH public key line: `<type> <base64> [comment]`. */
  key: string;
  ranges: SourceRanges;
  /** Write the no-forwarding, no-pty, no-user-rc set after `from=`. */
  restrict: boolean;
}

export interface AccessLineSpec extends DesiredAccessKey {
  configId: string;
}

export type AccessChangeAction =
  | 'update'
  | 'unchanged'
  | 'adopt'
  | 'drop-duplicate'
  | 'append'
  | 'remove';

export interface AccessChange {
  /** The access key the change is for. */
  key: string;
  action: AccessChangeAction;
  /**
   * 1-based line number: in the input for every action but `append`, in the
   * output for `append`.
   */
  line: number;
  /** The line after the change; the removed line for `remove` and `drop-duplicate`. */
  text: string;
}

export interface AccessRewritePlan {
  text: string;
  changes: AccessChange[];
}

/** A line with the same key blob as a desired access key carries `command=`: rdc refuses to rewrite it. */
export class AccessKeyConflictError extends Error {
  readonly code = 'ACCESS_KEY_CONFLICT';
  constructor(
    readonly keyName: string,
    readonly line: number
  ) {
    super(
      `authorized_keys line ${line} carries the key of access key ${keyName} with a command= option; ` +
        'remove that line or declare a different key'
    );
    this.name = 'AccessKeyConflictError';
  }
}

const BASE64_BLOB = /^[A-Za-z0-9+/]+={0,2}$/;
/** Key type tokens sshd accepts without options in front. */
const KEY_TYPE =
  /^(ssh-[a-z0-9-]+|ecdsa-sha2-[a-z0-9-]+|sk-[a-z0-9-]+@openssh\.com)(-cert-v01@openssh\.com)?$/;
const MARKER = new RegExp(`^${ACCESS_KEY_MARKER_PREFIX}([^:\\s]+):(\\S+)$`);

/** Index of the first unquoted whitespace character at or after `start`, or the length. */
function endOfOptions(text: string, start: number): number {
  let quoted = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (quoted && ch === '\\' && i + 1 < text.length) {
      i++;
      continue;
    }
    if (ch === '"') quoted = !quoted;
    else if (!quoted && (ch === ' ' || ch === '\t')) return i;
  }
  return text.length;
}

/** Split an options field on commas outside double quotes (sshd's own rule, `\"` escapes a quote). */
export function tokenizeOptions(options: string): string[] {
  const tokens: string[] = [];
  let current = '';
  let quoted = false;
  for (let i = 0; i < options.length; i++) {
    const ch = options[i];
    if (quoted && ch === '\\' && i + 1 < options.length) {
      current += ch + options[i + 1];
      i++;
      continue;
    }
    if (ch === '"') quoted = !quoted;
    if (ch === ',' && !quoted) {
      tokens.push(current);
      current = '';
      continue;
    }
    current += ch;
  }
  tokens.push(current);
  return tokens;
}

function skipBlanks(text: string, from: number): number {
  let i = from;
  while (i < text.length && (text[i] === ' ' || text[i] === '\t')) i++;
  return i;
}

function nextToken(text: string, from: number): { token: string; end: number } {
  let end = from;
  while (end < text.length && text[end] !== ' ' && text[end] !== '\t') end++;
  return { token: text.slice(from, end), end };
}

function parseMarker(comment: string | undefined): AccessMarker | undefined {
  if (comment === undefined) return undefined;
  const tokens = comment.trim().split(/\s+/);
  const match = MARKER.exec(tokens[tokens.length - 1] ?? '');
  return match ? { configPrefix: match[1], name: match[2] } : undefined;
}

type KeyFields = Pick<
  AuthorizedKeysLine,
  'kind' | 'options' | 'optionTokens' | 'type' | 'blob' | 'comment' | 'marker'
>;

function parseLineFields(raw: string): KeyFields {
  const start = skipBlanks(raw, 0);
  if (start === raw.length) return { kind: 'blank', optionTokens: [] };
  if (raw[start] === '#') return { kind: 'comment', optionTokens: [] };

  let cursor = start;
  let options: string | undefined;
  const first = nextToken(raw, cursor);
  if (!KEY_TYPE.test(first.token)) {
    const end = endOfOptions(raw, cursor);
    options = raw.slice(cursor, end);
    cursor = skipBlanks(raw, end);
  }
  const type = nextToken(raw, cursor);
  const blobStart = skipBlanks(raw, type.end);
  const blob = nextToken(raw, blobStart);
  if (!KEY_TYPE.test(type.token) || !BASE64_BLOB.test(blob.token)) {
    return { kind: 'unparsed', optionTokens: [] };
  }
  const commentStart = skipBlanks(raw, blob.end);
  const comment = commentStart < raw.length ? raw.slice(commentStart) : undefined;
  return {
    kind: 'key',
    options,
    optionTokens: options === undefined ? [] : tokenizeOptions(options),
    type: type.token,
    blob: blob.token,
    comment,
    marker: parseMarker(comment),
  };
}

/** One entry per physical line of an authorized_keys file. */
export function parseAuthorizedKeys(text: string): AuthorizedKeysLine[] {
  const lines: AuthorizedKeysLine[] = [];
  let offset = 0;
  while (offset < text.length) {
    const lf = text.indexOf('\n', offset);
    let raw: string;
    let eol: AuthorizedKeysLine['eol'];
    if (lf < 0) {
      raw = text.slice(offset);
      eol = '';
      offset = text.length;
    } else if (lf > offset && text[lf - 1] === '\r') {
      raw = text.slice(offset, lf - 1);
      eol = '\r\n';
      offset = lf + 1;
    } else {
      raw = text.slice(offset, lf);
      eol = '\n';
      offset = lf + 1;
    }
    lines.push({ number: lines.length + 1, raw, eol, ...parseLineFields(raw) });
  }
  return lines;
}

function parsePublicKey(
  name: string,
  key: string
): { type: string; blob: string; comment?: string } {
  const parsed = parseOpenSshPublicKey(key.trim());
  if (parsed === null) {
    throw new Error(`access key ${name}: publicKey is not one OpenSSH public key line`);
  }
  return parsed;
}

/**
 * `from="<ipv4...>,<ipv6...>"[,<restrict options>] <type> <blob>[ <comment>] rdc-access:<configId[0:8]>:<name>`.
 * IPv4 ranges first, then IPv6, each in declared order.
 */
export function renderAccessLine(spec: AccessLineSpec): string {
  const { type, blob, comment } = parsePublicKey(spec.name, spec.key);
  const ranges = [...(spec.ranges.ipv4 ?? []), ...(spec.ranges.ipv6 ?? [])];
  if (ranges.length === 0) {
    throw new Error(
      `access key ${spec.name}: no source range; an access key is never unrestricted`
    );
  }
  const options = [`from="${ranges.join(',')}"`, ...(spec.restrict ? ACCESS_RESTRICT_OPTIONS : [])];
  const marker = `${ACCESS_KEY_MARKER_PREFIX}${spec.configId.slice(0, CONFIG_ID_PREFIX_LENGTH)}:${spec.name}`;
  return [options.join(','), type, blob, ...(comment ? [comment] : []), marker].join(' ');
}

interface DesiredLine {
  name: string;
  /** The canonical blob (`canonicalKeyBlob`): the decoded key, so spellings differing in padding bits match. */
  blob: string;
  rendered: string;
}

/**
 * Whether a parsed line holds the desired key. Matching is by the decoded key, as sshd compares it:
 * options, comment and the base64 spelling (unused padding bits) never decide it.
 */
function holdsKey(line: AuthorizedKeysLine, desired: DesiredLine): boolean {
  if (line.kind !== 'key' || line.blob === undefined) return false;
  return canonicalKeyBlob(line.blob) === desired.blob;
}

function canonicalDesiredBlob(name: string, key: string): string {
  const blob = canonicalKeyBlob(parsePublicKey(name, key).blob);
  if (blob === null) throw new Error(`access key ${name}: publicKey blob is not valid base64`);
  return blob;
}

function hasCommandOption(line: AuthorizedKeysLine): boolean {
  return line.optionTokens.some((token) => /^command=/i.test(token));
}

type Disposition = { kind: 'keep' } | { kind: 'replace'; text: string } | { kind: 'delete' };

function lineEndingFor(lines: AuthorizedKeysLine[]): '\n' | '\r\n' {
  for (let i = lines.length - 1; i >= 0; i--) {
    const eol = lines[i].eol;
    if (eol !== '') return eol;
  }
  return '\n';
}

interface PlanState {
  parsed: AuthorizedKeysLine[];
  /** The config-id prefix this config's markers carry. */
  prefix: string;
  disposition: Map<number, Disposition>;
  changes: AccessChange[];
  appended: DesiredLine[];
}

function isOurs(state: PlanState, line: AuthorizedKeysLine): boolean {
  return line.marker?.configPrefix === state.prefix;
}

/** Record what one desired key does to the file: update/unchanged, adopt, drop-duplicate, or append. */
function planDesiredKey(state: PlanState, w: DesiredLine): void {
  const sameBlob = state.parsed.filter((line) => line.marker === undefined && holdsKey(line, w));
  const conflict = sameBlob.find(hasCommandOption);
  if (conflict) throw new AccessKeyConflictError(w.name, conflict.number);

  const marked = state.parsed.filter((line) => isOurs(state, line) && line.marker?.name === w.name);
  const [target, ...duplicates] = [...marked, ...sameBlob];
  if (target === undefined) {
    state.appended.push(w);
    return;
  }
  let action: AccessChangeAction = 'adopt';
  if (marked.length > 0) action = target.raw === w.rendered ? 'unchanged' : 'update';
  state.disposition.set(
    target.number,
    action === 'unchanged' ? { kind: 'keep' } : { kind: 'replace', text: w.rendered }
  );
  state.changes.push({ key: w.name, action, line: target.number, text: w.rendered });
  // sshd tries every line holding the key, so an unrestricted duplicate would bypass from=.
  for (const dup of duplicates) {
    state.disposition.set(dup.number, { kind: 'delete' });
    state.changes.push({ key: w.name, action: 'drop-duplicate', line: dup.number, text: dup.raw });
  }
}

/** Remove this config's marked lines whose key is no longer desired. */
function planRemovals(state: PlanState, wantedNames: Set<string>): void {
  for (const line of state.parsed) {
    const name = line.marker?.name ?? '';
    if (!isOurs(state, line) || wantedNames.has(name)) continue;
    state.disposition.set(line.number, { kind: 'delete' });
    state.changes.push({ key: name, action: 'remove', line: line.number, text: line.raw });
  }
}

/** The new text: kept lines with their own endings, then the appended lines. */
function assemble(state: PlanState): string {
  const out: string[] = [];
  let outLines = 0;
  let lastEol: AuthorizedKeysLine['eol'] = '';
  for (const line of state.parsed) {
    const d = state.disposition.get(line.number) ?? { kind: 'keep' };
    if (d.kind === 'delete') continue;
    out.push(d.kind === 'replace' ? d.text : line.raw, line.eol);
    lastEol = line.eol;
    outLines++;
  }
  if (state.appended.length === 0) return out.join('');

  const eol = lineEndingFor(state.parsed);
  // A file without a final newline gets one only here, when a line is appended after it.
  if (outLines > 0 && lastEol === '') out.push(eol);
  for (const w of state.appended) {
    outLines++;
    out.push(w.rendered, eol);
    state.changes.push({ key: w.name, action: 'append', line: outLines, text: w.rendered });
  }
  return out.join('');
}

/**
 * Plan the rewrite that makes the file hold exactly the desired access keys of
 * this config. Planning its own output gives the same text and only
 * `unchanged`. Throws AccessKeyConflictError when an unmarked line holding a
 * desired key carries `command=`.
 */
export function planAccessRewrite(
  parsed: AuthorizedKeysLine[],
  desired: DesiredAccessKey[],
  configId: string
): AccessRewritePlan {
  const wanted: DesiredLine[] = desired.map((d) => ({
    name: d.name,
    blob: canonicalDesiredBlob(d.name, d.key),
    rendered: renderAccessLine({ ...d, configId }),
  }));
  const state: PlanState = {
    parsed,
    prefix: configId.slice(0, CONFIG_ID_PREFIX_LENGTH),
    disposition: new Map(),
    changes: [],
    appended: [],
  };
  for (const w of wanted) planDesiredKey(state, w);
  planRemovals(state, new Set(wanted.map((w) => w.name)));
  const text = assemble(state);
  const order = (c: AccessChange) => (c.action === 'append' ? 1 : 0);
  state.changes.sort((a, b) => order(a) - order(b) || a.line - b.line);
  return { text, changes: state.changes };
}
