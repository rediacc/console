#!/usr/bin/env node
/**
 * Validates parity across the four sources that describe a tutorial:
 *   - cast file (recorded session, labeled markers = commands)
 *   - storyboard.json (scene order, marker indices, command snippets)
 *   - transcript JSON per language (event narration, cardLabel, chapters, title)
 *   - markdown/mdx docs page (must reference every cast-narrated step exactly once)
 *
 * Fails (exit 1) if any source drifts from the canonical recorded count or
 * misses a required field. Runs in CI via the quality-tutorial-parity job.
 */

import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { markerTimestamps, parseCast } from './lib/cast-splitter.ts';
import { rdcCommandPath } from './lib/cli-reference-catalog.js';
import { readStoryboard } from './lib/storyboard.ts';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const wwwRoot = path.resolve(scriptDir, '..');
const storyboardDir = path.join(wwwRoot, 'src', 'data', 'tutorial-storyboard');
const transcriptDir = path.join(wwwRoot, 'src', 'data', 'tutorial-transcripts');
const castDir = path.join(wwwRoot, 'public', 'assets', 'tutorials');
const docsDir = path.join(wwwRoot, 'src', 'content', 'docs', 'en');
const baselinePath = path.join(scriptDir, 'tutorial-parity-baseline.json');

// A storyboard command that disagrees with the recorded marker it narrates. Carries both
// texts so the backlog below can defer ONE known pair without muting the class.
interface Drift {
  key: string;
  commandFull: string;
  recorded: string;
}

interface Issue {
  tutorial: string;
  file: string;
  message: string;
  drift?: Drift;
}

type Baseline = Record<string, { commandFull: string; recorded: string }>;

function isAuthored(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0 && !value.startsWith('TODO:');
}

// The command "path" — used to assert a storyboard's full command matches the
// recorded cast command without requiring identical argument *values* (the web
// page templates them, e.g. `<machine-name>` vs recorded `machine-11`).
//
// For `rdc` this is resolved against the real command tree. It used to be
// guessed as "leading tokens up to the first `-` or `<`", which held only while
// every target was a flag. Once the CLI moved to positional refs the guess broke
// in a way that pointed at the wrong culprit: `rdc machine add <machine-name>`
// stopped at the placeholder (path `rdc machine add`) while the recording
// `rdc machine add machine-11` swallowed the value (path `rdc machine add
// machine-11`), so identical commands "differed". Every such pair — 68 of them —
// was then absorbed into the baseline as if the storyboards were at fault.
function commandPath(cmd: string): string {
  const rdcPath = rdcCommandPath(cmd);
  if (rdcPath !== null) return rdcPath;
  // Not an rdc command (ssh, docker, …): fall back to leading non-flag tokens.
  const out: string[] = [];
  for (const tok of cmd.trim().split(/\s+/)) {
    if (tok.startsWith('-') || tok.startsWith('<')) break;
    out.push(tok);
  }
  return out.join(' ');
}

// Suggested long form for the short flags tutorials use on rdc commands.
const SHORT_FLAG_LONG: Record<string, string> = {
  '-m': '--machine',
  '-r': '--repository',
  '-c': '--command (or --container for `repo tunnel`)',
};

