#!/usr/bin/env tsx
/**
 * `npm run ci`, as a parallel worker pool over the gate manifest.
 *
 * WHAT THIS REPLACED AND WHY. package.json `scripts.ci` was a 93-step `&&`
 * string, measured at 1041.6 s serial on a 20-core box. Two properties of that
 * shape were costing real time and real signal:
 *
 *   - `&&` is fail-fast, so one red hid every other red. check:i18n alone
 *     chains 19 leaf gates that way. CI fixed the same defect at lane level by
 *     putting `!cancelled()` on every quality step; the runner defaults to
 *     keep-going for the same reason, and --fail-fast is the opt-in.
 *   - check:ci-quality-gates was 443 s of that total, 43%, as one opaque unit
 *     wrapping run-all.sh. Scheduling it whole caps the speedup at 2.4x no
 *     matter how many cores exist, which is why its 57 tests are individually
 *     scheduled manifest entries.
 *
 * Usage:
 *   tsx scripts/ci-runner/run.ts [--jobs N] [--heavy-limit N] [--fail-fast]
 *                                [--only <glob,...>] [--skip <glob,...>]
 *                                [--changed] [--json] [--list]
 *                                [--merge-output] [--verbose] [--selftest]
 *
 * See agent/0731-2/PLAN-npm-ci-parallel-parity.md section 4.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { GATES, type GateSpec } from './manifest';
import { execGate } from './exec';
import { buildGraph, runPool, type GateResult } from './pool';
import { createReporter } from './report';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const DEFAULT_CACHE = path.join(REPO_ROOT, '.ci', 'cache', 'gate-durations.json');
const EWMA_ALPHA = 0.3;

interface Options {
    jobs?: number;
    heavyLimit?: number;
    failFast: boolean;
    json: boolean;
    list: boolean;
    changed: boolean;
    mergeOutput: boolean;
    selftest: boolean;
    verbose: boolean;
    only?: string[];
    skip?: string[];
    manifest?: string;
}

function parseArgs(argv: readonly string[]): Options {
    const opts: Options = {
        failFast: false,
        json: false,
        list: false,
        changed: false,
        mergeOutput: false,
        selftest: false,
        verbose: false,
        manifest: process.env.CI_RUNNER_MANIFEST,
    };
    const value = (i: number, flag: string): string => {
        const v = argv[i + 1];
        if (v === undefined) throw new Error(`ci-runner: ${flag} needs a value`);
        return v;
    };
    const number = (raw: string, flag: string): number => {
        const n = Number(raw);
        if (!Number.isInteger(n) || n < 1) throw new Error(`ci-runner: ${flag} needs a positive integer, got '${raw}'`);
        return n;
    };

    for (let i = 0; i < argv.length; i += 1) {
        const arg = argv[i];
        switch (arg) {
            case '--jobs':
                opts.jobs = number(value(i, arg), arg);
                i += 1;
                break;
            case '--heavy-limit':
                opts.heavyLimit = number(value(i, arg), arg);
                i += 1;
                break;
            case '--only':
                opts.only = value(i, arg).split(',').filter(Boolean);
                i += 1;
                break;
            case '--skip':
                opts.skip = value(i, arg).split(',').filter(Boolean);
                i += 1;
                break;
            case '--manifest':
                opts.manifest = value(i, arg);
                i += 1;
                break;
            case '--fail-fast':
                opts.failFast = true;
                break;
            case '--json':
                opts.json = true;
                break;
            case '--list':
                opts.list = true;
                break;
            case '--changed':
                opts.changed = true;
                break;
            case '--merge-output':
                opts.mergeOutput = true;
                break;
            case '--selftest':
                opts.selftest = true;
                break;
            case '--verbose':
                opts.verbose = true;
                break;
            default:
                throw new Error(`ci-runner: unknown flag '${arg}'`);
        }
    }
    if (opts.jobs === undefined && process.env.CI_JOBS !== undefined) {
        opts.jobs = number(process.env.CI_JOBS, 'CI_JOBS');
    }
    return opts;
}

async function loadManifest(source: string | undefined): Promise<readonly GateSpec[]> {
    if (source === undefined) return GATES;
    const abs = path.resolve(REPO_ROOT, source);
    if (abs.endsWith('.json')) {
        const parsed: unknown = JSON.parse(fs.readFileSync(abs, 'utf-8'));
        if (!Array.isArray(parsed)) throw new Error(`ci-runner: ${source} must contain an array of gate specs`);
        return parsed as GateSpec[];
    }
    const mod: unknown = await import(abs);
    const gates = (mod as { GATES?: unknown }).GATES;
    if (!Array.isArray(gates)) throw new Error(`ci-runner: ${source} does not export GATES`);
    return gates as GateSpec[];
}

/**
 * `*`, `**` and `?`; enough for gate ids and repo-relative path globs.
 * One pass, because a two-pass version needs a placeholder byte that cannot
 * occur in the input, and any such byte is invisible in the source.
 */
