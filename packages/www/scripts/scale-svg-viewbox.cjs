#!/usr/bin/env node

/**
 * Scale SVG illustrations from mixed viewBox sizes to unified 800x450.
 *
 * Usage: node packages/www/scripts/scale-svg-viewbox.js
 */

const { DOMParser, XMLSerializer } = require("@xmldom/xmldom");
const fs = require("fs");
const path = require("path");

const ILLUSTRATIONS_DIR = path.join(
	__dirname,
	"../src/assets/images/illustrations",
);
const TARGET_W = 800;
const TARGET_H = 450;

const FILES = {
	// 1200x675 → 800x450 (scale = 2/3)
	"preemptive-defense-hero.svg": [1200, 675],
	"preemptive-defense-bottom.svg": [1200, 675],
	"data-security-hero.svg": [1200, 675],
	"disaster-recovery-hero.svg": [1200, 675],
	"development-environments-hero.svg": [1200, 675],
	"system-portability-hero.svg": [1200, 675],
	"threat-response-hero.svg": [1200, 675],
	// 1100x618 → 800x450 (scale = 8/11)
	"data-security-bottom.svg": [1100, 618],
	"disaster-recovery-bottom.svg": [1100, 618],
	"development-environments-bottom.svg": [1100, 618],
	"system-portability-bottom.svg": [1100, 618],
	"threat-response-bottom.svg": [1100, 618],
};

// ─── Utilities ───────────────────────────────────────────────

function round1(n) {
	const r = Math.round(n * 10) / 10;
	return r;
}

function fmt(n) {
	const r = round1(n);
	return r === Math.floor(r) ? String(Math.floor(r)) : String(r);
}

// ─── Scale individual attribute values ───────────────────────

function scaleAttrVal(val, scale) {
	if (val.endsWith("%")) return val;
	const n = parseFloat(val);
	if (isNaN(n)) return val;
	return fmt(n * scale);
}

// Scale comma/space-separated number lists (dasharray, points)
function scaleNumList(str, scale) {
	return str.replace(/-?\d*\.?\d+/g, (m) => {
		const n = parseFloat(m);
		return isNaN(n) ? m : fmt(n * scale);
	});
}

// ─── Scale SVG path data ─────────────────────────────────────

function scalePath(d, scale) {
	if (!d || !d.trim()) return d;

	// Tokenize path data into commands and numbers
	const tokens = [];
	let i = 0;
	const s = d;

	while (i < s.length) {
		// Skip whitespace and commas
		const ch = s[i];
		if (ch === " " || ch === "," || ch === "\t" || ch === "\n" || ch === "\r") {
			i++;
			continue;
		}

		// Command letter
		if (/[A-Za-z]/.test(ch)) {
			tokens.push({ t: "c", v: ch });
			i++;
			continue;
		}

		// Number (may start with -, +, or .)
		let num = "";
		if (ch === "-" || ch === "+") {
			num += ch;
			i++;
		}
		while (i < s.length && ((s[i] >= "0" && s[i] <= "9") || s[i] === ".")) {
			num += s[i];
			i++;
		}
		// Scientific notation
		if (i < s.length && (s[i] === "e" || s[i] === "E")) {
			num += s[i];
			i++;
			if (i < s.length && (s[i] === "+" || s[i] === "-")) {
				num += s[i];
				i++;
			}
			while (i < s.length && s[i] >= "0" && s[i] <= "9") {
				num += s[i];
				i++;
			}
		}
		if (num && num !== "-" && num !== "+" && num !== ".") {
			tokens.push({ t: "n", v: parseFloat(num) });
		}
	}

	// Apply scaling based on command context
	let cmd = "";
	let pi = 0; // parameter index within current command repetition
	const parts = [];

	for (const tok of tokens) {
		if (tok.t === "c") {
			cmd = tok.v;
			pi = 0;
			parts.push({ t: "c", s: tok.v });
		} else {
			const uc = cmd.toUpperCase();
			let val;

			if (uc === "Z") {
				val = tok.v;
			} else if (uc === "A") {
				// Arc: rx ry rotation large-arc-flag sweep-flag x y (7 params)
				const pos = pi % 7;
				if (pos >= 2 && pos <= 4) {
					// rotation, large-arc-flag, sweep-flag — don't scale
					val = tok.v;
				} else {
					val = round1(tok.v * scale);
				}
				pi++;
			} else {
				// All other commands: scale all numeric params
				val = round1(tok.v * scale);
				pi++;
			}

			parts.push({ t: "n", s: fmt(val) });
		}
	}

	// Reconstruct path string
	let result = "";
	for (let j = 0; j < parts.length; j++) {
		const p = parts[j];
		if (j === 0) {
			result = p.s;
			continue;
		}

		if (p.t === "c") {
			// Command letter
			result += " " + p.s;
		} else {
			const prev = parts[j - 1];
			if (prev.t === "c") {
				// First number after command — no space
				result += p.s;
			} else {
				// Number after number — use negative sign as separator or space
				result += p.s.startsWith("-") ? p.s : " " + p.s;
			}
		}
	}

	return result;
}