// rdc commands must read self-documentingly: a short flag is allowed ONLY when
// its value is a `<placeholder>` (which names the flag), e.g. `-m <machine-name>`.
// A short flag followed by a literal value (e.g. `-r my-app`) is opaque and must
// use the long form. Standard shell tools (ssh, ssh-keygen, ls, cat, …) are exempt.
// Returns the first offending flag, or null. `cmd` may be a recorded cast marker
// or a card.commandFull string.
function rdcShortFlagViolation(cmd: string): { flag: string; suggestion: string } | null {
  const tokens = cmd.trim().split(/\s+/);
  // Skip harmless leading wrappers (`timeout 2s rdc …`, `sudo rdc …`).
  let i = 0;
  while (i < tokens.length && tokens[i] !== 'rdc') {
    if (tokens[i] === 'timeout' || tokens[i] === 'sudo' || /^\d+s?$/.test(tokens[i])) {
      i++;
      continue;
    }
    break;
  }
  if (tokens[i] !== 'rdc') return null; // not an rdc invocation — exempt
  for (let j = i + 1; j < tokens.length; j++) {
    // Everything after --command (or a -c payload) is the REMOTE command —
    // shell idioms like `df -h .` are fine there. Stop scanning rdc flags,
    // but still hold `-c` itself to the placeholder rule first.
    if (tokens[j] === '--command') break;
    if (/^-[a-z]$/.test(tokens[j])) {
      const value = tokens[j + 1];
      if (value && value.startsWith('<')) {
        if (tokens[j] === '-c') break;
        continue; // placeholder self-documents the flag
      }
      return { flag: tokens[j], suggestion: SHORT_FLAG_LONG[tokens[j]] ?? 'the long form' };
    }
  }
  return null;
}

// Fields that extract-tutorial-events.js knows to carry across a re-extraction.
// MUST stay in sync with that script. The meta-guard below fails if a transcript
// contains any key outside these sets, which means someone added a hand-authored
// field but didn't teach extract to preserve it — exactly the regression that
// silently wiped cardLabel/chapters/title/prose (rediacc/console tutorial work).
const PRESERVED_DOC_KEYS = new Set([
  'cast',
  'language',
  'version',
  'title',
  'chapters',
  'events',
  'narrations',
]);
const PRESERVED_EVENT_KEYS = new Set([
  'id',
  'markerIndex',
  'at',
  'text',
  'afterText',
  'cardLabel',
  'prose',
  'afterProse',
]);

function readJson<T = unknown>(filePath: string): T {
  return JSON.parse(readFileSync(filePath, 'utf-8')) as T;
}

interface TranscriptEvent {
  id?: string;
  markerIndex?: number;
  text?: string;
  afterText?: string;
  cardLabel?: string;
  prose?: string;
}
interface TranscriptDoc {
  title?: string;
  chapters?: Record<string, string>;
  events?: TranscriptEvent[];
  narrations?: { id: string; text: string }[];
}

function listStoryboards(): string[] {
  return readdirSync(storyboardDir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => f.replace(/\.json$/, ''))
    .sort();
}

