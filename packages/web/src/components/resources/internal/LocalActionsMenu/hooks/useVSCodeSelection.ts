import { useCallback } from 'react';
import { useDialogState } from '@/hooks/useDialogState';
import type { MachineSSHCredentials } from '@/hooks/useMachineCredentials';
import { isElectron, getElectronAPI, type VSCodeInstallations } from '@/types';

interface VSCodeSelectionData {
  installations: VSCodeInstallations;
  creds: MachineSSHCredentials;
  remotePath: string;
}

interface UseVSCodeSelectionParams {
  teamName: string;
  machine: string;
  repository?: string;
  onError: (error: string) => void;
}

export function useVSCodeSelection({
  teamName,
  machine,
  repository,
  onError,
}: UseVSCodeSelectionParams) {
  const modal = useDialogState<VSCodeSelectionData>();

  const handleSelection = useCallback(
    async (preferredType: 'windows' | 'wsl', remember: boolean) => {
      if (!isElectron()) return;

      const modalData = modal.state.data;
      if (!modalData) return;

      const electronAPI = getElectronAPI();

      if (remember) {
        await electronAPI.vscode.setPreference(preferredType);
      }

      const result = await electronAPI.vscode.launch({
        teamName,
        machineName: machine,
        repositoryName: repository,
        host: modalData.creds.host,
        port: modalData.creds.port,
        user: modalData.creds.user,
        privateKey: modalData.creds.privateKey,
        known_hosts: modalData.creds.known_hosts,
        remotePath: modalData.remotePath,
        datastore: modalData.creds.datastore,
        preferredType,
      });

      if (!result.success) {
        onError(result.error ?? 'common:vscodeConnectionFailed');
      }
    },
    [teamName, machine, repository, modal.state.data, onError]
  );

  return {
    modal,
    handleSelection,
  };
}
