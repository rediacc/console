import { spawn, type ChildProcess } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import type { FrameLocator, Locator, Page } from 'playwright';
import type {
  BrowserAction,
  BrowserPageSource,
  BrowserScene,
  BrowserSplitPane,
  BrowserSplitScene,
  SessionSpec,
  Storyboard,
} from '../storyboard.ts';
import {
  muxNarratedSegment,
  probeDurationSec,
  trimMp4Duration,
  videoCodecArgs,
  PAD_FILTER_CENTER,
  FPS,
  VIDEO_W,
  VIDEO_H,
} from '../ffmpeg-video.ts';
import { execFileSync } from 'node:child_process';
import type { ChunkProducer, SceneContext } from './index.ts';
import type { LiveSession } from './browser-session.ts';

/**
 * Environment for storyboard-driven host commands (setupCommand,
 * teardownCommand, urlFromCommand). npm/npx prepends node_modules/.bin to
 * PATH, where the workspace's dev `rdc` bin (cli-bundle.cjs) SHADOWS the
 * installed SEA — the two seed different renet builds to the lab machines
 * and the dev bundle may be stale relative to source. Strip those entries
 * so `rdc` always resolves to the real installed binary.
 */
export function hostCommandEnv(): NodeJS.ProcessEnv {
  const cleanedPath = (process.env.PATH ?? '')
    .split(':')
    .filter((p) => !p.includes('node_modules/.bin'))
    .join(':');
  return { ...process.env, PATH: cleanedPath };
}

/**
 * Substitute `${VAR}` environment references in storyboard strings so
 * secrets (logins, tokens) and lab-specific endpoints never live in the
 * committed JSON. Unset variables are a hard error — silently empty
 * values produce baffling recordings.
 */
export function substituteEnv(value: string): string {
  return value.replace(/\$\{([A-Z0-9_]+)\}/g, (_, name: string) => {
    const v = process.env[name];
    if (v === undefined) {
      throw new Error(`browser scene references \${${name}} but it is not set in the environment`);
    }
    return v;
  });
}

/**
 * Resolve a page source to a URL. `urlFromCommand` spawns the command,
 * reads the FIRST stdout line as the URL and keeps the process alive (it
 * holds the tunnel) — the returned handle must be killed at scene end.
 */
export async function resolvePageSource(
  source: BrowserPageSource,
  label: string
): Promise<{ url: string; proc?: ChildProcess }> {
  if (source.url) {
    return { url: substituteEnv(source.url) };
  }
  if (!source.urlFromCommand) {
    throw new Error(`browser scene ${label}: needs url or urlFromCommand`);
  }
  const command = substituteEnv(source.urlFromCommand);
  const proc = spawn('bash', ['-lc', command], {
    stdio: ['ignore', 'pipe', 'inherit'],
    env: hostCommandEnv(),
  });
  const url = await new Promise<string>((resolve, reject) => {
    let buffer = '';
    const timer = setTimeout(
      () => reject(new Error(`browser scene ${label}: urlFromCommand produced no URL in 180s`)),
      180_000
    );
    proc.stdout.on('data', (chunk: Buffer) => {
      buffer += chunk.toString();
      const newline = buffer.indexOf('\n');
      if (newline >= 0) {
        clearTimeout(timer);
        resolve(buffer.slice(0, newline).trim());
      }
    });
    proc.on('exit', (code) => {
      clearTimeout(timer);
      reject(new Error(`browser scene ${label}: urlFromCommand exited early (code ${code})`));
    });
    proc.on('error', reject);
  });
  if (!/^https?:\/\//.test(url)) {
    proc.kill('SIGTERM');
    throw new Error(`browser scene ${label}: urlFromCommand printed "${url}", not a URL`);
  }
  return { url, proc };
}

/**
 * Animated click indicator: a small cursor dot that glides to the target and
 * pulses before the real click fires, so viewers can SEE what is being
 * clicked. Injected idempotently (survives navigations by re-checking) into
 * the live page; pure inline styles, no external CSS.
 */
