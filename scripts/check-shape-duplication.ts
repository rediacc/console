#!/usr/bin/env tsx
/**
 * The Nth copy of a shape is a finding. This counts them.
 *
 * THE QUESTION NOBODY ASKS. The stop-gate judge asks "did you sweep the class?" and "is
 * there a gate?". Neither asks "is this the third copy of something you already have?", so
 * every finding correctly answers "add a script + a manifest entry + a workflow step", and
 * nothing is ever pointed at the accumulated surface.
 *
 * This repo reached that conclusion twice by hand and wrote it down both times --
 * `scripts/lib/shrink-only-baseline.ts:25-31` ("a class, not an instance… seven chances to
 * drift") and `.claude/hooks/pre-bash/block-adhoc-sanctioned.sh:4-8` (a new class is "a row
 * rather than a 22nd copy of this file"). Both were noticed by a person.
 *
 * SEEDED, AND THAT IS THE WHOLE DESIGN -- decisively so, once it was measured. The plan
 * estimated ~9 pre-existing shapes past three copies, from the nine LARGEST spans a survey
 * had named. Run unseeded over the four families this gate scans, the real number is
 * **219 spans** (336 raw windows before coalescing), the biggest at 21 copies.
 *
 * A gate reporting 219 findings on its first run is not a gate, it is a wall, and it would
 * be 219 blocks of the "inexhaustible supply of hook-satisfying non-work" this repo already
 * has a scar from. So today's fingerprints are SEEDED into a baseline and stay silent; the
 * gate fires only when a shape that was NOT already here reaches its Nth copy.
 *
 * The 219 are a real and much larger backlog than the plan assumed, and that is worth
 * saying plainly rather than burying: draining them is its own measured piece of work, and
 * the number should decide how much of it is worth doing.
 *
 * The same trick is already in the tree: `wl_reggate.py:130` hashes every existing check
 * script at marker init "so only new ones count".
 *
 * WHAT IS DELIBERATELY NOT COUNTED, each forced by a measurement:
 *
 *   - COMMENTS. Family C (`block-*.sh`) is 52% comments, and those comments are the
 *     incident histories the guards exist for. Any raw-similarity metric ranks prose first
 *     and creates pressure to delete exactly the lines that make a green mean something.
 *   - THE FINDINGS REPORT. Measured across ten gates: ten distinct shapes. The sentence
 *     telling a reader what failed and why IS the gate's value. Duplication is counted in
 *     the scaffolding, never in the reasons.
 *   - ONE-LINERS. The repo-root resolution appears in 79 files with 18 spellings. At a
 *     window of 1 it drowns every real signal; the 5-line window excludes it by
 *     construction, and a fix there would be churn across 79 files for no drift risk.
 *   - WRITTEN DECISIONS. `block-ci-polling.sh:19` says "NOT ROUTED THROUGH
 *     lib/command-scan.sh, and that is a decision". A counter that fires on a recorded
 *     decision is noise, so an opt-out marker excludes the file.
 *
 * DEVIATION FROM THE APPROVED PLAN, stated rather than buried. The plan said to normalise
 * identifiers to their kind. This does NOT: it strips comments and string literals and
 * collapses whitespace, and stops there. The measured clusters this gate is calibrated
 * against -- 8, 9 and 8 byte-identical instances -- were found WITHOUT identifier
 * normalisation, so shipping without it matches the evidence. Identifier normalisation is
 * strictly more aggressive and would need its own calibration before it could be trusted;
 * it can be added later behind the same seed.
 *
 * Usage:
 *   npx tsx scripts/check-shape-duplication.ts [--selftest]
 *   npx tsx scripts/check-shape-duplication.ts --seed    # rewrite the baseline
 */
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { runControls } from './lib/controls.js';
import { GREEN, NC, RED } from './utils/console.js';

const ROOT = path.resolve(import.meta.dirname, '..');
const SEED_FILE = path.join(ROOT, 'scripts/data/shape-duplication-seed.json');

