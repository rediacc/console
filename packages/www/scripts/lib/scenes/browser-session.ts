import path from 'node:path';
import type { ChildProcess } from 'node:child_process';
import { chromium, type Browser, type BrowserContext, type Page } from 'playwright';
import type { SessionSpec, Storyboard } from '../storyboard.ts';
import {
  cutSegmentMp4,
  extractPosterJpg,
  probeDurationSec,
  VIDEO_W,
  VIDEO_H,
} from '../ffmpeg-video.ts';
import { resolvePageSource, runActions } from './browser.ts';

/**
 * Long-lived browser sessions for tutorial videos.
 *
 * One Playwright context records CONTINUOUSLY for the session's whole life;
 * each referencing scene becomes a time-slice of that recording, cut after
 * the session closes. Page load and prepActions happen before the first
 * slice, so load flash and one-time UI (trust dialogs, panel cleanup,
 * logins) never appear in the final video — and consecutive scenes on the
 * same session play as one uninterrupted live surface.
 *
 * Timestamp mapping: Playwright's webm starts at the first painted frame
 * (the goto white-screen head is simply absent) and frame timestamps are
 * browser-side, so the timeline is wall-clock-proportional and does not
 * drift when the Node event loop is blocked by ffmpeg between scenes. All
 * missing time is attributed to the head:
 *   headGapSec   = wallSpanSec - webmDurSec
 *   videoTime(w) = (w - wallCreateMs)/1000 - headGapSec
 * Every mark is preceded by a settle wait, so each cut boundary sits inside
 * visually static footage and small mapping errors land on identical frames.
 */

/** Idle enforced before each boundary mark — the cut-precision safety margin. */
const SETTLE_MS = 400;

export type SessionWidth = 'full' | 'half';

interface SceneMarks {
  startMs: number;
  endMs: number;
}

export interface LiveSession {
  name: string;
  spec: SessionSpec;
  page: Page;
  context: BrowserContext;
  browser: Browser;
  proc?: ChildProcess;
  width: SessionWidth;
  recordScale: number;
  wallCreateMs: number;
  marks: Map<string, SceneMarks>;
  lastUseSceneIndex: number;
  crashed: boolean;
  result?: { webm: string; webmDurSec: number; headGapSec: number };
}

export interface SessionManager {
  /** Called by the scene loop before compiling scene i (anonymous-session lifetime). */
  beginScene(sceneIndex: number): void;
  acquire(name: string, need: SessionWidth, sceneId: string): Promise<LiveSession>;
  acquireAnonymous(spec: SessionSpec, need: SessionWidth, sceneId: string): Promise<LiveSession>;
  markStart(session: LiveSession, sceneId: string): Promise<void>;
  markEnd(session: LiveSession, sceneId: string): Promise<void>;
  /** Close sessions whose last referencing scene index is `sceneIndex`. */
  closeFinished(sceneIndex: number): Promise<void>;
  /** Idempotent; also kills tunnels. Safe to call from finally. */
  closeAll(): Promise<void>;
  /**
   * Cut a scene's slice out of its (closed) session recording into a silent
   * mp4. Returns the slice duration. In debug mode also extracts boundary
   * frames (<sceneId>.segstart/.segend.jpg) for verification.
   */
  cutSegment(
    sessionName: string,
    sceneId: string,
    outMp4: string,
    padFilter?: string
  ): { durSec: number };
  debugInfo(): Array<{
    name: string;
    webmDurSec: number;
    wallSpanSec: number;
    headGapSec: number;
    scenes: Array<{ id: string; videoStartSec: number; videoEndSec: number }>;
  }>;
}

function paneSize(width: SessionWidth): { w: number; h: number } {
  return width === 'half' ? { w: VIDEO_W / 2, h: VIDEO_H } : { w: VIDEO_W, h: VIDEO_H };
}

