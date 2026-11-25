/**
 * `rdc server install`: the self-hosted account server (Elite) as a repo on one machine.
 *
 * THE STEPS, each recorded when done so a rerun skips it: machine, preflight, setup, dns, tls,
 * repo, template, keys, bws, licence, settings, image, up, wait, owner. Every value is asked for first
 * (on a terminal), so the run is unattended once it starts.
 *
 *   machine    a configured machine by name, else `--ip --user [--port] [--name]` registers the
 *              existing server or LAN device (`machine add`'s helper). Provisioning a cloud VM is
 *              `rdc machine provision`, which this never calls.
 *   preflight  sudo -n, architecture, ports 80/443, disk, clock skew.
 *   setup      `rdc machine setup` when renet is missing.
 *   dns        print the A/AAAA records and wait until both names resolve to the machine. A
 *              customer zone is never written; a name in a Rediacc-owned zone is, when
 *              CLOUDFLARE_API_TOKEN is set and the name does not resolve yet.
 *   tls        letsencrypt (HTTP-01), cloudflare (DNS-01 via the infra token) or byo (per-host
 *              `renet proxy cert install`).
 *   repo       `repo create` when absent; a repo this install did not create is refused.
 *   template   `repo admin template apply --template elite`, then the sha256 of the files it wrote
 *              (the baseline `upgrade` compares to find local edits).
 *   keys       every secret generated on the box into the repo's secrets.env.
 *   bws        only with `--bws-project <id>` (Rediacc's own installs): the secrets copied to that
 *              Bitwarden Secrets Manager project under opaque names; otherwise nothing leaves the box.
 *   licence    `--cert <file>` (must name the box's key), else the logged-in config's
 *              `POST /delegation/issue`. A cert is dropped into the box's cert inbox; the server
 *              decides it at its first boot, before `/health` answers.
 *
 * A REGISTERED ACCOUNT, before anything else: an on-premise server never runs on the anonymous FREE
 * licence (operator ruling 2026-11-23). Without `--cert` or `--offline`, a config with no account
 * login is refused before the machine is touched, naming `rdc subscription login` (a registered
 * account holds COMMUNITY or higher); `--licence free` is refused the same way. A rerun of an
 * unfinished install recorded on the free tier redoes its licence step; a finished one is pointed
 * at `rdc server licence <domain>`.
 *   settings   the domains, the image ref, ROOT_EMAIL and ON_PREMISE_MODE into secrets.env.
 *   image      pull inside the repo's daemon, or ship `--image-file` into images/.
 *   up         `repo up`.
 *   wait       `/health` answers 200 over a certificate covering the domain, then the inbox's
 *              answer to the licence step's drop is read (a rejection fails the step).
 *   owner      the owner account, created in this run; with a cert, its subscription must be the
 *              cert's, and its `GET /onprem/cert-status` must report the cert's id.
 *
 * AIR-GAPPED (`--offline --bundle <dir>`, a bundle `rdc server bundle` built online): the bundle is
 * verified before anything else and nothing reaches the network. preflight adds the bundle's
 * architecture and the tools renet's offline setup assumes; setup loads the proxy image into the
 * machine's Docker, then runs `machine setup --offline`; dns prints the LAN records and never waits;
 * tls is `byo` only; licence stops after writing the box's request (AwaitingCert) and a rerun with
 * `--cert` (minted online by `rdc server licence mint`) resumes; settings add ELITE_OFFLINE=1; image
 * ships the bundle's tars through repo sync.
 *
 * On a terminal the one-time recovery bundle is printed at the end; it is never logged and never
 * part of `--output json`. Without a terminal the closing line names `rdc server backup`.
 */

