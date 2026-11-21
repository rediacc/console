/**
 * Byte-preserving JSON insertion for locale catalogs.
 *
 * The locale trees do not share one serialization: the www catalogs are prettier-formatted
 * (not `JSON.stringify` canonical, so a parse and re-stringify rewrites them), and every
 * catalog keeps its own key order. A sync that parses, merges, sorts and re-serializes
 * therefore rewrites whole files for a five-key delta. This module instead parses the text
 * with positions, computes the minimal set of insertions that bring a target up to a source,
 * and splices them in. Every byte outside an insertion is untouched.
 */

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

interface ScalarNode {
  kind: 'scalar';
  start: number;
  end: number;
}
interface MemberNode {
  key: string;
  start: number;
  end: number;
  value: SpanNode;
}
interface ObjectNode {
  kind: 'object';
  start: number;
  end: number;
  members: MemberNode[];
}
interface ItemNode {
  start: number;
  end: number;
  value: SpanNode;
}
interface ArrayNode {
  kind: 'array';
  start: number;
  end: number;
  items: ItemNode[];
}
type SpanNode = ScalarNode | ObjectNode | ArrayNode;

interface Edit {
  /** Offset in the original text where `deleteLen` characters are replaced by `text`. */
  pos: number;
  deleteLen: number;
  text: string;
}

export interface SpliceResult {
  text: string;
  /** Leaf values added (a missing subtree counts its leaves). */
  added: number;
}

const WS = new Set([' ', '\t', '\n', '\r']);

function parseSpans(text: string): SpanNode {
  let i = 0;
  const skip = () => {
    while (i < text.length && WS.has(text[i])) i++;
  };
  const readString = (): string => {
    const start = i;
    i++;
    while (i < text.length && text[i] !== '"') i += text[i] === '\\' ? 2 : 1;
    i++;
    return JSON.parse(text.slice(start, i)) as string;
  };
  const readValue = (): SpanNode => {
    skip();
    const start = i;
    const c = text[i];
    if (c === '{') {
      i++;
      const members: MemberNode[] = [];
      skip();
      while (text[i] !== '}') {
        skip();
        const mStart = i;
        const key = readString();
        skip();
        i++; // colon
        const value = readValue();
        members.push({ key, start: mStart, end: value.end, value });
        skip();
        if (text[i] === ',') i++;
        skip();
      }
      i++;
      return { kind: 'object', start, end: i, members };
    }
    if (c === '[') {
      i++;
      const items: ItemNode[] = [];
      skip();
      while (text[i] !== ']') {
        const value = readValue();
        items.push({ start: value.start, end: value.end, value });
        skip();
        if (text[i] === ',') i++;
        skip();
      }
      i++;
      return { kind: 'array', start, end: i, items };
    }
    if (c === '"') {
      readString();
    } else {
      while (i < text.length && !WS.has(text[i]) && !',]}'.includes(text[i])) i++;
    }
    return { kind: 'scalar', start, end: i };
  };
  const root = readValue();
  skip();
  if (i !== text.length) throw new Error(`trailing content at offset ${i}`);
  return root;
}

const isObj = (v: unknown): v is { [key: string]: JsonValue } =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

export function countLeaves(v: JsonValue): number {
  if (Array.isArray(v)) return v.reduce<number>((n, x) => n + countLeaves(x), 0);
  if (isObj(v)) return Object.values(v).reduce<number>((n, x) => n + countLeaves(x), 0);
  return 1;
}

const keyCmp = (a: string, b: string) =>
  a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });

function isSortedKeys(keys: string[]): boolean {
  return keys.every((k, i) => i === 0 || keyCmp(keys[i - 1], k) <= 0);
}

/** Whitespace between the start of the member's line and the member, or null if inline. */
function lineIndent(text: string, pos: number): string | null {
  const nl = text.lastIndexOf('\n', pos - 1);
  const lead = text.slice(nl + 1, pos);
  return /^[ \t]*$/.test(lead) ? lead : null;
}

function serialize(value: JsonValue, indent: string): string {
  return JSON.stringify(value, null, 2)
    .split('\n')
    .join('\n' + indent);
}

/**
 * The edits that bring `target` (whose text and spans are given) up to `source`:
 * missing keys are inserted, short arrays are extended, and a value whose container type
 * differs from the source is replaced. Existing leaf translations are never touched.
 */
