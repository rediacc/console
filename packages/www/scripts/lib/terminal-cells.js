/**
 * Terminal cell arithmetic for cast validation: strip what the terminal drew as
 * control, and measure what it drew as visible cells.
 *
 * Extracted from validate-tutorial-cast-output.js, which had grown past the
 * max-lines limit. These are the cohesive, pure half of that file: no I/O, no
 * error collection, no knowledge of casts. They are also the only place the
 * validator needs raw control characters, so keeping them together confines that
 * to one module.
 *
 * Every regex here is built from NAMED char codes rather than written with escape
 * literals. A raw control character inside a regex is exactly what no-control-regex
 * exists to catch, and naming the character says which one is meant instead of
 * leaving a reader to decode an escape.
 */
const ESC = String.fromCharCode(0x1b);
const BEL = String.fromCharCode(0x07);
const CR = String.fromCharCode(0x0d);

/** CSI sequence: ESC [ params final-byte (colours, cursor moves). */
const ANSI_CSI_RE = new RegExp(`${ESC}\\[[0-9;]*[a-zA-Z]`, 'g');
/** OSC sequence: ESC ] ... BEL (window title and friends). */
const ANSI_OSC_RE = new RegExp(`${ESC}\\][^${BEL}]*${BEL}`, 'g');
/** Cursor returned to column 0: a bare CR, or a CSI G/K erase-and-home. */
const LINE_RESET_RE = new RegExp(`${CR}(?!\\n)|${ESC}\\[[0-9]*[GK]`);

/** Strip ANSI escape sequences and OSC sequences from text. */
export function stripAnsi(text) {
    return text.replaceAll(ANSI_CSI_RE, '').replaceAll(ANSI_OSC_RE, '');
}

/**
 * Every run of text the terminal drew as one line, split at the points where the
 * cursor went back to the start.
 *
 * Two wrong models were tried before this one. Measuring raw newline-split lines
 * concatenates every spinner frame into a 22,562-column pseudo-line
 * (tutorial-live-migration), so all 24 of its "violations" are phantom. Keeping
 * only the LAST segment -- what finally settles on screen -- is wrong in the
 * opposite direction: a 358-column logrus line WRAPS across four rows when it is
 * written, and a following spinner repaint only overwrites the last of them, so
 * the check silently discarded the exact lines it exists to catch.
 *
 * Each segment is measured on its own. A spinner frame is short and passes; a
 * line that wrapped when it was drawn is caught, whatever happened afterwards.
 */
export function drawnSegments(text) {
    const out = [];
    for (const physical of text.split('\n')) {
        for (const segment of physical.split(LINE_RESET_RE)) out.push(stripAnsi(segment));
    }
    return out;
}

/** Display width, counting a wide CJK glyph as the two cells it occupies. */
export function displayWidth(line) {
    let w = 0;
    for (const ch of line) {
        const c = ch.codePointAt(0);
        if (c === undefined) continue;
        // Combining marks take no cell; CJK/fullwidth take two.
        if (c >= 0x0300 && c <= 0x036f) continue;
        w +=
            (c >= 0x1100 && c <= 0x115f) ||
            (c >= 0x2e80 && c <= 0xa4cf) ||
            (c >= 0xac00 && c <= 0xd7a3) ||
            (c >= 0xf900 && c <= 0xfaff) ||
            (c >= 0xfe30 && c <= 0xfe6f) ||
            (c >= 0xff00 && c <= 0xff60) ||
            (c >= 0xffe0 && c <= 0xffe6)
                ? 2
                : 1;
    }
    return w;
}
