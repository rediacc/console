/**
 * `rdc datastore`, named, mobile, single-mounter pools (spec 02 §1, 03 §5.3).
 *
 * ★ #34: this family used to dispatch `datastore_init` / `datastore_ceph_init`,
 * which DO NOT EXIST in renet, and `fork`/`unfork` were leaves whose entire body
 * was a throw. The whole noun was a facade over the pre-datastore world. P1 landed
 * the real named-registry bridge verbs (`datastore_create/attach/detach/fork/
 * list/delete/snapshot_*`); this is the porcelain over them.
 *
 * Every mutating leaf is gate class D (agentBlocked, REDIACC_ALLOW_CLUSTER_OPS):
 * a datastore holds every repo in it, so moving or destroying one is an
 * infrastructure act, not a repo act. Reads are class A.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { type Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import {
  assertCreatableName,
  at,
  childDatastores,
  forgetDatastore,
  getDatastore,
  listDatastoreState,
  listDatastores,
  parseDatastoreRef,
  reposInDatastore,
  requireDatastoreHost,
  setDatastoreState,
} from '../services/config/config-datastores.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { parseCapturedJson } from '../services/executor/local-executor.js';
import {
  type CommandJobOutcome,
  pendingExitCode,
  runCommandJob,
} from '../services/jobs/command-job.js';
import { outstandingSteps } from '../services/jobs/run-job.js';
import { bindStepHandler, type PlannedStep, planStep } from '../services/jobs/steps.js';
import { stateMismatch } from '../utils/cli-exit-error.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { askConfirm } from '../utils/prompt.js';
import { assertMachineExists } from './_validate.js';

interface DebugOpt {
  debug?: boolean;
}

/** Dispatch a datastore bridge verb, throwing on failure. */
async function dispatch(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  opts: { debug?: boolean; capture?: boolean } = {}
): Promise<string> {
  const res = await getExecutor().execute({
    functionName,
    machineName,
    params,
    debug: opts.debug,
    captureOutput: opts.capture,
  });
  if (!res.success) {
    throw new Error(`Datastore step "${functionName}" failed on ${machineName}: ${res.error}`);
  }
  return res.stdout ?? '';
}

/**
 * Run a datastore verb as one machine job with its client-side steps on the ticket (PLAN-detached-jobs J19). A job
 * that finished and failed throws like `dispatch`; a job still running past the attach window returns `pending`, and
 * its steps (the config record) run when `rdc job wait` or the finished notice sees it succeed.
 */
async function dispatchAsJob(
  verb: string,
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  steps: PlannedStep[],
  debug?: boolean,
  capture?: boolean
): Promise<CommandJobOutcome> {
  const outcome = await runCommandJob(
    verb,
    { functionName, machineName, params, debug, captureOutput: capture },
    steps
  );
  if (outcome.kind === 'finished' && !outcome.result.success) {
    throw new Error(
      `Datastore step "${functionName}" failed on ${machineName}: ${outcome.result.error}`
    );
  }
  return outcome;
}

/** A pending job owes its exit code (a lost tail) and prints nothing more: the ticket notice names how to wait. */
function settledPending(outcome: CommandJobOutcome): boolean {
  if (outcome.kind !== 'pending') {
    // A finished job whose step did not finish owes it to `rdc job wait`; the command does not claim success.
    const unfinished = outstandingSteps(outcome.steps);
    if (unfinished.length === 0) return false;
    outputService.warn(
      t('commands.job.stepsUnfinished', { verb: 'datastore', steps: unfinished.join(', ') })
    );
    setExitCode(1);
    return true;
  }
  const code = pendingExitCode(outcome);
  if (code !== undefined) setExitCode(code);
  return true;
}

/**
 * A datastore's registry record as the machine that holds it reports it.
 *
 * `renet datastore list --json` emits each row as the flattened Record plus its
 * `name`, which is the shape `datastore adopt --record-b64` reads back, so this
 * one call is both the lookup and the ferry payload.
 */
