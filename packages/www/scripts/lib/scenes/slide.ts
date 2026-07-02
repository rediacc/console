import path from 'node:path';
import { existsSync, readFileSync } from 'node:fs';
import type { SlideScene, TitleScene, OutroScene, CastNarratedScene } from '../storyboard.ts';
import { makeFreezeMp4, makeSilentFreezeMp4, PAD_FILTER_CENTER } from '../ffmpeg-video.ts';
import type { ParsedCast } from '../cast-splitter.ts';
import { escapeXmlText, rasterizeSvgTo1080p } from './svg-render.ts';
import type { SceneContext, TranscriptDoc } from './index.ts';

const SUB_ITEM_SLOTS = 8;
// JetBrains Mono at 28px in the 1120px command column (x=640..1760).
const COMMAND_WRAP_COLS = 64;
const COMMAND_MAX_LINES = 2;
// Must match the command column x offset in title-card.svg.
const COMMAND_COLUMN_X = 640;
const COMMAND_LINE_DY = 30;

/**
 * Step-card visual constants. The step card is a per-cast-narrated-scene
 * variant of the title card with one row at full opacity and the others
 * dimmed — a "you are here" anchor shown during the silent prePause beat.
 */
const STEP_CARD_ACTIVE_OPACITY = '1';
const STEP_CARD_INACTIVE_OPACITY = '0.30';

export function compileSlide(scene: SlideScene, ctx: SceneContext): string {
  const svgPath = path.join(ctx.wwwPublicRoot, 'img', 'tutorials', ctx.tutorial, scene.src);
  return renderSvgSlide(svgPath, scene.id, scene.narrationKey, ctx);
}

export function compileTitle(scene: TitleScene, ctx: SceneContext): string {
  const svgPath = resolveCardSvg(scene.src ?? 'title-card.svg', 'title-card.svg', ctx);
  // Intro card: activeIndex=null => all rows at full opacity.
  const { subs, raw } = buildTitleCardSubs(ctx, null);
  return renderSvgSlide(svgPath, scene.id, scene.narrationKey, ctx, subs, raw);
}

/**
 * Duration of a `title`/`slide`/`outro` scene: exactly its narration's audio
 * length -- `renderSvgSlide` freezes a static image and pads/holds it to
 * match that duration via `makeFreezeMp4`, so no rendering is needed to know
 * the final length. Shared by all three scene types since they all resolve
 * through `renderSvgSlide`.
 */
export function computeFreezeSceneDurationDry(narrationKey: string, ctx: SceneContext): number {
  const narration = ctx.narrations.get(narrationKey);
  return narration.audioDurationSec ?? 0;
}

/**
 * Render a silent per-step "you are here" card for `durationSec` seconds.
 * Reuses the title-card SVG with the same data assembly as `compileTitle`,
 * but dims the inactive sub-item rows to STEP_CARD_INACTIVE_OPACITY so only
 * the row at `activeIndex` (1-based) stands out.
 *
 * Used at the start of every cast-narrated scene (see scenes/cast.ts) in
 * place of the previous 0.5s held-terminal-first-frame prePause.
 */
export function renderStepCard(
  ctx: SceneContext,
  activeIndex: number,
  durationSec: number,
  sceneId: string
): string {
  const svgPath = resolveCardSvg('title-card.svg', 'title-card.svg', ctx);
  const png = path.join(ctx.tmp, `${sceneId}.png`);
  const mp4 = path.join(ctx.tmp, `${sceneId}.mp4`);
  const { subs, raw } = buildTitleCardSubs(ctx, activeIndex);
  rasterizeSvgTo1080p(svgPath, png, subs, raw);
  makeSilentFreezeMp4(png, durationSec, mp4, PAD_FILTER_CENTER);
  return mp4;
}

/**
 * Build the placeholder substitution map for the title-card SVG. Shared by
 * the intro card (activeIndex = null → all rows at full opacity) and the
 * per-step card (activeIndex 1..N → only the active row at full opacity).
 */
