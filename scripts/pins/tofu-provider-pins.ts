/**
 * The OpenTofu provider pins: one exact version per provider in
 * packages/cli/src/services/tofu/provider-registry.json, and the `.terraform.lock.hcl` block
 * `tofu providers lock` writes for it, shipped inside rdc as
 * packages/cli/src/services/tofu/provider-pins.generated.ts (agent/plans/PLAN-cli-tofu-toolchain.md T6).
 *
 * WHY A LOCK BLOCK. rdc writes the blocks into each machine's work dir before `tofu init`, and
 * init then refuses any provider package whose h1:/zh: hash the block does not list, whether it
 * came from the registry or from the shared plugin cache (TF_PLUGIN_CACHE_DIR).
 *
 * THE RECORD. scripts/pins/data/tofu-providers/providers.lock.hcl holds the blocks exactly as
 * `tofu providers lock` wrote them (one run per provider, so a provider that publishes no build
 * for a platform still locks the others). `tofu providers lock` verifies each provider's signed
 * SHA256SUMS against the registry's signing key before it writes a zh: hash, and computes each
 * h1: hash from the package it downloaded. The .ci/config/pins.json leaf
 * `cli-tool:tofu-providers` names every block twice (the record and the generated file) and every
 * version twice more (provider-registry.json and the record), so `npm run pins -- verify` and
 * check:ci-pin-registry are red when one copy of a hash or a version moves alone.
 *
 * Usage:
 *   npx tsx scripts/pins/tofu-provider-pins.ts --check     the generated file equals render(record),
 *                                                          and provider-registry.json carries the
 *                                                          recorded versions
 *   npx tsx scripts/pins/tofu-provider-pins.ts --write     render the generated file from the record
 *   npx tsx scripts/pins/tofu-provider-pins.ts --lock [--only <ns/name>]... [--set <ns/name>=<x.y.z>]...
 *                                                          re-resolve each provider to its newest
 *                                                          release inside its current major line that
 *                                                          the release-age window has cleared, lock
 *                                                          it, and rewrite the record, the registry
 *                                                          versions and the generated file (network)
 *   npx tsx scripts/pins/tofu-provider-pins.ts --sites     print the pins.json leaf for the record
 */
import { execFile } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { OPENTOFU_PIN } from '../../packages/cli/src/services/tools/opentofu-pin.generated.js';
import { isEntryPoint } from '../lib/entry-point.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from '../lib/release-age.js';
import { REPO_ROOT } from '../lib/repo-root.js';

export const PIN_ID = 'cli-tool:tofu-providers';
export const REGISTRY_REL = 'packages/cli/src/services/tofu/provider-registry.json';
export const RECORD_REL = 'scripts/pins/data/tofu-providers/providers.lock.hcl';
export const GENERATED_REL = 'packages/cli/src/services/tofu/provider-pins.generated.ts';

/** The registry host tofu resolves an unqualified provider source against. */
export const REGISTRY_HOST = 'registry.opentofu.org';
const REGISTRY_API = `https://${REGISTRY_HOST}/v1/providers`;
const DOCS_API = 'https://api.opentofu.org/registry/docs/providers';

/** The platforms rdc runs tofu on, in the `<os>_<arch>` form tofu names them. */
export const PLATFORMS = [
  'linux_amd64',
  'linux_arm64',
  'darwin_amd64',
  'darwin_arm64',
  'windows_amd64',
  'windows_arm64',
] as const;

const RECORD_HEADER = [
  '# This file is maintained automatically by "tofu init".',
  '# Manual edits may be lost in future updates.',
  '',
].join('\n');

export interface LockBlock {
  /** The registry source as provider-registry.json keys it (`IBM-Cloud/ibm`). */
  source: string;
  version: string;
  /** The block, from `provider "` through its closing brace, as tofu wrote it. */
  text: string;
}

/** The lower-cased `<ns>/<name>` tofu writes in the provider address. */
export const addressOf = (source: string): string => `${REGISTRY_HOST}/${source.toLowerCase()}`;

