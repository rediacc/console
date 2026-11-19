import {
  type FeedbackReport,
  type FeedbackSubmitResponse,
  feedbackKindSchema,
} from '@rediacc/shared';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import {
  fetchReports,
  findReport,
  listLines,
  parseStatusFilter,
  showLines,
  withDisplay,
} from '../services/feedback/list.js';
import { type RingEntry, readRing } from '../services/feedback/ring.js';
import {
  buildReport,
  type FeedbackAuth,
  type FetchFn,
  requestBody,
  resolveFeedbackAuth,
  sendReport,
} from '../services/feedback/send.js';
import { ERROR_CODES, type NextAction } from '../types/errors.js';
import { isAgentEnvironment } from '../utils/agent-guard.js';
import { CliExitError } from '../utils/cli-exit-error.js';
import { getOutputFormat, handleError } from '../utils/errors.js';
import { askConfirm } from '../utils/prompt.js';

export interface ReportOptions {
  last?: boolean;
  command?: string;
  listRecent?: boolean;
  kind?: string;
  message?: string;
}

export interface ReportDeps {
  readRing: () => RingEntry[];
  resolveAuth: () => Promise<FeedbackAuth>;
  confirm: (message: string) => Promise<boolean>;
  fetchFn?: FetchFn;
  yes: () => boolean;
  agent: () => boolean;
}

const defaultDeps: ReportDeps = {
  readRing,
  resolveAuth: () => resolveFeedbackAuth(),
  confirm: (message) => askConfirm(message, false),
  yes: () => process.env.REDIACC_YES === '1',
  agent: isAgentEnvironment,
};

function invalid(message: string): CliExitError {
  return new CliExitError(ERROR_CODES.VALIDATION_ERROR, message);
}

/** Ring entries newest first, so index 1 is the newest. */
function recentEntries(deps: ReportDeps): RingEntry[] {
  return [...deps.readRing()].reverse();
}

function pickEntry(options: ReportOptions, deps: ReportDeps): RingEntry | undefined {
  if (options.last && options.command !== undefined) {
    throw invalid(t('feedback.lastAndCommand'));
  }
  const recent = recentEntries(deps);
  if (options.command !== undefined) {
    const index = Number(options.command);
    const entry = Number.isInteger(index) ? recent[index - 1] : undefined;
    if (!entry) throw invalid(t('feedback.noSuchCommand', { index: options.command }));
    return entry;
  }
  if (options.last) {
    const failed = recent.find((e) => e.exitCode !== 0);
    if (!failed) throw invalid(t('feedback.noFailedCommand'));
    return failed;
  }
  return undefined;
}

function resolveKind(options: ReportOptions, entry: RingEntry | undefined): FeedbackReport['kind'] {
  if (options.kind === undefined) return entry ? 'bug' : 'feedback';
  const parsed = feedbackKindSchema.safeParse(options.kind);
  if (!parsed.success) throw invalid(t('feedback.badKind', { kind: options.kind }));
  return parsed.data;
}

function recentLines(deps: ReportDeps): string {
  const recent = recentEntries(deps);
  if (recent.length === 0) return t('feedback.noRecent');
  return recent.map((e, i) => `${i + 1}  ${e.at}  exit ${e.exitCode}  rdc ${e.argv}`).join('\n');
}

function sendNext(options: ReportOptions): NextAction {
  const flags = [
    options.last ? ' --last' : '',
    options.command === undefined ? '' : ` --command ${options.command}`,
    options.kind ? ` --kind ${options.kind}` : '',
    options.message === undefined ? '' : ` --message ${shellQuote(options.message)}`,
  ].join('');
  return {
    summary: t('feedback.previewOnly'),
    options: [
      {
        description: t('feedback.sendDescription'),
        run: `rdc feedback report${flags} --yes`,
      },
    ],
  };
}