function globToRegExp(glob: string): RegExp {
    const body = glob.replace(/\*\*|[*?.+^${}()|[\]\\]/g, (token) => {
        if (token === '**') return '.*';
        if (token === '*') return '[^/]*';
        if (token === '?') return '.';
        return `\\${token}`;
    });
    return new RegExp(`^${body}$`);
}

function matchesAny(text: string, globs: readonly string[]): boolean {
    return globs.some((g) => globToRegExp(g).test(text));
}

function changedFiles(warn: (text: string) => void): string[] {
    const base = process.env.CI_RUNNER_BASE ?? 'origin/main';
    try {
        const mergeBase = execFileSync('git', ['merge-base', 'HEAD', base], {
            cwd: REPO_ROOT,
            encoding: 'utf-8',
        }).trim();
        return execFileSync('git', ['diff', '--name-only', mergeBase], { cwd: REPO_ROOT, encoding: 'utf-8' })
            .split('\n')
            .filter(Boolean);
    } catch {
        warn(`ci-runner: --changed could not resolve a merge base against ${base}; selecting every gate\n`);
        return [];
    }
}

interface Selection {
    ids: Set<string>;
    /** Human description when the run is partial; undefined for a full run. */
    description?: string;
}

function select(specs: readonly GateSpec[], opts: Options, warn: (text: string) => void): Selection {
    const notes: string[] = [];
    // gate:false nodes are prerequisites, never selected on their own. They
    // enter the run only through the needs-closure in buildGraph.
    let chosen = specs.filter((spec) => spec.gate);

    if (opts.changed) {
        const files = changedFiles(warn);
        // An entry with no declared `paths` is ALWAYS selected. A half-populated
        // path table would make --changed drop gates silently, which is the
        // vacuity failure this design exists to prevent.
        chosen = chosen.filter((spec) => spec.paths === undefined || files.some((f) => matchesAny(f, spec.paths ?? [])));
        notes.push(`--changed (${files.length} files vs ${process.env.CI_RUNNER_BASE ?? 'origin/main'})`);
    }
    if (opts.only !== undefined) {
        chosen = chosen.filter((spec) => matchesAny(spec.id, opts.only ?? []));
        notes.push(`--only ${opts.only.join(',')}`);
    }
    if (opts.skip !== undefined) {
        chosen = chosen.filter((spec) => !matchesAny(spec.id, opts.skip ?? []));
        notes.push(`--skip ${opts.skip.join(',')}`);
    }

    return {
        ids: new Set(chosen.map((spec) => spec.id)),
        description: notes.length > 0 ? notes.join(' ') : undefined,
    };
}

function loadDurations(cachePath: string | undefined): Map<string, number> {
    const durations = new Map<string, number>();
    if (cachePath === undefined) return durations;
    try {
        const parsed: unknown = JSON.parse(fs.readFileSync(cachePath, 'utf-8'));
        if (parsed === null || typeof parsed !== 'object') return durations;
        for (const [id, ms] of Object.entries(parsed as Record<string, unknown>)) {
            if (typeof ms === 'number' && Number.isFinite(ms) && ms > 0) durations.set(id, ms);
        }
    } catch {
        // A missing or corrupt cache is a scheduling hint at worst. It must
        // never fail the run.
    }
    return durations;
}

function saveDurations(cachePath: string | undefined, prior: Map<string, number>, results: readonly GateResult[]): void {
    if (cachePath === undefined) return;
    try {
        const next: Record<string, number> = Object.fromEntries(prior);
        for (const r of results) {
            if (r.status === 'skipped' || r.ms <= 0) continue;
            const old = prior.get(r.id);
            next[r.id] = old === undefined ? r.ms : Math.round(old * (1 - EWMA_ALPHA) + r.ms * EWMA_ALPHA);
        }
        fs.mkdirSync(path.dirname(cachePath), { recursive: true });
        fs.writeFileSync(cachePath, `${JSON.stringify(next, null, 2)}\n`);
    } catch {
        // Same reasoning as loadDurations: a cache write is never load-bearing.
    }
}

const SELFTEST_OUT = 'ci-runner-selftest-stdout-marker';
const SELFTEST_ERR = 'ci-runner-selftest-stderr-marker';

function syntheticSpec(id: string, run: string, needs?: string[]): GateSpec {
    return {
        id,
        run,
        gate: true,
        needs,
        leaves: [],
        ci: { kind: 'local-only', blocker: 'BLOCKER: synthetic --selftest fixture, never part of the real gate set' },
    };
}

/**
 * The runner's anti-vacuity control, wired into the `ci` npm key itself so it
 * cannot sit behind a flag nothing invokes -- the exact failure
 * check-gate-reachability recorded for check-i18n-cross-locale, which shipped
 * broken behind a flag no caller passed.
 *
 * A planted failing gate must produce: exit 1, BOTH captured streams printed
 * verbatim, the gate named in the summary, and its dependent reported skipped
 * rather than passed. If any leg does not fire, the runner's green means
 * nothing, so this refuses to proceed.
 */
