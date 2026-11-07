import { t } from '../../i18n/index.js';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { assertBackupStoreUniverse } from '../backup/backup-store-universe.js';
import type { configService } from '../config/config-resources.js';
import { acquireRemoteRenet, verifyMachineSetup } from '../renet/renet-execution.js';
import {
  isRepoProvisioningFunction,
  isRestoreLicenseFunction,
} from '../renet/renet-license-contract.js';
import { renetMayUpload } from '../renet/renet-upload-decision.js';
import {
  ensureRepoLicenseForProvisioning,
  ensureRepoLicenseForRestore,
  maybeRefreshRepoLicenses,
} from './license-recovery.js';
import { renetAccessFor } from './renet-function-access.js';
import { timedStep } from './timed-step.js';
import type { ExecuteOptions } from './types.js';

/**
 * Provision renet, verify machine setup, and handle pre-flight licensing.
 * Returns the remote renet path and whether the binary was uploaded.
 */
export async function provisionAndVerify(
  config: Awaited<ReturnType<typeof configService.getLocalConfig>>,
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
  sshPrivateKey: string,
  options: ExecuteOptions,
  sftp: SFTPClient,
  cliSteps: { name: string; duration_ms: number; startedAtMs?: number }[],
  quiet: boolean
): Promise<{ remoteRenetPath: string; renetUploaded: boolean; routerRefreshDue: boolean }> {
  const provStart = Date.now();
  // The dispatched function decides whether this run may replace the machine's renet (RENET_FUNCTION_ACCESS).
  const access = renetAccessFor(options.functionName, options.params);
  const provisionFn = () =>
    acquireRemoteRenet(
      access,
      config,
      machine,
      sshPrivateKey,
      {
        debug: options.debug,
        skipRouterRestart: options.skipRouterRestart,
        // The router refresh waits for the runtime converge pass (executeSession).
        deferRouterRefresh: true,
        machineName: options.machineName,
      },
      sftp
    );
  const {
    remotePath: remoteRenetPath,
    uploaded: renetUploaded,
    routerRefreshDue,
  } = quiet || !renetMayUpload(access)
    ? await provisionFn()
    : await timedStep(t('timing.step.provisioning'), 'timing.step.renetProvisioned', provisionFn);
  cliSteps.push({
    name: 'renet_provision',
    duration_ms: Date.now() - provStart,
    startedAtMs: provStart,
  });

  const verifyFn = () =>
    verifyMachineSetup(
      machine,
      sshPrivateKey,
      { ...options, functionName: options.functionName },
      sftp
    );
  const runVerify = async () => {
    const verifyStart = Date.now();
    if (quiet) {
      await verifyFn();
    } else {
      await timedStep(t('timing.step.verifying'), 'timing.step.machineVerified', verifyFn);
    }
    cliSteps.push({
      name: 'machine_verify',
      duration_ms: Date.now() - verifyStart,
      startedAtMs: verifyStart,
    });
  };

  if (isRepoProvisioningFunction(options.functionName)) {
    // License issuance only needs the provisioned renet binary, not the verified machine setup, run it concurrently with verification.
    const runLicense = async () => {
      const licStart = Date.now();
      await timedStep(t('timing.step.activating'), 'timing.step.licenseActivated', () =>
        ensureRepoLicenseForProvisioning(options, machine, sshPrivateKey, remoteRenetPath, sftp)
      );
      cliSteps.push({
        name: 'license',
        duration_ms: Date.now() - licStart,
        startedAtMs: licStart,
      });
    };
    await Promise.all([runVerify(), runLicense()]);
  } else if (isRestoreLicenseFunction(options.functionName)) {
    // Sequential, unlike the provisioning arm above, and the difference is not stylistic. That arm's concurrency is safe because its pre-flight only needs the renet binary; this one runs a licence SCAN on the target (the skip probe) over the same shared SFTP session `verifyMachineSetup` is using, and a restore target is by construction a machine nobody has verified yet. Verify
    // first, then license: a DR restore or chunk-store browse (backup_restore, backup_browse_at) is not a path where a second of wall clock is worth an interleaving hazard.
    await runVerify();
    const licStart = Date.now();
    await timedStep(t('timing.step.activating'), 'timing.step.licenseActivated', () =>
      ensureRepoLicenseForRestore(options, machine, sshPrivateKey, remoteRenetPath, sftp)
    );
    cliSteps.push({ name: 'license', duration_ms: Date.now() - licStart, startedAtMs: licStart });
  } else {
    await runVerify();
  }

  await maybeRefreshRepoLicenses(
    machine,
    options.machineName,
    sshPrivateKey,
    remoteRenetPath,
    sftp
  );

  // After the licence pre-flight and refresh, so a licence this config just installed counts.
  await assertBackupStoreUniverse(
    options.functionName,
    options.machineName,
    options.params ?? {},
    sftp
  );

  return { remoteRenetPath, renetUploaded, routerRefreshDue: routerRefreshDue === true };
}
