import { readFileSync, writeFileSync } from 'node:fs';
import { Resvg } from '@resvg/resvg-js';
import { VIDEO_W, VIDEO_H } from '../ffmpeg-video.ts';

export function rasterizeSvgTo1080p(
  svgPath: string,
  pngPath: string,
  substitutions: Record<string, string> = {},
  rawSubstitutions: Record<string, string> = {}
): void {
  let svg = readFileSync(svgPath, 'utf8');
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
    font: { loadSystemFonts: true },
  });
  const pngBuf = resvg.render().asPng();
  writeFileSync(pngPath, pngBuf);
  void VIDEO_H;
}

export function escapeXmlText(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
