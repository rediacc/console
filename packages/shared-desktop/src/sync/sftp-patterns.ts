/**
 * Rsync-style exclude pattern subset for the SFTP fallback path.
 *
 *  - `*` matches any sequence within a path component.
 *  - `**` matches any sequence across components.
 *  - `?` matches a single character within a component.
 *  - `[abc]` is a character class.
 *  - Leading `/` anchors the pattern to the transfer root.
 *  - Trailing `/` matches directories only.
 */

export interface CompiledPattern {
  regex: RegExp;
  dirOnly: boolean;
}

function escapeChar(ch: string): string {
  return '.+^$(){}|\\'.includes(ch) ? `\\${ch}` : ch;
}

/**
 * Translate one body character (or look-ahead) to its regex equivalent.
 * Returns the regex fragment plus how many extra characters to skip.
 */
function translateChar(body: string, i: number): { fragment: string; advance: number } {
  const ch = body[i];
  if (ch === '*') {
    if (body[i + 1] === '*') {
      if (body[i + 2] === '/') {
        // `**/` collapses leading prefix or matches empty, so `**/x` also matches `x`.
        return { fragment: '(?:.*/)?', advance: 2 };
      }
      return { fragment: '.*', advance: 1 };
    }
    return { fragment: '[^/]*', advance: 0 };
  }
  if (ch === '?') return { fragment: '[^/]', advance: 0 };
  if (ch === '[') {
    const end = body.indexOf(']', i + 1);
    if (end === -1) return { fragment: '\\[', advance: 0 };
    return { fragment: body.slice(i, end + 1), advance: end - i };
  }
  return { fragment: escapeChar(ch), advance: 0 };
}

function compileBody(body: string): string {
  let re = '';
  for (let i = 0; i < body.length; i++) {
    const { fragment, advance } = translateChar(body, i);
    re += fragment;
    i += advance;
  }
  return re;
}

function wrapPattern(re: string, anchored: boolean, hasSlash: boolean): string {
  if (anchored) {
    // Anchored to root: matches the full path or a prefix segment.
    return `^${re}(/.*)?$`;
  }
  if (hasSlash) {
    // Path-relative match anywhere.
    return `(^|/)${re}(/.*)?$`;
  }
  // Bare name: match the basename (final segment) only.
  return `^([^/]+/)*${re}$`;
}

function compilePattern(pattern: string): CompiledPattern {
  const dirOnly = pattern.endsWith('/');
  let body = dirOnly ? pattern.slice(0, -1) : pattern;
  const anchored = body.startsWith('/');
  if (anchored) body = body.slice(1);
  const re = compileBody(body);
  const wrapped = wrapPattern(re, anchored, body.includes('/'));
  return { regex: new RegExp(wrapped), dirOnly };
}

/**
 * Compile a pattern set once. Pass the result to `isExcludedCompiled`
 * for every file/dir during a walk to avoid recompiling regexes on each
 * entry — a hot loop in large repositories.
 */
export function compilePatterns(patterns: string[]): CompiledPattern[] {
  return patterns.map(compilePattern);
}

export function isExcludedCompiled(
  relativePath: string,
  isDir: boolean,
  compiled: CompiledPattern[]
): boolean {
  const normalized = relativePath.replaceAll('\\', '/');
  for (const c of compiled) {
    if (c.dirOnly && !isDir) continue;
    if (c.regex.test(normalized)) return true;
  }
  return false;
}

/**
 * Convenience wrapper that compiles patterns on every call. Kept for
 * one-shot callers. Hot paths (filesystem walks) should call
 * `compilePatterns` once then `isExcludedCompiled` per entry.
 */
export function isExcluded(relativePath: string, isDir: boolean, patterns: string[]): boolean {
  return isExcludedCompiled(relativePath, isDir, compilePatterns(patterns));
}
