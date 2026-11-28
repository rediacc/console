/**
 * The two refusals a job start can end in: an overlap with other jobs on the
 * machine (exit 15) and a vault `expect` that no longer holds (exit 12).
 */

import type { JobOverlap } from '@rediacc/shared/cli-contract/wire';
import { t } from '../../i18n/index.js';
import { ERROR_CODES } from '../../types/errors.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { overlapWarningLines, type PreconditionRefusal } from './job-client.js';

const UNKNOWN_JOB_ID = '?';

/** The overlap refusal (section 19): exit 15, the other jobs as structured data. */
export class JobOverlapRefusedError extends CliExitError {
  constructor(
    readonly overlaps: JobOverlap[],
    machineName: string
  ) {
    const refusing = overlaps.filter((o) => o.action === 'refuse');
    const first = refusing[0];
    const holder = first
      ? t('errors.jobs.holderJob', { id: first.jobId ?? first.unit ?? UNKNOWN_JOB_ID })
      : t('errors.jobs.holderOther');
    super(ERROR_CODES.BUSY, t('errors.jobs.refused', { machine: machineName, holder }), {
      retryable: true,
      details: [
        ...refusing.flatMap(overlapWarningLines),
        ...(first?.jobId
          ? [t('errors.jobs.orStopIt', { id: first.jobId, machine: machineName })]
          : []),
      ],
    });
    this.name = 'JobOverlapRefusedError';
  }
}

/**
 * A start refused by its vault's `expect` (section 14): the machine's state is
 * not what the command was resolved against, and no unit was spawned. Exit 12,
 * the code the client-side presence probe this replaces refused with, and for
 * `repo_present` the same text, so the routing contradiction reads as before.
 */
export class JobPreconditionRefusedError extends CliExitError {
  constructor(
    readonly refusal: PreconditionRefusal,
    machineName: string
  ) {
    const machine = refusal.machine || machineName;
    super(
      ERROR_CODES.STATE_MISMATCH,
      refusal.expect === 'repo_present'
        ? `config places ${refusal.repository} on ${machine}, but ${machine} does not have its image. Run "rdc config reconcile", then retry.`
        : refusal.message
    );
    this.name = 'JobPreconditionRefusedError';
  }
}