function buildTitleCardSubs(
  ctx: SceneContext,
  activeIndex: number | null
): { subs: Record<string, string>; raw: Record<string, string> } {
  // Intro card (activeIndex === null) keeps full brightness everywhere.
  // Step cards spotlight one row by dimming the header AND all other rows to
  // the same low opacity, so the active row is the only fully bright element.
  const isStepCard = activeIndex !== null;
  const subs: Record<string, string> = {
    TITLE: lookupTitle(ctx.transcript, ctx.transcriptEn, ctx.tutorial),
    SUBTITLE: '',
    HEADER_OPACITY: isStepCard ? STEP_CARD_INACTIVE_OPACITY : STEP_CARD_ACTIVE_OPACITY,
  };
  // Commands are injected as raw SVG fragments so long commands can wrap
  // onto a second <tspan> line instead of being truncated with an ellipsis.
  const raw: Record<string, string> = {};
  const subItems = buildSubItems(ctx);
  for (let i = 0; i < SUB_ITEM_SLOTS; i++) {
    const oneBased = i + 1;
    subs[`ITEM_${oneBased}_LABEL`] = subItems[i]?.label ?? '';
    raw[`ITEM_${oneBased}_COMMAND`] = buildCommandMarkup(subItems[i]?.command ?? '');
    subs[`ITEM_${oneBased}_OPACITY`] =
      !isStepCard || oneBased === activeIndex
        ? STEP_CARD_ACTIVE_OPACITY
        : STEP_CARD_INACTIVE_OPACITY;
  }
  return { subs, raw };
}

/**
 * Word-wrap a command into at most COMMAND_MAX_LINES lines of
 * COMMAND_WRAP_COLS columns and emit it as SVG text content. Line two is a
 * relative <tspan>; only a command overflowing BOTH lines gets an ellipsis.
 */
function buildCommandMarkup(command: string): string {
  const words = command.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let current = '';
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length <= COMMAND_WRAP_COLS || !current) {
      current = candidate;
      continue;
    }
    lines.push(current);
    current = word;
    if (lines.length === COMMAND_MAX_LINES) break;
  }
  if (lines.length < COMMAND_MAX_LINES && current) {
    lines.push(current);
    current = '';
  }
  if (current || lines.length > COMMAND_MAX_LINES) {
    const last = lines[COMMAND_MAX_LINES - 1] ?? '';
    lines[COMMAND_MAX_LINES - 1] = `${last.slice(0, COMMAND_WRAP_COLS - 1)}…`;
    lines.length = COMMAND_MAX_LINES;
  }
  return lines
    .map((line, idx) =>
      idx === 0
        ? escapeXmlText(line)
        : `<tspan x="${COMMAND_COLUMN_X}" dy="${COMMAND_LINE_DY}">${escapeXmlText(line)}</tspan>`
    )
    .join('');
}

export function compileOutro(scene: OutroScene, ctx: SceneContext): string {
  const svgPath = resolveCardSvg(scene.src ?? 'outro-card.svg', 'outro-card.svg', ctx);
  const nextKey = ctx.storyboard.nextTutorialKey ?? '';
  const nextTitle = nextKey ? lookupNextTutorialTitle(ctx.wwwPublicRoot, ctx.lang, nextKey) : '';
  const nextHref = nextKey ? `/${ctx.lang}/docs/${nextKey}` : '';
  return renderSvgSlide(svgPath, scene.id, scene.narrationKey, ctx, {
    NEXT_TITLE: nextTitle,
    NEXT_HREF: nextHref,
  });
}

function resolveCardSvg(filename: string, templateName: string, ctx: SceneContext): string {
  const perTutorial = path.join(ctx.wwwPublicRoot, 'img', 'tutorials', ctx.tutorial, filename);
  if (existsSync(perTutorial)) return perTutorial;
  return path.join(ctx.wwwPublicRoot, 'img', 'tutorials', '_template', templateName);
}

function renderSvgSlide(
  svgPath: string,
  sceneId: string,
  narrationKey: string,
  ctx: SceneContext,
  substitutions: Record<string, string> = {},
  rawSubstitutions: Record<string, string> = {}
): string {
  const png = path.join(ctx.tmp, `${sceneId}.png`);
  const mp4 = path.join(ctx.tmp, `${sceneId}.mp4`);
  rasterizeSvgTo1080p(svgPath, png, substitutions, rawSubstitutions);
  const narration = ctx.narrations.get(narrationKey);
  const audioPath = ctx.narrations.resolvePath(narration.audioSrc);
  const duration = narration.audioDurationSec ?? 0;
  makeFreezeMp4(png, audioPath, duration, mp4, PAD_FILTER_CENTER);
  return mp4;
}

