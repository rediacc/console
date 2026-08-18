#!/usr/bin/env tsx
/**
 * Verify that each STAGED embedded asset is the version the lockfile CLAIMS.
 *
 * Why this exists, precisely. On 2026-08-15 the rsync pin was moved 3.4.4 ->
 * 3.5.0 in `embed-assets.lock.json` and in both Dockerfile `ARG` stages, the
 * credits were regenerated, and `./build.sh embed_assets --force` exited 0.
 * `check:ci-embed-asset-freshness` went green. `check:ci-embed-credits` went
 * green. The staged binary was still 3.4.4.
 *
 * Every embed check reads a DECLARATION against another DECLARATION: the pin
 * against upstream, the Dockerfile ARG against the lockfile, the generated
 * attribution against the lockfile. Not one of them opens the artifact. So a
 * rebuild that silently fails to update the binary passes all of them, which is
 * exactly what happened: `embed_assets` builds the image only
 * `if ! docker image inspect rediacc/renet:latest`, so `--force` re-extracted
 * from a STALE image and the ARG change could never reach it.
 *
 * This gate is the one that opens the box. It decompresses each staged asset
 * and asks the binary its own version, executing it when the asset's
 * architecture matches the host and reading its embedded strings when it does
 * not.
 *
 * CONTROL-FIRST. The comparison logic is self-tested on every run, including
 * runs where no asset is staged at all (a fresh checkout, or CI without the
 * embed cache: the `.zst` files are gitignored). A run that verified nothing
 * and reported success is the failure mode this whole gate was written about,
 * so "nothing to check" never silently means "pass": the controls still run,
 * and the skip says out loud what it did not look at.
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GREEN, NC, RED, YELLOW } from './utils/console.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');
const RENET_DIR = path.join(CONSOLE_ROOT, 'private', 'renet');
const LOCKFILE = path.join(RENET_DIR, 'embed-assets.lock.json');
const ASSETS_DIR = path.join(RENET_DIR, 'pkg', 'embed', 'assets');

interface Component {
  version?: string;
  class?: string;
  assetBase?: string;
}

// ─── The comparison, as a pure function so a control can exercise it ────────

/**
 * The forms a pinned version legitimately takes inside a binary.
 *
 * Measured against the real assets rather than guessed:
 *   rsync 3.5.0   -> "rsync  version 3.5.0"
 *   criu  4.2.1   -> "Version: 4.2.1"
 *   zot 2.1.2     -> "zot v2.1.2"           (v-prefixed)
 *   zot   2.1.20  -> "commit":"v2.1.20-0-g…" (v-prefixed, with a suffix)
 *   k3s   v1.36.3+k3s1 -> "k3s version v1.36.3+k3s1"  (pin already v-prefixed)
 */
function versionNeedles(pin: string): string[] {
  const trimmed = pin.trim();
  if (!trimmed) return [];
  const needles = new Set<string>([trimmed]);
  needles.add(trimmed.startsWith('v') ? trimmed.slice(1) : `v${trimmed}`);
  return [...needles].filter(Boolean);
}

/** True when `output` states `pin`. Substring, because a binary wraps its version in prose. */
function statesVersion(output: string, pin: string): boolean {
  return versionNeedles(pin).some((n) => output.includes(n));
}

/**
 * True when a cross-architecture binary's string table carries the pin as a
 * WHOLE line. Stricter than `statesVersion` on purpose: without the prose
 * around it, a loose substring would match any longer version that merely
 * starts with the same digits (3.5.0 inside 3.5.01), and a version check that
 * can be satisfied by a different version is not a version check.
 */
function stringsCarryVersion(lines: string[], pin: string): boolean {
  const needles = new Set(versionNeedles(pin));
  return lines.some((l) => needles.has(l.trim()));
}

/**
 * True when `buf` contains the pin as a COMPLETE printable run.
 *
 * Equivalent to `strings -a <bin> | grep -x <pin>`, done in process. Whole-run
 * rather than substring for the same reason as `stringsCarryVersion`: a loose
 * match would accept 3.5.01 as 3.5.0.
 */
