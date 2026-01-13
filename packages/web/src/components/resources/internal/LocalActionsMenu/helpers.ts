import type { MachineSSHCredentials } from '@/hooks/useMachineCredentials';
import {
  type ContainerParams,
  type ProtocolAction,
  protocolUrlService,
} from '@/services/protocolUrlService';
import { getElectronAPI, type VSCodeInstallations } from '@/types';

export type ContainerMenuAction = 'terminal' | 'logs' | 'stats';

export type ContainerModalData = {
  host: string;
  user: string;
  port: number;
  privateKey: string;
  known_hosts?: string;
  machineName: string;
  containerId: string;
  containerName?: string;
};

// Helper to determine error type from protocol check result
const determineErrorType = async (result: {
  error?: { type?: string; message: string };
}): Promise<'not-installed' | 'protocol-not-registered' | 'permission-denied'> => {
  try {
    const protocolStatus = await protocolUrlService.checkProtocolStatus();

    if (protocolStatus.available) {
      return 'permission-denied';
    }
    if (protocolStatus.errorReason?.includes('not registered')) {
      return 'protocol-not-registered';
    }
    return 'not-installed';
  } catch {
    if (result.error?.type === 'timeout') {
      return 'not-installed';
    }
    if (result.error?.message.includes('permission')) {
      return 'permission-denied';
    }
    return 'protocol-not-registered';
  }
};

// Helper to generate protocol URL for container actions
const generateContainerProtocolUrl = async (
  baseParams: { team: string; machine: string; repository: string },
  containerParams: ContainerParams,
  action?: ContainerMenuAction
): Promise<string> => {
  if (!action) {
    return protocolUrlService.generateDesktopUrl(baseParams, containerParams);
  }

  switch (action) {
    case 'logs':
      return protocolUrlService.generateContainerLogsUrl(baseParams, containerParams);
    case 'stats':
      return protocolUrlService.generateContainerStatsUrl(baseParams, containerParams);
    case 'terminal':
    default:
      return protocolUrlService.generateContainerTerminalUrl(baseParams, containerParams);
  }
};

// Helper to generate protocol URL for machine actions
const generateMachineProtocolUrl = async (
  baseParams: { team: string; machine: string; repository: string },
  action?: ProtocolAction
): Promise<string> => {
  if (!action) {
    return protocolUrlService.generateDesktopUrl(baseParams);
  }

  switch (action) {
    case 'terminal':
      return protocolUrlService.generateTerminalUrl(baseParams);
    case 'file-manager':
      return protocolUrlService.generateDesktopUrl(baseParams);
    case 'vscode':
      return protocolUrlService.generateVSCodeUrl(baseParams);
  }
};

// Helper to handle container actions in Electron
const handleElectronContainerAction = (
  containerAction: ContainerMenuAction | undefined,
  containerModalData: ContainerModalData,
  modals: {
    terminal: { open: (data: ContainerModalData) => void };
    logs: { open: (data: ContainerModalData) => void };
    stats: { open: (data: ContainerModalData) => void };
  }
): void => {
  switch (containerAction) {
    case 'terminal':
      modals.terminal.open(containerModalData);
      break;
    case 'logs':
      modals.logs.open(containerModalData);
      break;
    case 'stats':
      modals.stats.open(containerModalData);
      break;
    default:
      modals.terminal.open(containerModalData);
      break;
  }
};

// Helper to handle VS Code launch in Electron
export interface VSCodeLaunchParams {
  teamName: string;
  machine: string;
  repository?: string;
  creds: MachineSSHCredentials;
  remotePath: string;
  vsCodeSelection: {
    modal: {
      open: (data: {
        installations: VSCodeInstallations;
        creds: MachineSSHCredentials;
        remotePath: string;
      }) => void;
    };
  };
  message: { error: (msg: string) => void };
}

const handleElectronVSCode = async (params: VSCodeLaunchParams): Promise<void> => {
  const { teamName, machine, repository, creds, remotePath, vsCodeSelection, message } = params;
  const electronAPI = getElectronAPI();

  const installations = await electronAPI.vscode.getInstallations();
  const hasWindows = installations.windows !== null;
  const hasWSL = installations.wsl !== null;

  // If both are available and no preference is set, show selection dialog
  if (hasWindows && hasWSL) {
    const preference = await electronAPI.vscode.getPreference();
    if (!preference) {
      vsCodeSelection.modal.open({ installations, creds, remotePath });
      return;
    }
  }

  // Launch with auto-detected or preferred VS Code
  const result = await electronAPI.vscode.launch({
    teamName,
    machineName: machine,
    repositoryName: repository,
    host: creds.host,
    port: creds.port,
    user: creds.user,
    privateKey: creds.privateKey,
    known_hosts: creds.known_hosts,
    remotePath,
    datastore: creds.datastore,
  });

  if (!result.success) {
    message.error(result.error ?? 'shared:errors.vsCodeConnectionFailed');
  }
};

