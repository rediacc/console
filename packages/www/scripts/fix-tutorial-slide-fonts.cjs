#!/usr/bin/env node
// One-shot SVG font normalizer for tutorial slides.
//
// Converts CSS `font: <weight> <size>px <family>` shorthand to explicit
// `font-weight`, `font-size`, `font-family` properties because resvg-js
// doesn't parse the shorthand and silently falls back to serif fonts.
//
// Also bumps undersized `.num-text` (circles with text < 0.7 × radius) so the
// numbers fill their badges at 1920×1080.

const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..', 'public', 'img', 'tutorials');
const files = listSvgs(ROOT);

const UNDERSIZED_NUM_BUMPS = {
  'tutorial-backup-restore/slide-1.svg':  { className: 'num-text', toPx: 56 },
  'tutorial-deploy-app/slide-1.svg':      { className: 'num-text', toPx: 56 },
  'tutorial-networking/slide-1.svg':      { className: 'num-text', toPx: 50 },
  'tutorial-ssh-keys/slide-1.svg':        { className: 'num-text', toPx: 56 },
};

const FONT_SHORTHAND = /\.([a-zA-Z-]+)\s*\{\s*([^}]*?)font:\s*([0-9]+)\s+([0-9]+)px\s+([^;]+);([^}]*)\}/g;

let edited = 0;
for (const file of files) {
  const rel = path.relative(ROOT, file);
  let src = fs.readFileSync(file, 'utf8');
  const before = src;

  src = src.replace(FONT_SHORTHAND, (_m, cls, prefix, weight, size, family, suffix) => {
    const bump = UNDERSIZED_NUM_BUMPS[rel];
    const finalSize = bump && bump.className === cls ? bump.toPx : Number(size);
    return `.${cls} { ${prefix}font-weight: ${weight}; font-size: ${finalSize}px; font-family: ${family.trim()};${suffix}}`;
  });

  if (src !== before) {
    fs.writeFileSync(file, src);
    console.log(`updated ${rel}`);
    edited++;
  }
}
console.log(`\n${edited} file(s) updated`);

function listSvgs(root) {
  const out = [];
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith('.svg') && entry.name.startsWith('slide-')) out.push(full);
    }
  }
  walk(root);
  return out;
}
