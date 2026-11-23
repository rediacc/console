import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  ERROR_CODE_ORIGINS,
  errorOrigin,
  listErrorCodeOrigins,
  NAMED_ERROR_ORIGINS,
} from '../error-origins.js';
import { ERROR_CODES } from '../errors.js';

const SRC_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const ORIGINS = new Set(['user', 'environment', 'rediacc']);

/** CliExitError first arguments that are not literals and carry a code chosen at run time. */
const DYNAMIC_FIRST_ARGS: Record<string, string> = {
  'error.code': 'cluster-snapshot forwards the code of a renet refusal',
  'result.code': 'renet-execution forwards the code renet reported',
  'networkDown ? ERROR_CODES.NETWORK_ERROR : ERROR_CODES.GENERAL_ERROR':
    'two envelope codes, both listed',
};

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (name === '__tests__' || name === 'node_modules') continue;
    if (statSync(full).isDirectory()) out.push(...sourceFiles(full));
    else if (name.endsWith('.ts') && !name.endsWith('.d.ts')) out.push(full);
  }
  return out;
}

interface Found {
  /** A string literal code, or an `ERROR_CODES.X` key. */
  codes: Set<string>;
  /** CliExitError first arguments that are neither. */
  other: Set<string>;
}

/** Every code the source names, by four spellings: `errorCode:` and `code` literals, `*_CODE` constants, CliExitError first arguments. */
function inventory(texts: string[]): Found {
  const codes = new Set<string>();
  const other = new Set<string>();
  const constants = new Set<string>();
  for (const text of texts) {
    for (const m of text.matchAll(/\berrorCode:\s*'([A-Z][A-Z0-9_]+)'/g)) codes.add(m[1]);
    for (const m of text.matchAll(/\bcode(?::| =)\s*'([A-Z][A-Z0-9_]+)'/g)) codes.add(m[1]);
    for (const m of text.matchAll(/\b([A-Z][A-Z0-9_]*_CODE)\s*=\s*'([A-Z][A-Z0-9_]+)'/g)) {
      codes.add(m[2]);
      constants.add(m[1]);
    }
    for (const m of text.matchAll(/new CliExitError\(\s*([^,]+?),/g)) {
      const arg = m[1].trim();
      const literal = /^'([A-Z][A-Z0-9_]+)'$/.exec(arg);
      const key = /^ERROR_CODES\.([A-Z_]+)$/.exec(arg);
      if (literal) codes.add(literal[1]);
      else if (key) codes.add(key[1]);
      else other.add(arg);
    }
  }
  // A first argument that is a `*_CODE` constant is covered by its definition.
  for (const c of constants) other.delete(c);
  return { codes, other };
}

describe('error origins', () => {
  it('gives every envelope code a valid origin', () => {
    expect(Object.keys(ERROR_CODE_ORIGINS).sort()).toEqual(Object.keys(ERROR_CODES).sort());
    for (const [code, origin] of Object.entries(ERROR_CODE_ORIGINS)) {
      expect(ORIGINS.has(origin), code).toBe(true);
    }
  });

  it('gives every named code a valid origin', () => {
    for (const [code, origin] of Object.entries(NAMED_ERROR_ORIGINS)) {
      expect(ORIGINS.has(origin), code).toBe(true);
    }
  });

  it('lets a named code override its envelope code', () => {
    expect(errorOrigin('GENERAL_ERROR')).toBe('environment');
    expect(errorOrigin('GENERAL_ERROR', 'UNCAUGHT_EXCEPTION')).toBe('rediacc');
    expect(errorOrigin('SERVER_ERROR')).toBe('rediacc');
  });

  it('answers undefined for a code no table knows', () => {
    expect(errorOrigin('NO_SUCH_CODE')).toBeUndefined();
    expect(errorOrigin('NO_SUCH_CODE', 'ALSO_UNKNOWN')).toBeUndefined();
    expect(errorOrigin('toString')).toBeUndefined();
  });

  it('lists every code with an origin', () => {
    const rows = listErrorCodeOrigins();
    expect(rows).toHaveLength(
      Object.keys(ERROR_CODES).length + Object.keys(NAMED_ERROR_ORIGINS).length
    );
    for (const row of rows) expect(ORIGINS.has(row.origin), row.code).toBe(true);
  });

  it('lists every code the source emits', () => {
    const texts = sourceFiles(SRC_DIR).map((f) => readFileSync(f, 'utf8'));
    const { codes, other } = inventory(texts);
    const unlisted = [...codes].filter(
      (c) => !Object.hasOwn(NAMED_ERROR_ORIGINS, c) && !Object.hasOwn(ERROR_CODE_ORIGINS, c)
    );
    expect(unlisted).toEqual([]);
    expect([...other].filter((a) => !Object.hasOwn(DYNAMIC_FIRST_ARGS, a))).toEqual([]);
    // The scan sees real codes, so an empty inventory cannot pass.
    expect(codes.size).toBeGreaterThan(20);
    expect(relative(SRC_DIR, join(SRC_DIR, 'types'))).toBe('types');
  });

  it('reports an unlisted code (control)', () => {
    const { codes, other } = inventory([
      "throw new CliExitError('BRAND_NEW_CODE', 'x'); const X_CODE = 'ANOTHER_ONE';",
      "x({ errorCode: 'THIRD_ONE' }); new CliExitError(someVar, 'm');",
    ]);
    expect([...codes].sort()).toEqual(['ANOTHER_ONE', 'BRAND_NEW_CODE', 'THIRD_ONE']);
    expect([...other]).toEqual(['someVar']);
    expect(Object.hasOwn(NAMED_ERROR_ORIGINS, 'BRAND_NEW_CODE')).toBe(false);
  });
});
