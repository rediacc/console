#!/usr/bin/env node
/**
 * Derives per-locale tutorial-timeline JSON for languages that fall back to
 * English audio (ar, et, tr — see FALLBACK_LANGUAGES in
 * private/generative/src/tutorial_tts/cli.py). These locales translate their
 * transcripts but cannot run Qwen3-TTS, so generate-tutorial-video.ts needs a
 * timeline manifest pointing at the English audio MP3s with on-screen text
 * swapped to the locale's translation.
 *
 * Per (locale, tutorial):
 *   in:  src/data/tutorial-timeline/en/<slug>.json     (EN audio refs + timings)
 *        src/data/tutorial-transcripts/<lang>/<slug>.json   (locale text)
 *   out: src/data/tutorial-timeline/<lang>/<slug>.json
 *
 * The output keeps audioSrc / audioDurationSec / textHash from EN, overrides
 * narrationText from the locale's transcript, and strips wordTimings (their
 * char offsets target English text — meaningless against the locale's
 * translation, would render as scrambled karaoke highlighting).
 *
 * Idempotent: re-running with same inputs produces byte-identical output.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const FALLBACK_LANGUAGES = ['ar', 'et', 'tr'] as const;
type FallbackLang = (typeof FALLBACK_LANGUAGES)[number];

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const wwwRoot = path.resolve(scriptDir, '..');
const timelineDir = path.join(wwwRoot, 'src', 'data', 'tutorial-timeline');
const transcriptDir = path.join(wwwRoot, 'src', 'data', 'tutorial-transcripts');

interface TimelineStep {
  id: string;
  markerIndex: number;
  replayStartSec: number;
  replayEndSec: number;
  narrationText?: string;
  audioSrc: string;
  textHash?: string;
  audioDurationSec?: number;
  wordTimings?: unknown;
  afterAudioSrc?: string;
  afterAudioDurationSec?: number;
  afterTextHash?: string;
  afterWordTimings?: unknown;
}

interface NarrationAudioEntry {
  id: string;
  textHash?: string;
  audioSrc: string;
  audioDurationSec?: number;
  narrationText?: string;
  wordTimings?: unknown;
}

interface Timeline {
  cast: string;
  language: string;
  version: number;
  provider?: string;
  modelId?: string;
  audioFormat?: string;
  sampleRateHz?: number;
  voiceDesignPreset?: string;
  transcriptHash?: string;
  steps: TimelineStep[];
  narrationAudio?: NarrationAudioEntry[];
}

interface TranscriptEvent {
  id?: string;
  text?: string;
  afterText?: string;
}

interface Transcript {
  events?: TranscriptEvent[];
  narrations?: Array<{ id?: string; text?: string }>;
}

function parseArgs(argv: string[]): { lang?: FallbackLang } {
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--lang') {
      const v = argv[++i];
      if (!FALLBACK_LANGUAGES.includes(v as FallbackLang)) {
        throw new Error(`--lang must be one of ${FALLBACK_LANGUAGES.join(', ')} (got "${v}")`);
      }
      return { lang: v as FallbackLang };
    }
  }
  return {};
}

function readJson<T>(p: string): T {
  return JSON.parse(fs.readFileSync(p, 'utf8')) as T;
}

function deriveOne(lang: FallbackLang, slug: string): { wrote: boolean; reason?: string } {
  const enPath = path.join(timelineDir, 'en', `${slug}.json`);
  const transcriptPath = path.join(transcriptDir, lang, `${slug}.json`);
  const outPath = path.join(timelineDir, lang, `${slug}.json`);

  if (!fs.existsSync(enPath)) return { wrote: false, reason: `en timeline missing: ${enPath}` };
  if (!fs.existsSync(transcriptPath))
    return { wrote: false, reason: `transcript missing: ${transcriptPath}` };

  const en = readJson<Timeline>(enPath);
  const transcript = readJson<Transcript>(transcriptPath);

  const eventTextById = new Map<string, string>();
  const afterTextById = new Map<string, string>();
  for (const ev of transcript.events ?? []) {
    if (typeof ev.id === 'string') {
      if (typeof ev.text === 'string') eventTextById.set(ev.id, ev.text);
      if (typeof ev.afterText === 'string') afterTextById.set(ev.id, ev.afterText);
    }
  }
  const narrationTextById = new Map<string, string>();
  for (const n of transcript.narrations ?? []) {
    if (typeof n.id === 'string' && typeof n.text === 'string') {
      narrationTextById.set(n.id, n.text);
    }
  }

  const steps: TimelineStep[] = en.steps.map((s) => {
    const next: TimelineStep = {
      id: s.id,
      markerIndex: s.markerIndex,
      replayStartSec: s.replayStartSec,
      replayEndSec: s.replayEndSec,
      audioSrc: s.audioSrc,
    };
    if (typeof s.audioDurationSec === 'number') next.audioDurationSec = s.audioDurationSec;
    if (typeof s.textHash === 'string') next.textHash = s.textHash;
    const localText = eventTextById.get(s.id);
    next.narrationText = localText ?? s.narrationText ?? '';
    if (typeof s.afterAudioSrc === 'string') next.afterAudioSrc = s.afterAudioSrc;
    if (typeof s.afterAudioDurationSec === 'number')
      next.afterAudioDurationSec = s.afterAudioDurationSec;
    if (typeof s.afterTextHash === 'string') next.afterTextHash = s.afterTextHash;
    // wordTimings / afterWordTimings deliberately dropped — see header comment.
    return next;
  });

  const narrationAudio: NarrationAudioEntry[] = (en.narrationAudio ?? []).map((n) => {
    const out: NarrationAudioEntry = {
      id: n.id,
      audioSrc: n.audioSrc,
    };
    if (typeof n.textHash === 'string') out.textHash = n.textHash;
    if (typeof n.audioDurationSec === 'number') out.audioDurationSec = n.audioDurationSec;
    const localText = narrationTextById.get(n.id);
    out.narrationText = localText ?? n.narrationText ?? '';
    return out;
  });

  const payload: Timeline = {
    cast: en.cast,
    language: lang,
    version: en.version,
    steps,
    narrationAudio,
  };
  if (en.provider) payload.provider = en.provider;
  if (en.modelId) payload.modelId = en.modelId;
  if (en.audioFormat) payload.audioFormat = en.audioFormat;
  if (typeof en.sampleRateHz === 'number') payload.sampleRateHz = en.sampleRateHz;
  if (en.voiceDesignPreset) payload.voiceDesignPreset = en.voiceDesignPreset;
  if (en.transcriptHash) payload.transcriptHash = en.transcriptHash;

  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, `${JSON.stringify(payload, null, 2)}\n`);
  return { wrote: true };
}

function deriveForLang(lang: FallbackLang): void {
  const transcriptLangDir = path.join(transcriptDir, lang);
  if (!fs.existsSync(transcriptLangDir)) {
    console.log(`[skip] ${lang}: no transcripts directory at ${transcriptLangDir}`);
    return;
  }
  const slugs = fs
    .readdirSync(transcriptLangDir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => f.replace(/\.json$/, ''))
    .sort();
  let wrote = 0;
  let skipped = 0;
  for (const slug of slugs) {
    const result = deriveOne(lang, slug);
    if (result.wrote) {
      console.log(`[ok]   ${lang}/${slug}`);
      wrote++;
    } else {
      console.log(`[skip] ${lang}/${slug}: ${result.reason}`);
      skipped++;
    }
  }
  console.log(`[done] ${lang}: wrote=${wrote} skipped=${skipped}`);
}

function main(): number {
  const { lang } = parseArgs(process.argv.slice(2));
  const langs = lang ? [lang] : FALLBACK_LANGUAGES;
  for (const l of langs) {
    deriveForLang(l);
  }
  return 0;
}

process.exit(main());
