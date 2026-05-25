#!/usr/bin/env node
/**
 * compress-cast-idle.mjs
 *
 * Reads an asciinema v2 .cast file and caps every inter-event idle gap to a
 * maximum (default 800ms). All subsequent timestamps shift by the same delta,
 * preserving within-burst rhythm but eliminating dead air.
 *
 * Usage: node compress-cast-idle.mjs --input in.cast --output out.cast [--max-idle-ms 800]
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { parseArgs } from 'node:util';

function compress(inputPath, outputPath, maxIdleMs) {
    const maxIdleSec = maxIdleMs / 1000;
    const lines = readFileSync(inputPath, 'utf-8').split('\n').filter(Boolean);
    if (lines.length === 0) throw new Error('Empty cast file');

    const header = JSON.parse(lines[0]);
    const events = lines.slice(1).map((l) => JSON.parse(l));

    let shift = 0;
    let prevOriginalTs = 0;
    let trimmed = 0;
    const out = events.map((e) => {
        const [ts, kind, data] = e;
        const gap = ts - prevOriginalTs;
        if (gap > maxIdleSec) {
            const delta = gap - maxIdleSec;
            shift += delta;
            trimmed += delta;
        }
        prevOriginalTs = ts;
        return [Number((ts - shift).toFixed(6)), kind, data];
    });

    if (typeof header.duration === 'number') {
        header.duration = Number((header.duration - shift).toFixed(6));
    }

    writeFileSync(
        outputPath,
        [JSON.stringify(header), ...out.map((e) => JSON.stringify(e))].join('\n') + '\n',
    );
    console.log(`Compressed cast: trimmed ${trimmed.toFixed(2)}s of idle time (cap=${maxIdleMs}ms)`);
}

const { values } = parseArgs({
    options: {
        input: { type: 'string' },
        output: { type: 'string' },
        'max-idle-ms': { type: 'string', default: '800' },
    },
});

if (!values.input || !values.output) {
    console.error('Usage: compress-cast-idle.mjs --input <in> --output <out> [--max-idle-ms 800]');
    process.exit(1);
}

compress(values.input, values.output, Number(values['max-idle-ms']));
