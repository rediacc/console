#!/usr/bin/env node
/**
 * process-cast-markers.mjs
 *
 * Reads a raw asciinema .cast file (NDJSON), detects OSC escape sequences
 * emitted by tutorial-helpers.sh, and injects proper asciinema v2 marker
 * events: [timestamp, "m", "command label"].
 *
 * The OSC pattern is: \x1b]rediacc-marker:<label>\x07
 *
 * Usage: node process-cast-markers.mjs --input raw.cast --output processed.cast
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { parseArgs } from 'node:util';

const MARKER_RE = /\x1b\]rediacc-marker:(.*?)\x07/g;

// Substitute the recordist's real $HOME with ~ so the cast doesn't reveal the
// maintainer's username. The fake prompt is "user@rediacc:~$", so the home
// directory should display as ~.
const HOME = process.env.HOME ?? '';
const HOME_RE = HOME ? new RegExp(HOME.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g') : null;

function normalizePaths(s) {
    return HOME_RE ? s.replace(HOME_RE, '~') : s;
}

function processCast(inputPath, outputPath) {
    const raw = readFileSync(inputPath, 'utf-8');
    const lines = raw.split('\n').filter(Boolean);

    if (lines.length === 0) {
        throw new Error('Empty cast file');
    }

    // Line 1 is the JSON header
    const header = JSON.parse(lines[0]);
    const events = lines.slice(1).map((line) => JSON.parse(line));

    const outputEvents = [];
    let markerCount = 0;
    let pathSubstitutions = 0;
    const commandLabels = [];

    for (const event of events) {
        const [timestamp, eventType, data] = event;

        if (eventType === 'o' && typeof data === 'string') {
            // Extract markers from output
            const markers = [];
            let match;
            MARKER_RE.lastIndex = 0;
            while ((match = MARKER_RE.exec(data)) !== null) {
                markers.push(match[1]);
            }

            // Inject marker events (label normalized for path display)
            for (const label of markers) {
                outputEvents.push([timestamp, 'm', normalizePaths(label)]);
                commandLabels.push(label);
                markerCount++;
            }

            // Strip OSC sequences from the output data + normalize home paths
            let cleaned = data.replace(MARKER_RE, '');
            const before = cleaned;
            cleaned = normalizePaths(cleaned);
            if (cleaned !== before) pathSubstitutions++;
            if (cleaned.length > 0) {
                outputEvents.push([timestamp, eventType, cleaned]);
            }
        } else {
            outputEvents.push(event);
        }
    }

    // Write processed file
    const outputLines = [
        JSON.stringify(header),
        ...outputEvents.map((e) => JSON.stringify(e)),
    ];
    writeFileSync(outputPath, outputLines.join('\n') + '\n');

    // Summary
    console.log(`Markers injected: ${markerCount}`);
    if (pathSubstitutions > 0) {
        console.log(`Path substitutions (${HOME} → ~): ${pathSubstitutions} events`);
    }
    if (commandLabels.length > 0) {
        console.log(`Commands: ${commandLabels.join(', ')}`);
    }
}

const { values } = parseArgs({
    options: {
        input: { type: 'string' },
        output: { type: 'string' },
    },
});

if (!values.input || !values.output) {
    console.error('Usage: process-cast-markers.mjs --input <raw.cast> --output <processed.cast>');
    process.exit(1);
}

processCast(values.input, values.output);