/** A registry source as a pins role suffix (`IBM-Cloud/ibm` -> `ibm-cloud-ibm`). */
export const roleKey = (source: string): string => source.toLowerCase().replace(/\//g, '-');

const escapeRe = (s: string): string => s.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');

/** Every provider block of a lock file, keyed by its lower-cased `<ns>/<name>`. */
export function parseLock(text: string): Map<string, { version: string; text: string }> {
  const out = new Map<string, { version: string; text: string }>();
  const re = new RegExp(
    `^provider "${escapeRe(REGISTRY_HOST)}/([^"]+)" \\{\\n {2}version {5}= "([^"]+)"\\n[^}]*\\n\\}$`,
    'gm'
  );
  for (const m of text.matchAll(re)) out.set(m[1], { version: m[2], text: m[0] });
  return out;
}

/** The providers provider-registry.json pins, as `[source, version]`; `kvm` carries none. */
export function registryVersions(root: string = REPO_ROOT): [string, string | undefined][] {
  const reg = JSON.parse(fs.readFileSync(path.join(root, REGISTRY_REL), 'utf8')) as Record<
    string,
    { version?: string }
  >;
  return Object.entries(reg)
    .filter(([source]) => source.includes('/'))
    .map(([source, e]) => [source, e.version]);
}

/** The record's blocks in registry order; throws naming the first provider it lacks. */
export function readRecord(root: string = REPO_ROOT): LockBlock[] {
  const blocks = parseLock(fs.readFileSync(path.join(root, RECORD_REL), 'utf8'));
  return registryVersions(root).map(([source]) => {
    const b = blocks.get(source.toLowerCase());
    if (!b) throw new Error(`${RECORD_REL} has no block for ${source}`);
    return { source, version: b.version, text: b.text };
  });
}

/** The generated file, whole, for `blocks`. */
export function render(blocks: LockBlock[]): string {
  const rows = blocks.flatMap((b) => [
    `  '${b.source}': {`,
    `    version: '${b.version}',`,
    `    lock: \`${b.text}\`,`,
    '  },',
  ]);
  return [
    `// AUTO-GENERATED by npx tsx scripts/pins/tofu-provider-pins.ts - DO NOT EDIT`,
    `// Source: ${RECORD_REL}, the blocks \`tofu providers lock\` wrote for each provider at its exact`,
    '// version in provider-registry.json. rdc writes the blocks of the providers a config requires into',
    '// the work dir as .terraform.lock.hcl before `tofu init`, which then refuses any package whose hash',
    `// is not listed. .ci/config/pins.json entry ${PIN_ID} holds each block equal to the record.`,
    '',
    'export interface ProviderPin {',
    '  /** The exact version the provider is pinned at. */',
    '  version: string;',
    '  /** Its `.terraform.lock.hcl` block. */',
    '  lock: string;',
    '}',
    '',
    `export const PROVIDER_LOCK_HOST = '${REGISTRY_HOST}';`,
    '',
    'export const PROVIDER_PINS: Readonly<Record<string, ProviderPin>> = {',
    ...rows,
    '};',
    '',
  ].join('\n');
}

/** Why the tree is not consistent with the record; empty when it is. */
export function problems(root: string = REPO_ROOT): string[] {
  const out: string[] = [];
  let blocks: LockBlock[];
  try {
    blocks = readRecord(root);
  } catch (err) {
    return [(err as Error).message];
  }
  const versions = new Map(registryVersions(root));
  for (const b of blocks)
    if (versions.get(b.source) !== b.version)
      out.push(
        `${REGISTRY_REL} pins ${b.source} at ${JSON.stringify(versions.get(b.source))}, the record at ${b.version}`
      );
  const abs = path.join(root, GENERATED_REL);
  const text = fs.existsSync(abs) ? fs.readFileSync(abs, 'utf8') : null;
  if (text === null) out.push(`${GENERATED_REL} does not exist`);
  else if (text !== render(blocks)) {
    const a = text.split('\n');
    const w = render(blocks).split('\n');
    const i = a.findIndex((l, n) => l !== w[n]);
    out.push(
      `${GENERATED_REL} line ${i + 1} differs from render(record): ${JSON.stringify(a[i])} vs ${JSON.stringify(w[i])}`
    );
  }
  return out;
}

/** The pins.json leaf naming every block and version of the record. */
export function leafFor(blocks: LockBlock[]): Record<string, unknown> {
  const sites = blocks.flatMap((b) => {
    const k = roleKey(b.source);
    const block = `(?<value>provider "${escapeRe(addressOf(b.source))}" \\{\\n[^}]*\\n\\})`;
    return [
      {
        repo: '.',
        file: REGISTRY_REL,
        role: `version:${k}`,
        json: `/${b.source.replace(/~/g, '~0').replace(/\//g, '~1')}/version`,
        label: `provider-registry.json ${b.source} version`,
        expect: 1,
      },
      {
        repo: '.',
        file: RECORD_REL,
        role: `version:${k}`,
        match: `^provider "${escapeRe(addressOf(b.source))}" \\{\\n {2}version {5}= "(?<value>[^"]+)"$`,
        label: `the recorded lock block of ${b.source}, version`,
        expect: 1,
      },
      {
        repo: '.',
        file: RECORD_REL,
        role: `lock:${k}`,
        match: `^${block}$`,
        label: `the recorded lock block of ${b.source}`,
        expect: 1,
      },
      {
        repo: '.',
        file: GENERATED_REL,
        role: `lock:${k}`,
        match: `^ {4}lock: \`${block}\`,$`,
        label: `PROVIDER_PINS['${b.source}'].lock`,
        expect: 1,
      },
    ];
  });
  return {
    id: PIN_ID,
    kind: 'leaf',
    name: 'OpenTofu providers',
    driver: 'toolchain',
    source: {
      type: 'none',
      reason:
        'BLOCKER: this one leaf carries an exact version for each of the providers in provider-registry.json, and a pins driver compares a single version per leaf; npx tsx scripts/pins/tofu-provider-pins.ts --lock moves each provider to its newest release-age-cleared release inside its major line and rewrites every site',
    },
    safety: { mode: 'release-age', major: 'assisted' },
    holds: [],
    gates: ['check:ci-pin-registry'],
    sites,
    derive: [],
    literals: [],
  };
}

// ---- --lock (network) ---------------------------------------------------------------------

const major = (v: string): string => v.split('.')[0];
const cmp = (a: string, b: string): number => {
  const x = a.split('.').map(Number);
  const y = b.split('.').map(Number);
  for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] - y[i];
  return 0;
};

