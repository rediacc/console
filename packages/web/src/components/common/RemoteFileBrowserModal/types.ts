import type { RemoteFile as BaseRemoteFile } from '@rediacc/shared/queue-vault/storage-browser';

export interface RemoteFile extends BaseRemoteFile {
  originalGuid?: string;
  repositoryName?: string;
  repositoryTag?: string;
  isUnmapped?: boolean;
}

export interface RemoteFileBrowserModalProps {
  open: boolean;
  onCancel: () => void;
  machineName: string;
  teamName: string;
  bridgeName: string;
  onPullSelected?: (files: RemoteFile[], destination: string) => void;
  onClose?: () => void;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
}

export type AdditionalVaultData = Record<string, unknown>;

export interface SourceOption {
  value: string;
  label: string;
  type: 'machine' | 'storage';
}