// Helper to handle machine actions in Electron
export interface ElectronMachineActionParams {
  action: ProtocolAction | undefined;
  creds: MachineSSHCredentials;
  machine: string;
  repository?: string;
  remotePath: string;
  teamName: string;
  terminalModal: {
    open: (data: {
      host: string;
      user: string;
      port: number;
      privateKey: string;
      known_hosts?: string;
      machineName: string;
      repositoryName?: string;
      initialPath?: string;
    }) => void;
  };
  fileBrowserModal: { open: (data: MachineSSHCredentials & { machineName: string }) => void };
  vsCodeSelection: VSCodeLaunchParams['vsCodeSelection'];
  message: { error: (msg: string) => void };
}

const handleElectronMachineAction = async (params: ElectronMachineActionParams): Promise<void> => {
  const {
    action,
    creds,
    machine,
    repository,
    remotePath,
    teamName,
    terminalModal,
    fileBrowserModal,
    vsCodeSelection,
    message,
  } = params;

  switch (action) {
    case 'terminal':
      terminalModal.open({
        host: creds.host,
        user: creds.user,
        port: creds.port,
        privateKey: creds.privateKey,
        known_hosts: creds.known_hosts,
        machineName: machine,
        repositoryName: repository,
        initialPath: remotePath,
      });
      break;

    case 'vscode':
      await handleElectronVSCode({
        teamName,
        machine,
        repository,
        creds,
        remotePath,
        vsCodeSelection,
        message,
      });
      break;

    case 'file-manager':
    default:
      fileBrowserModal.open({ ...creds, machineName: machine });
      break;
  }
};

// Helper to handle web protocol URL flow
export interface WebProtocolFlowParams {
  baseParams: { team: string; machine: string; repository: string };
  isContainerMenu: boolean;
  containerId?: string;
  containerName?: string;
  containerAction?: ContainerMenuAction;
  action?: ProtocolAction;
  setIsCheckingProtocol: (value: boolean) => void;
  installModal: {
    open: (errorType: 'not-installed' | 'protocol-not-registered' | 'permission-denied') => void;
  };
  message: { error: (msg: string) => void };
}

export const handleWebProtocolFlow = async (params: WebProtocolFlowParams): Promise<void> => {
  const {
    baseParams,
    isContainerMenu,
    containerId,
    containerName,
    containerAction,
    action,
    setIsCheckingProtocol,
    installModal,
    message,
  } = params;

  let url: string;
  try {
    if (isContainerMenu && containerId) {
      const containerParams: ContainerParams = {
        containerId,
        containerName,
        action: containerAction ?? 'terminal',
      };
      url = await generateContainerProtocolUrl(baseParams, containerParams, containerAction);
    } else {
      url = await generateMachineProtocolUrl(baseParams, action);
    }
  } catch (error) {
    console.error('Failed to generate protocol URL:', error);
    message.error('common:desktopConnectionFailed');
    return;
  }

  setIsCheckingProtocol(true);
  const result = await protocolUrlService.openUrl(url);
  setIsCheckingProtocol(false);

  if (!result.success) {
    const errorType = await determineErrorType(result);
    installModal.open(errorType);
  }
};

// Helper to handle Electron flow
export interface ElectronFlowParams {
  teamName: string;
  machine: string;
  repository?: string;
  isContainerMenu: boolean;
  containerId?: string;
  containerName?: string;
  containerAction?: ContainerMenuAction;
  action?: ProtocolAction;
  getCredentials: (teamName: string, machine: string) => Promise<MachineSSHCredentials>;
  containerTerminalModal: { open: (data: ContainerModalData) => void };
  containerLogsModal: { open: (data: ContainerModalData) => void };
  containerStatsModal: { open: (data: ContainerModalData) => void };
  terminalModal: ElectronMachineActionParams['terminalModal'];
  fileBrowserModal: ElectronMachineActionParams['fileBrowserModal'];
  vsCodeSelection: VSCodeLaunchParams['vsCodeSelection'];
  message: { error: (msg: string) => void };
}

export const handleElectronFlow = async (params: ElectronFlowParams): Promise<void> => {
  const {
    teamName,
    machine,
    repository,
    isContainerMenu,
    containerId,
    containerName,
    containerAction,
    action,
    getCredentials,
    containerTerminalModal,
    containerLogsModal,
    containerStatsModal,
    terminalModal,
    fileBrowserModal,
    vsCodeSelection,
    message,
  } = params;

  const creds = await getCredentials(teamName, machine);

  // Handle container menus in Electron
  if (isContainerMenu && containerId) {
    const containerModalData = {
      host: creds.host,
      user: creds.user,
      port: creds.port,
      privateKey: creds.privateKey,
      known_hosts: creds.known_hosts,
      machineName: machine,
      containerId,
      containerName,
    };

    handleElectronContainerAction(containerAction, containerModalData, {
      terminal: containerTerminalModal,
      logs: containerLogsModal,
      stats: containerStatsModal,
    });
    return;
  }

  // Handle machine/repository menus in Electron
  const remotePath = repository ? `${creds.datastore}/${repository}` : creds.datastore;

  await handleElectronMachineAction({
    action,
    creds,
    machine,
    repository,
    remotePath,
    teamName,
    terminalModal,
    fileBrowserModal,
    vsCodeSelection,
    message,
  });
};