function findDatastoreRecord(
  output: string | undefined,
  machineName: string,
  ref: string
): { name: string; backend?: string; fork?: unknown } {
  const records = parseCapturedJson<{ name: string; backend?: string; fork?: unknown }[]>(
    output ?? ''
  );
  const record = records.find((r) => r.name === ref);
  if (!record) {
    throw new ValidationError(
      `Datastore "${ref}" is not in ${machineName}'s registry, so there is no record to move. ` +
        `Nothing has been changed.`
    );
  }
  return record;
}

/**
 * Copy a datastore's registry row from the machine that holds it to the machine
 * about to attach it.
 *
 * The registry is PER-MACHINE, and it is the only place a datastore's ceph pool
 * and image are written down. A machine that has never seen the datastore cannot
 * attach a name it does not know: the attach died with `datastore "<ref>" is not
 * registered on this machine`, and in the relocation case it died AFTER the
 * detach, leaving the datastore attached NOWHERE (found live by
 * `./run.sh drill license --legs b`, 2026-08-04). This is the same
 * `datastore_adopt` the cluster paths use (cluster-fork.ts, repo-replicate.ts;
 * findings #14 and #18), whose `--plain` half exists for exactly this non-fork
 * move.
 *
 * EVERYTHING NON-DESTRUCTIVE HAPPENS FIRST, which is why callers ferry before
 * they detach rather than merely before they attach. renet's own Adopt doc
 * states the ordering rule for this case (adopt.go:22-28: "adopts it BEFORE
 * anything destructive, so a registry miss can never strand a downed source"),
 * and adopt earns it: one registry row, no disk work, idempotent on a name
 * already present (adopt.go:61-62), so a resumed relocation converges. With the
 * adopt last, a malformed record or an unreachable target still strands the
 * datastore attached nowhere, the same bug, one step later.
 *
 * The record was captured by the relocation's first job (`datastore_list` on the holder), so a ticket handed back
 * early still owes this ferry to its step.
 */
async function ferryDatastoreRecord(
  captured: string | undefined,
  from: string,
  to: string,
  ref: string,
  debug?: boolean
): Promise<void> {
  const record = findDatastoreRecord(captured, from, ref);
  // A local-backend datastore's bytes never leave their machine, so relocating one is not something that can be half-done, it is something that must not start. renet refuses it too (adopt.go:44-46), but only after this command would already have detached.
  if (record.backend !== 'ceph') {
    const backend = record.backend ?? DEFAULTS.DATASTORE.BACKEND;
    throw new ValidationError(
      `Datastore "${ref}" is ${backend}-backed, so its bytes live on ` +
        `${from} alone and ${to} cannot reach them. Only a ceph-backed datastore ` +
        `relocates. Nothing has been changed.`
    );
  }
  await dispatch(
    'datastore_adopt',
    to,
    {
      name: ref,
      record_b64: Buffer.from(JSON.stringify(record)).toString('base64'),
      // renet refuses a fork record under --plain and a plain record without it, so the shape is read off the record, not guessed from the ref.
      ...(record.fork ? {} : { plain: true }),
    },
    { debug }
  );
}

function boolParam(value: unknown): boolean {
  return value === true;
}

function writesParam(value: unknown): 'local' | 'ceph' | undefined {
  return value === 'local' || value === 'ceph' ? value : undefined;
}

function strParam(value: unknown): string | undefined {
  return typeof value === 'string' && value !== '' ? value : undefined;
}

/**
 * The relocation tail of `datastore attach --to <machine>` (PLAN-detached-jobs J19). The relocation alternates
 * machines and each call consumes the one before (the source record feeds the target's adopt, and the adopt comes
 * before the detach), so it is not a static successor and renet has no compound function for it. The first job is the
 * `datastore_list` read on the holder; this step is the client-driven rest: adopt on the target, detach on the holder
 * (an attached datastore only), attach on the target, then the routing hint.
 */
