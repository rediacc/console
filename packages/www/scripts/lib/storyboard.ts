import { readFileSync } from 'node:fs';

export type SceneType =
  | 'title'
  | 'slide'
  | 'outro'
  | 'cast'
  | 'cast-freeze'
  | 'cast-narrated'
  | 'browser';

export interface TitleScene {
  id: string;
  type: 'title';
  narrationKey: string;
  src?: string;
}
export interface SlideScene {
  id: string;
  type: 'slide';
  src: string;
  narrationKey: string;
}
export interface OutroScene {
  id: string;
  type: 'outro';
  narrationKey: string;
  src?: string;
}
export interface CastScene {
  id: string;
  type: 'cast';
  from: 'start' | string;
  to: 'end' | string;
}
export interface CastFreezeScene {
  id: string;
  type: 'cast-freeze';
  markerIndex: number;
}
/**
 * Plays cast[markerIndex → next-marker-or-end] with narration audio overlaid.
 * Prepends `holdSec` of held first-frame so the prompt is visible before audio
 * starts. Tail-pads if narration outlasts the cast slice.
 *
 * `card.command` overrides the auto-derived command snippet on the title
 * card (computed from the cast marker's recorded text otherwise). Useful
 * when the recorded command is too long to display cleanly.
 *
 * `card.commandFull` is the full, copy-pasteable command (with `<placeholder>`
 * templates, e.g. `--name <machine-name>`) shown on the web/MDX page so readers
 * who don't watch the video can copy it. The video keeps the short `command`.
 */
export interface CastNarratedScene {
  id: string;
  type: 'cast-narrated';
  markerIndex: number;
  holdSec?: number;
  narrationKey?: string;
  afterTrimSec?: number;
  card?: { command?: string; commandFull?: string };
}
export interface BrowserScene {
  id: string;
  type: 'browser';
  url: string;
  durationSec: number;
  narrationKey: string;
  zoom?: number;
  actions?: Array<{
    wait?: number;
    click?: string;
    highlight?: string;
    scrollTo?: string;
    smooth?: boolean;
  }>;
}

export type Scene =
  | TitleScene
  | SlideScene
  | OutroScene
  | CastScene
  | CastFreezeScene
  | CastNarratedScene
  | BrowserScene;

export interface Storyboard {
  version: 1;
  tutorial: string;
  /**
   * Language-neutral key of the next tutorial (e.g. "tutorial-create-repo").
   * The renderer constructs the outro card's link per language as
   * `/<lang>/docs/<nextTutorialKey>` and looks up the next tutorial's
   * transcript.title for the displayed next-title text. Omit on the last
   * tutorial in a series.
   */
  nextTutorialKey?: string;
  /**
   * Marks an in-progress tutorial. Skipped by the parity CI check so
   * incomplete drafts don't block other tutorials' CI. Drafts must NOT have
   * a corresponding .mdx page in production docs.
   */
  draft?: boolean;
  scenes: Scene[];
}

export function readStoryboard(path: string): Storyboard {
  const sb = JSON.parse(readFileSync(path, 'utf8')) as Storyboard;
  if (sb.version !== 1) throw new Error(`Unsupported storyboard version ${sb.version} at ${path}`);
  return sb;
}

/**
 * Resolve a cast endpoint reference like "start", "end", "marker-0" to seconds
 * given an ordered list of marker timestamps and the cast end time.
 */
export function resolveCastEndpoint(
  ref: string | number,
  markers: number[],
  castEndSec: number
): number {
  if (typeof ref === 'number') return ref;
  if (ref === 'start') return 0;
  if (ref === 'end') return castEndSec;
  const m = ref.match(/^marker-(\d+)$/);
  if (!m) throw new Error(`Unparseable cast endpoint: ${ref}`);
  const idx = Number(m[1]);
  if (idx < 0 || idx >= markers.length)
    throw new Error(`marker-${idx} out of range (have ${markers.length} markers)`);
  return markers[idx];
}
