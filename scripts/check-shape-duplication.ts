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
 *   - IMPORT BLOCKS. Three files importing the same helper is ADOPTION, not duplication:
 *     an import statement IS the consolidation. This gate caught itself on this within an
 *     hour of landing -- moving five gates onto `utils/console.js` created a shared
 *     import preamble in three of them and the gate reported it, which would have
 *     discouraged exactly the consolidation it exists to encourage.
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
import { validateBlockerQuality } from './lib/blocker-validator.js';
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
export interface NormLine {
  /** The line's number in the ORIGINAL file, 1-based. */
  line: number;
  text: string;
}

export function normalise(src: string, kind: 'ts' | 'sh'): NormLine[] {
  let s = src;
  if (kind === 'ts') {
    // Replaced with its own newlines, not with nothing: swallowing them would renumber
    // every line after a JSDoc block.
    s = s.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ''));
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
  // THE LINE NUMBER IS CARRIED, and its absence was a real bug rather than a nicety.
  // Comment-stripping blanks a line and the filter below then DROPS it, so the index into
  // this array is not the index into the file -- every earlier `file:line` this gate
  // emitted was a normalised-array position wearing a file line's clothes. Measured
  // 2026-09-01 on `.ci/scripts/test/gates/test-watchdog-log-capture.sh`: a finding
  // reported at `:17` actually sits at file line 46. A finding whose coordinate points
  // somewhere else is a finding nobody can act on.
  //
  // Comment-stripping must therefore preserve the LINE COUNT, so a multi-line `/* */`
  // block cannot swallow the newlines that separate the code after it from the code
  // before it.
  return s
    .split('\n')
    .map((l, i): NormLine => ({ line: i + 1, text: l.replace(/\s+/g, ' ').trim() }))
    .filter((l) => l.text.length > 0);
}

const hash = (s: string) => createHash('sha1').update(s).digest('hex').slice(0, 12);

