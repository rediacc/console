import { readFileSync, writeFileSync } from 'node:fs';
import { Resvg } from '@resvg/resvg-js';
import { VIDEO_H, VIDEO_W } from '../ffmpeg-video.ts';
import { assertCardFontsUsable, cardFontsFor, vendoredFontFiles } from './card-fonts.ts';

export function rasterizeSvgTo1080p(
  svgPath: string,
  pngPath: string,
  lang: string,
  substitutions: Record<string, string> = {},
  rawSubstitutions: Record<string, string> = {}
): void {
  // Throws when this locale's family is absent or cannot draw its script, so a
  // font problem stops the render instead of shipping detached Arabic letters
  // or bitmap CJK. See card-fonts.ts for the failure this replaced.
  assertCardFontsUsable(lang);

  let svg = readFileSync(svgPath, 'utf8');
  // Injected here rather than at the call sites so no card template can be
  // rendered with a family that was chosen for a different locale.
  const fonts = cardFontsFor(lang);
  for (const [k, v] of Object.entries({ FONT_SANS: fonts.sans, FONT_MONO: fonts.mono })) {
    svg = svg.replaceAll(`{{${k}}}`, v);
  }
  for (const [k, v] of Object.entries(substitutions)) {
    svg = svg.replaceAll(`{{${k}}}`, escapeXmlText(v));
  }
  // Raw values are pre-escaped SVG fragments (e.g. multi-line command
  // markup with <tspan> line breaks) — substituted verbatim.
  for (const [k, v] of Object.entries(rawSubstitutions)) {
    svg = svg.replaceAll(`{{${k}}}`, v);
  }
  const resvg = new Resvg(svg, {
    fitTo: { mode: 'width', value: VIDEO_W },
    background: 'rgba(0,0,0,0)',
    // System fonts still supply Inter and JetBrains Mono for the Latin locales,
    // so their output is unchanged. The vendored faces are added so the Arabic
    // render does not depend on what the host happens to have installed.
    font: { loadSystemFonts: true, fontFiles: vendoredFontFiles() },
  });
  const pngBuf = resvg.render().asPng();
  writeFileSync(pngPath, pngBuf);
  void VIDEO_H;
}

export function escapeXmlText(s: string): string {
  return s.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
}
