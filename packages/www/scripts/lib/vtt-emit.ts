import { writeFileSync } from 'node:fs';
import type { Storyboard, Scene } from './storyboard.ts';
import { STEP_CARD_DURATION_SEC } from './scenes/cast.ts';
import type { CastNarratedDebug } from './scenes/index.ts';

// Single source of truth for the cast-narrated scene's pre-audio dwell:
// imported from scenes/cast.ts so emitter and renderer can never drift.
const START_HOLD_DEFAULT_SEC = 0.6;
const MAX_WORDS_PER_CUE = 10;
const MAX_CUE_DURATION_SEC = 2.5;
const PUNCT_BREAK = new Set(['.', ',', ';', ':', '!', '?']);

type WordTiming = { startSec: number; endSec: number; startChar: number; endChar: number };

interface TimelineStep {
  id: string;
  markerIndex: number;
  narrationText: string;
  audioDurationSec: number;
  audioSrc: string;
  wordTimings?: WordTiming[];
  afterAudioSrc?: string;
  afterAudioDurationSec?: number;
  afterWordTimings?: WordTiming[];
}

interface NarrationAudioEntry {
  id: string;
  narrationText?: string;
  audioDurationSec?: number;
  wordTimings?: WordTiming[];
}

interface Timeline {
  steps?: TimelineStep[];
  narrationAudio?: NarrationAudioEntry[];
}

interface TranscriptEvent {
  id: string;
  markerIndex: number;
  text: string;
  afterText?: string;
}

interface Transcript {
  events?: TranscriptEvent[];
}

interface SceneTiming {
  start: number;
  end: number;
}

interface VttCue {
  start: number;
  end: number;
  text: string;
}

/**
 * Word entry inside a cue group. `char` is a [start, end) pair into the cue's
 * `text` so the runtime can substring without re-tokenizing.
 */
interface WordEntry {
  start: number;
  end: number;
  char: [number, number];
}

/**
 * Unified intermediate consumed by both VTT and word-timings emitters. One
 * group per VTT cue. For non-narrated scenes (intro, slide, outro) and
 * afterText, `words` contains a single entry spanning the cue duration.
 */
interface CueGroup {
  start: number;
  end: number;
  text: string;
  words: WordEntry[];
}

function formatTimestamp(seconds: number): string {
  const total = Math.max(0, seconds);
  const hh = Math.floor(total / 3600);
  const mm = Math.floor((total % 3600) / 60);
  const ss = Math.floor(total % 60);
  const ms = Math.round((total - Math.floor(total)) * 1000);
  return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
}

function writeVtt(outPath: string, cues: VttCue[]): void {
  const body = cues
    .map((c) => `${formatTimestamp(c.start)} --> ${formatTimestamp(c.end)}\n${c.text}`)
    .join('\n\n');
  writeFileSync(outPath, `WEBVTT\n\n${body}\n`);
}

function titleCase(slug: string): string {
  return slug
    .split('-')
    .map((w) => (w.length === 0 ? w : w[0].toUpperCase() + w.slice(1)))
    .join(' ');
}

/**
 * Group wordTimings into cues bounded by MAX_WORDS_PER_CUE, MAX_CUE_DURATION_SEC,
 * and punctuation boundaries when present. Returns absolute-timestamped cue
 * groups (text + per-word array) given a base mp4 offset.
 */