/** An import, a require, or a shell `source` -- the line that USES a shared module. */
export function isImportish(line: string): boolean {
  return /^(import\b|export .*\bfrom\b|const .*=\s*require\(|source |\. )/.test(line);
}

/**
 * A line whose whole content is a MESSAGE, once the string is normalised away.
 *
 * THIS GATE PROMISED THIS EXCLUSION AND DID NOT IMPLEMENT IT FOR SHELL. The docstring
 * above says the findings report is never counted -- "the sentence telling a reader what
 * failed and why IS the gate's value" -- and that held for TypeScript, where a report is
 * built from template literals inside distinguishable code. In shell the idiom is bare
 * `echo "..." >&2`, and string normalisation collapses EVERY such line to `echo "S" >&2`.
 * Four consecutive ones plus a `fi` therefore hash identically no matter what they say.
 *
 * Caught on its author, 2026-09-01, and it is the strongest possible demonstration of the
 * defect: the gate reported `check-control-vacuity.sh`, `block-untagged-commit.sh` and
 * `block-unverified-push.sh` as sharing a shape. They share nothing but the ACT of
 * printing four lines to stderr; their messages are three unrelated explanations, and
 * consolidating them would delete the only part that has value.
 *
 * Same treatment as an import preamble, for the same reason: it is a majority test, so a
 * genuine shared span that happens to contain one echo still registers.
 */
export function isMessageish(line: string): boolean {
  // The `>&2` redirect is part of the idiom, so `&` cannot be excluded wholesale -- the
  // first cut did that and matched nothing, which is why this carries a control.
  return /^(echo|printf|print|console\.(log|error|warn))\b[^|;]*$/.test(line);
}

/**
 * Every sliding WINDOW-line span, minus the ones that are mostly imports.
 *
 * A window over an import preamble is not duplicated logic; it is three files agreeing to
 * use the same module, which is the outcome this gate wants. Majority rather than any,
 * so a genuine shared span that happens to start one line into an import block still
 * registers.
 */
export function windows(lines: NormLine[]): { h: string; line: number }[] {
  const out: { h: string; line: number }[] = [];
  for (let i = 0; i + WINDOW <= lines.length; i++) {
    const slice = lines.slice(i, i + WINDOW);
    if (slice.filter((l) => isImportish(l.text)).length * 2 > WINDOW) continue;
    if (slice.filter((l) => isMessageish(l.text)).length * 2 > WINDOW) continue;
    // The window's line is the REAL file line its first row came from.
    out.push({ h: hash(slice.map((l) => l.text).join('\n')), line: slice[0].line });
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
        normalise('const m = "dead css found";', 'ts')[0].text ===
        normalise('const m = "dead keys found";', 'ts')[0].text,
    },
    {
      name: `CONTROL: a ${WINDOW - 1}-line file yields no window, so a one-liner cannot fire`,
      ok: windows(normalise('a\nb\nc\nd', 'ts')).length === 0,
    },
    {
      name: 'an accepted divergence with a real BLOCKER is honoured',
      ok:
        checkAccepted({
          abc123: 'BLOCKER: run_gate() has three incompatible return contracts (echo rc, echo PASS/FAIL, propagate); extracting it verbatim would be wrong',
        }).ok.length === 1,
    },
    {
      name: 'CONTROL: a low-effort BLOCKER buys no silence',
      ok: checkAccepted({ abc123: 'BLOCKER: tbd' }).ok.length === 0,
    },
    {
      // The reason here is deliberately LONG and substantive, so the only rule that can
      // reject it is the prefix rule. The first version of this control used a 28-char
      // reason, which `validateBlockerQuality` rejects for length alone -- it passed with
      // the prefix check deleted, which is a control that cannot fail.
      name: 'CONTROL: a reason without the BLOCKER: prefix buys no silence',
      ok:
        checkAccepted({
          abc123: 'run_gate() has three incompatible return contracts (echo rc, echo PASS/FAIL, propagate); extracting it verbatim would be wrong',
        }).ok.length === 0,
    },
    {
      // THE COORDINATE MUST BE A FILE LINE. Comment-stripping drops lines, so the index
      // into the normalised array is not the index into the file. Before this, a finding
      // in `test-watchdog-log-capture.sh` reported `:17` for code sitting at line 46.
      name: 'a finding names the REAL file line, not the normalised index',
      ok: (() => {
        const src = '// a\n// b\n// c\nconst a = 1;\nconst b = 2;\nconst c = 3;\nconst d = 4;\nconst e = 5;';
        return normalise(src, 'ts')[0].line === 4 && windows(normalise(src, 'ts'))[0].line === 4;
      })(),
    },
    {
      name: 'CONTROL: a block comment does not renumber the code after it',
      ok: normalise('/* a\n b\n c */\nconst z = 1;', 'ts')[0].line === 4,
    },
    {
      // THE GATE CAUGHT ITS AUTHOR ON THIS. String literals normalise to "S", so four
      // consecutive stderr messages hash identically no matter what they SAY. It reported
      // check-control-vacuity.sh, block-untagged-commit.sh and block-unverified-push.sh as
      // one shape; they share only the ACT of printing, and consolidating them would
      // delete three unrelated explanations -- the findings report this gate's own
      // docstring promises never to count.
      name: 'CONTROL: four stderr messages are a report, not a shared shape',
      ok: (() => {
        const body =
          'if [ -n "$x" ]; then\n' +
          '  echo "a" >&2\n  echo "b" >&2\n  echo "c" >&2\n  echo "d" >&2\nfi';
        const per = new Map(
          ['f1', 'f2', 'f3'].map((f): [string, { h: string; line: number }[]] => [
            f,
            windows(normalise(body, 'sh')),
          ])
        );
        return judge(per, new Set()).length === 0;
      })(),
    },
    {
      name: 'the message matcher takes a stderr redirect and rejects a pipe or plain code',
      ok:
        isMessageish('echo "S" >&2') &&
        isMessageish('printf "S"') &&
        !isMessageish('fi') &&
        !isMessageish('echo "S" | grep x') &&
        !isMessageish('const a = 1;'),
    },
    {
      name: 'CONTROL: an import preamble is adoption, not duplication',
      ok: (() => {
        const imports = [
          "import a from 'x';",
          "import b from 'y';",
          "import c from 'z';",
          'const R = 1;',
          'const S = 2;',
        ].join('\n');
        return judge(
          new Map(
            Array.from({ length: N }, (_, i): [string, { h: string; line: number }[]] => [
              `f${i}.ts`,
              windows(normalise(imports, 'ts')),
            ])
          ),
          new Set()
        ).length === 0;
      })(),
    },
    {
      name: 'CONTROL: but a real span next to imports still fires',
      ok: (() => {
        const mixed = [
          "import a from 'x';",
          'const p = 1;',
          'const q = 2;',
          'const r = 3;',
          'const s = 4;',
          'const t = 5;',
        ].join('\n');
        return judge(
          new Map(
            Array.from({ length: N }, (_, i): [string, { h: string; line: number }[]] => [
              `f${i}.ts`,
              windows(normalise(mixed, 'ts')),
            ])
          ),
          new Set()
        ).length === 1;
      })(),
    },
    {
      name: 'CONTROL: a file declaring it stands apart is excluded from the corpus',
      ok: !tracked().some((f) => readFileSync(path.join(ROOT, f), 'utf8').includes(OPT_OUT)),
    },
  ];
}

/**
 * The pure half of the `accepted` check, split out so the controls drive the REAL
 * validation rather than a reimplementation of it -- the same reason `normalise`, `windows`
 * and `judge` are exported.
 */