function diffEdits(
  text: string,
  node: SpanNode,
  target: JsonValue,
  source: JsonValue,
  indent: string,
  edits: Edit[]
): number {
  let added = 0;

  if (node.kind === 'object' && isObj(target) && isObj(source)) {
    const members = node.members;
    const have = new Set(members.map((m) => m.key));
    const missing = Object.keys(source).filter((k) => !have.has(k));
    const memberIndent =
      (members.length > 0 ? lineIndent(text, members[0].start) : null) ?? indent + '  ';
    const closeIndent = lineIndent(text, node.end - 1) ?? indent;

    // gap g means "before members[g]"; g === members.length means after the last member.
    const gaps = new Map<number, string[]>();
    if (missing.length > 0) {
      const existing = members.map((m) => m.key);
      if (isSortedKeys(existing)) {
        for (const k of [...missing].sort(keyCmp)) {
          let g = existing.findIndex((e) => keyCmp(e, k) > 0);
          if (g === -1) g = existing.length;
          gaps.set(g, [...(gaps.get(g) ?? []), k]);
        }
      } else {
        // The file keeps its own order: follow the English predecessor that is present.
        let g = 0;
        for (const k of Object.keys(source)) {
          if (have.has(k)) {
            g = existing.indexOf(k) + 1;
          } else {
            gaps.set(g, [...(gaps.get(g) ?? []), k]);
          }
        }
      }
    }

    if (members.length === 0 && missing.length > 0) {
      const body = missing
        .map((k) => `${memberIndent}${JSON.stringify(k)}: ${serialize(source[k], memberIndent)}`)
        .join(',\n');
      edits.push({
        pos: node.start,
        deleteLen: node.end - node.start,
        text: `{\n${body}\n${closeIndent}}`,
      });
      added += missing.reduce((n, k) => n + countLeaves(source[k]), 0);
    } else {
      for (const [g, keys] of gaps) {
        const entries = keys.map(
          (k) => `${JSON.stringify(k)}: ${serialize(source[k], memberIndent)}`
        );
        added += keys.reduce((n, k) => n + countLeaves(source[k]), 0);
        if (g < members.length) {
          edits.push({
            pos: members[g].start,
            deleteLen: 0,
            text: entries.map((e) => `${e},\n${memberIndent}`).join(''),
          });
        } else {
          edits.push({
            pos: members[members.length - 1].end,
            deleteLen: 0,
            text: entries.map((e) => `,\n${memberIndent}${e}`).join(''),
          });
        }
      }
    }

    for (const m of members) {
      if (m.key in source) {
        added += diffEdits(text, m.value, target[m.key], source[m.key], memberIndent, edits);
      }
    }
    return added;
  }

  if (node.kind === 'array' && Array.isArray(target) && Array.isArray(source)) {
    const items = node.items;
    const itemIndent =
      (items.length > 0 ? lineIndent(text, items[0].start) : null) ?? indent + '  ';
    const closeIndent = lineIndent(text, node.end - 1) ?? indent;
    const extra = source.slice(items.length);
    if (extra.length > 0) {
      added += extra.reduce<number>((n, v) => n + countLeaves(v), 0);
      if (items.length === 0) {
        const body = extra.map((v) => `${itemIndent}${serialize(v, itemIndent)}`).join(',\n');
        edits.push({
          pos: node.start,
          deleteLen: node.end - node.start,
          text: `[\n${body}\n${closeIndent}]`,
        });
      } else if (lineIndent(text, items[items.length - 1].start) === null) {
        // An inline array (`["a", "b"]`) grows inline, so its line keeps its shape.
        edits.push({
          pos: items[items.length - 1].end,
          deleteLen: 0,
          text: extra.map((v) => `, ${JSON.stringify(v)}`).join(''),
        });
      } else {
        edits.push({
          pos: items[items.length - 1].end,
          deleteLen: 0,
          text: extra.map((v) => `,\n${itemIndent}${serialize(v, itemIndent)}`).join(''),
        });
      }
    }
    for (let n = 0; n < Math.min(items.length, source.length); n++) {
      added += diffEdits(text, items[n].value, target[n], source[n], itemIndent, edits);
    }
    return added;
  }

  const sourceIsContainer = Array.isArray(source) || isObj(source);
  const sameContainer =
    (Array.isArray(source) && Array.isArray(target)) || (isObj(source) && isObj(target));
  if (sourceIsContainer && !sameContainer) {
    edits.push({
      pos: node.start,
      deleteLen: node.end - node.start,
      text: serialize(source, indent),
    });
    return countLeaves(source);
  }
  // Both leaves (or a container replaced by a leaf): the existing translation stands.
  return added;
}

/** Bring `targetText` up to `source` by insertion only. Returns the same string when nothing is missing. */
export function spliceMissing(targetText: string, source: JsonValue): SpliceResult {
  const root = parseSpans(targetText);
  const target = JSON.parse(targetText) as JsonValue;
  const edits: Edit[] = [];
  const added = diffEdits(targetText, root, target, source, '', edits);
  if (edits.length === 0) return { text: targetText, added: 0 };
  let text = targetText;
  for (const e of [...edits].sort((a, b) => b.pos - a.pos)) {
    text = text.slice(0, e.pos) + e.text + text.slice(e.pos + e.deleteLen);
  }
  return { text, added };
}

/** Leaf paths present in `target` and absent from `source` (reported, never deleted). */
export function extraPaths(target: JsonValue, source: JsonValue, prefix = ''): string[] {
  if (isObj(target) && isObj(source)) {
    return Object.keys(target).flatMap((k) =>
      k in source ? extraPaths(target[k], source[k], `${prefix}${k}.`) : [`${prefix}${k}`]
    );
  }
  if (Array.isArray(target) && Array.isArray(source)) {
    return target
      .slice(source.length)
      .map((_, n) => `${prefix}${source.length + n}`)
      .concat(
        target.slice(0, source.length).flatMap((t, n) => extraPaths(t, source[n], `${prefix}${n}.`))
      );
  }
  return [];
}