bindStepHandler('relocateDatastore', async ({ params, machine, output, finishedAt }) => {
  const ref = String(params.datastore);
  const to = String(params.to);
  const debug = boolParam(params.debug);
  const writes = writesParam(params.writes);
  await ferryDatastoreRecord(output, machine, to, ref, debug);
  if (boolParam(params.detach)) {
    // Single-mounter relocation (02 §3): the old holder gives it up first, and a failed detach aborts the move with the old attach intact.
    await dispatch('datastore_detach', machine, { name: ref }, { debug });
  }
  const cowSize = strParam(params.cowSize);
  await dispatch(
    'datastore_attach',
    to,
    {
      name: ref,
      ...(writes && { writes }),
      ...(cowSize && { cow_size: cowSize }),
      ...(boolParam(params.force) && { force: true }),
      ...(boolParam(params.noAuto) && { no_auto: true }),
    },
    { debug }
  );
  const lastHolder = strParam(params.lastHolder);
  await setDatastoreState(ref, {
    attachedTo: to,
    ...(writes && { writes }),
    // Carried, not dropped: the schema's contract is that lastHolder is never cleared, only overwritten by the next detach. Attaching does not make the previous holder's registry row untrue.
    ...(lastHolder && { lastHolder }),
    mounted: true,
    attachedAt: finishedAt ?? new Date().toISOString(),
  });
  outputService.success(t('commands.datastore.attach.attached', { ref, machine: to }));
});

/** The attach leg of `datastore fork --attach-to`: the fork is the ticket's job, the attach on the second machine follows it. */
bindStepHandler('attachForkedDatastore', async ({ params, finishedAt }) => {
  const ref = String(params.datastore);
  const to = String(params.to);
  const writes = writesParam(params.writes);
  const cowSize = strParam(params.cowSize);
  await dispatch(
    'datastore_attach',
    to,
    { name: ref, writes, ...(cowSize && { cow_size: cowSize }) },
    { debug: boolParam(params.debug) }
  );
  await setDatastoreState(ref, {
    attachedTo: to,
    writes,
    mounted: true,
    attachedAt: finishedAt ?? new Date().toISOString(),
  });
  outputService.success(t('commands.datastore.attach.attached', { ref, machine: to }));
});

/** The tail of `datastore delete` on an attached datastore: the detach was the job, the unlink and the record follow it. */
bindStepHandler('deleteDatastoreTail', async ({ params, machine }) => {
  const ref = String(params.datastore);
  await dispatch('datastore_delete', machine, { name: ref }, { debug: boolParam(params.debug) });
  await forgetDatastore(ref);
  outputService.success(t('commands.datastore.delete.deleted', { ref }));
});

