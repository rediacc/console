/**
 * The cost and cell-size arithmetic behind `--rpo` and `backup churn` (D-cost, D-cells).
 *
 * The table in D-cost is the oracle: a cost estimate printed before a customer enables a 5-minute
 * target is a number they decide on, so the rows are pinned as known answers. Class B, the window,
 * waiting and storage columns reproduce the table exactly. Class A differs by under 4% in the
 * plan's table because it adds a flat 0.1 index put per run, where the plan's own formula (and the
 * code) charge one index put per hour, `1 / runsPerHour`; the table is low by 0.4 per run at 30 minutes, so the assertions below carry a 4% bound on Class A.
 */

import { describe, expect, it } from 'vitest';
import {
  type ChurnProbeRecord,
  estimateRpoCost,
  recommendCellSize,
  summarizeChurn,
} from '../rpo-cost.js';

const MIB = 1024 * 1024;
const GIB = 1024 ** 3;

/** One row of the D-cost table: C = 4 MiB, W = 1 day, G = 7 days, s = 16. */
const row = (minutes: number, changedCells: number) =>
  estimateRpoCost({
    changedCells,
    cellBytes: 4 * MIB,
    targetSeconds: minutes * 60,
    windowDays: 1,
  });

const close = (actual: number, expected: number, relative: number) =>
  expect(Math.abs(actual - expected) / expected).toBeLessThanOrEqual(relative);

describe('estimateRpoCost reproduces the D-cost table', () => {
  // [target minutes, N, runs a day, Class B, window GiB, waiting GiB, Class A (table), total $ (table)]
  const table = [
    [5, 10, 288, 259_200, 11.25, 78.75, 95_904, 1.87],
    [5, 30, 288, 432_000, 33.75, 236.25, 268_704, 5.42],
    [15, 10, 96, 86_400, 3.75, 26.25, 31_968, 0.62],
    [15, 30, 96, 144_000, 11.25, 78.75, 89_568, 1.8],
    [30, 10, 48, 43_200, 1.875, 13.125, 15_984, 0.32],
    [30, 30, 48, 72_000, 5.625, 39.375, 44_784, 0.9],
  ] as const;

  it.each(table)(
    '%d min, N=%d: %d runs a day',
    (minutes, cells, runs, classB, windowGiB, waitingGiB, classA, total) => {
      const e = row(minutes, cells);
      expect(e.runsPerDay).toBe(runs);
      // Exact columns.
      expect(e.monthlyClassB).toBe(classB);
      expect(e.windowGiB).toBeCloseTo(windowGiB, 6);
      expect(e.waitingGiB).toBeCloseTo(waitingGiB, 6);
      expect(e.storageUsd).toBeCloseTo((windowGiB + waitingGiB) * 0.015, 6);
      // Class A: within 4% of the table (the index term), and the dollars within two cents of its total.
      close(e.monthlyClassA, classA, 0.04);
      expect(Math.abs(e.totalUsd - total)).toBeLessThanOrEqual(0.02);
    }
  );

  it('prices a run as N + 1 manifest + the hourly index put on Class A, N + 16 + 4 on Class B', () => {
    const e = row(5, 10);
    // 12 runs an hour: one index put in twelve.
    expect(e.classAPerRun).toBeCloseTo(10 + 1 + 1 / 12, 9);
    expect(e.classBPerRun).toBe(10 + 16 + 4);
  });

  it('charges the index put on every run when runs are less frequent than hourly', () => {
    const e = estimateRpoCost({
      changedCells: 10,
      cellBytes: 4 * MIB,
      targetSeconds: 2 * 3600,
      windowDays: 1,
    });
    expect(e.classAPerRun).toBe(10 + 1 + 1);
  });

  it('prices the 5-minute N=10 case in dollars: 0.43 + 0.09 + 0.17 + 1.18 = 1.87', () => {
    const e = row(5, 10);
    expect(e.monthlyClassAUsd).toBeCloseTo(0.43, 2);
    expect(e.monthlyClassBUsd).toBeCloseTo(0.09, 2);
    expect(e.windowUsd).toBeCloseTo(0.17, 2);
    expect(e.waitingUsd).toBeCloseTo(1.18, 2);
    expect(e.totalUsd).toBeCloseTo(1.87, 2);
  });
});

describe('the churn cap verdict (D-safeguard)', () => {
  it('COMMUNITY (10 GiB quota, 20 GiB cap) at 5 minutes and N=10 reaches the cap in under two days', () => {
    const e = estimateRpoCost({
      changedCells: 10,
      cellBytes: 4 * MIB,
      targetSeconds: 300,
      windowDays: 1,
      quotaBytes: 10 * GIB,
    });
    expect(e.cap?.capGiB).toBe(20);
    expect(e.cap?.sustainable).toBe(false);
    // 11.25 GiB of waiting a day against a 20 GiB cap.
    expect(e.cap?.daysToCap).toBeCloseTo(20 / 11.25, 6);
    expect(e.cap?.daysToCap).toBeLessThan(2);
  });

  it('PROFESSIONAL (200 GiB cap) holds N=10 at 5 minutes and not N=30', () => {
    const at = (changedCells: number) =>
      estimateRpoCost({
        changedCells,
        cellBytes: 4 * MIB,
        targetSeconds: 300,
        windowDays: 1,
        quotaBytes: 100 * GIB,
      }).cap;
    expect(at(10)?.sustainable).toBe(true);
    expect(at(30)?.sustainable).toBe(false);
  });

  it('carries no verdict without a quota', () => {
    expect(row(5, 10).cap).toBeUndefined();
  });
});