function checkTutorial(slug: string, issues: Issue[]): void {
  const sbPath = path.join(storyboardDir, `${slug}.json`);
  const castPath = path.join(castDir, `${slug}.cast`);
  const trEnPath = path.join(transcriptDir, 'en', `${slug}.json`);
  const mdxPath = path.join(docsDir, `${slug}.mdx`);
  const mdPath = path.join(docsDir, `${slug}.md`);

  const push = (file: string, message: string, drift?: Drift) =>
    issues.push({ tutorial: slug, file: path.relative(wwwRoot, file), message, drift });

  // Storyboard is structural; load first.
  const storyboard = readStoryboard(sbPath);

  // Drafts skip all per-tutorial checks. They're in-progress and not yet
  // expected to have full transcripts/mdx pages.
  if (storyboard.draft === true) {
    return;
  }

  // 1. Cast exists
  if (!existsSync(castPath)) {
    push(castPath, 'cast file missing');
    return;
  }
  const cast = parseCast(castPath);
  const markers = markerTimestamps(cast);
  const labeledMarkers = cast.events.filter(
    ([, k, data]) => k === 'm' && typeof data === 'string' && data.length > 1
  );

  // 2. Storyboard cast-narrated scenes
  const castNarrated = storyboard.scenes.filter((s) => s.type === 'cast-narrated');

  // 3. cast-narrated count == labeled marker count
  if (castNarrated.length !== labeledMarkers.length) {
    push(
      sbPath,
      `storyboard has ${castNarrated.length} cast-narrated scenes but cast has ${labeledMarkers.length} labeled markers`
    );
  }

  // 4. Each markerIndex valid + unique
  const markerIndices = new Set<number>();
  for (const scene of castNarrated) {
    if (scene.type !== 'cast-narrated') continue;
    if (markerIndices.has(scene.markerIndex)) {
      push(sbPath, `duplicate markerIndex ${scene.markerIndex} in cast-narrated scenes`);
    }
    markerIndices.add(scene.markerIndex);
    if (scene.markerIndex < 0 || scene.markerIndex >= markers.length) {
      push(
        sbPath,
        `scene "${scene.id}" markerIndex=${scene.markerIndex} out of range [0, ${markers.length - 1}]`
      );
    }
  }

  // 4b. Every cast-narrated scene must carry card.commandFull (the full,
  // copy-pasteable command rendered on the web page), and its command path must
  // match the recorded cast marker so the page can't silently drift from the video.
  for (const scene of castNarrated) {
    if (scene.type !== 'cast-narrated') continue;
    const full = scene.card?.commandFull;
    if (!isAuthored(full)) {
      push(
        sbPath,
        `scene "${scene.id}" missing card.commandFull (full command shown on the web page)`
      );
      continue;
    }
    const markerEvent = labeledMarkers[scene.markerIndex];
    const recorded = typeof markerEvent?.[2] === 'string' ? (markerEvent[2]) : '';
    if (recorded && commandPath(full) !== commandPath(recorded)) {
      push(
        sbPath,
        `scene "${scene.id}" card.commandFull "${full}" command path differs from recorded marker "${recorded}"`,
        { key: `${slug}#${scene.id}`, commandFull: full.trim(), recorded: recorded.trim() }
      );
    }

    // 4c. rdc short flags must use the long form unless the value is a <placeholder>.
    const fullViol = rdcShortFlagViolation(full);
    if (fullViol) {
      push(
        sbPath,
        `scene "${scene.id}" card.commandFull uses short flag "${fullViol.flag}" with a literal value — use ${fullViol.suggestion}`
      );
    }
    const recViol = recorded ? rdcShortFlagViolation(recorded) : null;
    if (recViol) {
      push(
        castPath,
        `scene "${scene.id}" recorded command uses short flag "${recViol.flag}" with a literal value — re-record with ${recViol.suggestion}`
      );
    }
  }

  // 5. EN transcript exists with required fields
  if (!existsSync(trEnPath)) {
    push(trEnPath, 'EN transcript missing');
    return;
  }
  const tr = readJson<TranscriptDoc>(trEnPath);

  if (!isAuthored(tr.title)) {
    push(trEnPath, 'top-level "title" missing or TODO');
  }

  // Meta-guard: every key in the transcript must be in extract's preserve-list,
  // otherwise re-running `www tutorials extract` would silently drop it.
  const trRaw = readJson<Record<string, unknown>>(trEnPath);
  for (const key of Object.keys(trRaw)) {
    if (!PRESERVED_DOC_KEYS.has(key)) {
      push(
        trEnPath,
        `doc field "${key}" is not in extract-tutorial-events.js preserve-list — it will be wiped on re-extract. Add it there (and to PRESERVED_DOC_KEYS).`
      );
    }
  }
  if (Array.isArray(trRaw.events)) {
    for (const ev of trRaw.events as Record<string, unknown>[]) {
      for (const key of Object.keys(ev)) {
        if (!PRESERVED_EVENT_KEYS.has(key)) {
          push(
            trEnPath,
            `event field "${key}" is not in extract-tutorial-events.js preserve-list — it will be wiped on re-extract. Add it there (and to PRESERVED_EVENT_KEYS).`
          );
        }
      }
    }
  }

  if (!Array.isArray(tr.events)) {
    push(trEnPath, 'events[] missing');
    return;
  }

  if (tr.events.length !== castNarrated.length) {
    push(
      trEnPath,
      `events count ${tr.events.length} != storyboard cast-narrated count ${castNarrated.length}`
    );
  }

  for (const ev of tr.events) {
    if (!isAuthored(ev.cardLabel)) {
      push(trEnPath, `event "${ev.id ?? ev.markerIndex}" missing or TODO cardLabel`);
    }
    if (!isAuthored(ev.text)) {
      push(trEnPath, `event "${ev.id ?? ev.markerIndex}" missing or TODO text (narration)`);
    }
  }

  // 6. chapters{} entries for every storyboard scene
  const chapters = tr.chapters ?? {};
  for (const scene of storyboard.scenes) {
    if (!isAuthored(chapters[scene.id])) {
      push(trEnPath, `chapters["${scene.id}"] missing or TODO`);
    }
  }

  // 7. narrations[] entries for every narrationKey referenced
  const narrationIds = new Set((tr.narrations ?? []).map((n) => n.id));
  for (const scene of storyboard.scenes) {
    const key = (scene as { narrationKey?: string }).narrationKey;
    if (typeof key === 'string' && !narrationIds.has(key)) {
      push(trEnPath, `narration "${key}" referenced by scene "${scene.id}" is missing`);
    }
  }

  // 8. mdx page exists; references every step exactly once
  const pageExists = existsSync(mdxPath);
  if (!pageExists) {
    if (existsSync(mdPath)) {
      push(mdPath, '.md file present but should be .mdx (migrate to use <TutorialStep>)');
    } else {
      push(mdxPath, '.mdx page missing');
    }
    return;
  }
  const mdx = readFileSync(mdxPath, 'utf-8');
  const stepRefs = new Set<number>();
  // Match <TutorialStep number={N} ... />
  for (const m of mdx.matchAll(/<TutorialStep[^>]*\bnumber=\{(\d+)\}/g)) {
    const n = Number(m[1]);
    if (stepRefs.has(n)) {
      push(mdxPath, `duplicate <TutorialStep number={${n}}>`);
    }
    stepRefs.add(n);
  }
  const hasAllSteps = /<TutorialSteps\s*\/?>/.test(mdx);
  const expectedCount = castNarrated.length;

  if (hasAllSteps && stepRefs.size > 0) {
    push(mdxPath, 'page mixes <TutorialSteps /> with individual <TutorialStep>; pick one');
  } else if (hasAllSteps) {
    // covers all steps implicitly — OK
  } else {
    // Individual refs must cover 1..N
    for (let i = 1; i <= expectedCount; i++) {
      if (!stepRefs.has(i)) {
        push(mdxPath, `missing <TutorialStep number={${i}} />`);
      }
    }
    for (const n of stepRefs) {
      if (n < 1 || n > expectedCount) {
        push(mdxPath, `<TutorialStep number={${n}}> out of range [1, ${expectedCount}]`);
      }
    }
  }
}

