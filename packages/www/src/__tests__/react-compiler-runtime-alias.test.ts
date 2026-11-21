/**
 * The `react-compiler-runtime` alias in astro.config.mjs, and the fact that makes it safe.
 *
 * Video.js imports `c` from the polyfill package; the alias sends those imports to React's own `react/compiler-runtime`, which drops 5 kB of unreachable fallback from the deferred player chunk. The swap is only behaviour-preserving while the polyfill would have delegated to React anyway, so that precondition is asserted next to the alias rather than assumed.
 */
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import config from '../../astro.config.mjs';

const require = createRequire(import.meta.url);

interface AliasEntry {
  find: string | RegExp;
  replacement: string;
}

const { c } = require('react/compiler-runtime') as { c: (size: number) => unknown[] };

/** A component shaped like compiled output: one memo-cache slot, read during render. */
function Cached() {
  const cache = c(1);
  return createElement('span', null, String(cache.length));
}

function compilerRuntimeAlias(): AliasEntry | undefined {
  const alias = config.vite?.resolve?.alias;
  if (!Array.isArray(alias)) return undefined;
  return (alias as AliasEntry[]).find(
    (a) => a.find instanceof RegExp && a.find.test('react-compiler-runtime')
  );
}

describe('react-compiler-runtime alias', () => {
  it('sends the bare polyfill specifier to react/compiler-runtime', () => {
    const entry = compilerRuntimeAlias();
    expect(entry?.replacement).toBe('react/compiler-runtime');
  });

  it('matches only the bare specifier, never a deep path or a lookalike (control)', () => {
    const find = compilerRuntimeAlias()?.find as RegExp;
    expect(find.test('react-compiler-runtime/dist/index.js')).toBe(false);
    expect(find.test('my-react-compiler-runtime')).toBe(false);
  });

  it('is behaviour-preserving: the polyfill on this React already returns React’s own c', () => {
    const react = require('react') as { __COMPILER_RUNTIME?: { c?: unknown } };
    // Resolved the way Video.js loads it: from @videojs/react, the listed dependency that pulls the polyfill in.
    const fromVideojs = createRequire(require.resolve('@videojs/react'));
    const polyfill = fromVideojs('react-compiler-runtime') as { c: unknown };
    expect(typeof react.__COMPILER_RUNTIME?.c).toBe('function');
    expect(polyfill.c).toBe(react.__COMPILER_RUNTIME?.c);
  });

  it('react/compiler-runtime renders a memo-cache component under this React', () => {
    expect(renderToString(createElement(Cached))).toBe('<span>1</span>');
  });
});