function registerCreate(datastore: Command): void {
  datastore
    .command('create')
    .summary(t('commands.datastore.create.descriptionShort'))
    .description(t('commands.datastore.create.description'))
    .argument('<datastore>', t('options.datastoreRef'))
    .requiredOption('-m, --machine <name>', t('commands.datastore.create.machineOption'))
    .requiredOption('--size <size>', t('commands.datastore.create.sizeOption'))
    .addOption(
      new Option('--backend <type>', t('commands.datastore.create.backendOption'))
        .choices(['local', 'rbd'])
        .default('local')
    )
    .option('--pool <name>', t('commands.datastore.create.poolOption'))
    .option('--image <name>', t('commands.datastore.create.imageOption'))
    .option('--cluster <name>', t('commands.datastore.create.clusterOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        name: string,
        options: {
          machine: string;
          size: string;
          backend: string;
          pool?: string;
          image?: string;
          cluster?: string;
        } & DebugOpt
      ) => {
        try {
          await assertCommandPolicy(CMD.DATASTORE_CREATE, undefined, name);
          assertCreatableName(name);
          if (name in (await listDatastores())) {
            throw new ValidationError(`datastore "${name}" already exists.`);
          }
          await assertMachineExists(options.machine);
          if (options.cluster) {
            // A cluster backref that names no cluster would silently make the datastore kubernetes-world with no cluster to belong to.
            await configService.listClusters().then((clusters) => {
              if (!clusters.some((c) => c.name === options.cluster)) {
                throw new ValidationError(
                  `cluster "${options.cluster}" is not configured. Configured clusters: ` +
                    `${clusters.map((c) => c.name).join(', ') || 'none'}.`
                );
              }
            });
          }

          const rbd = options.backend === 'rbd';
          const outcome = await dispatchAsJob(
            'datastore create',
            'datastore_create',
            options.machine,
            {
              name,
              backend: rbd ? 'ceph' : 'local',
              size: options.size,
              ...(rbd && {
                pool: options.pool ?? DEFAULTS.DATASTORE.RBD_POOL,
                image: options.image ?? name,
              }),
              ...(options.cluster && { cluster: options.cluster }),
            },
            [
              planStep('recordDatastore', {
                datastore: name,
                record: JSON.stringify({
                  backend: rbd
                    ? {
                        kind: 'rbd',
                        pool: options.pool ?? DEFAULTS.DATASTORE.RBD_POOL,
                        image: options.image ?? name,
                      }
                    : { kind: 'local', machine: options.machine, path: `/mnt/rediacc-ds/${name}` },
                  ...(options.cluster && { cluster: options.cluster }),
                  size: options.size,
                }),
              }),
            ],
            options.debug
          );
          if (settledPending(outcome)) return;
          outputService.success(
            t('commands.datastore.create.created', { name, machine: options.machine })
          );
        } catch (error) {
          handleError(error);
        }
      }
    );
}

function registerReads(datastore: Command): void {
  datastore
    .command('list')
    .summary(t('commands.datastore.list.descriptionShort'))
    .description(t('commands.datastore.list.description'))
    .argument('[place]', t('commands.datastore.list.placeArgument'))
    .action(async (place?: string) => {
      try {
        const records = await listDatastores();
        const state = await listDatastoreState();
        const rows = await Promise.all(
          Object.entries(records).map(async ([name, record]) => {
            const entry = at(state, name);
            return {
              name,
              backend: record.backend.kind,
              size: record.size,
              cluster: record.cluster,
              attachedTo: entry?.attachedTo,
              writes: entry?.writes,
              repos: (await reposInDatastore(name)).length,
            };
          })
        );
        // A place narrows to one cluster (its backref) or one machine (its holder).
        const filtered = place
          ? rows.filter((r) => r.cluster === place || r.attachedTo === place)
          : rows;
        outputService.print(filtered, getOutputFormat());
      } catch (error) {
        handleError(error);
      }
    });

  datastore
    .command('status')
    .summary(t('commands.datastore.status.descriptionShort'))
    .description(t('commands.datastore.status.description'))
    .argument('<datastore>', t('options.datastoreRef'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string, options: DebugOpt) => {
      try {
        const record = await getDatastore(ref);
        const entry = at(await listDatastoreState(), ref);
        const host = entry?.attachedTo;
        // A detached datastore still HAS a status (its record); reads never exit
        // 12, so report the unverified state instead of refusing (spec §5.3).
        if (!host) {
          outputService.print(
            { name: ref, ...record, attached: false, state: { verified: false } },
            getOutputFormat()
          );
          return;
        }
        // One read job; the render is its step, so a ticket handed back early prints nothing half-done.
        const outcome = await dispatchAsJob(
          'datastore status',
          'datastore_status',
          host,
          { name: ref },
          [planStep('renderDatastoreStatus', { datastore: ref })],
          options.debug,
          true
        );
        settledPending(outcome);
      } catch (error) {
        handleError(error);
      }
    });
}

