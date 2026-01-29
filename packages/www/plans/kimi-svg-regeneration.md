# Kimi SVG Regeneration Plan

Regenerate all 10 hero/bottom SVG illustrations using Kimi CLI. The current versions (mix of codex/gemini/Claude-generated) should be replaced with Kimi-generated ones.

---

## Setup

```bash
ILLUST_DIR="/home/muhammed/monorepo/console/.worktrees/0129-1/packages/www/src/assets/images/illustrations"
cd "$ILLUST_DIR"
```

## Design Language (MUST include in every prompt)

```
Design language rules:
- Background: #f5f5f5
- Brand color: #556b2f (olive green) — use for checkmarks, status lights, accents
- Gray palette ONLY: #1a1a1a (darkest), #2d2d2d, #3d3d3d, #e0e0e0 (lightest)
- White: #ffffff (for text on dark backgrounds)
- NO other colors allowed (no red, blue, lime green, etc.)
- Drop shadow filter on major elements
- Decorative circles at bottom corners (fill #e0e0e0)
- Server rack motifs where relevant (gradient #2d2d2d → #1a1a1a)
- No JavaScript or <script> tags — pure static SVG only
- Use font-family="Arial, sans-serif" for any text
```

---

## Files to Generate (10 total)

### 1. disaster-recovery-hero.svg

**ViewBox:** `0 0 1200 675`

```bash
kimi -y -p 'Create an SVG file named "disaster-recovery-hero.svg" with viewBox="0 0 1200 675" width="1200" height="675".

Design language: background #f5f5f5, brand color #556b2f (olive green), grays #1a1a1a/#2d2d2d/#3d3d3d/#e0e0e0, white #ffffff. Drop shadow filter on major elements. Decorative #e0e0e0 circles at bottom. No other colors. No JavaScript. Pure static SVG. font-family="Arial, sans-serif".

Concept: Isometric view of 5 stacked rectangular server layers. Each layer alternates between #2d2d2d and #3d3d3d fills. Each layer has a green (#556b2f) checkmark badge on the right edge. A large shield shape (#2d2d2d fill) with a #556b2f checkmark floats above the stack, centered. Subtle glow lines emanate from each verified layer. Decorative circles at bottom corners.

Output ONLY the SVG code to the file, nothing else.'
```

### 2. disaster-recovery-bottom.svg

**ViewBox:** `0 0 1100 618`

```bash
kimi -y -p 'Create an SVG file named "disaster-recovery-bottom.svg" with viewBox="0 0 1100 618" width="1100" height="618".

Design language: background #f5f5f5, brand color #556b2f (olive green), grays #1a1a1a/#2d2d2d/#3d3d3d/#e0e0e0, white #ffffff. Drop shadow filter. No other colors. No JavaScript. Pure static SVG. font-family="Arial, sans-serif".

Concept: Dark dashboard (main frame #1a1a1a, header bar #2d2d2d with 3 small #3d3d3d dots). Contains 3 vertical panels side by side (#2d2d2d fill, rounded corners):
- Left panel header "30 Days" — 9 checklist rows (each row: #556b2f checkmark stroke + #3d3d3d rectangle bar)
- Center panel header "60 Days" — circular badge with "100%" text in #556b2f, a bar chart below (6 bars in #556b2f with varying heights and opacity), then 3 checklist rows
- Right panel header "90 Days" — 10 checklist rows

Panel headers in #e0e0e0 text. Decorative circles at bottom.

Output ONLY the SVG code to the file, nothing else.'
```

### 3. threat-response-hero.svg

**ViewBox:** `0 0 1200 675`

```bash
kimi -y -p 'Create an SVG file named "threat-response-hero.svg" with viewBox="0 0 1200 675" width="1200" height="675".

Design language: background #f5f5f5, brand color #556b2f (olive green), grays #1a1a1a/#2d2d2d/#3d3d3d/#e0e0e0, white #ffffff. Drop shadow filter. No other colors. No JavaScript. Pure static SVG. font-family="Arial, sans-serif".

Concept: Large circular vault door in center (#2d2d2d fill, #3d3d3d border). Spoked wheel handle (6 rectangular spokes in #e0e0e0 radiating from center, with #3d3d3d hub). Two crossed chains (#3d3d3d rectangles rotated ±25°) with a central padlock overlay (#e0e0e0 body, #3d3d3d shackle). A shield (#556b2f) with white checkmark sits above the vault. Dashed attack arrows from left and right (#1a1a1a) deflect off the vault surface. Subtle radial guide lines behind vault (#3d3d3d, low opacity). Decorative circles at bottom.

Output ONLY the SVG code to the file, nothing else.'
```

