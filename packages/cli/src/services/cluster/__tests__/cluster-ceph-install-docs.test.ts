import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/** Each doc block must sit directly above the function it describes (8b24deb8.1): a split left installCeph's doc on cephIsBootstrapped. */
describe('cluster-ceph-install doc blocks', () => {
  const src = readFileSync(
    fileURLToPath(new URL('../cluster-ceph-install.ts', import.meta.url)),
    'utf8'
  );

  it('installCeph carries the install doc and cephIsBootstrapped the mon-check doc', () => {
    expect(src).toMatch(
      /\* Install Ceph on the cluster's(?:(?!\*\/)[\s\S])*\*\/\s*export async function installCeph\(/
    );
    expect(src).toMatch(
      /\* Reports whether a ceph mon(?:(?!\*\/)[\s\S])*\*\/\s*async function cephIsBootstrapped\(/
    );
  });
});