async function getJson(url: string): Promise<unknown> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

/** The newest release of `source` in `current`'s major line that the release-age window cleared. */
async function newestCleared(source: string, current: string): Promise<string> {
  const [ns, name] = source.toLowerCase().split('/');
  const doc = (await getJson(`${DOCS_API}/${ns}/${name}/index.json`)) as {
    versions?: Array<{ id?: string; published?: string }>;
  };
  const window = getMinReleaseAgeMs();
  const now = Date.now();
  const cleared = (doc.versions ?? [])
    .map((v) => ({ v: String(v.id ?? '').replace(/^v/, ''), at: Date.parse(String(v.published)) }))
    .filter(
      (r) =>
        /^\d+\.\d+\.\d+$/.test(r.v) &&
        major(r.v) === major(current) &&
        !Number.isNaN(r.at) &&
        !isWithinFreshnessWindow(r.at, now, window)
    )
    .sort((a, b) => cmp(b.v, a.v));
  if (!cleared[0])
    throw new Error(`${source}: no release-age-cleared ${major(current)}.x release is listed`);
  return cleared[0].v;
}

/** The platforms of PLATFORMS that `source@version` publishes a build for. */
async function platformsOf(source: string, version: string): Promise<string[]> {
  const [ns, name] = source.toLowerCase().split('/');
  const doc = (await getJson(`${REGISTRY_API}/${ns}/${name}/versions`)) as {
    versions?: Array<{ version?: string; platforms?: Array<{ os?: string; arch?: string }> }>;
  };
  const entry = (doc.versions ?? []).find((v) => v.version === version);
  if (!entry) throw new Error(`${source}: ${REGISTRY_HOST} lists no ${version}`);
  const have = new Set((entry.platforms ?? []).map((p) => `${p.os}_${p.arch}`));
  return PLATFORMS.filter((p) => have.has(p));
}

function run(bin: string, args: string[], cwd: string): Promise<void> {
  return new Promise((resolve, reject) => {
    execFile(bin, args, { cwd, maxBuffer: 64 * 1024 * 1024, timeout: 3_600_000 }, (err, _o, e) =>
      err
        ? reject(new Error(`${bin} ${args.join(' ')} in ${cwd}: ${err.message}\n${e}`))
        : resolve()
    );
  });
}

function tofuBinary(): string {
  if (process.env.REDIACC_TOFU) return process.env.REDIACC_TOFU;
  const state = process.env.XDG_STATE_HOME ?? path.join(os.homedir(), '.local', 'state');
  return path.join(state, 'rediacc', 'tools', 'opentofu', OPENTOFU_PIN.version, 'tofu');
}