import { isIPv4 } from 'node:net';
import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { t } from '../../i18n/index.js';
import type { MachineConfig } from '../../types/index.js';
import { ValidationError } from '../../utils/errors.js';
import { promptRequiresTTY, type ServerPrompts } from '../../utils/server-prompts.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { addExistingMachine } from '../machine/add-existing.js';
import {
  generateKeys,
  locateRepo,
  type RepoOnBox,
  rdcMust,
  readBundle,
  ServerError,
  setBoxEnv,
} from './box.js';
import { type BundleManifest, serverImageOf } from './bundle/manifest.js';
import {
  AwaitingCert,
  assertOfflineOptions,
  loadProxyImage,
  offlinePreflight,
  uploadBundleImages,
  writeCertRequest,
} from './bundle/offline.js';
import { verifyBundle } from './bundle/verify.js';
import { backupToBws } from './bws-backup.js';
import {
  boxTarget,
  DEFAULT_IMAGE,
  DEFAULT_REPO,
  DEFAULT_SIZE,
  imageTag,
  machineAddresses,
  placeImage,
  storeDomainOf,
  TEMPLATE_NAME,
} from './common.js';
import { dnsRecords, printDnsRecords, waitForDns, writeOwnedRecords } from './dns.js';
import { createOwner, waitHealthy } from './http.js';
import {
  INSTALL_STEPS,
  type InstallOptions,
  type InstallResult,
  type InstallStep,
} from './install-options.js';
import { defaultMachineName, loggedInEmail, type Plan } from './install-plan.js';
import {
  awaitInboxResult,
  confirmCertId,
  dropCert,
  type LicenceResult,
  obtainLicence,
  type PendingDrop,
  readLiveCert,
} from './licence.js';
import { runPreflight } from './preflight.js';
import {
  ensureStateDir,
  loadOwner,
  loadRecord,
  ownerFile,
  recordFile,
  type ServerRecord,
} from './state.js';
import { writeTemplateSums } from './template-guard.js';
import { applyTls } from './tls.js';
import type { LicenceMode, ServerDeps, TlsMethod } from './types.js';

const DEFAULT_LICENCE: LicenceMode = 'auto';

export class ServerInstall {
  private record!: ServerRecord;
  private plan!: Plan;
  private where?: RepoOnBox;
  private boxKey = '';
  private licenceResult?: LicenceResult;
  /** The licence step's inbox drop, read back by the wait step. Unset on a rerun that skipped it. */
  private pendingDrop?: PendingDrop;
  /** Set by the preflight; the setup step runs `machine setup` only when it is true. */
  private renetMissing: boolean | undefined;
  /** The verified `--bundle` of an offline install. */
  private manifest?: BundleManifest;

  constructor(
    private readonly opts: InstallOptions,
    private readonly deps: ServerDeps,
    private readonly prompts: ServerPrompts
  ) {}

  /** Prompts only on a terminal and only without --yes; otherwise a missing value is refused by its flag. */
  private get interactive(): boolean {
    return this.deps.isTTY() && this.opts.yes !== true && this.opts.machineReadable !== true;
  }

  /** An offline box has no resolver to wait on: the LAN records are printed and the run goes on. */
  private get noDnsWait(): boolean {
    return this.opts.dnsWait === false || this.opts.offline === true;
  }

  async run(): Promise<InstallResult> {
    this.plan = await this.resolvePlan();
    ensureStateDir();
    this.record = this.openRecord(loadRecord(this.plan.domain));
    await this.save();

    for (const step of INSTALL_STEPS) {
      // keys always runs: it is idempotent on the box and the licence step needs its public key.
      if (this.record.steps[step] && step !== 'keys') {
        outputService.info(t('commands.server.install.skipped', { step }));
        continue;
      }
      outputService.info(t('commands.server.install.step', { step }));
      await this.runStep(step);
      this.record.steps[step] = new Date(this.deps.now()).toISOString();
      await this.save();
    }
    await this.closing();
    return {
      domain: this.plan.domain,
      storeDomain: this.plan.storeDomain,
      machine: this.plan.machine,
      repo: this.plan.repo,
      owner: this.plan.owner,
      tier: this.record.licence === 'cert' ? 'licensed' : 'free',
      ...(this.record.subscriptionId ? { subscriptionId: this.record.subscriptionId } : {}),
      image: this.plan.image,
      tls: this.plan.tls,
    };
  }

