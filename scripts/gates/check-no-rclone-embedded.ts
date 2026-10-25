/**
 * check:ci-no-rclone-embedded -- the rclone payload stays out of every renet and rdc artifact.
 *
 * WHY. rclone was decommissioned completely (payload and feature; operator 2026-10-15,
 * agent/plans/PLAN-rclone-decommission.md): backups moved to the S3/R2 chunk store. The
 * payload is a go:embed asset, so nothing in the Go sources has to change for it to come
 * back: a stale embed cache restored by the build lane, a lockfile merge that resurrects
 * the component, or an asset staged by hand would ship 22 MB of rclone again and every
 * other gate would stay green (the old embed gates read the lockfile's OWN component
 * list, which is exactly the file that would carry the resurrection).
 *
 * WHAT IT READS, three tiers, each of which can fail on its own:
 *   1. the embed lockfile (private/renet/embed-assets.lock.json): any mention of the term
 *      anywhere in the text, key or value, is a finding;
 *   2. the staged embed tree (private/renet/pkg/embed/assets/**): any file whose path
 *      names the term is a finding (the asset is `rclone-linux-<arch>.zst`);
 *   3. built binaries (private/bin/renet-*, private/renet/bin/renet*, dist/cli/rdc-*,
 *      plus anything named in RCLONE_GATE_BINARIES, colon separated): a streamed byte
 *      scan for the two signatures that mean the payload is present. A go:embed asset
 *      is compressed, so its CONTENT never shows in strings; its NAME does, because the
 *      embedded file table stores `rclone-linux-<arch>.zst`. The other signature is the
 *      module path `github.com/rclone/rclone`, which appears only if rclone code is
 *      linked. A bare occurrence of the word is NOT a signature: the i18n word list and
 *      retired-storage error text legitimately spell it.
 *
 * ANTI-VACUITY. The lockfile must exist and parse with at least one component, or the
 * gate refuses (tier 1 would be reading nothing). The staged tree must hold at least one
 * asset OR the gate says so on its success line. Binaries are optional on a fresh clone
 * (printed as 0 scanned), but RCLONE_GATE_REQUIRE_BINARIES=1, set by the build lane's
 * step, turns zero scanned binaries into a failure: that step runs right after the build,
 * so an empty scan there means the glob stopped matching the build output.
 *
 * ---- gate ----
 * step: Assert no rclone payload in the embed lockfile, staged assets or built binaries
 * needs: node, submodules
 * lane: quality-go
 * selftest: true
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';
import { GREEN, NC, RED, YELLOW } from '../lib/console.js';
import { isEntryPoint } from '../lib/entry-point.js';
import { requireSubmodule, submodulePath, submoduleRoot } from '../lib/submodule-presence.js';

/** The byte signatures that mean the payload is inside a binary. */
export const BINARY_SIGNATURES = ['rclone-linux-', 'github.com/rclone/rclone'] as const;

const TERM = /rclone/i;

/** Lockfile lines that name the term, as `line N: <text>`; empty when clean. */
export function lockfileFindings(text: string): string[] {
  const out: string[] = [];
  text.split('\n').forEach((line, i) => {
    if (TERM.test(line)) out.push(`line ${i + 1}: ${line.trim().slice(0, 120)}`);
  });
  return out;
}

/** Paths (relative, as given) whose own text names the term. */
export function assetFindings(paths: string[]): string[] {
  return paths.filter((p) => TERM.test(p));
}

/**
 * Count signature occurrences across a stream of chunks, carrying the tail of each chunk
 * so a signature split across a chunk boundary is still found exactly once.
 */
export function countSignatures(chunks: Iterable<Buffer>): Map<string, number> {
  const counts = new Map<string, number>(BINARY_SIGNATURES.map((s) => [s, 0]));
  const needles = BINARY_SIGNATURES.map((s) => [s, Buffer.from(s)] as const);
  const keep = Math.max(...needles.map(([, b]) => b.length)) - 1;
  let tail: Buffer = Buffer.alloc(0);
  for (const chunk of chunks) {
    const buf = Buffer.concat([tail, chunk]);
    for (const [name, needle] of needles) {
      // Occurrences wholly inside `tail` were counted on the previous pass: start after them.
      const floor = Math.max(0, tail.length - needle.length + 1);
      for (let at = buf.indexOf(needle, floor); at !== -1; at = buf.indexOf(needle, at + 1)) {
        counts.set(name, (counts.get(name) ?? 0) + 1);
      }
    }
    tail = buf.subarray(Math.max(0, buf.length - keep));
  }
  return counts;
}

function* fileChunks(file: string): Generator<Buffer> {
  const fd = fs.openSync(file, 'r');
  try {
    const buf = Buffer.alloc(8 * 1024 * 1024);
    for (let n = fs.readSync(fd, buf, 0, buf.length, null); n > 0; ) {
      yield Buffer.from(buf.subarray(0, n));
      n = fs.readSync(fd, buf, 0, buf.length, null);
    }
  } finally {
    fs.closeSync(fd);
  }
}

function walk(dir: string): string[] {
  if (!fs.existsSync(dir)) return [];
  const out: string[] = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p));
    else out.push(p);
  }
  return out;
}

/** Existing files in `dir` whose basename starts with `prefix`. */
function withPrefix(dir: string, prefix: string): string[] {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((n) => n.startsWith(prefix) && !/\.(sha256|log|json)$/.test(n))
    .map((n) => path.join(dir, n))
    .filter((p) => fs.statSync(p).isFile());
}