function bufferCarriesVersion(buf: Buffer, pin: string): boolean {
  const needles = versionNeedles(pin);
  if (needles.length === 0) return false;
  const runs: string[] = [];
  let cur = '';
  for (let i = 0; i < buf.length; i++) {
    const b = buf[i];
    // Printable ASCII, the same range strings(1) uses by default.
    if (b >= 0x20 && b <= 0x7e) {
      cur += String.fromCharCode(b);
      continue;
    }
    if (cur.length >= 3) runs.push(cur);
    cur = '';
  }
  if (cur.length >= 3) runs.push(cur);
  return stringsCarryVersion(runs, pin);
}

// ─── Probing a real artifact ────────────────────────────────────────────────

/**
 * A version-shaped token. Used only to decide whether a binary's output is
 * ABOUT versions at all, which is what separates "this is the wrong version"
 * from "this binary has no version to give".
 */
const VERSION_TOKEN = /\bv?\d+\.\d+(?:\.\d+)?[\w.+-]*/;

/**
 * Components proven probeable on real staged assets (2026-08-15). If one of
 * these is staged and comes back UNPROBED, the gate has gone quiet on something
 * it used to check, which is how a check decays into decoration. That is a
 * failure, not a shrug.
 */
const MUST_STAY_PROBEABLE = new Set(['rsync', 'criu']);

const HOST_ARCH = os.arch() === 'x64' ? 'amd64' : os.arch() === 'arm64' ? 'arm64' : os.arch();

type Verdict = 'match' | 'mismatch' | 'unprobed';

interface Result {
  component: string;
  asset: string;
  pin: string;
  verdict: Verdict;
  detail: string;
}

function probeAsset(
  component: string,
  zstPath: string,
  arch: string,
  pin: string,
  tmpDir: string
): Result {
  const asset = path.relative(ASSETS_DIR, zstPath);
  const bin = path.join(tmpDir, path.basename(zstPath).replace(/\.zst$/, ''));
  try {
    const raw = execFileSync('zstd', ['-dc', zstPath], { maxBuffer: 1024 * 1024 * 512 });
    fs.writeFileSync(bin, raw, { mode: 0o755 });
  } catch (error) {
    return {
      component,
      asset,
      pin,
      verdict: 'unprobed',
      detail: `could not decompress: ${String(error)}`,
    };
  }

  if (arch === HOST_ARCH) {
    // The strong form: the binary itself answers.
    for (const flag of ['--version', 'version', '-V']) {
      try {
        const out = execFileSync(bin, [flag], {
          encoding: 'utf-8',
          timeout: 20_000,
          stdio: ['ignore', 'pipe', 'pipe'],
          maxBuffer: 1024 * 1024 * 16,
        });
        if (statesVersion(out, pin)) {
          return { component, asset, pin, verdict: 'match', detail: `ran \`${flag}\`` };
        }
        // A MISMATCH needs evidence of a DIFFERENT version, never merely the
        // absence of ours. The CSI sidecars are the case that taught this: they
        // are built without version ldflags, answer `--version` with
        // `<binary> unknown`, and carry no version token at all. Calling that a
        // mismatch would red-flag a perfectly good asset, and a gate that cries
        // wolf on healthy input gets disabled, which is worse than not having it.
        if (VERSION_TOKEN.test(out)) {
          return {
            component,
            asset,
            pin,
            verdict: 'mismatch',
            detail: `ran \`${flag}\` and it stated a different version: ${out.split('\n')[0].slice(0, 120)}`,
          };
        }
        break; // it ran but says nothing about versions; fall through to strings
      } catch {
        // Some binaries exit non-zero or log to stderr for --version; try the
        // next flag, then fall through to the string table.
      }
    }
  }

  // Cross-architecture: read the binary's own string table, in process.
  //
  // Deliberately NOT `strings(1)`: that is an undeclared external binary (knip
  // flags it), it is absent from minimal images, and its absence would silently
  // downgrade every cross-arch asset to "unprobed" -- a check quietly getting
  // weaker, which is the failure this whole gate is about.
  try {
    const buf = fs.readFileSync(bin);
    if (bufferCarriesVersion(buf, pin)) {
      return {
        component,
        asset,
        pin,
        verdict: 'match',
        detail: 'string table carries the pin as a whole token',
      };
    }
    return {
      component,
      asset,
      pin,
      verdict: 'unprobed',
      detail: 'no version token in the string table',
    };
  } catch (error) {
    return { component, asset, pin, verdict: 'unprobed', detail: `read failed: ${String(error)}` };
  }
}

