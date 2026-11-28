import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  print: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  setExitCode: vi.fn(),
  format: { current: 'table' },
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { print: m.print, info: m.info, success: m.success, warn: m.warn },
}));
vi.mock('../../services/core/request-context.js', () => ({
  setExitCode: m.setExitCode,
  writeStderr: vi.fn(),
}));
vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => m.format.current,
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: vi.fn() }));

import {
  ForensicsClient,
  type ForensicsFetch,
  type IncidentRecord,
} from '../../services/forensics/client.js';
import type { DeclareDeps } from '../../services/forensics/declare.js';
import type { MachineSteps, StepRun } from '../../services/forensics/machine-steps.js';
import { failureDetail } from '../../services/forensics/machine-steps.js';
import { runIncidentClose, runIncidentDeclare } from '../incident.js';

const NOW = new Date('2026-11-25T12:00:00.000Z');
const GUID = '3f2b8c1e-5d4a-4e7b-9a10-0c2d4e6f8a1b';
const ID = 'a1b2c3d4-0000-4000-8000-00000000abcd';

const record = (over: Partial<IncidentRecord> = {}): IncidentRecord => ({
  id: ID,
  scopeKind: 'repo',
  scopeRef: GUID,
  windowFrom: '2026-11-24T12:00:00.000Z',
  windowTo: NOW.toISOString(),
  status: 'declared',
  declaredBy: 'user-1',
  declaredAt: NOW.toISOString(),
  awareAt: NOW.toISOString(),
  notifiedAt: null,
  containedAt: null,
  closedAt: null,
  closedBy: null,
  forkRef: null,
  steps: [{ name: 'hold', status: 'ok', at: NOW.toISOString() }],
  releaseAt: null,
  ...over,
});

interface Call {
  path: string;
  method?: string;
  body?: Record<string, unknown>;
}

type Body = Record<string, unknown> | undefined;

/** A declared incident built from a POST /incidents body. */
function declared(body: Body): IncidentRecord {
  return record({
    windowFrom: String(body?.windowFrom),
    windowTo: String(body?.windowTo),
    ...(body?.awareAt ? { awareAt: String(body.awareAt) } : {}),
  });
}

/** The incident after one reported step. */
function stepped(incident: IncidentRecord, body: Body): IncidentRecord {
  return {
    ...incident,
    steps: [
      ...incident.steps,
      { name: String(body?.name), status: String(body?.outcome), at: NOW.toISOString() },
    ],
    ...(body?.forkRef ? { forkRef: String(body.forkRef) } : {}),
  };
}

function closedIncident(incident: IncidentRecord): IncidentRecord {
  return {
    ...incident,
    status: 'closed',
    closedAt: NOW.toISOString(),
    releaseAt: '2026-12-25T12:00:00.000Z',
  };
}

/** The account server: it keeps one incident and applies each reported step to it. */
/** The incident after a step or close call; undefined for any other path. */
function mutate(path: string, incident: IncidentRecord, body: Body): IncidentRecord | undefined {
  if (path.endsWith('/steps')) return stepped(incident, body);
  if (path.endsWith('/close')) return closedIncident(incident);
  return undefined;
}

function server(initial: IncidentRecord | null = null) {
  const calls: Call[] = [];
  let incident = initial;
  const list = (method: string | undefined, body: Body): unknown => {
    if (method !== 'POST') return { incidents: incident ? [incident] : [] };
    incident = declared(body);
    return incident;
  };
  const answer = (path: string, method: string | undefined, body: Body): unknown => {
    if (path.endsWith('/incidents')) return list(method, body);
    const next = incident ? mutate(path, incident, body) : undefined;
    if (next) incident = next;
    return next;
  };
  const fetchFn = (path: string, options?: { method?: string; body?: unknown }) => {
    const body = options?.body as Body;
    calls.push({ path, method: options?.method, body });
    const reply = answer(path, options?.method, body);
    return reply === undefined
      ? Promise.reject(new Error(`unexpected ${path}`))
      : Promise.resolve(reply);
  };
  return {
    calls,
    client: new ForensicsClient(fetchFn as unknown as ForensicsFetch),
    current: () => incident,
  };
}

