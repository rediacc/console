/**
 * `rdc datastore` — named, mobile, single-mounter pools (spec 02 §1, 03 §5.3).
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

import { type Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import {
  assertCreatableName,
  at,
  forgetDatastore,
  getDatastore,
  listDatastores,
  listDatastoreState,
  parseDatastoreRef,
  recordDatastore,
  reposInDatastore,
  requireDatastoreHost,
  setDatastoreState,
} from '../services/config/config-datastores.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { parseCapturedJson } from '../services/executor/local-executor.js';
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
            // A cluster backref that names no cluster would silently make the
            // datastore kubernetes-world with no cluster to belong to.
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
          await dispatch(
            'datastore_create',
            options.machine,
            {
              name,
              backend: rbd ? 'ceph' : 'local',
              size: options.size,
              ...(rbd && { pool: options.pool ?? 'rbd', image: options.image ?? name }),
              ...(options.cluster && { cluster: options.cluster }),
            },
            { debug: options.debug }
          );

          await recordDatastore(name, {
            backend: rbd
              ? { kind: 'rbd', pool: options.pool ?? 'rbd', image: options.image ?? name }
              : { kind: 'local', machine: options.machine, path: `/mnt/rediacc-ds/${name}` },
            ...(options.cluster && { cluster: options.cluster }),
            size: options.size,
          });
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
        const raw = await dispatch(
          'datastore_status',
          host,
          { name: ref },
          { debug: options.debug, capture: true }
        );
        outputService.print(
          { name: ref, ...record, attachedTo: host, live: parseCapturedJson<unknown>(raw) },
          getOutputFormat()
        );
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

          // The teaching error (spec 03 §2): a fork's writes have to go somewhere,
          // and the two answers have opposite durability. Guessing for the operator
          // is how you silently throw away an experiment they meant to keep.
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
          if (current) {
            // Single-mounter relocation (02 §3): the old holder gives it up first,
            // and a failed detach aborts the move with the old attach intact.
            outputService.info(
              t('commands.datastore.attach.relocating', { ref, from: current, to: options.to })
            );
            await dispatch('datastore_detach', current, { name: ref }, { debug: options.debug });
          }

          await dispatch(
            'datastore_attach',
            options.to,
            {
              name: ref,
              ...(options.writes && { writes: options.writes }),
              ...(options.cowSize && { cow_size: options.cowSize }),
              ...(options.force && { force: true }),
              ...(options.auto === false && { no_auto: true }),
            },
            { debug: options.debug }
          );
          await setDatastoreState(ref, {
            attachedTo: options.to,
            ...(options.writes && { writes: options.writes }),
            mounted: true,
            attachedAt: new Date().toISOString(),
          });
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
        // A `--writes local` fork's overlay is ephemeral BY CONSTRUCTION: there is
        // nowhere for it to be written back to. Detaching it destroys it, so say so
        // and make the operator say --discard (spec §5.3).
        // The `!host` return above proves `entry` is present.
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

        await dispatch(
          'datastore_detach',
          host,
          { name: ref, ...(options.discard && { discard: true }) },
          { debug: options.debug }
        );
        await setDatastoreState(ref, undefined);
        if (options.discard) {
          await forgetDatastore(ref);
        }
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
          await dispatch(
            'datastore_fork',
            host,
            {
              parent: name,
              tag: options.tag,
              ...(options.cowSize && { cow_size: options.cowSize }),
            },
            { debug: options.debug }
          );
          await recordDatastore(forkRef, {
            backend: record.backend,
            ...(record.cluster && { cluster: record.cluster }),
            ...(record.size && { size: record.size }),
            parent: { datastore: name },
          });
          outputService.success(t('commands.datastore.fork.forked', { ref: forkRef, name }));

          if (options.attachTo) {
            await assertMachineExists(options.attachTo);
            await dispatch(
              'datastore_attach',
              options.attachTo,
              {
                name: forkRef,
                writes: options.writes,
                ...(options.cowSize && { cow_size: options.cowSize }),
              },
              { debug: options.debug }
            );
            await setDatastoreState(forkRef, {
              attachedTo: options.attachTo,
              writes: options.writes,
              mounted: true,
              attachedAt: new Date().toISOString(),
            });
            outputService.success(
              t('commands.datastore.attach.attached', { ref: forkRef, machine: options.attachTo })
            );
          }
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
        await dispatch(
          'datastore_snapshot_create',
          host,
          { name: ref, snapshot: label },
          { debug: options.debug }
        );
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
        const raw = await dispatch(
          'datastore_snapshot_list',
          host,
          { name: ref },
          { debug: options.debug, capture: true }
        );
        outputService.print(parseCapturedJson<unknown>(raw), getOutputFormat());
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
        const record = await getDatastore(ref);
        await assertCommandPolicy(CMD.DATASTORE_RESIZE, undefined, ref);
        const host = await requireDatastoreHost(ref);
        await dispatch(
          'datastore_resize',
          host,
          { name: ref, size: options.size },
          { debug: options.debug }
        );
        await recordDatastore(ref, { ...record, size: options.size });
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

        // Detach-before-unlink (03 hygiene rule 1): a datastore with repo records
        // still pointing at it is not garbage, it is someone's data.
        const repos = await reposInDatastore(ref);
        if (repos.length > 0 && !options.force) {
          throw new ValidationError(
            t('errors.datastore.deleteHasRepos', { ref, repos: repos.join(', ') })
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
          // A failed detach fails the delete: never unlink a record whose pool is
          // still mounted somewhere (03 rule 1).
          await dispatch('datastore_detach', host, { name: ref }, { debug: options.debug });
          await setDatastoreState(ref, undefined);
          await dispatch('datastore_delete', host, { name: ref }, { debug: options.debug });
        }
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