function buildCueGroupsFromWordTimings(
  narrationText: string,
  wordTimings: NonNullable<TimelineStep['wordTimings']>,
  baseOffsetSec: number
): CueGroup[] {
  if (wordTimings.length === 0) return [];
  const groups: CueGroup[] = [];
  let groupStart = 0;
  // Tracks where the previous cue ended in narrationText. The next cue
  // starts there so leading characters are never dropped — Qwen3-ASR
  // occasionally returns a startChar inside a word (e.g., maps "Alright"
  // back as "lright" → startChar=2), and any inter-cue whitespace or
  // punctuation that lives between mapped words still needs to appear.
  let cueTextCursor = 0;
  for (let i = 0; i < wordTimings.length; i++) {
    const cur = wordTimings[i];
    const groupHead = wordTimings[groupStart];
    const words = i - groupStart + 1;
    const dur = cur.endSec - groupHead.startSec;
    const lastChar = narrationText[cur.endChar - 1] ?? '';
    const isLast = i === wordTimings.length - 1;
    const isPunctBreak = PUNCT_BREAK.has(lastChar);
    const shouldBreak =
      isLast || words >= MAX_WORDS_PER_CUE || dur >= MAX_CUE_DURATION_SEC || isPunctBreak;
    if (!shouldBreak) continue;
    const cueTextStart = cueTextCursor;
    const cueTextEnd = isLast ? narrationText.length : cur.endChar;
    const rawSlice = narrationText.substring(cueTextStart, cueTextEnd);
    const text = rawSlice.trim();
    if (text.length > 0) {
      const leadingTrim = rawSlice.length - rawSlice.replace(/^\s+/, '').length;
      const wordEntries: WordEntry[] = [];
      for (let j = groupStart; j <= i; j++) {
        const w = wordTimings[j];
        const cs = Math.max(0, w.startChar - cueTextStart - leadingTrim);
        const ce = Math.min(text.length, w.endChar - cueTextStart - leadingTrim);
        if (ce <= cs) continue;
        wordEntries.push({
          start: baseOffsetSec + w.startSec,
          end: baseOffsetSec + w.endSec,
          char: [cs, ce],
        });
      }
      groups.push({
        start: baseOffsetSec + groupHead.startSec,
        end: baseOffsetSec + cur.endSec,
        text,
        words: wordEntries,
      });
    }
    cueTextCursor = cueTextEnd;
    groupStart = i + 1;
  }
  return groups;
}

/**
 * Defensive fallback when TTS hasn't been re-run with --subtitle for a given
 * narration type: distribute the audio duration evenly across words. Less
 * accurate than ASR-aligned timings but keeps word-by-word highlight working.
 * Returns timings RELATIVE to a 0 base.
 */
function estimateRelativeWordTimings(text: string, durationSec: number): WordTiming[] {
  const matches = Array.from(text.matchAll(/\S+/g));
  if (matches.length === 0) return [];
  const span = Math.max(0.2, durationSec) / matches.length;
  return matches.map((m, i) => ({
    startSec: i * span,
    endSec: (i + 1) * span,
    startChar: m.index ?? 0,
    endChar: (m.index ?? 0) + m[0].length,
  }));
}

/**
 * Build cue groups for one piece of narration. Prefers TTS-emitted
 * `wordTimings` when present and sufficiently dense; otherwise falls back to
 * estimate. All three narration types in collectCueGroups (main, afterText,
 * narrationAudio) use this so the cue-grouping logic + fallback policy live
 * in one place.
 *
 * Density gate: Qwen3-ASR transcribes the audio independently and maps each
 * detected word back to the transcript via substring search. When the ASR
 * diverges from the transcript (paraphrasing, dropped articles, etc.) most
 * words are unmappable and we end up with a handful of sparse timings spread
 * across a long text — which gives WORSE captions than a clean even-spaced
 * estimate. If fewer than half of the text's words got mapped, discard the
 * partial timings and estimate instead.
 */
const MIN_WORD_TIMING_COVERAGE = 0.5;

function cuesFromNarration(
  text: string,
  startSec: number,
  durationSec: number,
  wordTimings: WordTiming[] | undefined
): CueGroup[] {
  const expectedWords = (text.match(/\S+/g) ?? []).length;
  const wtCoverage = wordTimings && expectedWords > 0 ? wordTimings.length / expectedWords : 0;
  const wt =
    wordTimings && wordTimings.length > 0 && wtCoverage >= MIN_WORD_TIMING_COVERAGE
      ? wordTimings
      : estimateRelativeWordTimings(text, durationSec);
  return buildCueGroupsFromWordTimings(text, wt, startSec);
}

