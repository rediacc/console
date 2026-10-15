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
 *
 * ---- gate ----
 * step: Check embedded asset versions match their pins
 * needs: node
 * lane: quality-go
 * slow: true
 * ---- end gate ----
 */

import { execFile } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { grantedCores } from '../ci-runner/lease-client.js';
import { GREEN, NC, RED, YELLOW } from '../lib/console.js';
import { requireSubmodule, submodulePath } from '../lib/submodule-presence.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..', '..');
const RENET_DIR = submodulePath('private', 'renet');
const LOCKFILE = path.join(RENET_DIR, 'embed-assets.lock.json');
const ASSETS_DIR = path.join(RENET_DIR, 'pkg', 'embed', 'assets');
const execFileAsync = promisify(execFile);

/** Run a staged binary with stdin closed (as `stdio: 'ignore'` did), resolving its stdout or rejecting on a non-zero exit. */
function runForStdout(bin: string, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = execFile(
      bin,
      args,
      { encoding: 'utf-8', timeout: 20_000, maxBuffer: 1024 * 1024 * 16 },
      (error, stdout) => (error ? reject(error) : resolve(stdout))
    );
    child.stdin?.end();
  });
}

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

/**
 * True when `output` states `pin`. A substring, because a binary wraps its version in prose, but never one that is part of a longer number: `3.5.0` inside `3.5.01` or `13.5.0` is a different version. A following `-` or `+` stays allowed, because zot answers `--version` only with the git-describe form `v2.1.22-0-g6bbc7e5`, which names exactly the tag.
 */