describe('summarizeChurn: a baseline is not zero churn', () => {
  const rec = (over: Partial<ChurnProbeRecord>): ChurnProbeRecord => ({
    guid: 'g',
    status: 'measured',
    probedAt: '2026-11-02T10:00:00Z',
    intervalSeconds: 300,
    imageBytes: 8 * GIB,
    changedBytes: 0,
    changedExtents: 0,
    ...over,
  });
  const cells = (one: number, four: number, eight: number) => ({
    projectedUploadBytes: {
      '1MiB': one * MIB,
      '2MiB': one * 2 * MIB,
      '4MiB': four * 4 * MIB,
      '8MiB': eight * 8 * MIB,
    },
    projectedCells: { '1MiB': one, '2MiB': one, '4MiB': four, '8MiB': eight },
  });

  it('counts only measured records as samples', () => {
    const s = summarizeChurn([
      rec({ status: 'baseline' }),
      rec({ status: 'skipped', reason: 'cold backup running for this repo' }),
      rec({ status: 'failed', reason: 'boom' }),
      rec({ ...cells(40, 10, 5) }),
    ]);
    expect(s.samples).toBe(1);
    expect(s.skipped).toBe(1);
    expect(s.failed).toBe(1);
    expect(s.baselines).toBe(1);
  });

  it('answers "no measurement" for a baseline alone, never zero churn', () => {
    const s = summarizeChurn([rec({ status: 'baseline', changedBytes: 0 })]);
    expect(s.samples).toBe(0);
    expect(s.changedCellsPerRun).toBeUndefined();
    expect(s.recommendation).toBeUndefined();
  });

  it('answers "no measurement" for nothing at all', () => {
    expect(summarizeChurn([]).samples).toBe(0);
  });

  it('averages the measured samples and keeps the largest', () => {
    const s = summarizeChurn([rec({ ...cells(40, 10, 5) }), rec({ ...cells(80, 30, 15) })]);
    expect(s.changedCellsPerRun?.['4MiB']).toBe(20);
    expect(s.maxChangedCellsPerRun?.['4MiB']).toBe(30);
  });

  it('a truly idle repository IS zero churn once a measured sample says so', () => {
    const s = summarizeChurn([
      rec({
        ...cells(0, 0, 0),
        projectedUploadBytes: { '1MiB': 0, '4MiB': 0 },
        projectedCells: { '4MiB': 0 },
      }),
    ]);
    expect(s.samples).toBe(1);
    expect(s.changedCellsPerRun?.['4MiB']).toBe(0);
  });
});

describe('recommendCellSize (D-cells)', () => {
  const base = { imageBytes: 8 * GIB };
  const measured = (upload: Record<string, number>, cells: Record<string, number>) => ({
    ...base,
    projectedUploadBytes: upload,
    projectedCells: cells,
  });

  it('scattered small writes: 1 MiB when it saves at least 50% of the bytes', () => {
    const r = recommendCellSize(
      measured(
        { '1MiB': 40 * MIB, '2MiB': 80 * MIB, '4MiB': 160 * MIB, '8MiB': 320 * MIB },
        { '1MiB': 40, '2MiB': 40, '4MiB': 40, '8MiB': 40 }
      )
    );
    expect(r.cellBytes).toBe(MIB);
    expect(r.rule).toBe('scattered-small');
    expect(r.savedPercent).toBe(75);
  });

  it('keeps 4 MiB when 1 MiB saves less than half', () => {
    const r = recommendCellSize(
      measured(
        { '1MiB': 90 * MIB, '2MiB': 100 * MIB, '4MiB': 120 * MIB, '8MiB': 160 * MIB },
        { '1MiB': 90, '2MiB': 50, '4MiB': 30, '8MiB': 20 }
      )
    );
    expect(r.cellBytes).toBe(4 * MIB);
  });

  it('exactly 50% saved counts: the rule says at least', () => {
    const r = recommendCellSize(
      measured(
        { '1MiB': 50 * MIB, '2MiB': 80 * MIB, '4MiB': 100 * MIB, '8MiB': 200 * MIB },
        { '1MiB': 50, '2MiB': 40, '4MiB': 25, '8MiB': 25 }
      )
    );
    expect(r.cellBytes).toBe(MIB);
  });

  it('clustered large writes: 8 MiB when it uploads no more bytes and needs far fewer puts', () => {
    const r = recommendCellSize(
      measured(
        { '1MiB': 400 * MIB, '2MiB': 400 * MIB, '4MiB': 400 * MIB, '8MiB': 400 * MIB },
        { '1MiB': 400, '2MiB': 200, '4MiB': 100, '8MiB': 50 }
      )
    );
    expect(r.cellBytes).toBe(8 * MIB);
    expect(r.rule).toBe('clustered-large');
  });

  it('refuses 1 MiB past the collapse cap of 262,144 cells, and says why', () => {
    const r = recommendCellSize({
      imageBytes: 300 * GIB,
      projectedUploadBytes: { '1MiB': 10 * MIB, '4MiB': 100 * MIB, '8MiB': 200 * MIB },
      projectedCells: { '1MiB': 10, '4MiB': 25, '8MiB': 25 },
    });
    expect(r.cellBytes).toBe(4 * MIB);
    // The rule names the cap, so the caller can say why 1 MiB was not chosen although it saves 90%.
    expect(r.rule).toBe('collapse-cap');
    expect(r.savedPercent).toBe(90);
  });

  it('keeps 4 MiB for an idle repository (nothing to save)', () => {
    const r = recommendCellSize(
      measured({ '1MiB': 0, '4MiB': 0, '8MiB': 0 }, { '1MiB': 0, '4MiB': 0, '8MiB': 0 })
    );
    expect(r.cellBytes).toBe(4 * MIB);
    expect(r.rule).toBe('idle');
  });
});