// ─── Scale transform attribute ───────────────────────────────

function scaleTransform(val, scale) {
	return val
		.replace(/translate\(\s*([^)]+)\)/g, (_, args) => {
			const parts = args
				.split(/[\s,]+/)
				.filter(Boolean)
				.map((v) => scaleAttrVal(v.trim(), scale));
			return `translate(${parts.join(", ")})`;
		})
		.replace(/rotate\(\s*([^)]+)\)/g, (_, args) => {
			const parts = args.split(/[\s,]+/).filter(Boolean);
			if (parts.length === 1) return `rotate(${parts[0]})`;
			if (parts.length === 3) {
				// rotate(angle, cx, cy) — scale cx and cy only
				return `rotate(${parts[0]}, ${scaleAttrVal(parts[1], scale)}, ${scaleAttrVal(parts[2], scale)})`;
			}
			return `rotate(${args})`;
		})
		.replace(/matrix\(\s*([^)]+)\)/g, (_, args) => {
			const parts = args.split(/[\s,]+/).filter(Boolean);
			if (parts.length === 6) {
				// matrix(a b c d e f) — only scale e and f (translation)
				parts[4] = scaleAttrVal(parts[4], scale);
				parts[5] = scaleAttrVal(parts[5], scale);
				return `matrix(${parts.join(", ")})`;
			}
			return `matrix(${args})`;
		});
	// scale() and skew*() are left unchanged
}

// ─── Scale CSS in <style> blocks ─────────────────────────────

function scaleCss(css, scale) {
	return css
		.replace(
			/font-size:\s*([\d.]+)px/g,
			(_, v) => `font-size: ${fmt(parseFloat(v) * scale)}px`,
		)
		.replace(
			/stroke-width:\s*([\d.]+)/g,
			(_, v) => `stroke-width: ${fmt(parseFloat(v) * scale)}`,
		);
}

// ─── Scale inline style attribute ────────────────────────────

function scaleStyle(style, scale) {
	return style
		.replace(
			/font-size:\s*([\d.]+)(px)?/g,
			(_, v, u) => `font-size: ${fmt(parseFloat(v) * scale)}${u || ""}`,
		)
		.replace(
			/stroke-width:\s*([\d.]+)/g,
			(_, v) => `stroke-width: ${fmt(parseFloat(v) * scale)}`,
		)
		.replace(
			/stroke-dasharray:\s*([^;]+)/g,
			(_, v) => `stroke-dasharray: ${scaleNumList(v.trim(), scale)}`,
		);
}

// ─── Attribute scaling logic ─────────────────────────────────

const COORD_ATTRS = new Set([
	"x",
	"y",
	"width",
	"height",
	"cx",
	"cy",
	"r",
	"rx",
	"ry",
	"x1",
	"y1",
	"x2",
	"y2",
	"font-size",
	"stroke-width",
	"dx",
	"dy",
	"stdDeviation",
	"markerWidth",
	"markerHeight",
	"refX",
	"refY",
]);

function shouldScaleAttr(el, attr) {
	// Filter region uses objectBoundingBox by default — don't scale
	if (
		el.tagName === "filter" &&
		(attr === "x" || attr === "y" || attr === "width" || attr === "height")
	) {
		return false;
	}

	// Gradient coords in objectBoundingBox (default) — don't scale
	if (
		(el.tagName === "linearGradient" || el.tagName === "radialGradient") &&
		el.getAttribute("gradientUnits") !== "userSpaceOnUse"
	) {
		if (
			["x1", "y1", "x2", "y2", "cx", "cy", "r", "fx", "fy"].includes(attr)
		) {
			return false;
		}
	}

	return true;
}

