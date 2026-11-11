/**
 * Control for scripts/gen/generate-translation-hashes.ts (`npm run i18n:generate-hashes`).
 *
 * The generator restamped `$meta.sourceCommit` in manifests whose hashes had not changed.
 * Pinned here: (1) a second run with no source change leaves every manifest byte-identical,
 * even when the latest commit moved; (2) changing one www string rewrites only the www manifest;
 * (3) the control: the pre-fix behaviour (always write) is run through assertion 1 and MUST fail it.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  type LocaleConfig,
  processLocaleDir,
  writeHashManifest,
} from '../gen/generate-translation-hashes.ts';

const fail = (m: string): never => {
  console.error(`FAIL: ${m}`);
  process.exit(1);
};

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hashes-control-'));
const put = (rel: string, text: string) => {
  const p = path.join(root, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, text);
};
put('www/en.json', '{"a":"one","b":"two"}\n');
put('cli/en/cli.json', '{"x":"ex"}\n');

const configs: LocaleConfig[] = [
  { name: 'www', dir: path.join(root, 'www'), multipleNamespaces: false, flatFiles: true },
  { name: 'cli', dir: path.join(root, 'cli'), multipleNamespaces: false },
];
const manifestPath = (c: LocaleConfig) => path.join(c.dir, '.translation-hashes.json');

let counter = 0;
// Every call answers a NEW commit, like a git log whose latest commit moved.
const nextCommit = () => `commit-${++counter}`;

function run(write: typeof writeHashManifest): void {
  for (const c of configs) {
    const hashes = processLocaleDir(c);
    if (!hashes) fail(`no hashes for ${c.name}`);
    else write(c.dir, hashes, c.name, c, nextCommit);
  }
}
const snapshot = () => configs.map((c) => fs.readFileSync(manifestPath(c), 'utf-8'));
const same = (a: string[], b: string[]) => a.every((t, i) => t === b[i]);

const quiet = console.log;
console.log = () => undefined;
try {
  run(writeHashManifest);
  const first = snapshot();
  if (!first[0].includes('commit-1')) fail('first run did not stamp a sourceCommit');

  run(writeHashManifest);
  if (!same(first, snapshot())) fail('second run with no source change altered a manifest');

  put('www/en.json', '{"a":"one","b":"changed"}\n');
  run(writeHashManifest);
  const third = snapshot();
  if (first[0] === third[0]) fail('changed www string did not update the www manifest');
  if (!third[0].includes('commit-')) fail('www manifest lost its sourceCommit');
  if (first[1] !== third[1]) fail('changing a www string altered the cli manifest');

  // Control: the pre-fix writer (always restamp) must trip the idempotence assertion.
  const preFix: typeof writeHashManifest = (dir, hashes, _n, _c, resolve) => {
    const p = path.join(dir, '.translation-hashes.json');
    // tree-write: safe p is under a dir the control's own mkdtemp (os.tmpdir()) root handed in, never the tree
    fs.writeFileSync(p, JSON.stringify({ $meta: { sourceCommit: resolve?.(dir) }, hashes }));
    return p;
  };
  run(preFix);
  const before = snapshot();
  run(preFix);
  if (same(before, snapshot())) fail('control did not detect restamping: the test cannot fail');
} finally {
  console.log = quiet;
  fs.rmSync(root, { recursive: true, force: true });
}
console.log('OK: unchanged manifests stay byte-identical; control detects the pre-fix restamp');
