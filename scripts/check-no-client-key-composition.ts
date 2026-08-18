/**
 * check:ci-no-client-key-composition — the MACHINE never composes an object key.
 *
 * THE RULE. In the chunk store the SERVER names every key. The client receives
 * `chunkPrefix`, `manifestKey`, `manifestKeys`, `getUrls` and `manifestGetUrls`
 * already derived, and must never build a key by appending a `c/` or `m/`
 * segment to anything.
 *
 * WHY IT IS A GATE AND NOT A CONVENTION. This defect has now been introduced
 * TWICE, and the second time nothing caught it:
 *
 *   1. The client composed the chunk prefix from the grant's `prefix`, which is
 *      the LINEAGE prefix and covers both `c/` and `m/`. Every chunk landed one
 *      level above where the server looks: dedup silently died, chunks were
 *      orphaned yet still metered, and the snapshot was unrestorable. All of it
 *      silent. That is what motivated the server-names-the-keys design.
 *   2. The "fix" left a FALLBACK that composed the key whenever the server
 *      omitted `chunkPrefix` — and that fallback was then DUPLICATED into the
 *      read path when restore was built. Both were unreachable from a
 *      conforming server (the DTO makes the field required), so they could only
 *      ever fire against a broken server, where they papered over the bug
 *      instead of surfacing it.
 *
 * Why no existing check saw it: the write path and the read path each have
 * their own tests, and each passed in isolation. Nothing compared the two
 * paths' handling of the SAME missing field. `check:ci-backup-protocol-
 * conformance` pins that the field EXISTS on both sides of the wire; it says
 * nothing about what the client does when it is absent.
 *
 * The Go test `TestWireGrant_AMissingChunkPrefixIsRefusedNotComposed` covers
 * the instance and rides CI through ct-tests.yml. This gate covers the CLASS:
 * it fails on ANY key composition anywhere in the client, including a new one
 * in a file nobody has written yet.
 *
 * Run: npx tsx scripts/check-no-client-key-composition.ts
 *
 * Control-first: every run first proves the scanner on a synthetic file that
 * composes a key, and refuses to pass a scan that read nothing.
 */

import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');

/**
 * The client trees. private/account is deliberately NOT scanned: the server is
 * the party that SHOULD compose keys, and `backupKeys` there is the one correct
 * implementation.
 */
const TARGET_GLOBS = ['private/renet/pkg/chunkstore/**/*.go', 'private/renet/cmd/renet/**/*.go'];

/** A scan that reads fewer files than this means the globs broke. */
const MIN_FILES = 10;

/**
 * Key segments the client must never append. Written as the literals a Go
 * author would type, including both slash spellings.
 */
const FORBIDDEN = ['"c/"', '"/c/"', '"m/"', '"/m/"'];

interface Finding {
  file: string;
  line: number;
  text: string;
}

/**
 * Strip Go comments so the RULE can be explained in prose without tripping the
 * gate that enforces it. Without this the two comments that document why key
 * composition is forbidden would themselves fail the check — a gate that
 * punishes its own documentation gets deleted, not obeyed.
 */