// ─── Walk and scale DOM ──────────────────────────────────────

function walkNode(node, scale, inSymbol, rootEl) {
	// Text/CDATA nodes inside <style> — scale CSS values
	if (
		(node.nodeType === 3 || node.nodeType === 4) &&
		node.parentNode &&
		node.parentNode.tagName === "style"
	) {
		if (!inSymbol) {
			node.nodeValue = scaleCss(node.nodeValue, scale);
		}
		return;
	}

	if (node.nodeType !== 1) return; // Only process element nodes

	const tag = node.tagName;
	const enteringSymbol = tag === "symbol";

	if (!inSymbol && !enteringSymbol) {
		const attrs = node.attributes;
		if (attrs) {
			for (let i = 0; i < attrs.length; i++) {
				const a = attrs[i];
				const name = a.name;
				const val = a.value;

				// Root SVG: override viewBox, width, height
				if (node === rootEl) {
					if (name === "viewBox") {
						a.value = `0 0 ${TARGET_W} ${TARGET_H}`;
						continue;
					}
					if (name === "width") {
						a.value = String(TARGET_W);
						continue;
					}
					if (name === "height") {
						a.value = String(TARGET_H);
						continue;
					}
				}

				// Skip non-root viewBox attributes
				if (name === "viewBox") continue;

				// Coordinate attributes
				if (COORD_ATTRS.has(name)) {
					if (val.endsWith("%")) continue;
					if (!shouldScaleAttr(node, name)) continue;
					a.value = scaleAttrVal(val, scale);
					continue;
				}

				// Stroke dash arrays
				if (name === "stroke-dasharray") {
					a.value = scaleNumList(val, scale);
					continue;
				}

				// Stroke dash offset
				if (name === "stroke-dashoffset") {
					a.value = scaleAttrVal(val, scale);
					continue;
				}

				// Path data
				if (name === "d") {
					a.value = scalePath(val, scale);
					continue;
				}

				// Polygon/polyline points
				if (name === "points") {
					a.value = scaleNumList(val, scale);
					continue;
				}

				// Transform
				if (name === "transform") {
					a.value = scaleTransform(val, scale);
					continue;
				}

				// Inline style
				if (name === "style") {
					a.value = scaleStyle(val, scale);
					continue;
				}
			}
		}
	}

	// Recurse children (skip symbol children from scaling)
	const childInSymbol = inSymbol || enteringSymbol;
	for (let i = 0; i < node.childNodes.length; i++) {
		walkNode(node.childNodes[i], scale, childInSymbol, rootEl);
	}
}

// ─── Main ────────────────────────────────────────────────────

function processFile(filename, fromDims) {
	const filepath = path.join(ILLUSTRATIONS_DIR, filename);
	const content = fs.readFileSync(filepath, "utf-8");
	const scale = TARGET_W / fromDims[0];

	console.log(
		`Processing ${filename}: ${fromDims[0]}x${fromDims[1]} → ${TARGET_W}x${TARGET_H} (scale: ${scale.toFixed(4)})`,
	);

	const parser = new DOMParser({
		errorHandler: {
			warning: () => {},
			error: (msg) => console.error(`  XML error: ${msg}`),
			fatalError: (msg) => {
				throw new Error(`XML fatal: ${msg}`);
			},
		},
	});

	const doc = parser.parseFromString(content, "image/svg+xml");
	const root = doc.documentElement;

	walkNode(root, scale, false, root);

	const serializer = new XMLSerializer();
	let output = serializer.serializeToString(doc);

	// Ensure trailing newline
	if (!output.endsWith("\n")) output += "\n";

	fs.writeFileSync(filepath, output);
	console.log(`  → Written`);
}

// Process all files
console.log(
	`Scaling ${Object.keys(FILES).length} SVG files to ${TARGET_W}x${TARGET_H}\n`,
);

for (const [filename, fromDims] of Object.entries(FILES)) {
	try {
		processFile(filename, fromDims);
	} catch (err) {
		console.error(`  ERROR processing ${filename}: ${err.message}`);
	}
}

console.log("\nDone!");