  /** The record this run continues (or starts), refused on another machine or a finished free-tier install. */
  private openRecord(earlier: ServerRecord | undefined): ServerRecord {
    if (earlier && earlier.machine !== this.plan.machine) {
      throw new ValidationError(
        t('commands.server.errors.otherMachine', {
          domain: this.plan.domain,
          machine: earlier.machine,
        })
      );
    }
    if (earlier?.licence === 'free') {
      if (earlier.steps.owner) {
        throw new ValidationError(
          t('commands.server.errors.freeTierInstalled', { domain: this.plan.domain })
        );
      }
      // An unfinished install recorded on the free tier: its licence step runs again, for a cert.
      delete earlier.steps.licence;
      delete earlier.licence;
    }
    const record = earlier ?? {
      domain: this.plan.domain,
      storeDomain: this.plan.storeDomain,
      machine: this.plan.machine,
      repo: this.plan.repo,
      steps: {},
    };
    Object.assign(record, {
      storeDomain: this.plan.storeDomain,
      repo: this.plan.repo,
      owner: this.plan.owner,
      tls: this.plan.tls,
      image: this.plan.image,
      ...(this.opts.tlsCa ? { tlsCa: this.opts.tlsCa } : {}),
    });
    return record;
  }

  private async save(): Promise<void> {
    await this.deps.writePrivate(
      recordFile(this.record.domain),
      `${JSON.stringify(this.record, null, 2)}\n`
    );
  }

  // ── values, asked in order: machine, domain, store domain, TLS, owner ─────────────────────

  /** The anonymous FREE licence never runs an on-premise server: refused before any machine change. */
  private assertRegisteredAccount(): void {
    if (this.opts.licence === 'free') {
      throw new ValidationError(t('commands.server.errors.licenceFreeRefused'));
    }
    // A cert names its subscription, and an offline run carries one minted online by an account.
    if (this.opts.cert || this.opts.offline) return;
    if (!this.deps.hasAccountLogin()) {
      throw new ValidationError(t('commands.server.errors.accountRequired'));
    }
  }

  private async resolvePlan(): Promise<Plan> {
    this.assertRegisteredAccount();
    assertOfflineOptions(this.opts);
    if (this.opts.offline && this.opts.bundle && this.opts.signer) {
      this.manifest = await verifyBundle(this.deps, this.opts.bundle, this.opts.signer);
    }
    const { name: machine, config: machineConfig } = await this.resolveMachine();
    const domain = await this.value('--domain', this.opts.domain, () =>
      this.prompts.text(t('commands.server.prompts.domain'))
    );
    const storeDomain = await this.withDefault(this.opts.storeDomain, storeDomainOf(domain), (d) =>
      this.prompts.text(t('commands.server.prompts.storeDomain'), d)
    );
    const tls = await this.resolveTls();
    const owner = await this.withDefault(this.opts.owner, loggedInEmail(), (d) =>
      this.prompts.text(t('commands.server.prompts.owner'), d)
    );
    if (!owner) throw promptRequiresTTY('--owner');
    return {
      machine,
      machineConfig,
      domain,
      storeDomain,
      repo: this.opts.repo ?? DEFAULT_REPO,
      size: this.opts.size ?? DEFAULT_SIZE,
      owner,
      tls,
      licence: this.opts.licence ?? DEFAULT_LICENCE,
      image: this.manifest ? serverImageOf(this.manifest).ref : (this.opts.image ?? DEFAULT_IMAGE),
    };
  }

