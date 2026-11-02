/**
 * The `signed-release` case of `npm run pins -- --selftest` (agent/plans/PLAN-cli-tofu-toolchain.md
 * T1 and T2), offline over the RECORDED files of scripts/pins/data/opentofu:
 *
 *   - scripts/pins/signed-release.ts's own controls and their mutants (a tampered SHA256SUMS,
 *     another workflow identity, cosign absent or refusing, an API digest that disagrees);
 *   - the toolchain driver's plan for cli-tool:opentofu over a temporary copy of the pin files,
 *     with the release answered from the recorded files and cosign from a stand-in: the valid
 *     files plan every sha256 site from the signed SHA256SUMS and record the three files, and a
 *     SHA256SUMS changed by one byte refuses the plan whole;
 *   - the generated pin file is byte-equal to its template (scripts/pins/opentofu-pin.ts).
 *
 * No network: an upstream URL the stub does not hold fails the case rather than being fetched.
 */
import type { ControlCase } from '../lib/controls.js';
import { leafCurrent, PlanRefused } from '../lib/pins/driver.js';
import { createToolchainDriver } from '../lib/pins/drivers/toolchain.js';
import {
  ctxOf,
  entryOf,
  makeTree,
  removeRoots,
  stubUpstream,
} from '../lib/pins/drivers/toolchain-fixture.js';
import { gh } from '../lib/pins/drivers/toolchain-upstream.js';
import { REPO_ROOT } from '../lib/repo-root.js';
import { assetOf, driftOf, GENERATED_REL, PIN_ID, PLATFORMS } from './opentofu-pin.js';
import {
  type CosignRunner,
  EVIDENCE_FILES,
  parseSums,
  readEvidence,
  type SignedFiles,
  signedReleaseCases,
  signedReleaseOf,
  tamper,
} from './signed-release.js';

const okCosign: CosignRunner = () => ({ status: 0, out: 'Verified OK', missing: false });

async function driverCases(): Promise<ControlCase[]> {
  const spec = signedReleaseOf(PIN_ID);
  const files = spec && readEvidence(REPO_ROOT, spec);
  if (!spec || !files) return [{ name: `${PIN_ID}: the recorded files exist`, ok: false }];
  const evidence = Object.values(EVIDENCE_FILES).map((n) => `${spec.evidence}/${n}`);
  const entry = entryOf(PIN_ID);
  const plan = async (f: SignedFiles) => {
    const root = makeTree([GENERATED_REL, ...evidence], {}, []);
    const ctx = ctxOf(root);
    const version = leafCurrent(entry, ctx) ?? '';
    const url = `${spec.base.replaceAll('{version}', version)}/${spec.sums.replaceAll('{version}', version)}`;
    const up = stubUpstream({
      [gh('/repos/opentofu/opentofu/releases?per_page=100')]: [
        { tag_name: `v${version}`, published_at: '2026-01-01T00:00:00Z', assets: [] },
      ],
      [url]: f.sums,
      [`${url}.sig`]: f.sig,
      [`${url}.pem`]: f.pem,
    });
    const driver = createToolchainDriver(up, null, okCosign);
    try {
      return { version, p: await driver.plan(entry, { version, publishedMs: 0 }, ctx), why: '' };
    } catch (err) {
      if (!(err instanceof PlanRefused)) throw err;
      return { version, p: null, why: err.message };
    }
  };
  const valid = await plan(files);
  const tampered = await plan({ ...files, sums: tamper(files.sums) });
  const listed = parseSums(files.sums);
  const gen = valid.p?.writes.find((w) => w.file === GENERATED_REL)?.after ?? '';
  const recorded = evidence.every((e) => valid.p?.writes.some((w) => w.file === e));
  const everyHash = PLATFORMS.every((p) => {
    const d = listed.get(assetOf(valid.version, p));
    return d !== undefined && gen.includes(`'${p}': {`) && gen.includes(`sha256: '${d}'`);
  });
  return [
    {
      name: `${PIN_ID}: the driver plans all ${PLATFORMS.length} sha256 sites from the signed SHA256SUMS and records its three files`,
      ok: valid.p !== null && everyHash && recorded,
      detail: valid.why || `everyHash=${everyHash} recorded=${recorded}`,
    },
    {
      name: `${PIN_ID}: the driver refuses the whole plan when the SHA256SUMS differs from the signed one by one byte`,
      ok: tampered.p === null && /did not verify/.test(tampered.why),
      detail: tampered.p ? 'planned' : tampered.why,
    },
  ];
}

export async function signedReleaseSelftest(): Promise<ControlCase[]> {
  try {
    const drift = driftOf();
    return [
      ...(await signedReleaseCases()),
      ...(await driverCases()),
      {
        name: `${PIN_ID}: ${GENERATED_REL} is byte-equal to its template`,
        ok: drift === null,
        detail: drift ?? '',
      },
    ];
  } finally {
    removeRoots();
  }
}
