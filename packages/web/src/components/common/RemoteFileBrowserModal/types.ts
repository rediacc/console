export interface RemoteFile {
  name: string;
  originalGuid?: string;
  repositoryName?: string;
  repositoryTag?: string;
  isUnmapped?: boolean;
  size: number;
  isDirectory: boolean;
  modTime?: string;
  mimeType?: string;
  path?: string;
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