function checkCrossTutorial(slugs: string[], issues: Issue[]): void {
  const slugSet = new Set(slugs);
  for (const slug of slugs) {
    const sbPath = path.join(storyboardDir, `${slug}.json`);
    const sb = readStoryboard(sbPath);
    if (sb.draft === true) continue;
    const nextKey = sb.nextTutorialKey;
    if (typeof nextKey === 'string' && nextKey.length > 0 && !slugSet.has(nextKey)) {
      issues.push({
        tutorial: slug,
        file: path.relative(wwwRoot, sbPath),
        message: `nextTutorialKey "${nextKey}" does not resolve to an existing storyboard`,
      });
    }
  }
}

/**
 * The STALE-RECORDING parity backlog — CURRENTLY EMPTY, and the file is gone.
 *
 * The mechanism stays because it is a self-destruct ratchet, not a mute: an entry that matches
 * nothing is a FAILURE, so a deferral cannot outlive the re-record that fixes it. Each entry
 * pins BOTH texts (storyboard and recording), so it defers exact known facts and never a class;
 * every other parity check stays live.
 *
 * HISTORY, because it is the whole reason to distrust the next one. The backlog grew 4 -> 75
 * entries and was read as accumulated stale-recording debt from the P4 reshape. It was not. 68 of
 * those were a bug in this file: `commandPath()` guessed the command path as "leading tokens up
 * to the first `-` or `<`", which is only correct while every target is a flag. Once targets
 * became positional refs, `rdc machine add <machine-name>` stopped at the placeholder while the
 * recording `rdc machine add machine-11` swallowed the value, so a command and the recording OF
 * THAT SAME COMMAND resolved to different paths and compared unequal. The baseline dutifully
 * absorbed each phantom as though the storyboards were at fault. See `rdcCommandPath()`.
 *
 * The remaining entries were real (recorded commands using short `-c` with a literal value) and
 * were fixed by re-recording. Parity is now 18/18 with no deferrals.
 *
 * SO: if this list ever grows large again, suspect THIS GATE before believing the debt. A
 * baseline that only grows is evidence of a broken check, not of honest accumulated debt — a
 * large entry count is a symptom to investigate, never a number to re-freeze.
 */