async function showClickIndicator(page: Page, target: Locator, timeoutMs: number): Promise<void> {
  // boundingBox returns main-viewport coordinates even for elements inside
  // iframes, so the indicator (injected into the top document) lines up.
  const box = await target
    .first()
    .boundingBox({ timeout: timeoutMs })
    .catch(() => null);
  if (!box) return;
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page
    .evaluate(
      ([cx, cy]) => {
        let dot = document.getElementById('__tut_cursor') as HTMLElement | null;
        if (!dot) {
          dot = document.createElement('div');
          dot.id = '__tut_cursor';
          dot.style.cssText =
            'position:fixed;z-index:2147483647;width:22px;height:22px;border-radius:50%;' +
            'background:rgba(0,214,143,0.85);border:2px solid #fff;box-shadow:0 0 8px rgba(0,0,0,0.45);' +
            'pointer-events:none;transform:translate(-50%,-50%);left:50%;top:60%;' +
            'transition:left 0.32s ease,top 0.32s ease;';
          document.body.appendChild(dot);
        }
        dot.style.left = `${cx}px`;
        dot.style.top = `${cy}px`;
      },
      [x, y]
    )
    .catch(() => undefined);
  await page.waitForTimeout(380);
  await page
    .evaluate(
      ([cx, cy]) => {
        const pulse = document.createElement('div');
        pulse.style.cssText =
          'position:fixed;z-index:2147483646;width:22px;height:22px;border-radius:50%;' +
          'border:3px solid rgba(0,214,143,0.9);pointer-events:none;transform:translate(-50%,-50%);' +
          `left:${cx}px;top:${cy}px;`;
        document.body.appendChild(pulse);
        pulse.animate(
          [
            { transform: 'translate(-50%,-50%) scale(1)', opacity: 1 },
            { transform: 'translate(-50%,-50%) scale(2.6)', opacity: 0 },
          ],
          { duration: 320, easing: 'ease-out' }
        );
        setTimeout(() => pulse.remove(), 360);
      },
      [x, y]
    )
    .catch(() => undefined);
  await page.waitForTimeout(220);
}

/** Remove the click-indicator dot, e.g. when another pane takes over. */
async function hideClickIndicator(page: Page): Promise<void> {
  await page
    .evaluate(() => {
      document.getElementById('__tut_cursor')?.remove();
    })
    .catch(() => undefined);
}

export interface RunActionOptions {
  /** Show the animated click indicator before each click (default true). */
  showClicks?: boolean;
}

export async function runActions(
  page: Page,
  actions: BrowserAction[] | undefined,
  opts: RunActionOptions = {}
): Promise<void> {
  const showClicks = opts.showClicks ?? true;
  for (const action of actions ?? []) {
    // Selector scope: the page itself, or — when the action targets UI
    // docked inside an iframe — that frame.
    const scope: Page | FrameLocator = action.frame
      ? page.frameLocator(substituteEnv(action.frame)).first()
      : page;
    if (action.wait) await page.waitForTimeout(action.wait);
    if (action.waitForSelector) {
      await scope
        .locator(substituteEnv(action.waitForSelector))
        .first()
        .waitFor()
        .catch(() => undefined);
    }
    if (action.highlight) {
      await scope
        .locator(substituteEnv(action.highlight))
        .first()
        .evaluate((el) => {
          const target = el as HTMLElement;
          target.style.outline = '6px solid #00d68f';
          target.style.outlineOffset = '4px';
          target.scrollIntoView({
            block: 'center',
            inline: 'center',
            behavior: 'instant' as ScrollBehavior,
          });
        })
        .catch(() => undefined);
    }
    if (action.scrollTo) {
      const behavior = action.smooth ? 'smooth' : 'instant';
      await scope
        .locator(substituteEnv(action.scrollTo))
        .first()
        .evaluate((el, b) => {
          (el as HTMLElement).scrollIntoView({
            block: 'center',
            inline: 'center',
            behavior: b as ScrollBehavior,
          });
        }, behavior)
        .catch(() => undefined);
    }
    if (action.click) {
      const click = typeof action.click === 'string' ? { selector: action.click } : action.click;
      const target = scope.locator(substituteEnv(click.selector));
      if (showClicks) {
        await showClickIndicator(page, target, Math.min(click.timeoutMs ?? 5000, 5000));
      }
      await target
        .first()
        .click(click.timeoutMs ? { timeout: click.timeoutMs } : undefined)
        .catch(() => undefined);
    }
    if (action.fill) {
      await scope
        .locator(substituteEnv(action.fill.selector))
        .first()
        .fill(substituteEnv(action.fill.value))
        .catch(() => undefined);
    }
    if (action.type) {
      if (action.type.selector) {
        await scope
          .locator(substituteEnv(action.type.selector))
          .first()
          .click()
          .catch(() => undefined);
      }
      await page.keyboard.type(substituteEnv(action.type.text), {
        delay: action.type.delayMs ?? 70,
      });
    }
    if (action.press) {
      await page.keyboard.press(action.press);
    }
  }
}

