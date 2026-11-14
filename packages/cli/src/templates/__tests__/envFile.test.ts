import { parse } from 'yaml';
import { describe, expect, it } from 'vitest';
import { TEMPLATES } from '../embedded.generated';

type EnvFileEntry = string | { path: string; required?: boolean };

interface Compose {
  services?: Record<string, { env_file?: string | EnvFileEntry[] }>;
}

const envFileEntries = (compose: Compose): { service: string; path: string; optional: boolean }[] =>
  Object.entries(compose.services ?? {}).flatMap(([service, def]) => {
    const raw = def.env_file;
    if (raw === undefined) return [];
    const list: EnvFileEntry[] = typeof raw === 'string' ? [raw] : raw;
    return list.map((entry) =>
      typeof entry === 'string'
        ? { service, path: entry, optional: false }
        : { service, path: entry.path, optional: entry.required === false }
    );
  });

/** Body of `up() { ... }`: the templates close each function with a `}` in column 0. */
const upBody = (rediaccfile: string): string =>
  /^up\(\)\s*\{\n([\s\S]*?)^\}/m.exec(rediaccfile)?.[1] ?? '';

/** A line with its trailing comment removed: a `#` at the start or after whitespace, outside single and double quotes, starts the comment. */
const stripComment = (line: string): string =>
  // Left to right: a complete quoted string is kept whole, so a `#` inside it is never reached; the first `#` outside quotes that starts the line or follows whitespace takes the rest of the line.
  line.replace(
    /("[^"]*"|'[^']*')|(?:^|\s)#.*$/g,
    (_match, quoted: string | undefined) => quoted ?? ''
  );

/** True when a line of up(), with its comment stripped, redirects into exactly `path` (not `path.bak`). */
const createdByUp = (rediaccfile: string, path: string): boolean => {
  const escaped = path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const creator = new RegExp(`>>?\\s*["']?\\.?/?${escaped}(?![\\w.-])`);
  return upBody(rediaccfile)
    .split('\n')
    .map(stripComment)
    .some((line) => creator.test(line));
};

const shippedOrCreated = (files: Record<string, string>, path: string): boolean =>
  path in files ||
  Object.entries(files).some(([name, body]) => name === 'Rediaccfile' && createdByUp(body, path));

describe('embedded template env_file entries', () => {
  it('single-service declares secrets.env as optional', () => {
    const compose = parse(TEMPLATES['single-service'].files['docker-compose.yml']) as Compose;
    const entries = envFileEntries(compose).filter((e) => e.path === 'secrets.env');
    expect(entries.length).toBeGreaterThan(0);
    for (const e of entries) expect(e.optional, `${e.service} secrets.env`).toBe(true);
  });

  it('every env_file is optional, shipped, or created by the Rediaccfile', () => {
    let seen = 0;
    for (const [name, template] of Object.entries(TEMPLATES)) {
      const rootCompose = template.files['docker-compose.yml'];
      if (rootCompose === undefined) continue;
      for (const e of envFileEntries(parse(rootCompose) as Compose)) {
        seen += 1;
        const ok = e.optional || shippedOrCreated(template.files, e.path);
        expect(
          ok,
          `${name}/${e.service}: env_file ${e.path} is required but never shipped or created`
        ).toBe(true);
      }
    }
    expect(seen).toBeGreaterThan(0);
  });
});

describe('createdByUp', () => {
  const file = (up: string): string =>
    `#!/bin/bash\n\nup() {\n${up}\n}\n\ndown() {\n  echo x > .env\n}\n`;

  it('counts a redirect inside up()', () => {
    expect(createdByUp(file('  cat > .env <<EOF\nA=1\nEOF'), '.env')).toBe(true);
  });

  it('ignores a redirect inside a trailing comment (review ff7e55e6.1)', () => {
    expect(createdByUp(file('  cp a b # > .env'), '.env')).toBe(false);
  });

  it('counts a redirect after a # inside quotes (review ce9cdfe0.1)', () => {
    expect(createdByUp(file('  echo "key # x" > .env'), '.env')).toBe(true);
    expect(createdByUp(file("  echo 'key # x' > .env"), '.env')).toBe(true);
  });

  it('still strips a trailing comment after a quoted argument', () => {
    expect(createdByUp(file('  echo "a" # > .env'), '.env')).toBe(false);
  });

  it('ignores a comment-only mention in up()', () => {
    expect(createdByUp(file('  # writes > .env later'), '.env')).toBe(false);
  });

  it('ignores a write in another function', () => {
    expect(createdByUp(file('  true'), '.env')).toBe(false);
  });

  it('does not match a longer file name', () => {
    expect(createdByUp(file('  cp a > .env.bak'), '.env')).toBe(false);
  });
});