function loadBaseline(): Baseline {
  if (!existsSync(baselinePath)) return {};
  return JSON.parse(readFileSync(baselinePath, 'utf-8')) as Baseline;
}

/** Split the run into what is genuinely wrong and what the backlog defers. */
function applyBaseline(issues: Issue[], baseline: Baseline): { live: Issue[]; deferred: number } {
  const matched = new Set<string>();
  const live: Issue[] = [];

  for (const issue of issues) {
    const entry = issue.drift ? baseline[issue.drift.key] : undefined;
    if (
      issue.drift &&
      entry &&
      entry.commandFull === issue.drift.commandFull &&
      entry.recorded === issue.drift.recorded
    ) {
      matched.add(issue.drift.key);
      continue;
    }
    live.push(issue);
  }

  for (const key of Object.keys(baseline)) {
    if (matched.has(key)) continue;
    const [tutorial = key] = key.split('#');
    live.push({
      tutorial,
      file: path.relative(wwwRoot, baselinePath),
      message: `backlog entry "${key}" defers a drift that no longer exists — the recording, the storyboard, or the scene moved out from under it. DELETE it (see the BLOCKER: these entries must vanish at the re-record), and fix any parity break reported above.`,
    });
  }

  return { live, deferred: matched.size };
}

function main(): number {
  const slugs = listStoryboards();
  const issues: Issue[] = [];
  for (const slug of slugs) {
    try {
      checkTutorial(slug, issues);
    } catch (err) {
      issues.push({
        tutorial: slug,
        file: '(internal)',
        message: `unexpected error: ${err instanceof Error ? err.message : String(err)}`,
      });
    }
  }
  checkCrossTutorial(slugs, issues);

  // Re-freeze from THIS run's own findings — never scraped from stdout.
  if (process.argv.includes('--write-baseline')) {
    const next: Baseline = {};
    for (const { drift } of issues) {
      if (drift) next[drift.key] = { commandFull: drift.commandFull, recorded: drift.recorded };
    }
    const sorted = Object.fromEntries(Object.entries(next).sort(([a], [b]) => a.localeCompare(b)));
    writeFileSync(baselinePath, `${JSON.stringify(sorted, null, 2)}\n`);
    console.log(`Wrote stale-recording parity backlog: ${Object.keys(sorted).length} scene(s).`);
    return 0;
  }

  const { live, deferred } = applyBaseline(issues, loadBaseline());

  if (live.length === 0) {
    console.log(`✓ Tutorial parity OK for ${slugs.length} tutorials`);
    if (deferred > 0) {
      console.log(
        `⚠ ${deferred} scene(s) show a command their recording PREDATES (P4 reshape), pending a` +
          ' re-record. A new drift, an edit to either side, or any other parity break still fails.'
      );
    }
    return 0;
  }
  const issuesToReport = live;

  const byTutorial = new Map<string, Issue[]>();
  for (const issue of issuesToReport) {
    if (!byTutorial.has(issue.tutorial)) byTutorial.set(issue.tutorial, []);
    byTutorial.get(issue.tutorial)!.push(issue);
  }
  console.error(
    `✗ Tutorial parity check failed (${issuesToReport.length} issues across ${byTutorial.size} tutorials)\n`
  );
  for (const [tut, list] of byTutorial) {
    console.error(`[${tut}]`);
    for (const issue of list) {
      console.error(`  ${issue.file}: ${issue.message}`);
    }
    console.error('');
  }
  return 1;
}

process.exit(main());
