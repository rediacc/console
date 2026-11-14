/**
 * The anonymous Free License Terms acceptance is stored at /state/terms/*. Its four leaves are
 * registered public on the claim that none holds a secret; this pins both halves, so a new leaf
 * on the stored record fails here until it is classified on purpose.
 */

import { describe, expect, it } from 'vitest';
import { SENSITIVITY_REGISTRY } from '../sensitivity.js';
import { StateSchema } from '../state-schema.js';

const LEAVES = ['version', 'sha256', 'acceptedAt', 'method'] as const;
const byText = (a: string, b: string) => a.localeCompare(b);

describe('/state/terms sensitivity', () => {
  it('registers exactly the stored leaves, each public', () => {
    const registered = [...SENSITIVITY_REGISTRY.keys()].filter((k) =>
      k.startsWith('/state/terms/')
    );
    expect(registered.sort(byText)).toEqual(LEAVES.map((l) => `/state/terms/${l}`).sort(byText));
    for (const key of registered) expect(SENSITIVITY_REGISTRY.get(key)?.kind).toBe('public');
  });

  it('holds no leaf beyond the four classified ones', () => {
    const terms = StateSchema.shape.terms.unwrap();
    expect(Object.keys(terms.shape).sort(byText)).toEqual([...LEAVES].sort(byText));
  });
});
