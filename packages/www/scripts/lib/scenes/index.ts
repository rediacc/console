import type { Scene, Storyboard } from '../storyboard.ts';
import type { ParsedCast } from '../cast-splitter.ts';
import type { NarrationLookup } from '../narration-lookup.ts';
import type { SessionManager } from './browser-session.ts';
import { compileSlide, compileTitle, compileOutro } from './slide.ts';
import { compileCast, compileCastFreeze, compileCastNarrated } from './cast.ts';
import { compileBrowser, compileBrowserSplit } from './browser.ts';

export interface CastNarratedDebug {
  sceneId: string;
  markerIndex: number;
  startSec: number;
  rawEndSec: number;
  promptTime: number | null;
  mainEndSec: number;
  frameEndSec: number;
  mainAnimDur: number;
  readPauseSec: number;
  mainAudioDurSec: number;
  afterAudioDurSec: number | null;
  lastFramePngSrc: string;
}

export interface DebugCollector {
  framesDir: string;
  castNarrated: CastNarratedDebug[];
  recordCastNarrated(entry: CastNarratedDebug): void;
}

/**
 * Per-language transcript JSON. Loose-typed via `unknown`-valued keys
 * because each scene compiler picks specific fields (title for compileTitle,
 * chapters for vtt-emit, events[].cardLabel for compileTitle sub-items) and
 * the precise shape is documented in tutorial-transcripts/<lang>/<tutorial>.json.
 */
export type TranscriptDoc = Record<string, unknown>;

export interface SceneContext {
  tmp: string;
  wwwPublicRoot: string;
  tutorial: string;
  lang: string;
  storyboard: Storyboard;
  cast: ParsedCast;
  markers: number[];
  castEnd: number;
  narrations: NarrationLookup;
  chunks: string[];
  sessions: SessionManager;
  /**
   * Silent-segment cache for browser scenes (language-independent pixels).
   * `reuse`: mux from a cached segment when present (skips the live session).
   * `refresh`: force a live re-record and overwrite the cache.
   */
  browserCache: { dir: string; reuse: boolean; refresh: boolean };
  castMarkerToNarrationId: (markerIndex: number) => string;
  debug: DebugCollector | null;
  /** Per-language transcript for compileTitle/compileOutro localization. */
  transcript: TranscriptDoc | null;
  /** English transcript, used as fallback when the per-lang field is missing. */
  transcriptEn: TranscriptDoc | null;
}

/** Materializes a deferred browser-scene chunk after its session has closed. */
export type ChunkProducer = () => string;
/** Eager scenes return a finished mp4 path; browser scenes defer until sessions close. */
export type SceneOutput = string | { deferred: ChunkProducer };

export async function compileScene(scene: Scene, ctx: SceneContext): Promise<SceneOutput> {
  switch (scene.type) {
    case 'title':
      return compileTitle(scene, ctx);
    case 'slide':
      return compileSlide(scene, ctx);
    case 'outro':
      return compileOutro(scene, ctx);
    case 'cast':
      return compileCast(scene, ctx);
    case 'cast-freeze':
      return compileCastFreeze(scene, ctx);
    case 'cast-narrated':
      return compileCastNarrated(scene, ctx);
    case 'browser':
      return await compileBrowser(scene, ctx);
    case 'browser-split':
      return await compileBrowserSplit(scene, ctx);
    default: {
      const t: never = scene;
      throw new Error(`Unknown scene type: ${JSON.stringify(t)}`);
    }
  }
}