/**
 * Compute the absolute mp4 time at which the after-narration audio begins for
 * a cast-narrated scene, mirroring scenes/cast.ts::compileCastNarrated layout:
 *   sceneStart + prePause + mainCoreDuration + readPauseSec
 * where mainCoreDuration = max(mainAudioDurSec, startHold + mainAnimDur).
 * (The `startHold` term only shows up in mainCoreDuration via tpad's video
 * padding — the main narration audio itself starts at sceneStart + prePause
 * with no startHold offset; see mainAudioStart computation above.)
 */
function afterAudioStartSec(
  sceneStart: number,
  prePauseSec: number,
  startHoldSec: number,
  step: TimelineStep,
  castTiming: CastNarratedDebug
): number {
  const mainCoreDuration = Math.max(step.audioDurationSec, startHoldSec + castTiming.mainAnimDur);
  return sceneStart + prePauseSec + mainCoreDuration + castTiming.readPauseSec;
}

function indexTimelineStepsByMarker(timeline: Timeline): Map<number, TimelineStep> {
  const m = new Map<number, TimelineStep>();
  for (const s of timeline.steps ?? []) m.set(s.markerIndex, s);
  return m;
}

function indexNarrationAudio(timeline: Timeline): Map<string, NarrationAudioEntry> {
  const m = new Map<string, NarrationAudioEntry>();
  for (const n of timeline.narrationAudio ?? []) m.set(n.id, n);
  return m;
}

function indexTranscriptByMarker(transcript: Transcript | null): Map<number, TranscriptEvent> {
  const m = new Map<number, TranscriptEvent>();
  for (const e of transcript?.events ?? []) m.set(e.markerIndex, e);
  return m;
}

interface CollectArgs {
  storyboard: Storyboard;
  timeline: Timeline;
  transcript: Transcript | null;
  sceneTiming: Record<string, SceneTiming>;
  castTimingBySceneId: Map<string, CastNarratedDebug>;
}

/**
 * Walk the storyboard once and produce a sorted list of cue groups. Both VTT
 * emission and the per-word JSON sidecar consume this so they stay aligned.
 */
function collectCueGroups(args: CollectArgs): CueGroup[] {
  const stepsByMarker = indexTimelineStepsByMarker(args.timeline);
  const narrationById = indexNarrationAudio(args.timeline);
  const afterTextByMarker = indexTranscriptByMarker(args.transcript);
  const groups: CueGroup[] = [];

  for (const scene of args.storyboard.scenes) {
    const timing = args.sceneTiming[scene.id];
    if (!timing) continue;

    if (scene.type === 'cast-narrated') {
      const step = stepsByMarker.get(scene.markerIndex);
      if (!step) continue;
      const castTiming = args.castTimingBySceneId.get(scene.id);
      if (!castTiming) continue;

      const stepPrePause = STEP_CARD_DURATION_SEC;
      const startHold = scene.holdSec ?? START_HOLD_DEFAULT_SEC;
      // The cast-narrated scene is concat(prePauseMp4, mainCore). Audio plays
      // from t=0 of mainCore — the `tpad start_duration=startHold` filter in
      // muxNarratedSegment delays only the VIDEO (held first frame); the
      // audio stream is muxed in without any leading offset. So the narration
      // starts at sceneStart + prePause, NOT sceneStart + prePause + startHold.
      // (Confirmed by ffmpeg volumedetect probe: audio rises from −91 dB to
      // −15 dB at exactly sceneStart + prePause + 0.08, matching the first
      // wordTiming.startSec for "First".)
      const mainAudioStart = timing.start + stepPrePause;
      groups.push(
        ...cuesFromNarration(
          step.narrationText,
          mainAudioStart,
          step.audioDurationSec,
          step.wordTimings
        )
      );

      if (step.afterAudioSrc && typeof step.afterAudioDurationSec === 'number') {
        const afterStart = afterAudioStartSec(
          timing.start,
          stepPrePause,
          startHold,
          step,
          castTiming
        );
        const afterText = afterTextByMarker.get(scene.markerIndex)?.afterText?.trim();
        if (afterText && afterText.length > 0) {
          groups.push(
            ...cuesFromNarration(
              afterText,
              afterStart,
              step.afterAudioDurationSec,
              step.afterWordTimings
            )
          );
        }
      }
      continue;
    }

    if (
      scene.type === 'title' ||
      scene.type === 'slide' ||
      scene.type === 'outro' ||
      scene.type === 'browser'
    ) {
      const narrationKey = scene.narrationKey;
      if (!narrationKey) continue;
      const entry = narrationById.get(narrationKey);
      if (!entry || !entry.narrationText || !entry.audioDurationSec) continue;
      groups.push(
        ...cuesFromNarration(
          entry.narrationText,
          timing.start,
          entry.audioDurationSec,
          entry.wordTimings
        )
      );
      continue;
    }

    // 'cast' (bridge) and 'cast-freeze' produce no subtitle cues by themselves.
  }

  groups.sort((a, b) => a.start - b.start);
  return groups;
}