function candidateBinaries(root: string): string[] {
  const found = [
    ...withPrefix(path.join(root, 'private/bin'), 'renet-'),
    ...withPrefix(path.join(root, 'private/renet/bin'), 'renet'),
    ...withPrefix(path.join(root, 'dist/cli'), 'rdc-'),
    ...(process.env.RCLONE_GATE_BINARIES ?? '')
      .split(':')
      .filter((p) => p !== '')
      .map((p) => path.resolve(p)),
  ];
  return [...new Set(found)].filter((p) => fs.existsSync(p));
}

function selftest(): void {
  const fail = (m: string): never => {
    console.error(`${RED}selftest FAIL: ${m}${NC}`);
    process.exit(1);
  };
  const ok = (m: string): void => console.log(`  PASS  ${m}`);

  if (lockfileFindings('{"components":{"rclone":{"version":"1.2"}}}').length !== 1)
    fail('a lockfile component named rclone was not caught');
  ok('lockfile naming the component is caught');
  if (lockfileFindings('{"components":{"zot":{"version":"2.1"},"criu":{}}}').length !== 0)
    fail('a clean lockfile was flagged');
  ok('CONTROL: a clean lockfile is not flagged');
  if (assetFindings(['a/zot-linux-amd64.zst', 'a/rclone-linux-amd64.zst']).length !== 1)
    fail('asset path scan wrong');
  ok('asset path naming the term is caught, siblings are not');

  const sig = (parts: string[]): Map<string, number> =>
    countSignatures(parts.map((p) => Buffer.from(p)));
  const planted = sig(['xxxx rclone-linux-amd64.zst yyyy']);
  if (planted.get('rclone-linux-') !== 1) fail('planted asset name not counted');
  ok('planted asset name in a binary is counted');
  const split = sig(['aaaa rclone-lin', 'ux-arm64.zst']);
  if (split.get('rclone-linux-') !== 1) fail('a signature split across chunks was missed');
  ok('signature split across a chunk boundary is counted once');
  const dup = sig(['rclone-linux-', 'rclone-linux-']);
  if (dup.get('rclone-linux-') !== 2) fail('adjacent signatures miscounted');
  ok('adjacent signatures are each counted once');
  const mod = sig(['..github.com/rclone/rclone/fs..']);
  if (mod.get('github.com/rclone/rclone') !== 1) fail('module path signature not counted');
  ok('linked module path is counted');
  const word = sig(['cluster ssh sftp rsync rclone criu', 'the retired rclone kind']);
  if ([...word.values()].some((n) => n !== 0)) fail('the bare word was counted as a payload');
  ok('CONTROL: the bare word in i18n lists and error text is not a payload signature');

  const tmp = fs.mkdtempSync(path.join(fs.realpathSync(process.env.TMPDIR ?? '/tmp'), 'rcg-'));
  try {
    const f = path.join(tmp, 'renet-linux-amd64');
    fs.writeFileSync(f, Buffer.concat([Buffer.alloc(100), Buffer.from('rclone-linux-amd64.zst')]));
    const n = countSignatures(fileChunks(f)).get('rclone-linux-');
    if (n !== 1) fail('file scan missed the plant');
    ok('file stream scan finds a planted name');
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    selftest();
    console.log('check-no-rclone-embedded: selftest ok');
    return;
  }
  const lockfile = submodulePath('private/renet/embed-assets.lock.json');
  if (!requireSubmodule('no rclone embedded', [lockfile])) return;
  const root = submoduleRoot();

  const findings: string[] = [];

  const lockText = fs.readFileSync(lockfile, 'utf-8');
  let components = 0;
  try {
    components = Object.keys(
      (JSON.parse(lockText) as { components?: Record<string, unknown> }).components ?? {}
    ).length;
  } catch (e) {
    console.error(
      `${RED}✗ ${lockfile} does not parse (${(e as Error).message}); the gate cannot read it${NC}`
    );
    process.exit(1);
  }
  if (components === 0) {
    console.error(
      `${RED}✗ the embed lockfile declares no components; the gate is not seeing the tree, so its green would mean nothing${NC}`
    );
    process.exit(1);
  }
  for (const f of lockfileFindings(lockText))
    findings.push(`embed-assets.lock.json ${f}: remove the component and every reference`);

  const assetDir = submodulePath('private/renet/pkg/embed/assets');
  const assets = walk(assetDir);
  for (const a of assetFindings(assets))
    findings.push(
      `${path.relative(root, a)}: an rclone asset is staged; delete it and rebuild the embed cache`
    );

  const binaries = candidateBinaries(root);
  if (binaries.length === 0 && process.env.RCLONE_GATE_REQUIRE_BINARIES === '1') {
    console.error(
      `${RED}✗ RCLONE_GATE_REQUIRE_BINARIES=1 but no built binary matched private/bin/renet-*, private/renet/bin/renet*, dist/cli/rdc-* or RCLONE_GATE_BINARIES; the build output moved and this scan would be empty${NC}`
    );
    process.exit(1);
  }
  for (const b of binaries) {
    const counts = countSignatures(fileChunks(b));
    for (const [sig, n] of counts) {
      if (n > 0)
        findings.push(
          `${path.relative(root, b)}: ${n} occurrence(s) of "${sig}"; an rclone payload is embedded or linked. Find which build input restored it (embed cache, lockfile, staged asset)`
        );
    }
  }

  if (findings.length > 0) {
    console.error(`${RED}✗ rclone payload present (${findings.length} finding(s)):${NC}`);
    for (const f of findings) console.error(`  - ${f}`);
    console.error(`${YELLOW}rclone is decommissioned; do not allowlist this.${NC}`);
    process.exit(1);
  }
  console.log(
    `${GREEN}✓ no rclone payload: ${components} lockfile component(s), ${assets.length} staged asset(s), ${binaries.length} built binar${binaries.length === 1 ? 'y' : 'ies'} scanned${NC}`
  );
}

if (isEntryPoint(import.meta.filename)) main();
