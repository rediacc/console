import type { Scene, Storyboard } from '../storyboard.ts';
import type { ParsedCast } from '../cast-splitter.ts';
import type { NarrationLookup } from '../narration-lookup.ts';
import { compileSlide, compileTitle, compileOutro } from './slide.ts';
import { compileCast, compileCastFreeze, compileCastNarrated } from './cast.ts';
import { compileBrowser } from './browser.ts';

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
  castMarkerToNarrationId: (markerIndex: number) => string;
  debug: DebugCollector | null;
  /** Per-language transcript for compileTitle/compileOutro localization. */
  transcript: TranscriptDoc | null;
  /** English transcript, used as fallback when the per-lang field is missing. */
  transcriptEn: TranscriptDoc | null;
}

export async function compileScene(scene: Scene, ctx: SceneContext): Promise<string> {
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
    default: {
      const t: never = scene;
      throw new Error(`Unknown scene type: ${JSON.stringify(t)}`);
    }
  }
}