function stripComments(src: string): string[] {
  const out: string[] = [];
  let inBlock = false;
  for (const raw of src.split('\n')) {
    let line = raw;
    if (inBlock) {
      const end = line.indexOf('*/');
      if (end === -1) {
        out.push('');
        continue;
      }
      line = line.slice(end + 2);
      inBlock = false;
    }
    const block = line.indexOf('/*');
    if (block !== -1) {
      const end = line.indexOf('*/', block + 2);
      if (end === -1) {
        line = line.slice(0, block);
        inBlock = true;
      } else {
        line = line.slice(0, block) + line.slice(end + 2);
      }
    }
    // A `//` inside a string literal is not a comment. Rare in this tree, and
    // erring toward KEEPING text only ever produces a finding to look at.
    const slash = line.indexOf('//');
    if (slash !== -1 && (line.slice(0, slash).match(/"/g)?.length ?? 0) % 2 === 0) {
      line = line.slice(0, slash);
    }
    out.push(line);
  }
  return out;
}

function scan(root: string, globs: string[]): { findings: Finding[]; files: number } {
  const findings: Finding[] = [];
  let files = 0;
  for (const pattern of globs) {
    for (const rel of globSync(pattern, { cwd: root, absolute: false })) {
      // Tests legitimately spell server-shaped keys to assert on them.
      if (rel.endsWith('_test.go')) continue;
      files++;
      const lines = stripComments(readFileSync(join(root, rel), 'utf8'));
      lines.forEach((line, i) => {
        for (const token of FORBIDDEN) {
          if (line.includes(token)) {
            findings.push({ file: rel, line: i + 1, text: line.trim() });
            return;
          }
        }
      });
    }
  }
  return { findings, files };
}

// ── Control: the real scanner, on a real fixture, both directions ──────────
{
  const tmp = mkdtempSync(join(tmpdir(), 'keycomp-control-'));
  try {
    const dir = join(tmp, 'private/renet/pkg/chunkstore');
    mkdirSync(dir, { recursive: true });
    writeFileSync(
      join(dir, 'bad.go'),
      [
        'package chunkstore',
        '',
        'func p(prefix string) string {',
        '\treturn prefix + "c/"',
        '}',
      ].join('\n')
    );
    writeFileSync(
      join(dir, 'good.go'),
      [
        'package chunkstore',
        '',
        '// Composing one (prefix + "c/") is exactly the defect this forbids.',
        'func q(chunkPrefix string) string {',
        '\treturn chunkPrefix',
        '}',
      ].join('\n')
    );
    writeFileSync(
      join(dir, 'ignored_test.go'),
      ['package chunkstore', '', 'var k = "t/s/l/l/c/" + h'].join('\n')
    );

    const { findings } = scan(tmp, TARGET_GLOBS);
    const hit = findings.filter((f) => f.file.endsWith('bad.go'));
    if (hit.length === 0) {
      console.error(
        '✗ instrument control did not fire: a file composing `prefix + "c/"` was NOT\n' +
          '  reported, so a green run below would mean nothing.'
      );
      process.exit(1);
    }
    const over = findings.filter((f) => !f.file.endsWith('bad.go'));
    if (over.length > 0) {
      console.error(
        `✗ instrument control over-reports (${over.map((f) => f.file).join(', ')}):\n` +
          '  a COMMENT explaining the rule, or a _test.go asserting a server-shaped key,\n' +
          '  was flagged. Either would make this gate punish its own documentation.'
      );
      process.exit(1);
    }
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
}

const { findings, files } = scan(ROOT, TARGET_GLOBS);

if (files < MIN_FILES) {
  console.error(
    `✗ only ${files} Go file(s) scanned (floor ${MIN_FILES}).\n` +
      '  The globs broke, or private/renet is not checked out. An unrun check is not a pass.'
  );
  process.exit(1);
}

if (findings.length > 0) {
  console.error(
    `✗ the client composes object keys (${findings.length}):\n` +
      findings.map((f) => `    ${f.file}:${f.line}  ${f.text}`).join('\n') +
      '\n\n' +
      '  The SERVER names every key. The client receives chunkPrefix, manifestKey,\n' +
      '  manifestKeys, getUrls and manifestGetUrls already derived, and a missing one\n' +
      '  is a LOUD ERROR, never a composed fallback. A client-composed prefix once\n' +
      '  wrote every chunk one level above the server: dedup died, chunks were\n' +
      '  orphaned yet still metered, and the snapshot could not be restored — all\n' +
      '  silently. The same fallback was later duplicated into the read path.'
  );
  process.exit(1);
}

console.log(
  `✓ the client composes no object keys (${files} Go file(s) across ` +
    `${TARGET_GLOBS.length} tree(s); control fired both ways)`
);
