#!/usr/bin/env npx tsx
/**
 * No reader-facing doc may TEACH a command that the engine refuses.
 *
 * WHY THIS EXISTS. The rclone cloud arm was retired. Twelve locales of
 * `rdc-cheat-sheet.md` were carefully corrected, `validate:translation-freshness`
 * went green, and the page a visitor actually saw was still teaching
 * `rdc repo push <repo> --to <storage>` in every language -- because
 * `src/pages/[lang]/docs/rdc-cheat-sheet.astro` renders ONE hardcoded English
 * Marp source and ignores the locale content files entirely.
 *
 * So a gate was green over files the renderer does not read. That is worse than
 * no gate: it converts "nobody checked" into "somebody checked and it was fine".
 *
 * Separately, `quick-start.md` -- the first page a customer reads -- taught the
 * same retired flow and claimed it "works with any rclone-supported provider:
 * S3, R2, B2, OneDrive, Google Drive, SFTP". None of that was true any more.
 *
 * THE RULE, and the distinction that makes it decidable: a retired invocation
 * inside a FENCED CODE BLOCK is being taught, and is forbidden. The same string
 * in prose is allowed, because a doc must be able to say "this is retired and
 * now refuses" without tripping the check that enforces the retirement. Every
 * doc corrected in this wave does exactly that.
 *
 * WHAT IT DOES NOT COVER, stated plainly. It checks SOURCES, not rendered HTML,
 * so it cannot see a renderer that invents content. It was the source that was
 * wrong here, and checking sources costs no build; a rendered-HTML gate would
 * need a 67-second astro build to answer a question the source already answers.
 * It also cannot know a command is retired unless RETIRED lists it: this is a
 * manifest, and a retirement that does not add its pattern here is not covered.
 */

import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const REPO = path.resolve(import.meta.dirname, '..');
const RED = '\x1b[0;31m';
const GREEN = '\x1b[0;32m';
const NC = '\x1b[0m';

/**
 * Retired invocations, as patterns. Each entry names what replaced it, because
 * a gate that only says "no" makes the reader guess.
 *
 * These match the ARGUMENT SHAPE, not the verb alone: `rdc repo push` is alive
 * and well for machine targets, and only a storage destination is retired.
 */
