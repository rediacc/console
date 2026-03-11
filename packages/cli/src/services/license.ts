import { DEFAULTS } from '@rediacc/shared/config';
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import type { MachineConfig } from '../types/index.js';
import { getSubscriptionTokenState } from './subscription-auth.js';

const LICENSE_DIR = '/var/lib/rediacc/license';
const LICENSE_FILE = `${LICENSE_DIR}/license.json`;
const SUBSCRIPTION_FILE = `${LICENSE_DIR}/subscription.json`;
const REPO_LICENSE_DIR = `${LICENSE_DIR}/repos`;
const CLIENT_MACHINE_ID_PATH = '/etc/machine-id';
const DEFAULT_DATASTORE = '/mnt/rediacc';

async function readRemoteMachineId(sftp: SFTPClient, remoteRenetPath?: string): Promise<string> {
  const command = remoteRenetPath
    ? `sudo ${remoteRenetPath} machine-id 2>/dev/null || cat /etc/machine-id`
    : 'cat /etc/machine-id';
  return (await sftp.exec(command)).trim();
}

async function readLocalMachineId(): Promise<string> {
  const { readFile } = await import('node:fs/promises');
  return (await readFile(CLIENT_MACHINE_ID_PATH, 'utf-8')).trim();
}

async function readRepoIdentity(
  sftp: SFTPClient,
  datastore: string,
  repositoryGuid: string
): Promise<{ luksUuid?: string; storageFingerprint?: string }> {
  const repoPath = `${datastore}/repositories/${repositoryGuid}`;
  const luksUuid = (
    await sftp.exec(`sudo sh -lc 'cryptsetup luksUUID "${repoPath}" 2>/dev/null || true'`)
  ).trim();
  if (luksUuid) {
    return { luksUuid };
  }

  const storageFingerprint = (
    await sftp.exec(
      `sudo sh -lc 'if [ -e "${repoPath}" ]; then stat -c "%F:%d:%i:%s:%Y" "${repoPath}"; fi'`
    )
  ).trim();
  return storageFingerprint ? { storageFingerprint } : {};
}

async function readRepoSizeGb(
  sftp: SFTPClient,
  datastore: string,
  repositoryGuid: string
): Promise<number> {
  const repoPath = `${datastore}/repositories/${repositoryGuid}`;
  const bytesOutput = await sftp.exec(
    `sudo sh -lc 'if [ -e "${repoPath}" ]; then stat -c %s "${repoPath}" 2>/dev/null; else echo 0; fi'`
  );
  const bytes = Number.parseInt(bytesOutput.trim(), 10);
  return Math.max(1, Math.ceil((Number.isFinite(bytes) ? bytes : 0) / (1024 * 1024 * 1024)));
}

async function issueAndWriteLicense(
  sftp: SFTPClient,
  serverUrl: string,
  token: string,
  machineId: string
): Promise<boolean> {
  const resp = await fetch(`${serverUrl}/account/api/v1/licenses/issue`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ machineId }),
  });

  if (!resp.ok) {
    return false;
  }

  const { license, signedBlob } = (await resp.json()) as {
    license: unknown;
    signedBlob: unknown;
  };

  await sftp.exec(`sudo mkdir -p ${LICENSE_DIR}`);
  await sftp.execStreaming(`sudo tee ${LICENSE_FILE} > /dev/null`, {
    stdin: JSON.stringify(license, null, 2),
  });
  await sftp.execStreaming(`sudo tee ${SUBSCRIPTION_FILE} > /dev/null`, {
    stdin: JSON.stringify(signedBlob, null, 2),
  });
  await sftp.exec(`sudo chmod 640 ${LICENSE_FILE} ${SUBSCRIPTION_FILE}`);
  return true;
}

export async function issueMachineLicense(
  machine: MachineConfig,
  sshPrivateKey: string,
  remoteRenetPath?: string
): Promise<boolean> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') return false;

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });

  try {
    await sftp.connect();
    const machineId = await readRemoteMachineId(sftp, remoteRenetPath);
    if (!machineId) return false;

    return await issueAndWriteLicense(
      sftp,
      tokenState.serverUrl,
      tokenState.token.token,
      machineId
    );
  } finally {
    sftp.close();
  }
}

export async function issueRepoLicense(
  machine: MachineConfig,
  sshPrivateKey: string,
  params: {
    repositoryGuid: string;
    grandGuid?: string;
    kind: 'grand' | 'fork';
    requestedSizeGb: number;
    luksUuid?: string;
    storageFingerprint?: string;
  },
  remoteRenetPath?: string
): Promise<boolean> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') return false;

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });

  try {
    await sftp.connect();
    const [machineId, clientMachineId] = await Promise.all([
      readRemoteMachineId(sftp, remoteRenetPath),
      readLocalMachineId(),
    ]);
    if (!machineId || !clientMachineId) return false;

    const resp = await fetch(`${tokenState.serverUrl}/account/api/v1/licenses/issue-repo`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${tokenState.token.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        machineId,
        clientMachineId,
        repositoryGuid: params.repositoryGuid,
        grandGuid: params.grandGuid,
        kind: params.kind,
        requestedSizeGb: params.requestedSizeGb,
        luksUuid: params.luksUuid,
        storageFingerprint: params.storageFingerprint,
      }),
    });

    if (!resp.ok) return false;

    const { license } = (await resp.json()) as { license: unknown };
    await sftp.exec(`sudo mkdir -p ${REPO_LICENSE_DIR}`);
    const repoLicenseFile = `${REPO_LICENSE_DIR}/${params.repositoryGuid}.json`;
    await sftp.execStreaming(`sudo tee ${repoLicenseFile} > /dev/null`, {
      stdin: JSON.stringify(license, null, 2),
    });
    await sftp.exec(`sudo chmod 640 ${repoLicenseFile}`);
    return true;
  } finally {
    sftp.close();
  }
}

export async function refreshRepoLicenseIdentity(
  machine: MachineConfig,
  sshPrivateKey: string,
  params: {
    repositoryGuid: string;
    grandGuid?: string;
    kind: 'grand' | 'fork';
    requestedSizeGb?: number;
  },
  remoteRenetPath?: string
): Promise<boolean> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') return false;

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });

  try {
    await sftp.connect();
    const datastore = machine.datastore ?? DEFAULT_DATASTORE;
    const [identity, requestedSizeGb] = await Promise.all([
      readRepoIdentity(sftp, datastore, params.repositoryGuid),
      params.requestedSizeGb
        ? Promise.resolve(params.requestedSizeGb)
        : readRepoSizeGb(sftp, datastore, params.repositoryGuid),
    ]);
    return issueRepoLicense(
      machine,
      sshPrivateKey,
      {
        ...params,
        requestedSizeGb,
        ...identity,
      },
      remoteRenetPath
    );
  } finally {
    sftp.close();
  }
}