/** Spec for an anonymous (single-scene) session derived from a sessionless scene/pane. */
function anonymousSpec(
  source: BrowserPageSource,
  zoom: number | undefined,
  recordScale: number | undefined,
  showClicks: boolean | undefined
): SessionSpec {
  return {
    url: source.url,
    urlFromCommand: source.urlFromCommand,
    zoom,
    recordScale,
    showClicks,
  };
}

async function acquireForScene(
  ctx: SceneContext,
  scene: BrowserScene,
  sceneId: string
): Promise<{ session: LiveSession; showClicks: boolean }> {
  if (scene.session) {
    const session = await ctx.sessions.acquire(scene.session, 'full', sceneId);
    return { session, showClicks: session.spec.showClicks ?? true };
  }
  const session = await ctx.sessions.acquireAnonymous(
    anonymousSpec(scene, scene.zoom, scene.recordScale, scene.showClicks),
    'full',
    sceneId
  );
  return { session, showClicks: scene.showClicks ?? true };
}

async function acquireForPane(
  ctx: SceneContext,
  scene: BrowserSplitScene,
  pane: BrowserSplitPane,
  paneId: string
): Promise<{ session: LiveSession; showClicks: boolean }> {
  if (pane.session) {
    const session = await ctx.sessions.acquire(pane.session, 'half', paneId);
    return { session, showClicks: session.spec.showClicks ?? true };
  }
  const session = await ctx.sessions.acquireAnonymous(
    anonymousSpec(pane, scene.zoom, scene.recordScale, scene.showClicks),
    'half',
    paneId
  );
  return { session, showClicks: scene.showClicks ?? true };
}

/**
 * Browser scene PIXELS are language-independent (the live app UI), so a
 * scene's silent segment is recorded once and reused across every locale —
 * only the narration audio (muxed later) differs. The cache key hashes ONLY
 * the visual inputs: the scene's + referenced session's actions/prep and
 * geometry knobs. It deliberately EXCLUDES url/urlFromCommand (they carry the
 * lab-specific ${TUTORIAL_MACHINE_NAME}) so the same recording is valid on any
 * machine. Changing a scene's actions changes the hash → automatic re-record.
 */
function sessionVisualBits(storyboard: Storyboard, sessionName: string | undefined): unknown {
  if (!sessionName) return null;
  const s = storyboard.sessions?.[sessionName];
  if (!s) return null;
  // url/urlFromCommand intentionally omitted (lab-specific, not visual).
  return {
    prepActions: s.prepActions ?? null,
    recordScale: s.recordScale ?? null,
    zoom: s.zoom ?? null,
    width: s.width ?? null,
    showClicks: s.showClicks ?? null,
  };
}

/** Content hash of a browser scene's language-independent visual inputs. */
function sceneVisualHash(storyboard: Storyboard, scene: BrowserScene | BrowserSplitScene): string {
  const parts: unknown[] =
    scene.type === 'browser-split'
      ? [
          'browser-split',
          scene.holdSec ?? null,
          scene.recordScale ?? null,
          scene.zoom ?? null,
          scene.showClicks ?? null,
          {
            actions: scene.left.actions ?? null,
            session: sessionVisualBits(storyboard, scene.left.session),
          },
          {
            actions: scene.right.actions ?? null,
            session: sessionVisualBits(storyboard, scene.right.session),
          },
        ]
      : [
          'browser',
          scene.actions ?? null,
          scene.holdSec ?? null,
          scene.recordScale ?? null,
          scene.zoom ?? null,
          scene.showClicks ?? null,
          scene.session ? sessionVisualBits(storyboard, scene.session) : { anon: true },
        ];
  return createHash('sha256').update(JSON.stringify(parts)).digest('hex').slice(0, 12);
}

function cachePathFor(ctx: SceneContext, scene: BrowserScene | BrowserSplitScene): string {
  const hash = sceneVisualHash(ctx.storyboard, scene);
  return path.join(ctx.browserCache.dir, `${ctx.tutorial}.${scene.id}.${hash}.mp4`);
}

