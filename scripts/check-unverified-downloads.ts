#!/usr/bin/env node
/**
 * Every remote artifact a Dockerfile installs must be cryptographically verified.
 *
 * WHY THIS EXISTS. On 2026-09-01 five downloads in `.devcontainer/Dockerfile` were
 * hand-fixed to check a sha256: go, glab, bottom, openvscode-server, and the ttyd
 * image (which was pinned by a MUTABLE tag, so `1.7.8-alpine` could be repointed at
 * a different image without the version string changing). Before that, `bw` was the
 * only verified fetch in the file -- and it was only verified because it had just
 * been added by someone thinking about supply chain that day.
 *
 * Nothing prevented the sixth unverified download. Every existing Dockerfile gate is
 * blind to this by construction: they assert the build SUCCEEDS, and a build succeeds
 * perfectly well when it installs a substituted artifact. `check:ci-devcontainer-pins`
 * is the closest neighbour and it watches VERSION freshness, not integrity -- a pin can
 * be current and unverified at the same time.
 *
 * WHAT COUNTS AS VERIFIED
 *   - `sha256sum -c` / `sha512sum -c` in the same RUN as the fetch
 *   - `gpg --verify` / `cosign verify` in the same RUN
 *   - `COPY --from=<image>@sha256:<digest>` (a digest cannot drift; a tag can)
 *
 * DELIBERATELY OUT OF SCOPE, so a green here is not read as more than it is:
 *   - `npm install -g` / `pip install`: the registry's own integrity metadata is a
 *     different trust model, governed by .npmrc (ignore-scripts, minimum-release-age).
 *   - `apt-get install` from a repo added with a `signed-by` keyring: apt verifies
 *     every package against that keyring, so the packages are covered even though the
 *     keyring fetch itself is not.
 *   - Anything piped into a shell (`curl | bash`). No hash fixes those; only vendoring
 *     the installer does. They are allowlisted with that reason rather than pretended
 *     about.
 *
 * ESCAPE HATCH: .unverified-download-allowlist, BLOCKER-gated like every other
 * suppression list here, and liveness-probed by check-suppression-liveness.ts.
 *
 * Usage: npx tsx scripts/check-unverified-downloads.ts
 * Exit:  0 clean/allowlisted, 1 an unverified download or a malformed allowlist.
 */

import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseBlockeredList, verifyAllBlockers } from './lib/blocker-validator.js';
import { GREEN, NC, RED, YELLOW } from './utils/console.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const ALLOWLIST =
  process.env.UNVERIFIED_DOWNLOAD_ALLOWLIST || path.join(ROOT, '.unverified-download-allowlist');

const VERIFY_RE = /sha256sum\s+-c|sha512sum\s+-c|gpg\s+--verify|cosign\s+verify/;
const FETCH_RE = /\b(?:curl|wget)\b[^\n]*?(https?:\/\/[^\s"'\\]+)/g;
const LOCAL_RE = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])/;

export interface Finding {
  file: string;
  line: number;
  url: string;
  kind: 'fetch' | 'image';
}

/** Join backslash continuations into logical instructions, keeping the start line. */
export function logicalInstructions(src: string): Array<{ line: number; text: string }> {
  const out: Array<{ line: number; text: string }> = [];
  const lines = src.split('\n');
  let buf = '';
  let start = 0;
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    if (buf === '') start = i + 1;
    // A comment INSIDE a continuation is not part of the shell command, but it also
    // must not terminate the instruction -- Docker allows it.
    const isComment = /^\s*#/.test(raw);
    const stripped = raw.replace(/\\\s*$/, '');
    if (!isComment) buf += (buf ? '\n' : '') + stripped;
    if (/\\\s*$/.test(raw)) continue;
    if (buf.trim()) out.push({ line: start, text: buf });
    buf = '';
  }
  if (buf.trim()) out.push({ line: start, text: buf });
  return out;
}

/** Unverified remote artifacts in one Dockerfile's source. Pure, so a control can drive it. */
export function scan(file: string, src: string): Finding[] {
  const found: Finding[] = [];
  for (const { line, text } of logicalInstructions(src)) {
    const head = text.trimStart();

    // COPY --from=<ref>: a registry ref needs a digest; a build-stage name does not.
    const copyFrom = /^COPY\s+--from=(\S+)/i.exec(head);
    if (copyFrom) {
      const ref = copyFrom[1];
      const isStage = !ref.includes('/') && !ref.includes(':') && !ref.includes('@');
      if (!isStage && !ref.includes('@sha256:')) {
        found.push({ file, line, url: ref, kind: 'image' });
      }
      continue;
    }

    // Only RUN installs things. HEALTHCHECK/CMD hitting localhost is not a download.
    if (!/^RUN\b/i.test(head)) continue;
    const verified = VERIFY_RE.test(text);
    FETCH_RE.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = FETCH_RE.exec(text)) !== null) {
      const url = m[1];
      if (LOCAL_RE.test(url)) continue;
      if (!verified) found.push({ file, line, url, kind: 'fetch' });
    }
  }
  return found;
}

/** An allowlist entry matches a finding when its token appears in the URL or ref. */
function isAllowed(f: Finding, tokens: string[]): boolean {
  return tokens.some((t) => f.url.includes(t));
}