### 4. threat-response-bottom.svg

**ViewBox:** `0 0 1100 618`

```bash
kimi -y -p 'Create an SVG file named "threat-response-bottom.svg" with viewBox="0 0 1100 618" width="1100" height="618".

Design language: background #f5f5f5, brand color #556b2f (olive green), grays #1a1a1a/#2d2d2d/#3d3d3d/#e0e0e0, white #ffffff. Drop shadow filter. No other colors. No JavaScript. Pure static SVG. font-family="Arial, sans-serif".

Concept: Split layout with dashed center divider line (#3d3d3d).

Left side — header "Manual" (#3d3d3d text, bold): A winding/curved dashed path (#3d3d3d) connecting 4 circular nodes. Each node has an X mark (#3d3d3d strokes) inside a #e0e0e0 circle. At the bottom: an hourglass icon (#3d3d3d) and "Days" label in bold.

Right side — header "Automated" (#1a1a1a text, bold): A straight vertical line (#556b2f, thick) connecting 3 circular nodes. Each node is a #556b2f filled circle with a white checkmark. At the bottom: a lightning bolt icon (#556b2f fill) and "Minutes" label in bold.

Decorative circles at bottom corners.

Output ONLY the SVG code to the file, nothing else.'
```

### 5. data-security-hero.svg

**ViewBox:** `0 0 1200 675`

```bash
kimi -y -p 'Create an SVG file named "data-security-hero.svg" with viewBox="0 0 1200 675" width="1200" height="675".

Design language: background #f5f5f5, brand color #556b2f (olive green), grays #1a1a1a/#2d2d2d/#3d3d3d/#e0e0e0, white #ffffff. Drop shadow filter. No other colors. No JavaScript. Pure static SVG. font-family="Arial, sans-serif".

Concept: Two tall server racks on left (x~90) and right (x~930) edges. Each rack: #2d2d2d→#1a1a1a gradient fill, 180×395px, rounded corners, containing 4 drive bays (#2d2d2d with #3d3d3d border) with #556b2f status light dots and small #3d3d3d indicator bars.

Between the racks: a horizontal transparent pipeline (wide rounded rectangle, #556b2f fill-opacity 0.08, #556b2f stroke). Inside the pipeline: 5 data packet rectangles (#e0e0e0 fill, #3d3d3d border) evenly spaced, each containing a small padlock icon (#556b2f stroke — rectangle body + arc shackle). Small directional arrows at pipe ends (#556b2f, low opacity).

Decorative #e0e0e0 circles at bottom.

Output ONLY the SVG code to the file, nothing else.'
```

### 6. data-security-bottom.svg

**ViewBox:** `0 0 1100 618`

```bash
kimi -y -p 'Create an SVG file named "data-security-bottom.svg" with viewBox="0 0 1100 618" width="1100" height="618".

Design language: background #f5f5f5, brand color #556b2f (olive green), grays #1a1a1a/#2d2d2d/#3d3d3d/#e0e0e0, white #ffffff. Drop shadow filter. No other colors. No JavaScript. Pure static SVG. font-family="Arial, sans-serif".

Concept: Light-themed dashboard (white fill main area, #2d2d2d header bar with 3 small #3d3d3d dots). Three columns separated by #e0e0e0 vertical lines:

Column 1 "Migration" (#1a1a1a bold header): A circular progress ring (#e0e0e0 track, #556b2f filled arc showing 100%), "100%" text in center (#556b2f), "Complete" subtitle (#3d3d3d). Below: a full progress bar (#556b2f). Below that: 4 status rows each with a #556b2f dot and #3d3d3d text label.

Column 2 "Audit Trail" (#1a1a1a bold header): 6 log entry rows. Each row: #556b2f dot, two #e0e0e0 rectangle bars (varying widths), monospace timestamp text (#3d3d3d). A dashed vertical timeline line connecting the dots (#556b2f, low opacity).

Column 3 "Security" (#1a1a1a bold header): 2×3 grid of padlock icons. Each: #f5f5f5 rounded rectangle card with #e0e0e0 border, #556b2f stroke padlock (rectangle body + arc shackle), label below in #3d3d3d bold (SOC 2, ISO 27001, GDPR, AES-256, TLS 1.3, RBAC).

Decorative circles at bottom.

Output ONLY the SVG code to the file, nothing else.'
```