async function selftest(): Promise<number> {
    const specs = [
        syntheticSpec('selftest:pass', 'echo selftest-pass'),
        syntheticSpec('selftest:fail', `echo ${SELFTEST_OUT}; echo ${SELFTEST_ERR} >&2; exit 3`),
        syntheticSpec('selftest:dependent', 'echo selftest-dependent-ran', ['selftest:fail']),
    ];

    const captured: string[] = [];
    const reporter = createReporter({ idWidth: 20, out: (text) => captured.push(text) });
    const meta = { jobs: 2, failFast: false, wallMs: 0 };
    reporter.header(specs.length, meta);
    const results = await runPool(buildGraph(specs, new Set(specs.map((s) => s.id))), {
        jobs: 2,
        heavyLimit: 1,
        failFast: false,
        durations: new Map(),
        exec: (spec) => execGate(spec, { cwd: REPO_ROOT, mergeOutput: false }),
        onFinish: (result) => {
            reporter.finish(result);
        },
    });
    const exitCode = reporter.footer(results, meta);
    const text = captured.join('');

    const failures: string[] = [];
    const require_ = (cond: boolean, message: string): void => {
        if (!cond) failures.push(message);
    };
    require_(exitCode === 1, `a failing gate must make the run exit 1, got ${exitCode}`);
    require_(text.includes(SELFTEST_OUT), "the failing gate's captured stdout was not printed");
    require_(text.includes(SELFTEST_ERR), "the failing gate's captured stderr was not printed");
    require_(/FAIL {2}selftest:fail/.test(text), 'the failing gate was not named as FAIL');
    require_(text.includes('exit 3'), "the failing gate's exit code was not reported");
    require_(
        results.find((r) => r.id === 'selftest:dependent')?.status === 'skipped',
        'a dependent of a failed gate must be skipped, not passed',
    );
    require_(!text.includes('selftest-dependent-ran'), 'a dependent of a failed gate must not execute');
    require_(results.find((r) => r.id === 'selftest:pass')?.status === 'ok', 'the passing control gate did not pass');
    require_(!text.includes('selftest-pass'), "a passing gate's output must stay quiet");

    if (failures.length > 0) {
        process.stderr.write('CONTROL FAILED: ci-runner --selftest did not fire\n');
        for (const f of failures) process.stderr.write(`  - ${f}\n`);
        process.stderr.write('--- selftest transcript ---\n');
        process.stderr.write(text);
        return 1;
    }
    process.stdout.write('ci-runner: selftest ok (9 assertions)\n');
    return 0;
}

async function main(): Promise<number> {
    const opts = parseArgs(process.argv.slice(2));
    if (opts.selftest) return selftest();

    const specs = await loadManifest(opts.manifest);
    if (specs.length === 0) {
        process.stderr.write('ci-runner: Refusing to run: the manifest declares zero gates.\n');
        return 1;
    }

    if (opts.list) {
        for (const spec of specs) {
            process.stdout.write(`${spec.gate ? 'gate ' : 'prereq'} ${spec.id.padEnd(48)} ${spec.run}\n`);
        }
        return 0;
    }

    const humanOut = opts.json
        ? (text: string) => process.stderr.write(text)
        : (text: string) => process.stdout.write(text);
    const selection = select(specs, opts, humanOut);
    const graph = buildGraph(specs, selection.ids);
    if (graph.length === 0) {
        process.stderr.write('ci-runner: Refusing to run: the selection matched zero gates.\n');
        return 1;
    }

    const jobs = opts.jobs ?? Math.max(1, os.availableParallelism() - 2);
    const heavyLimit = opts.heavyLimit ?? Math.max(2, Math.floor(jobs / 4));
    // A synthetic manifest must not pollute (or be scheduled by) the real
    // duration cache, so caching is off unless the caller names a path.
    const cachePath =
        process.env.CI_RUNNER_CACHE ?? (opts.manifest === undefined ? DEFAULT_CACHE : undefined);
    const durations = loadDurations(cachePath);

    const reporter = createReporter({
        idWidth: Math.min(46, Math.max(...graph.map((spec) => spec.id.length))),
        out: humanOut,
        jsonOut: opts.json ? (text: string) => process.stdout.write(text) : undefined,
    });

    const started = Date.now();
    const meta = { jobs, failFast: opts.failFast, selection: selection.description, wallMs: 0 };
    reporter.header(graph.length, meta);
    const results = await runPool(graph, {
        jobs,
        heavyLimit,
        failFast: opts.failFast,
        durations,
        exec: (spec) => execGate(spec, { cwd: REPO_ROOT, mergeOutput: opts.mergeOutput }),
        onStart: opts.verbose
            ? (spec) => {
                  reporter.start(spec.id);
              }
            : undefined,
        onFinish: (result) => {
            reporter.finish(result);
        },
    });
    meta.wallMs = Date.now() - started;

    saveDurations(cachePath, durations, results);
    return reporter.footer(results, meta);
}

main()
    .then((code) => {
        process.exitCode = code;
    })
    .catch((error: unknown) => {
        process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
        process.exitCode = 1;
    });