  /** A flag's value, else the prompt (offering the default) on a terminal, else the default. */
  private withDefault<T extends string | undefined>(
    given: string | undefined,
    fallback: T,
    ask: (fallback: T) => Promise<string>
  ): Promise<string | T> {
    if (given) return Promise.resolve(given);
    return this.interactive ? ask(fallback) : Promise.resolve(fallback);
  }

  private async resolveTls(): Promise<TlsMethod> {
    let fallback: TlsMethod = this.opts.offline ? 'byo' : 'letsencrypt';
    if (this.opts.cfToken) fallback = 'cloudflare';
    if (this.opts.tlsCert) fallback = 'byo';
    const tls = this.opts.tls ?? (this.interactive ? await this.prompts.tls(fallback) : fallback);
    if (tls === 'byo' && (!this.opts.tlsCert || !this.opts.tlsKey)) {
      throw new ValidationError(t('commands.server.tls.byoNeedsPair'));
    }
    if (tls === 'cloudflare' && !this.opts.cfToken) {
      this.opts.cfToken = await this.value('--cf-token', undefined, () =>
        this.prompts.text(t('commands.server.prompts.cfToken'))
      );
    }
    return tls;
  }

  /** A flag's value, else the prompt on a terminal, else the TTY refusal naming the flag. */
  private value(
    flag: string,
    given: string | undefined,
    ask: () => Promise<string>
  ): Promise<string> {
    if (given) return Promise.resolve(given);
    if (!this.interactive) return Promise.reject(promptRequiresTTY(flag));
    return ask();
  }

  private async resolveMachine(): Promise<{ name: string; config: MachineConfig }> {
    const configured = await configService.listMachines();
    const pick = (name: string) => {
      const config = configured.find((m) => m.name === name)?.config;
      if (!config) {
        throw new ValidationError(t('commands.server.errors.machineUnknown', { machine: name }));
      }
      return { name, config };
    };

    if (this.opts.machine) return pick(this.opts.machine);
    if (this.opts.ip) {
      if (!this.opts.user) throw promptRequiresTTY('--user');
      return this.registerExisting(
        this.opts.name ?? defaultMachineName(this.opts.ip),
        this.opts.ip,
        this.opts.user,
        this.opts.port
      );
    }
    if (!this.interactive) throw promptRequiresTTY('[machine] | --ip --user');
    const answer = await this.prompts.machine(configured.map((m) => m.name));
    if (answer.kind === 'existing') return pick(answer.name);
    return this.registerExisting(answer.name, answer.ip, answer.user, String(answer.port));
  }

  /** Register a brought machine; one already registered under that name must be the same address. */
  private async registerExisting(
    name: string,
    ip: string,
    user: string,
    port?: string
  ): Promise<{ name: string; config: MachineConfig }> {
    const existing = (await configService.listMachines()).find((m) => m.name === name);
    if (existing) {
      if (existing.config.ip !== ip) {
        throw new ValidationError(
          t('commands.server.errors.machineNameTaken', { machine: name, ip: existing.config.ip })
        );
      }
      return { name, config: existing.config };
    }
    const config = await addExistingMachine(name, { ip, user, ...(port ? { port } : {}) });
    return { name, config };
  }

  // ── the steps ─────────────────────────────────────────────────────────────────────────────

  private get repoRef(): string {
    return `${this.plan.repo}@${this.plan.machine}`;
  }

  private async box(): Promise<RepoOnBox> {
    this.where ??= await locateRepo(this.plan.repo, this.plan.machine);
    return this.where;
  }

  private async runStep(step: InstallStep): Promise<void> {
    try {
      await this.steps[step]();
    } catch (error) {
      if (error instanceof ServerError || error instanceof ValidationError) {
        error.message = `${step}: ${error.message}`;
      }
      throw error;
    }
  }