const RETIRED: Array<{ pattern: RegExp; what: string; instead: string }> = [
  {
    pattern: /\brdc\s+repo\s+push\b[^\n]*--to\s+[<`'"]?(?:my-)?(?:storage|s3|r2|[a-z0-9-]*storage)\b/i,
    what: 'repo push to a storage destination',
    instead: '`rdc backup snapshot <repo>` (chunk store) or `rdc repo push <repo> --to <machine>`',
  },
  {
    pattern: /\brdc\s+repo\s+pull\b[^\n]*--from\s+[<`'"]?(?:my-)?(?:storage|s3|r2|[a-z0-9-]*storage)\b/i,
    what: 'repo pull from a storage source',
    instead: '`rdc backup restore <repo> --at <snapshot>` or `rdc repo pull <repo> --from <machine>`',
  },
  {
    pattern: /\brdc\s+backup\s+list\b[^\n]*--storage\b/i,
    what: 'backup list against a storage endpoint',
    instead: '`rdc backup manifests <repo-ref>`',
  },
];

/** Files a reader can end up looking at. */
function readerFacingSources(): string[] {
  return execFileSync(
    'git',
    [
      'ls-files',
      '--',
      'packages/www/src/content/docs/*',
      'packages/www/src/marp/*',
      'packages/www/src/i18n/translations/*',
      '.ci/tutorials/*',
    ],
    { cwd: REPO, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 }
  )
    .split('\n')
    .filter((f) => /\.(md|mdx|sh|json)$/.test(f));
}

export interface Finding {
  file: string;
  line: number;
  what: string;
  instead: string;
  text: string;
}

/**
 * Scan one file. Only lines INSIDE a fenced code block are judged, plus lines
 * inside a shell script that are not comments -- a tutorial script IS the
 * teaching, it has no fences.
 */
export function scanSource(file: string, body: string): Finding[] {
  const isScript = file.endsWith('.sh');
  // A translation JSON has no fences and no comments. Every string in it is
  // rendered to a reader, so any retired invocation there is being TAUGHT --
  // there is no "explaining the retirement" register to protect.
  //
  // This file type was added after the gate went green over docs while
  // `pages.solutionPages.backupVerification.bottomCta.command` shipped
  // `rdc backup list --storage backup-vault` in ALL 13 languages: a
  // customer-facing call to action, on the page about backup VERIFICATION,
  // naming a command that refuses. The gate was looking at the wrong files.
  const isTranslation = file.endsWith('.json');
  const findings: Finding[] = [];
  let fenced = false;

  body.split('\n').forEach((raw, i) => {
    const line = raw.trim();
    if (!isScript && /^(?:```|~~~)/.test(line)) {
      fenced = !fenced;
      return;
    }
    // A shell comment explaining the retirement is prose, not teaching.
    const teaching = isTranslation ? true : isScript ? !line.startsWith('#') : fenced;
    if (!teaching) return;

    for (const entry of RETIRED) {
      if (entry.pattern.test(raw)) {
        findings.push({
          file,
          line: i + 1,
          what: entry.what,
          instead: entry.instead,
          text: line.slice(0, 90),
        });
      }
    }
  });

  return findings;
}

function runControls(): string[] {
  const failures: string[] = [];

  const taught = ['# how to back up', '```bash', 'rdc repo push my-app --to my-storage', '```'].join(
    '\n'
  );
  if (scanSource('doc.md', taught).length === 0) {
    failures.push('a retired command inside a code fence was not caught');
  }

  // The case every corrected doc in this wave relies on.
  const explained = [
    'Pushing with `rdc repo push <repo> --to <storage>` is retired and now refuses.',
    'Use `rdc backup snapshot` instead.',
  ].join('\n');
  if (scanSource('doc.md', explained).length > 0) {
    failures.push('prose EXPLAINING the retirement was flagged; docs could not describe it');
  }

  const machine = ['```bash', 'rdc repo push my-app --to prod-2', '```'].join('\n');
  if (scanSource('doc.md', machine).length > 0) {
    failures.push('a machine-target push was flagged; only storage targets are retired');
  }

  const list = ['```bash', 'rdc backup list --storage my-s3', '```'].join('\n');
  if (scanSource('doc.md', list).length === 0) {
    failures.push('backup list --storage was not caught');
  }

  const script = ['#!/bin/bash', '# this used to run rdc repo push x --to my-storage', 'echo ok'].join(
    '\n'
  );
  if (scanSource('t.sh', script).length > 0) {
    failures.push('a shell COMMENT describing the retirement was flagged');
  }

  const scriptReal = ['#!/bin/bash', 'rdc repo push my-app --to my-storage'].join('\n');
  if (scanSource('t.sh', scriptReal).length === 0) {
    failures.push('a retired command in a runnable script line was not caught');
  }

  // The REAL string that shipped to 13 languages, verbatim. A translation JSON
  // has no fence to sit inside, so the fence rule alone would have missed it.
  const cta = '  "command": "rdc backup list --storage backup-vault",';
  if (scanSource('translations/en.json', cta).length === 0) {
    failures.push('a retired command in a translation VALUE was not caught');
  }
  // And the same string in a .md WITHOUT a fence must still be treated as prose,
  // so widening to JSON did not accidentally make every mention a finding.
  if (scanSource('doc.md', cta).length > 0) {
    failures.push('the JSON rule leaked into markdown: an unfenced mention was flagged');
  }

  return failures;
}

function main(): number {
  console.log('Reader-facing docs: does any of them still TEACH a retired command?');
  console.log('='.repeat(66));

  const controlFailures = runControls();
  if (controlFailures.length) {
    for (const f of controlFailures) console.log(`${RED}x${NC} control: ${f}`);
    console.log(`${RED}x${NC} the rule itself is broken, so no verdict it produces means anything.`);
    return 1;
  }
  console.log(
    `${GREEN}v${NC} control fired: taught commands caught in fences and scripts; prose and machine targets are not`
  );

  const files = readerFacingSources();
  if (files.length < 20) {
    console.log(
      `${RED}x${NC} only ${files.length} reader-facing source(s) found; the rule has been unhooked`
    );
    return 1;
  }

  const findings: Finding[] = [];
  for (const file of files) {
    try {
      findings.push(...scanSource(file, readFileSync(path.join(REPO, file), 'utf8')));
    } catch {
      /* unreadable files are not evidence */
    }
  }

  if (findings.length) {
    for (const f of findings) {
      console.log(`${RED}x${NC} ${f.file}:${f.line}: teaches ${f.what}`);
      console.log(`    ${f.text}`);
      console.log(`    use instead: ${f.instead}`);
    }
    console.log();
    console.log(`${RED}x${NC} ${findings.length} doc line(s) teach a command the engine refuses.`);
    console.log('  A reader copies the command, not the caveat. Prose may EXPLAIN a retirement;');
    console.log('  a code fence or a runnable script line may not teach one.');
    return 1;
  }

  console.log(
    `${GREEN}v${NC} ${files.length} reader-facing source(s): none teaches a retired command`
  );
  return 0;
}

process.exit(main());