export function createSessionManager(opts: {
  tmp: string;
  storyboard: Storyboard;
  debugFramesDir?: string;
}): SessionManager {
  const live = new Map<string, LiveSession>();
  const closed = new Map<string, LiveSession>();
  const closeInfo = new Map<string, { wallCloseMs: number }>();
  let currentSceneIndex = -1;

  // Precompute each named session's last referencing scene index so it can
  // be closed eagerly (bounds the recording length).
  const lastUse = new Map<string, number>();
  opts.storyboard.scenes.forEach((scene, i) => {
    if (scene.type === 'browser' && scene.session) lastUse.set(scene.session, i);
    if (scene.type === 'browser-split') {
      if (scene.left.session) lastUse.set(scene.left.session, i);
      if (scene.right.session) lastUse.set(scene.right.session, i);
    }
  });

  async function create(
    name: string,
    spec: SessionSpec,
    sceneId: string,
    lastUseSceneIndex: number
  ): Promise<LiveSession> {
    const width: SessionWidth = spec.width ?? 'full';
    const { w, h } = paneSize(width);
    const scale = spec.recordScale && spec.recordScale > 1 ? spec.recordScale : 1;
    // Record at the (possibly reduced) viewport size — Playwright never
    // upscales frames into a larger canvas, it pads them; downstream ffmpeg
    // filters do the upscale.
    const viewport = { width: Math.round(w / scale), height: Math.round(h / scale) };
    const { url, proc } = await resolvePageSource(spec, `session ${name} (scene ${sceneId})`);
    const wallCreateMs = Date.now();
    const browser = await chromium.launch();
    const context = await browser.newContext({
      viewport,
      deviceScaleFactor: 1,
      recordVideo: {
        dir: path.join(opts.tmp, 'sessions', name.replace(/[^\w.-]+/g, '_')),
        size: viewport,
      },
    });
    const page = await context.newPage();
    const session: LiveSession = {
      name,
      spec,
      page,
      context,
      browser,
      proc,
      width,
      recordScale: scale,
      wallCreateMs,
      marks: new Map(),
      lastUseSceneIndex,
      crashed: false,
    };
    page.on('crash', () => {
      session.crashed = true;
    });
    try {
      await page.goto(url, { waitUntil: 'load' });
      if (spec.zoom && spec.zoom !== 1) {
        await page.addStyleTag({ content: `html { zoom: ${spec.zoom}; }` });
      }
      await runActions(page, spec.prepActions, { showClicks: spec.showClicks ?? true });
      await page.waitForTimeout(SETTLE_MS);
    } catch (err) {
      await close(session).catch(() => undefined);
      throw err;
    }
    live.set(name, session);
    return session;
  }

  function assertAlive(session: LiveSession, sceneId: string): void {
    if (session.crashed) {
      throw new Error(`session "${session.name}" crashed before/while scene "${sceneId}" ran`);
    }
  }

  async function close(session: LiveSession): Promise<void> {
    const wallCloseMs = Date.now();
    const videoHandle = session.page.video();
    await session.context.close().catch(() => undefined);
    await session.browser.close().catch(() => undefined);
    session.proc?.kill('SIGTERM');
    if (!videoHandle) {
      throw new Error(`session "${session.name}": no recording handle at close`);
    }
    const webm = await videoHandle.path();
    const webmDurSec = probeDurationSec(webm);
    const wallSpanSec = (wallCloseMs - session.wallCreateMs) / 1000;
    const headGapSec = Math.max(0, wallSpanSec - webmDurSec);
    if (headGapSec >= 30) {
      throw new Error(
        `session "${session.name}": headGapSec=${headGapSec.toFixed(1)} (wallSpan=${wallSpanSec.toFixed(1)}s, webm=${webmDurSec.toFixed(1)}s) — timestamp model broke, refusing to cut`
      );
    }
    session.result = { webm, webmDurSec, headGapSec };
    closeInfo.set(session.name, { wallCloseMs });
    live.delete(session.name);
    closed.set(session.name, session);
    console.log(
      `[video] session ${session.name} closed: webm=${webmDurSec.toFixed(2)}s headGap=${headGapSec.toFixed(2)}s`
    );
  }

  function videoTime(session: LiveSession, wallMs: number): number {
    const r = session.result;
    if (!r) throw new Error(`session "${session.name}" not closed yet`);
    const t = (wallMs - session.wallCreateMs) / 1000 - r.headGapSec;
    return Math.min(Math.max(t, 0), r.webmDurSec);
  }

  return {
    beginScene(sceneIndex) {
      currentSceneIndex = sceneIndex;
    },

    async acquire(name, need, sceneId) {
      const spec = opts.storyboard.sessions?.[name];
      if (!spec) throw new Error(`scene "${sceneId}": unknown session "${name}"`);
      const want: SessionWidth = spec.width ?? 'full';
      if (want !== need) {
        throw new Error(
          `scene "${sceneId}" needs a '${need}' pane but session "${name}" is '${want}' — declare a separate ${need}-width session`
        );
      }
      const existing = live.get(name);
      if (existing) {
        assertAlive(existing, sceneId);
        return existing;
      }
      if (closed.has(name)) {
        throw new Error(
          `scene "${sceneId}": session "${name}" was already closed after its last use — scene ordering bug`
        );
      }
      const last = lastUse.get(name);
      if (last === undefined) throw new Error(`session "${name}" is never referenced`);
      console.log(`[video] creating session ${name} (for scene ${sceneId})...`);
      return create(name, spec, sceneId, last);
    },

    async acquireAnonymous(spec, need, sceneId) {
      const name = `__anon:${sceneId}:${live.size + closed.size}`;
      console.log(`[video] creating anonymous session for scene ${sceneId}...`);
      // Anonymous sessions live exactly as long as their own scene: the
      // loop's closeFinished(currentSceneIndex) call closes them.
      return create(name, { ...spec, width: need }, sceneId, currentSceneIndex);
    },

    async markStart(session, sceneId) {
      assertAlive(session, sceneId);
      await session.page.waitForTimeout(SETTLE_MS);
      const m = session.marks.get(sceneId) ?? { startMs: 0, endMs: 0 };
      m.startMs = Date.now();
      session.marks.set(sceneId, m);
    },

    async markEnd(session, sceneId) {
      assertAlive(session, sceneId);
      await session.page.waitForTimeout(SETTLE_MS);
      const m = session.marks.get(sceneId);
      if (!m)
        throw new Error(`session "${session.name}": markEnd without markStart for "${sceneId}"`);
      m.endMs = Date.now();
    },

    async closeFinished(sceneIndex) {
      for (const session of [...live.values()]) {
        if (session.lastUseSceneIndex === sceneIndex) await close(session);
      }
    },

    async closeAll() {
      for (const session of [...live.values()]) {
        await close(session).catch((err) => {
          console.error(`[video] session ${session.name} close failed: ${String(err)}`);
        });
      }
    },

    cutSegment(sessionName, sceneId, outMp4, padFilter) {
      const session = closed.get(sessionName);
      if (!session?.result) {
        throw new Error(`cutSegment: session "${sessionName}" has no closed recording`);
      }
      const marks = session.marks.get(sceneId);
      if (!marks || !marks.endMs) {
        throw new Error(`cutSegment: session "${sessionName}" has no marks for scene "${sceneId}"`);
      }
      const start = videoTime(session, marks.startMs);
      const end = videoTime(session, marks.endMs);
      if (end <= start) {
        throw new Error(
          `cutSegment: scene "${sceneId}" maps to an empty slice (${start.toFixed(3)}..${end.toFixed(3)}) in session "${sessionName}"`
        );
      }
      const durSec = end - start;
      cutSegmentMp4(session.result.webm, start, durSec, outMp4, padFilter);
      if (opts.debugFramesDir) {
        // Sanitize ':' (and other Windows-illegal chars) from scene IDs like
        // 'vscode-versions:left' so debug frame filenames never break checkout.
        const safeId = sceneId.replace(/[:<>"|?*]/g, '-');
        extractPosterJpg(
          session.result.webm,
          start,
          path.join(opts.debugFramesDir, `${safeId}.segstart.jpg`)
        );
        extractPosterJpg(
          session.result.webm,
          Math.max(start, end - 0.05),
          path.join(opts.debugFramesDir, `${safeId}.segend.jpg`)
        );
      }
      return { durSec };
    },

    debugInfo() {
      return [...closed.values()].map((s) => {
        const info = closeInfo.get(s.name);
        const wallSpanSec = info ? (info.wallCloseMs - s.wallCreateMs) / 1000 : 0;
        return {
          name: s.name,
          webmDurSec: s.result?.webmDurSec ?? 0,
          wallSpanSec,
          headGapSec: s.result?.headGapSec ?? 0,
          scenes: [...s.marks.entries()].map(([id, m]) => ({
            id,
            videoStartSec: videoTime(s, m.startMs),
            videoEndSec: videoTime(s, m.endMs),
          })),
        };
      });
    },
  };
}