// ─── Controls: prove the detector can fail before believing it passed ────────
function runControls(): string[] {
  const bad: string[] = [];
  const unverified = `RUN curl -fsSL -o /tmp/x.tgz "https://example.com/x.tgz" \\\n    && tar -xz -f /tmp/x.tgz\n`;
  if (scan('c', unverified).length !== 1) bad.push('an unverified curl was NOT detected');

  const verified = `RUN curl -fsSL -o /tmp/x.tgz "https://example.com/x.tgz" \\\n    && echo "abc  /tmp/x.tgz" | sha256sum -c - \\\n    && tar -xz -f /tmp/x.tgz\n`;
  if (scan('c', verified).length !== 0) bad.push('a sha256sum-verified curl WAS flagged');

  const health = `HEALTHCHECK CMD wget --quiet -O /dev/null http://localhost/health || exit 1\n`;
  if (scan('c', health).length !== 0) bad.push('a localhost HEALTHCHECK was flagged as a download');

  const tagImage = `COPY --from=vendor/tool:1.2.3 /usr/bin/tool /usr/bin/tool\n`;
  if (scan('c', tagImage).length !== 1) bad.push('a mutable image TAG was not flagged');

  const digestImage = `COPY --from=vendor/tool@sha256:${'a'.repeat(64)} /usr/bin/tool /usr/bin/tool\n`;
  if (scan('c', digestImage).length !== 0) bad.push('a digest-pinned image WAS flagged');

  const stage = `COPY --from=builder /out/app /app\n`;
  if (scan('c', stage).length !== 0) bad.push('a build-stage COPY was flagged as a registry ref');

  return bad;
}

function main(): void {
  console.log('Unverified downloads: is every remote artifact checked before use?');
  console.log('='.repeat(64));

  const controlFailures = runControls();
  if (controlFailures.length > 0) {
    for (const c of controlFailures) console.error(`${RED}✗${NC} control: ${c}`);
    console.error(`${RED}✗${NC} the detector is broken, so no verdict it produces means anything.`);
    process.exit(1);
  }
  console.log(`${GREEN}✓${NC} controls fired: the detector flags unverified and passes verified`);

  let tokens: string[] = [];
  if (fs.existsSync(ALLOWLIST)) {
    const entries = parseBlockeredList(ALLOWLIST);
    const errors = verifyAllBlockers(entries, ALLOWLIST);
    if (errors.length > 0) {
      console.error(`${RED}✗ ${path.basename(ALLOWLIST)} has invalid entries:${NC}`);
      for (const e of errors) console.error(`  ${e}`);
      process.exit(1);
    }
    tokens = entries.map((e) => e.entry.trim());
  }

  // --recurse-submodules, NOT a bare `git ls-files`. private/{account,renet,growth}
  // are submodules, and a bare listing cannot see inside them -- so five Dockerfiles
  // sat outside this gate's view while it reported "every remote artifact" verified.
  // A gate whose scope silently excludes half the build surface is the shape of
  // green-while-blind this file exists to prevent.
  const list = (args: string): string[] => {
    try {
      return execSync(`git ls-files ${args}`, { cwd: ROOT, encoding: 'utf-8' })
        .split('\n')
        .filter((p: string) => /(^|\/)Dockerfile(\.|$)/.test(p));
    } catch {
      return [];
    }
  };
  const tracked = list('');
  const withSubs = list('--recurse-submodules');
  const files = [...new Set([...tracked, ...withSubs])];

  // A submodule that is not checked out contributes nothing, and that must be
  // stated rather than counted as clean.
  const missingSubs = withSubs.filter((f) => !fs.existsSync(path.join(ROOT, f)));
  if (missingSubs.length > 0) {
    console.log(
      `${YELLOW}? ${missingSubs.length} Dockerfile(s) in un-checked-out submodules were not scanned${NC}`
    );
  }

  if (files.length === 0) {
    console.error(`${RED}✗${NC} no Dockerfiles found -- this gate would pass vacuously.`);
    process.exit(1);
  }

  const findings: Finding[] = [];
  const allowed: Finding[] = [];
  for (const rel of files) {
    const abs = path.join(ROOT, rel);
    if (!fs.existsSync(abs)) continue;
    for (const f of scan(rel, fs.readFileSync(abs, 'utf-8'))) {
      (isAllowed(f, tokens) ? allowed : findings).push(f);
    }
  }

  for (const a of allowed) console.log(`${YELLOW}⏸ allowlisted${NC} ${a.file}:${a.line} ${a.url}`);

  if (findings.length === 0) {
    console.log(
      `${GREEN}✓ every remote artifact across ${files.length} Dockerfile(s) is verified or allowlisted.${NC}`
    );
    return;
  }

  console.error('');
  console.error(`${RED}✗ ${findings.length} unverified remote artifact(s):${NC}`);
  for (const f of findings) {
    console.error(
      `  ${f.file}:${f.line}  ${f.kind === 'image' ? 'image pinned by TAG' : 'download'}  ${f.url}`
    );
  }
  console.error('');
  console.error(`${YELLOW}TO FIX:${NC}`);
  console.error('  download  -> add `echo "<sha256>  <file>" | sha256sum -c -` in the same RUN,');
  console.error('               after the curl and BEFORE the artifact is used. A stream piped');
  console.error('               straight into tar cannot be verified; download to a file first.');
  console.error('  image     -> replace the tag with @sha256:<digest>:');
  console.error('               docker buildx imagetools inspect <image>:<tag>');
  console.error('');
  console.error('If it genuinely cannot be verified (no published checksum, or curl|bash), add a');
  console.error(`token from its URL to ${path.basename(ALLOWLIST)} with a \`# BLOCKER:\` reason.`);
  process.exit(1);
}

// Only run when invoked directly. Importing this module (the gate test does, and so
// does any sibling that wants `scan`) must not execute the whole check.
if (process.argv[1] && import.meta.url === `file://${process.argv[1]}`) {
  main();
}