function isAuthored(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0 && !value.startsWith('TODO:');
}

/**
 * Lookup chain for the title-card big-title:
 *   1. per-language transcript.title
 *   2. English transcript.title       (fallback for untranslated locales)
 *   3. titleCase(tutorial key)         (last-resort auto-derive)
 */
function lookupTitle(
  transcript: TranscriptDoc | null,
  transcriptEn: TranscriptDoc | null,
  tutorial: string
): string {
  const fromLang = transcript?.title;
  if (isAuthored(fromLang)) return fromLang.trim();
  const fromEn = transcriptEn?.title;
  if (isAuthored(fromEn)) return fromEn.trim();
  return tutorial
    .replace(/^tutorial-/, '')
    .split('-')
    .map((w) => (w.length > 0 ? w[0].toUpperCase() + w.slice(1) : w))
    .join(' ');
}

/**
 * Read the next tutorial's transcript.title in the current language, falling
 * back to English when the per-lang transcript hasn't been translated yet.
 */
function lookupNextTutorialTitle(wwwPublicRoot: string, lang: string, nextKey: string): string {
  // wwwPublicRoot points at <wwwRoot>/public; the transcripts live under
  // <wwwRoot>/src/data, two dirs up from public.
  const dataDir = path.join(wwwPublicRoot, '..', 'src', 'data', 'tutorial-transcripts');
  const tryRead = (whichLang: string): TranscriptDoc | null => {
    const p = path.join(dataDir, whichLang, `${nextKey}.json`);
    if (!existsSync(p)) return null;
    try {
      return JSON.parse(readFileSync(p, 'utf8')) as TranscriptDoc;
    } catch {
      return null;
    }
  };
  const langDoc = tryRead(lang);
  if (isAuthored(langDoc?.title)) return (langDoc!.title as string).trim();
  if (lang !== 'en') {
    const enDoc = tryRead('en');
    if (isAuthored(enDoc?.title)) return (enDoc!.title as string).trim();
  }
  return '';
}

interface TranscriptEvent {
  id?: string;
  markerIndex?: number;
  cardLabel?: string;
}

function readEvents(doc: TranscriptDoc | null): TranscriptEvent[] {
  if (!doc || !Array.isArray(doc.events)) return [];
  return doc.events as TranscriptEvent[];
}

/**
 * Walk cast-narrated scenes in storyboard order and produce the (label, command)
 * pairs rendered as title-card sub-items. Capped at SUB_ITEM_SLOTS — any tutorial
 * with more cast-narrated steps silently truncates (the SVG only has 8 slots).
 */
function buildSubItems(ctx: SceneContext): Array<{ label: string; command: string }> {
  const events = readEvents(ctx.transcript);
  const eventsEn = readEvents(ctx.transcriptEn);
  const items: Array<{ label: string; command: string }> = [];
  for (const scene of ctx.storyboard.scenes) {
    if (scene.type !== 'cast-narrated') continue;
    const castNarrated = scene as CastNarratedScene;
    const label = lookupCardLabel(events, eventsEn, castNarrated.markerIndex);
    // Cards show the FULL command (wrapped onto two lines when long) — the
    // recorded marker text, with `card.command` as an authored override.
    const command = castNarrated.card?.command ?? markerCommand(ctx.cast, castNarrated.markerIndex);
    items.push({ label, command });
    if (items.length >= SUB_ITEM_SLOTS) break;
  }
  return items;
}

function lookupCardLabel(
  events: TranscriptEvent[],
  eventsEn: TranscriptEvent[],
  markerIndex: number
): string {
  const langLabel = events.find((e) => e.markerIndex === markerIndex)?.cardLabel;
  if (isAuthored(langLabel)) return langLabel.trim();
  const enLabel = eventsEn.find((e) => e.markerIndex === markerIndex)?.cardLabel;
  if (isAuthored(enLabel)) return enLabel.trim();
  return '';
}

/** The full recorded command text of a cast marker. */
function markerCommand(cast: ParsedCast, markerIndex: number): string {
  const markers = cast.events.filter(([, k]) => k === 'm');
  return (markers[markerIndex]?.[2] ?? '').toString().trim();
}