interface SubtitlesArgs extends CollectArgs {
  outPath: string;
}

export function emitSubtitlesVtt(args: SubtitlesArgs): void {
  const groups = collectCueGroups(args);
  const cues: VttCue[] = groups.map((g) => ({ start: g.start, end: g.end, text: g.text }));
  writeVtt(args.outPath, cues);
}

interface WordTimingsArgs extends CollectArgs {
  outPath: string;
}

export function emitWordTimingsJson(args: WordTimingsArgs): void {
  const groups = collectCueGroups(args);
  const doc = {
    version: 1,
    cues: groups.map((g) => ({
      start: Number(g.start.toFixed(3)),
      end: Number(g.end.toFixed(3)),
      text: g.text,
      words: g.words.map((w) => ({
        start: Number(w.start.toFixed(3)),
        end: Number(w.end.toFixed(3)),
        char: w.char,
      })),
    })),
  };
  writeFileSync(args.outPath, JSON.stringify(doc));
}

interface ChaptersArgs {
  outPath: string;
  storyboard: Storyboard;
  sceneTiming: Record<string, SceneTiming>;
  /** Per-language transcript. Reads chapters[scene.id] for the localized label. */
  transcript: Record<string, unknown> | null;
  /** English transcript, used as fallback when the per-lang map is missing keys. */
  transcriptEn: Record<string, unknown> | null;
}

function readChaptersMap(doc: Record<string, unknown> | null): Record<string, string> | null {
  if (!doc || typeof doc.chapters !== 'object' || doc.chapters === null) return null;
  return doc.chapters as Record<string, string>;
}

function isAuthored(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0 && !value.startsWith('TODO:');
}

/**
 * Lookup chain for a scene's chapter label:
 *   1. per-language transcript.chapters[scene.id]
 *   2. English transcript.chapters[scene.id]  (fallback for untranslated locales)
 *   3. title-cased scene.id                   (last-resort auto-derive)
 */
function chapterLabel(
  scene: Scene,
  transcript: Record<string, unknown> | null,
  transcriptEn: Record<string, unknown> | null
): string {
  const lang = readChaptersMap(transcript);
  if (lang && isAuthored(lang[scene.id])) return lang[scene.id].trim();
  const en = readChaptersMap(transcriptEn);
  if (en && isAuthored(en[scene.id])) return en[scene.id].trim();
  return titleCase(scene.id);
}

export function emitChaptersVtt(args: ChaptersArgs): void {
  const cues: VttCue[] = [];
  for (const scene of args.storyboard.scenes) {
    const t = args.sceneTiming[scene.id];
    if (!t) continue;
    cues.push({
      start: t.start,
      end: t.end,
      text: chapterLabel(scene, args.transcript, args.transcriptEn),
    });
  }
  writeVtt(args.outPath, cues);
}