/** POSIX single-quoting, so a message with spaces or quotes survives being pasted back as one argument. */
function shellQuote(value: string): string {
  return `'${value.replaceAll("'", `'\\''`)}'`;
}

/** The preview is the exact body that would be sent, so what the user reads is what leaves the machine. */
function previewText(body: unknown): string {
  return JSON.stringify(body, null, 2);
}

/** An agent without --yes: the preview and the command that sends it, never a send. */
function printPreviewOnly(body: unknown, options: ReportOptions, json: boolean): void {
  const next = sendNext(options);
  if (json) {
    outputService.print({ sent: false, preview: body, next }, 'json');
    return;
  }
  outputService.print(previewText(body));
  outputService.info(next.summary);
  outputService.info(next.options?.[0]?.run ?? '');
}

function printSent(body: unknown, response: FeedbackSubmitResponse, json: boolean): void {
  if (json) {
    outputService.print({ sent: true, preview: body, response }, 'json');
    return;
  }
  outputService.success(
    t(response.duplicate ? 'feedback.sentDuplicate' : 'feedback.sent', {
      id: response.id,
      fingerprint: response.fingerprint.slice(0, 12),
    })
  );
}

export async function runReport(
  options: ReportOptions,
  deps: ReportDeps = defaultDeps
): Promise<void> {
  if (options.listRecent) {
    outputService.print(recentLines(deps));
    return;
  }
  const entry = pickEntry(options, deps);
  const kind = resolveKind(options, entry);
  if (!entry && !options.message?.trim()) throw invalid(t('feedback.needsMessage'));

  const auth = await deps.resolveAuth();
  const body = requestBody(buildReport({ kind, message: options.message, entry }), auth);
  const json = getOutputFormat() === 'json';
  const yes = deps.yes();

  if (!yes && deps.agent()) return printPreviewOnly(body, options, json);

  if (!json) outputService.print(previewText(body));
  if (!yes && !(await deps.confirm(t('feedback.confirm')))) {
    outputService.info(t('feedback.declined'));
    return;
  }
  printSent(body, await sendReport(body, auth, deps.fetchFn), json);
}

export interface ReadDeps {
  resolveAuth: () => Promise<FeedbackAuth>;
  fetchFn?: FetchFn;
}

const defaultReadDeps: ReadDeps = { resolveAuth: () => resolveFeedbackAuth() };

export async function runList(
  options: { status?: string },
  deps: ReadDeps = defaultReadDeps
): Promise<void> {
  const statuses = parseStatusFilter(options.status);
  const reports = await fetchReports(await deps.resolveAuth(), statuses, deps.fetchFn);
  if (getOutputFormat() === 'json') {
    outputService.print({ reports: reports.map(withDisplay) }, 'json');
    return;
  }
  outputService.print(listLines(reports));
}

export async function runShow(id: string, deps: ReadDeps = defaultReadDeps): Promise<void> {
  const reports = await fetchReports(await deps.resolveAuth(), [], deps.fetchFn);
  const report = findReport(reports, id);
  if (getOutputFormat() === 'json') {
    outputService.print(withDisplay(report), 'json');
    return;
  }
  outputService.print(showLines(report));
}

export function registerFeedbackCommand(program: Command): void {
  const feedback = program
    .command('feedback')
    .summary(t('commands.feedback.descriptionShort'))
    .description(t('commands.feedback.description'));

  feedback
    .command('report')
    .summary(t('commands.feedback.report.descriptionShort'))
    .description(t('commands.feedback.report.description'))
    .option('--last', t('commands.feedback.report.optionLast'))
    .option('--command <n>', t('commands.feedback.report.optionCommand'))
    .option('--list-recent', t('commands.feedback.report.optionListRecent'))
    .option('--kind <kind>', t('commands.feedback.report.optionKind'))
    .option('--message <text>', t('commands.feedback.report.optionMessage'))
    .action(async (options: ReportOptions) => {
      try {
        await runReport(options);
      } catch (error) {
        handleError(error);
      }
    });

  feedback
    .command('list')
    .summary(t('commands.feedback.list.descriptionShort'))
    .description(t('commands.feedback.list.description'))
    .option('--status <list>', t('commands.feedback.list.optionStatus'))
    .action(async (options: { status?: string }) => {
      try {
        await runList(options);
      } catch (error) {
        handleError(error);
      }
    });

  feedback
    .command('show <id>')
    .summary(t('commands.feedback.show.descriptionShort'))
    .description(t('commands.feedback.show.description'))
    .action(async (id: string) => {
      try {
        await runShow(id);
      } catch (error) {
        handleError(error);
      }
    });
}