// ─── Control ────────────────────────────────────────────────────────────────

/**
 * Prove the comparison can FAIL before believing any run of it.
 *
 * This runs on EVERY invocation, not behind a flag, and it needs neither Docker
 * nor a staged asset. That is deliberate: on a fresh checkout the real assets
 * are absent (they are gitignored), and a gate whose only behaviour there is
 * "nothing to do, exit 0" is precisely the shape of check this file exists to
 * replace.
 */
function runControls(): string[] {
  const failures: string[] = [];
  // The pin lives in the CASE, not in a second array indexed by position. It was
  // written as two parallel arrays and they drifted immediately: the zot case
  // was checked against the pin 1.75.0, so the control that proves a v-prefixed
  // binary matches an unprefixed pin was really asserting that 2.1.2 equals
  // 1.75.0, and it failed. A control that cannot pass is as useless as one that
  // cannot fail, and positional pairing is what let a reader see nothing wrong.
  const cases: Array<{ output: string; pin: string; expected: boolean; label: string }> = [
    {
      output: 'rsync  version 3.5.0  protocol version 32',
      pin: '3.5.0',
      expected: true,
      label: 'plain version in prose',
    },
    {
      output: 'zot v2.1.2',
      pin: '2.1.2',
      expected: true,
      label: 'v-prefixed binary against an unprefixed pin',
    },
    {
      output: 'k3s version v1.36.3+k3s1 (5aed4d7b)',
      pin: 'v1.36.3+k3s1',
      expected: true,
      label: 'pin that already carries its v',
    },
    {
      output: 'rsync  version 3.4.4  protocol version 32',
      pin: '3.5.0',
      expected: false,
      label: 'THE REGRESSION: an older binary',
    },
    { output: '', pin: '3.5.0', expected: false, label: 'empty output is never a match' },
  ];
  for (const { output, pin, expected, label } of cases) {
    if (statesVersion(output, pin) !== expected) {
      failures.push(`control: ${label} (pin ${pin}) did not behave as ${expected}`);
    }
  }

  // The strict cross-arch form must reject a longer version that merely shares
  // a prefix, or it would certify 3.5.01 as 3.5.0.
  if (stringsCarryVersion(['3.5.01'], '3.5.0')) {
    failures.push('control: a prefix-sharing version was accepted by the string-table check');
  }
  if (!stringsCarryVersion(['irrelevant', '3.5.0', 'more'], '3.5.0')) {
    failures.push('control: an exact version line was not accepted by the string-table check');
  }
  return failures;
}

// ─── Main ───────────────────────────────────────────────────────────────────

