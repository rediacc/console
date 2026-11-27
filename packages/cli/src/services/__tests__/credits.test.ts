import { describe, expect, it } from 'vitest';
import { loadCreditsData, renderCredits, renderCreditsJson } from '../core/credits.js';

describe('credits inventory', () => {
  it('prints the exact running Node version on the runtime row', () => {
    const data = loadCreditsData();
    const runtime = data.components.find((c) => c.kind === 'runtime');
    expect(runtime?.version).toBe(process.version);
    const json = JSON.parse(renderCreditsJson(data)) as typeof data;
    expect(json.components.find((c) => c.kind === 'runtime')?.version).toBe(process.version);
    expect(renderCredits(data)).toContain(`Node.js ${process.version}`);
  });

  it('prints mirror URLs without a planned marker', () => {
    const text = renderCredits(loadCreditsData());
    expect(text).toContain('Mirror:   https://releases.rediacc.com/third-party-src/');
    expect(text).not.toContain('(planned)');
    expect(text).not.toContain('plannedMirror');
  });

  it('pins a source sha256 on every embedded binary and attributes the static libraries', () => {
    const { components } = loadCreditsData();
    const embedded = components.filter((c) => c.kind === 'embedded-binary');
    expect(embedded.length).toBeGreaterThan(0);
    for (const c of embedded) expect(c.sourceSha256).toMatch(/^[0-9a-f]{64}$/);
    const libs = components.filter((c) => c.kind === 'static-library').map((c) => c.name);
    expect(libs).toEqual(expect.arrayContaining(['glibc', 'zstd', 'OpenSSL', 'zlib']));
  });
});
