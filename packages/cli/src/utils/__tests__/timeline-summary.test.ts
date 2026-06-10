import { describe, expect, it } from 'vitest';
import {
  buildAttribution,
  buildTimingBars,
  buildTimingSummary,
  buildTimingWaterfall,
  PARALLEL_STEP_DETAIL,
  type TimelineStep,
  unattributedMs,
  workloadSplit,
} from '../timeline.js';

const T0 = 1_000_000;

function step(
  name: string,
  durationMs: number,
  startOffsetMs?: number,
  parallel = false
): TimelineStep {
  return {
    name,
    duration_ms: durationMs,
    ...(startOffsetMs === undefined ? {} : { startedAtMs: T0 + startOffsetMs }),
    ...(parallel ? { detail: PARALLEL_STEP_DETAIL } : {}),
  };
}

describe('unattributedMs', () => {
  it('subtracts the interval union, not the sum, for overlapping steps', () => {
    // Two fully-overlapping 10s steps cover 10s, not 20s.
    const steps = [step('compose_up', 10_000, 0), step('identity_refresh', 10_000, 0, true)];
    expect(unattributedMs(steps, 12_000)).toBe(2_000);
  });

  it('counts offset-less steps by duration and clamps at zero', () => {
    const steps = [step('config', 4_000), step('ssh_connect', 9_000)];
    expect(unattributedMs(steps, 10_000)).toBe(0);
  });
});

describe('buildTimingBars', () => {
  it('sorts by duration, shows percentages, and marks parallel steps', () => {
    const out = buildTimingBars(
      [step('luks_mount', 1_000, 0), step('compose_up', 8_000, 1_000), step('dns', 1_000, 0, true)],
      10_000
    );
    const lines = out.split('\n');
    expect(lines[0]).toContain('Services started');
    expect(lines[0]).toContain('80%');
    expect(out).toContain('∥');
  });

  it('folds sub-1% steps into an "other" row and reports unattributed time', () => {
    const tiny = Array.from({ length: 3 }, (_, i) => step(`tiny${i}`, 50, 9_000 + i * 50));
    const out = buildTimingBars([step('compose_up', 8_000, 0), ...tiny], 10_000);
    expect(out).toContain('other (3 steps)');
    expect(out).toContain('unattributed');
  });

  it('warns when the unattributed share exceeds 5%', () => {
    const out = buildTimingBars([step('compose_up', 5_000, 0)], 10_000);
    expect(out).toContain('unattributed');
    expect(out).toContain('⚠');
  });
});

describe('buildTimingWaterfall', () => {
  it('positions bars by start offset on a shared axis', () => {
    const out = buildTimingWaterfall(
      [step('cow_reflink', 2_000, 0), step('compose_up', 6_000, 4_000)],
      10_000,
      T0
    );
    expect(out).not.toBeNull();
    const lines = (out as string).split('\n');
    // Axis header + ruler + 2 step rows.
    expect(lines).toHaveLength(4);
    const cow = lines[2];
    const compose = lines[3];
    // compose_up starts ~40% across; its bar begins after cow_reflink's.
    expect(compose.indexOf('▓')).toBeGreaterThan(cow.indexOf('▓'));
  });

  it('uses a light glyph for parallel steps', () => {
    const out = buildTimingWaterfall(
      [step('compose_up', 6_000, 0), step('identity_refresh', 3_000, 500, true)],
      10_000,
      T0
    );
    expect(out).toContain('░');
  });

  it('returns null when fewer than two steps carry start offsets', () => {
    expect(
      buildTimingWaterfall([step('config', 100), step('cow_sync', 200, 0)], 10_000)
    ).toBeNull();
  });
});

describe('buildTimingSummary', () => {
  it('skips short runs entirely', () => {
    expect(buildTimingSummary([step('cow_sync', 900, 0)], 3_000)).toBeNull();
  });

  it('renders bars and waterfall together for long runs', () => {
    const out = buildTimingSummary(
      [step('cow_reflink', 4_000, 0), step('compose_up', 30_000, 5_000)],
      40_000,
      { epochMs: T0 }
    );
    expect(out).toContain('█');
    expect(out).toContain('▓');
  });
});

describe('buildAttribution', () => {
  it('returns null when no workload steps ran (plain fork)', () => {
    expect(buildAttribution([step('cow_reflink', 4_000, 0)], 10_000)).toBeNull();
  });

  it('splits platform vs service startup without a note when platform dominates', () => {
    const out = buildAttribution(
      [step('cow_reflink', 5_000, 0), step('compose_up', 3_000, 5_000)],
      10_000
    );
    expect(out).toContain('Rediacc pipeline 7.0s (70%)');
    expect(out).toContain('service startup 3.0s (30%)');
    expect(out).not.toContain('ℹ');
  });

  it('adds the neutral note when service startup exceeds half the wall time', () => {
    const out = buildAttribution(
      [step('cow_reflink', 2_000, 0), step('compose_up', 7_000, 2_000)],
      10_000
    );
    expect(out).toContain('service startup 7.0s (70%)');
    expect(out).toContain('ℹ Service startup is this repository');
    expect(out).toContain('completed in 3.0s');
  });

  it('counts service_ready as workload alongside compose_up', () => {
    const { workloadMs, platformMs } = workloadSplit(
      [step('compose_up', 4_000, 0), step('service_ready', 2_000, 4_000)],
      10_000
    );
    expect(workloadMs).toBe(6_000);
    expect(platformMs).toBe(4_000);
  });
});

describe('zero/negative wall guards', () => {
  it('builders degrade gracefully when wallMs is zero or negative', () => {
    const s = [step('compose_up', 1_000, 0)];
    expect(buildTimingBars(s, 0)).toBe('');
    expect(buildTimingWaterfall(s, -5, T0)).toBeNull();
    expect(buildTimingSummary(s, 0, { minWallMs: 0 })).toBeNull();
  });
});