function registerAttach(datastore: Command): void {
  datastore
    .command('attach')
    .summary(t('commands.datastore.attach.descriptionShort'))
    .description(t('commands.datastore.attach.description'))
    .argument('<datastore>', t('options.datastoreRef'))
    .requiredOption('--to <machine>', t('commands.datastore.attach.toOption'))
    .addOption(
      new Option('--writes <disposition>', t('commands.datastore.attach.writesOption')).choices([
        'local',
        'ceph',
      ])
    )
    .option('--cow-size <size>', t('commands.datastore.attach.cowSizeOption'))
    .option('--no-auto', t('commands.datastore.attach.noAutoOption'))
    .option('--force', t('commands.datastore.attach.forceOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        ref: string,
        options: {
          to: string;
          writes?: 'local' | 'ceph';
          cowSize?: string;
          auto: boolean;
          force?: boolean;
        } & DebugOpt
      ) => {
        try {
          const record = await getDatastore(ref);
          await assertCommandPolicy(CMD.DATASTORE_ATTACH, undefined, ref);
          await assertMachineExists(options.to);
          const isFork = parseDatastoreRef(ref).tag !== undefined || record.parent !== undefined;

          // The teaching error (spec 03 §2): a fork's writes have to go somewhere, and the two answers have opposite durability. Guessing for the operator is how you silently throw away an experiment they meant to keep.
          if (isFork && !options.writes) {
            throw new ValidationError(t('errors.datastore.forkNeedsWrites', { ref }));
          }
          if (!isFork && options.writes) {
            throw new ValidationError(t('errors.datastore.writesOnNonFork', { ref }));
          }

          const state = await listDatastoreState();
          const entry = at(state, ref);
          const current = entry?.attachedTo;
          if (current === options.to && entry?.writes === options.writes) {
            outputService.success(
              t('commands.datastore.attach.noop', { ref, machine: options.to })
            );
            return;
          }
          if (current === options.to) {
            throw new ValidationError(t('errors.datastore.writesImmutable', { ref }));
          }
          const relocateFrom =
            current ??
            (entry?.lastHolder && entry.lastHolder !== options.to ? entry.lastHolder : undefined);
          if (relocateFrom) {
            // Relocation: the first job reads the holder's registry row (`datastore_list`); the rest (adopt, the detach of an attached holder, the attach, the routing hint) is the step that follows it. A DETACHED relocation has no detach, but the row exists only on the machine that last held the datastore (`lastHolder`), and a guessed holder would fence a live one.
            if (current) {
              outputService.info(
                t('commands.datastore.attach.relocating', { ref, from: current, to: options.to })
              );
            }
            const relocation = await dispatchAsJob(
              'datastore attach',
              'datastore_list',
              relocateFrom,
              {},
              [
                planStep('relocateDatastore', {
                  datastore: ref,
                  to: options.to,
                  detach: current !== undefined,
                  ...(options.writes && { writes: options.writes }),
                  ...(options.cowSize && { cowSize: options.cowSize }),
                  ...(options.force && { force: true }),
                  ...(options.auto === false && { noAuto: true }),
                  ...(entry?.lastHolder && { lastHolder: entry.lastHolder }),
                  ...(options.debug && { debug: true }),
                }),
              ],
              options.debug,
              true
            );
            settledPending(relocation);
            return;
          }

          const outcome = await dispatchAsJob(
            'datastore attach',
            'datastore_attach',
            options.to,
            {
              name: ref,
              ...(options.writes && { writes: options.writes }),
              ...(options.cowSize && { cow_size: options.cowSize }),
              ...(options.force && { force: true }),
              ...(options.auto === false && { no_auto: true }),
            },
            [
              planStep('setDatastoreState', {
                datastore: ref,
                state: JSON.stringify({
                  attachedTo: options.to,
                  ...(options.writes && { writes: options.writes }),
                  mounted: true,
                  ...(entry?.lastHolder && { lastHolder: entry.lastHolder }),
                }),
              }),
            ],
            options.debug
          );
          if (settledPending(outcome)) return;
          outputService.success(
            t('commands.datastore.attach.attached', { ref, machine: options.to })
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  datastore
    .command('detach')
    .summary(t('commands.datastore.detach.descriptionShort'))
    .description(t('commands.datastore.detach.description'))
    .argument('<datastore>', t('options.datastoreRef'))
    .option('--discard', t('commands.datastore.detach.discardOption'))
    .option('-y, --yes', t('options.yes'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string, options: { discard?: boolean; yes?: boolean } & DebugOpt) => {
      try {
        await getDatastore(ref);
        await assertCommandPolicy(CMD.DATASTORE_DETACH, undefined, ref);
        const state = await listDatastoreState();
        const entry = at(state, ref);
        const host = entry?.attachedTo;
        if (!host) {
          outputService.success(t('commands.datastore.detach.noop', { ref }));
          return;
        }
        // A `--writes local` fork's overlay is ephemeral BY CONSTRUCTION: there is nowhere for it to be written back to. Detaching it destroys it, so say so and make the operator say --discard (spec §5.3). The `!host` return above proves `entry` is present.
        if (entry.writes === 'local' && !options.discard) {
          throw new ValidationError(t('errors.datastore.localForkNeedsDiscard', { ref }));
        }
        if (options.discard && !options.yes) {
          const ok = await askConfirm(t('commands.datastore.detach.confirmDiscard', { ref }));
          if (!ok) {
            outputService.info(t('commands.datastore.detach.aborted'));
            return;
          }
        }

        // Remember WHO held it. renet's registry row, the ceph pool/image record a later relocation has to ferry, survives only on that machine, so a detached datastore that forgets its last holder cannot be attached anywhere else: `datastore attach --to <other>` fails "not registered on this machine" and the CLI has nowhere to fetch the row from. The whole entry is replaced
        // rather than merged because every OTHER field describes an attachment that no longer exists. A --discard detach drops this again with the next step: forgetDatastore clears both halves, which is right, since there is no longer a datastore to relocate.
        const outcome = await dispatchAsJob(
          'datastore detach',
          'datastore_detach',
          host,
          { name: ref, ...(options.discard && { discard: true }) },
          [
            planStep('setDatastoreState', {
              datastore: ref,
              state: JSON.stringify({ lastHolder: host }),
            }),
            ...(options.discard ? [planStep('forgetDatastore', { datastore: ref })] : []),
          ],
          options.debug
        );
        if (settledPending(outcome)) return;
        outputService.success(
          t(
            options.discard
              ? 'commands.datastore.detach.discarded'
              : 'commands.datastore.detach.detached',
            { ref, machine: host }
          )
        );
      } catch (error) {
        handleError(error);
      }
    });
}

function registerFork(datastore: Command): void {
  datastore
    .command('fork')
    .summary(t('commands.datastore.fork.descriptionShort'))
    .description(t('commands.datastore.fork.description'))
    .argument('<datastore>', t('options.datastoreRef'))
    .requiredOption('--tag <tag>', t('commands.datastore.fork.tagOption'))
    .option('--attach-to <machine>', t('commands.datastore.fork.attachToOption'))
    .addOption(
      new Option('--writes <disposition>', t('commands.datastore.fork.writesOption')).choices([
        'local',
        'ceph',
      ])
    )
    .option('--cow-size <size>', t('commands.datastore.fork.cowSizeOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        name: string,
        options: {
          tag: string;
          attachTo?: string;
          writes?: 'local' | 'ceph';
          cowSize?: string;
        } & DebugOpt
      ) => {
        try {
          const record = await getDatastore(name);
          await assertCommandPolicy(CMD.DATASTORE_FORK, undefined, name);
          // Gate ruling C8 (spec 01 wins): there is no block-level clone primitive
          // for the local backend, so a local datastore cannot fork AT ALL, not even
          // on its own machine. Repos inside it fork individually by reflink.
          if (record.backend.kind !== 'rbd') {
            throw new ValidationError(t('errors.datastore.localForkUnsupported', { name }));
          }
          const forkRef = `${name}:${options.tag}`;
          if (forkRef in (await listDatastores())) {
            throw new ValidationError(`datastore fork "${forkRef}" already exists.`);
          }
          if (options.attachTo && !options.writes) {
            throw new ValidationError(t('errors.datastore.forkNeedsWrites', { ref: forkRef }));
          }

          const host = await requireDatastoreHost(name);
          if (options.attachTo) await assertMachineExists(options.attachTo);
          // One fork job on the holder; the record is its first step, and `--attach-to` is the client-driven second phase (the attach on another machine), a step too.
          const outcome = await dispatchAsJob(
            'datastore fork',
            'datastore_fork',
            host,
            {
              parent: name,
              tag: options.tag,
              ...(options.cowSize && { cow_size: options.cowSize }),
            },
            [
              planStep('recordDatastore', {
                datastore: forkRef,
                record: JSON.stringify({
                  backend: record.backend,
                  ...(record.cluster && { cluster: record.cluster }),
                  ...(record.size && { size: record.size }),
                  parent: { datastore: name },
                }),
              }),
              ...(options.attachTo
                ? [
                    planStep('attachForkedDatastore', {
                      datastore: forkRef,
                      to: options.attachTo,
                      ...(options.writes && { writes: options.writes }),
                      ...(options.cowSize && { cowSize: options.cowSize }),
                      ...(options.debug && { debug: true }),
                    }),
                  ]
                : []),
            ],
            options.debug
          );
          if (settledPending(outcome)) return;
          outputService.success(t('commands.datastore.fork.forked', { ref: forkRef, name }));
        } catch (error) {
          handleError(error);
        }
      }
    );
}

function registerSnapshot(datastore: Command): void {
  const snapshot = datastore
    .command('snapshot')
    .summary(t('commands.datastore.snapshot.descriptionShort'))
    .description(t('commands.datastore.snapshot.description'));

  snapshot
    .command('create')
    .summary(t('commands.datastore.snapshot.create.descriptionShort'))
    .description(t('commands.datastore.snapshot.create.description'))
    .argument('<datastore>', t('options.datastoreRef'))
    .option('--snapshot <label>', t('commands.datastore.snapshot.create.labelOption'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string, options: { snapshot?: string } & DebugOpt) => {
      try {
        await getDatastore(ref);
        await assertCommandPolicy(CMD.DATASTORE_SNAPSHOT_CREATE, undefined, ref);
        const label = options.snapshot ?? new Date().toISOString().replaceAll(/[:.]/g, '-');
        const host = await requireDatastoreHost(ref);
        const outcome = await dispatchAsJob(
          'datastore snapshot create',
          'datastore_snapshot_create',
          host,
          { name: ref, snapshot: label },
          [],
          options.debug
        );
        if (settledPending(outcome)) return;
        outputService.success(t('commands.datastore.snapshot.create.created', { ref, label }));
      } catch (error) {
        handleError(error);
      }
    });

  snapshot
    .command('list')
    .summary(t('commands.datastore.snapshot.list.descriptionShort'))
    .description(t('commands.datastore.snapshot.list.description'))
    .argument('<datastore>', t('options.datastoreRef'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string, options: DebugOpt) => {
      try {
        await getDatastore(ref);
        const host = await requireDatastoreHost(ref);
        const outcome = await dispatchAsJob(
          'datastore snapshot list',
          'datastore_snapshot_list',
          host,
          { name: ref },
          [planStep('printCapturedJson')],
          options.debug,
          true
        );
        settledPending(outcome);
      } catch (error) {
        handleError(error);
      }
    });
}

function registerMutators(datastore: Command): void {
  datastore
    .command('resize')
    .summary(t('commands.datastore.resize.descriptionShort'))
    .description(t('commands.datastore.resize.description'))
    .argument('<datastore>', t('options.datastoreRef'))
    .requiredOption('--size <size>', t('commands.datastore.resize.sizeOption'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string, options: { size: string } & DebugOpt) => {
      try {
        await assertCommandPolicy(CMD.DATASTORE_RESIZE, undefined, ref);
        const host = await requireDatastoreHost(ref);
        const outcome = await dispatchAsJob(
          'datastore resize',
          'datastore_resize',
          host,
          { name: ref, size: options.size },
          [planStep('setDatastoreSize', { datastore: ref, size: options.size })],
          options.debug
        );
        if (settledPending(outcome)) return;
        outputService.success(t('commands.datastore.resize.resized', { ref, size: options.size }));
      } catch (error) {
        handleError(error);
      }
    });

  datastore
    .command('delete')
    .summary(t('commands.datastore.delete.descriptionShort'))
    .description(t('commands.datastore.delete.description'))
    .argument('<datastore>', t('options.datastoreRef'))
    .option('-y, --yes', t('options.yes'))
    .option('--force', t('commands.datastore.delete.forceOption'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string, options: { yes?: boolean; force?: boolean } & DebugOpt) => {
      try {
        await getDatastore(ref);
        await assertCommandPolicy(CMD.DATASTORE_DELETE, undefined, ref);

        // Detach-before-unlink (03 hygiene rule 1): a datastore with repo records still pointing at it is not garbage, it is someone's data.
        const repos = await reposInDatastore(ref);
        if (repos.length > 0 && !options.force) {
          throw new ValidationError(
            t('errors.datastore.deleteHasRepos', { ref, repos: repos.join(', ') })
          );
        }
        // Children are never covered by --force: deleting the parent would orphan their reflink lineage.
        const children = await childDatastores(ref);
        if (children.length > 0) {
          throw stateMismatch(
            t('errors.datastore.deleteHasChildren', { ref, children: children.join(', ') }),
            { details: children }
          );
        }
        if (!options.yes) {
          const ok = await askConfirm(t('commands.datastore.delete.confirm', { ref }));
          if (!ok) {
            outputService.info(t('commands.datastore.delete.aborted'));
            return;
          }
        }

        const deleteState = at(await listDatastoreState(), ref);
        const host = deleteState?.attachedTo;
        if (host) {
          // A failed detach fails the delete: never unlink a record whose pool is still mounted somewhere (03 rule 1).
          // The detach is the ticket's job; clearing the routing hint and the unlink (`datastore_delete` on the same host, then the record) are the steps after it, so a ticket handed back early never unlinks a pool whose detach has not happened.
          const outcome = await dispatchAsJob(
            'datastore delete',
            'datastore_detach',
            host,
            { name: ref },
            [
              planStep('setDatastoreState', { datastore: ref }),
              planStep('deleteDatastoreTail', {
                datastore: ref,
                ...(options.debug && { debug: true }),
              }),
            ],
            options.debug
          );
          settledPending(outcome);
          return;
        }
        // Never attached: no machine holds it, so nothing runs as a job; only the record goes.
        await forgetDatastore(ref);
        outputService.success(t('commands.datastore.delete.deleted', { ref }));
      } catch (error) {
        handleError(error);
      }
    });
}

export function registerDatastoreCommands(program: Command): void {
  const datastore = program
    .command('datastore')
    .summary(t('commands.datastore.descriptionShort'))
    .description(t('commands.datastore.description'));

  registerCreate(datastore);
  registerReads(datastore);
  registerAttach(datastore);
  registerFork(datastore);
  registerSnapshot(datastore);
  registerMutators(datastore);
}