### 7. system-portability-hero.svg

**ViewBox:** `0 0 1200 675`

```bash
kimi -y -p 'Create an SVG file named "system-portability-hero.svg" with viewBox="0 0 1200 675" width="1200" height="675".

Design language: background #f5f5f5, brand color #556b2f (olive green), grays #1a1a1a/#2d2d2d/#3d3d3d/#e0e0e0, white #ffffff. Drop shadow filter. No other colors except subtle cloud tints. No JavaScript. Pure static SVG. font-family="Arial, sans-serif".

Concept: Three large cloud shapes in a horizontal row. Left cloud has a subtle blue tint (#4a6fa5 at opacity 0.3 overlay). Center cloud has a subtle red tint (#a54a4a at opacity 0.3 overlay). Right cloud has a subtle yellow tint (#a5924a at opacity 0.3 overlay). Each cloud base is #f5f5f5 fill with #3d3d3d stroke.

Each cloud contains a small server cube icon (#e0e0e0 fill, #2d2d2d stroke, with drive bay details and #1a1a1a status dots).

Between clouds: bidirectional arrows (#556b2f stroke, thick, with arrowheads). Below the clouds: a rectangular infrastructure box (#e0e0e0→#f5f5f5 gradient fill, #3d3d3d stroke) with two drive bays and status dots. Arrows connect the box up to the clouds (#556b2f).

Decorative #e0e0e0 circles at bottom.

Output ONLY the SVG code to the file, nothing else.'
```

### 8. system-portability-bottom.svg

**ViewBox:** `0 0 1100 618`

```bash
kimi -y -p 'Create an SVG file named "system-portability-bottom.svg" with viewBox="0 0 1100 618" width="1100" height="618".

Design language: background #f5f5f5, brand color #556b2f (olive green), grays #1a1a1a/#2d2d2d/#3d3d3d/#e0e0e0, white #ffffff. Drop shadow filter. No other colors. No JavaScript. Pure static SVG. font-family="Arial, sans-serif".

Concept: Simplified world map outline — continents as basic polygon shapes (#e0e0e0 fill and stroke, opacity 0.2). Three cloud nodes positioned at:
- North America region (left), labeled "US" (#1a1a1a bold text)
- Europe region (center), labeled "EU"
- Asia-Pacific region (right), labeled "APAC"

Each cloud: #e0e0e0 fill cloud path with drop shadow and bold label.

Dashed curved connection lines (#556b2f stroke, stroke-width 4) linking all three clouds (US↔EU, EU↔APAC, APAC↔US). At the midpoint of each connection line: a #556b2f filled circle with a white checkmark stroke inside.

Center of map: a shield icon (#2d2d2d fill) with #556b2f checkmark inside, with drop shadow.

Decorative background circles (#e0e0e0, low opacity).

Output ONLY the SVG code to the file, nothing else.'
```

### 9. development-environments-hero.svg

**ViewBox:** `0 0 1200 675`

```bash
kimi -y -p 'Create an SVG file named "development-environments-hero.svg" with viewBox="0 0 1200 675" width="1200" height="675".

Design language: background #f5f5f5, brand color #556b2f (olive green), grays #1a1a1a/#2d2d2d/#3d3d3d/#e0e0e0, white #ffffff. Drop shadow filter. No other colors. No JavaScript. Pure static SVG. font-family="Arial, sans-serif".

Concept: Left side: A developer figure (stick figure with #3d3d3d strokes — circle head, line body, line arms, line legs) sitting at a desk with a laptop (#e0e0e0 body, #1a1a1a screen showing thin code-like lines in #e0e0e0).

Center: A large lightning bolt shape (#556b2f fill) with "60s" text below it (#1a1a1a bold, large font).

Right side: Two stacked server boxes with drop shadow. Top server labeled "Production" (#1a1a1a text above), bottom server labeled "Dev Clone". Each server: #2d2d2d→#1a1a1a gradient fill, 300×150px, rounded corners, with 3 drive bays (#3d3d3d) and 3 status light dots (#556b2f, using proper cy= attribute).

A dashed curved arrow (#556b2f stroke) connecting the developer laptop area to the Dev Clone server.

Decorative #e0e0e0 circles at bottom corners.

Output ONLY the SVG code to the file, nothing else.'
```