  private readonly steps: Record<InstallStep, () => Promise<void>> = {
    preflight: async () => {
      const facts = await runPreflight(this.deps, {
        machine: this.plan.machine,
        datastore: this.plan.machineConfig.datastore ?? WK_DATASTORE_PATH,
        size: this.plan.size,
      });
      this.renetMissing = !facts.renet;
      if (this.manifest) {
        await offlinePreflight(this.deps, this.plan.machine, facts, this.manifest);
      }
    },
    setup: async () => {
      if (this.manifest && this.opts.bundle) {
        await loadProxyImage(this.deps, this.plan.machine, this.opts.bundle, this.manifest);
      }
      if (this.renetMissing) {
        const offline = this.opts.offline ? ['--offline'] : [];
        await rdcMust(this.deps, ['machine', 'setup', this.plan.machine, ...offline]);
      }
    },
    dns: async () => {
      const addresses = machineAddresses(this.plan.machineConfig);
      const records = dnsRecords([this.plan.domain, this.plan.storeDomain], addresses);
      printDnsRecords(records);
      if (!this.opts.offline) await writeOwnedRecords(this.deps, records);
      if (this.noDnsWait || records.length === 0) {
        outputService.info(t('commands.server.dns.notWaiting'));
        return;
      }
      await waitForDns(this.deps, records);
    },
    tls: async () => {
      const config = await configService.getLocalConfig();
      const m = this.plan.machineConfig;
      await applyTls(this.deps, {
        method: this.plan.tls,
        machine: this.plan.machine,
        hosts: [this.plan.domain, this.plan.storeDomain],
        certEmail: this.opts.certEmail ?? (config.certEmail ? undefined : this.plan.owner),
        cfToken: this.opts.cfToken,
        tlsCert: this.opts.tlsCert,
        tlsKey: this.opts.tlsKey,
        ...(!m.infra && isIPv4(m.ip) ? { publicIPv4: m.ip } : {}),
      });
    },
    repo: async () => {
      const existing = await configService.getRepository(this.plan.repo);
      if (existing) {
        if (!this.record.repoCreated) {
          throw new ServerError(
            t('commands.server.errors.repoExists', {
              repo: this.plan.repo,
              machine: this.plan.machine,
            })
          );
        }
        return;
      }
      this.record.repoCreated = true;
      await this.save();
      try {
        await rdcMust(this.deps, [
          'repo',
          'create',
          this.plan.repo,
          '-m',
          this.plan.machine,
          '--size',
          this.plan.size,
        ]);
      } catch (error) {
        // The create asks for the Terms of Service; a rerun with the root flag answers it.
        if (error instanceof ServerError) {
          throw new ServerError(`${error.message}. ${t('commands.server.install.termsHint')}`);
        }
        throw error;
      }
    },
    template: async () => {
      await rdcMust(this.deps, [
        'repo',
        'admin',
        'template',
        'apply',
        this.repoRef,
        '--template',
        TEMPLATE_NAME,
      ]);
      await writeTemplateSums(this.deps, await this.box());
    },
    keys: async () => {
      this.boxKey = await generateKeys(this.deps, await this.box());
    },
    bws: async () => {
      if (!this.opts.bwsProject) {
        outputService.info(t('commands.server.bws.skipped'));
        return;
      }
      await backupToBws(this.deps, await this.box(), {
        domain: this.plan.domain,
        projectId: this.opts.bwsProject,
        rotate: this.opts.rotate === true,
      });
    },
    licence: async () => {
      if (this.opts.offline && !this.opts.cert) {
        // Two trips: the request goes out, a cert minted online comes back through `--cert`.
        const file = await writeCertRequest(this.deps, this.plan.domain, this.boxKey);
        throw new AwaitingCert(
          t('commands.server.offline.awaitingCert', { file, domain: this.plan.domain })
        );
      }
      this.licenceResult = await obtainLicence(this.deps, {
        mode: this.plan.licence,
        certFile: this.opts.cert,
        boxPublicKey: this.boxKey,
      });
      this.pendingDrop = await dropCert(this.deps, await this.box(), this.licenceResult.signed);
      if (Object.keys(this.licenceResult.env).length > 0) {
        await setBoxEnv(this.deps, await this.box(), this.licenceResult.env);
      }
      this.record.licence = 'cert';
      this.record.subscriptionId = this.licenceResult.subscriptionId;
    },
    settings: async () => {
      await setBoxEnv(this.deps, await this.box(), {
        ELITE_DOMAIN: this.plan.domain,
        ELITE_STORE_DOMAIN: this.plan.storeDomain,
        ELITE_IMAGE: this.plan.image,
        TAG: imageTag(this.plan.image),
        ...(this.opts.offline ? { ELITE_OFFLINE: '1' } : {}),
        ROOT_EMAIL: this.plan.owner,
        // Every installed box is an on-premise server: terms gate off, on-prem licence route.
        ON_PREMISE_MODE: 'true',
        // byo: the pair is installed per host, so the labels tell the router to skip its resolver.
        ...(this.plan.tls === 'byo' ? { ELITE_TLS: 'provided' } : {}),
      });
    },
    image: async () => {
      if (this.manifest && this.opts.bundle) {
        await uploadBundleImages(this.deps, await this.box(), this.opts.bundle);
        return;
      }
      await placeImage(
        this.deps,
        await this.box(),
        this.plan.image,
        this.opts.imageFile,
        this.opts.localImage
      );
    },
    up: async () => {
      await rdcMust(this.deps, ['repo', 'up', this.repoRef]);
    },
    wait: async () => {
      await waitHealthy(this.deps, await this.target());
      if (this.pendingDrop) {
        await awaitInboxResult(this.deps, await this.box(), this.pendingDrop.requestId);
      }
    },
    owner: async () => {
      const saved = loadOwner(this.plan.domain);
      const creds = {
        email: this.plan.owner,
        password: saved?.email === this.plan.owner ? saved.password : this.deps.secret(),
      };
      // Saved before the account exists, so a crash between the two never loses the password.
      await this.deps.writePrivate(ownerFile(this.plan.domain), `${JSON.stringify(creds)}\n`);
      const target = await this.target();
      await createOwner(this.deps, target, creds, this.record.subscriptionId);
      // A rerun that skipped the licence step confirms the cert the box holds on disk.
      const certId =
        this.pendingDrop?.certId ?? (await readLiveCert(this.deps, await this.box()))?.certId;
      if (!certId) {
        throw new ServerError(
          t('commands.server.licence.confirmMismatch', { expected: '-', actual: '-' })
        );
      }
      await confirmCertId(this.deps, target, this.plan.domain, certId);
    },
  };

  private target() {
    const address = this.noDnsWait ? machineAddresses(this.plan.machineConfig)[0] : undefined;
    return boxTarget(this.deps, this.record, address);
  }

  /** The one-time recovery print on a terminal; otherwise the line that names `server backup`. */
  private async closing(): Promise<void> {
    outputService.success(t('commands.server.install.done', { domain: this.plan.domain }));
    const printable = this.deps.isTTY() && this.opts.machineReadable !== true;
    if (this.record.steps.bundle || !printable) {
      outputService.info(
        t('commands.server.install.backupHint', {
          domain: this.plan.domain,
          ownerFile: ownerFile(this.plan.domain),
        })
      );
      return;
    }
    const bundle = await readBundle(this.deps, await this.box(), this.plan.domain);
    const owner = loadOwner(this.plan.domain);
    this.deps.stdout(`\n${t('commands.server.bundle.once')}\n\n${bundle}`);
    if (owner) {
      this.deps.stdout(
        `\n${t('commands.server.bundle.owner', { email: owner.email, password: owner.password })}\n`
      );
    }
    this.record.steps.bundle = new Date(this.deps.now()).toISOString();
    await this.save();
  }
}