/**
 * Whether a browser scene will live-record (vs reuse cache) on this render.
 * The generator uses this to skip the lab setup/teardown entirely when every
 * browser scene is already cached.
 */
export function browserSceneWillRecord(
  storyboard: Storyboard,
  tutorial: string,
  cache: { dir: string; reuse: boolean; refresh: boolean },
  scene: BrowserScene | BrowserSplitScene
): boolean {
  if (!cache.reuse || cache.refresh) return true;
  const hash = sceneVisualHash(storyboard, scene);
  return !existsSync(path.join(cache.dir, `${tutorial}.${scene.id}.${hash}.mp4`));
}

/** Mux a cached silent segment with this language's narration (last-frame hold). */
function muxCachedSegment(
  ctx: SceneContext,
  scene: BrowserScene | BrowserSplitScene,
  cacheFile: string
): string {
  const durSec = probeDurationSec(cacheFile);
  const narration = ctx.narrations.get(scene.narrationKey);
  const audioPath = ctx.narrations.resolvePath(narration.audioSrc);
  const target = Math.max(durSec, scene.durationSec, narration.audioDurationSec ?? 0);
  const mp4 = path.join(ctx.tmp, `${scene.id}.mp4`);
  muxNarratedSegment(cacheFile, audioPath, mp4, {
    endHoldSec: target - durSec,
    padFilter: PAD_FILTER_CENTER,
  });
  return mp4;
}

/** Copy a freshly-cut silent segment into the cache for future-language reuse. */
function saveToCache(ctx: SceneContext, silentSeg: string, cacheFile: string): void {
  mkdirSync(ctx.browserCache.dir, { recursive: true });
  copyFileSync(silentSeg, cacheFile);
}

/**
 * Run a browser scene live against its (shared or anonymous) session, mark
 * the slice boundaries, and return a deferred producer that cuts + muxes the
 * slice once the session recording has closed. The slice is as long as the
 * actions actually took; narration/durationSec only ever EXTEND it via a
 * held last frame — actions are never truncated.
 *
 * When a cached silent segment exists (and --refresh-browser-cache is not
 * set), the live session is SKIPPED entirely and the locale's narration is
 * muxed onto the cached pixels — no lab, no Playwright.
 */
export async function compileBrowser(
  scene: BrowserScene,
  ctx: SceneContext
): Promise<{ deferred: ChunkProducer }> {
  const cacheFile = cachePathFor(ctx, scene);

  // Reuse: cached pixels exist → mux this language's audio, skip the lab.
  if (ctx.browserCache.reuse && !ctx.browserCache.refresh && existsSync(cacheFile)) {
    console.log(`[video] scene ${scene.id}: reusing cached browser segment`);
    return { deferred: () => muxCachedSegment(ctx, scene, cacheFile) };
  }

  // Record: live session, then cache the silent segment for other languages.
  const { session, showClicks } = await acquireForScene(ctx, scene, scene.id);
  await ctx.sessions.markStart(session, scene.id);
  await runActions(session.page, scene.actions, { showClicks });
  if (scene.holdSec) await session.page.waitForTimeout(scene.holdSec * 1000);
  await ctx.sessions.markEnd(session, scene.id);
  const sessionName = session.name;
  return {
    deferred: () => {
      const seg = path.join(ctx.tmp, `${scene.id}.seg.mp4`);
      const { durSec } = ctx.sessions.cutSegment(sessionName, scene.id, seg, PAD_FILTER_CENTER);
      if (ctx.browserCache.reuse) saveToCache(ctx, seg, cacheFile);
      const narration = ctx.narrations.get(scene.narrationKey);
      const audioPath = ctx.narrations.resolvePath(narration.audioSrc);
      const target = Math.max(durSec, scene.durationSec, narration.audioDurationSec ?? 0);
      const mp4 = path.join(ctx.tmp, `${scene.id}.mp4`);
      muxNarratedSegment(seg, audioPath, mp4, {
        endHoldSec: target - durSec,
        padFilter: PAD_FILTER_CENTER,
      });
      return mp4;
    },
  };
}

/**
 * Two live pages driven concurrently, composited side by side under one
 * narration. Panes may reference shared half-width sessions (warm pages,
 * off-camera prep) or fall back to anonymous per-scene sessions.
 */
