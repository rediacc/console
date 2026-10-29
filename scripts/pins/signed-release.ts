/**
 * Signed release checksums: a pin whose upstream signs its SHA256SUMS with a cosign keyless
 * signature takes its sha256 values from that file only after the signature verified
 * (agent/plans/PLAN-cli-tofu-toolchain.md T2).
 *
 * WHY. A digest read from the GitHub API, or from a SHA256SUMS fetched beside the assets, is only
 * as trustworthy as the account that uploaded it: whoever can replace an asset can replace its
 * checksum line too. The signature moves the trust to the release workflow's OIDC identity, which
 * an uploaded file cannot forge. `rdc tools install tofu` ships these checksums inside the CLI and
 * checks every download against them, so a bump is the one moment the chain can be verified.
 *
 * THE CHECKS, in order, and a bump is refused at the first that fails:
 *   1. identity   the Fulcio certificate's SAN URI is the release workflow of the version's line
 *                 (`.../release.yml@refs/heads/v1.13`), and its OIDC issuer extension
 *                 (1.3.6.1.4.1.57264.1.8, else the legacy .1.1) is the GitHub Actions issuer
 *   2. signature  the signature verifies over the SHA256SUMS bytes under the certificate's key
 *                 (node:crypto, offline). A tampered SUMS stops here.
 *   3. cosign     `cosign verify-blob` with the same identity and issuer: the chain to the
 *                 Fulcio root, the Rekor transparency-log entry and the signing time inside the
 *                 certificate's ten-minute window, none of which this file reimplements.
 *                 cosign is not a dependency of this repo, so it is called when present
 *                 (PINS_COSIGN names a binary, else `cosign` on PATH) and its ABSENCE REFUSES
 *                 THE BUMP: an unverifiable chain is never folded into a pass.
 *   4. digests    SHA256SUMS parses, names every asset a site needs, and agrees with every
 *                 digest the release API published for the same asset.
 * Checks 1 and 2 run offline over the recorded files. Check 4 needs the API digests, so only a bump
 * (verifySignedRelease) runs it; the selftest drives it with fixtures.
 *
 * THE RECORD. The verified SHA256SUMS, its signature and its certificate are written under the
 * spec's `evidence` directory, byte for byte as published. The pin's sha256 sites name that
 * SHA256SUMS as a second site of each role, so check:ci-pin-registry holds the shipped
 * checksums equal to the signed file: a hand-edited checksum disagrees with it and goes red, and
 * an edit of both copies no longer verifies against the recorded signature.
 *
 * Usage:
 *   npx tsx scripts/pins/signed-release.ts --selftest      the offline controls (also run by
 *                                                          `npm run pins -- --selftest`)
 *   npx tsx scripts/pins/signed-release.ts --verify-record <id>
 *                                                          checks 1 and 2 over the recorded
 *                                                          files, then 3; a missing cosign
 *                                                          exits 1, it does not skip check 3
 */
import { spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { WK_GH_ORIGIN } from '../../packages/shared/src/config/well-known.generated.js';
import { type ControlCase, summarizeControls } from '../lib/controls.js';
import { isEntryPoint } from '../lib/entry-point.js';
import { PlanRefused } from '../lib/pins/driver.js';
import type { Upstream } from '../lib/pins/drivers/toolchain-upstream.js';
import { REPO_ROOT } from '../lib/repo-root.js';

/** The OIDC issuer of a GitHub Actions workflow identity token. */
export const GITHUB_ACTIONS_ISSUER = 'https://token.actions.githubusercontent.com';

export interface SignedRelease {
  /** The checksum file's release asset name, `{version}` substituted. */
  sums: string;
  /** The URL directory the release assets download from, `{version}` substituted. */
  base: string;
  /** The certificate SAN the release workflow signs with, for one version. */
  identity(version: string): string;
  issuer: string;
  /** Where the verified checksum file, signature and certificate are recorded, relative to the console root. */
  evidence: string;
}

/** `major.minor` of a version: OpenTofu cuts each line's releases from its `v<major>.<minor>` branch. */
const lineOf = (version: string): string => version.split('.').slice(0, 2).join('.');

/** The pins whose sha256 values come from a cosign-signed checksum file, by registry id. */
export const SIGNED_RELEASES: Readonly<Record<string, SignedRelease>> = {
  'cli-tool:opentofu': {
    sums: 'tofu_{version}_SHA256SUMS',
    base: `${WK_GH_ORIGIN}/opentofu/opentofu/releases/download/v{version}`,
    identity: (v) =>
      `${WK_GH_ORIGIN}/opentofu/opentofu/.github/workflows/release.yml@refs/heads/v${lineOf(v)}`,
    issuer: GITHUB_ACTIONS_ISSUER,
    evidence: 'scripts/pins/data/opentofu',
  },
};

export const signedReleaseOf = (id: string): SignedRelease | null => SIGNED_RELEASES[id] ?? null;

/** The recorded files, by the fixed names the evidence directory holds them under. */
export const EVIDENCE_FILES = {
  sums: 'SHA256SUMS',
  sig: 'SHA256SUMS.sig',
  pem: 'SHA256SUMS.pem',
} as const;

/** Selftest mutants: each disables one check, and the selftest proves a case goes red. */
export const SIGNED_MUTANTS = [
  'no-signature-check',
  'no-identity-check',
  'cosign-optional',
  'no-api-crosscheck',
] as const;
export type SignedMutant = (typeof SIGNED_MUTANTS)[number];

// ---- cosign ---------------------------------------------------------------------------------

export interface CosignRun {
  /** Null when the binary could not be started. */
  status: number | null;
  out: string;
  /** The binary does not exist (ENOENT): the check could not run. */
  missing: boolean;
}
export type CosignRunner = (args: string[]) => CosignRun;

/** The cosign binary: PINS_COSIGN when set, else `cosign` on PATH. */
export const cosignBinary = (env: NodeJS.ProcessEnv = process.env): string =>
  env.PINS_COSIGN && env.PINS_COSIGN !== '' ? env.PINS_COSIGN : 'cosign';

export function systemCosign(env: NodeJS.ProcessEnv = process.env): CosignRunner {
  return (args) => {
    const r = spawnSync(cosignBinary(env), args, { encoding: 'utf8', timeout: 180_000 });
    const err = r.error as NodeJS.ErrnoException | undefined;
    return {
      status: r.status,
      out: `${r.stdout ?? ''}${r.stderr ?? ''}${err ? `${err.message}\n` : ''}`.trim(),
      missing: err?.code === 'ENOENT',
    };
  };
}

/** The install line a missing-cosign refusal prints; the module path is the one this file was proven with. */
export const COSIGN_FIX =
  'install cosign (sigstore) and re-run, or point PINS_COSIGN at a cosign binary; a Go toolchain builds one with ' +
  `\`GOBIN=<dir> go install ${new URL(WK_GH_ORIGIN).host}/sigstore/cosign/v2/cmd/cosign@v2.6.5\` (Go proxy plus sumdb verified)`;

// ---- certificate reading --------------------------------------------------------------------

/** The DER bytes of an OID, for the Fulcio extensions this file reads. */
function oidDer(oid: string): Buffer {
  const parts = oid.split('.').map(Number);
  const out = [40 * parts[0] + parts[1]];
  for (const n of parts.slice(2)) {
    const b: number[] = [n & 0x7f];
    for (let v = n >>> 7; v > 0; v >>>= 7) b.unshift((v & 0x7f) | 0x80);
    out.push(...b);
  }
  return Buffer.from([0x06, out.length, ...out]);
}

/** One DER TLV at `at`: its tag, the start of its contents and their length. */
function tlv(der: Buffer, at: number): { tag: number; start: number; len: number } | null {
  if (at + 2 > der.length) return null;
  const tag = der[at];
  let len = der[at + 1];
  let start = at + 2;
  if (len & 0x80) {
    const n = len & 0x7f;
    if (n === 0 || n > 4 || start + n > der.length) return null;
    len = 0;
    for (let i = 0; i < n; i++) len = len * 256 + der[start + i];
    start += n;
  }
  return start + len > der.length ? null : { tag, start, len };
}

/**
 * The text of a certificate extension: the OCTET STRING after the OID (skipping a `critical`
 * BOOLEAN), read as a DER UTF8String when it is one (Fulcio's 1.3.6.1.4.1.57264.1.8 onward), else
 * as raw text (the deprecated 1.3.6.1.4.1.57264.1.1). Null when the certificate has no such extension.
 */
export function extensionText(der: Buffer, oid: string): string | null {
  const at = der.indexOf(oidDer(oid));
  if (at < 0) return null;
  let next = tlv(der, at);
  if (!next) return null;
  let pos = next.start + next.len;
  next = tlv(der, pos);
  if (next?.tag === 0x01) {
    pos = next.start + next.len;
    next = tlv(der, pos);
  }
  if (next?.tag !== 0x04) return null;
  const inner = der.subarray(next.start, next.start + next.len);
  const str = tlv(inner, 0);
  if (str?.tag === 0x0c && str.start + str.len === inner.length)
    return inner.subarray(str.start).toString('utf8');
  return inner.toString('utf8');
}

const OID_ISSUER_V2 = '1.3.6.1.4.1.57264.1.8';
const OID_ISSUER_V1 = '1.3.6.1.4.1.57264.1.1';

/** A goreleaser-style `.pem` asset is the PEM base64-encoded once more; a plain PEM is accepted too. */
export function certificateOf(pem: string): crypto.X509Certificate {
  const t = pem.trim();
  const text = t.startsWith('-----BEGIN') ? t : Buffer.from(t, 'base64').toString('utf8');
  return new crypto.X509Certificate(text);
}

const sanUris = (cert: crypto.X509Certificate): string[] =>
  (cert.subjectAltName ?? '')
    .split(/,\s*/)
    .filter((x) => x.startsWith('URI:'))
    .map((x) => x.slice('URI:'.length));

// ---- the checks -----------------------------------------------------------------------------

export interface SignedFiles {
  sums: string;
  sig: string;
  pem: string;
}

/** `<64 hex>  <asset>` lines, by asset. Throws on a line of any other shape, and on an empty file. */
export function parseSums(text: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const [i, line] of text.split('\n').entries()) {
    if (line.trim() === '') continue;
    const m = /^([0-9a-f]{64}) [ *]?(\S+)$/.exec(line);
    if (!m) throw new PlanRefused(`SHA256SUMS line ${i + 1} is not "<sha256>  <asset>": ${line}`);
    if (out.has(m[2])) throw new PlanRefused(`SHA256SUMS names ${m[2]} twice`);
    out.set(m[2], m[1]);
  }
  if (out.size === 0) throw new PlanRefused('SHA256SUMS lists no asset');
  return out;
}