function steps(fork: StepRun, level: StepRun = { ok: true }) {
  const runs: string[][] = [];
  const machine: MachineSteps = {
    fork: (ref, tag) => {
      runs.push(['fork', ref, tag]);
      return Promise.resolve(fork);
    },
    level: (ref, lvl) => {
      runs.push(['level', ref, lvl]);
      return Promise.resolve(level);
    },
  };
  return { runs, machine };
}

function deps(client: ForensicsClient, machine: MachineSteps): DeclareDeps {
  return {
    client,
    repo: () => Promise.resolve({ guid: GUID, name: 'shop' }),
    steps: machine,
    now: () => NOW,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  m.format.current = 'table';
});

describe('incident declare', () => {
  it('records the incident first, then forks with the incident tag and switches capture to full once', async () => {
    const srv = server();
    const machine = steps({ ok: true });
    const result = await runIncidentDeclare(
      'shop@m1',
      { since: '24h' },
      deps(srv.client, machine.machine)
    );

    expect(srv.calls[0]).toMatchObject({
      path: '/account/api/v1/console/incidents',
      method: 'POST',
      body: {
        scopeKind: 'repo',
        scopeRef: GUID,
        windowFrom: '2026-11-24T12:00:00.000Z',
        windowTo: NOW.toISOString(),
      },
    });
    expect(machine.runs).toEqual([
      ['fork', 'shop@m1', `incident-${ID}`],
      ['level', 'shop@m1', 'full'],
    ]);
    expect(srv.calls.filter((c) => c.path.endsWith('/steps')).map((c) => c.body)).toEqual([
      { name: 'fork', outcome: 'ok', forkRef: `shop:incident-${ID}` },
      { name: 'level', outcome: 'ok' },
    ]);
    expect(result.retry).toBeNull();
    expect(m.setExitCode).not.toHaveBeenCalled();
  });

  it('keeps the account record when the fork fails, still raises capture, exits 1 and names the retry', async () => {
    const srv = server();
    const machine = steps({ ok: false, detail: 'fork refused: datastore full' });
    m.format.current = 'json';
    await runIncidentDeclare('shop@m1', {}, deps(srv.client, machine.machine));

    expect(srv.current()?.status).toBe('declared');
    expect(srv.calls.some((c) => c.path.endsWith('/close'))).toBe(false);
    expect(srv.calls.filter((c) => c.path.endsWith('/steps')).map((c) => c.body)).toEqual([
      { name: 'fork', outcome: 'failed', detail: 'fork refused: datastore full' },
      { name: 'level', outcome: 'ok' },
    ]);
    expect(m.setExitCode).toHaveBeenCalledWith(1);
    const [printed, format] = m.print.mock.calls[0] ?? [];
    expect(format).toBe('json');
    expect(printed).toMatchObject({
      retry: `rdc incident declare shop@m1 --resume ${ID}`,
      steps: [
        { name: 'fork', outcome: 'failed' },
        { name: 'level', outcome: 'ok' },
      ],
      incident: { id: ID, clocks: [{ name: 'earlyWarning' }, {}, {}] },
    });
  });

  it('names the retry command in text output', async () => {
    const srv = server();
    await runIncidentDeclare('shop', {}, deps(srv.client, steps({ ok: false }).machine));
    const warned = m.warn.mock.calls.map((c) => String(c[0])).join('\n');
    expect(warned).toContain('incident.stepFailed');
    expect(warned).toContain(`rdc incident declare shop --resume ${ID}`);
  });

  it('--resume runs only the step whose newest outcome is not ok, and declares nothing new', async () => {
    const srv = server(
      record({
        steps: [
          { name: 'fork', status: 'failed', at: NOW.toISOString() },
          { name: 'level', status: 'ok', at: NOW.toISOString() },
        ],
      })
    );
    const machine = steps({ ok: true });
    const result = await runIncidentDeclare(
      'shop',
      { resume: ID.slice(0, 8) },
      deps(srv.client, machine.machine)
    );
    expect(srv.calls.some((c) => c.method === 'POST' && c.path.endsWith('/incidents'))).toBe(false);
    expect(machine.runs).toEqual([['fork', 'shop', `incident-${ID}`]]);
    expect(result.steps).toEqual([
      { name: 'fork', outcome: 'ok' },
      { name: 'level', outcome: 'skipped' },
    ]);
    expect(m.setExitCode).not.toHaveBeenCalled();
  });

  it('--resume refuses an incident of another scope, a closed one and a new window', async () => {
    const other = server(record({ scopeRef: 'another-guid' }));
    await expect(
      runIncidentDeclare('shop', { resume: ID }, deps(other.client, steps({ ok: true }).machine))
    ).rejects.toMatchObject({ code: 'VALIDATION_ERROR', message: /incident.resumeScope/ });

    const closed = server(record({ status: 'closed' }));
    await expect(
      runIncidentDeclare('shop', { resume: ID }, deps(closed.client, steps({ ok: true }).machine))
    ).rejects.toMatchObject({ code: 'VALIDATION_ERROR', message: /incident.resumeClosed/ });

    const srv = server(record());
    await expect(
      runIncidentDeclare(
        'shop',
        { resume: ID, since: '7d' },
        deps(srv.client, steps({ ok: true }).machine)
      )
    ).rejects.toMatchObject({ code: 'VALIDATION_ERROR', message: /incident.resumeWindow/ });
  });

  it('sends an earlier awareness instant and refuses one that is not an instant', async () => {
    const srv = server();
    await runIncidentDeclare(
      'shop',
      { awareAt: '2026-11-24T08:00:00Z' },
      deps(srv.client, steps({ ok: true }).machine)
    );
    expect(srv.calls[0]?.body).toMatchObject({ awareAt: '2026-11-24T08:00:00.000Z' });

    const none = server();
    await expect(
      runIncidentDeclare(
        'shop',
        { awareAt: 'yesterday' },
        deps(none.client, steps({ ok: true }).machine)
      )
    ).rejects.toMatchObject({ code: 'VALIDATION_ERROR' });
    expect(none.calls).toEqual([]);
  });

  it('maps a refused step-up to the portal pointer before any machine step', async () => {
    const machine = steps({ ok: true });
    const refusing = new ForensicsClient((() =>
      Promise.reject(
        Object.assign(new Error('Re-authentication required'), {
          status: 403,
          details: { reauthRequired: true },
        })
      )) as unknown as ForensicsFetch);
    await expect(
      runIncidentDeclare('shop', {}, deps(refusing, machine.machine))
    ).rejects.toMatchObject({ code: 'AUTH_REQUIRED' });
    expect(machine.runs).toEqual([]);
  });
});

describe('incident close', () => {
  it('closes the incident a prefix names and prints when the hold ends', async () => {
    const srv = server(record());
    await runIncidentClose(ID.slice(0, 8), { client: srv.client, now: () => NOW });
    expect(srv.calls.at(-1)).toMatchObject({
      path: `/account/api/v1/console/incidents/${ID}/close`,
      method: 'POST',
    });
    expect(String(m.success.mock.calls[0]?.[0])).toContain('2026-12-25T12:00:00.000Z');
  });
});

describe('machine step detail', () => {
  it('keeps the last error line without colour codes, at most 500 characters', () => {
    expect(failureDetail('progress\n\u001b[31mError: fork refused\u001b[0m\n\n', 1)).toBe(
      'Error: fork refused'
    );
    expect(failureDetail('', 3)).toBe('exit 3');
    expect(failureDetail('x'.repeat(900), 1)).toHaveLength(500);
  });
});