### 10. development-environments-bottom.svg

**ViewBox:** `0 0 1100 618`

```bash
kimi -y -p 'Create an SVG file named "development-environments-bottom.svg" with viewBox="0 0 1100 618" width="1100" height="618".

Design language: background #f5f5f5, brand color #556b2f (olive green), grays #1a1a1a/#2d2d2d/#3d3d3d/#e0e0e0, white #ffffff. Drop shadow filter. No other colors. No JavaScript. Pure static SVG. font-family="Arial, sans-serif".

Concept: Horizontal pipeline flow at vertical center (~y=250-320):

1. "Git Branch" — circle icon (70×70 rounded, white fill, #e0e0e0 stroke) with a branch symbol inside (#3d3d3d strokes). Label below: "Git Branch" bold.

2. → Green checkmark circle (#556b2f) → connecting line (#3d3d3d) →

3. "Rediacc" — rounded rectangle (130×70, white fill, #e0e0e0 stroke) with lightning bolt icon (#556b2f) inside. Label below: "Rediacc" bold.

4. → Green checkmark circle → connecting line →

5. "Prod Clone" — rounded rectangle with server icon (#3d3d3d strokes, white fill) inside. Label below: "Prod Clone" bold.

6. → Green checkmark circle → connecting line →

7. "Dev Environment" — rounded rectangle with monitor/terminal icon inside (#3d3d3d strokes, #556b2f accent). Label below: "Dev Environment" bold.

8. → Green checkmark circle → connecting line →

9. "Merge" — circle icon with merge symbol inside (#3d3d3d strokes). Label below: "Merge" bold.

Below the merge icon: a dashed arrow going down to a "Cleanup" rounded rectangle (100×60, white fill) with recycling/arrows icon (#3d3d3d). Label: "Cleanup" bold.

Bottom row (y~550): 4 small icon+text pairs evenly spaced — checkmark circle "Zero Tickets", equals icon "Parity", dollar icon "Cost Opt.", person icon "Self-service". Each icon in a small white circle with #e0e0e0 border.

All connecting elements use drop shadow. All icons use the gray palette only with #556b2f accents.

Output ONLY the SVG code to the file, nothing else.'
```

---

## Execution

Run each command sequentially from the `$ILLUST_DIR` directory:

```bash
cd "$ILLUST_DIR"

# Run each kimi command one at a time
# (Kimi parallel execution has been unreliable — run sequentially)
```

## Post-Generation Checklist

After all 10 files are generated:

1. **Validate no scripts:** `grep -l '<script' *.svg` — should return nothing
2. **Validate palette:** `grep -rE '#[0-9a-fA-F]{6}' *-hero.svg *-bottom.svg | grep -vE '#f5f5f5|#556b2f|#1a1a1a|#2d2d2d|#3d3d3d|#e0e0e0|#ffffff|#000000|#4a6fa5|#a54a4a|#a5924a' | head -20` — check for off-palette colors
3. **Validate attributes:** `grep -n 'y="[0-9]' *-hero.svg *-bottom.svg | grep -v 'cy=\|ry=\|dy=\|y="0 '` — check for `y=` that should be `cy=` on circles
4. **Build:** `cd /home/muhammed/monorepo/console/.worktrees/0129-1/packages/www && npx astro build` — should build 240 pages
5. **Visual check:** `npm run dev` → visit each solution page and verify hero + bottom images render correctly

## Files Reference

All files are in: `src/assets/images/illustrations/`

Imports are already configured in `src/config/solutions.ts` — no import changes needed, just replace the SVG file contents.