function main(): void {
  console.log('Embedded asset versions: does the artifact match the pin?');
  console.log('='.repeat(60));

  const controlFailures = runControls();
  if (controlFailures.length > 0) {
    for (const f of controlFailures) console.error(`${RED}✗${NC} ${f}`);
    console.error(
      `${RED}✗${NC} the comparison itself is broken, so no verdict it produces means anything.`
    );
    process.exit(1);
  }
  console.log(
    `${GREEN}✓${NC} control fired: the comparison accepts a match and rejects a stale one`
  );

  if (!fs.existsSync(LOCKFILE)) {
    console.log(`${YELLOW}⚠${NC} SKIPPED: ${path.relative(CONSOLE_ROOT, LOCKFILE)} is absent`);
    console.log('  (the renet submodule is not checked out; nothing to verify)');
    process.exit(0);
  }

  const components: Record<string, Component> =
    JSON.parse(fs.readFileSync(LOCKFILE, 'utf-8')).components ?? {};

  const staged: Array<{ zst: string; arch: string; pin: string; name: string }> = [];
  for (const [name, comp] of Object.entries(components)) {
    const base = comp.assetBase ?? name;
    const cls = comp.class ?? 'base';
    for (const arch of ['amd64', 'arm64']) {
      const zst = path.join(ASSETS_DIR, arch, cls, `${base}-linux-${arch}.zst`);
      if (fs.existsSync(zst) && comp.version) {
        staged.push({ zst, arch, pin: comp.version, name });
      }
    }
  }

  if (staged.length === 0) {
    console.log(
      `${YELLOW}⚠${NC} SKIPPED: no staged assets under ${path.relative(CONSOLE_ROOT, ASSETS_DIR)}`
    );
    console.log('  The .zst payloads are gitignored, so a fresh checkout and any CI job that has');
    console.log('  not run `./build.sh embed_assets` legitimately has none. The controls above');
    console.log('  still ran, so this is a skip with its reason stated, not a silent pass.');
    process.exit(0);
  }

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'embed-verify-'));
  let results: Result[] = [];
  try {
    results = staged.map((s) => probeAsset(s.name, s.zst, s.arch, s.pin, tmpDir));
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }

  const mismatches = results.filter((r) => r.verdict === 'mismatch');
  const matched = results.filter((r) => r.verdict === 'match');
  const unprobed = results.filter((r) => r.verdict === 'unprobed');

  for (const r of matched) console.log(`  ${GREEN}✓${NC} ${r.asset} is ${r.pin} (${r.detail})`);
  for (const r of unprobed) console.log(`  ${YELLOW}?${NC} ${r.asset} unprobed: ${r.detail}`);
  for (const r of mismatches) console.error(`  ${RED}✗${NC} ${r.asset}: ${r.detail}`);

  if (mismatches.length > 0) {
    console.error('');
    console.error(`${RED}✗${NC} ${mismatches.length} staged asset(s) are NOT the version pinned.`);
    console.error('  The lockfile, the Dockerfile ARGs and the credits can all be correct while');
    console.error(
      '  this is wrong: `./build.sh embed_assets --force` re-extracts from an EXISTING'
    );
    console.error('  image, so a Dockerfile change needs `./build.sh docker_image` FIRST.');
    process.exit(1);
  }

  // Decay guard: something that used to be verifiable must not quietly stop being so.
  const wentQuiet = unprobed.filter((r) => MUST_STAY_PROBEABLE.has(r.component));
  if (wentQuiet.length > 0) {
    console.error('');
    console.error(
      `${RED}✗${NC} ${wentQuiet.length} asset(s) that this gate is known to verify came`
    );
    console.error('  back UNPROBED. The gate did not fail, it went QUIET, which is how a check');
    console.error(
      '  decays into decoration. Either the probe recipe broke or the asset changed shape:'
    );
    for (const r of wentQuiet) console.error(`    ${r.asset}: ${r.detail}`);
    process.exit(1);
  }

  if (matched.length === 0) {
    console.error('');
    console.error(`${RED}✗${NC} ${staged.length} asset(s) staged and NOT ONE could be verified.`);
    console.error('  A run that opened every box and read nothing is not a pass. If every line');
    console.error('  above says "could not decompress", `zstd` is missing from this environment.');
    process.exit(1);
  }

  console.log('');
  console.log(
    `${GREEN}✓${NC} ${matched.length} staged asset(s) match their pin` +
      (unprobed.length > 0 ? `, ${unprobed.length} unprobed (listed above)` : '')
  );
  process.exit(0);
}

main();
