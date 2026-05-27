import path from 'node:path';
import { chromium } from 'playwright';
import type { BrowserScene } from '../storyboard.ts';
import { muxVideoWithAudio, PAD_FILTER_CENTER } from '../ffmpeg-video.ts';
import type { SceneContext } from './index.ts';

export async function compileBrowser(scene: BrowserScene, ctx: SceneContext): Promise<string> {
  const sceneDir = path.join(ctx.tmp, scene.id);
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: { dir: sceneDir, size: { width: 1920, height: 1080 } },
  });
  const page = await context.newPage();
  await page.goto(scene.url, { waitUntil: 'load' });

  if (scene.zoom && scene.zoom !== 1) {
    await page.addStyleTag({ content: `html { zoom: ${scene.zoom}; }` });
  }

  for (const action of scene.actions ?? []) {
    if (action.wait) await page.waitForTimeout(action.wait);
    if (action.highlight) {
      await page
        .locator(action.highlight)
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
      await page
        .locator(action.scrollTo)
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
    if (action.click)
      await page
        .locator(action.click)
        .first()
        .click()
        .catch(() => undefined);
  }

  await page.waitForTimeout(scene.durationSec * 1000);
  const videoHandle = page.video();
  await context.close();
  await browser.close();
  if (!videoHandle) throw new Error(`browser scene ${scene.id}: no recording handle`);
  const webm = await videoHandle.path();

  const narration = ctx.narrations.get(scene.narrationKey);
  const audioPath = ctx.narrations.resolvePath(narration.audioSrc);
  const targetDuration = Math.max(scene.durationSec, narration.audioDurationSec ?? 0);
  const mp4 = path.join(ctx.tmp, `${scene.id}.mp4`);
  muxVideoWithAudio(webm, audioPath, targetDuration, mp4, PAD_FILTER_CENTER);
  return mp4;
}