export async function compileBrowserSplit(
  scene: BrowserSplitScene,
  ctx: SceneContext
): Promise<{ deferred: ChunkProducer }> {
  const leftId = `${scene.id}:left`;
  const rightId = `${scene.id}:right`;
  const cacheFile = cachePathFor(ctx, scene);

  if (ctx.browserCache.reuse && !ctx.browserCache.refresh && existsSync(cacheFile)) {
    console.log(`[video] scene ${scene.id}: reusing cached browser-split segment`);
    return { deferred: () => muxCachedSegment(ctx, scene, cacheFile) };
  }

  const left = await acquireForPane(ctx, scene, scene.left, leftId);
  const right = await acquireForPane(ctx, scene, scene.right, rightId);

  // Symmetric marks: both panes' slices span the same wall window, so the
  // composited halves stay in sync. Pane actions run SEQUENTIALLY (left
  // fully, then right) with a single visible cursor at a time — parallel
  // panes with two cursors are impossible to follow.
  await ctx.sessions.markStart(left.session, leftId);
  await ctx.sessions.markStart(right.session, rightId);
  await runActions(left.session.page, scene.left.actions, { showClicks: left.showClicks });
  await hideClickIndicator(left.session.page);
  await runActions(right.session.page, scene.right.actions, { showClicks: right.showClicks });
  await hideClickIndicator(right.session.page);
  if (scene.holdSec) await left.session.page.waitForTimeout(scene.holdSec * 1000);
  await ctx.sessions.markEnd(left.session, leftId);
  await ctx.sessions.markEnd(right.session, rightId);

  const leftName = left.session.name;
  const rightName = right.session.name;
  return {
    deferred: () => {
      const paneFilter = `fps=${FPS},setsar=1`;
      const leftSeg = path.join(ctx.tmp, `${scene.id}.left.seg.mp4`);
      const rightSeg = path.join(ctx.tmp, `${scene.id}.right.seg.mp4`);
      const leftCut = ctx.sessions.cutSegment(leftName, leftId, leftSeg, paneFilter);
      const rightCut = ctx.sessions.cutSegment(rightName, rightId, rightSeg, paneFilter);
      // Settle-wait jitter can leave the panes a few frames apart; trim both
      // to the shorter so hstack gets equal-length inputs.
      const durSec = Math.min(leftCut.durSec, rightCut.durSec);
      const leftEq = path.join(ctx.tmp, `${scene.id}.left.eq.mp4`);
      const rightEq = path.join(ctx.tmp, `${scene.id}.right.eq.mp4`);
      trimMp4Duration(leftSeg, leftEq, durSec);
      trimMp4Duration(rightSeg, rightEq, durSec);
      const stacked = path.join(ctx.tmp, `${scene.id}.stacked.mp4`);
      // A thin black spacer between the panes so the two surfaces read as
      // separate windows instead of one fused frame.
      const PANE_GAP = 16;
      const paneW = (VIDEO_W - PANE_GAP) / 2;
      execFileSync(
        'ffmpeg',
        [
          '-y',
          '-i',
          leftEq,
          '-i',
          rightEq,
          '-filter_complex',
          // shortest=1 is load-bearing: the color gap source is INFINITE,
          // and hstack's default (end with the longest input) would encode
          // forever.
          `[0:v]scale=${paneW}:${VIDEO_H}[l];[1:v]scale=${paneW}:${VIDEO_H}[r];color=c=black:s=${PANE_GAP}x${VIDEO_H}:r=${FPS}[gap];[l][gap][r]hstack=inputs=3:shortest=1[v]`,
          '-map',
          '[v]',
          ...videoCodecArgs(),
          '-an',
          stacked,
        ],
        { stdio: 'pipe' }
      );
      if (ctx.browserCache.reuse) saveToCache(ctx, stacked, cacheFile);
      const narration = ctx.narrations.get(scene.narrationKey);
      const audioPath = ctx.narrations.resolvePath(narration.audioSrc);
      const target = Math.max(durSec, scene.durationSec, narration.audioDurationSec ?? 0);
      const mp4 = path.join(ctx.tmp, `${scene.id}.mp4`);
      muxNarratedSegment(stacked, audioPath, mp4, {
        endHoldSec: target - durSec,
        padFilter: PAD_FILTER_CENTER,
      });
      return mp4;
    },
  };
}