/**
 * Checks 1 and 2, offline: the certificate names the release workflow of `version`'s line and
 * the GitHub Actions issuer, and the signature verifies over the SUMS bytes. Returns every
 * problem; empty means both held.
 */
export function offlineProblems(
  files: SignedFiles,
  spec: SignedRelease,
  version: string,
  mutant: SignedMutant | null = null
): string[] {
  const out: string[] = [];
  let cert: crypto.X509Certificate;
  try {
    cert = certificateOf(files.pem);
  } catch (err) {
    return [`the signing certificate does not parse: ${(err as Error).message}`];
  }
  if (mutant !== 'no-identity-check') {
    const want = spec.identity(version);
    const sans = sanUris(cert);
    if (!sans.includes(want))
      out.push(`the certificate identity is ${sans.join(', ') || '(none)'}, not ${want}`);
    const issuer =
      extensionText(cert.raw, OID_ISSUER_V2) ?? extensionText(cert.raw, OID_ISSUER_V1) ?? '(none)';
    if (issuer !== spec.issuer)
      out.push(`the certificate OIDC issuer is ${issuer}, not ${spec.issuer}`);
    if (!/(^|\n)O=sigstore\.dev(\n|$)/.test(cert.issuer))
      out.push(
        `the certificate was not issued by Fulcio (issuer ${cert.issuer.replace(/\n/g, ', ')})`
      );
  }
  if (mutant !== 'no-signature-check') {
    let ok = false;
    try {
      ok = crypto.verify(
        'sha256',
        Buffer.from(files.sums, 'utf8'),
        cert.publicKey,
        Buffer.from(files.sig.trim(), 'base64')
      );
    } catch (err) {
      out.push(`the signature does not decode: ${(err as Error).message}`);
    }
    if (!ok && !out.some((p) => p.startsWith('the signature')))
      out.push(
        'the signature does not verify over SHA256SUMS: the file is not the one the release workflow signed'
      );
  }
  return out;
}