export function checkAccepted(accepted: Record<string, string>): { ok: string[]; bad: string[] } {
  const ok: string[] = [];
  const bad: string[] = [];
  for (const [h, reason] of Object.entries(accepted)) {
    if (!/^BLOCKER:/i.test(reason)) {
      bad.push(`  ${h}: reason does not start with "BLOCKER:"`);
      continue;
    }
    const fail = validateBlockerQuality(h, reason.replace(/^BLOCKER:\s*/i, ''), SEED_FILE);
    if (fail) bad.push(fail.message);
    else ok.push(h);
  }
  return { ok, bad };
}

/**
 * The silence set: the standing backlog PLUS the shapes a person judged not one thing.
 *
 * THE SECOND HALF IS AN EXIT THIS GATE DID NOT HAVE, and its absence was a real defect
 * rather than a missing nicety. The judged rule next door (`wl_shapedup.py`) has three
 * answers -- yes, already, and `no` with a named DIVERGENCE -- because `run_gate()` really
 * is duplicated 23 times across three incompatible return contracts and extracting it
 * verbatim would be wrong. This gate had only two: consolidate, or stay red forever. The
 * only way out was re-running `--seed`, which absorbs EVERY new shape at once, so the sole
 * exit from a legitimate divergence was a command that silently suppresses the whole gate.
 *
 * So `accepted` is the repo's ordinary escape hatch, held to the ordinary rule: a
 * `BLOCKER:` reason, validated by the SAME `validateBlockerQuality` every other allowlist
 * uses (30-char minimum, banned-phrase list). Writing a second reason-checker here is the
 * exact duplication this gate exists to catch.
 *
 * `shapes` carries no reasons and should not: it is one measurement taken at install, the
 * same shape as `wl_reggate.py:130` hashing every existing check script so only new ones
 * count. `accepted` is per-entry judgement, and judgement is what needs a reason.
 */
function loadSeed(): { silent: Set<string>; accepted: number } {
  if (!existsSync(SEED_FILE)) return { silent: new Set(), accepted: 0 };
  const raw = JSON.parse(readFileSync(SEED_FILE, 'utf8')) as {
    shapes?: string[];
    accepted?: Record<string, string>;
  };
  const silent = new Set(raw.shapes ?? []);
  const { ok, bad } = checkAccepted(raw.accepted ?? {});
  for (const h of ok) silent.add(h);
  const accepted = ok.length;
  if (bad.length > 0) {
    console.error(`${RED}✗${NC} ${bad.length} accepted divergence(s) carry no usable BLOCKER:`);
    for (const b of bad) console.error(b);
    process.exit(1);
  }
  return { silent, accepted };
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
    // RE-SEEDING IS GATE SUPPRESSION, so it is not a routine command. A second `--seed`
    // absorbs every shape that has reached N copies since install -- including the
    // genuine duplication this gate exists to report -- and leaves no record that it
    // did. The exit for a shape that is legitimately not one thing is `accepted` with a
    // BLOCKER, one entry at a time, which is reviewable. This refuses rather than warns.
    if (existsSync(SEED_FILE) && !argv.includes('--force')) {
      console.error(
        `${RED}✗${NC} a seed already exists at ${SEED_FILE}.\n` +
          '    Re-seeding silences every shape that reached N copies since install, with no\n' +
          '    record of what was silenced. To accept ONE shape as legitimately divergent,\n' +
          '    add it to `accepted` with a BLOCKER reason instead. --force overrides.'
      );
      process.exit(1);
    }
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

  const { silent: seed, accepted } = loadSeed();
  if (seed.size === 0) {
    console.error(`${RED}✗${NC} no seed at ${SEED_FILE}; run --seed once, and commit it.`);
    console.error('    Without it every pre-existing shape reports as new.');
    process.exit(1);
  }

  const findings = judge(perFile, seed);

  // MACHINE-READABLE, for the stop-hook rule that asks the judged half of this question.
  // `wl_shapedup.py` needs the file:line spans as data; parsing them back out of the
  // human report would be a second, undeclared interface to the same answer.
  if (argv.includes('--json')) {
    console.log(JSON.stringify({ n: N, window: WINDOW, seeded: seed.size, findings }));
    return;
  }

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
      `${seed.size - accepted} seeded + ${accepted} accepted shape(s); ` +
      `no NEW shape has reached ${N} copies`
  );
}

// ENTRY-POINT GUARD, and it is not decoration. This module exports `normalise`, `windows`,
// `judge` and `coalesce` so a consumer can drive the REAL judgement rather than a
// reimplementation -- and until this line existed, importing any of them ran a full
// 320-file scan as a side effect and printed the gate's verdict. Found by doing exactly
// that from the calibration replay.
//
// The other 23 `scripts/check-*.ts` that both export and call `main()` bare are left
// alone deliberately: swept 2026-09-01, NONE of them is imported anywhere (the apparent
// hits in `ci-runner/manifest.ts` are script-name strings, not imports). This one is the
// only member of the class with a consumer, so it is the only one where the defect is
// live rather than latent.
if (process.argv[1] && import.meta.filename === path.resolve(process.argv[1])) {
  main();
}