/** Lock `source` at `version` on every platform it publishes, in a scratch dir; its block. */
async function lockOne(bin: string, scratch: string, source: string, version: string) {
  const dir = path.join(scratch, roleKey(source));
  fs.mkdirSync(dir, { recursive: true });
  const name = source.split('/')[1].toLowerCase();
  fs.writeFileSync(
    path.join(dir, 'main.tf.json'),
    JSON.stringify({ terraform: { required_providers: { [name]: { source, version } } } })
  );
  const plats = await platformsOf(source, version);
  await run(bin, ['providers', 'lock', ...plats.map((p) => `-platform=${p}`)], dir);
  const block = parseLock(fs.readFileSync(path.join(dir, '.terraform.lock.hcl'), 'utf8')).get(
    source.toLowerCase()
  );
  if (!block || block.version !== version)
    throw new Error(`${source}: tofu providers lock wrote no ${version} block`);
  fs.rmSync(dir, { recursive: true, force: true });
  return { source, version, text: block.text, plats };
}

async function lock(only: string[], set: Map<string, string>): Promise<number> {
  const bin = tofuBinary();
  if (!fs.existsSync(bin)) {
    console.error(`tofu-provider-pins: no tofu at ${bin}; run rdc tools install tofu`);
    return 1;
  }
  const regAbs = path.join(REPO_ROOT, REGISTRY_REL);
  const recAbs = path.join(REPO_ROOT, RECORD_REL);
  const existing = fs.existsSync(recAbs)
    ? parseLock(fs.readFileSync(recAbs, 'utf8'))
    : new Map<string, { version: string; text: string }>();
  const todo = registryVersions().filter(
    ([s]) => only.length === 0 || only.some((o) => o.toLowerCase() === s.toLowerCase())
  );
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'tofu-provider-pins-'));
  const results: LockBlock[] = [];
  const failures: string[] = [];
  const queue = [...todo];
  const worker = async () => {
    for (let item = queue.shift(); item; item = queue.shift()) {
      const [source, current] = item;
      try {
        const want =
          set.get(source.toLowerCase()) ??
          (await newestCleared(source, (current ?? '').replace(/^[~>=\s]+/, '')));
        const r = await lockOne(bin, scratch, source, want);
        results.push(r);
        console.log(`tofu-provider-pins: ${source} ${want} locked (${r.plats.join(', ')})`);
      } catch (err) {
        failures.push(`${source}: ${(err as Error).message}`);
      }
    }
  };
  await Promise.all(Array.from({ length: 4 }, worker));
  fs.rmSync(scratch, { recursive: true, force: true });
  if (failures.length > 0) {
    console.error(`tofu-provider-pins: nothing written:\n  - ${failures.join('\n  - ')}`);
    return 1;
  }
  for (const r of results)
    existing.set(r.source.toLowerCase(), { version: r.version, text: r.text });
  const blocks = [...existing.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  fs.mkdirSync(path.dirname(recAbs), { recursive: true });
  fs.writeFileSync(recAbs, `${RECORD_HEADER}${blocks.map(([, b]) => `${b.text}\n`).join('\n')}`);
  const reg = JSON.parse(fs.readFileSync(regAbs, 'utf8')) as Record<string, { version?: string }>;
  for (const r of results) reg[r.source].version = r.version;
  fs.writeFileSync(regAbs, `${JSON.stringify(reg, null, 2)}\n`);
  return write();
}

function write(): number {
  const blocks = readRecord();
  fs.writeFileSync(path.join(REPO_ROOT, GENERATED_REL), render(blocks));
  console.log(`tofu-provider-pins: wrote ${GENERATED_REL} (${blocks.length} providers)`);
  return 0;
}

async function main(argv: string[]): Promise<number> {
  if (argv[0] === '--check') {
    const found = problems();
    if (found.length > 0) {
      console.error(`tofu-provider-pins:\n  - ${found.join('\n  - ')}`);
      return 1;
    }
    console.log(`tofu-provider-pins: ${GENERATED_REL} and ${REGISTRY_REL} match the record`);
    return 0;
  }
  if (argv[0] === '--write') return write();
  if (argv[0] === '--sites') {
    console.log(JSON.stringify(leafFor(readRecord()), null, 2));
    return 0;
  }
  if (argv[0] === '--lock') {
    const only: string[] = [];
    const set = new Map<string, string>();
    for (let i = 1; i < argv.length; i += 2) {
      const v = argv[i + 1];
      if (argv[i] === '--only' && v) only.push(v);
      else if (argv[i] === '--set' && v?.includes('=')) {
        const [s, ver] = v.split('=');
        set.set(s.toLowerCase(), ver);
      } else {
        console.error(`tofu-provider-pins: unknown argument ${argv[i]}`);
        return 2;
      }
    }
    return lock(only, set);
  }
  console.error(
    'usage: tofu-provider-pins.ts --check | --write | --sites | --lock [--only <src>] [--set <src>=<ver>]'
  );
  return 2;
}

if (isEntryPoint(import.meta.filename)) process.exit(await main(process.argv.slice(2)));