/** Check 3: cosign verify-blob over the files, written to a temporary directory and removed after. */
export function cosignProblems(
  files: SignedFiles,
  spec: SignedRelease,
  version: string,
  cosign: CosignRunner,
  mutant: SignedMutant | null = null
): string[] {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pins-cosign-'));
  try {
    const at = (n: string): string => path.join(dir, n);
    fs.writeFileSync(at(EVIDENCE_FILES.sums), files.sums);
    fs.writeFileSync(at(EVIDENCE_FILES.sig), files.sig);
    fs.writeFileSync(at(EVIDENCE_FILES.pem), files.pem);
    const r = cosign([
      'verify-blob',
      '--certificate',
      at(EVIDENCE_FILES.pem),
      '--signature',
      at(EVIDENCE_FILES.sig),
      '--certificate-identity',
      spec.identity(version),
      '--certificate-oidc-issuer',
      spec.issuer,
      at(EVIDENCE_FILES.sums),
    ]);
    if (r.missing)
      return mutant === 'cosign-optional'
        ? []
        : [
            `cosign is not installed, so the certificate chain and the transparency-log entry of ${spec.sums.replace('{version}', version)} cannot be verified; ${COSIGN_FIX}`,
          ];
    if (r.status !== 0)
      return [
        `cosign verify-blob refused the signature (rc=${r.status}): ${r.out.split('\n').slice(-3).join(' | ')}`,
      ];
    return [];
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/**
 * Check 4: the digests the SUMS file gives `assets`, each agreeing with the API digest of the
 * same asset when the API published one. Throws PlanRefused naming every gap.
 */
export function signedDigests(
  sums: string,
  assets: string[],
  apiDigests: Map<string, string>,
  mutant: SignedMutant | null = null
): Map<string, string> {
  const listed = parseSums(sums);
  const problems: string[] = [];
  const out = new Map<string, string>();
  for (const a of assets) {
    const d = listed.get(a);
    if (!d) {
      problems.push(`SHA256SUMS lists no ${a}`);
      continue;
    }
    const api = apiDigests.get(a);
    if (api !== undefined && api !== d && mutant !== 'no-api-crosscheck')
      problems.push(`${a}: SHA256SUMS says ${d}, the release API says ${api}`);
    out.set(a, d);
  }
  if (problems.length > 0) throw new PlanRefused(problems.join('; '));
  return out;
}

export interface VerifiedRelease {
  digests: Map<string, string>;
  files: SignedFiles;
}

/**
 * Fetch `version`'s checksum file, signature and certificate through `up`, run the four checks,
 * and answer the digests of `assets`. Any failure is a PlanRefused naming every problem found.
 */
export async function verifySignedRelease(
  id: string,
  spec: SignedRelease,
  version: string,
  assets: string[],
  apiDigests: Map<string, string>,
  up: Upstream,
  cosign: CosignRunner,
  mutant: SignedMutant | null = null
): Promise<VerifiedRelease> {
  const sub = (s: string): string => s.replaceAll('{version}', version);
  const url = `${sub(spec.base)}/${sub(spec.sums)}`;
  const files: SignedFiles = {
    sums: await up.text(url, id),
    sig: await up.text(`${url}.sig`, id),
    pem: await up.text(`${url}.pem`, id),
  };
  const problems = offlineProblems(files, spec, version, mutant);
  // cosign runs only over files whose identity and signature already hold: its refusal adds nothing then.
  if (problems.length === 0) problems.push(...cosignProblems(files, spec, version, cosign, mutant));
  if (problems.length > 0)
    throw new PlanRefused(
      `${id} ${version}: the signed ${sub(spec.sums)} did not verify, so no checksum of this release is taken:\n  - ${problems.join('\n  - ')}`
    );
  return { digests: signedDigests(files.sums, assets, apiDigests, mutant), files };
}

/** The recorded files of `spec`, read from `root`; null when any is absent. */
export function readEvidence(root: string, spec: SignedRelease): SignedFiles | null {
  const read = (n: string): string | null => {
    const p = path.join(root, spec.evidence, n);
    return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null;
  };
  const sums = read(EVIDENCE_FILES.sums);
  const sig = read(EVIDENCE_FILES.sig);
  const pem = read(EVIDENCE_FILES.pem);
  return sums === null || sig === null || pem === null ? null : { sums, sig, pem };
}

/** The release version a recorded checksum file belongs to: the one version every `tofu_<v>_` asset names. */
export function versionOfSums(sums: string): string | null {
  const vs = new Set([...parseSums(sums).keys()].map((a) => /^[a-z]+_([^_]+)_/.exec(a)?.[1]));
  return vs.size === 1 ? ([...vs][0] ?? null) : null;
}

// ---- selftest -------------------------------------------------------------------------------

/** A cosign stand-in for the offline controls: it answers `rc`, or reports itself missing. */
const stubCosign =
  (rc: number | 'missing', seen: string[][] = []): CosignRunner =>
  (args) => {
    seen.push(args);
    return rc === 'missing'
      ? { status: null, out: 'spawn cosign ENOENT', missing: true }
      : { status: rc, out: rc === 0 ? 'Verified OK' : 'Error: invalid signature', missing: false };
  };

/** An upstream answering the three files of `version` from `files`, and nothing else. */
function filesUpstream(spec: SignedRelease, version: string, files: SignedFiles): Upstream {
  const url = `${spec.base.replaceAll('{version}', version)}/${spec.sums.replaceAll('{version}', version)}`;
  const map: Record<string, string> = {
    [url]: files.sums,
    [`${url}.sig`]: files.sig,
    [`${url}.pem`]: files.pem,
  };
  const text = (u: string): Promise<string> =>
    map[u] === undefined
      ? Promise.reject(new Error(`no fixture for ${u}`))
      : Promise.resolve(map[u]);
  return { text, json: async (u) => JSON.parse(await text(u)), lastModified: async () => null };
}

/** Flip one hex digit of the first checksum line: a SUMS that differs from the signed one by one byte. */
export function tamper(sums: string): string {
  const c = sums[0];
  const out = (c === 'f' ? '0' : 'f') + sums.slice(1);
  if (out === sums) throw new Error('VACUOUS control: the tamper changed no byte');
  return out;
}

async function controls(
  files: SignedFiles,
  id: string,
  spec: SignedRelease,
  version: string,
  mutant: SignedMutant | null
): Promise<ControlCase[]> {
  const listed = parseSums(files.sums);
  const assets = [...listed.keys()].filter((a) => a.endsWith('.zip')).slice(0, 3);
  const verify = (f: SignedFiles, cosign: CosignRunner, api = new Map<string, string>()) =>
    verifySignedRelease(
      id,
      spec,
      version,
      assets,
      api,
      filesUpstream(spec, version, f),
      cosign,
      mutant
    ).then(
      (r) => ({ ok: true as const, r, why: '' }),
      (e: Error) => ({ ok: false as const, r: null, why: e.message })
    );
  const seen: string[][] = [];
  const valid = await verify(files, stubCosign(0, seen));
  const askedOnTamper: string[][] = [];
  const tampered = await verify(
    { ...files, sums: tamper(files.sums) },
    stubCosign(0, askedOnTamper)
  );
  // The same files judged against another release line's workflow identity.
  const otherLine = await verifySignedRelease(
    id,
    { ...spec, identity: () => spec.identity('0.0.0') },
    version,
    assets,
    new Map(),
    filesUpstream(spec, version, files),
    stubCosign(0),
    mutant
  ).then(
    () => ({ ok: true, why: '' }),
    (e: Error) => ({ ok: false, why: e.message })
  );
  const noCosign = await verify(files, stubCosign('missing'));
  const cosignSays = await verify(files, stubCosign(1));
  const lying = new Map([[assets[0], tamper(listed.get(assets[0]) ?? '')]]);
  const apiDisagrees = await verify(files, stubCosign(0), lying);
  return [
    {
      name: 'the recorded SHA256SUMS, signature and certificate pass, and cosign is asked with the release identity and issuer',
      ok:
        valid.ok &&
        valid.r?.digests.size === assets.length &&
        seen.some(
          (a) =>
            a[0] === 'verify-blob' && a.includes(spec.identity(version)) && a.includes(spec.issuer)
        ),
      detail: valid.why,
    },
    {
      name: 'a SHA256SUMS changed by one byte is refused before cosign is asked, even when cosign would say yes',
      ok:
        !tampered.ok &&
        /does not verify over SHA256SUMS/.test(tampered.why) &&
        askedOnTamper.length === 0,
      detail: tampered.ok ? 'accepted' : tampered.why,
    },
    {
      name: 'a certificate of another workflow identity is refused',
      ok: !otherLine.ok && /certificate identity is/.test(otherLine.why),
      detail: otherLine.ok ? 'accepted' : otherLine.why,
    },
    {
      name: 'no cosign binary refuses the bump, naming the fix',
      ok:
        !noCosign.ok &&
        /cosign is not installed/.test(noCosign.why) &&
        noCosign.why.includes('PINS_COSIGN'),
      detail: noCosign.ok ? 'accepted' : noCosign.why,
    },
    {
      name: 'a cosign refusal (chain or transparency log) refuses the bump',
      ok: !cosignSays.ok && /cosign verify-blob refused/.test(cosignSays.why),
      detail: cosignSays.ok ? 'accepted' : cosignSays.why,
    },
    {
      name: 'a release API digest that disagrees with the signed SHA256SUMS refuses the bump',
      ok: !apiDisagrees.ok && /the release API says/.test(apiDisagrees.why),
      detail: apiDisagrees.ok ? 'accepted' : apiDisagrees.why,
    },
  ];
}

/** The pure-helper controls: both directions of the SUMS parser and the extension reader. */
function helperCases(files: SignedFiles, spec: SignedRelease): ControlCase[] {
  const cert = certificateOf(files.pem);
  const refusedParse = (t: string): boolean => {
    try {
      parseSums(t);
      return false;
    } catch {
      return true;
    }
  };
  return [
    {
      name: 'the Fulcio issuer extension reads as the GitHub Actions issuer',
      ok: extensionText(cert.raw, OID_ISSUER_V2) === spec.issuer,
      detail: String(extensionText(cert.raw, OID_ISSUER_V2)),
    },
    {
      name: 'an extension the certificate does not carry reads as null',
      ok: extensionText(cert.raw, '1.3.6.1.4.1.57264.1.999') === null,
    },
    {
      name: 'SHA256SUMS: a malformed line and an empty file are refused, a well-formed one is not',
      ok:
        refusedParse('not a checksum line\n') &&
        refusedParse('\n') &&
        !refusedParse(`${'a'.repeat(64)}  tofu_1.0.0_linux_amd64.zip\n`),
    },
  ];
}

/**
 * The offline controls over the RECORDED files of every signed pin (the live evidence directory,
 * or `root`'s), each run clean and once per mutant; a mutant that leaves every case green is red.
 */
export async function signedReleaseCases(root: string = REPO_ROOT): Promise<ControlCase[]> {
  const out: ControlCase[] = [];
  const ids = Object.keys(SIGNED_RELEASES);
  if (ids.length === 0) return [{ name: 'VACUOUS: no signed pin is declared', ok: false }];
  for (const id of ids) {
    const spec = SIGNED_RELEASES[id];
    const files = readEvidence(root, spec);
    if (files === null) {
      out.push({
        name: `${id}: the recorded files exist under ${spec.evidence}`,
        ok: false,
        detail: `run npm run pins -- bump ${id} to record them`,
      });
      continue;
    }
    const version = versionOfSums(files.sums);
    if (version === null) {
      out.push({ name: `${id}: the recorded SHA256SUMS names one release version`, ok: false });
      continue;
    }
    out.push(...helperCases(files, spec).map((c) => ({ ...c, name: `${id}: ${c.name}` })));
    out.push(
      ...(await controls(files, id, spec, version, null)).map((c) => ({
        ...c,
        name: `${id}: ${c.name}`,
      }))
    );
    for (const m of SIGNED_MUTANTS) {
      const red = (await controls(files, id, spec, version, m)).filter((c) => !c.ok);
      out.push({
        name: `${id}: MUTANT ${m} turns a signed-release case red`,
        ok: red.length > 0,
        detail: 'every case stayed green with the check disabled, so no case tests it',
      });
    }
  }
  return out;
}

async function main(argv: string[]): Promise<number> {
  if (argv[0] === '--selftest') return summarizeControls(await signedReleaseCases());
  if (argv[0] === '--verify-record' && argv[1]) {
    const spec = signedReleaseOf(argv[1]);
    if (!spec) {
      console.error(
        `signed-release: ${argv[1]} is not a signed pin (${Object.keys(SIGNED_RELEASES).join(', ')})`
      );
      return 2;
    }
    const files = readEvidence(REPO_ROOT, spec);
    const version = files && versionOfSums(files.sums);
    if (!files || !version) {
      console.error(`signed-release: no readable record under ${spec.evidence}`);
      return 1;
    }
    const problems = offlineProblems(files, spec, version);
    if (problems.length === 0)
      problems.push(...cosignProblems(files, spec, version, systemCosign()));
    if (problems.length > 0) {
      console.error(
        `signed-release: ${argv[1]} ${version} record does not verify:\n  - ${problems.join('\n  - ')}`
      );
      return 1;
    }
    const n = parseSums(files.sums).size;
    console.log(
      `signed-release: ${argv[1]} ${version}: ${n} checksum(s) signed by ${spec.identity(version)}, verified offline and by cosign`
    );
    return 0;
  }
  console.error('usage: signed-release.ts --selftest | --verify-record <id>');
  return 2;
}

if (isEntryPoint(import.meta.filename)) process.exit(await main(process.argv.slice(2)));