function statesVersion(output: string, pin: string): boolean {
  return versionNeedles(pin).some((n) =>
    new RegExp(`(?<![0-9])(?<![0-9]\\.)${escapeRegExp(n)}(?![0-9])(?!\\.[0-9])`).test(output)
  );
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Printable ASCII, the same range strings(1) uses by default. */
function isPrintable(b: number): boolean {
  return b >= 0x20 && b <= 0x7e;
}

// ─── Go build info: module versions that are NOT the stamp ──────────────────

/** The 16-byte sentinels Go's linker wraps around every copy of the module info string (cmd/go `modload.infoStart` / `infoEnd`), both the `runtime.modinfo` copy and the one inside the build info blob. */
const GO_MODINFO_START = Buffer.from('3077af0c9274080241e1c107e6d618e6', 'hex');
const GO_MODINFO_END = Buffer.from('f932433186182072008242104116d8f2', 'hex');
/** The build info header magic, as `debug/buildinfo` searches for it. */
const GO_BUILDINFO_MAGIC = Buffer.from('\xff Go buildinf:', 'latin1');

/** A byte range `[start, end)` of a binary. */
type Span = [number, number];

/** Read an unsigned LEB128 varint at `at`, as `encoding/binary.Uvarint` does; undefined when it runs off the buffer or overflows. */
function readUvarint(buf: Buffer, at: number): { value: number; next: number } | undefined {
  let value = 0;
  let shift = 0;
  for (let i = at; i < buf.length && shift <= 49; i++) {
    const b = buf[i];
    value += (b & 0x7f) * 2 ** shift;
    if (b < 0x80) return { value, next: i + 1 };
    shift += 7;
  }
  return undefined;
}

/**
 * The byte ranges `[start, end)` of `buf` that hold Go build info: every sentinel-wrapped module info string (its `path`, `mod`, `dep` and `=>` lines) and the build info header with the toolchain version and module info inlined after it (Go 1.18+, flag bit 2).
 *
 * A `dep` line carries a module version as a tab-delimited whole token (`dep\tgithub.com/kubernetes-csi/external-snapshotter/client/v8\tv8.6.0`), so a binary whose dependency happened to share the pin's version would satisfy a string-table probe with no stamp at all. zot did exactly that: its arm64 asset passed on `mod\tzotregistry.dev/zot/v2\tv2.1.22`, a module version, while its real stamp sat beside a float byte. Excluding these ranges makes the probe answer only to a version the binary was stamped with.
 *
 * A start sentinel with no end sentinel after it excludes to the end of the buffer: excluding too much can only turn a match into a loud UNPROBED, never a wrong version into a match.
 */
function goBuildInfoSpans(buf: Buffer): Span[] {
  const spans: Span[] = [];
  for (let s = buf.indexOf(GO_MODINFO_START); s !== -1; s = buf.indexOf(GO_MODINFO_START, s + 1)) {
    const e = buf.indexOf(GO_MODINFO_END, s + GO_MODINFO_START.length);
    spans.push([s, e === -1 ? buf.length : e + GO_MODINFO_END.length]);
  }
  for (
    let m = buf.indexOf(GO_BUILDINFO_MAGIC);
    m !== -1;
    m = buf.indexOf(GO_BUILDINFO_MAGIC, m + 1)
  ) {
    // Header: magic (14), pointer size (1), flags (1), then two pointer-or-padding words, 32 bytes in all.
    let end = Math.min(buf.length, m + 32);
    if (m + 16 <= buf.length && (buf[m + 15] & 0x2) !== 0) {
      // Inline strings: a varint-length toolchain version, then a varint-length module info.
      const ver = readUvarint(buf, m + 32);
      const mod = ver && readUvarint(buf, ver.next + ver.value);
      end = mod ? Math.min(buf.length, mod.next + mod.value) : buf.length;
    }
    spans.push([m, end]);
  }
  return spans.sort((a, b) => a[0] - b[0]);
}

// ─── The stamp predicate ────────────────────────────────────────────────────

/** Bytes that continue a version number or a module path: a stamp has none of these on either side, so `v18.7.0`, `v8.7.01`, `v8.7.0-rc.1`, `1.8.7.0` and `/v8.7.0/` are all a different token. */
const VERSION_CONTINUATION = new Set([...'0123456789.+-_/'].map((c) => c.charCodeAt(0)));

function isLetter(b: number): boolean {
  return (b >= 0x41 && b <= 0x5a) || (b >= 0x61 && b <= 0x7a);
}

/** A byte that can sit inside a module path (`golang.org/x/mod/module` allows letters, digits and `-._~/`, plus `+` in a version). */
function isModulePathByte(b: number): boolean {
  return isLetter(b) || VERSION_CONTINUATION.has(b) || b === 0x7e;
}

/**
 * True when `buf` carries the pin as a STAMPED version: outside every Go build info span, and bounded so that it is not part of a longer token. Equivalent to `bufferCarriesVersionReference`, which states the same rule as one regular expression over the blanked string; the controls compare the two on planted buffers every run.
 *
 * Why the old rule was replaced (2026-10-15). It required a non-printable byte on both sides, which is what strings(1) would call a whole run. Go packs string data without separators, so a `-X main.version=v8.7.0` stamp lands wherever the linker puts it: the arm64 snapshot-controller rebuilt for 8.7.0 carried `\xa0Lv8.7.0\x00` (the `L` is the high byte of a float constant) and went UNPROBED, while zot carried `\x08@v2.1.22\x00` and only passed because its module version sat in a `mod` line. The neighbour bytes are chance, so the rule now rejects only the bytes that change what the token means:
 *
 * - right: any version continuation (`0-9 . + - _ /`).
 * - left: any version continuation; for the bare needle (no `v`) also a letter or `@`, because `go1.26.9` is a toolchain version and not a pin of 1.26.9, and the `v` form is its own needle.
 * - left `@` for the `v` needle when the byte before the `@` is a module path byte: `github.com/x/y@v8.7.0` is a dependency, as in a `-trimpath` source path.
 * - a neighbour inside a build info span counts as a boundary, so the two implementations agree at a span edge.
 *
 * A needle shorter than 3 bytes never matches (strings(1)'s default minimum, kept from the old rule).
 */
function bufferCarriesVersion(buf: Buffer, pin: string): boolean {
  const spans = goBuildInfoSpans(buf);
  const spanAt = (i: number): Span | undefined => spans.find(([s, e]) => i >= s && i < e);
  const byteAt = (i: number): number =>
    i < 0 || i >= buf.length || spanAt(i) !== undefined ? -1 : buf[i];
  for (const needle of versionNeedles(pin)) {
    if (needle.length < 3 || ![...needle].every((c) => isPrintable(c.charCodeAt(0)))) continue;
    const pat = Buffer.from(needle, 'latin1');
    const bare = !needle.startsWith('v');
    for (let at = buf.indexOf(pat); at !== -1; at = buf.indexOf(pat, at + 1)) {
      const end = at + pat.length;
      // Overlapping a span: a module version, or a needle cut by a span edge.
      if (spans.some(([s, e]) => at < e && end > s)) continue;
      const after = byteAt(end);
      if (VERSION_CONTINUATION.has(after)) continue;
      const before = byteAt(at - 1);
      if (VERSION_CONTINUATION.has(before)) continue;
      if (bare && (isLetter(before) || before === 0x40)) continue;
      if (!bare && before === 0x40 && isModulePathByte(byteAt(at - 2))) continue;
      return true;
    }
  }
  return false;
}

/** The regular expression form of `bufferCarriesVersion`, kept as the oracle its controls compare against: build info spans are blanked to NUL first, then one lookaround pattern per needle states the boundary rule. */
function bufferCarriesVersionReference(buf: Buffer, pin: string): boolean {
  const bytes = Buffer.from(buf);
  for (const [s, e] of goBuildInfoSpans(buf)) bytes.fill(0, s, e);
  const text = bytes.toString('latin1');
  const cont = '0-9.+\\-_/';
  return versionNeedles(pin).some((needle) => {
    if (needle.length < 3 || !/^[\x20-\x7e]+$/.test(needle)) return false;
    const left = needle.startsWith('v')
      ? `(?<![${cont}])(?<![A-Za-z${cont}~]@)`
      : `(?<![${cont}A-Za-z@])`;
    return new RegExp(`${left}${escapeRegExp(needle)}(?![${cont}])`).test(text);
  });
}

// ─── Probing a real artifact ────────────────────────────────────────────────

/**
 * A version-shaped token. Used only to decide whether a binary's output is
 * ABOUT versions at all, which is what separates "this is the wrong version"
 * from "this binary has no version to give".
 */
const VERSION_TOKEN = /\bv?\d+\.\d+(?:\.\d+)?[\w.+-]*/;

/**
 * Components proven probeable on real staged assets (rsync and criu on 2026-08-15;
 * the CSI sidecars once renet's Dockerfile stamped their version, commit 63f3ff54 of
 * private/renet). If one of these is staged and comes back UNPROBED, the gate has gone quiet on something
 * it used to check, which is how a check decays into decoration. That is a
 * failure, not a shrug.
 */
const MUST_STAY_PROBEABLE = new Set([
  'rsync',
  'criu',
  // The CSI sidecars joined once renet's Dockerfile stamped `-X main.version=v<tag>` (private/renet commit 63f3ff54); before that they answered `<binary> unknown` and a wrong one went unnoticed.
  'csiprovisioner',
  'csisnapshotter',
  'snapshotcontroller',
  // zot and k3s joined on 2026-10-15, once the string-table probe stopped counting Go build info: both arm64 assets carry their own stamp (zot `v2.1.22`, k3s `v1.37.1+k3s1`) outside it. zot's arm64 asset had been passing only on its `mod` line, a module version, which is no evidence of a stamp.
  'zot',
  'k3s',
]);

const HOST_ARCH = os.arch() === 'x64' ? 'amd64' : os.arch() === 'arm64' ? 'arm64' : os.arch();

type Verdict = 'match' | 'mismatch' | 'unprobed';

interface Result {
  component: string;
  asset: string;
  pin: string;
  verdict: Verdict;
  detail: string;
}

async function probeAsset(
  component: string,
  zstPath: string,
  arch: string,
  pin: string,
  tmpDir: string
): Promise<Result> {
  const asset = path.relative(ASSETS_DIR, zstPath);
  const bin = path.join(tmpDir, path.basename(zstPath).replace(/\.zst$/, ''));
  try {
    // zstd writes the file itself: no 200 MB round trip through a Node buffer.
    await execFileAsync('zstd', ['-d', '-q', '-f', zstPath, '-o', bin]);
    fs.chmodSync(bin, 0o755);
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
        const out = await runForStdout(bin, [flag]);
        if (statesVersion(out, pin)) {
          return { component, asset, pin, verdict: 'match', detail: `ran \`${flag}\`` };
        }
        // A MISMATCH needs evidence of a DIFFERENT version, never merely the absence of ours. The CSI sidecars were the case that taught this: built without version ldflags, they answered `--version` with `<binary> unknown` and carried no version token at all (renet's Dockerfile has stamped `main.version` since private/renet commit 63f3ff54). Calling that a mismatch would red-flag a perfectly good asset, and a gate that cries wolf on healthy input gets disabled,
        // which is worse than not having it.
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
  // Deliberately NOT `strings(1)`: that is an undeclared external binary (knip flags it), it is absent from minimal images, and its absence would silently downgrade every cross-arch asset to "unprobed" -- a check quietly getting weaker, which is the failure this whole gate is about.
  try {
    const buf = fs.readFileSync(bin);
    if (bufferCarriesVersion(buf, pin)) {
      return {
        component,
        asset,
        pin,
        verdict: 'match',
        detail: 'string table carries the stamped pin, outside Go build info',
      };
    }
    return {
      component,
      asset,
      pin,
      verdict: 'unprobed',
      detail:
        'no stamped version in the string table (Go build info module versions are not counted)',
    };
  } catch (error) {
    return { component, asset, pin, verdict: 'unprobed', detail: `read failed: ${String(error)}` };
  }
}

/**
 * Probe every staged asset, as many at a time as the core grant allows. Each probe is independent (its own
 * temp file, its own subprocesses) and zstd decompression is single-threaded,
 * so serial probing left the gate waiting on one core for about 4 seconds.
 * Sized by grantedCores(), never a constant (operator ruling 2026-10-05): the
 * runner's grant bounds it while the gate shares the machine with the whole
 * ci:quick pool, and a decompressed k3s or zot is 70-230 MB on disk. Results keep the staged
 * order, so the report reads the same however the probes interleave.
 */
async function probeAll(
  staged: Array<{ zst: string; arch: string; pin: string; name: string }>,
  tmpDir: string
): Promise<Result[]> {
  const results = new Array<Result>(staged.length);
  let next = 0;
  const worker = async (): Promise<void> => {
    while (next < staged.length) {
      const i = next++;
      const s = staged[i];
      results[i] = await probeAsset(s.name, s.zst, s.arch, s.pin, tmpDir);
    }
  };
  const width = Math.min(grantedCores(), staged.length);
  await Promise.all(Array.from({ length: width }, () => worker()));
  return results;
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
  // The pin lives in the CASE, not in a second array indexed by position. It was written as two parallel arrays and they drifted immediately: the zot case was checked against the pin 1.75.0, so the control that proves a v-prefixed binary matches an unprefixed pin was really asserting that 2.1.2 equals 1.75.0, and it failed. A control that cannot pass is as useless as one that
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

  // The digit boundary on `--version` output: a longer number is a different version, and the git-describe suffix zot answers with is the same one.
  const outputCases: Array<{ output: string; pin: string; expected: boolean; label: string }> = [
    { output: 'rsync  version 3.5.01', pin: '3.5.0', expected: false, label: 'longer patch' },
    { output: 'tool v13.5.0', pin: '3.5.0', expected: false, label: 'longer major' },
    { output: 'version 3.5.0.', pin: '3.5.0', expected: true, label: 'sentence full stop' },
    {
      output: '"commit":"v2.1.22-0-g6bbc7e5"',
      pin: '2.1.22',
      expected: true,
      label: 'git-describe of the tag (zot)',
    },
  ];
  for (const { output, pin, expected, label } of outputCases) {
    if (statesVersion(output, pin) !== expected) {
      failures.push(`control: output ${label} (pin ${pin}) did not behave as ${expected}`);
    }
  }

  // Go build info as the linker writes it: a sentinel-wrapped module info string (the `runtime.modinfo` copy), and the same string inlined after a build info header with the toolchain version (Go 1.18+, flag bit 2).
  const latin1 = (b: Buffer): string => b.toString('latin1');
  const uvarint = (n: number): string => {
    let out = '';
    let v = n;
    while (v >= 0x80) {
      out += String.fromCharCode((v & 0x7f) | 0x80);
      v = Math.floor(v / 128);
    }
    return out + String.fromCharCode(v);
  };
  const modinfo = (lines: string[]): string =>
    latin1(GO_MODINFO_START) + lines.join('\n') + latin1(GO_MODINFO_END);
  const header = (mod: string): string => {
    const toolchain = 'go1.26.9';
    return `${latin1(GO_BUILDINFO_MAGIC)}\u0008\u0002${'\u0000'.repeat(16)}${uvarint(toolchain.length)}${toolchain}${uvarint(mod.length)}${mod}`;
  };
  const depOnPin = modinfo([
    'path\tgithub.com/kubernetes-csi/external-snapshotter/v8/cmd/snapshot-controller',
    'mod\tgithub.com/kubernetes-csi/external-snapshotter/v8\t(devel)\t',
    'dep\tgithub.com/kubernetes-csi/external-snapshotter/client/v8\tv8.7.0\t',
  ]);
  // A header whose module info runs past 127 bytes takes a two-byte length, and must still be excluded whole. Unwrapped on purpose: `debug/buildinfo` reads inline module info with or without the sentinels, and a wrapped one would be excluded by the sentinel scan whatever the length parse did.
  const longDep = [
    `dep\tgithub.com/${'x'.repeat(140)}\tv8.7.0\t`,
    'dep\tgithub.com/y\tv8.7.0\t',
  ].join('\n');
  const spanCovers = (text: string, needle: string): boolean => {
    const buf = Buffer.from(text, 'latin1');
    const spans = goBuildInfoSpans(buf);
    let at = buf.indexOf(needle);
    let seen = 0;
    for (; at !== -1; at = buf.indexOf(needle, at + 1), seen++) {
      if (!spans.some(([s, e]) => at >= s && at + needle.length <= e)) return false;
    }
    return seen > 0;
  };
  if (!spanCovers(`\u0000${header(longDep)}\u0000`, 'v8.7.0')) {
    failures.push(
      'control: a build info header with a two-byte module info length was not excluded whole'
    );
  }
  if (!spanCovers(`\u0000${header('')}\u0000`, 'go1.26.9')) {
    failures.push('control: the build info toolchain version was not excluded');
  }

  // The fast buffer scan must agree with the regular expression oracle, including where they could plausibly diverge: buffer edges, space padding, printable neighbours of chance (the linker packs strings with no separator), a longer version on either side, the v-prefixed form, needles under 3 bytes, module paths, Go build info, and a first occurrence that is rejected followed by a later one that is not.
  const nul = '\u0000';
  const bufferCases: Array<{ text: string; pin: string; expected: boolean; label: string }> = [
    { text: `${nul}3.5.0${nul}`, pin: '3.5.0', expected: true, label: 'NUL-delimited run' },
    { text: '3.5.0', pin: '3.5.0', expected: true, label: 'run at both buffer edges' },
    { text: `${nul}  3.5.0 ${nul}`, pin: '3.5.0', expected: true, label: 'space-padded run' },
    { text: `${nul}v2.1.2\n`, pin: '2.1.2', expected: true, label: 'v-prefixed run' },
    {
      text: `\u00ff\u00a0Lv8.7.0${nul}`,
      pin: '8.7.0',
      expected: true,
      label: 'THE 2026-10-15 CASE: the arm64 snapshot-controller stamp after a float byte `L`',
    },
    {
      text: `\u00e1z\u0014\u00aeG\u00e1\u0008@v2.1.22${nul}`,
      pin: '2.1.22',
      expected: true,
      label: 'the arm64 zot stamp after a float byte `@`',
    },
    {
      text: `${nul}3.5.0 x${nul}`,
      pin: '3.5.0',
      expected: true,
      label: 'a space then prose on the right is a boundary',
    },
    {
      text: `${nul}v8.7.0Kq${nul}`,
      pin: '8.7.0',
      expected: true,
      label: 'a chance letter on the right',
    },
    { text: `${nul}3.5.01${nul}`, pin: '3.5.0', expected: false, label: 'prefix-sharing version' },
    { text: `${nul}v8.7.01${nul}`, pin: '8.7.0', expected: false, label: 'longer patch, v form' },
    { text: `${nul}v18.7.0${nul}`, pin: '8.7.0', expected: false, label: 'longer major, v form' },
    { text: `${nul}1.8.7.0${nul}`, pin: '8.7.0', expected: false, label: 'a dotted prefix' },
    { text: `${nul}v8.7.0-rc.1${nul}`, pin: '8.7.0', expected: false, label: 'a pre-release' },
    { text: `${nul}v1.37.1+k3s1${nul}`, pin: '1.37.1', expected: false, label: 'a build suffix' },
    {
      text: `${nul}github.com/kubernetes-csi/external-snapshotter/client/v8@v8.7.0/apis/volumesnapshot.go${nul}`,
      pin: '8.7.0',
      expected: false,
      label: 'a module path @v (a -trimpath source path)',
    },
    {
      text: `${nul}github.com/x/y@v8.7.0${nul}`,
      pin: '8.7.0',
      expected: false,
      label: 'a module path @v at the end of a run',
    },
    { text: `${nul}x@3.5.0${nul}`, pin: '3.5.0', expected: false, label: 'a bare version after @' },
    {
      text: `${nul}x3.5.0${nul}`,
      pin: '3.5.0',
      expected: false,
      label: 'a letter before the bare needle',
    },
    { text: `${nul}go8.7.0${nul}`, pin: '8.7.0', expected: false, label: 'a toolchain version' },
    { text: `${nul}3.4.4${nul}`, pin: '3.5.0', expected: false, label: 'THE REGRESSION as bytes' },
    { text: `${nul}1.2${nul}1${nul}`, pin: '1', expected: false, label: 'needle under 3 bytes' },
    {
      text: `${nul}3.5.01${nul}3.5.0${nul}`,
      pin: '3.5.0',
      expected: true,
      label: 'a later stamp after a rejected occurrence',
    },
    {
      text: `${nul}${depOnPin}${nul}`,
      pin: '8.7.0',
      expected: false,
      label: 'THE HOLE: a runtime.modinfo dep line on the pin, no stamp',
    },
    {
      text: `${nul}${header(depOnPin)}${nul}`,
      pin: '8.7.0',
      expected: false,
      label: 'a build info header dep line on the pin, no stamp',
    },
    {
      text: `${nul}${header(longDep)}${nul}`,
      pin: '8.7.0',
      expected: false,
      label: 'a build info header past 127 bytes, no stamp',
    },
    {
      text: `${nul}${latin1(GO_MODINFO_START)}mod\tm\tv8.7.0\t`,
      pin: '8.7.0',
      expected: false,
      label: 'module info with no end sentinel excludes to the end',
    },
    {
      text: `${nul}${depOnPin}${nul}v8.7.0${nul}${header(depOnPin)}`,
      pin: '8.7.0',
      expected: true,
      label: 'a stamp between two build info copies is still found',
    },
    {
      text: `${nul}v8.7.0${depOnPin}`,
      pin: '8.7.0',
      expected: true,
      label: 'a stamp right before a sentinel (its 0 is not a digit of the stamp)',
    },
  ];
  for (const { text, pin, expected, label } of bufferCases) {
    const buf = Buffer.from(text, 'latin1');
    const fast = bufferCarriesVersion(buf, pin);
    const reference = bufferCarriesVersionReference(buf, pin);
    if (fast !== expected || reference !== expected) {
      failures.push(
        `control: buffer scan, ${label} (pin ${pin}): fast=${fast} reference=${reference}, expected ${expected}`
      );
    }
  }
  return failures;
}

// ─── Main ───────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
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

  if (!requireSubmodule('embed asset versions', [LOCKFILE])) process.exit(0);

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
    results = await probeAll(staged, tmpDir);
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

void main();