/** The Nth copy. Justified from the measured distribution, not from tradition. */
export const N = 3;
/** Below 5 the 79-file one-liner dominates; above 8 two real spans vanish entirely. */
export const WINDOW = 5;
/** A file saying it deliberately stands apart is not a copy to collapse. */
const OPT_OUT = 'NOT ROUTED THROUGH';

const FAMILIES = [
  'scripts/check-*.ts',
  '.ci/scripts/quality/check-*.sh',
  '.ci/scripts/test/gates/test-*.sh',
  '.claude/hooks/pre-bash/block-*.sh',
];

/**
 * Comments and string literals out, whitespace collapsed, blanks dropped.
 *
 * Exported so the controls exercise the SAME function the tree goes through. A control
 * that runs a reimplementation proves nothing.
 */
export function normalise(src: string, kind: 'ts' | 'sh'): string[] {
  let s = src;
  if (kind === 'ts') {
    s = s.replace(/\/\*[\s\S]*?\*\//g, '');
    s = s.replace(/(^|[^:])\/\/.*$/gm, '$1');
  } else {
    // A leading-hash line only. A trailing `# ...` can live inside a string or a regex,
    // and guessing wrong changes the code rather than the comment.
    s = s.replace(/^\s*#.*$/gm, '');
  }
  // String literals become one token, so two copies differing only in their message
  // still register as the same scaffolding.
  s = s.replace(/'(?:[^'\\]|\\.)*'/g, "'S'");
  s = s.replace(/"(?:[^"\\]|\\.)*"/g, '"S"');
  s = s.replace(/`(?:[^`\\]|\\.)*`/g, '`S`');
  return s
    .split('\n')
    .map((l) => l.replace(/\s+/g, ' ').trim())
    .filter((l) => l.length > 0);
}

const hash = (s: string) => createHash('sha1').update(s).digest('hex').slice(0, 12);

/** Every sliding WINDOW-line span of a normalised file, as (hash, firstLine). */
export function windows(lines: string[], startLine = 1): { h: string; line: number }[] {
  const out: { h: string; line: number }[] = [];
  for (let i = 0; i + WINDOW <= lines.length; i++) {
    out.push({ h: hash(lines.slice(i, i + WINDOW).join('\n')), line: startLine + i });
  }
  return out;
}

export interface Finding {
  shape: string;
  files: string[];
  /** How many overlapping windows were merged into this one span. */
  span: number;
}

/**
 * Overlapping windows over ONE shared span are one finding, not twenty-four.
 *
 * A 28-line span shared by four files produces 24 sliding windows, each with the same file
 * set and consecutive start lines. Reporting them separately turned a real measurement --
 * 336 windows on this tree -- into a number that describes the window size rather than the
 * duplication, and an operator reading it would have to do the division themselves.
 *
 * Two windows merge when they name the SAME files and their start lines are within one
 * window of each other in every file. Same-files is the strict half: two genuinely
 * different spans that happen to sit adjacent in one file will differ in the others.
 */
export function coalesce(findings: Finding[]): Finding[] {
  const byFileSet = new Map<string, Finding[]>();
  for (const f of findings) {
    const key = f.files.map((x) => x.split(':')[0]).join('|');
    const g = byFileSet.get(key);
    if (g) g.push(f);
    else byFileSet.set(key, [f]);
  }
  const out: Finding[] = [];
  for (const group of byFileSet.values()) {
    const sorted = [...group].sort(
      (a, b) => Number(a.files[0].split(':')[1]) - Number(b.files[0].split(':')[1])
    );
    let cur = sorted[0];
    let merged = 1;
    for (const f of sorted.slice(1)) {
      const prev = Number(cur.files[0].split(':')[1]) + merged - 1;
      if (Number(f.files[0].split(':')[1]) - prev <= WINDOW) merged += 1;
      else {
        out.push({ ...cur, span: merged + WINDOW - 1 });
        cur = f;
        merged = 1;
      }
    }
    out.push({ ...cur, span: merged + WINDOW - 1 });
  }
  return out.sort((a, b) => b.files.length * b.span - a.files.length * a.span);
}

/**
 * Which shapes have reached N copies and were not already here.
 *
 * `seed` is the set of hashes present when the gate was installed. Exported and pure, so
 * the controls drive the real judgement.
 */
export function judge(
  perFile: Map<string, { h: string; line: number }[]>,
  seed: Set<string>
): Finding[] {
  const byShape = new Map<string, Map<string, number>>();
  for (const [file, ws] of perFile) {
    for (const w of ws) {
      if (seed.has(w.h)) continue;
      let m = byShape.get(w.h);
      if (!m) byShape.set(w.h, (m = new Map()));
      if (!m.has(file)) m.set(file, w.line);
    }
  }
  const findings: Finding[] = [];
  for (const [h, files] of byShape) {
    if (files.size < N) continue;
    findings.push({
      shape: h,
      files: [...files].map(([f, l]) => `${f}:${l}`).sort(),
      span: WINDOW,
    });
  }
  return coalesce(findings);
}

function tracked(): string[] {
  const all = execFileSync('git', ['ls-files', ...FAMILIES], { cwd: ROOT, encoding: 'utf8' })
    .split('\n')
    .filter(Boolean);
  return all.filter((f) => {
    const src = readFileSync(path.join(ROOT, f), 'utf8');
    return !src.includes(OPT_OUT);
  });
}

function scan(files: string[]): Map<string, { h: string; line: number }[]> {
  const m = new Map<string, { h: string; line: number }[]>();
  for (const f of files) {
    const kind = f.endsWith('.ts') ? 'ts' : 'sh';
    m.set(f, windows(normalise(readFileSync(path.join(ROOT, f), 'utf8'), kind)));
  }
  return m;
}

/** Controls, each the real defect or the real non-defect, reconstructed. */
function controls(): { name: string; ok: boolean; detail?: string }[] {
  const mk = (n: number, body: string) =>
    new Map(
      Array.from({ length: n }, (_, i): [string, { h: string; line: number }[]] => [
        `f${i}.ts`,
        windows(normalise(body, 'ts')),
      ])
    );
  const SPAN = `const a = 1;\nconst b = 2;\nconst c = 3;\nconst d = 4;\nconst e = 5;`;
  const empty = new Set<string>();

  return [
    {
      name: `${N} files sharing a ${WINDOW}-line span is a finding`,
      ok: judge(mk(N, SPAN), empty).length === 1,
    },
    {
      name: `CONTROL: ${N - 1} files sharing it is not`,
      ok: judge(mk(N - 1, SPAN), empty).length === 0,
    },
    {
      name: 'CONTROL: a seeded shape stays silent however many copies it has',
      ok: (() => {
        const per = mk(N + 5, SPAN);
        const seed = new Set(windows(normalise(SPAN, 'ts')).map((w) => w.h));
        return judge(per, seed).length === 0;
      })(),
    },
    {
      name: 'the finding names every file, with a line',
      ok: judge(mk(N, SPAN), empty)[0]?.files.length === N &&
        /^f0\.ts:\d+$/.test(judge(mk(N, SPAN), empty)[0].files[0]),
    },
    {
      name: 'CONTROL: comments are not code, so a shared prose header is not a copy',
      ok: normalise('// a\n// b\n// c\n// d\n// e\nconst x = 1;', 'ts').length === 1,
    },
    {
      name: 'CONTROL: a shell prose header is not a copy either',
      ok: normalise('# a\n# b\n# c\n# d\n# e\nx=1', 'sh').length === 1,
    },
    {
      name: 'two gates whose only difference is their message are the same scaffolding',
      ok:
        normalise('const m = "dead css found";', 'ts')[0] ===
        normalise('const m = "dead keys found";', 'ts')[0],
    },
    {
      name: `CONTROL: a ${WINDOW - 1}-line file yields no window, so a one-liner cannot fire`,
      ok: windows(normalise('a\nb\nc\nd', 'ts')).length === 0,
    },
    {
      name: 'CONTROL: a file declaring it stands apart is excluded from the corpus',
      ok: !tracked().some((f) => readFileSync(path.join(ROOT, f), 'utf8').includes(OPT_OUT)),
    },
  ];
}

function loadSeed(): Set<string> {
  if (!existsSync(SEED_FILE)) return new Set();
  const raw = JSON.parse(readFileSync(SEED_FILE, 'utf8')) as { shapes?: string[] };
  return new Set(raw.shapes ?? []);
}

function main(): void {
  const argv = process.argv.slice(2);

  if (argv.includes('--selftest')) {
    const failed = runControls(controls());
    if (failed > 0) {
      console.error(`${RED}✗${NC} a control did not behave, so this gate cannot be trusted`);
      process.exit(1);
    }
  }

  const files = tracked();
  const perFile = scan(files);

  // FLOORS. Either means the scan is broken, and a broken scan reports a confident green
  // having verified nothing -- the exact failure this repo gates against.
  if (files.length < 200) {
    console.error(
      `${RED}✗${NC} only ${files.length} file(s) in the corpus; the globs are broken or the tree moved`
    );
    process.exit(1);
  }
  const totalWindows = [...perFile.values()].reduce((n, w) => n + w.length, 0);
  if (totalWindows < 5000) {
    console.error(`${RED}✗${NC} only ${totalWindows} window(s) hashed; normalisation is broken`);
    process.exit(1);
  }

  if (argv.includes('--seed')) {
    // ONLY the shapes that have ALREADY reached N copies. Seeding every hash in the tree
    // was the first attempt and it is wrong twice over: a 708 KB artifact, and -- the part
    // that matters -- it would suppress a line that exists ONCE today and gets copied
    // twice tomorrow. That is new duplication, exactly what this gate is for, and it would
    // have been silenced forever. Seeding the standing backlog and nothing else keeps the
    // 1 -> 2 -> 3 transition live.
    const shapes = new Set<string>();
    const counts = new Map<string, Set<string>>();
    for (const [file, ws] of perFile) {
      for (const w of ws) {
        let f = counts.get(w.h);
        if (!f) counts.set(w.h, (f = new Set()));
        f.add(file);
      }
    }
    for (const [h, f] of counts) if (f.size >= N) shapes.add(h);
    writeFileSync(
      SEED_FILE,
      `${JSON.stringify({ generated: new Date().toISOString().slice(0, 10), files: files.length, shapes: [...shapes].sort() }, null, 2)}\n`
    );
    console.log(`seeded ${shapes.size} shape(s) from ${files.length} file(s) -> ${SEED_FILE}`);
    return;
  }

  const seed = loadSeed();
  if (seed.size === 0) {
    console.error(`${RED}✗${NC} no seed at ${SEED_FILE}; run --seed once, and commit it.`);
    console.error('    Without it every pre-existing shape reports as new.');
    process.exit(1);
  }

  const findings = judge(perFile, seed);
  if (findings.length > 0) {
    console.error(`${RED}✗${NC} ${findings.length} NEW shape(s) have reached ${N} copies:\n`);
    for (const f of findings) {
      console.error(`  ~${f.span} lines x ${f.files.length} copies:`);
      for (const loc of f.files) console.error(`    ${loc}`);
    }
    console.error(
      '\n  Either extract the shared piece, or say which DIVERGENCE makes them not one' +
        '\n  thing (the way `run_gate()` has three incompatible return contracts).' +
        '\n  Triage it: .claude/hooks/stop/worklist.py --triage <you> "<the finding>"'
    );
    process.exit(1);
  }

  console.log(
    `${GREEN}✓${NC} shape duplication: ${files.length} file(s), ${totalWindows} window(s), ` +
      `${seed.size} seeded shape(s); no NEW shape has reached ${N} copies`
  );
}

main();
