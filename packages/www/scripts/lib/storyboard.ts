import { readFileSync } from 'node:fs';

export type SceneType =
  | 'title'
  | 'slide'
  | 'outro'
  | 'cast'
  | 'cast-freeze'
  | 'cast-narrated'
  | 'browser'
  | 'browser-split';

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
/**
 * One scripted browser interaction. Selector/value strings support `${VAR}`
 * environment substitution so secrets (logins, tokens) never live in the
 * committed storyboard.
 */
export interface BrowserAction {
  wait?: number;
  /**
   * CSS selector of an iframe; when set, every selector in this action
   * (click/fill/type/highlight/scrollTo/waitForSelector) resolves INSIDE
   * that frame. Needed for apps that dock tools in iframes (pgAdmin's
   * Query Tool). Keyboard actions are unaffected — focus follows the
   * click into the frame.
   */
  frame?: string;
  /**
   * Click a selector. The object form sets a custom timeout — use a short
   * one for optional UI (e.g. trust dialogs) so a missing element can't
   * stall the recording for the default 30s.
   */
  click?: string | { selector: string; timeoutMs?: number };
  highlight?: string;
  scrollTo?: string;
  smooth?: boolean;
  /** Fill an input/textarea via the DOM (instant). */
  fill?: { selector: string; value: string };
  /** Type with human cadence; selector optional (types into the focused element). */
  type?: { selector?: string; text: string; delayMs?: number };
  /** Press a keyboard key/chord, e.g. "Enter", "Control+`". */
  press?: string;
  /** Block until the selector appears (default Playwright timeout). */
  waitForSelector?: string;
}

/**
 * A browser page source: a literal `url`, or `urlFromCommand` — a shell
 * command (e.g. `rdc vscode connect … --browser --url-only`) whose FIRST
 * stdout line is the URL; the process is kept alive (it holds a tunnel)
 * and SIGTERMed when the scene finishes. Both support `${VAR}` env
 * substitution.
 */
export interface BrowserPageSource {
  url?: string;
  urlFromCommand?: string;
}

/**
 * A named long-lived browser session. Created lazily at the first scene that
 * references it, kept alive across intervening scenes (the page, its server
 * and its tunnel stay warm), closed after its last referencing scene. One
 * continuous recording spans the session; each referencing scene becomes a
 * time-slice of it, so page load and `prepActions` (trust dialogs, panel
 * cleanup, logins) happen ONCE and never appear on camera.
 *
 * Sessions are viewport-bound: `width: 'full'` records at 1920x1080 for
 * `browser` scenes, `width: 'half'` at 960x1080 for `browser-split` panes.
 * Referencing a session from the wrong slot is a hard error.
 *
 * Concurrent sessions each hold their own tunnel — urlFromCommand commands
 * must use distinct local ports.
 */
export interface SessionSpec extends BrowserPageSource {
  /** Off-camera actions run once at session creation, before the first scene's slice. */
  prepActions?: BrowserAction[];
  zoom?: number;
  /** See BrowserScene.recordScale. */
  recordScale?: number;
  /** Pane geometry. Default 'full'. */
  width?: 'full' | 'half';
  /** Disable the animated click indicator for this session's scenes. */
  showClicks?: boolean;
}

export interface BrowserScene extends BrowserPageSource {
  id: string;
  type: 'browser';
  /**
   * Minimum scene length. The recorded slice is as long as the actions
   * actually take (plus `holdSec`); if narration or `durationSec` is longer,
   * the last frame is held — actions are never truncated.
   */
  durationSec: number;
  narrationKey: string;
  /**
   * Reference into `storyboard.sessions`. Mutually exclusive with
   * url/urlFromCommand/zoom/recordScale on the scene (those live on the
   * session). Sessionless scenes get an anonymous single-scene session.
   */
  session?: string;
  /** Live hold after the last action, before the slice ends (seconds). */
  holdSec?: number;
  zoom?: number;
  /**
   * Magnify by recording at a smaller viewport (width/scale x height/scale)
   * and upscaling the recording to full size. Unlike `zoom` (CSS zoom), this
   * never breaks apps that lay themselves out in JS pixel units (VS Code
   * web positions its workbench from window.innerWidth and renders garbage
   * under CSS zoom).
   */
  recordScale?: number;
  /** Disable the animated click indicator for this scene (sessionless scenes). */
  showClicks?: boolean;
  actions?: BrowserAction[];
}

/**
 * Side-by-side comparison: two live pages composited left|right (ffmpeg
 * hstack) under one narration. The money shot for fork-isolation demos.
 */
export interface BrowserSplitPane extends BrowserPageSource {
  /** Reference into `storyboard.sessions` (must be a 'half'-width session). */
  session?: string;
  actions?: BrowserAction[];
  label?: string;
}

export interface BrowserSplitScene {
  id: string;
  type: 'browser-split';
  /** Minimum scene length — see BrowserScene.durationSec. */
  durationSec: number;
  narrationKey: string;
  /** Live hold after the last action of both panes, before the slice ends. */
  holdSec?: number;
  zoom?: number;
  /** See BrowserScene.recordScale — applies to both panes. */
  recordScale?: number;
  /** Disable the animated click indicator (sessionless panes). */
  showClicks?: boolean;
  left: BrowserSplitPane;
  right: BrowserSplitPane;
}

export type Scene =
  | TitleScene
  | SlideScene
  | OutroScene
  | CastScene
  | CastFreezeScene
  | CastNarratedScene
  | BrowserScene
  | BrowserSplitScene;

export interface Storyboard {
  version: 1;
  tutorial: string;
  /**
   * Optional shell commands run by generate-tutorial-video around scene
   * compilation: `setupCommand` before the first scene (e.g. create a fork,
   * start a demo stack), `teardownCommand` after the last (guaranteed via
   * try/finally). `${VAR}` env substitution applies.
   */
  setupCommand?: string;
  teardownCommand?: string;
  /** Named long-lived browser sessions referenced by browser scenes/panes. */
  sessions?: Record<string, SessionSpec>;
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

function validateSessionRef(
  sb: Storyboard,
  ref: { session?: string; url?: string; urlFromCommand?: string },
  label: string
): void {
  if (!ref.session) return;
  if (!sb.sessions?.[ref.session]) {
    throw new Error(`${label}: references unknown session "${ref.session}"`);
  }
  const loose = ref as Record<string, unknown>;
  for (const field of ['url', 'urlFromCommand', 'zoom', 'recordScale'] as const) {
    if (loose[field] !== undefined) {
      throw new Error(
        `${label}: "${field}" conflicts with session "${ref.session}" — move it to the session spec`
      );
    }
  }
}

export function readStoryboard(path: string): Storyboard {
  const sb = JSON.parse(readFileSync(path, 'utf8')) as Storyboard;
  if (sb.version !== 1) throw new Error(`Unsupported storyboard version ${sb.version} at ${path}`);
  for (const scene of sb.scenes) {
    if (scene.type === 'browser') {
      validateSessionRef(sb, scene, `browser scene "${scene.id}"`);
    } else if (scene.type === 'browser-split') {
      validateSessionRef(sb, scene.left, `browser-split scene "${scene.id}" left pane`);
      validateSessionRef(sb, scene.right, `browser-split scene "${scene.id}" right pane`);
    }
  }
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
